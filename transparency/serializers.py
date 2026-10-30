from rest_framework import serializers

from .models import PublicationPolicy, Publication, RedactionRule, DataExport


class PublicationPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = PublicationPolicy
        fields = [
            'id', 'dataset', 'aggregation', 'lag_days', 'min_amount_threshold',
            'requires_snapshot', 'status', 'approved_by', 'approved_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['approved_by', 'approved_at', 'created_at', 'updated_at']


class PublicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Publication
        fields = [
            'id', 'policy', 'snapshot', 'title', 'dataset_key', 'fiscal_year',
            'period', 'status', 'published_at', 'published_url', 'published_by',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['published_at', 'published_by', 'created_at', 'updated_at']


class RedactionRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RedactionRule
        fields = [
            'id', 'field_name', 'pattern', 'replacement', 'is_active',
        ]


class DataExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataExport
        fields = [
            'id', 'dataset_key', 'format', 'publication', 'file', 'row_count',
            'created_at',
        ]
        read_only_fields = ['created_at']
