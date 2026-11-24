"""Warrant recommendations: the rule is checkable by hand, nothing is issued without a reference, and the Warrant's own rules still apply."""
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
from budget.models import Appropriation, Warrant
from cash_planning.models import CashPlan, WarrantRecommendation
from cash_planning.services import ForecastEngine
from cash_planning.warrants import WarrantPlanError, convert_to_warrant, generate_recommendations
from core.models import TenantModule
from core.permissions import invalidate_module_cache
from hrm.models import PayrollPeriod, PayrollRun

pytestmark = pytest.mark.django_db
YEAR = 2044
DOMAIN = 'pytest.localhost'
BASE = '/api/v1/cash-planning/recommendations/'


def _tenant():
    from tenants.models import Client, Domain
    with schema_context('public'):
        tenant, _ = Client.objects.get_or_create(schema_name='pytest_schema', defaults={'name': 'PyTest Tenant'})
        Domain.objects.get_or_create(domain=DOMAIN, tenant=tenant, defaults={'is_primary': True})
    return tenant


def client_for(role='admin'):
    from tenants.models import UserTenantRole
    tenant = _tenant()
    user, _ = User.objects.get_or_create(username=f'wr_{role}', defaults={'email': f'{role}@t.test'})
    UserTenantRole.objects.update_or_create(user=user, tenant=tenant, defaults={'role': role, 'is_active': True})
    token, _ = Token.objects.get_or_create(user=user)
    c = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
    c.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return c


def module(active):
    TenantModule.objects.update_or_create(module_name='cash_planning', defaults={'is_active': active})
    invalidate_module_cache(_tenant().pk, 'cash_planning')


@pytest.fixture
def world(db, _route_to_pytest_schema):
    module(True)
    fy, _ = FiscalYear.objects.get_or_create(year=YEAR, defaults={'name': f'FY{YEAR}'})
    FiscalYear.objects.filter(pk=fy.pk).update(start_date=date(YEAR, 1, 1), end_date=date(YEAR, 12, 31))
    fy.refresh_from_db()
    admin, _ = AdministrativeSegment.objects.get_or_create(
        code='097500000000', defaults={'name': 'Warrant Test MDA', 'level': 'ORGANIZATION', 'sector_code': '09'})
    func, _ = FunctionalSegment.objects.get_or_create(code='70175', defaults={'name': 'Warrant Function', 'division_code': '701'})
    prog, _ = ProgrammeSegment.objects.get_or_create(
        code='09750000000000', defaults={'name': 'Warrant Programme', 'policy_code': '09', 'programme_code': '09'})
    fund, _ = FundSegment.objects.get_or_create(code='09750', defaults={'name': 'Warrant Fund', 'main_fund_code': '09'})
    accounts = [Account.objects.get_or_create(code=f'2275{i}00', defaults={'name': f'Warrant Line {i}', 'account_type': 'Expense'})[0]
                for i in range(3)]
    Appropriation.objects.filter(administrative=admin).delete()      # also clears warrants (cascade) and recommendations' targets
    WarrantRecommendation.objects.filter(fiscal_year=YEAR).delete()

    def appropriation(i=0, amount='1200.00', spread=None, status='ACTIVE'):
        return Appropriation.objects.create(
            fiscal_year=fy, administrative=admin, economic=accounts[i], functional=func, programme=prog, fund=fund,
            amount_approved=Decimal(amount), status=status, appropriation_type='ORIGINAL', monthly_spread=spread)

    def warrant(a, amount, start, end, status='RELEASED'):
        return Warrant.objects.create(appropriation=a, amount_released=Decimal(amount), release_date=start, effective_from=start,
                                      effective_to=end, authority_reference='AGF/TEST', status=status)

    return dict(fy=fy, admin=admin, appropriation=appropriation, warrant=warrant)


def proposals(a):
    return list(WarrantRecommendation.objects.filter(appropriation=a, fiscal_year=YEAR).order_by('quarter'))


