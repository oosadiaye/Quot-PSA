"""
Seed NCoA Economic Segments as Legacy Chart of Accounts
========================================================
Creates a legacy Account record for every NCoA EconomicSegment and links
them via the `legacy_account` OneToOne FK bridge.

This ensures:
1. Every NCoA code has a GL account for journal posting
2. The legacy ChartOfAccounts UI shows NCoA-aligned accounts
3. Treasury/Revenue journal posting finds correct GL accounts (no .first() fallback)
4. IPSAS reports can aggregate via either NCoA or legacy path

Run: python manage.py seed_ncoa_as_coa
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from accounting.models.gl import Account
from accounting.models.ncoa import EconomicSegment


# Map NCoA account_type_code to legacy account_type
NCOA_TO_LEGACY_TYPE = {
    '1': 'Income',
    '2': 'Expense',
    '3': 'Asset',
    '4': 'Liability',  # Includes Net Assets/Equity
}

# Special override: Net Assets codes map to Equity
EQUITY_PREFIXES = ('43',)  # 43xxxxxx = Net Assets / Equity


class Command(BaseCommand):
    help = 'Create legacy Account records from NCoA EconomicSegments and link via bridge FK'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Preview changes without writing to DB',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        created = linked = skipped = 0

        segments = EconomicSegment.objects.all().order_by('code')
        self.stdout.write(f'Processing {segments.count()} NCoA Economic Segments...')

        for seg in segments:
            # Determine legacy account_type
            if seg.code[:2] in EQUITY_PREFIXES:
                legacy_type = 'Equity'
            else:
                legacy_type = NCOA_TO_LEGACY_TYPE.get(seg.account_type_code, 'Expense')

            # Determine parent Account (if segment has a parent)
            parent_account = None
            if seg.parent and seg.parent.legacy_account:
                parent_account = seg.parent.legacy_account

            if dry_run:
                status = 'EXISTS' if seg.legacy_account else 'CREATE'
                self.stdout.write(f'  [{status}] {seg.code} | {seg.name} | {legacy_type}')
                if status == 'CREATE':
                    created += 1
                else:
                    skipped += 1
                continue

            # Check if already linked
            if seg.legacy_account:
                # Update existing account to match NCoA
                acct = seg.legacy_account
                acct.name = seg.name
                acct.account_type = legacy_type
                acct.is_active = seg.is_active
                acct.parent = parent_account
                acct.save(update_fields=['name', 'account_type', 'is_active', 'parent'])
                linked += 1
                continue

            # Check if a legacy Account with this code already exists
            existing = Account.objects.filter(code=seg.code).first()
            if existing:
                # Link existing account to this segment
                seg.legacy_account = existing
                seg.save(update_fields=['legacy_account'])
                # Update account details to match NCoA
                existing.name = seg.name
                existing.account_type = legacy_type
                existing.is_active = seg.is_active
                existing.parent = parent_account
                existing.save(update_fields=['name', 'account_type', 'is_active', 'parent'])
                linked += 1
                self.stdout.write(f'  [LINKED] {seg.code} | {seg.name}')
                continue

            # Create new Account
            acct = Account.objects.create(
                code=seg.code,
                name=seg.name,
                account_type=legacy_type,
                is_active=seg.is_active,
                parent=parent_account,
                is_reconciliation=seg.is_control_account,
                reconciliation_type=self._get_recon_type(seg),
            )

            # Link the bridge
            seg.legacy_account = acct
            seg.save(update_fields=['legacy_account'])
            created += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'\nDRY RUN: Would create {created}, skip {skipped}'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\nNCoA -> Chart of Accounts bridge complete:\n'
                f'  Created: {created}\n'
                f'  Linked:  {linked}\n'
                f'  Skipped: {skipped}\n'
                f'  Total Accounts: {Account.objects.count()}\n'
                f'  Linked Segments: {EconomicSegment.objects.filter(legacy_account__isnull=False).count()}'
            ))

    def _get_recon_type(self, seg: EconomicSegment) -> str:
        """Map NCoA control accounts to reconciliation types."""
        code = seg.code
        if code.startswith('411'):   # Accounts Payable
            return 'accounts_payable'
        if code.startswith('312'):   # Receivables
            return 'accounts_receivable'
        if code.startswith('314'):   # Inventory
            return 'inventory'
        if code.startswith('32'):    # Non-current assets
            return 'asset_accounting'
        if code.startswith('311'):   # Cash / TSA
            return 'bank_accounting'
        return ''
