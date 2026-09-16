"""Inter-TSA transfer, exercised against a real database.

The existing transfer tests mock the TreasuryAccounts with SimpleNamespace,
so ``process_transfer`` never ran against Postgres — and two bugs hid there
until a real transfer 500'd:

  * ``select_for_update().select_related('gl_cash_account')`` over a nullable
    FK is a lock on the nullable side of an outer join, which Postgres
    refuses ("FOR UPDATE cannot be applied to the nullable side of an outer
    join"). Every transfer failed.
  * ``JournalHeader.mda`` was handed the TSA's AdministrativeSegment instead
    of its legacy MDA.

These run the service end to end so a regression in either resurfaces as a
red test rather than a production 500.

``transaction=True`` and uuid-unique accounts, as the other journal-posting
tests here.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def two_tsas(db, open_fiscal_period):
    from accounting.models.gl import Account
    from accounting.models.treasury import TreasuryAccount

    def _make(suffix, balance):
        tok = uuid.uuid4().hex[:8]
        cash = Account.objects.create(
            code=f'ZX{tok}', name=f'CASH: Transfer {suffix} {tok}', account_type='Asset',
        )
        return TreasuryAccount.objects.create(
            account_number=f'TSA-X-{tok}', account_name=f'Transfer {suffix}',
            bank='Test Bank', account_type='CONSOLIDATED',
            gl_cash_account=cash, current_balance=Decimal(balance),
        )

    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.filter(is_superuser=True).first() or User.objects.create_superuser(
        username='xfer-tester', email='x@example.com', password='x',
    )
    return _make('src', '20000.00'), _make('tgt', '0.00'), user


def _transfer(src, tgt, amount, user, narration='test'):
    from accounting.services.treasury_service import TSABalanceService
    return TSABalanceService.process_transfer(
        source_tsa=src, target_tsa=tgt, amount=Decimal(amount),
        actor=user, narration=narration,
    )


def test_transfer_succeeds_against_the_database(two_tsas):
    """The bug, stated directly: this used to raise NotSupportedError."""
    src, tgt, user = two_tsas
    jv = _transfer(src, tgt, '5000.00', user)
    jv.refresh_from_db()
    assert jv.status == 'Posted'


def test_transfer_debits_target_cash_and_credits_source_cash(two_tsas):
    from accounting.models.gl import JournalLine
    src, tgt, user = two_tsas
    jv = _transfer(src, tgt, '5000.00', user)

    lines = {jl.account_id: (jl.debit, jl.credit) for jl in JournalLine.objects.filter(header=jv)}
    assert lines[tgt.gl_cash_account_id] == (Decimal('5000.00'), Decimal('0'))  # DR target
    assert lines[src.gl_cash_account_id] == (Decimal('0'), Decimal('5000.00'))  # CR source


def test_transfer_moves_both_balances(two_tsas):
    src, tgt, user = two_tsas
    _transfer(src, tgt, '5000.00', user)
    src.refresh_from_db(); tgt.refresh_from_db()
    assert src.current_balance == Decimal('15000.00')
    assert tgt.current_balance == Decimal('5000.00')


def test_transfer_reference_is_not_double_prefixed(two_tsas):
    src, tgt, user = two_tsas
    jv = _transfer(src, tgt, '100.00', user)
    assert jv.reference_number.startswith('TT-')
    assert not jv.reference_number.startswith('TT-TT-')


def test_transfer_beyond_balance_is_refused(two_tsas):
    src, tgt, user = two_tsas
    with pytest.raises(ValueError, match='Insufficient funds'):
        _transfer(src, tgt, '999999.00', user)
