"""
Seed BPP Procurement Thresholds
================================
Seeds procurement approval thresholds per the Public Procurement Act 2007
and BPP revised threshold circulars.

Usage:
    python manage.py seed_procurement_thresholds
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from procurement.models import ProcurementThreshold


class Command(BaseCommand):
    help = 'Seeds BPP procurement approval thresholds'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Seeding BPP Procurement Thresholds...')

        # Deactivate existing thresholds
        ProcurementThreshold.objects.filter(is_active=True).update(is_active=False)

        thresholds = [
            # Goods & Services
            {
                'category': 'GOODS_SERVICES',
                'authority_level': 'ACCOUNTING_OFFICER',
                'min_amount': Decimal('0'),
                'max_amount': Decimal('2500000'),
                'requires_bpp_no': False,
            },
            {
                'category': 'GOODS_SERVICES',
                'authority_level': 'PTB',
                'min_amount': Decimal('2500001'),
                'max_amount': Decimal('10000000'),
                'requires_bpp_no': False,
            },
            {
                'category': 'GOODS_SERVICES',
                'authority_level': 'MTB',
                'min_amount': Decimal('10000001'),
                'max_amount': Decimal('50000000'),
                'requires_bpp_no': True,
            },
            {
                'category': 'GOODS_SERVICES',
                'authority_level': 'EXCO',
                'min_amount': Decimal('50000001'),
                'max_amount': None,
                'requires_bpp_no': True,
            },
            # Works / Construction
            {
                'category': 'WORKS',
                'authority_level': 'ACCOUNTING_OFFICER',
                'min_amount': Decimal('0'),
                'max_amount': Decimal('5000000'),
                'requires_bpp_no': False,
            },
            {
                'category': 'WORKS',
                'authority_level': 'PTB',
                'min_amount': Decimal('5000001'),
                'max_amount': Decimal('25000000'),
                'requires_bpp_no': False,
            },
            {
                'category': 'WORKS',
                'authority_level': 'MTB',
                'min_amount': Decimal('25000001'),
                'max_amount': Decimal('100000000'),
                'requires_bpp_no': True,
            },
            {
                'category': 'WORKS',
                'authority_level': 'EXCO',
                'min_amount': Decimal('100000001'),
                'max_amount': None,
                'requires_bpp_no': True,
            },
            # Consultancy
            {
                'category': 'CONSULTANCY',
                'authority_level': 'ACCOUNTING_OFFICER',
                'min_amount': Decimal('0'),
                'max_amount': Decimal('2500000'),
                'requires_bpp_no': False,
            },
            {
                'category': 'CONSULTANCY',
                'authority_level': 'MTB',
                'min_amount': Decimal('2500001'),
                'max_amount': Decimal('50000000'),
                'requires_bpp_no': True,
            },
            {
                'category': 'CONSULTANCY',
                'authority_level': 'EXCO',
                'min_amount': Decimal('50000001'),
                'max_amount': None,
                'requires_bpp_no': True,
            },
        ]

        for t in thresholds:
            ProcurementThreshold.objects.create(is_active=True, **t)

        self.stdout.write(self.style.SUCCESS(
            f'  {len(thresholds)} procurement thresholds seeded'
        ))
