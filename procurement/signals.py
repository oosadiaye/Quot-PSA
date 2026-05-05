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
        a posting failure does NOT roll back the approval (the
        exception is captured into ``document.gl_post_error`` so the
        UI can surface it for manual retry); but successful posting
        clears any prior error.

        Scoped tightly: only the ``invoicematching`` model on a
        successful approval. All other approvals are ignored.

        H4 guard: skip when the caller has already posted directly via
        the ``submit_for_approval`` auto-approve fast path
        (``matching._auto_posted`` sentinel). Without this, every auto-
        approval would log a spurious "already_posted" warning because
        the idempotency guard in ``_post_matching_to_gl_inner`` raises
        on the second call.
        """
        if action != 'approve' or model_name != 'invoicematching':
            return
        if document is None or getattr(document, 'status', None) != 'Approved':
            return
        # H4 sentinel — the caller posted directly already.
        if getattr(document, '_auto_posted', False):
            return
        # Idempotency: skip if the matching is already linked to a
        # Posted journal (mirrors the ``_post_matching_to_gl_inner``
        # internal guard but check it here too so we never log noisy
        # "already posted" warnings).
        if getattr(document, 'journal_entry_id', None):
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
            # H3 fix: surface the failure to the operator instead of
            # silent log-only behaviour. Approval still commits (so the
            # workflow trail isn't disrupted); the matching carries a
            # ``gl_post_error`` flag the UI renders as a banner. A
            # subsequent successful "Post to GL" clears the flag.
            logger.warning(
                'Workflow-approved matching %s auto-post to GL failed '
                '(user can retry via Post to GL): %s',
                getattr(document, 'pk', '?'), exc,
            )
            err_msg = f'{type(exc).__name__}: {exc}'[:5000]
            try:
                # Use update() so we don't re-trigger any save-time
                # signals (this whole block runs inside the workflow
                # atomic; an inner save() that touches status would
                # fight the parent transaction).
                from procurement.models import InvoiceMatching
                InvoiceMatching.objects.filter(pk=document.pk).update(
                    gl_post_error=err_msg,
                )
            except Exception:  # noqa: BLE001 — last-ditch best effort
                logger.exception(
                    'Failed to stamp gl_post_error on matching %s',
                    getattr(document, 'pk', '?'),
                )
        else:
            # Clear any prior error stamp on success.
            if getattr(document, 'gl_post_error', ''):
                from procurement.models import InvoiceMatching
                InvoiceMatching.objects.filter(pk=document.pk).update(
                    gl_post_error='',
                )
