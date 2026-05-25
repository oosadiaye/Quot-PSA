"""
``manage.py seed_tenant_defaults`` — backfill or refresh default
FiscalYear / FiscalPeriod / BudgetPeriod / CoA / BudgetCheckRule /
TreasuryAccount rows on existing tenants.

Why this command exists
-----------------------
``tenants.tasks.provision_tenant_schema`` now seeds these on first
provision (see step 3a). Tenants that pre-date that change are missing
the defaults — their operators see "No period defined for date X" on
every journal post. This command sweeps every active tenant (or one
named via ``--schema``) and runs ``TenantDefaultsSeeder.seed_all()``,
which is idempotent: re-running on a fully-seeded tenant is a no-op.

Examples::

    # Backfill every active tenant
    python manage.py seed_tenant_defaults

    # One tenant only (handy for spot fixes)
    python manage.py seed_tenant_defaults --schema delta_state

    # Override the FY anchor year (default = today's calendar year)
    python manage.py seed_tenant_defaults --year 2027
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        'Seed tenant defaults (FiscalYear, periods, CoA, BudgetCheckRule, TSA) '
        'across every active tenant. Idempotent.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema',
            help=(
                'Restrict the run to a single tenant schema. Omit to '
                'iterate every active tenant (skipping public).'
            ),
        )
        parser.add_argument(
            '--year',
            type=int,
            help=(
                'Override the FY anchor year used by placeholder '
                'substitution (default: today\'s calendar year).'
            ),
        )

    def handle(self, *args, **options):
        from tenants.models import Client
        from tenants.services.default_seeder import TenantDefaultsSeeder

        schema = options.get('schema')
        year = options.get('year')

        if schema:
            schemas = [schema]
        else:
            # Iterate every active tenant, skipping the public schema
            # (which holds the shared Client/Domain rows, not tenant
            # tables). Use ``values_list`` so we don't materialise
            # full Client objects we don't need.
            schemas = list(
                Client.objects
                .exclude(schema_name='public')
                .filter(provisioning_status='active')
                .values_list('schema_name', flat=True)
            )

        if not schemas:
            self.stdout.write(self.style.WARNING(
                'No tenants matched. Nothing to do.'
            ))
            return

        total_rows = 0
        for s in schemas:
            try:
                report = TenantDefaultsSeeder(s, year=year).seed_all()
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(self.style.ERROR(
                    f'  {s}: FAILED — {type(exc).__name__}: {exc}'
                ))
                continue
            total_rows += report.total()
            self.stdout.write(
                f'  {s}: {report.total()} rows created '
                f'(FY={report.fiscal_year_created}, '
                f'FP={report.fiscal_periods_created}, '
                f'BP={report.budget_periods_created}, '
                f'Acct={report.accounts_created}, '
                f'Rule={report.rules_created}, '
                f'TSA={report.tsa_created})'
                + (f' — skipped: {", ".join(report.skipped)}' if report.skipped else '')
            )

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Tenants processed: {len(schemas)}, total rows created: {total_rows}'
        ))
