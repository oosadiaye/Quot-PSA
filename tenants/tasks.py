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
        from django_tenants.utils import schema_context

        call_command('migrate_schemas', '--schema', tenant.schema_name, verbosity=0)

        # Seed the Chart of Accounts so every module's GL posting works
        # from day one. Uses get_or_create internally, so safe to re-run.
        with schema_context(tenant.schema_name):
            call_command('seed_coa', '--validate', verbosity=0)

        # Seed tenant defaults: warehouse, asset categories, UOMs, base currency
        with schema_context(tenant.schema_name):
            from core.management.commands.seed_tenant_defaults import seed_defaults
            seed_defaults(tenant_name=tenant.name)

        # Bridge any pre-existing NCoA segments → legacy MDA/Fund/Function/
        # Program/Geo so the Journal/Voucher/Asset forms have populated
        # dropdowns from day one. Idempotent. The post_save signal in
        # ``accounting.signals.ncoa_to_legacy`` keeps the bridge in sync
        # going forward; this initial run covers segments that were created
        # before the signal had a chance to fire (seeders, raw SQL imports).
        with schema_context(tenant.schema_name):
            try:
                call_command('backfill_legacy_dims', verbosity=0)
            except Exception:
                # Bridge is a UI convenience; never fail tenant provisioning
                # because of it. Log and carry on.
                logger.exception(
                    'NCoA → legacy bridge backfill failed for tenant %s; '
                    'forms may need manual `backfill_legacy_dims` run.',
                    tenant.schema_name,
                )

        logger.info('Schema created, migrated, COA + defaults seeded for tenant %s (%s)',
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


@shared_task(
    name='tenants.provision_tenant_schema',
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    ignore_result=False,
)
def provision_tenant_schema(
    self,
    tenant_id,
    *,
    admin_username,
    admin_email,
    temp_password=None,
    plan_type='',
    first_name='',
    last_name='',
    selected_modules=None,
    business_category='',
):
    """End-to-end async provisioning: schema + admin user + subscription + email.

    Why async: ``create_schema()`` runs 170+ migrations (accounting alone has
    86). That used to block the superadmin API call for 1–3 minutes; now the
    ``Client`` row saves instantly and this worker handles the rest.

    State machine on ``Client.provisioning_status``::

        pending ──▶ provisioning ──▶ active
                                  └─▶ failed  (error stored on row)

    Idempotent: re-running on an ``active`` tenant is a no-op, and
    ``create_schema(check_if_exists=True)`` treats an existing schema as
    success, so retries after a transient failure start clean.
    """
    from datetime import timedelta
    from django.contrib.auth import get_user_model
    from django.db import transaction as _tx
    from django.utils import timezone as _tz
    from django_tenants.utils import schema_context as _schema_ctx

    from core.models import TenantModule as PerTenantModule
    from tenants.models import (
        AVAILABLE_MODULES, Client, SubscriptionPlan,
        TenantSubscription, UserTenantRole,
    )

    User = get_user_model()

    try:
        tenant = Client.objects.get(pk=tenant_id)
    except Client.DoesNotExist:
        logger.error('provision_tenant_schema: tenant id=%s vanished', tenant_id)
        return {'status': 'missing', 'tenant_id': tenant_id}

    # Idempotent short-circuit.
    if tenant.provisioning_status == 'active':
        logger.info('tenant %s already active; nothing to do', tenant.schema_name)
        return {'status': 'already_active', 'tenant_id': tenant_id}

    tenant.provisioning_status = 'provisioning'
    tenant.provisioning_started_at = _tz.now()
    tenant.provisioning_error = ''
    tenant.save(update_fields=[
        'provisioning_status', 'provisioning_started_at', 'provisioning_error',
    ])

    try:
        # 1. Create the Postgres schema + run every tenant-app migration.
        #    This is the slow step (60–180s) — the whole reason we're async.
        tenant.create_schema(check_if_exists=True, verbosity=0)

        # 1b. Bridge the legacy `django_content_type.name NOT NULL` constraint.
        #     django-tenants' `create_schema()` has been observed to apply
        #     `contenttypes.0001_initial` (which creates the table with the
        #     legacy NOT NULL `name` column) but NOT `0002_remove_content_type_name`
        #     when contenttypes lives in both SHARED_APPS and TENANT_APPS.
        #     The result is a zombie tenant that crashes on the very next
        #     ContentType insert. We can't simply call `migrate_schemas` to
        #     finish 0002, because *any* migration that introduces new models
        #     in the same run inserts ContentType rows and trips the NOT NULL.
        #     Drop NOT NULL + add an empty default at the SQL level first, so
        #     interim inserts succeed; 0002 then drops the column entirely.
        from django.db import connection as _conn
        from django.core.management import call_command as _cc
        try:
            with _conn.cursor() as _cur:
                _cur.execute(
                    f'ALTER TABLE "{tenant.schema_name}".django_content_type '
                    f"ALTER COLUMN name DROP NOT NULL"
                )
                _cur.execute(
                    f'ALTER TABLE "{tenant.schema_name}".django_content_type '
                    f"ALTER COLUMN name SET DEFAULT ''"
                )
        except Exception as bridge_err:  # noqa: BLE001
            # If the column was already removed (newer schema) or the table
            # is absent, that's fine — there is nothing to bridge.
            logger.debug(
                'contenttypes name-column bridge skipped for %s: %s',
                tenant.schema_name, bridge_err,
            )
        try:
            _cc('migrate_schemas', '--schema', tenant.schema_name,
                'contenttypes', verbosity=0)
        except Exception as ct_err:  # noqa: BLE001
            logger.warning(
                'contenttypes migration sweep failed for %s: %s',
                tenant.schema_name, ct_err,
            )

        # 2. Admin user + tenant role (public schema).
        with _schema_ctx('public'):
            admin_user, created = User.objects.get_or_create(
                username=admin_username.lower(),
                defaults={
                    'email': admin_email,
                    'first_name': first_name or 'Admin',
                    'last_name': last_name or tenant.name,
                    'is_staff': True,
                    'is_superuser': False,
                },
            )
            if created and temp_password:
                admin_user.set_password(temp_password)
                admin_user.save(update_fields=['password'])

            UserTenantRole.objects.get_or_create(
                user=admin_user,
                tenant=tenant,
                defaults={'role': 'admin', 'is_active': True},
            )

        # 3. Subscription + module enablement.
        plan = None
        if plan_type:
            plan = SubscriptionPlan.objects.filter(
                plan_type=plan_type, is_active=True,
            ).first()

        if plan:
            with _tx.atomic():
                TenantSubscription.objects.get_or_create(
                    tenant=tenant,
                    defaults={
                        'plan': plan,
                        'status': 'trial' if plan.trial_days else 'active',
                        'start_date': _tz.now().date(),
                        'end_date': _tz.now().date() + timedelta(
                            days=plan.trial_days or (
                                30 if plan.billing_cycle == 'monthly' else 365
                            ),
                        ),
                        'auto_renew': True,
                    },
                )

            # Signup-provided selected_modules override the plan's allowed_modules
            # so users who hand-picked modules on the marketing page get exactly
            # what they chose. Falls back to plan defaults when empty.
            modules_to_enable = list(selected_modules or []) or list(plan.allowed_modules or [])
            title_map = {key: title for key, title, _desc in AVAILABLE_MODULES}
            with _schema_ctx(tenant.schema_name):
                for mod_name in modules_to_enable:
                    PerTenantModule.objects.update_or_create(
                        module_name=mod_name,
                        defaults={
                            'module_title': title_map.get(mod_name, mod_name),
                            'description': f'Included in {plan.name} plan',
                            'is_active': True,
                        },
                    )

        # 3b. Industry-specific seed (CoA, BOMs, work centers) — best-effort.
        #     Only runs on signup, where business_category is explicit; admin
        #     creation flow leaves it blank and skips.
        if business_category and business_category != 'other':
            try:
                from core.services.industry_seed_service import (
                    seed_industry_defaults,
                )
                seed_industry_defaults(tenant.schema_name, business_category)
            except Exception as seed_err:  # noqa: BLE001
                logger.warning(
                    'industry seeding failed for %s (%s): %s',
                    tenant.schema_name, business_category, seed_err,
                )
        elif business_category:
            try:
                from core.services.industry_seed_service import _seed_setup_profile
                with _schema_ctx(tenant.schema_name):
                    _seed_setup_profile(business_category)
            except Exception:  # noqa: BLE001
                pass

        # 4. Welcome email — best-effort; a bad SMTP must not fail the tenant.
        try:
            from superadmin.views import send_tenant_welcome_email
            send_tenant_welcome_email(
                tenant, admin_user, temp_password,
                plan.name if plan else 'None',
            )
        except Exception as email_err:  # noqa: BLE001
            logger.warning('welcome email failed for %s: %s',
                           tenant.schema_name, email_err)

    except Exception as exc:
        logger.exception('tenant provisioning failed: %s', tenant.schema_name)
        tenant.provisioning_status = 'failed'
        tenant.provisioning_error = f'{type(exc).__name__}: {exc}'[:2000]
        tenant.provisioning_completed_at = _tz.now()
        tenant.save(update_fields=[
            'provisioning_status', 'provisioning_error',
            'provisioning_completed_at',
        ])
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {
                'status': 'failed', 'tenant_id': tenant_id, 'error': str(exc),
            }

    tenant.provisioning_status = 'active'
    tenant.provisioning_completed_at = _tz.now()
    tenant.save(update_fields=[
        'provisioning_status', 'provisioning_completed_at',
    ])
    logger.info(
        'tenant %s provisioned in %.1fs',
        tenant.schema_name,
        (tenant.provisioning_completed_at - tenant.provisioning_started_at).total_seconds(),
    )
    return {'status': 'active', 'tenant_id': tenant_id}


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
