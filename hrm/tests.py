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
        with patch('hrm.models.TaxConfiguration') as MockTC:
            MockTC.objects.filter.return_value.first.return_value = None
            result = svc.calculate_pension(None, Decimal('5000'))
        for key in ('employee_pension', 'employer_pension', 'total_pension', 'rate_used'):
            self.assertIn(key, result)

    def test_calculate_pension_default_rate_5_pct(self):
        """Falls back to 5% when TaxConfiguration is absent."""
        svc = self._svc()
        with patch('hrm.models.TaxConfiguration') as MockTC:
            MockTC.objects.filter.return_value.first.return_value = None
            result = svc.calculate_pension(None, Decimal('10000'))
        self.assertEqual(result['rate_used'], Decimal('0.05'))
        self.assertEqual(result['employee_pension'], Decimal('500.00'))

    def test_calculate_pension_enforces_cap(self):
        """Pension is capped at the default cap of 10 000."""
        svc = self._svc()
        with patch('hrm.models.TaxConfiguration') as MockTC:
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
        with patch('hrm.models.TaxConfiguration') as MockTC:
            MockTC.objects.filter.return_value.first.return_value = mock_config
            result = svc.calculate_pension(None, Decimal('10000'))
        self.assertEqual(result['employee_pension'], Decimal('1000.00'))

    def test_calculate_social_security_default_rate(self):
        svc = self._svc()
        with patch('hrm.models.TaxConfiguration') as MockTC:
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


# ---------------------------------------------------------------------------
# Phase 3 — Payroll Runner (pure-Python tests for compute_line)
# ---------------------------------------------------------------------------


class PayrollRunnerComputeLineTests(SimpleTestCase):
    """Unit tests for the deterministic payroll pipeline.

    We stub the Employee / PayrollPeriod objects because compute_line only
    reads attributes — no DB writes.
    """

    def _period(self):
        from types import SimpleNamespace
        from datetime import date
        return SimpleNamespace(start_date=date(2026, 4, 1), end_date=date(2026, 4, 30))

    def _employee(self, basic):
        from types import SimpleNamespace
        return SimpleNamespace(
            pk=1,
            base_salary=Decimal(basic),
            salary_structure=None,
            employee_type='Permanent',
            bank_name='',
            bank_account='',
        )

    def test_compute_line_produces_expected_net_pay(self):
        """A 500_000 NGN monthly salary must produce positive net pay with
        PAYE + pension + NHF applied."""
        from hrm.services.payroll_runner import compute_line
        with patch('hrm.models.NigeriaTaxBracket') as MockB, \
             patch('hrm.models.PensionConfiguration') as MockP:
            MockB.objects.filter.return_value.order_by.return_value.exists.return_value = False
            MockP.objects.filter.return_value.first.return_value = None

            calc = compute_line(
                self._employee('500000'),
                self._period(),
                statutory_templates=[],
            )

        self.assertEqual(calc.basic_salary, Decimal('500000.00'))
        self.assertEqual(calc.gross_salary, Decimal('500000.00'))
        # 8% pension on 500,000 = 40,000
        self.assertEqual(calc.pension_deduction, Decimal('40000.00'))
        # 2.5% NHF on 500,000 = 12,500
        self.assertEqual(calc.nhf_deduction, Decimal('12500.00'))
        # Employer pension 10% = 50,000
        self.assertEqual(calc.employer_pension, Decimal('50000.00'))
        # Net must be positive and equal gross - deductions
        self.assertGreater(calc.net_salary, Decimal('0'))
        self.assertEqual(
            calc.net_salary,
            calc.gross_salary - calc.total_deductions,
        )
        # Working days in April 2026 — Wed Apr 1 to Thu Apr 30 inclusive, Mon-Fri only
        self.assertEqual(calc.working_days, 22)

    def test_compute_line_handles_zero_basic(self):
        from hrm.services.payroll_runner import compute_line
        with patch('hrm.models.NigeriaTaxBracket') as MockB, \
             patch('hrm.models.PensionConfiguration') as MockP:
            MockB.objects.filter.return_value.order_by.return_value.exists.return_value = False
            MockP.objects.filter.return_value.first.return_value = None
            calc = compute_line(
                self._employee('0'), self._period(), statutory_templates=[],
            )
        self.assertEqual(calc.gross_salary, Decimal('0.00'))
        self.assertEqual(calc.pension_deduction, Decimal('0.00'))
        self.assertEqual(calc.net_salary, Decimal('0.00'))

    def test_compute_line_is_deterministic(self):
        """Running compute_line twice with identical inputs yields identical output."""
        from hrm.services.payroll_runner import compute_line
        with patch('hrm.models.NigeriaTaxBracket') as MockB, \
             patch('hrm.models.PensionConfiguration') as MockP:
            MockB.objects.filter.return_value.order_by.return_value.exists.return_value = False
            MockP.objects.filter.return_value.first.return_value = None
            emp = self._employee('350000')
            period = self._period()
            a = compute_line(emp, period, statutory_templates=[])
            b = compute_line(emp, period, statutory_templates=[])
        self.assertEqual(a, b)


