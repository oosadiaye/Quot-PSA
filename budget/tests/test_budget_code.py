"""The budget code is the organisation's own reference, and stays theirs.

An appropriation line is identified structurally by its six NCoA
segments. ``budget_code`` is something else: the reference an officer
reads off their appropriation book (e.g. 'BL-2026-0142') so a row can be
tied back to the document it came from. Nothing derives it, and nothing
may overwrite it.

The first cut of this field generated a value from the line's own
dimensions and backfilled every row. That is what these tests exist to
prevent coming back — a value nobody typed is not data, it is noise that
looks like data, and it makes a code search return rows the officer never
coded while hiding the ones they did.

Not unique, deliberately. One budget code legitimately covers several
rows: the same expenditure split across funds is the normal case, and
this chart has exactly that shape.
"""
from __future__ import annotations

from decimal import Decimal

import pytest


pytestmark = pytest.mark.django_db


@pytest.fixture
def line(db):
    """One appropriation line, with the dimensions it needs."""
    from accounting.models.advanced import FiscalYear
    from accounting.models.gl import Account
    from accounting.models.ncoa import (
        AdministrativeSegment, FunctionalSegment, ProgrammeSegment,
        FundSegment, GeographicSegment,
    )
    from budget.models import Appropriation

    fy, _ = FiscalYear.objects.get_or_create(
        year=2031, defaults={'name': 'FY2031', 'is_active': False},
    )
    admin, _ = AdministrativeSegment.objects.get_or_create(
        code='099000000000',
        defaults={'name': 'Budget Code Test MDA', 'level': 'ORGANIZATION',
                  'sector_code': '09'},
    )
    econ, _ = Account.objects.get_or_create(
        code='22109900',
        defaults={'name': 'Budget Code Test Expense', 'account_type': 'Expense'},
    )
    func, _ = FunctionalSegment.objects.get_or_create(
        code='70199', defaults={'name': 'Test Function', 'division_code': '701'},
    )
    prog, _ = ProgrammeSegment.objects.get_or_create(
        code='09090000000000',
        defaults={'name': 'Test Programme', 'policy_code': '09',
                  'programme_code': '09'},
    )
    fund, _ = FundSegment.objects.get_or_create(
        code='09000', defaults={'name': 'Test Fund', 'main_fund_code': '09'},
    )
    geo, _ = GeographicSegment.objects.get_or_create(
        code='59000000', defaults={'name': 'Test Geo', 'zone_code': '5'},
    )

    def _make(**overrides):
        kwargs = dict(
            fiscal_year=fy, administrative=admin, economic=econ,
            functional=func, programme=prog, fund=fund, geographic=geo,
            amount_approved=Decimal('1000.00'),
            appropriation_type='ORIGINAL', status='DRAFT',
        )
        kwargs.update(overrides)
        return Appropriation.objects.create(**kwargs)

    return _make


def test_a_new_line_has_no_budget_code(line):
    """Blank until somebody types one — never auto-filled."""
    assert line().budget_code == ''


def test_the_code_an_officer_types_is_what_is_stored(line):
    appropriation = line(budget_code='BL-2026-0142')
    appropriation.refresh_from_db()
    assert appropriation.budget_code == 'BL-2026-0142'


def test_saving_the_line_again_does_not_rewrite_the_code(line):
    """The regression that matters.

    An earlier version recomputed the code on every save from the
    dimensions. Any unrelated save — the totals refresher runs often —
    would then silently replace what the officer entered.
    """
    appropriation = line(budget_code='BL-2026-0142')

    appropriation.amount_approved = Decimal('2000.00')
    appropriation.save()
    appropriation.refresh_from_db()

    assert appropriation.budget_code == 'BL-2026-0142'


def test_a_partial_save_does_not_rewrite_the_code(line):
    """``update_fields`` is the totals refresher's hot path."""
    appropriation = line(budget_code='BL-2026-0142')

    appropriation.cached_total_expended = Decimal('50.00')
    appropriation.save(update_fields=['cached_total_expended'])
    appropriation.refresh_from_db()

    assert appropriation.budget_code == 'BL-2026-0142'


def test_one_code_may_cover_several_lines(line):
    """Not unique, on purpose.

    The same expenditure split across funds shares one budget code —
    the normal shape of an appropriation book. A unique constraint would
    reject correct data.
    """
    from accounting.models.ncoa import FundSegment
    from budget.models import Appropriation

    other_fund, _ = FundSegment.objects.get_or_create(
        code='09100', defaults={'name': 'Test Fund B', 'main_fund_code': '09'},
    )
    line(budget_code='BL-2026-0142')
    line(budget_code='BL-2026-0142', fund=other_fund)

    assert Appropriation.objects.filter(budget_code='BL-2026-0142').count() == 2


def test_the_code_is_long_enough_for_a_real_reference(line):
    """50 characters — the column the Delta State schema already had."""
    field = line()._meta.get_field('budget_code')
    assert field.max_length == 50
    assert field.blank is True
    assert field.unique is False
