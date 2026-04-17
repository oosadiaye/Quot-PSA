import logging

from django.core.cache import caches
from django.http import JsonResponse
from django.utils.translation import activate

LANGUAGE_SESSION_KEY = '_language'
from django_tenants.middleware.main import TenantMainMiddleware
from django_tenants.utils import schema_context
from tenants.models import Domain

from .geolocation import detect_language, get_client_ip

logger = logging.getLogger('security')


def _get_tenant_cache():
    """Get the tenant cache backend (falls back to default)."""
    try:
        return caches['tenant_cache']
    except Exception:
        return caches['default']

# Exact public paths (match only this exact path)
PUBLIC_PATHS_EXACT = {
    '/api/v1/core/auth/login/',
    '/api/v1/core/auth/logout/',
    '/api/v1/core/auth/my-tenants/',
    '/api/v1/core/auth/select-tenant/',
    '/api/v1/core/users/register/',
    '/api/v1/core/users/change_password/',
    '/api/v1/core/auth/forgot-password/',
    '/api/v1/core/auth/reset-password/',
    '/api/v1/core/auth/verify-email/',
    '/api/v1/core/auth/resend-verification/',
    '/api/v1/core/auth/sessions/',
    '/api/v1/core/auth/sessions/revoke/',
    '/api/v1/core/auth/sessions/revoke-all/',
    '/api/v1/core/auth/login-history/',
    '/api/v1/core/health/',
    # Backward compat (unversioned)
    '/api/core/auth/login/',
    '/api/core/auth/logout/',
    '/api/core/auth/my-tenants/',
    '/api/core/auth/select-tenant/',
    '/api/core/users/register/',
    '/api/core/users/change_password/',
    '/api/core/auth/forgot-password/',
    '/api/core/auth/reset-password/',
    '/api/core/auth/verify-email/',
    '/api/core/auth/resend-verification/',
    '/api/core/auth/sessions/',
    '/api/core/auth/sessions/revoke/',
    '/api/core/auth/sessions/revoke-all/',
    '/api/core/auth/login-history/',
    '/api/core/health/',
}

# Prefix public paths (match this prefix and any sub-paths)
PUBLIC_PATHS_PREFIX = (
    '/api/v1/superadmin/',
    '/api/superadmin/',
    '/admin/',
    '/api/v1/core/auth/reset-password/',  # reset-password/<uid>/<token>/
)


def _is_public_path(path):
    """Check if a path is public using exact match or controlled prefix match."""
    if path in PUBLIC_PATHS_EXACT:
        return True
    return any(path.startswith(p) for p in PUBLIC_PATHS_PREFIX)


