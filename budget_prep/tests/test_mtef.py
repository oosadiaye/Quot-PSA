"""The MTEF: totals worked out from the parts, every fiscal rule tripped on its own, the three-year view, scenarios,
roll-forward, the approval gate, and the link to MDA ceilings."""
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from accounting.models.advanced import FiscalYear
from accounting.models.gl import Account
from accounting.models.ncoa import AdministrativeSegment, FunctionalSegment, FundSegment, ProgrammeSegment
from budget.models import Appropriation
from budget_prep.models import MDACeiling, MTEFPolicy, MTEFProjection
from budget_prep.services import mtef
from budget_prep.tests.test_incorporate_endpoint import _client, _module

pytestmark = pytest.mark.django_db
YEAR = 2051
D = Decimal

#: A framework that obeys every default rule: revenue 1100 (recurrent 1000), spending 1250, deficit 150 fully financed.
HEALTHY = dict(
    inflation_assumption=D('10'), exchange_rate_assumption=D('1500'), oil_price_assumption=D('75'), oil_sensitivity=D('1'),
    rev_statutory=D('600'), rev_vat=D('200'), rev_igr=D('150'), rev_other=D('50'), rev_grants=D('100'), rev_capital_receipts=D('0'),
    exp_debt_service=D('200'), exp_personnel=D('450'), exp_overhead=D('150'), exp_other_recurrent=D('50'), exp_capital=D('400'),
    fin_domestic=D('100'), fin_external=D('50'), fin_other=D('0'),
)


@pytest.fixture(autouse=True)
def clean(db, _route_to_pytest_schema):
    MTEFProjection.objects.filter(fiscal_year__gte=YEAR - 2, fiscal_year__lte=YEAR + 3).delete()
    MDACeiling.objects.filter(fiscal_year=YEAR).delete()
    MTEFPolicy.objects.all().delete()


def make(year=YEAR, **over):
    return MTEFProjection.objects.create(fiscal_year=year, **{**HEALTHY, **over})


def rules(p, **kw):
    return {f.rule: f for f in mtef.assess_year(p, mtef.get_policy(), **kw)}


# ── the numbers are worked out, never typed ───────────────────────────────────────────────────────────────────

def test_totals_and_balance_follow_the_parts():
    p = make()
    assert (p.aggregate_revenue, p.aggregate_expenditure, p.fiscal_balance) == (D('1100'), D('1250'), D('-150'))
    assert (p.total_revenue, p.recurrent_revenue, p.recurrent_expenditure, p.total_financing, p.unfinanced_gap) == (
        D('1100'), D('1000'), D('850'), D('150'), D('0'))


def test_changing_a_part_changes_the_totals_on_save():
    p = make()
    p.rev_igr = D('250')
    p.save()
    p.refresh_from_db()
    assert (p.aggregate_revenue, p.fiscal_balance) == (D('1200'), D('-50'))


def test_a_row_holding_only_legacy_totals_keeps_them_and_still_gets_a_balance():
    p = MTEFProjection.objects.create(fiscal_year=YEAR, aggregate_revenue=D('100'), aggregate_expenditure=D('40'))
    assert (p.aggregate_revenue, p.aggregate_expenditure, p.fiscal_balance) == (D('100'), D('40'), D('60'))


def test_a_surplus_has_no_unfinanced_gap():
    p = make(exp_capital=D('0'), fin_domestic=D('0'), fin_external=D('0'))
    assert p.fiscal_balance > 0 and p.unfinanced_gap == 0


def test_one_framework_per_year():
    make()
    with pytest.raises(IntegrityError), transaction.atomic():
        make()


# ── each fiscal rule, on its own ──────────────────────────────────────────────────────────────────────────────

def test_a_framework_that_obeys_every_rule_passes_all_of_them():
    assert {f.status for f in rules(make()).values()} == {mtef.PASS}


def test_an_unfinanced_deficit_fails_and_says_by_how_much():
    p = make(fin_domestic=D('60'), fin_external=D('30'))                # deficit 150, financing 90
    f = rules(p)['Fully financed']
    assert f.status == mtef.FAIL and f.value == '60.00' and 'unfunded' in f.message and mtef.worst(list(rules(p).values())) == mtef.FAIL


def test_over_financing_is_not_a_failure():
    assert rules(make(fin_other=D('500')))['Fully financed'].status == mtef.PASS


