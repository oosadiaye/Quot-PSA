"""
Production Minimum Viable Test Suite
======================================
Covers: WorkCenter, BillOfMaterials, BOMLine model CRUD.

Run with:
    python manage.py test production --verbosity=2
"""
from decimal import Decimal

from django_tenants.test.cases import TenantTestCase


# ---------------------------------------------------------------------------
# WorkCenter model
# ---------------------------------------------------------------------------

class WorkCenterModelTests(TenantTestCase):
    """CRUD tests for production.WorkCenter."""

    def test_create_work_center(self):
        from production.models import WorkCenter
        wc = WorkCenter.objects.create(
            name='Assembly Line 1',
            code='WC001',
            capacity_hours=Decimal('8.00'),
        )
        self.assertEqual(wc.name, 'Assembly Line 1')
        self.assertTrue(wc.is_active)

    def test_work_center_defaults(self):
        from production.models import WorkCenter
        wc = WorkCenter.objects.create(
            name='Welding', code='WC002', capacity_hours=Decimal('6.00'),
        )
        self.assertEqual(wc.efficiency, Decimal('100'))
        self.assertEqual(wc.labor_rate, Decimal('0'))
        self.assertEqual(wc.overhead_rate, Decimal('0'))

    def test_work_center_str(self):
        from production.models import WorkCenter
        wc = WorkCenter.objects.create(name='Painting', code='WC003', capacity_hours=Decimal('4'))
        self.assertEqual(str(wc), 'Painting')

    def test_work_center_code_unique(self):
        from production.models import WorkCenter
        from django.db import IntegrityError
        WorkCenter.objects.create(name='CNC', code='WC-DUP', capacity_hours=Decimal('8'))
        with self.assertRaises(IntegrityError):
            WorkCenter.objects.create(name='CNC2', code='WC-DUP', capacity_hours=Decimal('8'))


# ---------------------------------------------------------------------------
# BillOfMaterials model
# ---------------------------------------------------------------------------

class BillOfMaterialsModelTests(TenantTestCase):
    """CRUD tests for production.BillOfMaterials."""

    def _make_bom(self, **kwargs):
        from production.models import BillOfMaterials
        defaults = dict(
            item_code='FIN-001',
            item_name='Finished Widget',
            item_type='Finished',
            unit='PCS',
        )
        defaults.update(kwargs)
        return BillOfMaterials.objects.create(**defaults)

    def test_create_bom(self):
        bom = self._make_bom()
        self.assertEqual(bom.item_code, 'FIN-001')
        self.assertEqual(bom.item_type, 'Finished')

    def test_bom_item_code_unique(self):
        from django.db import IntegrityError
        self._make_bom(item_code='FIN-DUP')
        with self.assertRaises(IntegrityError):
            self._make_bom(item_code='FIN-DUP')

    def test_bom_standard_cost_default(self):
        bom = self._make_bom(item_code='FIN-002')
        self.assertEqual(bom.standard_cost, Decimal('0'))

    def test_bom_item_type_choices(self):
        from production.models import BillOfMaterials
        valid_types = ['Finished', 'Semi-Finished', 'Raw Material']
        for i, t in enumerate(valid_types):
            bom = BillOfMaterials.objects.create(
                item_code=f'TEST-{i:03d}', item_name=t,
                item_type=t, unit='PCS',
            )
            self.assertEqual(bom.item_type, t)


# ---------------------------------------------------------------------------
# BOMLine model
# ---------------------------------------------------------------------------

class BOMLineModelTests(TenantTestCase):
    """CRUD tests for production.BOMLine."""

    def setUp(self):
        from production.models import BillOfMaterials
        self.bom = BillOfMaterials.objects.create(
            item_code='PARENT-001', item_name='Parent Assembly',
            item_type='Finished', unit='PCS',
        )

    def test_add_bom_line(self):
        from production.models import BOMLine, BillOfMaterials
        component = BillOfMaterials.objects.create(
            item_code='RAW-001', item_name='Raw Part',
            item_type='Raw Material', unit='PCS',
        )
        line = BOMLine.objects.create(
            bom=self.bom,
            component=component,
            quantity=Decimal('2.00'),
            unit='PCS',
        )
        self.assertEqual(line.quantity, Decimal('2.00'))
        self.assertIn(line, self.bom.lines.all())
