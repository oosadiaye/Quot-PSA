"""
Seed Revenue Heads linked to NCoA Economic Segments.
Run: python manage.py seed_revenue_heads
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from accounting.models.ncoa import EconomicSegment
from accounting.models.revenue import RevenueHead


REVENUE_HEADS = [
    # (code, name, revenue_type, economic_segment_code)
    ('IGR-PAYE',     'Pay As You Earn (PAYE)',       'PAYE',              '11100100'),
    ('IGR-DA',       'Direct Assessment Tax',         'DIRECT_ASSESSMENT', '11100200'),
    ('IGR-ROAD',     'Road Tax / Vehicle License',    'ROAD_TAX',          '11100300'),
    ('IGR-STAMP',    'Stamp Duty',                    'STAMP_DUTY',        '11100400'),
    ('IGR-CGT',      'Capital Gains Tax',             'CGT',               '11100500'),
    ('IGR-WHT',      'Withholding Tax',               'WHT',               '11100600'),
    ('IGR-FEES',     'Fees and Fines',                'FEES_FINES',        '12100100'),
    ('IGR-LICENSE',  'Licenses and Permits',           'LICENSE',           '12100200'),
    ('IGR-RENT',     'Rent on Government Property',   'RENT',              '12100300'),
    ('IGR-INTEREST', 'Interest Income',                'INVESTMENT',        '12100400'),
    ('IGR-DIVIDEND', 'Dividends from Gov Companies',  'DIVIDEND',          '12100500'),
    ('FAAC-STAT',    'FAAC Statutory Allocation',      'FAAC',              '13100100'),
    ('FAAC-VAT',     'FAAC VAT Distribution',          'FAAC',              '13100200'),
    ('FAAC-EXCESS',  'FAAC Excess Crude Account',      'FAAC',              '13100300'),
    ('GRANT-DEV',    'Development Partner Grants',     'GRANT',             '13200100'),
    ('IGR-OTHER',    'Other IGR / Miscellaneous',      'OTHER',             '12100700'),
]


class Command(BaseCommand):
    help = 'Seed Revenue Heads linked to NCoA Economic Segments'

    @transaction.atomic
    def handle(self, *args, **options):
        created = updated = skipped = 0

        for code, name, rev_type, eco_code in REVENUE_HEADS:
            try:
                eco = EconomicSegment.objects.get(code=eco_code)
            except EconomicSegment.DoesNotExist:
                self.stdout.write(self.style.WARNING(
                    f'  Skipped {code}: Economic segment {eco_code} not found'
                ))
                skipped += 1
                continue

            obj, was_created = RevenueHead.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'revenue_type': rev_type,
                    'economic_segment': eco,
                    'is_active': True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Revenue Heads: {created} created, {updated} updated, {skipped} skipped. '
            f'Total: {RevenueHead.objects.count()}'
        ))