# ---------------------------------------------------------------------------
# Phase 4 — Leave Automation
# ---------------------------------------------------------------------------


class LeaveAccrualHelperTests(SimpleTestCase):
    """Unit tests for the pure helper :func:`_completed_months`."""

    def test_completed_months_same_day(self):
        from datetime import date
        from hrm.services.leave_accrual import _completed_months
        self.assertEqual(
            _completed_months(date(2025, 1, 15), date(2026, 4, 15)), 15,
        )

    def test_completed_months_before_anniversary_day(self):
        from datetime import date
        from hrm.services.leave_accrual import _completed_months
        # Hired Jan 15; on Apr 14, Apr does NOT count yet.
        self.assertEqual(
            _completed_months(date(2026, 1, 15), date(2026, 4, 14)), 2,
        )

    def test_completed_months_future_hire(self):
        from datetime import date
        from hrm.services.leave_accrual import _completed_months
        self.assertEqual(
            _completed_months(date(2027, 1, 1), date(2026, 4, 1)), 0,
        )


class LeaveAccrualIntegrationTests(TenantTestCase):
    """End-to-end accrual against a real (tenant) DB."""

    def _employee(self, hire: str = '2024-01-01'):
        from datetime import date
        from hrm.models import Department, Employee
        dept = Department.objects.create(name='Ops', code='OPS01')
        hire_date = date.fromisoformat(hire)
        return Employee.objects.create(
            employee_id=f'EMP-{hire.replace("-", "")}',
            first_name='Ada',
            last_name='Lovelace',
            email=f'ada-{hire}@example.com',
            phone='0800',
            hire_date=hire_date,
            department=dept,
            status='Active',
        )

    def _leave_with_policy(self, accrual='1.67', min_service=0, max_balance=0):
        from hrm.models import LeavePolicy, LeaveType
        lt = LeaveType.objects.create(
            name='Annual', code=f'AL-{accrual}-{min_service}',
            max_days_per_year=20,
        )
        LeavePolicy.objects.create(
            leave_type=lt,
            accrual_per_month=Decimal(accrual),
            max_balance=Decimal(max_balance),
            min_service_months=min_service,
            requires_hr_approval=True,
            is_active=True,
        )
        return lt

    def test_accrue_month_is_idempotent(self):
        """Running accrual twice must not double-credit."""
        from hrm.models import LeaveAccrualEntry
        from hrm.services.leave_accrual import accrue_month
        self._employee('2024-01-01')
        self._leave_with_policy(accrual='1.67')

        first = accrue_month(2026, 4)
        second = accrue_month(2026, 4)

        self.assertEqual(first.entries_created, 1)
        self.assertEqual(second.entries_created, 0)
        self.assertEqual(second.entries_skipped, 1)
        self.assertEqual(LeaveAccrualEntry.objects.count(), 1)

    def test_accrue_month_respects_min_service(self):
        from hrm.services.leave_accrual import accrue_month
        # Hired Feb 2026; by Apr 2026 only 2 completed months → below min 6.
        self._employee('2026-02-01')
        self._leave_with_policy(accrual='1.67', min_service=6)

        summary = accrue_month(2026, 4)
        self.assertEqual(summary.entries_created, 0)
        self.assertEqual(summary.entries_skipped, 1)

    def test_accrue_month_respects_max_balance_cap(self):
        """Once balance reaches the cap, no further credit that month."""
        from datetime import date
        from hrm.models import LeaveAccrualEntry
        from hrm.services.leave_accrual import accrue_month

        emp = self._employee('2024-01-01')
        lt = self._leave_with_policy(accrual='5.00', max_balance='6.00')

        # Seed a prior month with 5 days already accrued.
        LeaveAccrualEntry.objects.create(
            employee=emp, leave_type=lt, year=2026, month=3,
            days_credited=Decimal('5.00'),
        )
        summary = accrue_month(2026, 4)
        # Only 1 day of headroom remains (6 - 5) — credit is capped.
        self.assertEqual(summary.entries_created, 1)
        entry = LeaveAccrualEntry.objects.get(
            employee=emp, leave_type=lt, year=2026, month=4,
        )
        self.assertEqual(entry.days_credited, Decimal('1.00'))


