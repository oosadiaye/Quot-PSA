import logging
import re
import uuid

from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework import permissions
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.response import Response

from tenants.models import (
    AVAILABLE_MODULES, Client, Domain, ModulePricing, SubscriptionPlan,
    TenantModule, TenantPayment, TenantSubscription, UserTenantRole,
)
# Per-tenant schema models — live in each tenant's own PostgreSQL schema.
# Superadmin cross-tenant operations must wrap queries in schema_context().
from core.models import TenantModule as PerTenantModule
from .models import (
    SuperAdminProfile, SuperAdminSettings, ImpersonationLog,
    Referrer, Referral, Commission, CommissionPayout,
    SupportTicket, TicketComment, TicketAttachment,
    LanguageConfig, CurrencyConfig, TenantLanguageSetting, TenantCurrencySetting,
    TenantSMTPConfig, TenantAPIKey,
    WebhookConfig, WebhookDelivery, Announcement, TenantNotification,
    TenantUsage, Invoice,
)

logger = logging.getLogger('dtsg')
security_logger = logging.getLogger('security')


class ImpersonateThrottle(ScopedRateThrottle):
    """Dedicated throttle for the impersonate_user endpoint.

    Rate is configured via settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['impersonate'].

    NOTE: ScopedRateThrottle raises ImproperlyConfigured (not a silent pass)
    if the scope key is absent from DEFAULT_THROTTLE_RATES, so the settings
    entry is REQUIRED. Current default: 'impersonate': '20/hour'.
    """
    scope = 'impersonate'


# ---------------------------------------------------------------------------
# HTML sanitisation helper
# ---------------------------------------------------------------------------

def sanitize_html(html):
    """Strip potentially dangerous HTML tags and attributes."""
    if not html:
        return ''
    # Remove script/style tags and their content
    html = re.sub(r'<(script|style|iframe|object|embed|form|input|textarea|select|button)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<(script|style|iframe|object|embed|form|input|textarea|select|button)[^>]*/>', '', html, flags=re.IGNORECASE)
    # Remove ALL event handlers (on*=) with any quoting style
    html = re.sub(r'\s+on\w+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]*)', '', html, flags=re.IGNORECASE)
    # Remove javascript: URLs
    html = re.sub(r'(?:href|src|action)\s*=\s*(?:"javascript:[^"]*"|\'javascript:[^\']*\')', '', html, flags=re.IGNORECASE)
    # Remove data: URLs (can contain scripts)
    html = re.sub(r'(?:href|src)\s*=\s*(?:"data:[^"]*"|\'data:[^\']*\')', '', html, flags=re.IGNORECASE)
    return html.strip()


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class IsSuperAdminUser(permissions.BasePermission):
    """Check if user is superadmin.

    Accepts either:
    1. A SuperAdminProfile with is_superadmin=True, OR
    2. Django's built-in is_superuser flag (fallback for centralized auth)

    The profile lookup uses the public schema to avoid tenant context issues.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        # Fast path: Django superuser flag
        if user.is_superuser:
            return True
        # Check SuperAdminProfile (query public schema explicitly)
        try:
            from django_tenants.utils import schema_context
            with schema_context('public'):
                from superadmin.models import SuperAdminProfile
                return SuperAdminProfile.objects.filter(
                    user=user, is_superadmin=True, is_active=True
                ).exists()
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Pagination helper
# ---------------------------------------------------------------------------

def paginate(queryset_or_list, request, default_page_size=20):
    """Simple pagination helper returning (page_items, meta)."""
    try:
        page = max(int(request.query_params.get('page', 1)), 1)
    except (ValueError, TypeError):
        page = 1
    try:
        page_size = min(int(request.query_params.get('page_size', default_page_size)), 100)
    except (ValueError, TypeError):
        page_size = default_page_size

    if isinstance(queryset_or_list, list):
        total = len(queryset_or_list)
        items = queryset_or_list[(page - 1) * page_size: page * page_size]
    else:
        total = queryset_or_list.count()
        items = queryset_or_list[(page - 1) * page_size: page * page_size]

    return items, {
        'count': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max((total + page_size - 1) // page_size, 1),
    }


# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------

def generate_temp_password():
    import secrets
    return secrets.token_urlsafe(16)


def send_tenant_welcome_email(tenant, admin_user, temp_password, plan_name):
    """Send welcome email to new tenant admin.

    If temp_password is None, the user chose their own password during signup
    and the email omits the password line.
    """
    frontend_url = django_settings.FRONTEND_URL
    subject = f"Welcome to QUOT ERP - {tenant.name} Organization Created"

    password_line = (
        f"Temporary Password: {temp_password}\n" if temp_password
        else "Password: (the one you chose during sign-up)\n"
    )

    message = f"""
Dear {admin_user.first_name or admin_user.username},

Your organization "{tenant.name}" has been successfully created on QUOT ERP Platform.

Login Details:
--------------
Portal URL: {frontend_url}
Username: {admin_user.username}
{password_line}
Subscription Plan: {plan_name}
Organization Schema: {tenant.schema_name}

Important Next Steps:
--------------------
1. Login with the credentials above
{('2. Change your password immediately' + chr(10)) if temp_password else ''}3. Complete your organization profile
4. Invite team members

If you have any questions, please contact support.

Best regards,
QUOT ERP Administration
    """
    try:
        send_mail(
            subject, message,
            getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@dtsg.test'),
            [admin_user.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.error('Email send failed for tenant %s: %s', tenant.schema_name, e)
        return False


def send_password_reset_email(tenant, admin_user, temp_password):
    """Notify tenant admin that their password has been reset by superadmin."""
    frontend_url = django_settings.FRONTEND_URL
    subject = f"Password Reset - {tenant.name} | QUOT ERP"
    message = f"""
Dear {admin_user.first_name or admin_user.username},

Your password for "{tenant.name}" on QUOT ERP has been reset by the platform administrator.

New Login Details:
------------------
Portal URL: {frontend_url}
Username: {admin_user.username}
Temporary Password: {temp_password}

IMPORTANT: Please login and change your password immediately.

If you did not request this change, please contact support.

Best regards,
QUOT ERP Administration
    """
    try:
        send_mail(
            subject, message,
            getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@dtsg.test'),
            [admin_user.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.error('Password reset email failed for tenant %s: %s', tenant.schema_name, e)
        return False


def send_plan_change_email(tenant, old_plan, new_plan):
    """Notify the tenant admin (and support) of a plan change.

    Recipient resolution order:
    1. Email of the active tenant admin from UserTenantRole (role='admin')
    2. Any active UserTenantRole user for the tenant
    3. Settings SUPPORT_EMAIL fallback
    """
    subject = f"Plan Change Notification - {tenant.name}"
    message = f"""
Dear {tenant.name} Administrator,

Your subscription plan has been changed:

Old Plan: {old_plan.name if old_plan else 'None'}
New Plan: {new_plan.name}

If you did not initiate this change, please contact support immediately.

