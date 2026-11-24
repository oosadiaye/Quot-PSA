"""Binding a payroll run to the appropriation that pays for it: suggested, checked, snapshotted, and not forgeable."""
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounting.models.advanced import FiscalYear
from accounting.models.gl import Account
from accounting.models.ncoa import AdministrativeSegment, FunctionalSegment, FundSegment, ProgrammeSegment
from budget.models import Appropriation
from core.models import TenantModule
from core.permissions import invalidate_module_cache
from hrm.models import PayrollPeriod, PayrollRun
from personnel_budget.models import PayrollBudgetBinding

pytestmark = pytest.mark.django_db
YEAR = 2043
DOMAIN = 'pytest.localhost'
BASE = '/api/v1/personnel-budget/payroll-bindings/'


def _tenant():
    from tenants.models import Client, Domain
    with schema_context('public'):
        tenant, _ = Client.objects.get_or_create(schema_name='pytest_schema', defaults={'name': 'PyTest Tenant'})
        Domain.objects.get_or_create(domain=DOMAIN, tenant=tenant, defaults={'is_primary': True})
    return tenant


def client_for(role='admin'):
    from tenants.models import UserTenantRole
    tenant = _tenant()
    user, _ = User.objects.get_or_create(username=f'pb_bind_{role}', defaults={'email': f'{role}@t.test'})
    UserTenantRole.objects.update_or_create(user=user, tenant=tenant, defaults={'role': role, 'is_active': True})
    token, _ = Token.objects.get_or_create(user=user)
    c = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
    c.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return c


def module(active):
    TenantModule.objects.update_or_create(module_name='personnel_budget', defaults={'is_active': active})
    invalidate_module_cache(_tenant().pk, 'personnel_budget')


@pytest.fixture
def world(db, _route_to_pytest_schema):
    module(True)
    PayrollBudgetBinding.objects.all().delete()
    fy, _ = FiscalYear.objects.get_or_create(year=YEAR, defaults={'name': f'FY{YEAR}'})
    FiscalYear.objects.filter(pk=fy.pk).update(start_date=date(YEAR, 1, 1), end_date=date(YEAR, 12, 31))
    other_fy, _ = FiscalYear.objects.get_or_create(year=YEAR + 1, defaults={'name': f'FY{YEAR + 1}'})
    FiscalYear.objects.filter(pk=other_fy.pk).update(start_date=date(YEAR + 1, 1, 1), end_date=date(YEAR + 1, 12, 31))
    admin, _ = AdministrativeSegment.objects.get_or_create(
        code='098000000000', defaults={'name': 'Bind Test MDA', 'level': 'ORGANIZATION', 'sector_code': '09'})
    func, _ = FunctionalSegment.objects.get_or_create(code='70188', defaults={'name': 'Bind Function', 'division_code': '701'})
    prog, _ = ProgrammeSegment.objects.get_or_create(
        code='09880000000000', defaults={'name': 'Bind Programme', 'policy_code': '09', 'programme_code': '09'})
    fund, _ = FundSegment.objects.get_or_create(code='09800', defaults={'name': 'Bind Fund', 'main_fund_code': '09'})
    salaries, _ = Account.objects.get_or_create(code='21108801', defaults={'name': 'Bind Salaries', 'account_type': 'Expense'})
    wages, _ = Account.objects.get_or_create(code='21108802', defaults={'name': 'Bind Wages', 'account_type': 'Expense'})
    overhead, _ = Account.objects.get_or_create(code='22108801', defaults={'name': 'Bind Overhead', 'account_type': 'Expense'})
    Appropriation.objects.filter(administrative=admin).delete()

    def appropriation(account, approved, *, status='ACTIVE', year=fy, spent='0', committed='0'):
        return Appropriation.objects.create(
            fiscal_year=year, administrative=admin, economic=account, functional=func, programme=prog, fund=fund,
            amount_approved=Decimal(approved), status=status, appropriation_type='ORIGINAL',
            cached_total_expended=Decimal(spent), cached_total_committed=Decimal(committed))

    period, _ = PayrollPeriod.objects.get_or_create(
        start_date=date(YEAR, 3, 1), end_date=date(YEAR, 3, 31),
        defaults=dict(period_type='Monthly', payment_date=date(YEAR, 3, 28)))

    def run(number, gross='400.00', status='Draft'):
        PayrollRun.objects.filter(run_number=number).delete()
        return PayrollRun.objects.create(period=period, run_number=number, total_gross=Decimal(gross), status=status)

    return dict(fy=fy, other_fy=other_fy, admin=admin, salaries=salaries, wages=wages, overhead=overhead,
                appropriation=appropriation, run=run)