class TenantHeaderMiddleware(TenantMainMiddleware):
    """Tenant middleware that supports centralized login across all tenants.

    How it works:
    1. Auth endpoints (login, logout, select-tenant) run on the **public**
       schema — no tenant header required.
    2. All other endpoints require an ``X-Tenant-Domain`` header.  The
       middleware resolves the header to a known Domain record and sets
       ``HTTP_HOST`` so django-tenants can activate the correct schema.
    3. After authentication, a second pass (process_view) verifies the
       user actually has access to the resolved tenant via
       ``UserTenantRole``.
    """

    def __init__(self, get_response):
        super().__init__(get_response)
        self.get_response = get_response

    # ------------------------------------------------------------------
    # Override: resolve tenant directly when X-Tenant-Domain is present.
    #
    # django-tenants' TenantMainMiddleware uses request.get_host() which
    # validates the hostname against RFC 1034/1035.  Our internal tenant
    # domain names may contain underscores (e.g. test_farm_corp.dtsg.test)
    # which are technically invalid per the RFC, causing DisallowedHost.
    #
    # Instead of relying on HTTP_HOST rewriting, we resolve the tenant
    # ourselves and hand it directly to connection.set_tenant(), skipping
    # the hostname validation entirely for header-based requests.
    # ------------------------------------------------------------------

    def __call__(self, request):
        path = request.path_info

        # Let public paths pass through without tenant resolution
        if _is_public_path(path):
            return super().__call__(request)

        tenant_domain = request.META.get('HTTP_X_TENANT_DOMAIN')

        if tenant_domain:
            # Phase 2: Cache domain lookups to reduce per-request DB hits
            cache = _get_tenant_cache()
            cache_key = f'domain:{tenant_domain}'
            cached = cache.get(cache_key)

            if cached == '__deleted__':
                return JsonResponse(
                    {'error': 'This organization has been deactivated'},
                    status=403,
                )
            elif cached == '__unknown__':
                return JsonResponse(
                    {'error': 'Unknown tenant domain'},
                    status=400,
                )

            # Resolve domain → tenant (cache-aware)
            if cached == '__valid__':
                # Cache hit — still need to fetch the tenant object for
                # connection.set_tenant().  Use a secondary cache for the
                # schema_name so we can avoid a DB hit on every request.
                schema_key = f'schema:{tenant_domain}'
                schema_name = cache.get(schema_key)
                if schema_name:
                    domain_obj = None  # resolved via schema_name below
                else:
                    domain_obj = Domain.objects.select_related('tenant').filter(domain=tenant_domain).first()
                    if domain_obj:
                        schema_name = domain_obj.tenant.schema_name
                        cache.set(schema_key, schema_name, timeout=900)
            else:
                # Cache miss — query the database
                domain_obj = Domain.objects.select_related('tenant').filter(domain=tenant_domain).first()

                if domain_obj and not getattr(domain_obj.tenant, 'is_deleted', False):
                    cache.set(cache_key, '__valid__', timeout=900)  # 15 min
                    schema_name = domain_obj.tenant.schema_name
                    cache.set(f'schema:{tenant_domain}', schema_name, timeout=900)
                elif domain_obj and getattr(domain_obj.tenant, 'is_deleted', False):
                    cache.set(cache_key, '__deleted__', timeout=300)  # 5 min
                    return JsonResponse(
                        {'error': 'This organization has been deactivated'},
                        status=403,
                    )
                else:
                    logger.warning(
                        'Rejected unknown tenant domain=%s ip=%s path=%s',
                        tenant_domain,
                        request.META.get('REMOTE_ADDR', 'unknown'),
                        path,
                    )
                    cache.set(cache_key, '__unknown__', timeout=60)
                    return JsonResponse(
                        {'error': 'Unknown tenant domain'},
                        status=400,
                    )

            # Directly activate the tenant on the DB connection, bypassing
            # TenantMainMiddleware's hostname-based resolution entirely.
            from django.db import connection as db_connection
            from tenants.models import Client

            db_connection.set_schema_to_public()
            try:
                if domain_obj:
                    tenant = domain_obj.tenant
                else:
                    tenant = Client.objects.get(schema_name=schema_name)
                tenant.domain_url = tenant_domain
                request.tenant = tenant
                db_connection.set_tenant(tenant)
                self.setup_url_routing(request)
            except Client.DoesNotExist:
                cache.delete(cache_key)
                cache.delete(f'schema:{tenant_domain}')
                return JsonResponse({'error': 'Unknown tenant domain'}, status=400)

            # Continue to the next middleware / view
            return self.get_response(request)

        # No X-Tenant-Domain header — fall through to normal
        # TenantMainMiddleware hostname-based resolution (for direct
        # domain access, admin, etc.)
        return super().__call__(request)


