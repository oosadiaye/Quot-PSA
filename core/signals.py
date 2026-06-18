"""
core.signals
============
Cache-invalidation hooks for the rule-driven RBAC + SoD models.

Whenever a tenant admin edits a Role's permission set, adds/removes a
permission from the catalogue, or flips an SoD rule's severity, the
``tenant_perms:*`` cache entries for every active user in this tenant
are dropped so the very next request re-resolves their permissions
from the fresh database state.

Why this design — instead of per-user cache keys we already have:
the existing ``invalidate_permission_cache(user_id, tenant_id)``
clears two specific keys for one (user, tenant) pair. When a Role's
permissions change, every user holding that role is affected, so we
need a fan-out invalidation. The simplest correct approach is to
walk active ``RoleAssignment`` rows for the affected role(s) and
invalidate each user's cache.

For SoD-rule changes we don't know in advance which users could be
affected (the rule applies tenant-wide), so we bump a tenant-scoped
"version" key — every consumer that reads SoD rules already queries
the database, so no cache to invalidate there. The version key is
useful for the frontend's react-query cache: a websocket / poll
endpoint that returns the current version lets the UI refetch when
it changes.
"""
from __future__ import annotations

import logging

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _invalidate_for_role(role) -> None:
    """Drop the permission cache for every active assignee of ``role``.

    Imported lazily so this module can be imported at app-ready time
    without pulling the auth user model into the import graph.
    """
    try:
        from core.permissions import invalidate_permission_cache
        from django.db import connection

        # In a tenant schema, ``connection.tenant`` exists; in public
        # we have no tenant_id to invalidate against, so we no-op.
        tenant = getattr(connection, 'tenant', None)
        tenant_id = getattr(tenant, 'pk', None) or getattr(tenant, 'id', None)
        if tenant_id is None:
            return

        user_ids = list(
            role.assignments.filter(is_active=True)
            .values_list('user_id', flat=True)
        )
        for user_id in user_ids:
            invalidate_permission_cache(user_id, tenant_id)
        if user_ids:
            logger.info(
                'rbac: invalidated permission cache for %d user(s) '
                'after role %s change',
                len(user_ids), role.code,
            )
    except Exception as exc:  # pragma: no cover — defensive
        # Cache invalidation must never bubble — failing here would
        # take down the role-edit endpoint.
        logger.warning('rbac: cache invalidation failed: %s', exc)


def _invalidate_all_active_users() -> None:
    """Tenant-wide invalidation for SoD-rule / permission-catalogue
    changes. Walks every active ``RoleAssignment`` because a SoD rule
    can be triggered by ANY of a user's permissions."""
    try:
        from core.models import RoleAssignment
        from core.permissions import invalidate_permission_cache
        from django.db import connection

        tenant = getattr(connection, 'tenant', None)
        tenant_id = getattr(tenant, 'pk', None) or getattr(tenant, 'id', None)
        if tenant_id is None:
            return

        user_ids = (
            RoleAssignment.objects.filter(is_active=True)
            .values_list('user_id', flat=True)
            .distinct()
        )
        n = 0
        for uid in user_ids:
            invalidate_permission_cache(uid, tenant_id)
            n += 1
        if n:
            logger.info('rbac: tenant-wide permission cache invalidated for %d user(s)', n)
    except Exception as exc:  # pragma: no cover
        logger.warning('rbac: tenant-wide cache invalidation failed: %s', exc)


# ─── Role attribute changes ──────────────────────────────────────────

def _role_post_save(sender, instance, created, **kwargs):
    # Booleans + name + active flag changes affect all assignees.
    _invalidate_for_role(instance)


def _role_post_delete(sender, instance, **kwargs):
    _invalidate_for_role(instance)


# ─── Role.permissions M2M changes ────────────────────────────────────

def _role_permissions_m2m_changed(sender, instance, action, **kwargs):
    # ``post_add``, ``post_remove``, ``post_clear`` — these are the
    # actions that mutate the M2M. ``pre_*`` would invalidate too
    # eagerly (the change might roll back), so we only act after.
    if action in ('post_add', 'post_remove', 'post_clear'):
        _invalidate_for_role(instance)


