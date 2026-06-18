"""
Role, Permission, and SoD-rule management API.

Endpoints
---------
Roles:
  * ``GET    /api/v1/core/roles/``                  — list roles
  * ``POST   /api/v1/core/roles/``                  — create custom role
  * ``GET    /api/v1/core/roles/{id}/``             — retrieve role
  * ``PATCH  /api/v1/core/roles/{id}/``             — update role + perms
  * ``DELETE /api/v1/core/roles/{id}/``             — deactivate (soft)
  * ``POST   /api/v1/core/roles/{id}/check-sod/``   — preview SoD violations
                                                       this role would create

Permission catalogue:
  * ``GET    /api/v1/core/permissions/``            — list / filter perms

SoD rules (rule-driven, runtime-editable):
  * ``GET    /api/v1/core/sod-rules/``              — list rules
  * ``POST   /api/v1/core/sod-rules/``              — create rule
  * ``PATCH  /api/v1/core/sod-rules/{id}/``         — edit rule
  * ``DELETE /api/v1/core/sod-rules/{id}/``         — delete rule (system rules
                                                       are deactivated, not deleted)

Legacy (kept for back-compat with existing UI):
  * ``GET    /api/v1/core/roles/sod-matrix/``       — hardcoded role matrix
  * ``POST   /api/v1/core/roles/sod-check/``        — role-pair conflict check

Real-time effect: every write goes through cache invalidation in
``core/signals/role_perm_signals.py`` so changes show up on the very
next request from any active user — no logout, no restart.
"""
from __future__ import annotations

from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from core.models import PermissionDefinition, Role, SoDRule
from core.services.sod_conflicts import (
    matrix as sod_matrix,
    conflicts_for_roles,
)
from core.services.sod_evaluator import check_assignment


# ─────────────────────────────────────────────────────────────────────
# Permission catalogue
# ─────────────────────────────────────────────────────────────────────

class PermissionDefinitionSerializer(serializers.ModelSerializer):
    module_display = serializers.CharField(source='get_module_display', read_only=True)
    risk_level_display = serializers.CharField(source='get_risk_level_display', read_only=True)

    class Meta:
        model = PermissionDefinition
        fields = [
            'id', 'code', 'module', 'module_display',
            'resource', 'action', 'label', 'description',
            'risk_level', 'risk_level_display',
            'sort_order', 'is_system',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'module_display', 'risk_level_display',
                            'created_at', 'updated_at']


class PermissionDefinitionViewSet(viewsets.ModelViewSet):
    """The granular permission catalogue.

    Read access for any authenticated user (the role editor needs the
    full list to render its tree). Write access is admin-only and is
    really only useful for tenant-specific custom permissions —
    system permissions are seeded by ``seed_permission_catalog`` and
    refreshed on every release.
    """
    queryset = PermissionDefinition.objects.all().order_by('module', 'resource', 'sort_order')
    serializer_class = PermissionDefinitionSerializer
    filterset_fields = ['module', 'resource', 'risk_level', 'is_system']
    ordering = ['module', 'resource', 'sort_order']
    pagination_class = None  # the catalogue is small enough to ship in one go

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def perform_destroy(self, instance: PermissionDefinition):
        # System permissions cannot be deleted — they're referenced by
        # signal handlers and SoD rules. Custom permissions go.
        if instance.is_system:
            raise serializers.ValidationError(
                'System permissions cannot be deleted. They are seeded and '
                'used by signal handlers / SoD rules. Create your own '
                'custom (is_system=False) permission instead.'
            )
        instance.delete()


# ─────────────────────────────────────────────────────────────────────
# Roles
# ─────────────────────────────────────────────────────────────────────

class RoleSerializer(serializers.ModelSerializer):
    module_display = serializers.CharField(source='get_module_display', read_only=True)
    role_type_display = serializers.CharField(source='get_role_type_display', read_only=True)

    # Granular permissions — write as list of PermissionDefinition codes
    # (the editor sends codes, not pks, so the payload is portable
    # across tenants when the same template is exported / imported).
    permission_codes = serializers.SerializerMethodField()
    permission_codes_input = serializers.ListField(
        child=serializers.CharField(),
        write_only=True, required=False,
    )

    # Legacy permission strings derived from boolean flags (kept for
    # back-compat with anything that still consumes them).
    legacy_permission_strings = serializers.SerializerMethodField()

    assigned_user_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            'id', 'code', 'name', 'description',
            'module', 'module_display',
            'role_type', 'role_type_display',
            # Legacy boolean flags — still editable so old-shape roles work.
            'can_view', 'can_add', 'can_change', 'can_delete',
            'can_approve', 'can_post',
            'is_active', 'is_default', 'is_system',
            'permission_codes', 'permission_codes_input',
            'legacy_permission_strings',
            'assigned_user_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'module_display', 'role_type_display',
            'permission_codes', 'legacy_permission_strings',
            'assigned_user_count',
            'created_at', 'updated_at',
        ]

    def get_permission_codes(self, obj: Role) -> list[str]:
        return list(obj.permissions.values_list('code', flat=True))

    def get_legacy_permission_strings(self, obj: Role) -> list[str]:
        try:
            return obj.get_permissions()
        except Exception:
            return []

    def get_assigned_user_count(self, obj: Role) -> int:
        # Number of *active* assignments — useful for the role-list UI
        # so admins can see at a glance which roles are actually in use.
        return obj.assignments.filter(is_active=True).count()

    def _set_permissions(self, role: Role, codes: list[str]) -> None:
        """Resolve permission codes → PermissionDefinition rows and
        update the M2M. Unknown codes are silently dropped — the UI
        already filters against the catalogue, and silently dropping
        is friendlier on cross-tenant imports than a hard error."""
        wanted = list(
            PermissionDefinition.objects.filter(code__in=codes)
        )
        role.permissions.set(wanted)

    def create(self, validated_data):
        codes = validated_data.pop('permission_codes_input', None)
        role = super().create(validated_data)
        if codes is not None:
            self._set_permissions(role, codes)
        return role

    def update(self, instance, validated_data):
        codes = validated_data.pop('permission_codes_input', None)
        role = super().update(instance, validated_data)
        if codes is not None:
            self._set_permissions(role, codes)
        return role


