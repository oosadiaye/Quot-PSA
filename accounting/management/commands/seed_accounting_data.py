from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import tenant_context
from tenants.models import Client
from datetime import timedelta
from decimal import Decimal
from accounting.models import (
    Currency, VendorInvoice, CustomerInvoice, FixedAsset,
    GLBalance, Fund, Function, Program, Geo, Account,
    AccountingSettings,
)
from procurement.models import Vendor

class Command(BaseCommand):
    help = 'Seed demo accounting data for testing'

    def handle(self, *args, **options):
        tenant_name = 'dtsg_hq'
        try:
            tenant = Client.objects.get(schema_name=tenant_name)
        except Client.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Tenant {tenant_name} not found."))
            return

        with tenant_context(tenant):
            self.stdout.write(f'Seeding accounting data for {tenant.name}...')

            # Get existing dimensions (required for all transactions)
            try:
                fund = Fund.objects.first()
                function = Function.objects.first()
                program = Program.objects.first()
                geo = Geo.objects.first()

                if not all([fund, function, program, geo]):
                    self.stdout.write(self.style.ERROR('ERROR: Missing required dimensions (Fund, Function, Program, Geo).'))
                    self.stdout.write(self.style.WARNING('Please run seed_demo_data command first to create dimensions.'))
                    return
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'ERROR: Could not access dimension tables: {e}'))
                return

            # Get existing accounts
            try:
                cash_account = Account.objects.filter(code__startswith='101').first()
                ar_account = Account.objects.filter(code__startswith='102').first()
                ap_account = Account.objects.filter(code__startswith='201').first()
                revenue_account = Account.objects.filter(code__startswith='401').first()
                expense_account = Account.objects.filter(code__startswith='501').first()
                asset_account = Account.objects.filter(code__startswith='103').first()

                if not all([cash_account, ar_account, ap_account, revenue_account, expense_account, asset_account]):
                    self.stdout.write(self.style.WARNING('WARNING: Some accounts not found. Creating default accounts...'))

                    # Create minimal accounts if they don't exist
                    cash_account, _ = Account.objects.get_or_create(
                        code='10100000',
                        defaults={'name': 'Cash in Bank', 'account_type': 'Asset', 'is_active': True}
                    )
                    ar_account, _ = Account.objects.get_or_create(
                        code='10200000',
                        defaults={'name': 'Accounts Receivable', 'account_type': 'Asset', 'is_active': True}
                    )
                    ap_account, _ = Account.objects.get_or_create(
                        code='20100000',
                        defaults={'name': 'Accounts Payable', 'account_type': 'Liability', 'is_active': True}
                    )
                    revenue_account, _ = Account.objects.get_or_create(
                        code='40100000',
                        defaults={'name': 'Service Revenue', 'account_type': 'Income', 'is_active': True}
                    )
                    expense_account, _ = Account.objects.get_or_create(
                        code='50100000',
                        defaults={'name': 'Operating Expenses', 'account_type': 'Expense', 'is_active': True}
                    )
                    asset_account, _ = Account.objects.get_or_create(
                        code='10300000',
                        defaults={'name': 'Fixed Assets', 'account_type': 'Asset', 'is_active': True}
                    )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'ERROR: Could not access Account table: {e}'))
                return


            # 1. Seed Currencies — NGN (Nigerian Naira) as base currency
            self.stdout.write('Creating currencies...')
            ngn, created = Currency.objects.get_or_create(
                code='NGN',
                defaults={
                    'name': 'Nigerian Naira',
                    'symbol': '\u20a6',
                    'exchange_rate': Decimal('1.00'),
                    'is_base': True,
                    'is_active': True
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  Created currency: {ngn.code}'))

            currencies_data = [
                {'code': 'USD', 'name': 'US Dollar', 'symbol': '$', 'rate': '0.00065'},
                {'code': 'EUR', 'name': 'Euro', 'symbol': '\u20ac', 'rate': '0.00060'},
                {'code': 'GBP', 'name': 'British Pound', 'symbol': '\u00a3', 'rate': '0.00052'},
                {'code': 'CAD', 'name': 'Canadian Dollar', 'symbol': 'C$', 'rate': '0.00088'},
            ]

            for curr_data in currencies_data:
                currency, created = Currency.objects.get_or_create(
                    code=curr_data['code'],
                    defaults={
                        'name': curr_data['name'],
                        'symbol': curr_data['symbol'],
                        'exchange_rate': Decimal(curr_data['rate']),
                        'is_base': False,
                        'is_active': True
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Created currency: {currency.code}'))

            # Set NGN as default currency in AccountingSettings
            settings_obj, _ = AccountingSettings.objects.get_or_create(pk=1)
            if not settings_obj.default_currency_1:
                settings_obj.default_currency_1 = ngn
                settings_obj.save()
                self.stdout.write(self.style.SUCCESS('  Set NGN as default currency'))

            # 2. Seed Vendor Invoices (AP)
            self.stdout.write('Creating vendor invoices...')
            vendors = list(Vendor.objects.all()[:5])
            if not vendors:
                self.stdout.write(self.style.WARNING('  ! No vendors found. Run seed_demo_data first.'))
            else:
                statuses = ['Draft', 'Approved', 'Partially Paid', 'Paid']
                for i, vendor in enumerate(vendors):
                    for j in range(2):  # 2 invoices per vendor
                        invoice_date = timezone.now().date() - timedelta(days=30 + i * 10 + j * 5)
                        due_date = invoice_date + timedelta(days=30)
                        amount = Decimal(str(1000 + i * 500 + j * 250))

                        invoice, created = VendorInvoice.objects.get_or_create(
                            invoice_number=f'VINV-{i+1:03d}-{j+1}',
                            defaults={
                                'vendor': vendor,
                                'invoice_date': invoice_date,
                                'due_date': due_date,
                                'subtotal': amount,
                                'tax_amount': Decimal('0.00'),
                                'total_amount': amount,
                                'currency': ngn,
                                'status': statuses[j % len(statuses)],
                                'fund': fund,
                                'function': function,
                                'program': program,
                                'geo': geo
                            }
                        )
                        if created:
                            self.stdout.write(self.style.SUCCESS(f'  ✓ Created vendor invoice: {invoice.invoice_number}'))

            # 3. Seed Fixed Assets (Customer invoices skipped — sales module removed)
            self.stdout.write('Creating fixed assets...')

            # Get depreciation accounts — use exact codes matching seed_coa.py entries
            depreciation_expense_account = Account.objects.filter(code='66100000').first()
            accumulated_depreciation_account = Account.objects.filter(code='12306000').first()

            if not depreciation_expense_account:
                depreciation_expense_account, _ = Account.objects.get_or_create(
                    code='66100000',
                    defaults={'name': 'Depreciation Expense', 'account_type': 'Expense', 'is_active': True}
                )
            if not accumulated_depreciation_account:
                accumulated_depreciation_account, _ = Account.objects.get_or_create(
                    code='12306000',
                    defaults={'name': 'Accumulated Depreciation - Equipment', 'account_type': 'Asset', 'is_active': True}
                )

            assets_data = [
                {'name': 'Dell Latitude Laptop', 'category': 'IT', 'tag': 'IT-001', 'cost': '1200', 'life': 3},
                {'name': 'HP LaserJet Printer', 'category': 'IT', 'tag': 'IT-002', 'cost': '800', 'life': 5},
                {'name': 'Ford Transit Van', 'category': 'Vehicle', 'tag': 'VEH-001', 'cost': '35000', 'life': 7},
                {'name': 'Office Desk Set', 'category': 'Furniture', 'tag': 'FUR-001', 'cost': '1500', 'life': 10},
                {'name': 'Conference Table', 'category': 'Furniture', 'tag': 'FUR-002', 'cost': '2500', 'life': 10},
                {'name': 'Manufacturing Equipment', 'category': 'Equipment', 'tag': 'EQ-001', 'cost': '50000', 'life': 15},
                {'name': 'Office Building', 'category': 'Building', 'tag': 'BLDG-001', 'cost': '500000', 'life': 30},
            ]

            for i, asset_data in enumerate(assets_data):
                acquisition_date = timezone.now().date() - timedelta(days=365 + i * 60)
                cost = Decimal(asset_data['cost'])
                useful_life = asset_data['life']

                # Calculate depreciation (straight-line)
                days_owned = (timezone.now().date() - acquisition_date).days
                years_owned = days_owned / 365.25
                annual_depreciation = cost / useful_life
                accumulated_depreciation = min(annual_depreciation * Decimal(str(years_owned)), cost)

                asset, created = FixedAsset.objects.get_or_create(
                    asset_number=asset_data['tag'],
                    defaults={
                        'name': asset_data['name'],
                        'asset_category': asset_data['category'],
                        'acquisition_date': acquisition_date,
                        'acquisition_cost': cost,
                        'useful_life_years': useful_life,
                        'accumulated_depreciation': accumulated_depreciation.quantize(Decimal('0.01')),
                        'status': 'Active',
                        'fund': fund,
                        'function': function,
                        'program': program,
                        'geo': geo,
                        'asset_account': asset_account,
                        'depreciation_expense_account': depreciation_expense_account,
                        'accumulated_depreciation_account': accumulated_depreciation_account
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Created fixed asset: {asset.name}'))

            # 5. Seed GL Balances (from existing data)
            self.stdout.write('Creating GL balances...')
            current_year = timezone.now().year
            current_period = timezone.now().month

            # Create sample balances for key accounts
            balances_data = [
                {'account': cash_account, 'debit': '50000', 'credit': '0'},
                {'account': ar_account, 'debit': '25000', 'credit': '0'},
                {'account': ap_account, 'debit': '0', 'credit': '15000'},
                {'account': revenue_account, 'debit': '0', 'credit': '75000'},
                {'account': expense_account, 'debit': '45000', 'credit': '0'},
                {'account': asset_account, 'debit': '590000', 'credit': '0'},
            ]

            for balance_data in balances_data:
                balance, created = GLBalance.objects.get_or_create(
                    account=balance_data['account'],
                    fund=fund,
                    function=function,
                    program=program,
                    geo=geo,
                    fiscal_year=current_year,
                    period=current_period,
                    defaults={
                        'debit_balance': Decimal(balance_data['debit']),
                        'credit_balance': Decimal(balance_data['credit'])
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Created GL balance: {balance.account.name}'))

            self.stdout.write(self.style.SUCCESS('\n✅ Accounting demo data seeded successfully!'))
            self.stdout.write(self.style.SUCCESS(f'   - {Currency.objects.count()} currencies'))
            self.stdout.write(self.style.SUCCESS(f'   - {VendorInvoice.objects.count()} vendor invoices'))
            self.stdout.write(self.style.SUCCESS(f'   - {CustomerInvoice.objects.count()} customer invoices'))
            self.stdout.write(self.style.SUCCESS(f'   - {FixedAsset.objects.count()} fixed assets'))
            self.stdout.write(self.style.SUCCESS(f'   - {GLBalance.objects.count()} GL balances'))
