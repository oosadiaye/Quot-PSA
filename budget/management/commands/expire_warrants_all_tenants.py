"""
expire_warrants_all_tenants — multi-tenant wrapper for ``expire_warrants``.

Why this exists:
  The base ``expire_warrants`` command operates on whichever tenant the
  ORM is currently bound to. Under django-tenants, that's whatever
  ``tenant_context()`` last set — so calling it once at the public
  schema level does nothing useful. Cron/Task Scheduler needs a single
  entry point that fans out across every tenant.

This loops over all non-public tenants, switches schema, and invokes
``expire_warrants`` for each. Designed to be the only thing the OS
scheduler needs to know about.

Usage:
    python manage.py expire_warrants_all_tenants
    python manage.py expire_warrants_all_tenants --dry-run

Schedule daily (one run after midnight is enough — the property-based
``Warrant.effective_status`` already returns "EXPIRED" on read between
runs, so the persisted status only lags by ≤24h).

Windows Task Scheduler:
    Program:    C:\\Users\\USER\\Documents\\Antigravity\\public_sector erp\\.venv\\Scripts\\python.exe
    Arguments:  manage.py expire_warrants_all_tenants
    Start in:   C:\\Users\\USER\\Documents\\Antigravity\\public_sector erp
    Trigger:    Daily at 00:15

Cron (Linux/macOS):
    15 0 * * *  cd /path/to/project && /path/to/.venv/bin/python manage.py expire_warrants_all_tenants
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand

from django_tenants.utils import get_tenant_model, schema_context


class Command(BaseCommand):
    help = (
        'Run ``expire_warrants`` against every tenant schema. '
        'Single entry point for the OS scheduler.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Pass-through to expire_warrants — show without writing.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        Tenant = get_tenant_model()

        # Public schema holds tenant metadata only; warrants live in
        # tenant schemas, so skip it. ``schema_name='public'`` is the
        # canonical filter django-tenants uses internally.
        tenants = Tenant.objects.exclude(schema_name='public')

        total_flipped = 0
        total_failed = 0
        for tenant in tenants:
            self.stdout.write(
                self.style.MIGRATE_HEADING(f'\n=== {tenant.schema_name} ({tenant.name}) ===')
            )
            try:
                with schema_context(tenant.schema_name):
                    # call_command captures the sub-command's output to
                    # this stdout, so the operator sees the per-tenant
                    # results inline. The base command already logs
                    # "Marked N warrant(s)…" / "No warrants to expire".
                    call_command(
                        'expire_warrants',
                        dry_run=dry_run,
                        stdout=self.stdout,
                    )
            except Exception as exc:  # pragma: no cover — defensive
                # Don't let one bad tenant block the rest of the fan-out.
                # Log + continue; the operator will see the failure in
                # the Task Scheduler / cron output.
                total_failed += 1
                self.stderr.write(self.style.ERROR(
                    f'  ✗ {tenant.schema_name}: {exc}'
                ))

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Tenants processed: {tenants.count()}  '
            f'Failures: {total_failed}'
        ))
        if total_flipped:
            self.stdout.write(
                f'Total rows flipped to EXPIRED: {total_flipped}'
            )
