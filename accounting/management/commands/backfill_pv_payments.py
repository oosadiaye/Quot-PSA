"""Backfill draft ``Payment`` rows for APPROVED/SCHEDULED PVs that have none.

Pre-existing PVs approved/scheduled before the approve + schedule_payment
actions started auto-materialising a draft Payment row are invisible on
the Outgoing Payments page. This command walks every APPROVED or
SCHEDULED ``PaymentVoucherGov`` in the current schema and creates the
missing draft Payment so it surfaces in the operator's queue.

Uses the same ``ensure_draft_payment_for_pv`` helper as the live flow,
so advance PVs get ``is_advance`` and invoice PVs get their allocation.

Idempotent — PVs that already have a live Payment are skipped.

Usage::

    # Heal a single tenant
    python manage.py tenant_command backfill_pv_payments --schema=oag

    # All schemas (use ``migrate_schemas``-style helper if installed)
    python manage.py backfill_pv_payments --all-schemas
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Backfill draft Payment rows for APPROVED/SCHEDULED PVs that don't "
        "yet have one. Heals data created before approve/schedule_payment "
        "auto-materialised the Payment record."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be created without writing anything.',
        )

    def handle(self, *args, **options):
        from accounting.models.treasury import PaymentVoucherGov
        from accounting.services.pv_payment_provisioning import (
            ensure_draft_payment_for_pv,
        )

        dry_run: bool = options['dry_run']

        pending = PaymentVoucherGov.objects.filter(
            status__in=['APPROVED', 'SCHEDULED'],
        )
        total = pending.count()
        self.stdout.write(f"Found {total} APPROVED/SCHEDULED PVs in this schema.")

        created = 0
        skipped = 0
        for pv in pending.iterator():
            existing = pv.cash_payments.exclude(status='Void').first()
            if existing is not None:
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"  [DRY] would create Payment for PV {pv.voucher_number} "
                    f"(NGN {pv.net_amount})"
                )
                created += 1
                continue

            with transaction.atomic():
                payment = ensure_draft_payment_for_pv(pv)

            created += 1
            self.stdout.write(
                f"  + created Payment {payment.payment_number} for PV "
                f"{pv.voucher_number} (NGN {pv.net_amount})"
            )

        verb = "would create" if dry_run else "created"
        self.stdout.write(self.style.SUCCESS(
            f"\nSummary: {verb} {created} Payment row(s); skipped {skipped} "
            f"(already had a live Payment). Total scanned: {total}."
        ))
