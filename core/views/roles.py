"""
Role & Permission management API.

Endpoints
---------
* ``GET    /api/v1/core/roles/``                 — list all roles
* ``GET    /api/v1/core/roles/{id}/``            — retrieve one role
* ``PATCH  /api/v1/core/roles/{id}/``            — update permission flags
* ``POST   /api/v1/core/roles/``                 — create a custom role
* ``DELETE /api/v1/core/roles/{id}/``            — deactivate a role
* ``GET    /api/v1/core/roles/sod-matrix/``      — full SOD conflict matrix
* ``POST   /api/v1/core/roles/sod-check/``       — check a role combination
                                                    (body: ``{"codes": [...]}``)
"""
from __future__ import annotations

from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from core.models import Role
from core.services.sod_conflicts import (
    matrix as sod_matrix,
    conflicts_for_roles,
)


class RoleSerializer(serializers.ModelSerializer):
    module_display = serializers.CharField(
        source='get_module_display', read_only=True,
    )
    role_type_display = serializers.CharField(
        source='get_role_type_display', read_only=True,
    )
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            'id', 'code', 'name',
            'module', 'module_display',
            'role_type', 'role_type_display',
            'can_view', 'can_add', 'can_change', 'can_delete',
            'can_approve', 'can_post',
            'is_active', 'is_default',
            'permissions',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'module_display', 'role_type_display', 'permissions',
            'created_at', 'updated_at',
        ]

    def get_permissions(self, obj: Role) -> list[str]:
        try:
            return obj.get_permissions()
        except Exception:
            return []


class RoleViewSet(viewsets.ModelViewSet):
    """CRUD over tenant-local Role definitions.

    Writes (create / update / delete) require IsAdminUser so non-admin
    users can browse the role catalogue but only an admin can change
    authority flags.
    """
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    filterset_fields = ['module', 'role_type', 'is_active']
    ordering = ['module', 'role_type', 'name']

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'sod_matrix', 'sod_check'):
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def perform_destroy(self, instance: Role):
        # Soft-delete — deactivate rather than hard-delete so audit
        # trails and historical permission grants remain intact.
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])

    # -----------------------------------------------------------------
    # SOD matrix — display the canonical rules.
    # -----------------------------------------------------------------
    @action(detail=False, methods=['get'], url_path='sod-matrix')
    def sod_matrix(self, request):
        return Response({'rules': sod_matrix()})

    # -----------------------------------------------------------------
    # SOD check — validate a proposed role combination.
    # -----------------------------------------------------------------
    @action(detail=False, methods=['post'], url_path='sod-check')
    def sod_check(self, request):
        raw = request.data.get('codes')
        if not isinstance(raw, list):
            return Response(
                {'error': 'Body must be JSON with {"codes": [<role-code>, …]}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            codes = [str(c).strip() for c in raw if c]
        except Exception:
            return Response(
                {'error': 'Every code must be a string.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        conflicts = conflicts_for_roles(codes)
        highest = 'none'
        if conflicts:
            if any(c['severity'] == 'high' for c in conflicts):
                highest = 'high'
            elif any(c['severity'] == 'medium' for c in conflicts):
                highest = 'medium'
            else:
                highest = 'low'

        return Response({
            'codes_checked':   codes,
            'conflict_count':  len(conflicts),
            'highest_severity': highest,
            'conflicts':       conflicts,
            'sod_clean':       len(conflicts) == 0,
        })
