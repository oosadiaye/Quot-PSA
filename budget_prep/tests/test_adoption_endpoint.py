"""The adopt-actuals endpoints: gated by the module switch, explicit about errors, and the preview writes nothing."""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from budget_prep.models import BudgetSubmission, SubmissionLine
from budget_prep.tests.test_adoption import MDA, YEAR, prior  # noqa: F401  (fixtures)
from budget_prep.tests.test_incorporation import dims  # noqa: F401  (fixture prior depends on)
from budget_prep.tests.test_incorporate_endpoint import DOMAIN, _client, _module

pytestmark = pytest.mark.django_db


@pytest.fixture
def draft(prior):  # noqa: F811
    return BudgetSubmission.objects.create(fiscal_year=YEAR, mda_name=MDA, stage='draft')


def adopt(sub):
    return f'/api/v1/budget-prep/submissions/{sub.pk}/adopt-actuals/'


def preview(sub, basis='outturn'):
    return f'/api/v1/budget-prep/submissions/{sub.pk}/adoption-preview/?basis={basis}'


def test_adopting_writes_audited_lines(draft):
    _module(True)
    r = _client('admin').post(adopt(draft), {'basis': 'outturn', 'growth_pct': 10}, format='json')
    assert r.status_code == 200, r.content
    body = r.json()
    assert (body['created'], body['source_year'], body['total_proposed']) == (2, YEAR - 1, '1375.00')   # (900+350) * 1.10
    assert set(draft.lines.values_list('adopted_basis', flat=True)) == {'outturn'}


def test_the_preview_shows_the_baseline_and_writes_nothing(draft):
    _module(True)
    r = _client('admin').get(preview(draft))
    assert r.status_code == 200
    assert r.json()['total'] == '1250.00' and {x['economic_code'] for x in r.json()['rows']} == {'21107700', '22107700'}
    assert draft.lines.count() == 0


def test_module_off_refuses_both(draft):
    _module(False)
    c = _client('admin')
    assert c.post(adopt(draft), {}, format='json').status_code == 403
    assert c.get(preview(draft)).status_code == 403
    assert draft.lines.count() == 0


def test_a_bad_basis_is_a_400_that_lists_the_choices(draft):
    _module(True)
    r = _client('admin').post(adopt(draft), {'basis': 'guess'}, format='json')
    assert r.status_code == 400 and r.json()['bases'] == ['outturn', 'appropriation', 'run_rate']


def test_a_non_numeric_adjustment_is_a_400_not_a_500(draft):
    _module(True)
    r = _client('admin').post(adopt(draft), {'growth_pct': 'lots'}, format='json')
    assert r.status_code == 400 and 'numbers' in r.json()['error']


def test_a_submitted_submission_cannot_be_overwritten(draft):
    _module(True)
    BudgetSubmission.objects.filter(pk=draft.pk).update(stage='submitted')
    SubmissionLine.objects.create(submission=draft, line_type='capital', proposed_amount=Decimal('5.00'))
    r = _client('admin').post(adopt(draft), {}, format='json')
    assert r.status_code == 400 and draft.lines.count() == 1


def test_anonymous_callers_are_turned_away(draft):
    _module(True)
    assert APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN).post(adopt(draft), {}, format='json').status_code in (401, 403)
