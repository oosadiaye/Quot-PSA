"""
Unit Tests for Budget Module
============================
Comprehensive test coverage for:
- UnifiedBudget creation and lifecycle
- Budget allocation calculations
- Encumbrance tracking
- Variance computation
- Amendment workflows
- Budget availability checks
"""

from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock

from budget.models import (
    UnifiedBudget,
    UnifiedBudgetEncumbrance,
    UnifiedBudgetVariance,
    UnifiedBudgetAmendment,
)
from accounting.models import (
    Account,
    MDA,
    Fund,
    Function,
    Program,
    Geo,
    CostCenter,
    GLBalance,
    FiscalPeriod,
)
from django.utils import timezone


class UnifiedBudgetTestCase(TestCase):
    """Test cases for UnifiedBudget model"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.fund = Fund.objects.create(
            code='001',
            name='Recurrent Fund',
            is_active=True
        )
        
        self.function = Function.objects.create(
            code='GEN',
            name='General Public Services',
            is_active=True
        )
        
        self.program = Program.objects.create(
            code='01',
            name='Executive and Legislative',
            is_active=True
        )
        
        self.geo = Geo.objects.create(
            code='NG',
            name='Nigeria',
            is_active=True
        )
        
        self.mda = MDA.objects.create(
            code='001',
            name='Ministry of Finance',
            short_name='MoF',
            mda_type='MINISTRY',
            is_active=True
        )
        
        self.cost_center = CostCenter.objects.create(
            code='CC001',
            name='Finance Department',
            center_type='DEPARTMENT',
            is_active=True,
            is_operational=True
        )
        
        self.expense_account = Account.objects.create(
            code='50100000',
            name='Travel Expense',
            account_type='Expense',
            is_active=True
        )
        
        self.revenue_account = Account.objects.create(
            code='40100000',
            name='Government Revenue',
            account_type='Income',
            is_active=True
        )
    
    def test_budget_creation_public_sector(self):
        """Test creating a public sector budget with MDA"""
        budget = UnifiedBudget.objects.create(
            budget_code='2026-001',
            name='Annual Travel Budget 2026',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='ANNUAL',
            period_number=1,
            mda=self.mda,
            fund=self.fund,
            function=self.function,
            program=self.program,
            geo=self.geo,
            account=self.expense_account,
            original_amount=Decimal('1000000.00'),
            status='APPROVED',
            control_level='HARD_STOP'
        )
        
        self.assertEqual(budget.allocated_amount, Decimal('1000000.00'))
        self.assertEqual(budget.budget_type, 'PUBLIC_SECTOR')
        self.assertTrue(budget.enable_encumbrance)
        self.assertFalse(budget.allow_over_expenditure)
    
    def test_budget_creation_private_sector(self):
        """Test creating a private sector budget with Cost Center"""
        budget = UnifiedBudget.objects.create(
            budget_code='2026-CC001-001',
            name='Marketing Department Budget 2026',
            budget_type='PRIVATE_SECTOR',
            fiscal_year='2026',
            period_type='MONTHLY',
            period_number=1,
            cost_center=self.cost_center,
            fund=self.fund,
            function=self.function,
            account=self.expense_account,
            original_amount=Decimal('500000.00'),
            status='DRAFT',
            control_level='WARNING'
        )
        
        self.assertEqual(budget.budget_type, 'PRIVATE_SECTOR')
        self.assertEqual(budget.allocated_amount, Decimal('500000.00'))
        self.assertEqual(budget.period_type, 'MONTHLY')
    
    def test_budget_revision_amount(self):
        """Test that revised_amount takes precedence over original"""
        budget = UnifiedBudget.objects.create(
            budget_code='2026-002',
            name='Original Budget',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='ANNUAL',
            period_number=1,
            mda=self.mda,
            account=self.expense_account,
            original_amount=Decimal('1000000.00'),
            revised_amount=Decimal('1200000.00'),
            status='APPROVED'
        )
        
        self.assertEqual(budget.allocated_amount, Decimal('1200000.00'))
    
    def test_budget_status_transitions(self):
        """Test budget status changes"""
        budget = UnifiedBudget.objects.create(
            budget_code='2026-003',
            name='Budget for Status Test',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='ANNUAL',
            period_number=1,
            mda=self.mda,
            account=self.expense_account,
            original_amount=Decimal('500000.00'),
            status='DRAFT'
        )
        
        # Transition to Pending
        budget.status = 'PENDING'
        budget.save()
        self.assertEqual(budget.status, 'PENDING')
        
        # Transition to Approved
        budget.status = 'APPROVED'
        budget.approved_by = self.user
        budget.approved_date = timezone.now()
        budget.save()
        self.assertEqual(budget.status, 'APPROVED')
        
        # Transition to Closed
        budget.status = 'CLOSED'
        budget.closed_date = timezone.now()
        budget.save()
        self.assertEqual(budget.status, 'CLOSED')
    
    def test_budget_validation_public_sector_requires_mda(self):
        """Test that public sector budgets require MDA"""
        budget = UnifiedBudget(
            budget_code='2026-004',
            name='Invalid Public Budget',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='ANNUAL',
            period_number=1,
            mda=None,  # Missing MDA for public sector
            account=self.expense_account,
            original_amount=Decimal('100000.00')
        )
        
        with self.assertRaises(ValidationError) as ctx:
            budget.clean()
        self.assertIn('Public sector budgets require an MDA', str(ctx.exception))
    
    def test_budget_validation_private_sector_requires_cost_center(self):
        """Test that private sector budgets require Cost Center"""
        budget = UnifiedBudget(
            budget_code='2026-005',
            name='Invalid Private Budget',
            budget_type='PRIVATE_SECTOR',
            fiscal_year='2026',
            period_type='ANNUAL',
            period_number=1,
            cost_center=None,  # Missing cost center
            account=self.expense_account,
            original_amount=Decimal('100000.00')
        )
        
        with self.assertRaises(ValidationError) as ctx:
            budget.clean()
        self.assertIn('Private sector budgets require a Cost Center', str(ctx.exception))
    
    def test_budget_validation_monthly_period_range(self):
        """Test monthly period must be 1-12"""
        budget = UnifiedBudget(
            budget_code='2026-006',
            name='Invalid Monthly Period',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='MONTHLY',
            period_number=15,  # Invalid month
            mda=self.mda,
            account=self.expense_account,
            original_amount=Decimal('100000.00')
        )
        
        with self.assertRaises(ValidationError) as ctx:
            budget.clean()
        self.assertIn('Monthly period must be 1-12', str(ctx.exception))
    
    def test_budget_validation_quarterly_period_range(self):
        """Test quarterly period must be 1-4"""
        budget = UnifiedBudget(
            budget_code='2026-007',
            name='Invalid Quarterly Period',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='QUARTERLY',
            period_number=5,  # Invalid quarter
            mda=self.mda,
            account=self.expense_account,
            original_amount=Decimal('100000.00')
        )
        
        with self.assertRaises(ValidationError) as ctx:
            budget.clean()
        self.assertIn('Quarterly period must be 1-4', str(ctx.exception))
    
    def test_budget_dimension_key(self):
        """Test dimension key generation"""
        budget = UnifiedBudget.objects.create(
            budget_code='2026-008',
            name='Dimension Test',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='ANNUAL',
            period_number=1,
            mda=self.mda,
            fund=self.fund,
            function=self.function,
            program=self.program,
            geo=self.geo,
            account=self.expense_account,
            original_amount=Decimal('1000000.00'),
            status='APPROVED'
        )
        
        key = budget.get_dimension_key()
        self.assertEqual(len(key), 7)
        self.assertEqual(key[4], self.mda.id)  # mda_id
        self.assertEqual(key[0], self.fund.id)  # fund_id
    
    def test_budget_str_representation(self):
        """Test string representation of budget"""
        budget = UnifiedBudget(
            budget_code='2026-009',
            name='Test Budget',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            mda=self.mda,
            account=self.expense_account,
            original_amount=Decimal('100000.00')
        )
        
        self.assertEqual(str(budget), '2026-009 - Test Budget')


class UnifiedBudgetEncumbranceTestCase(TestCase):
    """Test cases for budget encumbrance tracking"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass123'
        )
        
        self.fund = Fund.objects.create(code='001', name='Fund', is_active=True)
        self.mda = MDA.objects.create(code='001', name='MoF', mda_type='MINISTRY', is_active=True)
        self.expense_account = Account.objects.create(
            code='50100000', name='Expense', account_type='Expense', is_active=True
        )
        
        self.budget = UnifiedBudget.objects.create(
            budget_code='2026-ENC-001',
            name='Encumbrance Test Budget',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='ANNUAL',
            period_number=1,
            mda=self.mda,
            fund=self.fund,
            account=self.expense_account,
            original_amount=Decimal('1000000.00'),
            status='APPROVED',
            enable_encumbrance=True
        )
    
    def test_encumbrance_creation(self):
        """Test creating an encumbrance against a budget"""
        encumbrance = UnifiedBudgetEncumbrance.objects.create(
            budget=self.budget,
            reference_type='PO',
            reference_id=1,
            reference_number='PO-2026-001',
            encumbrance_date=date.today(),
            amount=Decimal('250000.00'),
            status='ACTIVE',
            description='Purchase Order for office supplies',
            created_by=self.user
        )
        
        self.assertEqual(encumbrance.remaining_amount, Decimal('250000.00'))
        self.assertEqual(encumbrance.status, 'ACTIVE')
    
    def test_encumbrance_liquidation(self):
        """Test partial liquidation of encumbrance"""
        encumbrance = UnifiedBudgetEncumbrance.objects.create(
            budget=self.budget,
            reference_type='PO',
            reference_id=2,
            reference_number='PO-2026-002',
            encumbrance_date=date.today(),
            amount=Decimal('100000.00'),
            liquidated_amount=Decimal('30000.00'),
            status='ACTIVE',
            created_by=self.user
        )
        
        encumbrance.liquidate(Decimal('20000.00'))
        
        self.assertEqual(encumbrance.liquidated_amount, Decimal('50000.00'))
        self.assertEqual(encumbrance.remaining_amount, Decimal('50000.00'))
    
    def test_encumbrance_auto_status_on_full_liquidation(self):
        """Test status changes to FULLY_LIQUIDATED when fully liquidated"""
        encumbrance = UnifiedBudgetEncumbrance.objects.create(
            budget=self.budget,
            reference_type='PO',
            reference_id=3,
            reference_number='PO-2026-003',
            encumbrance_date=date.today(),
            amount=Decimal('50000.00'),
            liquidated_amount=Decimal('45000.00'),
            status='ACTIVE',
            created_by=self.user
        )
        
        encumbrance.liquidate(Decimal('5000.00'))
        
        self.assertEqual(encumbrance.status, 'FULLY_LIQUIDATED')
    
    def test_encumbrance_cancel(self):
        """Test cancelling an encumbrance"""
        encumbrance = UnifiedBudgetEncumbrance.objects.create(
            budget=self.budget,
            reference_type='PO',
            reference_id=4,
            reference_number='PO-2026-004',
            encumbrance_date=date.today(),
            amount=Decimal('75000.00'),
            status='ACTIVE',
            created_by=self.user
        )
        
        encumbrance.cancel('Budget cut - order cancelled')
        
        self.assertEqual(encumbrance.status, 'CANCELLED')
        self.assertIn('order cancelled', encumbrance.description)
    
    def test_budget_encumbered_amount_property(self):
        """Test budget's encumbered_amount calculation"""
        UnifiedBudgetEncumbrance.objects.create(
            budget=self.budget,
            reference_type='PO',
            reference_id=10,
            reference_number='PO-001',
            encumbrance_date=date.today(),
            amount=Decimal('200000.00'),
            status='ACTIVE',
            created_by=self.user
        )
        
        UnifiedBudgetEncumbrance.objects.create(
            budget=self.budget,
            reference_type='PO',
            reference_id=11,
            reference_number='PO-002',
            encumbrance_date=date.today(),
            amount=Decimal('150000.00'),
            liquidated_amount=Decimal('50000.00'),
            status='PARTIALLY_LIQUIDATED',
            created_by=self.user
        )
        
        UnifiedBudgetEncumbrance.objects.create(
            budget=self.budget,
            reference_type='CONTRACT',
            reference_id=1,
            reference_number='CON-001',
            encumbrance_date=date.today(),
            amount=Decimal('100000.00'),
            status='CANCELLED',  # Should not count
            created_by=self.user
        )
        
        # Active: 200000, Partially Liquidated: 150000 - 50000 = 100000
        # Cancelled: not counted
        self.assertEqual(self.budget.encumbered_amount, Decimal('300000.00'))


