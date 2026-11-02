from rest_framework import serializers

from .models import (
    StaffAdvance,
    ImprestAccount,
    ImprestRetirement,
    PerDiemTable,
    TravelRequest,
    TravelAdvance,
    TravelRetirement,
)


class StaffAdvanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source='employee.first_name', read_only=True, default='',
    )
    outstanding = serializers.DecimalField(read_only=True, max_digits=15, decimal_places=2)

    class Meta:
        model = StaffAdvance
        fields = [
            'id', 'employee', 'employee_name', 'recon_account', 'purpose',
            'amount', 'advance_date', 'recovery_start', 'status',
            'recovered_amount', 'outstanding', 'journal', 'reference', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['recovered_amount', 'journal', 'created_at', 'updated_at']


class ImprestAccountSerializer(serializers.ModelSerializer):
    outstanding_retirement = serializers.DecimalField(
        read_only=True, max_digits=15, decimal_places=2,
    )

    class Meta:
        model = ImprestAccount
        fields = [
            'id', 'employee', 'reference', 'issued_amount', 'retired_amount',
            'replenished_amount', 'issue_date', 'retirement_due_date', 'status',
            'outstanding_retirement', 'created_at', 'updated_at',
        ]
        read_only_fields = ['retired_amount', 'replenished_amount', 'created_at', 'updated_at']


class ImprestRetirementSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImprestRetirement
        fields = [
            'id', 'imprest', 'retirement_date', 'amount', 'supporting_docs',
            'approved_by', 'approved_at', 'journal',
        ]
        read_only_fields = ['approved_by', 'approved_at', 'journal']


class PerDiemTableSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerDiemTable
        fields = [
            'id', 'grade', 'destination', 'daily_rate', 'effective_date',
            'is_active',
        ]


class TravelRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source='employee.first_name', read_only=True, default='',
    )

    class Meta:
        model = TravelRequest
        fields = [
            'id', 'employee', 'employee_name', 'destination', 'purpose',
            'start_date', 'end_date', 'days', 'estimated_cost', 'status',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class TravelAdvanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = TravelAdvance
        fields = ['id', 'travel_request', 'staff_advance', 'amount', 'advance_date']


class TravelRetirementSerializer(serializers.ModelSerializer):
    class Meta:
        model = TravelRetirement
        fields = [
            'id', 'travel_advance', 'retired_date', 'amount',
            'balance_returned', 'documents',
        ]
