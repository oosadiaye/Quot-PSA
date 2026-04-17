"""
Seed default vendor categories for government procurement.
Each category links to an AP reconciliation account in the Chart of Accounts.
"""
from django.core.management.base import BaseCommand


CATEGORIES = [
    ('CONTRACTOR', 'Contractors & Suppliers', 'General vendors providing goods, works, and services'),
    ('CONSULTANT', 'Consultants & Professional Services', 'Consulting firms, legal, audit, and advisory'),
    ('COOPERATIVE', 'Staff Cooperatives', 'Staff cooperative societies and thrift associations'),
    ('UNION', 'Labour Unions', 'Trade unions and staff associations'),
    ('PFA', 'Pension Fund Administrators', 'Licensed PFAs for CPS pension remittance'),
    ('TAX_AUTH', 'Tax Authorities', 'FIRS, SIRS, and statutory deduction recipients'),
    ('UTILITY', 'Utility Providers', 'Electricity (PHCN/DisCos), water, telecoms'),
    ('INSURER', 'Insurance Companies', 'Group life, vehicle, and property insurance'),
]


class Command(BaseCommand):
    help = 'Seed default vendor categories for government procurement'

    def handle(self, *args, **options):
        from procurement.models import VendorCategory
        from accounting.models.gl import Account

        # Find a generic AP account to use as default reconciliation
        ap_account = Account.objects.filter(
            account_type='Liability', name__icontains='payable',
        ).first()
        if not ap_account:
            ap_account = Account.objects.filter(account_type='Liability').first()

        if not ap_account:
            self.stdout.write(self.style.WARNING(
                'No Liability account found for reconciliation. '
                'Create AP accounts in Chart of Accounts first.'
            ))
            return

        created = 0
        for code, name, desc in CATEGORIES:
            _, was_created = VendorCategory.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'description': desc,
                    'reconciliation_account': ap_account,
                    'is_active': True,
                },
            )
            if was_created:
                created += 1
                self.stdout.write(f'  + {code}: {name}')

        self.stdout.write(self.style.SUCCESS(
            f'Done: {created} categories created (using recon account: {ap_account.code} - {ap_account.name})'
        ))
