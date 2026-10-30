from rest_framework import serializers

from .models import (
    EstablishmentPost,
    EstablishmentVariance,
    PersonnelCostForecast,
    PayrollBudgetBinding,
)


class EstablishmentPostSerializer(serializers.ModelSerializer):
    mda_display = serializers.CharField(source='mda_name', read_only=True)
    filled_quantity = serializers.SerializerMethodField()

    class Meta:
        model = EstablishmentPost
        fields = [
            'id', 'mda_admin', 'mda_name', 'mda_display', 'grade',
            'approved_quantity', 'effective_date', 'expiry_date',
            'status', 'approved_by', 'approved_at', 'comments',
            'filled_quantity', 'created_at', 'updated_at',
        ]
        read_only_fields = ['approved_by', 'approved_at', 'created_at', 'updated_at']

    def get_filled_quantity(self, obj):
        variance = obj.variances.order_by('-computed_at').first()
        return variance.filled_quantity if variance else 0


class EstablishmentVarianceSerializer(serializers.ModelSerializer):
    post_grade = serializers.CharField(source='post.grade', read_only=True)
    post_mda = serializers.CharField(source='post.mda_name', read_only=True)

    class Meta:
        model = EstablishmentVariance
        fields = [
            'id', 'post', 'post_grade', 'post_mda', 'filled_quantity',
            'approved_quantity', 'variance', 'is_breach', 'utilisation_pct',
            'computed_at',
        ]
        read_only_fields = ['computed_at']


class PersonnelCostForecastSerializer(serializers.ModelSerializer):
    total_projected = serializers.DecimalField(read_only=True, max_digits=18, decimal_places=2)
    over_appropriation = serializers.BooleanField(read_only=True)

    class Meta:
        model = PersonnelCostForecast
        fields = [
            'id', 'fiscal_year', 'mda_name', 'appropriation_line', 'month',
            'projected_payroll', 'approved_appropriation',
            'projected_increment', 'projected_promotion', 'total_projected',
            'over_appropriation', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class PayrollBudgetBindingSerializer(serializers.ModelSerializer):
    payroll_run_ref = serializers.CharField(
        source='payroll_run.reference', read_only=True, default='',
    )

    class Meta:
        model = PayrollBudgetBinding
        fields = [
            'id', 'payroll_run', 'payroll_run_ref', 'appropriation_line',
            'bound_amount', 'remaining_at_binding', 'check_level',
            'bound_by', 'bound_at',
        ]
        read_only_fields = ['remaining_at_binding', 'check_level', 'bound_by', 'bound_at']


class PayrollBudgetBindingCreateSerializer(PayrollBudgetBindingSerializer):
    """Write serializer: requires appropriation_line and amount; the service
    resolves remaining balance and check_level at binding time."""
