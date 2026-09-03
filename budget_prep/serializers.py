from rest_framework import serializers

from .models import (
    CallCircular,
    MTEFProjection,
    MDACeiling,
    BudgetSubmission,
    SubmissionLine,
    ReviewComment,
)


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
            'functional', 'description', 'proposed_amount', 'ceiling_reference',
        ]


class BudgetSubmissionSerializer(serializers.ModelSerializer):
    lines = SubmissionLineSerializer(many=True, read_only=True)

    class Meta:
        model = BudgetSubmission
        fields = [
            'id', 'fiscal_year', 'mda_name', 'circular', 'stage',
            'submitted_at', 'total_personnel', 'total_overhead', 'total_capital',
            'notes', 'lines', 'created_at', 'updated_at',
        ]
        read_only_fields = ['submitted_at', 'created_at', 'updated_at']


class ReviewCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewComment
        fields = [
            'id', 'submission', 'comment', 'action_required',
            'commented_by', 'commented_at',
        ]
        read_only_fields = ['commented_at']
