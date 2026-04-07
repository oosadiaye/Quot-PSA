from rest_framework import serializers
from .models import (
    IntegrationConfig, FieldMapping, WebhookEndpoint,
    WebhookDelivery, WebhookInboundLog, SyncLog, SyncLogItem,
)


class FieldMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldMapping
        fields = '__all__'
        read_only_fields = ['config']


class WebhookEndpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEndpoint
        fields = '__all__'
        extra_kwargs = {'secret': {'write_only': True}}


class WebhookDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = '__all__'
        read_only_fields = ['endpoint']


class WebhookInboundLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookInboundLog
        fields = '__all__'


class SyncLogItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncLogItem
        exclude = ['content_type', 'object_id']


class SyncLogSerializer(serializers.ModelSerializer):
    items = SyncLogItemSerializer(many=True, read_only=True)
    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = SyncLog
        fields = '__all__'

    def get_duration_seconds(self, obj):
        return obj.duration_seconds


class IntegrationConfigSerializer(serializers.ModelSerializer):
    field_mappings = FieldMappingSerializer(many=True, read_only=True)
    webhook_endpoints = WebhookEndpointSerializer(many=True, read_only=True)
    sync_logs = SyncLogSerializer(many=True, read_only=True)

    class Meta:
        model = IntegrationConfig
        fields = '__all__'
        extra_kwargs = {
            'credentials': {'write_only': True},
            'token_cache': {'write_only': True},
            'webhook_secret': {'write_only': True},
        }


class IntegrationConfigListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views — omits nested logs."""
    class Meta:
        model = IntegrationConfig
        exclude = ['credentials', 'token_cache', 'webhook_secret']
