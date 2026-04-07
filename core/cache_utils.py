from django.core.cache import cache
from functools import wraps
import hashlib
import json
from typing import Any, Callable, Optional


class CacheManager:
    """Centralized cache management for the ERP"""
    
    @staticmethod
    def make_key(prefix: str, *args, **kwargs) -> str:
        """Generate a cache key from prefix and arguments"""
        if args or kwargs:
            data = json.dumps({'args': args, 'kwargs': kwargs}, sort_keys=True)
            hash_key = hashlib.md5(data.encode()).hexdigest()[:8]
            return f"{prefix}:{hash_key}"
        return prefix
    
    @staticmethod
    def get(prefix: str, *args, **kwargs) -> Optional[Any]:
        """Get value from cache"""
        key = CacheManager.make_key(prefix, *args, **kwargs)
        return cache.get(key)
    
    @staticmethod
    def set(prefix: str, value: Any, ttl: int = None, *args, **kwargs):
        """Set value in cache with optional TTL"""
        key = CacheManager.make_key(prefix, *args, **kwargs)
        if ttl:
            cache.set(key, value, ttl)
        else:
            cache.set(key, value)
    
    @staticmethod
    def delete(prefix: str, *args, **kwargs):
        """Delete a specific cache key"""
        key = CacheManager.make_key(prefix, *args, **kwargs)
        cache.delete(key)
    
    @staticmethod
    def delete_pattern(pattern: str):
        """Delete all keys matching a pattern ( Redis only)"""
        # For Redis, you would use: cache.delete_pattern(f"{pattern}*")
        # For LocMemCache, we clear all
        cache.clear()
    
    @staticmethod
    def clear_all():
        """Clear all cache"""
        cache.clear()


def cache_view(ttl: int = 300, prefix: str = None):
    """
    Decorator to cache view responses
    Usage:
        @cache_view(ttl=60, prefix='dashboard')
        def my_view(request):
            ...
    """
    def decorator(view_func: Callable):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Skip cache for logged-out users
            if not request.user.is_authenticated:
                return view_func(request, *args, **kwargs)
            
            cache_key = prefix or view_func.__name__
            if request.user.id:
                cache_key = f"{cache_key}:user_{request.user.id}"
            
            # Check for query params
            if request.GET:
                query_hash = hashlib.md5(request.GET.urlencode().encode()).hexdigest()[:8]
                cache_key = f"{cache_key}:{query_hash}"
            
            cached_response = cache.get(cache_key)
            if cached_response is not None:
                return cached_response
            
            response = view_func(request, *args, **kwargs)
            
            # Only cache successful responses
            if response.status_code == 200:
                cache.set(cache_key, response, ttl)
            
            return response
        return wrapper
    return decorator


def invalidate_user_cache(user_id: int):
    """Invalidate all cache for a specific user"""
    # In production with Redis, you'd use pattern matching
    cache.clear()


# =============================================================================
# Phase 2: Tenant-aware cache invalidation
# =============================================================================

def _get_tenant_cache():
    """Get the tenant_cache backend, falling back to default."""
    from django.core.cache import caches
    try:
        return caches['tenant_cache']
    except Exception:
        return caches['default']


def invalidate_domain_cache(domain: str):
    """Invalidate cached domain lookup. Call when tenant is created/deleted/suspended."""
    _get_tenant_cache().delete(f'domain:{domain}')


def invalidate_access_cache(user_id: int, schema_name: str):
    """Invalidate cached access check. Call when UserTenantRole changes."""
    _get_tenant_cache().delete(f'access:{user_id}:{schema_name}')


def invalidate_subscription_cache(schema_name: str):
    """Invalidate cached subscription status. Call when subscription changes."""
    _get_tenant_cache().delete(f'sub_status:{schema_name}')


def invalidate_all_tenant_cache(tenant):
    """Invalidate all cached data for a tenant. Call on major tenant changes."""
    from tenants.models import Domain
    tc = _get_tenant_cache()
    domains = Domain.objects.filter(tenant=tenant).values_list('domain', flat=True)
    for domain in domains:
        tc.delete(f'domain:{domain}')
    tc.delete(f'sub_status:{tenant.schema_name}')