"""
Quality Minimum Viable Test Suite
===================================
Covers: QAConfiguration, QualityInspection, NonConformance model CRUD;
QualityInspection status transitions.

Run with:
    python manage.py test quality --verbosity=2
"""
from datetime import date
from decimal import Decimal

from django_tenants.test.cases import TenantTestCase


# ---------------------------------------------------------------------------
# QAConfiguration model
# ---------------------------------------------------------------------------

class QAConfigurationModelTests(TenantTestCase):
    """CRUD tests for quality.QAConfiguration."""

    def test_create_qa_config(self):
        from quality.models import QAConfiguration
        cfg = QAConfiguration.objects.create(
            name='Incoming Inspection',
            trigger_event='GRN_Created',
            inspection_type='Incoming',
        )
        self.assertEqual(cfg.name, 'Incoming Inspection')
        self.assertTrue(cfg.is_required)
        self.assertTrue(cfg.auto_create)
        self.assertTrue(cfg.is_active)

    def test_qa_config_str(self):
        from quality.models import QAConfiguration
        cfg = QAConfiguration.objects.create(
            name='Final QC', trigger_event='Sales_Dispatch', inspection_type='Final',
        )
        # __str__ includes display label
        self.assertIn('Final QC', str(cfg))


# ---------------------------------------------------------------------------
# QualityInspection model
# ---------------------------------------------------------------------------

class QualityInspectionModelTests(TenantTestCase):
    """CRUD tests for quality.QualityInspection."""

    def _make_inspection(self, **kwargs):
        from quality.models import QualityInspection
        defaults = dict(
            inspection_number=f'QI-{QualityInspection.objects.count() + 1:04d}',
            inspection_type='Incoming',
            inspection_date=date.today(),
        )
        defaults.update(kwargs)
        return QualityInspection.objects.create(**defaults)

    def test_create_inspection(self):
        insp = self._make_inspection()
        self.assertEqual(insp.status, 'Pending')
        self.assertIsNotNone(insp.pk)

    def test_inspection_number_unique(self):
        from django.db import IntegrityError
        self._make_inspection(inspection_number='QI-DUP')
        with self.assertRaises(IntegrityError):
            self._make_inspection(inspection_number='QI-DUP')

    def test_inspection_status_transitions(self):
        """Status can be updated from Pending → In Progress → Passed."""
        insp = self._make_inspection()
        self.assertEqual(insp.status, 'Pending')

        insp.status = 'In Progress'
        insp.save()
        insp.refresh_from_db()
        self.assertEqual(insp.status, 'In Progress')

        insp.status = 'Passed'
        insp.save()
        insp.refresh_from_db()
        self.assertEqual(insp.status, 'Passed')

    def test_inspection_optional_fields_nullable(self):
        insp = self._make_inspection()
        self.assertIsNone(insp.goods_received_note)
        self.assertIsNone(insp.inspector)
        self.assertIsNone(insp.qc_expense_account)


# ---------------------------------------------------------------------------
# NonConformance model
# ---------------------------------------------------------------------------

class NonConformanceModelTests(TenantTestCase):
    """CRUD tests for quality.NonConformance."""

    def setUp(self):
        from quality.models import QualityInspection
        self.inspection = QualityInspection.objects.create(
            inspection_number='QI-NCR-001',
            inspection_type='Final',
            inspection_date=date.today(),
        )

    def test_create_non_conformance(self):
        from quality.models import NonConformance
        ncr = NonConformance.objects.create(
            ncr_number='NCR-001',
            title='Dimensional Deviation',
            description='Dimensional deviation on shaft diameter',
            severity='Major',
            related_inspection=self.inspection,
        )
        self.assertEqual(ncr.ncr_number, 'NCR-001')
        self.assertEqual(ncr.status, 'Open')
        self.assertIsNotNone(ncr.pk)
