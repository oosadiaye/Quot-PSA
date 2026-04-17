"""
Seed per-tenant defaults that every tenant needs from day one:
  1. Default Warehouse — named after the tenant org, marked central
  2. Five major Asset Categories — wired to the seeded GL accounts
  3. Default Units of Measure (UOM)
  4. Base Currency + AccountingSettings default_currency_1

Idempotent: uses get_or_create so safe to re-run.

Usage:
  python manage.py seed_tenant_defaults                  # within current schema
  python manage.py seed_tenant_defaults --schema myco    # explicit tenant
"""

import logging
from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)

# ── Default UOMs ─────────────────────────────────────────────────────────
DEFAULT_UOMS = [
    {'code': 'PCS', 'name': 'Pieces'},
    {'code': 'KG',  'name': 'Kilograms'},
    {'code': 'G',   'name': 'Grams'},
    {'code': 'LTR', 'name': 'Litres'},
    {'code': 'ML',  'name': 'Millilitres'},
    {'code': 'MTR', 'name': 'Metres'},
    {'code': 'CM',  'name': 'Centimetres'},
    {'code': 'BOX', 'name': 'Boxes'},
    {'code': 'PKT', 'name': 'Packets'},
    {'code': 'SET', 'name': 'Sets'},
    {'code': 'DOZ', 'name': 'Dozens'},
    {'code': 'TON', 'name': 'Tonnes'},
    {'code': 'BAG', 'name': 'Bags'},
    {'code': 'BTL', 'name': 'Bottles'},
    {'code': 'ROL', 'name': 'Rolls'},
]

# ── 5 Major Asset Categories ────────────────────────────────────────────
#   Keys map to DEFAULT_GL_ACCOUNTS for automatic GL wiring
ASSET_CATEGORIES = [
    {
        'code': 'LAND',
        'name': 'Land',
        'depreciation_method': 'Straight-Line',
        'default_life_years': 0,   # non-depreciable
        'residual_value_type': 'percentage',
        'residual_value': 100,     # 100% residual = no depreciation
        'cost_key': 'ASSET_LAND',
        'accum_depr_key': None,
        'depr_expense_key': None,
    },
    {
        'code': 'BLDG',
        'name': 'Buildings',
        'depreciation_method': 'Straight-Line',
        'default_life_years': 25,
        'residual_value_type': 'percentage',
        'residual_value': 10,
        'cost_key': 'ASSET_BUILDINGS',
        'accum_depr_key': 'ACCUM_DEPR_BUILDINGS',
        'depr_expense_key': 'DEPR_EXPENSE_BUILDINGS',
    },
    {
        'code': 'EQUIP',
        'name': 'Equipment & Machinery',
        'depreciation_method': 'Straight-Line',
        'default_life_years': 10,
        'residual_value_type': 'percentage',
        'residual_value': 5,
        'cost_key': 'ASSET_EQUIPMENT',
        'accum_depr_key': 'ACCUM_DEPR_EQUIPMENT',
        'depr_expense_key': 'DEPR_EXPENSE_EQUIPMENT',
    },
    {
        'code': 'VEH',
        'name': 'Motor Vehicles',
        'depreciation_method': 'Straight-Line',
        'default_life_years': 5,
        'residual_value_type': 'percentage',
        'residual_value': 10,
        'cost_key': 'ASSET_VEHICLES',
        'accum_depr_key': 'ACCUM_DEPR_VEHICLES',
        'depr_expense_key': 'DEPR_EXPENSE_VEHICLES',
    },
    {
        'code': 'FURN',
        'name': 'Furniture & Fixtures',
        'depreciation_method': 'Straight-Line',
        'default_life_years': 7,
        'residual_value_type': 'percentage',
        'residual_value': 5,
        'cost_key': 'ASSET_FURNITURE',
        'accum_depr_key': 'ACCUM_DEPR_FURNITURE',
        'depr_expense_key': 'DEPR_EXPENSE_FURNITURE',
    },
]

# ── Default base currency ────────────────────────────────────────────────
DEFAULT_BASE_CURRENCY = {
    'code': 'NGN',
    'name': 'Nigerian Naira',
    'symbol': '\u20a6',
}