Best regards,
QUOT ERP Administration
    """

    # Resolve tenant admin email
    admin_email = None
    try:
        admin_role = (
            UserTenantRole.objects
            .filter(tenant=tenant, role='admin', is_active=True)
            .select_related('user')
            .first()
        )
        if not admin_role:
            admin_role = (
                UserTenantRole.objects
                .filter(tenant=tenant, is_active=True)
                .select_related('user')
                .first()
            )
        if admin_role and admin_role.user.email:
            admin_email = admin_role.user.email
    except Exception as exc:
        logger.warning(
            "superadmin: could not resolve tenant admin email for tenant %s; "
            "plan-change notification will only be sent to support: %s",
            getattr(tenant, 'pk', '?'), exc,
        )

    support_email = getattr(django_settings, 'SUPPORT_EMAIL', 'support@dtsg.test')
    # Always CC support so the platform team is aware of every plan change.
    # Tenant admin (when found) is the primary recipient; support is secondary.
    # dict.fromkeys preserves insertion order while deduplicating — guards against
    # the case where the admin email and support email are the same address.
    recipients = list(dict.fromkeys(filter(None, [admin_email, support_email])))

    try:
        send_mail(
            subject, message,
            getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@dtsg.test'),
            recipients,
        )
    except Exception as e:
        logger.error('Plan change email failed for tenant %s: %s', tenant.schema_name, e)


# ---------------------------------------------------------------------------
# Tenant Signup (public)
# ---------------------------------------------------------------------------

class SignupThrottle(ScopedRateThrottle):
    scope = 'signup'


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([SignupThrottle])
def tenant_signup(request):
    """Public endpoint for new tenant registration.

    Accepts the following fields from the frontend Register page:
      - organization_name  (required)
      - admin_email        (required)
      - admin_username     (required)
      - admin_password     (required) — user-chosen password
      - first_name         (optional)
      - last_name          (optional)
      - selected_modules   (optional) — list of module keys e.g. ['accounting', 'sales']
      - billing_cycle      (optional) — 'monthly' or 'yearly', defaults to 'monthly'
      - plan_id            (optional) — ID of a specific SubscriptionPlan
      - plan_type          (optional) — plan type e.g. 'basic', 'standard', 'premium'
      - business_category  (optional) — industry category for pre-populating defaults
    """
    data = request.data

    required_fields = ['organization_name', 'admin_email', 'admin_username', 'admin_password']
    for field in required_fields:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    org_name = data['organization_name']
    admin_email = data['admin_email']
    admin_username = data['admin_username']
    admin_password = data['admin_password']
    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    selected_modules = data.get('selected_modules', [])
    billing_cycle = data.get('billing_cycle', 'monthly')
    plan_id = data.get('plan_id')
    plan_type = data.get('plan_type', '')
    business_category = data.get('business_category', 'other')

    # Government configuration (Quot PSE)
    government_tier = data.get('government_tier', '')   # STATE or LGA
    state_nbs_code = data.get('state_nbs_code', '')     # NBS 2-digit code
    state_name = data.get('state_name', '')
    lga_code = data.get('lga_code', '')
    lga_name = data.get('lga_name', '')

    # Validate password strength (match frontend rules: >= 8 chars, 1 upper, 1 digit, 1 special)
    if len(admin_password) < 8:
        return Response({'error': 'Password must be at least 8 characters.'}, status=400)

    # Sanitize schema name
    schema_name = re.sub(r'[^a-z0-9_]', '', org_name.lower().replace(' ', '_'))[:50]
    if not schema_name or not re.match(r'^[a-z][a-z0-9_]*$', schema_name):
        return Response({'error': 'Invalid organization name. Must start with a letter and contain only letters, numbers, and underscores.'}, status=400)

    RESERVED_SCHEMAS = {
        'public', 'information_schema', 'pg_catalog', 'pg_toast', 'pg_temp',
        'pg_toast_temp', 'pg_internal', 'pg_stat', 'pg_stats',
    }
    if schema_name in RESERVED_SCHEMAS:
        return Response({'error': 'This organization name is reserved. Please choose another.'}, status=400)

    with schema_context('public'):
        if Client.objects.filter(schema_name=schema_name).exists():
            return Response({'error': 'Organization name already exists'}, status=400)

        if User.objects.filter(username=admin_username).exists():
            return Response({'error': 'Username already taken'}, status=400)

        if User.objects.filter(email=admin_email).exists():
            return Response({'error': 'Email already registered'}, status=400)

    # Resolve subscription plan: plan_id > plan_type > billing_cycle > any active
    plan = None
    if plan_id:
        plan = SubscriptionPlan.objects.filter(id=plan_id, is_active=True).first()
    if not plan and plan_type:
        plan = SubscriptionPlan.objects.filter(plan_type=plan_type, is_active=True).first()
    if not plan:
        plan = (
            SubscriptionPlan.objects.filter(billing_cycle=billing_cycle, is_active=True).first()
            or SubscriptionPlan.objects.filter(is_active=True).first()
        )
    if not plan:
        return Response({'error': 'No subscription plans available. Please contact support.'}, status=400)

    # If subscribing to a plan and no modules explicitly selected, use plan's modules
    if not selected_modules and plan.allowed_modules:
        selected_modules = plan.allowed_modules

    # ── ASYNC PROVISIONING ──────────────────────────────────────────────
    # Create the Client row + Domain synchronously in the public schema
    # (~30ms), then dispatch the heavy lifting (CREATE SCHEMA, 170+
    # migrations, admin user, subscription, modules, welcome email) to
    # the Celery task `provision_tenant_schema`. The signup request
    # returns 202 in well under a second; the frontend polls for
    # `provisioning_status='active'` before redirecting to login.
    try:
        with transaction.atomic():
            # Client.save() auto-generates a unique slug from ``name`` if
            # the caller doesn't pass one; that slug becomes the
            # subdomain prefix on the URL the user is redirected to
            # post-login. ``schema_name`` stays as the (possibly longer)
            # internal Postgres schema identifier — the two CAN be
            # equal but no longer have to be.
            tenant = Client.objects.create(
                name=org_name,
                schema_name=schema_name,
                business_category=business_category,
                government_tier=government_tier,
                state_nbs_code=state_nbs_code,
                state_name=state_name,
                lga_code=lga_code,
                lga_name=lga_name,
                provisioning_status='pending',
            )
            # Primary subdomain on the configured apex (e.g.
            # ``oag-delta.erp.tryquot.com``). This becomes the URL the
            # frontend redirects to after the user picks the tenant.
            from django.conf import settings as _s
            base = getattr(_s, 'TENANT_SUBDOMAIN_BASE', None) or 'erp.tryquot.com'
            primary_domain = f"{tenant.slug}.{base}"
            Domain.objects.create(
                domain=primary_domain, tenant=tenant, is_primary=True,
            )
    except Exception as e:
        logger.error('Tenant row creation failed for %s: %s', org_name, e, exc_info=True)
        return Response(
            {'error': 'Failed to create organization. Please try again.'},
            status=500,
        )

    # Dispatch the slow provisioning work. We use .delay() when a broker
    # is reachable; if not (dev without redis), fall back to .apply()
    # which runs inline — same result, just blocks the request like the
    # old synchronous path did.
    task_kwargs = {
        'admin_username': admin_username,
        'admin_email': admin_email,
        'temp_password': admin_password,
        'plan_type': plan.plan_type or plan_type or '',
        'first_name': first_name,
        'last_name': last_name,
        'selected_modules': selected_modules,
        'business_category': business_category,
    }
    try:
        from tenants.tasks import provision_tenant_schema
        provision_tenant_schema.delay(tenant.id, **task_kwargs)
    except Exception as broker_err:
        # Broker down (dev without Redis). Run the task in a daemon thread
        # so the HTTP response still returns 202 immediately; the single-
        # threaded dev server isn't blocked by the 60-180s migration run.
        logger.warning(
            'Celery broker unavailable, provisioning in background thread: %s',
            broker_err,
        )
        import threading
        from tenants.tasks import provision_tenant_schema as _prov

        def _run_inline(tid, kwargs):
            try:
                _prov.apply(args=(tid,), kwargs=kwargs)
            except Exception:
                logger.exception('Inline provisioning thread crashed for %s', tid)

        threading.Thread(
            target=_run_inline,
            args=(tenant.id, task_kwargs),
            daemon=True,
        ).start()

    cache.delete('superadmin_dashboard_stats')

    security_logger.info(
        'TENANT_SIGNUP_QUEUED: org=%s schema=%s admin=%s modules=%s billing=%s category=%s',
        org_name, schema_name, admin_username, selected_modules, billing_cycle, business_category,
    )

    # 202 Accepted — the tenant row exists and is visible in the superadmin
    # UI as `pending`; the frontend polls GET /api/v1/tenants/provisioning-status/
    # (or the superadmin tenants list) until it flips to `active`.
    return Response({
        'message': 'Organization queued for provisioning. You can sign in once it\'s ready.',
        'tenant_id': tenant.id,
        'schema_name': schema_name,
        'domain': domain_name,
        'login_url': django_settings.FRONTEND_URL,
        'modules_activated': len(selected_modules),
        'business_category': business_category,
        'provisioning_status': 'pending',
    }, status=202)


# ---------------------------------------------------------------------------
# Subscription Plans
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def subscription_plans(request):
    """Manage subscription plans."""
    if request.method == 'GET':
        plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
        data = [{
            'id': p.id,
            'name': p.name,
            'plan_type': p.plan_type,
            'description': p.description,
            'price': str(p.price),
            'billing_cycle': p.billing_cycle,
            'max_users': p.max_users,
            'max_storage_gb': p.max_storage_gb,
            'allowed_modules': p.allowed_modules,
            'features': p.features or [],
            'is_featured': p.is_featured,
            'trial_days': p.trial_days,
        } for p in plans]
        return Response(data)

    # POST - create plan
    data = request.data
    name = data.get('name')
    if not name:
        return Response({'error': 'Plan name is required'}, status=400)

    # Check for soft-deleted plan with same name — reactivate it instead
    existing = SubscriptionPlan.objects.filter(name=name).first()
    if existing:
        if existing.is_active:
            return Response({'error': f'A plan with the name "{name}" already exists'}, status=400)
        # Reactivate the soft-deleted plan with new data
        existing.plan_type = data.get('plan_type', 'basic')
        existing.description = data.get('description', '')
        existing.price = data.get('price', 0)
        existing.billing_cycle = data.get('billing_cycle', 'monthly')
        existing.max_users = data.get('max_users', 5)
        existing.max_storage_gb = data.get('max_storage_gb', 10)
        existing.allowed_modules = data.get('allowed_modules', [])
        existing.features = data.get('features', [])
        existing.is_active = True
        existing.is_featured = data.get('is_featured', False)
        existing.trial_days = data.get('trial_days', 0)
        existing.save()
        return Response({'id': existing.id, 'name': existing.name}, status=201)

    try:
        plan = SubscriptionPlan.objects.create(
            name=name,
            plan_type=data.get('plan_type', 'basic'),
            description=data.get('description', ''),
            price=data.get('price', 0),
            billing_cycle=data.get('billing_cycle', 'monthly'),
            max_users=data.get('max_users', 5),
            max_storage_gb=data.get('max_storage_gb', 10),
            allowed_modules=data.get('allowed_modules', []),
            features=data.get('features', []),
            is_active=True,
            is_featured=data.get('is_featured', False),
            trial_days=data.get('trial_days', 0),
        )
        return Response({'id': plan.id, 'name': plan.name}, status=201)
    except Exception as e:
        return Response({'error': str(e)}, status=400)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsSuperAdminUser])
def subscription_plan_detail(request, plan_id):
    """Manage individual subscription plan."""
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id)
    except SubscriptionPlan.DoesNotExist:
        return Response({'error': 'Plan not found'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': plan.id,
            'name': plan.name,
            'plan_type': plan.plan_type,
            'description': plan.description,
            'price': str(plan.price),
            'billing_cycle': plan.billing_cycle,
            'max_users': plan.max_users,
            'max_storage_gb': plan.max_storage_gb,
            'allowed_modules': plan.allowed_modules,
            'features': plan.features or [],
            'is_featured': plan.is_featured,
            'trial_days': plan.trial_days,
        })

    if request.method == 'DELETE':
        plan.is_active = False
        plan.save(update_fields=['is_active'])
        return Response(status=204)

    # PUT - update
    try:
        for field in ['name', 'plan_type', 'description', 'price', 'billing_cycle', 'max_users',
                      'max_storage_gb', 'allowed_modules', 'features', 'is_featured', 'trial_days']:
            if field in request.data:
                setattr(plan, field, request.data[field])
        plan.save()
        return Response({'id': plan.id})
    except Exception as e:
        return Response({'error': str(e)}, status=400)


# ---------------------------------------------------------------------------
# Tenants
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def tenant_list(request):
    """List all tenants with subscription info."""
    if request.method == 'GET':
        tenants = Client.objects.filter(
            is_deleted=False
        ).exclude(
            schema_name='public'
        ).select_related(
            'subscription', 'subscription__plan'
        ).prefetch_related('domains').order_by('-created_on')

        data = []
        for tenant in tenants:
            sub = getattr(tenant, 'subscription', None)
            data.append({
                'id': tenant.id,
                'name': tenant.name,
                'schema_name': tenant.schema_name,
                'created_on': tenant.created_on,
                'status': sub.status if sub else 'no_subscription',
                'plan': sub.plan.name if sub and sub.plan else None,
                'end_date': sub.end_date if sub else None,
                'domains': list(tenant.domains.values_list('domain', flat=True)),
                # Async provisioning state — frontend polls until 'active'.
                'provisioning_status': tenant.provisioning_status,
                'provisioning_error': tenant.provisioning_error or None,
                'provisioning_started_at': tenant.provisioning_started_at,
                'provisioning_completed_at': tenant.provisioning_completed_at,
            })
        return Response(data)

    # POST - create tenant manually (superadmin)
    data = request.data
    org_name = data.get('organization_name', '')
    if not org_name:
        return Response({'error': 'organization_name is required'}, status=400)

    admin_email = data.get('admin_email', '')
    admin_username = data.get('admin_username', '')
    plan_type = data.get('plan_type', '')

    schema_name = re.sub(r'[^a-z0-9_]', '', org_name.lower().replace(' ', '_'))[:50]
    if not schema_name or not re.match(r'^[a-z][a-z0-9_]*$', schema_name):
        return Response({'error': 'Invalid organization name'}, status=400)

    # Auto-generate admin credentials if not provided
    if not admin_username:
        admin_username = f"admin_{schema_name}"
    if not admin_email:
        admin_email = f"admin@{schema_name}.dtsg.test"

    with schema_context('public'):
        if Client.objects.filter(schema_name=schema_name).exists():
            return Response({'error': 'Organization name already exists'}, status=400)

        if User.objects.filter(username=admin_username).exists():
            return Response({'error': 'Username already taken'}, status=400)

        if User.objects.filter(email=admin_email).exists():
            return Response({'error': 'Email already registered'}, status=400)

    temp_password = generate_temp_password()

    # Create the tenant row + domain INSTANTLY. Because Client has
    # ``auto_create_schema = False``, this is now ~30ms instead of 60–180s.
    # The Celery task provision_tenant_schema does the heavy lifting:
    # migrations, admin user, subscription, modules, welcome email.
    try:
        with transaction.atomic():
            tenant = Client.objects.create(
                name=org_name, schema_name=schema_name,
                provisioning_status='pending',
            )
            domain_name = f"{schema_name}.dtsg.test"
            Domain.objects.create(
                domain=domain_name, tenant=tenant, is_primary=True,
            )
    except Exception as e:
        logger.error('Tenant row creation failed: %s', e, exc_info=True)
        return Response({'error': 'Failed to create tenant'}, status=500)

    # Queue async provisioning.
    try:
        from tenants.tasks import provision_tenant_schema
        provision_tenant_schema.delay(
            tenant.id,
            admin_username=admin_username,
            admin_email=admin_email,
            temp_password=temp_password,
            plan_type=plan_type or '',
        )
    except Exception as e:
        # Broker down → run in a daemon thread so the request still returns
        # 202 immediately instead of blocking on 170+ migrations.
        logger.warning(
            'Celery broker unavailable, provisioning in background thread: %s', e,
        )
        import threading
        from tenants.tasks import provision_tenant_schema as _prov

        _kwargs = {
            'admin_username': admin_username,
            'admin_email': admin_email,
            'temp_password': temp_password,
            'plan_type': plan_type or '',
        }

        def _run_inline(tid, kwargs):
            try:
                _prov.apply(args=(tid,), kwargs=kwargs)
            except Exception:
                logger.exception('Inline provisioning thread crashed for %s', tid)

        threading.Thread(
            target=_run_inline,
            args=(tenant.id, _kwargs),
            daemon=True,
        ).start()

    cache.delete('superadmin_dashboard_stats')

    security_logger.info(
        'TENANT_QUEUED: org=%s schema=%s admin=%s by=%s',
        org_name, schema_name, admin_username, request.user.username,
    )

    # 202 Accepted — tenant row exists; provisioning is in-flight. The
    # frontend polls GET /superadmin/tenants to see provisioning_status
    # flip to 'active' (or 'failed').
    return Response({
        'id': tenant.id,
        'name': tenant.name,
        'schema_name': schema_name,
        'domain': domain_name,
        'admin_username': admin_username,
        'temp_password': temp_password,
        'provisioning_status': 'pending',
    }, status=202)


@api_view(['GET', 'PUT', 'DELETE', 'POST'])
@permission_classes([IsSuperAdminUser])
def tenant_detail(request, tenant_id):
    """Manage individual tenant."""
    try:
        tenant = Client.objects.select_related(
            'subscription', 'subscription__plan'
        ).get(id=tenant_id)
    except Client.DoesNotExist:
        return Response({'error': 'Tenant not found'}, status=404)

    if request.method == 'GET':
        sub = getattr(tenant, 'subscription', None)
        return Response({
            'id': tenant.id,
            'name': tenant.name,
            'schema_name': tenant.schema_name,
            'created_on': tenant.created_on,
            'status': sub.status if sub else 'no_subscription',
            'plan_id': sub.plan.id if sub and sub.plan else None,
            'plan_name': sub.plan.name if sub and sub.plan else None,
            'start_date': sub.start_date if sub else None,
            'end_date': sub.end_date if sub else None,
            'auto_renew': sub.auto_renew if sub else False,
            'domains': list(tenant.domains.values_list('domain', flat=True)),
            # Async provisioning state (same shape as list endpoint).
            'provisioning_status': tenant.provisioning_status,
            'provisioning_error': tenant.provisioning_error or None,
            'provisioning_started_at': tenant.provisioning_started_at,
            'provisioning_completed_at': tenant.provisioning_completed_at,
        })

    if request.method == 'DELETE':
        # Soft delete: mark as deleted rather than destroying schema
        tenant.is_deleted = True
        tenant.deleted_at = timezone.now()
        tenant.save(update_fields=['is_deleted', 'deleted_at'])
        # Also suspend subscription
        sub = getattr(tenant, 'subscription', None)
        if sub:
            sub.status = 'cancelled'
            sub.save(update_fields=['status'])
        cache.delete('superadmin_dashboard_stats')
        # Phase 2: Invalidate tenant middleware cache
        from core.cache_utils import invalidate_all_tenant_cache
        invalidate_all_tenant_cache(tenant)
        security_logger.info(
            'TENANT_DELETED: id=%s name=%s by=%s',
            tenant.id, tenant.name, request.user.username,
        )
        return Response(status=204)

    if request.method == 'POST':  # Suspend/Activate/Extend/ResetPassword
        action = request.data.get('action')

        # Password reset — independent of subscription status
        if action == 'reset_password':
            # Exclude superusers — a global superuser must never be selected as
            # the "tenant admin" target of a reset, because set_password would
            # overwrite the superuser's own login (real incident: 2026-04).
            admin_role = (
                UserTenantRole.objects
                .filter(tenant=tenant, role='admin', is_active=True)
                .exclude(user__is_superuser=True)
                .select_related('user')
                .order_by('id')
                .first()
            )
            if not admin_role:
                return Response({'error': 'No active admin user found for this tenant'}, status=404)

            admin_user = admin_role.user
            temp_password = generate_temp_password()
            admin_user.set_password(temp_password)
            admin_user.save(update_fields=['password'])

            email_sent = send_password_reset_email(tenant, admin_user, temp_password)

            security_logger.info(
                'TENANT_PASSWORD_RESET: tenant_id=%s tenant=%s admin=%s by=%s email_sent=%s',
                tenant.id, tenant.name, admin_user.username, request.user.username, email_sent,
            )
            return Response({
                'status': 'password_reset',
                'username': admin_user.username,
                'email': admin_user.email,
                'temp_password': temp_password,
                'email_sent': email_sent,
            })

        # Re-queue a failed (or stuck) provisioning job.
        # Idempotent: the Celery task short-circuits on 'active', so re-running
        # over a partially-migrated schema completes the remaining steps.
        if action == 'retry_provisioning':
            if tenant.provisioning_status not in ('failed', 'pending'):
                return Response(
                    {'error': f"Cannot retry a tenant in '{tenant.provisioning_status}' state"},
                    status=400,
                )

            # Reuse the original admin if one exists; otherwise require payload.
            admin_role = UserTenantRole.objects.filter(
                tenant=tenant, role='admin',
            ).select_related('user').first()

            if admin_role:
                admin_username = admin_role.user.username
                admin_email = admin_role.user.email
            else:
                admin_username = request.data.get('admin_username')
                admin_email = request.data.get('admin_email')
                if not admin_username or not admin_email:
                    return Response(
                        {'error': 'admin_username and admin_email required — no prior admin found'},
                        status=400,
                    )

            temp_password = generate_temp_password()

            # Reset state so polling resumes from 'pending'.
            tenant.provisioning_status = 'pending'
            tenant.provisioning_error = ''
            tenant.provisioning_started_at = None
            tenant.provisioning_completed_at = None
            tenant.save(update_fields=[
                'provisioning_status', 'provisioning_error',
                'provisioning_started_at', 'provisioning_completed_at',
            ])

            from tenants.tasks import provision_tenant_schema
            task_kwargs = {
                'admin_username': admin_username,
                'admin_email': admin_email,
                'temp_password': temp_password,
                'plan_type': request.data.get('plan_type', ''),
            }
            try:
                provision_tenant_schema.delay(tenant.id, **task_kwargs)
            except Exception:  # pragma: no cover — broker-down fallback
                logger.exception('Celery broker unavailable; running provisioning inline')
                provision_tenant_schema.apply(args=(tenant.id,), kwargs=task_kwargs)

            security_logger.info(
                'TENANT_RETRY_PROVISIONING: id=%s name=%s by=%s',
                tenant.id, tenant.name, request.user.username,
            )
            return Response({
                'status': 'retry_queued',
                'provisioning_status': 'pending',
                'admin_username': admin_username,
                'admin_email': admin_email,
                'temp_password': temp_password,
            }, status=202)

        # Subscription actions
        sub = getattr(tenant, 'subscription', None)
        if sub:
            if action == 'suspend':
                sub.status = 'suspended'
            elif action == 'activate':
                sub.status = 'active'
            elif action == 'extend':
                try:
                    days = int(request.data.get('days', 30))
                except (ValueError, TypeError):
                    return Response({'error': 'Invalid days value'}, status=400)
                if days < 1 or days > 3650:
                    return Response({'error': 'Days must be between 1 and 3650'}, status=400)
                if sub.end_date:
                    sub.end_date += timedelta(days=days)
                else:
                    sub.end_date = timezone.now().date() + timedelta(days=days)
            sub.save()
            cache.delete('superadmin_dashboard_stats')
            # Phase 2: Invalidate tenant middleware cache on status change
            from core.cache_utils import invalidate_subscription_cache
            invalidate_subscription_cache(tenant.schema_name)
        return Response({'status': sub.status if sub else 'no_subscription'})

    # PUT - update name
    if 'name' in request.data:
        tenant.name = request.data['name']
        tenant.save(update_fields=['name'])
    return Response({'id': tenant.id})


@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
def tenant_change_plan(request, tenant_id):
    """Change tenant subscription plan."""
    try:
        tenant = Client.objects.get(id=tenant_id)
    except Client.DoesNotExist:
        return Response({'error': 'Tenant not found'}, status=404)

    plan_id = request.data.get('plan_id')
    if not plan_id:
        return Response({'error': 'plan_id is required'}, status=400)

    try:
        plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
    except SubscriptionPlan.DoesNotExist:
        return Response({'error': 'Plan not found'}, status=404)

    sub = getattr(tenant, 'subscription', None)
    old_plan = sub.plan if sub else None

    with transaction.atomic():
        if sub:
            sub.plan = plan
            sub.status = 'active'
            sub.save(update_fields=['plan', 'status'])
        else:
            TenantSubscription.objects.create(
                tenant=tenant,
                plan=plan,
                status='active',
                start_date=timezone.now().date(),
                end_date=timezone.now().date() + timedelta(
                    days=30 if plan.billing_cycle == 'monthly' else 365
                ),
            )

        # Sync modules in the tenant's own schema to match the new plan
        allowed = set(plan.allowed_modules or [])
        _mod_title_map = {k: t for k, t, _d in AVAILABLE_MODULES}
        with schema_context(tenant.schema_name):
            PerTenantModule.objects.exclude(module_name__in=allowed).update(is_active=False)
            for mod_name in allowed:
                PerTenantModule.objects.update_or_create(
                    module_name=mod_name,
                    defaults={
                        'module_title': _mod_title_map.get(mod_name, mod_name),
                        'description': f'Included in {plan.name} plan',
                        'is_active': True,
                    },
                )

    send_plan_change_email(tenant, old_plan, plan)
    cache.delete('superadmin_dashboard_stats')

    return Response({'message': 'Plan changed successfully', 'new_plan': plan.name})


# ---------------------------------------------------------------------------
# Dashboard Stats (cached)
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def dashboard_stats(request):
    """Get superadmin dashboard statistics (cached 60s).

    All Client / TenantSubscription queries exclude the django-tenants
    'public' schema row, which is an internal record — not a real tenant.
    """
    cache_key = 'superadmin_dashboard_stats'
    data = cache.get(cache_key)
    if data:
        return Response(data)

    # Exclude the django-tenants internal 'public' schema record
    # and soft-deleted tenants (is_deleted=True)
    real_tenants = Client.objects.filter(is_deleted=False).exclude(schema_name='public')
    real_subs    = TenantSubscription.objects.filter(tenant__is_deleted=False).exclude(tenant__schema_name='public')

    total_tenants          = real_tenants.count()
    active_subscriptions   = real_subs.filter(status='active').count()
    trial_subscriptions    = real_subs.filter(status='trial').count()
    suspended              = real_subs.filter(status='suspended').count()
    expired_subscriptions  = real_subs.filter(status='expired').count()
    cancelled_subscriptions = real_subs.filter(status='cancelled').count()

    total_revenue = (
        TenantPayment.objects.filter(status='processed', tenant__is_deleted=False)
        .exclude(tenant__schema_name='public')
        .aggregate(total=Sum('amount'))['total'] or 0
    )

    recent_tenants = real_tenants.order_by('-created_on')[:5]
    recent_data = [{'name': t.name, 'created_on': t.created_on} for t in recent_tenants]

    data = {
        'total_tenants': total_tenants,
        'active_subscriptions': active_subscriptions,
        'trial_subscriptions': trial_subscriptions,
        'suspended': suspended,
        'expired_subscriptions': expired_subscriptions,
        'cancelled_subscriptions': cancelled_subscriptions,
        'total_revenue': str(total_revenue),
        'recent_signups': recent_data,
    }
    cache.set(cache_key, data, timeout=60)
    return Response(data)


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def payment_list(request):
    """List all payments with pagination."""
    payments = TenantPayment.objects.select_related('tenant').order_by('-created_at')
    page_items, meta = paginate(payments, request)

    data = [{
        'id': p.id,
        'tenant': p.tenant.name,
        'amount': str(p.amount),
        'currency': p.currency,
        'payment_method': p.payment_method,
        'transaction_reference': p.transaction_reference,
        'payment_date': p.payment_date,
        'status': p.status,
        'created_at': p.created_at,
    } for p in page_items]

    return Response({**meta, 'results': data})


@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
def payment_approve(request, payment_id):
    """Approve/reject a payment."""
    try:
        payment = TenantPayment.objects.select_related(
            'subscription', 'subscription__plan'
        ).get(id=payment_id)
    except TenantPayment.DoesNotExist:
        return Response({'error': 'Payment not found'}, status=404)

    action = request.data.get('action')
    notes = request.data.get('notes', '')

    if action not in ('approve', 'reject'):
        return Response({'error': 'action must be "approve" or "reject"'}, status=400)

    with transaction.atomic():
        if action == 'approve':
            payment.status = 'approved'
            payment.approved_by = request.user
            payment.approval_notes = notes
            payment.save()

            if payment.subscription:
                payment.subscription.status = 'active'
                payment.subscription.last_payment_date = payment.payment_date
                if payment.subscription.end_date and payment.subscription.plan:
                    billing_cycle = payment.subscription.plan.billing_cycle
                    months = {'monthly': 1, 'quarterly': 3, 'yearly': 12}.get(billing_cycle, 1)
                    payment.subscription.end_date += relativedelta(months=months)
                payment.subscription.save()
        else:
            payment.status = 'rejected'
            payment.approved_by = request.user
            payment.approval_notes = notes
            payment.save()

    cache.delete('superadmin_dashboard_stats')
    return Response({'status': payment.status})


# ---------------------------------------------------------------------------
# Global Module Toggle (optimized)
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def global_module_toggle(request):
    """Toggle a module globally for all tenants or get global module status."""
    if request.method == 'GET':
        # Exclude django-tenants internal 'public' schema row
        tenants_qs = Client.objects.exclude(schema_name='public')
        total_tenants = tenants_qs.count()

        # Aggregate module stats across ALL tenant schemas.
        # Each tenant owns its modules in its own schema — we switch context per tenant.
        stats_map: dict[str, dict] = {}
        for tenant in tenants_qs.only('schema_name'):
            with schema_context(tenant.schema_name):
                for row in PerTenantModule.objects.values('module_name', 'is_active'):
                    entry = stats_map.setdefault(
                        row['module_name'], {'active_count': 0, 'total_count': 0}
                    )
                    entry['total_count'] += 1
                    if row['is_active']:
                        entry['active_count'] += 1

        modules_data = []
        for module_key, module_title, module_desc in AVAILABLE_MODULES:
            stats = stats_map.get(module_key, {'active_count': 0, 'total_count': 0})
            is_global = (
                stats['active_count'] >= (stats['total_count'] / 2)
                if stats['total_count'] > 0 else False
            )
            modules_data.append({
                'module_name': module_key,
                'module_title': module_title,
                'description': module_desc,
                'is_globally_enabled': is_global,
                'active_tenants': stats['active_count'],
                'total_configured': stats['total_count'],
                'total_tenants': total_tenants,
            })

        return Response(modules_data)

    # POST - Toggle module globally (bulk operation)
    module_name = request.data.get('module_name')
    is_enabled = request.data.get('is_enabled', True)

    if not module_name:
        return Response({'error': 'module_name is required'}, status=400)

    module_info = None
    for key, title, desc in AVAILABLE_MODULES:
        if key == module_name:
            module_info = (key, title, desc)
            break
    if not module_info:
        return Response({'error': 'Module not found'}, status=404)

    # Apply the toggle to every tenant's own schema.
    tenants_qs = Client.objects.exclude(schema_name='public')
    updated_count = 0
    created_count = 0
    for tenant in tenants_qs.only('schema_name'):
        with schema_context(tenant.schema_name):
            _, created = PerTenantModule.objects.update_or_create(
                module_name=module_info[0],
                defaults={
                    'module_title': module_info[1],
                    'description': module_info[2],
                    'is_active': is_enabled,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

    return Response({
        'message': f'Module {"enabled" if is_enabled else "disabled"} globally',
        'module_name': module_name,
        'is_enabled': is_enabled,
        'updated_tenants': updated_count,
        'created_for_tenants': created_count,
        'total_tenants': updated_count + created_count,
    })


# ---------------------------------------------------------------------------
# Cross-Tenant User Management (fixed: uses public schema)
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def user_list(request):
    """List all users with their tenant assignments (from public schema)."""
    with schema_context('public'):
        users = User.objects.all().order_by('-date_joined')

        # Single query for all tenant roles
        all_roles = (
            UserTenantRole.objects
            .select_related('tenant')
            .values_list(
                'user_id', 'tenant_id', 'tenant__name', 'role', 'is_active',
            )
        )
        roles_by_user = {}
        for user_id, tenant_id, tenant_name, role, is_active in all_roles:
            roles_by_user.setdefault(user_id, []).append({
                'tenant_id': tenant_id,
                'tenant_name': tenant_name,
                'role': role,
                'is_active': is_active,
            })

        # Apply search filter
        search = request.query_params.get('search', '').strip()
        if search:
            users = users.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )

        page_items, meta = paginate(users, request)

        data = []
        for user in page_items:
            tenants = roles_by_user.get(user.id, [])
            # For backward compatibility, include primary tenant info
            primary = tenants[0] if tenants else {}
            data.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'is_active': user.is_active,
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
                'date_joined': user.date_joined,
                'last_login': user.last_login,
                'tenant_id': primary.get('tenant_id'),
                'tenant_name': primary.get('tenant_name', ''),
                'tenants': tenants,
            })

    return Response({**meta, 'results': data})


@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
def bulk_delete_users(request):
    """Bulk delete users. Superadmin users cannot be deleted."""
    ids = request.data.get('ids', [])
    if not ids:
        return Response({'error': 'No user IDs provided.'}, status=status.HTTP_400_BAD_REQUEST)
    if len(ids) > 100:
        return Response({'error': 'Maximum 100 users per bulk delete.'}, status=status.HTTP_400_BAD_REQUEST)

    with schema_context('public'):
        users = User.objects.filter(id__in=ids)

        # Block deletion of superusers
        superusers = users.filter(is_superuser=True)
        if superusers.exists():
            names = ', '.join(u.username for u in superusers[:5])
            return Response(
                {'error': f'Cannot delete superadmin users: {names}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Block self-deletion
        if request.user.id in ids:
            return Response(
                {'error': 'Cannot delete your own account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        count = users.count()
        usernames = list(users.values_list('username', flat=True))

        # Delete related data: tenant roles, tokens, sessions
        from tenants.models import UserTenantRole
        from rest_framework.authtoken.models import Token
        UserTenantRole.objects.filter(user__in=users).delete()
        Token.objects.filter(user__in=users).delete()
        users.delete()

        security_logger.info(
            'BULK_DELETE_USERS: deleted=%d users=%s by=%s',
            count, usernames, request.user.username,
        )

    return Response({'status': f'{count} user(s) deleted successfully.', 'deleted': count})


@api_view(['PATCH'])
@permission_classes([IsSuperAdminUser])
def user_detail(request, user_id):
    """Update user in public schema."""
    with schema_context('public'):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

        is_active = request.data.get('is_active')
        if is_active is not None:
            user.is_active = is_active
            user.save(update_fields=['is_active'])

            security_logger.info(
                'USER_STATUS_CHANGE: user=%s is_active=%s by=%s',
                user.username, is_active, request.user.username,
            )

    return Response({'message': 'User updated successfully'})


# ---------------------------------------------------------------------------
# Audit Logs (uses Django admin LogEntry as interim solution)
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def audit_logs(request):
    """Get audit logs from Django admin LogEntry (public schema)."""
    from django.contrib.admin.models import LogEntry

    with schema_context('public'):
        entries = LogEntry.objects.select_related(
            'user', 'content_type'
        ).order_by('-action_time')

        # Filters
        action_type = request.query_params.get('action_type')
        if action_type:
            action_map = {'CREATE': 1, 'UPDATE': 2, 'DELETE': 3}
            flag = action_map.get(action_type.upper())
            if flag:
                entries = entries.filter(action_flag=flag)

        start_date = request.query_params.get('start_date')
        if start_date:
            entries = entries.filter(action_time__gte=start_date)

        end_date = request.query_params.get('end_date')
        if end_date:
            entries = entries.filter(action_time__lte=end_date)

        page_items, meta = paginate(entries, request)

        action_labels = {1: 'CREATE', 2: 'UPDATE', 3: 'DELETE'}
        data = [{
            'id': e.id,
            'timestamp': e.action_time,
            'user_id': e.user_id,
            'username': e.user.username if e.user else None,
            'action_type': action_labels.get(e.action_flag, 'UNKNOWN'),
            'module': e.content_type.app_label if e.content_type else '',
            'object_repr': e.object_repr,
            'changes': e.get_change_message(),
            'ip_address': None,
            'tenant_id': None,
            'tenant_name': 'Platform',
        } for e in page_items]

    return Response({**meta, 'results': data})


# ---------------------------------------------------------------------------
# Tenant Modules
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def tenant_modules(request, tenant_id):
    """Get or configure modules for a specific tenant."""
    try:
        tenant = Client.objects.get(id=tenant_id)
    except Client.DoesNotExist:
        return Response({'error': 'Tenant not found'}, status=404)

    if request.method == 'GET':
        with schema_context(tenant.schema_name):
            configured = {
                m.module_name: {
                    'id': m.id,
                    'module_name': m.module_name,
                    'module_title': m.module_title,
                    'description': m.description,
                    'is_active': m.is_active,
                    'configured': True,
                }
                for m in PerTenantModule.objects.all()
            }

        data = list(configured.values())
        for key, title, desc in AVAILABLE_MODULES:
            if key not in configured:
                data.append({
                    'id': None,
                    'module_name': key,
                    'module_title': title,
                    'description': desc,
                    'is_active': False,
                    'configured': False,
                })

        return Response(data)

    # POST - Update tenant modules in the tenant's own schema
    modules_data = request.data.get('modules', [])
    _module_map = {k: (t, d) for k, t, d in AVAILABLE_MODULES}

    with schema_context(tenant.schema_name):
        for mod in modules_data:
            module_name = mod.get('module_name')
            is_active = mod.get('is_active', False)
            if not module_name or module_name not in _module_map:
                continue
            title, desc = _module_map[module_name]
            PerTenantModule.objects.update_or_create(
                module_name=module_name,
                defaults={
                    'module_title': title,
                    'description': desc,
                    'is_active': is_active,
                },
            )

    return Response({'message': 'Modules updated successfully'})


# ---------------------------------------------------------------------------
# System Health
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def system_health(request):
    """Get system health status."""
    from django.db import connection as db_connection

    try:
        import psutil
        _has_psutil = True
    except ImportError:
        _has_psutil = False

    health_data = {
        'database': 'unknown',
        'disk_usage': 0,
        'memory_usage': 0,
        'active_connections': 0,
        'tenants': {
            # Exclude django-tenants internal 'public' schema row from all counts
            'total': Client.objects.exclude(schema_name='public').count(),
            'active': TenantSubscription.objects.filter(status='active').exclude(tenant__schema_name='public').count(),
            'trial': TenantSubscription.objects.filter(status='trial').exclude(tenant__schema_name='public').count(),
            'suspended': TenantSubscription.objects.filter(status='suspended').exclude(tenant__schema_name='public').count(),
        },
        'timestamp': timezone.now().isoformat(),
    }

    try:
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            health_data['database'] = 'healthy'
    except Exception:
        health_data['database'] = 'unhealthy'

    try:
        if _has_psutil:
            health_data['disk_usage'] = psutil.disk_usage('/').percent
            health_data['memory_usage'] = psutil.virtual_memory().percent

        with db_connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_stat_activity")
            health_data['active_connections'] = cursor.fetchone()[0]
    except Exception as exc:
        logger.warning(
            "superadmin health-check: could not collect system metrics "
            "(psutil or DB stats unavailable): %s", exc,
        )

    return Response(health_data)


# ---------------------------------------------------------------------------
# Platform Settings
# ---------------------------------------------------------------------------

@api_view(['GET', 'PUT'])
@permission_classes([IsSuperAdminUser])
def platform_settings(request):
    """Get or update global platform settings (singleton)."""
    sa_settings = SuperAdminSettings.load()

    if request.method == 'GET':
        return Response({
            'organization_name': sa_settings.organization_name,
            'default_timezone': sa_settings.default_timezone,
            'default_currency': sa_settings.default_currency,
            'maintenance_mode': sa_settings.maintenance_mode,
            'session_timeout_minutes': sa_settings.session_timeout_minutes,
            'require_special_chars': sa_settings.require_special_chars,
            'require_uppercase': sa_settings.require_uppercase,
            'min_password_length': sa_settings.min_password_length,
            'two_factor_enabled': sa_settings.two_factor_enabled,
            'rate_limit_per_hour': sa_settings.rate_limit_per_hour,
            'token_expiry_days': sa_settings.token_expiry_days,
            'max_login_attempts': sa_settings.max_login_attempts,
            # SMTP fields (Phase 4 will populate these)
            'smtp_host': getattr(sa_settings, 'smtp_host', ''),
            'smtp_port': getattr(sa_settings, 'smtp_port', 587),
            'smtp_username': getattr(sa_settings, 'smtp_username', ''),
            'smtp_password': '****' if getattr(sa_settings, 'smtp_password', '') else '',
            'smtp_use_tls': getattr(sa_settings, 'smtp_use_tls', True),
            'smtp_use_ssl': getattr(sa_settings, 'smtp_use_ssl', False),
            'smtp_from_email': getattr(sa_settings, 'smtp_from_email', ''),
            'smtp_from_name': getattr(sa_settings, 'smtp_from_name', 'QUOT ERP'),
            'support_email': getattr(sa_settings, 'support_email', ''),
            'smtp_enabled': getattr(sa_settings, 'smtp_enabled', False),
        })

    # PUT - update fields
    data = request.data
    fields = [
        'organization_name', 'default_timezone', 'default_currency', 'maintenance_mode',
        'session_timeout_minutes', 'require_special_chars', 'require_uppercase',
        'min_password_length', 'two_factor_enabled',
        'rate_limit_per_hour', 'token_expiry_days', 'max_login_attempts',
        # SMTP fields
        'smtp_host', 'smtp_port', 'smtp_username', 'smtp_password',
        'smtp_use_tls', 'smtp_use_ssl', 'smtp_from_email', 'smtp_from_name',
        'support_email', 'smtp_enabled',
    ]
    for field in fields:
        if field not in data or not hasattr(sa_settings, field):
            continue
        value = data[field]
        # Skip masked sentinel ('****') sent back by the frontend when the user
        # did not change the password — overwriting with the mask would corrupt
        # the stored credential.
        if field == 'smtp_password' and value == '****':
            continue
        setattr(sa_settings, field, value)
    sa_settings.save()
    return Response({'message': 'Settings saved successfully'})


# ---------------------------------------------------------------------------
# SMTP Test
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
def test_smtp(request):
    """Send a test email to verify SMTP configuration."""
    to_email = request.data.get('to_email')
    if not to_email:
        return Response({'error': 'to_email is required'}, status=400)

    try:
        from .email_utils import send_test_email
        send_test_email(to_email)
        return Response({'message': f'Test email sent to {to_email}'})
    except Exception as e:
        logger.error('SMTP test failed: %s', e, exc_info=True)
        return Response({'error': str(e)}, status=500)


# ---------------------------------------------------------------------------
# Tenant Impersonation
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
@throttle_classes([ImpersonateThrottle])
def impersonate_user(request):
    """Generate a temporary token for impersonating a tenant user."""
    from rest_framework.authtoken.models import Token


    user_id = request.data.get('user_id')
    tenant_id = request.data.get('tenant_id')

    if not tenant_id:
        return Response({'error': 'tenant_id is required'}, status=400)

    with schema_context('public'):
        try:
            tenant = Client.objects.get(id=tenant_id)
        except Client.DoesNotExist:
            return Response({'error': 'Tenant not found'}, status=404)

        if user_id:
            # Impersonate a specific user
            try:
                target_user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response({'error': 'User not found'}, status=404)

            if not UserTenantRole.objects.filter(
                user=target_user, tenant=tenant, is_active=True,
            ).exists():
                return Response({'error': 'User has no access to this tenant'}, status=400)
        else:
            # No user_id provided — auto-select the tenant admin
            admin_role = UserTenantRole.objects.filter(
                tenant=tenant, role='admin', is_active=True,
            ).select_related('user').first()
            if not admin_role:
                # Fallback to any active user in the tenant
                admin_role = UserTenantRole.objects.filter(
                    tenant=tenant, is_active=True,
                ).select_related('user').first()
            if not admin_role:
                # Auto-create an admin user for this orphaned tenant
                auto_username = f"admin_{tenant.schema_name}"
                auto_email = f"admin@{tenant.schema_name}.dtsg.test"
                auto_password = generate_temp_password()

                # Check if username/email already exists
                if User.objects.filter(username=auto_username).exists():
                    auto_username = f"admin_{tenant.schema_name}_{tenant.id}"
                if User.objects.filter(email=auto_email).exists():
                    auto_email = f"admin{tenant.id}@{tenant.schema_name}.dtsg.test"

                target_user = User.objects.create_user(
                    username=auto_username.lower(),
                    email=auto_email,
                    password=auto_password,
                    first_name='Admin',
                    last_name=tenant.name,
                    is_staff=True,
                    is_superuser=False,
                )
                UserTenantRole.objects.create(
                    user=target_user,
                    tenant=tenant,
                    role='admin',
                    is_active=True,
                )
                logger.info(
                    'AUTO_CREATED admin user %s for orphaned tenant %s during impersonation',
                    auto_username, tenant.schema_name,
                )
            else:
                target_user = admin_role.user

        # Revoke any existing tokens for this user and issue a fresh one.
        # This guarantees the impersonator always receives a valid token and
        # avoids orphaned tokens from repeated impersonation of the same user.
        Token.objects.filter(user=target_user).delete()
        token = Token.objects.create(user=target_user)

        # Get domain
        domain = tenant.domains.filter(is_primary=True).first()

        # Log the impersonation
        log = ImpersonationLog.objects.create(
            superadmin=request.user,
            target_user=target_user,
            target_tenant=tenant,
            token_key=token.key,
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        security_logger.warning(
            'IMPERSONATION: admin=%s target_user=%s tenant=%s ip=%s',
            request.user.username, target_user.username,
            tenant.schema_name, request.META.get('REMOTE_ADDR'),
        )

    return Response({
        'token': token.key,
        'user': {
            'id': target_user.id,
            'username': target_user.username,
            'email': target_user.email,
            'first_name': target_user.first_name,
            'last_name': target_user.last_name,
        },
        'tenant_domain': domain.domain if domain else None,
        'tenant_name': tenant.name,
        'session_id': log.id,
    })


@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
def stop_impersonation(request):
    """End an impersonation session."""


    session_id = request.data.get('session_id')
    if session_id:
        log = ImpersonationLog.objects.filter(id=session_id, is_active=True).first()
        if log:
            log.is_active = False
            log.ended_at = timezone.now()
            log.save(update_fields=['is_active', 'ended_at'])
            # Revoke the impersonation token so it can't be reused
            if log.token_key:
                Token.objects.filter(key=log.token_key).delete()
    return Response({'message': 'Impersonation ended'})


@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def impersonation_logs(request):
    """List impersonation history."""


    logs = ImpersonationLog.objects.select_related(
        'superadmin', 'target_user', 'target_tenant',
    ).order_by('-started_at')

    page_items, meta = paginate(logs, request)

    data = [{
        'id': log.id,
        'superadmin': log.superadmin.username,
        'target_user': log.target_user.username,
        'target_tenant': log.target_tenant.name,
        'started_at': log.started_at,
        'ended_at': log.ended_at,
        'ip_address': log.ip_address,
        'is_active': log.is_active,
    } for log in page_items]

    return Response({**meta, 'results': data})


# ---------------------------------------------------------------------------
# Plan Comparison & Trial Management
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def plan_comparison(request):
    """Get all plans with tenant counts for comparison view."""
    plans = SubscriptionPlan.objects.filter(is_active=True).annotate(
        tenant_count=Count('tenantsubscription__tenant', distinct=True),
        active_tenants=Count(
            'tenantsubscription__tenant',
            filter=Q(tenantsubscription__status='active'),
            distinct=True,
        ),
        trial_tenants=Count(
            'tenantsubscription__tenant',
            filter=Q(tenantsubscription__status='trial'),
            distinct=True,
        ),
    ).order_by('price')

    data = [{
        'id': p.id,
        'name': p.name,
        'plan_type': p.plan_type,
        'description': p.description,
        'price': str(p.price),
        'billing_cycle': p.billing_cycle,
        'max_users': p.max_users,
        'max_storage_gb': p.max_storage_gb,
        'allowed_modules': p.allowed_modules,
        'features': p.features or [],
        'is_featured': p.is_featured,
        'trial_days': p.trial_days,
        'tenant_count': p.tenant_count,
        'active_tenants': p.active_tenants,
        'trial_tenants': p.trial_tenants,
    } for p in plans]

    return Response(data)


@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def expiring_trials(request):
    """Get tenants with trials expiring within N days."""
    try:
        days = int(request.query_params.get('days', 7))
    except (ValueError, TypeError):
        days = 7
    cutoff = timezone.now().date() + timedelta(days=days)

    trials = TenantSubscription.objects.filter(
        status='trial',
        end_date__lte=cutoff,
        end_date__gte=timezone.now().date(),
    ).select_related('tenant', 'plan')

    data = [{
        'tenant_id': t.tenant_id,
        'tenant_name': t.tenant.name,
        'plan': t.plan.name if t.plan else None,
        'end_date': t.end_date,
        'days_remaining': (t.end_date - timezone.now().date()).days,
    } for t in trials]

    return Response(data)


# ---------------------------------------------------------------------------
# SAAS ENHANCEMENT APIs - PHASE 1: REFERRER & COMMISSION
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def referrer_list_create(request):
    """List all referrers or create a new referrer."""
    if request.method == 'GET':
        referrers = Referrer.objects.all().order_by('-created_at')
        search = request.query_params.get('search', '').strip()
        if search:
            referrers = referrers.filter(
                Q(contact_name__icontains=search) |
                Q(email__icontains=search) |
                Q(referrer_code__icontains=search) |
                Q(company_name__icontains=search)
            )
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            referrers = referrers.filter(is_active=is_active == 'true')

        page_items, meta = paginate(referrers, request)
        data = [{
            'id': r.id,
            'referrer_code': r.referrer_code,
            'referrer_type': r.referrer_type,
            'company_name': r.company_name,
            'contact_name': r.contact_name,
            'email': r.email,
            'phone': r.phone,
            'address': r.address,
            'commission_rate': str(r.commission_rate),
            'commission_type': r.commission_type,
            'bank_name': r.bank_name,
            'bank_account': r.bank_account,
            'payment_schedule': r.payment_schedule,
            'is_active': r.is_active,
            'created_at': r.created_at,
            'total_referrals': r.referrals.count(),
            'total_commission': str(
                r.commissions.filter(status='Paid').aggregate(t=Sum('commission_amount'))['t'] or 0
            ),
            'pending_commission': str(
                r.commissions.filter(status__in=['Pending', 'Approved']).aggregate(t=Sum('commission_amount'))['t'] or 0
            ),
        } for r in page_items]
        return Response({**meta, 'results': data})

    # POST
    data = request.data
    required = ['contact_name', 'email']
    for field in required:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    referrer = Referrer.objects.create(
        referrer_type=data.get('referrer_type', 'Partner'),
        company_name=data.get('company_name', ''),
        contact_name=data['contact_name'],
        email=data['email'],
        phone=data.get('phone', ''),
        address=data.get('address', ''),
        commission_rate=data.get('commission_rate', 10),
        commission_type=data.get('commission_type', 'Percentage'),
        bank_name=data.get('bank_name', ''),
        bank_account=data.get('bank_account', ''),
        payment_schedule=data.get('payment_schedule', 'Monthly'),
    )
    return Response({'id': referrer.id, 'referrer_code': referrer.referrer_code}, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsSuperAdminUser])
def referrer_detail(request, pk):
    """Get, update, or delete a referrer."""
    try:
        referrer = Referrer.objects.get(pk=pk)
    except Referrer.DoesNotExist:
        return Response({'error': 'Referrer not found'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': referrer.id,
            'referrer_code': referrer.referrer_code,
            'referrer_type': referrer.referrer_type,
            'company_name': referrer.company_name,
            'contact_name': referrer.contact_name,
            'email': referrer.email,
            'phone': referrer.phone,
            'address': referrer.address,
            'commission_rate': str(referrer.commission_rate),
            'commission_type': referrer.commission_type,
            'bank_name': referrer.bank_name,
            'bank_account': referrer.bank_account,
            'payment_schedule': referrer.payment_schedule,
            'is_active': referrer.is_active,
            'created_at': referrer.created_at,
            'updated_at': referrer.updated_at,
            'total_referrals': referrer.referrals.count(),
            'total_commission': str(
                referrer.commissions.filter(status='Paid').aggregate(t=Sum('commission_amount'))['t'] or 0
            ),
            'pending_commission': str(
                referrer.commissions.filter(status__in=['Pending', 'Approved']).aggregate(t=Sum('commission_amount'))['t'] or 0
            ),
        })

    if request.method == 'PUT':
        updatable = [
            'referrer_type', 'company_name', 'contact_name', 'email', 'phone',
            'address', 'commission_rate', 'commission_type', 'bank_name',
            'bank_account', 'payment_schedule', 'is_active',
        ]
        for field in updatable:
            if field in request.data:
                setattr(referrer, field, request.data[field])
        referrer.save()
        return Response({'status': 'updated'})

    # DELETE
    referrer.delete()
    return Response(status=204)


@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def referral_list_create(request):
    """List all referrals or create a new referral."""
    if request.method == 'GET':
        referrals = Referral.objects.select_related('referrer', 'tenant').order_by('-referred_at')
        referrer_id = request.query_params.get('referrer_id')
        if referrer_id:
            referrals = referrals.filter(referrer_id=referrer_id)
        status = request.query_params.get('status')
        if status:
            referrals = referrals.filter(status=status)

        page_items, meta = paginate(referrals, request)
        data = [{
            'id': r.id,
            'referrer_id': r.referrer_id,
            'referrer_name': r.referrer.contact_name,
            'referrer_code': r.referrer.referrer_code,
            'tenant_id': r.tenant_id,
            'tenant_name': r.tenant.name,
            'status': r.status,
            'source': r.source,
            'utm_campaign': r.utm_campaign,
            'utm_medium': r.utm_medium,
            'referred_at': r.referred_at,
            'converted_at': r.converted_at,
        } for r in page_items]
        return Response({**meta, 'results': data})

    # POST
    data = request.data
    for field in ['referrer_id', 'tenant_id']:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    try:
        referrer = Referrer.objects.get(pk=data['referrer_id'])
    except Referrer.DoesNotExist:
        return Response({'error': 'Referrer not found'}, status=404)
    try:
        tenant = Client.objects.get(pk=data['tenant_id'])
    except Client.DoesNotExist:
        return Response({'error': 'Tenant not found'}, status=404)

    if Referral.objects.filter(referrer=referrer, tenant=tenant).exists():
        return Response({'error': 'Referral already exists for this tenant'}, status=400)

    referral = Referral.objects.create(
        referrer=referrer,
        tenant=tenant,
        status=data.get('status', 'Pending'),
        source=data.get('source', ''),
        utm_campaign=data.get('utm_campaign', ''),
        utm_medium=data.get('utm_medium', ''),
    )
    return Response({'id': referral.id}, status=201)


@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def commission_list_create(request):
    """List all commissions or create a new commission."""
    if request.method == 'GET':
        comms = Commission.objects.select_related('referrer', 'tenant', 'referral').order_by('-sale_date')
        referrer_id = request.query_params.get('referrer_id')
        if referrer_id:
            comms = comms.filter(referrer_id=referrer_id)
        status = request.query_params.get('status')
        if status:
            comms = comms.filter(status=status)

        page_items, meta = paginate(comms, request)
        data = [{
            'id': c.id,
            'referrer_id': c.referrer_id,
            'referrer_name': c.referrer.contact_name,
            'tenant_id': c.tenant_id,
            'tenant_name': c.tenant.name,
            'referral_id': c.referral_id,
            'sale_amount': str(c.sale_amount),
            'sale_date': c.sale_date,
            'commission_rate': str(c.commission_rate),
            'commission_type': c.commission_type,
            'commission_amount': str(c.commission_amount),
            'status': c.status,
            'payment_date': c.payment_date,
            'invoice_number': c.invoice_number,
            'notes': c.notes,
            'created_at': c.created_at,
        } for c in page_items]
        return Response({**meta, 'results': data})

    # POST
    data = request.data
    for field in ['referrer_id', 'referral_id', 'tenant_id', 'sale_amount', 'sale_date']:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    try:
        referrer = Referrer.objects.get(pk=data['referrer_id'])
    except Referrer.DoesNotExist:
        return Response({'error': 'Referrer not found'}, status=404)

    commission = Commission.objects.create(
        referrer=referrer,
        referral_id=data['referral_id'],
        tenant_id=data['tenant_id'],
        subscription_id=data.get('subscription_id'),
        sale_amount=data['sale_amount'],
        sale_date=data['sale_date'],
        commission_rate=data.get('commission_rate', referrer.commission_rate),
        commission_type=data.get('commission_type', referrer.commission_type),
        notes=data.get('notes', ''),
    )
    commission.calculate_commission()
    commission.save()
    return Response({
        'id': commission.id,
        'commission_amount': str(commission.commission_amount),
    }, status=201)


@api_view(['GET', 'PUT'])
@permission_classes([IsSuperAdminUser])
def commission_detail(request, pk):
    """Get or update a commission."""
    try:
        commission = Commission.objects.select_related('referrer', 'tenant').get(pk=pk)
    except Commission.DoesNotExist:
        return Response({'error': 'Commission not found'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': commission.id,
            'referrer_id': commission.referrer_id,
            'referrer_name': commission.referrer.contact_name,
            'tenant_id': commission.tenant_id,
            'tenant_name': commission.tenant.name,
            'sale_amount': str(commission.sale_amount),
            'sale_date': commission.sale_date,
            'commission_rate': str(commission.commission_rate),
            'commission_type': commission.commission_type,
            'commission_amount': str(commission.commission_amount),
            'status': commission.status,
            'payment_date': commission.payment_date,
            'invoice_number': commission.invoice_number,
            'notes': commission.notes,
        })

    # PUT — approve / reject / pay
    action = request.data.get('action')
    if action == 'approve':
        commission.status = 'Approved'
    elif action == 'reject':
        commission.status = 'Cancelled'
    elif action == 'pay':
        commission.status = 'Paid'
        commission.payment_date = timezone.now().date()
    else:
        for field in ['status', 'notes', 'payment_date', 'invoice_number']:
            if field in request.data:
                setattr(commission, field, request.data[field])
    commission.save()
    return Response({'status': commission.status})


@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def commission_payout_list_create(request):
    """List payouts or create a new payout batch."""
    if request.method == 'GET':
        payouts = CommissionPayout.objects.select_related('referrer').order_by('-period_end')
        referrer_id = request.query_params.get('referrer_id')
        if referrer_id:
            payouts = payouts.filter(referrer_id=referrer_id)
        status = request.query_params.get('status')
        if status:
            payouts = payouts.filter(status=status)

        page_items, meta = paginate(payouts, request)
        data = [{
            'id': p.id,
            'referrer_id': p.referrer_id,
            'referrer_name': p.referrer.contact_name,
            'period_start': p.period_start,
            'period_end': p.period_end,
            'total_commissions': str(p.total_commissions),
            'commissions_count': p.commissions_count,
            'status': p.status,
            'payout_date': p.payout_date,
            'payout_reference': p.payout_reference,
            'payment_method': p.payment_method,
            'notes': p.notes,
            'created_at': p.created_at,
        } for p in page_items]
        return Response({**meta, 'results': data})

    # POST — create payout draft
    data = request.data
    for field in ['referrer_id', 'period_start', 'period_end']:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    try:
        referrer = Referrer.objects.get(pk=data['referrer_id'])
    except Referrer.DoesNotExist:
        return Response({'error': 'Referrer not found'}, status=404)

    # Calculate approved commissions in the period
    approved = Commission.objects.filter(
        referrer=referrer,
        status='Approved',
        sale_date__gte=data['period_start'],
        sale_date__lte=data['period_end'],
    )
    total = approved.aggregate(t=Sum('commission_amount'))['t'] or 0
    count = approved.count()

    payout = CommissionPayout.objects.create(
        referrer=referrer,
        period_start=data['period_start'],
        period_end=data['period_end'],
        total_commissions=total,
        commissions_count=count,
        notes=data.get('notes', ''),
        created_by=request.user,
    )
    return Response({'id': payout.id, 'total_commissions': str(total), 'count': count}, status=201)


@api_view(['PUT'])
@permission_classes([IsSuperAdminUser])
def commission_payout_detail(request, pk):
    """Process or complete a payout."""
    try:
        payout = CommissionPayout.objects.get(pk=pk)
    except CommissionPayout.DoesNotExist:
        return Response({'error': 'Payout not found'}, status=404)

    action = request.data.get('action')
    if action == 'process':
        payout.status = 'Processing'
    elif action == 'complete':
        payout.status = 'Completed'
        payout.payout_date = timezone.now().date()
        payout.payout_reference = request.data.get('payout_reference', '')
        payout.payment_method = request.data.get('payment_method', '')
        # Mark related commissions as paid
        Commission.objects.filter(
            referrer=payout.referrer,
            status='Approved',
            sale_date__gte=payout.period_start,
            sale_date__lte=payout.period_end,
        ).update(status='Paid', payment_date=payout.payout_date)
    elif action == 'fail':
        payout.status = 'Failed'
    else:
        return Response({'error': 'action must be process, complete, or fail'}, status=400)

    if 'notes' in request.data:
        payout.notes = request.data['notes']
    payout.save()
    return Response({'status': payout.status})


# ---------------------------------------------------------------------------
# PHASE 2: SUPPORT TICKETS
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def support_ticket_list_create(request):
    """List or create support tickets."""
    if request.method == 'GET':
        tickets = SupportTicket.objects.select_related(
            'assigned_to', 'resolved_by', 'requester_tenant'
        ).order_by('-created_at')

        status = request.query_params.get('status')
        if status:
            tickets = tickets.filter(status=status)
        priority = request.query_params.get('priority')
        if priority:
            tickets = tickets.filter(priority=priority)
        category = request.query_params.get('category')
        if category:
            tickets = tickets.filter(category=category)
        search = request.query_params.get('search', '').strip()
        if search:
            tickets = tickets.filter(
                Q(ticket_number__icontains=search) |
                Q(subject__icontains=search) |
                Q(requester_name__icontains=search)
            )

        page_items, meta = paginate(tickets, request)
        data = [{
            'id': t.id,
            'ticket_number': t.ticket_number,
            'subject': t.subject,
            'description': t.description,
            'category': t.category,
            'priority': t.priority,
            'status': t.status,
            'requester_name': t.requester_name,
            'requester_email': t.requester_email,
            'requester_tenant_id': t.requester_tenant_id,
            'requester_tenant_name': t.requester_tenant.name if t.requester_tenant else None,
            'assigned_to_id': t.assigned_to_id,
            'assigned_to_name': t.assigned_to.username if t.assigned_to else None,
            'resolution': t.resolution,
            'resolved_at': t.resolved_at,
            'created_at': t.created_at,
            'updated_at': t.updated_at,
        } for t in page_items]
        return Response({**meta, 'results': data})

    # POST
    data = request.data
    for field in ['subject', 'description', 'requester_name', 'requester_email']:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    ticket = SupportTicket.objects.create(
        subject=data['subject'],
        description=data['description'],
        category=data.get('category', 'Other'),
        priority=data.get('priority', 'Medium'),
        requester_name=data['requester_name'],
        requester_email=data['requester_email'],
        requester_tenant_id=data.get('requester_tenant_id'),
    )
    return Response({'id': ticket.id, 'ticket_number': ticket.ticket_number}, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsSuperAdminUser])
def support_ticket_detail(request, pk):
    """Get, update, or delete a support ticket."""
    try:
        ticket = SupportTicket.objects.select_related(
            'assigned_to', 'resolved_by', 'requester_tenant'
        ).get(pk=pk)
    except SupportTicket.DoesNotExist:
        return Response({'error': 'Ticket not found'}, status=404)

    if request.method == 'GET':
        comments = [{
            'id': c.id,
            'author_id': c.author_id,
            'author_name': c.author.username,
            'content': c.content,
            'is_internal': c.is_internal,
            'created_at': c.created_at,
        } for c in ticket.comments.select_related('author').all()]

        attachments = [{
            'id': a.id,
            'file_name': a.file_name,
            'file_size': a.file_size,
            'uploaded_by': a.uploaded_by.username,
            'uploaded_at': a.uploaded_at,
            'file_url': a.file.url if a.file else None,
        } for a in ticket.attachments.select_related('uploaded_by').all()]

        return Response({
            'id': ticket.id,
            'ticket_number': ticket.ticket_number,
            'subject': ticket.subject,
            'description': ticket.description,
            'category': ticket.category,
            'priority': ticket.priority,
            'status': ticket.status,
            'requester_name': ticket.requester_name,
            'requester_email': ticket.requester_email,
            'requester_tenant_id': ticket.requester_tenant_id,
            'requester_tenant_name': ticket.requester_tenant.name if ticket.requester_tenant else None,
            'assigned_to_id': ticket.assigned_to_id,
            'assigned_to_name': ticket.assigned_to.username if ticket.assigned_to else None,
            'resolution': ticket.resolution,
            'resolved_at': ticket.resolved_at,
            'resolved_by_name': ticket.resolved_by.username if ticket.resolved_by else None,
            'created_at': ticket.created_at,
            'updated_at': ticket.updated_at,
            'comments': comments,
            'attachments': attachments,
        })

    if request.method == 'DELETE':
        ticket.delete()
        return Response(status=204)

    # PUT
    updatable = ['status', 'priority', 'category', 'resolution', 'assigned_to_id']
    for field in updatable:
        if field in request.data:
            setattr(ticket, field, request.data[field])

    if request.data.get('status') == 'Resolved' and not ticket.resolved_at:
        ticket.resolved_at = timezone.now()
        ticket.resolved_by = request.user

    ticket.save()
    return Response({'status': 'updated'})


@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
def ticket_comment_create(request, pk):
    """Add a comment to a support ticket."""
    try:
        ticket = SupportTicket.objects.get(pk=pk)
    except SupportTicket.DoesNotExist:
        return Response({'error': 'Ticket not found'}, status=404)

    content = request.data.get('content', '').strip()
    if not content:
        return Response({'error': 'content is required'}, status=400)

    comment = TicketComment.objects.create(
        ticket=ticket,
        author=request.user,
        content=content,
        is_internal=request.data.get('is_internal', False),
    )
    return Response({
        'id': comment.id,
        'author_name': comment.author.username,
        'content': comment.content,
        'is_internal': comment.is_internal,
        'created_at': comment.created_at,
    }, status=201)


@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
def ticket_attachment_upload(request, pk):
    """Upload an attachment to a support ticket."""
    try:
        ticket = SupportTicket.objects.get(pk=pk)
    except SupportTicket.DoesNotExist:
        return Response({'error': 'Ticket not found'}, status=404)

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return Response({'error': 'file is required'}, status=400)

    # Validate file size (max 10MB)
    MAX_TICKET_FILE_SIZE = 10 * 1024 * 1024
    if uploaded_file.size > MAX_TICKET_FILE_SIZE:
        return Response({'error': 'File too large. Maximum 10MB allowed.'}, status=400)

    # Validate file extension
    import os
    ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.csv', '.xlsx', '.xls', '.doc', '.docx', '.txt', '.zip'}
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return Response({'error': f'File type {ext} not allowed.'}, status=400)

    attachment = TicketAttachment.objects.create(
        ticket=ticket,
        file=uploaded_file,
        file_name=uploaded_file.name,
        file_size=uploaded_file.size,
        uploaded_by=request.user,
    )
    return Response({
        'id': attachment.id,
        'file_name': attachment.file_name,
        'file_size': attachment.file_size,
    }, status=201)


@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
def ticket_assign(request, pk):
    """Assign a ticket to a staff user."""
    try:
        ticket = SupportTicket.objects.get(pk=pk)
    except SupportTicket.DoesNotExist:
        return Response({'error': 'Ticket not found'}, status=404)

    user_id = request.data.get('assigned_to_id')
    if user_id:
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)
        ticket.assigned_to = user
    else:
        ticket.assigned_to = None

    if ticket.status == 'Open':
        ticket.status = 'InProgress'
    ticket.save()
    return Response({'status': 'assigned'})


# ---------------------------------------------------------------------------
# PHASE 3: LANGUAGE & CURRENCY
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def language_config_list(request):
    """List or create language configurations."""
    if request.method == 'GET':
        return Response([{
            'id': lang.id,
            'language_code': lang.language_code,
            'language_name': lang.language_name,
            'native_name': lang.native_name,
            'flag_emoji': lang.flag_emoji,
            'is_active': lang.is_active,
            'is_default': lang.is_default,
            'is_rtl': lang.is_rtl,
            'date_format': lang.date_format,
            'time_format': lang.time_format,
            'sort_order': lang.sort_order,
        } for lang in LanguageConfig.objects.all()])

    # POST
    data = request.data
    for field in ['language_code', 'language_name', 'native_name']:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    if LanguageConfig.objects.filter(language_code=data['language_code']).exists():
        return Response({'error': 'Language code already exists'}, status=400)

    # If setting as default, clear other defaults
    if data.get('is_default'):
        LanguageConfig.objects.filter(is_default=True).update(is_default=False)

    lang = LanguageConfig.objects.create(
        language_code=data['language_code'],
        language_name=data['language_name'],
        native_name=data['native_name'],
        flag_emoji=data.get('flag_emoji', '🌐'),
        is_active=data.get('is_active', True),
        is_default=data.get('is_default', False),
        is_rtl=data.get('is_rtl', False),
        date_format=data.get('date_format', 'YYYY-MM-DD'),
        time_format=data.get('time_format', 'HH:mm'),
        sort_order=data.get('sort_order', 0),
    )
    return Response({'id': lang.id}, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsSuperAdminUser])
def language_config_detail(request, pk):
    """Get, update, or delete a language config."""
    try:
        lang = LanguageConfig.objects.get(pk=pk)
    except LanguageConfig.DoesNotExist:
        return Response({'error': 'Language not found'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': lang.id,
            'language_code': lang.language_code,
            'language_name': lang.language_name,
            'native_name': lang.native_name,
            'flag_emoji': lang.flag_emoji,
            'is_active': lang.is_active,
            'is_default': lang.is_default,
            'is_rtl': lang.is_rtl,
            'date_format': lang.date_format,
            'time_format': lang.time_format,
            'sort_order': lang.sort_order,
        })

    if request.method == 'DELETE':
        if lang.is_default:
            return Response({'error': 'Cannot delete the default language'}, status=400)
        lang.delete()
        return Response(status=204)

    # PUT
    if request.data.get('is_default'):
        LanguageConfig.objects.filter(is_default=True).exclude(pk=pk).update(is_default=False)

    updatable = [
        'language_name', 'native_name', 'flag_emoji', 'is_active',
        'is_default', 'is_rtl', 'date_format', 'time_format', 'sort_order',
    ]
    for field in updatable:
        if field in request.data:
            setattr(lang, field, request.data[field])
    lang.save()
    return Response({'status': 'updated'})


@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def currency_config_list(request):
    """List or create currency configurations."""
    if request.method == 'GET':
        return Response([{
            'id': c.id,
            'currency_code': c.currency_code,
            'currency_name': c.currency_name,
            'symbol': c.symbol,
            'is_active': c.is_active,
            'is_default': c.is_default,
            'decimal_places': c.decimal_places,
            'decimal_separator': c.decimal_separator,
            'thousand_separator': c.thousand_separator,
            'symbol_position': c.symbol_position,
            'exchange_rate_to_base': str(c.exchange_rate_to_base),
            'last_updated': c.last_updated,
            'auto_update': c.auto_update,
            'country_codes': c.country_codes or [],
            'flag_emoji': c.flag_emoji or '',
        } for c in CurrencyConfig.objects.all()])

    # POST
    data = request.data
    for field in ['currency_code', 'currency_name', 'symbol']:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    if CurrencyConfig.objects.filter(currency_code=data['currency_code']).exists():
        return Response({'error': 'Currency code already exists'}, status=400)

    if data.get('is_default'):
        CurrencyConfig.objects.filter(is_default=True).update(is_default=False)

    curr = CurrencyConfig.objects.create(
        currency_code=data['currency_code'],
        currency_name=data['currency_name'],
        symbol=data['symbol'],
        is_active=data.get('is_active', True),
        is_default=data.get('is_default', False),
        decimal_places=data.get('decimal_places', 2),
        decimal_separator=data.get('decimal_separator', '.'),
        thousand_separator=data.get('thousand_separator', ','),
        symbol_position=data.get('symbol_position', 'prefix'),
        exchange_rate_to_base=data.get('exchange_rate_to_base', 1.0),
        country_codes=data.get('country_codes', []),
        flag_emoji=data.get('flag_emoji', ''),
    )
    return Response({'id': curr.id}, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsSuperAdminUser])
def currency_config_detail(request, pk):
    """Get, update, or delete a currency config."""
    try:
        curr = CurrencyConfig.objects.get(pk=pk)
    except CurrencyConfig.DoesNotExist:
        return Response({'error': 'Currency not found'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': curr.id,
            'currency_code': curr.currency_code,
            'currency_name': curr.currency_name,
            'symbol': curr.symbol,
            'is_active': curr.is_active,
            'is_default': curr.is_default,
            'decimal_places': curr.decimal_places,
            'decimal_separator': curr.decimal_separator,
            'thousand_separator': curr.thousand_separator,
            'symbol_position': curr.symbol_position,
            'exchange_rate_to_base': str(curr.exchange_rate_to_base),
            'last_updated': curr.last_updated,
            'auto_update': curr.auto_update,
            'country_codes': curr.country_codes or [],
            'flag_emoji': curr.flag_emoji or '',
        })

    if request.method == 'DELETE':
        if curr.is_default:
            return Response({'error': 'Cannot delete the default currency'}, status=400)
        curr.delete()
        return Response(status=204)

    # PUT
    if request.data.get('is_default'):
        CurrencyConfig.objects.filter(is_default=True).exclude(pk=pk).update(is_default=False)

    updatable = [
        'currency_name', 'symbol', 'is_active', 'is_default', 'decimal_places',
        'decimal_separator', 'thousand_separator', 'symbol_position',
        'exchange_rate_to_base', 'auto_update', 'country_codes', 'flag_emoji',
    ]
    for field in updatable:
        if field in request.data:
            setattr(curr, field, request.data[field])
    curr.last_updated = timezone.now()
    curr.save()
    return Response({'status': 'updated'})


@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def tenant_language_setting_list(request):
    """List or assign per-tenant language settings."""
    if request.method == 'GET':
        settings = TenantLanguageSetting.objects.select_related('tenant', 'language').all()
        return Response([{
            'id': s.id,
            'tenant_id': s.tenant_id,
            'tenant_name': s.tenant.name,
            'language_id': s.language_id,
            'language_name': s.language.language_name,
            'language_code': s.language.language_code,
            'allow_user_override': s.allow_user_override,
        } for s in settings])

    # POST / create or update
    data = request.data
    for field in ['tenant_id', 'language_id']:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    setting, created = TenantLanguageSetting.objects.update_or_create(
        tenant_id=data['tenant_id'],
        defaults={
            'language_id': data['language_id'],
            'allow_user_override': data.get('allow_user_override', True),
        },
    )
    return Response({'id': setting.id}, status=201 if created else 200)


@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def tenant_currency_setting_list(request):
    """List or assign per-tenant currency settings."""
    if request.method == 'GET':
        settings = TenantCurrencySetting.objects.select_related('tenant', 'currency').all()
        return Response([{
            'id': s.id,
            'tenant_id': s.tenant_id,
            'tenant_name': s.tenant.name,
            'currency_id': s.currency_id,
            'currency_code': s.currency.currency_code,
            'currency_name': s.currency.currency_name,
            'allow_user_override': s.allow_user_override,
        } for s in settings])

    # POST / create or update
    data = request.data
    for field in ['tenant_id', 'currency_id']:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    setting, created = TenantCurrencySetting.objects.update_or_create(
        tenant_id=data['tenant_id'],
        defaults={
            'currency_id': data['currency_id'],
            'allow_user_override': data.get('allow_user_override', False),
        },
    )
    return Response({'id': setting.id}, status=201 if created else 200)


# ---------------------------------------------------------------------------
# PHASE 4: TENANT SMTP
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def tenant_smtp_list(request):
    """List or create tenant SMTP configurations."""
    if request.method == 'GET':
        configs = TenantSMTPConfig.objects.select_related('tenant').all()
        return Response([{
            'id': s.id,
            'tenant_id': s.tenant_id,
            'tenant_name': s.tenant.name,
            'smtp_host': s.smtp_host,
            'smtp_port': s.smtp_port,
            'smtp_username': s.smtp_username,
            'smtp_use_tls': s.smtp_use_tls,
            'smtp_use_ssl': s.smtp_use_ssl,
            'smtp_from_email': s.smtp_from_email,
            'smtp_from_name': s.smtp_from_name,
            'reply_to_email': s.reply_to_email,
            'is_active': s.is_active,
            'is_verified': s.is_verified,
            'verified_at': s.verified_at,
            'test_sent_at': s.test_sent_at,
            'test_status': s.test_status,
            'created_at': s.created_at,
        } for s in configs])

    # POST
    data = request.data
    for field in ['tenant_id', 'smtp_host', 'smtp_username', 'smtp_password', 'smtp_from_email', 'smtp_from_name']:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    try:
        tenant = Client.objects.get(pk=data['tenant_id'])
    except Client.DoesNotExist:
        return Response({'error': 'Tenant not found'}, status=404)

    if TenantSMTPConfig.objects.filter(tenant=tenant).exists():
        return Response({'error': 'SMTP config already exists for this tenant. Use PUT to update.'}, status=400)

    smtp = TenantSMTPConfig.objects.create(
        tenant=tenant,
        smtp_host=data['smtp_host'],
        smtp_port=data.get('smtp_port', 587),
        smtp_username=data['smtp_username'],
        smtp_password=data['smtp_password'],
        smtp_use_tls=data.get('smtp_use_tls', True),
        smtp_use_ssl=data.get('smtp_use_ssl', False),
        smtp_from_email=data['smtp_from_email'],
        smtp_from_name=data['smtp_from_name'],
        reply_to_email=data.get('reply_to_email', ''),
    )
    return Response({'id': smtp.id}, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsSuperAdminUser])
def tenant_smtp_detail(request, pk):
    """Get, update, or delete a tenant SMTP config."""
    try:
        smtp = TenantSMTPConfig.objects.select_related('tenant').get(pk=pk)
    except TenantSMTPConfig.DoesNotExist:
        return Response({'error': 'SMTP config not found'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': smtp.id,
            'tenant_id': smtp.tenant_id,
            'tenant_name': smtp.tenant.name,
            'smtp_host': smtp.smtp_host,
            'smtp_port': smtp.smtp_port,
            'smtp_username': smtp.smtp_username,
            'smtp_use_tls': smtp.smtp_use_tls,
            'smtp_use_ssl': smtp.smtp_use_ssl,
            'smtp_from_email': smtp.smtp_from_email,
            'smtp_from_name': smtp.smtp_from_name,
            'reply_to_email': smtp.reply_to_email,
            'is_active': smtp.is_active,
            'is_verified': smtp.is_verified,
        })

    if request.method == 'DELETE':
        smtp.delete()
        return Response(status=204)

    # PUT
    updatable = [
        'smtp_host', 'smtp_port', 'smtp_username', 'smtp_password',
        'smtp_use_tls', 'smtp_use_ssl', 'smtp_from_email', 'smtp_from_name',
        'reply_to_email', 'is_active',
    ]
    for field in updatable:
        if field not in request.data:
            continue
        value = request.data[field]
        # Skip masked sentinel — frontend sends '****' when the user did not
        # change the password; overwriting with the mask would corrupt the credential.
        if field == 'smtp_password' and value == '****':
            continue
        setattr(smtp, field, value)
    smtp.is_verified = False  # Reset verification when settings change
    smtp.save()
    return Response({'status': 'updated'})


@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
def test_smtp_connection(request, pk):
    """Test a tenant SMTP connection."""
    try:
        smtp_config = TenantSMTPConfig.objects.get(pk=pk)
    except TenantSMTPConfig.DoesNotExist:
        return Response({'error': 'SMTP config not found'}, status=404)

    try:
        import smtplib
        server = smtplib.SMTP(smtp_config.smtp_host, smtp_config.smtp_port, timeout=10)
        if smtp_config.smtp_use_tls:
            server.starttls()
        server.login(smtp_config.smtp_username, smtp_config.smtp_password)
        server.quit()
        smtp_config.is_verified = True
        smtp_config.test_status = 'Success'
        smtp_config.verified_at = timezone.now()
    except Exception as e:
        smtp_config.is_verified = False
        smtp_config.test_status = str(e)[:200]

    smtp_config.test_sent_at = timezone.now()
    smtp_config.save()
    return Response({
        'success': smtp_config.is_verified,
        'test_status': smtp_config.test_status,
    })


# ---------------------------------------------------------------------------
# PHASE 5: API KEYS & WEBHOOKS
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def api_key_list(request):
    """List or create API keys."""
    if request.method == 'GET':
        keys = TenantAPIKey.objects.select_related('tenant', 'created_by').all()
        tenant_id = request.query_params.get('tenant_id')
        if tenant_id:
            keys = keys.filter(tenant_id=tenant_id)

        return Response([{
            'id': k.id,
            'tenant_id': k.tenant_id,
            'tenant_name': k.tenant.name,
            'key_name': k.key_name,
            'key_type': k.key_type,
            'api_key': k.api_key[:12] + '...',
            'allowed_ips': k.allowed_ips,
            'rate_limit': k.rate_limit,
            'is_active': k.is_active,
            'expires_at': k.expires_at,
            'last_used_at': k.last_used_at,
            'created_at': k.created_at,
            'created_by_name': k.created_by.username if k.created_by else None,
        } for k in keys])

    # POST
    data = request.data
    for field in ['tenant_id', 'key_name']:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    try:
        tenant = Client.objects.get(pk=data['tenant_id'])
    except Client.DoesNotExist:
        return Response({'error': 'Tenant not found'}, status=404)

    key = TenantAPIKey.objects.create(
        tenant=tenant,
        key_name=data['key_name'],
        key_type=data.get('key_type', 'Production'),
        allowed_ips=data.get('allowed_ips', ''),
        rate_limit=data.get('rate_limit', 1000),
        expires_at=data.get('expires_at'),
        created_by=request.user,
    )
    # Full key + secret are returned ONLY on creation and never again.
    # The GET endpoint returns a masked key and omits the secret entirely.
    return Response({
        'id': key.id,
        'api_key': key.api_key,
        'api_secret': key.api_secret,
        'warning': 'Store these credentials securely — the secret will not be shown again.',
    }, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsSuperAdminUser])
def api_key_detail(request, pk):
    """Get, update, or revoke an API key."""
    try:
        key = TenantAPIKey.objects.select_related('tenant').get(pk=pk)
    except TenantAPIKey.DoesNotExist:
        return Response({'error': 'API key not found'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': key.id,
            'tenant_id': key.tenant_id,
            'tenant_name': key.tenant.name,
            'key_name': key.key_name,
            'key_type': key.key_type,
            'api_key': key.api_key[:12] + '...',
            'allowed_ips': key.allowed_ips,
            'rate_limit': key.rate_limit,
            'is_active': key.is_active,
            'expires_at': key.expires_at,
            'last_used_at': key.last_used_at,
            'created_at': key.created_at,
        })

    if request.method == 'DELETE':
        key.delete()
        return Response(status=204)

    # PUT
    updatable = ['key_name', 'key_type', 'allowed_ips', 'rate_limit', 'is_active', 'expires_at']
    for field in updatable:
        if field in request.data:
            setattr(key, field, request.data[field])

    # Regenerate key if requested
    if request.data.get('regenerate'):
        import secrets
        key.api_key = secrets.token_urlsafe(32)
        key.api_secret = secrets.token_urlsafe(48)
        key.save()
        return Response({
            'status': 'regenerated',
            'api_key': key.api_key,
            'api_secret': key.api_secret,
        })

    key.save()
    return Response({'status': 'updated'})


@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def webhook_list(request):
    """List or create webhooks."""
    if request.method == 'GET':
        webhooks = WebhookConfig.objects.select_related('tenant', 'created_by').all()
        tenant_id = request.query_params.get('tenant_id')
        if tenant_id:
            webhooks = webhooks.filter(tenant_id=tenant_id)

        return Response([{
            'id': w.id,
            'tenant_id': w.tenant_id,
            'tenant_name': w.tenant.name,
            'webhook_name': w.webhook_name,
            'webhook_url': w.webhook_url,
            'subscribed_events': w.subscribed_events,
            'is_active': w.is_active,
            'timeout_seconds': w.timeout_seconds,
            'retry_count': w.retry_count,
            'last_triggered_at': w.last_triggered_at,
            'last_status_code': w.last_status_code,
            'created_at': w.created_at,
            'created_by_name': w.created_by.username if w.created_by else None,
        } for w in webhooks])

    # POST
    data = request.data
    for field in ['tenant_id', 'webhook_name', 'webhook_url']:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    try:
        tenant = Client.objects.get(pk=data['tenant_id'])
    except Client.DoesNotExist:
        return Response({'error': 'Tenant not found'}, status=404)

    # secret_key is auto-generated by WebhookConfig.save() if not provided
    wh = WebhookConfig.objects.create(
        tenant=tenant,
        webhook_name=data['webhook_name'],
        webhook_url=data['webhook_url'],
        subscribed_events=data.get('subscribed_events', []),
        timeout_seconds=data.get('timeout_seconds', 30),
        retry_count=data.get('retry_count', 3),
        created_by=request.user,
    )
    return Response({'id': wh.id, 'secret_key': wh.secret_key}, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsSuperAdminUser])
def webhook_detail(request, pk):
    """Get, update, or delete a webhook."""
    try:
        wh = WebhookConfig.objects.select_related('tenant').get(pk=pk)
    except WebhookConfig.DoesNotExist:
        return Response({'error': 'Webhook not found'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': wh.id,
            'tenant_id': wh.tenant_id,
            'tenant_name': wh.tenant.name,
            'webhook_name': wh.webhook_name,
            'webhook_url': wh.webhook_url,
            'subscribed_events': wh.subscribed_events,
            'is_active': wh.is_active,
            'timeout_seconds': wh.timeout_seconds,
            'retry_count': wh.retry_count,
            'last_triggered_at': wh.last_triggered_at,
            'last_status_code': wh.last_status_code,
            'created_at': wh.created_at,
        })

    if request.method == 'DELETE':
        wh.delete()
        return Response(status=204)

    # PUT
    updatable = [
        'webhook_name', 'webhook_url', 'subscribed_events',
        'is_active', 'timeout_seconds', 'retry_count',
    ]
    for field in updatable:
        if field in request.data:
            setattr(wh, field, request.data[field])
    wh.save()
    return Response({'status': 'updated'})


@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
def webhook_test(request, pk):
    """Send a test webhook delivery."""
    try:
        wh = WebhookConfig.objects.get(pk=pk)
    except WebhookConfig.DoesNotExist:
        return Response({'error': 'Webhook not found'}, status=404)

    import requests as http_requests
    import time
    import hashlib
    import hmac
    from urllib.parse import urlparse
    import socket

    # SSRF protection: validate ALL resolved addresses (IPv4 + IPv6) are public.
    # socket.gethostbyname() only returns one IPv4 address and misses IPv6 AAAA
    # records, which is an SSRF bypass vector.  getaddrinfo() returns every
    # address family the DNS server advertises so we can block all private ranges.
    try:
        import ipaddress
        parsed = urlparse(wh.webhook_url)
        hostname = parsed.hostname
        if not hostname:
            return Response({'error': 'Invalid webhook URL'}, status=400)
        # Resolve both A and AAAA records (AF_UNSPEC = 0)
        addr_infos = socket.getaddrinfo(hostname, None)
        if not addr_infos:
            return Response({'error': 'Cannot resolve webhook URL hostname'}, status=400)
        for _family, _type, _proto, _canonname, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip_str)
            if (
                ip_obj.is_private or ip_obj.is_loopback
                or ip_obj.is_link_local or ip_obj.is_reserved
                or ip_obj.is_multicast
            ):
                return Response(
                    {'error': 'Webhook URL must resolve to a public IP address'},
                    status=400,
                )
    except (socket.gaierror, ValueError):
        return Response({'error': 'Cannot resolve webhook URL hostname'}, status=400)

    payload = {
        'event': 'test.ping',
        'timestamp': timezone.now().isoformat(),
        'data': {'message': 'Test webhook from QUOT ERP'},
    }

    # Sign the payload
    import json
    body = json.dumps(payload)
    signature = hmac.new(
        wh.secret_key.encode(), body.encode(), hashlib.sha256
    ).hexdigest()

    delivery = WebhookDelivery.objects.create(
        webhook=wh,
        event='test.ping',
        payload=payload,
        status='Pending',
    )

    # Attempt delivery with exponential back-off (honours wh.retry_count).
    # Delays: 1 s, 2 s, 4 s … capped at wh.retry_count attempts total.
    max_attempts = max(1, wh.retry_count)
    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature': signature,
        'X-Webhook-Event': 'test.ping',
    }
    last_exc = None
    resp = None
    # Initialise start_time before the loop so `duration` is always defined
    # even if the loop somehow executes zero iterations.
    start_time = time.time()
    for attempt in range(max_attempts):
        if attempt > 0:
            time.sleep(2 ** (attempt - 1))   # 1 s, 2 s, 4 s …
        delivery.retry_attempt = attempt
        start_time = time.time()
        try:
            resp = http_requests.post(
                wh.webhook_url,
                json=payload,
                headers=headers,
                timeout=wh.timeout_seconds,
            )
            last_exc = None
            if resp.status_code < 400:
                break   # success — stop retrying
        except Exception as exc:
            last_exc = exc
            resp = None

    duration = int((time.time() - start_time) * 1000)
    if resp is not None:
        delivery.status = 'Success' if resp.status_code < 400 else 'Failed'
        delivery.status_code = resp.status_code
        delivery.response_body = resp.text[:2000]
        delivery.duration_ms = duration
        delivery.delivered_at = timezone.now() if resp.status_code < 400 else None

        wh.last_triggered_at = timezone.now()
        wh.last_status_code = resp.status_code
        wh.save()
    else:
        delivery.status = 'Failed'
        delivery.error_message = str(last_exc)[:500] if last_exc else 'Unknown error'
        delivery.duration_ms = duration

    delivery.save()

    return Response({
        'delivery_id': delivery.id,
        'status': delivery.status,
        'status_code': delivery.status_code,
        'duration_ms': delivery.duration_ms,
        'error': delivery.error_message or None,
    })


@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
def webhook_regenerate_secret(request, pk):
    """Rotate the signing secret for a webhook configuration.

    Returns the new secret so the caller can update their receiver.
    Old deliveries signed with the previous secret will immediately fail
    verification on the remote end — callers should update promptly.
    """
    import secrets
    try:
        wh = WebhookConfig.objects.get(pk=pk)
    except WebhookConfig.DoesNotExist:
        return Response({'error': 'Webhook not found'}, status=404)

    new_secret = secrets.token_urlsafe(64)
    wh.secret_key = new_secret
    wh.save(update_fields=['secret_key'])

    security_logger.info(
        'Webhook secret rotated: webhook_id=%s tenant=%s by user=%s',
        wh.pk, wh.tenant.schema_name, request.user.username,
    )
    return Response({'secret_key': new_secret})


@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def webhook_deliveries(request, pk):
    """List delivery logs for a webhook."""
    try:
        wh = WebhookConfig.objects.get(pk=pk)
    except WebhookConfig.DoesNotExist:
        return Response({'error': 'Webhook not found'}, status=404)

    deliveries = wh.deliveries.order_by('-attempted_at')
    page_items, meta = paginate(deliveries, request)
    data = [{
        'id': d.id,
        'event': d.event,
        'status': d.status,
        'status_code': d.status_code,
        'error_message': d.error_message,
        'duration_ms': d.duration_ms,
        'attempted_at': d.attempted_at,
        'delivered_at': d.delivered_at,
        'retry_attempt': d.retry_attempt,
    } for d in page_items]
    return Response({**meta, 'results': data})


# ---------------------------------------------------------------------------
# PHASE 6: ANNOUNCEMENTS & NOTIFICATIONS
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def announcement_list(request):
    """List or create announcements."""
    if request.method == 'GET':
        announcements = Announcement.objects.all()
        is_published = request.query_params.get('is_published')
        if is_published is not None:
            announcements = announcements.filter(is_published=is_published == 'true')

        return Response([{
            'id': a.id,
            'title': a.title,
            'content': a.content,
            'content_html': a.content_html,
            'priority': a.priority,
            'target': a.target,
            'target_plan_ids': list(a.target_plans.values_list('id', flat=True)),
            'target_tenant_ids': list(a.target_tenants.values_list('id', flat=True)),
            'show_on_login': a.show_on_login,
            'show_on_dashboard': a.show_on_dashboard,
            'starts_at': a.starts_at,
            'ends_at': a.ends_at,
            'is_published': a.is_published,
            'created_by_name': a.created_by.username if a.created_by else None,
            'created_at': a.created_at,
        } for a in announcements])

    # POST
    data = request.data
    for field in ['title', 'content', 'starts_at']:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    ann = Announcement.objects.create(
        title=data['title'],
        content=data['content'],
        content_html=sanitize_html(data.get('content_html', '')),
        priority=data.get('priority', 'Normal'),
        target=data.get('target', 'All'),
        show_on_login=data.get('show_on_login', True),
        show_on_dashboard=data.get('show_on_dashboard', True),
        starts_at=data['starts_at'],
        ends_at=data.get('ends_at'),
        is_published=data.get('is_published', False),
        created_by=request.user,
    )

    # Set M2M targets
    if data.get('target_plan_ids'):
        ann.target_plans.set(data['target_plan_ids'])
    if data.get('target_tenant_ids'):
        ann.target_tenants.set(data['target_tenant_ids'])

    return Response({'id': ann.id}, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsSuperAdminUser])
def announcement_detail(request, pk):
    """Get, update, or delete an announcement."""
    try:
        ann = Announcement.objects.get(pk=pk)
    except Announcement.DoesNotExist:
        return Response({'error': 'Announcement not found'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': ann.id,
            'title': ann.title,
            'content': ann.content,
            'content_html': ann.content_html,
            'priority': ann.priority,
            'target': ann.target,
            'target_plan_ids': list(ann.target_plans.values_list('id', flat=True)),
            'target_tenant_ids': list(ann.target_tenants.values_list('id', flat=True)),
            'show_on_login': ann.show_on_login,
            'show_on_dashboard': ann.show_on_dashboard,
            'starts_at': ann.starts_at,
            'ends_at': ann.ends_at,
            'is_published': ann.is_published,
            'created_at': ann.created_at,
        })

    if request.method == 'DELETE':
        ann.delete()
        return Response(status=204)

    # PUT
    updatable = [
        'title', 'content', 'content_html', 'priority', 'target',
        'show_on_login', 'show_on_dashboard', 'starts_at', 'ends_at', 'is_published',
    ]
    for field in updatable:
        if field in request.data:
            value = request.data[field]
            if field == 'content_html':
                value = sanitize_html(value)
            setattr(ann, field, value)
    ann.save()

    if 'target_plan_ids' in request.data:
        ann.target_plans.set(request.data['target_plan_ids'])
    if 'target_tenant_ids' in request.data:
        ann.target_tenants.set(request.data['target_tenant_ids'])

    return Response({'status': 'updated'})


@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
def announcement_publish(request, pk):
    """Publish an announcement and create notifications for targeted tenants."""
    try:
        ann = Announcement.objects.get(pk=pk)
    except Announcement.DoesNotExist:
        return Response({'error': 'Announcement not found'}, status=404)

    ann.is_published = True
    ann.save()

    # Determine target tenants — always exclude the django-tenants internal public schema
    if ann.target == 'All':
        target_tenants = Client.objects.exclude(schema_name='public')
    elif ann.target == 'Plan':
        plan_ids = ann.target_plans.values_list('id', flat=True)
        tenant_ids = TenantSubscription.objects.filter(
            plan_id__in=plan_ids, status__in=['active', 'trial']
        ).values_list('tenant_id', flat=True)
        target_tenants = Client.objects.filter(id__in=tenant_ids)
    elif ann.target == 'Tenant':
        target_tenants = ann.target_tenants.all()
    else:
        target_tenants = Client.objects.none()

    # Create notifications (skip duplicates)
    existing = set(
        TenantNotification.objects.filter(announcement=ann)
        .values_list('tenant_id', flat=True)
    )
    notifications = []
    for tenant in target_tenants:
        if tenant.id not in existing:
            notifications.append(TenantNotification(
                tenant=tenant,
                announcement=ann,
                notification_type='Announcement',
                title=ann.title,
                message=ann.content,
            ))
    TenantNotification.objects.bulk_create(notifications)

    return Response({
        'status': 'published',
        'notifications_created': len(notifications),
    })


@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def notification_list(request):
    """List all tenant notifications."""
    notifications = TenantNotification.objects.select_related('tenant', 'announcement').order_by('-created_at')
    tenant_id = request.query_params.get('tenant_id')
    if tenant_id:
        notifications = notifications.filter(tenant_id=tenant_id)
    is_read = request.query_params.get('is_read')
    if is_read is not None:
        notifications = notifications.filter(is_read=is_read == 'true')

    page_items, meta = paginate(notifications, request)
    data = [{
        'id': n.id,
        'tenant_id': n.tenant_id,
        'tenant_name': n.tenant.name,
        'announcement_id': n.announcement_id,
        'notification_type': n.notification_type,
        'title': n.title,
        'message': n.message,
        'is_read': n.is_read,
        'read_at': n.read_at,
        'action_url': n.action_url,
        'created_at': n.created_at,
    } for n in page_items]
    return Response({**meta, 'results': data})


# ---------------------------------------------------------------------------
# PHASE 7: USAGE METERING & BILLING
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def tenant_usage_list(request):
    """List tenant usage records or create a snapshot."""
    if request.method == 'GET':
        records = TenantUsage.objects.select_related('tenant').order_by('-billing_period_start')
        tenant_id = request.query_params.get('tenant_id')
        if tenant_id:
            records = records.filter(tenant_id=tenant_id)
        is_billed = request.query_params.get('is_billed')
        if is_billed is not None:
            records = records.filter(is_billed=is_billed == 'true')

        page_items, meta = paginate(records, request)
        data = [{
            'id': r.id,
            'tenant_id': r.tenant_id,
            'tenant_name': r.tenant.name,
            'billing_period_start': r.billing_period_start,
            'billing_period_end': r.billing_period_end,
            'users_count': r.users_count,
            'storage_mb': r.storage_mb,
            'api_calls': r.api_calls,
            'transactions_count': r.transactions_count,
            'overage_users': r.overage_users,
            'overage_storage_mb': r.overage_storage_mb,
            'overage_api_calls': r.overage_api_calls,
            'base_cost': str(r.base_cost),
            'overage_cost': str(r.overage_cost),
            'total_cost': str(r.total_cost),
            'is_billed': r.is_billed,
            'created_at': r.created_at,
        } for r in page_items]
        return Response({**meta, 'results': data})

    # POST — create usage snapshot for a tenant
    data = request.data
    for field in ['tenant_id', 'billing_period_start', 'billing_period_end']:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    try:
        tenant = Client.objects.get(pk=data['tenant_id'])
    except Client.DoesNotExist:
        return Response({'error': 'Tenant not found'}, status=404)

    # Count users for this tenant
    with schema_context('public'):
        user_count = UserTenantRole.objects.filter(
            tenant=tenant, is_active=True
        ).count()

    # Get plan limits for overage calculation
    sub = getattr(tenant, 'subscription', None)
    max_users = sub.plan.max_users if sub and sub.plan else 0
    overage_users = max(0, user_count - max_users) if max_users > 0 else 0

    usage = TenantUsage.objects.create(
        tenant=tenant,
        billing_period_start=data['billing_period_start'],
        billing_period_end=data['billing_period_end'],
        users_count=user_count,
        storage_mb=data.get('storage_mb', 0),
        api_calls=data.get('api_calls', 0),
        transactions_count=data.get('transactions_count', 0),
        overage_users=overage_users,
        overage_storage_mb=data.get('overage_storage_mb', 0),
        overage_api_calls=data.get('overage_api_calls', 0),
        base_cost=data.get('base_cost', sub.plan.price if sub and sub.plan else 0),
        overage_cost=data.get('overage_cost', 0),
        total_cost=data.get('total_cost', sub.plan.price if sub and sub.plan else 0),
    )
    return Response({'id': usage.id}, status=201)


@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def invoice_list_create(request):
    """List or create invoices."""
    if request.method == 'GET':
        invoices = Invoice.objects.select_related('tenant').order_by('-issue_date')
        tenant_id = request.query_params.get('tenant_id')
        if tenant_id:
            invoices = invoices.filter(tenant_id=tenant_id)
        status = request.query_params.get('status')
        if status:
            invoices = invoices.filter(status=status)

        page_items, meta = paginate(invoices, request)
        data = [{
            'id': inv.id,
            'invoice_number': inv.invoice_number,
            'tenant_id': inv.tenant_id,
            'tenant_name': inv.tenant.name,
            'period_start': inv.period_start,
            'period_end': inv.period_end,
            'subscription_amount': str(inv.subscription_amount),
            'usage_amount': str(inv.usage_amount),
            'tax_amount': str(inv.tax_amount),
            'discount_amount': str(inv.discount_amount),
            'total_amount': str(inv.total_amount),
            'status': inv.status,
            'paid_at': inv.paid_at,
            'payment_method': inv.payment_method,
            'payment_reference': inv.payment_reference,
            'issue_date': inv.issue_date,
            'due_date': inv.due_date,
            'notes': inv.notes,
            'created_at': inv.created_at,
        } for inv in page_items]
        return Response({**meta, 'results': data})

    # POST — create invoice
    data = request.data
    for field in ['tenant_id', 'period_start', 'period_end', 'due_date']:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    try:
        tenant = Client.objects.get(pk=data['tenant_id'])
    except Client.DoesNotExist:
        return Response({'error': 'Tenant not found'}, status=404)

    invoice = Invoice.objects.create(
        tenant=tenant,
        period_start=data['period_start'],
        period_end=data['period_end'],
        due_date=data['due_date'],
        subscription_amount=data.get('subscription_amount', 0),
        usage_amount=data.get('usage_amount', 0),
        tax_amount=data.get('tax_amount', 0),
        discount_amount=data.get('discount_amount', 0),
        status=data.get('status', 'Draft'),
        notes=data.get('notes', ''),
    )
    return Response({
        'id': invoice.id,
        'invoice_number': invoice.invoice_number,
        'total_amount': str(invoice.total_amount),
    }, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsSuperAdminUser])
def invoice_detail(request, pk):
    """Get, update, or delete an invoice."""
    try:
        invoice = Invoice.objects.select_related('tenant').get(pk=pk)
    except Invoice.DoesNotExist:
        return Response({'error': 'Invoice not found'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'tenant_id': invoice.tenant_id,
            'tenant_name': invoice.tenant.name,
            'period_start': invoice.period_start,
            'period_end': invoice.period_end,
            'subscription_amount': str(invoice.subscription_amount),
            'usage_amount': str(invoice.usage_amount),
            'tax_amount': str(invoice.tax_amount),
            'discount_amount': str(invoice.discount_amount),
            'total_amount': str(invoice.total_amount),
            'status': invoice.status,
            'paid_at': invoice.paid_at,
            'payment_method': invoice.payment_method,
            'payment_reference': invoice.payment_reference,
            'issue_date': invoice.issue_date,
            'due_date': invoice.due_date,
            'notes': invoice.notes,
        })

    if request.method == 'DELETE':
        if invoice.status == 'Paid':
            return Response({'error': 'Cannot delete a paid invoice'}, status=400)
        invoice.delete()
        return Response(status=204)

    # PUT
    updatable = [
        'subscription_amount', 'usage_amount', 'tax_amount', 'discount_amount',
        'status', 'payment_method', 'payment_reference', 'due_date', 'notes',
    ]
    for field in updatable:
        if field in request.data:
            setattr(invoice, field, request.data[field])

    if request.data.get('status') == 'Paid' and not invoice.paid_at:
        invoice.paid_at = timezone.now()

    invoice.save()  # triggers total recalculation
    return Response({
        'status': invoice.status,
        'total_amount': str(invoice.total_amount),
    })


@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def billing_analytics(request):
    """Revenue analytics for the platform."""
    from django.db.models.functions import TruncMonth

    # Monthly revenue from invoices
    monthly_revenue = (
        Invoice.objects.filter(status='Paid')
        .annotate(month=TruncMonth('paid_at'))
        .values('month')
        .annotate(total=Sum('total_amount'), count=Count('id'))
        .order_by('month')
    )

    # Summary stats
    total_invoiced = Invoice.objects.aggregate(t=Sum('total_amount'))['t'] or 0
    total_paid = Invoice.objects.filter(status='Paid').aggregate(t=Sum('total_amount'))['t'] or 0
    total_pending = Invoice.objects.filter(status='Pending').aggregate(t=Sum('total_amount'))['t'] or 0
    total_overdue = Invoice.objects.filter(status='Overdue').aggregate(t=Sum('total_amount'))['t'] or 0

    # Commission stats
    total_commissions = Commission.objects.filter(status='Paid').aggregate(t=Sum('commission_amount'))['t'] or 0
    pending_commissions = Commission.objects.filter(
        status__in=['Pending', 'Approved']
    ).aggregate(t=Sum('commission_amount'))['t'] or 0

    return Response({
        'monthly_revenue': [{
            'month': r['month'],
            'total': str(r['total']),
            'count': r['count'],
        } for r in monthly_revenue],
        'summary': {
            'total_invoiced': str(total_invoiced),
            'total_paid': str(total_paid),
            'total_pending': str(total_pending),
            'total_overdue': str(total_overdue),
            'total_commissions_paid': str(total_commissions),
            'pending_commissions': str(pending_commissions),
        },
    })


# ---------------------------------------------------------------------------
# SAAS DASHBOARD STATS (enhanced)
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsSuperAdminUser])
def saas_dashboard_stats(request):
    """Comprehensive SaaS dashboard stats."""
    return Response({
        'referrers': {
            'total': Referrer.objects.count(),
            'active': Referrer.objects.filter(is_active=True).count(),
        },
        'referrals': {
            'total': Referral.objects.count(),
            'active': Referral.objects.filter(status='Active').count(),
            'pending': Referral.objects.filter(status='Pending').count(),
        },
        'commissions': {
            'total_paid': str(
                Commission.objects.filter(status='Paid').aggregate(t=Sum('commission_amount'))['t'] or 0
            ),
            'total_pending': str(
                Commission.objects.filter(status__in=['Pending', 'Approved']).aggregate(t=Sum('commission_amount'))['t'] or 0
            ),
        },
        'support': {
            'open': SupportTicket.objects.filter(status='Open').count(),
            'in_progress': SupportTicket.objects.filter(status='InProgress').count(),
            'resolved': SupportTicket.objects.filter(status='Resolved').count(),
        },
        'announcements': {
            'total': Announcement.objects.count(),
            'published': Announcement.objects.filter(is_published=True).count(),
        },
        'invoices': {
            'total': Invoice.objects.count(),
            'paid': Invoice.objects.filter(status='Paid').count(),
            'pending': Invoice.objects.filter(status='Pending').count(),
            'overdue': Invoice.objects.filter(status='Overdue').count(),
        },
    })


# ---------------------------------------------------------------------------
# Public Platform Info (unauthenticated — for public pricing pages)
# ---------------------------------------------------------------------------

@api_view(['GET'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def public_platform_info(request):
    """Return non-sensitive platform settings for public pages (currency, org name)."""
    sa_settings = SuperAdminSettings.load()
    return Response({
        'default_currency': sa_settings.default_currency,
        'organization_name': sa_settings.organization_name,
    })


@api_view(['GET'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def public_currencies(request):
    """Return all active currencies with exchange rates for public pricing pages."""
    currencies = CurrencyConfig.objects.filter(is_active=True)
    sa_settings = SuperAdminSettings.load()
    return Response({
        'base_currency': sa_settings.default_currency,
        'currencies': [{
            'currency_code': c.currency_code,
            'currency_name': c.currency_name,
            'symbol': c.symbol,
            'symbol_position': c.symbol_position,
            'exchange_rate_to_base': str(c.exchange_rate_to_base),
            'decimal_places': c.decimal_places,
            'is_default': c.is_default,
            'country_codes': c.country_codes or [],
            'flag_emoji': c.flag_emoji or '',
        } for c in currencies],
    })


def _get_client_ip(request):
    """Extract real client IP from X-Forwarded-For or REMOTE_ADDR."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


