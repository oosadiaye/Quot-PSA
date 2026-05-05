"""Cross-module signal handlers for procurement events.

This module is intentionally minimal. The legacy ``on_grn_posted`` handler
that updated ``accounting.BudgetEncumbrance`` was removed because:

1. It used a non-existent ``reference_number`` field on
   ``BudgetEncumbrance`` (the real key is ``reference_type`` +
   ``reference_id``), which raised ``FieldError`` on every GRN post and
   produced a 400 Bad Request from the API.

2. The same lifecycle event is now handled by the canonical, schema-
   correct path:

       GoodsReceivedNote.save()
         → mark_commitment_invoiced_for_po(po)
           → ProcurementBudgetLink.status: ACTIVE → INVOICED

   This is the IPSAS-compliant commitment progression that the Budget
   Execution Report and Appropriation.total_committed depend on. See
   ``accounting/services/procurement_commitments.py`` for the helpers.

If you ever need a cross-module side effect on GRN posting, prefer
calling a service helper from ``GoodsReceivedNote.save()`` rather than
re-introducing a signal — signals make the side-effect graph harder to
reason about and harder to test.

The one exception: workflow-driven side effects.  Workflow approvals
fire across many document types and the workflow module shouldn't
import each downstream module's ViewSet to dispatch them. The
``document_approval_completed`` signal owned by workflow lets us hook
in from this side without creating a dependency in workflow → us.
"""
import logging

from django.dispatch import receiver

logger = logging.getLogger(__name__)

try:
    # Imported eagerly so a typo in the signal's name surfaces at app
    # load (system check) rather than the first time an approval fires.
    from workflow.signals import document_approval_completed
except ImportError:  # pragma: no cover — workflow is always installed
    document_approval_completed = None


if document_approval_completed is not None:

    @receiver(document_approval_completed, dispatch_uid='procurement.invoicematching_auto_post')
    def auto_post_invoicematching_on_approval(
        sender, approval, model_name, document, action, **kwargs,
    ):
        """Auto-post a verified InvoiceMatching to GL when its workflow
        approval completes.

        Mirrors the auto-posting behaviour of ``verify_and_post`` — the
        user expectation is that a 3-way-matched invoice books to GL
        the moment its approval clears, with no extra "Post to GL"
        click. The receiver runs inside the workflow's atomic block, so
        a posting failure rolls back the approval transition and the
        document status change together.

        Scoped tightly: only the ``invoicematching`` model on a
        successful approval. All other approvals are ignored (the
        ``return`` early-exits keep this signal cheap for the common
        case).
        """
        if action != 'approve' or model_name != 'invoicematching':
            return
        if document is None or getattr(document, 'status', None) != 'Approved':
            return
        try:
            # Local import — circular at module load (procurement.views
            # imports procurement.models which imports procurement.signals
            # via apps.ready). Lazy import here defers resolution until
            # signal-dispatch time, by which point the import graph has
            # settled.
            from procurement.views import InvoiceMatchingViewSet
            InvoiceMatchingViewSet._post_matching_to_gl_inner(document)
        except Exception as exc:
            # Don't re-raise: the user expectation is "approval succeeds
            # even if GL posting hiccups; user retries via Post to GL".
            # The previous direct-call code already had this swallow
            # behaviour (logged, not re-raised). Preserve it so the
            # signal switch is behaviour-preserving.
            logger.warning(
                'Workflow-approved matching %s auto-post to GL failed '
                '(user can still retry via Post to GL): %s',
                getattr(document, 'pk', '?'), exc,
            )
