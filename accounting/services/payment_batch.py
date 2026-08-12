"""
Payment batching service — every business rule for the bank
payment/confirmation letter lives here, never in the viewset.

Mirrors the structure of ``social_benefit_batch_pay.py``: module-level
helpers plus a service class with classmethods, raising a domain
exception the HTTP layer translates.
"""
from __future__ import annotations

from datetime import date as _date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

BATCH_NUMBER_PREFIX = 'PB'


def format_batch_number(year: int, sequence: int) -> str:
    """``PB/2026/0001``.

    Nigeria's fiscal year aligns with the calendar year, so the year
    component is simply the calendar year of ``batch_date``.
    """
    if sequence < 1:
        raise ValueError(f'sequence must be >= 1, got {sequence}')
    return f'{BATCH_NUMBER_PREFIX}/{year}/{sequence:04d}'


def resolve_payee_snapshot(payment) -> dict:
    """Freeze the letter row for ``payment``.

    Reads the Payment Voucher first — it is the statutory authority to pay
    and already snapshots payee bank details as at authorisation. Falls
    back per-field to the live Vendor record, because
    ``Payment.payment_voucher`` is nullable (mandatory only when
    ``AccountingSettings.require_pv_before_payment`` is on).

    ``amount`` uses the PV **net** amount: the bank credits the vendor
    after withholding tax. Where no PV exists, ``payment.total_amount`` is
    already the disbursed figure.
    """
    pv = getattr(payment, 'payment_voucher', None)
    vendor = getattr(payment, 'vendor', None)

    def pick(pv_attr: str, vendor_attr: str) -> str:
        pv_val = (getattr(pv, pv_attr, '') or '') if pv else ''
        if pv_val:
            return pv_val
        return (getattr(vendor, vendor_attr, '') or '') if vendor else ''

    purpose = (getattr(pv, 'narration', '') or '') if pv else ''
    if not purpose:
        purpose = getattr(payment, 'reference_number', '') or ''

    amount = (getattr(pv, 'net_amount', None) if pv else None)
    if amount is None:
        amount = getattr(payment, 'total_amount', None) or Decimal('0')

    return {
        'payee_name': pick('payee_name', 'name'),
        'payee_bank': pick('payee_bank', 'bank_name'),
        'payee_account': pick('payee_account', 'bank_account_number'),
        'purpose': purpose[:255],
        'amount': amount,
    }
