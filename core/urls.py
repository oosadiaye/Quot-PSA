from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from .views import (
    UserViewSet, TenantUserViewSet, menu_api, api_root, module_list,
    login_view, jwt_login_view, logout_view, select_tenant, my_tenants, health_check,
    forgot_password, reset_password_confirm,
    verify_email, resend_verification_email,
    active_sessions, revoke_session, revoke_all_sessions,
    login_history, dashboard_stats,
    setup_profile, complete_setup,
)
from .views.organization import (
    OrganizationListCreate, OrganizationDetail,
    my_organizations, switch_organization, OrganizationUsers,
    sync_from_ncoa,
)
from .views.audit import AuditLogListView
from .views.notifications import NotificationViewSet
# S6-04 — MFA endpoints.
from .views.mfa import (
    MFAEnrollView as _mfa_enroll_cls,
    MFAVerifyEnrollView as _mfa_verify_enroll_cls,
    MFAVerifyView as _mfa_verify_cls,
    MFADisableView as _mfa_disable_cls,
    MFAStatusView as _mfa_status_cls,
)
_mfa_enroll        = _mfa_enroll_cls.as_view()
_mfa_verify_enroll = _mfa_verify_enroll_cls.as_view()
_mfa_verify        = _mfa_verify_cls.as_view()
_mfa_disable       = _mfa_disable_cls.as_view()
_mfa_status        = _mfa_status_cls.as_view()

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'notifications', NotificationViewSet, basename='notifications')
router.register(r'tenant-users', TenantUserViewSet, basename='tenant-users')

# S23 — Role & Permission management.
from .views.roles import RoleViewSet  # noqa: E402
router.register(r'roles', RoleViewSet, basename='role')

# S24 — User↔Role assignments with SOD pre-check.
from .views.role_assignments import RoleAssignmentViewSet  # noqa: E402
router.register(r'role-assignments', RoleAssignmentViewSet, basename='role-assignment')

urlpatterns = [
    path('', include(router.urls)),
    path('menu/', menu_api, name='menu-api'),
    path('', api_root, name='api-root'),
    path('modules/', module_list, name='module-list'),
    # JWT Authentication
    path('auth/token/', jwt_login_view, name='jwt_login'),
    path('auth/token/pair/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    # Standard Authentication
    path('auth/login/', login_view, name='login'),
    path('auth/logout/', logout_view, name='logout'),
    path('auth/select-tenant/', select_tenant, name='select-tenant'),
    path('auth/my-tenants/', my_tenants, name='my-tenants'),
    path('auth/forgot-password/', forgot_password, name='forgot-password'),
    path('auth/reset-password/', reset_password_confirm, name='reset-password'),
    # ── S6-04 — Multi-Factor Authentication (TOTP) ────────────────────
    path('auth/mfa/enroll/',        _mfa_enroll,        name='mfa-enroll'),
    path('auth/mfa/verify-enroll/', _mfa_verify_enroll, name='mfa-verify-enroll'),
    path('auth/mfa/verify/',        _mfa_verify,        name='mfa-verify'),
    path('auth/mfa/disable/',       _mfa_disable,       name='mfa-disable'),
    path('auth/mfa/status/',        _mfa_status,        name='mfa-status'),
    # Email verification
    path('auth/verify-email/', verify_email, name='verify-email'),
    path('auth/resend-verification/', resend_verification_email, name='resend-verification'),
    # Session management
    path('auth/sessions/', active_sessions, name='active-sessions'),
    path('auth/sessions/revoke/', revoke_session, name='revoke-session'),
    path('auth/sessions/revoke-all/', revoke_all_sessions, name='revoke-all-sessions'),
    # Login history
    path('auth/login-history/', login_history, name='login-history'),
    # Health check
    path('health/', health_check, name='health-check'),
    # Dashboard KPI stats
    path('dashboard-stats/', dashboard_stats, name='dashboard-stats'),
    # Setup wizard
    path('setup/profile/', setup_profile, name='setup-profile'),
    path('setup/complete/', complete_setup, name='setup-complete'),
    # Organization (MDA-as-Branch)
    path('organizations/', OrganizationListCreate.as_view(), name='org-list-create'),
    path('organizations/<int:pk>/', OrganizationDetail.as_view(), name='org-detail'),
    path('organizations/my/', my_organizations, name='org-my'),
    path('organizations/switch/', switch_organization, name='org-switch'),
    path('organizations/<int:org_id>/users/', OrganizationUsers.as_view(), name='org-users'),
    path('organizations/sync-from-ncoa/', sync_from_ncoa, name='org-sync-from-ncoa'),
    # Audit Trail
    path('audit-trail/', AuditLogListView.as_view(), name='audit-trail'),
]
