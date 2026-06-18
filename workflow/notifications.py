"""
Approval event notification orchestrator.

Public API:
    notify_approval_submitted(approval_id)
    notify_approval_step_advanced(approval_id, new_step_number)
    notify_approval_completed(approval_id)
    notify_approval_rejected(approval_id, rejecting_step_number)
    notify_approval_cancelled(approval_id)
    notify_approval_sla_breach(approval_step_id)
"""
import logging

from django.contrib.auth.models import User

from workflow.models import Approval, ApprovalStep, GlobalApprovalSettings
from workflow.views import _MODEL_TO_MODULE_KEY, APPROVABLE_LABELS
from core.localized_emails import (
    send_approval_submitted_email,
    send_approval_completed_email,
    send_approval_rejected_email,
    send_approval_step_advanced_email,
    send_approval_sla_breach_email,
)
from core.models import Notification

logger = logging.getLogger('workflow.notifications')


def _build_action_url(approval_id: int) -> str:
    """Build a deep-link URL to the approval detail page."""
    from django.conf import settings
    base = getattr(settings, 'FRONTEND_URL', getattr(settings, 'SITE_URL', ''))
    base = base.rstrip('/')
    return f'{base}/workflow/approvals/{approval_id}/'


def _resolve_module_settings(approval: Approval):
    """Return GlobalApprovalSettings for this approval's content type, or None."""
    model_name = approval.content_type.model  # lowercase
    module_key = _MODEL_TO_MODULE_KEY.get(model_name, model_name.capitalize())
    return GlobalApprovalSettings.objects.filter(module=module_key).first()


def _resolve_step_approvers(approval_step: ApprovalStep) -> list:
    """Return active Users who are effective members of the step's approver_group."""
    group = approval_step.approver_group
    if group is None:
        return []
    effective_ids = group.effective_user_ids()
    return list(User.objects.filter(pk__in=effective_ids, is_active=True))


def _resolve_requester(approval: Approval):
    """Return the User who requested this approval, or None."""
    return approval.requested_by


def _get_document_label(approval: Approval) -> str:
    model_name = approval.content_type.model
    return APPROVABLE_LABELS.get(model_name, model_name)


def notify_approval_submitted(approval_id: int) -> None:
    """
    Notify the step-1 approver group that a new document has been submitted.
    Respects GlobalApprovalSettings.send_notifications flag.
    """
    try:
        approval = Approval.objects.select_related(
            'content_type', 'requested_by', 'template'
        ).get(pk=approval_id)
    except Approval.DoesNotExist:
        logger.warning('notify_approval_submitted: approval %s not found', approval_id)
        return

    settings_obj = _resolve_module_settings(approval)
    if settings_obj is not None and not settings_obj.send_notifications:
        return

    step_1 = approval.steps.filter(step_number=1).select_related('approver_group').first()
    recipients = _resolve_step_approvers(step_1) if step_1 else []
    document_label = _get_document_label(approval)
    action_url = _build_action_url(approval_id)

    for user in recipients:
        try:
            send_approval_submitted_email(user, approval, document_label, action_url)
        except Exception:
            logger.warning(
                'Failed to send approval_submitted email to user %s', user.pk, exc_info=True
            )

    if recipients:
        try:
            requester_name = (
                approval.requested_by.get_full_name() or approval.requested_by.username
                if approval.requested_by else 'system'
            )
            Notification.send(
                users=recipients,
                category='APPROVAL',
                title=f'Approval needed: {approval.title}',
                message=(
                    f'A new {document_label} requires your approval. '
                    f'Submitted by {requester_name}.'
                ),
                action_url=action_url,
                priority='NORMAL',
                related_model='approval',
                related_id=approval_id,
            )
        except Exception:
            logger.warning(
                'Failed to create in-app notifications for approval_submitted %s',
                approval_id,
                exc_info=True,
            )


