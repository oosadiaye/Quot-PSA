"""
Seed the CurrencyConfig table with major African currencies + USD/EUR/GBP.

Usage:
    python manage.py seed_platform_currencies
    python manage.py seed_platform_currencies --reset   # deletes existing and re-seeds
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from superadmin.models import CurrencyConfig


# Exchange rates vs USD (approximate — superadmin should update regularly)
CURRENCIES = [
    # code, name, symbol, position, rate_to_usd, countries, flag, decimals
    ('USD', 'US Dollar', '$', 'prefix', 1.0, ['US'], '🇺🇸', 2),
    ('EUR', 'Euro', '€', 'prefix', 0.92, ['FR', 'DE', 'IT', 'ES'], '🇪🇺', 2),
    ('GBP', 'British Pound', '£', 'prefix', 0.79, ['GB'], '🇬🇧', 2),

    # ── Major African Currencies ──
    ('NGN', 'Nigerian Naira', '₦', 'prefix', 1550.0, ['NG'], '🇳🇬', 2),
    ('ZAR', 'South African Rand', 'R', 'prefix', 18.20, ['ZA', 'LS', 'SZ'], '🇿🇦', 2),
    ('KES', 'Kenyan Shilling', 'KSh', 'prefix', 129.0, ['KE'], '🇰🇪', 2),
    ('GHS', 'Ghanaian Cedi', 'GH₵', 'prefix', 15.80, ['GH'], '🇬🇭', 2),
    ('EGP', 'Egyptian Pound', 'E£', 'prefix', 50.80, ['EG'], '🇪🇬', 2),
    ('TZS', 'Tanzanian Shilling', 'TSh', 'prefix', 2680.0, ['TZ'], '🇹🇿', 0),
    ('UGX', 'Ugandan Shilling', 'USh', 'prefix', 3760.0, ['UG'], '🇺🇬', 0),
    ('ETB', 'Ethiopian Birr', 'Br', 'prefix', 127.0, ['ET'], '🇪🇹', 2),
    ('XOF', 'West African CFA Franc', 'CFA', 'suffix', 604.0,
     ['SN', 'CI', 'BF', 'ML', 'BJ', 'NE', 'TG', 'GW'], '🇸🇳', 0),
    ('XAF', 'Central African CFA Franc', 'FCFA', 'suffix', 604.0,
     ['CM', 'CF', 'TD', 'CG', 'GA', 'GQ'], '🇨🇲', 0),
    ('MAD', 'Moroccan Dirham', 'MAD', 'prefix', 10.05, ['MA'], '🇲🇦', 2),
    ('RWF', 'Rwandan Franc', 'RF', 'prefix', 1380.0, ['RW'], '🇷🇼', 0),
    ('MZN', 'Mozambican Metical', 'MT', 'prefix', 63.8, ['MZ'], '🇲🇿', 2),
    ('AOA', 'Angolan Kwanza', 'Kz', 'prefix', 920.0, ['AO'], '🇦🇴', 2),
    ('BWP', 'Botswana Pula', 'P', 'prefix', 13.70, ['BW'], '🇧🇼', 2),
    ('MUR', 'Mauritian Rupee', '₨', 'prefix', 46.0, ['MU'], '🇲🇺', 2),
    ('ZMW', 'Zambian Kwacha', 'ZK', 'prefix', 27.50, ['ZM'], '🇿🇲', 2),
    ('CDF', 'Congolese Franc', 'FC', 'prefix', 2830.0, ['CD'], '🇨🇩', 2),
]


class Command(BaseCommand):
    help = 'Seed platform CurrencyConfig with major African currencies + USD/EUR/GBP'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Delete all existing currencies before seeding')

    def handle(self, *args, **options):
        if options['reset']:
            deleted, _ = CurrencyConfig.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'Deleted {deleted} existing currency records.'))

        created = 0
        updated = 0
        for code, name, symbol, position, rate, countries, flag, decimals in CURRENCIES:
            obj, was_created = CurrencyConfig.objects.update_or_create(
                currency_code=code,
                defaults={
                    'currency_name': name,
                    'symbol': symbol,
                    'symbol_position': position,
                    'exchange_rate_to_base': rate,
                    'country_codes': countries,
                    'flag_emoji': flag,
                    'decimal_places': decimals,
                    'is_active': True,
                    'is_default': code == 'USD',
                    'last_updated': timezone.now(),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done: {created} created, {updated} updated ({len(CURRENCIES)} total currencies).'
        ))
