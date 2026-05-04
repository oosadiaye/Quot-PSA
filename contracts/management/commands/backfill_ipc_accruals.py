"""Retroactively post the accrual journal for orphan IPCs.

Historical IPCs that reached APPROVED / VOUCHER_RAISED / PAID before
the fail-closed approval fix landed may have a NULL ``accrual_journal``
field — the post-and-swallow path silently dropped the journal while
still transitioning the IPC. The IPC's "GL Ledger Projected" panel
still renders the projected lines (it computes them on demand) but
``GLBalance`` was never updated, so every IPSAS report under-reports
the expense.

This command walks every such orphan, calls
``IPCService._post_accrual_journal`` to materialise the journal, and
links it back to the IPC. Idempotent — IPCs that already have an
``accrual_journal`` are skipped.

Usage::

    # Dry-run for a tenant (recommended first)
    python manage.py tenant_command backfill_ipc_accruals \\
        --schema=office_of_accountant_general_delta_state --dry-run

    # Apply
    python manage.py tenant_command backfill_ipc_accruals \\
        --schema=office_of_accountant_general_delta_state
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Backfill accrual journals for IPCs in APPROVED / VOUCHER_RAISED "
        "/ PAID status that have no linked ``accrual_journal``. Idempotent."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be posted without writing anything.',
        )
        parser.add_argument(
            '--actor-username',
            help=(
                'Username to attribute the back-posting to. Defaults to '
                'the first superuser in the schema.'
            ),
        )

    def handle(self, *args, **options):
        from contracts.models import InterimPaymentCertificate
        from contracts.services.ipc_service import IPCService

        dry_run: bool = options['dry_run']
        User = get_user_model()
        actor = None
        if options.get('actor_username'):
            actor = User.objects.filter(username=options['actor_username']).first()
        if actor is None:
            actor = User.objects.filter(is_superuser=True).order_by('id').first()
        if actor is None:
            self.stderr.write(self.style.ERROR(
                "No actor user available. Pass --actor-username or create a superuser first."
            ))
            return

        orphans = (
            InterimPaymentCertificate.objects
            .filter(
                status__in=['APPROVED', 'VOUCHER_RAISED', 'PAID'],
                accrual_journal__isnull=True,
            )
            .select_related('contract')
        )
        total = orphans.count()
        self.stdout.write(
            f"Found {total} orphan IPC(s) needing accrual back-post."
        )

        posted = 0
        failed = 0
        for ipc in orphans.iterator():
            label = f"IPC {ipc.ipc_number} (pk={ipc.pk}, status={ipc.status})"
            if dry_run:
                self.stdout.write(f"  [DRY] would post accrual for {label}")
                posted += 1
                continue
            try:
                with transaction.atomic():
                    journal = IPCService._post_accrual_journal(ipc, actor)
                    # IPCService._post_accrual_journal sets ipc.accrual_journal
                    # in-memory; persist the link explicitly.
                    InterimPaymentCertificate.objects.filter(pk=ipc.pk).update(
                        accrual_journal=journal,
                    )
                self.stdout.write(self.style.SUCCESS(
                    f"  + posted {journal.reference_number} for {label}"
                ))
                posted += 1
            except Exception as exc:  # noqa: BLE001 — surface the exact failure per IPC
                failed += 1
                self.stderr.write(self.style.WARNING(
                    f"  ! failed to post for {label}: {exc}"
                ))

        verb = "would post" if dry_run else "posted"
        summary = (
            f"\nSummary: {verb} {posted}; failed {failed}; total scanned {total}."
        )
        if failed:
            self.stdout.write(self.style.WARNING(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