class TenantAccessMiddleware:
    """Validates that the authenticated user has access to the current tenant.

    Must be placed **after** ``TenantHeaderMiddleware`` and
    ``AuthenticationMiddleware`` in the middleware stack.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info

        if _is_public_path(path):
            return self.get_response(request)

        user = getattr(request, 'user', None)
        tenant = getattr(request, 'tenant', None)

        if user and user.is_authenticated and tenant:
            if not user.is_superuser:
                from tenants.models import UserTenantRole, TenantSubscription

                # Phase 2: Cache access checks to reduce per-request DB hits
                cache = _get_tenant_cache()
                access_key = f'access:{user.pk}:{tenant.schema_name}'
                cached_access = cache.get(access_key)

                if cached_access is None:
                    # Cache miss — query the database
                    with schema_context('public'):
                        has_access = UserTenantRole.objects.filter(
                            user=user, tenant=tenant, is_active=True
                        ).exists()
                    cache.set(access_key, has_access, timeout=600)  # 10 min
                else:
                    has_access = cached_access

                if not has_access:
                    logger.warning(
                        'Tenant access denied user_id=%s tenant=%s ip=%s',
                        user.pk,
                        tenant.schema_name,
                        request.META.get('REMOTE_ADDR', 'unknown'),
                    )
                    return JsonResponse(
                        {'error': 'You do not have access to this tenant'},
                        status=403,
                    )

                # Phase 2: Cache subscription status check
                sub_key = f'sub_status:{tenant.schema_name}'
                cached_sub = cache.get(sub_key)

                if cached_sub is None:
                    with schema_context('public'):
                        try:
                            sub = TenantSubscription.objects.get(tenant=tenant)
                            sub_status = sub.status
                        except TenantSubscription.DoesNotExist:
                            sub_status = 'active'  # Allow if no subscription
                    cache.set(sub_key, sub_status, timeout=300)  # 5 min
                else:
                    sub_status = cached_sub

                if sub_status in ('suspended', 'expired', 'cancelled'):
                    logger.warning(
                        'Tenant subscription %s user_id=%s tenant=%s',
                        sub_status, user.pk, tenant.schema_name,
                    )
                    return JsonResponse(
                        {'error': f'Tenant subscription is {sub_status}. Please contact support.'},
                        status=403,
                    )

        return self.get_response(request)


class LanguageDetectionMiddleware:
    """
    Middleware to detect and set the request language based on:
    1. User's saved preference
    2. Session preference
    3. Cookie preference
    4. IP geolocation
    5. Email domain
    6. Browser Accept-Language header
    7. Default language
    """

    # Paths that should not have language detection
    EXEMPT_PATHS = (
        '/admin/',
        '/static/',
        '/media/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info

        # Skip language detection for exempt paths
        if any(path.startswith(p) for p in self.EXEMPT_PATHS):
            return self.get_response(request)

        # Get user if authenticated
        user = getattr(request, 'user', None)

        # Detect language from multiple sources
        language = detect_language(request, user)

        # Store detected language in request for later use
        request.detected_language = language

        # Activate the language for this request
        activate(language)

        # Store in session if available
        if hasattr(request, 'session'):
            request.session[LANGUAGE_SESSION_KEY] = language

        # Set response language header
        response = self.get_response(request)

        # Add detected language to response headers
        response['X-Detected-Language'] = language

        # Add country info if available
        ip = get_client_ip(request)
        if ip and not self._is_local_ip(ip):
            from .geolocation import get_country_from_ip
            country = get_country_from_ip(ip)
            if country:
                response['X-Detected-Country'] = country

        return response

    def _is_local_ip(self, ip: str) -> bool:
        """Check if IP is local/private."""
        if not ip:
            return True
        return (
            ip.startswith('127.') or
            ip.startswith('10.') or
            ip.startswith('192.168.') or
            ip.startswith('172.16.') or
            ip == '::1' or
            ip == 'localhost'
        )


class ForceDefaultLanguageMiddleware:
    """
    Middleware to force default language when explicitly requested.
    Used for API endpoints that should always return in English.
    """

    # Paths that should always use default language
    DEFAULT_LANGUAGE_PATHS = (
        '/api/v1/core/health/',
        '/api/v1/superadmin/saas-stats',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info

        # Force English for specified paths
        if any(path.startswith(p) for p in self.DEFAULT_LANGUAGE_PATHS):
            activate('en')
            request.force_language = 'en'

        return self.get_response(request)


# ── Organization Middleware ────────────────────────────────────────

class OrganizationMiddleware:
    """
    Resolves the active Organization for the current request.

    Must come AFTER ``TenantAccessMiddleware`` so ``request.tenant`` and
    ``request.user`` are both available.

    Reads the active org from:
    1. ``X-Organization-Id`` request header (primary, from frontend)
    2. ``session['active_organization_id']`` (fallback, from switch API)

    Sets on ``request``:
    - ``mda_isolation_mode``  — 'UNIFIED' or 'SEPARATED'
    - ``organization``        — Organization instance or None
    """

    # Paths that skip org resolution (public, auth, health)
    SKIP_PATHS = ('/api/v1/auth/', '/health/', '/admin/', '/__debug__/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Default: no org context
        request.mda_isolation_mode = 'UNIFIED'
        request.organization = None

        # Skip for unauthenticated or non-API requests
        if not hasattr(request, 'tenant') or not hasattr(request, 'user'):
            return self.get_response(request)

        if any(request.path_info.startswith(p) for p in self.SKIP_PATHS):
            return self.get_response(request)

        if not request.user.is_authenticated:
            return self.get_response(request)

        # Read tenant isolation mode
        tenant = getattr(request, 'tenant', None)
        if tenant:
            request.mda_isolation_mode = getattr(
                tenant, 'mda_isolation_mode', 'UNIFIED',
            )

        # Resolve active organization from header or session
        org_id = (
            request.headers.get('X-Organization-Id')
            or request.session.get('active_organization_id')
        )
        if org_id:
            try:
                from core.models import UserOrganization
                org_id = int(org_id)
                # Validate user is assigned to this org
                assignment = UserOrganization.objects.select_related(
                    'organization',
                    'organization__administrative_segment',
                    'organization__legacy_mda',
                ).filter(
                    user=request.user,
                    organization_id=org_id,
                    organization__is_active=True,
                    is_active=True,
                ).first()
                if assignment:
                    request.organization = assignment.organization
            except (ValueError, TypeError):
                pass

        return self.get_response(request)
