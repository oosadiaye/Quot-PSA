"""Permission resolvers and DRF permission classes for the snapshots feature.

Defense-in-depth strategy:
  1. permission_classes here gate based on actor type + target schema.
  2. Queryset filtering in views.py (Task 14) gates based on rows the actor
     can see.

A bug in either layer is caught by the other.

Two actor tiers:
  * Platform superadmin — `is_superuser=True` OR a SuperAdminProfile row
    with `is_superadmin=True` and `is_active=True`. Uses the same dual-check
    as `superadmin.views.IsSuperAdminUser`.
  * Tenant admin — holds a `UserTenantRole` with `role='admin'` (or any
    active role on the tenant) AND holds an active assignment to the
    'all_access' ``core.Role`` on that tenant (checked via
    `core.permissions._user_has_all_access`, which queries in the current
    schema context). For Phase 1 we rely on the shared `UserTenantRole`
    model (SHARED_APPS, public schema) to enumerate tenants, and we trust
    the `role='admin'` coarse check plus the `_user_has_all_access` fine
    check together as the admission gate.
"""
from __future__ import annotations

import logging

from django.contrib.auth.models import AnonymousUser
from rest_framework.permissions import BasePermission


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Resolver helpers
# ---------------------------------------------------------------------------

def is_platform_superadmin(user) -> bool:
    """True if `user` is a platform-level superadmin (cross-tenant).

    Mirrors the logic of ``superadmin.views.IsSuperAdminUser``:
      1. Django's ``is_superuser`` flag — fast path.
      2. A ``SuperAdminProfile`` row with ``is_superadmin=True`` and
         ``is_active=True`` (queried in the public schema via schema_context).

    Returns False for anonymous users and any unexpected exception.
    """
    if user is None or isinstance(user, AnonymousUser):
        return False
    if not getattr(user, 'is_authenticated', False):
        return False
    # Fast path — Django built-in superuser flag.
    if getattr(user, 'is_superuser', False):
        return True
    # Slower path — dedicated SuperAdminProfile row.
    try:
        from django_tenants.utils import schema_context
        with schema_context('public'):
            from superadmin.models import SuperAdminProfile
            return SuperAdminProfile.objects.filter(
                user=user, is_superadmin=True, is_active=True
            ).exists()
    except Exception:
        logger.exception(
            'snapshots.permissions: SuperAdminProfile lookup failed for user %s',
            getattr(user, 'pk', '?'),
        )
        return False


def is_tenant_admin_of(user, schema_name: str) -> bool:
    """True if `user` holds the all_access Role on the tenant `schema_name`.

    Resolution order:
      1. Check `UserTenantRole` (public schema, SHARED_APPS) — confirms the
         user is linked to the named tenant at all.
      2. Run `core.permissions._user_has_all_access` inside a
         `schema_context` for that tenant — confirms the fine-grained
         'all_access' role assignment exists in the tenant schema.

    Falls back gracefully to False on any import or DB error so that a
    missing-schema condition never grants access.
    """
    if user is None or isinstance(user, AnonymousUser):
        return False
    if not getattr(user, 'is_authenticated', False):
        return False
    if not schema_name:
        return False

    try:
        from tenants.models import Client, UserTenantRole
        # Step 1: coarse check — does the user have *any* active role on
        # the tenant identified by schema_name?
        try:
            tenant = Client.objects.get(schema_name=schema_name)
        except Client.DoesNotExist:
            return False

        has_utr = UserTenantRole.objects.filter(
            user=user, tenant=tenant, is_active=True
        ).exists()
        if not has_utr:
            return False

        # Step 2: fine-grained check — does the user hold all_access inside
        # the tenant schema?
        from django_tenants.utils import schema_context
        from core.permissions import _user_has_all_access
        with schema_context(schema_name):
            return bool(_user_has_all_access(user))

    except Exception:
        logger.exception(
            'snapshots.permissions: is_tenant_admin_of failed '
            '(user=%s schema=%s)',
            getattr(user, 'pk', '?'),
            schema_name,
        )
        return False


def tenant_schemas_with_all_access(user) -> set[str]:
    """Set of schema names where `user` holds active all_access.

    Used by queryset filtering in views.py (Task 14) to restrict the rows
    a tenant admin can see.  Platform superadmins get the full set as a
    defensive measure, though the view layer typically bypasses the filter
    for superadmins.

    Returns an empty set on any error so that a DB fault never expands
    access.
    """
    if user is None or isinstance(user, AnonymousUser):
        return set()
    if not getattr(user, 'is_authenticated', False):
        return set()

    try:
        from tenants.models import Client, UserTenantRole
    except ImportError:
        logger.exception('snapshots.permissions: could not import tenants models')
        return set()

    # Superadmins have platform-wide access — return all active schemas.
    if is_platform_superadmin(user):
        return set(Client.objects.values_list('schema_name', flat=True))

    # For non-superadmins, enumerate tenants via the shared UserTenantRole
    # table, then verify all_access inside each tenant schema.
    try:
        tenant_qs = (
            UserTenantRole.objects
            .filter(user=user, is_active=True)
            .select_related('tenant')
        )
        result: set[str] = set()
        from django_tenants.utils import schema_context
        from core.permissions import _user_has_all_access
        for utr in tenant_qs:
            sn = utr.tenant.schema_name
            try:
                with schema_context(sn):
                    if _user_has_all_access(user):
                        result.add(sn)
            except Exception:
                logger.warning(
                    'snapshots.permissions: schema_context(%s) failed; skipping',
                    sn,
                )
        return result
    except Exception:
        logger.exception(
            'snapshots.permissions: tenant_schemas_with_all_access failed '
            'for user %s',
            getattr(user, 'pk', '?'),
        )
        return set()


# ---------------------------------------------------------------------------
# DRF permission classes
# ---------------------------------------------------------------------------

class CanCreateSnapshot(BasePermission):
    """Gate for creating (POST) a new SnapshotJob.

    * Platform superadmin: always allowed.
    * Tenant admin: allowed only when ``request.data['schema_name']`` is a
      tenant they hold all_access on.
    * All other actors (anonymous, regular users): denied.

    Non-POST methods pass through to ``has_object_permission`` — the
    caller is expected to pair this with ``CanAccessSnapshot`` or handle
    object-level checks in the view.
    """

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        if request.method != 'POST':
            # Listing / retrieving is governed by has_object_permission or
            # the queryset filter in Task 14.
            return True
        if is_platform_superadmin(user):
            return True
        target_schema = (request.data or {}).get('schema_name', '')
        if not target_schema:
            return False
        return is_tenant_admin_of(user, target_schema)


class CanAccessSnapshot(BasePermission):
    """Object-level permission for retrieve / download / destroy.

    ``has_permission`` only checks authentication so that list views can
    apply a queryset filter (Task 14) rather than a blanket deny.
    ``has_object_permission`` enforces the per-object schema check.
    """

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and getattr(user, 'is_authenticated', False))

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        if is_platform_superadmin(user):
            return True
        return is_tenant_admin_of(user, obj.schema_name)
