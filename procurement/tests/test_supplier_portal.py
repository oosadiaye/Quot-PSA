"""Supplier self-service: the portal is off until switched on; a supplier is invited and let in (by an officer, or on paying
registration); it sees and changes only its own records; bank details change only when the procurement office approves."""
from datetime import date
from decimal import Decimal

import secrets

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.middleware import _get_tenant_cache
from procurement.models import PurchaseOrder, PurchaseOrderLine, SupplierPortalSettings, Vendor, VendorBankChangeRequest, VendorUser
from procurement.services import supplier_portal as portal
from procurement.tests.test_vendor_role_containment import DOMAIN, _tenant, client_with_role

pytestmark = pytest.mark.django_db
PORTAL = '/api/v1/supplier-portal/'
TEST_PASSWORD = f'{secrets.token_urlsafe(18)}-aA1!'     # made fresh each run, never kept in the repository
GOOD_NUBAN = '0123456789'       # any 10 digits passes the format check


@pytest.fixture(autouse=True)
def tenant_schema(db, _route_to_pytest_schema):
    _tenant()
    SupplierPortalSettings.objects.all().delete()
    Vendor.objects.filter(code__startswith='SP-').delete()
    _get_tenant_cache().clear()


def make_vendor(code, **kw):
    return Vendor.objects.create(code=code, name=f'{code} Supplies Ltd', email=f'{code.lower()}@example.test', is_active=True, **kw)


def switch_portal(on=True, auto=False):
    cfg = portal.portal_settings()
    cfg.enabled, cfg.auto_activate_on_payment = on, auto
    cfg.save()


def supplier_client(vendor):
    """Invite and activate the supplier, then return a client signed in as it."""
    portal.invite(vendor)
    portal.activate(vendor)
    user = VendorUser.objects.get(vendor=vendor).user
    token, _ = Token.objects.get_or_create(user=user)
    _get_tenant_cache().clear()
    client = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


def make_po(vendor, status='Approved', number=None):
    from accounting.models.gl import Account, Fund, Function, Geo, MDA, Program

    fund, _ = Fund.objects.get_or_create(code='SP1', defaults={'name': 'SP Fund'})
    fn, _ = Function.objects.get_or_create(code='SP1', defaults={'name': 'SP Func'})
    pr, _ = Program.objects.get_or_create(code='SP1', defaults={'name': 'SP Prog'})
    geo, _ = Geo.objects.get_or_create(code='SP1', defaults={'name': 'SP Geo'})
    acct, _ = Account.objects.get_or_create(code='22100992', defaults={'name': 'SP Expense', 'account_type': 'Expense'})
    mda, _ = MDA.objects.get_or_create(code='SP-MDA', defaults={'name': 'SP MDA', 'short_name': 'SPM'})
    po = PurchaseOrder.objects.create(mda=mda, vendor=vendor, order_date=date(2026, 3, 1), fund=fund, function=fn, program=pr, geo=geo,
                                      status='Pending', po_number=number or f'PO-{vendor.code}-{PurchaseOrder.objects.count()}')
    PurchaseOrderLine.objects.create(po=po, item_description='Cement', quantity=Decimal('10'), unit_price=Decimal('100.00'), account=acct)
    PurchaseOrder.objects.filter(pk=po.pk).update(status=status)       # skip the approval side effects; only the status matters here
    return po


# ── the switch, and getting in ────────────────────────────────────────────────────────────────────────────────

def test_inviting_is_refused_while_the_portal_is_off():
    with pytest.raises(portal.PortalError, match='switched off'):
        portal.invite(make_vendor('SP-OFF'))


def test_a_supplier_without_an_email_cannot_be_invited():
    switch_portal()
    v = Vendor.objects.create(code='SP-NOMAIL', name='No Mail Ltd', email='')
    with pytest.raises(portal.PortalError, match='no email address'):
        portal.invite(v)


def test_inviting_gives_the_supplier_a_narrow_role_and_a_link_to_choose_a_password(mailoutbox):
    from tenants.models import UserTenantRole
    switch_portal()
    v = make_vendor('SP-INV')
    link = portal.invite(v)
    v.refresh_from_db()
    assert v.portal_status == 'invited' and link.user.email == 'sp-inv@example.test'
    assert not link.user.has_usable_password()
    role = UserTenantRole.objects.get(user=link.user, tenant=_tenant())
    assert role.role == 'vendor' and role.is_active
    assert len(mailoutbox) == 1 and '/reset-password?uid=' in mailoutbox[0].body


def test_an_invited_supplier_is_not_in_until_it_is_activated():
    switch_portal()
    v = make_vendor('SP-WAIT')
    portal.invite(v)
    user = VendorUser.objects.get(vendor=v).user
    token, _ = Token.objects.get_or_create(user=user)
    _get_tenant_cache().clear()
    c = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
    c.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    assert c.get(PORTAL + 'me/').status_code == 403


