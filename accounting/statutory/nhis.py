"""
NHIA (National Health Insurance Authority) monthly contribution schedule.

Under the National Health Insurance Authority Act 2022 (which replaced
the older NHIS Act):

  * Contribution rate is **5% of basic salary** for formal-sector
    employees, typically split **1.75% employee / 3.25% employer** in
    the public-sector FSSHIP scheme. State SHIS variations may differ
    slightly — the exporter exposes both halves separately so the
    state scheme's numbers reconcile.
  * Contribution is monthly, remitted to the employee's registered
    HMO (Health Maintenance Organisation).

The schedule groups employees by HMO because remittance happens per
HMO, similar to PENCOM. For deployments where HMO assignment isn't
yet on file, the export still emits the line with a remark.

Data source
-----------
``hrm.PayrollLine`` for the target month, applying the rates to
``basic_salary`` (NOT gross — NHIA contributions are on basic only,
per the scheme's definition). This differs from NSITF and PAYE which
use gross.

Columns
-------
    HMO · Employee Name · NHIS ID · Staff Number · Basic Salary
    · Employee Contribution (1.75%) · Employer Contribution (3.25%)
    · Total Contribution · Period · Remarks
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from . import ExportResult, format_csv


NHIS_COLUMNS = [
    'HMO',
    'Employee Name',
    'NHIS ID',
    'Staff Number',
    'Basic Salary (NGN)',
    'Employee Contribution (NGN)',
    'Employer Contribution (NGN)',
    'Total Contribution (NGN)',
    'Period',
    'Remarks',
]

# NHIA FSSHIP split: 1.75% employee / 3.25% employer = 5% total of basic.
# State SHIS schemes sometimes use a flat 2.5/2.5 split; a future
# enhancement can make these configurable via AccountingSettings.
NHIS_EMPLOYEE_RATE = Decimal('0.0175')
NHIS_EMPLOYER_RATE = Decimal('0.0325')


def export_nhis_schedule(
    year: int,
    month: int,
    tenant_name: str = '',
) -> ExportResult:
    """Build the NHIA monthly contribution schedule.

    Pulls every ``PayrollLine`` with non-zero ``basic_salary`` in the
    target month. Employees without an HMO assignment on file are
    still listed with a "HMO not assigned" remark.
    """
    from hrm.models import PayrollLine

    start, end = _month_bounds(year, month)
    period_label = f'{year:04d}-{month:02d}'

    lines = (
        PayrollLine.objects
        .filter(
            payroll_run__pay_date__gte=start,
            payroll_run__pay_date__lte=end,
            basic_salary__gt=0,
        )
        .select_related('employee')
        .order_by('employee__last_name', 'employee__first_name')
    )

    rows: list[dict] = []
    total_basic = Decimal('0')
    total_employee = Decimal('0')
    total_employer = Decimal('0')

    for line in lines:
        emp = line.employee
        basic = line.basic_salary or Decimal('0')

        employee_amt = (basic * NHIS_EMPLOYEE_RATE).quantize(Decimal('0.01'))
        employer_amt = (basic * NHIS_EMPLOYER_RATE).quantize(Decimal('0.01'))

        hmo = getattr(emp, 'hmo_name', '') or ''
        nhis_id = getattr(emp, 'nhis_id', '') or ''

        remarks = ''
        if not hmo:
            remarks = 'HMO not assigned'
        if not nhis_id:
            remarks = (remarks + '; ' if remarks else '') + 'NHIS ID missing'

        rows.append({
            'HMO':                         hmo or '(unassigned)',
            'Employee Name':               _full_name(emp),
            'NHIS ID':                     nhis_id,
            'Staff Number':                getattr(emp, 'employee_id', '') or '',
            'Basic Salary (NGN)':          basic,
            'Employee Contribution (NGN)': employee_amt,
            'Employer Contribution (NGN)': employer_amt,
            'Total Contribution (NGN)':    employee_amt + employer_amt,
            'Period':                      period_label,
            'Remarks':                     remarks,
        })
        total_basic += basic
        total_employee += employee_amt
        total_employer += employer_amt

    csv = format_csv(NHIS_COLUMNS, rows)

    return ExportResult(
        regulator='NHIA',
        report_name='Monthly Contribution Schedule (FSSHIP)',
        tenant_name=tenant_name,
        period_label=period_label,
        rows=rows,
        csv=csv,
        totals={
            'total_basic_salary':          total_basic,
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
