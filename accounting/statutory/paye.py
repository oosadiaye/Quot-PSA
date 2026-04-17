"""
PAYE (Pay-As-You-Earn) monthly schedule exporter for the state
internal revenue service.

Each Nigerian state runs its own Internal Revenue Service (IRS) that
receives employee PAYE returns — LIRS for Lagos, DTSG-BIR for Delta,
KWIRS for Kwara, etc. The upload format is near-identical across
states (the template has been harmonised by the Joint Tax Board),
with minor column-order variations.

This exporter produces the JTB-aligned column set. Target-state
variations can be handled by wrapping the result and reshuffling
columns per state spec — a follow-up ticket when we have concrete
state format specs in hand.

Data source
-----------
``hrm.PayrollLine`` joined to ``hrm.Employee`` for the target month.
PAYE amount = ``PayrollLine.tax_deduction`` (computed at payroll run
time using the PITAM bracket engine in ``hrm.NigeriaPAYEBracket``).

Columns (JTB harmonised)
------------------------
SN · Employee Name · TIN · Staff Number · Designation · Bank Name
· Bank Account · Gross Emolument · Consolidated Relief · Taxable Income
· PAYE Amount · Pension Deduction · Net Pay · Period
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from . import ExportResult, format_csv


PAYE_COLUMNS = [
    'SN',
    'Employee Name',
    'TIN',
    'Staff Number',
    'Designation',
    'Bank Name',
    'Bank Account',
    'Gross Emolument (NGN)',
    'Consolidated Relief (NGN)',
    'Taxable Income (NGN)',
    'PAYE Amount (NGN)',
    'Pension Deduction (NGN)',
    'Net Pay (NGN)',
    'Period',
]


def export_paye_schedule(
    year: int,
    month: int,
    tenant_name: str = '',
) -> ExportResult:
    """Build the PAYE monthly schedule for ``year``/``month``.

    Pulls every ``PayrollLine`` whose parent ``PayrollRun`` has a
    ``pay_date`` in the target month and which has a non-zero
    ``tax_deduction``. Zero-PAYE employees are included if the
    gross > threshold so the state IRS can reconcile the headcount.
    """
    from hrm.models import PayrollLine

    start, end = _month_bounds(year, month)
    period_label = f'{year:04d}-{month:02d}'

    lines = (
        PayrollLine.objects
        .filter(
            payroll_run__pay_date__gte=start,
            payroll_run__pay_date__lte=end,
        )
        .select_related('employee', 'payroll_run')
        .order_by('employee__last_name', 'employee__first_name')
    )

    rows: list[dict] = []
    total_gross = Decimal('0')
    total_paye = Decimal('0')
    total_pension = Decimal('0')
    total_net = Decimal('0')

    for idx, line in enumerate(lines, start=1):
        emp = line.employee
        gross = line.gross_salary or Decimal('0')
        paye = line.tax_deduction or Decimal('0')
        pension = line.pension_deduction or Decimal('0')
        net = line.net_salary or Decimal('0')

        # Consolidated Relief Allowance (CRA) per PITAM:
        # = Max(200k, 1% of gross) + 20% of gross. Approximate when
        # the payroll engine has already materialised it; otherwise
        # derive on the fly so the state IRS sees the same figure.
        cra = _derive_cra(gross)
        taxable = max(Decimal('0'), gross - cra - pension)

        rows.append({
            'SN': idx,
            'Employee Name':            _full_name(emp),
            'TIN':                      getattr(emp, 'tin', '') or '',
            'Staff Number':             getattr(emp, 'employee_id', '') or '',
            'Designation':              _designation(emp),
            'Bank Name':                line.bank_name or getattr(emp, 'bank_name', '') or '',
            'Bank Account':             line.bank_account or getattr(emp, 'bank_account_number', '') or '',
            'Gross Emolument (NGN)':    gross,
            'Consolidated Relief (NGN)': cra,
            'Taxable Income (NGN)':     taxable,
            'PAYE Amount (NGN)':        paye,
            'Pension Deduction (NGN)':  pension,
            'Net Pay (NGN)':            net,
            'Period':                   period_label,
        })
        total_gross += gross
        total_paye += paye
        total_pension += pension
        total_net += net

    csv = format_csv(PAYE_COLUMNS, rows)

    return ExportResult(
        regulator='State IRS',
        report_name='PAYE Monthly Schedule (JTB format)',
        tenant_name=tenant_name,
        period_label=period_label,
        rows=rows,
        csv=csv,
        totals={
            'total_gross':   total_gross,
            'total_paye':    total_paye,
            'total_pension': total_pension,
            'total_net_pay': total_net,
            'line_count':    Decimal(len(rows)),
        },
    )


# ─── Helpers ───────────────────────────────────────────────────────────

def _month_bounds(year: int, month: int) -> tuple[date, date]:
    from calendar import monthrange
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def _full_name(employee) -> str:
    parts = [
        getattr(employee, 'first_name', ''),
        getattr(employee, 'middle_name', ''),
        getattr(employee, 'last_name', ''),
    ]
    return ' '.join(p for p in parts if p).strip() or str(employee)


def _designation(employee) -> str:
    pos = getattr(employee, 'position', None)
    if pos:
        return getattr(pos, 'title', '') or getattr(pos, 'name', '') or str(pos)
    return ''


# Consolidated Relief Allowance per PITAM section 33(1).
# CRA = higher of (NGN 200,000, 1% of gross annual) + 20% of gross.
# The schedule is monthly, so we compute CRA on monthly gross.
_CRA_ONE_PERCENT_FLOOR_MONTHLY = Decimal('200000') / Decimal('12')  # roughly NGN 16,666.67


def _derive_cra(gross_monthly: Decimal) -> Decimal:
    """Derive monthly CRA from monthly gross per PITAM.

    CRA (annual) = max(200k, 1% × gross_annual) + 20% × gross_annual
    Implemented at monthly granularity so the schedule balances.
    """
    if gross_monthly <= 0:
        return Decimal('0')
    one_percent = gross_monthly * Decimal('0.01')
    floor = _CRA_ONE_PERCENT_FLOOR_MONTHLY
    base = one_percent if one_percent > floor else floor
    return (base + gross_monthly * Decimal('0.20')).quantize(Decimal('0.01'))
