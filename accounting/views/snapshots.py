"""
ReportSnapshot HTTP endpoints.

``GET    /api/v1/accounting/snapshots/``
    List snapshots. Filterable by report_type, fiscal_year, period.

``POST   /api/v1/accounting/snapshots/``
    Persist the current run of a report as a snapshot. Body:
    ``{report_type, fiscal_year, period, payload, notes}``.

``GET    /api/v1/accounting/snapshots/{id}/``
    Retrieve a single snapshot (payload + hash + provenance).

``GET    /api/v1/accounting/snapshots/{id}/verify/``
    Recompute the hash and compare — tamper-evidence check.

``GET    /api/v1/accounting/snapshots/latest/?report_type=ipsas.sofp&fiscal_year=2026&period=4``
    Convenience: return the latest snapshot for a (type, fy, period)
    triple without needing the caller to know its primary key.
"""
from __future__ import annotations

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import serializers as drf_serializers

from accounting.models import ReportSnapshot
from accounting.permissions import CanViewFinancialStatements
from accounting.services.report_snapshot import ReportSnapshotService


class ReportSnapshotSerializer(drf_serializers.ModelSerializer):
    generated_by_username = drf_serializers.SerializerMethodField()
    short_hash = drf_serializers.SerializerMethodField()

    class Meta:
        model = ReportSnapshot
        fields = [
            'id', 'report_type', 'fiscal_year', 'period',
            'payload', 'content_hash', 'short_hash',
            'generated_at', 'generated_by', 'generated_by_username',
            'notes',
        ]
        read_only_fields = [
            'content_hash', 'short_hash',
            'generated_at', 'generated_by_username',
        ]

    def get_generated_by_username(self, obj):
        return getattr(obj.generated_by, 'username', None)

    def get_short_hash(self, obj):
        """First 8 characters — useful for UI badges and search."""
        return (obj.content_hash or '')[:8]


class ReportSnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only list/retrieve; create via the dedicated ``persist`` action."""
    queryset = ReportSnapshot.objects.all().select_related('generated_by')
    serializer_class = ReportSnapshotSerializer
    permission_classes = [CanViewFinancialStatements]
    filterset_fields = ['report_type', 'fiscal_year', 'period']
    ordering = ['-generated_at']

    # ── Create via an explicit action (keeps the ReadOnly base clean) ──
    @action(detail=False, methods=['post'])
    def persist(self, request):
        """Body: {report_type, fiscal_year, period, payload, notes}."""
        try:
            report_type = request.data['report_type']
            fiscal_year = int(request.data['fiscal_year'])
            payload = request.data['payload']
        except (KeyError, TypeError, ValueError) as exc:
            return Response(
                {'error': f'Missing or invalid required field: {exc}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        period = int(request.data.get('period') or 0)
        notes = request.data.get('notes') or ''

        if not isinstance(payload, dict):
            return Response(
                {'error': 'payload must be a JSON object.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        snap = ReportSnapshotService.persist(
            report_type=report_type,
            fiscal_year=fiscal_year,
            period=period,
            payload=payload,
            user=request.user,
            notes=notes,
        )
        return Response(
            self.get_serializer(snap).data,
            status=status.HTTP_201_CREATED,
        )

    # ── Latest snapshot for a (type, fy, period) triple ───────────────
    @action(detail=False, methods=['get'])
    def latest(self, request):
        """?report_type=ipsas.sofp&fiscal_year=2026&period=4."""
        report_type = request.query_params.get('report_type')
        try:
            fiscal_year = int(request.query_params.get('fiscal_year'))
        except (TypeError, ValueError):
            return Response(
                {'error': 'fiscal_year is required and must be an integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not report_type:
            return Response(
                {'error': 'report_type is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            period = int(request.query_params.get('period') or 0)
        except (TypeError, ValueError):
            period = 0

        snap = ReportSnapshotService.get_latest(
            report_type=report_type,
            fiscal_year=fiscal_year,
            period=period,
        )
        if snap is None:
            return Response(
                {'detail': 'No snapshot on file for that (report_type, fiscal_year, period).'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(self.get_serializer(snap).data)

    # ── Tamper-evidence check ──────────────────────────────────────────
    @action(detail=True, methods=['get'])
    def verify(self, request, pk=None):
        """Recompute the hash and compare to the stored ``content_hash``."""
        snap = self.get_object()
        ok = ReportSnapshotService.verify_hash(snap)
        return Response({
            'snapshot_id':      snap.id,
            'stored_hash':      snap.content_hash,
            'verification_ok':  ok,
            'message': (
                'Payload matches stored hash — snapshot is intact.'
                if ok
                else 'Payload does not match stored hash. Possible tampering.'
            ),
        })
