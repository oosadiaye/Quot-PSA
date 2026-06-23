"""Payment Voucher GL posting service.

Extracts the IPSAS payment journal logic from
``PaymentVoucherViewSet._post_payment_journal`` in
``accounting/views/treasury_revenue.py`` into a standalone callable that
can be invoked from:

  1. The view (``PaymentVoucherViewSet.mark_paid``) — same behaviour as
     before the extraction; call site updated to call this function.
  2. The workflow-dispatch receiver
     (``accounting.signals.workflow_dispatch``) — auto-post on workflow
     approval of ``paymentvoucher`` / ``paymentvouchergov`` documents.

Public API
----------
``post_payment_voucher_to_gl(pv, user=None) -> JournalHeader``

  Builds and posts the IPSAS payment journal:
      DR  Expenditure / AP account        NGN gross
      CR  TSA Cash                        NGN net paid
      CR  <Deduction liability>           NGN (one row per deduction)
      ...

  Returns the created ``JournalHeader``.  Does NOT flip ``pv.status`` or
  stamp ``pv.journal`` — the caller owns those side-effects.

Scope
-----
This service only handles ``PaymentVoucherGov`` (the treasury-side PV
model in ``accounting.models.treasury``).  The legacy ``PaymentVoucher``
model in ``accounting.models.advanced`` has its own posting path via
``accounting.views.payables.PaymentViewSet.post_payment`` and is a
separate concern.

Atomic boundaries
-----------------
Does NOT wrap in ``transaction.atomic`` — same reasoning as
``revenue_collection_posting.py``: the caller (view or signal receiver)
already runs inside a transaction.

Raises
------
``ValueError``  — if an NCoA / GL account bridge is not configured.
``Exception``   — propagated from ``IPSASJournalService`` / DB layer.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from accounting.models.treasury import PaymentVoucherGov
    from accounting.models.gl import JournalHeader
    from django.contrib.auth.models import AbstractBaseUser


def post_payment_voucher_to_gl(
    pv: "PaymentVoucherGov",
    user: "AbstractBaseUser | None" = None,
) -> "JournalHeader":
    """Create and post the IPSAS payment journal for a PaymentVoucherGov.

    Payment-time recognition model (Nigerian IFMIS, cash basis):
        DR  Expenditure / AP account        NGN gross
        CR  TSA Cash                        NGN net paid
        CR  <Deduction liability>           NGN (one row per deduction)
        ...

    Deductions come from ``pv.deductions`` (PaymentVoucherDeduction child
    rows). Typical kinds: WHT, Stamp Duty, VAT withheld, Bank Handling
    Charges, Insurance, Retention, Other.  Each deduction row carries its
    own ``gl_account`` so operators can pick the correct liability /
    revenue account per the CoA.

    Backward-compat: if no deduction lines exist but the legacy
    ``pv.wht_amount`` is non-zero, a single WHT credit row is emitted
    against the configured WHT NCoA code (41200600) so old records
    continue to post correctly.

    All accounts resolved via NCoA → legacy_account bridge; no codes are
    hardcoded here.

    Args:
        pv: The ``PaymentVoucherGov`` instance to post.
        user: The user initiating the post, passed to
            ``IPSASJournalService`` for audit trail.  May be ``None``
            when called from an automated context (signal receiver).

    Returns:
        The newly created and posted ``JournalHeader``.

    Raises:
        ValueError: When the NCoA expenditure segment has no linked GL
            account (bridge not yet seeded).
    """
    from decimal import Decimal

    # Lazy imports — safe at call time (signal fires after app startup).
    from accounting.models.gl import JournalHeader, JournalLine, TransactionSequence, Account
    from accounting.models.ncoa import EconomicSegment
    from accounting.services.ipsas_journal_service import IPSASJournalService
    from accounting.services.tsa_gl_resolver import resolve_tsa_cash_gl

    from django.utils import timezone

    ref = TransactionSequence.get_next('journal', prefix='JE-')
    header = JournalHeader.objects.create(
        reference_number=ref,
        description=f"Payment: {pv.narration}",
        posting_date=timezone.now().date(),
        status='Draft',
        source_module='treasury',
        source_document_id=pv.pk,
        posted_by=user,
    )

    # DR: Expenditure account from NCoA bridge (full gross).
    expenditure_account = pv.ncoa_code.economic.legacy_account
    if not expenditure_account:
        raise ValueError(
            f"NCoA segment {pv.ncoa_code.economic.code} has no linked GL "
            f"account.  Run: python manage.py seed_ncoa_as_coa"
        )
    JournalLine.objects.create(
        header=header,
        account=expenditure_account,
        debit=pv.gross_amount,
        credit=0,
        memo=f"PV {pv.voucher_number}: {pv.payee_name}",
        ncoa_code=pv.ncoa_code,
    )

    # Resolve TSA cash GL account (per-TSA → AccountingSettings default
    # → first 31* asset GL — never a hardcoded code).
    tsa_gl_account = resolve_tsa_cash_gl(
        tsa_account=getattr(pv, 'tsa_account', None),
    )

    # ── Deduction lines ──────────────────────────────────────────────────
    deductions = list(pv.deductions.select_related('gl_account').all())
    total_deductions = sum((d.amount for d in deductions), Decimal('0'))

    # Legacy fallback: header-only wht_amount with no deduction rows.
    if not deductions and (pv.wht_amount or Decimal('0')) > 0:
        wht_seg = EconomicSegment.objects.filter(code='41200600').first()
        wht_account = (
            wht_seg.legacy_account if wht_seg
            else Account.objects.filter(code='41200600').first()
            or Account.objects.filter(
                code__startswith='412', account_type='Liability',
            ).first()
        )
        if wht_account:
            JournalLine.objects.create(
                header=header,
                account=wht_account,
                debit=0,
                credit=pv.wht_amount,
                memo=f"WHT on PV {pv.voucher_number}",
            )
            total_deductions = pv.wht_amount

    # One credit row per deduction line.
    for d in deductions:
        if d.amount and d.amount > 0 and d.gl_account:
            JournalLine.objects.create(
                header=header,
                account=d.gl_account,
                debit=0,
                credit=d.amount,
                memo=(
                    f"{d.get_deduction_type_display()} on PV {pv.voucher_number}"
                    + (f" — {d.description}" if d.description else '')
                )[:255],
            )

    # CR: TSA cash = gross − Σ deductions (the amount actually paid out).
    net_paid = (pv.gross_amount or Decimal('0')) - total_deductions
    if net_paid > 0:
        JournalLine.objects.create(
            header=header,
            account=tsa_gl_account,
            debit=0,
            credit=net_paid,
            memo=(
                f"TSA payment: {pv.voucher_number}"
                + (
                    f" (net of {total_deductions} deductions)"
                    if total_deductions > 0 else ""
                )
            ),
        )

    IPSASJournalService.post_journal(header, user)
    return header
