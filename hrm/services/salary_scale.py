"""Grade-step salary scale service.

Public API:
    current_placement(employee, *, as_of=None) -> EmployeeGradePlacement | None
    monthly_basic_for(employee, *, as_of=None) -> Decimal | None
    place_employee(employee, step, *, effective_from, reason, user=None)
    advance_step(employee, *, as_of=None, user=None) -> EmployeeGradePlacement
    bulk_advance_due(as_of=None, *, user=None) -> AdvanceSummary

Placement is append-only. The "current" placement is the row with the
latest ``effective_from`` ≤ query date.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from hrm.models import (
    Employee,
    EmployeeGradePlacement,
    SalaryGrade,
    SalaryStep,
)


@dataclass(frozen=True)
class AdvanceSummary:
    """Immutable result from :func:`bulk_advance_due`."""

    as_of: date
    employees_considered: int
    advanced: int
    skipped_max_step: int
    skipped_not_due: int
    skipped_no_placement: int


# --------------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------------- #

def current_placement(
    employee: Employee, *, as_of: Optional[date] = None,
) -> Optional[EmployeeGradePlacement]:
    """Return the employee's active placement as of the given date."""
    as_of = as_of or timezone.now().date()
    return (
        EmployeeGradePlacement.objects
        .filter(employee=employee, effective_from__lte=as_of)
        .select_related('step', 'step__grade', 'step__grade__scale')
        .order_by('-effective_from', '-id')
        .first()
    )


def monthly_basic_for(
    employee: Employee, *, as_of: Optional[date] = None,
) -> Optional[Decimal]:
    """Monthly basic from the scale, or ``None`` if employee isn't placed."""
    placement = current_placement(employee, as_of=as_of)
    if placement is None:
        return None
    return placement.step.monthly_basic


# --------------------------------------------------------------------------- #
# Mutations
# --------------------------------------------------------------------------- #

@transaction.atomic
def place_employee(
    employee: Employee,
    step: SalaryStep,
    *,
    effective_from: date,
    reason: str,
    user=None,
    notes: str = '',
) -> EmployeeGradePlacement:
    """Record a new placement for the employee (insert-only ledger)."""
    return EmployeeGradePlacement.objects.create(
        employee=employee,
        step=step,
        effective_from=effective_from,
        reason=reason,
        notes=notes,
        created_by=user,
        updated_by=user,
    )


def _next_step(step: SalaryStep) -> Optional[SalaryStep]:
    """Return the next step within the same grade, or None if at top."""
    if step.step_number >= step.grade.max_steps:
        return None
    return SalaryStep.objects.filter(
        grade=step.grade, step_number=step.step_number + 1,
    ).first()


def _is_due(placement: EmployeeGradePlacement, as_of: date) -> bool:
    """Has the annual increment window elapsed?"""
    months = placement.step.grade.annual_increment_months
    earliest = date(
        placement.effective_from.year + (placement.effective_from.month - 1 + months) // 12,
        ((placement.effective_from.month - 1 + months) % 12) + 1,
        min(placement.effective_from.day, 28),
    )
    return as_of >= earliest


@transaction.atomic
def advance_step(
    employee: Employee, *, as_of: Optional[date] = None, user=None,
) -> Optional[EmployeeGradePlacement]:
    """Promote employee one step within their current grade (if due).

    Returns the new placement or ``None`` if no advance happened.
    """
    as_of = as_of or timezone.now().date()
    current = current_placement(employee, as_of=as_of)
    if current is None:
        return None
    if not _is_due(current, as_of):
        return None
    nxt = _next_step(current.step)
    if nxt is None:
        return None
    return place_employee(
        employee, nxt,
        effective_from=as_of,
        reason='Step_Increment',
        user=user,
        notes=(
            f'Auto-increment from {current.step.grade.code} '
            f'step {current.step.step_number} on {as_of.isoformat()}'
        ),
    )


def bulk_advance_due(
    as_of: Optional[date] = None, *, user=None,
) -> AdvanceSummary:
    """Run :func:`advance_step` across all active employees.

    Idempotent within the same day: re-running won't double-increment
    because the new placement's ``effective_from = as_of`` and the
    ``_is_due`` check looks N months ahead of that.
    """
    as_of = as_of or timezone.now().date()
    employees = Employee.objects.filter(status='Active').iterator()

    advanced = 0
    skipped_max = 0
    skipped_not_due = 0
    skipped_none = 0
    considered = 0

    for emp in employees:
        considered += 1
        current = current_placement(emp, as_of=as_of)
        if current is None:
            skipped_none += 1
            continue
        if not _is_due(current, as_of):
            skipped_not_due += 1
            continue
        nxt = _next_step(current.step)
        if nxt is None:
            skipped_max += 1
            continue
        place_employee(
            emp, nxt,
            effective_from=as_of, reason='Step_Increment', user=user,
            notes=f'Bulk auto-increment on {as_of.isoformat()}',
        )
        advanced += 1

    return AdvanceSummary(
        as_of=as_of,
        employees_considered=considered,
        advanced=advanced,
        skipped_max_step=skipped_max,
        skipped_not_due=skipped_not_due,
        skipped_no_placement=skipped_none,
    )
