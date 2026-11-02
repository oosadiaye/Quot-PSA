"""The budget calendar: a standard set of steps for a year, and the status of each against today's date.

The standard template follows the usual Nigerian budget cycle, counted in days from the date the call circular is
issued. It is only a starting point: seeding creates the steps, after which every date is the Budget Office's to edit,
and seeding again never moves or duplicates one.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from budget_prep.models import BudgetMilestone, CallCircular

DUE_SOON_DAYS = 14

#: (std_key, name, days after the call circular is issued)
STANDARD_STEPS: tuple[tuple[str, str, int], ...] = (
    ('call_circular', 'Budget call circular issued', 0),
    ('ceilings_issued', 'MDA ceilings communicated', 10),
    ('mda_submissions', 'MDA budget submissions due', 45),
    ('budget_review', 'Budget Office review and consolidation', 75),
    ('budget_defence', 'MDA budget defence sessions complete', 100),
    ('executive_approval', 'Executive Council approves the draft budget', 115),
    ('legislature_submission', 'Appropriation bill sent to the legislature', 125),
    ('enactment', 'Appropriation law enacted', 185),
    ('warrants_released', 'First warrants released', 200),
)

COMPLETED, OVERDUE, DUE_SOON, UPCOMING = 'completed', 'overdue', 'due_soon', 'upcoming'


class CalendarError(Exception):
    pass


@dataclass
class SeedResult:
    created: int
    existing: int
    anchor: date


def status_of(milestone: BudgetMilestone, today: date) -> str:
    if milestone.completed_on:
        return COMPLETED
    if milestone.due_date < today:
        return OVERDUE
    if (milestone.due_date - today).days <= DUE_SOON_DAYS:
        return DUE_SOON
    return UPCOMING


def seed_standard_calendar(fiscal_year: int, *, anchor: date | None = None) -> SeedResult:
    """Create the standard steps that this year does not have yet. Idempotent; never changes an existing step."""
    circular = CallCircular.objects.filter(fiscal_year=fiscal_year).order_by('-pk').first()
    anchor = anchor or (circular.issue_date if circular else None)
    if anchor is None:
        raise CalendarError(
            f'There is no call circular for {fiscal_year} to count from. Give the date the circular is (or was) issued.')
    existing = set(BudgetMilestone.objects.filter(fiscal_year=fiscal_year).exclude(std_key='')
                   .values_list('std_key', flat=True))
    created = 0
    for order, (key, name, offset) in enumerate(STANDARD_STEPS):
        if key in existing:
            continue
        due = anchor + timedelta(days=offset)
        # The circular's own deadline is the real date for the submissions step.
        if key == 'mda_submissions' and circular and circular.submission_deadline:
            due = circular.submission_deadline
        BudgetMilestone.objects.create(fiscal_year=fiscal_year, sequence=order, name=name, due_date=due, std_key=key)
        created += 1
    return SeedResult(created=created, existing=len(existing), anchor=anchor)
