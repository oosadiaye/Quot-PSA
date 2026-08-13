"""WHT derivation by invoice number — QA finding M-4, reclassified.

The QA report listed "WHT ₦0.00 on all payment vouchers" as a MEDIUM,
config-dependent observation. It is not configuration. WHT is configured
(WHT01 @ 10%, active), no vendor is flagged exempt, and one invoice line
carries the withholding_tax FK — yet no PV has ever received a WHT
deduction.

The cause: ``derive_wht_for_invoice`` builds its lookup with
``select_related('vendor', 'tax_code', 'withholding_tax')``, but
``tax_code`` and ``withholding_tax`` are fields of ``VendorInvoiceLine``,
not ``VendorInvoice``. Django raises ``FieldError`` as soon as the
queryset is evaluated, so the function fails 100% of the time on the
invoice_number path — which is the path both production callers use.

It was invisible because ``serializers_treasury`` wraps the call in a
bare ``except Exception: derived_wht = None``, so every PV silently
skipped withholding.

That matters beyond tidiness: WHT is a statutory deduction remitted to
FIRS. Silently withholding nothing understates the liability on every
vendor payment.
"""
from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.integration
class TestDeriveWhtByInvoiceNumber:

    def _make_invoice(self, vendor, account, wht):
        from accounting.models import VendorInvoice, VendorInvoiceLine
        invoice = VendorInvoice.objects.create(
            invoice_number='WHT-TEST-0001',
            vendor=vendor,
            total_amount=Decimal('100000.00'),
        )
        VendorInvoiceLine.objects.create(
            invoice=invoice,
            account=account,
            description='Consultancy',
            amount=Decimal('100000.00'),
            withholding_tax=wht,
        )
        return invoice

    @pytest.fixture
    def wht_vendor(self, db):
        from procurement.models import Vendor
        return Vendor.objects.create(
            name='WHT Test Vendor', code='V-WHT-TEST', is_active=True,
        )

    @pytest.fixture
    def wht_code(self, db, expense_account):
        from accounting.models import WithholdingTax
        return WithholdingTax.objects.create(
            code='WHT-T10', name='Test WHT 10%',
            rate=Decimal('10.00'), is_active=True,
            withholding_account=expense_account,
        )

    def test_lookup_by_invoice_number_does_not_raise(
            self, db, wht_vendor, expense_account, wht_code):
        """The regression guard: this raised FieldError for every caller."""
        from accounting.services.wht_payment_derivation import (
            derive_wht_for_invoice,
        )
        self._make_invoice(wht_vendor, expense_account, wht_code)
        # Must not raise. Before the fix this was
        # FieldError: Invalid field name(s) given in select_related.
        derive_wht_for_invoice(invoice_number='WHT-TEST-0001')

    def test_derives_wht_from_the_invoice_line(
            self, db, wht_vendor, expense_account, wht_code):
        from accounting.services.wht_payment_derivation import (
            derive_wht_for_invoice,
        )
        self._make_invoice(wht_vendor, expense_account, wht_code)
        result = derive_wht_for_invoice(invoice_number='WHT-TEST-0001')
        assert result is not None, 'no WHT determination returned'
        assert result.get('is_exempt') is False
        # 10% of 100,000
        assert Decimal(str(result['amount'])) == Decimal('10000.00')

    def test_returns_none_for_unknown_invoice_number(self, db):
        from accounting.services.wht_payment_derivation import (
            derive_wht_for_invoice,
        )
        assert derive_wht_for_invoice(invoice_number='NOPE-9999') is None

    def test_vendor_exemption_short_circuits(
            self, db, wht_vendor, expense_account, wht_code):
        from accounting.services.wht_payment_derivation import (
            derive_wht_for_invoice,
        )
        wht_vendor.wht_exempt = True
        wht_vendor.save(update_fields=['wht_exempt'])
        self._make_invoice(wht_vendor, expense_account, wht_code)
        result = derive_wht_for_invoice(invoice_number='WHT-TEST-0001')
        assert result is not None
        assert result['is_exempt'] is True
        assert Decimal(str(result['amount'])) == Decimal('0')
