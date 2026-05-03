"""Deterministic monthly leave accrual engine.

The accrual job is **idempotent**: re-running it for the same (year, month)
credits each eligible (employee, leave_type) pair exactly once, guaranteed
by the ``LeaveAccrualEntry`` unique_together constraint.

Public API:
    accrue_month(year, month, *, user=None) -> AccrualSummary
    employee_balance(employee, leave_type, year) -> Decimal
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from django.db import transaction
from django.db.models import Sum

from hrm.models import (
    Employee,
    LeaveAccrualEntry,
    LeavePolicy,
    LeaveRequest,
    LeaveType,
)

ZERO = Decimal('0.00')


@dataclass(frozen=True)
class AccrualSummary:
    """Immutable result of a single :func:`accrue_month` call."""

    year: int
    month: int
    entries_created: int
    entries_skipped: int
    employees_considered: int
    total_days_credited: Decimal


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _completed_months(hire_date: date, as_of: date) -> int:
    """Whole months between ``hire_date`` and ``as_of`` (inclusive of start)."""
    if hire_date > as_of:
        return 0
    months = (as_of.year - hire_date.year) * 12 + (as_of.month - hire_date.month)
    if as_of.day < hire_date.day:
        months -= 1
    return max(months, 0)


def _current_balance(
    employee: Employee, leave_type: LeaveType, year: int
) -> Decimal:
    """Year-to-date accrued - taken for the employee/type."""
    accrued = (
        LeaveAccrualEntry.objects.filter(
            employee=employee, leave_type=leave_type, year=year,
        ).aggregate(total=Sum('days_credited'))['total'] or ZERO
    )
    taken = (
        LeaveRequest.objects.filter(
            employee=employee,
            leave_type=leave_type,
            status='Approved',
            start_date__year=year,
        ).aggregate(total=Sum('total_days'))['total'] or ZERO
    )
    return Decimal(accrued) - Decimal(taken)


def _eligible_policies() -> Iterable[LeavePolicy]:
    return LeavePolicy.objects.select_related('leave_type').filter(
        is_active=True, leave_type__is_active=True,
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

@transaction.atomic
def accrue_month(year: int, month: int, *, user=None) -> AccrualSummary:
    """Credit one month's worth of leave for every eligible employee.

    Idempotent: unique_together on (employee, leave_type, year, month)
    makes duplicate inserts raise IntegrityError, which we catch and
    count as ``entries_skipped``.
    """
    if not (1 <= month <= 12):
        raise ValueError(f'month must be 1..12, got {month}')
    if year < 2000 or year > 2100:
        raise ValueError(f'year out of range: {year}')

    as_of = date(year, month, 1)
    employees = list(Employee.objects.filter(status='Active'))
    policies = list(_eligible_policies())

    entries_created = 0
    entries_skipped = 0
    total_credited = ZERO

    for emp in employees:
        if not emp.hire_date:
            continue

        for policy in policies:
            if policy.accrual_per_month <= ZERO:
                continue

            completed = _completed_months(emp.hire_date, as_of)
            if completed < policy.min_service_months:
                entries_skipped += 1
                continue

            # Honour max_balance cap (0 = uncapped).
            if policy.max_balance > ZERO:
                current = _current_balance(emp, policy.leave_type, year)
                if current >= policy.max_balance:
                    entries_skipped += 1
                    continue
                headroom = policy.max_balance - current
                credit = min(policy.accrual_per_month, headroom)
            else:
                credit = policy.accrual_per_month

            if credit <= ZERO:
                entries_skipped += 1
                continue

            _, created = LeaveAccrualEntry.objects.get_or_create(
                employee=emp,
                leave_type=policy.leave_type,
                year=year,
                month=month,
                defaults={
                    'days_credited': credit,
                    'notes': f'Auto-accrual {year}-{month:02d}',
                    'created_by': user,
                    'updated_by': user,
                },
            )
            if created:
                entries_created += 1
                total_credited += credit
            else:
                entries_skipped += 1

    return AccrualSummary(
        year=year,
        month=month,
        entries_created=entries_created,
        entries_skipped=entries_skipped,
        employees_considered=len(employees),
        total_days_credited=total_credited.quantize(Decimal('0.01')),
    )


def employee_balance(
    employee: Employee, leave_type: LeaveType, year: int,
) -> Decimal:
    """Return an employee's net leave balance for a given type/year."""
    return _current_balance(employee, leave_type, year).quantize(Decimal('0.01'))
