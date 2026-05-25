from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Sum
from rest_framework import serializers

from .models import (
    Referrer, Referral, Commission, CommissionPayout,
    SupportTicket, TicketComment, TicketAttachment,
    LanguageConfig, CurrencyConfig, TenantLanguageSetting, TenantCurrencySetting,
    TenantSMTPConfig, TenantAPIKey,
    WebhookConfig, WebhookDelivery, Announcement, TenantNotification,
    SubscriptionPlan, SuperAdminSettings, ImpersonationLog,
    TenantUsage, Invoice,
)
# NOTE: ``Subscription`` was previously imported here but no such
# model exists in ``superadmin.models`` — the import has been broken
# since this file was first written, and ``SubscriptionSerializer``
# below was dead code (never referenced from any view). The
# canonical subscription model is ``tenants.models.TenantSubscription``
# which is exposed via ``tenants.serializers.TenantSubscriptionSerializer``.
# The broken import and dead serializer have been removed.


# Universal mass-assignment guard. Every serializer in this module
# uses ``fields = '__all__'`` because the superadmin UI consumes a
# wide projection — but most of these fields must NEVER be writable
# from the client. The audit (S4 finding "fields='__all__' mass
# assignment") flagged the risk: a malicious POST could set
# ``id``, ``created_at``, ``created_by``, or — worst — ``tenant``
# (re-pointing a record into a different tenant). Adding this
# universal read-only set to every Meta.read_only_fields closes
# that without forcing every serializer to enumerate the full
# field list. Per-model sensitive fields (``is_active`` toggles,
# billing fields, audit-log payloads) are layered on top in each
# class.
_UNIVERSAL_READ_ONLY = (
    'id',
    'created_at', 'updated_at',
    'created_by', 'updated_by',
    # ``tenant`` FK is the classic horizontal-privilege-escalation
    # vector — re-pointing a Subscription to another tenant would
    # silently transfer ownership. Always read-only via the API;
    # writes happen via the dedicated provision/transfer service
    # paths.
    'tenant',
)


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = '__all__'
        # SubscriptionPlan has no ``tenant`` FK — it's the catalogue
        # of available plans. The base audit fields are still
        # locked down.
        read_only_fields = ('id', 'created_at', 'updated_at')


class ReferrerSerializer(serializers.ModelSerializer):
    total_referrals = serializers.SerializerMethodField()
    total_commission = serializers.SerializerMethodField()
    pending_commission = serializers.SerializerMethodField()

    class Meta:
        model = Referrer
        fields = '__all__'
        # No tenant FK on Referrer — they're platform-wide partners.
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_total_referrals(self, obj):
        return obj.referrals.count()
    
    def get_total_commission(self, obj):
        total = obj.commissions.filter(status='Paid').aggregate(
            total=Sum('commission_amount')
        )['total']
        return total or Decimal('0')

    def get_pending_commission(self, obj):
        total = obj.commissions.filter(status__in=['Pending', 'Approved']).aggregate(
            total=Sum('commission_amount')
        )['total']
        return total or Decimal('0')


class ReferralSerializer(serializers.ModelSerializer):
    referrer_name = serializers.ReadOnlyField(source='referrer.contact_name')
    tenant_name = serializers.ReadOnlyField(source='tenant.name')

    class Meta:
        model = Referral
        fields = '__all__'
        read_only_fields = _UNIVERSAL_READ_ONLY


class CommissionSerializer(serializers.ModelSerializer):
    referrer_name = serializers.ReadOnlyField(source='referrer.contact_name')
    tenant_name = serializers.ReadOnlyField(source='tenant.name')
    referral_status = serializers.ReadOnlyField(source='referral.status')

    class Meta:
        model = Commission
        fields = '__all__'
        # ``status`` is a workflow column controlled by the
        # admin's approve/pay actions — never directly settable
        # on POST/PUT. Same for ``paid_at``.
        read_only_fields = _UNIVERSAL_READ_ONLY + ('status', 'paid_at')


class TicketCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.ReadOnlyField(source='author.username')

    class Meta:
        model = TicketComment
        fields = '__all__'
        # ``author`` must be set from request.user by the view, not
        # from the body — otherwise users could impersonate.
        read_only_fields = ('id', 'created_at', 'updated_at', 'author')


class SupportTicketSerializer(serializers.ModelSerializer):
    comments = TicketCommentSerializer(many=True, read_only=True)
    assigned_to_name = serializers.ReadOnlyField(source='assigned_to.username', allow_null=True)
    resolved_by_name = serializers.ReadOnlyField(source='resolved_by.username', allow_null=True)
    tenant_name = serializers.ReadOnlyField(source='requester_tenant.name', allow_null=True)

    class Meta:
        model = SupportTicket
        fields = '__all__'
        # ``requester_tenant`` is the tenant FK on this model. Lock
        # it down with the universal set so a ticket can't be
        # silently transferred. ``resolved_by`` / ``resolved_at``
        # belong to the resolve action, not the create body.
        read_only_fields = (
            'id', 'created_at', 'updated_at',
            'requester_tenant', 'resolved_by', 'resolved_at',
        )

    def create(self, validated_data):
        comments_data = validated_data.pop('comments', [])
        ticket = SupportTicket.objects.create(**validated_data)
        for comment_data in comments_data:
            TicketComment.objects.create(ticket=ticket, **comment_data)
        return ticket


class LanguageConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = LanguageConfig
        fields = '__all__'
        # Platform-wide reference data; lock the audit columns.
        read_only_fields = ('id', 'created_at', 'updated_at')


class CurrencyConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurrencyConfig
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')


class TenantSMTPConfigSerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')

    class Meta:
        model = TenantSMTPConfig
        fields = '__all__'
        # SMTP password stays write-only (existing protection); the
        # universal lock down covers the tenant-rebind attack.
        read_only_fields = _UNIVERSAL_READ_ONLY
        extra_kwargs = {'smtp_password': {'write_only': True}}


class TenantAPIKeySerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')
    created_by_name = serializers.ReadOnlyField(source='created_by.username', allow_null=True)

    class Meta:
        model = TenantAPIKey
        fields = '__all__'
        # API key + secret are generated server-side (kept read-only
        # via extra_kwargs). ``last_used_at`` is system-maintained.
        read_only_fields = _UNIVERSAL_READ_ONLY + ('last_used_at',)
        extra_kwargs = {
            'api_key': {'read_only': True},
            'api_secret': {'read_only': True},
        }


class WebhookConfigSerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')

    class Meta:
        model = WebhookConfig
        fields = '__all__'
        read_only_fields = _UNIVERSAL_READ_ONLY
        extra_kwargs = {'secret_key': {'write_only': True}}


class AnnouncementSerializer(serializers.ModelSerializer):
    created_by_name = serializers.ReadOnlyField(source='created_by.username', allow_null=True)
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = '__all__'
        # Platform-wide announcement — no tenant FK.
        read_only_fields = ('id', 'created_at', 'updated_at', 'created_by')

    def get_is_active(self, obj):
        from django.utils import timezone
        now = timezone.now()
        is_published = obj.is_published
        is_started = obj.starts_at <= now
        is_not_ended = obj.ends_at is None or obj.ends_at >= now
        return is_published and is_started and is_not_ended


class TenantNotificationSerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')

    class Meta:
        model = TenantNotification
        fields = '__all__'
        read_only_fields = _UNIVERSAL_READ_ONLY


class SuperAdminSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SuperAdminSettings
        fields = '__all__'
        # Platform singleton — no tenant FK. Audit fields locked.
        read_only_fields = ('id', 'created_at', 'updated_at')
        extra_kwargs = {'smtp_password': {'write_only': True}}


class ImpersonationLogSerializer(serializers.ModelSerializer):
    superadmin_name = serializers.ReadOnlyField(source='superadmin.username')
    target_user_name = serializers.ReadOnlyField(source='target_user.username')
    target_tenant_name = serializers.ReadOnlyField(source='target_tenant.name')

    class Meta:
        model = ImpersonationLog
        fields = '__all__'
        # **Whole-row read-only** — this is an immutable audit log.
        # Writes happen via the impersonation start/stop service path,
        # never through this serializer. Field names verified against
        # the model on 2026-05-24; if a new field lands on the model,
        # add it here too so it can't be set via the API.
        read_only_fields = (
            'id',
            'superadmin', 'target_user', 'target_tenant',
            'started_at', 'ended_at', 'token_key',
            'ip_address', 'is_active',
        )


