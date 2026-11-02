"""Supplementary budgets: a separate line with its own economic code, justified, handed over as SUPPLEMENTARY, and reportable."""
from decimal import Decimal

import pytest

from accounting.models.gl import Account
from budget.models import Appropriation
from budget_prep.models import BudgetSubmission, MDACeiling, SubmissionLine
from budget_prep.services.adoption import AdoptionError, adopt_actuals
from budget_prep.services.ceilings import SubmissionError, check_ceiling, submit_submission
from budget_prep.services.incorporation import IncorporationError, incorporate_submission
from budget_prep.services.supplementary import supplementary_report
from budget_prep.tests.test_incorporate_endpoint import _client, _module
from budget_prep.tests.test_incorporation import YEAR, dims  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db
MDA = 'Prep Test MDA'


def sup(kind='supplementary', stage='draft', justification='Flood response'):
    return BudgetSubmission.objects.create(fiscal_year=YEAR, mda_name=MDA, kind=kind, stage=stage, justification=justification)


def line(s, d, amount, econ='econ2', fund=True):
    return SubmissionLine.objects.create(
        submission=s, line_type='overhead', administrative=d['admin'], economic=d[econ], functional=d['func'],
        programme=d['prog'], fund=d['fund'] if fund else None, proposed_amount=Decimal(amount))


def existing(d, status='ACTIVE', econ='econ', amount='1000', type_='ORIGINAL'):
    return Appropriation.objects.create(
        fiscal_year=d['fy'], administrative=d['admin'], economic=d[econ], functional=d['func'], programme=d['prog'],
        fund=d['fund'], amount_approved=Decimal(amount), status=status, appropriation_type=type_)


@pytest.fixture(autouse=True)
def clean(dims):  # noqa: F811
    Appropriation.objects.filter(fiscal_year=dims['fy'], administrative=dims['admin']).delete()


def test_a_supplementary_is_handed_over_as_supplementary_appropriations(dims):  # noqa: F811
    s = sup(stage='incorporated')
    line(s, dims, '250.00')
    incorporate_submission(s)
    a = Appropriation.objects.get(source_reference=f'submission:{s.pk}')
    assert (a.appropriation_type, a.status, a.amount_approved, a.economic_id) == ('SUPPLEMENTARY', 'DRAFT', Decimal('250.00'), dims['econ2'].pk)


def test_an_original_submission_still_makes_original_appropriations(dims):  # noqa: F811
    s = sup(kind='original', stage='incorporated')
    line(s, dims, '250.00')
    incorporate_submission(s)
    assert Appropriation.objects.get(source_reference=f'submission:{s.pk}').appropriation_type == 'ORIGINAL'


def test_the_user_chooses_the_economic_code_but_cannot_land_on_an_existing_line(dims):  # noqa: F811
    existing(dims, econ='econ2', status='ACTIVE')
    s = sup(stage='incorporated')
    bad = line(s, dims, '250.00', econ='econ2')
    with pytest.raises(IncorporationError, match='existing appropriation') as err:
        incorporate_submission(s)
    assert err.value.lines[0]['line'] == bad.pk and 'different economic code' in err.value.lines[0]['conflict']
    assert not Appropriation.objects.filter(source_reference=f'submission:{s.pk}').exists()


def test_a_closed_line_does_not_block_a_new_supplementary(dims):  # noqa: F811
    existing(dims, econ='econ2', status='CLOSED')
    s = sup(stage='incorporated')
    line(s, dims, '250.00', econ='econ2')
    incorporate_submission(s)
    assert Appropriation.objects.filter(source_reference=f'submission:{s.pk}').count() == 1


def test_running_the_hand_over_again_does_not_collide_with_its_own_drafts(dims):  # noqa: F811
    s = sup(stage='incorporated')
    line(s, dims, '250.00')
    incorporate_submission(s)
    again = incorporate_submission(s)
    assert (again.created, again.updated) == (0, 1)


def test_a_supplementary_needs_a_justification_to_be_submitted(dims):  # noqa: F811
    s = sup(justification='   ')
    line(s, dims, '10.00')
    with pytest.raises(SubmissionError, match='justification'):
        submit_submission(s)
    BudgetSubmission.objects.filter(pk=s.pk).update(justification='Emergency')
    s.refresh_from_db()
    submit_submission(s)


