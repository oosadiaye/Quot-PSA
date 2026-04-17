"""
OAGF Monthly Financial Report (MFR) exporter.

The Office of the Accountant-General of the Federation requires every
MDA (federal) and every state government to file a monthly report
summarising revenue collected, expenditure incurred, fund balances,
and budget execution progress. The report is used by the Federation
Account Allocation Committee (FAAC) and published on the OAGF
Transparency Portal.

Structure (OAGF circulars + state practice):

  1. **Revenue Summary**
       Tax revenue, non-tax revenue, grants/transfers, other revenue,
       loan proceeds — totals plus per-category breakdown.

  2. **Expenditure Summary**
       Personnel, overhead, capital, debt service, transfers/subventions.

  3. **Surplus / Deficit**
       Revenue - Expenditure for the period.

  4. **Budget Execution**
       Original vs Final vs Actual per economic classification, with
       execution percentages.

  5. **Fund Position**
       TSA cash balances grouped by fund (consolidated fund, development
       fund, special funds).

We DON'T re-implement these aggregations — the ``IPSASReportService``
already computes them for IPSAS 1/24. The OAGF MFR is a structured
wrapper that calls those services with the target month and
reshapes the output into OAGF-expected columns.

NCoA → UCoA mapping: the Nigerian NCoA is already aligned with the
OAGF Uniform Chart. We pass through economic codes as-is; a few
federation-specific summary groupings may need renames (flagged in
the follow-up TODO in the wrapper below).

Output: Multi-section JSON (for API consumers and dashboard widgets)
+ a single consolidated CSV that treasury uploads to the OAGF portal.
CSV uses a "section,label,amount" long format because that's what
the portal accepts for the generic MFR intake template.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from . import ExportResult, format_csv


OAGF_CSV_COLUMNS = ['Section', 'Code', 'Label', 'Amount (NGN)']


def export_oagf_mfr(
    year: int,
    month: int,
    tenant_name: str = '',
) -> ExportResult:
    """Build the OAGF Monthly Financial Report for ``year``/``month``.

    Pulls from the IPSAS services in ``accounting.services.ipsas_reports``
    to keep computation consistent with the statutory financial
    statements the Auditor-General will review.
    """
    from accounting.services.ipsas_reports import IPSASReportService

    period_label = f'{year:04d}-{month:02d}'

    # ── Section 1/2/3: Performance (revenue + expenditure + surplus) ──
    # IPSAS 1 SoFPerformance already groups revenue by tax/non-tax/
    # grants/other and expenditure by personnel/overhead/capital/debt/
    # transfers — exactly the OAGF classification.
    perf = IPSASReportService.statement_of_financial_performance(
        fiscal_year=year, period=month, comparative=False,
    )

    revenue_section = _flatten_performance_section(perf.get('revenue', {}))
    expenditure_section = _flatten_performance_section(perf.get('expenditure', {}))
    surplus_deficit = perf.get('surplus_deficit', Decimal('0'))

    # ── Section 4: Budget execution (IPSAS 24) ──────────────────────────
    # IPSAS 24 needs a fiscal_year_id; we try to resolve it from the
    # year value via the FiscalYear lookup. If unavailable we skip
    # with a note.
    budget_rows = _build_budget_execution_section(year)

    # ── Section 5: Fund position (TSA cash) ─────────────────────────────
    tsa = IPSASReportService.tsa_cash_position()
    fund_position_rows = _build_fund_position_section(tsa)

    # ── Assemble CSV (long format) ──────────────────────────────────────
    csv_rows: list[dict] = []

    for r in revenue_section:
        csv_rows.append({
            'Section': 'Revenue', 'Code': r['code'],
            'Label': r['label'], 'Amount (NGN)': r['amount'],
        })
    for r in expenditure_section:
        csv_rows.append({
            'Section': 'Expenditure', 'Code': r['code'],
            'Label': r['label'], 'Amount (NGN)': r['amount'],
        })
    csv_rows.append({
        'Section': 'Surplus/Deficit', 'Code': '',
        'Label': 'Net Surplus (Deficit) for the Period',
        'Amount (NGN)': surplus_deficit,
    })
    for r in budget_rows:
        csv_rows.append({
            'Section': 'Budget Execution', 'Code': r['code'],
            'Label': r['label'], 'Amount (NGN)': r['amount'],
        })
    for r in fund_position_rows:
        csv_rows.append({
            'Section': 'Fund Position', 'Code': r['code'],
            'Label': r['label'], 'Amount (NGN)': r['amount'],
        })

    csv = format_csv(OAGF_CSV_COLUMNS, csv_rows)

    # Totals for cover-page + sanity checks at the portal.
    total_revenue = perf.get('revenue', {}).get('total', Decimal('0'))
    total_expenditure = perf.get('expenditure', {}).get('total', Decimal('0'))
    total_tsa = tsa.get('total_balance', Decimal('0'))

    return ExportResult(
        regulator='OAGF',
        report_name='Monthly Financial Report',
        tenant_name=tenant_name,
        period_label=period_label,
        rows=[
            # Structured sections for consumers that want JSON,
            # preserved alongside the flat csv_rows so a dashboard
            # can render them without re-parsing the CSV.
            {'section': 'revenue',          'items': revenue_section},
            {'section': 'expenditure',      'items': expenditure_section},
            {'section': 'surplus_deficit',  'amount': surplus_deficit},
            {'section': 'budget_execution', 'items': budget_rows},
            {'section': 'fund_position',    'items': fund_position_rows},
        ],
        csv=csv,
        totals={
            'total_revenue':     total_revenue,
            'total_expenditure': total_expenditure,
            'surplus_deficit':   surplus_deficit,
            'tsa_cash_balance':  total_tsa,
        },
    )


# ── Helpers ────────────────────────────────────────────────────────────

def _flatten_performance_section(section: dict) -> list[dict]:
    """Flatten an IPSAS-1 revenue/expenditure section into (code, label,
    amount) triples suitable for OAGF's long-format CSV.

    IPSAS structure is nested::

        {
          "tax_revenue":     {"items": [{code, name, amount}, ...], "total": ...},
          "non_tax_revenue": {"items": [...], "total": ...},
          ...
          "total": <grand total>
        }

    We emit one row per line item plus a subtotal row per group, with
    a final grand-total row.
    """
    out: list[dict] = []
    grand_total = section.get('total', Decimal('0'))

    for key, group in section.items():
        if key == 'total':
            continue
        if not isinstance(group, dict):
            continue
        for item in group.get('items', []) or []:
            out.append({
                'code':   str(item.get('code', '')),
                'label':  str(item.get('name', '')),
                'amount': _to_decimal(item.get('amount', 0)),
            })
        subtotal = group.get('total', Decimal('0'))
        out.append({
            'code':   '',
            'label':  f"Subtotal — {_humanise_group(key)}",
            'amount': _to_decimal(subtotal),
        })

    out.append({
        'code':   '',
        'label':  'Grand Total',
        'amount': _to_decimal(grand_total),
    })
    return out


def _build_budget_execution_section(fiscal_year_year: int) -> list[dict]:
    """Pull the IPSAS-24 budget-vs-actual items for the OAGF section.

    We need a FiscalYear PK to call the service; resolve it by year.
    Returns an empty list with a single "not available" marker row
    when no FiscalYear matches — keeps the MFR useful for mid-year
    onboarding where the year record may not exist yet.
    """
    try:
        from accounting.models.advanced import FiscalYear
        fy = FiscalYear.objects.filter(year=fiscal_year_year).first()
    except Exception:
        fy = None

    if not fy:
        return [{
            'code':   '',
            'label':  f'Budget-vs-Actual unavailable: no FiscalYear record for {fiscal_year_year}',
            'amount': Decimal('0'),
        }]

    from accounting.services.ipsas_reports import IPSASReportService
    try:
        data = IPSASReportService.budget_vs_actual(fiscal_year_id=fy.pk)
    except Exception as exc:
        return [{
            'code':   '',
            'label':  f'Budget-vs-Actual service error: {exc}',
            'amount': Decimal('0'),
        }]

    rows: list[dict] = []
    for item in data.get('items', []) or []:
        label = (
            f"{item.get('mda', '')} / {item.get('account', '')}"
        ).strip(' /')
        rows.append({
            'code':   str(item.get('account_code', '')),
            'label':  f'[Original] {label}',
            'amount': _to_decimal(item.get('original_budget', 0)),
        })
        rows.append({
            'code':   str(item.get('account_code', '')),
            'label':  f'[Final] {label}',
            'amount': _to_decimal(item.get('final_budget', 0)),
        })
        rows.append({
            'code':   str(item.get('account_code', '')),
            'label':  f'[Actual] {label}',
            'amount': _to_decimal(item.get('actual_expenditure', 0)),
        })

    totals = data.get('totals', {})
    rows.append({
        'code': '', 'label': 'Total Original Budget',
        'amount': _to_decimal(totals.get('total_original_budget', 0)),
    })
    rows.append({
        'code': '', 'label': 'Total Final Budget',
        'amount': _to_decimal(totals.get('total_final_budget', 0)),
    })
    rows.append({
        'code': '', 'label': 'Total Actual Expenditure',
        'amount': _to_decimal(totals.get('total_expended', 0)),
    })
    return rows


def _build_fund_position_section(tsa: dict) -> list[dict]:
    """Flatten the TSA cash-position summary into OAGF rows.

    The IPSAS service returns balances by account_type (MAIN_TSA,
    SUB_ACCOUNT, ZERO_BALANCE, etc.) and by MDA. OAGF's fund-position
    section wants a by-fund view; absent a fund FK on TreasuryAccount,
    we emit the by-type summary as a reasonable proxy — OAGF accepts
    this breakdown as long as the grand total matches the ledger.
    """
    rows: list[dict] = []
    by_type = tsa.get('by_account_type', [])
    for entry in by_type:
        rows.append({
            'code':   str(entry.get('account_type', '')),
            'label':  f"TSA {_humanise_account_type(entry.get('account_type', ''))}",
            'amount': _to_decimal(entry.get('balance', 0)),
        })
    rows.append({
        'code':   '',
        'label':  'Total TSA Cash Position',
        'amount': _to_decimal(tsa.get('total_balance', 0)),
    })
    return rows


def _humanise_group(key: str) -> str:
    """Convert snake_case group keys into display labels."""
    return key.replace('_', ' ').title()


def _humanise_account_type(code: str) -> str:
    """Human labels for TreasuryAccount.account_type values."""
    table = {
        'MAIN_TSA':     'Main TSA (CBN)',
        'CONSOLIDATED': 'Consolidated Revenue Fund',
        'SUB_ACCOUNT':  'MDA Sub-Accounts',
        'ZERO_BALANCE': 'Zero-Balance Accounts',
        'HOLDING':      'Holding Accounts',
        'REVENUE':      'Revenue Collection Accounts',
    }
    return table.get(code, code)


def _to_decimal(value: Any) -> Decimal:
    """Coerce miscellaneous numeric inputs (Decimal, int, float, str)
    into a ``Decimal``. Falls back to ``Decimal('0')`` on unparseable
    input — defensive for IPSAS service outputs that occasionally
    return floats or stringified decimals."""
    if isinstance(value, Decimal):
        return value
    if value is None or value == '':
        return Decimal('0')
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal('0')