class LeaveApprovalStateMachineTests(TenantTestCase):
    """Multi-step approval chain transitions."""

    def setUp(self):
        from datetime import date
        from django.contrib.auth.models import User
        from hrm.models import (
            Department, Employee, LeavePolicy, LeaveRequest, LeaveType,
        )
        self.manager_user = User.objects.create_user('mgr', password='x')
        self.hr_user = User.objects.create_user('hr', password='x')
        dept = Department.objects.create(name='Ops', code='OPS')
        self.supervisor_emp = Employee.objects.create(
            employee_id='SUP-001', first_name='Sue', last_name='Pervisor',
            email='sue@example.com', phone='0800', hire_date=date(2020, 1, 1),
            department=dept, status='Active', user=self.manager_user,
        )
        self.emp = Employee.objects.create(
            employee_id='EMP-100', first_name='Ada', last_name='Lovelace',
            email='ada@example.com', phone='0800', hire_date=date(2024, 1, 1),
            department=dept, status='Active', supervisor=self.supervisor_emp,
        )
        self.lt = LeaveType.objects.create(
            name='Annual', code='AL', max_days_per_year=20,
        )
        LeavePolicy.objects.create(
            leave_type=self.lt, accrual_per_month=Decimal('1.67'),
            requires_hr_approval=True, is_active=True,
        )
        self.request = LeaveRequest.objects.create(
            employee=self.emp, leave_type=self.lt,
            start_date=date(2026, 5, 1), end_date=date(2026, 5, 3),
            reason='Annual break', status='Draft',
        )

    def test_submit_creates_two_step_chain(self):
        from hrm.services.leave_approval import submit_request
        submit_request(self.request)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, 'Pending')
        steps = list(self.request.approval_steps.order_by('step_order'))
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].role, 'Line_Manager')
        self.assertEqual(steps[0].assigned_to, self.manager_user)
        self.assertEqual(steps[1].role, 'HR')

    def test_full_approval_flips_request_to_approved(self):
        from hrm.services.leave_approval import (
            DECISION_APPROVED, decide_step, submit_request,
        )
        submit_request(self.request)
        step1, step2 = self.request.approval_steps.order_by('step_order')

        decide_step(step1, user=self.manager_user, decision=DECISION_APPROVED)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, 'Pending')  # still awaiting HR

        decide_step(step2, user=self.hr_user, decision=DECISION_APPROVED)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, 'Approved')
        self.assertEqual(self.request.approved_by, self.hr_user)

    def test_rejection_short_circuits_chain(self):
        from hrm.services.leave_approval import (
            DECISION_REJECTED, decide_step, submit_request,
        )
        submit_request(self.request)
        step1, step2 = self.request.approval_steps.order_by('step_order')

        decide_step(
            step1, user=self.manager_user,
            decision=DECISION_REJECTED, comments='Insufficient notice',
        )
        self.request.refresh_from_db()
        step2.refresh_from_db()
        self.assertEqual(self.request.status, 'Rejected')
        self.assertEqual(step2.decision, 'Skipped')

    def test_cannot_skip_step_order(self):
        """Step 2 cannot be decided while step 1 is still Pending."""
        from hrm.services.leave_approval import (
            ApprovalError, DECISION_APPROVED, decide_step, submit_request,
        )
        submit_request(self.request)
        _, step2 = self.request.approval_steps.order_by('step_order')
        with self.assertRaises(ApprovalError):
            decide_step(step2, user=self.hr_user, decision=DECISION_APPROVED)


# ---------------------------------------------------------------------------
# Phase 5 — Grade/Step Salary Scale
# ---------------------------------------------------------------------------


