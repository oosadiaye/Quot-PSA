"""DRF ViewSet for SnapshotJob — list/retrieve/create/download.

Defense-in-depth:
  - permission_classes gate based on actor type + target schema
  - get_queryset() additionally filters by tenant_schemas_with_all_access
"""
from __future__ import annotations

import io

from django.conf import settings
from django.db import transaction
from django.http import StreamingHttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
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
from snapshots.services.crypto import decrypt_stream
from snapshots.services.storage import LocalFilesystemStorage
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

    @action(detail=True, methods=['GET'], url_path='download')
    def download(self, request, pk=None):
        """Stream-decrypt the artifact and return it as a download."""
        job = self.get_object()  # permission + queryset filter applied

        if job.status != SnapshotJob.Status.SUCCEEDED:
            raise NotFound('Snapshot is not available for download.')
        if not job.artifact_path:
            raise NotFound('Snapshot artifact has been removed.')

        audit.record_downloaded(
            actor=request.user,
            job=job,
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        # Resolve settings eagerly — the generator runs lazily during
        # response serialisation, after any override_settings context exits.
        kek = bytes.fromhex(settings.SNAPSHOTS_KEK_HEX)
        backup_dir = settings.SNAPSHOTS_BACKUP_DIR

        return StreamingHttpResponse(
            _stream_decrypt(job, kek=kek, backup_dir=backup_dir),
            content_type='application/octet-stream',
            headers={
                'Content-Disposition': f'attachment; filename="{job.id}.tar.gz"',
                'X-Content-Type-Options': 'nosniff',
            },
        )


def _stream_decrypt(job, *, kek: bytes, backup_dir: str):
    """Generator decrypting the artifact in 64KB chunks.

    kek and backup_dir are passed explicitly so callers can resolve them from
    settings *before* entering async/lazy context, avoiding override_settings
    timing issues in tests.
    """
    storage = LocalFilesystemStorage(root=backup_dir)
    plain_buf = io.BytesIO()
    with storage.open_read(job.artifact_path) as cipher_fh:
        decrypt_stream(cipher_fh, plain_buf, kek=kek)
    plain_buf.seek(0)
    while True:
        chunk = plain_buf.read(64 * 1024)
        if not chunk:
            break
        yield chunk
