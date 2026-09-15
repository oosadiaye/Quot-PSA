"""
How much of a vendor invoice may still be allocated to a payment.

Extracted from ``PaymentAllocationViewSet.perform_create`` so the
arithmetic can be tested without a database, and because it was wrong.

The rule has to reconcile two places the same money is recorded:

  * ``invoice.paid_amount`` — incremented when a payment is **posted**;
  * ``PaymentAllocation`` rows — created while a payment is still Draft,
    and left in place after it posts.

A posted allocation therefore appears in both. Summing every allocation
and comparing it against ``total_amount - paid_amount`` counts it twice,
and the consequence is not a rounding error — it is that an invoice
becomes unpayable after its first instalment:

    invoice 1,000,000, first payment 600,000 posted
    remaining balance                        400,000
    sum of all allocations                   600,000
    600,000 + 400,000 > 400,000           -> rejected

Paying the exact outstanding balance was refused. On a public-sector
ledger, where interim certificates and staged payments are the norm
rather than the exception, that is most invoices.

Only allocations still sitting on **Draft** payments are outstanding.
Posted ones are already inside ``paid_amount``; Void ones were reversed
and represent no claim on the invoice at all.
"""
from __future__ import annotations

from decimal import Decimal

#: Payment statuses and what they mean for this calculation.
#:
#: Draft  — allocation is a claim not yet reflected in paid_amount
#: Posted — already inside paid_amount; counting it again double-counts
#: Void   — reversed; represents no claim
PENDING_PAYMENT_STATUS = "Draft"


def remaining_allocatable(
    *,
    total_amount: Decimal,
    paid_amount: Decimal,
    pending_allocated: Decimal,
) -> Decimal:
    """What is left of an invoice to allocate.

    ``pending_allocated`` is the sum of allocations on Draft payments
    only — see the module docstring for why every-allocation is the
    wrong input here.

    Never returns a negative: an invoice already over-allocated has zero
    room, not negative room, and letting the figure go below zero would
    make the error message quote a nonsensical amount.
    """
    remaining = (
        Decimal(total_amount) - Decimal(paid_amount) - Decimal(pending_allocated)
    )
    return remaining if remaining > 0 else Decimal("0")


def check_allocation(
    *,
    amount: Decimal,
    total_amount: Decimal,
    paid_amount: Decimal,
    pending_allocated: Decimal,
) -> str | None:
    """Return an error message, or None when the allocation is allowed.

    Returning the message rather than raising keeps this importable from
    anywhere — a serializer, a service, a management command — without
    each caller having to know which exception type the others expect.
    """
    amount = Decimal(amount)
    if amount <= 0:
        return "Allocation amount must be greater than zero."

    remaining = remaining_allocatable(
        total_amount=total_amount,
        paid_amount=paid_amount,
        pending_allocated=pending_allocated,
    )
    if amount > remaining:
        return (
            f"Allocation of {amount} exceeds the remaining invoice balance "
            f"({remaining})."
        )
    return None


def pending_allocated_for(invoice, *, exclude_allocation_id: int | None = None) -> Decimal:
    """Sum of allocations against ``invoice`` that are not yet posted.

    ``exclude_allocation_id`` lets an edit exclude the row being changed,
    so raising an allocation from 100 to 150 is measured against the
    other 100s rather than against itself.
    """
    from django.db.models import Sum

    from accounting.models.receivables import PaymentAllocation

    qs = PaymentAllocation.objects.filter(
        invoice=invoice, payment__status=PENDING_PAYMENT_STATUS,
    )
    if exclude_allocation_id is not None:
        qs = qs.exclude(pk=exclude_allocation_id)
    return qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")