# ─── SoDRule changes ──────────────────────────────────────────────────

def _sod_rule_changed(sender, instance, **kwargs):
    # SoD rules apply tenant-wide; can't narrow the invalidation set.
    _invalidate_all_active_users()


# ─── PermissionDefinition catalogue changes ──────────────────────────

def _permission_catalogue_changed(sender, instance, **kwargs):
    # Adding / removing a permission from the catalogue can void
    # SoD evaluations that referenced it. Tenant-wide invalidation
    # is the safe play — catalogue edits are rare.
    _invalidate_all_active_users()


# ─── RoleAssignment changes ──────────────────────────────────────────
# When an admin grants / revokes a Role (including 'All Access') to a
# specific user, that user's tenant_perms cache must be busted
# immediately — otherwise the change wouldn't take effect for up to
# the cache TTL (5 min). Without this, granting All Access wouldn't
# unlock the user's permissions until they re-login or the cache
# expired naturally. Cheap: one cache key per affected user.

def _role_assignment_changed(sender, instance, **kwargs):
    """Invalidate the affected user's tenant_perms cache."""
    try:
        from core.permissions import invalidate_permission_cache
        from django.db import connection

        tenant = getattr(connection, 'tenant', None)
        tenant_id = getattr(tenant, 'pk', None) or getattr(tenant, 'id', None)
        if tenant_id is None or instance.user_id is None:
            return

        invalidate_permission_cache(instance.user_id, tenant_id)
        logger.info(
            'rbac: invalidated permission cache for user %s after '
            'role assignment (role=%s) change',
            instance.user_id, getattr(instance.role, 'code', '?'),
        )
    except Exception as exc:  # pragma: no cover
        logger.warning('rbac: role-assignment invalidation failed: %s', exc)

    # Invalidate snapshots admin-check cache for this user. We don't have
    # the tenant schema_name available here from RoleAssignment alone, so we
    # clear the all_access_schemas set; the per-schema key will expire via TTL
    # or be cleared on the next targeted call.
    try:
        from snapshots.permissions import (
            invalidate_snapshot_admin_cache,
            invalidate_all_access_schemas_cache,
        )
        invalidate_all_access_schemas_cache(instance.user_id)
        # We don't know the tenant schema_name from RoleAssignment here;
        # rely on the next read to refresh via cache miss.
    except ImportError:
        pass


def connect_rbac_signals():
    """Wire all RBAC + SoD signal handlers. Called from CoreConfig.ready()."""
    from core.models import PermissionDefinition, Role, RoleAssignment, SoDRule

    post_save.connect(
        _role_post_save, sender=Role,
        dispatch_uid='core_role_post_save_perm_invalidation',
    )
    post_delete.connect(
        _role_post_delete, sender=Role,
        dispatch_uid='core_role_post_delete_perm_invalidation',
    )
    m2m_changed.connect(
        _role_permissions_m2m_changed,
        sender=Role.permissions.through,
        dispatch_uid='core_role_permissions_m2m_perm_invalidation',
    )
    post_save.connect(
        _sod_rule_changed, sender=SoDRule,
        dispatch_uid='core_sod_rule_post_save_perm_invalidation',
    )
    post_delete.connect(
        _sod_rule_changed, sender=SoDRule,
        dispatch_uid='core_sod_rule_post_delete_perm_invalidation',
    )
    post_save.connect(
        _permission_catalogue_changed, sender=PermissionDefinition,
        dispatch_uid='core_perm_def_post_save_perm_invalidation',
    )
    post_delete.connect(
        _permission_catalogue_changed, sender=PermissionDefinition,
        dispatch_uid='core_perm_def_post_delete_perm_invalidation',
    )
    post_save.connect(
        _role_assignment_changed, sender=RoleAssignment,
        dispatch_uid='core_role_assignment_post_save_perm_invalidation',
    )
    post_delete.connect(
        _role_assignment_changed, sender=RoleAssignment,
        dispatch_uid='core_role_assignment_post_delete_perm_invalidation',
    )
    logger.debug('core: RBAC + SoD cache-invalidation signals connected')
