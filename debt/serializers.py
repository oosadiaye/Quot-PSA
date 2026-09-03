from rest_framework import serializers

from .models import (
    DebtInstrument,
    AmortisationSchedule,
    AmortisationCoupon,
    AmortisationLedger,
    DebtServiceCost,
    DebtAversionStatement,
)


class DebtInstrumentSerializer(serializers.ModelSerializer):
    outstanding_principal = serializers.DecimalField(read_only=True, max_digits=18, decimal_places=2)

    class Meta:
        model = DebtInstrument
        fields = [
            'id', 'instrument_number', 'instrument_type', 'creditor', 'currency',
            'principal_amount', 'interest_rate', 'commitment_fee_rate',
            'start_date', 'maturity_date', 'grace_period', 'status',
            'is_concessional', 'outstanding_principal', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class AmortisationScheduleSerializer(serializers.ModelSerializer):
    total_amount = serializers.DecimalField(read_only=True, max_digits=18, decimal_places=2)

    class Meta:
        model = AmortisationSchedule
        fields = [
            'id', 'instrument', 'coupon_date', 'principal_amount',
            'interest_amount', 'commitment_fee', 'total_amount', 'is_released',
        ]


class AmortisationCouponSerializer(serializers.ModelSerializer):
    total_amount = serializers.DecimalField(read_only=True, max_digits=18, decimal_places=2)

    class Meta:
        model = AmortisationCoupon
        fields = [
            'id', 'schedule', 'principal_amount', 'interest_amount',
            'commitment_fee', 'total_amount', 'status', 'warrant', 'paid_at',
        ]
        read_only_fields = ['paid_at']


class AmortisationLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = AmortisationLedger
        fields = [
            'id', 'coupon', 'event', 'amount', 'warrant', 'description',
            'recorded_by', 'recorded_at',
        ]
        read_only_fields = ['recorded_at']


class DebtServiceCostSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebtServiceCost
        fields = [
            'id', 'fiscal_year', 'month', 'instrument', 'principal_paid',
            'interest_paid', 'fees_paid',
        ]


class DebtAversionStatementSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebtAversionStatement
        fields = [
            'id', 'fiscal_year', 'pillar', 'outstanding_balance', 'gdp',
            'revenue', 'debt_to_gdp', 'debt_service_to_revenue', 'assessment',
        ]
