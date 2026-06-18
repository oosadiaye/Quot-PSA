"""Celery task wrappers for the snapshots feature.

Three tasks:
- ``run_snapshot_job(job_id)`` — main worker; calls SnapshotService.
- ``enforce_retention_all`` — nightly beat; walks every schema.
- ``reap_stale_jobs`` — periodic beat; rescues jobs stuck in RUNNING.

The tasks are intentionally thin — all real logic lives in
``snapshots.services``. Tests at this layer verify wiring and the
stale-job reaper's time math.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from snapshots.models import SnapshotJob
from snapshots.services.retention import RetentionService
from snapshots.services.snapshot_service import SnapshotService
from snapshots.services.storage import LocalFilesystemStorage


logger = logging.getLogger(__name__)


# ── Celery decorator import (graceful: Celery may not be installed in
# every dev environment). When Celery is absent, the bare functions
# below remain callable but cannot be enqueued.
try:
    from celery import shared_task
    _HAS_CELERY = True
except ImportError:  # pragma: no cover
    _HAS_CELERY = False
    def shared_task(*decor_args, **decor_kwargs):
        def wrap(fn):
            return fn
        return wrap


def _hard_time_limit() -> int:
    return int(getattr(settings, 'SNAPSHOTS_HARD_TIME_LIMIT_SEC', 3600))


def _soft_time_limit() -> int:
    return int(getattr(settings, 'SNAPSHOTS_SOFT_TIME_LIMIT_SEC', 3000))


def _reaper_buffer() -> int:
    """Buffer added on top of hard time limit before declaring a RUNNING job orphaned."""
    return int(getattr(settings, 'SNAPSHOTS_REAPER_BUFFER_SEC', 300))


def _run_snapshot_job(pk: int) -> None:
    """Real implementation. Tests call this directly; the Celery task is a
    thin wrapper to keep the public signature clean."""
    with transaction.atomic():
        try:
            job = SnapshotJob.objects.select_for_update().get(pk=pk)
        except SnapshotJob.DoesNotExist:
            logger.warning(
                'snapshots.run_snapshot_job: job_id=%s not found — skipping', pk)
            return

    # SnapshotService re-fetches with select_related, so the row lock above
    # is held only for the lookup window. The actual work runs outside the
    # transaction so a long pg_dump doesn't keep the row locked.
    try:
        SnapshotService(job).execute()
    except Exception:
        # SnapshotService._mark_failed already ran if execute() reached
        # _transition_running. Re-raise so Celery records the task failure.
        logger.exception(
            'snapshots.run_snapshot_job: unhandled error for job_id=%s', pk)
        raise


@shared_task(
    bind=True,
    max_retries=0,
    name='snapshots.run_snapshot_job',
    time_limit=_hard_time_limit() if _HAS_CELERY else None,
    soft_time_limit=_soft_time_limit() if _HAS_CELERY else None,
)
def run_snapshot_job(self, job_id: int) -> None:
    """Celery entry point. Time limits are frozen at module import — to
    change them, update the env var AND restart the Celery worker."""
    _run_snapshot_job(job_id)


@shared_task(name='snapshots.enforce_retention_all')
def enforce_retention_all():
    """Beat task: walk every distinct schema_name and apply retention."""
    schemas = (
        SnapshotJob.objects
        .values_list('schema_name', flat=True)
        .distinct()
    )
    storage = LocalFilesystemStorage(root=settings.SNAPSHOTS_BACKUP_DIR)
    service = RetentionService(storage=storage)
    for schema in schemas:
        try:
            service.enforce_for_schema(schema)
        except Exception:
            logger.exception(
                'snapshots.enforce_retention_all: failed for schema=%s',
                schema,
                extra={'schema_name': schema},
            )


@shared_task(name='snapshots.reap_stale_jobs')
def reap_stale_jobs():
    """Find jobs stuck in RUNNING past (hard_time_limit + reaper buffer) and FAIL them.

    Closes the failure mode where a Celery worker crashes mid-job: the row
    stays RUNNING forever until something rescues it. The beat task is the
    rescue mechanism.
    """
    cutoff = timezone.now() - timedelta(
        seconds=_hard_time_limit() + _reaper_buffer())
    with transaction.atomic():
        # QuerySet.update() is intentional here: a single atomic UPDATE
        # bypasses model signals (no SnapshotJob signal listeners currently
        # exist) and avoids N individual saves.
        count = SnapshotJob.objects.filter(
            status=SnapshotJob.Status.RUNNING,
            started_at__lt=cutoff,
        ).update(
            status=SnapshotJob.Status.FAILED,
            completed_at=timezone.now(),
            error_class='WorkerCrashOrTimeout',
            error_message=(
                f'snapshots: reaped — RUNNING past '
                f'{_hard_time_limit() + _reaper_buffer()}s'
            ),
        )
    if count:
        logger.warning('snapshots.reap_stale_jobs: reaped %s stale jobs', count)
