"""Accounting workflow-dispatch signal receiver.

Listens for ``document_approval_completed`` signals emitted by the
workflow engine and triggers the appropriate accounting-domain
side-effect (e.g. auto-posting a JournalHeader to GL once its
approval workflow completes).

This module is imported by ``accounting/signals/__init__.py`` so it
loads at app startup via ``AccountingConfig.ready()``.

Failure policy (mirrors procurement/signals.py template):
- JournalHeader auto-post failure: log WARNING, do NOT roll back the
  approval. The approval commit is preserved and the error is stamped
  into ``JournalHeader.gl_post_error`` if that field exists; otherwise
  just logged. A subsequent "Post to GL" click can retry.
- RevenueCollection auto-post failure: log-only. Revenue already
  confirmed by cash receipt; GL post failure should not reverse the
  confirmed collection. Operator retries via the "Post to GL" endpoint.
- PaymentVoucherGov / PaymentVoucher auto-post failure: log-only.
  PV approval is high-volume; operators can retry via the existing UI
  without rolling back the approval audit trail.

Idempotency:
- Skip if JournalHeader.status is already 'Posted'.
- Skip if RevenueCollection.status is already 'POSTED' or
  is_reconciled is True.
- Skip if PaymentVoucherGov / PaymentVoucher status is already in a
  terminal state ('PAID', 'REVERSED', 'CANCELLED').
"""
import logging

from django.dispatch import receiver

logger = logging.getLogger(__name__)

try:
    from workflow.signals import document_approval_completed
except ImportError:  # pragma: no cover — workflow is always installed
    document_approval_completed = None


