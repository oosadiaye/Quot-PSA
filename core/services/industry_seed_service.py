"""
Industry-specific seed data service.

Seeds default Chart of Accounts, BOM templates, item categories, and
work centers based on the tenant's chosen business_category. Called
during tenant signup after the schema and modules are created.

Each category defines:
  - recommended_modules: modules to auto-activate
  - extra_coa: industry-specific GL accounts (on top of the base CoA)
  - bom_templates: starter BOM structures (for manufacturing/agriculture)
  - item_categories: default inventory categories
  - work_centers: default production work centers
"""
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Industry configurations
# ---------------------------------------------------------------------------

INDUSTRY_CONFIGS = {
    'agriculture': {
        'recommended_modules': [
            'accounting', 'inventory', 'procurement', 'production',
            'sales', 'hrm', 'quality', 'budget',
        ],
        'extra_coa': [
            # Agriculture-specific accounts
            ('10310000', 'Livestock Inventory', 'Asset'),
            ('10311000', 'Crop Inventory - Growing', 'Asset'),
            ('10312000', 'Crop Inventory - Harvested', 'Asset'),
            ('10313000', 'Seeds & Seedlings Inventory', 'Asset'),
            ('10314000', 'Fertilizer & Chemical Inventory', 'Asset'),
            ('10315000', 'Feed Inventory', 'Asset'),
            ('10500100', 'Farm Equipment', 'Asset'),
            ('10500200', 'Irrigation Systems', 'Asset'),
            ('10500300', 'Land & Farm Property', 'Asset'),
            ('40300000', 'Crop Sales Revenue', 'Income'),
            ('40310000', 'Livestock Sales Revenue', 'Income'),
            ('40320000', 'Farm Produce Revenue', 'Income'),
            ('50300000', 'Cost of Crops Sold', 'Expense'),
            ('50310000', 'Cost of Livestock Sold', 'Expense'),
            ('50320000', 'Seed & Planting Costs', 'Expense'),
            ('50330000', 'Fertilizer & Chemical Costs', 'Expense'),
            ('50340000', 'Irrigation Costs', 'Expense'),
            ('50350000', 'Harvesting Costs', 'Expense'),
            ('50360000', 'Feed Costs', 'Expense'),
            ('50370000', 'Veterinary Costs', 'Expense'),
            ('60200000', 'Farm Labor', 'Expense'),
            ('60210000', 'Seasonal Labor', 'Expense'),
        ],
        'bom_templates': [
            {
                'item_code': 'AGR-MAIZE-001',
                'item_name': 'Maize Production (per Hectare)',
                'item_type': 'Finished',
                'unit': 'Hectare',
                'components': [
                    ('AGR-SEED-MAIZE', 'Maize Seeds', 'Raw Material', 25, 'kg'),
                    ('AGR-FERT-NPK', 'NPK Fertilizer', 'Raw Material', 200, 'kg'),
                    ('AGR-FERT-UREA', 'Urea Fertilizer', 'Raw Material', 100, 'kg'),
                    ('AGR-CHEM-HERB', 'Herbicide', 'Raw Material', 5, 'Litre'),
                    ('AGR-CHEM-PEST', 'Pesticide', 'Raw Material', 3, 'Litre'),
                ],
            },
            {
                'item_code': 'AGR-RICE-001',
                'item_name': 'Rice Production (per Hectare)',
                'item_type': 'Finished',
                'unit': 'Hectare',
                'components': [
                    ('AGR-SEED-RICE', 'Rice Seeds', 'Raw Material', 60, 'kg'),
                    ('AGR-FERT-NPK', 'NPK Fertilizer', 'Raw Material', 250, 'kg'),
                    ('AGR-FERT-UREA', 'Urea Fertilizer', 'Raw Material', 150, 'kg'),
                    ('AGR-CHEM-HERB', 'Herbicide', 'Raw Material', 4, 'Litre'),
                ],
            },
            {
                'item_code': 'AGR-POULTRY-001',
                'item_name': 'Poultry Batch (per 100 Birds)',
                'item_type': 'Finished',
                'unit': 'Batch',
                'components': [
                    ('AGR-CHICK-DOC', 'Day-Old Chicks', 'Raw Material', 100, 'pcs'),
                    ('AGR-FEED-START', 'Starter Feed', 'Raw Material', 250, 'kg'),
                    ('AGR-FEED-GROW', 'Grower Feed', 'Raw Material', 500, 'kg'),
                    ('AGR-FEED-FINISH', 'Finisher Feed', 'Raw Material', 400, 'kg'),
                    ('AGR-MED-VACC', 'Vaccines & Medication', 'Raw Material', 1, 'Set'),
                ],
            },
        ],
        'item_categories': [
            'Seeds & Seedlings', 'Fertilizers', 'Pesticides & Chemicals',
            'Farm Equipment', 'Animal Feed', 'Livestock',
            'Harvested Crops', 'Farm Produce', 'Irrigation Supplies',
        ],
        'work_centers': [
            ('WC-FIELD', 'Farm Field Operations', 8.0),
            ('WC-GREENHOUSE', 'Greenhouse', 10.0),
            ('WC-PROCESSING', 'Post-Harvest Processing', 8.0),
            ('WC-PACKAGING', 'Packaging & Storage', 8.0),
            ('WC-POULTRY', 'Poultry House', 12.0),
        ],
    },

    'manufacturing': {
        'recommended_modules': [
            'accounting', 'inventory', 'procurement', 'production',
            'sales', 'hrm', 'quality', 'workflow', 'budget',
        ],
        'extra_coa': [
            ('10302100', 'Work-in-Progress - Assembly', 'Asset'),
            ('10302200', 'Work-in-Progress - Machining', 'Asset'),
            ('10303100', 'Finished Goods - Standard', 'Asset'),
            ('10303200', 'Finished Goods - Custom', 'Asset'),
            ('50210000', 'Direct Labor - Production', 'Expense'),
            ('50220000', 'Direct Labor - Assembly', 'Expense'),
            ('50400000', 'Manufacturing Overhead', 'Expense'),
            ('50410000', 'Factory Utilities', 'Expense'),
            ('50420000', 'Equipment Maintenance', 'Expense'),
            ('50430000', 'Tooling & Consumables', 'Expense'),
            ('50440000', 'Factory Insurance', 'Expense'),
        ],
        'bom_templates': [
            {
                'item_code': 'MFG-SAMPLE-001',
                'item_name': 'Sample Assembled Product',
                'item_type': 'Finished',
                'unit': 'pcs',
                'components': [
                    ('MFG-RAW-STEEL', 'Steel Sheet', 'Raw Material', 2, 'kg'),
                    ('MFG-RAW-BOLT', 'Bolts & Fasteners', 'Raw Material', 10, 'pcs'),
                    ('MFG-RAW-PAINT', 'Surface Coating', 'Raw Material', 0.5, 'Litre'),
                    ('MFG-SUB-FRAME', 'Frame Assembly', 'Semi-Finished', 1, 'pcs'),
                ],
            },
        ],
        'item_categories': [
            'Raw Materials', 'Semi-Finished Goods', 'Finished Goods',
            'Packaging Materials', 'Spare Parts', 'Consumables',
            'Tools & Fixtures', 'Safety Equipment',
        ],
        'work_centers': [
            ('WC-CUT', 'Cutting & Shearing', 8.0),
            ('WC-WELD', 'Welding Station', 8.0),
            ('WC-ASSEMBLY', 'Assembly Line', 16.0),
            ('WC-PAINT', 'Painting & Finishing', 8.0),
            ('WC-QC', 'Quality Control Station', 8.0),
            ('WC-PACK', 'Packaging', 8.0),
        ],
    },

    'construction': {
        'recommended_modules': [
            'accounting', 'inventory', 'procurement', 'production',
            'sales', 'hrm', 'budget', 'quality', 'workflow',
        ],
        'extra_coa': [
            ('10400000', 'Construction Work-in-Progress', 'Asset'),
            ('10401000', 'Project Materials on Site', 'Asset'),
            ('10500400', 'Heavy Equipment', 'Asset'),
            ('10500500', 'Vehicles - Construction', 'Asset'),
            ('40400000', 'Contract Revenue', 'Income'),
            ('40410000', 'Retention Income', 'Income'),
            ('50600000', 'Subcontractor Costs', 'Expense'),
            ('50610000', 'Site Labor Costs', 'Expense'),
            ('50620000', 'Equipment Rental', 'Expense'),
            ('50630000', 'Site Overhead', 'Expense'),
        ],
        'bom_templates': [],
        'item_categories': [
            'Building Materials', 'Cement & Concrete', 'Steel & Metal',
            'Electrical Supplies', 'Plumbing Supplies', 'Safety Gear',
            'Heavy Equipment', 'Power Tools', 'Finishing Materials',
        ],
        'work_centers': [],
    },

    'trading': {
        'recommended_modules': [
            'accounting', 'inventory', 'procurement', 'sales',
            'budget', 'workflow',
        ],
        'extra_coa': [
            ('10305000', 'Goods in Transit - Import', 'Asset'),
            ('10306000', 'Goods in Transit - Export', 'Asset'),
            ('20602000', 'Customs Duties Payable', 'Liability'),
            ('40500000', 'Trading Revenue - Domestic', 'Income'),
            ('40510000', 'Trading Revenue - Export', 'Income'),
            ('50700000', 'Import Duties & Taxes', 'Expense'),
            ('50710000', 'Shipping & Freight', 'Expense'),
            ('50720000', 'Warehouse & Storage', 'Expense'),
        ],
        'bom_templates': [],
        'item_categories': [
            'Fast-Moving Goods', 'Slow-Moving Goods', 'Seasonal Items',
            'Imported Goods', 'Export Goods', 'Packaging',
            'Promotional Items', 'Returns & Damaged',
        ],
        'work_centers': [],
    },

    'healthcare': {
        'recommended_modules': [
            'accounting', 'inventory', 'procurement', 'hrm',
            'budget', 'quality', 'service', 'workflow',
        ],
        'extra_coa': [
            ('10316000', 'Pharmaceutical Inventory', 'Asset'),
            ('10317000', 'Medical Supplies Inventory', 'Asset'),
            ('10500600', 'Medical Equipment', 'Asset'),
            ('40600000', 'Patient Service Revenue', 'Income'),
            ('40610000', 'Laboratory Revenue', 'Income'),
            ('40620000', 'Pharmacy Revenue', 'Income'),
            ('50800000', 'Cost of Pharmaceuticals', 'Expense'),
            ('50810000', 'Medical Consumables', 'Expense'),
            ('50820000', 'Laboratory Costs', 'Expense'),
        ],
        'bom_templates': [],
        'item_categories': [
            'Pharmaceuticals', 'Medical Consumables', 'Laboratory Supplies',
            'Medical Equipment', 'Surgical Instruments', 'PPE',
            'Cleaning & Sterilization', 'Office Supplies',
        ],
        'work_centers': [],
    },

    'hospitality': {
        'recommended_modules': [
            'accounting', 'inventory', 'procurement', 'sales',
            'hrm', 'budget', 'service',
        ],
        'extra_coa': [
            ('10318000', 'Food & Beverage Inventory', 'Asset'),
            ('10319000', 'Linen & Supplies', 'Asset'),
            ('40700000', 'Room Revenue', 'Income'),
            ('40710000', 'Food & Beverage Revenue', 'Income'),
            ('40720000', 'Events & Banquet Revenue', 'Income'),
            ('50900000', 'Cost of Food', 'Expense'),
            ('50910000', 'Cost of Beverages', 'Expense'),
            ('50920000', 'Housekeeping Costs', 'Expense'),
            ('50930000', 'Laundry Costs', 'Expense'),
        ],
        'bom_templates': [
            {
                'item_code': 'FB-MENU-001',
                'item_name': 'Standard Breakfast Set',
                'item_type': 'Finished',
                'unit': 'Serving',
                'components': [
                    ('FB-BREAD', 'Bread/Toast', 'Raw Material', 2, 'pcs'),
                    ('FB-EGG', 'Eggs', 'Raw Material', 2, 'pcs'),
                    ('FB-JUICE', 'Fresh Juice', 'Raw Material', 1, 'Glass'),
                    ('FB-TEA', 'Tea/Coffee', 'Raw Material', 1, 'Cup'),
                ],
            },
        ],
        'item_categories': [
            'Food - Perishable', 'Food - Dry Goods', 'Beverages',
            'Kitchen Supplies', 'Cleaning Supplies', 'Linen & Towels',
            'Room Amenities', 'Maintenance Supplies',
        ],
        'work_centers': [
            ('WC-KITCHEN', 'Main Kitchen', 16.0),
            ('WC-BAKERY', 'Bakery & Pastry', 8.0),
        ],
    },

    'technology': {
        'recommended_modules': [
            'accounting', 'sales', 'hrm', 'budget',
            'service', 'workflow',
        ],
        'extra_coa': [
            ('10500700', 'Computer Equipment', 'Asset'),
            ('10500800', 'Software Licenses', 'Asset'),
            ('40800000', 'Software License Revenue', 'Income'),
            ('40810000', 'SaaS Subscription Revenue', 'Income'),
            ('40820000', 'Consulting Revenue', 'Income'),
            ('40830000', 'Support & Maintenance Revenue', 'Income'),
            ('60300000', 'Cloud Hosting Costs', 'Expense'),
            ('60310000', 'Software Subscriptions', 'Expense'),
            ('60320000', 'R&D Expenses', 'Expense'),
        ],
        'bom_templates': [],
        'item_categories': [
            'Hardware', 'Software Licenses', 'Cloud Services',
            'Network Equipment', 'Peripherals', 'Office Supplies',
        ],
        'work_centers': [],
    },

    'retail': {
        'recommended_modules': [
            'accounting', 'inventory', 'procurement', 'sales',
            'hrm', 'budget',
        ],
        'extra_coa': [
            ('10307000', 'Merchandise Inventory', 'Asset'),
            ('40900000', 'Retail Sales Revenue', 'Income'),
            ('40910000', 'Online Sales Revenue', 'Income'),
            ('40920000', 'Sales Returns & Allowances', 'Income'),
            ('51000000', 'Cost of Merchandise', 'Expense'),
            ('60400000', 'Store Rent', 'Expense'),
            ('60410000', 'POS & Payment Processing', 'Expense'),
            ('60420000', 'Visual Merchandising', 'Expense'),
        ],
        'bom_templates': [],
        'item_categories': [
            'General Merchandise', 'Electronics', 'Clothing & Apparel',
            'Home & Garden', 'Food & Grocery', 'Health & Beauty',
            'Stationery', 'Packaging & Bags',
        ],
        'work_centers': [],
    },

    # Simpler configs for remaining categories
    'education': {
        'recommended_modules': [
            'accounting', 'hrm', 'procurement', 'budget',
            'inventory', 'workflow',
        ],
        'extra_coa': [
            ('40110000', 'Tuition Revenue', 'Income'),
            ('40120000', 'Grant Revenue', 'Income'),
            ('60500000', 'Teaching Materials', 'Expense'),
            ('60510000', 'Student Activities', 'Expense'),
        ],
        'bom_templates': [],
        'item_categories': [
            'Teaching Materials', 'Lab Equipment', 'Stationery',
            'Furniture', 'IT Equipment', 'Sports Equipment',
        ],
        'work_centers': [],
    },

    'mining': {
        'recommended_modules': [
            'accounting', 'inventory', 'procurement', 'production',
            'hrm', 'budget', 'quality', 'workflow',
        ],
        'extra_coa': [
            ('10320000', 'Mineral Inventory', 'Asset'),
            ('10500900', 'Mining Equipment', 'Asset'),
            ('40130000', 'Mineral Sales Revenue', 'Income'),
            ('51100000', 'Extraction Costs', 'Expense'),
            ('51110000', 'Processing Costs', 'Expense'),
            ('51120000', 'Environmental Compliance', 'Expense'),
        ],
        'bom_templates': [],
        'item_categories': [
            'Raw Minerals', 'Processed Minerals', 'Explosives',
            'Mining Equipment', 'Safety Equipment', 'Fuel & Lubricants',
        ],
        'work_centers': [
            ('WC-EXTRACT', 'Extraction Site', 24.0),
            ('WC-CRUSH', 'Crushing Plant', 16.0),
            ('WC-PROCESS', 'Processing Plant', 16.0),
        ],
    },

    'logistics': {
        'recommended_modules': [
            'accounting', 'inventory', 'procurement', 'sales',
            'hrm', 'service', 'budget',
        ],
        'extra_coa': [
            ('10501000', 'Fleet Vehicles', 'Asset'),
            ('40140000', 'Freight Revenue', 'Income'),
            ('40150000', 'Warehousing Revenue', 'Income'),
            ('51200000', 'Fuel Costs', 'Expense'),
            ('51210000', 'Vehicle Maintenance', 'Expense'),
            ('51220000', 'Driver Costs', 'Expense'),
            ('51230000', 'Toll & Permit Fees', 'Expense'),
        ],
        'bom_templates': [],
        'item_categories': [
            'Fuel', 'Vehicle Parts', 'Tires', 'Packaging Materials',
            'Warehouse Supplies', 'Safety Equipment',
        ],
        'work_centers': [],
    },
}

