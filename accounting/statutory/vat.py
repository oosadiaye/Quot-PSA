"""
FIRS VAT return monthly schedule exporter.

Nigerian VAT at 7.5% (Finance Act 2019 onward). Public-sector
entities are VAT-exempt for core operations but MDAs that engage in
commercial activities (state-owned enterprises, parastatals, internal
billing between MDAs) still file VAT returns with FIRS.

Structure of FIRS Form VAT 002 / TaxProMax upload:

  * Output VAT (VAT collected on sales / services rendered).
  * Input VAT (VAT paid on purchases).
  * Net VAT Payable = Output − Input. Carry forward if negative.

This exporter leverages the existing ``VATReturnService`` for the
actual aggregation and reshapes its output into the two-section long
format FIRS accepts.

Output columns
--------------
    Section · Document Type · Document Number · Document Date
    · Counterparty · Taxable Amount (NGN) · VAT Rate (%)
    · VAT Amount (NGN)
"""
from __future__ import annotations

from decimal import Decimal

from . import ExportResult, format_csv


VAT_COLUMNS = [
    'Section',
    'Document Type',
    'Document Number',
    'Document Date',
    'Counterparty',
    'Taxable Amount (NGN)',
    'VAT Rate (%)',
    'VAT Amount (NGN)',
]


def export_vat_return(
    year: int,
    month: int,
    tenant_name: str = '',
) -> ExportResult:
    """Build the FIRS VAT return for ``year``/``month``.

    Returns separate rows per invoice line (Output and Input) plus
    summary totals in ``totals``.
    """
    from datetime import date
    from calendar import monthrange
    from accounting.services.vat_returns import VATReturnService

    last = monthrange(year, month)[1]
    start, end = date(year, month, 1), date(year, month, last)
    period_label = f'{year:04d}-{month:02d}'

    output = VATReturnService.get_output_vat(start, end)
    input_ = VATReturnService.get_input_vat(start, end)

    rows: list[dict] = []
    total_output_vat = Decimal('0')
    total_input_vat = Decimal('0')
    total_output_taxable = Decimal('0')
    total_input_taxable = Decimal('0')

    for tx in output:
        taxable = _to_decimal(tx.get('taxable_amount'))
        vat = _to_decimal(tx.get('vat_amount'))
        rows.append({
            'Section':              'Output VAT',
            'Document Type':        tx.get('document_type', 'CI'),
            'Document Number':      tx.get('document_number', ''),
            'Document Date':        tx.get('document_date', ''),
            'Counterparty':         tx.get('customer_name', ''),
            'Taxable Amount (NGN)': taxable,
            'VAT Rate (%)':         _to_decimal(tx.get('vat_rate', '7.5')),
            'VAT Amount (NGN)':     vat,
        })
        total_output_taxable += taxable
        total_output_vat += vat

    for tx in input_:
        taxable = _to_decimal(tx.get('taxable_amount'))
        vat = _to_decimal(tx.get('vat_amount'))
        rows.append({
            'Section':              'Input VAT',
            'Document Type':        tx.get('document_type', 'VI'),
            'Document Number':      tx.get('document_number', ''),
            'Document Date':        tx.get('document_date', ''),
            'Counterparty':         tx.get('vendor_name', ''),
            'Taxable Amount (NGN)': taxable,
            'VAT Rate (%)':         _to_decimal(tx.get('vat_rate', '7.5')),
            'VAT Amount (NGN)':     vat,
        })
        total_input_taxable += taxable
        total_input_vat += vat

    net_vat_payable = total_output_vat - total_input_vat

    csv = format_csv(VAT_COLUMNS, rows)

    return ExportResult(
        regulator='FIRS',
        report_name='VAT Return (Form VAT-002)',
        tenant_name=tenant_name,
        period_label=period_label,
        rows=rows,
        csv=csv,
        totals={
            'total_output_taxable': total_output_taxable,
            'total_output_vat':     total_output_vat,
            'total_input_taxable':  total_input_taxable,
            'total_input_vat':      total_input_vat,
            'net_vat_payable':      net_vat_payable,
            'line_count':           Decimal(len(rows)),
        },
    )


def _to_decimal(value) -> Decimal:
    """Coerce to Decimal, defaulting to 0."""
    if isinstance(value, Decimal):
        return value
    if value is None or value == '':
        return Decimal('0')
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal('0')
