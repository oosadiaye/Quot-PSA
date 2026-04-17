"""
Seed Nigeria Payroll Configuration
===================================
Seeds PAYE tax brackets (Finance Act 2020), pension configuration (PRA 2014),
and registered PFA list.

Usage:
    python manage.py seed_nigeria_payroll
"""

from decimal import Decimal
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction
from hrm.models import NigeriaTaxBracket, PensionConfiguration, PensionFundAdministrator


class Command(BaseCommand):
    help = 'Seeds Nigeria PAYE tax brackets, pension config, and PFA registry'

    @transaction.atomic
    def handle(self, *args, **options):
        self._seed_paye_brackets()
        self._seed_pension_config()
        self._seed_pfas()
        self.stdout.write(self.style.SUCCESS('Nigeria payroll configuration seeded.'))

    def _seed_paye_brackets(self):
        """Seeds PAYE brackets per Finance Act 2020."""
        self.stdout.write('Seeding PAYE Tax Brackets (Finance Act 2020)...')

        # Mark old brackets as inactive
        NigeriaTaxBracket.objects.filter(is_current=True).update(is_current=False)

        brackets = [
            (Decimal('0'),         Decimal('300000'),    Decimal('7.00')),
            (Decimal('300001'),    Decimal('600000'),    Decimal('11.00')),
            (Decimal('600001'),    Decimal('1100000'),   Decimal('15.00')),
            (Decimal('1100001'),   Decimal('1600000'),   Decimal('19.00')),
            (Decimal('1600001'),   Decimal('3200000'),   Decimal('21.00')),
            (Decimal('3200001'),   None,                 Decimal('24.00')),
        ]

        for lower, upper, rate in brackets:
            NigeriaTaxBracket.objects.update_or_create(
                lower_bound=lower,
                effective_date=date(2020, 1, 1),
                defaults={
                    'upper_bound': upper,
                    'rate': rate,
                    'is_current': True,
                },
            )

        self.stdout.write(self.style.SUCCESS(f'  {NigeriaTaxBracket.objects.filter(is_current=True).count()} brackets seeded'))

    def _seed_pension_config(self):
        """Seeds CPS configuration per PRA 2014."""
        self.stdout.write('Seeding Pension Configuration (PRA 2014)...')

        PensionConfiguration.objects.filter(is_current=True).update(is_current=False)

        PensionConfiguration.objects.update_or_create(
            effective_date=date(2014, 7, 1),
            defaults={
                'employer_rate': Decimal('10.00'),
                'employee_rate': Decimal('8.00'),
                'qualifying_components': ['basic_salary', 'housing_allowance', 'transport_allowance'],
                'remittance_deadline_days': 7,
                'is_current': True,
            },
        )
        self.stdout.write(self.style.SUCCESS('  Pension config: 10% employer + 8% employee'))

    def _seed_pfas(self):
        """Seeds major registered PFAs."""
        self.stdout.write('Seeding Pension Fund Administrators...')

        pfas = [
            ('PFA001', 'ARM Pension Managers'),
            ('PFA002', 'Stanbic IBTC Pension Managers'),
            ('PFA003', 'Premium Pension'),
            ('PFA004', 'AIICO Pension Managers'),
            ('PFA005', 'Leadway Pensure PFA'),
            ('PFA006', 'PAL Pensions'),
            ('PFA007', 'Trustfund Pensions'),
            ('PFA008', 'NLPC Pension Fund Administrators'),
            ('PFA009', 'Radix Pension Managers'),
            ('PFA010', 'Crusader Sterling Pensions'),
            ('PFA011', 'First Guarantee Pension'),
            ('PFA012', 'Veritas Glanvills Pensions'),
            ('PFA013', 'Oak Pensions'),
            ('PFA014', 'NPF Pensions'),
            ('PFA015', 'Tangerine Pensions (APT Pensions)'),
            ('PFA016', 'IEI-Anchor Pension Managers'),
            ('PFA017', 'Fidelity Pension Managers'),
            ('PFA018', 'Access Pensions'),
        ]

        for code, name in pfas:
            PensionFundAdministrator.objects.update_or_create(
                pfa_code=code,
                defaults={
                    'name': name,
                    'bank_name': 'To be configured',
                    'bank_account': '0000000000',
                    'is_active': True,
                },
            )

        self.stdout.write(self.style.SUCCESS(f'  {len(pfas)} PFAs seeded'))
