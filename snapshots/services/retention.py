"""Apply age + per-tenant-count retention rules to SnapshotJob rows.

Order: age first (cheap, indexed), then count (operates on what's left).
Either rule fires -> EXPIRED + artifact unlinked.

Transaction ordering: DB update -> commit -> file unlink. Opposite ordering
risks a row pointing at a deleted file. Our worst case is an orphan file,
which the nightly beat reconciles.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from snapshots import audit
from snapshots.models import SnapshotJob


logger = logging.getLogger(__name__)


@dataclass
class RetentionReport:
    schema_name: str
    expired_count: int


class RetentionService:
    def __init__(self, storage):
        self.storage = storage

    def enforce_for_schema(self, schema_name: str) -> RetentionReport:
        retention_days = int(settings.SNAPSHOTS_RETENTION_DAYS)
        max_per_tenant = int(settings.SNAPSHOTS_MAX_PER_TENANT)
        expired_total = 0

        age_cutoff = timezone.now() - timedelta(days=retention_days)
        age_victims = list(SnapshotJob.objects.filter(
            schema_name=schema_name,
            status=SnapshotJob.Status.SUCCEEDED,
            triggered_at__lt=age_cutoff,
        ).values_list('pk', 'artifact_path'))
        expired_total += self._expire(age_victims)

        survivors = SnapshotJob.objects.filter(
            schema_name=schema_name,
            status=SnapshotJob.Status.SUCCEEDED,
        ).order_by('-triggered_at')
        keepers = list(survivors[:max_per_tenant].values_list('pk', flat=True))
        count_victims = list(survivors.exclude(pk__in=keepers).values_list(
            'pk', 'artifact_path'))
        expired_total += self._expire(count_victims)

        return RetentionReport(schema_name=schema_name, expired_count=expired_total)

    def enforce_all(self) -> list[RetentionReport]:
        schemas = SnapshotJob.objects.values_list(
            'schema_name', flat=True).distinct()
        return [self.enforce_for_schema(s) for s in schemas]

    def _expire(self, victims: list[tuple[int, str]]) -> int:
        if not victims:
            return 0
        ids = [pk for pk, _ in victims]
        with transaction.atomic():
            SnapshotJob.objects.filter(pk__in=ids).update(
                status=SnapshotJob.Status.EXPIRED,
                artifact_path='',
            )
        for pk, artifact in victims:
            # Audit FIRST so the event is recorded even if file delete fails.
            try:
                job_stub = SnapshotJob.objects.get(pk=pk)
                audit.record_expired(job_stub)
            except Exception:
                logger.exception(
                    'snapshots.retention: audit failed for pk=%s', pk)
            if not artifact:
                continue
            try:
                self.storage.delete(artifact)
            except Exception:
                logger.exception('snapshots.retention: failed to delete %s', artifact)
        return len(ids)
