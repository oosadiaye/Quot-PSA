"""Advisory GL coding check endpoint.

Posting forms call this before they submit: it compares each line's GL account
label against its description and returns per-line verdicts so the form can show
a non-blocking amber warning on suspect lines. See
``accounting/services/gl_coding_check.py``.
"""
from __future__ import annotations

from django.db import connection
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounting.services.gl_coding_check import check_lines


class GlCodingCheckView(APIView):
    """POST ``{"lines": [{"index"?, "name", "code"?, "description"}]}`` →
    ``{"results": [...], "ai_used": bool}``. Advisory only — any authenticated
    user may call it; it changes nothing."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        lines = request.data.get("lines")
        if not isinstance(lines, list):
            return Response({"error": "'lines' must be a list."}, status=400)
        tenant = getattr(connection, "tenant", None) or getattr(request, "tenant", None)
        return Response(check_lines(lines, tenant=tenant, actor=request.user))