def test_original_ceilings_do_not_apply_to_a_supplementary(dims):  # noqa: F811
    MDACeiling.objects.filter(fiscal_year=YEAR).delete()
    MDACeiling.objects.create(fiscal_year=YEAR, mda_name=MDA, personnel_ceiling=1, overhead_ceiling=1, capital_ceiling=1)
    s = sup()
    line(s, dims, '999999.00')
    check = check_ceiling(s)
    assert check.ok and not check.has_ceiling
    assert check_ceiling(sup(kind='original', justification='')).has_ceiling


def test_adopting_last_years_figures_is_for_the_original_budget_only(dims):  # noqa: F811
    with pytest.raises(AdoptionError, match='not a supplementary'):
        adopt_actuals(sup())


# --- the report ----------------------------------------------------------------------------------------------

def test_the_report_groups_supplementaries_by_stage_against_the_original(dims):  # noqa: F811
    existing(dims, status='ACTIVE', amount='1000.00')                                      # the original appropriation
    existing(dims, status='DRAFT', econ='econ2', amount='100.00', type_='SUPPLEMENTARY')
    other = Account.objects.get_or_create(code='22107900', defaults={'name': 'Prep Overhead 3', 'account_type': 'Expense'})[0]
    Appropriation.objects.create(
        fiscal_year=dims['fy'], administrative=dims['admin'], economic=other, functional=dims['func'], programme=dims['prog'],
        fund=dims['fund'], amount_approved=Decimal('150.00'), status='ENACTED', appropriation_type='SUPPLEMENTARY',
        source_module='budget_prep', source_reference='submission:1')
    report = supplementary_report(YEAR)
    row = [r for r in report['rows'] if r['mda'] == dims['admin'].name][0]
    assert (row['lines'], row['lines_from_prep']) == (2, 1)
    assert (row['total'], row['draft'], row['enacted'], row['before_legislature']) == ('250.00', '100.00', '150.00', '0.00')
    assert row['original_appropriation'] == '1000.00' and row['percent_of_original'] == '25.00'
    assert report['totals']['total'] == '250.00' and report['totals']['lines'] == 2


def test_the_report_includes_supplementaries_entered_directly_in_budget(dims):  # noqa: F811
    existing(dims, status='SUBMITTED', econ='econ2', amount='40.00', type_='SUPPLEMENTARY')
    row = [r for r in supplementary_report(YEAR)['rows'] if r['mda'] == dims['admin'].name][0]
    assert (row['lines'], row['lines_from_prep'], row['before_legislature']) == (1, 0, '40.00')


def test_an_mda_with_no_original_has_no_percentage_not_a_division_error(dims):  # noqa: F811
    existing(dims, status='DRAFT', econ='econ2', amount='40.00', type_='SUPPLEMENTARY')
    row = [r for r in supplementary_report(YEAR)['rows'] if r['mda'] == dims['admin'].name][0]
    assert row['percent_of_original'] is None


def test_other_years_are_not_counted(dims):  # noqa: F811
    existing(dims, status='DRAFT', econ='econ2', amount='40.00', type_='SUPPLEMENTARY')
    assert supplementary_report(YEAR + 5)['rows'] == []


# --- API ------------------------------------------------------------------------------------------------------

def test_report_endpoint_and_its_validation(dims):  # noqa: F811
    _module(True)
    existing(dims, status='DRAFT', econ='econ2', amount='40.00', type_='SUPPLEMENTARY')
    c = _client('admin')
    ok = c.get(f'/api/v1/budget-prep/submissions/supplementary-report/?fiscal_year={YEAR}')
    assert ok.status_code == 200 and ok.json()['totals']['total'] == '40.00'
    assert c.get('/api/v1/budget-prep/submissions/supplementary-report/').status_code == 400


def test_report_endpoint_is_gated_by_the_module(dims):  # noqa: F811
    _module(False)
    assert _client('admin').get(f'/api/v1/budget-prep/submissions/supplementary-report/?fiscal_year={YEAR}').status_code == 403


def test_kind_and_justification_are_part_of_the_submission_api(dims):  # noqa: F811
    _module(True)
    r = _client('admin').post('/api/v1/budget-prep/submissions/', {
        'fiscal_year': YEAR, 'mda_name': MDA, 'kind': 'supplementary', 'justification': 'Flood response'}, format='json')
    assert r.status_code == 201 and r.json()['kind'] == 'supplementary'