def test_activating_needs_an_invitation_first():
    switch_portal()
    with pytest.raises(portal.PortalError, match='Invite this supplier first'):
        portal.activate(make_vendor('SP-NOINV'))


def test_an_email_that_belongs_to_another_supplier_is_refused():
    switch_portal()
    a, b = make_vendor('SP-A'), make_vendor('SP-B')
    portal.invite(a)
    with pytest.raises(portal.PortalError, match='another supplier'):
        portal.invite(b, email=a.email)


def test_an_invitation_never_lands_on_a_staff_account():
    """The supplier role must not overwrite a staff user's, nor mail that user a way in, because an officer typed their address."""
    from django.contrib.auth.models import User
    from django_tenants.utils import schema_context
    from tenants.models import UserTenantRole
    switch_portal()
    tenant = _tenant()
    with schema_context('public'):
        staff = User.objects.create_user(username='sp-staff', email='sp-staff@example.test', password=TEST_PASSWORD)
        UserTenantRole.objects.update_or_create(user=staff, tenant=tenant, defaults={'role': 'admin', 'is_active': True})
    with pytest.raises(portal.PortalError, match='already belongs to a user'):
        portal.invite(make_vendor('SP-TAKE'), email='sp-staff@example.test')
    with schema_context('public'):
        assert UserTenantRole.objects.get(user=staff, tenant=tenant).role == 'admin'
        assert User.objects.get(pk=staff.pk).check_password(TEST_PASSWORD)


def test_an_account_with_a_password_but_no_role_is_not_taken_either():
    from django.contrib.auth.models import User
    from django_tenants.utils import schema_context
    switch_portal()
    with schema_context('public'):
        User.objects.create_user(username='sp-lone', email='sp-lone@example.test', password=TEST_PASSWORD)
    with pytest.raises(portal.PortalError, match='already belongs to a user'):
        portal.invite(make_vendor('SP-LONE'), email='sp-lone@example.test')


def test_a_user_who_is_already_a_supplier_here_can_be_invited_again():
    switch_portal()
    v = make_vendor('SP-AGAIN')
    first = portal.invite(v)
    assert portal.invite(v).user_id == first.user_id


def test_switching_the_portal_off_locks_every_supplier_out():
    switch_portal()
    c = supplier_client(make_vendor('SP-LOCK'))
    assert c.get(PORTAL + 'me/').status_code == 200
    switch_portal(on=False)
    assert c.get(PORTAL + 'me/').status_code == 403


def test_a_suspended_supplier_is_out():
    switch_portal()
    v = make_vendor('SP-SUSP')
    c = supplier_client(v)
    portal.suspend(v)
    assert c.get(PORTAL + 'me/').status_code == 403


def test_a_staff_user_is_not_a_supplier():
    switch_portal()
    assert client_with_role('admin').get(PORTAL + 'me/').status_code == 403


# ── automatic activation on paying registration ──────────────────────────────────────────────────────────────

def test_a_confirmed_registration_payment_lets_the_supplier_in_when_the_tenant_asks_for_that():
    switch_portal(auto=True)
    v = make_vendor('SP-AUTO')
    portal.on_registration_paid(v)
    v.refresh_from_db()
    assert v.portal_status == 'active'


def test_a_confirmed_payment_does_nothing_when_automatic_activation_is_off():
    switch_portal(auto=False)
    v = make_vendor('SP-MAN')
    portal.on_registration_paid(v)
    v.refresh_from_db()
    assert v.portal_status == 'not_invited'


def test_a_portal_problem_never_undoes_a_confirmed_payment(monkeypatch):
    switch_portal(auto=True)
    v = make_vendor('SP-BOOM')
    monkeypatch.setattr(portal, 'invite', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('mail server down')))
    portal.on_registration_paid(v)          # must not raise
    v.refresh_from_db()
    assert v.portal_status == 'not_invited'


# ── a supplier sees and changes only its own ─────────────────────────────────────────────────────────────────

def test_a_supplier_sees_only_its_own_approved_orders():
    switch_portal()
    mine, theirs = make_vendor('SP-MINE'), make_vendor('SP-THEIRS')
    c = supplier_client(mine)
    ok, draft, other = make_po(mine, number='SP-PO-1'), make_po(mine, status='Draft', number='SP-PO-2'), make_po(theirs, number='SP-PO-3')
    numbers = [o['po_number'] for o in c.get(PORTAL + 'orders/').json()]
    assert numbers == ['SP-PO-1']
    assert c.get(f'{PORTAL}orders/{ok.pk}/').status_code == 200
    assert c.get(f'{PORTAL}orders/{draft.pk}/').status_code == 404       # a draft is internal
    assert c.get(f'{PORTAL}orders/{other.pk}/').status_code == 404       # another supplier's order is simply not there