class RoleViewSet(viewsets.ModelViewSet):
    """CRUD over tenant-local Role definitions.

    Writes require IsAdminUser; reads are open to authenticated users
    so the role-picker on the user-management screen can show options.

    System roles cannot be deleted (only deactivated). Tenants can
    edit their permission set; the boolean flags are preserved for
    legacy consumers.
    """
    queryset = Role.objects.all().prefetch_related('permissions')
    serializer_class = RoleSerializer
    filterset_fields = ['module', 'role_type', 'is_active', 'is_system']
    ordering = ['module', 'role_type', 'name']
    # Roles are bounded — even a heavy tenant rarely exceeds 30. Returning
    # them all in one shot avoids a paginated frontend list missing rows
    # when default PAGE_SIZE=20 truncates them. (Revalidation finding #2.)
    pagination_class = None

    def get_permissions(self):
        if self.action in (
            'list', 'retrieve', 'sod_matrix', 'sod_check',
            'check_sod', 'permission_catalogue',
        ):
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def perform_destroy(self, instance: Role):
        # System roles: soft-delete (deactivate). Custom roles: real
        # delete is fine. Either way audit history survives because
        # ``RoleAssignment`` rows are not cascaded.
        if instance.is_system:
            instance.is_active = False
            instance.save(update_fields=['is_active', 'updated_at'])
        else:
            instance.delete()

    # ─── action: preview SoD violations on a permission set ──────────
    @action(detail=True, methods=['post'], url_path='check-sod')
    def check_sod(self, request, pk=None):
        """Preview which SoD ``hold``-scope rules a user would breach
        if they were assigned this role (optionally combined with
        permission codes the caller supplies in the body — handy for
        previewing changes before save).

        Body (optional):
            {"user_id": 42, "additional_permissions": ["accounting.journal.post"]}

        Response:
            {
              "violations": [
                {
                  "rule_code": "sod.journal.create_approve",
                  "rule_name": "...",
                  "scope": "hold",
                  "severity": "block",
                  "permission_a_code": "accounting.journal.create",
                  "permission_b_code": "accounting.journal.approve",
                  "reason": "..."
                },
                ...
              ],
              "blocking_count": N,
              "warning_count":  M
            }
        """
        from django.contrib.auth import get_user_model
        User = get_user_model()

        role = self.get_object()
        user_id = request.data.get('user_id')
        extra = request.data.get('additional_permissions') or []

        target_user = None
        if user_id:
            try:
                target_user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                return Response(
                    {'error': f'User {user_id} not found.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            target_user = request.user

        violations = check_assignment(
            target_user,
            additional_role=role,
            additional_permission_codes=extra,
        )
        return Response({
            'violations': [
                {
                    'rule_id': v.rule_id,
                    'rule_code': v.rule_code,
                    'rule_name': v.rule_name,
                    'scope': v.scope,
                    'severity': v.severity,
                    'permission_a_code': v.permission_a_code,
                    'permission_a_label': v.permission_a_label,
                    'permission_b_code': v.permission_b_code,
                    'permission_b_label': v.permission_b_label,
                    'reason': v.reason,
                }
                for v in violations
            ],
            'blocking_count': sum(1 for v in violations if v.is_blocking),
            'warning_count':  sum(1 for v in violations if not v.is_blocking),
        })

    # ─── catalogue passthrough — common UI helper ────────────────────
    @action(detail=False, methods=['get'], url_path='permission-catalogue')
    def permission_catalogue(self, request):
        """Return the full permission catalogue grouped by module →
        resource. Convenience endpoint for the role-editor tree so the
        client doesn't have to do the grouping."""
        perms = list(
            PermissionDefinition.objects.all().order_by(
                'module', 'resource', 'sort_order',
            )
        )
        grouped: dict = {}
        for p in perms:
            module_bucket = grouped.setdefault(p.module, {
                'module': p.module,
                'module_display': p.get_module_display(),
                'resources': {},
            })
            resource_bucket = module_bucket['resources'].setdefault(p.resource, {
                'resource': p.resource,
                'permissions': [],
            })
            resource_bucket['permissions'].append({
                'id': p.id,
                'code': p.code,
                'action': p.action,
                'label': p.label,
                'description': p.description,
                'risk_level': p.risk_level,
                'is_system': p.is_system,
            })
        # Flatten resource dicts into lists for stable iteration order.
        return Response([
            {
                'module': bucket['module'],
                'module_display': bucket['module_display'],
                'resources': list(bucket['resources'].values()),
            }
            for bucket in grouped.values()
        ])

    # ─── legacy: hardcoded SoD matrix (back-compat) ──────────────────
    @action(detail=False, methods=['get'], url_path='sod-matrix')
    def sod_matrix(self, request):
        """Returns the legacy hardcoded role-pair SoD matrix. Kept so
        the existing SoD page still works during the migration to
        rule-driven SoD."""
        return Response({'rules': sod_matrix()})

    @action(detail=False, methods=['post'], url_path='sod-check')
    def sod_check(self, request):
        raw = request.data.get('codes')
        if not isinstance(raw, list):
            return Response(
                {'error': 'Body must be JSON with {"codes": [<role-code>, …]}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        codes = [str(c).strip() for c in raw if c]
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
            'codes_checked': codes,
            'conflict_count': len(conflicts),
            'highest_severity': highest,
            'conflicts': conflicts,
            'sod_clean': len(conflicts) == 0,
        })


# ─────────────────────────────────────────────────────────────────────
# SoD rules
# ─────────────────────────────────────────────────────────────────────

class SoDRuleSerializer(serializers.ModelSerializer):
    permission_a_code = serializers.CharField(source='permission_a.code', read_only=True)
    permission_a_label = serializers.CharField(source='permission_a.label', read_only=True)
    permission_b_code = serializers.CharField(source='permission_b.code', read_only=True)
    permission_b_label = serializers.CharField(source='permission_b.label', read_only=True)

    # Editable by code (the editor sends codes, not pks).
    permission_a_input = serializers.CharField(write_only=True, required=False)
    permission_b_input = serializers.CharField(write_only=True, required=False)

    scope_display = serializers.CharField(source='get_scope_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)

    class Meta:
        model = SoDRule
        fields = [
            'id', 'code', 'name', 'description',
            'permission_a', 'permission_a_code', 'permission_a_label', 'permission_a_input',
            'permission_b', 'permission_b_code', 'permission_b_label', 'permission_b_input',
            'scope', 'scope_display',
            'severity', 'severity_display',
            'is_active', 'is_system',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'permission_a_code', 'permission_a_label',
            'permission_b_code', 'permission_b_label',
            'scope_display', 'severity_display',
            'created_at', 'updated_at',
        ]
        extra_kwargs = {
            'permission_a': {'required': False},
            'permission_b': {'required': False},
        }

    def _resolve_codes(self, validated_data):
        """If the caller sent code strings, resolve them to FKs. The
        editor uses codes so the payload is human-readable in dev tools
        and stable across tenants for export/import."""
        for src_field, fk_field in [
            ('permission_a_input', 'permission_a'),
            ('permission_b_input', 'permission_b'),
        ]:
            code = validated_data.pop(src_field, None)
            if code:
                try:
                    validated_data[fk_field] = (
                        PermissionDefinition.objects.get(code=code)
                    )
                except PermissionDefinition.DoesNotExist as exc:
                    raise serializers.ValidationError({
                        src_field: f'No permission with code "{code}".',
                    }) from exc

    def validate(self, attrs):
        # Combine input + FK fields so create/update can resolve either way.
        attrs = dict(attrs)
        self._resolve_codes(attrs)
        pa = attrs.get('permission_a') or getattr(self.instance, 'permission_a', None)
        pb = attrs.get('permission_b') or getattr(self.instance, 'permission_b', None)
        if pa and pb and pa.id == pb.id:
            raise serializers.ValidationError(
                'permission_a and permission_b must be different — a SoD rule '
                'against itself has no meaning.',
            )
        return attrs

    def create(self, validated_data):
        return super().create(validated_data)


class SoDRuleViewSet(viewsets.ModelViewSet):
    """CRUD over the SoD rule table.

    Reads are open to any authenticated user (the role editor uses
    them to surface inline warnings). Writes require admin.
    """
    queryset = SoDRule.objects.all().select_related('permission_a', 'permission_b')
    serializer_class = SoDRuleSerializer
    filterset_fields = ['scope', 'severity', 'is_active', 'is_system']
    ordering = ['code']
    # SoD rules are bounded (typically 20–100 even in mature tenants).
    # Default PAGE_SIZE=20 was hiding rows from the frontend list — see
    # revalidation finding #2.
    pagination_class = None

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def perform_destroy(self, instance: SoDRule):
        if instance.is_system:
            instance.is_active = False
            instance.save(update_fields=['is_active', 'updated_at'])
        else:
            instance.delete()
