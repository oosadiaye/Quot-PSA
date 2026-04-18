import logging
from django.core.cache import cache
from django.db import connection
from rest_framework import permissions

logger = logging.getLogger('dtsg')


def _get_tenant_role(user, tenant):
    """Get the UserTenantRole for a user+tenant pair, with caching."""
    from tenants.models import UserTenantRole

    # Handle None tenant case
    tenant_key = tenant.pk if tenant else 'none'
    cache_key = f"utr:{user.pk}:{tenant_key}"
    utr = cache.get(cache_key)
    if utr is not None:
        return utr if utr != '__none__' else None

    # Don't cache for None tenant
    if tenant is None:
        return None

    try:
        utr = UserTenantRole.objects.get(user=user, tenant=tenant, is_active=True)
    except UserTenantRole.DoesNotExist:
        utr = None

    cache.set(cache_key, utr or '__none__', timeout=300)
    return utr


def _get_tenant_permissions(user, tenant):
    """Get all permission strings for a user in a specific tenant, with caching."""
    # Handle None tenant case
    tenant_key = tenant.pk if tenant else 'none'
    cache_key = f"tenant_perms:{user.pk}:{tenant_key}"
    perms = cache.get(cache_key)
    if perms is not None:
        return perms

    # Return empty set for None tenant
    if tenant is None:
        return set()

    utr = _get_tenant_role(user, tenant)
    if not utr:
        perms = set()
    elif utr.role == 'admin':
        perms = {'__all__'}
    else:
        perms = utr.get_all_permissions()

    cache.set(cache_key, perms, timeout=300)
    return perms


def invalidate_permission_cache(user_id, tenant_id):
    """Call this when a user's role or groups change."""
    cache.delete(f"utr:{user_id}:{tenant_id}")
    cache.delete(f"tenant_perms:{user_id}:{tenant_id}")


class RBACPermission(permissions.DjangoModelPermissions):
    """
    Tenant-scoped RBAC permission class.

    Resolves permissions from the Django Groups assigned via UserTenantRole
    (tenant-scoped) rather than the user's global groups.

    Role hierarchy:
    - Superuser: bypass all checks
    - Tenant Admin (role='admin'): bypass model-level checks for their tenant
    - Senior Manager / Mid-Level Manager / User: checked against tenant-scoped groups
    - Viewer: read-only access (GET/HEAD/OPTIONS only)

    Every denial sets ``self.message`` to a human-readable reason so the
    DRF-serialised 403 body surfaces WHY (authentication? tenant role?
    missing model permission?) rather than a generic "forbidden".
    """
    perms_map = {
        'GET': ['%(app_label)s.view_%(model_name)s'],
        'OPTIONS': [],
        'HEAD': [],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }

    def has_permission(self, request, view):
        # Must be authenticated
        if not request.user or not request.user.is_authenticated:
            self.message = 'You must be signed in to perform this action.'
            return False

        # Superuser bypass — explicitly granted access overrides all RBAC
        # and SOD (initiator != approver) rules. A superuser who holds
        # the permission IS authorized by definition.
        if request.user.is_superuser:
            return True

        # Determine current tenant
        tenant = getattr(connection, 'tenant', None)
        if not tenant or tenant.schema_name == 'public':
            return True  # Public schema endpoints — no model-level restrictions

        # Get tenant-scoped role
        utr = _get_tenant_role(request.user, tenant)
        if not utr:
            self.message = (
                f'You do not have a role on the "{tenant.schema_name}" tenant. '
                'Contact your tenant administrator to be assigned access.'
            )
            return False

        # Tenant admin bypass
        if utr.role == 'admin':
            return True

        # Viewer: read-only
        if utr.role == 'viewer' and request.method not in ('GET', 'HEAD', 'OPTIONS'):
            self.message = (
                'Your role on this tenant is read-only (Viewer). You cannot '
                'create, update or delete records. Request a higher role from '
                'your tenant administrator.'
            )
            return False

        # For safe methods with no queryset (e.g. custom actions), allow
        if not hasattr(view, 'queryset') or view.queryset is None:
            model_cls = getattr(view, 'model', None)
            if model_cls is None:
                return request.method in permissions.SAFE_METHODS
        else:
            model_cls = view.queryset.model

        # Get required permissions for the HTTP method
        required_perms = self.get_required_permissions(request.method, model_cls)
        if not required_perms:
            return True

        # Check against tenant-scoped permissions
        tenant_perms = _get_tenant_permissions(request.user, tenant)
        if '__all__' in tenant_perms:
            return True

        missing = [p for p in required_perms if p not in tenant_perms]
        if missing:
            self.message = (
                f'Your role ({utr.role}) does not grant the permission '
                f'required for this action: {", ".join(missing)}. '
                'Ask your tenant administrator to update your role.'
            )
            return False
        return True


class IsApprover(permissions.BasePermission):
    """
    Check if the user has a custom action permission for the current tenant.
    Defaults to 'approve_<model>' but supports other prefixes like 'post' or 'process'.
    Usage: IsApprover() or IsApprover('post') or IsApprover('process')

    Superusers and tenant admins bypass — that's the documented SOD escape
    hatch for approved-access users. For anyone else, sets ``self.message``
    on denial so the 403 body explains which permission is missing.
    """
    def __init__(self, perm_prefix='approve'):
        self.perm_prefix = perm_prefix
        super().__init__()

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            self.message = 'You must be signed in to perform this action.'
            return False

        # Superuser bypass — explicitly authorised access over-rides SOD.
        if request.user.is_superuser:
            return True

        tenant = getattr(connection, 'tenant', None)
        if not tenant or tenant.schema_name == 'public':
            return True

        utr = _get_tenant_role(request.user, tenant)
        if not utr:
            self.message = (
                f'You do not have a role on "{tenant.schema_name}". '
                'Contact your tenant administrator for access.'
            )
            return False
        # Tenant admin bypass — admins hold the documented SOD override.
        if utr.role == 'admin':
            return True

        model_cls = view.queryset.model if hasattr(view, 'queryset') and view.queryset else None
        if not model_cls:
            self.message = 'This action requires a specific approval permission.'
            return False

        app = model_cls._meta.app_label
        model_name = model_cls._meta.model_name
        perm = f"{app}.{self.perm_prefix}_{model_name}"

        tenant_perms = _get_tenant_permissions(request.user, tenant)
        if perm in tenant_perms:
            return True

        # Verb-specific messaging so the user sees why
        verb_label = {
            'approve': 'approve',
            'post': 'post to GL',
            'process': 'process',
            'release': 'release',
        }.get(self.perm_prefix, self.perm_prefix)
        self.message = (
            f'You are not authorised to {verb_label} this {model_name}. '
            f'Missing permission: {perm}. '
            f'This is a Segregation-of-Duties control — the initiator of a '
            f'document cannot also {verb_label} it. Ask a different authorised '
            f'user, or request the {perm} permission from your tenant admin.'
        )
        return False


class IsTenantAdmin(permissions.BasePermission):
    """
    Only allows access for tenant admins and senior managers.
    Used for user management endpoints.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True

        tenant = getattr(connection, 'tenant', None)
        if not tenant or tenant.schema_name == 'public':
            return False

        utr = _get_tenant_role(request.user, tenant)
        if not utr:
            return False
        return utr.role in ('admin', 'senior_manager')
