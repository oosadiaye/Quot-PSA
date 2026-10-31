"""Adopt actuals to plan: the baseline comes from real figures, the adjustment is explicit, and nothing typed by hand is lost."""
from datetime import date
from decimal import Decimal

import pytest

from accounting.models.advanced import FiscalYear
from budget.models import Appropriation
from budget_prep.models import BudgetSubmission, SubmissionLine
from budget_prep.services.adoption import AdoptionError, adopt_actuals
from budget_prep.tests.test_incorporation import YEAR, dims  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db
SOURCE = YEAR - 1
MDA = 'Prep Test MDA'


@pytest.fixture
def prior(dims):  # noqa: F811
    """Last year's books: personnel (21...) and overhead (22...) appropriations with different spend."""
    from accounting.models.gl import Account
    fy, _ = FiscalYear.objects.get_or_create(
        year=SOURCE, defaults={'name': f'FY{SOURCE}', 'start_date': date(SOURCE, 1, 1), 'end_date': date(SOURCE, 12, 31)})
    FiscalYear.objects.filter(pk=fy.pk).update(start_date=date(SOURCE, 1, 1), end_date=date(SOURCE, 12, 31))
    salaries, _ = Account.objects.get_or_create(code='21107700', defaults={'name': 'Prep Salaries', 'account_type': 'Expense'})
    Appropriation.objects.filter(fiscal_year=fy, administrative=dims['admin']).delete()

    def make(account, approved, spent, status='ACTIVE'):
        return Appropriation.objects.create(
            fiscal_year=fy, administrative=dims['admin'], economic=account, functional=dims['func'],
            programme=dims['prog'], fund=dims['fund'], amount_approved=Decimal(approved), status=status,
            appropriation_type='ORIGINAL', cached_total_expended=Decimal(spent))

    make(salaries, '1000.00', '900.00')
    make(dims['econ'], '500.00', '350.00')
    return dims


def sub(stage='draft', mda=MDA):
    return BudgetSubmission.objects.create(fiscal_year=YEAR, mda_name=mda, stage=stage)


def by_code(s):
    return {l.economic.code: l for l in s.lines.select_related('economic')}


def test_outturn_is_what_was_actually_spent(prior):
    s = sub()
    r = adopt_actuals(s, basis='outturn')
    lines = by_code(s)
    assert (r.created, r.source_year) == (2, SOURCE)
    assert lines['21107700'].proposed_amount == Decimal('900.00') and lines['22107700'].proposed_amount == Decimal('350.00')


def test_appropriation_basis_uses_the_approved_figure(prior):
    s = sub()
    adopt_actuals(s, basis='appropriation')
    assert by_code(s)['21107700'].proposed_amount == Decimal('1000.00')


def test_run_rate_annualises_part_year_spending(prior):
    s = sub()
    adopt_actuals(s, basis='run_rate', as_of=date(SOURCE, 7, 2))      # 183 of 365 days elapsed
    got = by_code(s)['21107700'].proposed_amount
    assert Decimal('1790.00') < got < Decimal('1800.00')               # 900 / (183/365) ~= 1795


def test_run_rate_of_a_finished_year_is_just_the_outturn(prior):
    s = sub()
    adopt_actuals(s, basis='run_rate', as_of=date(YEAR, 6, 1))
    assert by_code(s)['21107700'].proposed_amount == Decimal('900.00')


def test_overall_growth_and_a_longer_prefix_override(prior):
    s = sub()
    adopt_actuals(s, basis='outturn', growth_pct=10, class_adjustments={'2': 3, '21': 5, '2210': 0})
    lines = by_code(s)
    assert lines['21107700'].proposed_amount == Decimal('945.00') and lines['21107700'].adjustment_pct == Decimal('5')
    assert lines['22107700'].proposed_amount == Decimal('350.00')     # '2210' beats both '2' and the overall 10 %; '21' beats '2'


def test_each_line_records_where_its_number_came_from(prior):
    s = sub()
    adopt_actuals(s, basis='outturn', growth_pct=10)
    line = by_code(s)['21107700']
    assert (line.adopted_basis, line.baseline_amount, line.adjustment_pct) == ('outturn', Decimal('900.00'), Decimal('10'))
    assert line.proposed_amount == Decimal('990.00') and line.line_type == 'personnel'


def test_re_adopting_replaces_adopted_lines_but_keeps_hand_entered_ones(prior):
    s = sub()
    mine = SubmissionLine.objects.create(submission=s, line_type='capital', proposed_amount=Decimal('77.00'), description='mine')
    adopt_actuals(s, basis='outturn')
    r = adopt_actuals(s, basis='appropriation')
    assert r.replaced == 2 and s.lines.count() == 3
    assert SubmissionLine.objects.get(pk=mine.pk).proposed_amount == Decimal('77.00')


def test_submission_totals_follow_the_lines(prior):
    s = sub()
    SubmissionLine.objects.create(submission=s, line_type='capital', proposed_amount=Decimal('77.00'))
    adopt_actuals(s, basis='outturn')
    s.refresh_from_db()
    assert (s.total_personnel, s.total_overhead, s.total_capital) == (Decimal('900.00'), Decimal('350.00'), Decimal('77.00'))


def test_a_draft_proposal_is_not_an_actual(prior):
    Appropriation.objects.filter(economic__code='22107700').update(status='DRAFT')
    s = sub()
    r = adopt_actuals(s, basis='outturn')
    assert r.created == 1 and '22107700' not in by_code(s)


def test_a_submission_already_sent_in_cannot_be_overwritten(prior):
    with pytest.raises(AdoptionError, match='draft or sent back'):
        adopt_actuals(sub(stage='submitted'), basis='outturn')


def test_an_unknown_mda_or_year_is_explained_not_empty(prior):
    with pytest.raises(AdoptionError, match='No approved appropriations'):
        adopt_actuals(sub(mda='No Such MDA'), basis='outturn')
    with pytest.raises(AdoptionError, match='No fiscal year'):
        adopt_actuals(BudgetSubmission.objects.create(fiscal_year=2090, mda_name=MDA), basis='outturn')


def test_an_unknown_basis_is_refused(prior):
    with pytest.raises(AdoptionError, match='Unknown basis'):
        adopt_actuals(sub(), basis='guess')
