from rest_framework import serializers
from .models import UnifiedBudget, UnifiedBudgetEncumbrance, UnifiedBudgetVariance, UnifiedBudgetAmendment, RevenueBudget


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


# ─── Government Appropriation & Warrant (Quot PSE Phase 3) ───────────

from .models import Appropriation, Warrant


class AppropriationSerializer(serializers.ModelSerializer):
    # ── Segment codes (for audit / cross-reference) ──────────
    administrative_code = serializers.CharField(source='administrative.code', read_only=True)
    administrative_name = serializers.CharField(source='administrative.name', read_only=True)
    economic_code = serializers.CharField(source='economic.code', read_only=True)
    economic_name = serializers.CharField(source='economic.name', read_only=True)
    functional_code = serializers.CharField(source='functional.code', read_only=True)
    functional_name = serializers.CharField(source='functional.name', read_only=True)
    programme_code = serializers.CharField(source='programme.code', read_only=True)
    programme_name = serializers.CharField(source='programme.name', read_only=True)
    fund_code = serializers.CharField(source='fund.code', read_only=True)
    fund_name = serializers.CharField(source='fund.name', read_only=True)
    geographic_code = serializers.CharField(source='geographic.code', read_only=True)
    geographic_name = serializers.CharField(source='geographic.name', read_only=True)

    fiscal_year_label = serializers.SerializerMethodField()
    total_warrants_released = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    total_committed = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    total_expended = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    available_balance = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    execution_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = Appropriation
        fields = [
            'id', 'fiscal_year', 'fiscal_year_label',
            'administrative', 'administrative_code', 'administrative_name',
            'economic', 'economic_code', 'economic_name',
            'functional', 'functional_code', 'functional_name',
            'programme', 'programme_code', 'programme_name',
            'fund', 'fund_code', 'fund_name',
            'geographic', 'geographic_code', 'geographic_name',
            'amount_approved', 'appropriation_type', 'status',
            'law_reference', 'enactment_date', 'description', 'notes',
            'total_warrants_released', 'total_committed',
            'total_expended', 'available_balance', 'execution_rate',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_fiscal_year_label(self, obj: Appropriation) -> str:
        return str(obj.fiscal_year) if obj.fiscal_year else ''


class WarrantSerializer(serializers.ModelSerializer):
    appropriation_mda = serializers.CharField(
        source='appropriation.administrative.name', read_only=True,
    )
    appropriation_account = serializers.CharField(
        source='appropriation.economic.name', read_only=True,
    )
    attachment_url = serializers.SerializerMethodField()

    class Meta:
        model = Warrant
        fields = [
            'id', 'appropriation', 'appropriation_mda', 'appropriation_account',
            'quarter', 'amount_released', 'release_date',
            'authority_reference', 'issued_by', 'status',
            'attachment', 'attachment_url', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'attachment_url']

    def get_attachment_url(self, obj: Warrant) -> str | None:
        if obj.attachment:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.attachment.url)
            return obj.attachment.url
        return None


class RevenueBudgetSerializer(serializers.ModelSerializer):
    administrative_name = serializers.CharField(
        source='administrative.name', read_only=True,
    )
    economic_name = serializers.CharField(
        source='economic.name', read_only=True,
    )
    fund_name = serializers.CharField(
        source='fund.name', read_only=True,
    )
    actual_collected = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    variance = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    performance_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = RevenueBudget
        fields = [
            'id', 'fiscal_year', 'administrative', 'administrative_name',
            'economic', 'economic_name', 'fund', 'fund_name',
            'estimated_amount', 'monthly_spread', 'status',
            'actual_collected', 'variance', 'performance_rate',
            'description', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'actual_collected', 'variance', 'performance_rate']


class BudgetValidationRequestSerializer(serializers.Serializer):
    """For the pre-expenditure validation endpoint."""
    administrative_id = serializers.IntegerField()
    economic_id = serializers.IntegerField()
    fund_id = serializers.IntegerField()
    fiscal_year_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
