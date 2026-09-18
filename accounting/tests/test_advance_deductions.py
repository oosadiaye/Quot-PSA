"""Tests for deductions on a vendor down payment (special-G/L "A" advance).

Two layers are covered:

* ``_resolve_advance_deductions`` (accounting.services.pv_factory) — the
  SECURITY boundary. A client may only name *which* trusted master record
  (a WithholdingTax or a PaymentDeductionCode) to apply; the GL account,
  rate and amount are all derived server-side from that record. A raw
  client-supplied ``gl_account``/``amount`` must never be trusted — that
  was the fund-diversion hole this suite locks shut.

* ``VendorAdvanceService.disburse`` deduction math — the advance is
  recognised at GROSS on the vendor sub-ledger (``amount_paid``) while
  only the NET cash (gross − deductions) leaves the TSA, and the journal
  stays balanced (DR gross == CR deductions + CR net cash).
"""
from __future__ import annotations

from decimal import Decimal

import pytest


# ── Master-record fixtures (trusted config the client references) ──────

@pytest.fixture
def wht_liability_account(db):
    from accounting.models import Account
    acc, _ = Account.objects.get_or_create(
        code='41030103',
        defaults={
            'name': 'Unremitted WHT (State)',
            'account_type': 'Liability', 'is_active': True,
        },
    )
    return acc


@pytest.fixture
def wht_code(db, wht_liability_account):
    """A 10% withholding-tax master record pointing at its liability GL."""
    from accounting.models import WithholdingTax
    return WithholdingTax.objects.create(
        code='WHT-TEST', name='Contractor WHT', rate=Decimal('10.00'),
        withholding_account=wht_liability_account, is_active=True,
    )


@pytest.fixture
def handling_code(db, wht_liability_account):
    """A fixed-amount deduction code (₦1,500 handling charge)."""
    from accounting.models.tax import PaymentDeductionCode
    return PaymentDeductionCode.objects.create(
        code='HND-TEST', name='Handling Charge', deduction_type='HANDLING',
        calculation_method='fixed', fixed_amount=Decimal('1500.00'),
        gl_account=wht_liability_account, is_active=True,
    )


# ── _resolve_advance_deductions — the security boundary ───────────────

class TestResolveAdvanceDeductions:

    def test_derives_gl_and_amount_from_wht_master_ignoring_client_values(
        self, wht_code, wht_liability_account,
    ):
        # Arrange — a hostile payload naming a bogus GL + inflated amount.
        from accounting.services.pv_factory import _resolve_advance_deductions
        payload = [{
            'withholding_tax': wht_code.id,
            'gl_account': 999999,          # attacker-chosen — must be ignored
            'amount': '999999.00',         # attacker-chosen — must be ignored
        }]

        # Act
        rows = _resolve_advance_deductions(Decimal('100000.00'), payload)

        # Assert — GL + amount come from the master, not the client.
        assert len(rows) == 1
        assert rows[0]['gl_account'].id == wht_liability_account.id
        assert rows[0]['amount'] == Decimal('10000.00')   # 10% of gross
        assert rows[0]['deduction_type'] == 'WHT'
        assert rows[0]['withholding_tax'].id == wht_code.id

    def test_rejects_raw_gl_account_without_a_master_reference(
        self, wht_liability_account,
    ):
        from accounting.services.pv_factory import (
            _resolve_advance_deductions, PVFactoryError,
        )
        with pytest.raises(PVFactoryError):
            _resolve_advance_deductions(
                Decimal('100000'),
                [{'gl_account': wht_liability_account.id, 'amount': '50000'}],
            )

    def test_rejects_unknown_withholding_tax(self, db):
        from accounting.services.pv_factory import (
            _resolve_advance_deductions, PVFactoryError,
        )
        with pytest.raises(PVFactoryError):
            _resolve_advance_deductions(Decimal('100000'), [{'withholding_tax': 987654}])

    def test_rejects_inactive_withholding_tax(self, db, wht_liability_account):
        from accounting.models import WithholdingTax
        from accounting.services.pv_factory import (
            _resolve_advance_deductions, PVFactoryError,
        )
        inactive = WithholdingTax.objects.create(
            code='WHT-OFF', name='Retired', rate=Decimal('5.00'),
            withholding_account=wht_liability_account, is_active=False,
        )
        with pytest.raises(PVFactoryError):
            _resolve_advance_deductions(Decimal('100000'), [{'withholding_tax': inactive.id}])

    def test_rejects_master_with_no_gl_configured(self, db):
        from accounting.models import WithholdingTax
        from accounting.services.pv_factory import (
            _resolve_advance_deductions, PVFactoryError,
        )
        no_gl = WithholdingTax.objects.create(
            code='WHT-NOGL', name='Misconfigured', rate=Decimal('5.00'),
            withholding_account=None, is_active=True,
        )
        with pytest.raises(PVFactoryError):
            _resolve_advance_deductions(Decimal('100000'), [{'withholding_tax': no_gl.id}])

    def test_derives_fixed_amount_from_deduction_code(self, handling_code):
        from accounting.services.pv_factory import _resolve_advance_deductions
        rows = _resolve_advance_deductions(
            Decimal('100000'), [{'deduction_code': handling_code.id}],
        )
        assert rows[0]['amount'] == Decimal('1500.00')  # the fixed amount
        assert rows[0]['rate'] == Decimal('0')
        assert rows[0]['deduction_type'] == 'HANDLING'

    def test_rejects_total_deductions_at_or_above_gross(self, handling_code):
        from accounting.services.pv_factory import (
            _resolve_advance_deductions, PVFactoryError,
        )
        # Fixed ₦1,500 handling on a ₦1,500 advance → total == gross.
        with pytest.raises(PVFactoryError):
            _resolve_advance_deductions(Decimal('1500'), [{'deduction_code': handling_code.id}])

    def test_drops_zero_amount_line(self, db, wht_liability_account):
        from accounting.models import WithholdingTax
        from accounting.services.pv_factory import _resolve_advance_deductions
        zero = WithholdingTax.objects.create(
            code='WHT-ZERO', name='Nil rate', rate=Decimal('0.00'),
            withholding_account=wht_liability_account, is_active=True,
        )
        rows = _resolve_advance_deductions(Decimal('100000'), [{'withholding_tax': zero.id}])
        assert rows == []

    def test_empty_and_none_return_empty(self, db):
        from accounting.services.pv_factory import _resolve_advance_deductions
        assert _resolve_advance_deductions(Decimal('100000'), []) == []
        assert _resolve_advance_deductions(Decimal('100000'), None) == []


