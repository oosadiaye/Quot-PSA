"""P6-T2 — bulk rebuild of Appropriation denormalised totals.

Runs as part of the monthly-close checklist and after any data-fix
migration that touches commitments or direct AP invoices. Safe to run
repeatedly — it recomputes from live aggregates and overwrites.

Usage:
    ./manage.py resync_appropriation_totals
    ./manage.py resync_appropriation_totals --fiscal-year 2026
    ./manage.py resync_appropriation_totals --dry-run
"""
from django.core.management.base import BaseCommand

from accounting.services.appropriation_totals import refresh_totals


class Command(BaseCommand):
    help = 'Recompute cached_total_committed / cached_total_expended on every Appropriation.'

    def add_arguments(self, parser):
        parser.add_argument('--fiscal-year', type=int, default=None,
                            help='Limit to one fiscal-year year number (e.g. 2026).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Iterate and print counts without writing.')

    def handle(self, *args, **opts):
        from budget.models import Appropriation

        qs = Appropriation.objects.all()
        if opts['fiscal_year']:
            qs = qs.filter(fiscal_year__year=opts['fiscal_year'])

        total = qs.count()
        self.stdout.write(f'Resyncing {total} appropriation row(s)...')

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING('DRY RUN — no writes.'))
            return

        processed = 0
        for appr in qs.iterator(chunk_size=200):
            refresh_totals(appr)
            processed += 1
            if processed % 100 == 0:
                self.stdout.write(f'  ...{processed}/{total}')

        self.stdout.write(self.style.SUCCESS(f'Resynced {processed} appropriations.'))