def test_suggestions_are_active_personnel_lines_of_the_runs_year_with_enough_balance_first(world):
    covers = world['appropriation'](world['salaries'], '1000.00', spent='100.00', committed='50.00')       # 850 available
    short = world['appropriation'](world['wages'], '1000.00', spent='900.00')                              # 100 available
    world['appropriation'](world['overhead'], '5000.00')                                                    # not personnel
    world['appropriation'](world['salaries'], '9999.00', status='DRAFT', year=world['other_fy'])             # wrong year, not active
    r = client_for().get(f"{BASE}suggest/?payroll_run={world['run']('PB-S-1').pk}")
    got = r.json()['candidates']
    assert r.status_code == 200
    assert [c['id'] for c in got] == [covers.pk, short.pk]
    assert (got[0]['available'], got[0]['covers'], got[1]['covers']) == ('850.00', True, False)


def test_suggest_needs_a_real_payroll_run(world):
    assert client_for().get(f'{BASE}suggest/').status_code == 400
    assert client_for().get(f'{BASE}suggest/?payroll_run=999999999').status_code == 400


def test_binding_takes_the_amount_and_snapshot_from_the_run_and_the_books(world):
    line = world['appropriation'](world['salaries'], '1000.00', spent='100.00', committed='50.00')
    run = world['run']('PB-B-1', gross='400.00')
    r = client_for().post(BASE, {'payroll_run': run.pk, 'appropriation_line': line.pk}, format='json')
    body = r.json()
    assert r.status_code == 201, body
    assert (body['bound_amount'], body['remaining_at_binding']) == ('400.00', '850.00')
    assert body['bound_by'] is not None and body['check_level']


def test_a_forged_amount_or_snapshot_in_the_request_is_ignored(world):
    line = world['appropriation'](world['salaries'], '1000.00')
    run = world['run']('PB-B-2', gross='400.00')
    r = client_for().post(BASE, {'payroll_run': run.pk, 'appropriation_line': line.pk, 'bound_amount': '1.00',
                                 'remaining_at_binding': '999999.00', 'check_level': 'FORGED'}, format='json')
    assert r.status_code == 201
    saved = PayrollBudgetBinding.objects.get(payroll_run=run)
    assert (saved.bound_amount, saved.remaining_at_binding) == (Decimal('400.00'), Decimal('1000.00'))
    assert saved.check_level != 'FORGED'


def test_only_an_active_appropriation_can_fund_payroll(world):
    draft = world['appropriation'](world['salaries'], '1000.00', status='DRAFT')
    r = client_for().post(BASE, {'payroll_run': world['run']('PB-B-3').pk, 'appropriation_line': draft.pk}, format='json')
    assert r.status_code == 400 and 'active appropriation' in r.json()['error']


def test_an_appropriation_from_another_year_is_refused_naming_both_years(world):
    wrong = world['appropriation'](world['salaries'], '1000.00', year=world['other_fy'])
    r = client_for().post(BASE, {'payroll_run': world['run']('PB-B-4').pk, 'appropriation_line': wrong.pk}, format='json')
    assert r.status_code == 400 and str(YEAR + 1) in r.json()['error'] and str(YEAR) in r.json()['error']


def test_a_paid_run_can_no_longer_change_its_funding(world):
    line = world['appropriation'](world['salaries'], '1000.00')
    r = client_for().post(BASE, {'payroll_run': world['run']('PB-B-5', status='Paid').pk, 'appropriation_line': line.pk}, format='json')
    assert r.status_code == 400 and 'already been paid' in r.json()['error']


def test_rebinding_switches_the_line_and_retakes_the_snapshot(world):
    first = world['appropriation'](world['salaries'], '1000.00')
    second = world['appropriation'](world['wages'], '2000.00', spent='500.00')
    run = world['run']('PB-B-6')
    c = client_for()
    made = c.post(BASE, {'payroll_run': run.pk, 'appropriation_line': first.pk}, format='json').json()
    r = c.patch(f"{BASE}{made['id']}/", {'appropriation_line': second.pk}, format='json')
    assert r.status_code == 200 and r.json()['appropriation_line'] == second.pk
    assert r.json()['remaining_at_binding'] == '1500.00'
    assert PayrollBudgetBinding.objects.filter(payroll_run=run).count() == 1


def test_a_binding_can_be_removed_before_payment_but_not_after(world):
    line = world['appropriation'](world['salaries'], '1000.00')
    c = client_for()
    run = world['run']('PB-B-7')
    made = c.post(BASE, {'payroll_run': run.pk, 'appropriation_line': line.pk}, format='json').json()
    assert c.delete(f"{BASE}{made['id']}/").status_code == 204
    paid = world['run']('PB-B-8')
    binding = PayrollBudgetBinding.objects.create(payroll_run=paid, appropriation_line=line, bound_amount=Decimal('1'))
    PayrollRun.objects.filter(pk=paid.pk).update(status='Paid')
    r = c.delete(f'{BASE}{binding.pk}/')
    assert r.status_code == 400 and PayrollBudgetBinding.objects.filter(pk=binding.pk).exists()


def test_module_off_refuses_binding(world):
    module(False)
    line = world['appropriation'](world['salaries'], '1000.00')
    r = client_for().post(BASE, {'payroll_run': world['run']('PB-B-9').pk, 'appropriation_line': line.pk}, format='json')
    assert r.status_code == 403
    assert not PayrollBudgetBinding.objects.exists()