def test_quarter_one_proposes_three_twelfths_of_the_budget(world):
    a = world['appropriation']()
    result = generate_recommendations(YEAR, 1)
    (rec,) = proposals(a)
    assert (result.created, rec.proposed_amount, rec.status) == (1, Decimal('300.00'), 'proposed')
    assert (rec.effective_from, rec.effective_to, rec.quarter) == (date(YEAR, 1, 1), date(YEAR, 3, 31), 1)
    assert '300.00' in rec.rationale and 'already released 0.00' in rec.rationale


def test_a_later_quarter_carries_over_what_earlier_ones_did_not_release(world):
    a = world['appropriation']()
    world['warrant'](a, '200.00', date(YEAR, 1, 1), date(YEAR, 3, 31))          # only 200 of the 300 due in Q1 was released
    generate_recommendations(YEAR, 2)
    (rec,) = proposals(a)
    assert rec.proposed_amount == Decimal('400.00')                              # 600 phased by end of Q2 - 200 released
    assert (rec.effective_from, rec.effective_to) == (date(YEAR, 4, 1), date(YEAR, 6, 30))


def test_a_front_loaded_spread_is_followed(world):
    a = world['appropriation'](spread={str(m): ('400' if m <= 3 else '50') for m in range(1, 13)})
    generate_recommendations(YEAR, 1)
    assert proposals(a)[0].proposed_amount == Decimal('1200.00')


def test_nothing_is_recommended_once_the_quarter_is_already_covered_by_releases(world):
    a = world['appropriation']()
    world['warrant'](a, '300.00', date(YEAR, 1, 1), date(YEAR, 1, 31), status='EXHAUSTED')   # exhausted, so it no longer blocks the window
    result = generate_recommendations(YEAR, 1)
    assert proposals(a) == [] and 'nothing further' in result.skipped[0]['reason']


def test_a_warrant_already_covering_the_quarter_is_not_duplicated(world):
    a = world['appropriation']()
    world['warrant'](a, '100.00', date(YEAR, 1, 1), date(YEAR, 3, 31))
    result = generate_recommendations(YEAR, 1)
    assert proposals(a) == [] and 'already covers' in result.skipped[0]['reason']


def test_cash_available_scales_every_proposal_by_the_same_proportion(world):
    a, b = world['appropriation'](0), world['appropriation'](1)
    result = generate_recommendations(YEAR, 1, available_cash='300.00')       # 600 wanted, 300 available
    assert [p.proposed_amount for p in proposals(a) + proposals(b)] == [Decimal('150.00'), Decimal('150.00')]
    assert result.scaled_to == Decimal('300.00') and 'Scaled to 50.0%' in proposals(a)[0].rationale


def test_enough_cash_leaves_proposals_unscaled(world):
    a = world['appropriation']()
    generate_recommendations(YEAR, 1, available_cash='99999.00')
    assert proposals(a)[0].proposed_amount == Decimal('300.00') and 'Scaled' not in proposals(a)[0].rationale


def test_generating_again_replaces_proposals_instead_of_piling_them_up(world):
    a = world['appropriation']()
    generate_recommendations(YEAR, 1)
    again = generate_recommendations(YEAR, 1)
    assert (again.created, again.replaced) == (1, 1) and len(proposals(a)) == 1


def test_an_accepted_recommendation_is_kept_and_not_regenerated(world):
    a = world['appropriation']()
    generate_recommendations(YEAR, 1)
    WarrantRecommendation.objects.filter(appropriation=a).update(status='accepted')
    result = generate_recommendations(YEAR, 1)
    assert result.created == 0 and 'accepted or converted' in result.skipped[0]['reason'] and len(proposals(a)) == 1


def test_only_active_appropriations_are_considered_and_a_missing_year_is_explained(world):
    draft = world['appropriation'](status='DRAFT')
    generate_recommendations(YEAR, 1)
    assert proposals(draft) == []
    with pytest.raises(WarrantPlanError, match='No fiscal year 2099'):
        generate_recommendations(2099, 1)
    with pytest.raises(WarrantPlanError, match='quarter'):
        generate_recommendations(YEAR, 5)


