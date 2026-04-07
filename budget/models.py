"""
Unified Budget System
=====================
This module provides a consolidated budget system that works for both:
- Public Sector: Uses MDA (Ministries/Departments/Agencies) for organizational structure
- Private Sector: Uses CostCenter for organizational structure

The system supports:
- Budget allocation and tracking
- Budget variance analysis
- Budget encumbrance (commitments)
- Budget control levels (None/Warning/Hard Stop)
- Multi-dimensional tracking (Fund, Function, Program, Geo, MDA/CostCenter)
"""

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.models import AuditBaseModel
from decimal import Decimal


def get_dimension_fields():
    """Returns the standard dimension fields for budget queries"""
    return ['fund', 'function', 'program', 'geo', 'mda', 'cost_center', 'account']


class UnifiedBudget(AuditBaseModel):
    """
    Unified Budget Model that supports both Public Sector (MDA-based) and Private Sector (CostCenter-based).
    
    For Public Sector:
        - Use MDA, Fund, Function, Program, Geo dimensions
        - Typically annual/quarterly budget cycles
        
    For Private Sector:
        - Use CostCenter, Fund, Function, Program dimensions  
        - Typically monthly budget cycles with cost center allocation
    """
    BUDGET_TYPE_CHOICES = [
        ('PUBLIC_SECTOR', 'Public Sector (MDA-based)'),
        ('PRIVATE_SECTOR', 'Private Sector (CostCenter-based)'),
        ('HYBRID', 'Hybrid (MDA + CostCenter)'),
    ]
    
    CONTROL_LEVEL_CHOICES = [
        ('NONE', 'No Control'),
        ('WARNING', 'Warning Only'),
        ('HARD_STOP', 'Hard Stop'),
    ]
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('CLOSED', 'Closed'),
        ('ARCHIVED', 'Archived'),
    ]
    
    # Identification
    budget_code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    
    # Budget Type
    budget_type = models.CharField(max_length=20, choices=BUDGET_TYPE_CHOICES, default='PUBLIC_SECTOR')
    
    # Period
    fiscal_year = models.CharField(max_length=4, db_index=True)
    period_type = models.CharField(max_length=20, choices=[
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
        ('ANNUAL', 'Annual'),
    ], default='ANNUAL')
    period_number = models.IntegerField(default=1, help_text="1-12 for monthly, 1-4 for quarterly, 1 for annual")
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    # Public Sector Dimensions
    mda = models.ForeignKey(
        'accounting.MDA', on_delete=models.PROTECT, 
        null=True, blank=True, related_name='unified_budgets'
    )
    fund = models.ForeignKey(
        'accounting.Fund', on_delete=models.PROTECT,
        null=True, blank=True, related_name='unified_budgets'
    )
    function = models.ForeignKey(
        'accounting.Function', on_delete=models.PROTECT,
        null=True, blank=True, related_name='unified_budgets'
    )
    program = models.ForeignKey(
        'accounting.Program', on_delete=models.PROTECT,
        null=True, blank=True, related_name='unified_budgets'
    )
    geo = models.ForeignKey(
        'accounting.Geo', on_delete=models.PROTECT,
        null=True, blank=True, related_name='unified_budgets'
    )
    
    # Private Sector Dimensions
    cost_center = models.ForeignKey(
        'accounting.CostCenter', on_delete=models.PROTECT,
        null=True, blank=True, related_name='unified_budgets'
    )
    
    # Account
    account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT,
        null=True, blank=True, related_name='unified_budgets'
    )
    
    # Amounts
    original_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    revised_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    supplemental_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    
    # Control
    control_level = models.CharField(max_length=10, choices=CONTROL_LEVEL_CHOICES, default='HARD_STOP')
    enable_encumbrance = models.BooleanField(default=True)
    allow_over_expenditure = models.BooleanField(default=False)
    over_expenditure_limit_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Tracking
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='budgets_approved'
    )
    approved_date = models.DateTimeField(null=True, blank=True)
    closed_date = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'unified_budget'
        ordering = ['-fiscal_year', 'period_type', 'period_number', 'budget_code']
        unique_together = [
            'fiscal_year', 'period_type', 'period_number', 'mda', 'cost_center', 
            'fund', 'function', 'program', 'geo', 'account'
        ]
        indexes = [
            models.Index(fields=['fiscal_year', 'period_type', 'status']),
            models.Index(fields=['mda', 'fiscal_year']),
            models.Index(fields=['cost_center', 'fiscal_year']),
            models.Index(fields=['account', 'fiscal_year']),
        ]
        permissions = [
            ('approve_unifiedbudget', 'Can approve unified budgets'),
            ('close_unifiedbudget', 'Can close unified budgets'),
        ]

    def __str__(self):
        return f"{self.budget_code} - {self.name}"

    @property
    def allocated_amount(self):
        """Total allocated amount (original + supplemental)"""
        return self.revised_amount or self.original_amount

    @property
    def encumbered_amount(self):
        """Total encumbered (committed but not yet expensed)"""
        from django.db.models import Sum
        total = self.encumbrances.filter(
            status__in=['ACTIVE', 'PARTIALLY_LIQUIDATED']
        ).aggregate(
            total=Sum(models.F('amount') - models.F('liquidated_amount'))
        )['total']
        return total or Decimal('0')

    @property
    def actual_expended(self):
        """Actual amount expensed against this budget"""
        from django.db.models import Sum
        from accounting.models import GLBalance
        
        query = GLBalance.objects.filter(
            account=self.account,
            fiscal_year=int(self.fiscal_year),
        )
        
        if self.mda and self.budget_type in ('PUBLIC_SECTOR', 'HYBRID'):
            # Would need MDA dimension in GLBalance - placeholder
            pass
        if self.fund:
            query = query.filter(fund=self.fund)
        if self.function:
            query = query.filter(function=self.function)
        if self.program:
            query = query.filter(program=self.program)
        if self.geo:
            query = query.filter(geo=self.geo)
            
        total = query.aggregate(total=Sum('debit_balance'))['total']
        return total or Decimal('0')

    @property
    def available_amount(self):
        """Amount available for new commitments"""
        allocated = self.allocated_amount
        encumbered = self.encumbered_amount
        expended = self.actual_expended
        
        available = allocated - encumbered - expended
        
        # Allow over-expenditure if configured
        if self.allow_over_expenditure and self.over_expenditure_limit_percent > 0:
            max_over = allocated * (self.over_expenditure_limit_percent / 100)
            available += max_over
            
        return max(Decimal('0'), available)

    @property
    def utilization_rate(self):
        """Percentage of budget utilized"""
        allocated = self.allocated_amount
        if allocated <= 0:
            return Decimal('0')
        utilized = self.encumbered_amount + self.actual_expended
        return (utilized / allocated) * 100

    @property
    def variance_amount(self):
        """Budget vs Actual variance"""
        return self.allocated_amount - self.actual_expended

    @property
    def variance_percent(self):
        """Budget vs Actual variance percentage"""
        allocated = self.allocated_amount
        if allocated <= 0:
            return Decimal('0')
        return (self.variance_amount / allocated) * 100

    def clean(self):
        """Validate budget based on type"""
        if self.budget_type == 'PUBLIC_SECTOR' and not self.mda:
            raise ValidationError("Public sector budgets require an MDA")
        if self.budget_type == 'PRIVATE_SECTOR' and not self.cost_center:
            raise ValidationError("Private sector budgets require a Cost Center")
        if self.period_type == 'MONTHLY' and (self.period_number < 1 or self.period_number > 12):
            raise ValidationError("Monthly period must be 1-12")
        if self.period_type == 'QUARTERLY' and (self.period_number < 1 or self.period_number > 4):
            raise ValidationError("Quarterly period must be 1-4")

    def check_availability(self, amount, transaction_type='GENERAL'):
        """
        Check if amount is available in budget.
        Returns (is_allowed: bool, message: str, available: Decimal)
        """
        available = self.available_amount
        
        if available >= amount:
            return True, "Budget available", available
        
        if self.control_level == 'NONE':
            return True, f"Warning: Only {available} available, but no control enforced", available
        elif self.control_level == 'WARNING':
            return True, f"Warning: Only {available} available", available
        else:
            return False, f"Insufficient budget. Available: {available}, Requested: {amount}", available

    def get_dimension_key(self):
        """Returns a tuple key for dimension matching"""
        return (
            self.fund_id, self.function_id, self.program_id, 
            self.geo_id, self.mda_id, self.cost_center_id, self.account_id
        )

    @classmethod
    def get_budget_for_transaction(cls, dimensions, account, fiscal_year, period_type, period_number):
        """
        Find the appropriate budget for a transaction.
        dimensions: dict with fund, function, program, geo, mda, cost_center
        """
        from accounting.models import BudgetPeriod
        
        # Try exact match first
        budget = cls.objects.filter(
            fiscal_year=str(fiscal_year),
            period_type=period_type,
            period_number=period_number,
            status='APPROVED'
        )
        
        # Match on available dimensions
        if dimensions.get('mda'):
            budget = budget.filter(
                models.Q(mda=dimensions['mda']) | models.Q(mda__isnull=True)
            )
        if dimensions.get('cost_center'):
            budget = budget.filter(
                models.Q(cost_center=dimensions['cost_center']) | models.Q(cost_center__isnull=True)
            )
        if dimensions.get('fund'):
            budget = budget.filter(
                models.Q(fund=dimensions['fund']) | models.Q(fund__isnull=True)
            )
        if dimensions.get('function'):
            budget = budget.filter(
                models.Q(function=dimensions['function']) | models.Q(function__isnull=True)
            )
        if dimensions.get('program'):
            budget = budget.filter(
                models.Q(program=dimensions['program']) | models.Q(program__isnull=True)
            )
        if dimensions.get('geo'):
            budget = budget.filter(
                models.Q(geo=dimensions['geo']) | models.Q(geo__isnull=True)
            )
        if account:
            budget = budget.filter(
                models.Q(account=account) | models.Q(account__isnull=True)
            )
        
        return budget.first()


