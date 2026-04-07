"""
Management command: migrate_module_data

Copies existing TenantModule and Role rows from the legacy public-schema
tables (tenants.TenantModule / tenants.Role) into each tenant's own
PostgreSQL schema (core.TenantModule / core.Role).

Run this ONCE after deploying the migration that creates core_tenantmodule
and core_role in every tenant schema:

    python manage.py migrate_schemas         # creates tables in tenant schemas
    python manage.py migrate_module_data     # copies data into each schema

After verifying data integrity, the legacy public-schema tables can be
removed in a future migration.

Options:
    --tenant <schema>   Migrate a single tenant only
    --dry-run           Show what would be copied, without writing
    --skip-roles        Only migrate TenantModule data, skip Roles
    --skip-modules      Only migrate Role data, skip TenantModules
"""
from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from tenants.models import Client


class Command(BaseCommand):
    help = 'Migrate TenantModule and Role data from public schema to per-tenant schemas'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', type=str, help='Schema name of a single tenant to migrate')
        parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
        parser.add_argument('--skip-roles', action='store_true', help='Skip Role migration')
        parser.add_argument('--skip-modules', action='store_true', help='Skip TenantModule migration')

    def handle(self, *args, **options):
        tenant_filter = options.get('tenant')
        dry_run = options['dry_run']
        skip_roles = options['skip_roles']
        skip_modules = options['skip_modules']

        tenants_qs = Client.objects.exclude(schema_name='public')
        if tenant_filter:
            tenants_qs = tenants_qs.filter(schema_name=tenant_filter)
            if not tenants_qs.exists():
                self.stderr.write(self.style.ERROR(f'Tenant "{tenant_filter}" not found.'))
                return

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Migrating data for {tenants_qs.count()} tenant(s)'
            + (' [DRY RUN]' if dry_run else '')
        ))

        total_modules = 0
        total_roles = 0

        for tenant in tenants_qs:
            self.stdout.write(f'\nTenant: {tenant.name} ({tenant.schema_name})')

            if not skip_modules:
                n = self._migrate_modules(tenant, dry_run)
                total_modules += n
                self.stdout.write(f'  TenantModule: {n} rows {"would be " if dry_run else ""}migrated')

            if not skip_roles:
                n = self._migrate_roles(tenant, dry_run)
                total_roles += n
                self.stdout.write(f'  Role: {n} rows {"would be " if dry_run else ""}migrated')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. TenantModule rows: {total_modules}, Role rows: {total_roles}'
        ))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _migrate_modules(self, tenant, dry_run):
        """Copy tenants.TenantModule rows → core.TenantModule in tenant schema."""
        from tenants.models import TenantModule as LegacyModule
        from core.models import TenantModule as PerTenantModule

        legacy_rows = LegacyModule.objects.filter(tenant=tenant)
        count = 0

        with schema_context(tenant.schema_name):
            for row in legacy_rows:
                if dry_run:
                    self.stdout.write(
                        f'    [DRY] Would upsert module: {row.module_name} '
                        f'(active={row.is_active})'
                    )
                else:
                    PerTenantModule.objects.update_or_create(
                        module_name=row.module_name,
                        defaults={
                            'module_title': row.module_title,
                            'description': row.description,
                            'is_active': row.is_active,
                        },
                    )
                count += 1

        return count

    def _migrate_roles(self, tenant, dry_run):
        """Copy tenants.Role rows → core.Role in tenant schema."""
        from tenants.models import Role as LegacyRole
        from core.models import Role as PerTenantRole

        legacy_rows = LegacyRole.objects.filter(tenant=tenant)
        count = 0

        with schema_context(tenant.schema_name):
            for row in legacy_rows:
                if dry_run:
                    self.stdout.write(
                        f'    [DRY] Would upsert role: {row.code} ({row.name})'
                    )
                else:
                    PerTenantRole.objects.update_or_create(
                        code=row.code,
                        defaults={
                            'name': row.name,
                            'module': row.module,
                            'role_type': row.role_type,
                            'can_view': row.can_view,
                            'can_add': row.can_add,
                            'can_change': row.can_change,
                            'can_delete': row.can_delete,
                            'can_approve': row.can_approve,
                            'can_post': row.can_post,
                            'is_active': row.is_active,
                            'is_default': row.is_default,
                        },
                    )
                count += 1

        return count
