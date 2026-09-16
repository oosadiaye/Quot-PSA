"""current_balance is a cache of the GL cash account, and reconciles to it.

Some posting paths (vendor advances) credited a TSA cash GL account
without updating the denormalised ``current_balance``, so the stored
figure drifted from the double-entry truth. ``reconcile_balance`` rebuilds
it from the GL — the repair behind the ``reconcile_tsa_balances`` command
and the auto-resync now wired into the advance path.

``transaction=True`` and per-test unique accounts, as the other
journal-posting tests here.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def drifted_tsa(db):
    """A TSA whose stored balance disagrees with its GL cash account."""
    from accounting.models.gl import Account, JournalHeader, JournalLine
    from accounting.models.treasury import TreasuryAccount

    tok = uuid.uuid4().hex[:8]
    cash = Account.objects.create(
        code=f'Z{tok}R', name=f'CASH: Recon {tok}', account_type='Asset',
    )
    # GL: DR 8,000 in, CR 3,000 out -> net 5,000.
    for dr, cr in ((Decimal('8000.00'), Decimal('0')), (Decimal('0'), Decimal('3000.00'))):
        h = JournalHeader.objects.create(
            status='Posted', source_module='vendor_advance',
            posting_date=date(2026, 4, 28), description='recon test',
        )
        JournalLine.objects.create(header=h, account=cash, debit=dr, credit=cr)

    # Stored balance is deliberately wrong (as if a path skipped the update).
    tsa = TreasuryAccount.objects.create(
        account_number=f'TSA-R-{tok}', account_name='Recon Test TSA',
        bank='Test Bank', account_type='CONSOLIDATED',
        gl_cash_account=cash, current_balance=Decimal('99999.00'),
    )
    return tsa


def test_gl_cash_balance_nets_debits_minus_credits(drifted_tsa):
    from accounting.services.treasury_service import TSABalanceService
    assert TSABalanceService.gl_cash_balance(drifted_tsa) == Decimal('5000.00')


def test_reconcile_sets_stored_balance_to_the_gl_net(drifted_tsa):
    from accounting.services.treasury_service import TSABalanceService
    TSABalanceService.reconcile_balance(drifted_tsa)
    drifted_tsa.refresh_from_db()
    assert drifted_tsa.current_balance == Decimal('5000.00')


def test_reconcile_is_idempotent(drifted_tsa):
    from accounting.services.treasury_service import TSABalanceService
    TSABalanceService.reconcile_balance(drifted_tsa)
    TSABalanceService.reconcile_balance(drifted_tsa)
    drifted_tsa.refresh_from_db()
    assert drifted_tsa.current_balance == Decimal('5000.00')


def test_dry_run_reports_but_does_not_write(drifted_tsa):
    from accounting.services.treasury_service import TSABalanceService
    results = TSABalanceService.reconcile_all(dry_run=True)
    mine = [(t, b, a) for (t, b, a) in results if t.pk == drifted_tsa.pk]
    assert mine, 'the drifted TSA was not in the dry-run report'
    _, before, after = mine[0]
    assert before == Decimal('99999.00') and after == Decimal('5000.00')
    drifted_tsa.refresh_from_db()
    assert drifted_tsa.current_balance == Decimal('99999.00')  # unchanged


def test_reconcile_from_gl_account_fixes_every_tsa_on_it(drifted_tsa):
    from accounting.services.treasury_service import TSABalanceService
    TSABalanceService.reconcile_from_gl_account(drifted_tsa.gl_cash_account)
    drifted_tsa.refresh_from_db()
    assert drifted_tsa.current_balance == Decimal('5000.00')
