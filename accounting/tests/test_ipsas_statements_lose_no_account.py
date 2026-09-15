"""No account falls between the statements' headings.

The IPSAS statements aggregate a fixed list of two-digit sub-families:

    Statement of Financial Position     31, 32 assets
                                        41, 42 liabilities, 43 net assets
    Statement of Financial Performance  11-14 revenue, 21-25 expenditure

A chart is not obliged to stay inside that list. Real tenants here hold
30xxxxxx, 33xxxxxx, 40xxxxxx and 48xxxxxx codes, and every naira on them
used to be absent from the statements — no heading claimed it and no
total missed it, so nothing said so. Around 8.9m of liabilities in one
tenant.

Each family now has a remainder bucket. It makes no claim about where
those codes belong — deciding that is an accounting judgement — it just
refuses to lose them while somebody decides.

The property under test is the identity that makes the omission
detectable at all:

    assets - (liabilities + net assets)  ==  surplus/(deficit)

Before year-end close the current-year result has not been moved into
accumulated fund, so the two sides of the position statement differ by
exactly that result — but only if every account reached one statement or
the other. Drop one, and the identity breaks by its balance. All three
live tenants reconcile to the naira with the buckets in place, and none
did without them.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from accounting.services.ipsas_reports import IPSASReportService


# A year of its own, so balances seeded by other tests cannot drift in.
FY = 2099


def _account(code, name, account_type):
    from accounting.models import Account
    account, _ = Account.objects.get_or_create(
        code=code,
        defaults={'name': name, 'account_type': account_type, 'is_active': True},
    )
    return account


def _balance(account, *, debit='0', credit='0'):
    from accounting.models.balances import GLBalance
    GLBalance.objects.create(
        account=account, fiscal_year=FY, period=1,
        debit_balance=Decimal(debit), credit_balance=Decimal(credit),
    )


@pytest.fixture
def a_ledger_that_balances(db):
    """DR 1,700 / CR 1,700 spread over classified and unclassified codes.

    Half the money sits on codes the statements name (31, 41, 22, 12) and
    half on codes they do not (30, 48). A statement that ignores the
    second half reports assets 1,000 against liabilities 1,200 — and the
    identity below breaks by 200.
    """
    _balance(_account('31100100', 'Cash in TSA', 'Asset'), debit='1000.00')
    _balance(_account('30500000', 'Asset Suspense', 'Asset'), debit='500.00')

    _balance(_account('41100100', 'Accounts Payable', 'Liability'), credit='1200.00')
    _balance(_account('48010101', 'Deferred Inflow', 'Liability'), credit='300.00')

    _balance(_account('22100100', 'Travel and Transport', 'Expense'), debit='200.00')
    _balance(_account('12100100', 'Fees and Fines', 'Income'), credit='200.00')


@pytest.mark.django_db
def test_the_position_statement_reconciles_to_the_result(a_ledger_that_balances):
    """The accounting identity, which is what the omission used to break."""
    position = IPSASReportService.statement_of_financial_position(FY)
    performance = IPSASReportService.statement_of_financial_performance(FY)

    check = position['balance_check']
    difference = check['assets'] - check['liabilities_plus_net_assets']

    assert difference == performance['surplus_deficit'], (
        'assets - (liabilities + net assets) must equal the unclosed '
        'surplus/(deficit); a mismatch means an account reached neither '
        'statement'
    )


@pytest.mark.django_db
def test_assets_outside_the_named_sub_families_are_reported(a_ledger_that_balances):
    position = IPSASReportService.statement_of_financial_position(FY)
    unclassified = position['assets']['unclassified']

    assert unclassified['total'] == Decimal('500.00')
    assert [i['code'] for i in unclassified['items']] == ['30500000']
    # …and they count towards the headline figure, not just their bucket.
    assert position['assets']['total'] == Decimal('1500.00')


@pytest.mark.django_db
def test_liabilities_outside_the_named_sub_families_are_reported(a_ledger_that_balances):
    position = IPSASReportService.statement_of_financial_position(FY)
    unclassified = position['liabilities']['unclassified']

    assert unclassified['total'] == Decimal('300.00')
    assert [i['code'] for i in unclassified['items']] == ['48010101']
    assert position['liabilities']['total'] == Decimal('1500.00')


@pytest.mark.django_db
def test_a_named_sub_family_does_not_swallow_the_remainder(a_ledger_that_balances):
    """30500000 belongs to the remainder, not to Current Assets.

    The remainder is selected as "family 3, excluding 31 and 32". If that
    exclusion were dropped the money would be counted twice — once in its
    own bucket and once inside a named heading — and the identity above
    would break in the opposite direction.
    """
    position = IPSASReportService.statement_of_financial_position(FY)
    current_codes = {i['code'] for i in position['assets']['current']['items']}

    assert '30500000' not in current_codes
    assert position['assets']['current']['total'] == Decimal('1000.00')


@pytest.mark.django_db
def test_expenditure_outside_21_to_25_would_read_as_underspend(db):
    """Family 2 has its own remainder — 20xxxxxx is the common case.

    No heading covered it, so expenditure coded there was simply missing
    from the statement, which for an Accountant-General reads as money
    not spent.
    """
    _balance(_account('20900000', 'Expenditure Suspense', 'Expense'), debit='750.00')

    performance = IPSASReportService.statement_of_financial_performance(FY)

    assert performance['expenditure']['unclassified']['total'] == Decimal('750.00')
    assert performance['expenditure']['total'] == Decimal('750.00')
