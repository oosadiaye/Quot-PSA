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
        'triggered_by', 'triggered_by_username',
        'triggered_at', 'started_at', 'completed_at',
        'size_bytes', 'sha256', 'manifest',
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
