"""SnapshotJobViewSet — list/retrieve/create with defense-in-depth scoping.

Middleware note: the snapshots API runs in the public schema.
``core.middleware.TenantHeaderMiddleware`` bypasses tenant resolution for
/api/snapshots/ paths, so ``APIClient`` can reach the view without a
tenant domain header.

Celery note: Celery may not be installed in every dev/CI environment.
``snapshots.tasks.run_snapshot_job`` may be a plain function (no ``.delay``
attribute).  Tests patch the whole task object so both envs are covered.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from snapshots.models import SnapshotJob


User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def superuser(db):
    return User.objects.create_user(
        username='super', password='x', is_superuser=True)


@pytest.fixture
def tenant_admin(db):
    return User.objects.create_user(username='ada', password='x')


@pytest.fixture
def api_client():
    return APIClient()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_task():
    """Return a MagicMock that works as both a callable and has .delay."""
    task = MagicMock()
    task.delay = MagicMock()
    return task


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.django_db
def test_anonymous_returns_401(api_client):
    resp = api_client.get('/api/snapshots/')
    assert resp.status_code in (401, 403)


@pytest.mark.integration
def test_authenticated_superadmin_lists_all_jobs(superuser, tenant_admin, api_client):
    SnapshotJob.objects.create(
        schema_name='a', triggered_by=tenant_admin,
        status=SnapshotJob.Status.SUCCEEDED)
    SnapshotJob.objects.create(
        schema_name='b', triggered_by=tenant_admin,
        status=SnapshotJob.Status.SUCCEEDED)
    api_client.force_authenticate(user=superuser)
    resp = api_client.get('/api/snapshots/')
    assert resp.status_code == 200
    # Paginated or non-paginated:
    payload = resp.json()
    items = payload.get('results', payload)
    schemas = {item['schema_name'] for item in items}
    assert {'a', 'b'}.issubset(schemas)


@pytest.mark.integration
def test_tenant_admin_lists_only_own_schema_jobs(tenant_admin, api_client):
    SnapshotJob.objects.create(
        schema_name='mine', triggered_by=tenant_admin,
        status=SnapshotJob.Status.SUCCEEDED)
    SnapshotJob.objects.create(
        schema_name='theirs', triggered_by=tenant_admin,
        status=SnapshotJob.Status.SUCCEEDED)
    api_client.force_authenticate(user=tenant_admin)
    with patch('snapshots.views.tenant_schemas_with_all_access',
               return_value={'mine'}):
        resp = api_client.get('/api/snapshots/')
    assert resp.status_code == 200
    payload = resp.json()
    items = payload.get('results', payload)
    schemas = {item['schema_name'] for item in items}
    assert schemas == {'mine'}


@pytest.mark.integration
def test_create_as_tenant_admin_for_own_schema_succeeds(tenant_admin, api_client):
    mock_task = _mock_task()
    api_client.force_authenticate(user=tenant_admin)
    # CanCreateSnapshot.has_permission calls is_tenant_admin_of from
    # snapshots.permissions, not from snapshots.views.
    with patch('snapshots.permissions.is_tenant_admin_of', return_value=True):
        with patch('snapshots.views.run_snapshot_job', mock_task):
            with patch('snapshots.views.audit.record_created'):
                resp = api_client.post('/api/snapshots/',
                                       {'schema_name': 'delta_state', 'label': 'test'},
                                       format='json')
    assert resp.status_code == 201, resp.content
    job_id = resp.json()['id']
    job = SnapshotJob.objects.get(pk=job_id)
    assert job.schema_name == 'delta_state'
    assert job.triggered_by_id == tenant_admin.pk
    assert job.status == SnapshotJob.Status.QUEUED
    mock_task.delay.assert_called_once_with(job.pk)


@pytest.mark.integration
def test_create_as_tenant_admin_for_other_schema_returns_403(tenant_admin, api_client):
    api_client.force_authenticate(user=tenant_admin)
    with patch('snapshots.permissions.is_tenant_admin_of', return_value=False):
        resp = api_client.post('/api/snapshots/',
                               {'schema_name': 'other', 'label': 'test'},
                               format='json')
    assert resp.status_code == 403


@pytest.mark.integration
def test_create_enqueues_celery_task(tenant_admin, api_client):
    mock_task = _mock_task()
    api_client.force_authenticate(user=tenant_admin)
    with patch('snapshots.permissions.is_tenant_admin_of', return_value=True):
        with patch('snapshots.views.run_snapshot_job', mock_task):
            with patch('snapshots.views.audit.record_created'):
                api_client.post('/api/snapshots/',
                                {'schema_name': 'delta_state'},
                                format='json')
    mock_task.delay.assert_called_once()


@pytest.mark.integration
def test_create_emits_audit(tenant_admin, api_client):
    mock_task = _mock_task()
    api_client.force_authenticate(user=tenant_admin)
    with patch('snapshots.permissions.is_tenant_admin_of', return_value=True):
        with patch('snapshots.views.run_snapshot_job', mock_task):
            with patch('snapshots.views.audit.record_created') as mock_audit:
                api_client.post('/api/snapshots/',
                                {'schema_name': 'delta_state'},
                                format='json')
    mock_audit.assert_called_once()


@pytest.mark.integration
def test_put_method_not_allowed(tenant_admin, api_client):
    job = SnapshotJob.objects.create(
        schema_name='mine', triggered_by=tenant_admin,
        status=SnapshotJob.Status.SUCCEEDED)
    api_client.force_authenticate(user=tenant_admin)
    with patch('snapshots.permissions.is_tenant_admin_of', return_value=True):
        with patch('snapshots.views.tenant_schemas_with_all_access',
                   return_value={'mine'}):
            resp = api_client.put(f'/api/snapshots/{job.pk}/',
                                  {'label': 'changed'}, format='json')
    assert resp.status_code == 405  # Method Not Allowed
