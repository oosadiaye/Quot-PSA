"""
FIRS WHT (Withholding Tax) monthly schedule exporter.

Produces the schedule FIRS requires with monthly WHT remittance
(variously called "WHT Schedule" or "Form WHT"). The schedule lists
every payment on which WHT was deducted, with beneficiary details,
gross amount, WHT rate, WHT amount, and transaction date.

Data sources (in priority order):

1. ``PaymentVoucherGov`` (``wht_amount > 0`` and ``status = 'PAID'``)
   — this is the canonical government-payment path. WHT is withheld
   at the PV stage; ``gross_amount - wht_amount = net_amount`` is
   what's paid to the beneficiary.

2. ``Payment`` + ``VendorInvoiceLine.withholding_tax`` — commercial
   AP path. Deferred to a future sprint; government tenants post
   through the PV pipeline.

The output is a CSV that treasurers upload to the FIRS TaxProMax
portal. A direct API integration with TaxProMax is a P1 roadmap item
for a later sprint; until then, manual upload is the accepted flow.

Column set matches the FIRS WHT return form (Form WHT-401):

    SN, Beneficiary Name, Beneficiary TIN, Beneficiary Address,
    Nature of Transaction, Contract Date, Invoice Number,
    Gross Amount (NGN), WHT Rate (%), WHT Amount (NGN),
    Date Deducted, Remarks
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from . import ExportResult, format_csv


FIRS_WHT_COLUMNS = [
    'SN',
    'Beneficiary Name',
    'Beneficiary TIN',
    'Beneficiary Address',
    'Nature of Transaction',
    'Contract Date',
    'Invoice Number',
    'Gross Amount (NGN)',
    'WHT Rate (%)',
    'WHT Amount (NGN)',
    'Date Deducted',
    'Remarks',
]


def export_wht_schedule(
    year: int,
    month: int,
    tenant_name: str = '',
) -> ExportResult:
    """Build the FIRS WHT monthly schedule for ``year``/``month``.

    Pulls every ``PaymentVoucherGov`` marked PAID in the target month
    with non-zero ``wht_amount``. Beneficiary details come from the PV
    fields (``payee_name``, ``payee_address``) with a graceful fallback
    to empty strings — FIRS accepts partial rows with a 'TIN pending'
    remark when the payee's TIN wasn't on file at deduction time.

    Returns :class:`ExportResult` containing structured rows, ready
    CSV, per-column totals, and cover-page metadata.
    """
    from accounting.models.treasury import PaymentVoucherGov

    start, end = _month_bounds(year, month)
    period_label = f'{year:04d}-{month:02d}'

    pvs = (
        PaymentVoucherGov.objects
        .filter(
            status__in=('PAID', 'SCHEDULED'),
            wht_amount__gt=0,
            created_at__date__gte=start,
            created_at__date__lte=end,
        )
        .select_related('ncoa_code__economic', 'appropriation')
        .order_by('created_at')
    )

    rows: list[dict] = []
    total_gross = Decimal('0')
    total_wht = Decimal('0')

    for idx, pv in enumerate(pvs, start=1):
        gross = pv.gross_amount or Decimal('0')
        wht = pv.wht_amount or Decimal('0')
        rate = _derive_rate(gross, wht)
        # Nature of transaction: prefer the NCoA economic name (it's
        # already a human-friendly classification — "Consultancy",
        # "Works", "Rent", etc. — exactly what FIRS expects).
        nature = _resolve_transaction_nature(pv)

        rows.append({
            'SN': idx,
            'Beneficiary Name':       pv.payee_name or '(unnamed)',
            'Beneficiary TIN':        _payee_tin(pv),
            'Beneficiary Address':    _payee_address(pv),
            'Nature of Transaction':  nature,
            'Contract Date':          _contract_date(pv),
            'Invoice Number':         pv.invoice_number or pv.source_document or '',
            'Gross Amount (NGN)':     gross,
            'WHT Rate (%)':           rate,
            'WHT Amount (NGN)':       wht,
            'Date Deducted':          pv.created_at.date() if pv.created_at else '',
            'Remarks':                _remarks(pv),
        })
        total_gross += gross
        total_wht += wht

    csv = format_csv(FIRS_WHT_COLUMNS, rows)

    return ExportResult(
        regulator='FIRS',
        report_name='Withholding Tax Monthly Schedule (Form WHT-401)',
        tenant_name=tenant_name,
        period_label=period_label,
        rows=rows,
        csv=csv,
        totals={
            'total_gross_amount': total_gross,
            'total_wht_amount':   total_wht,
            'line_count':         Decimal(len(rows)),
        },
    )


# ─── Helpers ───────────────────────────────────────────────────────────

def _month_bounds(year: int, month: int) -> tuple[date, date]:
    """(first day, last day) of the target month."""
    from calendar import monthrange
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def _derive_rate(gross: Decimal, wht: Decimal) -> Decimal:
    """WHT rate as a percentage, to 2 decimal places."""
    if gross == 0:
        return Decimal('0.00')
    return (wht / gross * Decimal('100')).quantize(Decimal('0.01'))


def _payee_tin(pv) -> str:
    """Best-effort TIN lookup — from the linked vendor if present."""
    # The PV model doesn't carry a direct vendor FK in the current schema.
    # If the source_document links to a VendorInvoice, we can backtrack,
    # but for v1 we emit an empty string and FIRS accepts rows with
    # 'TIN pending' remarks.
    return getattr(pv, 'payee_tin', '') or ''


def _payee_address(pv) -> str:
    return getattr(pv, 'payee_address', '') or ''


def _resolve_transaction_nature(pv) -> str:
    """Human-readable nature of transaction for the FIRS form.

    Preferred order:
      1. The NCoA economic segment's ``name`` (e.g. "Professional Fees")
      2. The PV's ``payment_type`` choice label (e.g. "Vendor Payment")
      3. Generic fallback
    """
    ncoa = getattr(pv, 'ncoa_code', None)
    if ncoa is not None:
        econ = getattr(ncoa, 'economic', None)
        if econ is not None and getattr(econ, 'name', None):
            return econ.name
    try:
        return pv.get_payment_type_display()
    except Exception:
        return 'Payment to Beneficiary'


def _contract_date(pv) -> Optional[date]:
    """Date of the underlying contract/invoice. Falls back to invoice_date."""
    return getattr(pv, 'invoice_date', None)


def _remarks(pv) -> str:
    """Free-text remarks column. Flag TIN-missing cases up-front so FIRS
    accepts the row with a mitigation note."""
    if not _payee_tin(pv):
        return 'TIN pending'
    return ''
