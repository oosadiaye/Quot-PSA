"""DRF ViewSet for SnapshotJob — list/retrieve/create/download.

Defense-in-depth:
  - permission_classes gate based on actor type + target schema
  - get_queryset() additionally filters by tenant_schemas_with_all_access
"""
from __future__ import annotations

import io
import logging

from django.conf import settings
from django.db import transaction
from django.http import StreamingHttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from core.security.client_ip import get_trusted_client_ip
from snapshots import audit
from snapshots.models import SnapshotJob
from snapshots.permissions import (
    CanAccessSnapshot,
    CanCreateSnapshot,
    is_platform_superadmin,
    tenant_schemas_with_all_access,
)
from snapshots.serializers import SnapshotJobSerializer
from snapshots.services.crypto import SnapshotDecryptionError, decrypt_stream
from snapshots.services.storage import LocalFilesystemStorage
from snapshots.tasks import run_snapshot_job

logger = logging.getLogger(__name__)


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
        if self.action == 'download':
            self.throttle_scope = 'snapshot_download'
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

        # Resolve settings eagerly so override_settings in tests captures them
        # before the generator is consumed.
        kek = bytes.fromhex(settings.SNAPSHOTS_KEK_HEX)
        backup_dir = settings.SNAPSHOTS_BACKUP_DIR

        # Decrypt eagerly into a buffer now, before audit is emitted.
        # Generators are lazy — decryption would only run on first iteration,
        # after the response is returned, making it impossible to catch errors
        # here and preventing audit integrity (audit must not fire on failure).
        try:
            plain_buf = _decrypt_to_buffer(job, kek=kek, backup_dir=backup_dir)
        except SnapshotDecryptionError:
            logger.exception(
                'snapshots: artifact decryption failed for job_id=%s', job.pk)
            raise NotFound('Snapshot artifact could not be decrypted.')

        gen = _iter_buffer(plain_buf)

        # Audit only AFTER successful decryption construction.
        audit.record_downloaded(
            actor=request.user,
            job=job,
            ip_address=get_trusted_client_ip(request),
        )

        filename = (
            f'{job.schema_name}_'
            f'{job.triggered_at.strftime("%Y%m%dT%H%M%SZ")}_{job.id}.tar.gz'
        )
        return StreamingHttpResponse(
            gen,
            content_type='application/octet-stream',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'X-Content-Type-Options': 'nosniff',
                'Cache-Control': 'no-store, no-cache, must-revalidate, private',
                'Pragma': 'no-cache',
            },
        )


def _decrypt_to_buffer(job, *, kek: bytes, backup_dir: str) -> io.BytesIO:
    """Decrypt the artifact eagerly and return a seeked BytesIO buffer.

    Raises SnapshotDecryptionError on wrong KEK, tamper, or truncation.
    kek and backup_dir are passed explicitly so callers resolve them from
    settings *before* entering any lazy/async context.
    """
    storage = LocalFilesystemStorage(root=backup_dir)
    plain_buf = io.BytesIO()
    with storage.open_read(job.artifact_path) as cipher_fh:
        decrypt_stream(cipher_fh, plain_buf, kek=kek)
    plain_buf.seek(0)
    return plain_buf


def _iter_buffer(buf: io.BytesIO, chunk_size: int = 64 * 1024):
    """Yield the contents of a BytesIO buffer in fixed-size chunks."""
    while True:
        chunk = buf.read(chunk_size)
        if not chunk:
            break
        yield chunk
