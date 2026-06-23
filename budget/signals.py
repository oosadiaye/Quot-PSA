"""Budget workflow-dispatch signal receiver.

Listens for ``document_approval_completed`` signals emitted by the
workflow engine and triggers the appropriate budget-domain side-effect.

Currently handles:
- ``warrant``: transitions a Warrant from workflow-set 'Approved'
  status to domain-canonical 'RELEASED' status.

This module is imported by ``BudgetConfig.ready()`` in ``budget/apps.py``.

Failure policy for warrant:
- Re-raise on failure: a half-released warrant would silently inflate
  ``Appropriation.total_warrants_released`` and corrupt budget checks.
  Re-raising lets the workflow's ``transaction.atomic()`` roll back
  both the approval status change and any partial writes in this
  receiver. The approval remains in 'Pending' state so the operator
  can investigate and re-approve once the underlying issue is fixed.

Idempotency:
- Skip if Warrant.status is already 'RELEASED' or 'EXPIRED'.
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
