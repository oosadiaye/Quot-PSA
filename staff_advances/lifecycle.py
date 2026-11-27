"""The travel-advance workflow: request, approve, advance, retire.

Money movements go through ``StaffAdvanceGLService`` (the single posting path); this module only enforces the order of
the steps and that a retirement accounts for the whole advance. Separation of duties is by role and permission, not by
who created the record: any holder of the approving permission may approve.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from .models import StaffAdvance, TravelAdvance, TravelRequest, TravelRetirement
from .services import StaffAdvanceGLService

ZERO = Decimal('0')


class AdvanceError(Exception):
    """The step is not allowed in the record's current state, or the figures do not add up."""


def _require(request: TravelRequest, *allowed: str, verb: str) -> None:
    if request.status not in allowed:
        raise AdvanceError(f'A travel request that is {request.status} cannot be {verb}.')


def submit_travel_request(request: TravelRequest) -> TravelRequest:
    _require(request, 'draft', verb='submitted')
    if not request.destination.strip():
        raise AdvanceError('A travel request needs a destination.')
    if request.estimated_cost <= ZERO:
        raise AdvanceError('A travel request needs an estimated cost above zero.')
    if request.end_date < request.start_date:
        raise AdvanceError('The trip cannot end before it starts.')
    request.status = 'submitted'
    request.save(update_fields=['status', 'updated_at'])
    return request


def approve_travel_request(request: TravelRequest) -> TravelRequest:
    _require(request, 'submitted', verb='approved')
    request.status = 'approved'
    request.save(update_fields=['status', 'updated_at'])
    return request


def reject_travel_request(request: TravelRequest, reason: str) -> TravelRequest:
    _require(request, 'submitted', verb='rejected')
    if not (reason or '').strip():
        raise AdvanceError('Say why the request is rejected.')
    request.status = 'rejected'
    request.purpose = f'{request.purpose}\n[Rejected: {reason.strip()}]'.strip()
    request.save(update_fields=['status', 'purpose', 'updated_at'])
    return request


@transaction.atomic
def advance_travel(request: TravelRequest, *, actor, amount: Decimal | None = None, bank_account=None) -> TravelAdvance:
    """Pay an approved request's advance: raises the staff advance and posts DR recon / CR cash."""
    request = TravelRequest.objects.select_for_update().get(pk=request.pk)
    _require(request, 'approved', verb='advanced')
    amount = Decimal(amount) if amount is not None else request.estimated_cost
    if amount <= ZERO:
        raise AdvanceError('The advance must be more than zero.')
    recon = StaffAdvanceGLService.resolve_recon_account()
    if recon is None:
        raise AdvanceError('No staff-advance reconciliation account is configured.')
    staff_advance = StaffAdvance.objects.create(
        employee=request.employee, recon_account=recon, purpose='travel', amount=amount,
        reference=f'TRAVEL-{request.pk:05d}', notes=f'Travel to {request.destination}',
    )
    StaffAdvanceGLService.disburse(staff_advance=staff_advance, actor=actor, bank_account=bank_account)
    travel_advance = TravelAdvance.objects.create(travel_request=request, staff_advance=staff_advance, amount=amount)
    request.status = 'advanced'
    request.save(update_fields=['status', 'updated_at'])
    return travel_advance


@transaction.atomic
def retire_travel(retirement: TravelRetirement, *, actor, expense_account=None, bank_account=None) -> TravelRetirement:
    """Account for a travel advance: what was spent is charged to expenditure, what is left is returned in cash.

    The two must add up to the advance exactly. Both are posted through the recovery path, so the advance clears
    through the same journals as any other recovery and cannot be retired twice.
    """
    advance = retirement.travel_advance
    staff_advance = StaffAdvance.objects.select_for_update().get(pk=advance.staff_advance_id)
    if staff_advance.status == 'CLEARED':
        raise AdvanceError('This advance has already been retired.')
    spent, returned = retirement.amount, retirement.balance_returned
    if spent < ZERO or returned < ZERO:
        raise AdvanceError('Amounts cannot be negative.')
    outstanding = staff_advance.amount - staff_advance.recovered_amount
    if spent + returned != outstanding:
        raise AdvanceError(
            f'A retirement must account for the whole advance: {outstanding} is outstanding but '
            f'spent {spent} + returned {returned} = {spent + returned}.')
    if spent > ZERO:
        StaffAdvanceGLService.record_recovery(
            staff_advance=staff_advance, amount=spent, actor=actor, expense_account=expense_account,
            posting_date=retirement.retired_date, notes='travel expenses retired')
    if returned > ZERO:
        cash = StaffAdvanceGLService._resolve_cash_account(bank_account)
        StaffAdvanceGLService.record_recovery(
            staff_advance=staff_advance, amount=returned, actor=actor, expense_account=cash,
            posting_date=retirement.retired_date, notes='unspent balance returned in cash')
    request = advance.travel_request
    request.status = 'retired'
    request.save(update_fields=['status', 'updated_at'])
    return retirement
