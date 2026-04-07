from rest_framework import serializers
from .models import Client, Domain, TenantModule, TenantSubscription, SubscriptionPlan, AVAILABLE_MODULES, TenantPayment, UserTenantRole, Role
# Per-tenant schema models (live in each tenant's own PostgreSQL schema)
from core.models import TenantModule as PerTenantModule, Role as PerTenantRole


class DomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = Domain
        fields = ['id', 'domain', 'is_primary']


class TenantSerializer(serializers.ModelSerializer):
    domains = DomainSerializer(many=True, read_only=True)
    subscription_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Client
        fields = ['id', 'name', 'schema_name', 'created_on', 'domains', 'subscription_status']
    
    def get_subscription_status(self, obj):
        try:
            sub = obj.subscription
            return {
                'status': sub.status,
                'plan': sub.plan.name if sub.plan else None,
                'end_date': sub.end_date
            }
        except:
            return {'status': 'none', 'plan': None, 'end_date': None}


class TenantModuleSerializer(serializers.ModelSerializer):
    """Serializer for per-tenant TenantModule (core.TenantModule — no tenant FK)."""

    class Meta:
        model = PerTenantModule
        fields = ['id', 'module_name', 'module_title', 'description', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    module_names = serializers.SerializerMethodField()
    
    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'plan_type', 'description', 'price', 'billing_cycle',
                  'max_users', 'max_storage_gb', 'allowed_modules', 'features', 'module_names',
                  'is_active', 'is_featured', 'trial_days', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']
    
    def get_module_names(self, obj):
        module_dict = {key: title for key, title, _desc in AVAILABLE_MODULES}
        return [module_dict.get(m, m) for m in obj.allowed_modules]


class SubscriptionPlanListSerializer(serializers.ModelSerializer):
    """Simplified serializer for list view"""
    display_price = serializers.SerializerMethodField()
    modules_count = serializers.SerializerMethodField()
    
    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'plan_type', 'price', 'billing_cycle', 
                  'max_users', 'is_active', 'is_featured', 'display_price', 'modules_count']
    
    def get_display_price(self, obj):
        return f"${obj.price}/{obj.get_billing_cycle_display()}"
    
    def get_modules_count(self, obj):
        return len(obj.allowed_modules)


class TenantSubscriptionSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    
    class Meta:
        model = TenantSubscription
        fields = ['id', 'tenant', 'tenant_name', 'plan', 'plan_name', 'status', 
                  'start_date', 'end_date', 'auto_renew', 'payment_method',
                  'last_payment_date', 'next_billing_date', 'notes', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class AssignPlanSerializer(serializers.Serializer):
    """Serializer for assigning a plan to a tenant"""
    tenant_id = serializers.IntegerField()
    plan_id = serializers.IntegerField()
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    auto_renew = serializers.BooleanField(default=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class ModuleActivationSerializer(serializers.Serializer):
    """Serializer for bulk updating module activations"""
    tenant_id = serializers.IntegerField()
    modules = serializers.DictField(
        child=serializers.BooleanField()
    )


class AvailableModuleSerializer(serializers.Serializer):
    """Serializer for listing available modules"""
    name = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()


class TenantPaymentSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.username', read_only=True)
    
    class Meta:
        model = TenantPayment
        fields = ['id', 'tenant', 'tenant_name', 'subscription', 'amount', 'currency',
                  'payment_method', 'bank_name', 'account_number', 'transaction_reference',
                  'payment_date', 'receipt_document', 'receipt_filename', 'status',
                  'approved_by', 'approved_by_name', 'approved_date', 'approval_notes',
                  'notes', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at', 'status', 'approved_by', 'approved_date']


class TenantPaymentCreateSerializer(serializers.Serializer):
    """Serializer for tenants to create payment records"""
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField(max_length=3, default='NGN')
    payment_method = serializers.ChoiceField(choices=TenantPayment.PAYMENT_METHOD_CHOICES)
    bank_name = serializers.CharField(max_length=100)
    account_number = serializers.CharField(max_length=20)
    transaction_reference = serializers.CharField(max_length=100)
    payment_date = serializers.DateField()
    receipt = serializers.FileField(required=False, allow_null=True)


class PaymentApprovalSerializer(serializers.Serializer):
    """Serializer for approving/rejecting payments"""
    payment_id = serializers.IntegerField()
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    notes = serializers.CharField(required=False, allow_blank=True)


class UserTenantRoleSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)

    class Meta:
        model = UserTenantRole
        fields = [
            'id', 'user', 'username', 'tenant', 'tenant_name',
            'role', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class RoleSerializer(serializers.ModelSerializer):
    """Serializer for per-tenant Role (core.Role — no tenant FK)."""
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = PerTenantRole
        fields = [
            'id', 'name', 'code', 'module', 'role_type',
            'can_view', 'can_add', 'can_change', 'can_delete', 'can_approve', 'can_post',
            'is_active', 'is_default', 'permissions', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at', 'permissions']

    def get_permissions(self, obj):
        return obj.get_permissions()
