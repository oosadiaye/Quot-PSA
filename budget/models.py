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
        """Actual amount expensed against this budget.

        S3-05 — MDA dimension now filters the GLBalance query. Previously
        this was a TODO placeholder and `actual_expended` summed across
        ALL MDAs sharing the same expense account, breaking every
        budget-execution report in a multi-MDA deployment.
        """
        from django.db.models import Sum
        from accounting.models import GLBalance

        query = GLBalance.objects.filter(
            account=self.account,
            fiscal_year=int(self.fiscal_year),
        )

        # S3-05 — MDA filter (was placeholder). Only apply when the
        # budget actually targets an MDA; BUDGETS without an MDA
        # (state-wide funds) remain unfiltered on that dimension.
        if self.mda and self.budget_type in ('PUBLIC_SECTOR', 'HYBRID'):
            query = query.filter(mda=self.mda)

        # Budget control: MDA + Account + Fund only
        # Function, Programme, Geo are reporting dimensions — not budget filters
        if self.fund:
            query = query.filter(fund=self.fund)

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

        Budget control uses 3 pillars only:
          MDA (Administrative) + Account (Economic Code) + Fund
        Function, Programme, Geo are for reporting — not budget gating.
        """
        budget = cls.objects.filter(
            fiscal_year=str(fiscal_year),
            period_type=period_type,
            period_number=period_number,
            status='APPROVED'
        )

        # 3 budget control dimensions only
        if dimensions.get('mda'):
            budget = budget.filter(
                models.Q(mda=dimensions['mda']) | models.Q(mda__isnull=True)
            )
        if dimensions.get('fund'):
            budget = budget.filter(
                models.Q(fund=dimensions['fund']) | models.Q(fund__isnull=True)
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


# =============================================================================
# APPROPRIATION & WARRANT — Government Budget Authority
# =============================================================================

class Appropriation(AuditBaseModel):
    """
    Legislative budget appropriation — the legal authority to spend.
    No expenditure may exceed its appropriation without Supplementary approval.

    Every state government budget is enacted by the State House of Assembly
    through an Appropriation Act. This model tracks the approved amounts
    per NCoA segment combination.
    """
    APPROPRIATION_TYPE_CHOICES = [
        ('ORIGINAL',       'Original Appropriation'),
        ('SUPPLEMENTARY',  'Supplementary Appropriation'),
        ('VIREMENT',       'Virement (Transfer)'),
    ]
    STATUS_CHOICES = [
        ('DRAFT',     'Draft'),
        ('SUBMITTED', 'Submitted to Legislature'),
        ('APPROVED',  'Approved by Legislature'),
        ('ENACTED',   'Enacted into Law'),
        ('ACTIVE',    'Active / Current'),
        ('CLOSED',    'Closed'),
    ]

    fiscal_year      = models.ForeignKey(
        'accounting.FiscalYear', on_delete=models.PROTECT,
        related_name='appropriations',
    )
    administrative   = models.ForeignKey(
        'accounting.AdministrativeSegment', on_delete=models.PROTECT,
        related_name='appropriations',
    )
    economic         = models.ForeignKey(
        'accounting.EconomicSegment', on_delete=models.PROTECT,
        related_name='appropriations',
    )
    functional       = models.ForeignKey(
        'accounting.FunctionalSegment', on_delete=models.PROTECT,
        related_name='appropriations',
    )
    programme        = models.ForeignKey(
        'accounting.ProgrammeSegment', on_delete=models.PROTECT,
        related_name='appropriations',
    )
    fund             = models.ForeignKey(
        'accounting.FundSegment', on_delete=models.PROTECT,
        related_name='appropriations',
    )
    # S19 — Geographic dimension on appropriations. Nigerian
    # Appropriation Acts do not mandate a geographic slice at
    # enactment; this field is therefore NULLABLE so pre-S19 rows
    # remain valid. When populated it enables the Geographic
    # Distribution Performance Report to report real (non pro-rata)
    # budget-vs-actual by LGA / zone.
    geographic       = models.ForeignKey(
        'accounting.GeographicSegment', on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='appropriations',
        help_text='Optional geographic dimension (LGA / zone) '
                  'for statistical and dimensional reporting. '
                  'Not required for legal enactment.',
    )
    amount_approved  = models.DecimalField(max_digits=20, decimal_places=2)
    # S2-04 — original (as-enacted) budget snapshot, captured at the
    # moment the appropriation is activated. ``amount_approved`` evolves
    # via amendments/virements (becoming the "Final Budget" in IPSAS 24
    # terminology); ``original_amount`` stays immutable so auditors can
    # see both original and final figures side-by-side.
    original_amount  = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True,
        help_text='Original (as-enacted) appropriation; immutable after activation.',
    )
    # S2-04 — free-text explanation of budget vs actual variance,
    # required by IPSAS 24 when the variance is material. Presented in
    # the budget_vs_actual report next to the numeric variance.
    variance_explanation = models.TextField(
        blank=True, default='',
        help_text='IPSAS 24 variance narrative (for the final FS notes).',
    )
    appropriation_type = models.CharField(
        max_length=20, choices=APPROPRIATION_TYPE_CHOICES, default='ORIGINAL',
    )
    status           = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='DRAFT',
    )

    # Monthly budget spread — JSON with keys "1" through "12" for each month
    # If null, the annual amount is divided equally across 12 months
    # Example: {"1": 50000, "2": 50000, ..., "12": 100000}
    monthly_spread   = models.JSONField(
        null=True, blank=True, default=None,
        help_text='Monthly budget allocation {1: Jan, 2: Feb, ...12: Dec}. '
                  'Null = equal monthly spread.',
    )

    law_reference    = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Appropriation Act citation",
    )
    enactment_date   = models.DateField(null=True, blank=True)
    description      = models.CharField(max_length=500, blank=True, default='')
    notes            = models.TextField(blank=True, default='')

    # P6-T2 — denormalised totals. Maintained by
    # accounting.services.appropriation_totals.refresh_totals() on commit /
    # invoice / payment events, and by the ``resync_appropriation_totals``
    # management command for full rebuilds. NULL => fall back to live aggregate.
    cached_total_committed = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True,
        help_text='Denormalised sum of open commitments. '
                  'Maintained by accounting.services.appropriation_totals.',
    )
    cached_total_expended = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True,
        help_text='Denormalised sum of CLOSED commitments + direct AP. '
                  'Maintained by accounting.services.appropriation_totals.',
    )
    cached_totals_refreshed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['fiscal_year', 'administrative', 'economic']
        verbose_name = 'Appropriation'
        verbose_name_plural = 'Appropriations'
        indexes = [
            models.Index(fields=['fiscal_year', 'status']),
            models.Index(fields=['administrative', 'economic', 'fiscal_year']),
        ]

    def __str__(self):
        return (
            f"APP/{self.fiscal_year}/{self.administrative.code}/"
            f"{self.economic.code} - NGN {self.amount_approved:,.2f}"
        )

    @property
    def total_warrants_released(self):
        from django.db.models import Sum
        return self.warrants.filter(status='RELEASED').aggregate(
            total=Sum('amount_released'),
        )['total'] or Decimal('0')

    @property
    def total_committed(self):
        """Sum of all *open* commitments (POs) against this appropriation.

        Includes ACTIVE (PO approved, goods not yet received) and INVOICED
        (goods received, vendor invoice pending). Excludes CLOSED — once
        the vendor invoice is posted the commitment is replaced by the
        actual expense booked in the GL.

        P6-T2: prefer the denormalised column; live-aggregate only when
        the cache is empty (pre-backfill / freshly created rows).
        """
        if self.cached_total_committed is not None:
            return self.cached_total_committed
        from django.db.models import Sum
        return self.commitments.filter(
            status__in=['ACTIVE', 'INVOICED'],
        ).aggregate(total=Sum('committed_amount'))['total'] or Decimal('0')

    @property
    def total_active_commitments(self):
        """Sub-slice of total_committed: PO approved, goods not yet received."""
        from django.db.models import Sum
        return self.commitments.filter(status='ACTIVE').aggregate(
            total=Sum('committed_amount'),
        )['total'] or Decimal('0')

    @property
    def total_invoiced_commitments(self):
        """Sub-slice of total_committed: goods received, awaiting vendor invoice."""
        from django.db.models import Sum
        return self.commitments.filter(status='INVOICED').aggregate(
            total=Sum('committed_amount'),
        )['total'] or Decimal('0')

    @property
    def total_closed_commitments(self):
        """Lifetime invoice-verified value (commitments that have been replaced
        by actual GL expense). Useful for execution-rate audits — sums the
        original committed amounts of all CLOSED links.
        """
        from django.db.models import Sum
        return self.commitments.filter(status='CLOSED').aggregate(
            total=Sum('committed_amount'),
        )['total'] or Decimal('0')

    @property
    def total_expended(self):
        """IPSAS expenditure recognised against this appropriation.

        In public-sector accounting, *expenditure* is recognised at the
        moment the vendor invoice is verified — that's when the GL
        journal posts ``DR Expense / CR AP`` and the spend leaves the
        commitment table. Cash payment that follows is a separate
        treasury event, not an additional expenditure.

        Calculation (three sources, de-duplicated):
        1. **CLOSED commitments** — POs whose vendor invoice was posted
           via the 3-way matching flow (ProcurementBudgetLink.status =
           'CLOSED'). The canonical expenditure metric for procurement.
        2. **Direct (no-PO) AP invoices** — Vendor Invoices posted via
           the standalone ``post_invoice`` flow (e.g. utility bills,
           rent, recurring services) where there's no PO upstream. Their
           expense lands at VI posting time, so we sum their
           ``total_amount`` here. Filtered by ``purchase_order__isnull``
           to avoid double-counting PO-backed invoices (already in 1).
        3. **Direct PAID payment vouchers** — non-PO PVs paid straight
           from voucher. Filtered by ``source_document=''`` to avoid
           double-counting PO-backed PVs (already in 1).

        For the cash-out metric (what actually left the bank), see
        ``total_cash_paid``.

        P6-T2: prefer the denormalised column; fall through to the full
        multi-source live computation only when the cache is empty.
        """
        if self.cached_total_expended is not None:
            return self.cached_total_expended
        from django.db.models import Sum

        # 1. PO-backed commitments that have been invoice-verified.
        closed_commitments = self.commitments.filter(status='CLOSED').aggregate(
            total=Sum('committed_amount'),
        )['total'] or Decimal('0')

        # 2. Direct AP invoices (no PO) posted against this appropriation.
        #    Match via the legacy_* bridges so VI's flat MDA/Account/Fund
        #    FKs join correctly to the NCoA-segmented appropriation.
        #
        #    Economic-code parent-chain walk: a VI coded to a LEAF
        #    (e.g. 21100100 Salaries) rolls up to a PARENT appropriation
        #    (e.g. 21000000 Personnel Costs or 20000000 Expenditure).
        #    Mirrors the create_commitment_for_po() lookup pattern so
        #    budget-control dimensions stay consistent across procurement
        #    and direct-voucher flows.
        direct_ap_invoices = Decimal('0')
        admin_legacy = getattr(self.administrative, 'legacy_mda', None) if self.administrative_id else None
        fund_legacy  = getattr(self.fund,           'legacy_fund', None) if self.fund_id else None
        if admin_legacy and fund_legacy and self.economic_id:
            from accounting.models.receivables import VendorInvoice
            from accounting.models.ncoa import EconomicSegment as _EconSeg
            # Collect every legacy Account whose NCoA economic segment is
            # this appropriation's economic OR any descendant of it. That
            # way a child-coded VI is captured by the parent appropriation.
            descendant_econ_segs = [self.economic]
            # BFS down the parent chain
            frontier = [self.economic]
            while frontier:
                children = list(_EconSeg.objects.filter(parent__in=frontier))
                descendant_econ_segs.extend(children)
                frontier = children
            # Gather legacy_account FKs for all descendant economic segments.
            legacy_accounts = [
                seg.legacy_account_id for seg in descendant_econ_segs
                if seg.legacy_account_id
            ]
            if legacy_accounts:
                # S1-12 — restrict direct AP invoices to the fiscal year
                # that covers THIS appropriation. Without the year filter,
                # a prior-year direct utility invoice leaks into the next
                # year's appropriation and permanently distorts
                # ``available_balance``.
                fy = getattr(self, 'fiscal_year', None)
                fy_start = getattr(fy, 'start_date', None)
                fy_end = getattr(fy, 'end_date', None)

                direct_q = VendorInvoice.objects.filter(
                    status='Posted',
                    purchase_order__isnull=True,
                    mda=admin_legacy,
                    account_id__in=legacy_accounts,
                    fund=fund_legacy,
                )
                if fy_start and fy_end:
                    direct_q = direct_q.filter(
                        invoice_date__gte=fy_start,
                        invoice_date__lte=fy_end,
                    )
                elif fy and hasattr(fy, 'year') and fy.year:
                    direct_q = direct_q.filter(invoice_date__year=fy.year)
                direct_ap_invoices = (
                    direct_q.aggregate(total=Sum('total_amount'))['total']
                    or Decimal('0')
                )

        # 3. Direct PVs (no PO upstream) paid in cash.
        direct_pv_paid = self.payment_vouchers.filter(
            status='PAID', source_document='',
        ).aggregate(total=Sum('net_amount'))['total'] or Decimal('0')

        return closed_commitments + direct_ap_invoices + direct_pv_paid

    @property
    def total_cash_paid(self):
        """Cash actually disbursed against this appropriation.

        Distinct from ``total_expended``. Sums ALL paid Payment Vouchers
        (both PO-backed and direct). Useful for treasury reporting where
        the question is "how much money has actually left this fund".
        """
        from django.db.models import Sum
        return self.payment_vouchers.filter(
            status='PAID',
        ).aggregate(total=Sum('net_amount'))['total'] or Decimal('0')

    @property
    def available_balance(self):
        """Appropriation remaining for new commitments.

        = approved − open commitments (ACTIVE+INVOICED) − recognised expenditure.

        ``total_committed`` covers POs not yet invoice-verified (ACTIVE +
        INVOICED). ``total_expended`` covers POs whose invoice has been
        verified (CLOSED commitments) plus any direct non-PO payment
        vouchers. Together they describe the appropriation's full
        consumption picture; ``available_balance`` is what's left to
        commit or spend.
        """
        return self.amount_approved - self.total_committed - self.total_expended

    @property
    def unwarranted_balance(self):
        """Approved but not yet cash-released."""
        return self.amount_approved - self.total_warrants_released

    @property
    def execution_rate(self):
        """Budget execution percentage."""
        if self.amount_approved <= 0:
            return Decimal('0')
        return (self.total_expended / self.amount_approved) * 100

    def get_monthly_amount(self, month: int) -> Decimal:
        """Get budget amount for a specific month (1-12).

        If monthly_spread is set, returns the amount for that month.
        Otherwise, divides the annual amount equally across 12 months.
        """
        if self.monthly_spread and str(month) in self.monthly_spread:
            return Decimal(str(self.monthly_spread[str(month)]))
        return (self.amount_approved / Decimal('12')).quantize(Decimal('0.01'))


class Warrant(AuditBaseModel):
    """
    Quarterly cash release (warrant) against approved appropriation.
    Money cannot be spent until a warrant is issued — the cash release authority.

    The Accountant General issues warrants quarterly based on:
    - Cash availability in TSA
    - Revenue performance
    - Expenditure priorities

    Warrant amount <= Appropriation amount (cumulative across quarters).
    """
    STATUS_CHOICES = [
        ('PENDING',   'Pending Release'),
        ('RELEASED',  'Released'),
        ('SUSPENDED', 'Suspended'),
        ('EXHAUSTED', 'Exhausted'),
    ]

    appropriation     = models.ForeignKey(
        Appropriation, on_delete=models.PROTECT, related_name='warrants',
    )
    quarter           = models.IntegerField(
        choices=[(1, 'Q1'), (2, 'Q2'), (3, 'Q3'), (4, 'Q4')],
    )
    amount_released   = models.DecimalField(max_digits=20, decimal_places=2)
    release_date      = models.DateField()
    authority_reference = models.CharField(
        max_length=100,
        help_text="AGF warrant letter/reference number",
    )
    issued_by         = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='warrants_issued',
    )
    status            = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='PENDING',
    )
    attachment        = models.FileField(
        upload_to='warrants/aie_letters/%Y/',
        null=True, blank=True,
        help_text='Scanned AIE letter from Budget Office (PDF/image)',
    )
    notes             = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['appropriation', 'quarter']
        verbose_name = 'Warrant (Cash Release)'
        verbose_name_plural = 'Warrants (Cash Releases)'
        unique_together = ['appropriation', 'quarter']

    def __str__(self):
        return (
            f"WNT/{self.appropriation.fiscal_year}/Q{self.quarter} "
            f"- NGN {self.amount_released:,.2f}"
        )

    def clean(self):
        super().clean()
        # Warrant cumulative total cannot exceed appropriation
        existing = Warrant.objects.filter(
            appropriation=self.appropriation,
            status__in=['PENDING', 'RELEASED'],
        ).exclude(pk=self.pk)
        from django.db.models import Sum
        total_released = existing.aggregate(
            total=Sum('amount_released'),
        )['total'] or Decimal('0')
        if total_released + self.amount_released > self.appropriation.amount_approved:
            raise ValidationError(
                f"Total warrants (NGN {total_released + self.amount_released:,.2f}) "
                f"exceed appropriation (NGN {self.appropriation.amount_approved:,.2f})."
            )


class RevenueBudget(AuditBaseModel):
    """
    Revenue budget target — statistical (non-enforced).

    Unlike Appropriation (which enforces hard stops on expenditure), revenue
    budgets are **targets only**. Actual collections can exceed the target —
    that's a good thing. This model exists purely for performance reporting:
    comparing actual IGR/FAAC collections against estimates.

    No warrant required. No hard stop. Just tracking.
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active'),
        ('CLOSED', 'Closed'),
    ]

    fiscal_year = models.ForeignKey(
        'accounting.FiscalYear', on_delete=models.PROTECT,
        related_name='revenue_budgets',
    )
    administrative = models.ForeignKey(
        'accounting.AdministrativeSegment', on_delete=models.PROTECT,
        related_name='revenue_budgets',
        help_text='MDA responsible for collecting this revenue',
    )
    economic = models.ForeignKey(
        'accounting.EconomicSegment', on_delete=models.PROTECT,
        related_name='revenue_budgets',
        help_text='NCoA Revenue account (must be type 1 = Revenue)',
    )
    fund = models.ForeignKey(
        'accounting.FundSegment', on_delete=models.PROTECT,
        related_name='revenue_budgets',
    )
    estimated_amount = models.DecimalField(
        max_digits=20, decimal_places=2,
        help_text='Budgeted/estimated revenue target for the fiscal year',
    )
    monthly_spread = models.JSONField(
        null=True, blank=True, default=None,
        help_text='Monthly revenue targets {1: Jan, 2: Feb, ...12: Dec}. '
                  'Null = equal monthly spread.',
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='DRAFT',
    )
    description = models.CharField(max_length=500, blank=True, default='')
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['fiscal_year', 'administrative', 'economic']
        verbose_name = 'Revenue Budget'
        verbose_name_plural = 'Revenue Budgets'
        indexes = [
            models.Index(fields=['fiscal_year', 'status']),
            models.Index(fields=['administrative', 'economic', 'fiscal_year']),
        ]

    def __str__(self):
        return (
            f"REV/{self.fiscal_year}/{self.administrative.code}/"
            f"{self.economic.code} - Target NGN {self.estimated_amount:,.2f}"
        )

    @property
    def actual_collected(self):
        """Actual revenue collected from GL journal postings."""
        from accounting.models.gl import GLBalance
        return GLBalance.objects.filter(
            account__code=self.economic.code,
            fiscal_year=self.fiscal_year.year,
        ).aggregate(
            total=models.Sum('credit_balance'),
        )['total'] or Decimal('0')

    @property
    def variance(self):
        """Positive = exceeded target, Negative = shortfall."""
        return self.actual_collected - self.estimated_amount

    @property
    def performance_rate(self):
        """Collection performance as percentage of target."""
        if self.estimated_amount <= 0:
            return Decimal('0')
        return (self.actual_collected / self.estimated_amount) * 100


# BudgetValidationService and BudgetExceededError are in budget/services.py
# Import from there: from budget.services import BudgetValidationService, BudgetExceededError
