"""
Phase 2: Celery tasks for tenant lifecycle operations.

These tasks run asynchronously to avoid blocking HTTP requests for
expensive operations like schema creation, migration, and maintenance.
"""

import logging

from celery import shared_task
from django.core.cache import caches

logger = logging.getLogger('dtsg')


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def create_tenant_schema(self, tenant_id):
    """Async schema creation for a new tenant.

    Called after the Client record is saved. Runs migrations on the new
    schema without blocking the signup HTTP response.
    """
    from tenants.models import Client

    try:
        tenant = Client.objects.get(pk=tenant_id)
        if not tenant.schema_name:
            logger.error('Tenant %s has no schema_name', tenant_id)
            return

        # django-tenants creates the schema and runs migrations
        # when auto_create_schema=True on save(). If we want manual control:
        from django.core.management import call_command
        call_command('migrate_schemas', '--schema', tenant.schema_name, verbosity=0)

        logger.info('Schema created and migrated for tenant %s (%s)',
                     tenant.schema_name, tenant_id)
    except Client.DoesNotExist:
        logger.error('Tenant %s does not exist', tenant_id)
    except Exception as exc:
        logger.exception('Schema creation failed for tenant %s', tenant_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def run_tenant_migrations(self, schema_name):
    """Run pending migrations on a specific tenant schema.

    Useful for rolling out migrations one tenant at a time
    instead of blocking the deploy.
    """
    try:
        from django.core.management import call_command
        call_command('migrate_schemas', '--schema', schema_name, verbosity=0)
        logger.info('Migrations completed for schema %s', schema_name)
    except Exception as exc:
        logger.exception('Migration failed for schema %s', schema_name)
        raise self.retry(exc=exc)


@shared_task
def invalidate_tenant_cache(tenant_domain):
    """Invalidate cached domain and access data for a tenant.

    Call this when a tenant is updated, suspended, or deleted.
    """
    try:
        cache = caches['tenant_cache']
    except Exception:
        cache = caches['default']

    # Clear domain cache
    cache.delete(f'domain:{tenant_domain}')

    # Clear subscription status cache (need schema_name)
    from tenants.models import Domain
    domain_obj = Domain.objects.filter(domain=tenant_domain).select_related('tenant').first()
    if domain_obj:
        cache.delete(f'sub_status:{domain_obj.tenant.schema_name}')

    logger.info('Cache invalidated for tenant domain %s', tenant_domain)


@shared_task
def bulk_migrate_tenants():
    """Run migrations on all tenant schemas sequentially.

    Use this instead of `migrate_schemas` to avoid locking the deploy.
    Each tenant's migration is a separate task for parallelism.
    """
    from tenants.models import Client

    tenants = Client.objects.exclude(schema_name='public').values_list('schema_name', flat=True)
    for schema in tenants:
        run_tenant_migrations.delay(schema)

    logger.info('Queued migrations for %d tenant schemas', len(tenants))


@shared_task
def cleanup_expired_sessions():
    """Remove expired sessions from the database/cache."""
    from django.core.management import call_command
    call_command('clearsessions', verbosity=0)
    logger.info('Expired sessions cleaned up')


@shared_task
def cleanup_expired_tokens():
    """Remove expired auth tokens from the database.
    
    Runs on a schedule (e.g., daily) to clean up tokens that weren't
    deleted when they expired (e.g., if user never made a request after expiry).
    """
    from datetime import timedelta
    from django.utils import timezone
    from rest_framework.authtoken.models import Token
    
    expiration_hours = 24  # Should match TOKEN_EXPIRATION_HOURS in settings
    cutoff = timezone.now() - timedelta(hours=expiration_hours)
    
    try:
        with schema_context('public'):
            expired_count, _ = Token.objects.filter(created__lt=cutoff).delete()
            logger.info('Cleaned up %d expired tokens', expired_count)
    except Exception as exc:
        logger.exception('Failed to cleanup expired tokens: %s', exc)
        raise exc