def test_the_golden_rule_fails_when_recurrent_spending_exceeds_recurrent_revenue():
    p = make(exp_personnel=D('650'))                                    # recurrent 1050 > recurrent revenue 1000
    f = rules(p)['Golden rule']
    assert f.status == mtef.FAIL and '50.00' in f.message


def test_the_golden_rule_can_be_switched_off_by_policy():
    MTEFPolicy.objects.create(enforce_golden_rule=False)
    assert 'Golden rule' not in rules(make(exp_personnel=D('650')))


def test_debt_service_over_the_limit_fails():
    p = make(exp_debt_service=D('400'), exp_capital=D('200'))           # 400 / 1100 = 36.36% > 30%
    f = rules(p)['Debt service']
    assert f.status == mtef.FAIL and f.value == '36.36' and f.limit == '30.00'


def test_personnel_cost_over_the_limit_warns():
    p = make(exp_personnel=D('520'), exp_capital=D('330'), fin_domestic=D('100'), fin_external=D('50'))   # 520/1000 = 52%
    f = rules(p)['Personnel cost']
    assert f.status == mtef.WARN and f.value == '52.00'


def test_a_thin_capital_share_warns():
    p = make(exp_capital=D('300'), exp_overhead=D('250'))               # 300 / 1250 = 24%
    f = rules(p)['Capital share']
    assert f.status == mtef.WARN and f.value == '24.00'


def test_borrowing_over_the_limit_warns():
    p = make(fin_domestic=D('150'), fin_external=D('50'))               # 200 / 1100 = 18.18% > 15%
    assert rules(p)['Borrowing'].status == mtef.WARN


def test_blank_assumptions_warn():
    assert rules(make(inflation_assumption=D('0')))['Assumptions'].status == mtef.WARN
    assert rules(make(YEAR + 1, exchange_rate_assumption=D('0')))['Assumptions'].status == mtef.WARN


def test_a_framework_with_no_revenue_fails_outright():
    p = MTEFProjection.objects.create(fiscal_year=YEAR)
    assert [(f.rule, f.status) for f in mtef.assess_year(p, mtef.get_policy())] == [('Resource envelope', mtef.FAIL)]


def test_the_limits_are_the_governments_to_set():
    MTEFPolicy.objects.create(max_debt_service_pct=D('10'))
    assert rules(make())['Debt service'].status == mtef.FAIL            # 18.18% is fine by default, not under a 10% rule


# ── realism ───────────────────────────────────────────────────────────────────────────────────────────────────

def test_out_year_revenue_growth_beyond_inflation_plus_margin_warns():
    prev = make(YEAR - 1, rev_statutory=D('400'), rev_vat=D('150'), rev_igr=D('100'), rev_other=D('50'), rev_grants=D('0'))   # 700
    # 1100 on 700 = +57%, against 10% inflation + 10 points
    assert rules(make(), previous=prev)['Revenue growth'].status == mtef.WARN


def test_credible_revenue_growth_passes():
    prev = make(YEAR - 1, rev_statutory=D('560'), rev_vat=D('180'), rev_igr=D('140'), rev_other=D('40'), rev_grants=D('90'))      # 1010
    f = rules(make(), previous=prev)['Revenue growth']
    assert f.status == mtef.PASS and f.value == '8.91'


@pytest.fixture
def last_year_actuals():
    fy, _ = FiscalYear.objects.get_or_create(year=YEAR - 1, defaults={'name': f'FY{YEAR - 1}'})
    admin = AdministrativeSegment.objects.get_or_create(code='094000000000', defaults={'name': 'MTEF Test MDA', 'level': 'ORGANIZATION', 'sector_code': '09'})[0]
    func = FunctionalSegment.objects.get_or_create(code='70194', defaults={'name': 'MTEF Function', 'division_code': '701'})[0]
    prog = ProgrammeSegment.objects.get_or_create(code='09940000000000', defaults={'name': 'MTEF Programme', 'policy_code': '09', 'programme_code': '09'})[0]
    fund = FundSegment.objects.get_or_create(code='09940', defaults={'name': 'MTEF Fund', 'main_fund_code': '09'})[0]
    Appropriation.objects.filter(administrative=admin).delete()

    def spent(code, amount):
        acct = Account.objects.get_or_create(code=code, defaults={'name': f'MTEF {code}', 'account_type': 'Expense'})[0]
        Appropriation.objects.create(fiscal_year=fy, administrative=admin, economic=acct, functional=func, programme=prog, fund=fund,
                                     amount_approved=D('9999'), status='ACTIVE', appropriation_type='ORIGINAL', cached_total_expended=D(amount))
    return spent


