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

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'tenant-users', TenantUserViewSet, basename='tenant-users')

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
]
