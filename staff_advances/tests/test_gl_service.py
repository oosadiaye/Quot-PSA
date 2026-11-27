"""The ledger legs of a staff advance: disburse, recover, retire. Pins what the journals are, not just that they exist."""
from decimal import Decimal

import pytest

from django.core.exceptions import ValidationError

from accounting.models import Account, JournalLine
from accounting.services.base_posting import TransactionPostingError
from staff_advances.models import ImprestAccount, ImprestRetirement, StaffAdvance
from staff_advances.services import StaffAdvanceGLService

pytestmark = pytest.mark.django_db(transaction=True)
D = Decimal


@pytest.fixture
def advance(employee, gl):
    return StaffAdvance.objects.create(
        employee=employee, recon_account=gl.recon, amount=D("1000.00"), purpose="travel", reference="ADV-T-1")


def _legs(journal):
    return {l.account.code: (l.debit, l.credit) for l in JournalLine.objects.filter(header=journal)}


def test_disbursing_debits_the_recon_account_and_credits_cash(advance, gl, actor, open_fiscal_period):
    journal = StaffAdvanceGLService.disburse(staff_advance=advance, actor=actor, bank_account=gl.bank)
    legs = _legs(journal)
    assert legs[gl.recon.code] == (D("1000.00"), D("0"))
    assert legs[gl.cash.code] == (D("0"), D("1000.00"))
    advance.refresh_from_db()
    assert advance.journal_id == journal.pk and advance.status == "OUTSTANDING"


def test_an_advance_cannot_be_disbursed_twice(advance, gl, actor, open_fiscal_period):
    StaffAdvanceGLService.disburse(staff_advance=advance, actor=actor, bank_account=gl.bank)
    with pytest.raises(TransactionPostingError):
        StaffAdvanceGLService.disburse(staff_advance=advance, actor=actor, bank_account=gl.bank)


def test_recovery_debits_expense_credits_recon_and_rolls_the_status(advance, gl, actor, open_fiscal_period):
    StaffAdvanceGLService.disburse(staff_advance=advance, actor=actor, bank_account=gl.bank)
    journal = StaffAdvanceGLService.record_recovery(
        staff_advance=advance, amount=D("400.00"), actor=actor, expense_account=gl.expense)
    assert _legs(journal) == {gl.expense.code: (D("400.00"), D("0")), gl.recon.code: (D("0"), D("400.00"))}
    advance.refresh_from_db()
    assert (advance.recovered_amount, advance.status) == (D("400.00"), "PARTIAL")
    StaffAdvanceGLService.record_recovery(staff_advance=advance, amount=D("600.00"), actor=actor, expense_account=gl.expense)
    advance.refresh_from_db()
    assert (advance.recovered_amount, advance.status) == (D("1000.00"), "CLEARED")


def test_cannot_recover_more_than_is_outstanding_or_before_disbursing(advance, gl, actor, open_fiscal_period):
    with pytest.raises(TransactionPostingError):          # never disbursed
        StaffAdvanceGLService.record_recovery(staff_advance=advance, amount=D("1"), actor=actor, expense_account=gl.expense)
    StaffAdvanceGLService.disburse(staff_advance=advance, actor=actor, bank_account=gl.bank)
    with pytest.raises(TransactionPostingError):          # more than the 1000 outstanding
        StaffAdvanceGLService.record_recovery(staff_advance=advance, amount=D("1000.01"), actor=actor, expense_account=gl.expense)


def test_retiring_an_imprest_posts_once_and_raises_the_retired_total(employee, gl, actor, open_fiscal_period):
    imprest = ImprestAccount.objects.create(employee=employee, reference="IMP-1", issued_amount=D("500.00"))
    retirement = ImprestRetirement.objects.create(imprest=imprest, amount=D("120.00"))
    journal = StaffAdvanceGLService.retire_imprest(retirement=retirement, actor=actor, expense_account=gl.expense)
    assert _legs(journal) == {gl.expense.code: (D("120.00"), D("0")), gl.recon.code: (D("0"), D("120.00"))}
    imprest.refresh_from_db()
    assert imprest.retired_amount == D("120.00")
    with pytest.raises(TransactionPostingError):
        StaffAdvanceGLService.retire_imprest(retirement=retirement, actor=actor, expense_account=gl.expense)


def test_recovering_into_a_strictly_controlled_expense_line_needs_an_appropriation(advance, gl, actor, open_fiscal_period):
    """Charging an advance to expenditure is spending: budget control applies to it exactly as it does to any journal."""
    StaffAdvanceGLService.disburse(staff_advance=advance, actor=actor, bank_account=gl.bank)
    strict, _ = Account.objects.update_or_create(
        code="22900100", defaults=dict(name="Advances Strict Expense", account_type="Expense", is_active=True))
    with pytest.raises(ValidationError, match="Budget check failed"):
        StaffAdvanceGLService.record_recovery(staff_advance=advance, amount=D("10.00"), actor=actor, expense_account=strict)
    advance.refresh_from_db()
    assert advance.recovered_amount == D("0")             # the refused journal left no trace on the advance
