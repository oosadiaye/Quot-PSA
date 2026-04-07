from django.contrib import admin

from .models import (
    SuperAdminProfile, SuperAdminSettings, ImpersonationLog,
    Referrer, Referral, Commission, CommissionPayout,
    SupportTicket, TicketComment, TicketAttachment,
    LanguageConfig, CurrencyConfig, TenantLanguageSetting, TenantCurrencySetting,
    TenantSMTPConfig, TenantAPIKey,
    WebhookConfig, WebhookDelivery, Announcement, TenantNotification,
    TenantUsage, Invoice,
)


@admin.register(SuperAdminProfile)
class SuperAdminProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_superadmin', 'is_active', 'created_at']
    list_filter = ['is_superadmin', 'is_active']


@admin.register(SuperAdminSettings)
class SuperAdminSettingsAdmin(admin.ModelAdmin):
    list_display = ['organization_name', 'default_timezone', 'default_currency', 'maintenance_mode']
    # SEC: never expose SMTP credentials in the admin UI
    exclude = ['smtp_password']

    def has_add_permission(self, request):
        return not SuperAdminSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ImpersonationLog)
class ImpersonationLogAdmin(admin.ModelAdmin):
    """Read-only audit trail — no adding or deleting from the admin interface."""
    list_display = ['superadmin', 'target_user', 'target_tenant', 'started_at', 'ended_at', 'is_active']
    list_filter = ['is_active', 'target_tenant']
    # Every field is readonly — the audit log must be immutable
    readonly_fields = [
        'superadmin', 'target_user', 'target_tenant', 'token_key',
        'started_at', 'ended_at', 'ip_address', 'is_active',
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Referrer)
class ReferrerAdmin(admin.ModelAdmin):
    list_display = ['contact_name', 'referrer_code', 'referrer_type', 'email', 'commission_rate', 'is_active']
    list_filter = ['referrer_type', 'is_active']
    search_fields = ['contact_name', 'email', 'referrer_code', 'company_name']


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ['referrer', 'tenant', 'status', 'referred_at', 'converted_at']
    list_filter = ['status']
    search_fields = ['referrer__contact_name', 'tenant__name']


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = ['referrer', 'tenant', 'sale_amount', 'commission_amount', 'status', 'sale_date']
    list_filter = ['status']
    search_fields = ['referrer__contact_name', 'tenant__name']


@admin.register(CommissionPayout)
class CommissionPayoutAdmin(admin.ModelAdmin):
    list_display = ['referrer', 'period_start', 'period_end', 'total_commissions', 'status']
    list_filter = ['status']


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ['ticket_number', 'subject', 'category', 'priority', 'status', 'requester_name', 'created_at']
    list_filter = ['status', 'priority', 'category']
    search_fields = ['ticket_number', 'subject', 'requester_name', 'requester_email']


@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'author', 'is_internal', 'created_at']
    list_filter = ['is_internal']


@admin.register(TicketAttachment)
class TicketAttachmentAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'file_name', 'uploaded_by', 'uploaded_at']


@admin.register(LanguageConfig)
class LanguageConfigAdmin(admin.ModelAdmin):
    list_display = ['language_code', 'language_name', 'native_name', 'is_active', 'is_default']
    list_filter = ['is_active', 'is_default']


@admin.register(CurrencyConfig)
class CurrencyConfigAdmin(admin.ModelAdmin):
    list_display = ['currency_code', 'currency_name', 'symbol', 'is_active', 'is_default', 'exchange_rate_to_base']
    list_filter = ['is_active', 'is_default']


@admin.register(TenantLanguageSetting)
class TenantLanguageSettingAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'language', 'allow_user_override']


@admin.register(TenantCurrencySetting)
class TenantCurrencySettingAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'currency', 'allow_user_override']


@admin.register(TenantSMTPConfig)
class TenantSMTPConfigAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'smtp_host', 'smtp_from_email', 'is_active', 'is_verified']
    list_filter = ['is_active', 'is_verified']
    # SEC: never expose SMTP credentials in the admin UI
    exclude = ['smtp_password']


@admin.register(TenantAPIKey)
class TenantAPIKeyAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'key_name', 'key_type', 'is_active', 'created_at']
    list_filter = ['key_type', 'is_active']


@admin.register(WebhookConfig)
class WebhookConfigAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'webhook_name', 'webhook_url', 'is_active']
    list_filter = ['is_active']


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ['webhook', 'event', 'status', 'status_code', 'attempted_at']
    list_filter = ['status', 'event']


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ['title', 'priority', 'target', 'is_published', 'starts_at', 'ends_at']
    list_filter = ['priority', 'target', 'is_published']


@admin.register(TenantNotification)
class TenantNotificationAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'notification_type', 'title', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read']


@admin.register(TenantUsage)
class TenantUsageAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'billing_period_start', 'billing_period_end', 'total_cost', 'is_billed']
    list_filter = ['is_billed']


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'tenant', 'total_amount', 'status', 'issue_date', 'due_date']
    list_filter = ['status']
    search_fields = ['invoice_number', 'tenant__name']