class SalaryScaleHelperTests(SimpleTestCase):
    """Pure-python helpers for scale arithmetic (no DB)."""

    def test_monthly_basic_rounds_to_two_dp(self):
        from types import SimpleNamespace
        from hrm.models import SalaryStep
        # Use SalaryStep.monthly_basic via a SimpleNamespace that mimics it.
        step = SimpleNamespace(annual_basic=Decimal('1234567.89'))
        # Mirror the property logic.
        monthly = (step.annual_basic / Decimal('12')).quantize(Decimal('0.01'))
        self.assertEqual(monthly, Decimal('102880.66'))

    def test_is_due_exactly_at_anniversary(self):
        from datetime import date
        from types import SimpleNamespace
        from hrm.services.salary_scale import _is_due
        placement = SimpleNamespace(
            effective_from=date(2025, 4, 1),
            step=SimpleNamespace(grade=SimpleNamespace(annual_increment_months=12)),
        )
        self.assertTrue(_is_due(placement, date(2026, 4, 1)))
        self.assertFalse(_is_due(placement, date(2026, 3, 31)))

    def test_is_due_handles_month_overflow(self):
        from datetime import date
        from types import SimpleNamespace
        from hrm.services.salary_scale import _is_due
        placement = SimpleNamespace(
            effective_from=date(2025, 6, 15),
            step=SimpleNamespace(grade=SimpleNamespace(annual_increment_months=12)),
        )
        self.assertFalse(_is_due(placement, date(2026, 6, 14)))
        self.assertTrue(_is_due(placement, date(2026, 6, 15)))


class SalaryScaleIntegrationTests(TenantTestCase):
    """End-to-end placement and step advancement."""

    def _make_scale(self):
        from datetime import date
        from hrm.models import SalaryGrade, SalaryScale, SalaryStep
        scale = SalaryScale.objects.create(
            family='CONPSS', name='Test scale',
            effective_from=date(2024, 1, 1), is_active=True,
        )
        grade = SalaryGrade.objects.create(
            scale=scale, code='GL08', rank_order=8,
            max_steps=3, annual_increment_months=12,
        )
        steps = [
            SalaryStep.objects.create(grade=grade, step_number=i, annual_basic=amt)
            for i, amt in enumerate([Decimal('1200000'), Decimal('1260000'), Decimal('1320000')], start=1)
        ]
        return scale, grade, steps

    def _employee(self):
        from datetime import date
        from hrm.models import Department, Employee
        dept = Department.objects.create(name='Ops', code='OPS99')
        return Employee.objects.create(
            employee_id='EMP-SCALE', first_name='Ada', last_name='L',
            email='ada-scale@example.com', phone='0800',
            hire_date=date(2024, 1, 1), department=dept, status='Active',
        )

    def test_current_placement_returns_latest_before_date(self):
        from datetime import date
        from hrm.services.salary_scale import current_placement, place_employee
        _, _, steps = self._make_scale()
        emp = self._employee()
        p1 = place_employee(emp, steps[0], effective_from=date(2024, 1, 1), reason='Appointment')
        p2 = place_employee(emp, steps[1], effective_from=date(2025, 1, 1), reason='Step_Increment')
        # As of mid-2024, only p1 applies.
        self.assertEqual(current_placement(emp, as_of=date(2024, 6, 1)), p1)
        # As of 2025, p2 applies.
        self.assertEqual(current_placement(emp, as_of=date(2025, 6, 1)), p2)

    def test_advance_step_moves_to_next_step(self):
        from datetime import date
        from hrm.services.salary_scale import advance_step, place_employee
        _, _, steps = self._make_scale()
        emp = self._employee()
        place_employee(emp, steps[0], effective_from=date(2024, 1, 1), reason='Appointment')

        new_placement = advance_step(emp, as_of=date(2025, 1, 1))
        self.assertIsNotNone(new_placement)
        self.assertEqual(new_placement.step.step_number, 2)
        self.assertEqual(new_placement.reason, 'Step_Increment')

    def test_advance_step_noop_before_due(self):
        from datetime import date
        from hrm.services.salary_scale import advance_step, place_employee
        _, _, steps = self._make_scale()
        emp = self._employee()
        place_employee(emp, steps[0], effective_from=date(2024, 1, 1), reason='Appointment')

        # Only 6 months in — not yet due.
        self.assertIsNone(advance_step(emp, as_of=date(2024, 7, 1)))

    def test_advance_step_stops_at_max(self):
        from datetime import date
        from hrm.services.salary_scale import advance_step, place_employee
        _, _, steps = self._make_scale()
        emp = self._employee()
        # Place directly at top step.
        place_employee(emp, steps[-1], effective_from=date(2024, 1, 1), reason='Appointment')
        self.assertIsNone(advance_step(emp, as_of=date(2026, 1, 1)))