class CommissionPayoutSerializer(serializers.ModelSerializer):
    referrer_name = serializers.ReadOnlyField(source='referrer.contact_name')
    created_by_name = serializers.ReadOnlyField(source='created_by.username', allow_null=True)

    class Meta:
        model = CommissionPayout
        fields = '__all__'
        # No tenant FK — referrer is platform-wide. Audit fields locked.
        read_only_fields = ('id', 'created_at', 'updated_at', 'created_by')


class TicketAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.ReadOnlyField(source='uploaded_by.username')

    class Meta:
        model = TicketAttachment
        fields = '__all__'
        # ``uploaded_by`` is set from request.user in the view, not
        # from the request body.
        read_only_fields = ('id', 'created_at', 'updated_at', 'uploaded_by')
        extra_kwargs = {'file': {'required': True}}


class TenantLanguageSettingSerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')
    language_name = serializers.ReadOnlyField(source='language.language_name')

    class Meta:
        model = TenantLanguageSetting
        fields = '__all__'
        read_only_fields = _UNIVERSAL_READ_ONLY


class TenantCurrencySettingSerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')
    currency_name = serializers.ReadOnlyField(source='currency.currency_name')

    class Meta:
        model = TenantCurrencySetting
        fields = '__all__'
        read_only_fields = _UNIVERSAL_READ_ONLY


class WebhookDeliverySerializer(serializers.ModelSerializer):
    webhook_name = serializers.ReadOnlyField(source='webhook.webhook_name')

    class Meta:
        model = WebhookDelivery
        fields = '__all__'
        # Whole-row read-only: WebhookDelivery rows are written by
        # the dispatch worker, never by API clients. Field names
        # verified against the model on 2026-05-24.
        read_only_fields = (
            'id', 'attempted_at', 'delivered_at', 'duration_ms',
            'error_message', 'event', 'payload',
            'response_body', 'retry_attempt', 'status', 'status_code',
            'webhook',
        )


class TenantUsageSerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')

    class Meta:
        model = TenantUsage
        fields = '__all__'
        # Whole-row read-only: usage rows are populated by the daily
        # metering job; admin UI is view-only. Field names verified
        # against the model on 2026-05-24.
        read_only_fields = (
            'id', 'created_at',
            'tenant', 'billing_period_start', 'billing_period_end',
            'users_count', 'storage_mb', 'api_calls',
            'transactions_count', 'is_billed',
            'base_cost', 'overage_api_calls', 'overage_cost',
            'overage_storage_mb', 'overage_users', 'total_cost',
        )


class InvoiceSerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')

    class Meta:
        model = Invoice
        fields = '__all__'
        # ``status`` is driven by payment webhooks and the
        # mark-paid/refund admin actions — never settable on
        # POST/PUT. Same for ``paid_at`` and ``payment_reference``
        # (set on the dedicated payment-confirm endpoint).
        read_only_fields = _UNIVERSAL_READ_ONLY + (
            'status', 'paid_at',
            'payment_reference', 'payment_method',
        )
        extra_kwargs = {'invoice_number': {'read_only': True}}


class SaaSDashboardStatsSerializer(serializers.Serializer):
    total_tenants = serializers.IntegerField()
    active_tenants = serializers.IntegerField()
    total_users = serializers.IntegerField()
    monthly_revenue = serializers.DecimalField(max_digits=15, decimal_places=2)
    monthly_commissions = serializers.DecimalField(max_digits=15, decimal_places=2)
    open_tickets = serializers.IntegerField()
    total_referrers = serializers.IntegerField()
    pending_commissions = serializers.DecimalField(max_digits=15, decimal_places=2)
    tenants_by_plan = serializers.DictField()
    recent_tenants = serializers.ListField()
    recent_tickets = serializers.ListField()
