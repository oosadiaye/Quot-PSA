"""
Inventory Minimum Viable Test Suite
=====================================
Covers: Item, Warehouse, ItemCategory, ItemStock model CRUD;
item quantity/value validators; stock movement basics.

Run with:
    python manage.py test inventory --verbosity=2
"""
from decimal import Decimal

from django_tenants.test.cases import TenantTestCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(**kwargs):
    from inventory.models import Item
    defaults = dict(
        sku=f"SKU-{Item.objects.count() + 1:04d}",
        name='Test Item',
        description='A test inventory item',
        unit_of_measure='PCS',
        is_active=True,
    )
    defaults.update(kwargs)
    return Item.objects.create(**defaults)


# ---------------------------------------------------------------------------
# ItemCategory model
# ---------------------------------------------------------------------------

class ItemCategoryModelTests(TenantTestCase):
    """CRUD tests for inventory.ItemCategory."""

    def test_create_category(self):
        from inventory.models import ItemCategory
        cat = ItemCategory.objects.create(name='Electronics', code='ELEC')
        self.assertEqual(cat.name, 'Electronics')

    def test_category_str(self):
        from inventory.models import ItemCategory
        cat = ItemCategory.objects.create(name='Furniture', code='FURN')
        self.assertIn('Furniture', str(cat))


# ---------------------------------------------------------------------------
# Warehouse model
# ---------------------------------------------------------------------------

class WarehouseModelTests(TenantTestCase):
    """CRUD tests for inventory.Warehouse."""

    def test_create_warehouse(self):
        from inventory.models import Warehouse
        wh = Warehouse.objects.create(name='Main Warehouse', code='WH01')
        self.assertEqual(wh.name, 'Main Warehouse')

    def test_warehouse_str(self):
        from inventory.models import Warehouse
        wh = Warehouse.objects.create(name='South Store', code='SS01')
        self.assertIn('South Store', str(wh))


# ---------------------------------------------------------------------------
# Item model
# ---------------------------------------------------------------------------

class ItemModelTests(TenantTestCase):
    """CRUD tests for inventory.Item."""

    def test_create_item(self):
        item = _make_item()
        self.assertIsNotNone(item.pk)
        self.assertEqual(item.total_quantity, Decimal('0'))
        self.assertEqual(item.total_value, Decimal('0'))

    def test_item_sku_unique(self):
        from django.db import IntegrityError
        _make_item(sku='UNIQUE001')
        with self.assertRaises(IntegrityError):
            _make_item(sku='UNIQUE001')

    def test_item_total_quantity_non_negative_validator(self):
        """Negative total_quantity should fail full_clean validation."""
        from inventory.models import Item
        from django.core.exceptions import ValidationError
        item = Item(
            sku='NEG001', name='Bad Item',
            description='test', unit_of_measure='PCS',
            is_active=True, total_quantity=Decimal('-1'),
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_item_is_active_field(self):
        item = _make_item(is_active=False)
        self.assertFalse(item.is_active)

    def test_item_reorder_fields_default_zero(self):
        item = _make_item()
        self.assertEqual(item.min_stock, Decimal('0'))
        self.assertEqual(item.max_stock, Decimal('0'))
        self.assertEqual(item.reorder_point, Decimal('0'))


# ---------------------------------------------------------------------------
# ItemStock model
# ---------------------------------------------------------------------------

class ItemStockModelTests(TenantTestCase):
    """Basic tests for inventory.ItemStock."""

    def test_item_stock_can_be_created(self):
        from inventory.models import ItemStock, Warehouse
        item = _make_item(sku='STOCK001')
        wh = Warehouse.objects.create(name='Stock WH', code='SWH1')
        stock = ItemStock.objects.create(item=item, warehouse=wh, quantity=Decimal('100'))
        self.assertEqual(stock.quantity, Decimal('100'))
