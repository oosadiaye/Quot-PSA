from django.contrib import admin
from .models import (
    IntegrationConfig, FieldMapping, WebhookEndpoint,
    WebhookDelivery, WebhookInboundLog, SyncLog, SyncLogItem,
)


@admin.register(IntegrationConfig)
class IntegrationConfigAdmin(admin.ModelAdmin):
    list_display = ['name', 'system_type', 'is_active', 'direction', 'last_sync_at', 'created_at']
    list_filter = ['system_type', 'is_active', 'direction']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at', 'last_sync_at']
    actions = ['test_connections']

    def test_connections(self, request, queryset):
        from .adapters.factory import get_adapter
        for config in queryset:
            try:
                adapter = get_adapter(config)
                ok = adapter.test_connection()
                self.message_user(request, f'{config.name}: {"OK" if ok else "FAILED"}')
            except Exception as exc:
                self.message_user(request, f'{config.name}: ERROR — {exc}', level='error')
    test_connections.short_description = 'Test connection to selected integrations'


class FieldMappingInline(admin.TabularInline):
    model = FieldMapping
    extra = 1


@admin.register(FieldMapping)
class FieldMappingAdmin(admin.ModelAdmin):
    list_display = ['config', 'module', 'dtsg_field', 'remote_field', 'transform', 'direction']
    list_filter = ['module', 'direction', 'config']
    search_fields = ['dtsg_field', 'remote_field']


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ['name', 'target_url', 'is_active', 'max_retries', 'created_at']
    list_filter = ['is_active']


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ['endpoint', 'event_type', 'status', 'response_status', 'attempt_count', 'created_at']
    list_filter = ['status', 'event_type']
    readonly_fields = ['endpoint', 'event_type', 'payload', 'response_status',
                       'response_body', 'attempt_count', 'status', 'created_at',
                       'delivered_at', 'next_retry_at', 'error_message']


@admin.register(WebhookInboundLog)
class WebhookInboundLogAdmin(admin.ModelAdmin):
    list_display = ['source_system', 'event_type', 'processing_status', 'signature_valid', 'received_at']
    list_filter = ['source_system', 'processing_status']
    readonly_fields = ['received_at', 'processed_at']


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ['config', 'module', 'direction', 'status', 'records_total',
                    'records_created', 'records_updated', 'records_failed', 'started_at']
    list_filter = ['status', 'module', 'direction']
    readonly_fields = ['started_at', 'finished_at']


@admin.register(SyncLogItem)
class SyncLogItemAdmin(admin.ModelAdmin):
    list_display = ['sync_log', 'action', 'status', 'remote_id', 'created_at']
    list_filter = ['status', 'action']
