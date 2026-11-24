"""Signing out really ends the login, for every kind of user.

Two bugs made it half-work:

* ``logout_view`` fell under the default model-permission check, which has no
  model to look at for this view and so refused every non-admin (and, on the
  public host, every non-superuser). Their token and session were never revoked.
* ``logout = logout_view`` (a backward-compat alias) shadowed Django's
  ``logout`` import, so ``logout(request)`` inside the view called the view
  itself and crashed with a 500 after the token had already been deleted.
"""
from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import override_settings
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import UserSession
from tenants.models import Client, UserTenantRole

URL = '/api/v1/core/auth/logout/'
DOMAIN = 'pytest.localhost'

pytestmark = pytest.mark.django_db


def _signed_in(role='user'):
    tenant = Client.objects.get(schema_name='pytest_schema')
    user = User.objects.create_user(f'logout_{role}', f'logout_{role}@t.test', 'Pass-1234-xyz')
    UserTenantRole.objects.create(user=user, tenant=tenant, role=role, is_active=True)
    token, _ = Token.objects.get_or_create(user=user)
    with schema_context('public'):
        UserSession.objects.create(user=user, token_key=token.key)
    client = APIClient(HTTP_HOST=DOMAIN, HTTP_X_TENANT_DOMAIN=DOMAIN)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return user, token, client


def _post(client):
    # Logout is a public-path route: the tenant comes from the Host header, and only
    # 'testserver' is an allowed host under test, so allow the tenant's.
    with override_settings(ALLOWED_HOSTS=[*settings.ALLOWED_HOSTS, DOMAIN]):
        return client.post(URL)


@pytest.mark.parametrize('role', ['user', 'viewer', 'manager', 'admin'])
def test_every_role_can_sign_out_and_it_revokes_the_login(role):
    user, token, client = _signed_in(role)

    response = _post(client)

    assert response.status_code == 200, response.content
    assert not Token.objects.filter(key=token.key).exists()
    with schema_context('public'):
        assert UserSession.objects.get(token_key=token.key).is_active is False


def test_signing_out_with_no_login_is_still_a_normal_logout():
    # A page can be left open past its token's life; signing out then must not error.
    anonymous = APIClient(HTTP_HOST=DOMAIN, HTTP_X_TENANT_DOMAIN=DOMAIN)
    assert _post(anonymous).status_code == 200


def test_the_logout_alias_does_not_shadow_djangos_function():
    import core.views.auth as auth_module

    # The alias for old importers still points at the view...
    assert auth_module.logout is auth_module.logout_view
    # ...and the view calls Django's real logout under a name the alias cannot shadow.
    assert auth_module.django_logout.__module__ == 'django.contrib.auth'
