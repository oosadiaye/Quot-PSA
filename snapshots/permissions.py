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
from django.core.cache import cache as _cache
from rest_framework.permissions import BasePermission


logger = logging.getLogger(__name__)


_CACHE_TTL = 300


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


def _admin_cache_key(user_id: int, schema_name: str) -> str:
    return f'snapshots:admin:{user_id}:{schema_name}'


def is_tenant_admin_of(user, schema_name: str) -> bool:
    """True if user holds 'all_access' on `schema_name`.

    Caches the boolean result per (user_id, schema_name) for 5 minutes.
    Cache is invalidated by core.signals._role_assignment_changed via the
    `invalidate_snapshot_admin_cache` hook below.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if not schema_name:
        return False

    cache_key = _admin_cache_key(user.pk, schema_name)
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from tenants.models import Client, UserTenantRole
        try:
            tenant = Client.objects.get(schema_name=schema_name)
        except Client.DoesNotExist:
            _cache.set(cache_key, False, _CACHE_TTL)
            return False

        has_utr = UserTenantRole.objects.filter(
            user=user, tenant=tenant, is_active=True,
        ).exists()
        if not has_utr:
            _cache.set(cache_key, False, _CACHE_TTL)
            return False

        from django_tenants.utils import schema_context
        from core.permissions import _user_has_all_access
        with schema_context(schema_name):
            result = bool(_user_has_all_access(user))
        _cache.set(cache_key, result, _CACHE_TTL)
        return result
    except Exception:
        logger.exception(
            'snapshots.permissions: is_tenant_admin_of check failed for '
            'user=%s schema=%s', getattr(user, 'pk', None), schema_name)
        return False


def invalidate_snapshot_admin_cache(user_id: int, schema_name: str | None = None) -> None:
    """Clear cached admin status. Used by RoleAssignment post_save signal."""
    if schema_name is None:
        # Best-effort: we don't know which schemas to invalidate. For now,
        # callers should pass schema_name. This is a no-op fallback.
        return
    _cache.delete(_admin_cache_key(user_id, schema_name))


def _all_access_cache_key(user_id: int) -> str:
    return f'snapshots:all_access_schemas:{user_id}'


def tenant_schemas_with_all_access(user) -> set[str]:
    """Set of schema_names where `user` holds all_access.

    For superadmins: returns ALL schemas (full enumeration).
    For tenant admins: result is cached per user for 5 minutes.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return set()

    if is_platform_superadmin(user):
        try:
            from tenants.models import Client
            return set(Client.objects.values_list('schema_name', flat=True))
        except Exception:
            logger.exception(
                'snapshots.permissions: could not enumerate Client schemas')
            return set()

    cache_key = _all_access_cache_key(user.pk)
    cached = _cache.get(cache_key)
    if cached is not None:
        return set(cached)

    result: set[str] = set()
    try:
        from tenants.models import UserTenantRole
        from django_tenants.utils import schema_context
        from core.permissions import _user_has_all_access

        utr_qs = (
            UserTenantRole.objects
            .filter(user=user, is_active=True)
            .select_related('tenant')
        )
        for utr in utr_qs:
            schema = utr.tenant.schema_name
            try:
                with schema_context(schema):
                    if _user_has_all_access(user):
                        result.add(schema)
            except Exception:
                logger.exception(
                    'snapshots.permissions: per-schema all_access lookup failed '
                    'for user=%s schema=%s', user.pk, schema)
    except Exception:
        logger.exception(
            'snapshots.permissions: tenant_schemas_with_all_access failed for user=%s',
            user.pk)
        return set()

    _cache.set(cache_key, list(result), _CACHE_TTL)
    return result


def invalidate_all_access_schemas_cache(user_id: int) -> None:
    """Clear cached schemas-with-all-access set. Used by signal."""
    _cache.delete(_all_access_cache_key(user_id))


# ---------------------------------------------------------------------------
# DRF permission classes
# ---------------------------------------------------------------------------

class CanCreateSnapshot(BasePermission):
    """Permission gate for snapshot creation (POST /api/snapshots/).

    Contract:
        - Unauthenticated requests are denied on ALL methods.
        - For POST: validates `request.data['schema_name']` is one the actor
          can create snapshots for (superadmin: any; tenant admin: own only).
        - For non-POST: returns True at the class level (no schema_name in
          body to gate on). This means GET/PATCH/DELETE pass through to
          object-level permissions (`CanAccessSnapshot.has_object_permission`)
          and to the queryset filter in views.py.

    IMPORTANT: Use composed with `CanAccessSnapshot` on retrieve/destroy
    endpoints. Used alone on a retrieve endpoint, it would allow any
    authenticated user to fetch any snapshot.
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