def test_an_order_shows_its_lines_and_total():
    switch_portal()
    v = make_vendor('SP-LINES')
    c = supplier_client(v)
    po = make_po(v, number='SP-PO-L')
    body = c.get(f'{PORTAL}orders/{po.pk}/').json()
    assert [(l['description'], Decimal(str(l['quantity'])), Decimal(str(l['total_price']))) for l in body['lines']] == [('Cement', Decimal('10'), Decimal('1000'))]


def test_a_supplier_acknowledges_its_own_order_once_and_not_anothers():
    switch_portal()
    mine, theirs = make_vendor('SP-ACK'), make_vendor('SP-ACK2')
    c = supplier_client(mine)
    po, other = make_po(mine, number='SP-PO-A'), make_po(theirs, number='SP-PO-B')
    first = c.post(f'{PORTAL}orders/{po.pk}/acknowledge/', {'note': 'Will deliver Friday'}, format='json')
    again = c.post(f'{PORTAL}orders/{po.pk}/acknowledge/', {}, format='json')
    assert (first.status_code, again.status_code) == (201, 200) and first.json()['acknowledged_at']
    assert c.post(f'{PORTAL}orders/{other.pk}/acknowledge/', {}, format='json').status_code == 404


def test_a_supplier_updates_its_contact_details_but_not_its_bank_or_name():
    switch_portal()
    v = make_vendor('SP-PROF')
    c = supplier_client(v)
    assert c.patch(PORTAL + 'me/', {'phone': '08030000000', 'address': '1 Market Road'}, format='json').json()['phone'] == '08030000000'
    refused = c.patch(PORTAL + 'me/', {'bank_account_number': GOOD_NUBAN, 'name': 'Renamed'}, format='json')
    assert refused.status_code == 400 and 'bank_account_number' in refused.json()['error']
    v.refresh_from_db()
    assert v.bank_account_number == '' and v.name == 'SP-PROF Supplies Ltd'


def test_the_profile_never_shows_the_full_account_number():
    switch_portal()
    v = make_vendor('SP-MASK', bank_name='First Bank', bank_account_number=GOOD_NUBAN)
    body = supplier_client(v).get(PORTAL + 'me/').json()
    assert body['bank_account_masked'] == '••••••6789' and GOOD_NUBAN not in str(body)


# ── bank details change only on approval ─────────────────────────────────────────────────────────────────────

def test_a_bank_change_waits_for_approval_and_only_one_may_wait():
    switch_portal()
    v = make_vendor('SP-BANK', bank_name='Old Bank', bank_account_number='1111111111')
    c = supplier_client(v)
    r = c.post(PORTAL + 'bank-changes/', {'bank_name': 'New Bank', 'bank_account_number': GOOD_NUBAN}, format='json')
    assert r.status_code == 201 and r.json()['status'] == 'pending'
    v.refresh_from_db()
    assert (v.bank_name, v.bank_account_number) == ('Old Bank', '1111111111')       # nothing has moved yet
    second = c.post(PORTAL + 'bank-changes/', {'bank_name': 'Third Bank', 'bank_account_number': GOOD_NUBAN}, format='json')
    assert second.status_code == 400 and 'waiting for approval' in second.json()['error']
    assert c.get(PORTAL + 'me/').json()['pending_bank_change']['bank_name'] == 'New Bank'


def test_a_bad_account_number_is_refused_up_front():
    switch_portal()
    c = supplier_client(make_vendor('SP-NUBAN'))
    assert c.post(PORTAL + 'bank-changes/', {'bank_name': 'X Bank', 'bank_account_number': '12345'}, format='json').status_code == 400


def test_approving_changes_where_the_supplier_is_paid():
    switch_portal()
    v = make_vendor('SP-APPR', bank_name='Old Bank', bank_account_number='1111111111')
    change = portal.request_bank_change(v, None, bank_name='New Bank', bank_account_number=GOOD_NUBAN, bank_sort_code='011')
    portal.decide_bank_change(change, None, approve=True)
    v.refresh_from_db()
    assert (v.bank_name, v.bank_account_number, v.bank_sort_code) == ('New Bank', GOOD_NUBAN, '011')


def test_rejecting_needs_a_reason_and_changes_nothing():
    switch_portal()
    v = make_vendor('SP-REJ', bank_name='Old Bank', bank_account_number='1111111111')
    change = portal.request_bank_change(v, None, bank_name='New Bank', bank_account_number=GOOD_NUBAN)
    with pytest.raises(portal.PortalError, match='Give a reason'):
        portal.decide_bank_change(change, None, approve=False)
    portal.decide_bank_change(change, None, approve=False, reason='Account name does not match the registration')
    v.refresh_from_db()
    assert v.bank_account_number == '1111111111' and VendorBankChangeRequest.objects.get(pk=change.pk).status == 'rejected'


