"""
Debt-service GL posting.

``FUTURE_MODULES.md`` §3 requires an activation-cycle test per module and
this module shipped without one, so 197 lines that write journals into a
statutory ledger had no coverage at all.

What is worth pinning here is not that a row appears. It is:

  * the journal **balances**, and its total equals principal + interest +
    fees rather than any one of them;
  * a coupon cannot be paid **twice**, by either of the two routes the
    service guards against;
  * a missing GL configuration **refuses** rather than posting a
    half-entry or guessing an account;
  * disabling the module afterwards leaves the posted journal **intact**,
    which is invariant 2 in §3: "A toggle never rewrites the general
    ledger."

That last one is the reason this module is gated at all, and it was the
only invariant with no test behind it.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services.base_posting import TransactionPostingError
from debt.models import (
    AmortisationCoupon,
    AmortisationLedger,
    AmortisationSchedule,
    DebtInstrument,
)
from debt.services import DebtServiceGLService

ZERO = Decimal("0")


@pytest.mark.django_db
class TestDebtServiceGL:
    """Every test drives DebtServiceGLService.pay_coupon.

    Plain pytest rather than TenantTestCase: see conftest.py -
    auto_create_schema is False in this project, so the tenant test
    cases never materialise the tenant tables.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, db, open_fiscal_period):
        # post_journal refuses a date with no open period, so every
        # posting test needs one or it fails on the gate instead of
        # on the thing it is checking.
        self.actor = User.objects.create_user(
            username="debt_officer", password="x", email="d@example.com",
        )
        # Tagged accounts: the service prefers reconciliation_type over the
        # DEFAULT_GL_ACCOUNTS fallback, so tagging is the narrower setup.
        self.expense = Account.objects.create(
            code="5300100", name="Debt Service Expense",
            account_type="Expense", reconciliation_type="debt_service_expense",
            is_active=True,
        )
        self.payable = Account.objects.create(
            code="2300100", name="Debt Service Payable",
            account_type="Liability", reconciliation_type="debt_service",
            is_active=True,
        )
        self.instrument = DebtInstrument.objects.create(
            instrument_number="LN-2026-001",
            creditor="World Bank",
            principal_amount=Decimal("1000000.00"),
        )
        self.schedule = AmortisationSchedule.objects.create(
            instrument=self.instrument, coupon_date="2026-06-30",
        )

    def _coupon(self, principal="0", interest="0", fees="0"):
        return AmortisationCoupon.objects.create(
            schedule=self.schedule,
            principal_amount=Decimal(principal),
            interest_amount=Decimal(interest),
            commitment_fee=Decimal(fees),
        )

    # ── the balance invariant ────────────────────────────────────────

    def test_journal_balances_and_totals_all_three_components(self):
        # A coupon is principal + interest + fees. Posting only one of
        # them, or two, still produces a balanced journal - which is why
        # "it balances" alone is not a sufficient assertion.
        coupon = self._coupon(principal="800.00", interest="150.50", fees="49.50")

        journal = DebtServiceGLService.pay_coupon(coupon=coupon, actor=self.actor)

        lines = JournalLine.objects.filter(header=journal)
        assert lines.count() == 2
        total_dr = sum(l.debit for l in lines)
        total_cr = sum(l.credit for l in lines)
        assert total_dr == total_cr, "journal does not balance"
        assert total_dr == Decimal("1000.00")

    def test_debit_is_the_expense_and_credit_is_the_payable(self):
        # Reversing the legs would still balance and still total
        # correctly, while making the expense a credit - so the sides
        # need pinning independently of the amount.
        coupon = self._coupon(principal="500.00")

        journal = DebtServiceGLService.pay_coupon(coupon=coupon, actor=self.actor)

        debit = JournalLine.objects.get(header=journal, debit__gt=ZERO)
        credit = JournalLine.objects.get(header=journal, credit__gt=ZERO)
        assert debit.account_id == self.expense.id
        assert credit.account_id == self.payable.id

    def test_interest_only_coupon_posts_interest_only(self):
        coupon = self._coupon(interest="275.25")
        journal = DebtServiceGLService.pay_coupon(coupon=coupon, actor=self.actor)
        total = sum(l.debit for l in JournalLine.objects.filter(header=journal))
        assert total == Decimal("275.25")

    # ── the double-post guards ───────────────────────────────────────

    def test_a_paid_coupon_is_refused(self):
        coupon = self._coupon(principal="100.00")
        DebtServiceGLService.pay_coupon(coupon=coupon, actor=self.actor)
        coupon.refresh_from_db()

        with pytest.raises(TransactionPostingError):
            DebtServiceGLService.pay_coupon(coupon=coupon, actor=self.actor)

    def test_a_paid_ledger_event_is_refused_even_if_status_was_reset(self):
        # The second guard exists because status is a field somebody can
        # edit. The ledger row is the durable record of having posted.
        coupon = self._coupon(principal="100.00")
        DebtServiceGLService.pay_coupon(coupon=coupon, actor=self.actor)

        AmortisationCoupon.objects.filter(pk=coupon.pk).update(status="due")
        coupon.refresh_from_db()
        assert AmortisationLedger.objects.filter(
            coupon=coupon, event="paid",
        ).exists()

        with pytest.raises(TransactionPostingError):
            DebtServiceGLService.pay_coupon(coupon=coupon, actor=self.actor)

    def test_a_refused_second_attempt_posts_no_extra_journal(self):
        # The guard raising is not the point; the point is that the
        # ledger is unchanged afterwards.
        coupon = self._coupon(principal="100.00")
        DebtServiceGLService.pay_coupon(coupon=coupon, actor=self.actor)
        before = JournalHeader.objects.count()

        with pytest.raises(TransactionPostingError):
            DebtServiceGLService.pay_coupon(coupon=coupon, actor=self.actor)

        assert JournalHeader.objects.count() == before

    # ── refusals rather than guesses ─────────────────────────────────

    def test_a_zero_coupon_is_refused(self):
        with pytest.raises(TransactionPostingError):
            DebtServiceGLService.pay_coupon(coupon=self._coupon(), actor=self.actor)

    def test_missing_expense_gl_refuses_without_posting(self):
        # Guessing an account here would put debt service somewhere
        # nobody reconciles.
        #
        # Deactivating is NOT enough to simulate 'unconfigured'.
        # resolve_expense_account falls back to get_gl_account, whose
        # name search filters on account_type and name only - no
        # is_active check - so a deactivated 'Debt Service Expense'
        # is still found. Both routes have to be closed here: the
        # reconciliation tag and the name the fallback matches on.
        Account.objects.filter(pk=self.expense.pk).update(
            is_active=False, reconciliation_type="", name="Unrelated Expense",
        )
        coupon = self._coupon(principal="100.00")
        before = JournalHeader.objects.count()

        with pytest.raises(TransactionPostingError):
            DebtServiceGLService.pay_coupon(coupon=coupon, actor=self.actor)

        assert JournalHeader.objects.count() == before

    def test_missing_payable_gl_refuses_without_posting(self):
        # The credit leg is resolved after the debit leg, so this also
        # proves the failure does not leave a one-sided journal behind.
        # Same two routes to close as the expense case above.
        Account.objects.filter(pk=self.payable.pk).update(
            is_active=False, reconciliation_type="", name="Unrelated Liability",
        )
        coupon = self._coupon(principal="100.00")
        before = JournalHeader.objects.count()

        with pytest.raises(TransactionPostingError):
            DebtServiceGLService.pay_coupon(coupon=coupon, actor=self.actor)

        assert JournalHeader.objects.count() == before
        assert (JournalLine.objects.filter(header__isnull=False).count()
                == JournalLine.objects.count())

    # ── §3 invariant 2: a toggle never rewrites the ledger ───────────

    def test_disabling_the_module_leaves_the_posted_journal_intact(self):
        # "Journals posted while a module was active remain posted - they
        # are part of the statutory accounts and an Accountant-General has
        # signed statements built on them." (FUTURE_MODULES §3)
        from core.models import TenantModule

        coupon = self._coupon(principal="750.00", interest="250.00")
        journal = DebtServiceGLService.pay_coupon(coupon=coupon, actor=self.actor)
        journal_id = journal.pk

        TenantModule.objects.update_or_create(
            module_name="debt",
            defaults={"module_title": "Public Debt", "is_active": False},
        )

        surviving = JournalHeader.objects.filter(pk=journal_id).first()
        assert surviving is not None, "disabling the module removed a journal"
        lines = JournalLine.objects.filter(header_id=journal_id)
        assert lines.count() == 2
        assert sum(l.debit for l in lines) == Decimal("1000.00")
        assert sum(l.debit for l in lines) == sum(l.credit for l in lines)
