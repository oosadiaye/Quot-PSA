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
# Rule-driven SoD evaluator (data-backed, tenant-editable). Coexists
# with the legacy hardcoded role-pair matrix above — the assignment
# workflow runs both engines and surfaces violations from either one.
from core.services.sod_evaluator import (
    check_assignment as _check_assignment_rule_driven,
)

User = get_user_model()


def _rule_driven_violations_for_user(user, additional_role=None) -> list[dict]:
    """Run the rule-driven SoD evaluator and shape its output to match
    the legacy ``conflicts_for_roles`` response shape so the frontend
    can render both engines through one renderer.

    Returns a list of plain dicts:
        [
          {
            'rule_code': 'sod.budget_vs_treasury',
            'rule_name': 'Budget Officer cannot also be Treasury Officer',
            'permission_a': 'budget.appropriation.create',
            'permission_b': 'treasury.voucher.pay',
            'scope': 'hold',
            'severity': 'block',     # or 'warn'
            'reason':   '<rule.description>',
            'engine':   'rule_driven',
          },
          …
        ]

    Empty list when no rule-driven hold-scope rules apply.
    """
    if user is None:
        return []
    try:
        violations = _check_assignment_rule_driven(
            user, additional_role=additional_role,
        )
    except Exception:
        # Defensive — failing here should never block an assignment.
        # Logged to debug only; admin still gets the legacy result.
        return []
    return [
        {
            'rule_code':     v.rule_code,
            'rule_name':     v.rule_name,
            'permission_a':  v.permission_a_code,
            'permission_b':  v.permission_b_code,
            'scope':         v.scope,
            'severity':      v.severity,
            'reason':        v.reason,
            'engine':        'rule_driven',
        }
        for v in violations
    ]


