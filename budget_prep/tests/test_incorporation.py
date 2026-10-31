"""Submission -> DRAFT appropriation hand-off: aggregation, idempotence, and the line it will not cross."""
from decimal import Decimal

import pytest

from accounting.models.advanced import FiscalYear
from accounting.models.gl import Account
from accounting.models.ncoa import (
    AdministrativeSegment, FunctionalSegment, FundSegment, ProgrammeSegment,
)
from budget.models import Appropriation
from budget_prep.models import BudgetSubmission, SubmissionLine
from budget_prep.services.incorporation import IncorporationError, incorporate_submission

pytestmark = pytest.mark.django_db
YEAR = 2037


@pytest.fixture
def dims(db):
    fy, _ = FiscalYear.objects.get_or_create(year=YEAR, defaults={'name': f'FY{YEAR}', 'is_active': False})
    admin, _ = AdministrativeSegment.objects.get_or_create(
        code='097000000000', defaults={'name': 'Prep Test MDA', 'level': 'ORGANIZATION', 'sector_code': '09'})
    econ, _ = Account.objects.get_or_create(code='22107700', defaults={'name': 'Prep Overhead', 'account_type': 'Expense'})
    econ2, _ = Account.objects.get_or_create(code='22107800', defaults={'name': 'Prep Overhead 2', 'account_type': 'Expense'})
    func, _ = FunctionalSegment.objects.get_or_create(code='70177', defaults={'name': 'Prep Function', 'division_code': '701'})
    prog, _ = ProgrammeSegment.objects.get_or_create(
        code='09770000000000', defaults={'name': 'Prep Programme', 'policy_code': '09', 'programme_code': '09'})
    prog2, _ = ProgrammeSegment.objects.get_or_create(
        code='09780000000000', defaults={'name': 'Prep Programme 2', 'policy_code': '09', 'programme_code': '09'})
    fund, _ = FundSegment.objects.get_or_create(code='09700', defaults={'name': 'Prep Test Fund', 'main_fund_code': '09'})
    return dict(fy=fy, admin=admin, econ=econ, econ2=econ2, func=func, prog=prog, prog2=prog2, fund=fund)


def submission(stage='incorporated'):
    return BudgetSubmission.objects.create(fiscal_year=YEAR, mda_name='Prep Test MDA', stage=stage)


def line(sub, d, amount, *, econ='econ', prog='prog', fund=True):
    return SubmissionLine.objects.create(
        submission=sub, line_type='overhead', administrative=d['admin'], economic=d[econ], functional=d['func'],
        programme=d[prog], fund=d['fund'] if fund else None, proposed_amount=Decimal(amount))


def drafts(sub):
    return Appropriation.objects.filter(source_module='budget_prep', source_reference=f'submission:{sub.pk}')


def test_lines_with_the_same_key_become_one_draft_appropriation(dims):
    sub = submission()
    line(sub, dims, '100.00')
    line(sub, dims, '50.00')
    result = incorporate_submission(sub)
    assert (result.created, result.updated) == (1, 0)
    a = drafts(sub).get()
    assert a.status == 'DRAFT' and a.appropriation_type == 'ORIGINAL' and a.amount_approved == Decimal('150.00')


def test_different_economic_codes_stay_separate(dims):
    sub = submission()
    line(sub, dims, '100.00')
    line(sub, dims, '40.00', econ='econ2')
    incorporate_submission(sub)
    assert sorted(a.amount_approved for a in drafts(sub)) == [Decimal('40.00'), Decimal('100.00')]


def test_running_it_twice_updates_in_place(dims):
    sub = submission()
    first = line(sub, dims, '100.00')
    incorporate_submission(sub)
    first.proposed_amount = Decimal('120.00')
    first.save()
    result = incorporate_submission(sub)
    assert (result.created, result.updated) == (0, 1)
    assert drafts(sub).count() == 1 and drafts(sub).get().amount_approved == Decimal('120.00')


def test_a_line_removed_upstream_drops_its_draft(dims):
    sub = submission()
    line(sub, dims, '100.00')
    gone = line(sub, dims, '40.00', econ='econ2')
    incorporate_submission(sub)
    gone.delete()
    result = incorporate_submission(sub)
    assert result.removed == 1 and drafts(sub).count() == 1


def test_a_draft_taken_over_by_the_legislature_is_never_touched(dims):
    sub = submission()
    line(sub, dims, '100.00')
    incorporate_submission(sub)
    Appropriation.objects.filter(pk=drafts(sub).get().pk).update(status='SUBMITTED')
    with pytest.raises(IncorporationError, match='past Draft'):
        incorporate_submission(sub)
    assert drafts(sub).get().amount_approved == Decimal('100.00')


def test_only_an_incorporated_submission_can_be_handed_off(dims):
    sub = submission(stage='in_review')
    line(sub, dims, '100.00')
    with pytest.raises(IncorporationError, match='incorporated'):
        incorporate_submission(sub)
    assert drafts(sub).count() == 0


def test_a_line_without_a_fund_is_named_not_guessed(dims):
    sub = submission()
    bad = line(sub, dims, '100.00', fund=False)
    with pytest.raises(IncorporationError) as err:
        incorporate_submission(sub)
    assert err.value.lines == [{'line': bad.pk, 'missing': ['fund']}]
    assert drafts(sub).count() == 0


def test_a_caller_default_fills_a_missing_fund(dims):
    sub = submission()
    line(sub, dims, '100.00', fund=False)
    incorporate_submission(sub, defaults={'fund': dims['fund'].pk})
    assert drafts(sub).count() == 1


def test_disagreeing_programmes_in_one_key_are_refused(dims):
    sub = submission()
    line(sub, dims, '100.00')
    line(sub, dims, '50.00', prog='prog2')
    with pytest.raises(IncorporationError, match='cannot be handed off'):
        incorporate_submission(sub)


def test_a_missing_fiscal_year_is_explained(dims):
    sub = BudgetSubmission.objects.create(fiscal_year=2099, mda_name='X', stage='incorporated')
    line(sub, dims, '10.00')
    with pytest.raises(IncorporationError, match='fiscal year 2099'):
        incorporate_submission(sub)
