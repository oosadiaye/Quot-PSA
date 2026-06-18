"""DRF ViewSet for SnapshotJob — list/retrieve/create.

Download and delete actions live in views.py too but are added by
Tasks 15-16 to keep this file's commit focused.

Defense-in-depth:
  - permission_classes gate based on actor type + target schema
  - get_queryset() additionally filters by tenant_schemas_with_all_access
"""
from __future__ import annotations

from django.db import transaction
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from snapshots import audit
from snapshots.models import SnapshotJob
from snapshots.permissions import (
    CanAccessSnapshot,
    CanCreateSnapshot,
    is_platform_superadmin,
    tenant_schemas_with_all_access,
)
from snapshots.serializers import SnapshotJobSerializer
from snapshots.tasks import run_snapshot_job


class SnapshotJobViewSet(viewsets.ModelViewSet):
    """Snapshot management endpoints.

    Endpoints:
        POST   /api/snapshots/             create (queues a job)
        GET    /api/snapshots/             list (scoped per actor)
        GET    /api/snapshots/{id}/        retrieve
        PUT    /api/snapshots/{id}/        405 (snapshots are immutable)
        PATCH  /api/snapshots/{id}/        405

    Download (Task 15) and delete (Task 16) actions extend this class.
    """
    serializer_class = SnapshotJobSerializer
    permission_classes = [IsAuthenticated, CanCreateSnapshot, CanAccessSnapshot]
    # Exclude PUT/PATCH — snapshots are immutable once created.
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'snapshot_create'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        qs = SnapshotJob.objects.select_related('triggered_by').all()
        user = self.request.user
        if is_platform_superadmin(user):
            return qs
        allowed = tenant_schemas_with_all_access(user)
        return qs.filter(schema_name__in=allowed)

    def perform_create(self, serializer):
        job = serializer.save(triggered_by=self.request.user)
        audit.record_created(self.request.user, job)
        transaction.on_commit(lambda: run_snapshot_job.delay(job.pk))
