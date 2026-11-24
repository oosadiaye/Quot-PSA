from rest_framework import serializers

from .models import (
    AuditUniverse,
    AuditPlan,
    AuditEngagement,
    WorkingPaper,
    AuditFinding,
    FollowUp,
    ContinuousAuditRule,
)


class AuditUniverseSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditUniverse
        fields = ['id', 'entity_name', 'entity_ref', 'risk_score', 'is_active']


class AuditPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditPlan
        fields = [
            'id', 'fiscal_year', 'title', 'status', 'total_engagements',
            'approved_by', 'approved_at',
        ]
        read_only_fields = ['approved_by', 'approved_at']


class AuditEngagementSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEngagement
        fields = [
            'id', 'plan', 'universe', 'title', 'scope', 'status', 'team',
            'planned_start', 'planned_end',
        ]


class WorkingPaperSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkingPaper
        fields = [
            'id', 'engagement', 'title', 'reference', 'description',
            'attachment', 'attachment_hash', 'created_by',
        ]
        read_only_fields = ['created_by']


class AuditFindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditFinding
        fields = [
            'id', 'engagement', 'title', 'rating', 'status', 'recommendation',
            'management_response', 'agreed_action', 'due_date',
        ]


class FollowUpSerializer(serializers.ModelSerializer):
    class Meta:
        model = FollowUp
        fields = [
            'id', 'finding', 'follow_up_date', 'note', 'is_overdue', 'escalated_by',
        ]
        read_only_fields = ['escalated_by']


class ContinuousAuditRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContinuousAuditRule
        fields = ['id', 'name', 'sql_hint', 'schedule', 'is_active']