# --- conversion -------------------------------------------------------------------------------------------------

def test_conversion_issues_a_pending_warrant_over_the_quarter(world):
    a = world['appropriation']()
    generate_recommendations(YEAR, 1)
    rec = proposals(a)[0]
    user = User.objects.get_or_create(username='wr_issuer')[0]
    w = convert_to_warrant(rec, authority_reference='AGF/2044/Q1', issued_by=user)
    rec.refresh_from_db()
    assert (w.status, w.amount_released, w.effective_from, w.effective_to, w.issued_by) == (
        'PENDING', Decimal('300.00'), date(YEAR, 1, 1), date(YEAR, 3, 31), user)
    assert (rec.status, rec.warrant_id) == ('converted', w.pk)


def test_conversion_can_lower_the_amount_but_never_raise_it(world):
    a = world['appropriation']()
    generate_recommendations(YEAR, 1)
    rec = proposals(a)[0]
    with pytest.raises(WarrantPlanError, match='no more than'):
        convert_to_warrant(rec, authority_reference='AGF/1', amount='301.00')
    assert convert_to_warrant(rec, authority_reference='AGF/1', amount='250.00').amount_released == Decimal('250.00')


def test_a_warrant_letter_reference_is_required(world):
    a = world['appropriation']()
    generate_recommendations(YEAR, 1)
    with pytest.raises(WarrantPlanError, match='authority reference'):
        convert_to_warrant(proposals(a)[0], authority_reference='   ')
    assert not Warrant.objects.filter(appropriation=a).exists()


def test_budgets_own_overlap_rule_still_applies_and_leaves_the_recommendation_open(world):
    a = world['appropriation']()
    generate_recommendations(YEAR, 1)
    rec = proposals(a)[0]
    world['warrant'](a, '50.00', date(YEAR, 2, 1), date(YEAR, 2, 28))          # someone issued one by hand in the meantime
    with pytest.raises(WarrantPlanError, match='overlaps'):
        convert_to_warrant(rec, authority_reference='AGF/1')
    rec.refresh_from_db()
    assert rec.status == 'proposed' and rec.warrant_id is None


def test_a_converted_recommendation_cannot_be_converted_twice(world):
    a = world['appropriation']()
    generate_recommendations(YEAR, 1)
    rec = proposals(a)[0]
    convert_to_warrant(rec, authority_reference='AGF/1')
    with pytest.raises(WarrantPlanError, match='already converted'):
        convert_to_warrant(rec, authority_reference='AGF/2')
    assert Warrant.objects.filter(appropriation=a, status='PENDING').count() == 1


# --- API ---------------------------------------------------------------------------------------------------------

def test_generate_endpoint_returns_a_summary_and_validates_input(world):
    world['appropriation']()
    c = client_for('admin')
    ok = c.post(f'{BASE}generate/', {'fiscal_year': YEAR, 'quarter': 1}, format='json')
    assert ok.status_code == 200 and ok.json()['created'] == 1 and ok.json()['total'] == '300.00'
    assert c.post(f'{BASE}generate/', {'quarter': 1}, format='json').status_code == 400
    assert c.post(f'{BASE}generate/', {'fiscal_year': YEAR, 'quarter': 1, 'available_cash': 'lots'}, format='json').status_code == 400
    assert c.post(f'{BASE}generate/', {'fiscal_year': 2099, 'quarter': 1}, format='json').status_code == 400


def test_convert_endpoint_issues_the_warrant_and_shows_the_reference_rule(world):
    a = world['appropriation']()
    c = client_for('admin')
    c.post(f'{BASE}generate/', {'fiscal_year': YEAR, 'quarter': 1}, format='json')
    rec = proposals(a)[0]
    assert c.post(f'{BASE}{rec.pk}/convert/', {}, format='json').status_code == 400
    r = c.post(f'{BASE}{rec.pk}/convert/', {'authority_reference': 'AGF/2044/Q1'}, format='json')
    assert r.status_code == 201 and r.json()['status'] == 'PENDING' and r.json()['recommendation']['status'] == 'converted'


