"""A posting charges the most specific budget line that covers it.

``find_matching_appropriation`` walks up the GL account's parent chain so
that spending on an account with no line of its own is still controlled
by an ancestor's. That roll-up is correct and necessary. What it must not
do is reach past a line that fits.

It did. Every ancestor went into one ``economic__in`` list and the first
row won, with no ordering by specificity — so the winner was whatever the
model's default ordering produced, which is ``economic`` foreign-key id.
Accounts are seeded parent before child, so a parent's id is always the
lower one: in this chart all seventy child accounts have a lower-id
parent. The parent therefore won every time both had a line.

Concretely, on the data this was found in: a posting to 23100100
Acquisition of Land, which has its own 90,000,000 line, consumed the
23000000 Capital Expenditure line of 2,000,000 instead. Two failures in
one. The line that should have been charged never depletes, so available
budget reads high and over-commitment is permitted. And a small parent
line is exhausted by spending that is not its own, so legitimate postings
against it are refused.

Neither shows up as an error. Both sides look like ordinary numbers.
"""
from __future__ import annotations

from decimal import Decimal

import pytest


pytestmark = pytest.mark.django_db


@pytest.fixture
def chart(db):
    """A parent account with a child, and the dimensions a line needs."""
    from accounting.models.advanced import FiscalYear
    from accounting.models.gl import Account, Fund, MDA
    from accounting.models.ncoa import (
        AdministrativeSegment, FunctionalSegment, ProgrammeSegment,
        FundSegment, GeographicSegment,
    )

    fy, _ = FiscalYear.objects.get_or_create(
        year=2033, defaults={'name': 'FY2033', 'is_active': False},
    )
    # Parent created first, so its id is the lower one — the very
    # condition that made the old ordering pick it.
    parent, _ = Account.objects.get_or_create(
        code='23000077',
        defaults={'name': 'Match Parent', 'account_type': 'Expense'},
    )
    child, _ = Account.objects.get_or_create(
        code='23100077',
        defaults={'name': 'Match Child', 'account_type': 'Expense',
                  'parent': parent},
    )
    if child.parent_id != parent.pk:
        child.parent = parent
        child.save(update_fields=['parent'])

    legacy_mda, _ = MDA.objects.get_or_create(
        code='077000000000', defaults={'name': 'Match MDA'},
    )
    legacy_fund, _ = Fund.objects.get_or_create(
        code='07700', defaults={'name': 'Match Fund'},
    )
    admin, _ = AdministrativeSegment.objects.get_or_create(
        code='077000000000',
        defaults={'name': 'Match MDA', 'level': 'ORGANIZATION',
                  'sector_code': '07', 'legacy_mda': legacy_mda},
    )
    if admin.legacy_mda_id != legacy_mda.pk:
        admin.legacy_mda = legacy_mda
        admin.save(update_fields=['legacy_mda'])
    fund_seg, _ = FundSegment.objects.get_or_create(
        code='07700',
        defaults={'name': 'Match Fund', 'main_fund_code': '07',
                  'legacy_fund': legacy_fund},
    )
    if fund_seg.legacy_fund_id != legacy_fund.pk:
        fund_seg.legacy_fund = legacy_fund
        fund_seg.save(update_fields=['legacy_fund'])
    func, _ = FunctionalSegment.objects.get_or_create(
        code='70177', defaults={'name': 'Match Function', 'division_code': '701'},
    )
    prog, _ = ProgrammeSegment.objects.get_or_create(
        code='07070000000000',
        defaults={'name': 'Match Programme', 'policy_code': '07',
                  'programme_code': '07'},
    )
    geo, _ = GeographicSegment.objects.get_or_create(
        code='57000000', defaults={'name': 'Match Geo', 'zone_code': '5'},
    )

    from types import SimpleNamespace

    def _line(account, amount):
        from budget.models import Appropriation
        return Appropriation.objects.create(
            fiscal_year=fy, administrative=admin, economic=account,
            functional=func, programme=prog, fund=fund_seg, geographic=geo,
            amount_approved=Decimal(amount),
            appropriation_type='ORIGINAL', status='ACTIVE',
        )

    return SimpleNamespace(
        parent=parent, child=child, line=_line,
        mda=legacy_mda, fund=legacy_fund, year=2033,
    )


def _match(chart, account):
    from accounting.services.budget_check_rules import find_matching_appropriation
    return find_matching_appropriation(
        mda=chart.mda, fund=chart.fund, account=account, fiscal_year=chart.year,
    )


def test_a_posting_charges_the_account_s_own_line(chart):
    """The regression. Both lines exist; the child's must win."""
    parent_line = chart.line(chart.parent, '2000000.00')
    child_line = chart.line(chart.child, '90000000.00')

    hit = _match(chart, chart.child)

    assert hit is not None
    assert hit.pk == child_line.pk, (
        f'charged the parent line ({parent_line.economic.code}) instead of the '
        f'account\'s own ({child_line.economic.code})'
    )


def test_the_parent_line_is_left_alone(chart):
    """The other half of the same failure.

    A parent line exhausted by its children's spending refuses postings
    that genuinely belong to it, which reads as "no budget" for work that
    is funded.
    """
    parent_line = chart.line(chart.parent, '2000000.00')
    chart.line(chart.child, '90000000.00')

    assert _match(chart, chart.parent).pk == parent_line.pk


def test_spending_still_rolls_up_when_the_account_has_no_line(chart):
    """Roll-up is the feature; reaching past a closer line was the bug."""
    parent_line = chart.line(chart.parent, '2000000.00')

    hit = _match(chart, chart.child)

    assert hit is not None, 'a child with no line of its own must still be controlled'
    assert hit.pk == parent_line.pk


def test_nothing_matches_when_no_ancestor_has_a_line(chart):
    """No line anywhere means no match — not a silent pass."""
    assert _match(chart, chart.child) is None


def test_a_closed_line_does_not_capture_the_posting(chart):
    """Only ACTIVE lines carry authority to spend."""
    from budget.models import Appropriation

    child_line = chart.line(chart.child, '90000000.00')
    Appropriation.objects.filter(pk=child_line.pk).update(status='CLOSED')
    parent_line = chart.line(chart.parent, '2000000.00')

    assert _match(chart, chart.child).pk == parent_line.pk
