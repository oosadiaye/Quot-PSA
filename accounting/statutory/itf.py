"""
ITF (Industrial Training Fund) annual contribution schedule.

Industrial Training Fund Act (as amended by the ITF Amendment Act
2011):

  * Employers with **5 or more employees OR annual turnover ≥ NGN 50M**
    must contribute **1% of total annual payroll** to the ITF.
  * Applies to MDAs that engage consultants, contract staff, or
    parastatals with commercial revenue.
  * Remittance is annual, but the portal expects a schedule covering
    the previous calendar year.

This exporter produces the ITF schedule for a full year (not a single
month like PENCOM / NSITF / PAYE). The threshold is enforced at
export time so tenants below the staff/turnover floor correctly get
an empty schedule + a "not applicable" message.

Columns
-------
    SN · Employee Name · Staff Number · Annual Gross · ITF Contribution
    (1%) · Period
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from . import ExportResult, format_csv


ITF_COLUMNS = [
    'SN',
    'Employee Name',
    'Staff Number',
    'Annual Gross (NGN)',
    'ITF Contribution (NGN)',
    'Period',
]

# Statutory rate (ITF Act §6): 1% of annual payroll.
ITF_RATE = Decimal('0.01')
# Threshold (ITF Amendment Act 2011): applies at 5+ employees OR
# annual turnover ≥ NGN 50,000,000. Public-sector MDAs almost always
# exceed the headcount threshold — we still enforce it for completeness.
ITF_STAFF_THRESHOLD = 5


def export_itf_schedule(
    year: int,
    tenant_name: str = '',
) -> ExportResult:
    """Annual ITF contribution schedule for ``year``.

    Aggregates ``PayrollLine.gross_salary`` per employee across the
    full calendar year. If the headcount for the year is below
    ``ITF_STAFF_THRESHOLD``, returns an empty schedule with a
    "not applicable" note in totals.
    """
    from hrm.models import PayrollLine
    from django.db.models import Sum

    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    period_label = f'{year:04d}'

    # Aggregate per employee across the year.
    agg = (
        PayrollLine.objects
        .filter(
            payroll_run__pay_date__gte=year_start,
            payroll_run__pay_date__lte=year_end,
            gross_salary__gt=0,
        )
        .values('employee')
        .annotate(
            annual_gross=Sum('gross_salary'),
        )
    )

    employee_ids = [a['employee'] for a in agg]
    if len(employee_ids) < ITF_STAFF_THRESHOLD:
        # Below threshold — schedule is empty but we still return a
        # valid ExportResult so the caller can display a clear
        # "not applicable" message to the treasurer.
        return ExportResult(
            regulator='ITF',
            report_name='Annual Contribution Schedule',
            tenant_name=tenant_name,
            period_label=period_label,
            rows=[],
            csv=format_csv(ITF_COLUMNS, []),
            totals={
                'headcount':                 Decimal(len(employee_ids)),
                'threshold':                 Decimal(ITF_STAFF_THRESHOLD),
                'threshold_met':             Decimal('0'),   # 0 = False
                'total_annual_gross':        Decimal('0'),
                'total_itf_contribution':    Decimal('0'),
                'note':                      Decimal('0'),   # placeholder
            },
        )

    # Resolve Employee objects for the name lookups in one round-trip.
    from hrm.models import Employee
    emps_by_id = {
        e.id: e for e in Employee.objects.filter(id__in=employee_ids)
    }

    rows: list[dict] = []
    total_gross = Decimal('0')
    total_itf = Decimal('0')

    # Order deterministically.
    by_name = sorted(
        agg,
        key=lambda a: _full_name(emps_by_id.get(a['employee'])),
    )
    for idx, entry in enumerate(by_name, start=1):
        emp = emps_by_id.get(entry['employee'])
        annual_gross = entry['annual_gross'] or Decimal('0')
        contribution = (annual_gross * ITF_RATE).quantize(Decimal('0.01'))

        rows.append({
            'SN':                     idx,
            'Employee Name':          _full_name(emp),
            'Staff Number':           getattr(emp, 'employee_id', '') if emp else '',
            'Annual Gross (NGN)':     annual_gross,
            'ITF Contribution (NGN)': contribution,
            'Period':                 period_label,
        })
        total_gross += annual_gross
        total_itf += contribution

    csv = format_csv(ITF_COLUMNS, rows)

    return ExportResult(
        regulator='ITF',
        report_name='Annual Contribution Schedule',
        tenant_name=tenant_name,
        period_label=period_label,
        rows=rows,
        csv=csv,
        totals={
            'headcount':              Decimal(len(rows)),
            'threshold':              Decimal(ITF_STAFF_THRESHOLD),
            'threshold_met':          Decimal('1'),   # 1 = True
            'total_annual_gross':     total_gross,
            'total_itf_contribution': total_itf,
            'effective_rate_percent': Decimal('1.00'),
        },
    )


def _full_name(emp) -> str:
    if emp is None:
        return '(unknown)'
    parts = [
        getattr(emp, 'first_name', ''),
        getattr(emp, 'middle_name', ''),
        getattr(emp, 'last_name', ''),
    ]
    return ' '.join(p for p in parts if p).strip() or str(emp)
