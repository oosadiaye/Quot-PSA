from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import tenant_context
from tenants.models import Client
from accounting.models import BudgetPeriod, Budget, MDA, Account, Fund, Function, Program, Geo
from decimal import Decimal
import datetime

class Command(BaseCommand):
    help = 'Seed budget data for the active tenant'

    def handle(self, *args, **options):
        tenant_name = 'dtsg_hq'
        try:
            tenant = Client.objects.get(schema_name=tenant_name)
        except Client.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Tenant {tenant_name} not found."))
            return

        with tenant_context(tenant):
            self.stdout.write(f'Seeding budget data for {tenant.name}...')

            # 1. Ensure Active Budget Period
            current_year = timezone.now().year
            period, created = BudgetPeriod.objects.get_or_create(
                fiscal_year=current_year,
                period_type='ANNUAL',
                period_number=1,
                defaults={
                    'start_date': datetime.date(current_year, 1, 1),
                    'end_date': datetime.date(current_year, 12, 31),
                    'status': 'ACTIVE'
                }
            )
            
            if not created and period.status != 'ACTIVE':
                period.status = 'ACTIVE'
                period.save()
            
            self.stdout.write(f"  ✓ Budget Period: {period} (Status: {period.status})")

            # 2. Ensure some budgets exist
            mda = MDA.objects.first()
            if not mda:
                mda = MDA.objects.create(code='HQ', name='Headquarters', mda_type='MINISTRY')
            
            # Use Expense accounts
            accounts = Account.objects.filter(account_type='Expense')[:5]
            if not accounts:
                # Create a sample expense account
                acc, _ = Account.objects.get_or_create(
                    code='50000000',
                    defaults={'name': 'General Operating Expenses', 'account_type': 'Expense', 'is_active': True}
                )
                accounts = [acc]

            for acc in accounts:
                budget, created = Budget.objects.get_or_create(
                    period=period,
                    mda=mda,
                    account=acc,
                    defaults={
                        'allocated_amount': Decimal('5000000.00'),
                        'revised_amount': Decimal('5000000.00'),
                        'control_level': 'HARD_STOP',
                        'enable_encumbrance': True
                    }
                )
                if created:
                    self.stdout.write(f"  ✓ Created Budget: {budget.budget_code}")

            self.stdout.write(self.style.SUCCESS('\n✅ Budget data seeded successfully!'))
