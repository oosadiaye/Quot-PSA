"""Budget workflow-dispatch signal receivers.

Listens for ``document_approval_completed`` signals emitted by the
workflow engine and triggers the appropriate budget-domain side-effect.

Currently handles:
- ``warrant``: transitions a Warrant from workflow-set 'Approved'
  status to domain-canonical 'RELEASED' status.
- ``appropriationvirement``: calls ``approve_and_apply_virement`` to
  atomically move budget between appropriation lines.
- ``revenuebudget``: flips RevenueBudget.status from DRAFT → ACTIVE.
- ``appropriation``: flips Appropriation.status → ACTIVE after calling
  full_clean() to validate NCoA bridges (B7 guard).

This module is imported by ``BudgetConfig.ready()`` in ``budget/apps.py``.

Failure policy:
- **Re-raise** (all receivers): these mutations are load-bearing.
  A half-applied virement leaves budget lines in inconsistent state;
  a half-activated appropriation/revenue budget silently blocks
  expenditure or collection. Re-raising rolls back the workflow's
  ``transaction.atomic()`` so the approval stays in Pending and the
  operator can investigate and re-approve.

Idempotency:
- ``warrant``: skip if status is already 'RELEASED' or 'EXPIRED'.
- ``appropriationvirement``: skip if status is already 'APPLIED'.
- ``revenuebudget``: skip if status is already 'ACTIVE'.
- ``appropriation``: skip if status is already 'ACTIVE'.
"""
import logging

from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)

try:
    from workflow.signals import document_approval_completed
except ImportError:  # pragma: no cover — workflow is always installed
    document_approval_completed = None


