from django.contrib import admin
from .models import Client, Domain, TenantModule, SubscriptionPlan, TenantSubscription, TenantPayment, UserTenantRole


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['name', 'schema_name', 'created_on']
    search_fields = ['name', 'schema_name']


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ['domain', 'tenant', 'is_primary']
    list_filter = ['is_primary']
    search_fields = ['domain']


@admin.register(UserTenantRole)
class UserTenantRoleAdmin(admin.ModelAdmin):
    list_display = ['user', 'tenant', 'role', 'is_active', 'created_at']
    list_filter = ['role', 'is_active']
    search_fields = ['user__username', 'tenant__name']
    raw_id_fields = ['user', 'tenant']


@admin.register(TenantModule)
class TenantModuleAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'module_name', 'module_title', 'is_active']
    list_filter = ['is_active', 'module_name']
    search_fields = ['tenant__name', 'module_name']


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'plan_type', 'price', 'billing_cycle', 'is_active']
    list_filter = ['plan_type', 'is_active']


@admin.register(TenantSubscription)
class TenantSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'plan', 'status', 'start_date', 'end_date']
    list_filter = ['status']
    search_fields = ['tenant__name']


@admin.register(TenantPayment)
class TenantPaymentAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'amount', 'payment_method', 'status', 'payment_date']
    list_filter = ['status', 'payment_method']
    search_fields = ['tenant__name', 'transaction_reference']
