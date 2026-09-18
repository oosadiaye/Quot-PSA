"""Provision the draft Payment for an approved Payment Voucher.

Central payment processing: the moment a ``PaymentVoucherGov`` is
approved, a DRAFT ``Payment`` is materialised in Outgoing Payments so
the Treasury operator can pick a bank account and post it. Posting the
Payment is the ONLY disbursement event (the PV no longer posts its own
GL journal — "Mark Paid" was removed).

The draft carries everything the payment post needs to build the
deduction-aware journal (DR vendor/AP or Vendor-Advance recon = gross /
CR each deduction G/L / CR bank = net):

  * Invoice PV  → a ``PaymentAllocation`` to the matched ``VendorInvoice``
                  for the full GROSS (WHT is withheld, but the invoice is
                  settled in full — the deduction is remitted separately).
  * Advance PV  → ``is_advance=True``, NO allocation (no invoice exists;
                  the advance clears against invoices later, F-54).

``Payment.total_amount`` stays NET (cash out) — the same value
``schedule_payment`` has always set — so bank balance, bank
reconciliation and ``PaymentInstruction.amount`` keep matching the
actual cash that leaves the TSA. Gross / deductions are read from the
linked PV at post time.

This helper is the single source of truth for that draft, called from
``PaymentVoucherViewSet.approve`` / ``schedule_payment``, the
``backfill_pv_payments`` command, and the workflow-dispatch receiver.
It is idempotent: one PV maps to at most one non-void Payment, and it
never touches a Payment that has already posted.

No ``transaction.atomic`` here — callers own the transaction (mirrors
``payment_voucher_posting.py`` / ``vendor_advance.py``).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from accounting.models.treasury import PaymentVoucherGov
    from accounting.models.receivables import Payment


def _resolve_invoice(pv):
    """Best-effort ``VendorInvoice`` behind the PV's ``invoice_number``.

    Returns ``None`` for salary / statutory / direct PVs that reference
    no invoice — those post allocation-free.
    """
    if not pv.invoice_number:
        return None
    from accounting.models.receivables import VendorInvoice
    return (
        VendorInvoice.objects
        .filter(invoice_number=pv.invoice_number)
        .select_related('vendor')
        .first()
    )


def _ensure_allocation(payment, invoice, *, amount) -> None:
    """Create the payment→invoice allocation once (gross), if missing."""
    if invoice is None:
        return
    from accounting.models.receivables import PaymentAllocation
    exists = payment.allocations.filter(invoice=invoice).exists()
    if not exists:
        PaymentAllocation.objects.create(
            payment=payment, invoice=invoice, amount=amount,
        )


def ensure_draft_payment_for_pv(pv: "PaymentVoucherGov", *, actor=None) -> "Payment":
    """Idempotently materialise the DRAFT Payment for an approved PV.

    Returns the existing non-void Payment (topping up its allocation if
    needed) or creates a new Draft one. Never creates a second Payment
    and never mutates a Posted/Void one.
    """
    from accounting.models import TransactionSequence
    from accounting.models.receivables import Payment
    from datetime import date as _date

    from accounting.models.treasury import PaymentVoucherGov

    # Serialise concurrent provisioning for the same PV (a double-submitted
    # approve/schedule, or the workflow receiver racing the approve action).
    # The row lock is held in the caller's transaction; the idempotency
    # check below then sees any Payment a competing txn committed. The DB
    # partial-unique constraint on Payment (payment_voucher WHERE status !=
    # 'Void') is the belt-and-suspenders backstop.
    PaymentVoucherGov.objects.select_for_update().filter(pk=pv.pk).first()

    is_advance = bool(
        pv.payment_type == 'ADVANCE'
        and pv.special_gl_indicator == 'A'
        and pv.vendor_id
    )

    invoice = None if is_advance else _resolve_invoice(pv)
    vendor = pv.vendor if (is_advance or invoice is None) else invoice.vendor

    # Idempotency — reuse any live (non-void) Payment already linked.
    existing = pv.cash_payments.exclude(status='Void').order_by('id').first()
    if existing is not None:
        if not is_advance:
            _ensure_allocation(existing, invoice, amount=pv.gross_amount)
        return existing

    payment_number = TransactionSequence.get_next('payment', 'PAY-')
    payment = Payment.objects.create(
        payment_number=payment_number,
        payment_date=_date.today(),
        payment_method='Wire',  # operator can change before posting
        reference_number=pv.voucher_number or '',
        total_amount=pv.net_amount,  # NET = cash out (keeps bank rec correct)
        status='Draft',
        payment_voucher=pv,
        vendor=vendor,
        is_advance=is_advance,
        advance_type='Supplier Advance' if is_advance else '',
        document_number=payment_number,
        created_by=actor,
    )

    if not is_advance:
        # Invoice settled at GROSS; the deduction is withheld from cash,
        # not from the vendor's settlement.
        _ensure_allocation(payment, invoice, amount=pv.gross_amount)

    return payment
