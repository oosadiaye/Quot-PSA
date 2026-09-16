"""The TSA ledger itemises GL cash movements, not just documents.

A TSA account's balance can move through GL journals that carry no
RevenueCollection or PaymentInstruction — vendor registration fees,
advance disbursements, inter-TSA transfers, sweeps. The ledger read only
those two document sources, so a balance built entirely from journals
(as one Zenith Bank TSA's ₦10,000 was, from a single vendor-registration
entry) itemised to nothing: a balance with no line explaining it.

These pin that the GL cash-account movements now appear, that a debit to
the cash account reads as an inflow (and a credit as an outflow), that
revenue/payment twins are not double-counted, and that a current_balance
which disagrees with the GL is reported rather than hidden.

``transaction=True`` throughout, as every other journal-posting test in
this suite — plain ``django_db`` does not survive the tenant-schema
routing's teardown. Because committed rows are not rolled back, each test
builds its own cash account and TSA (unique per call) so one test's
journals never leak into another's GL balance.
"""
from __future__ import annotations

import itertools
from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate


pytestmark = pytest.mark.django_db(transaction=True)

# Committed rows persist between transaction=True tests, so every test
# gets its own account codes off this counter — no cross-test bleed.
_seq = itertools.count(1)


@pytest.fixture
def tsa_with_journal(db):
    from accounting.models.gl import Account, JournalHeader, JournalLine
    from accounting.models.treasury import TreasuryAccount

    n = next(_seq)
    cash = Account.objects.create(
        code=f'ZZTSA{n:05d}', name=f'CASH: Ledger Test {n}', account_type='Asset',
    )
    acct = TreasuryAccount.objects.create(
        account_number=f'TSA-LEDGER-TEST-{n}',
        account_name='Ledger Test TSA',
        bank='Test Bank',
        account_type='CONSOLIDATED',
        gl_cash_account=cash,
        current_balance=Decimal('10000.00'),
    )

    def _post(source_module, *, debit, credit, desc, ref, day=date(2026, 4, 28)):
        h = JournalHeader.objects.create(
            status='Posted', source_module=source_module,
            posting_date=day, description=desc, reference_number=f'{ref}-{n}',
        )
        JournalLine.objects.create(header=h, account=cash, debit=debit, credit=credit)
        return h

    return acct, _post


def _ledger(acct):
    from accounting.views.treasury_revenue import TreasuryAccountViewSet
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.filter(is_superuser=True).first()
    if user is None:
        user = User.objects.create_superuser(
            username='tsa-ledger-tester', email='t@example.com', password='x',
        )
    req = APIRequestFactory().get(f'/treasury-accounts/{acct.pk}/ledger/')
    force_authenticate(req, user=user)
    resp = TreasuryAccountViewSet.as_view({'get': 'ledger'})(req, pk=acct.pk)
    assert resp.status_code == 200, resp.data
    return resp.data


def test_a_gl_cash_movement_appears_in_the_ledger(tsa_with_journal):
    """The bug, stated directly: a journal credit to cash used to show nothing."""
    acct, post = tsa_with_journal
    post('vendor_registration', debit=Decimal('10000.00'), credit=Decimal('0'),
         desc='Vendor Registration: Jacob PLC', ref='JE-TEST-1')

    data = _ledger(acct)

    journal_rows = [e for e in data['entries'] if e['source'] == 'JOURNAL']
    assert journal_rows, 'the GL cash movement did not appear in the ledger'
    # A debit to a cash (asset) account is money IN -> ledger credit column.
    assert Decimal(journal_rows[0]['credit']) == Decimal('10000.00')
    assert Decimal(journal_rows[0]['debit']) == Decimal('0')


def test_a_cash_credit_reads_as_an_outflow(tsa_with_journal):
    acct, post = tsa_with_journal
    post('vendor_advance', debit=Decimal('0'), credit=Decimal('4000.00'),
         desc='Advance disbursement', ref='ADV-1')

    row = next(e for e in _ledger(acct)['entries'] if e['source'] == 'JOURNAL')
    # A credit to cash is money OUT -> ledger debit column.
    assert Decimal(row['debit']) == Decimal('4000.00')
    assert Decimal(row['credit']) == Decimal('0')


def test_revenue_journal_is_not_double_counted(tsa_with_journal):
    """Revenue/payment GL twins are excluded — RevenueCollection shows them,
    so adding the GL line too would count the same money twice."""
    acct, post = tsa_with_journal
    post('revenue', debit=Decimal('5000.00'), credit=Decimal('0'),
         desc='Revenue GL twin', ref='REV-1')

    data = _ledger(acct)
    assert not [e for e in data['entries'] if e['source'] == 'JOURNAL'], (
        'a revenue-sourced journal was added as a JOURNAL entry, double-counting '
        'the RevenueCollection view'
    )


def test_a_drifted_current_balance_is_reported(tsa_with_journal):
    """current_balance 10,000 but GL nets to -4,000 -> flagged, not hidden."""
    acct, post = tsa_with_journal
    post('vendor_advance', debit=Decimal('0'), credit=Decimal('4000.00'),
         desc='Advance', ref='ADV-2')

    data = _ledger(acct)
    assert data['balance_reconciled'] is False
    assert Decimal(data['gl_cash_balance']) == Decimal('-4000.00')
    # discrepancy = current_balance - gl = 10,000 - (-4,000) = 14,000
    assert Decimal(data['balance_discrepancy']) == Decimal('14000.00')


def test_reconciled_when_balance_matches_the_gl(tsa_with_journal):
    acct, post = tsa_with_journal
    # A single 10,000 debit (inflow) -> GL net = 10,000 = current_balance.
    post('vendor_registration', debit=Decimal('10000.00'), credit=Decimal('0'),
         desc='Vendor Registration', ref='JE-2')

    data = _ledger(acct)
    assert data['balance_reconciled'] is True
    assert Decimal(data['gl_cash_balance']) == Decimal('10000.00')
