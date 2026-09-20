"""PO down payment request → draft advance PaymentVoucher (central pipeline).

Approving a PO with a down payment request raises a DRAFT advance
PaymentVoucherGov (special G/L "A") built from the PO's committed budget line
(``ProcurementBudgetLink.ncoa_code``). That PV then rides the same pipeline as
contract mobilisation: approve the PV → draft Payment in Outgoing Payments →
post (DR Vendor-Advance recon / CR bank). No direct Payment is created.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest


def _dpr_with_committed_po():
    """A DownPaymentRequest whose PO has a committed budget line (NCoA)."""
    from accounting.models.gl import Account, Fund, Function, Program, Geo
    from accounting.models.ncoa import (
        AdministrativeSegment, FunctionalSegment, ProgrammeSegment,
        FundSegment, GeographicSegment, NCoACode,
    )
    from accounting.models.advanced import FiscalYear
    from accounting.models.treasury import TreasuryAccount
    from budget.models import Appropriation
    from procurement.models import (
        Vendor, PurchaseOrder, ProcurementBudgetLink, DownPaymentRequest,
    )

    fy, _ = FiscalYear.objects.get_or_create(
        year=2033, defaults={'name': 'FY2033', 'is_active': False},
    )
    admin, _ = AdministrativeSegment.objects.get_or_create(
        code='050900000000', defaults={'name': 'DP MDA', 'level': 'UNIT', 'sector_code': '05'},
    )
    econ, _ = Account.objects.get_or_create(
        code='22100900', defaults={'name': 'DP Expense', 'account_type': 'Expense'},
    )
    func, _ = FunctionalSegment.objects.get_or_create(
        code='70190', defaults={'name': 'DP Func', 'division_code': '701'},
    )
    prog, _ = ProgrammeSegment.objects.get_or_create(
        code='01010000000090', defaults={'name': 'DP Prog', 'policy_code': '01', 'programme_code': '01'},
    )
    fund_seg, _ = FundSegment.objects.get_or_create(
        code='01090', defaults={'name': 'DP Fund', 'main_fund_code': '01'},
    )
    geo, _ = GeographicSegment.objects.get_or_create(
        code='51000090', defaults={'name': 'DP Geo', 'zone_code': '5'},
    )
    ncoa, _ = NCoACode.objects.get_or_create(
        administrative=admin, economic=econ, functional=func,
        programme=prog, fund=fund_seg, geographic=geo,
        defaults={'is_active': True},
    )
    appr = Appropriation.objects.create(
        fiscal_year=fy, administrative=admin, economic=econ, functional=func,
        programme=prog, fund=fund_seg, geographic=geo,
        amount_approved=Decimal('1000000.00'),
        appropriation_type='ORIGINAL', status='ACTIVE',
    )
    vendor, _ = Vendor.objects.get_or_create(
        code='V-DP', defaults={'name': 'DP Vendor Ltd', 'is_active': True},
    )
    if not vendor.is_active:
        vendor.is_active = True
        vendor.save(update_fields=['is_active'])
    tsa, _ = TreasuryAccount.objects.get_or_create(
        account_number='0099887766',
        defaults={'account_name': 'DP TSA', 'bank': 'CBN', 'account_type': 'MAIN_TSA'},
    )
    if not tsa.is_active:
        tsa.is_active = True
        tsa.save(update_fields=['is_active'])
    lf, _ = Fund.objects.get_or_create(code='01090', defaults={'name': 'DP Fund'})
    lfn, _ = Function.objects.get_or_create(code='70190', defaults={'name': 'DP Func'})
    lp, _ = Program.objects.get_or_create(code='0109', defaults={'name': 'DP Prog'})
    lg, _ = Geo.objects.get_or_create(code='51000090', defaults={'name': 'DP Geo'})
    po = PurchaseOrder.objects.create(
        po_number='PO-DP-0001', vendor=vendor, order_date=date(2026, 3, 1),
        fund=lf, function=lfn, program=lp, geo=lg, notes='DP test', status='APPROVED',
    )
    ProcurementBudgetLink.objects.get_or_create(
        purchase_order=po,
        defaults={'appropriation': appr, 'ncoa_code': ncoa,
                  'committed_amount': Decimal('500000.00'), 'status': 'ACTIVE'},
    )
    dpr = DownPaymentRequest.objects.create(
        purchase_order=po, calc_type='amount', calc_value=Decimal('100000.00'),
        requested_amount=Decimal('100000.00'), payment_method='Bank', status='Approved',
    )
    return dpr, ncoa, vendor


@pytest.mark.django_db
class TestDownPaymentAdvancePV:

    def test_factory_creates_advance_pv_from_committed_po(self):
        from accounting.services.pv_factory import create_draft_voucher_from_down_payment
        dpr, ncoa, vendor = _dpr_with_committed_po()
        pv = create_draft_voucher_from_down_payment(dpr=dpr, actor=None)
        assert pv.payment_type == 'ADVANCE'
        assert pv.special_gl_indicator == 'A'
        assert pv.vendor_id == vendor.id
        assert pv.ncoa_code_id == ncoa.id        # the PO's committed NCoA line
        assert pv.gross_amount == Decimal('100000.00')
        assert pv.status == 'DRAFT'

    def test_factory_idempotent(self):
        from accounting.services.pv_factory import create_draft_voucher_from_down_payment
        dpr, _, _ = _dpr_with_committed_po()
        pv1 = create_draft_voucher_from_down_payment(dpr=dpr, actor=None)
        dpr.payment_voucher = pv1
        dpr.save(update_fields=['payment_voucher'])
        pv2 = create_draft_voucher_from_down_payment(dpr=dpr, actor=None)
        assert pv1.pk == pv2.pk

    def test_recognised_as_advance_by_central_helper(self):
        from django.db import transaction
        from accounting.services.pv_factory import create_draft_voucher_from_down_payment
        from accounting.services.pv_payment_provisioning import ensure_draft_payment_for_pv
        dpr, _, _ = _dpr_with_committed_po()
        pv = create_draft_voucher_from_down_payment(dpr=dpr, actor=None)
        with transaction.atomic():
            payment = ensure_draft_payment_for_pv(pv)
        assert payment.is_advance is True
        assert payment.advance_type == 'Supplier Advance'
        assert payment.allocations.count() == 0
        assert payment.total_amount == Decimal('100000.00')

    def test_missing_budget_link_raises(self):
        from accounting.services.pv_factory import (
            create_draft_voucher_from_down_payment, PVFactoryError,
        )
        from procurement.models import ProcurementBudgetLink, DownPaymentRequest
        dpr, _, _ = _dpr_with_committed_po()
        ProcurementBudgetLink.objects.filter(purchase_order=dpr.purchase_order).delete()
        dpr = DownPaymentRequest.objects.get(pk=dpr.pk)  # drop cached budget_link
        with pytest.raises(PVFactoryError):
            create_draft_voucher_from_down_payment(dpr=dpr, actor=None)