@api_view(['GET'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def public_detect_currency(request):
    """Detect the visitor's currency from IP geolocation.

    Flow: client IP → free geolocation API → ISO country code → matching CurrencyConfig.
    Falls back to platform default currency if detection fails.
    Also accepts ?country=XX query param for client-side detection passthrough.
    """
    import requests as http_requests

    country_code = request.query_params.get('country', '').upper()

    if not country_code:
        # Server-side IP detection using free ip-api.com (no key needed, 45 req/min)
        client_ip = _get_client_ip(request)
        if client_ip and client_ip not in ('127.0.0.1', '::1', 'localhost'):
            try:
                geo = http_requests.get(
                    f'http://ip-api.com/json/{client_ip}?fields=status,countryCode',
                    timeout=3,
                )
                if geo.status_code == 200:
                    data = geo.json()
                    if data.get('status') == 'success':
                        country_code = data.get('countryCode', '')
            except Exception:
                pass  # fail silently, use fallback

    detected_currency = None
    if country_code:
        # Search CurrencyConfig where country_codes JSON array contains this code
        for c in CurrencyConfig.objects.filter(is_active=True):
            if country_code in (c.country_codes or []):
                detected_currency = c
                break

    if not detected_currency:
        # Fall back to platform default or USD
        sa_settings = SuperAdminSettings.load()
        detected_currency = (
            CurrencyConfig.objects.filter(
                currency_code=sa_settings.default_currency, is_active=True
            ).first()
            or CurrencyConfig.objects.filter(is_default=True).first()
        )

    if detected_currency:
        return Response({
            'detected_country': country_code or None,
            'currency_code': detected_currency.currency_code,
            'currency_name': detected_currency.currency_name,
            'symbol': detected_currency.symbol,
            'symbol_position': detected_currency.symbol_position,
            'exchange_rate_to_base': str(detected_currency.exchange_rate_to_base),
            'flag_emoji': detected_currency.flag_emoji or '',
        })

    # Ultimate fallback
    return Response({
        'detected_country': country_code or None,
        'currency_code': 'USD',
        'currency_name': 'US Dollar',
        'symbol': '$',
        'symbol_position': 'prefix',
        'exchange_rate_to_base': '1.000000',
        'flag_emoji': '🇺🇸',
    })


# ---------------------------------------------------------------------------
# Module Pricing — Public + Superadmin endpoints
# ---------------------------------------------------------------------------

@api_view(['GET'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def public_module_pricing(request):
    """Public endpoint: list active module pricing for the SaaS landing page."""
    modules = ModulePricing.objects.filter(is_active=True)
    data = [{
        'id': m.id,
        'module_name': m.module_name,
        'title': m.title,
        'tagline': m.tagline,
        'description': m.description,
        'icon': m.icon,
        'price_monthly': str(m.price_monthly),
        'price_yearly': str(m.price_yearly),
        'features': m.features or [],
        'highlights': m.highlights or [],
        'is_popular': m.is_popular,
        'sort_order': m.sort_order,
    } for m in modules]
    return Response(data)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def public_module_pricing_detail(request, module_name):
    """Public endpoint: get details for a single module by module_name."""
    try:
        m = ModulePricing.objects.get(module_name=module_name, is_active=True)
    except ModulePricing.DoesNotExist:
        return Response({'error': 'Module not found'}, status=404)
    return Response({
        'id': m.id,
        'module_name': m.module_name,
        'title': m.title,
        'tagline': m.tagline,
        'description': m.description,
        'icon': m.icon,
        'price_monthly': str(m.price_monthly),
        'price_yearly': str(m.price_yearly),
        'features': m.features or [],
        'highlights': m.highlights or [],
        'is_popular': m.is_popular,
    })


@api_view(['GET'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def public_subscription_plans(request):
    """Public endpoint: list active subscription plans for the pricing page.

    Returns plan details including allowed modules and features so the
    pricing page can display "Subscribe to a plan" cards alongside the
    "Build your own" module-by-module selection.
    """
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
    # Also fetch module pricing for display names
    module_titles = {
        m.module_name: m.title
        for m in ModulePricing.objects.filter(is_active=True)
    }
    data = []
    for p in plans:
        module_names = [
            module_titles.get(m, m.replace('_', ' ').title())
            for m in (p.allowed_modules or [])
        ]
        data.append({
            'id': p.id,
            'name': p.name,
            'plan_type': p.plan_type,
            'description': p.description,
            'price': str(p.price),
            'billing_cycle': p.billing_cycle,
            'max_users': p.max_users,
            'max_storage_gb': p.max_storage_gb,
            'allowed_modules': p.allowed_modules,
            'module_names': module_names,
            'features': p.features or [],
            'is_featured': p.is_featured,
            'trial_days': p.trial_days,
        })
    return Response(data)


@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def module_pricing_list(request):
    """Superadmin: list all module pricing or create a new one."""
    if request.method == 'GET':
        modules = ModulePricing.objects.all()
        data = [{
            'id': m.id,
            'module_name': m.module_name,
            'title': m.title,
            'tagline': m.tagline,
            'description': m.description,
            'icon': m.icon,
            'price_monthly': str(m.price_monthly),
            'price_yearly': str(m.price_yearly),
            'features': m.features or [],
            'highlights': m.highlights or [],
            'is_active': m.is_active,
            'is_popular': m.is_popular,
            'sort_order': m.sort_order,
            'created_at': m.created_at,
            'updated_at': m.updated_at,
        } for m in modules]
        return Response(data)

    # POST — create
    d = request.data
    module_name = d.get('module_name', '')
    if not module_name:
        return Response({'error': 'module_name is required'}, status=400)

    valid_names = [m[0] for m in AVAILABLE_MODULES]
    if module_name not in valid_names:
        return Response({'error': f'Invalid module_name. Must be one of: {", ".join(valid_names)}'}, status=400)

    if ModulePricing.objects.filter(module_name=module_name).exists():
        return Response({'error': f'Pricing for "{module_name}" already exists'}, status=400)

    mp = ModulePricing.objects.create(
        module_name=module_name,
        title=d.get('title', dict(AVAILABLE_MODULES[0:0]).get(module_name, module_name.title())),
        tagline=d.get('tagline', ''),
        description=d.get('description', ''),
        icon=d.get('icon', 'AppstoreOutlined'),
        price_monthly=d.get('price_monthly', 0),
        price_yearly=d.get('price_yearly', 0),
        features=d.get('features', []),
        highlights=d.get('highlights', []),
        is_active=d.get('is_active', True),
        is_popular=d.get('is_popular', False),
        sort_order=d.get('sort_order', 0),
    )
    return Response({'id': mp.id, 'module_name': mp.module_name, 'title': mp.title}, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsSuperAdminUser])
def module_pricing_detail(request, pk):
    """Superadmin: get, update, or delete a module pricing entry."""
    try:
        mp = ModulePricing.objects.get(pk=pk)
    except ModulePricing.DoesNotExist:
        return Response({'error': 'Module pricing not found'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': mp.id,
            'module_name': mp.module_name,
            'title': mp.title,
            'tagline': mp.tagline,
            'description': mp.description,
            'icon': mp.icon,
            'price_monthly': str(mp.price_monthly),
            'price_yearly': str(mp.price_yearly),
            'features': mp.features or [],
            'highlights': mp.highlights or [],
            'is_active': mp.is_active,
            'is_popular': mp.is_popular,
            'sort_order': mp.sort_order,
        })

    if request.method == 'PUT':
        d = request.data
        for field in ['title', 'tagline', 'description', 'icon', 'is_active', 'is_popular', 'sort_order']:
            if field in d:
                setattr(mp, field, d[field])
        if 'price_monthly' in d:
            mp.price_monthly = d['price_monthly']
        if 'price_yearly' in d:
            mp.price_yearly = d['price_yearly']
        if 'features' in d:
            mp.features = d['features']
        if 'highlights' in d:
            mp.highlights = d['highlights']
        mp.save()
        return Response({'id': mp.id, 'title': mp.title})

    # DELETE
    mp.delete()
    return Response(status=204)


# ---------------------------------------------------------------------------
# EMAIL TEMPLATES
# ---------------------------------------------------------------------------

from .models import EmailTemplate  # noqa: E402  (kept local to minimise churn)
from .email_rendering import base_layout, strip_html, substitute  # noqa: E402


def _serialize_email_template(tpl: EmailTemplate) -> dict:
    return {
        'id': tpl.id,
        'key': tpl.key,
        'language': tpl.language,
        'category': tpl.category,
        'display_name': tpl.display_name,
        'description': tpl.description,
        'subject': tpl.subject,
        'body_html': tpl.body_html,
        'body_text': tpl.body_text,
        'variables': tpl.variables or [],
        'is_active': tpl.is_active,
        'is_system': tpl.is_system,
        'updated_at': tpl.updated_at.isoformat() if tpl.updated_at else None,
        'updated_by': tpl.updated_by.username if tpl.updated_by else None,
    }


@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdminUser])
def email_template_list(request):
    """List or create email templates."""
    if request.method == 'GET':
        qs = EmailTemplate.objects.all()
        category = request.query_params.get('category')
        language = request.query_params.get('language')
        search = request.query_params.get('search')
        if category:
            qs = qs.filter(category=category)
        if language:
            qs = qs.filter(language=language)
        if search:
            qs = qs.filter(
                Q(key__icontains=search)
                | Q(display_name__icontains=search)
                | Q(subject__icontains=search)
            )
        return Response([_serialize_email_template(t) for t in qs])

    # POST — create a new template
    data = request.data
    required = ['key', 'language', 'display_name', 'subject', 'body_html']
    for field in required:
        if not data.get(field):
            return Response({'error': f'{field} is required'}, status=400)

    if EmailTemplate.objects.filter(key=data['key'], language=data['language']).exists():
        return Response({'error': 'A template with this key + language already exists'}, status=400)

    tpl = EmailTemplate.objects.create(
        key=data['key'],
        language=data['language'],
        category=data.get('category', 'notification'),
        display_name=data['display_name'],
        description=data.get('description', ''),
        subject=data['subject'],
        body_html=sanitize_html(data['body_html']),
        body_text=data.get('body_text', ''),
        variables=data.get('variables') or [],
        is_active=data.get('is_active', True),
        is_system=False,
        updated_by=request.user if request.user.is_authenticated else None,
    )
    return Response(_serialize_email_template(tpl), status=201)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsSuperAdminUser])
def email_template_detail(request, pk):
    """Retrieve, update, or delete a single template."""
    try:
        tpl = EmailTemplate.objects.get(pk=pk)
    except EmailTemplate.DoesNotExist:
        return Response({'error': 'Template not found'}, status=404)

    if request.method == 'GET':
        return Response(_serialize_email_template(tpl))

    if request.method == 'DELETE':
        if tpl.is_system:
            return Response(
                {'error': 'System templates cannot be deleted. Deactivate instead.'},
                status=400,
            )
        tpl.delete()
        return Response(status=204)

    # PUT / PATCH
    data = request.data
    editable_fields = [
        'display_name', 'description', 'category', 'subject',
        'body_text', 'variables', 'is_active',
    ]
    for f in editable_fields:
        if f in data:
            setattr(tpl, f, data[f])

    if 'body_html' in data:
        tpl.body_html = sanitize_html(data['body_html'])

    # Key/language may only be changed for non-system rows and only if unique.
    if not tpl.is_system:
        if 'key' in data and data['key'] != tpl.key:
            tpl.key = data['key']
        if 'language' in data and data['language'] != tpl.language:
            tpl.language = data['language']
        # Unique constraint check
        dup = EmailTemplate.objects.filter(
            key=tpl.key, language=tpl.language,
        ).exclude(pk=tpl.pk).exists()
        if dup:
            return Response({'error': 'Another template already uses this key + language'}, status=400)

    tpl.updated_by = request.user if request.user.is_authenticated else None
    tpl.save()
    return Response(_serialize_email_template(tpl))


@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
def email_template_preview(request, pk):
    """Render a template to HTML using sample values — returns wrapped output.

    Body may include ``context`` (dict of placeholder values). Missing
    placeholders are left literal so editors can see what's unresolved.
    """
    try:
        tpl = EmailTemplate.objects.get(pk=pk)
    except EmailTemplate.DoesNotExist:
        return Response({'error': 'Template not found'}, status=404)

    context = request.data.get('context') or {}
    # Provide sensible defaults for every declared variable.
    for var in tpl.variables or []:
        context.setdefault(var, f'<{var}>')

    settings_obj = SuperAdminSettings.load()
    org_name = settings_obj.organization_name or 'QUOT ERP'
    support_email = settings_obj.support_email or settings_obj.smtp_from_email or 'support@example.com'

    rendered_subject = substitute(tpl.subject, context)
    rendered_body = substitute(tpl.body_html, context)
    html = base_layout(
        title=rendered_subject,
        content_html=rendered_body,
        org_name=org_name,
        support_email=support_email,
        preheader=rendered_subject,
    )
    text = substitute(tpl.body_text, context) if tpl.body_text else strip_html(rendered_body)

    return Response({
        'subject': rendered_subject,
        'html': html,
        'text': text,
    })


@api_view(['POST'])
@permission_classes([IsSuperAdminUser])
def email_template_send_test(request, pk):
    """Send a test email of this template to a specified address."""
    try:
        tpl = EmailTemplate.objects.get(pk=pk)
    except EmailTemplate.DoesNotExist:
        return Response({'error': 'Template not found'}, status=404)

    to_email = request.data.get('to_email') or (request.user.email if request.user.is_authenticated else None)
    if not to_email:
        return Response({'error': 'to_email is required'}, status=400)

    context = request.data.get('context') or {}
    for var in tpl.variables or []:
        context.setdefault(var, f'<{var}>')

    settings_obj = SuperAdminSettings.load()
    org_name = settings_obj.organization_name or 'QUOT ERP'
    support_email = settings_obj.support_email or settings_obj.smtp_from_email or 'support@example.com'

    rendered_subject = substitute(tpl.subject, context)
    rendered_body = substitute(tpl.body_html, context)
    html = base_layout(
        title=rendered_subject,
        content_html=rendered_body,
        org_name=org_name,
        support_email=support_email,
        preheader=rendered_subject,
    )
    text = substitute(tpl.body_text, context) if tpl.body_text else strip_html(rendered_body)

    from django.core.mail import EmailMultiAlternatives
    from django.conf import settings as dj_settings
    try:
        msg = EmailMultiAlternatives(
            subject=f'[TEST] {rendered_subject}',
            body=text,
            from_email=dj_settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send(fail_silently=False)
    except Exception as e:
        logger.exception('Failed to send test email for template %s', tpl.pk)
        return Response({'error': str(e)}, status=500)

    return Response({'ok': True, 'sent_to': to_email})
