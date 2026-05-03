"""Deterministic payroll pipeline for the PSA ERP (Phase 3).

This module replaces ad-hoc payroll processing with a single, auditable
pipeline:

1. ``compute_line(employee, period)`` — pure function that returns a
   :class:`PayrollCalculation` dataclass describing every earning,
   statutory deduction, and net pay amount. No database writes.
2. ``run_payroll(run, user)`` — orchestrator that calls ``compute_line``
   for every active employee on the run's period and commits the result
   atomically.

The pipeline applies:

* **PAYE** via :class:`PAYECalculationService` using the live
  ``NigeriaTaxBracket`` table (with Finance Act 2020 fallback).
* **Pension** (8% employee / 10% employer default) via
  :class:`PensionCalculationService`.
* **NHF** — 2.5% of basic salary.
* Salary components from the employee's ``SalaryStructure``
  (``Earning`` rows lift gross; non-statutory ``Deduction`` rows are
  subtracted as ``other_deductions``).

The design is deliberately **replayable**: feeding the same employee +
period state into ``compute_line`` twice yields identical output, which
is what makes payroll auditable for Office of the Accountant-General
inspections.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from typing import Iterable

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from hrm.models import (
    Employee,
    PayrollDeduction,
    PayrollEarning,
    PayrollLine,
    PayrollPeriod,
    PayrollRun,
    Payslip,
    SalaryComponent,
    SalaryStructureTemplate,
    StatutoryDeduction,
    StatutoryDeductionTemplate,
)
from hrm.services.payroll_computation import (
    PAYECalculationService,
    PensionCalculationService,
)

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
TWO_PLACES = Decimal("0.01")


def _q(amount: Decimal) -> Decimal:
    """Quantize to 2 decimal places using banker's-friendly half-up."""
    return amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Pure computation layer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentLine:
    """One row of either earnings or deductions on the payslip."""

    component_id: int
    name: str
    amount: Decimal
    is_earning: bool


@dataclass(frozen=True)
class StatutoryLine:
    """One applied ``StatutoryDeductionTemplate`` row."""

    template_id: int
    code: str
    deduction_type: str
    employee_amount: Decimal
    employer_amount: Decimal


@dataclass(frozen=True)
class PayrollCalculation:
    """Complete payslip figures for a single employee in one period.

    Instances are immutable — once built, they represent the definitive
    record of how the line was calculated.
    """

    employee_id: int
    basic_salary: Decimal
    gross_salary: Decimal
    total_earnings: Decimal
    total_deductions: Decimal
    net_salary: Decimal
    tax_deduction: Decimal
    pension_deduction: Decimal
    nhf_deduction: Decimal
    other_deductions: Decimal
    employer_pension: Decimal
    working_days: int
    components: tuple[ComponentLine, ...] = field(default_factory=tuple)
    statutory: tuple[StatutoryLine, ...] = field(default_factory=tuple)


def _working_days_in_period(period: PayrollPeriod) -> int:
    current = period.start_date
    total = 0
    while current <= period.end_date:
        if current.weekday() < 5:  # Mon-Fri
            total += 1
        current += timedelta(days=1)
    return total


def _component_amount(component: SalaryComponent, basic: Decimal) -> Decimal:
    """Resolve a salary component to its monetary amount."""
    if component.calculation_type == "Percentage" and component.percentage_of_basic:
        return basic * component.percentage_of_basic / Decimal("100")
    # Fixed or Variable both fall back to ``value``.
    return component.value or ZERO


