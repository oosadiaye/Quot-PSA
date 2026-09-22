"""Vendor open-item clearing (Supplier History) — SAP F-44 style.

Applies available vendor **credit** against **open invoices**
(``balance_due > 0``), oldest-first (FIFO), capped so nothing is over-applied.

Two credit sources, each routed to its correct posting engine:

* **Outstanding vendor advances** → ``VendorAdvanceService.clear`` posts the
  contra journal (DR AP-recon / CR Vendor-Advance) — the advance obligation
  moves into AP — and we bump the invoice's ``paid_amount`` so its balance
  drops. Net AP then equals what is still owed. (SAP down-payment clearing.)
* **Unapplied posted payments** (non-advance ``Payment`` with an unallocated
  remainder) → a new ``PaymentAllocation`` links the payment to the invoice.
  **GL-neutral** — the payment already debited AP at post time.

Nothing here posts an expense or moves cash: it only *matches* items that are
already on the ledger. See
``docs/superpowers/specs/2026-09-21-vendor-open-item-clearing-design.md``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

ZERO = Decimal("0.00")


def _q(amount) -> Decimal:
    """Quantise to 2dp; treats None as zero."""
    return Decimal(str(amount or 0)).quantize(Decimal("0.01"))


def open_invoices_for_vendor(vendor) -> list:
    """Posted vendor invoices with an outstanding balance, oldest-first."""
    from accounting.models.receivables import VendorInvoice

    rows = (
        VendorInvoice.objects
        .filter(vendor=vendor, status__in=["Posted", "Partially Paid"])
        .order_by("invoice_date", "id")
    )
    return [inv for inv in rows if _q(inv.balance_due) > ZERO]


def unapplied_payments_for_vendor(vendor) -> list[tuple]:
    """Posted, non-advance payments carrying an unallocated remainder — i.e.
    on-account cash that already hit AP. Returns ``[(payment, remaining)]``
    oldest-first."""
    from accounting.models.receivables import Payment

    out: list[tuple] = []
    payments = (
        Payment.objects
        .filter(vendor=vendor, status="Posted", is_advance=False)
        .order_by("payment_date", "id")
    )
    for pmt in payments:
        allocated = pmt.allocations.aggregate(s=Sum("amount"))["s"] or ZERO
        remaining = _q(pmt.total_amount) - _q(allocated)
        if remaining > ZERO:
            out.append((pmt, remaining))
    return out


@dataclass
class ClearLine:
    invoice_id: int
    invoice_number: str
    amount: Decimal
    source: str          # 'advance' | 'payment'
    source_reference: str


def open_items_for_vendor(vendor) -> dict:
    """Read model for the Open Items tab: what is open and what credit is
    available to clear it. Amounts are strings for JSON transport."""
    from accounting.services.vendor_advance import VendorAdvanceService

    invoices = open_invoices_for_vendor(vendor)
    advances = VendorAdvanceService.list_outstanding(vendor)
    payments = unapplied_payments_for_vendor(vendor)

    advance_credit = sum((_q(a.amount_outstanding) for a in advances), ZERO)
    payment_credit = sum((rem for _p, rem in payments), ZERO)
    open_total = sum((_q(inv.balance_due) for inv in invoices), ZERO)

    return {
        "open_invoices": [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "invoice_date": inv.invoice_date,
                "total_amount": str(_q(inv.total_amount)),
                "balance_due": str(_q(inv.balance_due)),
            }
            for inv in invoices
        ],
        "open_total": str(open_total),
        "available_credit": str(advance_credit + payment_credit),
        "advance_credit": str(advance_credit),
        "payment_credit": str(payment_credit),
    }


@transaction.atomic
def clear_open_items(vendor, *, invoice_ids=None, actor=None, posting_date=None) -> dict:
    """Apply available vendor credit (advances first, then unapplied payments)
    against open invoices, oldest-first, capped at each invoice's balance and
    each credit's remaining amount. All-or-nothing within one transaction.

    ``invoice_ids`` restricts clearing to those invoices (manual mode); omit it
    to clear every open invoice (auto-clear).
    """
    from accounting.models.receivables import PaymentAllocation
    from accounting.services.vendor_advance import VendorAdvanceService

    posting_date = posting_date or _date.today()

    invoices = open_invoices_for_vendor(vendor)
    if invoice_ids:
        wanted = {int(i) for i in invoice_ids}
        invoices = [inv for inv in invoices if inv.id in wanted]

    advances = VendorAdvanceService.list_outstanding(vendor)          # oldest-first
    adv_remaining: dict[int, Decimal] = {a.id: _q(a.amount_outstanding) for a in advances}

    payments = unapplied_payments_for_vendor(vendor)                  # [(pmt, remaining)]
    pay_remaining: dict[int, Decimal] = {p.id: rem for p, rem in payments}
    pay_by_id = {p.id: p for p, _rem in payments}

    lines: list[ClearLine] = []
    total = ZERO

    for inv in invoices:
        need = _q(inv.balance_due)
        if need <= ZERO:
            continue
        applied = ZERO   # how much credit this invoice actually received

        # 1) Advances — contra journal (DR AP / CR Vendor-Advance).
        for adv in advances:
            if need <= ZERO:
                break
            avail = adv_remaining.get(adv.id, ZERO)
            if avail <= ZERO:
                continue
            draw = min(avail, need)
            VendorAdvanceService.clear(
                advance=adv, amount=draw, posting_date=posting_date, actor=actor,
                cleared_against_type="vendor_invoice", cleared_against_id=inv.id,
                cleared_against_reference=inv.invoice_number,
                notes=f"Open-item clearing against invoice {inv.invoice_number}",
            )
            adv_remaining[adv.id] = avail - draw
            inv.paid_amount = _q(inv.paid_amount) + draw
            need -= draw
            applied += draw
            total += draw
            lines.append(ClearLine(inv.id, inv.invoice_number, draw, "advance", adv.reference))

        # 2) Unapplied payments — GL-neutral allocation.
        for pid in list(pay_remaining.keys()):
            if need <= ZERO:
                break
            avail = pay_remaining.get(pid, ZERO)
            if avail <= ZERO:
                continue
            draw = min(avail, need)
            PaymentAllocation.objects.create(payment=pay_by_id[pid], invoice=inv, amount=draw)
            pay_remaining[pid] = avail - draw
            inv.paid_amount = _q(inv.paid_amount) + draw
            need -= draw
            applied += draw
            total += draw
            lines.append(ClearLine(inv.id, inv.invoice_number, draw, "payment", pay_by_id[pid].payment_number))

        # Only touch invoices that actually received credit — an invoice the
        # FIFO run couldn't fund must stay 'Posted', not be mislabelled
        # 'Partially Paid'. ImmutableModelMixin blocks edits to a Posted row
        # unless _allow_status_change is set — the same escape hatch the
        # payment-posting propagation uses (payables.py).
        if applied > ZERO:
            new_balance = _q(inv.total_amount) - _q(inv.paid_amount)
            inv.status = "Paid" if new_balance <= ZERO else "Partially Paid"
            inv.save(_allow_status_change=True)

    return {
        "cleared": [
            {
                "invoice_id": ln.invoice_id,
                "invoice_number": ln.invoice_number,
                "amount": str(ln.amount),
                "source": ln.source,
                "source_reference": ln.source_reference,
            }
            for ln in lines
        ],
        "total_cleared": str(total),
        "invoices_touched": len({ln.invoice_id for ln in lines}),
    }
