"""A supplier proposes catalogue prices; the office accepts or rejects them; nothing a supplier does reaches another's prices."""
from decimal import Decimal

import pytest

from catalogue import portal_service as service
from catalogue.models import CatalogueItem, CataloguePriceProposal, PriceHistory, SupplierCatalogue
from core.models import TenantModule
from core.permissions import invalidate_module_cache
from inventory.models import Item
from procurement.models import Vendor
from procurement.tests.test_supplier_portal import make_vendor, supplier_client, switch_portal  # noqa: F401  (autouse fixture too)
from procurement.tests.test_supplier_portal import tenant_schema  # noqa: F401
from procurement.tests.test_vendor_role_containment import client_with_role

pytestmark = pytest.mark.django_db
D = Decimal
PORTAL = '/api/v1/supplier-portal/catalogue/'


def catalogue_module(active=True):
    TenantModule.objects.update_or_create(module_name='catalogue', defaults={'is_active': active})
    from procurement.tests.test_vendor_role_containment import _tenant
    invalidate_module_cache(_tenant().pk, 'catalogue')


@pytest.fixture(autouse=True)
def clean(db):
    CataloguePriceProposal.objects.all().delete()
    CatalogueItem.objects.all().delete()
    SupplierCatalogue.objects.filter(supplier__code__startswith='SP-').delete()
    PriceHistory.objects.filter(supplier__code__startswith='SP-').delete()
    catalogue_module(True)
    yield
    catalogue_module(False)


def make_item(sku='CAT-CEMENT', name='Cement 50kg bag', active=True):
    item, _ = Item.objects.get_or_create(
        sku=sku, defaults={'name': name, 'description': name, 'unit_of_measure': 'bag', 'barcode': sku, 'is_active': active})
    Item.objects.filter(pk=item.pk).update(is_active=active)
    item.refresh_from_db()
    return item


# ── the service ───────────────────────────────────────────────────────────────────────────────────────────────

def test_a_price_must_be_more_than_zero():
    with pytest.raises(service.ProposalError, match='more than zero'):
        service.propose(make_vendor('SP-C1'), None, item=make_item(), unit_price=0)


def test_an_item_the_government_does_not_buy_is_refused():
    with pytest.raises(service.ProposalError, match='not currently bought'):
        service.propose(make_vendor('SP-C2'), None, item=make_item('CAT-OLD', 'Old stock', active=False), unit_price=100)


def test_only_one_proposal_may_wait_per_item_and_supplier():
    v, item = make_vendor('SP-C3'), make_item()
    service.propose(v, None, item=item, unit_price=100)
    with pytest.raises(service.ProposalError, match='already have a price waiting'):
        service.propose(v, None, item=item, unit_price=90)
    service.propose(make_vendor('SP-C3B'), None, item=item, unit_price=95)        # another supplier may


def test_approving_puts_the_price_in_force_and_in_the_history():
    v, item = make_vendor('SP-C4'), make_item()
    p = service.propose(v, None, item=item, unit_price=D('4500.00'), specification='Dangote, 50kg')
    service.decide(p, None, approve=True)
    line = CatalogueItem.objects.get(catalogue__supplier=v, item=item)
    assert (line.unit_price, line.specification, line.is_active) == (D('4500.00'), 'Dangote, 50kg', True)
    assert line.catalogue.status == 'active'
    assert list(PriceHistory.objects.filter(supplier=v, item=item).values_list('unit_price', flat=True)) == [D('4500.00')]


def test_a_later_price_replaces_the_old_one_and_remembers_it():
    v, item = make_vendor('SP-C5'), make_item()
    service.decide(service.propose(v, None, item=item, unit_price=D('4500.00')), None, approve=True)
    second = service.propose(v, None, item=item, unit_price=D('4800.00'))
    assert second.current_price == D('4500.00')                      # what it replaces is recorded with the request
    service.decide(second, None, approve=True)
    assert CatalogueItem.objects.get(catalogue__supplier=v, item=item).unit_price == D('4800.00')
    assert SupplierCatalogue.objects.filter(supplier=v).count() == 1  # the same catalogue, not a new one
    assert PriceHistory.objects.filter(supplier=v, item=item).count() == 2


def test_rejecting_needs_a_reason_and_changes_no_price():
    v, item = make_vendor('SP-C6'), make_item()
    p = service.propose(v, None, item=item, unit_price=100)
    with pytest.raises(service.ProposalError, match='Give a reason'):
        service.decide(p, None, approve=False)
    service.decide(p, None, approve=False, reason='Above the framework ceiling')
    assert not CatalogueItem.objects.filter(catalogue__supplier=v).exists()
    assert CataloguePriceProposal.objects.get(pk=p.pk).status == 'rejected'


