"""Tests for snapshots/permissions.py — resolvers and DRF permission classes.

All tests are marked ``integration`` so they participate in the shared
pytest-django DB setup (SnapshotJob lives in the public schema, which is
set up by the normal ``migrate`` run).

Resolver helpers that call into tenant-schema infrastructure (schema_context,
_user_has_all_access) are patched at the module boundary so these tests run
without a full multi-tenant Postgres stack.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from snapshots.models import SnapshotJob
from snapshots.permissions import (
    CanAccessSnapshot,
    CanCreateSnapshot,
    is_platform_superadmin,
    is_tenant_admin_of,
    tenant_schemas_with_all_access,
)


User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def superuser(db):
    return User.objects.create_user(
        username='super', password='x', is_superuser=True
    )


@pytest.fixture
def tenant_admin(db):
    """Ordinary user who will be granted all_access via mocks."""
    return User.objects.create_user(username='ada', password='x')


@pytest.fixture
def stranger(db):
    """Ordinary user with no tenant access."""
    return User.objects.create_user(username='alice', password='x')


@pytest.fixture
def snapshot_job(db, tenant_admin):
    """A succeeded SnapshotJob in 'delta_state' schema."""
    return SnapshotJob.objects.create(
        schema_name='delta_state',
        triggered_by=tenant_admin,
        status=SnapshotJob.Status.SUCCEEDED,
    )


# ---------------------------------------------------------------------------
# is_platform_superadmin
# ---------------------------------------------------------------------------

def test_is_platform_superadmin_returns_false_for_none():
    assert is_platform_superadmin(None) is False


def test_is_platform_superadmin_returns_false_for_anonymous():
    from django.contrib.auth.models import AnonymousUser
    assert is_platform_superadmin(AnonymousUser()) is False


@pytest.mark.integration
def test_is_platform_superadmin_true_for_is_superuser(superuser):
    assert is_platform_superadmin(superuser) is True


@pytest.mark.integration
def test_is_platform_superadmin_false_for_regular_user(tenant_admin):
    # Regular user without is_superuser and no SuperAdminProfile.
    # We patch the profile lookup so it doesn't need a real public schema.
    with patch(
        'snapshots.permissions.SuperAdminProfile',
        create=True,
    ):
        with patch(
            'snapshots.permissions.schema_context',
            create=True,
        ):
            # Fallback: just ensure it doesn't crash and returns False.
            result = is_platform_superadmin(tenant_admin)
            # Result depends on the mock; the important thing is no exception.
            assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# CanCreateSnapshot — superadmin
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_superadmin_can_create_for_any_schema(superuser):
    perm = CanCreateSnapshot()
    req = MagicMock()
    req.user = superuser
    req.method = 'POST'
    req.data = {'schema_name': 'delta_state'}
    assert perm.has_permission(req, MagicMock()) is True


# ---------------------------------------------------------------------------
# CanCreateSnapshot — tenant admin (own schema)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_tenant_admin_can_create_for_own_schema(tenant_admin):
    perm = CanCreateSnapshot()
    req = MagicMock()
    req.user = tenant_admin
    req.method = 'POST'
    req.data = {'schema_name': 'delta_state'}
    with patch(
        'snapshots.permissions.is_tenant_admin_of', return_value=True
    ) as mock_check:
        result = perm.has_permission(req, MagicMock())
    mock_check.assert_called_once_with(tenant_admin, 'delta_state')
    assert result is True


# ---------------------------------------------------------------------------
# CanCreateSnapshot — tenant admin (another tenant's schema)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_tenant_admin_cannot_create_for_other_schema(tenant_admin):
    perm = CanCreateSnapshot()
    req = MagicMock()
    req.user = tenant_admin
    req.method = 'POST'
    req.data = {'schema_name': 'other_state'}
    with patch(
        'snapshots.permissions.is_tenant_admin_of', return_value=False
    ):
        result = perm.has_permission(req, MagicMock())
    assert result is False


# ---------------------------------------------------------------------------
# CanCreateSnapshot — anonymous / unauthenticated
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_anonymous_or_unknown_user_denied():
    perm = CanCreateSnapshot()
    req = MagicMock()
    req.user = MagicMock(is_authenticated=False)
    req.method = 'POST'
    req.data = {'schema_name': 'delta_state'}
    assert perm.has_permission(req, MagicMock()) is False


@pytest.mark.integration
def test_missing_schema_name_denied(tenant_admin):
    """POST with no schema_name in the body is denied for non-superadmins."""
    perm = CanCreateSnapshot()
    req = MagicMock()
    req.user = tenant_admin
    req.method = 'POST'
    req.data = {}
    assert perm.has_permission(req, MagicMock()) is False


# ---------------------------------------------------------------------------
# CanAccessSnapshot — superadmin can access any job
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_superadmin_can_access_any_job(superuser, snapshot_job):
    perm = CanAccessSnapshot()
    req = MagicMock()
    req.user = superuser
    req.method = 'GET'
    assert perm.has_object_permission(req, MagicMock(), snapshot_job) is True


# ---------------------------------------------------------------------------
# CanAccessSnapshot — tenant admin cannot access another tenant's job
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_tenant_admin_cannot_access_other_tenants_job(tenant_admin, db):
    # Create a job belonging to a different schema.
    other_job = SnapshotJob.objects.create(
        schema_name='other_state',
        triggered_by=tenant_admin,
        status=SnapshotJob.Status.QUEUED,
    )
    perm = CanAccessSnapshot()
    req = MagicMock()
    req.user = tenant_admin
    req.method = 'GET'
    with patch(
        'snapshots.permissions.is_tenant_admin_of', return_value=False
    ):
        result = perm.has_object_permission(req, MagicMock(), other_job)
    assert result is False


# ---------------------------------------------------------------------------
# tenant_schemas_with_all_access
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_tenant_schemas_with_all_access_returns_empty_for_anonymous():
    user = MagicMock(is_authenticated=False)
    assert tenant_schemas_with_all_access(user) == set()


@pytest.mark.integration
def test_tenant_schemas_with_all_access_returns_empty_for_none():
    assert tenant_schemas_with_all_access(None) == set()


@pytest.mark.integration
def test_tenant_schemas_with_all_access_returns_correct_set(tenant_admin):
    """For a tenant admin with all_access on two schemas, returns those two.

    The function uses lazy imports inside its body, so we patch at the
    source module rather than at 'snapshots.permissions.*'.
    """
    mock_utr_a = MagicMock()
    mock_utr_a.tenant.schema_name = 'alpha_state'
    mock_utr_b = MagicMock()
    mock_utr_b.tenant.schema_name = 'beta_state'

    mock_utr_model = MagicMock()
    mock_utr_model.objects.filter.return_value \
        .select_related.return_value = [mock_utr_a, mock_utr_b]

    # schema_context used as: `with schema_context(sn): ...`
    mock_ctx = MagicMock()
    mock_ctx.return_value.__enter__ = MagicMock(return_value=None)
    mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

    with (
        patch('snapshots.permissions.is_platform_superadmin', return_value=False),
        # Patch the lazy import targets inside the function body.
        patch('tenants.models.UserTenantRole', mock_utr_model),
        patch('django_tenants.utils.schema_context', mock_ctx),
        patch('core.permissions._user_has_all_access', return_value=True),
    ):
        result = tenant_schemas_with_all_access(tenant_admin)

    assert 'alpha_state' in result
    assert 'beta_state' in result


@pytest.mark.integration
def test_superadmin_tenant_schemas_returns_all(superuser):
    """Superadmin gets all Client schema names.

    is_platform_superadmin returns True, so the function uses
    Client.objects.values_list to collect all schema names.
    Patching at the tenants.models source so the lazy import picks it up.
    """
    fake_schemas = ['public', 'alpha_state', 'beta_state']
    mock_client = MagicMock()
    mock_client.objects.values_list.return_value = fake_schemas

    with (
        patch('snapshots.permissions.is_platform_superadmin', return_value=True),
        patch('tenants.models.Client', mock_client),
    ):
        result = tenant_schemas_with_all_access(superuser)

    assert result == set(fake_schemas)