def test_a_decided_request_cannot_be_decided_again():
    switch_portal()
    change = portal.request_bank_change(make_vendor('SP-TWICE'), None, bank_name='B', bank_account_number=GOOD_NUBAN)
    portal.decide_bank_change(change, None, approve=True)
    with pytest.raises(portal.PortalError, match='already approved'):
        portal.decide_bank_change(change, None, approve=True)


# ── the procurement office's side, through the API ───────────────────────────────────────────────────────────

def test_an_officer_invites_activates_and_suspends_through_the_api(mailoutbox):
    switch_portal()
    v = make_vendor('SP-API')
    admin = client_with_role('admin')
    assert admin.post(f'/api/v1/procurement/vendors/{v.pk}/portal-invite/', {}, format='json').json() == {'portal_status': 'invited'}
    assert admin.post(f'/api/v1/procurement/vendors/{v.pk}/portal-activate/', {}, format='json').json() == {'portal_status': 'active'}
    assert admin.post(f'/api/v1/procurement/vendors/{v.pk}/portal-suspend/', {}, format='json').json() == {'portal_status': 'suspended'}
    assert len(mailoutbox) == 1


def test_an_officer_gets_a_clear_message_when_the_portal_is_off():
    v = make_vendor('SP-APIOFF')
    r = client_with_role('admin').post(f'/api/v1/procurement/vendors/{v.pk}/portal-invite/', {}, format='json')
    assert r.status_code == 400 and 'switched off' in r.json()['error']


def test_the_portal_settings_can_be_read_and_changed_by_an_officer():
    admin = client_with_role('admin')
    assert admin.get('/api/v1/procurement/portal-settings/current/').json()['enabled'] is False
    r = admin.patch('/api/v1/procurement/portal-settings/current/', {'enabled': True, 'auto_activate_on_payment': True}, format='json')
    assert (r.json()['enabled'], r.json()['auto_activate_on_payment']) == (True, True)


def test_an_officer_approves_a_bank_change_through_the_api():
    switch_portal()
    v = make_vendor('SP-APIBANK', bank_name='Old', bank_account_number='1111111111')
    change = portal.request_bank_change(v, None, bank_name='New Bank', bank_account_number=GOOD_NUBAN)
    admin = client_with_role('admin')
    listed = admin.get('/api/v1/procurement/bank-change-requests/?status=pending').json()
    assert any(row['id'] == change.pk for row in (listed.get('results') or listed))
    assert admin.post(f'/api/v1/procurement/bank-change-requests/{change.pk}/approve/', {}, format='json').json()['status'] == 'approved'
    v.refresh_from_db()
    assert v.bank_account_number == GOOD_NUBAN


def test_a_supplier_cannot_decide_its_own_bank_change():
    switch_portal()
    v = make_vendor('SP-SELF')
    c = supplier_client(v)
    change = portal.request_bank_change(v, None, bank_name='New Bank', bank_account_number=GOOD_NUBAN)
    r = c.post(f'/api/v1/procurement/bank-change-requests/{change.pk}/approve/', {}, format='json')
    assert r.status_code == 403
    v.refresh_from_db()
    assert v.bank_account_number == ''


def test_the_supplier_list_leaves_out_unpaid_suppliers_unless_asked():
    paid = make_vendor('SP-PAID')
    unpaid = Vendor.objects.create(code='SP-UNPAID', name='SP-UNPAID Supplies Ltd', email='sp-unpaid@example.test', is_active=False)
    admin = client_with_role('admin')

    def codes(url):
        body = admin.get(url).json()
        return {row['code'] for row in (body.get('results') or body)}

    assert 'SP-PAID' in codes('/api/v1/procurement/vendors/?search=SP-&page_size=100')
    assert 'SP-UNPAID' not in codes('/api/v1/procurement/vendors/?search=SP-&page_size=100')
    assert {'SP-PAID', 'SP-UNPAID'} <= codes('/api/v1/procurement/vendors/?search=SP-&page_size=100&include_unpaid=1')
    assert paid.pk and unpaid.pk


def test_an_unpaid_supplier_can_be_invited_and_sees_that_its_registration_is_pending():
    switch_portal()
    v = Vendor.objects.create(code='SP-PEND', name='SP-PEND Supplies Ltd', email='sp-pend@example.test', is_active=False)
    c = supplier_client(v)
    assert c.get(PORTAL + 'me/').json()['registration_status'] == 'PENDING_ACTIVATION'
    assert c.get(PORTAL + 'orders/').json() == []