if document_approval_completed is not None:

    @receiver(
        document_approval_completed,
        dispatch_uid='budget.warrant_auto_release',
    )
    def auto_release_warrant_on_approval(
        sender, approval, model_name, document, action, **kwargs,
    ):
        """Transition a Warrant to RELEASED when its workflow approval completes.

        The workflow engine's generic ``sync_document_status_on_approval``
        receiver sets ``warrant.status = 'Approved'`` (the generic
        workflow string). This receiver takes the next step: flipping the
        Warrant from that transient 'Approved' state to the domain-
        canonical 'RELEASED' state, which is what the budget expenditure
        gate (``BudgetValidationService._is_warrant_enforced``) actually
        checks for.

        Runs inside the workflow's ``transaction.atomic()`` — failure
        here DOES roll back the approval so no half-released Warrant can
        inflate ``Appropriation.total_warrants_released``.

        Idempotency: no-op when status is already 'RELEASED' or 'EXPIRED'.
        """
        if action != 'approve' or model_name != 'warrant':
            return

        if document is None:
            return

        # Idempotency guard — already in a terminal release state.
        current_status = getattr(document, 'status', None)
        if current_status in ('RELEASED', 'EXPIRED'):
            return

        try:
            from budget.models import Warrant

            # select_for_update to prevent concurrent double-release
            warrant = Warrant.objects.select_for_update().get(pk=document.pk)

            # Re-check idempotency under lock
            if warrant.status in ('RELEASED', 'EXPIRED'):
                return

            warrant.status = 'RELEASED'
            warrant.save(update_fields=['status', 'updated_at'])

            logger.info(
                'Warrant %s auto-released via workflow approval %s.',
                warrant.pk,
                getattr(approval, 'pk', '?'),
            )

        except Exception as exc:
            logger.warning(
                'Warrant %s auto-release failed (approval %s will be rolled back): %s',
                getattr(document, 'pk', '?'),
                getattr(approval, 'pk', '?'),
                exc,
            )
            # Re-raise — rolls back the approval so no half-released
            # Warrant silently corrupts budget balance calculations.
            raise

    @receiver(
        document_approval_completed,
        dispatch_uid='budget.appropriationvirement_auto_apply',
    )
    def auto_apply_virement_on_approval(
        sender, approval, model_name, document, action, **kwargs,
    ):
        """Apply an AppropriationVirement when its workflow approval completes.

        Calls ``approve_and_apply_virement`` which atomically moves
        ``amount_approved`` from the source to the target Appropriation
        and stamps audit snapshots. The service is already ``@transaction.atomic``
        but that is nested inside the workflow's outer atomic, so any failure
        here rolls back the entire approval.

        Idempotency: no-op when virement status is already 'APPLIED'.

        Failure policy: re-raise — a partial virement (source deducted,
        target not credited) would corrupt available balances on both lines.
        """
        if action != 'approve' or model_name != 'appropriationvirement':
            return

        if document is None:
            return

        # Pre-lock idempotency guard.
        if getattr(document, 'status', None) == 'APPLIED':
            return

        try:
            from budget.models import AppropriationVirement
            from budget.services_virement import approve_and_apply_virement

            # Row-lock the virement before calling the service so concurrent
            # double-fires see the 'APPLIED' status and short-circuit.
            virement = AppropriationVirement.objects.select_for_update().get(
                pk=document.pk,
            )

            # Under-lock idempotency re-check.
            if virement.status == 'APPLIED':
                return

            # Pass the approving user from the approval record when available.
            approving_user = getattr(approval, 'approved_by', None) or getattr(
                approval, 'created_by', None
            )
            approve_and_apply_virement(virement, user=approving_user)

            logger.info(
                'AppropriationVirement %s applied via workflow approval %s.',
                virement.pk,
                getattr(approval, 'pk', '?'),
            )

        except Exception as exc:
            logger.warning(
                'AppropriationVirement %s apply failed (approval %s will be '
                'rolled back): %s',
                getattr(document, 'pk', '?'),
                getattr(approval, 'pk', '?'),
                exc,
            )
            raise

    @receiver(
        document_approval_completed,
        dispatch_uid='budget.revenuebudget_auto_activate',
    )
    def auto_activate_revenue_budget_on_approval(
        sender, approval, model_name, document, action, **kwargs,
    ):
        """Flip a RevenueBudget from DRAFT to ACTIVE when workflow approval completes.

        RevenueBudget has no dedicated service — the transition is a single
        field flip, mirroring the warrant receiver pattern. ACTIVE is the
        precondition for revenue collection reporting against this line.

        Idempotency: no-op when status is already 'ACTIVE'.

        Failure policy: re-raise — a DB error on save should block the
        approval rather than leave a RevenueBudget in an ambiguous state.
        """
        if action != 'approve' or model_name != 'revenuebudget':
            return

        if document is None:
            return

        # Pre-lock idempotency guard.
        if getattr(document, 'status', None) == 'ACTIVE':
            return

        try:
            from budget.models import RevenueBudget

            revenue_budget = RevenueBudget.objects.select_for_update().get(
                pk=document.pk,
            )

            # Under-lock idempotency re-check.
            if revenue_budget.status == 'ACTIVE':
                return

            revenue_budget.status = 'ACTIVE'
            revenue_budget.save(update_fields=['status', 'updated_at'])

            logger.info(
                'RevenueBudget %s activated via workflow approval %s.',
                revenue_budget.pk,
                getattr(approval, 'pk', '?'),
            )

        except Exception as exc:
            logger.warning(
                'RevenueBudget %s activation failed (approval %s will be '
                'rolled back): %s',
                getattr(document, 'pk', '?'),
                getattr(approval, 'pk', '?'),
                exc,
            )
            raise

    @receiver(
        document_approval_completed,
        dispatch_uid='budget.appropriation_auto_activate',
    )
    def auto_activate_appropriation_on_approval(
        sender, approval, model_name, document, action, **kwargs,
    ):
        """Flip an Appropriation to ACTIVE when its workflow approval completes.

        Sets ``status='ACTIVE'``, calls ``full_clean()`` to trigger the B7
        NCoA bridge validation (``Appropriation.clean()``), then saves.
        If ``full_clean()`` raises ``ValidationError`` (missing bridges),
        the exception propagates and rolls back the approval — the operator
        must fix the segment bridges and re-approve.

        Idempotency: no-op when status is already 'ACTIVE'.

        Failure policy: re-raise — a half-enacted appropriation with missing
        bridges would silently allow over-commitment via an inflated
        ``available_balance``.
        """
        if action != 'approve' or model_name != 'appropriation':
            return

        if document is None:
            return

        # Pre-lock idempotency guard.
        if getattr(document, 'status', None) == 'ACTIVE':
            return

        try:
            from budget.models import Appropriation

            appropriation = Appropriation.objects.select_for_update().get(
                pk=document.pk,
            )

            # Under-lock idempotency re-check.
            if appropriation.status == 'ACTIVE':
                return

            appropriation.status = 'ACTIVE'
            # Trigger B7 NCoA bridge validation before committing.
            appropriation.full_clean()
            appropriation.save(update_fields=['status', 'updated_at'])

            logger.info(
                'Appropriation %s activated via workflow approval %s.',
                appropriation.pk,
                getattr(approval, 'pk', '?'),
            )

        except Exception as exc:
            logger.warning(
                'Appropriation %s activation failed (approval %s will be '
                'rolled back): %s',
                getattr(document, 'pk', '?'),
                getattr(approval, 'pk', '?'),
                exc,
            )
            raise
