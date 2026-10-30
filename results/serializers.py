from rest_framework import serializers

from .models import (
    ResultsFramework,
    Outcome,
    Output,
    Indicator,
    IndicatorTarget,
    IndicatorActual,
    PerformanceReport,
)


class ResultsFrameworkSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResultsFramework
        fields = ['id', 'name', 'description', 'fiscal_year', 'is_active']


class OutcomeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Outcome
        fields = ['id', 'framework', 'name', 'programme', 'description']


class OutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = Output
        fields = ['id', 'outcome', 'name', 'description']


class IndicatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Indicator
        fields = [
            'id', 'output', 'name', 'indicator_type', 'unit', 'data_source',
            'verification_note', 'baseline',
        ]


class IndicatorTargetSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndicatorTarget
        fields = ['id', 'indicator', 'fiscal_year', 'period', 'frequency', 'target_value']


class IndicatorActualSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndicatorActual
        fields = [
            'id', 'indicator', 'fiscal_year', 'period', 'actual_value',
            'data_source', 'verification_note', 'recorded_at',
        ]
        read_only_fields = ['recorded_at']


class PerformanceReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceReport
        fields = [
            'id', 'scope', 'scope_ref', 'fiscal_year', 'period',
            'physical_progress', 'financial_execution', 'narrative', 'generated_at',
        ]
        read_only_fields = ['generated_at']
