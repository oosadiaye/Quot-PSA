# Views package — re-exports everything needed by core/urls.py.
from core.views.auth import (
    LoginRateThrottle,
    SignupRateThrottle,
    login_view,
    jwt_login_view,
    logout_view,
    logout,
    select_tenant,
    my_tenants,
    forgot_password,
    reset_password_confirm,
    verify_email,
    resend_verification_email,
    active_sessions,
    revoke_session,
    revoke_all_sessions,
    login_history,
    _get_user_tenants,
)
from core.views.user import UserViewSet
from core.views.tenant_user import TenantUserViewSet
from core.views.misc import (
    menu_api,
    api_root,
    module_list,
    health_check,
    dashboard_stats,
)
from core.views.setup import setup_profile, complete_setup

__all__ = [
    # Throttle classes
    'LoginRateThrottle',
    'SignupRateThrottle',
    # Auth views
    'login_view',
    'jwt_login_view',
    'logout_view',
    'logout',
    'select_tenant',
    'my_tenants',
    'forgot_password',
    'reset_password_confirm',
    'verify_email',
    'resend_verification_email',
    'active_sessions',
    'revoke_session',
    'revoke_all_sessions',
    'login_history',
    '_get_user_tenants',
    # ViewSets
    'UserViewSet',
    'TenantUserViewSet',
    # Misc views
    'menu_api',
    'api_root',
    'module_list',
    'health_check',
    'dashboard_stats',
    # Setup wizard
    'setup_profile',
    'complete_setup',
]