# ── disburse deduction math ───────────────────────────────────────────

@pytest.fixture
def advance_recon_account(db):
    from accounting.models import Account
    acc, _ = Account.objects.get_or_create(
        code='31050000',
        defaults={
            'name': 'Vendor Advances (Special GL)', 'account_type': 'Asset',
            'is_active': True, 'reconciliation_type': 'vendor_advance',
        },
    )
    return acc


# transaction=True → flush-based teardown (conftest patches sql_flush to
# CASCADE). Required because disburse() posts a balanced journal whose
# deferred ``prevent_unbalanced_posted_journal`` trigger otherwise fires
# under the wrong search_path during rollback-teardown's check_constraints.
@pytest.mark.django_db(transaction=True)
class TestDisburseWithDeductions:

    def _disburse(self, *, vendor, bank_account, actor, amount, deductions):
        from accounting.services.vendor_advance import VendorAdvanceService
        from datetime import date
        return VendorAdvanceService.disburse(
            vendor=vendor, amount=amount, source_type='AP_DOWNPAYMENT',
            source_id=None, reference=f'DP-TEST-{amount}',
            posting_date=date.today(), actor=actor,
            bank_account=bank_account, notes='pytest advance',
            deductions=deductions,
        )

    def test_journal_balances_gross_and_pays_net(
        self, advance_recon_account, wht_liability_account,
        bank_account_for_batch, batch_vendor, superuser, open_fiscal_period,
    ):
        # Arrange — ₦100,000 advance, ₦10,000 WHT withheld.
        deductions = [{
            'account': wht_liability_account, 'amount': Decimal('10000.00'),
            'memo': 'WHT',
        }]

        # Act
        adv = self._disburse(
            vendor=batch_vendor, bank_account=bank_account_for_batch,
            actor=superuser, amount=Decimal('100000.00'), deductions=deductions,
        )

        # Assert — advance recognised at GROSS, journal balanced, cash NET.
        assert adv.amount_paid == Decimal('100000.00')
        j = adv.disbursement_journal
        dr = sum((l.debit or 0) for l in j.lines.all())
        cr = sum((l.credit or 0) for l in j.lines.all())
        assert dr == cr == Decimal('100000.00')
        recon_dr = next(l for l in j.lines.all() if l.account_id == advance_recon_account.id)
        wht_cr = next(l for l in j.lines.all() if l.account_id == wht_liability_account.id)
        cash_cr = next(l for l in j.lines.all() if l.account_id == bank_account_for_batch.gl_account_id)
        assert recon_dr.debit == Decimal('100000.00')
        assert wht_cr.credit == Decimal('10000.00')
        assert cash_cr.credit == Decimal('90000.00')   # net of the WHT

    def test_rejects_deductions_at_or_above_gross(
        self, advance_recon_account, wht_liability_account,
        bank_account_for_batch, batch_vendor, superuser, open_fiscal_period,
    ):
        from accounting.services.base_posting import TransactionPostingError
        deductions = [{
            'account': wht_liability_account, 'amount': Decimal('100000.00'),
            'memo': 'over',
        }]
        with pytest.raises(TransactionPostingError):
            self._disburse(
                vendor=batch_vendor, bank_account=bank_account_for_batch,
                actor=superuser, amount=Decimal('100000.00'), deductions=deductions,
            )
