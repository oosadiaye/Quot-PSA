"""Regression tests for ``TenantAccessMiddleware`` and the public schema.

Root cause captured here
------------------------
``TenantAccessMiddleware`` enforces that an authenticated, non-superuser
request carries a ``UserTenantRole`` for ``request.tenant``. That rule is
correct for *tenant* schemas, but the **public** (platform) schema is not
a tenant anyone is a "member" of — no ``UserTenantRole`` ever points at
it.

The bug: a browser that still holds a Django **session cookie** from
login (``withCredentials: true``) issues a *bare* request to an
``AllowAny`` endpoint that has no ``X-Tenant-Domain`` header — e.g.
``GET /api/v1/tenants/public-branding/``. With no tenant header,
``TenantMainMiddleware`` resolves the host (``localhost``) to the
**public** schema, ``AuthenticationMiddleware`` hydrates the session
user, and the membership check then fails with
``403 {"error": "You do not have access to this tenant"}`` — even though
the endpoint is explicitly public.

These tests pin the fix (public schema is exempt from the membership
check) while guarding that real tenant schemas stay enforced.

They are no-DB / pure-Python: the membership query and ``schema_context``
are mocked so the test exercises the middleware *branching*, not the ORM.
"""
from __future__ import annotations

import contextlib
from unittest import mock

import pytest
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory


PUBLIC_BRANDING_PATH = '/api/v1/tenants/public-branding/'


@pytest.fixture
def rf():
    return RequestFactory()


class _Tenant:
    """Minimal stand-in for a ``Client`` row — the middleware only reads
    ``schema_name``."""

    def __init__(self, schema_name: str):
        self.schema_name = schema_name


class _User:
    """Authenticated non-superuser. ``pk`` feeds the access cache key."""

    is_authenticated = True
    is_superuser = False
    pk = 12


def _build_middleware(downstream_status: int = 200):
    """Return ``(middleware, sentinel_response)``. The sentinel is what a
    *non-blocked* request must yield — i.e. the middleware called through
    to ``get_response`` instead of short-circuiting with a 403."""
    sentinel = HttpResponse(status=downstream_status)
    from core.middleware import TenantAccessMiddleware

    return TenantAccessMiddleware(lambda request: sentinel), sentinel


@contextlib.contextmanager
def _patched_membership(*, has_access: bool):
    """Patch the DB-touching bits so the test stays no-DB and the
    membership outcome is deterministic.

    * ``schema_context`` → a no-op context manager (no search_path / DB).
    * ``UserTenantRole.objects.filter(...).exists()`` → ``has_access``.
    * tenant cache → always-miss so the query branch runs.
    """
    fake_cache = mock.Mock()
    fake_cache.get.return_value = None  # force cache miss → DB branch

    fake_utr = mock.Mock()
    fake_utr.objects.filter.return_value.exists.return_value = has_access

    with mock.patch('core.middleware._get_tenant_cache', return_value=fake_cache), \
            mock.patch('core.middleware.schema_context',
                       lambda *a, **k: contextlib.nullcontext()), \
            mock.patch('tenants.models.UserTenantRole', fake_utr):
        yield


def _make_request(rf, *, tenant_schema: str, user=None):
    request = rf.get(PUBLIC_BRANDING_PATH)
    request.user = user if user is not None else _User()
    request.tenant = _Tenant(tenant_schema)
    return request


class TestPublicSchemaExempt:
    """The public schema must never be subjected to the membership check."""

    def test_public_schema_request_is_not_403(self, rf):
        """Authenticated non-superuser hitting an AllowAny endpoint that
        resolved to the public schema must pass through, not 403."""
        middleware, sentinel = _build_middleware()
        request = _make_request(rf, tenant_schema='public')

        # has_access=False would 403 *if* the buggy membership branch ran.
        with _patched_membership(has_access=False):
            response = middleware(request)

        assert response is sentinel
        assert response.status_code == 200
        assert not isinstance(response, JsonResponse)


class TestRealTenantStillEnforced:
    """Guard against an over-broad fix — real tenants keep their gate."""

    def test_tenant_member_passes(self, rf):
        middleware, sentinel = _build_middleware()
        request = _make_request(rf, tenant_schema='office_oag')

        with _patched_membership(has_access=True):
            # subscription lookup also runs once access passes; return an
            # 'active' subscription so the request completes normally.
            with mock.patch('tenants.models.TenantSubscription') as sub:
                sub.objects.get.return_value.status = 'active'
                response = middleware(request)

        assert response is sentinel
        assert response.status_code == 200

    def test_non_member_is_403(self, rf):
        middleware, _ = _build_middleware()
        request = _make_request(rf, tenant_schema='office_oag')

        with _patched_membership(has_access=False):
            response = middleware(request)

        assert response.status_code == 403
        assert b'do not have access' in response.content
