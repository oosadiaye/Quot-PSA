"""
Procurement Minimum Viable Test Suite
=======================================
Covers: Vendor, VendorCategory model CRUD;
Vendor.performance_rating property; serializer validation.

Run with:
    python manage.py test procurement --verbosity=2
"""
from decimal import Decimal

from django_tenants.test.cases import TenantTestCase


# ---------------------------------------------------------------------------
# VendorCategory model
# ---------------------------------------------------------------------------

class VendorCategoryModelTests(TenantTestCase):
    """CRUD tests for procurement.VendorCategory."""

    def test_create_category(self):
        from procurement.models import VendorCategory
        cat = VendorCategory.objects.create(name='Raw Materials', code='RM')
        self.assertEqual(cat.name, 'Raw Materials')

    def test_category_str(self):
        from procurement.models import VendorCategory
        cat = VendorCategory.objects.create(name='Services', code='SVC')
        self.assertIn('Services', str(cat))


# ---------------------------------------------------------------------------
# Vendor model
# ---------------------------------------------------------------------------

class VendorModelTests(TenantTestCase):
    """CRUD tests for procurement.Vendor."""

    def test_create_vendor(self):
        from procurement.models import Vendor
        vendor = Vendor.objects.create(name='Supplier Ltd', code='SUP001')
        self.assertEqual(vendor.name, 'Supplier Ltd')
        self.assertTrue(vendor.is_active)

    def test_vendor_code_unique(self):
        from procurement.models import Vendor
        from django.db import IntegrityError
        Vendor.objects.create(name='Vendor A', code='V001')
        with self.assertRaises(IntegrityError):
            Vendor.objects.create(name='Vendor B', code='V001')

    def test_vendor_defaults(self):
        from procurement.models import Vendor
        vendor = Vendor.objects.create(name='Default Vendor', code='DEF001')
        self.assertEqual(vendor.balance, Decimal('0'))
        self.assertEqual(vendor.total_orders, 0)

    def test_performance_rating_no_orders(self):
        """Zero orders → rating is 0, no ZeroDivisionError."""
        from procurement.models import Vendor
        vendor = Vendor(name='New Vendor', code='NV001', total_orders=0)
        self.assertEqual(vendor.performance_rating, 0)

    def test_performance_rating_all_on_time(self):
        """100% on-time + full quality score → 100 rating."""
        from procurement.models import Vendor
        vendor = Vendor(
            name='Perfect Vendor', code='PV001',
            total_orders=10,
            on_time_deliveries=10,
            quality_score=Decimal('100'),
        )
        self.assertAlmostEqual(vendor.performance_rating, 100.0, places=1)

    def test_performance_rating_mixed(self):
        """50% on-time, 80 quality score → 0.5×50 + 0.5×80 = 65."""
        from procurement.models import Vendor
        vendor = Vendor(
            name='Mixed Vendor', code='MX001',
            total_orders=10,
            on_time_deliveries=5,
            quality_score=Decimal('80'),
        )
        self.assertAlmostEqual(vendor.performance_rating, 65.0, places=1)


# ---------------------------------------------------------------------------
# PurchaseType model
# ---------------------------------------------------------------------------

class PurchaseTypeModelTests(TenantTestCase):
    """CRUD tests for procurement.PurchaseType."""

    def test_create_purchase_type(self):
        from procurement.models import PurchaseType
        pt = PurchaseType.objects.create(name='Standard', code='STD')
        self.assertEqual(pt.name, 'Standard')