def test_planned_spending_is_compared_with_what_was_actually_spent(last_year_actuals):
    last_year_actuals('21940001', '500')
    last_year_actuals('22940001', '200')
    last_year_actuals('23940001', '300')
    outturn = mtef.prior_outturn(YEAR)
    assert (outturn['year'], outturn['personnel'], outturn['overhead'], outturn['capital'], outturn['total']) == (YEAR - 1, '500.00', '200.00', '300.00', '1000.00')
    f = rules(make(), outturn=outturn)["Against last year's actual spending"]      # 1250 vs 1000: +25%, allowed 35%
    assert f.status == mtef.PASS and f.value == '25.00'


def test_a_budget_far_above_last_years_actuals_warns(last_year_actuals):
    last_year_actuals('21940001', '800')
    f = rules(make(), outturn=mtef.prior_outturn(YEAR))["Against last year's actual spending"]   # 1250 vs 800: +56%
    assert f.status == mtef.WARN


def test_no_outturn_when_there_is_no_earlier_year():
    assert mtef.prior_outturn(YEAR) is None


# ── the three-year view ───────────────────────────────────────────────────────────────────────────────────────

def test_the_framework_shows_three_years_and_flags_the_missing_ones():
    make()
    fw = mtef.framework(YEAR)
    assert [(y['year'], y['missing']) for y in fw['years']] == [(YEAR, False), (YEAR + 1, True), (YEAR + 2, True)]
    assert fw['complete'] is False and fw['overall'] == mtef.PASS


def test_a_complete_healthy_framework_is_complete_and_passes():
    mtef.roll_forward(make().fiscal_year)
    fw = mtef.framework(YEAR)
    assert fw['complete'] is True and all(not y['missing'] for y in fw['years'])


def test_the_framework_reports_the_worst_year():
    make()
    make(YEAR + 1, fin_domestic=D('0'), fin_external=D('0'))
    assert mtef.framework(YEAR)['overall'] == mtef.FAIL


def test_the_framework_for_an_empty_horizon():
    assert mtef.framework(YEAR)['overall'] == 'empty'


def test_the_framework_carries_the_policy_it_was_judged_by():
    assert mtef.framework(YEAR)['policy']['max_debt_service_pct'] == '30.00'


# ── roll-forward ──────────────────────────────────────────────────────────────────────────────────────────────

def test_roll_forward_grows_each_line_by_inflation_and_holds_financing_flat():
    make()
    result = mtef.roll_forward(YEAR)
    y1, y2 = MTEFProjection.objects.get(fiscal_year=YEAR + 1), MTEFProjection.objects.get(fiscal_year=YEAR + 2)
    assert result.created == [YEAR + 1, YEAR + 2] and result.kept == []
    assert (y1.rev_statutory, y1.exp_personnel) == (D('660.00'), D('495.00'))
    assert (y2.rev_statutory, y2.exp_personnel) == (D('726.00'), D('544.50'))        # compounds on the year before
    assert (y1.fin_domestic, y1.inflation_assumption, y1.exchange_rate_assumption, y1.status) == (D('100'), D('10'), D('1500'), 'draft')


def test_roll_forward_leaves_an_existing_year_alone():
    make()
    keep = make(YEAR + 1, rev_statutory=D('999'))
    result = mtef.roll_forward(YEAR)
    keep.refresh_from_db()
    assert result.created == [YEAR + 2] and result.kept == [YEAR + 1] and keep.rev_statutory == D('999')


def test_rolling_forward_twice_changes_nothing_the_second_time():
    make()
    mtef.roll_forward(YEAR)
    again = mtef.roll_forward(YEAR)
    assert again.created == [] and MTEFProjection.objects.filter(fiscal_year__gte=YEAR).count() == 3


def test_each_category_can_grow_at_its_own_rate():
    make()
    mtef.roll_forward(YEAR, growth={'revenue_growth_pct': '5', 'capital_growth_pct': '20', 'personnel_growth_pct': '0'})
    y1 = MTEFProjection.objects.get(fiscal_year=YEAR + 1)
    assert (y1.rev_statutory, y1.exp_capital, y1.exp_personnel, y1.exp_overhead) == (D('630.00'), D('480.00'), D('450.00'), D('165.00'))


def test_roll_forward_needs_a_budget_year_to_start_from():
    with pytest.raises(mtef.MTEFError, match='no MTEF'):
        mtef.roll_forward(YEAR)


