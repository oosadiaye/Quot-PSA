"""
HRM Minimum Viable Test Suite
==============================
Covers: Department, Position, LeaveType model CRUD and
TaxCalculationService pure-Python calculations (no DB).

Run with:
    python manage.py test hrm --verbosity=2
"""
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase
from django_tenants.test.cases import TenantTestCase


# ---------------------------------------------------------------------------
# TaxCalculationService — pure Python, no DB required
# ---------------------------------------------------------------------------

class TaxCalculationServiceTests(SimpleTestCase):
    """Unit tests for tax / pension / social-security calculation logic."""

    def _svc(self):
        from hrm.services.tax_calculation import TaxCalculationService
        return TaxCalculationService

    def test_calculate_pension_returns_required_keys(self):
        svc = self._svc()
        with patch('hrm.services.tax_calculation.TaxConfiguration') as MockTC:
            MockTC.objects.filter.return_value.first.return_value = None
            result = svc.calculate_pension(None, Decimal('5000'))
        for key in ('employee_pension', 'employer_pension', 'total_pension', 'rate_used'):
            self.assertIn(key, result)

    def test_calculate_pension_default_rate_5_pct(self):
        """Falls back to 5% when TaxConfiguration is absent."""
        svc = self._svc()
        with patch('hrm.services.tax_calculation.TaxConfiguration') as MockTC:
            MockTC.objects.filter.return_value.first.return_value = None
            result = svc.calculate_pension(None, Decimal('10000'))
        self.assertEqual(result['rate_used'], Decimal('0.05'))
        self.assertEqual(result['employee_pension'], Decimal('500.00'))

    def test_calculate_pension_enforces_cap(self):
        """Pension is capped at the default cap of 10 000."""
        svc = self._svc()
        with patch('hrm.services.tax_calculation.TaxConfiguration') as MockTC:
            MockTC.objects.filter.return_value.first.return_value = None
            result = svc.calculate_pension(None, Decimal('300000'))
        self.assertEqual(result['employee_pension'], Decimal('10000.00'))

    def test_calculate_pension_uses_config_when_present(self):
        """Uses TaxConfiguration values when a config row exists."""
        from unittest.mock import MagicMock
        svc = self._svc()
        mock_config = MagicMock()
        mock_config.pension_rate = Decimal('0.10')
        mock_config.pension_cap = Decimal('20000')
        with patch('hrm.services.tax_calculation.TaxConfiguration') as MockTC:
            MockTC.objects.filter.return_value.first.return_value = mock_config
            result = svc.calculate_pension(None, Decimal('10000'))
        self.assertEqual(result['employee_pension'], Decimal('1000.00'))

    def test_calculate_social_security_default_rate(self):
        svc = self._svc()
        with patch('hrm.services.tax_calculation.TaxConfiguration') as MockTC:
            MockTC.objects.filter.return_value.first.return_value = None
            result = svc.calculate_social_security(None, Decimal('10000'))
        # Default 5% with cap 50 000 → 10 000 × 0.05 = 500
        self.assertEqual(result['employee_ss'], Decimal('500.00'))


# ---------------------------------------------------------------------------
# Department model
# ---------------------------------------------------------------------------

class DepartmentModelTests(TenantTestCase):
    """CRUD tests for hrm.Department."""

    def test_create_department(self):
        from hrm.models import Department
        dept = Department.objects.create(name='Engineering', code='ENG')
        self.assertEqual(dept.name, 'Engineering')
        self.assertTrue(dept.is_active)

    def test_department_str(self):
        from hrm.models import Department
        dept = Department.objects.create(name='Finance', code='FIN')
        self.assertEqual(str(dept), 'Finance')

    def test_department_code_unique(self):
        from hrm.models import Department
        from django.db import IntegrityError
        Department.objects.create(name='HR', code='HR01')
        with self.assertRaises(IntegrityError):
            Department.objects.create(name='Human Resources', code='HR01')

    def test_department_parent_hierarchy(self):
        from hrm.models import Department
        parent = Department.objects.create(name='Corporate', code='CORP')
        child = Department.objects.create(name='IT', code='IT01', parent=parent)
        self.assertEqual(child.parent, parent)
        self.assertIn(child, parent.sub_departments.all())

    def test_department_defaults(self):
        from hrm.models import Department
        dept = Department.objects.create(name='Legal', code='LEG')
        self.assertIsNone(dept.parent)
        self.assertIsNone(dept.manager)
        self.assertEqual(dept.description, '')


# ---------------------------------------------------------------------------
# Position model
# ---------------------------------------------------------------------------

class PositionModelTests(TenantTestCase):
    """CRUD tests for hrm.Position."""

    def setUp(self):
        from hrm.models import Department
        self.dept = Department.objects.create(name='Operations', code='OPS')

    def test_create_position(self):
        from hrm.models import Position
        pos = Position.objects.create(
            title='Senior Developer', code='P001',
            department=self.dept, grade='Senior',
        )
        self.assertEqual(pos.title, 'Senior Developer')
        self.assertTrue(pos.is_active)

    def test_position_str(self):
        from hrm.models import Position
        pos = Position.objects.create(
            title='Analyst', code='P002',
            department=self.dept, grade='Mid',
        )
        self.assertIn(self.dept.name, str(pos))

    def test_position_code_unique_within_department(self):
        from hrm.models import Position
        from django.db import IntegrityError
        Position.objects.create(title='Dev', code='P010', department=self.dept, grade='Mid')
        with self.assertRaises(IntegrityError):
            Position.objects.create(title='Dev 2', code='P010', department=self.dept, grade='Senior')


# ---------------------------------------------------------------------------
# LeaveType model
# ---------------------------------------------------------------------------

class LeaveTypeModelTests(TenantTestCase):
    """CRUD tests for hrm.LeaveType."""

    def test_create_leave_type(self):
        from hrm.models import LeaveType
        lt = LeaveType.objects.create(name='Annual Leave', code='AL', max_days_per_year=21)
        self.assertEqual(lt.max_days_per_year, 21)
        self.assertTrue(lt.is_paid)   # default True
        self.assertTrue(lt.is_active)  # default True
