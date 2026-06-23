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
- BadDebtWriteOff GL-post failure: re-raise. A write-off approved but
  not posted leaves the receivable on the books while the approval says
  it was written off — silent AR overstatement.
- VendorAdvance disbursement failure: re-raise. An approved advance
  that fails disbursement journal posting must not leave the VendorAdvance
  in OUTSTANDING status without a corresponding GL entry.
- TSAReconciliation completion failure: re-raise. A half-completed
  reconciliation (some payments marked reconciled, statement not locked)
  would create duplicate-reconciliation risk on the next cycle.

Idempotency:
- Skip if JournalHeader.status is already 'Posted'.
- Skip if RevenueCollection.status is already 'POSTED' or
  is_reconciled is True.
- Skip if PaymentVoucherGov / PaymentVoucher status is already in a
  terminal state ('PAID', 'REVERSED', 'CANCELLED').
- Skip if BadDebtWriteOff.status is already 'POSTED' or journal_id
  is set.
- Skip if VendorAdvance.status is already 'CLEARED' or
  disbursement_journal_id is already set.
- Skip if TSAReconciliation.status is already 'COMPLETED'.
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

    # -----------------------------------------------------------------------
    # Receiver 4 — BadDebtWriteOff GL posting
    # -----------------------------------------------------------------------

    @receiver(
        document_approval_completed,
        dispatch_uid='accounting.baddebtwriteoff',
    )
    def post_baddebtwriteoff_on_approval(
        sender, approval, model_name, document, action, **kwargs,
    ):
        """Post a BadDebtWriteOff to GL when its workflow approval completes.

        Trigger: model_name='baddebtwriteoff' + action='approve'.

        The write-off journal (DR Allowance / CR AR) is posted automatically
        so the receivable is removed from the books the moment the approving
        officer signs off — no separate "Post to GL" click required.

        Failure policy: re-raise. A write-off approved but not posted leaves
        the receivable on the books while the approval says it was written off
        — silent AR overstatement. The approval is rolled back so the operator
        can fix the underlying cause (missing accounts, closed period) and
        re-approve.

        Idempotency: skips silently if ``status == 'POSTED'`` or
        ``journal_id`` is already set (posted via the direct UI button).
        """
        if action != 'approve' or model_name != 'baddebtwriteoff':
            return

        if document is None:
            return

        # Idempotency guards.
        if getattr(document, 'status', None) == 'POSTED':
            return
        if getattr(document, 'journal_id', None):
            return

        try:
            from accounting.services.bad_debt_writeoff_posting import (
                post_bad_debt_writeoff,
            )
            post_bad_debt_writeoff(document, user=None)

        except Exception as exc:
            logger.warning(
                'Workflow-approved BadDebtWriteOff %s GL posting failed '
                '(approval will be rolled back): %s',
                getattr(document, 'pk', '?'),
                exc,
            )
            raise

    # -----------------------------------------------------------------------
    # Receiver 5 — VendorAdvance disbursement journal posting
    # -----------------------------------------------------------------------

    @receiver(
        document_approval_completed,
        dispatch_uid='accounting.vendoradvance',
    )
    def disburse_vendoradvance_on_approval(
        sender, approval, model_name, document, action, **kwargs,
    ):
        """Post the disbursement journal for a VendorAdvance on approval.

        Trigger: model_name='vendoradvance' + action='approve'.

        The VendorAdvance document is approved through the workflow before
        the disbursement journal is posted. Once approved, this receiver
        posts the journal:
            DR  Vendor-Advance Recon (Special GL)   amount_paid
            CR  Cash / TSA                                         amount_paid

        Parameter mapping from ``VendorAdvance`` model fields to
        ``VendorAdvanceService.disburse()``:
            vendor        → document.vendor
            amount        → document.amount_paid
            source_type   → document.source_type
            source_id     → document.source_id
            reference     → document.reference
            posting_date  → document.posting_date
            actor         → None (workflow approval is the authority gate)

        The service's own idempotency guard will also reject a duplicate
        ``(source_type, source_id)`` pair — raising ``TransactionPostingError``
        — so we have two layers of protection.

        Failure policy: re-raise. An approved advance without a posted
        disbursement journal would inflate the vendor's special-GL advance
        balance without a corresponding cash credit — silent ledger drift.

        Idempotency: skips silently if ``disbursement_journal_id`` is already
        set (journal posted via a prior path) or if ``status == 'CLEARED'``
        (advance was fully recovered — disbursement already happened).
        """
        if action != 'approve' or model_name != 'vendoradvance':
            return

        if document is None:
            return

        # Idempotency guards.
        if getattr(document, 'disbursement_journal_id', None):
            return
        if getattr(document, 'status', None) == 'CLEARED':
            return

        try:
            from accounting.services.vendor_advance import VendorAdvanceService
            from accounting.models.vendor_advance import VendorAdvance

            VendorAdvanceService.disburse(
                vendor=document.vendor,
                amount=document.amount_paid,
                source_type=document.source_type,
                source_id=document.source_id,
                reference=document.reference,
                posting_date=document.posting_date,
                actor=None,
            )

        except Exception as exc:
            logger.warning(
                'Workflow-approved VendorAdvance %s disbursement journal '
                'posting failed (approval will be rolled back): %s',
                getattr(document, 'pk', '?'),
                exc,
            )
            raise

    # -----------------------------------------------------------------------
    # Receiver 6 — TSAReconciliation completion
    # -----------------------------------------------------------------------

    @receiver(
        document_approval_completed,
        dispatch_uid='accounting.tsareconciliation',
    )
    def complete_tsareconciliation_on_approval(
        sender, approval, model_name, document, action, **kwargs,
    ):
        """Finalise a TSAReconciliation when its workflow approval completes.

        Trigger: model_name='tsareconciliation' + action='approve'.

        The reconciliation session is completed automatically — flagging all
        matched PaymentInstruction/RevenueCollection rows as is_reconciled=True
        and locking the bank statement — when the AG/Treasury approver signs
        off via the workflow. No separate "Complete" button click required.

        MFA bypass note:
            The view's ``complete`` action enforces ``RequiresMFA`` + ``CanReconcileTSA``.
            When this receiver fires, those permission classes are NOT checked
            again. The workflow approval itself is the authorisation gate — the
            submitter and approver both authenticated at the point of workflow
            submission/approval. Do NOT change this behaviour; the MFA gate
            belongs at the approval call site, not inside this receiver. This
            is consistent with other re-raise receivers in this module
            (appropriation, virement) that similarly bypass view-layer
            permission classes.

        Failure policy: re-raise. A half-completed reconciliation (some
        payments marked reconciled, bank statement not locked) would create
        duplicate-reconciliation risk on the next cycle.

        Idempotency: skips silently if ``status == 'COMPLETED'``.
        """
        if action != 'approve' or model_name != 'tsareconciliation':
            return

        if document is None:
            return

        # Idempotency guard.
        if getattr(document, 'status', None) == 'COMPLETED':
            return

        try:
            from accounting.services.tsa_reconciliation_service import (
                complete_reconciliation,
            )
            complete_reconciliation(document, user=None)

        except Exception as exc:
            logger.warning(
                'Workflow-approved TSAReconciliation %s completion failed '
                '(approval will be rolled back): %s',
                getattr(document, 'pk', '?'),
                exc,
            )
            raise