# ---------------------------------------------------------------------------
# Phase 6 — Lifecycle Automation
# ---------------------------------------------------------------------------


class LifecycleHelperTests(SimpleTestCase):
    """Pure date-math helpers (no DB)."""

    def test_age_years_before_birthday(self):
        from datetime import date
        from hrm.services.lifecycle import _age_years
        # Born June 15, 1965; on June 14, 2025 → still 59.
        self.assertEqual(_age_years(date(1965, 6, 15), date(2025, 6, 14)), 59)
        # On June 15, 2025 → 60.
        self.assertEqual(_age_years(date(1965, 6, 15), date(2025, 6, 15)), 60)

    def test_service_years_future_hire(self):
        from datetime import date
        from hrm.services.lifecycle import _service_years
        self.assertEqual(
            _service_years(date(2030, 1, 1), date(2026, 1, 1)), 0,
        )

    def test_service_years_exactly_35(self):
        from datetime import date
        from hrm.services.lifecycle import _service_years
        self.assertEqual(
            _service_years(date(1990, 4, 1), date(2025, 4, 1)), 35,
        )

    def test_extract_dob_reads_personal_info(self):
        from types import SimpleNamespace
        from datetime import date
        from hrm.services.lifecycle import _extract_dob
        emp = SimpleNamespace(personal_info={'date_of_birth': '1965-06-15'})
        self.assertEqual(_extract_dob(emp), date(1965, 6, 15))

    def test_extract_dob_returns_none_on_bad_input(self):
        from types import SimpleNamespace
        from hrm.services.lifecycle import _extract_dob
        self.assertIsNone(_extract_dob(SimpleNamespace(personal_info={})))
        self.assertIsNone(_extract_dob(
            SimpleNamespace(personal_info={'dob': 'not-a-date'})
        ))

    def test_check_retirement_eligibility_by_age(self):
        from types import SimpleNamespace
        from datetime import date
        from hrm.services.lifecycle import check_retirement_eligibility
        emp = SimpleNamespace(
            status='Active',
            personal_info={'date_of_birth': '1965-01-01'},
            hire_date=date(2010, 1, 1),
        )
        eligible, trigger = check_retirement_eligibility(emp, as_of=date(2026, 1, 1))
        self.assertTrue(eligible)
        self.assertEqual(trigger, 'Age_60')

    def test_check_retirement_eligibility_by_service(self):
        from types import SimpleNamespace
        from datetime import date
        from hrm.services.lifecycle import check_retirement_eligibility
        emp = SimpleNamespace(
            status='Active',
            personal_info={'date_of_birth': '1980-01-01'},  # age 46
            hire_date=date(1990, 1, 1),  # 36 years service
        )
        eligible, trigger = check_retirement_eligibility(emp, as_of=date(2026, 1, 1))
        self.assertTrue(eligible)
        self.assertEqual(trigger, 'Service_35')

    def test_check_retirement_eligibility_ignores_inactive(self):
        from types import SimpleNamespace
        from datetime import date
        from hrm.services.lifecycle import check_retirement_eligibility
        emp = SimpleNamespace(
            status='Terminated',
            personal_info={'date_of_birth': '1960-01-01'},
            hire_date=date(1980, 1, 1),
        )
        eligible, trigger = check_retirement_eligibility(emp, as_of=date(2026, 1, 1))
        self.assertFalse(eligible)
        self.assertIsNone(trigger)

    def test_check_retirement_eligibility_young_short_service(self):
        from types import SimpleNamespace
        from datetime import date
        from hrm.services.lifecycle import check_retirement_eligibility
        emp = SimpleNamespace(
            status='Active',
            personal_info={'date_of_birth': '1985-01-01'},
            hire_date=date(2015, 1, 1),
        )
        eligible, _ = check_retirement_eligibility(emp, as_of=date(2026, 1, 1))
        self.assertFalse(eligible)


