"""Central payment processing.

Approving a Payment Voucher provisions a deduction-aware DRAFT Payment
(auto-allocated to the invoice, or allocation-free for advances), and
posting that Payment is the ONLY disbursement event — DR vendor/AP
(gross) / CR each deduction G/L / CR bank (net). "Mark Paid" on the PV
is gone.

Covers:
  * ``ensure_draft_payment_for_pv`` — the shared provisioning helper.
  * ``PaymentViewSet.post_payment`` deduction-aware journal for an
    invoice PV, plus allocation-optional and the advance branch.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


# ── Reference-data builders (get_or_create — survive transaction=True) ──

def _ncoa():
    from accounting.models.gl import Account
    from accounting.models.ncoa import (
        AdministrativeSegment, FunctionalSegment,
        ProgrammeSegment, FundSegment, GeographicSegment, NCoACode,
    )
    admin, _ = AdministrativeSegment.objects.get_or_create(
        code='050200000000',
        defaults={'name': 'Test MDA', 'level': 'UNIT', 'sector_code': '05'},
    )
    econ, _ = Account.objects.get_or_create(
        code='22100100',
        defaults={'name': 'Test Expense', 'account_type': 'Expense'},
    )
    # Keep these shared segments UNBRIDGED so the unbridged direct-PV tests
    # skip the warrant gate (the bridged warrant test uses _ncoa_bridged()).
    if admin.legacy_mda_id is not None:
        admin.legacy_mda = None
        admin.save()
    func, _ = FunctionalSegment.objects.get_or_create(
        code='70100',
        defaults={'name': 'General Services', 'division_code': '701'},
    )
    prog, _ = ProgrammeSegment.objects.get_or_create(
        code='01010000000000',
        defaults={'name': 'Test Programme', 'policy_code': '01', 'programme_code': '01'},
    )
    fund, _ = FundSegment.objects.get_or_create(
        code='01000',
        defaults={'name': 'Consolidated Fund', 'main_fund_code': '01'},
    )
    if fund.legacy_fund_id is not None:
        fund.legacy_fund = None
        fund.save()
    geo, _ = GeographicSegment.objects.get_or_create(
        code='51000000',
        defaults={'name': 'Test State', 'zone_code': '5'},
    )
    ncoa, _ = NCoACode.objects.get_or_create(
        administrative=admin, economic=econ, functional=func,
        programme=prog, fund=fund, geographic=geo,
        defaults={'is_active': True},
    )
    return ncoa


def _ncoa_bridged():
    """A distinct NCoA whose admin/fund segments carry the legacy MDA/Fund
    bridge — so the warrant-dimension resolution fires. Kept separate from
    ``_ncoa()`` (which stays unbridged) so only the warrant test exercises
    the gate."""
    from accounting.models.gl import Account, MDA, Fund
    from accounting.models.ncoa import (
        AdministrativeSegment, FunctionalSegment,
        ProgrammeSegment, FundSegment, GeographicSegment, NCoACode,
    )
    mda, _ = MDA.objects.get_or_create(
        code='CPP-MDA', defaults={'name': 'Bridged MDA', 'mda_type': 'MDA'},
    )
    fund_leg, _ = Fund.objects.get_or_create(code='CPP-FUND', defaults={'name': 'Bridged Fund'})
    admin, _ = AdministrativeSegment.objects.get_or_create(
        code='050200000099',
        defaults={'name': 'Bridged MDA seg', 'level': 'UNIT', 'sector_code': '05'},
    )
    if admin.legacy_mda_id != mda.id:
        admin.legacy_mda = mda
        admin.save()
    econ, _ = Account.objects.get_or_create(
        code='22100199', defaults={'name': 'Bridged Expense', 'account_type': 'Expense'},
    )
    func, _ = FunctionalSegment.objects.get_or_create(
        code='70199', defaults={'name': 'GS', 'division_code': '701'},
    )
    prog, _ = ProgrammeSegment.objects.get_or_create(
        code='01010000000099', defaults={'name': 'Prog', 'policy_code': '01', 'programme_code': '01'},
    )
    fund_seg, _ = FundSegment.objects.get_or_create(
        code='01099', defaults={'name': 'Fund', 'main_fund_code': '01'},
    )
    if fund_seg.legacy_fund_id != fund_leg.id:
        fund_seg.legacy_fund = fund_leg
        fund_seg.save()
    geo, _ = GeographicSegment.objects.get_or_create(
        code='51000099', defaults={'name': 'State', 'zone_code': '5'},
    )
    ncoa, _ = NCoACode.objects.get_or_create(
        administrative=admin, economic=econ, functional=func,
        programme=prog, fund=fund_seg, geographic=geo,
        defaults={'is_active': True},
    )
    _permit_budget('22100199')
    return ncoa


def _tsa():
    from accounting.models.treasury import TreasuryAccount
    tsa, _ = TreasuryAccount.objects.get_or_create(
        account_number='0011223344',
        defaults={'account_name': 'Test TSA', 'bank': 'CBN', 'account_type': 'MAIN_TSA'},
    )
    return tsa


def _vendor():
    from procurement.models import Vendor
    vendor, _ = Vendor.objects.get_or_create(
        code='V-CPP', defaults={'name': 'Central Pay Ltd'},
    )
    return vendor


def _accounts():
    """AP (recon-tagged), a WHT liability GL, and the advance recon."""
    from accounting.models.gl import Account
    ap, _ = Account.objects.get_or_create(
        code='20100000',
        defaults={'name': 'Accounts Payable', 'account_type': 'Liability', 'is_active': True},
    )
    if ap.reconciliation_type != 'accounts_payable' or not ap.is_active:
        ap.reconciliation_type = 'accounts_payable'
        ap.is_active = True
        ap.save()
    wht_gl, _ = Account.objects.get_or_create(
        code='41030103',
        defaults={'name': 'Unremitted WHT', 'account_type': 'Liability', 'is_active': True},
    )
    recon, _ = Account.objects.get_or_create(
        code='31050000',
        defaults={'name': 'Vendor Advances (Special GL)', 'account_type': 'Asset', 'is_active': True},
    )
    if recon.reconciliation_type != 'vendor_advance' or not recon.is_active:
        recon.reconciliation_type = 'vendor_advance'
        recon.is_active = True
        recon.save()
    # The default seeded rule puts these codes under STRICT budget control
    # (needs an appropriation). Paying down AP / crediting a deduction /
    # crediting bank consumes no new budget, so permit them explicitly with
    # a width-0 NONE rule (narrowest → wins resolution). 22100100 is the
    # NCoA economic (expense) line a direct/non-invoice PV debits.
    _permit_budget('20100000', '41030103', '10100000', '31050000', '22100100')
    _disable_warrant()  # off by default; the warrant test patches it on
    return ap, wht_gl, recon


def _permit_budget(*codes):
    from accounting.models import BudgetCheckRule
    for c in codes:
        BudgetCheckRule.objects.get_or_create(
            gl_from=c, gl_to=c,
            defaults={
                'check_level': 'NONE', 'priority': 1000,
                'is_active': True, 'description': 'test-permit',
            },
        )


def _disable_warrant():
    """warrant_enforcement_enabled() fails closed (True) with no settings
    row, so give the test schema an explicit OFF switch. The warrant test
    patches the helper back on."""
    from accounting.models.advanced import AccountingSettings
    s = AccountingSettings.objects.first() or AccountingSettings.objects.create()
    if s.require_warrant_before_payment:
        s.require_warrant_before_payment = False
        s.save(update_fields=['require_warrant_before_payment'])


def _make_pv(*, payment_type='VENDOR', special_gl='', invoice_number='',
             gross=Decimal('100000.00'), vendor=None, ncoa=None):
    from accounting.models.treasury import PaymentVoucherGov
    return PaymentVoucherGov.objects.create(
        voucher_number=f'PV-{uuid.uuid4().hex[:10]}',
        payment_type=payment_type,
        ncoa_code=ncoa or _ncoa(),
        payee_name=(vendor.name if vendor else 'Test Payee'),
        gross_amount=gross,
        net_amount=gross,
        narration='central pay test',
        tsa_account=_tsa(),
        invoice_number=invoice_number,
        special_gl_indicator=special_gl,
        vendor=vendor,
        status='DRAFT',
    )


def _add_wht(pv, gl, amount):
    """Attach a WHT deduction and refresh net_amount via save()."""
    from accounting.models.treasury import PaymentVoucherDeduction
    PaymentVoucherDeduction.objects.create(
        payment_voucher=pv, deduction_type='WHT', description='WHT 10%',
        rate=Decimal('10.00'), amount=Decimal(str(amount)), gl_account=gl,
    )
    pv.save()
    pv.refresh_from_db()


# ── The provisioning helper ────────────────────────────────────────────

@pytest.mark.django_db
class TestEnsureDraftPaymentForPV:

    def test_invoice_pv_creates_payment_and_allocation_at_gross(self, db):
        from accounting.models.receivables import VendorInvoice
        from accounting.services.pv_payment_provisioning import ensure_draft_payment_for_pv
        vendor = _vendor()
        inv_no = f'VINV-{uuid.uuid4().hex[:8]}'
        inv = VendorInvoice.objects.create(
            invoice_number=inv_no, vendor=vendor,
            total_amount=Decimal('100000.00'), status='Posted',
        )
        _, wht_gl, _ = _accounts()
        pv = _make_pv(invoice_number=inv_no, gross=Decimal('100000.00'), vendor=vendor)
        _add_wht(pv, wht_gl, '10000.00')  # net = 90,000

        payment = _provision(pv)

        assert payment.status == 'Draft'
        assert payment.is_advance is False
        assert payment.total_amount == Decimal('90000.00')     # net = cash
        assert payment.vendor_id == vendor.id
        alloc = payment.allocations.get()
        assert alloc.invoice_id == inv.id
        assert alloc.amount == Decimal('100000.00')            # gross settlement

    def test_advance_pv_creates_payment_with_no_allocation(self, db):
        from accounting.services.pv_payment_provisioning import ensure_draft_payment_for_pv
        vendor = _vendor()
        pv = _make_pv(payment_type='ADVANCE', special_gl='A', vendor=vendor,
                      gross=Decimal('50000.00'))
        payment = _provision(pv)
        assert payment.is_advance is True
        assert payment.advance_type == 'Supplier Advance'
        assert payment.allocations.count() == 0

    def test_no_invoice_pv_creates_payment_without_allocation(self, db):
        from accounting.services.pv_payment_provisioning import ensure_draft_payment_for_pv
        pv = _make_pv(payment_type='SALARY', invoice_number='', gross=Decimal('30000.00'))
        payment = _provision(pv)
        assert payment.is_advance is False
        assert payment.allocations.count() == 0

    def test_idempotent_no_duplicate_payment(self, db):
        from accounting.services.pv_payment_provisioning import ensure_draft_payment_for_pv
        vendor = _vendor()
        pv = _make_pv(payment_type='ADVANCE', special_gl='A', vendor=vendor)
        p1 = ensure_draft_payment_for_pv(pv)
        p2 = ensure_draft_payment_for_pv(pv)
        assert p1.id == p2.id
        assert pv.cash_payments.exclude(status='Void').count() == 1


# ── Posting through the real DRF action ────────────────────────────────

def _provision(pv):
    """Provision the draft Payment the way real callers do — inside a
    transaction (the helper takes a row lock via select_for_update)."""
    from django.db import transaction
    from accounting.services.pv_payment_provisioning import ensure_draft_payment_for_pv
    with transaction.atomic():
        return ensure_draft_payment_for_pv(pv)


def _post_payment(payment, user):
    """Drive PaymentViewSet.post_payment via a superuser DRF request."""
    from rest_framework.test import APIRequestFactory, force_authenticate
    from accounting.views.payables import PaymentViewSet
    factory = APIRequestFactory()
    request = factory.post(
        f'/accounting/payments/{payment.pk}/post_payment/', {}, format='json',
    )
    force_authenticate(request, user=user)
    view = PaymentViewSet.as_view({'post': 'post_payment'})
    return view(request, pk=payment.pk)


@pytest.mark.django_db(transaction=True)
class TestPostPaymentDeductions:

    def test_invoice_payment_posts_gross_deductions_net(
        self, superuser, bank_account_for_batch, open_fiscal_period,
    ):
        from accounting.models.receivables import VendorInvoice, Payment
        from accounting.services.pv_payment_provisioning import ensure_draft_payment_for_pv
        vendor = _vendor()
        ap, wht_gl, _ = _accounts()
        inv_no = f'VINV-{uuid.uuid4().hex[:8]}'
        inv = VendorInvoice.objects.create(
            invoice_number=inv_no, vendor=vendor,
            total_amount=Decimal('100000.00'), status='Posted',
        )
        pv = _make_pv(invoice_number=inv_no, gross=Decimal('100000.00'), vendor=vendor)
        _add_wht(pv, wht_gl, '10000.00')  # net 90,000
        payment = _provision(pv)
        payment.bank_account = bank_account_for_batch
        payment.save()

        resp = _post_payment(payment, superuser)
        assert resp.status_code == 200, getattr(resp, 'data', resp)

        payment.refresh_from_db()
        assert payment.status == 'Posted'
        j = payment.journal_entry
        lines = {l.account_id: (l.debit or 0, l.credit or 0) for l in j.lines.all()}
        assert lines[ap.id][0] == Decimal('100000.00')                       # DR AP gross
        assert lines[wht_gl.id][1] == Decimal('10000.00')                    # CR WHT
        assert lines[bank_account_for_batch.gl_account_id][1] == Decimal('90000.00')  # CR bank net
        dr = sum(d for d, _ in lines.values()); cr = sum(c for _, c in lines.values())
        assert dr == cr == Decimal('100000.00')
        inv.refresh_from_db(); pv.refresh_from_db()
        assert inv.status == 'Paid'
        assert pv.status == 'PAID'

    def test_no_allocation_payment_still_posts(self, superuser, bank_account_for_batch, open_fiscal_period):
        """Allocation is not mandatory: a no-invoice PV payment posts."""
        from accounting.services.pv_payment_provisioning import ensure_draft_payment_for_pv
        pv = _make_pv(payment_type='SALARY', invoice_number='', gross=Decimal('40000.00'))
        _accounts()
        payment = _provision(pv)
        payment.bank_account = bank_account_for_batch
        payment.save()
        assert payment.allocations.count() == 0

        resp = _post_payment(payment, superuser)
        assert resp.status_code == 200, getattr(resp, 'data', resp)
        payment.refresh_from_db(); pv.refresh_from_db()
        assert payment.status == 'Posted'
        assert pv.status == 'PAID'

    def test_advance_payment_posts_gross_advance_net_cash(
        self, superuser, bank_account_for_batch, open_fiscal_period,
    ):
        from accounting.models.vendor_advance import VendorAdvance
        from accounting.services.pv_payment_provisioning import ensure_draft_payment_for_pv
        vendor = _vendor()
        _, wht_gl, recon = _accounts()
        pv = _make_pv(payment_type='ADVANCE', special_gl='A', vendor=vendor,
                      gross=Decimal('100000.00'))
        _add_wht(pv, wht_gl, '10000.00')  # net 90,000
        payment = _provision(pv)
        payment.bank_account = bank_account_for_batch
        payment.save()
        assert payment.is_advance is True and payment.allocations.count() == 0

        resp = _post_payment(payment, superuser)
        assert resp.status_code == 200, getattr(resp, 'data', resp)

        payment.refresh_from_db(); pv.refresh_from_db()
        assert payment.status == 'Posted'
        assert pv.status == 'PAID'
        adv = VendorAdvance.objects.get(source_id=payment.pk, source_type='AP_DOWNPAYMENT')
        assert adv.amount_paid == Decimal('100000.00')  # advance recognised at gross
        j = adv.disbursement_journal
        lines = {l.account_id: (l.debit or 0, l.credit or 0) for l in j.lines.all()}
        assert lines[recon.id][0] == Decimal('100000.00')
        assert lines[wht_gl.id][1] == Decimal('10000.00')

    def test_direct_pv_recognises_expense_not_ap(
        self, superuser, bank_account_for_batch, open_fiscal_period,
    ):
        """A non-invoice PV debits the EXPENSE line (recognises the expense
        + triggers budget/warrant), not AP."""
        ap, _, _ = _accounts()
        econ = _ncoa().economic
        pv = _make_pv(payment_type='SALARY', invoice_number='', gross=Decimal('40000.00'))
        payment = _provision(pv)
        payment.bank_account = bank_account_for_batch
        payment.save()

        resp = _post_payment(payment, superuser)
        assert resp.status_code == 200, getattr(resp, 'data', resp)
        payment.refresh_from_db()
        lines = {l.account_id: (l.debit or 0, l.credit or 0) for l in payment.journal_entry.lines.all()}
        assert lines[econ.id][0] == Decimal('40000.00')                        # DR expense (recognised)
        assert lines[bank_account_for_batch.gl_account_id][1] == Decimal('40000.00')  # CR bank
        assert ap.id not in lines                                             # NOT the AP settlement journal

    def test_direct_pv_blocked_when_warrant_exceeded(
        self, superuser, bank_account_for_batch, open_fiscal_period,
    ):
        """The quarterly warrant/AIE ceiling is enforced on the direct-PV
        branch (parity with the AP/invoice branch)."""
        from unittest.mock import patch
        _accounts()
        # Bridged NCoA → the warrant dimensions resolve (distinct segments,
        # so the other direct-PV tests stay unbridged and skip the gate).
        pv = _make_pv(payment_type='STATUTORY', invoice_number='',
                      gross=Decimal('25000.00'), ncoa=_ncoa_bridged())
        payment = _provision(pv)
        payment.bank_account = bank_account_for_batch
        payment.save()

        with patch('accounting.budget_logic.warrant_enforcement_enabled', return_value=True), \
             patch(
                 'accounting.budget_logic.check_warrant_availability',
                 return_value=(False, 'ceiling exceeded', {'warrants_released': Decimal('10000')}),
             ):
            resp = _post_payment(payment, superuser)

        assert resp.status_code == 400
        assert resp.data.get('warrant_exceeded') is True
        payment.refresh_from_db()
        assert payment.status == 'Draft'  # no cash moved

    def test_standalone_payment_without_pv_or_allocation_rejected(
        self, superuser, bank_account_for_batch, open_fiscal_period,
    ):
        """CRITICAL: a payment with no PV and no allocation must not post."""
        from accounting.models.receivables import Payment
        _accounts()
        pay = Payment.objects.create(
            payment_number=f'PAY-{uuid.uuid4().hex[:8]}', payment_method='Wire',
            total_amount=Decimal('5000.00'), status='Draft',
            bank_account=bank_account_for_batch,
        )
        resp = _post_payment(pay, superuser)
        assert resp.status_code == 400
        assert 'Payment Voucher' in str(getattr(resp, 'data', resp))
        pay.refresh_from_db()
        assert pay.status == 'Draft'  # unchanged — no cash moved

    def test_cannot_post_when_pv_already_paid(
        self, superuser, bank_account_for_batch, open_fiscal_period,
    ):
        """CRITICAL: the terminal-status precondition blocks double-pay."""
        from accounting.models.receivables import VendorInvoice
        vendor = _vendor()
        _accounts()
        inv_no = f'VINV-{uuid.uuid4().hex[:8]}'
        VendorInvoice.objects.create(
            invoice_number=inv_no, vendor=vendor,
            total_amount=Decimal('100000.00'), status='Posted',
        )
        pv = _make_pv(invoice_number=inv_no, gross=Decimal('100000.00'), vendor=vendor)
        payment = _provision(pv)
        payment.bank_account = bank_account_for_batch
        payment.save()
        pv.status = 'PAID'  # already disbursed elsewhere
        pv.save(update_fields=['status'])

        resp = _post_payment(payment, superuser)
        assert resp.status_code == 400
        assert 'already' in str(getattr(resp, 'data', resp)).lower()


@pytest.mark.django_db
class TestOneLivePaymentPerPV:

    def test_duplicate_live_payment_per_pv_blocked(self, db):
        """CRITICAL: the DB partial-unique constraint blocks a 2nd live
        Payment for the same PV (backstops the provisioning race)."""
        from django.db import IntegrityError, transaction as _txn
        from accounting.models.receivables import Payment
        vendor = _vendor()
        pv = _make_pv(payment_type='ADVANCE', special_gl='A', vendor=vendor)
        _provision(pv)  # first live Payment
        with pytest.raises(IntegrityError):
            with _txn.atomic():
                Payment.objects.create(
                    payment_number=f'PAY-{uuid.uuid4().hex[:8]}',
                    payment_method='Wire', total_amount=Decimal('1.00'),
                    status='Draft', payment_voucher=pv,
                )