# ── scenarios ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_an_oil_price_fall_cuts_the_oil_linked_revenue_and_exposes_the_gap():
    make()
    s = mtef.scenario(YEAR, oil_price_change_pct=-30)
    y = s['years'][0]
    assert y['after']['revenue'] == '860.00'                              # statutory 600 + VAT 200 fall 30% (-240)
    assert y['balance_change'] == '-240.00'
    assert [f['rule'] for f in y['newly_failing']] == ['Fully financed', 'Golden rule'] or 'Fully financed' in [f['rule'] for f in y['newly_failing']]
    assert y['overall'] == mtef.FAIL


def test_the_oil_sensitivity_decides_how_far_revenue_follows_the_price():
    make(oil_sensitivity=D('0'))
    assert mtef.scenario(YEAR, oil_price_change_pct=-30)['years'][0]['balance_change'] == '0.00'
    MTEFProjection.objects.all().delete()
    make(oil_sensitivity=D('0.5'))
    assert mtef.scenario(YEAR, oil_price_change_pct=-30)['years'][0]['balance_change'] == '-120.00'


def test_a_fall_in_igr_and_a_rise_in_costs_each_move_the_balance():
    make()
    assert mtef.scenario(YEAR, igr_change_pct=-20)['years'][0]['balance_change'] == '-30.00'          # IGR 150 x 20%
    assert mtef.scenario(YEAR, cost_change_pct=10)['years'][0]['balance_change'] == '-65.00'          # (450+150+50) x 10%


def test_a_scenario_changes_nothing_that_is_saved():
    make()
    before = MTEFProjection.objects.get(fiscal_year=YEAR)
    mtef.scenario(YEAR, oil_price_change_pct=-50, igr_change_pct=-50, cost_change_pct=50)
    after = MTEFProjection.objects.get(fiscal_year=YEAR)
    assert (after.rev_statutory, after.rev_igr, after.exp_personnel, after.fiscal_balance) == (
        before.rev_statutory, before.rev_igr, before.exp_personnel, before.fiscal_balance)


def test_no_shock_leaves_every_year_unchanged():
    make()
    y = mtef.scenario(YEAR)['years'][0]
    assert y['before'] == y['after'] and y['balance_change'] == '0.00' and y['newly_failing'] == []


# ── approval ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_compliant_framework_can_be_approved_and_records_who_and_when():
    p = make()
    mtef.approve(p, actor_name='A. Officer')
    p.refresh_from_db()
    assert p.status == 'approved' and p.approved_by == 'A. Officer' and p.approved_at is not None and p.override_reason == ''


def test_a_framework_that_breaks_a_rule_cannot_be_approved_without_a_reason():
    p = make(fin_domestic=D('0'), fin_external=D('0'))
    with pytest.raises(mtef.MTEFError, match='Fully financed') as err:
        mtef.approve(p)
    p.refresh_from_db()
    assert p.status == 'draft' and any(f.status == mtef.FAIL for f in err.value.findings)


def test_a_reason_lets_it_through_and_is_kept_on_the_record():
    p = make(fin_domestic=D('0'), fin_external=D('0'))
    mtef.approve(p, override_reason='Bridge financing agreed with the CBN', actor_name='A. Officer')
    p.refresh_from_db()
    assert p.status == 'approved' and 'CBN' in p.override_reason


def test_a_blank_reason_does_not_count():
    with pytest.raises(mtef.MTEFError):
        mtef.approve(make(fin_domestic=D('0'), fin_external=D('0')), override_reason='   ')


def test_warnings_alone_do_not_block_approval():
    p = make(exp_capital=D('300'), exp_overhead=D('250'))                # thin capital share is a warning, not a failure
    mtef.approve(p)
    assert p.status == 'approved'


def test_an_approved_framework_cannot_be_approved_again_and_reopening_needs_a_reason():
    p = make()
    mtef.approve(p)
    with pytest.raises(mtef.MTEFError, match='already approved'):
        mtef.approve(p)
    with pytest.raises(mtef.MTEFError, match='reason'):
        mtef.reopen(p, reason='')
    mtef.reopen(p, reason='Revenue forecast revised after the FAAC meeting')
    p.refresh_from_db()
    assert p.status == 'draft' and p.approved_by == '' and 'FAAC' in p.notes


def test_only_an_approved_framework_can_be_reopened():
    with pytest.raises(mtef.MTEFError, match='approved'):
        mtef.reopen(make(), reason='x')