def compute_line(
    employee: Employee,
    period: PayrollPeriod,
    *,
    statutory_templates: Iterable[StatutoryDeductionTemplate] | None = None,
    auto_statutory: bool = True,
) -> PayrollCalculation:
    """Return the deterministic payslip calculation for ``employee``.

    The ``auto_statutory`` flag (default True) applies PAYE, pension,
    and NHF from Nigerian statutory rules. Callers who want to compute
    only from explicit ``StatutoryDeductionTemplate`` rows (the legacy
    behaviour) can pass ``auto_statutory=False``.
    """
    # Prefer the grade-step scale amount if the employee has a placement;
    # fall back to the raw ``base_salary`` field otherwise. Imported lazily
    # to avoid a circular hit during migration/collectstatic.
    basic = employee.base_salary or ZERO
    try:
        from hrm.services.salary_scale import monthly_basic_for
        scale_basic = monthly_basic_for(employee, as_of=period.start_date)
        if scale_basic is not None:
            basic = scale_basic
    except Exception:  # noqa: BLE001 — scale is optional, never break payroll
        pass

    components: list[ComponentLine] = []

    total_earnings = basic
    other_deductions = ZERO
    housing = ZERO
    transport = ZERO

    # ---- Salary structure components -------------------------------------
    if employee.salary_structure:
        templates = (
            SalaryStructureTemplate.objects.filter(
                salary_structure=employee.salary_structure, is_active=True
            )
            .select_related("component")
        )
        for tmpl in templates:
            comp = tmpl.component
            if not comp.is_active:
                continue
            amount = _q(_component_amount(comp, basic))
            if amount <= 0:
                continue
            if comp.component_type == "Earning":
                total_earnings += amount
                components.append(
                    ComponentLine(comp.pk, comp.name, amount, is_earning=True)
                )
                # Heuristic: detect housing/transport by code so the
                # pension base matches Pension Reform Act 2014.
                code = (comp.code or "").upper()
                if "HOUS" in code:
                    housing += amount
                elif "TRANS" in code:
                    transport += amount
            elif comp.component_type == "Deduction":
                other_deductions += amount
                components.append(
                    ComponentLine(comp.pk, comp.name, amount, is_earning=False)
                )

    gross = _q(total_earnings)

    # ---- Statutory deductions (PAYE, Pension, NHF) -----------------------
    statutory: list[StatutoryLine] = []
    tax_deduction = ZERO
    pension_deduction = ZERO
    employer_pension = ZERO
    nhf_deduction = ZERO

    if auto_statutory:
        pension_result = PensionCalculationService.compute_contributions(
            basic_salary=basic,
            housing_allowance=housing,
            transport_allowance=transport,
        )
        pension_deduction = _q(pension_result["employee_amount"])
        employer_pension = _q(pension_result["employer_amount"])
        nhf_deduction = _q(PensionCalculationService.compute_nhf(basic))

        paye = PAYECalculationService.compute_monthly_paye(
            gross_monthly=gross,
            pension_employee=pension_deduction,
            nhf=nhf_deduction,
        )
        tax_deduction = _q(paye["monthly_paye"])

    # ---- Explicit StatutoryDeductionTemplate rows ------------------------
    if statutory_templates is None:
        statutory_templates = (
            StatutoryDeductionTemplate.objects.filter(is_active=True)
            if not auto_statutory
            else []
        )
    for tmpl in statutory_templates:
        applies = tmpl.applies_to_employment_types or []
        if applies and employee.employee_type not in applies:
            continue
        emp_amount = _q(tmpl.calculate_deduction(gross))
        if tmpl.employer_fixed and tmpl.employer_fixed > 0:
            employer_amount = _q(tmpl.employer_fixed)
        elif tmpl.employer_rate and tmpl.employer_rate > 0:
            employer_amount = _q(gross * tmpl.employer_rate)
        else:
            employer_amount = ZERO
        if emp_amount <= 0 and employer_amount <= 0:
            continue
        statutory.append(
            StatutoryLine(
                template_id=tmpl.pk,
                code=tmpl.code,
                deduction_type=tmpl.deduction_type,
                employee_amount=emp_amount,
                employer_amount=employer_amount,
            )
        )
        if tmpl.deduction_type in {"Tier1", "Tier2"}:
            pension_deduction += emp_amount
        elif tmpl.deduction_type == "Income_Tax":
            tax_deduction += emp_amount
        else:
            other_deductions += emp_amount

    total_deductions = _q(
        tax_deduction + pension_deduction + nhf_deduction + other_deductions
    )
    net_salary = _q(gross - total_deductions)

    return PayrollCalculation(
        employee_id=employee.pk,
        basic_salary=_q(basic),
        gross_salary=gross,
        total_earnings=gross,  # gross already includes basic + earnings
        total_deductions=total_deductions,
        net_salary=net_salary,
        tax_deduction=_q(tax_deduction),
        pension_deduction=_q(pension_deduction),
        nhf_deduction=_q(nhf_deduction),
        other_deductions=_q(other_deductions),
        employer_pension=_q(employer_pension),
        working_days=_working_days_in_period(period),
        components=tuple(components),
        statutory=tuple(statutory),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


@dataclass
class PayrollRunSummary:
    run_id: int
    employees_processed: int
    total_gross: Decimal
    total_deductions: Decimal
    total_net: Decimal


@transaction.atomic
def run_payroll(
    run: PayrollRun,
    *,
    user=None,
    auto_statutory: bool = True,
) -> PayrollRunSummary:
    """Compute and persist every line on ``run``.

    Safe to call repeatedly only on ``Draft`` runs; raises ``ValueError``
    otherwise so callers can't silently overwrite an approved run.
    """
    if run.status != "Draft":
        raise ValueError(
            f"Run {run.run_number} is in {run.status} status — only Draft runs can be processed."
        )

    period = run.period
    employees = (
        Employee.objects.filter(status__in=["Active", "Probation"])
        .select_related("salary_structure", "user")
    )
    statutory_templates = list(
        StatutoryDeductionTemplate.objects.filter(is_active=True)
    )

    # Wipe any existing draft lines so re-running is idempotent.
    run.lines.all().delete()

    employee_count = 0
    for employee in employees:
        calc = compute_line(
            employee,
            period,
            statutory_templates=statutory_templates,
            auto_statutory=auto_statutory,
        )
        _persist_line(run, employee, calc)
        employee_count += 1

    totals = run.lines.aggregate(
        total_gross=Sum("gross_salary"),
        total_deductions=Sum("total_deductions"),
        total_net=Sum("net_salary"),
    )
    run.total_gross = totals["total_gross"] or ZERO
    run.total_deductions = totals["total_deductions"] or ZERO
    run.total_net = totals["total_net"] or ZERO
    run.status = "In Progress"
    if user:
        run.processed_by = user
    run.save(
        update_fields=[
            "total_gross",
            "total_deductions",
            "total_net",
            "status",
            "processed_by",
            "updated_at",
        ]
    )

    logger.info(
        "payroll_run %s processed: %d employees, net=%s",
        run.run_number,
        employee_count,
        run.total_net,
    )

    return PayrollRunSummary(
        run_id=run.pk,
        employees_processed=employee_count,
        total_gross=run.total_gross,
        total_deductions=run.total_deductions,
        total_net=run.total_net,
    )


def _persist_line(run: PayrollRun, employee: Employee, calc: PayrollCalculation) -> None:
    line = PayrollLine.objects.create(
        payroll_run=run,
        employee=employee,
        basic_salary=calc.basic_salary,
        gross_salary=calc.gross_salary,
        total_earnings=calc.total_earnings,
        total_deductions=calc.total_deductions,
        net_salary=calc.net_salary,
        working_days=calc.working_days,
        days_worked=calc.working_days,
        tax_deduction=calc.tax_deduction,
        pension_deduction=calc.pension_deduction,
        other_deductions=calc.nhf_deduction + calc.other_deductions,
        bank_name=employee.bank_name or "",
        bank_account=employee.bank_account or "",
    )
    for comp in calc.components:
        if comp.is_earning:
            PayrollEarning.objects.create(
                payroll_line=line, component_id=comp.component_id, amount=comp.amount
            )
        else:
            PayrollDeduction.objects.create(
                payroll_line=line, component_id=comp.component_id, amount=comp.amount
            )
    for stat in calc.statutory:
        StatutoryDeduction.objects.create(
            payroll_line=line,
            template_id=stat.template_id,
            employee_amount=stat.employee_amount,
            employer_amount=stat.employer_amount,
            is_employer_contribution=stat.employer_amount > 0,
        )
    # Generate an initial payslip record so the portal can surface it
    # immediately on approval.
    Payslip.objects.get_or_create(payroll_line=line)


# ---------------------------------------------------------------------------
# Period generation
# ---------------------------------------------------------------------------


def generate_monthly_periods(
    year: int, *, payment_day: int = 25
) -> list[PayrollPeriod]:
    """Create twelve monthly ``PayrollPeriod`` rows for ``year``.

    Idempotent: existing rows for the same (period_type, start_date) are
    left alone.  Payment date defaults to the 25th of the same month, or
    the last day of the month when ``payment_day`` overflows.
    """
    import calendar

    created: list[PayrollPeriod] = []
    for month in range(1, 13):
        start = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end = date(year, month, last_day)
        pay_day = min(payment_day, last_day)
        payment = date(year, month, pay_day)

        obj, was_created = PayrollPeriod.objects.get_or_create(
            period_type="Monthly",
            start_date=start,
            defaults={
                "end_date": end,
                "payment_date": payment,
                "status": "Draft",
                "is_active": True,
            },
        )
        if was_created:
            created.append(obj)
    return created