# Categories without specialized config use a base template
_BASE_CONFIG = {
    'recommended_modules': ['accounting', 'budget', 'procurement', 'sales', 'hrm'],
    'extra_coa': [],
    'bom_templates': [],
    'item_categories': ['General Supplies', 'Office Supplies', 'Equipment'],
    'work_centers': [],
}

for _cat in ('real_estate', 'nonprofit', 'government', 'energy', 'other'):
    if _cat not in INDUSTRY_CONFIGS:
        INDUSTRY_CONFIGS[_cat] = _BASE_CONFIG.copy()


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

def seed_industry_defaults(schema_name, business_category):
    """
    Seed industry-specific defaults into a tenant's schema.

    Must be called AFTER the schema exists and base CoA is seeded.
    Runs inside schema_context(schema_name) — caller is responsible
    for wrapping if needed, or this function handles it internally.
    """
    from django_tenants.utils import schema_context

    config = INDUSTRY_CONFIGS.get(business_category, _BASE_CONFIG)

    with schema_context(schema_name):
        _seed_extra_coa(config.get('extra_coa', []))
        _seed_bom_templates(config.get('bom_templates', []))
        _seed_item_categories(config.get('item_categories', []))
        _seed_work_centers(config.get('work_centers', []))
        _seed_setup_profile(business_category)

    logger.info(
        'Seeded industry defaults for tenant=%s category=%s',
        schema_name, business_category,
    )