# ── MDA ceilings and the envelope ─────────────────────────────────────────────────────────────────────────────

def test_without_a_framework_for_the_year_a_ceiling_is_not_held_to_anything():
    mtef.check_ceiling_fits(YEAR, personnel=999999, overhead=0, capital=0)


def test_ceilings_cannot_be_issued_from_an_unapproved_framework():
    make()
    with pytest.raises(mtef.MTEFError, match='not approved'):
        mtef.check_ceiling_fits(YEAR, personnel=10, overhead=10, capital=10)


def test_a_ceiling_inside_the_approved_envelope_is_allowed():
    mtef.approve(make())
    mtef.check_ceiling_fits(YEAR, personnel=450, overhead=150, capital=400)


def test_ceilings_together_cannot_exceed_the_envelope_for_their_type():
    mtef.approve(make())
    MDACeiling.objects.create(fiscal_year=YEAR, mda_name='Works', personnel_ceiling=D('300'))
    with pytest.raises(mtef.MTEFError, match=r'450\.00') as err:
        mtef.check_ceiling_fits(YEAR, personnel=200, overhead=0, capital=0)       # 300 + 200 = 500 > 450
    assert 'already allocated: 300.00' in str(err.value)


def test_editing_a_ceiling_does_not_count_its_old_value_against_itself():
    mtef.approve(make())
    c = MDACeiling.objects.create(fiscal_year=YEAR, mda_name='Works', personnel_ceiling=D('450'))
    mtef.check_ceiling_fits(YEAR, personnel=400, overhead=0, capital=0, exclude_pk=c.pk)


def test_the_framework_reports_headroom_and_overallocation():
    p = mtef.approve(make()) and MTEFProjection.objects.get(fiscal_year=YEAR)
    MDACeiling.objects.create(fiscal_year=YEAR, mda_name='Works', personnel_ceiling=D('500'), overhead_ceiling=D('50'), capital_ceiling=D('0'))
    rows = {r['type']: r for r in mtef.ceilings_against(p)}
    assert (rows['personnel']['over'], rows['personnel']['headroom']) == (True, '-50.00')
    assert (rows['overhead']['over'], rows['overhead']['headroom']) == (False, '100.00')


# ── the API ───────────────────────────────────────────────────────────────────────────────────────────────────

BASE = '/api/v1/budget-prep/mtef-projections/'


def payload(year=YEAR, **over):
    return {'fiscal_year': year, **{k: str(v) for k, v in {**HEALTHY, **over}.items()}}


def test_creating_a_year_through_the_api_computes_the_totals():
    _module(True)
    r = _client('admin').post(BASE, payload(), format='json')
    body = r.json()
    assert r.status_code == 201, body
    assert (body['total_revenue'], body['total_expenditure'], body['fiscal_balance'], body['unfinanced_gap']) == ('1100.00', '1250.00', '-150.00', '0.00')


def test_typed_in_totals_and_status_are_ignored():
    _module(True)
    c = _client('admin')
    made = c.post(BASE, payload(), format='json').json()
    r = c.patch(f"{BASE}{made['id']}/", {'aggregate_revenue': '1', 'fiscal_balance': '999', 'status': 'approved', 'approved_by': 'me'}, format='json')
    p = MTEFProjection.objects.get(pk=made['id'])
    assert r.status_code == 200 and (p.fiscal_balance, p.status, p.approved_by) == (D('-150'), 'draft', '')


def test_negative_money_and_silly_years_are_refused():
    _module(True)
    c = _client('admin')
    assert c.post(BASE, payload(rev_igr='-5'), format='json').status_code == 400
    assert c.post(BASE, payload(year=3000), format='json').status_code == 400
    assert c.post(BASE, payload(oil_sensitivity='5'), format='json').status_code == 400


def test_the_framework_endpoint_and_its_validation():
    _module(True)
    make()
    c = _client('admin')
    r = c.get(f'{BASE}framework/?base_year={YEAR}')
    assert r.status_code == 200 and r.json()['years'][0]['totals']['balance'] == '-150.00'
    assert c.get(f'{BASE}framework/').status_code == 400


def test_the_scenario_endpoint():
    _module(True)
    make()
    c = _client('admin')
    r = c.post(f'{BASE}scenario/', {'base_year': YEAR, 'oil_price_change_pct': -30}, format='json')
    assert r.status_code == 200 and r.json()['years'][0]['balance_change'] == '-240.00'
    assert c.post(f'{BASE}scenario/', {'base_year': YEAR, 'oil_price_change_pct': 'lots'}, format='json').status_code == 400
    assert c.post(f'{BASE}scenario/', {}, format='json').status_code == 400


