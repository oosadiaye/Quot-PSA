"""The budget calendar: a standard year can be seeded once, statuses follow the dates, and nothing someone edited is overwritten."""
from datetime import date, timedelta

import pytest
from django.utils import timezone

from budget_prep.models import BudgetMilestone, CallCircular
from budget_prep.services.calendar import STANDARD_STEPS, CalendarError, seed_standard_calendar, status_of
from budget_prep.tests.test_incorporate_endpoint import _client, _module

pytestmark = pytest.mark.django_db
YEAR = 2041


@pytest.fixture(autouse=True)
def clean(db, _route_to_pytest_schema):
    BudgetMilestone.objects.filter(fiscal_year=YEAR).delete()
    CallCircular.objects.filter(fiscal_year=YEAR).delete()


def circular(issue=date(2040, 9, 1), deadline=None):
    return CallCircular.objects.create(fiscal_year=YEAR, issue_date=issue, submission_deadline=deadline)


def milestone(due, done=None, **kw):
    return BudgetMilestone.objects.create(fiscal_year=YEAR, name=kw.pop('name', 'Step'), due_date=due, completed_on=done, **kw)


def test_seeding_counts_the_standard_steps_from_the_circular_date():
    circular(issue=date(2040, 9, 1))
    r = seed_standard_calendar(YEAR)
    rows = {m.std_key: m for m in BudgetMilestone.objects.filter(fiscal_year=YEAR)}
    assert r.created == len(STANDARD_STEPS) == len(rows)
    assert rows['call_circular'].due_date == date(2040, 9, 1)
    assert rows['enactment'].due_date == date(2040, 9, 1) + timedelta(days=185)


def test_the_circulars_own_deadline_is_the_submissions_date():
    circular(issue=date(2040, 9, 1), deadline=date(2040, 10, 20))
    seed_standard_calendar(YEAR)
    assert BudgetMilestone.objects.get(fiscal_year=YEAR, std_key='mda_submissions').due_date == date(2040, 10, 20)


def test_seeding_twice_creates_nothing_new_and_moves_no_date():
    circular()
    seed_standard_calendar(YEAR)
    edited = BudgetMilestone.objects.get(fiscal_year=YEAR, std_key='enactment')
    edited.due_date = date(2041, 3, 31)
    edited.save()
    again = seed_standard_calendar(YEAR)
    assert again.created == 0 and again.existing == len(STANDARD_STEPS)
    assert BudgetMilestone.objects.get(fiscal_year=YEAR, std_key='enactment').due_date == date(2041, 3, 31)


def test_a_missing_step_is_filled_in_without_touching_the_rest():
    circular()
    seed_standard_calendar(YEAR)
    BudgetMilestone.objects.filter(fiscal_year=YEAR, std_key='budget_review').delete()
    assert seed_standard_calendar(YEAR).created == 1


def test_without_a_circular_a_date_is_needed_and_asked_for():
    with pytest.raises(CalendarError, match='no call circular'):
        seed_standard_calendar(YEAR)
    assert seed_standard_calendar(YEAR, anchor=date(2040, 9, 1)).created == len(STANDARD_STEPS)


def test_steps_added_by_hand_do_not_collide_with_the_template():
    circular()
    milestone(date(2040, 9, 5), name='Custom A')
    milestone(date(2040, 9, 6), name='Custom B')
    seed_standard_calendar(YEAR)
    assert BudgetMilestone.objects.filter(fiscal_year=YEAR).count() == len(STANDARD_STEPS) + 2


@pytest.mark.parametrize('offset, done, expected', [
    (-1, None, 'overdue'), (0, None, 'due_soon'), (14, None, 'due_soon'), (15, None, 'upcoming'),
    (-30, date(2040, 1, 1), 'completed'),
])
def test_status_follows_the_dates(offset, done, expected):
    today = date(2040, 6, 15)
    assert status_of(milestone(today + timedelta(days=offset), done), today) == expected


# --- API ----------------------------------------------------------------------------------------------------

def test_seed_endpoint_and_upcoming_list():
    _module(True)
    c = _client('admin')
    circular(issue=timezone.localdate() - timedelta(days=50))
    r = c.post('/api/v1/budget-prep/milestones/seed-standard/', {'fiscal_year': YEAR}, format='json')
    assert r.status_code == 200 and r.json()['created'] == len(STANDARD_STEPS)
    results = c.get('/api/v1/budget-prep/milestones/upcoming/?days=10').json()
    assert results and all(x['status'] in ('overdue', 'due_soon') for x in results)
    assert [x['due_date'] for x in results] == sorted(x['due_date'] for x in results)


def test_seed_endpoint_explains_a_missing_circular_and_bad_input():
    _module(True)
    c = _client('admin')
    assert 'no call circular' in c.post('/api/v1/budget-prep/milestones/seed-standard/', {'fiscal_year': YEAR}, format='json').json()['error']
    assert c.post('/api/v1/budget-prep/milestones/seed-standard/', {}, format='json').status_code == 400
    assert c.post('/api/v1/budget-prep/milestones/seed-standard/', {'fiscal_year': YEAR, 'anchor_date': 'soon'}, format='json').status_code == 400


def test_complete_endpoint_marks_a_step_done():
    _module(True)
    m = milestone(timezone.localdate() - timedelta(days=3))
    r = _client('admin').post(f'/api/v1/budget-prep/milestones/{m.pk}/complete/', {}, format='json')
    body = r.json()
    assert r.status_code == 200 and body['status'] == 'completed' and body['days_to_due'] is None


def test_module_off_refuses_the_calendar():
    _module(False)
    assert _client('admin').get('/api/v1/budget-prep/milestones/').status_code == 403
