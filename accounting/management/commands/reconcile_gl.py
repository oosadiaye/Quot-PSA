from django.core.management.base import BaseCommand
from django.db import connection, transaction


class Command(BaseCommand):
    help = 'Reconcile GL balances from posted journal entries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Actually fix the GL balances',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        fix = options['fix']

        with connection.cursor() as cursor:
            # Find accounts with journal entries but no GL balance
            cursor.execute('''
                SELECT DISTINCT l.account_id, a.code, a.name
                FROM accounting_journalline l
                JOIN accounting_journalheader h ON l.header_id = h.id
                JOIN accounting_account a ON l.account_id = a.id
                WHERE h.status = 'Posted'
                AND l.account_id NOT IN (
                    SELECT DISTINCT account_id FROM accounting_glbalance 
                    WHERE account_id IS NOT NULL
                )
            ''')
            missing_accounts = cursor.fetchall()

            if not missing_accounts:
                self.stdout.write(
                    self.style.SUCCESS('All accounts with journal entries have GL balances.')
                )
                return

            self.stdout.write(
                self.style.WARNING(f'Found {len(missing_accounts)} accounts missing GL balances:')
            )
            for acc_id, code, name in missing_accounts:
                self.stdout.write(f'  - {code}: {name} (ID: {acc_id})')

            if dry_run:
                self.stdout.write(
                    self.style.WARNING('DRY RUN - No changes made')
                )
                return

            if not fix:
                self.stdout.write(
                    self.style.WARNING('Run with --fix to create missing GL balances')
                )
                return

            # Create missing GL balances
            with transaction.atomic():
                sql = '''
                INSERT INTO accounting_glbalance 
                    (fiscal_year, period, account_id, debit_balance, credit_balance, 
                     function_id, fund_id, geo_id, program_id)
                SELECT 
                    EXTRACT(YEAR FROM h.posting_date)::integer as fiscal_year,
                    EXTRACT(MONTH FROM h.posting_date)::integer as period,
                    l.account_id,
                    COALESCE(SUM(l.debit), 0) as debit_balance,
                    COALESCE(SUM(l.credit), 0) as credit_balance,
                    h.function_id,
                    h.fund_id,
                    h.geo_id,
                    h.program_id
                FROM accounting_journalline l
                JOIN accounting_journalheader h ON l.header_id = h.id
                WHERE h.status = 'Posted'
                AND l.account_id NOT IN (
                    SELECT DISTINCT account_id FROM accounting_glbalance 
                    WHERE account_id IS NOT NULL
                )
                GROUP BY 
                    EXTRACT(YEAR FROM h.posting_date)::integer,
                    EXTRACT(MONTH FROM h.posting_date)::integer,
                    l.account_id, h.function_id, h.fund_id, h.geo_id, h.program_id
                '''
                cursor.execute(sql)
                self.stdout.write(
                    self.style.SUCCESS(f'Created {cursor.rowcount} GL balance records')
                )

            # Verify fix
            cursor.execute('''
                SELECT COUNT(DISTINCT l.account_id)
                FROM accounting_journalline l
                JOIN accounting_journalheader h ON l.header_id = h.id
                WHERE h.status = 'Posted'
                AND l.account_id NOT IN (
                    SELECT DISTINCT account_id FROM accounting_glbalance 
                    WHERE account_id IS NOT NULL
                )
            ''')
            remaining = cursor.fetchone()[0]
            if remaining == 0:
                self.stdout.write(
                    self.style.SUCCESS('GL balance reconciliation complete!')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'Still have {remaining} accounts missing balances')
                )
