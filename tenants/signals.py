from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_save, sender='tenants.UserTenantRole')
def invalidate_cache_on_role_save(sender, instance, **kwargs):
    """Invalidate permission + access cache when a UserTenantRole is created/updated."""
    from core.permissions import invalidate_permission_cache
    from core.cache_utils import invalidate_access_cache
    invalidate_permission_cache(instance.user_id, instance.tenant_id)
    # Phase 2: Also invalidate middleware access cache
    if hasattr(instance, 'tenant') and instance.tenant:
        invalidate_access_cache(instance.user_id, instance.tenant.schema_name)


@receiver(post_delete, sender='tenants.UserTenantRole')
def invalidate_cache_on_role_delete(sender, instance, **kwargs):
    """Invalidate permission + access cache when a UserTenantRole is deleted."""
    from core.permissions import invalidate_permission_cache
    from core.cache_utils import invalidate_access_cache
    invalidate_permission_cache(instance.user_id, instance.tenant_id)
    if hasattr(instance, 'tenant') and instance.tenant:
        invalidate_access_cache(instance.user_id, instance.tenant.schema_name)


@receiver(post_save, sender='tenants.TenantSubscription')
def invalidate_cache_on_subscription_change(sender, instance, **kwargs):
    """Invalidate subscription status cache when subscription changes."""
    from core.cache_utils import invalidate_subscription_cache
    if hasattr(instance, 'tenant') and instance.tenant:
        invalidate_subscription_cache(instance.tenant.schema_name)
