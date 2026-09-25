"""``create_draft_voucher_from_invoice`` must raise the PV for **payable_now**
(gross − paid − retention lien), never ``balance_due``.

A contract milestone invoice is booked GROSS with a ``retention_withheld`` lien
that is frozen from disbursement until released. If the Create-PV factory used
``balance_due`` (gross − paid) it would pull that frozen retention into a
payable — disbursing money the contract deliberately held back. This locks the
factory to ``payable_now`` so the lien is respected at the PV step.

See docs/superpowers/specs/2026-09-23-ap-register-create-pv-flow-design.md (Delta A).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest


def _prereqs():
    """The Vendor + active TSA + active NCoACode the factory requires."""
    from accounting.models.gl import Account
    from accounting.models.ncoa import (
        AdministrativeSegment, FunctionalSegment, ProgrammeSegment,
        FundSegment, GeographicSegment, NCoACode,
    )
    from accounting.models.treasury import TreasuryAccount
    from procurement.models import Vendor

    admin, _ = AdministrativeSegment.objects.get_or_create(
        code='050900000001', defaults={'name': 'PVF MDA', 'level': 'UNIT', 'sector_code': '05'},
    )
    econ, _ = Account.objects.get_or_create(
        code='22100901', defaults={'name': 'PVF Expense', 'account_type': 'Expense'},
    )
    func, _ = FunctionalSegment.objects.get_or_create(
        code='70191', defaults={'name': 'PVF Func', 'division_code': '701'},
    )
    prog, _ = ProgrammeSegment.objects.get_or_create(
        code='01010000000091', defaults={'name': 'PVF Prog', 'policy_code': '01', 'programme_code': '01'},
    )
    fund_seg, _ = FundSegment.objects.get_or_create(
        code='01091', defaults={'name': 'PVF Fund', 'main_fund_code': '01'},
    )
    geo, _ = GeographicSegment.objects.get_or_create(
        code='51000091', defaults={'name': 'PVF Geo', 'zone_code': '5'},
    )
    NCoACode.objects.get_or_create(
        administrative=admin, economic=econ, functional=func,
        programme=prog, fund=fund_seg, geographic=geo,
        defaults={'is_active': True},
    )
    vendor, _ = Vendor.objects.get_or_create(
        code='V-PVF', defaults={'name': 'PVF Vendor Ltd', 'is_active': True},
    )
    TreasuryAccount.objects.get_or_create(
        account_number='0011223344',
        defaults={'account_name': 'PVF TSA', 'bank': 'CBN',
                  'account_type': 'MAIN_TSA', 'is_active': True},
    )
    return vendor


def _invoice(vendor, *, total, paid='0.00', retention='0.00'):
    from accounting.models.receivables import VendorInvoice
    return VendorInvoice.objects.create(
        invoice_number=f'PVF-{total}-{paid}-{retention}',
        vendor=vendor, invoice_date=date(2026, 3, 1), due_date=date(2026, 3, 1),
        subtotal=Decimal(total), total_amount=Decimal(total),
        paid_amount=Decimal(paid), retention_withheld=Decimal(retention),
        status='Posted',
    )


@pytest.mark.django_db
class TestCreateDraftVoucherFromInvoice:

    def test_gross_excludes_retention_lien(self, db):
        """₦20M invoice with a ₦1M retention lien → PV gross ₦19M, not ₦20M."""
        from accounting.services.pv_factory import create_draft_voucher_from_invoice
        vendor = _prereqs()
        inv = _invoice(vendor, total='20000000.00', retention='1000000.00')
        pv = create_draft_voucher_from_invoice(invoice=inv, actor=None)
        assert inv.payable_now == Decimal('19000000.00')
        assert pv.gross_amount == Decimal('19000000.00')   # payable_now, NOT balance_due (20M)

    def test_gross_excludes_paid_and_retention(self, db):
        from accounting.services.pv_factory import create_draft_voucher_from_invoice
        vendor = _prereqs()
        inv = _invoice(vendor, total='1000000.00', paid='200000.00', retention='50000.00')
        pv = create_draft_voucher_from_invoice(invoice=inv, actor=None)
        assert pv.gross_amount == Decimal('750000.00')     # 1,000,000 − 200,000 − 50,000

    def test_no_retention_matches_balance_due(self, db):
        """Backward-compat: with no lien, payable_now == balance_due."""
        from accounting.services.pv_factory import create_draft_voucher_from_invoice
        vendor = _prereqs()
        inv = _invoice(vendor, total='500000.00', paid='100000.00', retention='0.00')
        pv = create_draft_voucher_from_invoice(invoice=inv, actor=None)
        assert pv.gross_amount == Decimal('400000.00') == inv.balance_due
