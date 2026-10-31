from django.utils import timezone
from rest_framework import serializers

from .models import (
    BudgetMilestone,
    CallCircular,
    MTEFProjection,
    MDACeiling,
    BudgetSubmission,
    SubmissionLine,
    ReviewComment,
)
from .services.calendar import status_of


class CallCircularSerializer(serializers.ModelSerializer):
    class Meta:
        model = CallCircular
        fields = [
            'id', 'fiscal_year', 'issue_date', 'submission_deadline',
            'guidelines', 'is_active', 'document',
        ]


class MTEFProjectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MTEFProjection
        fields = [
            'id', 'fiscal_year', 'inflation_assumption', 'exchange_rate_assumption',
            'oil_price_assumption', 'aggregate_revenue', 'aggregate_expenditure',
            'fiscal_balance',
        ]


class MDACeilingSerializer(serializers.ModelSerializer):
    total_ceiling = serializers.DecimalField(read_only=True, max_digits=18, decimal_places=2)

    class Meta:
        model = MDACeiling
        fields = [
            'id', 'fiscal_year', 'mda_name', 'personnel_ceiling',
            'overhead_ceiling', 'capital_ceiling', 'total_ceiling',
        ]


class SubmissionLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmissionLine
        fields = [
            'id', 'submission', 'line_type', 'administrative', 'economic',
            'functional', 'fund', 'programme', 'description', 'proposed_amount', 'ceiling_reference',
            'adopted_basis', 'baseline_amount', 'adjustment_pct',
        ]
        read_only_fields = ['adopted_basis', 'baseline_amount', 'adjustment_pct']


class BudgetSubmissionSerializer(serializers.ModelSerializer):
    lines = SubmissionLineSerializer(many=True, read_only=True)

    class Meta:
        model = BudgetSubmission
        fields = [
            'id', 'fiscal_year', 'mda_name', 'circular', 'stage',
            'submitted_at', 'total_personnel', 'total_overhead', 'total_capital',
            'notes', 'lines', 'created_at', 'updated_at',
        ]
        read_only_fields = ['submitted_at', 'total_personnel', 'total_overhead', 'total_capital', 'created_at', 'updated_at']

    def validate_stage(self, value):
        # Submitting is the one move that has a control (the MDA ceiling), so it only happens through the Submit action.
        current = self.instance.stage if self.instance else None
        if value == 'submitted' and current != 'submitted':
            raise serializers.ValidationError('Use Submit to send a submission to the Budget Office; it checks the MDA ceiling.')
        return value


class BudgetMilestoneSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    days_to_due = serializers.SerializerMethodField()

    class Meta:
        model = BudgetMilestone
        fields = [
            'id', 'fiscal_year', 'sequence', 'name', 'due_date', 'completed_on', 'owner', 'notes', 'std_key',
            'status', 'days_to_due',
        ]
        read_only_fields = ['std_key']

    def get_status(self, obj) -> str:
        return status_of(obj, timezone.localdate())

    def get_days_to_due(self, obj):
        return None if obj.completed_on else (obj.due_date - timezone.localdate()).days


class ReviewCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewComment
        fields = [
            'id', 'submission', 'comment', 'action_required',
            'commented_by', 'commented_at',
        ]
        read_only_fields = ['commented_at']
