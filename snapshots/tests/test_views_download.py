"""SnapshotJobViewSet download action — stream-decrypt + audit."""
from __future__ import annotations

import io
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from snapshots.models import SnapshotJob


User = get_user_model()
KEK_HEX = 'aa' * 32


@pytest.fixture
def superuser(db):
    return User.objects.create_user(
        username='super', password='x', is_superuser=True)


@pytest.fixture
def api_client():
    return APIClient()


def _make_artifact(workdir: Path) -> bytes:
    """Build a fake encrypted snapshot artifact and return its bytes."""
    import json
    from snapshots.services.crypto import encrypt_stream

    # Build a minimal tarball
    inner_tar = io.BytesIO()
    with tarfile.open(fileobj=inner_tar, mode='w:gz') as tar:
        manifest_bytes = json.dumps({'test': 'fake'}).encode()
        info = tarfile.TarInfo('manifest.json')
        info.size = len(manifest_bytes)
        tar.addfile(info, io.BytesIO(manifest_bytes))
    inner_tar.seek(0)

    cipher_buf = io.BytesIO()
    encrypt_stream(
        inner_tar, cipher_buf,
        kek=bytes.fromhex(KEK_HEX), kek_id='kek-test',
    )
    return cipher_buf.getvalue()


@pytest.fixture
def succeeded_job_with_artifact(superuser, tmp_path):
    """Create a SUCCEEDED job and write a real encrypted artifact to disk."""
    storage_root = tmp_path / 'snapshots_storage'
    storage_root.mkdir()
    artifact_relpath = 'delta/snap-1.tar.gz.enc'
    artifact_full = storage_root / artifact_relpath
    artifact_full.parent.mkdir(parents=True, exist_ok=True)
    artifact_full.write_bytes(_make_artifact(tmp_path))

    job = SnapshotJob.objects.create(
        schema_name='delta', triggered_by=superuser,
        status=SnapshotJob.Status.SUCCEEDED,
        artifact_path=artifact_relpath,
        size_bytes=artifact_full.stat().st_size,
    )
    return job, str(storage_root)


@pytest.mark.integration
@pytest.mark.django_db
def test_download_succeeded_job_returns_decrypted_artifact(
    succeeded_job_with_artifact, superuser, api_client,
):
    job, storage_root = succeeded_job_with_artifact
    api_client.force_authenticate(user=superuser)

    from django.test import override_settings
    with override_settings(
        SNAPSHOTS_KEK_HEX=KEK_HEX,
        SNAPSHOTS_BACKUP_DIR=storage_root,
    ):
        with patch('snapshots.views.audit.record_downloaded'):
            resp = api_client.get(f'/api/snapshots/{job.pk}/download/')

    assert resp.status_code == 200
    # Body is the decrypted tarball
    body = b''.join(resp.streaming_content)
    assert len(body) > 0
    # Should be a valid gzipped tar
    with tarfile.open(fileobj=io.BytesIO(body), mode='r:gz') as tar:
        names = tar.getnames()
        assert 'manifest.json' in names


@pytest.mark.integration
@pytest.mark.django_db
def test_download_failed_job_returns_404(superuser, api_client):
    job = SnapshotJob.objects.create(
        schema_name='delta', triggered_by=superuser,
        status=SnapshotJob.Status.FAILED,
        artifact_path='',
    )
    api_client.force_authenticate(user=superuser)
    resp = api_client.get(f'/api/snapshots/{job.pk}/download/')
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.django_db
def test_download_expired_job_returns_404(superuser, api_client):
    job = SnapshotJob.objects.create(
        schema_name='delta', triggered_by=superuser,
        status=SnapshotJob.Status.EXPIRED,
        artifact_path='',
    )
    api_client.force_authenticate(user=superuser)
    resp = api_client.get(f'/api/snapshots/{job.pk}/download/')
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.django_db
def test_download_emits_audit_with_ip(
    succeeded_job_with_artifact, superuser, api_client,
):
    job, storage_root = succeeded_job_with_artifact
    api_client.force_authenticate(user=superuser)

    from django.test import override_settings
    with override_settings(
        SNAPSHOTS_KEK_HEX=KEK_HEX,
        SNAPSHOTS_BACKUP_DIR=storage_root,
    ):
        with patch('snapshots.views.audit.record_downloaded') as mock_audit:
            api_client.get(f'/api/snapshots/{job.pk}/download/',
                           REMOTE_ADDR='10.0.0.42')

    mock_audit.assert_called_once()
    kwargs = mock_audit.call_args.kwargs
    assert kwargs.get('ip_address') == '10.0.0.42'


@pytest.mark.integration
@pytest.mark.django_db
def test_download_returns_correct_content_disposition_header(
    succeeded_job_with_artifact, superuser, api_client,
):
    job, storage_root = succeeded_job_with_artifact
    api_client.force_authenticate(user=superuser)

    from django.test import override_settings
    with override_settings(
        SNAPSHOTS_KEK_HEX=KEK_HEX,
        SNAPSHOTS_BACKUP_DIR=storage_root,
    ):
        with patch('snapshots.views.audit.record_downloaded'):
            resp = api_client.get(f'/api/snapshots/{job.pk}/download/')

    assert 'Content-Disposition' in resp.headers
    assert 'attachment' in resp.headers['Content-Disposition']
    assert f'{job.id}.tar.gz' in resp.headers['Content-Disposition']
    assert resp.headers.get('X-Content-Type-Options') == 'nosniff'
