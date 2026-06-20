"""
Async report-export API (additive, non-blocking).

Three endpoints, all owner-scoped and throttled under the ``exports``
scope (already declared in ``settings.DEFAULT_THROTTLE_RATES``):

* ``POST /accounting/exports/``
      Body ``{label, fmt, report_payload}``. Creates a PENDING
      ``AsyncExportJob`` owned by the caller, enqueues the Celery render
      task, and returns ``202 Accepted`` with ``{id, status}``.

* ``GET /accounting/exports/<id>/``
      Returns the job's status envelope so the client can poll.

* ``GET /accounting/exports/<id>/download/``
      Streams the rendered file as an attachment once the job is
      ``SUCCESS``; otherwise ``409 Conflict`` with the current status.

The existing synchronous export endpoints are NOT touched — this is a
parallel surface for clients that prefer the queue-and-poll flow to keep
heavy renders off the web worker.

Ownership scoping: the queryset is filtered to ``requested_by=request
.user`` so one operator can never read or download another operator's
exports.
"""
from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from django.http import FileResponse

from accounting.models import AsyncExportJob
from accounting.serializers_async_export import (
    AsyncExportJobCreateSerializer,
    AsyncExportJobSerializer,
)


class AsyncExportJobViewSet(viewsets.GenericViewSet):
    """Queue-and-poll surface for off-worker report exports."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'exports'
    serializer_class = AsyncExportJobSerializer

    def get_queryset(self):
        # Owner scoping — a user only ever sees their own jobs. Guard
        # against the schema-generation pass (AnonymousUser) so the
        # router/OpenAPI introspection doesn't blow up.
        user = self.request.user
        if not user or not user.is_authenticated:
            return AsyncExportJob.objects.none()
        return AsyncExportJob.objects.filter(requested_by=user)

    def create(self, request):
        """POST /accounting/exports/ — enqueue a render job."""
        serializer = AsyncExportJobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        job = AsyncExportJob.objects.create(
            label=serializer.validated_data['label'],
            fmt=serializer.validated_data['fmt'],
            report_payload=serializer.validated_data['report_payload'],
            requested_by=request.user,
            status=AsyncExportJob.STATUS_PENDING,
        )

        # Enqueue off-worker render. Import here so a celery-less
        # deployment importing this module for URL resolution doesn't
        # require a broker until an export is actually requested.
        from accounting.tasks_export import run_async_export
        run_async_export.delay(job.id)

        return Response(
            {'id': job.id, 'status': job.status},
            status=status.HTTP_202_ACCEPTED,
        )

    def retrieve(self, request, pk=None):
        """GET /accounting/exports/<id>/ — poll job status."""
        job = self.get_object()
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """GET /accounting/exports/<id>/download/ — stream the artefact."""
        job = self.get_object()
        if job.status != AsyncExportJob.STATUS_SUCCESS or not job.file:
            return Response(
                {
                    'error': 'Export is not ready for download.',
                    'status': job.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        job.file.open('rb')
        response = FileResponse(
            job.file,
            as_attachment=True,
            filename=job.filename or f'export-{job.pk}',
            content_type=job.content_type or 'application/octet-stream',
        )
        return response