class UnifiedBudgetVarianceTestCase(TestCase):
    """Test cases for budget variance calculations"""
    
    def setUp(self):
        self.fund = Fund.objects.create(code='001', name='Fund', is_active=True)
        self.mda = MDA.objects.create(code='001', name='MoF', mda_type='MINISTRY', is_active=True)
        self.expense_account = Account.objects.create(
            code='50100000', name='Expense', account_type='Expense', is_active=True
        )
        
        self.budget = UnifiedBudget.objects.create(
            budget_code='2026-VAR-001',
            name='Variance Test Budget',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='MONTHLY',
            period_number=1,
            mda=self.mda,
            fund=self.fund,
            account=self.expense_account,
            original_amount=Decimal('1200000.00'),
            status='APPROVED'
        )
    
    def test_variance_calculation_on_save(self):
        """Test that variance is calculated on save"""
        variance = UnifiedBudgetVariance.objects.create(
            budget=self.budget,
            fiscal_year='2026',
            period_type='MONTHLY',
            period_number=1,
            period_budget=Decimal('100000.00'),
            period_actual=Decimal('85000.00'),
            ytd_budget=Decimal('100000.00'),
            ytd_actual=Decimal('85000.00')
        )
        
        self.assertEqual(variance.period_variance, Decimal('15000.00'))
        self.assertEqual(variance.ytd_variance, Decimal('15000.00'))
        self.assertEqual(variance.period_variance_percent, Decimal('15.00'))
        self.assertEqual(variance.ytd_variance_percent, Decimal('15.00'))
    
    def test_variance_with_zero_budget(self):
        """Test variance calculation with zero budget"""
        variance = UnifiedBudgetVariance.objects.create(
            budget=self.budget,
            fiscal_year='2026',
            period_type='MONTHLY',
            period_number=1,
            period_budget=Decimal('0.00'),
            period_actual=Decimal('5000.00'),
            ytd_budget=Decimal('0.00'),
            ytd_actual=Decimal('5000.00')
        )
        
        self.assertEqual(variance.period_variance_percent, Decimal('0.00'))
    
    def test_variance_str_representation(self):
        """Test string representation of variance"""
        variance = UnifiedBudgetVariance(
            budget=self.budget,
            fiscal_year='2026',
            period_type='MONTHLY',
            period_number=3,
            variance_type='PERIOD'
        )
        
        self.assertEqual(str(variance), 'Variance 2026 P3 (PERIOD)')


