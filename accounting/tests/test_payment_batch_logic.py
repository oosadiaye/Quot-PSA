"""Payment batching — fast unit tests (no DB, no I/O)."""
from __future__ import annotations

from datetime import date

import pytest


@pytest.mark.unit
class TestBatchNumberFormat:

    def test_formats_with_year_and_zero_padded_sequence(self):
        from accounting.services.payment_batch import format_batch_number
        assert format_batch_number(2026, 1) == 'PB/2026/0001'

    def test_pads_to_four_digits(self):
        from accounting.services.payment_batch import format_batch_number
        assert format_batch_number(2026, 42) == 'PB/2026/0042'

    def test_does_not_truncate_beyond_four_digits(self):
        from accounting.services.payment_batch import format_batch_number
        assert format_batch_number(2026, 12345) == 'PB/2026/12345'

    def test_rejects_non_positive_sequence(self):
        from accounting.services.payment_batch import format_batch_number
        with pytest.raises(ValueError):
            format_batch_number(2026, 0)


class _FakePV:
    def __init__(self, name='', bank='', acct='', narration='', net=None):
        self.payee_name = name
        self.payee_bank = bank
        self.payee_account = acct
        self.narration = narration
        self.net_amount = net


class _FakeVendor:
    def __init__(self, name='', bank_name='', acct=''):
        self.name = name
        self.bank_name = bank_name
        self.bank_account_number = acct


class _FakePayment:
    def __init__(self, pv=None, vendor=None, ref='', total=None):
        self.payment_voucher = pv
        self.vendor = vendor
        self.reference_number = ref
        self.total_amount = total


@pytest.mark.unit
class TestResolvePayeeSnapshot:

    def test_prefers_pv_fields(self):
        from decimal import Decimal
        from accounting.services.payment_batch import resolve_payee_snapshot
        pay = _FakePayment(
            pv=_FakePV('ACME Ltd', 'Zenith Bank', '0123456789',
                       'Supply of stationery', Decimal('900.00')),
            vendor=_FakeVendor('STALE NAME', 'STALE BANK', '9999999999'),
            ref='REF-1', total=Decimal('1000.00'),
        )
        snap = resolve_payee_snapshot(pay)
        assert snap['payee_name'] == 'ACME Ltd'
        assert snap['payee_bank'] == 'Zenith Bank'
        assert snap['payee_account'] == '0123456789'
        assert snap['purpose'] == 'Supply of stationery'
        # Identity comes from the PV; the SUM never does. The bank is told
        # to move the cash this Payment actually disburses (1000.00), not
        # the voucher's net (900.00) — one PV may be settled by several
        # payments, and billing each line the full voucher would instruct
        # the bank to pay it more than once.
        assert snap['amount'] == Decimal('1000.00')

    def test_falls_back_to_vendor_when_no_pv(self):
        from decimal import Decimal
        from accounting.services.payment_batch import resolve_payee_snapshot
        pay = _FakePayment(
            pv=None,
            vendor=_FakeVendor('Beta Works', 'First Bank', '0987654321'),
            ref='Consultancy', total=Decimal('500.00'),
        )
        snap = resolve_payee_snapshot(pay)
        assert snap['payee_name'] == 'Beta Works'
        assert snap['payee_bank'] == 'First Bank'
        assert snap['payee_account'] == '0987654321'
        assert snap['purpose'] == 'Consultancy'
        assert snap['amount'] == Decimal('500.00')

    def test_falls_back_per_field_when_pv_field_blank(self):
        from decimal import Decimal
        from accounting.services.payment_batch import resolve_payee_snapshot
        pay = _FakePayment(
            pv=_FakePV('ACME Ltd', '', '', '', Decimal('900.00')),
            vendor=_FakeVendor('ACME Ltd', 'GTB', '0123456789'),
            ref='REF-1', total=Decimal('1000.00'),
        )
        snap = resolve_payee_snapshot(pay)
        assert snap['payee_bank'] == 'GTB'
        assert snap['payee_account'] == '0123456789'

    def test_handles_payment_with_no_vendor_and_no_pv(self):
        from decimal import Decimal
        from accounting.services.payment_batch import resolve_payee_snapshot
        pay = _FakePayment(pv=None, vendor=None, ref='', total=Decimal('10.00'))
        snap = resolve_payee_snapshot(pay)
        assert snap['payee_name'] == ''
        assert snap['payee_bank'] == ''
        assert snap['payee_account'] == ''
        assert snap['amount'] == Decimal('10.00')


@pytest.mark.unit
class TestNUBANValidator:

    def test_accepts_ten_digits(self):
        from procurement.validators import validate_nuban
        validate_nuban('0123456789')   # must not raise

    def test_rejects_nine_digits(self):
        from django.core.exceptions import ValidationError
        from procurement.validators import validate_nuban
        with pytest.raises(ValidationError):
            validate_nuban('012345678')

    def test_rejects_non_digits(self):
        from django.core.exceptions import ValidationError
        from procurement.validators import validate_nuban
        with pytest.raises(ValidationError):
            validate_nuban('01234-6789')

    def test_allows_blank(self):
        """Bank details stay optional on Vendor; completeness is enforced
        at the batch boundary instead."""
        from procurement.validators import validate_nuban
        validate_nuban('')   # must not raise
