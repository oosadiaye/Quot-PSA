from rest_framework import serializers
from .models import UnifiedBudget, UnifiedBudgetEncumbrance, UnifiedBudgetVariance, UnifiedBudgetAmendment


class UnifiedBudgetVarianceSerializer(serializers.ModelSerializer):
    budget_code = serializers.ReadOnlyField(source='budget.budget_code')
    period_variance_percent = serializers.ReadOnlyField()
    ytd_variance_percent = serializers.ReadOnlyField()
    
    class Meta:
        model = UnifiedBudgetVariance
        fields = [
            'id', 'budget', 'budget_code', 'fiscal_year', 'period_type', 'period_number',
            'variance_type', 'period_budget', 'period_actual', 'period_variance', 'period_variance_percent',
            'ytd_budget', 'ytd_actual', 'ytd_variance', 'ytd_variance_percent',
            'encumbered_amount', 'committed_amount', 'calculated_at'
        ]


class UnifiedBudgetEncumbranceSerializer(serializers.ModelSerializer):
    budget_code = serializers.ReadOnlyField(source='budget.budget_code')
    remaining_amount = serializers.ReadOnlyField()
    
    class Meta:
        model = UnifiedBudgetEncumbrance
        fields = [
            'id', 'budget', 'budget_code', 'reference_type', 'reference_id', 'reference_number',
            'encumbrance_date', 'amount', 'liquidated_amount', 'remaining_amount',
            'status', 'description', 'is_aggregate', 'created_by', 'created_at'
        ]


class UnifiedBudgetAmendmentSerializer(serializers.ModelSerializer):
    budget_code = serializers.ReadOnlyField(source='budget.budget_code')
    requested_by_name = serializers.ReadOnlyField(source='requested_by.username')
    approved_by_name = serializers.ReadOnlyField(source='approved_by.username')
    
    class Meta:
        model = UnifiedBudgetAmendment
        fields = [
            'id', 'budget', 'budget_code', 'amendment_number', 'amendment_type',
            'original_amount', 'new_amount', 'change_amount',
            'from_budget', 'to_budget', 'reason', 'status',
            'requested_by', 'requested_by_name', 'approved_by', 'approved_by_name',
            'approved_date', 'created_at'
        ]


class UnifiedBudgetSerializer(serializers.ModelSerializer):
    """Serializer for Unified Budget - supports both Public and Private Sector"""
    allocated_amount = serializers.ReadOnlyField()
    encumbered_amount = serializers.ReadOnlyField()
    actual_expended = serializers.ReadOnlyField()
    available_amount = serializers.ReadOnlyField()
    utilization_rate = serializers.ReadOnlyField()
    variance_amount = serializers.ReadOnlyField()
    variance_percent = serializers.ReadOnlyField()
    
    mda_name = serializers.ReadOnlyField(source='mda.name')
    cost_center_name = serializers.ReadOnlyField(source='cost_center.name')
    fund_name = serializers.ReadOnlyField(source='fund.name')
    function_name = serializers.ReadOnlyField(source='function.name')
    program_name = serializers.ReadOnlyField(source='program.name')
    geo_name = serializers.ReadOnlyField(source='geo.name')
    account_code = serializers.ReadOnlyField(source='account.code')
    account_name = serializers.ReadOnlyField(source='account.name')
    
    class Meta:
        model = UnifiedBudget
        fields = [
            'id', 'budget_code', 'name', 'description', 'budget_type',
            'fiscal_year', 'period_type', 'period_number', 'status',
            'mda', 'mda_name', 'fund', 'fund_name', 'function', 'function_name',
            'program', 'program_name', 'geo', 'geo_name', 'cost_center', 'cost_center_name',
            'account', 'account_code', 'account_name',
            'original_amount', 'revised_amount', 'supplemental_amount', 'allocated_amount',
            'control_level', 'enable_encumbrance', 'allow_over_expenditure', 'over_expenditure_limit_percent',
            'approved_by', 'approved_date', 'closed_date',
            'encumbered_amount', 'actual_expended', 'available_amount',
            'utilization_rate', 'variance_amount', 'variance_percent',
            'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'approved_date', 'closed_date']


# Legacy aliases for backward compatibility
BudgetVarianceSerializer = UnifiedBudgetVarianceSerializer
BudgetLineSerializer = UnifiedBudgetEncumbranceSerializer
BudgetAllocationSerializer = UnifiedBudgetSerializer
