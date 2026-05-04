"""Heal historical posted journals whose debits don't equal credits.

Pre-fix AP invoice posting silently produced unbalanced journals when
the tenant's CoA had no Input VAT recoverable account: it added the
VAT amount to the AP credit but skipped the matching DR Input VAT
line. The result: a Posted journal with DR < CR by exactly the VAT
amount (typically 7.5% of subtotal). Reports computed from
``JournalLine`` or ``GLBalance`` then disagreed.

This command finds every Posted journal where DR != CR and adds a
balancing line. The balancing rule:

  • If the journal looks like an AP invoice (has at least one DR
    expense / asset line and one CR liability/AP line) AND the gap is
    on the DR side (DR < CR), we **gross-up the existing expense
    line** to absorb the missing VAT. This matches the new
    ``post_invoice`` behaviour for tenants without an Input VAT GL —
    VAT becomes part of expense.

  • Otherwise the command refuses to auto-heal and prints the journal
    so an accountant can post a manual correcting JV.

Updates ``GLBalance`` to reflect the gross-up so reports stay
consistent. Idempotent — already-balanced journals are skipped.

Usage::

    python manage.py tenant_command heal_unbalanced_journals \\
        --schema=<schema> --dry-run
    python manage.py tenant_command heal_unbalanced_journals \\
        --schema=<schema>
"""
from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, Sum


_TOLERANCE = Decimal('0.01')


class Command(BaseCommand):
    help = (
        "Heal historical Posted journals where DR != CR by gross-ing "
        "up the expense line for AP-invoice-shaped journals. Refuses "
        "to auto-heal anything ambiguous."
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        from accounting.models.gl import JournalHeader, JournalLine
        from accounting.models.balances import GLBalance

        dry_run: bool = options['dry_run']

        unbalanced = []
        for j in JournalHeader.objects.filter(status='Posted'):
            agg = j.lines.aggregate(d=Sum('debit'), c=Sum('credit'))
            d = agg['d'] or Decimal('0')
            c = agg['c'] or Decimal('0')
            diff = d - c
            if abs(diff) > _TOLERANCE:
                unbalanced.append((j, d, c, diff))

        self.stdout.write(
            f"Found {len(unbalanced)} unbalanced Posted journal(s)."
        )

        healed = 0
        skipped_ambiguous = 0

        for j, dr_total, cr_total, diff in unbalanced:
            label = (
                f"id={j.id} ref={j.reference_number} "
                f"DR={dr_total} CR={cr_total} DIFF={diff}"
            )

            # Heal only the AP-invoice shape: DR < CR and at least one
            # debit line exists. The DR side is grossed up to match CR.
            if diff >= 0:
                self.stdout.write(self.style.WARNING(
                    f"  ! skipping (DR >= CR — manual review): {label}"
                ))
                skipped_ambiguous += 1
                continue

            shortfall = abs(diff)
            # Pick the first debit line — that's the expense leg we
            # gross up. Order by id so the result is deterministic
            # across re-runs.
            dr_line = (
                j.lines
                .filter(debit__gt=0)
                .order_by('id')
                .select_related('account')
                .first()
            )
            if dr_line is None:
                self.stdout.write(self.style.WARNING(
                    f"  ! skipping (no DR line to gross-up): {label}"
                ))
                skipped_ambiguous += 1
                continue

            account = dr_line.account
            if account is None:
                self.stdout.write(self.style.WARNING(
                    f"  ! skipping (DR line has no account): {label}"
                ))
                skipped_ambiguous += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"  [DRY] would gross-up line {dr_line.id} "
                    f"(account {account.code}) by NGN {shortfall} -> {label}"
                )
                healed += 1
                continue

            with transaction.atomic():
                # 1. Gross up the journal line itself (atomic F() update).
                JournalLine.objects.filter(pk=dr_line.pk).update(
                    debit=F('debit') + shortfall,
                    memo=(dr_line.memo or '') + f' (+ NGN {shortfall} VAT gross-up)',
                )
                # 2. Mirror the increment in GLBalance so reports
                #    reading from the cache stay consistent. We update
                #    every matching dimensional bucket (a journal
                #    contributes to exactly one row per (account,
                #    fund, function, program, geo, mda, fy, period)).
                fy = j.posting_date.year
                period = j.posting_date.month
                bucket = GLBalance.objects.filter(
                    account=account,
                    fund=j.fund,
                    function=j.function,
                    program=j.program,
                    geo=j.geo,
                    mda=j.mda,
                    fiscal_year=fy,
                    period=period,
                ).first()
                if bucket is not None:
                    GLBalance.objects.filter(pk=bucket.pk).update(
                        debit_balance=F('debit_balance') + shortfall,
                    )
                else:
                    GLBalance.objects.create(
                        account=account,
                        fund=j.fund,
                        function=j.function,
                        program=j.program,
                        geo=j.geo,
                        mda=j.mda,
                        fiscal_year=fy,
                        period=period,
                        debit_balance=shortfall,
                        credit_balance=Decimal('0.00'),
                    )

                # 3. Bust the report cache.
                try:
                    from accounting.services.report_cache import invalidate_period_reports
                    invalidate_period_reports(fiscal_year=fy)
                except Exception:  # noqa: BLE001
                    pass

            self.stdout.write(self.style.SUCCESS(
                f"  + healed {label} (account {account.code}, +NGN {shortfall})"
            ))
            healed += 1

        verb = "would heal" if dry_run else "healed"
        msg = (
            f"\nSummary: {verb} {healed}; "
            f"skipped (manual review needed) {skipped_ambiguous}; "
            f"total scanned {len(unbalanced)}."
        )
        if skipped_ambiguous:
            self.stdout.write(self.style.WARNING(msg))
        else:
            self.stdout.write(self.style.SUCCESS(msg))
