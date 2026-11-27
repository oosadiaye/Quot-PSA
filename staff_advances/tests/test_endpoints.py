"""The advance workflow over HTTP: gated by the module switch and the caller's role; refusals are 409s with a reason."""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import TenantModule
from core.permissions import invalidate_module_cache
from staff_advances.models import StaffAdvance, TravelRequest

pytestmark = pytest.mark.django_db(transaction=True)
DOMAIN = 'pytest.localhost'
BASE = '/api/v1/staff-advances'
D = Decimal


def _tenant():
    from tenants.models import Client, Domain
    with schema_context('public'):
        tenant, _ = Client.objects.get_or_create(schema_name='pytest_schema', defaults={'name': 'PyTest Tenant'})
        Domain.objects.get_or_create(domain=DOMAIN, tenant=tenant, defaults={'is_primary': True})
    return tenant


def _client(role='admin'):
    from tenants.models import UserTenantRole
    tenant = _tenant()
    user, _ = User.objects.get_or_create(username=f'adv_api_{role}', defaults={'email': f'{role}@t.test'})
    UserTenantRole.objects.update_or_create(user=user, tenant=tenant, defaults={'role': role, 'is_active': True})
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


def _module(active):
    TenantModule.objects.update_or_create(module_name='staff_advances', defaults={'is_active': active})
    invalidate_module_cache(_tenant().pk, 'staff_advances')


@pytest.fixture
def advance(employee, gl):
    return StaffAdvance.objects.create(employee=employee, recon_account=gl.recon, amount=D('500.00'), reference='ADV-API-1')


def test_an_admin_disburses_once_and_a_second_attempt_is_a_409_with_a_reason(advance, gl, open_fiscal_period):
    _module(True)
    admin = _client('admin')
    first = admin.post(f'{BASE}/staff-advances/{advance.pk}/disburse/', {}, format='json')
    assert first.status_code == 200, first.content
    assert first.json()['journal']
    again = admin.post(f'{BASE}/staff-advances/{advance.pk}/disburse/', {}, format='json')
    assert again.status_code == 409 and 'already' in again.json()['error'].lower()


def test_recovery_over_http_rolls_the_status_and_refuses_more_than_is_outstanding(advance, gl, open_fiscal_period):
    _module(True)
    admin = _client('admin')
    assert admin.post(f'{BASE}/staff-advances/{advance.pk}/disburse/', {}, format='json').status_code == 200
    part = admin.post(f'{BASE}/staff-advances/{advance.pk}/recover/',
                      {'amount': '200.00', 'expense_account': gl.expense.pk, 'notes': 'first slice'}, format='json')
    assert part.status_code == 200, part.content
    assert part.json()['status'] == 'PARTIAL' and part.json()['recovered_amount'] == '200.00'
    too_much = admin.post(f'{BASE}/staff-advances/{advance.pk}/recover/',
                          {'amount': '999.00', 'expense_account': gl.expense.pk}, format='json')
    assert too_much.status_code == 409 and 'outstanding' in too_much.json()['error']
    bad = admin.post(f'{BASE}/staff-advances/{advance.pk}/recover/', {'amount': 'abc'}, format='json')
    assert bad.status_code == 400


def test_a_travel_request_goes_through_its_approval_steps_over_http(employee, gl, open_fiscal_period):
    _module(True)
    admin = _client('admin')
    request = TravelRequest.objects.create(employee=employee, destination='Warri', estimated_cost=D('300.00'))
    url = f'{BASE}/travel-requests/{request.pk}'
    assert admin.post(f'{url}/approve/', {}, format='json').status_code == 409          # not submitted yet
    assert admin.post(f'{url}/submit/', {}, format='json').json()['status'] == 'submitted'
    assert admin.post(f'{url}/approve/', {}, format='json').json()['status'] == 'approved'
    paid = admin.post(f'{url}/advance/', {}, format='json')
    assert paid.status_code == 201, paid.content
    assert D(paid.json()['amount']) == D('300.00')
    request.refresh_from_db()
    assert request.status == 'advanced'


def test_rejecting_without_a_reason_is_a_409(employee):
    _module(True)
    admin = _client('admin')
    request = TravelRequest.objects.create(employee=employee, destination='Sapele', estimated_cost=D('50.00'))
    admin.post(f'{BASE}/travel-requests/{request.pk}/submit/', {}, format='json')
    assert admin.post(f'{BASE}/travel-requests/{request.pk}/reject/', {}, format='json').status_code == 409
    done = admin.post(f'{BASE}/travel-requests/{request.pk}/reject/', {'reason': 'Out of budget'}, format='json')
    assert done.status_code == 200 and done.json()['status'] == 'rejected'


def test_with_the_module_off_nothing_can_be_disbursed(advance):
    _module(False)
    r = _client('admin').post(f'{BASE}/staff-advances/{advance.pk}/disburse/', {}, format='json')
    assert r.status_code == 403 and r.json().get('code') == 'module_disabled'
    advance.refresh_from_db()
    assert advance.journal_id is None


def test_a_read_only_viewer_cannot_disburse(advance):
    _module(True)
    assert _client('viewer').post(f'{BASE}/staff-advances/{advance.pk}/disburse/', {}, format='json').status_code == 403
    advance.refresh_from_db()
    assert advance.journal_id is None


def test_anonymous_callers_are_turned_away(advance):
    _module(True)
    r = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN).post(f'{BASE}/staff-advances/{advance.pk}/disburse/', {}, format='json')
    assert r.status_code in (401, 403)