def test_a_decided_proposal_cannot_be_decided_again():
    p = service.propose(make_vendor('SP-C7'), None, item=make_item(), unit_price=100)
    service.decide(p, None, approve=True)
    with pytest.raises(service.ProposalError, match='already approved'):
        service.decide(p, None, approve=True)


# ── the supplier's API ────────────────────────────────────────────────────────────────────────────────────────

def test_a_supplier_proposes_and_sees_its_own_proposals_only():
    switch_portal()
    mine, theirs = make_vendor('SP-C8'), make_vendor('SP-C8B')
    c = supplier_client(mine)
    item = make_item()
    service.propose(theirs, None, item=item, unit_price=70)
    r = c.post(PORTAL + 'proposals/', {'item': item.pk, 'proposed_price': '4500.00', 'specification': '50kg'}, format='json')
    assert r.status_code == 201 and r.json()['status'] == 'pending'
    listed = c.get(PORTAL + 'proposals/').json()
    assert [p['proposed_price'] for p in listed] == ['4500.00']


def test_a_supplier_sees_only_its_own_prices_in_force():
    switch_portal()
    mine, theirs = make_vendor('SP-C9'), make_vendor('SP-C9B')
    item = make_item()
    service.decide(service.propose(mine, None, item=item, unit_price=D('4500.00')), None, approve=True)
    service.decide(service.propose(theirs, None, item=item, unit_price=D('1.00')), None, approve=True)
    rows = supplier_client(mine).get(PORTAL).json()
    assert [(r['item_code'], r['unit_price']) for r in rows] == [('CAT-CEMENT', '4500.00')]


def test_a_bad_price_or_a_second_waiting_proposal_comes_back_as_a_clear_message():
    switch_portal()
    c = supplier_client(make_vendor('SP-C10'))
    item = make_item()
    assert c.post(PORTAL + 'proposals/', {'item': item.pk, 'proposed_price': '0'}, format='json').status_code == 400
    assert c.post(PORTAL + 'proposals/', {'item': item.pk, 'proposed_price': '100'}, format='json').status_code == 201
    again = c.post(PORTAL + 'proposals/', {'item': item.pk, 'proposed_price': '90'}, format='json')
    assert again.status_code == 400 and 'already have a price waiting' in again.json()['error']


def test_item_search_gives_only_a_code_a_name_and_a_unit():
    switch_portal()
    make_item()
    rows = supplier_client(make_vendor('SP-C11')).get(PORTAL + 'items/?search=cement').json()
    assert rows and set(rows[0]) == {'id', 'code', 'name', 'unit'}


def test_a_search_that_is_too_short_returns_nothing():
    switch_portal()
    make_item()
    assert supplier_client(make_vendor('SP-C12')).get(PORTAL + 'items/?search=c').json() == []


def test_with_the_catalogue_module_off_the_supplier_is_told_so():
    switch_portal()
    c = supplier_client(make_vendor('SP-C13'))
    catalogue_module(False)
    r = c.get(PORTAL)
    assert r.status_code == 403 and 'module' in str(r.json()).lower()


# ── the office's side ─────────────────────────────────────────────────────────────────────────────────────────

def test_an_officer_approves_a_proposal_through_the_api():
    switch_portal()
    v, item = make_vendor('SP-C14'), make_item()
    p = service.propose(v, None, item=item, unit_price=D('4500.00'))
    admin = client_with_role('admin')
    listed = admin.get('/api/v1/catalogue/price-proposals/?status=pending').json()
    assert any(row['id'] == p.pk for row in (listed.get('results') or listed))
    assert admin.post(f'/api/v1/catalogue/price-proposals/{p.pk}/approve/', {}, format='json').json()['status'] == 'approved'
    assert CatalogueItem.objects.filter(catalogue__supplier=v, item=item, unit_price=D('4500.00')).exists()


def test_a_supplier_cannot_approve_its_own_price():
    switch_portal()
    v = make_vendor('SP-C15')
    c = supplier_client(v)
    p = service.propose(v, None, item=make_item(), unit_price=100)
    assert c.post(f'/api/v1/catalogue/price-proposals/{p.pk}/approve/', {}, format='json').status_code == 403
    assert CataloguePriceProposal.objects.get(pk=p.pk).status == 'pending'


def test_staff_can_find_a_suppliers_price_for_an_item_which_is_what_the_order_form_shows():
    switch_portal()
    mine, other = make_vendor('SP-C16'), make_vendor('SP-C16B')
    item = make_item()
    service.decide(service.propose(mine, None, item=item, unit_price=D('4500.00')), None, approve=True)
    service.decide(service.propose(other, None, item=item, unit_price=D('4100.00')), None, approve=True)
    admin = client_with_role('admin')
    url = f'/api/v1/catalogue/items/?item={item.pk}&catalogue__supplier={mine.pk}&catalogue__status=active&is_active=true&page_size=1'
    body = admin.get(url).json()
    rows = body.get('results') or body
    assert [r['unit_price'] for r in rows] == ['4500.00']

