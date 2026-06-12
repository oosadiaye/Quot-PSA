"""RetentionService — age rule + per-tenant count rule + orphan-file resilience."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from snapshots.models import SnapshotJob
from snapshots.services.retention import RetentionService


User = get_user_model()


def _make_job(actor, schema, age_days=0, status=SnapshotJob.Status.SUCCEEDED,
              artifact_path='dummy.tar.gz.enc'):
    job = SnapshotJob.objects.create(
        schema_name=schema, triggered_by=actor, status=status,
        artifact_path=artifact_path)
    if age_days:
        SnapshotJob.objects.filter(pk=job.pk).update(
            triggered_at=timezone.now() - timedelta(days=age_days))
    return SnapshotJob.objects.get(pk=job.pk)


@pytest.fixture
def actor(db):
    return User.objects.create_user(username='ada', password='x')


@pytest.mark.integration
@override_settings(SNAPSHOTS_RETENTION_DAYS=14, SNAPSHOTS_MAX_PER_TENANT=99)
def test_age_rule_expires_old_jobs(actor, tmp_path):
    old = _make_job(actor, 'delta_state', age_days=20)
    fresh = _make_job(actor, 'delta_state', age_days=1)
    storage = _FakeStorage(tmp_path)
    storage.touch(old.artifact_path)
    storage.touch(fresh.artifact_path)

    report = RetentionService(storage=storage).enforce_for_schema('delta_state')

    old.refresh_from_db(); fresh.refresh_from_db()
    assert old.status == SnapshotJob.Status.EXPIRED
    assert old.artifact_path == ''
    assert fresh.status == SnapshotJob.Status.SUCCEEDED
    assert report.expired_count == 1


@pytest.mark.integration
@override_settings(SNAPSHOTS_RETENTION_DAYS=365, SNAPSHOTS_MAX_PER_TENANT=2)
def test_count_rule_keeps_most_recent(actor, tmp_path):
    jobs = [_make_job(actor, 'delta_state', age_days=i) for i in range(5)]
    storage = _FakeStorage(tmp_path)
    for j in jobs:
        storage.touch(j.artifact_path)

    RetentionService(storage=storage).enforce_for_schema('delta_state')

    surviving = SnapshotJob.objects.filter(
        schema_name='delta_state', status=SnapshotJob.Status.SUCCEEDED)
    assert surviving.count() == 2  # newest 2 kept


@pytest.mark.integration
def test_both_rules_can_coexist(actor, tmp_path):
    with override_settings(SNAPSHOTS_RETENTION_DAYS=7,
                            SNAPSHOTS_MAX_PER_TENANT=2):
        ancient = _make_job(actor, 'delta_state', age_days=30)
        old1 = _make_job(actor, 'delta_state', age_days=2)
        old2 = _make_job(actor, 'delta_state', age_days=1)
        new = _make_job(actor, 'delta_state', age_days=0)
        storage = _FakeStorage(tmp_path)
        for j in (ancient, old1, old2, new):
            storage.touch(j.artifact_path)

        RetentionService(storage=storage).enforce_for_schema('delta_state')

        ancient.refresh_from_db(); old1.refresh_from_db()
        old2.refresh_from_db(); new.refresh_from_db()
        assert ancient.status == SnapshotJob.Status.EXPIRED
        assert new.status == SnapshotJob.Status.SUCCEEDED


@pytest.mark.integration
def test_orphan_file_does_not_raise(actor, tmp_path):
    with override_settings(SNAPSHOTS_RETENTION_DAYS=1):
        old = _make_job(actor, 'delta_state', age_days=10)
        storage = _FakeStorage(tmp_path)

        RetentionService(storage=storage).enforce_for_schema('delta_state')

        old.refresh_from_db()
        assert old.status == SnapshotJob.Status.EXPIRED


class _FakeStorage:
    def __init__(self, root: Path):
        self.root = root
    def open_write(self, rel): return (self.root / rel).open('wb')
    def open_read(self, rel): return (self.root / rel).open('rb')
    def delete(self, rel):
        try:
            (self.root / rel).unlink()
        except FileNotFoundError:
            pass
    def size(self, rel): return (self.root / rel).stat().st_size
    def exists(self, rel): return (self.root / rel).exists()
    def touch(self, rel):
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'x')
