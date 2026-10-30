from rest_framework import serializers

from .models import (
    CashPlan,
    CashForecastLine,
    CashPosition,
    WarrantRecommendation,
    CashPlanVariance,
)


class CashPlanSerializer(serializers.ModelSerializer):
    net_planned = serializers.DecimalField(read_only=True, max_digits=18, decimal_places=2)
    lines = serializers.SerializerMethodField()

    class Meta:
        model = CashPlan
        fields = [
            'id', 'fiscal_year', 'month', 'plan_type', 'fund', 'mda_name',
            'planned_inflow', 'planned_outflow', 'net_planned', 'notes',
            'lines', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_lines(self, obj):
        try:
            return CashForecastLineSerializer(obj.lines.all(), many=True).data
        except Exception:
            return []


class CashForecastLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashForecastLine
        fields = [
            'id', 'cash_plan', 'source', 'flow', 'amount', 'due_date',
            'description', 'source_ref',
        ]


class CashPositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashPosition
        fields = [
            'id', 'position_date', 'opening_balance', 'projected_inflow',
            'projected_outflow', 'closing_balance', 'warning_floor',
            'is_below_floor', 'notes',
        ]


class WarrantRecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = WarrantRecommendation
        fields = [
            'id', 'recommendation_date', 'mda_name', 'appropriation', 'fund',
            'proposed_amount', 'status', 'rationale', 'warrant',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class CashPlanVarianceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashPlanVariance
        fields = [
            'id', 'fiscal_year', 'month', 'mda_name', 'planned_inflow',
            'actual_inflow', 'planned_outflow', 'actual_outflow',
        ]