def test_the_roll_forward_endpoint():
    _module(True)
    make()
    c = _client('admin')
    r = c.post(f'{BASE}roll-forward/', {'base_year': YEAR}, format='json')
    assert r.status_code == 200 and r.json() == {'created': [YEAR + 1, YEAR + 2], 'kept': []}
    assert c.post(f'{BASE}roll-forward/', {'base_year': 2099}, format='json').status_code == 400


def test_approve_and_reopen_through_the_api_with_the_lock_in_between():
    _module(True)
    c = _client('admin')
    made = c.post(BASE, payload(), format='json').json()
    assert c.post(f"{BASE}{made['id']}/approve/", {}, format='json').status_code == 200
    assert c.patch(f"{BASE}{made['id']}/", {'rev_igr': '1'}, format='json').status_code == 400          # locked
    assert c.delete(f"{BASE}{made['id']}/").status_code == 400
    assert c.post(f"{BASE}{made['id']}/reopen/", {}, format='json').status_code == 400                  # needs a reason
    assert c.post(f"{BASE}{made['id']}/reopen/", {'reason': 'Forecast revised'}, format='json').status_code == 200
    assert c.patch(f"{BASE}{made['id']}/", {'rev_igr': '160'}, format='json').status_code == 200        # editable again


def test_approving_a_failing_framework_returns_the_findings():
    _module(True)
    c = _client('admin')
    made = c.post(BASE, payload(fin_domestic='0', fin_external='0'), format='json').json()
    r = c.post(f"{BASE}{made['id']}/approve/", {}, format='json')
    assert r.status_code == 400 and any(f['rule'] == 'Fully financed' and f['status'] == 'fail' for f in r.json()['findings'])
    ok = c.post(f"{BASE}{made['id']}/approve/", {'override_reason': 'Agreed financing to follow'}, format='json')
    assert ok.status_code == 200


def test_approving_is_an_approvers_act():
    from core.permissions import IsApprover
    from budget_prep.views import MTEFProjectionViewSet

    def needs_approver(action):
        view = MTEFProjectionViewSet()
        view.action = action
        return any(isinstance(p, IsApprover) and p.perm_prefix == 'post' for p in view.get_permissions())

    assert needs_approver('approve') and needs_approver('reopen')
    assert not any(needs_approver(a) for a in ('list', 'create', 'framework', 'scenario', 'partial_update'))


def test_the_ceiling_api_is_held_to_the_approved_envelope():
    _module(True)
    c = _client('admin')
    made = c.post(BASE, payload(), format='json').json()
    ceiling = {'fiscal_year': YEAR, 'mda_name': 'Works', 'personnel_ceiling': '300', 'overhead_ceiling': '100', 'capital_ceiling': '200'}
    early = c.post('/api/v1/budget-prep/mda-ceilings/', ceiling, format='json')
    assert early.status_code == 400 and 'not approved' in str(early.json())
    c.post(f"{BASE}{made['id']}/approve/", {}, format='json')
    assert c.post('/api/v1/budget-prep/mda-ceilings/', ceiling, format='json').status_code == 201
    over = c.post('/api/v1/budget-prep/mda-ceilings/', {**ceiling, 'mda_name': 'Health', 'personnel_ceiling': '300'}, format='json')
    assert over.status_code == 400 and 'already allocated: 300.00' in str(over.json())


def test_policy_can_be_read_changed_and_changes_the_verdict():
    _module(True)
    c = _client('admin')
    assert c.get('/api/v1/budget-prep/mtef-policy/current/').json()['max_debt_service_pct'] == '30.00'
    assert c.patch('/api/v1/budget-prep/mtef-policy/current/', {'max_debt_service_pct': '10'}, format='json').status_code == 200
    assert c.patch('/api/v1/budget-prep/mtef-policy/current/', {'max_debt_service_pct': '500'}, format='json').status_code == 400
    make()
    year = c.get(f'{BASE}framework/?base_year={YEAR}').json()['years'][0]
    assert next(f for f in year['findings'] if f['rule'] == 'Debt service')['status'] == 'fail'


def test_module_off_refuses_the_mtef():
    _module(False)
    assert _client('admin').get(f'{BASE}framework/?base_year={YEAR}').status_code == 403
