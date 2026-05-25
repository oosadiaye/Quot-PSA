"""
expire_warrants — flip status to EXPIRED for any warrant whose
``effective_to`` has passed and is still in an active state
(PENDING / RELEASED).

Run on a daily schedule (cron, Celery beat, Windows Task Scheduler).
The Warrant.effective_status property already overlays "EXPIRED" on
read paths so the UI is correct between runs; this command brings
the persisted ``status`` column into sync so reports that filter on
``status='RELEASED'`` don't accidentally include expired rows.

Idempotent: safe to run as often as you like; only flips rows that
need flipping.

Usage:
    python manage.py expire_warrants
    python manage.py expire_warrants --dry-run   # show what would change
"""
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from budget.models import Warrant


class Command(BaseCommand):
    help = (
        'Mark warrants whose effective_to date has passed as EXPIRED. '
        'Run daily as a scheduled task.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would change without writing.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = date.today()

        # Filter: anything still PENDING/RELEASED whose effective_to
        # is set and strictly less than today. Suspended/exhausted
        # rows are deliberately untouched — those terminal-ish states
        # carry meaning that EXPIRED would erase.
        qs = Warrant.objects.filter(
            status__in=['PENDING', 'RELEASED'],
            effective_to__isnull=False,
            effective_to__lt=today,
        )

        count = qs.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS(
                f'No warrants to expire (cutoff: {today.isoformat()}).'
            ))
            return

        if dry_run:
            self.stdout.write(
                f'[dry-run] Would mark {count} warrant(s) as EXPIRED.'
            )
            # ASCII-only output: Windows console (cp1252) on Task
            # Scheduler can't encode bullets / arrows / ellipses, and
            # this command runs unattended. Keep the diff readable
            # without forcing PYTHONIOENCODING on the operator.
            for w in qs.select_related('appropriation__administrative')[:25]:
                self.stdout.write(
                    f'  - #{w.pk} {w.authority_reference} '
                    f'({w.effective_from} -> {w.effective_to}) '
                    f'on {w.appropriation.administrative.name}'
                )
            if count > 25:
                self.stdout.write(f'  ...and {count - 25} more.')
            return

        # Single UPDATE — much cheaper than per-row save() and side-
        # effect-free (no signal handlers fire for bulk updates,
        # which is the right call: the property-based effective_status
        # already informed any subscribers in the meantime).
        with transaction.atomic():
            updated = qs.update(
                status='EXPIRED',
                updated_at=timezone.now(),
            )

        self.stdout.write(self.style.SUCCESS(
            f'Marked {updated} warrant(s) as EXPIRED (cutoff: {today.isoformat()}).'
        ))
