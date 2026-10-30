"""Debt on the general ledger: chart of accounts, bank accounts, and the non-current / current liability split.

Posting writes journals, so these run with ``transaction=True`` (the balance trigger reads the tenant schema). Account codes
used for posting are seven digits, outside the 8-digit strict budget ranges, so the tests exercise the debt accounting and
not the appropriation gate (which has its own tests).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account, BankAccount, FiscalPeriod, JournalLine
from accounting.services.base_posting import TransactionPostingError
from debt import gl
from debt.models import AmortisationCoupon, AmortisationSchedule, DebtClassification, DebtInstrument
from debt.services import DebtServiceGLService

D = Decimal
pytestmark = pytest.mark.django_db(transaction=True)


def _account(code, name, kind):
    acct, _ = Account.objects.get_or_create(code=code, defaults={"name": name, "account_type": kind})
    if not acct.is_active or not acct.is_postable:
        acct.is_active, acct.is_postable = True, True
        acct.save(update_fields=["is_active", "is_postable"])
    return acct


@pytest.fixture(autouse=True)
def open_period(db):
    today = date.today()
    # today, tomorrow, and the date 400 days ahead that the "later classification" test posts on
    for when in (today, today + timedelta(days=1), today + timedelta(days=400)):
        FiscalPeriod.objects.get_or_create(
            fiscal_year=when.year, period_number=when.month, period_type="Monthly",
            defaults={"start_date": when.replace(day=1), "end_date": when, "status": "Open", "is_closed": False},
        )


@pytest.fixture
def world(db):
    actor = User.objects.create_user(username=f"debt_gl_{User.objects.count()}", password="x", email="d@example.com")
    noncurrent = _account("4200199", "Long-term Borrowings (test)", "Liability")
    current = _account("4140199", "Current Portion (test)", "Liability")
    interest = _account("5410199", "Loan Interest (test)", "Expense")
    bank_gl = _account("3110199", "Cash at Bank (test)", "Asset")
    bank = BankAccount.objects.create(name="Debt Test Bank", account_number=f"DT-{BankAccount.objects.count()}", account_type="Bank",
                                      gl_account=bank_gl, opening_balance=D("0.00"), currency=None)
    instrument = DebtInstrument.objects.create(
        instrument_number=f"LN-{DebtInstrument.objects.count() + 1:04d}-GL", creditor="World Bank", principal_amount=D("1200000.00"),
        liability_account=noncurrent, current_portion_account=current, interest_expense_account=interest, bank_account=bank)
    return type("World", (), dict(actor=actor, noncurrent=noncurrent, current=current, interest=interest, bank_gl=bank_gl,
                                  bank=bank, instrument=instrument))


def coupon(instrument, due, principal="0", interest="0", fees="0"):
    schedule = AmortisationSchedule.objects.create(instrument=instrument, coupon_date=due)
    return AmortisationCoupon.objects.create(
        schedule=schedule, principal_amount=D(principal), interest_amount=D(interest), commitment_fee=D(fees))


def lines_of(journal):
    """{(account code, Dr/Cr): amount}, summing lines that share an account and a side."""
    out = {}
    for l in JournalLine.objects.filter(header=journal):
        key = (l.account.code, "Dr" if l.debit else "Cr")
        out[key] = out.get(key, D("0")) + (l.debit or l.credit)
    return out


class TestStandardAccounts:
    def test_a_loan_maps_to_domestic_loans_a_bond_to_bonds_and_the_current_portion_account_is_made(self, world):
        _account("42100100", "Domestic Borrowings - Bonds", "Liability")
        _account("42100200", "Domestic Borrowings - Loans", "Liability")
        _account("41000000", "Current Liabilities", "Liability")
        _account("24100100", "Domestic Loan Interest", "Expense")
        loan = DebtInstrument.objects.create(instrument_number="STD-LOAN", creditor="A", principal_amount=D("100.00"))
        bond = DebtInstrument.objects.create(instrument_number="STD-BOND", creditor="B", principal_amount=D("100.00"), instrument_type="bond")
        assert gl.apply_standard_accounts(loan)["liability"] == "42100200"
        assert gl.apply_standard_accounts(bond)["liability"] == "42100100"
        loan.refresh_from_db()
        assert loan.current_portion_account.code == "41400100" and loan.interest_expense_account.code == "24100100"
        assert loan.current_portion_account.account_type == "Liability"

    def test_the_current_portion_account_gets_an_economic_segment_so_the_statement_can_see_it(self, world):
        _account("42100200", "Domestic Borrowings - Loans", "Liability")
        _account("24100100", "Domestic Loan Interest", "Expense")
        instrument = DebtInstrument.objects.create(instrument_number="STD-SEG", creditor="A", principal_amount=D("100.00"))
        gl.apply_standard_accounts(instrument)
        from accounting.models import EconomicSegment
        segment = EconomicSegment.objects.get(code="41400100")
        assert segment.is_posting_level and segment.legacy_account.code == "41400100"

    def test_a_chart_without_the_liability_account_is_explained(self, world):
        Account.objects.filter(code="42100200").update(is_active=False)
        instrument = DebtInstrument.objects.create(instrument_number="STD-NONE", creditor="A", principal_amount=D("100.00"))
        with pytest.raises(gl.DebtGLConfigError, match="42100200"):
            gl.apply_standard_accounts(instrument)
        Account.objects.filter(code="42100200").update(is_active=True)


class TestDrawdown:
    def test_money_received_debits_the_bank_and_credits_the_non_current_liability(self, world):
        drawdown = gl.record_drawdown(world.instrument, amount=D("500000.00"), actor=world.actor)
        assert lines_of(drawdown.journal) == {("3110199", "Dr"): D("500000.00"), ("4200199", "Cr"): D("500000.00")}
        world.bank.refresh_from_db()
        assert world.bank.current_balance == D("500000.00")
        world.instrument.refresh_from_db()
        assert world.instrument.status == "active" and world.instrument.outstanding_principal == D("500000.00")

    def test_it_cannot_draw_more_than_the_facility(self, world):
        gl.record_drawdown(world.instrument, amount=D("1000000.00"), actor=world.actor)
        with pytest.raises(gl.DebtGLConfigError, match="above the facility"):
            gl.record_drawdown(world.instrument, amount=D("200001.00"), actor=world.actor)
        assert world.instrument.drawdowns.count() == 1

    def test_an_unmapped_instrument_or_a_missing_bank_is_refused_with_what_to_do(self, world):
        bare = DebtInstrument.objects.create(instrument_number="BARE-1", creditor="A", principal_amount=D("100.00"))
        with pytest.raises(gl.DebtGLConfigError, match="non-current liability"):
            gl.record_drawdown(bare, amount=D("10.00"), actor=world.actor, bank_account=world.bank)
        world.instrument.bank_account = None
        world.instrument.save()
        with pytest.raises(gl.DebtGLConfigError, match="bank account"):
            gl.record_drawdown(world.instrument, amount=D("10.00"), actor=world.actor)

    def test_the_amount_must_be_positive(self, world):
        with pytest.raises(gl.DebtGLConfigError, match="greater than zero"):
            gl.record_drawdown(world.instrument, amount=D("0"), actor=world.actor)

    def test_a_bank_account_with_no_gl_account_is_refused(self, world):
        no_gl = BankAccount.objects.create(name="No GL", account_number="DT-NOGL", account_type="Bank", opening_balance=D("0"), currency=None)
        with pytest.raises(Exception):
            gl.record_drawdown(world.instrument, amount=D("10.00"), actor=world.actor, bank_account=no_gl)


class TestCurrentPortion:
    def _drawn(self, world, amount="1200000.00"):
        gl.record_drawdown(world.instrument, amount=D(amount), actor=world.actor)
        today = date.today()
        coupon(world.instrument, today + timedelta(days=90), principal="100000.00")
        coupon(world.instrument, today + timedelta(days=300), principal="100000.00")
        coupon(world.instrument, today + timedelta(days=700), principal="100000.00")        # beyond twelve months

    def test_principal_due_within_twelve_months_moves_to_current(self, world):
        self._drawn(world)
        row = gl.reclassify_current_portion(world.instrument, actor=world.actor)
        assert row.current_portion == D("200000.00") and row.adjustment == D("200000.00")
        assert lines_of(row.journal) == {("4200199", "Dr"): D("200000.00"), ("4140199", "Cr"): D("200000.00")}
        world.instrument.refresh_from_db()
        pos = gl.position(world.instrument)
        assert pos["current_portion"] == D("200000.00") and pos["non_current_portion"] == D("1000000.00")

    def test_it_is_done_once_per_date_and_does_nothing_when_nothing_changed(self, world):
        self._drawn(world)
        gl.reclassify_current_portion(world.instrument, actor=world.actor)
        with pytest.raises(gl.DebtGLConfigError, match="already classified"):
            gl.reclassify_current_portion(world.instrument, actor=world.actor)
        later = gl.reclassify_current_portion(world.instrument, as_of=date.today() + timedelta(days=1), actor=world.actor)
        assert later.adjustment == D("0.00") and later.journal is None

    def test_a_later_date_picks_up_the_next_instalment(self, world):
        self._drawn(world)
        gl.reclassify_current_portion(world.instrument, actor=world.actor)
        row = gl.reclassify_current_portion(world.instrument, as_of=date.today() + timedelta(days=400), actor=world.actor)
        # 400 days on, the 90- and 300-day coupons are still unpaid and the 700-day one has come within twelve months
        assert row.current_portion == D("300000.00") and row.adjustment == D("100000.00")
        assert DebtClassification.objects.filter(instrument=world.instrument).count() == 2

    def test_current_portion_never_exceeds_what_is_owed(self, world):
        self._drawn(world, amount="50000.00")
        row = gl.reclassify_current_portion(world.instrument, actor=world.actor)
        assert row.current_portion == D("50000.00")


class TestPayCoupon:
    def test_principal_comes_off_the_liability_interest_is_expense_and_the_bank_pays(self, world):
        gl.record_drawdown(world.instrument, amount=D("1000000.00"), actor=world.actor)
        due = coupon(world.instrument, date.today(), principal="100000.00", interest="25000.00", fees="500.00")
        gl.reclassify_current_portion(world.instrument, actor=world.actor)
        journal = DebtServiceGLService.pay_coupon(coupon=due, actor=world.actor)
        assert lines_of(journal) == {
            ("4140199", "Dr"): D("100000.00"),       # principal clears the current portion first
            ("5410199", "Dr"): D("25500.00"),        # interest and fees are the only expense
            ("3110199", "Cr"): D("125500.00"),
        }
        due.refresh_from_db()
        assert due.status == "paid" and due.journal_id == journal.pk and due.bank_account_id == world.bank.pk
        world.bank.refresh_from_db()
        assert world.bank.current_balance == D("1000000.00") - D("125500.00")
        world.instrument.refresh_from_db()
        assert world.instrument.current_portion_booked == D("0.00") and world.instrument.outstanding_principal == D("900000.00")

    def test_principal_not_yet_reclassified_comes_off_the_non_current_liability(self, world):
        gl.record_drawdown(world.instrument, amount=D("1000000.00"), actor=world.actor)
        due = coupon(world.instrument, date.today(), principal="40000.00")
        journal = DebtServiceGLService.pay_coupon(coupon=due, actor=world.actor)
        assert lines_of(journal) == {("4200199", "Dr"): D("40000.00"), ("3110199", "Cr"): D("40000.00")}

    def test_principal_splits_across_both_liabilities_when_only_part_is_current(self, world):
        gl.record_drawdown(world.instrument, amount=D("1000000.00"), actor=world.actor)
        coupon(world.instrument, date.today() + timedelta(days=30), principal="30000.00")
        gl.reclassify_current_portion(world.instrument, actor=world.actor)
        due = coupon(world.instrument, date.today(), principal="50000.00")
        journal = DebtServiceGLService.pay_coupon(coupon=due, actor=world.actor)
        assert lines_of(journal) == {("4140199", "Dr"): D("30000.00"), ("4200199", "Dr"): D("20000.00"), ("3110199", "Cr"): D("50000.00")}

    def test_a_coupon_is_paid_once(self, world):
        gl.record_drawdown(world.instrument, amount=D("1000000.00"), actor=world.actor)
        due = coupon(world.instrument, date.today(), principal="10000.00")
        DebtServiceGLService.pay_coupon(coupon=due, actor=world.actor)
        with pytest.raises(TransactionPostingError, match="already (paid|has a paid)"):
            DebtServiceGLService.pay_coupon(coupon=due, actor=world.actor)

    def test_it_cannot_repay_principal_that_was_never_drawn(self, world):
        due = coupon(world.instrument, date.today(), principal="10000.00")
        with pytest.raises(gl.DebtGLConfigError, match="outstanding"):
            DebtServiceGLService.pay_coupon(coupon=due, actor=world.actor, bank_account=world.bank)

    def test_the_bank_can_be_chosen_at_payment_time(self, world):
        other = BankAccount.objects.create(name="Other Bank", account_number="DT-OTHER", account_type="Bank", gl_account=world.bank_gl,
                                           opening_balance=D("0"), currency=None)
        gl.record_drawdown(world.instrument, amount=D("100000.00"), actor=world.actor)
        due = coupon(world.instrument, date.today(), principal="10000.00")
        DebtServiceGLService.pay_coupon(coupon=due, actor=world.actor, bank_account=other)
        other.refresh_from_db()
        assert other.current_balance == D("-10000.00")

    def test_an_instrument_with_no_mapping_keeps_the_older_behaviour(self, world):
        expense = _account("5300199", "Debt Service Expense (legacy)", "Expense")
        payable = _account("2300199", "Debt Service Payable (legacy)", "Liability")
        Account.objects.filter(pk=expense.pk).update(reconciliation_type="debt_service_expense")
        Account.objects.filter(pk=payable.pk).update(reconciliation_type="debt_service")
        legacy = DebtInstrument.objects.create(instrument_number="LEGACY-1", creditor="A", principal_amount=D("1000.00"))
        due = coupon(legacy, date.today(), principal="100.00", interest="10.00")
        journal = DebtServiceGLService.pay_coupon(coupon=due, actor=world.actor)
        assert {code for code, _ in lines_of(journal)} == {"5300199", "2300199"}


class TestStatementOfFinancialPosition:
    def test_the_non_current_and_current_liabilities_show_where_the_standard_accounts_put_them(self, world):
        from accounting.models import EconomicSegment
        from accounting.services.ipsas_reports import IPSASReportService

        parent_current = _account("41000000", "Current Liabilities", "Liability")
        parent_non = _account("42000000", "Non-Current Liabilities", "Liability")
        loans = _account("42100200", "Domestic Borrowings - Loans", "Liability")
        _account("24100100", "Domestic Loan Interest", "Expense")
        for acct, parent in ((parent_current, None), (parent_non, None)):
            EconomicSegment.objects.get_or_create(code=acct.code, defaults=dict(
                name=acct.name, account_type_code="4", is_active=True, is_posting_level=True, normal_balance="CREDIT",
                legacy_account=acct, legacy_account_type="Liability"))
        seg_parent = EconomicSegment.objects.get(code="42000000")
        seg_loans, _ = EconomicSegment.objects.get_or_create(code="42100200", defaults=dict(
            name=loans.name, account_type_code="4", parent=seg_parent, is_active=True, is_posting_level=True,
            normal_balance="CREDIT", legacy_account=loans, legacy_account_type="Liability"))
        if seg_loans.legacy_account_id != loans.pk:
            seg_loans.legacy_account = loans
            seg_loans.save()
        instrument = DebtInstrument.objects.create(instrument_number="SOFP-1", creditor="A", principal_amount=D("1000000.00"))
        gl.apply_standard_accounts(instrument)
        gl.record_drawdown(instrument, amount=D("1000000.00"), actor=world.actor, bank_account=world.bank)
        coupon(instrument, date.today() + timedelta(days=60), principal="150000.00")
        gl.reclassify_current_portion(instrument, actor=world.actor)

        sofp = IPSASReportService.statement_of_financial_position(date.today().year, comparative=False)["liabilities"]
        current_items = {i["code"]: i for i in sofp["current"]["items"] if i.get("code")}
        non_current_items = {i["code"]: i for i in sofp["non_current"]["items"] if i.get("code")}
        assert "41400100" in current_items, "the current portion is shown under current liabilities"
        assert D(str(current_items["41400100"]["amount"])) >= D("150000.00")
        assert "42100200" in non_current_items, "the long-term loan is shown under non-current liabilities"
