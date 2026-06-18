"""SnapshotJobViewSet destroy action — soft-expire + file unlink."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from snapshots.models import SnapshotJob


User = get_user_model()


@pytest.fixture
def superuser(db):
    return User.objects.create_user(
        username='super', password='x', is_superuser=True)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def succeeded_job_with_file(superuser, tmp_path):
    """Create a SUCCEEDED job with a real file on disk."""
    storage_root = tmp_path / 'snapshots_storage'
    storage_root.mkdir()
    artifact_relpath = 'delta/snap-1.tar.gz.enc'
    artifact_full = storage_root / artifact_relpath
    artifact_full.parent.mkdir(parents=True, exist_ok=True)
    artifact_full.write_bytes(b'fake encrypted data')

    job = SnapshotJob.objects.create(
        schema_name='delta', triggered_by=superuser,
        status=SnapshotJob.Status.SUCCEEDED,
        artifact_path=artifact_relpath,
        size_bytes=artifact_full.stat().st_size,
    )
    return job, str(storage_root)


@pytest.mark.integration
@pytest.mark.django_db
def test_delete_succeeded_job_transitions_to_expired(
    succeeded_job_with_file, superuser, api_client,
):
    job, storage_root = succeeded_job_with_file
    api_client.force_authenticate(user=superuser)

    with override_settings(SNAPSHOTS_BACKUP_DIR=storage_root):
        with patch('snapshots.views.audit.record_deleted'):
            resp = api_client.delete(f'/api/snapshots/{job.pk}/')

    assert resp.status_code == 204
    job.refresh_from_db()
    assert job.status == SnapshotJob.Status.EXPIRED
    assert job.artifact_path == ''


@pytest.mark.integration
@pytest.mark.django_db
def test_delete_unlinks_artifact_file(
    succeeded_job_with_file, superuser, api_client,
):
    job, storage_root = succeeded_job_with_file
    api_client.force_authenticate(user=superuser)
    artifact_full = Path(storage_root) / 'delta' / 'snap-1.tar.gz.enc'
    assert artifact_full.exists()

    with override_settings(SNAPSHOTS_BACKUP_DIR=storage_root):
        with patch('snapshots.views.audit.record_deleted'):
            api_client.delete(f'/api/snapshots/{job.pk}/')

    assert not artifact_full.exists()


@pytest.mark.integration
@pytest.mark.django_db
def test_delete_preserves_audit_row(
    succeeded_job_with_file, superuser, api_client,
):
    """The SnapshotJob row stays in DB (status=EXPIRED), not actually deleted."""
    job, storage_root = succeeded_job_with_file
    api_client.force_authenticate(user=superuser)

    with override_settings(SNAPSHOTS_BACKUP_DIR=storage_root):
        with patch('snapshots.views.audit.record_deleted'):
            api_client.delete(f'/api/snapshots/{job.pk}/')

    # Row still exists; triggered_by, triggered_at retained
    refreshed = SnapshotJob.objects.get(pk=job.pk)
    assert refreshed.status == SnapshotJob.Status.EXPIRED
    assert refreshed.triggered_by_id == superuser.pk
    assert refreshed.triggered_at is not None


@pytest.mark.integration
@pytest.mark.django_db
def test_delete_emits_audit(
    succeeded_job_with_file, superuser, api_client,
):
    job, storage_root = succeeded_job_with_file
    api_client.force_authenticate(user=superuser)

    with override_settings(SNAPSHOTS_BACKUP_DIR=storage_root):
        with patch('snapshots.views.audit.record_deleted') as mock_audit:
            api_client.delete(f'/api/snapshots/{job.pk}/')

    mock_audit.assert_called_once()


@pytest.mark.integration
@pytest.mark.django_db
def test_delete_already_expired_returns_204_idempotent(superuser, api_client):
    """Re-delete is a no-op."""
    job = SnapshotJob.objects.create(
        schema_name='delta', triggered_by=superuser,
        status=SnapshotJob.Status.EXPIRED,
        artifact_path='',
    )
    api_client.force_authenticate(user=superuser)

    with patch('snapshots.views.audit.record_deleted'):
        resp = api_client.delete(f'/api/snapshots/{job.pk}/')

    assert resp.status_code == 204


@pytest.mark.integration
@pytest.mark.django_db
def test_delete_succeeds_when_file_already_gone(superuser, api_client, tmp_path):
    """Storage already lost the file — destroy still expires the row."""
    storage_root = tmp_path / 'snapshots_storage'
    storage_root.mkdir()
    job = SnapshotJob.objects.create(
        schema_name='delta', triggered_by=superuser,
        status=SnapshotJob.Status.SUCCEEDED,
        artifact_path='delta/nonexistent.tar.gz.enc',  # file does NOT exist
    )
    api_client.force_authenticate(user=superuser)

    with override_settings(SNAPSHOTS_BACKUP_DIR=str(storage_root)):
        with patch('snapshots.views.audit.record_deleted'):
            resp = api_client.delete(f'/api/snapshots/{job.pk}/')

    assert resp.status_code == 204
    job.refresh_from_db()
    assert job.status == SnapshotJob.Status.EXPIRED
