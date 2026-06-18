"""SnapshotJobSerializer — field exposure + create validation."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from snapshots.models import SnapshotJob
from snapshots.serializers import SnapshotJobSerializer


User = get_user_model()


@pytest.fixture
def actor(db):
    return User.objects.create_user(username='ada', password='x')


@pytest.mark.integration
def test_serializer_exposes_read_fields(actor):
    job = SnapshotJob.objects.create(
        schema_name='delta_state',
        triggered_by=actor,
        status=SnapshotJob.Status.SUCCEEDED,
        label='test',
        artifact_path='delta_state/snap.tar.gz.enc',
        size_bytes=1024,
        sha256='deadbeef',
    )
    data = SnapshotJobSerializer(job).data
    for key in (
        'id', 'schema_name', 'label', 'status', 'status_display',
        'triggered_by_username',
        'triggered_at', 'started_at', 'completed_at',
        'size_bytes', 'sha256', 'manifest_summary',
        'error_class', 'error_message',
        'has_artifact',
    ):
        assert key in data, f'missing field: {key}'


@pytest.mark.integration
def test_serializer_does_not_expose_artifact_path(actor):
    """artifact_path is an internal storage detail — never exposed to clients."""
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor,
        artifact_path='secret/path.tar.gz.enc',
    )
    data = SnapshotJobSerializer(job).data
    assert 'artifact_path' not in data


@pytest.mark.integration
def test_serializer_does_not_expose_kek_fingerprint(actor):
    """kek_fingerprint is internal — clients shouldn't see which key was used."""
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor,
        kek_fingerprint='kek-v1',
    )
    data = SnapshotJobSerializer(job).data
    assert 'kek_fingerprint' not in data


@pytest.mark.integration
def test_has_artifact_true_when_succeeded(actor):
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor,
        status=SnapshotJob.Status.SUCCEEDED,
        artifact_path='delta_state/snap.tar.gz.enc',
    )
    data = SnapshotJobSerializer(job).data
    assert data['has_artifact'] is True


@pytest.mark.integration
def test_has_artifact_false_when_expired(actor):
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor,
        status=SnapshotJob.Status.EXPIRED,
        artifact_path='',
    )
    data = SnapshotJobSerializer(job).data
    assert data['has_artifact'] is False


@pytest.mark.integration
def test_has_artifact_false_when_failed(actor):
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor,
        status=SnapshotJob.Status.FAILED,
        artifact_path='',
    )
    data = SnapshotJobSerializer(job).data
    assert data['has_artifact'] is False


@pytest.mark.integration
def test_has_artifact_false_when_succeeded_but_no_path(actor):
    """Anomalous state: SUCCEEDED but artifact_path empty (e.g., post-retention)."""
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor,
        status=SnapshotJob.Status.SUCCEEDED,
        artifact_path='',
    )
    data = SnapshotJobSerializer(job).data
    assert data['has_artifact'] is False


@pytest.mark.integration
def test_manifest_summary_strips_encryption_envelope(actor):
    """API must NOT expose wrapped_dek_b64, iv_b64, or tag_b64."""
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor,
        status=SnapshotJob.Status.SUCCEEDED,
        manifest={
            'schema_version': 1,
            'snapshot': {'created_at_utc': '2026-06-18T00:00:00Z'},
            'source': {
                'pii_key_fingerprint': 'sk-deadbeef',
                'code_version': 'main@abc1234',
                'django_version': '5.2.4',
            },
            'contents': {
                'database_sql_sha256': 'abc123',
                'media_file_count': 5,
                'media_total_bytes': 100,
            },
            'encryption': {
                'algorithm': 'AES-256-GCM',
                'kek_id': 'kek-v1',
                'wrapped_dek_b64': 'SECRET_WRAPPED_DEK',
                'iv_b64': 'SECRET_IV',
                'tag_b64': 'SECRET_TAG',
            },
        },
    )
    data = SnapshotJobSerializer(job).data
    # The summary should be present but should NOT include any crypto material
    # or PII fingerprint or code version.
    summary = data['manifest_summary']
    assert 'wrapped_dek_b64' not in str(summary)
    assert 'iv_b64' not in str(summary)
    assert 'tag_b64' not in str(summary)
    assert 'SECRET_WRAPPED_DEK' not in str(summary)
    assert 'SECRET_IV' not in str(summary)
    assert 'SECRET_TAG' not in str(summary)
    assert 'pii_key_fingerprint' not in str(summary)
    assert 'code_version' not in str(summary)
    # Operationally useful fields should be present
    assert summary['schema_version'] == 1
    assert summary['database_sql_sha256'] == 'abc123'
    assert summary['media_file_count'] == 5


@pytest.mark.integration
def test_triggered_by_pk_not_exposed(actor):
    """Don't leak internal user IDs to API clients."""
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor)
    data = SnapshotJobSerializer(job).data
    assert 'triggered_by' not in data, \
        'triggered_by user PK must not be exposed; use triggered_by_username instead'
    assert data['triggered_by_username'] == 'ada'


@pytest.mark.integration
def test_create_validation_accepts_valid_payload(actor):
    serializer = SnapshotJobSerializer(data={
        'schema_name': 'delta_state',
        'label': 'pre-import',
    })
    assert serializer.is_valid(), serializer.errors


@pytest.mark.integration
def test_create_validation_rejects_bad_schema_name(actor):
    serializer = SnapshotJobSerializer(data={
        'schema_name': 'Bad-Schema!',
        'label': 'test',
    })
    assert not serializer.is_valid()
    assert 'schema_name' in serializer.errors


@pytest.mark.integration
def test_create_validation_requires_schema_name(actor):
    serializer = SnapshotJobSerializer(data={'label': 'no schema'})
    assert not serializer.is_valid()
    assert 'schema_name' in serializer.errors


@pytest.mark.integration
def test_label_max_length_enforced(actor):
    """label > 120 chars rejected at serializer layer."""
    serializer = SnapshotJobSerializer(data={
        'schema_name': 'delta_state',
        'label': 'x' * 121,
    })
    assert not serializer.is_valid()
    assert 'label' in serializer.errors
