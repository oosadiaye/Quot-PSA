"""
Phase 3: Tenant-aware read replica database router.

Routes read-heavy queries (reports, dashboards, list views) to the replica
database while all writes go to the primary. Falls back to 'default' if no
replica is configured.

The router respects django-tenants by only routing at the database level —
schema selection is still handled by django-tenants middleware.

Usage:
    Set DB_REPLICA_HOST in .env to enable. Without it, all queries go to default.

    To force a specific query to the primary (e.g., read-after-write):
        from django.db import connections
        with connections['default'].cursor() as cursor:
            cursor.execute(...)

    Or use the `using()` queryset method:
        MyModel.objects.using('default').filter(...)
"""

import threading

from django.conf import settings


# Thread-local storage for forcing primary reads (read-after-write)
_thread_locals = threading.local()


def force_primary():
    """Context: force all reads to primary for the current thread."""
    _thread_locals.force_primary = True


def release_primary():
    """Release the force-primary override."""
    _thread_locals.force_primary = False


class TenantAwareReadReplicaRouter:
    """
    Routes reads to 'replica' database when available, writes to 'default'.

    This works transparently with django-tenants: the router only decides
    WHICH database alias to use. The tenant middleware still sets the
    schema search_path on whichever connection is chosen.
    """

    # Models that should ALWAYS read from primary (consistency-critical)
    PRIMARY_ONLY_MODELS = {
        'authtoken.token',
        'auth.user',
        'tenants.client',
        'tenants.domain',
        'tenants.usertenantrole',
        'tenants.tenantsubscription',
        'sessions.session',
    }

    # Apps whose reads can safely go to replica
    REPLICA_SAFE_APPS = {
        'accounting',
        'budget',
        'inventory',
        'procurement',
        'hrm',
        'workflow',
        'simple_history',
    }

    def _has_replica(self):
        return 'replica' in settings.DATABASES

    def _is_forced_primary(self):
        return getattr(_thread_locals, 'force_primary', False)

    def _model_label(self, model):
        return f'{model._meta.app_label}.{model._meta.model_name}'

    def db_for_read(self, model, **hints):
        """Route reads to replica for safe apps, primary for auth/tenant models."""
        if not self._has_replica():
            return None  # Let next router decide (TenantSyncRouter)

        if self._is_forced_primary():
            return None

        label = self._model_label(model)
        if label in self.PRIMARY_ONLY_MODELS:
            return None  # Primary

        if model._meta.app_label in self.REPLICA_SAFE_APPS:
            return 'replica'

        return None  # Default to primary for unlisted models

    def db_for_write(self, model, **hints):
        """All writes go to primary."""
        return None  # Let TenantSyncRouter handle it (always 'default')

    def allow_relation(self, obj1, obj2, **hints):
        """Allow relations between objects in default and replica."""
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Migrations only run on default (primary), never on replica."""
        if db == 'replica':
            return False
        return None  # Let TenantSyncRouter decide
