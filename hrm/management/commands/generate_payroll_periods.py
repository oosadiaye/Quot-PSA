"""Create twelve monthly :class:`PayrollPeriod` rows for a calendar year.

Usage:
    python manage.py generate_payroll_periods --year 2026
    python manage.py generate_payroll_periods --year 2026 --payment-day 28
"""
from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from hrm.services.payroll_runner import generate_monthly_periods


class Command(BaseCommand):
    help = "Generate twelve monthly PayrollPeriod rows for a given year."

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=date.today().year,
            help="Calendar year to generate periods for (default: current year).",
        )
        parser.add_argument(
            "--payment-day",
            type=int,
            default=25,
            help="Day of month for payment_date (clamped to month length).",
        )

    def handle(self, *args, **options):
        year = options["year"]
        payment_day = options["payment_day"]

        if not (1 <= payment_day <= 31):
            raise CommandError("--payment-day must be between 1 and 31.")
        if year < 2000 or year > 2100:
            raise CommandError("--year must be between 2000 and 2100.")

        created = generate_monthly_periods(year, payment_day=payment_day)

        if not created:
            self.stdout.write(
                self.style.WARNING(
                    f"All 12 monthly periods for {year} already exist — nothing to do."
                )
            )
            return

        for period in created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  + {period.start_date} → {period.end_date} (pay {period.payment_date})"
                )
            )
        self.stdout.write(
            self.style.SUCCESS(f"Created {len(created)} payroll periods for {year}.")
        )
