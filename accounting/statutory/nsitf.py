"""
NSITF Employee Compensation Scheme (ECS) monthly contribution exporter.

Employee's Compensation Act 2010, administered by the Nigeria Social
Insurance Trust Fund (NSITF):

  * Employer contributes **1% of total gross payroll** monthly.
  * Employee contributes nothing (ECS is 100% employer-funded).
  * Remittance is monthly; late payment attracts 10% penalty.

The NSITF portal accepts two common upload formats:

  * An aggregate monthly return (single row: total payroll, 1%,
    payment reference).
  * A detailed employee schedule (per-employee breakdown for audit).

This exporter produces the **detailed schedule** because it's a strict
superset — the aggregate totals come from the file header. If a state
tenant only needs the aggregate, they read ``result.totals`` instead
of ``result.rows``.

Columns
-------
    SN · Employee Name · Staff Number · Department · Gross Pay
    · NSITF Contribution (1%) · Period
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from . import ExportResult, format_csv


NSITF_COLUMNS = [
    'SN',
    'Employee Name',
    'Staff Number',
    'Department',
    'Gross Pay (NGN)',
    'NSITF Contribution (NGN)',
    'Period',
]

# Statutory rate: 1% of gross monthly payroll (Employee's Compensation
# Act 2010, §33). Pull into a constant so future-proof against rate
# changes — if NSITF revises the rate, a single-line edit here
# propagates everywhere.
NSITF_RATE = Decimal('0.01')


def export_nsitf_schedule(
    year: int,
    month: int,
    tenant_name: str = '',
) -> ExportResult:
    """Monthly NSITF employer contribution schedule.

    Sums ``PayrollLine.gross_salary`` for every employee with a
    payroll line in the target month and applies 1%. Zero-pay lines
    are excluded.
    """
    from hrm.models import PayrollLine

    start, end = _month_bounds(year, month)
    period_label = f'{year:04d}-{month:02d}'

    lines = (
        PayrollLine.objects
        .filter(
            payroll_run__pay_date__gte=start,
            payroll_run__pay_date__lte=end,
            gross_salary__gt=0,
        )
        .select_related('employee', 'employee__department')
        .order_by('employee__last_name', 'employee__first_name')
    )

    rows: list[dict] = []
    total_gross = Decimal('0')
    total_nsitf = Decimal('0')

    for idx, line in enumerate(lines, start=1):
        emp = line.employee
        gross = line.gross_salary or Decimal('0')
        contribution = (gross * NSITF_RATE).quantize(Decimal('0.01'))

        rows.append({
            'SN':                     idx,
            'Employee Name':          _full_name(emp),
            'Staff Number':           getattr(emp, 'employee_id', '') or '',
            'Department':             _department_name(emp),
            'Gross Pay (NGN)':        gross,
            'NSITF Contribution (NGN)': contribution,
            'Period':                 period_label,
        })
        total_gross += gross
        total_nsitf += contribution

    csv = format_csv(NSITF_COLUMNS, rows)

    return ExportResult(
        regulator='NSITF',
        report_name='Employee Compensation Scheme Monthly Contribution',
        tenant_name=tenant_name,
        period_label=period_label,
        rows=rows,
        csv=csv,
        totals={
            'total_gross_payroll':      total_gross,
            'total_nsitf_contribution': total_nsitf,
            'effective_rate_percent':   Decimal('1.00'),
            'line_count':               Decimal(len(rows)),
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


def _department_name(emp) -> str:
    dept = getattr(emp, 'department', None)
    if dept is None:
        return ''
    return getattr(dept, 'name', '') or str(dept)