class UnifiedBudgetAmendmentTestCase(TestCase):
    """Test cases for budget amendments"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser3',
            email='test3@example.com',
            password='testpass123'
        )
        
        self.fund = Fund.objects.create(code='001', name='Fund', is_active=True)
        self.mda = MDA.objects.create(code='001', name='MoF', mda_type='MINISTRY', is_active=True)
        self.expense_account = Account.objects.create(
            code='50100000', name='Expense', account_type='Expense', is_active=True
        )
        
        self.budget = UnifiedBudget.objects.create(
            budget_code='2026-AM-001',
            name='Amendment Test Budget',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='ANNUAL',
            period_number=1,
            mda=self.mda,
            fund=self.fund,
            account=self.expense_account,
            original_amount=Decimal('1000000.00'),
            status='APPROVED'
        )
    
    def test_supplemental_budget_creation(self):
        """Test creating a supplemental budget amendment"""
        amendment = UnifiedBudgetAmendment.objects.create(
            budget=self.budget,
            amendment_number='AMD-2026-001',
            amendment_type='SUPPLEMENTAL',
            original_amount=Decimal('1000000.00'),
            new_amount=Decimal('1200000.00'),
            reason='Additional allocation for capital projects',
            justification='Approved by Ministry Head',
            status='PENDING',
            requested_by=self.user
        )
        
        self.assertEqual(amendment.change_amount, Decimal('200000.00'))
        self.assertEqual(amendment.status, 'PENDING')
    
    def test_transfer_in_creation(self):
        """Test creating a transfer-in amendment"""
        from_budget = UnifiedBudget.objects.create(
            budget_code='2026-AM-FROM',
            name='Source Budget',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='ANNUAL',
            period_number=1,
            mda=self.mda,
            account=self.expense_account,
            original_amount=Decimal('500000.00'),
            status='APPROVED'
        )
        
        amendment = UnifiedBudgetAmendment.objects.create(
            budget=self.budget,
            amendment_number='AMD-2026-002',
            amendment_type='TRANSFER_IN',
            original_amount=Decimal('1000000.00'),
            new_amount=Decimal('1150000.00'),
            from_budget=from_budget,
            reason='Transfer from savings in procurement',
            status='DRAFT',
            requested_by=self.user
        )
        
        self.assertEqual(amendment.change_amount, Decimal('150000.00'))
    
    def test_supplemental_negative_change_validation(self):
        """Test that supplemental cannot have negative change"""
        amendment = UnifiedBudgetAmendment(
            budget=self.budget,
            amendment_number='AMD-2026-003',
            amendment_type='SUPPLEMENTAL',
            original_amount=Decimal('1000000.00'),
            new_amount=Decimal('800000.00'),  # Less than original
            reason='Test'
        )
        
        with self.assertRaises(ValidationError) as ctx:
            amendment.save()
        self.assertIn('must increase the budget', str(ctx.exception))
    
    def test_reduction_negative_change_validation(self):
        """Test that reduction must have negative change"""
        amendment = UnifiedBudgetAmendment(
            budget=self.budget,
            amendment_number='AMD-2026-004',
            amendment_type='REDUCTION',
            original_amount=Decimal('1000000.00'),
            new_amount=Decimal('1200000.00'),  # More than original
            reason='Test'
        )
        
        with self.assertRaises(ValidationError) as ctx:
            amendment.save()
        self.assertIn('must decrease the budget', str(ctx.exception))
    
    def test_amendment_approve(self):
        """Test approving an amendment"""
        amendment = UnifiedBudgetAmendment.objects.create(
            budget=self.budget,
            amendment_number='AMD-2026-005',
            amendment_type='SUPPLEMENTAL',
            original_amount=Decimal('1000000.00'),
            new_amount=Decimal('1100000.00'),
            reason='Additional funding',
            status='PENDING',
            requested_by=self.user
        )
        
        amendment.approve(self.user)
        
        self.assertEqual(amendment.status, 'APPROVED')
        self.assertEqual(amendment.approved_by, self.user)
        self.assertIsNotNone(amendment.approved_date)
        
        # Reload budget to check supplemental amount
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.supplemental_amount, Decimal('100000.00'))
    
    def test_amendment_reject(self):
        """Test rejecting an amendment"""
        amendment = UnifiedBudgetAmendment.objects.create(
            budget=self.budget,
            amendment_number='AMD-2026-006',
            amendment_type='SUPPLEMENTAL',
            original_amount=Decimal('1000000.00'),
            new_amount=Decimal('1100000.00'),
            reason='Additional funding',
            status='PENDING',
            requested_by=self.user
        )
        
        amendment.reject(self.user, 'Insufficient funds available')
        
        self.assertEqual(amendment.status, 'REJECTED')
        self.assertIn('Rejected:', amendment.justification)


class UnifiedBudgetAvailabilityTestCase(TestCase):
    """Test budget availability checks"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser4',
            email='test4@example.com',
            password='testpass123'
        )
        
        self.fund = Fund.objects.create(code='001', name='Fund', is_active=True)
        self.mda = MDA.objects.create(code='001', name='MoF', mda_type='MINISTRY', is_active=True)
        self.expense_account = Account.objects.create(
            code='50100000', name='Expense', account_type='Expense', is_active=True
        )
        
        self.budget = UnifiedBudget.objects.create(
            budget_code='2026-AVAIL-001',
            name='Availability Test Budget',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='ANNUAL',
            period_number=1,
            mda=self.mda,
            fund=self.fund,
            account=self.expense_account,
            original_amount=Decimal('1000000.00'),
            status='APPROVED',
            control_level='HARD_STOP'
        )
    
    def test_available_amount_with_no_encumbrances(self):
        """Test available amount with no commitments"""
        self.assertEqual(self.budget.available_amount, Decimal('1000000.00'))
    
    def test_available_amount_with_encumbrances(self):
        """Test available amount with active encumbrances"""
        UnifiedBudgetEncumbrance.objects.create(
            budget=self.budget,
            reference_type='PO',
            reference_id=1,
            reference_number='PO-001',
            encumbrance_date=date.today(),
            amount=Decimal('300000.00'),
            status='ACTIVE',
            created_by=self.user
        )
        
        self.assertEqual(self.budget.available_amount, Decimal('700000.00'))
    
    def test_available_amount_with_over_expenditure_allowed(self):
        """Test over-expenditure allowance"""
        self.budget.allow_over_expenditure = True
        self.budget.over_expenditure_limit_percent = Decimal('10.00')
        self.budget.save()
        
        available = self.budget.available_amount
        
        # Basic available + 10% overage
        self.assertEqual(available, Decimal('1100000.00'))
    
    def test_check_availability_allowed(self):
        """Test check_availability when funds available"""
        is_allowed, message, available = self.budget.check_availability(
            Decimal('500000.00')
        )
        
        self.assertTrue(is_allowed)
        self.assertIn('Budget available', message)
        self.assertEqual(available, Decimal('1000000.00'))
    
    def test_check_availability_insufficient_hard_stop(self):
        """Test check_availability with hard stop"""
        is_allowed, message, available = self.budget.check_availability(
            Decimal('1500000.00')
        )
        
        self.assertFalse(is_allowed)
        self.assertIn('Insufficient budget', message)
    
    def test_check_availability_warning_level(self):
        """Test check_availability with warning level"""
        self.budget.control_level = 'WARNING'
        self.budget.save()
        
        is_allowed, message, available = self.budget.check_availability(
            Decimal('1500000.00')
        )
        
        self.assertTrue(is_allowed)
        self.assertIn('Warning', message)
    
    def test_check_availability_none_level(self):
        """Test check_availability with no control"""
        self.budget.control_level = 'NONE'
        self.budget.save()
        
        is_allowed, message, available = self.budget.check_availability(
            Decimal('1500000.00')
        )
        
        self.assertTrue(is_allowed)
        self.assertIn('no control enforced', message.lower())


