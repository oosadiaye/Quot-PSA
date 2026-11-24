"""MDA ceilings: the check is made from the lines, going over needs a recorded reason, and the stage dropdown is no way round it."""
from decimal import Decimal

import pytest

from budget_prep.models import BudgetSubmission, MDACeiling, ReviewComment, SubmissionLine
from budget_prep.services.ceilings import SubmissionError, check_ceiling, submit_submission
from budget_prep.tests.test_incorporate_endpoint import _client, _module
from budget_prep.tests.test_incorporation import YEAR, dims  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db
MDA = 'Prep Test MDA'


def ceiling(personnel='1000', overhead='500', capital='0', mda=MDA):
    MDACeiling.objects.filter(fiscal_year=YEAR).delete()
    return MDACeiling.objects.create(
        fiscal_year=YEAR, mda_name=mda, personnel_ceiling=Decimal(personnel),
        overhead_ceiling=Decimal(overhead), capital_ceiling=Decimal(capital))


def sub(stage='draft'):
    return BudgetSubmission.objects.create(fiscal_year=YEAR, mda_name=MDA, stage=stage)


def line(s, kind, amount):
    return SubmissionLine.objects.create(submission=s, line_type=kind, proposed_amount=Decimal(amount))


def test_a_submission_within_its_ceilings_goes_through(dims):  # noqa: F811
    ceiling()
    s = sub()
    line(s, 'personnel', '900')
    line(s, 'overhead', '500')
    check = submit_submission(s)
    s.refresh_from_db()
    assert check.ok and s.stage == 'submitted' and s.submitted_at is not None
    assert (s.total_personnel, s.total_overhead) == (Decimal('900'), Decimal('500'))


def test_going_over_is_refused_and_says_by_how_much(dims):  # noqa: F811
    ceiling()
    s = sub()
    line(s, 'personnel', '1250')
    with pytest.raises(SubmissionError, match='personnel is over by 250.00') as err:
        submit_submission(s)
    assert [r.line_type for r in err.value.check.exceeded] == ['personnel']
    s.refresh_from_db()
    assert s.stage == 'draft' and s.submitted_at is None


def test_a_reason_lets_it_through_and_is_kept_for_the_reviewer(dims):  # noqa: F811
    ceiling()
    s = sub()
    line(s, 'personnel', '1250')
    submit_submission(s, override_reason='Wage award agreed after the circular', actor_name='A. Officer')
    s.refresh_from_db()
    note = ReviewComment.objects.get(submission=s)
    assert s.stage == 'submitted'
    assert note.action_required and 'Wage award' in note.comment and '1,250.00' in note.comment and note.commented_by == 'A. Officer'


def test_a_blank_reason_does_not_count(dims):  # noqa: F811
    ceiling()
    s = sub()
    line(s, 'personnel', '1250')
    with pytest.raises(SubmissionError):
        submit_submission(s, override_reason='   ')


def test_the_check_reads_the_lines_not_the_typed_totals(dims):  # noqa: F811
    ceiling()
    s = sub()
    line(s, 'personnel', '1250')
    BudgetSubmission.objects.filter(pk=s.pk).update(total_personnel=Decimal('1'))     # a stale or dishonest stored total
    assert not check_ceiling(s).ok


def test_an_mda_with_no_ceiling_has_nothing_to_enforce(dims):  # noqa: F811
    MDACeiling.objects.filter(fiscal_year=YEAR).delete()
    s = sub()
    line(s, 'capital', '999999')
    check = check_ceiling(s)
    assert not check.has_ceiling and check.ok
    submit_submission(s)


def test_the_mda_is_matched_ignoring_case(dims):  # noqa: F811
    ceiling(mda=MDA.upper())
    s = sub()
    line(s, 'personnel', '1250')
    assert not check_ceiling(s).ok


def test_only_draft_or_sent_back_submissions_can_be_submitted(dims):  # noqa: F811
    ceiling()
    s = sub(stage='in_review')
    line(s, 'personnel', '1')
    with pytest.raises(SubmissionError, match='draft or sent-back'):
        submit_submission(s)


def test_an_empty_submission_is_refused(dims):  # noqa: F811
    ceiling()
    with pytest.raises(SubmissionError, match='no lines'):
        submit_submission(sub())


# --- through the API -----------------------------------------------------------------------------------------

def url(s, action):
    return f'/api/v1/budget-prep/submissions/{s.pk}/{action}/'


def test_the_submit_endpoint_refuses_with_the_per_type_detail(dims):  # noqa: F811
    _module(True)
    ceiling()
    s = sub()
    line(s, 'overhead', '700')
    r = _client('admin').post(url(s, 'submit'), {}, format='json')
    body = r.json()
    assert r.status_code == 400
    assert 'Over the MDA ceiling' in body['error']
    over = [x for x in body['check']['rows'] if x['line_type'] == 'overhead'][0]
    assert (over['proposed'], over['ceiling'], over['over_by']) == ('700.00', '500.00', '200.00')


def test_the_submit_endpoint_accepts_a_reason(dims):  # noqa: F811
    _module(True)
    ceiling()
    s = sub()
    line(s, 'overhead', '700')
    r = _client('admin').post(url(s, 'submit'), {'override_reason': 'Flood response'}, format='json')
    assert r.status_code == 200 and r.json()['stage'] == 'submitted'


def test_ceiling_check_endpoint_writes_nothing(dims):  # noqa: F811
    _module(True)
    ceiling()
    s = sub()
    line(s, 'overhead', '700')
    r = _client('admin').get(url(s, 'ceiling-check'))
    assert r.status_code == 200 and r.json()['ok'] is False
    s.refresh_from_db()
    assert s.stage == 'draft'


def test_the_stage_dropdown_cannot_be_used_to_skip_the_check(dims):  # noqa: F811
    _module(True)
    ceiling()
    s = sub()
    line(s, 'overhead', '700')
    r = _client('admin').patch(f'/api/v1/budget-prep/submissions/{s.pk}/', {'stage': 'submitted'}, format='json')
    assert r.status_code == 400 and 'Use Submit' in str(r.json())
    s.refresh_from_db()
    assert s.stage == 'draft'


def test_other_stage_moves_are_untouched(dims):  # noqa: F811
    _module(True)
    s = sub(stage='submitted')
    r = _client('admin').patch(f'/api/v1/budget-prep/submissions/{s.pk}/', {'stage': 'in_review'}, format='json')
    assert r.status_code == 200


def test_totals_follow_line_changes_made_through_the_api(dims):  # noqa: F811
    _module(True)
    s = sub()
    c = _client('admin')
    made = c.post('/api/v1/budget-prep/submission-lines/', {'submission': s.pk, 'line_type': 'capital', 'proposed_amount': '40.00'}, format='json')
    assert made.status_code == 201, made.content
    s.refresh_from_db()
    assert s.total_capital == Decimal('40.00')
    c.delete(f"/api/v1/budget-prep/submission-lines/{made.json()['id']}/")
    s.refresh_from_db()
    assert s.total_capital == Decimal('0')


def test_the_stored_totals_cannot_be_typed_in(dims):  # noqa: F811
    _module(True)
    s = sub()
    r = _client('admin').patch(f'/api/v1/budget-prep/submissions/{s.pk}/', {'total_personnel': '5.00'}, format='json')
    s.refresh_from_db()
    assert r.status_code == 200 and s.total_personnel == Decimal('0')


def test_module_off_refuses_submit(dims):  # noqa: F811
    _module(False)
    s = sub()
    line(s, 'personnel', '1')
    assert _client('admin').post(url(s, 'submit'), {}, format='json').status_code == 403
