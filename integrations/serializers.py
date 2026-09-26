from rest_framework import serializers

from .models import IntegrationEndpoint, IntegrationRun, IntegrationMessage


class IntegrationEndpointSerializer(serializers.ModelSerializer):
    sources = serializers.ListField(source='sources', read_only=True)

    class Meta:
        model = IntegrationEndpoint
        fields = [
            'id', 'name', 'connector_type', 'environment', 'base_url',
            'credentials_ref', 'is_enabled', 'config', 'timeout_seconds',
            'retry_limit', 'last_success_at', 'last_error', 'sources',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['last_success_at', 'last_error', 'created_at', 'updated_at']


class IntegrationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationMessage
        fields = [
            'id', 'run', 'direction', 'message_key', 'payload_hash', 'status',
            'retry_count', 'failure_reason', 'source_model', 'source_id',
            'sent_at',
        ]
        read_only_fields = ['sent_at']


class IntegrationRunSerializer(serializers.ModelSerializer):
    endpoint_name = serializers.CharField(source='endpoint.name', read_only=True)

    class Meta:
        model = IntegrationRun
        fields = [
            'id', 'endpoint', 'endpoint_name', 'started_at', 'finished_at',
            'status', 'messages_sent', 'messages_received', 'messages_failed',
            'payload_hash', 'trigger', 'operator_note',
        ]
        read_only_fields = ['started_at', 'finished_at']