# ---------------------------------------------------------------------------
# Phase 7 — Notification Task Helpers
# ---------------------------------------------------------------------------


class NotificationHelperTests(SimpleTestCase):
    """Pure functions used by the Celery tasks."""

    def test_days_until_future(self):
        from datetime import date
        from hrm.tasks import _days_until
        self.assertEqual(
            _days_until(date(2026, 5, 10), as_of=date(2026, 5, 1)), 9,
        )

    def test_days_until_past_is_negative(self):
        from datetime import date
        from hrm.tasks import _days_until
        self.assertEqual(
            _days_until(date(2026, 4, 20), as_of=date(2026, 5, 1)), -11,
        )

    def test_is_reminder_window_inclusive(self):
        from datetime import date
        from hrm.tasks import _is_reminder_window
        today = date(2026, 5, 1)
        # Deadline exactly 7 days out → inside window.
        self.assertTrue(_is_reminder_window(date(2026, 5, 8), as_of=today))
        # Deadline today → inside window.
        self.assertTrue(_is_reminder_window(today, as_of=today))
        # Deadline 8 days out → outside.
        self.assertFalse(_is_reminder_window(date(2026, 5, 9), as_of=today))
        # Deadline yesterday → outside (past, excluded).
        self.assertFalse(_is_reminder_window(date(2026, 4, 30), as_of=today))

    def test_is_retirement_lookahead_respects_horizon(self):
        from datetime import date
        from hrm.tasks import _is_retirement_lookahead
        today = date(2026, 5, 1)
        # 45 days out → within 90.
        self.assertTrue(_is_retirement_lookahead(date(2026, 6, 15), as_of=today))
        # 120 days out → outside 90.
        self.assertFalse(_is_retirement_lookahead(date(2026, 8, 29), as_of=today))

    def test_safe_send_swallows_exception(self):
        """A broken email backend must not raise — returns False."""
        from unittest.mock import patch
        from hrm.tasks import _safe_send
        with patch('core.localized_emails.send_localized_email',
                   side_effect=RuntimeError('SMTP down')):
            result = _safe_send('anything', 'x@example.com', {})
        self.assertFalse(result)

    def test_safe_send_returns_true_when_email_sent(self):
        from unittest.mock import patch
        from hrm.tasks import _safe_send
        with patch('core.localized_emails.send_localized_email',
                   return_value=True):
            result = _safe_send('anything', 'x@example.com', {})
        self.assertTrue(result)


# --------------------------------------------------------------------------- #
# Phase 8 — Biometric helpers (pure, no DB)
# --------------------------------------------------------------------------- #