if document_approval_completed is not None:

    @receiver(
        document_approval_completed,
        dispatch_uid='accounting.journalheader_auto_post',
    )
    def auto_post_journalheader_on_approval(
        sender, approval, model_name, document, action, **kwargs,
    ):
        """Auto-post a JournalHeader to GL when its workflow approval completes.

        The user expectation for manual journal entries that go through
        an approval workflow is that the journal posts to GL the moment
        the approval clears — no separate "Post to GL" click required.

        Runs inside the workflow's ``transaction.atomic()`` block, but
        deliberately does NOT re-raise on failure so the approval commit
        is preserved. The failure is surfaced via a WARNING log (and an
        optional ``gl_post_error`` stamp) so the operator can retry via
        the "Post to GL" button.

        Idempotency: skips silently if the header is already 'Posted'.
        """
        if action != 'approve' or model_name != 'journalheader':
            return

        if document is None:
            return

        # Idempotency guard — already posted by some other path.
        if getattr(document, 'status', None) == 'Posted':
            return

        try:
            # Lazy imports — avoids circular import at module load time
            # (accounting.signals is imported by accounting.apps.ready(),
            # which fires before accounting.services is fully resolved in
            # some import orderings). Safe at signal-dispatch time.
            from accounting.services.ipsas_journal_service import IPSASJournalService

            IPSASJournalService.post_journal(document, user=None)

        except Exception as exc:
            # Log the failure but do NOT re-raise: the approval itself
            # should commit even if GL posting fails. The operator can
            # retry via the "Post to GL" endpoint.
            logger.warning(
                'Workflow-approved JournalHeader %s auto-post to GL failed '
                '(retry via Post to GL): %s',
                getattr(document, 'pk', '?'),
                exc,
            )
            err_msg = f'{type(exc).__name__}: {exc}'[:5000]
            # Stamp error field if it exists on the model, using update()
            # to avoid re-triggering save-time signals inside the atomic.
            try:
                from accounting.models.gl import JournalHeader
                if hasattr(JournalHeader, 'gl_post_error'):
                    JournalHeader.objects.filter(pk=document.pk).update(
                        gl_post_error=err_msg,
                    )
            except Exception:  # noqa: BLE001 — best-effort stamp
                logger.exception(
                    'Failed to stamp gl_post_error on JournalHeader %s',
                    getattr(document, 'pk', '?'),
                )
        else:
            # Clear any prior error stamp on success (best-effort).
            try:
                from accounting.models.gl import JournalHeader
                if hasattr(JournalHeader, 'gl_post_error'):
                    if getattr(document, 'gl_post_error', ''):
                        JournalHeader.objects.filter(pk=document.pk).update(
                            gl_post_error='',
                        )
            except Exception:  # noqa: BLE001 — best-effort clear
                pass

    @receiver(
        document_approval_completed,
        dispatch_uid='accounting.revenuecollection_auto_post',
    )
    def auto_post_revenuecollection_on_approval(
        sender, approval, model_name, document, action, **kwargs,
    ):
        """Auto-post a RevenueCollection to GL when its workflow approval completes.

        Trigger: model_name='revenuecollection' + action='approve'.

        The operator expectation is that once a revenue collection clears
        its approval gate, the GL journal posts automatically — no separate
        "Post to GL" click required for workflow-managed collections.

        Architecture note — B4 tenant-isolation gap:
        The underlying ``RevenueCollectionViewSet.get_queryset()`` does not
        apply ``OrganizationFilterMixin``'s MDA scope (B4 review finding:
        tenant isolation gap on that ViewSet). This receiver does NOT change
        that isolation behaviour — it only wires the auto-post. The B4 gap
        must be addressed separately in the ViewSet queryset.

        Failure policy: log-only.  Revenue confirmed by cash receipt; a GL
        post failure should not reverse the approval. Operator retries via
        the "Post to GL" endpoint.

        Idempotency: skips silently if status is already 'POSTED' or if
        the collection has already been reconciled (is_reconciled=True).
        """
        if action != 'approve' or model_name != 'revenuecollection':
            return

        if document is None:
            return

        # Idempotency: already posted or reconciled.
        if getattr(document, 'status', None) == 'POSTED':
            return
        if getattr(document, 'is_reconciled', False):
            return

        try:
            from accounting.services.revenue_collection_posting import (
                post_revenue_collection_to_gl,
            )
            journal = post_revenue_collection_to_gl(document, user=None)

            # Stamp status + journal FK.  Use update() to avoid re-triggering
            # save-time signals inside the workflow's atomic block.
            from accounting.models.revenue import RevenueCollection
            RevenueCollection.objects.filter(pk=document.pk).update(
                status='POSTED',
                journal=journal,
            )

        except Exception as exc:
            logger.warning(
                'Workflow-approved RevenueCollection %s auto-post to GL failed '
                '(retry via Post to GL): %s',
                getattr(document, 'pk', '?'),
                exc,
            )
            # Stamp gl_post_error if the field exists — forward-compat guard.
            if hasattr(document, 'gl_post_error'):
                err_msg = f'{type(exc).__name__}: {exc}'[:5000]
                try:
                    from accounting.models.revenue import RevenueCollection
                    RevenueCollection.objects.filter(pk=document.pk).update(
                        gl_post_error=err_msg,
                    )
                except Exception:  # noqa: BLE001 — best-effort stamp
                    logger.exception(
                        'Failed to stamp gl_post_error on RevenueCollection %s',
                        getattr(document, 'pk', '?'),
                    )

    @receiver(
        document_approval_completed,
        dispatch_uid='accounting.paymentvoucher_auto_post',
    )
    def auto_post_paymentvoucher_on_approval(
        sender, approval, model_name, document, action, **kwargs,
    ):
        """Auto-post a PaymentVoucherGov / PaymentVoucher to GL on approval.

        Trigger: model_name in ('paymentvoucher', 'paymentvouchergov') +
        action='approve'.

        Both model names are handled in one receiver because they share the
        same approval-driven auto-post semantics.  Both map to 'PaymentVoucher'
        in ``workflow.views._MODEL_TO_MODULE_KEY``.

        Production-readiness note: workflow-approved PVs currently show as
        "Approved" in the UI but the IPSAS payment journal is NOT posted
        automatically. This receiver closes that gap — once the workflow
        approval completes, the journal posts without a separate operator
        action.

        Failure policy: log-only.  PV approval is high-volume; a GL post
        failure must not roll back the approval audit trail. Operators can
        retry via the "Post to GL" / "Mark Paid" UI buttons.

        Idempotency: skips if the document status is already in a terminal
        state ('PAID', 'REVERSED', 'CANCELLED') where posting again would
        be either a no-op or destructive.  Uses ``hasattr`` to handle both
        ``PaymentVoucherGov`` (treasury model, has 'PAID') and the legacy
        ``PaymentVoucher`` (advanced model, has 'APPROVED' as its only
        terminal non-error state but carries ``journal_id`` as idempotency
        key).
        """
        if action != 'approve' or model_name not in (
            'paymentvoucher', 'paymentvouchergov',
        ):
            return

        if document is None:
            return

        # Idempotency: terminal status check.
        doc_status = getattr(document, 'status', None)
        _TERMINAL_STATUSES = ('PAID', 'REVERSED', 'CANCELLED')
        if doc_status in _TERMINAL_STATUSES:
            return

        # For the legacy PaymentVoucher (accounting.models.advanced), the
        # journal_id field serves as the idempotency key (no 'PAID' status).
        if hasattr(document, 'journal_id') and document.journal_id:
            return

        try:
            from accounting.services.payment_voucher_posting import (
                post_payment_voucher_to_gl,
            )
            journal = post_payment_voucher_to_gl(document, user=None)

            # Stamp journal FK.  Use update() to skip model .save() signals
            # inside the workflow's atomic block.  The status is deliberately
            # left as 'APPROVED' (not 'PAID') because marking PAID requires
            # the full bank-settlement path (PaymentInstruction + TSA balance
            # update) which is not part of the approval-only auto-post.
            # The operator completes the APPROVED → PAID transition via the
            # "Mark Paid" action once bank confirmation arrives.
            if hasattr(document, 'journal_id'):
                # Legacy PaymentVoucher (accounting.models.advanced)
                type(document).objects.filter(pk=document.pk).update(
                    journal_id=journal.pk,
                )
            else:
                # PaymentVoucherGov (accounting.models.treasury)
                from accounting.models.treasury import PaymentVoucherGov
                PaymentVoucherGov.objects.filter(pk=document.pk).update(
                    journal=journal,
                )

        except Exception as exc:
            logger.warning(
                'Workflow-approved PaymentVoucher (%s) %s auto-post to GL failed '
                '(retry via Post to GL): %s',
                model_name,
                getattr(document, 'pk', '?'),
                exc,
            )
            # Stamp gl_post_error if the field exists — forward-compat guard.
            if hasattr(document, 'gl_post_error'):
                err_msg = f'{type(exc).__name__}: {exc}'[:5000]
                try:
                    type(document).objects.filter(pk=document.pk).update(
                        gl_post_error=err_msg,
                    )
                except Exception:  # noqa: BLE001 — best-effort stamp
                    logger.exception(
                        'Failed to stamp gl_post_error on PaymentVoucher (%s) %s',
                        model_name,
                        getattr(document, 'pk', '?'),
                    )
