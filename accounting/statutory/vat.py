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

import logging
from decimal import Decimal

from . import ExportResult, StatutoryReturnError, format_csv

logger = logging.getLogger(__name__)


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

    # V8 — partial-result accumulators. A single corrupt invoice line
    # must NOT take down the whole VAT filing endpoint.
    partial_failures: list[dict] = []
    warnings: list[str] = []
    total_rows_attempted = 0

    for tx in output:
        total_rows_attempted += 1
        try:
            taxable = _to_decimal(tx.get('taxable_amount'))
            vat = _to_decimal(tx.get('vat_amount'))
        except StatutoryReturnError as exc:
            doc = tx.get('document_number', '<unknown>')
            warnings.append(f"Output VAT row '{doc}': {exc}")
            partial_failures.append({
                'section': 'output_vat', 'document_number': doc,
                'error': str(exc),
            })
            logger.warning('FIRS VAT partial-failure (output): %s — %s', doc, exc)
            continue
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
        total_rows_attempted += 1
        try:
            taxable = _to_decimal(tx.get('taxable_amount'))
            vat = _to_decimal(tx.get('vat_amount'))
        except StatutoryReturnError as exc:
            doc = tx.get('document_number', '<unknown>')
            warnings.append(f"Input VAT row '{doc}': {exc}")
            partial_failures.append({
                'section': 'input_vat', 'document_number': doc,
                'error': str(exc),
            })
            logger.warning('FIRS VAT partial-failure (input): %s — %s', doc, exc)
            continue
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

    # All-fail re-raise: if every row failed and at least one was
    # attempted, the filing carries no real data — escalate to a hard
    # block at the view layer rather than return an empty CSV.
    if total_rows_attempted > 0 and len(rows) == 0 and partial_failures:
        raise StatutoryReturnError(
            'FIRS VAT return: every Output/Input row failed to coerce. '
            f'Errors: {"; ".join(w for w in warnings[:5])}'
        )

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
        warnings=warnings,
        partial_failures=partial_failures,
    )


def _to_decimal(value) -> Decimal:
    """Coerce to Decimal.

    H8 fix: unparseable numeric input is now a hard error rather than a
    silent zero. A corrupt VAT amount returned by the VATReturnService
    would otherwise file a zero VAT line to FIRS — a material
    compliance breach because the operator believed the return
    succeeded. ``None`` and empty string remain legitimate "no data"
    markers and map to zero.
    """
    if isinstance(value, Decimal):
        return value
    if value is None or value == '':
        return Decimal('0')
    try:
        return Decimal(str(value))
    except Exception as exc:
        logger.error(
            'FIRS VAT return: cannot coerce numeric value %r to Decimal: %s',
            value, exc,
        )
        raise StatutoryReturnError(
            f"Cannot compute FIRS VAT return line: value {value!r} is "
            f"not a valid number ({exc}); refusing to file a zero return."
        ) from exc
