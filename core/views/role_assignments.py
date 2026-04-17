"""
Role ↔ User assignment API.

Endpoints
---------
* ``GET    /api/v1/core/role-assignments/``          — list assignments
* ``POST   /api/v1/core/role-assignments/``          — assign role to user
                                                        (runs SOD pre-check)
* ``PATCH  /api/v1/core/role-assignments/{id}/``     — update notes / deactivate
* ``DELETE /api/v1/core/role-assignments/{id}/``     — revoke assignment
* ``GET    /api/v1/core/role-assignments/by-user/``  — users with their roles
                                                        (list view keyed by user)
* ``POST   /api/v1/core/role-assignments/preview-sod/`` — dry-run check:
    ``{"user_id": 5, "role_codes": ["budget_officer"]}`` → what conflicts
    would arise from this combination, before any write happens.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from core.models import Role, RoleAssignment
from core.services.sod_conflicts import conflicts_for_roles

User = get_user_model()


class RoleAssignmentSerializer(serializers.ModelSerializer):
    user_username  = serializers.CharField(source='user.username', read_only=True)
    user_full_name = serializers.SerializerMethodField()
    role_code      = serializers.CharField(source='role.code', read_only=True)
    role_name      = serializers.CharField(source='role.name', read_only=True)
    role_module    = serializers.CharField(source='role.module', read_only=True)
    role_type      = serializers.CharField(source='role.role_type', read_only=True)
    assigned_by_username = serializers.SerializerMethodField()

    class Meta:
        model = RoleAssignment
        fields = [
            'id', 'user', 'user_username', 'user_full_name',
            'role', 'role_code', 'role_name', 'role_module', 'role_type',
            'is_active', 'assigned_at', 'assigned_by', 'assigned_by_username',
            'notes',
        ]
        read_only_fields = [
            'id', 'user_username', 'user_full_name',
            'role_code', 'role_name', 'role_module', 'role_type',
            'assigned_at', 'assigned_by', 'assigned_by_username',
        ]

    def get_user_full_name(self, obj: RoleAssignment) -> str:
        first = getattr(obj.user, 'first_name', '') or ''
        last = getattr(obj.user, 'last_name', '') or ''
        return f'{first} {last}'.strip()

    def get_assigned_by_username(self, obj: RoleAssignment) -> str | None:
        return getattr(obj.assigned_by, 'username', None)


class RoleAssignmentViewSet(viewsets.ModelViewSet):
    """CRUD over user↔role assignments.

    Writes require IsAdminUser. SOD conflicts are checked on create and
    returned as a 400 with the offending rules — clients can either
    refuse or re-post with ``override=true`` (which flags the assignment
    in ``notes`` for audit review).
    """
    queryset = RoleAssignment.objects.select_related('user', 'role', 'assigned_by')
    serializer_class = RoleAssignmentSerializer
    filterset_fields = ['user', 'role', 'is_active', 'role__module']
    ordering = ['-assigned_at']

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'by_user', 'preview_sod'):
            return [IsAuthenticated()]
        return [IsAdminUser()]

    # -----------------------------------------------------------------
    # CREATE — SOD pre-check
    # -----------------------------------------------------------------
    def create(self, request, *args, **kwargs):
        user_id = request.data.get('user')
        role_id = request.data.get('role')
        override = _truthy(request.data.get('override'))

        if not user_id or not role_id:
            return Response(
                {'error': 'Both "user" and "role" are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Guard against duplicate assignment before running SOD (cheap).
        existing = RoleAssignment.objects.filter(
            user_id=user_id, role_id=role_id,
        ).first()
        if existing:
            return Response(
                {
                    'error': 'User already holds this role.',
                    'assignment_id': existing.id,
                    'is_active': existing.is_active,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_role = Role.objects.filter(pk=role_id, is_active=True).first()
        if new_role is None:
            return Response(
                {'error': 'Role not found or inactive.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Project what the user's active role set would look like *after*
        # this assignment, then run the SOD matrix against it.
        current_codes = list(
            RoleAssignment.objects
            .filter(user_id=user_id, is_active=True)
            .values_list('role__code', flat=True)
        )
        projected = set(current_codes) | {new_role.code}
        conflicts = conflicts_for_roles(projected)

        if conflicts and not override:
            return Response(
                {
                    'error': 'Assignment would violate Segregation-of-Duties.',
                    'conflicts': conflicts,
                    'hint': 'Resubmit with {"override": true} and document '
                            'justification in "notes" to proceed with '
                            'dual-control approval.',
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Stamp assigned_by + override justification.
        assigned_by = request.user if request.user.is_authenticated else None
        notes = (request.data.get('notes') or '').strip()
        if conflicts and override and not notes:
            return Response(
                {'error': 'Override requires non-empty "notes" justification.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if conflicts and override:
            notes = (
                f'[SOD override] {notes}\n'
                f'Approved conflicts: '
                + '; '.join(
                    f'{c["role_a"]}+{c["role_b"]} ({c["severity"]})'
                    for c in conflicts
                )
            )

        assignment = RoleAssignment.objects.create(
            user_id=user_id, role_id=role_id,
            is_active=True,
            assigned_by=assigned_by,
            notes=notes,
        )
        payload = self.get_serializer(assignment).data
        if conflicts and override:
            payload['sod_override'] = {
                'conflict_count': len(conflicts),
                'conflicts':      conflicts,
            }
        return Response(payload, status=status.HTTP_201_CREATED)

    # -----------------------------------------------------------------
    # BY-USER — pivot the list so the UI can render "users with roles"
    # -----------------------------------------------------------------
    @action(detail=False, methods=['get'], url_path='by-user')
    def by_user(self, request):
        qs = self.get_queryset().filter(is_active=True)
        by_user: dict[int, dict] = {}
        for a in qs:
            uid = a.user_id
            bucket = by_user.setdefault(uid, {
                'user_id':       uid,
                'username':      a.user.username,
                'full_name':     f'{a.user.first_name or ""} {a.user.last_name or ""}'.strip(),
                'email':         a.user.email or '',
                'is_superuser':  bool(a.user.is_superuser),
                'role_codes':    [],
                'roles':         [],
            })
            bucket['role_codes'].append(a.role.code)
            bucket['roles'].append({
                'assignment_id': a.id,
                'code':          a.role.code,
                'name':          a.role.name,
                'module':        a.role.module,
                'role_type':     a.role.role_type,
                'assigned_at':   a.assigned_at.isoformat(),
            })

        # SOD analysis per user so the UI can flag each row.
        rows = []
        for uid, bucket in by_user.items():
            conflicts = conflicts_for_roles(bucket['role_codes'])
            bucket['sod_conflicts']    = conflicts
            bucket['sod_clean']        = not conflicts
            bucket['highest_severity'] = (
                'high'   if any(c['severity'] == 'high'   for c in conflicts) else
                'medium' if any(c['severity'] == 'medium' for c in conflicts) else
                'low'    if conflicts else
                'none'
            )
            rows.append(bucket)

        rows.sort(key=lambda r: (
            # SOD-violating rows first so admins see them immediately.
            0 if r['highest_severity'] == 'high' else
            1 if r['highest_severity'] == 'medium' else
            2,
            r['username'],
        ))
        return Response({'count': len(rows), 'rows': rows})

    # -----------------------------------------------------------------
    # OVERRIDES — list every assignment with [SOD override] in notes
    # -----------------------------------------------------------------
    @action(detail=False, methods=['get'], url_path='overrides')
    def overrides(self, request):
        """Return all role assignments that were granted with an SOD
        override. The notes field is marked ``[SOD override]`` by the
        create() path, so a prefix match gives us the full audit trail
        without adding a dedicated column."""
        qs = (
            self.get_queryset()
            .filter(notes__icontains='[SOD override]')
            .order_by('-assigned_at')
        )
        rows = []
        for a in qs[:500]:
            rows.append({
                'assignment_id':     a.id,
                'user_id':           a.user_id,
                'username':          a.user.username,
                'full_name':         (
                    f'{a.user.first_name or ""} '
                    f'{a.user.last_name or ""}'.strip()
                ),
                'role_code':         a.role.code,
                'role_name':         a.role.name,
                'role_module':       a.role.module,
                'assigned_at':       a.assigned_at.isoformat(),
                'assigned_by':       getattr(a.assigned_by, 'username', None),
                'is_active':         a.is_active,
                'notes':             a.notes,
            })
        return Response({
            'count': len(rows),
            'rows':  rows,
        })

    # -----------------------------------------------------------------
    # PREVIEW-SOD — dry-run check without writing
    # -----------------------------------------------------------------
    @action(detail=False, methods=['post'], url_path='preview-sod')
    def preview_sod(self, request):
        raw_codes = request.data.get('role_codes')
        if not isinstance(raw_codes, list):
            return Response(
                {'error': 'Body must be {"role_codes": [<code>, …]} '
                          'plus optional {"user_id": <int>}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        codes = [str(c).strip() for c in raw_codes if c]

        # If user_id given, *union* with their existing active roles so
        # the preview reflects the post-assignment state.
        user_id = request.data.get('user_id')
        if user_id:
            existing = list(
                RoleAssignment.objects
                .filter(user_id=user_id, is_active=True)
                .values_list('role__code', flat=True)
            )
            codes = list(set(codes) | set(existing))

        conflicts = conflicts_for_roles(codes)
        return Response({
            'codes_checked':    codes,
            'conflict_count':   len(conflicts),
            'sod_clean':        not conflicts,
            'highest_severity': (
                'high'   if any(c['severity'] == 'high'   for c in conflicts) else
                'medium' if any(c['severity'] == 'medium' for c in conflicts) else
                'low'    if conflicts else
                'none'
            ),
            'conflicts':        conflicts,
        })


def _truthy(v) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ('1', 'true', 'yes', 'on')
