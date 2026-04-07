"""
Tenant app URL configuration.

Architecture note — two API surfaces exist for tenant management:

1. **Superadmin API** (/api/v1/superadmin/...)
   - Function-based views in superadmin/views.py
   - Used exclusively by the frontend SuperAdmin dashboard
   - Canonical API for all superadmin operations

2. **Tenant API** (/api/v1/tenants/...)  — THIS FILE
   - DRF ViewSets providing RESTful CRUD
   - ViewSets marked DEPRECATED overlap with superadmin endpoints
   - Active (non-deprecated) endpoints:
     * user-roles/ — UserTenantRoleViewSet (unique)
     * roles/ — RoleViewSet (unique, module-based permissions)
     * settings/, company/, email/, payment-methods/, enabled-modules/
       — tenant-facing views used by the tenant dashboard
   - Deprecated ViewSets kept for programmatic/API access:
     * tenants/ — use /superadmin/tenants instead
     * modules/ — use /superadmin/tenants/<id>/modules instead
     * plans/ — use /superadmin/plans instead (create_default_plans action still useful)
     * subscriptions/ — use /superadmin/tenants/<id>/change-plan instead
     * payments/ — superadmin uses /superadmin/payments; tenant receipt upload still used
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TenantViewSet, TenantModuleViewSet, UserTenantRoleViewSet, RoleViewSet,
    SubscriptionPlanViewSet, TenantSubscriptionViewSet,
    TenantPaymentViewSet,
    available_modules, tenant_modules,
    pending_payments_list,
    tenant_settings_api, tenant_company_api, tenant_public_branding_api,
    tenant_branding_api, tenant_email_api, tenant_payment_methods_api,
    tenant_modules_api
)

router = DefaultRouter()
# Active — unique endpoints with no superadmin equivalent
router.register(r'user-roles', UserTenantRoleViewSet, basename='user-tenant-role')
router.register(r'roles', RoleViewSet, basename='tenant-role')

# Deprecated — overlaps with /api/v1/superadmin/ endpoints (see docstring above)
router.register(r'tenants', TenantViewSet, basename='tenant')
router.register(r'modules', TenantModuleViewSet, basename='tenant-module')
router.register(r'plans', SubscriptionPlanViewSet, basename='subscription-plan')
router.register(r'subscriptions', TenantSubscriptionViewSet, basename='tenant-subscription')
router.register(r'payments', TenantPaymentViewSet, basename='tenant-payment')

urlpatterns = [
    # Tenant-facing settings endpoints (used by tenant dashboard, NOT superadmin)
    path('settings/', tenant_settings_api, name='tenant-settings'),
    path('company/', tenant_company_api, name='tenant-company'),
    path('branding/', tenant_branding_api, name='tenant-branding'),
    path('public-branding/', tenant_public_branding_api, name='tenant-public-branding'),
    path('email/', tenant_email_api, name='tenant-email'),
    path('payment-methods/', tenant_payment_methods_api, name='tenant-payment-methods'),
    path('enabled-modules/', tenant_modules_api, name='tenant-enabled-modules'),

    # Router-registered ViewSets
    path('', include(router.urls)),

    # Standalone views
    path('available-modules/', available_modules, name='available-modules'),
    path('tenant-modules/', tenant_modules, name='tenant-modules'),
    path('pending-payments/', pending_payments_list, name='pending-payments'),
]