def seed_defaults(tenant_name='My Business'):
    """
    Seed all tenant defaults. Called by management command or by
    the tenant signup flow directly.

    Args:
        tenant_name: Used as the default warehouse name.

    Returns:
        dict with counts of created items.
    """
    results = {
        'warehouse': 0,
        'asset_categories': 0,
        'uoms': 0,
        'currency': 0,
    }

    # ── 1. Default Warehouse ─────────────────────────────────────────
    from inventory.models import Warehouse
    _, created = Warehouse.objects.get_or_create(
        is_central=True,
        defaults={
            'name': f'{tenant_name} - Main Warehouse',
            'location': 'Head Office',
            'is_active': True,
        },
    )
    if created:
        results['warehouse'] = 1

    # ── 2. Default UOMs ──────────────────────────────────────────────
    try:
        from inventory.models import UnitOfMeasure
        for uom_data in DEFAULT_UOMS:
            _, created = UnitOfMeasure.objects.get_or_create(
                code=uom_data['code'],
                defaults={'name': uom_data['name'], 'is_active': True},
            )
            if created:
                results['uoms'] += 1
    except Exception:
        # UOM model may not exist yet — store as JSON fallback
        logger.info('UnitOfMeasure model not found; skipping UOM seed.')

    # ── 3. Base Currency ─────────────────────────────────────────────
    from accounting.models import Currency
    from accounting.models.advanced import AccountingSettings

    base_cur, created = Currency.objects.get_or_create(
        code=DEFAULT_BASE_CURRENCY['code'],
        defaults={
            'name': DEFAULT_BASE_CURRENCY['name'],
            'symbol': DEFAULT_BASE_CURRENCY['symbol'],
            'exchange_rate': 1,
            'is_base_currency': True,
            'is_active': True,
        },
    )
    if created:
        results['currency'] = 1
    elif not base_cur.is_base_currency:
        base_cur.is_base_currency = True
        base_cur.save(update_fields=['is_base_currency'])

    # Wire to AccountingSettings so frontend CurrencyContext picks it up
    acct_settings, _ = AccountingSettings.objects.get_or_create(pk=1)
    if not acct_settings.default_currency_1_id:
        acct_settings.default_currency_1 = base_cur
        acct_settings.save(update_fields=['default_currency_1'])

    # ── 4. Asset Categories with GL wiring ───────────────────────────
    from accounting.models import Account
    from accounting.models.assets import AssetCategory
    gl = getattr(settings, 'DEFAULT_GL_ACCOUNTS', {})

    for cat_data in ASSET_CATEGORIES:
        # Resolve GL accounts by code
        cost_code = gl.get(cat_data['cost_key'], '')
        cost_acct = Account.objects.filter(code=cost_code).first() if cost_code else None

        accum_code = gl.get(cat_data['accum_depr_key'] or '', '')
        accum_acct = Account.objects.filter(code=accum_code).first() if accum_code else None

        depr_code = gl.get(cat_data['depr_expense_key'] or '', '')
        depr_acct = Account.objects.filter(code=depr_code).first() if depr_code else None

        _, created = AssetCategory.objects.get_or_create(
            code=cat_data['code'],
            defaults={
                'name': cat_data['name'],
                'is_active': True,
                'cost_account': cost_acct,
                'accumulated_depreciation_account': accum_acct,
                'depreciation_expense_account': depr_acct,
                'depreciation_method': cat_data['depreciation_method'],
                'default_life_years': cat_data['default_life_years'],
                'residual_value_type': cat_data['residual_value_type'],
                'residual_value': cat_data['residual_value'],
            },
        )
        if created:
            results['asset_categories'] += 1

    return results


class Command(BaseCommand):
    help = 'Seed default warehouse, asset categories, UOMs, and base currency for a tenant.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema',
            type=str,
            help='Tenant schema name (if not already in schema context)',
        )
        parser.add_argument(
            '--tenant-name',
            type=str,
            default='My Business',
            help='Tenant organization name (used for warehouse naming)',
        )

    def handle(self, *args, **options):
        schema = options.get('schema')
        tenant_name = options.get('tenant_name') or 'My Business'

        if schema:
            from django_tenants.utils import schema_context
            with schema_context(schema):
                results = seed_defaults(tenant_name)
        else:
            results = seed_defaults(tenant_name)

        self.stdout.write(self.style.SUCCESS(
            f"Tenant defaults seeded: "
            f"warehouse={results['warehouse']}, "
            f"asset_categories={results['asset_categories']}, "
            f"uoms={results['uoms']}, "
            f"currency={results['currency']}"
        ))