class UnifiedBudgetUtilizationTestCase(TestCase):
    """Test budget utilization calculations"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser5',
            email='test5@example.com',
            password='testpass123'
        )
        
        self.fund = Fund.objects.create(code='001', name='Fund', is_active=True)
        self.mda = MDA.objects.create(code='001', name='MoF', mda_type='MINISTRY', is_active=True)
        self.expense_account = Account.objects.create(
            code='50100000', name='Expense', account_type='Expense', is_active=True
        )
        
        self.budget = UnifiedBudget.objects.create(
            budget_code='2026-UTIL-001',
            name='Utilization Test Budget',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='ANNUAL',
            period_number=1,
            mda=self.mda,
            fund=self.fund,
            account=self.expense_account,
            original_amount=Decimal('1000000.00'),
            status='APPROVED'
        )
    
    def test_utilization_rate_zero(self):
        """Test utilization rate with no activity"""
        self.assertEqual(self.budget.utilization_rate, Decimal('0'))
    
    def test_utilization_rate_with_activity(self):
        """Test utilization rate with encumbrance and expenditure"""
        UnifiedBudgetEncumbrance.objects.create(
            budget=self.budget,
            reference_type='PO',
            reference_id=1,
            encumbrance_date=date.today(),
            amount=Decimal('200000.00'),
            status='ACTIVE',
            created_by=self.user
        )
        
        self.assertEqual(self.budget.utilization_rate, Decimal('20'))
    
    def test_variance_amount(self):
        """Test variance amount calculation"""
        # Mock actual expended
        with patch.object(self.budget, 'actual_expended', new_callable=lambda: Decimal('650000.00')):
            variance = self.budget.variance_amount
            self.assertEqual(variance, Decimal('350000.00'))
    
    def test_variance_percent(self):
        """Test variance percentage calculation"""
        with patch.object(self.budget, 'actual_expended', new_callable=lambda: Decimal('750000.00')):
            variance_percent = self.budget.variance_percent
            self.assertEqual(variance_percent, Decimal('25'))


class UnifiedBudgetQueryTestCase(TestCase):
    """Test budget querying and retrieval"""
    
    def setUp(self):
        self.fund = Fund.objects.create(code='001', name='Fund', is_active=True)
        self.fund2 = Fund.objects.create(code='002', name='Capital Fund', is_active=True)
        self.mda = MDA.objects.create(code='001', name='MoF', mda_type='MINISTRY', is_active=True)
        self.mda2 = MDA.objects.create(code='002', name='MoE', mda_type='MINISTRY', is_active=True)
        self.expense_account = Account.objects.create(
            code='50100000', name='Expense', account_type='Expense', is_active=True
        )
        
        # Create multiple budgets for different MDAs and years
        UnifiedBudget.objects.create(
            budget_code='2025-001',
            name='2025 Budget',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2025',
            period_type='ANNUAL',
            period_number=1,
            mda=self.mda,
            account=self.expense_account,
            original_amount=Decimal('800000.00'),
            status='APPROVED'
        )
        
        UnifiedBudget.objects.create(
            budget_code='2026-001',
            name='2026 Budget MoF',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='ANNUAL',
            period_number=1,
            mda=self.mda,
            account=self.expense_account,
            original_amount=Decimal('1000000.00'),
            status='APPROVED'
        )
        
        UnifiedBudget.objects.create(
            budget_code='2026-002',
            name='2026 Budget MoE',
            budget_type='PUBLIC_SECTOR',
            fiscal_year='2026',
            period_type='ANNUAL',
            period_number=1,
            mda=self.mda2,
            account=self.expense_account,
            original_amount=Decimal('1200000.00'),
            status='APPROVED'
        )
    
    def test_get_budget_for_transaction_exact_match(self):
        """Test finding exact budget match"""
        dimensions = {
            'mda': self.mda.id,
            'fund': None,
            'function': None,
            'program': None,
            'geo': None,
        }
        
        budget = UnifiedBudget.get_budget_for_transaction(
            dimensions=dimensions,
            account=self.expense_account,
            fiscal_year=2026,
            period_type='ANNUAL',
            period_number=1
        )
        
        self.assertIsNotNone(budget)
        self.assertEqual(budget.budget_code, '2026-001')
    
    def test_get_budget_for_transaction_fallback_to_null_mda(self):
        """Test fallback when no exact MDA match"""
        dimensions = {
            'mda': self.mda.id,
            'fund': self.fund2.id,  # Different fund
            'function': None,
            'program': None,
            'geo': None,
        }
        
        # Should fall back to budget with null fund
        budget = UnifiedBudget.get_budget_for_transaction(
            dimensions=dimensions,
            account=self.expense_account,
            fiscal_year=2026,
            period_type='ANNUAL',
            period_number=1
        )
        
        self.assertIsNotNone(budget)
    
    def test_filter_by_fiscal_year(self):
        """Test filtering budgets by fiscal year"""
        budgets_2026 = UnifiedBudget.objects.filter(fiscal_year='2026')
        self.assertEqual(budgets_2026.count(), 2)
    
    def test_filter_by_mda(self):
        """Test filtering budgets by MDA"""
        budgets_mof = UnifiedBudget.objects.filter(mda=self.mda)
        self.assertEqual(budgets_mof.count(), 2)  # 2025 and 2026
    
    def test_filter_by_status(self):
        """Test filtering budgets by status"""
        approved = UnifiedBudget.objects.filter(status='APPROVED')
        self.assertEqual(approved.count(), 3)
