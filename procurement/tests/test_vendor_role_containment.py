"""A supplier account is confined to the supplier portal, whatever an endpoint's own permissions say."""
import pytest
from django.contrib.auth.models import User
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.middleware import _get_tenant_cache

pytestmark = pytest.mark.django_db
DOMAIN = 'pytest.localhost'
CONFINED_MESSAGE = 'Supplier accounts can only use the supplier portal.'


def _tenant():
    from tenants.models import Client, Domain
    with schema_context('public'):
        tenant, _ = Client.objects.get_or_create(schema_name='pytest_schema', defaults={'name': 'PyTest Tenant'})
        Domain.objects.get_or_create(domain=DOMAIN, tenant=tenant, defaults={'is_primary': True})
    return tenant


def client_with_role(role, *, active=True):
    from tenants.models import UserTenantRole
    tenant = _tenant()
    user, _ = User.objects.get_or_create(username=f'contain_{role}', defaults={'email': f'{role}@t.test'})
    UserTenantRole.objects.update_or_create(user=user, tenant=tenant, defaults={'role': role, 'is_active': active})
    token, _ = Token.objects.get_or_create(user=user)
    _get_tenant_cache().clear()          # access and role are cached per user and tenant; a test must not see another's answer
    c = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
    c.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return c


@pytest.fixture(autouse=True)
def tenant_schema(db, _route_to_pytest_schema):
    _tenant()


def confined(response):
    return response.status_code == 403 and response.json().get('error') == CONFINED_MESSAGE


@pytest.mark.parametrize('path', [
    '/api/v1/budget/appropriations/',
    '/api/v1/budget/warrants/',
    '/api/v1/procurement/vendors/',
    '/api/v1/procurement/purchase-orders/',
    '/api/v1/hrm/payroll-runs/',
    '/api/v1/accounting/journals/',
    '/api/v1/budget-prep/submissions/',
    '/api/v1/tenants/enabled-modules/',
    '/api/v1/some/endpoint/that/does/not/exist/',       # fail closed: unknown paths are refused, not 404'd
])
def test_a_supplier_is_refused_everywhere_outside_the_portal(path):
    assert confined(client_with_role('vendor').get(path)), path


@pytest.mark.parametrize('method', ['post', 'patch', 'delete'])
def test_writes_outside_the_portal_are_refused_too(method):
    assert confined(getattr(client_with_role('vendor'), method)('/api/v1/procurement/vendors/1/', {}, format='json'))


def test_a_supplier_can_read_their_own_profile():
    r = client_with_role('vendor').get('/api/v1/core/users/me/')
    assert r.status_code == 200 and not confined(r)


def test_the_portal_prefix_is_open_to_a_supplier():
    r = client_with_role('vendor').get('/api/v1/supplier-portal/anything/')
    assert not confined(r)               # whatever the portal itself decides (it may 404 until built), the gate lets it through


@pytest.mark.parametrize('path', [
    '/api/v1/supplier-portalx/',                         # a look-alike prefix must not slip through
    '/api/v1/supplier-portal',                           # the bare prefix without its slash is not the portal either
    '/api/v1/budget/appropriations/?next=/api/v1/supplier-portal/',
])
def test_look_alike_paths_do_not_pass(path):
    assert confined(client_with_role('vendor').get(path)), path


def test_staff_roles_are_not_affected_by_the_confinement():
    for role in ('admin', 'viewer', 'user'):
        assert not confined(client_with_role(role).get('/api/v1/budget/appropriations/')), role


def test_a_deactivated_supplier_is_refused_at_the_tenant_door():
    r = client_with_role('vendor', active=False).get('/api/v1/supplier-portal/anything/')
    assert r.status_code == 403 and r.json().get('error') == 'You do not have access to this tenant'


# --- the tenant door itself (this was open for token requests before the middleware resolved the token) ----------------

@pytest.mark.parametrize('path', ['/api/v1/budget/appropriations/', '/api/v1/budget/warrants/', '/api/v1/tenants/enabled-modules/'])
def test_a_signed_in_user_with_no_role_on_the_tenant_is_refused(path):
    from tenants.models import UserTenantRole
    user, _ = User.objects.get_or_create(username='contain_norole', defaults={'email': 'n@t.test'})
    UserTenantRole.objects.filter(user=user).delete()
    token, _ = Token.objects.get_or_create(user=user)
    _get_tenant_cache().clear()
    c = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
    c.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    r = c.get(path)
    assert r.status_code == 403 and r.json().get('error') == 'You do not have access to this tenant'


def test_a_bad_token_is_left_for_the_view_to_answer_with_401():
    c = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
    c.credentials(HTTP_AUTHORIZATION='Token not-a-real-token')
    assert c.get('/api/v1/budget/appropriations/').status_code == 401


def test_requests_with_no_credentials_are_still_the_views_business():
    r = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN).get('/api/v1/budget/appropriations/')
    assert r.status_code in (401, 403) and r.json().get('error') != 'You do not have access to this tenant'