class UnifiedBudgetEncumbrance(models.Model):
    """
    Tracks commitments/reservations against a budget.
    Used for purchase orders, contracts, and other commitments.
    """
    REFERENCE_TYPE_CHOICES = [
        ('PR', 'Purchase Requisition'),
        ('PO', 'Purchase Order'),
        ('CONTRACT', 'Contract'),
        ('WORK_ORDER', 'Work Order'),
        ('GENERAL', 'General Commitment'),
    ]
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active (Committed)'),
        ('PARTIALLY_LIQUIDATED', 'Partially Liquidated'),
        ('FULLY_LIQUIDATED', 'Fully Liquidated'),
        ('CANCELLED', 'Cancelled'),
        ('REVERSED', 'Reversed'),
    ]
    
    budget = models.ForeignKey(
        UnifiedBudget, on_delete=models.CASCADE, 
        related_name='encumbrances', null=True, blank=True
    )
    reference_type = models.CharField(max_length=20, choices=REFERENCE_TYPE_CHOICES)
    reference_id = models.IntegerField()
    reference_number = models.CharField(max_length=50, blank=True, default='')
    
    encumbrance_date = models.DateField()
    amount = models.DecimalField(max_digits=19, decimal_places=2)
    liquidated_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='DRAFT')
    description = models.TextField(blank=True, default='')
    
    # For multi-line encumbrances
    is_aggregate = models.BooleanField(default=False)
    parent_encumbrance = models.ForeignKey(
        'self', on_delete=models.CASCADE, 
        related_name='line_items', null=True, blank=True
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='encumbrances_created'
    )
    
    class Meta:
        db_table = 'unified_budget_encumbrance'
        ordering = ['-encumbrance_date']
        unique_together = ['budget', 'reference_type', 'reference_id']
        indexes = [
            models.Index(fields=['reference_type', 'reference_id']),
            models.Index(fields=['status', 'encumbrance_date']),
        ]

    def __str__(self):
        return f"{self.reference_type} #{self.reference_id} - {self.amount}"

    def save(self, *args, **kwargs):
        self.remaining_amount = self.amount - self.liquidated_amount
        
        if self.status == 'ACTIVE' and self.remaining_amount <= 0:
            self.status = 'FULLY_LIQUIDATED'
        elif self.status == 'ACTIVE' and self.liquidated_amount > 0:
            self.status = 'PARTIALLY_LIQUIDATED'
            
        super().save(*args, **kwargs)

    def liquidate(self, amount, reference_id=None):
        """Record liquidation (expense) against this encumbrance"""
        self.liquidated_amount += amount
        self.save()
        
        # Update budget's expended amount
        if self.budget:
            # Expended is calculated dynamically, no need to update
            pass

    def cancel(self, reason=''):
        """Cancel this encumbrance"""
        self.status = 'CANCELLED'
        self.description = f"{self.description}\nCancelled: {reason}".strip()
        self.save()