def notify_approval_step_advanced(approval_id: int, new_step_number: int) -> None:
    """
    Notify the approver group for the new current step that it is their turn to act.
    """
    try:
        approval = Approval.objects.select_related(
            'content_type', 'requested_by', 'template'
        ).get(pk=approval_id)
    except Approval.DoesNotExist:
        logger.warning('notify_approval_step_advanced: approval %s not found', approval_id)
        return

    settings_obj = _resolve_module_settings(approval)
    if settings_obj is not None and not settings_obj.send_notifications:
        return

    step = (
        approval.steps
        .filter(step_number=new_step_number)
        .select_related('approver_group')
        .first()
    )
    recipients = _resolve_step_approvers(step) if step else []
    document_label = _get_document_label(approval)
    action_url = _build_action_url(approval_id)

    for user in recipients:
        try:
            send_approval_step_advanced_email(user, approval, document_label, action_url)
        except Exception:
            logger.warning(
                'Failed to send approval_step_advanced email to user %s', user.pk, exc_info=True
            )

    if recipients:
        try:
            Notification.send(
                users=recipients,
                category='APPROVAL',
                title=f'Approval ready for your review: {approval.title}',
                message=(
                    f'Step {new_step_number} of {approval.total_steps} of '
                    f'{document_label} is ready for your review.'
                ),
                action_url=action_url,
                priority='NORMAL',
                related_model='approval',
                related_id=approval_id,
            )
        except Exception:
            logger.warning(
                'Failed to create in-app notifications for approval_step_advanced %s',
                approval_id,
                exc_info=True,
            )


def notify_approval_completed(approval_id: int) -> None:
    """
    Notify the original requester that their request has been fully approved.
    Respects GlobalApprovalSettings.send_notifications and notify_requester flags.
    """
    try:
        approval = Approval.objects.select_related(
            'content_type', 'requested_by', 'template'
        ).get(pk=approval_id)
    except Approval.DoesNotExist:
        logger.warning('notify_approval_completed: approval %s not found', approval_id)
        return

    settings_obj = _resolve_module_settings(approval)
    if settings_obj is not None and not settings_obj.send_notifications:
        return
    if settings_obj is not None and not settings_obj.notify_requester:
        return

    requester = _resolve_requester(approval)
    if not requester:
        return

    action_url = _build_action_url(approval_id)

    try:
        send_approval_completed_email(requester, approval, action_url)
    except Exception:
        logger.warning(
            'Failed to send approval_completed email to user %s', requester.pk, exc_info=True
        )

    try:
        Notification.send(
            users=requester,
            category='APPROVAL',
            title=f'Approved: {approval.title}',
            message=f'Your request for {approval.title} has been fully approved.',
            action_url=action_url,
            priority='NORMAL',
            related_model='approval',
            related_id=approval_id,
        )
    except Exception:
        logger.warning(
            'Failed to create in-app notification for approval_completed %s',
            approval_id,
            exc_info=True,
        )


def notify_approval_rejected(approval_id: int, rejecting_step_number: int) -> None:
    """
    Notify the original requester that their request has been rejected.
    Includes the step number, rejector name, and rejection comment.
    Respects GlobalApprovalSettings.send_notifications and notify_requester flags.
    """
    try:
        approval = Approval.objects.select_related(
            'content_type', 'requested_by', 'template'
        ).get(pk=approval_id)
    except Approval.DoesNotExist:
        logger.warning('notify_approval_rejected: approval %s not found', approval_id)
        return

    settings_obj = _resolve_module_settings(approval)
    if settings_obj is not None and not settings_obj.send_notifications:
        return
    if settings_obj is not None and not settings_obj.notify_requester:
        return

    requester = _resolve_requester(approval)
    if not requester:
        return

    action_url = _build_action_url(approval_id)

    rej_step = (
        approval.steps
        .filter(step_number=rejecting_step_number)
        .select_related('approver')
        .first()
    )
    rejector = 'Unknown'
    comment = ''
    if rej_step:
        if rej_step.approver:
            rejector = rej_step.approver.get_full_name() or rej_step.approver.username
        comment = rej_step.comment or ''

    try:
        send_approval_rejected_email(
            requester, approval, rejecting_step_number, rejector, comment, action_url
        )
    except Exception:
        logger.warning(
            'Failed to send approval_rejected email to user %s', requester.pk, exc_info=True
        )

    try:
        Notification.send(
            users=requester,
            category='APPROVAL',
            title=f'Rejected: {approval.title}',
            message=(
                f'Your request for {approval.title} was rejected at step '
                f'{rejecting_step_number} by {rejector}.'
            ),
            action_url=action_url,
            priority='HIGH',
            related_model='approval',
            related_id=approval_id,
        )
    except Exception:
        logger.warning(
            'Failed to create in-app notification for approval_rejected %s',
            approval_id,
            exc_info=True,
        )


