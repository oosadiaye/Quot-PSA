"""
WHT Payment Derivation — Nigerian PFM cash-basis recognition.

Public-sector accounting in Nigeria recognises WHT at *payment* time, not
at invoice accrual. The invoice nevertheless carries the WHT
*determination* (rate + exempt flag) so the cash outflow knows what to
deduct. This module is the single source of truth for that derivation.

Used by:
  • PaymentVoucherSerializer.create — auto-creates a PaymentVoucherDeduction
    row when the operator references an invoice without explicitly listing
    deductions.
  • Outgoing-payment API (direct cash disbursement against an invoice).
  • Frontend "Apply invoice WHT" preview action (returns the derived row
    so the operator can review before save).

The same helper is the authoritative answer for both flows so a vendor
cannot end up with one side honouring the WHT exemption and the other
still deducting.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, TypedDict

from accounting.models import VendorInvoice


class DerivedWht(TypedDict, total=False):
    deduction_type: str          # always 'WHT'
    description: str             # human-readable narrative
    withholding_tax: int         # WithholdingTax FK id
    rate: Decimal                # rate %
    amount: Decimal              # NGN amount
    gl_account: int              # GL liability account FK id
    invoice_id: int
    invoice_number: str
    is_exempt: bool              # True when invoice flagged exempt
    exempt_reason: str           # populated when is_exempt
    source: str                  # diagnostic — which path matched


def derive_wht_for_invoice(
    invoice: VendorInvoice | None = None,
    invoice_number: str | None = None,
) -> Optional[DerivedWht]:
    """Return the WHT deduction implied by an invoice's determination.

    Resolution rules (mirrors the determination order at invoice
    verification):
      1. Vendor-master ``wht_exempt=True`` → returns exempt marker.
      2. Any invoice line carries ``wht_exempt=True`` → exempt marker.
         (Per-transaction override beats vendor master only when the
         invoice opted-in to exemption.)
      3. Sum WHT across lines whose ``withholding_tax`` FK is set:
         ``rate × line.amount`` per line; each line credits the
         WithholdingTax.withholding_account.
      4. No determination found → returns None (no WHT to apply).

    Args:
        invoice:        Resolved VendorInvoice instance (preferred —
                        avoids the lookup roundtrip).
        invoice_number: Alternative — invoice_number string the PV
                        operator typed. Resolved via case-sensitive
                        exact match. Used only when ``invoice`` is None.

    Returns:
        ``DerivedWht`` dict, or ``None`` if no WHT applies and no
        exemption is recorded (silence == nothing to do). Exempt
        invoices return a dict with ``is_exempt=True`` and
        ``amount=Decimal('0')`` so callers can suppress prompting.
    """
    if invoice is None and invoice_number:
        invoice = (
            VendorInvoice.objects
            .filter(invoice_number=invoice_number)
            .select_related('vendor', 'tax_code', 'withholding_tax')
            .prefetch_related('lines__withholding_tax__withholding_account')
            .first()
        )
    if invoice is None:
        return None

    vendor = getattr(invoice, 'vendor', None)
    vendor_exempt = bool(getattr(vendor, 'wht_exempt', False)) if vendor else False
    if vendor_exempt:
        return DerivedWht(
            deduction_type='WHT',
            description=f"Vendor exempt: WHT not applicable on {invoice.invoice_number}",
            rate=Decimal('0'),
            amount=Decimal('0'),
            invoice_id=invoice.pk,
            invoice_number=invoice.invoice_number,
            is_exempt=True,
            exempt_reason='Vendor permanently exempt from WHT (master data)',
            source='vendor_master',
        )

    # Transaction-level exemption check — InvoiceMatching.wht_exempt is
    # set when the verifier opted to exempt this specific invoice on the
    # 3-way match form. Honour it BEFORE looking for any WHT codes so
    # the exemption isn't overridden by line-level WHT FKs that may
    # have been left in place from defaults.
    try:
        exempt_matching = invoice.invoice_matchings.filter(
            wht_exempt=True,
        ).first()
    except Exception:
        exempt_matching = None
    if exempt_matching is not None:
        return DerivedWht(
            deduction_type='WHT',
            description=f"Transaction exempt: invoice {invoice.invoice_number}",
            rate=Decimal('0'),
            amount=Decimal('0'),
            invoice_id=invoice.pk,
            invoice_number=invoice.invoice_number,
            is_exempt=True,
            exempt_reason=(
                exempt_matching.wht_exempt_reason
                or 'Invoice flagged WHT-exempt at verification'
            ),
            source='matching_transaction_exempt',
        )

    # Per-line determination (preferred — supports mixed lines).
    total_wht = Decimal('0.00')
    wht_obj = None
    wht_account = None
    line_count_with_wht = 0
    line_count_exempt = 0
    line_exempt_reasons: list[str] = []

    for line in invoice.lines.all():
        if getattr(line, 'wht_exempt', False):
            line_count_exempt += 1
            reason = getattr(line, 'wht_exempt_reason', '') or ''
            if reason:
                line_exempt_reasons.append(reason)
            continue
        wht = getattr(line, 'withholding_tax', None)
        if not (wht and wht.rate and Decimal(str(wht.rate)) > 0):
            continue
        rate = Decimal(str(wht.rate))
        amount = (
            Decimal(str(line.amount)) * rate / Decimal('100')
        ).quantize(Decimal('0.01'))
        if amount <= 0:
            continue
        # Track the predominant WHT code/GL — when the invoice mixes
        # codes we still emit one consolidated deduction row using the
        # last code's GL (operator can split later if needed).
        wht_obj = wht
        wht_account = getattr(wht, 'withholding_account', None)
        total_wht += amount
        line_count_with_wht += 1

    # No lines carried WHT — fall back to the matching's header-level
    # determination (set on InvoiceMatching when the operator picked WHT
    # on the verification screen).
    if total_wht == 0:
        # Try an InvoiceMatching linked to this invoice
        matching = invoice.invoice_matchings.filter(
            withholding_tax__isnull=False, wht_exempt=False,
        ).first() if hasattr(invoice, 'invoice_matchings') else None
        if matching is None:
            matching = getattr(invoice, 'invoicematching_set', None)
            matching = matching.filter(
                withholding_tax__isnull=False, wht_exempt=False,
            ).first() if matching is not None else None
        if matching is not None and matching.withholding_tax:
            wht_obj = matching.withholding_tax
            rate = Decimal(str(wht_obj.rate or 0))
            sub = Decimal(str(matching.invoice_subtotal or matching.invoice_amount or 0))
            if rate > 0 and sub > 0:
                total_wht = (sub * rate / Decimal('100')).quantize(Decimal('0.01'))
                wht_account = getattr(wht_obj, 'withholding_account', None)

    # If ANY line is exempt and none triggered WHT, surface that to the caller.
    if total_wht == 0 and line_count_exempt > 0:
        return DerivedWht(
            deduction_type='WHT',
            description=f"Invoice {invoice.invoice_number} flagged WHT-exempt",
            rate=Decimal('0'),
            amount=Decimal('0'),
            invoice_id=invoice.pk,
            invoice_number=invoice.invoice_number,
            is_exempt=True,
            exempt_reason='; '.join(line_exempt_reasons) or 'Invoice flagged WHT-exempt',
            source='invoice_line_exempt',
        )

    if total_wht <= 0 or wht_obj is None or wht_account is None:
        return None

    return DerivedWht(
        deduction_type='WHT',
        description=(
            f"WHT @ {wht_obj.rate}% ({wht_obj.code}) on invoice "
            f"{invoice.invoice_number}"
        ),
        withholding_tax=wht_obj.pk,
        rate=Decimal(str(wht_obj.rate)),
        amount=total_wht,
        gl_account=wht_account.pk,
        invoice_id=invoice.pk,
        invoice_number=invoice.invoice_number,
        is_exempt=False,
        exempt_reason='',
        source='invoice_line' if line_count_with_wht else 'invoice_matching',
    )
