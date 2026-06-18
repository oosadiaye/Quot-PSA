"""Celery task wrappers — orchestration, retention beat, stale-job reaper."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from snapshots.models import SnapshotJob
from snapshots.tasks import (
    _run_snapshot_job,
    enforce_retention_all,
    reap_stale_jobs,
    run_snapshot_job,
)


User = get_user_model()


@pytest.fixture
def actor(db):
    return User.objects.create_user(username='ada', password='x')


@pytest.mark.integration
def test_run_snapshot_job_delegates_to_service(actor):
    """_run_snapshot_job(job_id) re-loads the job and calls execute()."""
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor,
        status=SnapshotJob.Status.QUEUED)

    calls = {'execute': 0}

    class FakeSvc:
        def __init__(self, job_arg, storage=None):
            calls['received_pk'] = job_arg.pk
        def execute(self):
            calls['execute'] += 1

    with patch('snapshots.tasks.SnapshotService', FakeSvc):
        _run_snapshot_job(job.pk)

    assert calls['execute'] == 1
    assert calls['received_pk'] == job.pk


@pytest.mark.integration
def test_run_snapshot_job_missing_id_is_noop(actor):
    """If the job_id doesn't exist (deleted between enqueue and run), no raise."""
    # Should not raise.
    _run_snapshot_job(999_999_999)


@pytest.mark.integration
@override_settings(SNAPSHOTS_RETENTION_DAYS=14, SNAPSHOTS_MAX_PER_TENANT=99)
def test_enforce_retention_all_visits_each_schema(actor):
    SnapshotJob.objects.create(
        schema_name='a', triggered_by=actor,
        status=SnapshotJob.Status.SUCCEEDED)
    SnapshotJob.objects.create(
        schema_name='b', triggered_by=actor,
        status=SnapshotJob.Status.SUCCEEDED)
    SnapshotJob.objects.create(
        schema_name='b', triggered_by=actor,   # duplicate schema
        status=SnapshotJob.Status.SUCCEEDED)

    visited = []

    class FakeRetention:
        def __init__(self, storage=None):
            pass
        def enforce_for_schema(self, schema_name):
            visited.append(schema_name)

    with patch('snapshots.tasks.RetentionService', FakeRetention):
        enforce_retention_all()

    assert set(visited) == {'a', 'b'}   # distinct schemas only


@pytest.mark.integration
@override_settings(
    SNAPSHOTS_HARD_TIME_LIMIT_SEC=60,
    SNAPSHOTS_REAPER_BUFFER_SEC=300,
)
def test_reap_stale_jobs_marks_long_running_failed(actor):
    """A job stuck in RUNNING past hard limit + buffer becomes FAILED."""
    stale = SnapshotJob.objects.create(
        schema_name='delta', triggered_by=actor,
        status=SnapshotJob.Status.RUNNING)
    SnapshotJob.objects.filter(pk=stale.pk).update(
        started_at=timezone.now() - timedelta(seconds=60 + 300 + 60),  # past boundary
    )

    fresh = SnapshotJob.objects.create(
        schema_name='delta', triggered_by=actor,
        status=SnapshotJob.Status.RUNNING)
    SnapshotJob.objects.filter(pk=fresh.pk).update(
        started_at=timezone.now() - timedelta(seconds=10),
    )

    reap_stale_jobs()

    stale.refresh_from_db()
    fresh.refresh_from_db()
    assert stale.status == SnapshotJob.Status.FAILED
    assert stale.error_class == 'WorkerCrashOrTimeout'
    assert fresh.status == SnapshotJob.Status.RUNNING  # untouched


@pytest.mark.integration
def test_enforce_retention_all_continues_after_per_schema_error(actor):
    """If RetentionService raises for one schema, the task still processes others."""
    SnapshotJob.objects.create(
        schema_name='a', triggered_by=actor,
        status=SnapshotJob.Status.SUCCEEDED)
    SnapshotJob.objects.create(
        schema_name='b', triggered_by=actor,
        status=SnapshotJob.Status.SUCCEEDED)

    visited = []

    class FakeRetention:
        def __init__(self, storage=None):
            pass
        def enforce_for_schema(self, schema_name):
            if schema_name == 'a':
                raise RuntimeError('boom')
            visited.append(schema_name)

    with patch('snapshots.tasks.RetentionService', FakeRetention):
        enforce_retention_all()   # must not raise

    assert visited == ['b']
