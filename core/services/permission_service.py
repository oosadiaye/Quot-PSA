import logging

from django.db import connection

logger = logging.getLogger('dtsg')


class PermissionService:
    @staticmethod
    def get_user_permissions(user, tenant=None):
        """Resolve the effective permissions for a user, optionally scoped to a tenant.

        Returns a dict with keys: role, role_display, groups, permissions.
        For admins permissions will be ['__all__'].
        """
        from tenants.models import UserTenantRole
        from core.permissions import invalidate_permission_cache  # noqa — available for callers

        if tenant is None:
            tenant = getattr(connection, 'tenant', None)

        if user.is_superuser:
            return {
                'role': 'admin',
                'role_display': 'Admin',
                'groups': [],
                'permissions': ['__all__'],
            }

        if not tenant or tenant.schema_name == 'public':
            return {
                'role': None,
                'role_display': None,
                'groups': [],
                'permissions': [],
            }

        try:
            utr = UserTenantRole.objects.prefetch_related('groups').get(
                user=user, tenant=tenant, is_active=True
            )
            groups = list(utr.groups.values_list('name', flat=True))
            if utr.role == 'admin':
                permissions = ['__all__']
            else:
                permissions = sorted(
                    p.split('.')[-1] for p in utr.get_all_permissions()
                )
            return {
                'role': utr.role,
                'role_display': utr.get_role_display(),
                'groups': groups,
                'permissions': permissions,
            }
        except UserTenantRole.DoesNotExist:
            return {
                'role': None,
                'role_display': None,
                'groups': [],
                'permissions': [],
            }

    @staticmethod
    def invalidate_cache(user, tenant=None):
        """Invalidate the permission cache for a user (and optionally a tenant)."""
        from core.permissions import invalidate_permission_cache

        tenant_id = tenant.pk if tenant else None
        invalidate_permission_cache(user.pk, tenant_id)