class UnifiedBudgetVariance(models.Model):
    """
    Tracks budget variance analysis - compares budgeted vs actual amounts.
    Can be calculated periodically (monthly/quarterly) or YTD.
    """
    VARIANCE_TYPE_CHOICES = [
        ('PERIOD', 'Period (Monthly/Quarterly)'),
        ('YEAR_TO_DATE', 'Year to Date'),
        ('FORECAST', 'Forecast'),
    ]
    
    budget = models.ForeignKey(
        UnifiedBudget, on_delete=models.CASCADE,
        related_name='variances', null=True, blank=True
    )
    
    fiscal_year = models.CharField(max_length=4)
    period_type = models.CharField(max_length=20)
    period_number = models.IntegerField()
    variance_type = models.CharField(max_length=20, choices=VARIANCE_TYPE_CHOICES, default='PERIOD')
    
    # Budget figures
    period_budget = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    ytd_budget = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    
    # Actual figures  
    period_actual = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    ytd_actual = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    
    # Variance calculations
    period_variance = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    ytd_variance = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    
    # Variance percentage
    period_variance_percent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    ytd_variance_percent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Additional metrics
    encumbered_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    committed_amount = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'unified_budget_variance'
        unique_together = ['budget', 'fiscal_year', 'period_type', 'period_number', 'variance_type']
        ordering = ['-fiscal_year', '-period_number']

    def __str__(self):
        return f"Variance {self.fiscal_year} P{self.period_number} ({self.variance_type})"

    def save(self, *args, **kwargs):
        # Calculate variances
        self.period_variance = self.period_budget - self.period_actual
        self.ytd_variance = self.ytd_budget - self.ytd_actual

        if self.period_budget > 0:
            self.period_variance_percent = (self.period_variance / self.period_budget) * 100
        else:
            self.period_variance_percent = Decimal('0')
        if self.ytd_budget > 0:
            self.ytd_variance_percent = (self.ytd_variance / self.ytd_budget) * 100
        else:
            self.ytd_variance_percent = Decimal('0')

        super().save(*args, **kwargs)

    @classmethod
    def calculate_for_period(cls, budget, period_number, period_type='MONTHLY'):
        """Calculate and create variance record for a given period."""
        if budget is None:
            raise ValueError("budget is required for variance calculation")

        from accounting.models import GLBalance
        from django.db.models import Sum

        allocated = budget.allocated_amount or Decimal('0')

        # Validate period_number bounds
        max_periods = {'MONTHLY': 12, 'QUARTERLY': 4}
        limit = max_periods.get(period_type)
        if limit and not (1 <= period_number <= limit):
            raise ValueError(
                f"period_number {period_number} out of range for {period_type} (expected 1-{limit})"
            )

        # Determine which GL balance column to aggregate based on account type.
        # Expense/Asset accounts are debit-normal; Income/Liability/Equity are credit-normal.
        account_type = getattr(budget.account, 'account_type', 'Expense')
        if account_type in ('Income', 'Liability', 'Equity'):
            agg_field = 'credit_balance'
        else:
            agg_field = 'debit_balance'

        # Build dimension filters
        dim_filters = {}
        for dim in ('fund', 'function', 'program', 'geo'):
            val = getattr(budget, dim, None)
            if val:
                dim_filters[dim] = val

        # Get actuals from GL for the period
        query = GLBalance.objects.filter(
            account=budget.account,
            fiscal_year=int(budget.fiscal_year),
            period=period_number,
            **dim_filters,
        )
        period_actual = query.aggregate(total=Sum(agg_field))['total'] or Decimal('0')

        # Calculate YTD actuals
        ytd_query = GLBalance.objects.filter(
            account=budget.account,
            fiscal_year=int(budget.fiscal_year),
            period__lte=period_number,
            **dim_filters,
        )
        ytd_actual = ytd_query.aggregate(total=Sum(agg_field))['total'] or Decimal('0')

        # Calculate YTD budget (linear proration)
        if period_type == 'MONTHLY':
            ytd_budget = allocated / 12 * period_number
        elif period_type == 'QUARTERLY':
            ytd_budget = allocated / 4 * period_number
        else:
            ytd_budget = allocated

        # Get encumbered
        encumbered = budget.encumbered_amount or Decimal('0')

        # Period budget
        if period_type == 'ANNUAL':
            period_budget = allocated
        elif period_type == 'MONTHLY':
            period_budget = allocated / 12
        else:
            period_budget = allocated / 4

        # Create or update variance
        variance, created = cls.objects.update_or_create(
            budget=budget,
            fiscal_year=budget.fiscal_year,
            period_type=period_type,
            period_number=period_number,
            variance_type='PERIOD',
            defaults={
                'period_budget': period_budget,
                'period_actual': period_actual,
                'ytd_budget': ytd_budget,
                'ytd_actual': ytd_actual,
                'encumbered_amount': encumbered,
            }
        )

        return variance


