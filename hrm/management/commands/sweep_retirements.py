"""Flag employees who have reached statutory retirement thresholds.

Creates a :class:`RetirementRecord` (status=Pending) for every Active
employee who is ≥60 years old OR has ≥35 years of continuous service.

Usage:
    python manage.py sweep_retirements
    python manage.py sweep_retirements --as-of 2026-12-31 --dry-run
"""
from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand

from hrm.services.lifecycle import sweep_retirements_due


class Command(BaseCommand):
    help = "Sweep active employees for statutory retirement triggers."

    def add_arguments(self, parser):
        parser.add_argument(
            '--as-of', default=None,
            help='Date to evaluate against (YYYY-MM-DD); defaults to today.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Do not write records; just report counts.',
        )

    def handle(self, *args, **options):
        as_of = (
            date.fromisoformat(options['as_of']) if options['as_of'] else None
        )
        summary = sweep_retirements_due(
            as_of=as_of, dry_run=options['dry_run'],
        )

        style = self.style.WARNING if summary.dry_run else self.style.SUCCESS
        self.stdout.write(style(
            f"Retirement sweep {summary.as_of} "
            f"({'dry-run' if summary.dry_run else 'live'}): "
            f"{summary.records_created} new, "
            f"{summary.already_flagged} already flagged, "
            f"{summary.not_eligible} not eligible "
            f"(of {summary.employees_considered} active)."
        ))