def test_pages_of_recommendations_are_stable_and_cover_every_row_once(world):
    for i in range(25):
        WarrantRecommendation.objects.create(mda_name=f'M{i}', fiscal_year=YEAR, quarter=1, proposed_amount=Decimal('1'))
    c = client_for('admin')
    first = c.get(f'{BASE}?fiscal_year={YEAR}&quarter=1&page=1').json()
    second = c.get(f'{BASE}?fiscal_year={YEAR}&quarter=1&page=2').json()
    ids = [r['id'] for r in first['results'] + second['results']]
    assert first['count'] == 25 and len(ids) == 25 and len(set(ids)) == 25
    from cash_planning.views import WarrantRecommendationViewSet
    assert tuple(WarrantRecommendationViewSet.queryset.query.order_by) == ('recommendation_date', 'id')


def test_status_cannot_be_set_by_editing_the_row(world):
    a = world['appropriation']()
    c = client_for('admin')
    c.post(f'{BASE}generate/', {'fiscal_year': YEAR, 'quarter': 1}, format='json')
    rec = proposals(a)[0]
    c.patch(f'{BASE}{rec.pk}/', {'status': 'converted'}, format='json')
    rec.refresh_from_db()
    assert rec.status == 'proposed'


def test_accept_and_reject_follow_the_status_rules(world):
    a = world['appropriation']()
    c = client_for('admin')
    c.post(f'{BASE}generate/', {'fiscal_year': YEAR, 'quarter': 1}, format='json')
    rec = proposals(a)[0]
    assert c.post(f'{BASE}{rec.pk}/accept/', {}, format='json').json()['status'] == 'accepted'
    assert c.post(f'{BASE}{rec.pk}/accept/', {}, format='json').status_code == 400
    r = c.post(f'{BASE}{rec.pk}/reject/', {'reason': 'Cash tight in Q1'}, format='json')
    assert r.json()['status'] == 'rejected' and 'Cash tight' in r.json()['rationale']


def test_module_off_refuses_everything(world):
    module(False)
    assert client_for('admin').post(f'{BASE}generate/', {'fiscal_year': YEAR, 'quarter': 1}, format='json').status_code == 403


def test_issuing_actions_require_the_approver_permission_and_ordinary_ones_do_not():
    """Wiring check: a non-admin needs the explicit 'post' permission to generate or issue; reading and editing do not."""
    from core.permissions import IsApprover
    from cash_planning.views import WarrantRecommendationViewSet

    def needs_approver(action_name):
        view = WarrantRecommendationViewSet()
        view.action = action_name
        return any(isinstance(p, IsApprover) and p.perm_prefix == 'post' for p in view.get_permissions())

    assert needs_approver('generate') and needs_approver('convert')
    assert not any(needs_approver(a) for a in ('list', 'retrieve', 'accept', 'reject', 'partial_update'))


# --- the payroll forecast source ---------------------------------------------------------------------------------

def test_the_payroll_forecast_reads_real_payroll_runs(world):
    period, _ = PayrollPeriod.objects.get_or_create(
        start_date=date(YEAR, 5, 1), end_date=date(YEAR, 5, 31), defaults=dict(period_type='Monthly', payment_date=date(YEAR, 5, 28)))
    PayrollRun.objects.filter(run_number__startswith='WR-').delete()
    PayrollRun.objects.create(period=period, run_number='WR-1', total_gross=Decimal('45000000.00'), status='Approved')
    PayrollRun.objects.create(period=period, run_number='WR-2', total_gross=Decimal('9999.00'), status='Cancelled')
    plan = CashPlan.objects.create(fiscal_year=YEAR)
    lines = ForecastEngine(YEAR, cash_plan=plan).from_payroll()
    assert len(lines) == 1 and Decimal(str(lines[0]['amount'])) == Decimal('45000000.00')
