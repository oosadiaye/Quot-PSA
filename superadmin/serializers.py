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
    SubscriptionPlan, Subscription, SuperAdminSettings, ImpersonationLog,
    TenantUsage, Invoice,
)


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = '__all__'


class SubscriptionSerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')
    plan_name = serializers.ReadOnlyField(source='plan.name')
    
    class Meta:
        model = Subscription
        fields = '__all__'


class ReferrerSerializer(serializers.ModelSerializer):
    total_referrals = serializers.SerializerMethodField()
    total_commission = serializers.SerializerMethodField()
    pending_commission = serializers.SerializerMethodField()
    
    class Meta:
        model = Referrer
        fields = '__all__'
    
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


class CommissionSerializer(serializers.ModelSerializer):
    referrer_name = serializers.ReadOnlyField(source='referrer.contact_name')
    tenant_name = serializers.ReadOnlyField(source='tenant.name')
    referral_status = serializers.ReadOnlyField(source='referral.status')
    
    class Meta:
        model = Commission
        fields = '__all__'


class TicketCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.ReadOnlyField(source='author.username')
    
    class Meta:
        model = TicketComment
        fields = '__all__'


class SupportTicketSerializer(serializers.ModelSerializer):
    comments = TicketCommentSerializer(many=True, read_only=True)
    assigned_to_name = serializers.ReadOnlyField(source='assigned_to.username', allow_null=True)
    resolved_by_name = serializers.ReadOnlyField(source='resolved_by.username', allow_null=True)
    tenant_name = serializers.ReadOnlyField(source='requester_tenant.name', allow_null=True)
    
    class Meta:
        model = SupportTicket
        fields = '__all__'
    
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


class CurrencyConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurrencyConfig
        fields = '__all__'


class TenantSMTPConfigSerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')
    
    class Meta:
        model = TenantSMTPConfig
        fields = '__all__'
        extra_kwargs = {'smtp_password': {'write_only': True}}


class TenantAPIKeySerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')
    created_by_name = serializers.ReadOnlyField(source='created_by.username', allow_null=True)

    class Meta:
        model = TenantAPIKey
        fields = '__all__'
        extra_kwargs = {
            'api_key': {'read_only': True},
            'api_secret': {'read_only': True},
        }


class WebhookConfigSerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')
    
    class Meta:
        model = WebhookConfig
        fields = '__all__'
        extra_kwargs = {'secret_key': {'write_only': True}}


class AnnouncementSerializer(serializers.ModelSerializer):
    created_by_name = serializers.ReadOnlyField(source='created_by.username', allow_null=True)
    is_active = serializers.SerializerMethodField()
    
    class Meta:
        model = Announcement
        fields = '__all__'
    
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


class SuperAdminSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SuperAdminSettings
        fields = '__all__'
        extra_kwargs = {'smtp_password': {'write_only': True}}


class ImpersonationLogSerializer(serializers.ModelSerializer):
    superadmin_name = serializers.ReadOnlyField(source='superadmin.username')
    target_user_name = serializers.ReadOnlyField(source='target_user.username')
    target_tenant_name = serializers.ReadOnlyField(source='target_tenant.name')
    
    class Meta:
        model = ImpersonationLog
        fields = '__all__'


class CommissionPayoutSerializer(serializers.ModelSerializer):
    referrer_name = serializers.ReadOnlyField(source='referrer.contact_name')
    created_by_name = serializers.ReadOnlyField(source='created_by.username', allow_null=True)

    class Meta:
        model = CommissionPayout
        fields = '__all__'


class TicketAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.ReadOnlyField(source='uploaded_by.username')

    class Meta:
        model = TicketAttachment
        fields = '__all__'
        extra_kwargs = {'file': {'required': True}}


class TenantLanguageSettingSerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')
    language_name = serializers.ReadOnlyField(source='language.language_name')

    class Meta:
        model = TenantLanguageSetting
        fields = '__all__'


class TenantCurrencySettingSerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')
    currency_name = serializers.ReadOnlyField(source='currency.currency_name')

    class Meta:
        model = TenantCurrencySetting
        fields = '__all__'


class WebhookDeliverySerializer(serializers.ModelSerializer):
    webhook_name = serializers.ReadOnlyField(source='webhook.webhook_name')

    class Meta:
        model = WebhookDelivery
        fields = '__all__'


class TenantUsageSerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')

    class Meta:
        model = TenantUsage
        fields = '__all__'


class InvoiceSerializer(serializers.ModelSerializer):
    tenant_name = serializers.ReadOnlyField(source='tenant.name')

    class Meta:
        model = Invoice
        fields = '__all__'
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
