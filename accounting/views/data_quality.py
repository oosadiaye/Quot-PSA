"""
GL Data Quality diagnostic endpoint.

GET /accounting/data-quality/
    Runs five audit checks and returns a structured report with per-check
    status, count, and drill-down sample rows.
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class DataQualityView(APIView):
    """Read-only diagnostic endpoint — no database writes."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from accounting.services.data_quality import DataQualityService
        return Response(DataQualityService.run_all())
