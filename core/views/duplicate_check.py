"""Advisory master-data duplicate lookup endpoint.

Create/edit forms for Vendor, GL account, MDA and the other registered master
data call this while the operator types and again on save. See
``core/services/duplicate_lookup.py``. Read-only; changes nothing.
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import RBACPermission
from core.services.duplicate_lookup import ENTITIES, find_matches, get_model, get_spec


class _ViewPermission(RBACPermission):
    """RBAC gate that requires ``view_<model>`` for a POST (the lookup reads
    the master list, so it needs the same right as listing it)."""
    perms_map = {**RBACPermission.perms_map, "POST": ["%(app_label)s.view_%(model_name)s"]}


class _ModelShim:
    def __init__(self, model):
        self.queryset = model._default_manager.none()


class DuplicateCheckView(APIView):
    """POST ``{"entity": "vendor", "values": {...}, "exclude_id"?: n}`` →
    ``{"matches": [{id, code, name, is_active, level, score, reasons, extra}]}``.

    ``level`` is ``exact`` | ``likely`` | ``similar``. Unknown entity → 400.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        entity = request.data.get("entity")
        spec = get_spec(entity) if isinstance(entity, str) else None
        if spec is None:
            return Response(
                {"error": f"Unknown entity. Expected one of: {', '.join(sorted(ENTITIES))}."},
                status=400,
            )
        values = request.data.get("values")
        if not isinstance(values, dict):
            return Response({"error": "'values' must be an object."}, status=400)

        perm = _ViewPermission()
        if not perm.has_permission(request, _ModelShim(get_model(spec))):
            return Response({"error": getattr(perm, "message", "Forbidden.")}, status=403)

        try:
            matches = find_matches(entity, values, exclude_id=request.data.get("exclude_id"))
        except Exception:  # noqa: BLE001 - advisory: a lookup failure must never block entry
            matches = []
        return Response({"entity": entity, "label": spec.label, "matches": matches})
