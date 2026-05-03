"""Tenant-aware monthly depreciation auto-run.

Invoked by cron (e.g. ``0 1 * * * python manage.py run_monthly_depreciation``)
or by a ``django-celery-beat`` PeriodicTask. Walks every tenant schema,
picks up every ``DepreciationRunSchedule`` whose ``is_active=True`` and
``next_run_date <= today``, re-queries **all eligible active assets in
that tenant** (so assets added since the previous run are included
automatically), runs the shared
``accounting.services.depreciation.run_monthly_depreciation`` in POST
mode, and advances ``next_run_date`` by one month.

Usage
=====
One-shot across every tenant::

    python manage.py run_monthly_depreciation

Dry-run preview (no DB writes, prints the same payload the API
simulation returns)::

    python manage.py run_monthly_depreciation --simulate

Single tenant::

    python manage.py run_monthly_depreciation --schema=dplux_tect

Force-run today regardless of next_run_date (manual trigger)::

    python manage.py run_monthly_depreciation --force
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import schema_context


def _month_end(d: date) -> date:
    """Last day of the month that contains ``d``."""
    last_day = calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last_day)


def _advance_month(d: date, day_of_month: int) -> date:
    """Return the same day of the following month (clamped to 28)."""
    day = min(day_of_month or 1, 28)
    if d.month == 12:
        return date(d.year + 1, 1, day)
    return date(d.year, d.month + 1, day)


class Command(BaseCommand):
    help = 'Run scheduled monthly depreciation across every active tenant schedule.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema', type=str, default=None,
            help='Restrict to a single tenant schema (defaults to every tenant).',
        )
        parser.add_argument(
            '--simulate', action='store_true',
            help='Dry-run: compute depreciation but do not post journals.',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Fire every active schedule regardless of next_run_date.',
        )

    def handle(self, *args, **options):
        from tenants.models import Client
        schemas = Client.objects.exclude(schema_name='public')
        if options.get('schema'):
            schemas = schemas.filter(schema_name=options['schema'])

        total_processed = 0
        for client in schemas:
            processed = self._run_tenant(
                client.schema_name,
                simulate=options.get('simulate', False),
                force=options.get('force', False),
            )
            total_processed += processed

        self.stdout.write(self.style.SUCCESS(
            f'Done. {total_processed} schedule(s) fired across {schemas.count()} tenant(s).'
        ))

    # ------------------------------------------------------------------
    def _run_tenant(self, schema_name: str, *, simulate: bool, force: bool) -> int:
        """Process one tenant's schedules. Returns the number fired."""
        fired = 0
        with schema_context(schema_name):
            from accounting.models import DepreciationRunSchedule
            from accounting.services.depreciation import (
                run_monthly_depreciation as run_svc,
            )

            today = timezone.localdate()
            qs = DepreciationRunSchedule.objects.filter(is_active=True)
            if not force:
                qs = qs.filter(next_run_date__lte=today)

            for sched in qs:
                # Depreciation is booked against the period END (last
                # day of the prior month that the schedule is catching
                # up on). If ``next_run_date`` is e.g. 1-May-2026 then
                # the period we depreciate is April (month-end 30-Apr).
                period = _month_end(sched.next_run_date - timedelta(days=1)) \
                    if sched.next_run_date else _month_end(today)

                try:
                    result = run_svc(
                        period_date=period,
                        asset_ids=None,     # None = every eligible active asset
                        simulate=simulate,
                        user=None,
                    )
                except Exception as exc:
                    self.stderr.write(
                        f'[{schema_name}] schedule #{sched.pk} failed: {exc}'
                    )
                    if not simulate:
                        sched.last_run_error = str(exc)[:4000]
                        sched.save(update_fields=['last_run_error'])
                    continue

                summary = result.get('summary', {})
                # Persist bookkeeping only when we actually posted
                if not simulate:
                    sched.last_run_at = timezone.now()
                    sched.last_run_period_date = period
                    sched.last_run_assets_posted = int(summary.get('posted', 0))
                    sched.last_run_total_amount = summary.get('total_amount', 0)
                    sched.last_run_skipped = int(summary.get('skipped', 0))
                    sched.last_run_error = ''
                    sched.next_run_date = _advance_month(
                        sched.next_run_date or today, sched.day_of_month,
                    )
                    sched.save()

                fired += 1
                msg = (
                    f'[{schema_name}] schedule #{sched.pk} '
                    f'mode={result.get("mode")} period={period} '
                    f'posted={summary.get("posted")} '
                    f'skipped={summary.get("skipped")} '
                    f'total={summary.get("total_amount")}'
                )
                self.stdout.write(self.style.SUCCESS(msg))
        return fired
