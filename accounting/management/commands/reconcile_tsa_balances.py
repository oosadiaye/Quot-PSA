"""Rebuild TreasuryAccount.current_balance from the GL cash account.

``current_balance`` is a denormalised cache of the TSA's GL cash-control
account. Most posting paths keep the two in step, but some (notably
vendor advances) posted to the GL without updating the field, so the
stored balance drifted from the double-entry truth — the gap the TSA
ledger's reconciliation banner reports.

This recomputes ``current_balance`` = net of the GL cash account
(debits raise cash, credits lower it) for every TSA. Idempotent: safe to
run repeatedly, and a clean run reports no changes.

Runs against the CURRENT schema — invoke per tenant (e.g. via
django-tenants ``tenant_command`` or inside a ``schema_context``).

Usage:
    ./manage.py reconcile_tsa_balances
    ./manage.py reconcile_tsa_balances --dry-run
"""
from django.core.management.base import BaseCommand

from accounting.services.treasury_service import TSABalanceService


class Command(BaseCommand):
    help = "Rebuild every TreasuryAccount.current_balance from its GL cash account."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would change without writing.',
        )

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        results = TSABalanceService.reconcile_all(dry_run=dry)

        if not results:
            self.stdout.write('No TSA accounts with a GL cash account.')
            return

        changed = 0
        for tsa, before, after in results:
            if before != after:
                changed += 1
                self.stdout.write(
                    f'  {tsa.account_number} ({tsa.account_name}): '
                    f'{before} -> {after}  (diff {after - before})'
                )

        verb = 'would reconcile' if dry else 'reconciled'
        if changed:
            style = self.style.WARNING if dry else self.style.SUCCESS
            self.stdout.write(style(
                f'{verb} {changed} of {len(results)} TSA account(s).'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'All {len(results)} TSA account(s) already reconcile with the GL.'
            ))
