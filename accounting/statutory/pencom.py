"""
PENCOM monthly RSA contribution schedule exporter.

Under the Pension Reform Act 2014 (as amended):

  * Employee contributes a minimum of 8% of (basic + housing + transport).
  * Employer contributes a minimum of 10% of (basic + housing + transport).
  * Contributions are remitted monthly to each employee's chosen Pension
    Fund Administrator (PFA) within 7 working days of payroll.

The PENCOM / industry-standard remittance schedule groups contributions
BY PFA, with a per-employee breakdown so each PFA can post to the right
Retirement Savings Account (RSA).

Data source
-----------
``hrm.PayrollLine`` for the target month (pension_deduction) joined to
``hrm.EmployeePensionProfile`` (RSA PIN, PFA). When an employee lacks a
pension profile, we flag them in the "Remarks" column — the line is
still emitted so the schedule matches total payroll.

Employer contribution is NOT always stored per-line; where the
``PayrollRun`` carries an aggregate ``employer_pension_contribution`` we
use it, otherwise we apply the statutory 10% / 8% ratio: employer =
employee_deduction × 1.25 (since 10/8 = 1.25).

Output columns
--------------
    PFA Name · PFA Code · RSA PIN · Employee Name · Staff Number
    · Pensionable Pay · Employee Contribution (8%) · Employer
    Contribution (10%) · Total Contribution · Period · Remarks
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from . import ExportResult, format_csv


PENCOM_COLUMNS = [
    'PFA Name',
    'PFA Code',
    'RSA PIN',
    'Employee Name',
    'Staff Number',
    'Pensionable Pay (NGN)',
    'Employee Contribution (NGN)',
    'Employer Contribution (NGN)',
    'Total Contribution (NGN)',
    'Period',
    'Remarks',
]

# Statutory ratio under PRA 2014: employer 10% ÷ employee 8% = 1.25×.
# Used only when the payroll engine hasn't materialised the employer
# contribution separately.
_EMPLOYER_TO_EMPLOYEE_RATIO = Decimal('1.25')


def export_pencom_schedule(
    year: int,
    month: int,
    tenant_name: str = '',
) -> ExportResult:
    """Build the PENCOM monthly RSA contribution schedule.

    Includes every employee with a non-zero pension deduction in the
    target month. Employees without a pension profile (no RSA PIN / no
    PFA on file) are still listed with a "Pension profile missing"
    remark so the treasurer sees the gap and the schedule total
    reconciles to the payroll ledger.
    """
    from hrm.models import PayrollLine

    start, end = _month_bounds(year, month)
    period_label = f'{year:04d}-{month:02d}'

    lines = (
        PayrollLine.objects
        .filter(
            payroll_run__pay_date__gte=start,
            payroll_run__pay_date__lte=end,
            pension_deduction__gt=0,
        )
        .select_related(
            'employee', 'employee__pension_profile', 'employee__pension_profile__pfa',
        )
        # Group by PFA for the remittance UX — batches post to each PFA
        # in turn, so presenting them PFA-by-PFA makes upload easier.
        .order_by(
            'employee__pension_profile__pfa__name',
            'employee__last_name',
            'employee__first_name',
        )
    )

    rows: list[dict] = []
    total_employee = Decimal('0')
    total_employer = Decimal('0')

    for line in lines:
        emp = line.employee
        profile = getattr(emp, 'pension_profile', None)
        pfa = getattr(profile, 'pfa', None) if profile else None

        employee_amt = line.pension_deduction or Decimal('0')
        employer_amt = _employer_amount(line, employee_amt)
        # Pensionable pay is usually derived; where payroll exposes it
        # directly we'd use that. Here we approximate as the sum divided
        # by 18% (8% + 10%) so the schedule math is internally
        # consistent. For deployments where actual pensionable pay is
        # materialised, replace this with that field.
        pensionable_pay = (
            (employee_amt + employer_amt) / Decimal('0.18')
        ).quantize(Decimal('0.01')) if (employee_amt + employer_amt) else Decimal('0')

        remarks = ''
        if not profile:
            remarks = 'Pension profile missing — RSA PIN and PFA not on file'
        elif not pfa:
            remarks = 'PFA not assigned to employee'

        rows.append({
            'PFA Name':                    pfa.name if pfa else '(unassigned)',
            'PFA Code':                    getattr(pfa, 'pfa_code', '') if pfa else '',
            'RSA PIN':                     profile.rsa_pin if profile else '',
            'Employee Name':               _full_name(emp),
            'Staff Number':                getattr(emp, 'employee_id', '') or '',
            'Pensionable Pay (NGN)':       pensionable_pay,
            'Employee Contribution (NGN)': employee_amt,
            'Employer Contribution (NGN)': employer_amt,
            'Total Contribution (NGN)':    employee_amt + employer_amt,
            'Period':                      period_label,
            'Remarks':                     remarks,
        })
        total_employee += employee_amt
        total_employer += employer_amt

    csv = format_csv(PENCOM_COLUMNS, rows)

    return ExportResult(
        regulator='PENCOM',
        report_name='Monthly RSA Contribution Schedule (PRA 2014)',
        tenant_name=tenant_name,
        period_label=period_label,
        rows=rows,
        csv=csv,
        totals={
            'total_employee_contribution': total_employee,
            'total_employer_contribution': total_employer,
            'grand_total':                 total_employee + total_employer,
            'line_count':                  Decimal(len(rows)),
        },
    )


# ── Helpers ────────────────────────────────────────────────────────────

def _month_bounds(year: int, month: int) -> tuple[date, date]:
    from calendar import monthrange
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def _full_name(emp) -> str:
    parts = [
        getattr(emp, 'first_name', ''),
        getattr(emp, 'middle_name', ''),
        getattr(emp, 'last_name', ''),
    ]
    return ' '.join(p for p in parts if p).strip() or str(emp)


def _employer_amount(payroll_line, employee_amount: Decimal) -> Decimal:
    """Resolve employer pension contribution for a line.

    Preference:
      1. ``payroll_line.employer_pension_contribution`` when the model
         exposes it (set by the payroll engine).
      2. ``employee_amount × 1.25`` (PRA 2014 minimum ratio).

    Returns ``Decimal('0.00')`` quantised for schedule consistency.
    """
    explicit = getattr(payroll_line, 'employer_pension_contribution', None)
    if explicit:
        return Decimal(str(explicit)).quantize(Decimal('0.01'))
    return (employee_amount * _EMPLOYER_TO_EMPLOYEE_RATIO).quantize(Decimal('0.01'))
