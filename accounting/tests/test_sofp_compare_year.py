"""The Statement of Financial Position can be set against any other fiscal year, not only the one before."""
from decimal import Decimal

import pytest

from accounting.models.balances import GLBalance
from accounting.services.ipsas_reports import IPSASReportService
from procurement.tests.test_vendor_role_containment import client_with_role

pytestmark = pytest.mark.django_db
URL = '/api/v1/accounting/ipsas/financial-position/'


@pytest.fixture
def balances(db):
    """Cash of 1 000 in 2022, 2 500 in 2024 and 4 000 in 2026, on one asset account, with no other balances in those years."""
    from accounting.models import Account
    acct, _ = Account.objects.get_or_create(code='31100777', defaults={'name': 'Cash for compare tests', 'account_type': 'Asset', 'is_active': True})
    Account.objects.filter(pk=acct.pk).update(is_postable=True, is_active=True)
    for year in (2022, 2024, 2026):
        GLBalance.objects.filter(fiscal_year=year).delete()
    for year, amount in ((2022, '1000.00'), (2024, '2500.00'), (2026, '4000.00')):
        GLBalance.objects.create(account=acct, fiscal_year=year, period=1, debit_balance=Decimal(amount), credit_balance=Decimal('0'))
    return acct


def total_assets(block):
    return Decimal(str(block['assets']['total']))


def test_the_comparison_year_defaults_to_the_year_before(balances):
    data = IPSASReportService.statement_of_financial_position(2026)
    assert data['comparative_year'] == 2025
    assert total_assets(data) == Decimal('4000.00')


def test_any_other_year_can_be_the_comparison(balances):
    data = IPSASReportService.statement_of_financial_position(2026, compare_year=2022)
    assert data['comparative_year'] == 2022
    assert total_assets(data['comparative']) == Decimal('1000.00')
    data = IPSASReportService.statement_of_financial_position(2026, compare_year=2024)
    assert total_assets(data['comparative']) == Decimal('2500.00')


def test_an_earlier_year_can_be_set_against_a_later_one(balances):
    data = IPSASReportService.statement_of_financial_position(2022, compare_year=2026)
    assert total_assets(data) == Decimal('1000.00') and total_assets(data['comparative']) == Decimal('4000.00')


def test_no_comparison_leaves_the_block_out(balances):
    data = IPSASReportService.statement_of_financial_position(2026, comparative=False, compare_year=2022)
    assert data['comparative'] is None and data['comparative_year'] is None


def test_the_endpoint_takes_compare_year_and_says_which_year_it_used(balances):
    r = client_with_role('admin').get(f'{URL}?fiscal_year=2026&compare_year=2022')
    assert r.status_code == 200
    body = r.json()
    assert body['comparative_year'] == 2022 and Decimal(str(body['comparative']['assets']['total'])) == Decimal('1000.00')


def test_the_endpoint_does_not_serve_one_comparison_for_another(balances):
    admin = client_with_role('admin')
    a = admin.get(f'{URL}?fiscal_year=2026&compare_year=2022').json()
    b = admin.get(f'{URL}?fiscal_year=2026&compare_year=2024').json()
    assert Decimal(str(a['comparative']['assets']['total'])) == Decimal('1000.00')
    assert Decimal(str(b['comparative']['assets']['total'])) == Decimal('2500.00')


def test_a_comparison_year_that_is_not_a_year_is_refused_plainly(balances):
    admin = client_with_role('admin')
    assert admin.get(f'{URL}?fiscal_year=2026&compare_year=abc').status_code == 400
    r = admin.get(f'{URL}?fiscal_year=2026&compare_year=12')
    assert r.status_code == 400 and 'compare_year' in str(r.json())
