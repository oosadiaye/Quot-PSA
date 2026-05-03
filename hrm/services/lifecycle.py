"""Employee lifecycle automation: promotion, transfer, retirement.

Public API:
    implement_promotion(promotion, *, to_step=None, user=None)
    implement_transfer(transfer, *, user=None)
    check_retirement_eligibility(employee, *, as_of=None) -> tuple[bool, str|None]
    sweep_retirements_due(as_of=None, *, user=None, dry_run=False) -> RetirementSweepSummary

Public Service Rules §020908 & Pension Reform Act 2014 triggers:
    * Compulsory retirement at age 60, or
    * Mandatory retirement after 35 years of continuous pensionable
      service (whichever comes first).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from django.db import transaction
from django.utils import timezone

from hrm.models import (
    Employee,
    EmployeeGradePlacement,
    EmployeeTransfer,
    Promotion,
    RetirementRecord,
)

COMPULSORY_RETIREMENT_AGE = 60
MAX_PENSIONABLE_YEARS = 35


class LifecycleError(Exception):
    """Raised for invalid state transitions in the lifecycle machine."""


@dataclass(frozen=True)
class RetirementSweepSummary:
    """Immutable result from :func:`sweep_retirements_due`."""

    as_of: date
    employees_considered: int
    records_created: int
    already_flagged: int
    not_eligible: int
    dry_run: bool


# --------------------------------------------------------------------------- #
# Date helpers (pure; no DB)
# --------------------------------------------------------------------------- #

def _age_years(dob: date, as_of: date) -> int:
    """Whole years between ``dob`` and ``as_of``."""
    years = as_of.year - dob.year
    if (as_of.month, as_of.day) < (dob.month, dob.day):
        years -= 1
    return years


def _service_years(hire_date: date, as_of: date) -> int:
    """Whole years of continuous service."""
    if hire_date > as_of:
        return 0
    years = as_of.year - hire_date.year
    if (as_of.month, as_of.day) < (hire_date.month, hire_date.day):
        years -= 1
    return max(years, 0)


def _extract_dob(employee: Employee) -> Optional[date]:
    """Best-effort DOB lookup from ``personal_info`` JSON."""
    info = employee.personal_info or {}
    raw = info.get('date_of_birth') or info.get('dob')
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# Promotion
# --------------------------------------------------------------------------- #

@transaction.atomic
def implement_promotion(
    promotion: Promotion,
    *,
    to_step=None,
    user=None,
) -> Promotion:
    """Finalise an approved promotion.

    Effects:
        * Updates the employee's ``position`` and ``base_salary``.
        * Optionally inserts an :class:`EmployeeGradePlacement` with
          reason ``Promotion`` when ``to_step`` is provided.
        * Flips promotion status to ``Implemented``.
    """
    if promotion.status != 'Approved':
        raise LifecycleError(
            f'Cannot implement promotion in status {promotion.status!r}; '
            'must be Approved first.'
        )

    employee = promotion.employee
    if promotion.to_position is not None:
        employee.position = promotion.to_position
    if promotion.to_salary is not None:
        employee.base_salary = promotion.to_salary
    employee.save(update_fields=['position', 'base_salary'])

    if to_step is not None:
        EmployeeGradePlacement.objects.create(
            employee=employee,
            step=to_step,
            effective_from=promotion.effective_date,
            reason='Promotion',
            notes=f'Promotion #{promotion.pk}: {promotion.reason[:120]}',
            created_by=user,
            updated_by=user,
        )

    promotion.status = 'Implemented'
    promotion.save(update_fields=['status'])
    return promotion


# --------------------------------------------------------------------------- #
# Transfer
# --------------------------------------------------------------------------- #

@transaction.atomic
def implement_transfer(
    transfer: EmployeeTransfer, *, user=None,
) -> EmployeeTransfer:
    """Finalise an approved transfer — move employee to new dept/position."""
    if transfer.status != 'Approved':
        raise LifecycleError(
            f'Cannot implement transfer in status {transfer.status!r}; '
            'must be Approved first.'
        )

    employee = transfer.employee
    employee.department = transfer.to_department
    employee.position = transfer.to_position
    employee.save(update_fields=['department', 'position'])

    transfer.status = 'Implemented'
    transfer.implemented_at = timezone.now()
    transfer.approved_by = transfer.approved_by or user
    transfer.save(update_fields=['status', 'implemented_at', 'approved_by'])
    return transfer


# --------------------------------------------------------------------------- #
# Retirement
# --------------------------------------------------------------------------- #

def check_retirement_eligibility(
    employee: Employee, *, as_of: Optional[date] = None,
) -> tuple[bool, Optional[str]]:
    """Return (eligible, trigger_code).

    trigger_code ∈ {'Age_60', 'Service_35', None}.
    The trigger fires the moment either threshold is reached.
    """
    as_of = as_of or timezone.now().date()
    if employee.status != 'Active':
        return False, None

    dob = _extract_dob(employee)
    if dob is not None and _age_years(dob, as_of) >= COMPULSORY_RETIREMENT_AGE:
        return True, 'Age_60'

    if employee.hire_date and _service_years(employee.hire_date, as_of) >= MAX_PENSIONABLE_YEARS:
        return True, 'Service_35'

    return False, None


@transaction.atomic
def _create_retirement_record(
    employee: Employee,
    trigger: str,
    retirement_date: date,
    *,
    user=None,
) -> RetirementRecord:
    record, created = RetirementRecord.objects.get_or_create(
        employee=employee,
        defaults={
            'trigger': trigger,
            'retirement_date': retirement_date,
            'status': 'Pending',
            'created_by': user,
            'updated_by': user,
        },
    )
    if created:
        # Keep the employee active until HR finalises the record — the
        # sweep flags eligibility; it does NOT unilaterally terminate.
        pass
    return record


def sweep_retirements_due(
    as_of: Optional[date] = None, *, user=None, dry_run: bool = False,
) -> RetirementSweepSummary:
    """Scan every active employee and flag statutory retirees.

    Creates one :class:`RetirementRecord` per newly-eligible employee.
    Idempotent: employees that already have a record are counted as
    ``already_flagged`` and skipped. When ``dry_run=True`` nothing is
    written.
    """
    as_of = as_of or timezone.now().date()
    qs = Employee.objects.filter(status='Active').iterator()

    considered = 0
    created = 0
    already = 0
    not_eligible = 0

    for emp in qs:
        considered += 1
        eligible, trigger = check_retirement_eligibility(emp, as_of=as_of)
        if not eligible:
            not_eligible += 1
            continue
        if RetirementRecord.objects.filter(employee=emp).exists():
            already += 1
            continue
        if not dry_run:
            _create_retirement_record(emp, trigger, as_of, user=user)
        created += 1

    return RetirementSweepSummary(
        as_of=as_of,
        employees_considered=considered,
        records_created=created,
        already_flagged=already,
        not_eligible=not_eligible,
        dry_run=dry_run,
    )