def _highest_severity(legacy: list[dict], rule_driven: list[dict]) -> str:
    """Combine both engines' worst-case severity into one label.

    Legacy uses 'high' / 'medium' / 'low'; rule-driven uses 'block' /
    'warn'. We map them onto a single ordered scale for the UI.
    """
    if any(c.get('severity') == 'block' for c in rule_driven):
        return 'high'
    if any(c.get('severity') == 'high' for c in legacy):
        return 'high'
    if any(c.get('severity') == 'warn' for c in rule_driven):
        return 'medium'
    if any(c.get('severity') == 'medium' for c in legacy):
        return 'medium'
    if legacy or rule_driven:
        return 'low'
    return 'none'


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
        # this assignment, then run BOTH SoD engines against it:
        #
        #   1. Legacy hardcoded role-pair matrix (``conflicts_for_roles``)
        #      — fast, well-known role combinations from
        #      ``core/services/sod_conflicts.py``.
        #   2. Rule-driven evaluator (``check_assignment``) — walks the
        #      tenant-editable ``SoDRule`` table, hold-scope rules.
        #
        # Either engine flagging a conflict triggers the 409 unless the
        # caller passes ``override=true`` with non-empty notes.
        current_codes = list(
            RoleAssignment.objects
            .filter(user_id=user_id, is_active=True)
            .values_list('role__code', flat=True)
        )
        projected = set(current_codes) | {new_role.code}
        conflicts = conflicts_for_roles(projected)

        # Resolve the target user once for the rule-driven evaluator.
        target_user = User.objects.filter(pk=user_id).first()
        rule_violations = _rule_driven_violations_for_user(
            target_user, additional_role=new_role,
        )

        # Blocking severity — only ``block``-level rule-driven
        # violations count as hard reject (the rest are warnings the
        # admin can accept). Legacy hits are ALL blocking.
        blocking_rule_violations = [
            v for v in rule_violations if v.get('severity') == 'block'
        ]

        if (conflicts or blocking_rule_violations) and not override:
            return Response(
                {
                    'error': 'Assignment would violate Segregation-of-Duties.',
                    'conflicts':              conflicts,
                    'rule_driven_violations': rule_violations,
                    'highest_severity': _highest_severity(conflicts, rule_violations),
                    'hint': (
                        'Resubmit with {"override": true} and document '
                        'justification in "notes" to proceed with '
                        'dual-control approval.'
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Stamp assigned_by + override justification.
        assigned_by = request.user if request.user.is_authenticated else None
        notes = (request.data.get('notes') or '').strip()
        any_violation = bool(conflicts or blocking_rule_violations)
        if any_violation and override and not notes:
            return Response(
                {'error': 'Override requires non-empty "notes" justification.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if any_violation and override:
            # Pin all violations into the audit-trail notes so an
            # auditor reading the row later sees exactly which SoD
            # rules were knowingly bypassed.
            override_lines = []
            if conflicts:
                override_lines.append(
                    'Legacy: '
                    + '; '.join(
                        f'{c["role_a"]}+{c["role_b"]} ({c["severity"]})'
                        for c in conflicts
                    )
                )
            if blocking_rule_violations:
                override_lines.append(
                    'Rule-driven: '
                    + '; '.join(
                        f'{v["rule_code"]} ({v["severity"]})'
                        for v in blocking_rule_violations
                    )
                )
            notes = (
                f'[SOD override] {notes}\n'
                f'Approved conflicts: ' + ' | '.join(override_lines)
            )

        assignment = RoleAssignment.objects.create(
            user_id=user_id, role_id=role_id,
            is_active=True,
            assigned_by=assigned_by,
            notes=notes,
        )
        payload = self.get_serializer(assignment).data
        if any_violation and override:
            payload['sod_override'] = {
                'legacy_conflict_count':       len(conflicts),
                'rule_driven_conflict_count':  len(blocking_rule_violations),
                'conflicts':                   conflicts,
                'rule_driven_violations':      blocking_rule_violations,
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

        # SoD analysis per user — runs BOTH engines so admins see
        # legacy hardcoded role-pair flags AND any tenant-defined
        # rule-driven SoDRule violations side-by-side.
        rows = []
        # Resolve users in one query so we don't hit User.objects N times.
        user_lookup = {
            u.pk: u for u in User.objects.filter(pk__in=by_user.keys())
        }
        for uid, bucket in by_user.items():
            conflicts = conflicts_for_roles(bucket['role_codes'])
            rule_violations = _rule_driven_violations_for_user(
                user_lookup.get(uid),
            )
            bucket['sod_conflicts']            = conflicts
            bucket['rule_driven_violations']   = rule_violations
            bucket['sod_clean']                = not (conflicts or rule_violations)
            bucket['highest_severity']         = _highest_severity(
                conflicts, rule_violations,
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

        # Rule-driven preview: resolve the projected role codes back
        # to permission codes and run check_assignment(). When user_id
        # is provided we use the live user (so existing assignments
        # contribute their permissions); otherwise we project from
        # ``codes`` alone using a temporary set of permission codes.
        rule_violations: list[dict] = []
        target_user = None
        if user_id:
            target_user = User.objects.filter(pk=user_id).first()

        if codes:
            # Collect permission codes from the projected role set.
            projected_perm_codes = set(
                Role.objects
                .filter(code__in=codes, is_active=True)
                .values_list('permissions__code', flat=True)
            )
            projected_perm_codes.discard(None)

            if target_user is not None:
                # Use the standard evaluator so the user's existing
                # permissions are included automatically. We pass the
                # projected permission set as ``additional`` — the
                # evaluator unions it with the live RoleAssignment perms.
                from core.services.sod_evaluator import check_assignment
                try:
                    violations = check_assignment(
                        target_user,
                        additional_permission_codes=projected_perm_codes,
                    )
                    rule_violations = [
                        {
                            'rule_code':     v.rule_code,
                            'rule_name':     v.rule_name,
                            'permission_a':  v.permission_a_code,
                            'permission_b':  v.permission_b_code,
                            'scope':         v.scope,
                            'severity':      v.severity,
                            'reason':        v.reason,
                            'engine':        'rule_driven',
                        }
                        for v in violations
                    ]
                except Exception:
                    pass
            else:
                # No user context — match hold-scope rules where BOTH
                # legs intersect the projected permission set. This
                # answers "would these roles together be SoD-clean?"
                # without needing a target user.
                from core.models import SoDRule
                if projected_perm_codes:
                    candidates = SoDRule.objects.filter(
                        is_active=True, scope='hold',
                        permission_a__code__in=projected_perm_codes,
                        permission_b__code__in=projected_perm_codes,
                    ).select_related('permission_a', 'permission_b')
                    rule_violations = [
                        {
                            'rule_code':     r.code,
                            'rule_name':     r.name,
                            'permission_a':  r.permission_a.code,
                            'permission_b':  r.permission_b.code,
                            'scope':         r.scope,
                            'severity':      r.severity,
                            'reason':        r.description or r.name,
                            'engine':        'rule_driven',
                        }
                        for r in candidates
                    ]

        return Response({
            'codes_checked':           codes,
            'conflict_count':          len(conflicts),
            'rule_driven_count':       len(rule_violations),
            'sod_clean':               not (conflicts or rule_violations),
            'highest_severity':        _highest_severity(conflicts, rule_violations),
            'conflicts':               conflicts,
            'rule_driven_violations':  rule_violations,
        })


def _truthy(v) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ('1', 'true', 'yes', 'on')
