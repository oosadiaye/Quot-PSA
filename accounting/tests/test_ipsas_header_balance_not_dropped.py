"""An IPSAS statement never loses money because the chart was tidied.

A header account aggregates its children and should never be posted to.
``Account.is_postable`` now stops that happening — but balances that
predate the flag exist, because re-classifying an account turns
yesterday's legitimate posting into today's header balance. Migrations
0121 and 0122 do exactly that to the NCoA group roots (20000000
Expenditure, 31000000 Current Assets, and so on).

The statements used to drop those balances on the floor:

  * ``_sum_ncoa_group`` gave a header its amount purely from the sum of
    its descendants, and counted only posting rows in the total.
  * ``_sum_posting_only`` filtered ``is_postable=True``, so a header
    balance was never even visited.
  * ``_bp_group`` did the same, which in budget-vs-actual reads as
    underspend against the appropriation.

In each case the money left the statement with no trace — the docstring
claimed a warning that was never actually logged. For an expenditure
statement in a public-sector ERP that is the worst direction to be wrong
in: the Accountant-General's report would show less spent than was spent.

These tests pin the rule rather than the mechanism: a balance on a header
is still reported, and still counted in the total.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from accounting.services.ipsas_reports import IPSASReportService


FY = 2026


@pytest.fixture
def header_and_leaf(db):
    """A 22-series header with a postable child beneath it."""
    from accounting.models import Account
    header, _ = Account.objects.get_or_create(
        code='22000000',
        defaults={'name': 'Operations & Maintenance', 'account_type': 'Expense',
                  'is_active': True},
    )
    header.is_postable = False
    header.save(update_fields=['is_postable'])

    leaf, _ = Account.objects.get_or_create(
        code='22100100',
        defaults={'name': 'Travel and Transport', 'account_type': 'Expense',
                  'is_active': True},
    )
    leaf.is_postable = True
    leaf.save(update_fields=['is_postable'])
    return header, leaf


def _balance(account, *, debit='0', credit='0', period=1):
    from accounting.models.balances import GLBalance
    return GLBalance.objects.create(
        account=account, fiscal_year=FY, period=period,
        debit_balance=Decimal(debit), credit_balance=Decimal(credit),
    )


def _expenditure_items(report, group='overhead_costs'):
    return report['expenditure'][group]['items']


@pytest.mark.django_db
def test_a_balance_on_a_header_still_appears_in_the_performance_statement(
    header_and_leaf,
):
    header, leaf = header_and_leaf
    _balance(leaf, debit='1000.00')
    _balance(header, debit='250.00')   # the legacy posting

    report = IPSASReportService.statement_of_financial_performance(FY)
    codes = {i['code']: i['amount'] for i in _expenditure_items(report)}

    assert codes.get('22000000') == Decimal('250.00'), (
        'the header balance was dropped — expenditure is under-reported'
    )
    assert codes.get('22100100') == Decimal('1000.00')


@pytest.mark.django_db
def test_the_header_balance_is_counted_in_the_group_total(header_and_leaf):
    header, leaf = header_and_leaf
    _balance(leaf, debit='1000.00')
    _balance(header, debit='250.00')

    report = IPSASReportService.statement_of_financial_performance(FY)
    assert report['expenditure']['overhead_costs']['total'] == Decimal('1250.00')


@pytest.mark.django_db
def test_a_header_line_is_marked_as_one(header_and_leaf):
    """So the UI can render it differently from a real posting line."""
    header, leaf = header_and_leaf
    _balance(leaf, debit='1000.00')
    _balance(header, debit='250.00')

    report = IPSASReportService.statement_of_financial_performance(FY)
    rows = {i['code']: i for i in _expenditure_items(report)}
    assert rows['22000000']['is_header'] is True
    assert rows['22100100']['is_header'] is False


@pytest.mark.django_db
def test_descendants_are_not_double_counted_in_the_position_statement(db):
    """``_sum_ncoa_group`` adds the header's own balance, not its children's.

    The header line shows roll-up + direct, but the grand total must add
    the direct part only — the rolled-up part is already there via the
    children's own rows.
    """
    from accounting.models import Account
    header, _ = Account.objects.get_or_create(
        code='31000000',
        defaults={'name': 'Current Assets', 'account_type': 'Asset', 'is_active': True},
    )
    header.is_postable = False
    header.save(update_fields=['is_postable'])
    leaf, _ = Account.objects.get_or_create(
        code='31100100',
        defaults={'name': 'Cash in TSA', 'account_type': 'Asset', 'is_active': True},
    )
    leaf.is_postable = True
    leaf.save(update_fields=['is_postable'])

    _balance(leaf, debit='800.00')
    _balance(header, debit='200.00')

    report = IPSASReportService.statement_of_financial_position(FY)
    current = report['assets']['current']
    rows = {i['code']: i['amount'] for i in current['items']}

    # Header line reads as roll-up (800) + its own direct balance (200).
    assert rows['31000000'] == Decimal('1000.00')
    assert rows['31100100'] == Decimal('800.00')
    # Total counts each naira once: 800 via the leaf, 200 via the header.
    assert current['total'] == Decimal('1000.00')
