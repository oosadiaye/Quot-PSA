"""SnapshotService — orchestrator integration. Heavy mocking of pg_dump
and media collection; we are testing the 6-phase wiring, not pg_dump itself."""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from snapshots.models import SnapshotJob
from snapshots.services.crypto import decrypt_stream
from snapshots.services.snapshot_service import SnapshotService


User = get_user_model()


@pytest.fixture
def actor(db):
    return User.objects.create_user(username='ada', password='x')


@pytest.fixture
def queued_job(actor):
    return SnapshotJob.objects.create(
        schema_name='delta_state',
        triggered_by=actor,
        status=SnapshotJob.Status.QUEUED,
        label='integration test',
    )


@pytest.mark.integration
def test_execute_runs_all_six_phases_and_marks_succeeded(
    queued_job, configured_settings,
):
    """End-to-end: fake pg_dump + skip media + real crypto + real storage."""
    def fake_run_pg_dump(*, schema, dsn, target, pg_dump_bin, timeout_sec=None):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'-- fake pg dump\nSELECT 1;\n')

    with patch('snapshots.services.snapshot_service.run_pg_dump',
               side_effect=fake_run_pg_dump):
        with patch('snapshots.services.snapshot_service.collect_referenced_media',
                   return_value=[]):
            svc = SnapshotService(queued_job)
            svc.execute()

    queued_job.refresh_from_db()
    assert queued_job.status == SnapshotJob.Status.SUCCEEDED
    assert queued_job.completed_at is not None
    assert queued_job.artifact_path
    assert queued_job.size_bytes and queued_job.size_bytes > 0
    assert queued_job.sha256
    assert queued_job.kek_fingerprint == 'kek-test'
    assert queued_job.manifest.get('snapshot', {}).get('schema_name') == 'delta_state'


@pytest.mark.integration
def test_execute_artifact_decrypts_with_kek(
    queued_job, configured_settings, kek_hex,
):
    """The artifact written to disk must be decryptable with the configured KEK."""
    def fake_run_pg_dump(*, schema, dsn, target, pg_dump_bin, timeout_sec=None):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'-- fake\n')

    with patch('snapshots.services.snapshot_service.run_pg_dump',
               side_effect=fake_run_pg_dump):
        with patch('snapshots.services.snapshot_service.collect_referenced_media',
                   return_value=[]):
            svc = SnapshotService(queued_job)
            svc.execute()

    queued_job.refresh_from_db()
    artifact_full = Path(svc.storage.root) / queued_job.artifact_path
    plain_out = io.BytesIO()
    with artifact_full.open('rb') as fh:
        decrypt_stream(fh, plain_out, kek=bytes.fromhex(kek_hex))
    assert plain_out.tell() > 0  # bytes were produced


@pytest.mark.integration
def test_execute_marks_failed_on_pg_dump_error(
    queued_job, configured_settings,
):
    """A pg_dump failure must transition status -> FAILED with error_class set."""
    from snapshots.services.dump import PgDumpError

    def fake_run_pg_dump(*, schema, dsn, target, pg_dump_bin, timeout_sec=None):
        raise PgDumpError('fatal: bad role')

    with patch('snapshots.services.snapshot_service.run_pg_dump',
               side_effect=fake_run_pg_dump):
        svc = SnapshotService(queued_job)
        with pytest.raises(PgDumpError):
            svc.execute()

    queued_job.refresh_from_db()
    assert queued_job.status == SnapshotJob.Status.FAILED
    assert queued_job.error_class == 'PgDumpError'
    assert 'fatal: bad role' in queued_job.error_message


@pytest.mark.integration
def test_manifest_records_encryption_envelope(
    queued_job, configured_settings,
):
    """SnapshotJob.manifest must have non-null iv_b64/tag_b64/wrapped_dek_b64."""
    def fake_run_pg_dump(*, schema, dsn, target, pg_dump_bin, timeout_sec=None):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'-- fake\n')

    with patch('snapshots.services.snapshot_service.run_pg_dump',
               side_effect=fake_run_pg_dump):
        with patch('snapshots.services.snapshot_service.collect_referenced_media',
                   return_value=[]):
            svc = SnapshotService(queued_job)
            svc.execute()

    queued_job.refresh_from_db()
    enc = queued_job.manifest.get('encryption', {})
    assert enc.get('iv_b64'), 'iv_b64 must be filled after _encrypt_and_store'
    assert enc.get('tag_b64'), 'tag_b64 must be filled'
    assert enc.get('wrapped_dek_b64'), 'wrapped_dek_b64 must be filled'