class UnifiedBudgetAmendment(AuditBaseModel):
    """
    Tracks budget amendments (supplemental, transfers, virements).
    """
    AMENDMENT_TYPE_CHOICES = [
        ('SUPPLEMENTAL', 'Supplemental Budget'),
        ('REDUCTION', 'Budget Reduction'),
        ('TRANSFER_IN', 'Transfer In (Virement)'),
        ('TRANSFER_OUT', 'Transfer Out (Virement)'),
        ('REVISION', 'Budget Revision'),
    ]
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    budget = models.ForeignKey(
        UnifiedBudget, on_delete=models.CASCADE,
        related_name='amendments', null=True, blank=True
    )
    
    amendment_number = models.CharField(max_length=50, unique=True)
    amendment_type = models.CharField(max_length=20, choices=AMENDMENT_TYPE_CHOICES)
    
    original_amount = models.DecimalField(max_digits=19, decimal_places=2)
    new_amount = models.DecimalField(max_digits=19, decimal_places=2)
    change_amount = models.DecimalField(max_digits=19, decimal_places=2)
    
    # For transfers
    from_budget = models.ForeignKey(
        UnifiedBudget, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='transfers_out'
    )
    to_budget = models.ForeignKey(
        UnifiedBudget, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='transfers_in'
    )
    
    reason = models.TextField()
    justification = models.TextField(blank=True, default='')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='budget_amendments_requested'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='budget_amendments_approved'
    )
    approved_date = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'unified_budget_amendment'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.amendment_number} - {self.amendment_type}"

    def save(self, *args, **kwargs):
        self.change_amount = self.new_amount - self.original_amount
        
        if self.amendment_type in ('TRANSFER_IN', 'SUPPLEMENTAL', 'REVISION'):
            if self.change_amount < 0:
                raise ValidationError("Transfer in/revision must increase the budget")
        elif self.amendment_type in ('TRANSFER_OUT', 'REDUCTION'):
            if self.change_amount > 0:
                raise ValidationError("Transfer out/reduction must decrease the budget")
                
        super().save(*args, **kwargs)

    def approve(self, user):
        """Approve the amendment and update budget atomically."""
        from django.db import transaction as db_transaction

        with db_transaction.atomic():
            self.status = 'APPROVED'
            self.approved_by = user
            self.approved_date = timezone.now()
            self.save()

            # Update budget amount with row lock to prevent race conditions
            if self.budget:
                budget = UnifiedBudget.objects.select_for_update().get(pk=self.budget.pk)
                if self.amendment_type in ('SUPPLEMENTAL', 'TRANSFER_IN', 'REVISION'):
                    budget.supplemental_amount += self.change_amount
                elif self.amendment_type in ('TRANSFER_OUT', 'REDUCTION'):
                    budget.supplemental_amount += self.change_amount  # Negative value
                budget.save()

    def reject(self, user, reason=''):
        """Reject the amendment"""
        self.status = 'REJECTED'
        self.justification = f"Rejected: {reason}"
        self.save()
