"""Applying posted revenue collections to what taxpayers owe.

``apply_collection`` is called by the receiver for accounting's ``revenue_collected`` event. It is idempotent on the
receipt number: replaying the same receipt (a retry, a catch-up run) never reduces a balance twice.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Q

from .models import ArrearsLedger, CollectionApplication, DemandNotice, Taxpayer, TaxAccount

ZERO = Decimal('0')
OPEN_NOTICE_STATUSES = ('issued', 'partial', 'overdue')   # a disputed notice is not paid down until the dispute ends


@dataclass(frozen=True)
class ApplicationResult:
    applied: Decimal          # reduced arrears and notices
    unapplied: Decimal        # matched nothing: unknown TIN, or more than was owed
    already_applied: bool     # this receipt had been handled before; nothing changed


def _summarise(receipt_number: str) -> ApplicationResult:
    rows = CollectionApplication.objects.filter(collection_receipt=receipt_number)
    applied = sum((r.amount for r in rows if r.arrears_id or r.demand_notice_id), ZERO)
    unapplied = sum((r.amount for r in rows if not (r.arrears_id or r.demand_notice_id)), ZERO)
    return ApplicationResult(applied=applied, unapplied=unapplied, already_applied=True)


def _open_arrears(taxpayer, revenue_head):
    return (ArrearsLedger.objects.select_for_update(of=('self',))
            .filter(taxpayer=taxpayer, is_settled=False, amount__gt=0)
            .filter(Q(revenue_head=revenue_head) | Q(revenue_head__isnull=True))
            .order_by('arrears_date', 'id'))


def _open_notices(taxpayer, revenue_head):
    same_head = (Q(assessment__revenue_head=revenue_head) | Q(billing_run__revenue_head=revenue_head)
                 | Q(assessment__isnull=True, billing_run__isnull=True))
    return (DemandNotice.objects.select_for_update(of=('self',))
            .filter(taxpayer=taxpayer, status__in=OPEN_NOTICE_STATUSES).filter(same_head)
            .order_by('due_date', 'id'))


def apply_collection(*, receipt_number: str, payer_tin: str, revenue_head, amount: Decimal) -> ApplicationResult:
    """Reduce the payer's arrears (oldest first), then their open demand notices (earliest due first)."""
    amount = Decimal(amount)
    with transaction.atomic():
        if CollectionApplication.objects.filter(collection_receipt=receipt_number).exists():
            return _summarise(receipt_number)

        taxpayer = Taxpayer.objects.select_for_update().filter(tin__iexact=(payer_tin or '').strip()).first()
        remaining = amount
        line = 0
        if taxpayer is not None:
            for arrears in _open_arrears(taxpayer, revenue_head):
                if remaining <= ZERO:
                    break
                pay = min(remaining, arrears.amount)
                arrears.amount -= pay
                arrears.is_settled = arrears.amount <= ZERO
                arrears.save(update_fields=['amount', 'is_settled'])
                line += 1
                CollectionApplication.objects.create(
                    collection_receipt=receipt_number, line_no=line, taxpayer=taxpayer, arrears=arrears, amount=pay)
                remaining -= pay
            for notice in _open_notices(taxpayer, revenue_head):
                if remaining <= ZERO:
                    break
                pay = min(remaining, notice.amount_due - notice.amount_paid)
                if pay <= ZERO:
                    continue
                notice.amount_paid += pay
                notice.status = 'paid' if notice.amount_paid >= notice.amount_due else 'partial'
                notice.save(update_fields=['amount_paid', 'status'])
                line += 1
                CollectionApplication.objects.create(
                    collection_receipt=receipt_number, line_no=line, taxpayer=taxpayer, demand_notice=notice, amount=pay)
                remaining -= pay

            applied = amount - remaining
            if applied > ZERO:
                TaxAccount.objects.filter(taxpayer=taxpayer, revenue_head=revenue_head).update(
                    running_balance=F('running_balance') - applied)

        if remaining > ZERO or line == 0:       # always leave a row, so a replay is recognised
            CollectionApplication.objects.create(
                collection_receipt=receipt_number, line_no=line + 1, taxpayer=taxpayer, amount=remaining)
        return ApplicationResult(applied=amount - remaining, unapplied=remaining, already_applied=False)
