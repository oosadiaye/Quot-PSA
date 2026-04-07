# Backward-compatibility shim — all view classes and functions
# have been moved to core/views/ package.
from core.views import (
    UserViewSet, TenantUserViewSet,
    login_view, jwt_login_view, logout_view, logout,
    select_tenant, my_tenants,
    forgot_password, reset_password_confirm, verify_email, resend_verification_email,
    _get_user_tenants,
    active_sessions, revoke_session, revoke_all_sessions,
    login_history,
    menu_api, api_root, module_list,
    health_check, dashboard_stats,
)

__all__ = [
    'UserViewSet', 'TenantUserViewSet',
    'login_view', 'jwt_login_view', 'logout_view', 'logout',
    'select_tenant', 'my_tenants',
    'forgot_password', 'reset_password_confirm', 'verify_email',
    'resend_verification_email', '_get_user_tenants',
    'active_sessions', 'revoke_session', 'revoke_all_sessions',
    'login_history',
    'menu_api', 'api_root', 'module_list',
    'health_check', 'dashboard_stats',
]