def notify_approval_cancelled(approval_id: int) -> None:
    """
    Send an in-app notification to the requester that the approval was cancelled.
    No email is sent for cancellations — the actor who cancelled already knows.
    Respects GlobalApprovalSettings.send_notifications and notify_requester flags.
    """
    try:
        approval = Approval.objects.select_related(
            'content_type', 'requested_by', 'template'
        ).get(pk=approval_id)
    except Approval.DoesNotExist:
        logger.warning('notify_approval_cancelled: approval %s not found', approval_id)
        return

    settings_obj = _resolve_module_settings(approval)
    if settings_obj is not None and not settings_obj.send_notifications:
        return
    if settings_obj is not None and not settings_obj.notify_requester:
        return

    requester = _resolve_requester(approval)
    if not requester:
        return

    action_url = _build_action_url(approval_id)
    document_label = _get_document_label(approval)

    try:
        Notification.send(
            users=requester,
            category='APPROVAL',
            title=f'Cancelled: {approval.title}',
            message=(
                f'The approval request for {document_label} '
                f'"{approval.title}" has been cancelled.'
            ),
            action_url=action_url,
            priority='LOW',
            related_model='approval',
            related_id=approval_id,
        )
    except Exception:
        logger.warning(
            'Failed to create in-app notification for approval_cancelled %s',
            approval_id,
            exc_info=True,
        )


def notify_approval_sla_breach(approval_step_id: int) -> None:
    """
    Alert the effective approvers of an overdue step via email + in-app notification.
    Delay hours are computed from ApprovalStep.due_date vs. now.
    Respects GlobalApprovalSettings.send_notifications flag.
    """
    try:
        step = ApprovalStep.objects.select_related(
            'approval__content_type', 'approval__requested_by', 'approver_group'
        ).get(pk=approval_step_id)
    except ApprovalStep.DoesNotExist:
        logger.warning('notify_approval_sla_breach: step %s not found', approval_step_id)
        return

    approval = step.approval
    settings_obj = _resolve_module_settings(approval)
    if settings_obj is not None and not settings_obj.send_notifications:
        return

    recipients = _resolve_step_approvers(step)
    action_url = _build_action_url(approval.pk)

    from django.utils import timezone
    if step.due_date:
        delta = timezone.now() - step.due_date
        delay_hours = max(0, int(delta.total_seconds() / 3600))
    else:
        delay_hours = 0

    for user in recipients:
        try:
            send_approval_sla_breach_email(user, approval, delay_hours, action_url)
        except Exception:
            logger.warning(
                'Failed to send approval_sla_breach email to user %s', user.pk, exc_info=True
            )

    if recipients:
        try:
            Notification.send(
                users=recipients,
                category='APPROVAL',
                title=f'URGENT: Approval overdue: {approval.title}',
                message=(
                    f'The approval for "{approval.title}" is overdue by '
                    f'{delay_hours} hours. Please action immediately.'
                ),
                action_url=action_url,
                priority='URGENT',
                related_model='approval',
                related_id=approval.pk,
            )
        except Exception:
            logger.warning(
                'Failed to create in-app notification for approval_sla_breach step %s',
                approval_step_id,
                exc_info=True,
            )
