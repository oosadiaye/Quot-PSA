"""Every source in the drill-down runs, and says so when it does not.

``/budget/appropriations/{id}/transactions/`` enumerates what consumed a
budget line, from several sources in turn. Each is wrapped in its own
try/except so one broken source cannot sink the whole response — a sound
design that had quietly cost the report an entire class of transaction.

The PO source read ``po.description``. ``PurchaseOrder`` has no such
field, so every CLOSED purchase commitment vanished from the itemisation
while the appropriation went on counting it in ``total_expended``. The
figures and their explanation disagreed, and nothing on screen said so:
the response carried ``_warnings`` throughout, and no caller rendered it.

Two things are pinned here, because the bug needed both to stay hidden:

  1. A PO commitment actually appears. Catches the typo directly.
  2. ``_warnings`` is absent when every source ran. Catches the next
     typo, in whichever source it lands — a silent source is the failure
     mode, not any particular field name.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate


pytestmark = pytest.mark.django_db


@pytest.fixture
def line_with_a_commitment(db):
    """An appropriation with one CLOSED purchase commitment against it."""
    from accounting.models.advanced import FiscalYear
    from accounting.models.gl import Account, Fund, Function, Program, Geo
    from accounting.models.ncoa import (
        AdministrativeSegment, FunctionalSegment, ProgrammeSegment,
        FundSegment, GeographicSegment, NCoACode,
    )
    from budget.models import Appropriation
    from procurement.models import ProcurementBudgetLink, PurchaseOrder, Vendor

    fy, _ = FiscalYear.objects.get_or_create(
        year=2032, defaults={'name': 'FY2032', 'is_active': False},
    )
    admin, _ = AdministrativeSegment.objects.get_or_create(
        code='098000000000',
        defaults={'name': 'Drilldown MDA', 'level': 'ORGANIZATION', 'sector_code': '09'},
    )
    econ, _ = Account.objects.get_or_create(
        code='22108800',
        defaults={'name': 'Drilldown Expense', 'account_type': 'Expense'},
    )
    func, _ = FunctionalSegment.objects.get_or_create(
        code='70188', defaults={'name': 'Drilldown Function', 'division_code': '701'},
    )
    prog, _ = ProgrammeSegment.objects.get_or_create(
        code='08080000000000',
        defaults={'name': 'Drilldown Programme', 'policy_code': '08', 'programme_code': '08'},
    )
    fund_seg, _ = FundSegment.objects.get_or_create(
        code='08000', defaults={'name': 'Drilldown Fund', 'main_fund_code': '08'},
    )
    geo, _ = GeographicSegment.objects.get_or_create(
        code='58000000', defaults={'name': 'Drilldown Geo', 'zone_code': '5'},
    )
    ncoa, _ = NCoACode.objects.get_or_create(
        administrative=admin, economic=econ, functional=func,
        programme=prog, fund=fund_seg, geographic=geo,
    )

    appropriation = Appropriation.objects.create(
        fiscal_year=fy, administrative=admin, economic=econ, functional=func,
        programme=prog, fund=fund_seg, geographic=geo,
        amount_approved=Decimal('1000000.00'),
        appropriation_type='ORIGINAL', status='ACTIVE',
    )

    # ``is_active`` defaults to False and PurchaseOrder.clean() refuses an
    # inactive vendor, so it has to be set explicitly.
    vendor, _ = Vendor.objects.get_or_create(
        code='V-DRILL',
        defaults={'name': 'Drilldown Vendor Ltd', 'is_active': True},
    )
    if not vendor.is_active:
        vendor.is_active = True
        vendor.save(update_fields=['is_active'])
    legacy_fund, _ = Fund.objects.get_or_create(code='08000', defaults={'name': 'Drilldown Fund'})
    legacy_func, _ = Function.objects.get_or_create(code='70188', defaults={'name': 'Drilldown Function'})
    legacy_prog, _ = Program.objects.get_or_create(code='0808', defaults={'name': 'Drilldown Programme'})
    legacy_geo, _ = Geo.objects.get_or_create(code='58000000', defaults={'name': 'Drilldown Geo'})

    po = PurchaseOrder.objects.create(
        po_number='PO-DRILL-0001',
        vendor=vendor,
        order_date=date(2032, 3, 1),
        fund=legacy_fund, function=legacy_func, program=legacy_prog, geo=legacy_geo,
        notes='Supply of drilldown widgets',
        status='APPROVED',
    )
    ProcurementBudgetLink.objects.create(
        purchase_order=po,
        appropriation=appropriation,
        ncoa_code=ncoa,
        committed_amount=Decimal('250000.00'),
        status='CLOSED',
    )
    return appropriation


def _drilldown(appropriation):
    from budget.views import AppropriationViewSet
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.filter(is_superuser=True).first()
    if user is None:
        user = User.objects.create_superuser(
            username='drilldown-admin', email='d@example.com', password='x',
        )
    request = APIRequestFactory().get(
        f'/budget/appropriations/{appropriation.pk}/transactions/'
    )
    force_authenticate(request, user=user)
    response = AppropriationViewSet.as_view({'get': 'transactions'})(
        request, pk=appropriation.pk
    )
    assert response.status_code == 200, response.data
    return response.data


def test_a_closed_purchase_commitment_appears_in_the_drilldown(line_with_a_commitment):
    """The bug, stated directly: this row used to be missing."""
    data = _drilldown(line_with_a_commitment)

    po_rows = [t for t in data['transactions'] if t['type'] == 'PO_COMMITMENT']

    assert po_rows, (
        'the PO commitment source produced nothing — the appropriation '
        'counts this money but the itemisation does not show it'
    )
    assert Decimal(po_rows[0]['amount']) == Decimal('250000.00')
    assert po_rows[0]['kind'] == 'expended'  # CLOSED means spent, not committed


def test_no_source_reports_itself_unavailable(line_with_a_commitment):
    """The general guard, and the one that outlives this particular typo.

    Each source swallows its own exception and records a warning, so a
    broken one shows up as a shorter list rather than an error. Asserting
    the warnings are absent is the only way a test notices.
    """
    data = _drilldown(line_with_a_commitment)

    assert not data.get('_warnings'), data.get('_warnings')
    assert not data.get('partial_sources_failed'), data.get('partial_sources_failed')


def test_the_purchase_order_narrative_is_carried_through(line_with_a_commitment):
    """``notes`` is the field that exists; ``description`` is what broke it."""
    data = _drilldown(line_with_a_commitment)

    po_row = next(t for t in data['transactions'] if t['type'] == 'PO_COMMITMENT')
    assert po_row['description'] == 'Supply of drilldown widgets'
    assert po_row['party'] == 'Drilldown Vendor Ltd'


def test_the_summary_counts_what_the_list_shows(line_with_a_commitment):
    """A summary that disagrees with its own rows is worse than no summary."""
    data = _drilldown(line_with_a_commitment)

    listed_expended = sum(
        Decimal(t['amount']) for t in data['transactions'] if t['kind'] == 'expended'
    )
    assert Decimal(data['summary']['expended_total']) == listed_expended
    assert data['summary']['expended_count'] == sum(
        1 for t in data['transactions'] if t['kind'] == 'expended'
    )