def _seed_extra_coa(accounts):
    """Seed industry-specific Chart of Accounts entries."""
    if not accounts:
        return

    from accounting.models.gl import Account

    for code, name, account_type in accounts:
        Account.objects.get_or_create(
            code=code,
            defaults={'name': name, 'account_type': account_type, 'is_active': True},
        )


def _seed_bom_templates(templates):
    """Seed starter BOM templates with component lines."""
    if not templates:
        return

    from production.models import BillOfMaterials, BOMLine

    for tmpl in templates:
        parent_bom, _ = BillOfMaterials.objects.get_or_create(
            item_code=tmpl['item_code'],
            defaults={
                'item_name': tmpl['item_name'],
                'item_type': tmpl['item_type'],
                'unit': tmpl['unit'],
                'is_active': True,
            },
        )

        for comp_code, comp_name, comp_type, qty, unit in tmpl.get('components', []):
            comp_bom, _ = BillOfMaterials.objects.get_or_create(
                item_code=comp_code,
                defaults={
                    'item_name': comp_name,
                    'item_type': comp_type,
                    'unit': unit,
                    'is_active': True,
                },
            )
            BOMLine.objects.get_or_create(
                bom=parent_bom,
                component=comp_bom,
                defaults={'quantity': qty, 'unit': unit},
            )


def _seed_item_categories(categories):
    """Seed default inventory item categories."""
    if not categories:
        return

    try:
        from inventory.models import ItemCategory
        for name in categories:
            ItemCategory.objects.get_or_create(name=name)
    except Exception:
        logger.debug('ItemCategory model not available, skipping category seed')


def _seed_work_centers(centers):
    """Seed default production work centers."""
    if not centers:
        return

    try:
        from production.models import WorkCenter
        for code, name, hours in centers:
            WorkCenter.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'capacity_hours': hours,
                    'is_active': True,
                },
            )
    except Exception:
        logger.debug('WorkCenter model not available, skipping work center seed')


def _seed_setup_profile(business_category):
    """Create the TenantSetupProfile singleton."""
    from core.models import TenantSetupProfile

    TenantSetupProfile.objects.get_or_create(
        pk=1,
        defaults={
            'business_category': business_category,
            'setup_completed': False,
            'current_step': 0,
        },
    )


def get_recommended_modules(business_category):
    """Return the list of recommended module keys for an industry."""
    config = INDUSTRY_CONFIGS.get(business_category, _BASE_CONFIG)
    return config.get('recommended_modules', _BASE_CONFIG['recommended_modules'])