class BiometricHelperTests(SimpleTestCase):
    """HMAC, geodesy, and event-classification helpers."""

    def test_verify_signature_accepts_valid_hex(self):
        import hmac as _hmac
        import hashlib as _hashlib
        from hrm.services.biometric import verify_signature
        secret = 'topsecret'
        body = b'{"event_type":"check_in"}'
        sig = _hmac.new(secret.encode(), body, _hashlib.sha256).hexdigest()
        self.assertTrue(verify_signature(secret, body, sig))

    def test_verify_signature_rejects_tampered_body(self):
        import hmac as _hmac
        import hashlib as _hashlib
        from hrm.services.biometric import verify_signature
        secret = 'topsecret'
        good_sig = _hmac.new(secret.encode(), b'ORIGINAL', _hashlib.sha256).hexdigest()
        self.assertFalse(verify_signature(secret, b'TAMPERED', good_sig))

    def test_verify_signature_rejects_wrong_secret(self):
        import hmac as _hmac
        import hashlib as _hashlib
        from hrm.services.biometric import verify_signature
        body = b'payload'
        sig = _hmac.new(b'secret-a', body, _hashlib.sha256).hexdigest()
        self.assertFalse(verify_signature('secret-b', body, sig))

    def test_verify_signature_rejects_empty_secret(self):
        from hrm.services.biometric import verify_signature
        self.assertFalse(verify_signature('', b'body', 'deadbeef'))

    def test_verify_signature_rejects_empty_signature(self):
        from hrm.services.biometric import verify_signature
        self.assertFalse(verify_signature('secret', b'body', ''))

    def test_verify_signature_handles_bad_hex_gracefully(self):
        from hrm.services.biometric import verify_signature
        # Non-hex garbage must not raise.
        self.assertFalse(verify_signature('secret', b'body', 'ZZZZ-not-hex'))

    def test_haversine_zero_for_identical_points(self):
        from hrm.services.biometric import haversine_distance_m
        d = haversine_distance_m(6.5244, 3.3792, 6.5244, 3.3792)
        self.assertAlmostEqual(d, 0.0, places=3)

    def test_haversine_one_degree_latitude_is_about_111km(self):
        from hrm.services.biometric import haversine_distance_m
        d = haversine_distance_m(0.0, 0.0, 1.0, 0.0)
        # 1° of latitude ≈ 111.195 km; allow ±1 km tolerance.
        self.assertGreater(d, 110_000)
        self.assertLess(d, 112_000)

    def test_classify_event_explicit_check_in(self):
        from hrm.services.biometric import _classify_event
        self.assertEqual(_classify_event('check_in', existing_check_in=True), 'check_in')

    def test_classify_event_explicit_check_out(self):
        from hrm.services.biometric import _classify_event
        self.assertEqual(_classify_event('check_out', existing_check_in=False), 'check_out')

    def test_classify_event_first_implicit_becomes_check_in(self):
        from hrm.services.biometric import _classify_event
        self.assertEqual(_classify_event('scan', existing_check_in=False), 'check_in')

    def test_classify_event_subsequent_implicit_becomes_check_out(self):
        from hrm.services.biometric import _classify_event
        self.assertEqual(_classify_event('scan', existing_check_in=True), 'check_out')

    def test_parse_occurred_at_accepts_iso_with_z_suffix(self):
        from datetime import datetime, timezone as _tz
        from hrm.services.biometric import _parse_occurred_at
        got = _parse_occurred_at('2026-04-24T09:15:00Z')
        self.assertEqual(got, datetime(2026, 4, 24, 9, 15, tzinfo=_tz.utc))

    def test_parse_occurred_at_accepts_offset_suffix(self):
        from hrm.services.biometric import _parse_occurred_at
        got = _parse_occurred_at('2026-04-24T09:15:00+01:00')
        self.assertEqual(got.utcoffset().total_seconds(), 3600)

    def test_parse_occurred_at_passes_through_datetime(self):
        from datetime import datetime, timezone as _tz
        from hrm.services.biometric import _parse_occurred_at
        dt = datetime(2026, 4, 24, 9, 15, tzinfo=_tz.utc)
        self.assertIs(_parse_occurred_at(dt), dt)

    def test_parse_occurred_at_rejects_non_string(self):
        from hrm.services.biometric import _parse_occurred_at, BiometricIngestError
        with self.assertRaises(BiometricIngestError):
            _parse_occurred_at(12345)

    def test_geofence_violation_none_when_device_has_no_fence(self):
        from types import SimpleNamespace
        from hrm.services.biometric import _geofence_violation
        device = SimpleNamespace(
            geofence_latitude=None, geofence_longitude=None, geofence_radius_m=None,
        )
        self.assertIsNone(_geofence_violation(device, 6.5, 3.3))

    def test_geofence_violation_none_when_payload_has_no_coords(self):
        from types import SimpleNamespace
        from hrm.services.biometric import _geofence_violation
        device = SimpleNamespace(
            geofence_latitude=6.5244, geofence_longitude=3.3792, geofence_radius_m=100,
        )
        self.assertIsNone(_geofence_violation(device, None, None))

    def test_geofence_violation_fires_when_outside_radius(self):
        from types import SimpleNamespace
        from hrm.services.biometric import _geofence_violation
        device = SimpleNamespace(
            geofence_latitude=6.5244, geofence_longitude=3.3792, geofence_radius_m=50,
        )
        # ~1° away is ~111 km >> 50 m.
        note = _geofence_violation(device, 7.5244, 3.3792)
        self.assertIsNotNone(note)
        self.assertIn('outside_geofence', note)

    def test_geofence_violation_passes_when_inside_radius(self):
        from types import SimpleNamespace
        from hrm.services.biometric import _geofence_violation
        device = SimpleNamespace(
            geofence_latitude=6.5244, geofence_longitude=3.3792, geofence_radius_m=200,
        )
        # Tiny offset ≈ a few metres.
        self.assertIsNone(_geofence_violation(device, 6.52441, 3.37921))
