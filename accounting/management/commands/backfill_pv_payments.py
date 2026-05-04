"""Backfill draft ``Payment`` rows for SCHEDULED PVs that have none.

Pre-existing scheduled PVs that were created before the
``schedule_payment`` action started auto-materialising a draft Payment
row are invisible on the Outgoing Payments page. This command walks
every SCHEDULED ``PaymentVoucherGov`` in the current schema and creates
the missing draft Payment so it surfaces in the operator's queue.

Idempotent — PVs that already have a draft Payment are skipped.

Usage::

    # Heal a single tenant
    python manage.py tenant_command backfill_pv_payments --schema=oag

    # All schemas (use ``migrate_schemas``-style helper if installed)
    python manage.py backfill_pv_payments --all-schemas
"""
from __future__ import annotations

from datetime import date as _date
from typing import Optional

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Backfill draft Payment rows for SCHEDULED PVs that don't yet "
        "have one. Heals data created before schedule_payment auto-"
        "materialised the Payment record."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be created without writing anything.',
        )

    def handle(self, *args, **options):
        from accounting.models.treasury import PaymentVoucherGov
        from accounting.models.receivables import Payment, VendorInvoice
        from accounting.models import TransactionSequence

        dry_run: bool = options['dry_run']

        scheduled = PaymentVoucherGov.objects.filter(status='SCHEDULED')
        total = scheduled.count()
        self.stdout.write(f"Found {total} SCHEDULED PVs in this schema.")

        created = 0
        skipped = 0
        for pv in scheduled.iterator():
            existing = pv.cash_payments.filter(status='Draft').first()
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
                payment_number = TransactionSequence.get_next('payment', 'PAY-')

                vendor: Optional[object] = None
                if pv.invoice_number:
                    vi = (
                        VendorInvoice.objects
                        .filter(invoice_number=pv.invoice_number)
                        .select_related('vendor')
                        .first()
                    )
                    if vi and vi.vendor_id:
                        vendor = vi.vendor

                Payment.objects.create(
                    payment_number=payment_number,
                    payment_date=_date.today(),
                    payment_method='Wire',
                    reference_number=pv.voucher_number or '',
                    total_amount=pv.net_amount,
                    status='Draft',
                    payment_voucher=pv,
                    vendor=vendor,
                    document_number=payment_number,
                )

            created += 1
            self.stdout.write(
                f"  + created Payment {payment_number} for PV {pv.voucher_number} "
                f"(NGN {pv.net_amount})"
            )

        verb = "would create" if dry_run else "created"
        self.stdout.write(self.style.SUCCESS(
            f"\nSummary: {verb} {created} Payment row(s); skipped {skipped} "
            f"(already had drafts). Total scanned: {total}."
        ))
