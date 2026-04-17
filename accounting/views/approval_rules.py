"""
Approval rule admin API.

Read-biased: any authenticated user can browse the configured rules
(so they understand what needs approval before submitting). Writes
require admin.

Endpoints
---------
* ``GET    /api/v1/accounting/approval-rules/``       — list rules
* ``GET    /api/v1/accounting/approval-rules/{id}/``  — retrieve
* ``POST   /api/v1/accounting/approval-rules/``       — create (admin)
* ``PATCH  /api/v1/accounting/approval-rules/{id}/``  — update (admin)
* ``DELETE /api/v1/accounting/approval-rules/{id}/``  — soft-delete
                                                         (is_active=False)
* ``GET    /api/v1/accounting/approval-rules/summary/`` — grouped view
                                                             for the UI
"""
from __future__ import annotations

from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from accounting.models.audit import (
    ApprovalRule, ApprovalLevel, DualControlOverride,
)


class ApprovalLevelSerializer(serializers.ModelSerializer):
    approver_type_display = serializers.CharField(
        source='get_approver_type_display', read_only=True,
    )
    role_name = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalLevel
        fields = [
            'id', 'level', 'approver_type', 'approver_type_display',
            'approver_value', 'role_name', 'min_approvers',
        ]
        read_only_fields = ['id', 'approver_type_display', 'role_name']

    def get_role_name(self, obj: ApprovalLevel) -> str | None:
        """When approver_type='ROLE' and the code matches a core.Role,
        surface the human-readable name so the UI doesn't have to do a
        second round-trip."""
        if obj.approver_type != 'ROLE' or not obj.approver_value:
            return None
        try:
            from core.models import Role
            r = Role.objects.filter(code=obj.approver_value).first()
            return r.name if r else None
        except Exception:
            return None


class ApprovalRuleSerializer(serializers.ModelSerializer):
    document_type_display = serializers.CharField(
        source='get_document_type_display', read_only=True,
    )
    levels = ApprovalLevelSerializer(many=True, read_only=True)
    level_count = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRule
        fields = [
            'id', 'document_type', 'document_type_display',
            'min_amount', 'max_amount',
            'approval_levels',  # legacy JSON field — kept for back-compat
            'auto_approve_roles',
            'skip_approval_if_same_user',
            'require_comment_on_reject',
            'is_active',
            'levels', 'level_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'document_type_display', 'levels', 'level_count',
            'created_at', 'updated_at',
        ]

    def get_level_count(self, obj: ApprovalRule) -> int:
        return obj.levels.count()


class ApprovalRuleViewSet(viewsets.ModelViewSet):
    """CRUD over approval rules. Read for all authenticated users,
    write for admin only."""
    queryset = (
        ApprovalRule.objects
        .prefetch_related('levels')
        .order_by('document_type', 'min_amount')
    )
    serializer_class = ApprovalRuleSerializer
    filterset_fields = ['document_type', 'is_active']
    ordering_fields = ['document_type', 'min_amount', 'created_at']

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'summary'):
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def perform_destroy(self, instance: ApprovalRule):
        # Soft-delete so historic ApprovalInstance rows keep their
        # rule reference alive for audit queries.
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])

    # -----------------------------------------------------------------
    # Summary — grouped by document_type for the admin page.
    # -----------------------------------------------------------------
    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """Pivot the rule list into a document-type-keyed structure
        with human-readable role names pre-resolved. Used by the
        admin page to render the matrix in one query."""
        from core.models import Role

        # Cache role lookup to avoid N+1.
        role_name_by_code = {
            r.code: r.name
            for r in Role.objects.filter(is_active=True)
        }

        rules = list(
            ApprovalRule.objects
            .filter(is_active=True)
            .prefetch_related('levels')
            .order_by('document_type', 'min_amount')
        )

        groups: dict[str, dict] = {}
        for rule in rules:
            doc = rule.document_type
            bucket = groups.setdefault(doc, {
                'document_type':         doc,
                'document_type_display': rule.get_document_type_display(),
                'rules': [],
            })
            levels_payload = []
            for lvl in rule.levels.all():
                levels_payload.append({
                    'level':          lvl.level,
                    'approver_type':  lvl.approver_type,
                    'approver_value': lvl.approver_value,
                    'role_name':      role_name_by_code.get(
                        lvl.approver_value
                    ) if lvl.approver_type == 'ROLE' else None,
                    'min_approvers':  lvl.min_approvers,
                })
            bucket['rules'].append({
                'id':         rule.id,
                'min_amount': str(rule.min_amount),
                'max_amount': str(rule.max_amount) if rule.max_amount else None,
                'is_active':  rule.is_active,
                'levels':     levels_payload,
            })

        return Response({
            'groups': list(groups.values()),
            'total_rules': len(rules),
            'documents_covered': len(groups),
        })


class DualControlOverrideSerializer(serializers.ModelSerializer):
    requested_by_username = serializers.SerializerMethodField()
    approved_by_username = serializers.SerializerMethodField()

    class Meta:
        model = DualControlOverride
        fields = [
            'id', 'document_type', 'document_id',
            'requested_by', 'requested_by_username',
            'requested_at',
            'justification',
            'approved_by', 'approved_by_username', 'approved_at',
            'status', 'ip_address',
        ]
        read_only_fields = fields

    def get_requested_by_username(self, obj):
        return getattr(obj.requested_by, 'username', None)

    def get_approved_by_username(self, obj):
        return (
            getattr(obj.approved_by, 'username', None)
            if obj.approved_by_id else None
        )


class DualControlOverrideViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only feed of dual-control override attempts.

    Surfaces every time a single user invoked a dual-sig override with
    its justification + approval state. Used by the Override Audit
    panel on the frontend.
    """
    queryset = DualControlOverride.objects.select_related(
        'requested_by', 'approved_by',
    ).order_by('-requested_at')
    serializer_class = DualControlOverrideSerializer
    filterset_fields = ['status', 'document_type', 'requested_by']
    ordering = ['-requested_at']
    permission_classes = [IsAuthenticated]
