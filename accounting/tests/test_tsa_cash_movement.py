"""Every TSA cash movement posts to the GL — a cash-book entry cannot drift.

``record_cash_movement`` is the manual side of "all postings to a TSA
account must post to a GL account": an incoming or outgoing amount whose
other leg the operator chooses, posted as a balanced JV to the TSA's GL
cash account plus that contra. Because it goes through
``IPSASJournalService.post_journal`` and updates ``current_balance`` under
the same lock, the GL, the stored balance, and the ledger move together —
there is no path here that touches one without the other.

``transaction=True`` and per-test unique accounts, as the other
journal-posting tests in this suite.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def tsa_and_contra(db, open_fiscal_period):
    # open_fiscal_period (from accounting/tests/conftest.py) covers today, so
    # post_journal's period gate is satisfied — cash movements post with the
    # current date by default.
    from accounting.models.gl import Account
    from accounting.models.treasury import TreasuryAccount
    from django.contrib.auth import get_user_model

    # Globally-unique ids: with transaction=True + --reuse-db, accounting_
    # account is NOT flushed between runs, so a per-run counter collides on
    # re-run. A uuid token never does.
    tok = uuid.uuid4().hex[:8]
    cash = Account.objects.create(
        code=f'Z{tok}C', name=f'CASH: CB Test {tok}', account_type='Asset',
    )
    contra = Account.objects.create(
        code=f'Z{tok}X', name=f'Contra: CB Test {tok}', account_type='Expense',
    )
    tsa = TreasuryAccount.objects.create(
        account_number=f'TSA-{tok}', account_name='CB Test TSA',
        bank='Test Bank', account_type='CONSOLIDATED',
        gl_cash_account=cash, current_balance=Decimal('20000.00'),
    )
    User = get_user_model()
    user = User.objects.filter(is_superuser=True).first() or User.objects.create_superuser(
        username='cb-tester', email='cb@example.com', password='x',
    )
    return tsa, cash, contra, user


def _record(tsa, direction, amount, contra, user):
    from accounting.services.treasury_service import TSABalanceService
    return TSABalanceService.record_cash_movement(
        tsa=tsa, direction=direction, amount=Decimal(amount),
        contra_account=contra, actor=user, narration='test',
    )


def _lines(journal):
    from accounting.models.gl import JournalLine
    return {
        jl.account_id: (jl.debit, jl.credit)
        for jl in JournalLine.objects.filter(header=journal)
    }


def test_incoming_debits_cash_and_credits_contra(tsa_and_contra):
    tsa, cash, contra, user = tsa_and_contra
    jv = _record(tsa, 'IN', '5000.00', contra, user)

    lines = _lines(jv)
    assert lines[cash.pk] == (Decimal('5000.00'), Decimal('0'))    # DR cash
    assert lines[contra.pk] == (Decimal('0'), Decimal('5000.00'))  # CR contra
    tsa.refresh_from_db()
    assert tsa.current_balance == Decimal('25000.00')


def test_outgoing_credits_cash_and_debits_contra(tsa_and_contra):
    tsa, cash, contra, user = tsa_and_contra
    jv = _record(tsa, 'OUT', '5000.00', contra, user)

    lines = _lines(jv)
    assert lines[cash.pk] == (Decimal('0'), Decimal('5000.00'))    # CR cash
    assert lines[contra.pk] == (Decimal('5000.00'), Decimal('0'))  # DR contra
    tsa.refresh_from_db()
    assert tsa.current_balance == Decimal('15000.00')


def test_the_posting_reaches_the_gl_cash_account(tsa_and_contra):
    """The whole point — a TSA movement that does not touch the GL is the
    exact failure that let current_balance drift."""
    tsa, cash, contra, user = tsa_and_contra
    jv = _record(tsa, 'IN', '1000.00', contra, user)
    jv.refresh_from_db()
    assert jv.status == 'Posted'
    assert cash.pk in _lines(jv), 'the cash GL account was not posted to'


def test_outgoing_beyond_balance_is_refused(tsa_and_contra):
    tsa, cash, contra, user = tsa_and_contra
    with pytest.raises(ValueError, match='Insufficient funds'):
        _record(tsa, 'OUT', '999999.00', contra, user)


def test_contra_must_differ_from_cash(tsa_and_contra):
    tsa, cash, contra, user = tsa_and_contra
    with pytest.raises(ValueError, match='contra account must differ'):
        _record(tsa, 'IN', '1000.00', cash, user)


def test_bad_direction_is_refused(tsa_and_contra):
    tsa, cash, contra, user = tsa_and_contra
    with pytest.raises(ValueError, match="'IN'.*'OUT'"):
        _record(tsa, 'SIDEWAYS', '1000.00', contra, user)


def test_non_positive_amount_is_refused(tsa_and_contra):
    tsa, cash, contra, user = tsa_and_contra
    with pytest.raises(ValueError, match='greater than zero'):
        _record(tsa, 'IN', '0', contra, user)
