"""Credit one month of leave accrual to every eligible employee.

Usage:
    python manage.py accrue_leave --year 2026 --month 4
    python manage.py accrue_leave                 # current year/month
"""
from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from hrm.services.leave_accrual import accrue_month


class Command(BaseCommand):
    help = "Run deterministic monthly leave accrual."

    def add_arguments(self, parser):
        today = date.today()
        parser.add_argument('--year', type=int, default=today.year)
        parser.add_argument('--month', type=int, default=today.month)

    def handle(self, *args, **options):
        year = options['year']
        month = options['month']
        if not (1 <= month <= 12):
            raise CommandError('--month must be 1..12.')

        summary = accrue_month(year, month)

        self.stdout.write(self.style.SUCCESS(
            f"Leave accrual {year}-{month:02d}: "
            f"{summary.entries_created} created, "
            f"{summary.entries_skipped} skipped, "
            f"{summary.total_days_credited} days credited across "
            f"{summary.employees_considered} active employees."
        ))
