from datetime import date
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from core.models import AuditBaseModel
from django.contrib.auth.models import User


class GLBalance(models.Model):
    account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, null=True, blank=True)
    fund = models.ForeignKey('accounting.Fund', on_delete=models.PROTECT, null=True, blank=True)
    function = models.ForeignKey('accounting.Function', on_delete=models.PROTECT, null=True, blank=True)
    program = models.ForeignKey('accounting.Program', on_delete=models.PROTECT, null=True, blank=True)
    geo = models.ForeignKey('accounting.Geo', on_delete=models.PROTECT, null=True, blank=True)
    # S3-05 — MDA dimension added so budget "actual expended" can be
    # attributed to the correct administrative unit. Previously budget
    # execution rolled up shared expense accounts across ALL MDAs,
    # producing wrong budget-vs-actual numbers for any multi-MDA tenant.
    # Nullable so legacy rows load; posting services write the MDA on
    # every new balance row.
    mda = models.ForeignKey(
        'accounting.MDA', on_delete=models.PROTECT,
        null=True, blank=True, related_name='gl_balances',
    )
    fiscal_year = models.IntegerField(db_index=True, default=0)
    period = models.IntegerField(default=0)
    debit_balance = models.DecimalField(max_digits=19, decimal_places=2, default=0)
    credit_balance = models.DecimalField(max_digits=19, decimal_places=2, default=0)

    class Meta:
        # S3-05 — uniqueness now includes MDA. Different MDAs sharing
        # the same economic account maintain separate balance rows.
        unique_together = ['account', 'fund', 'function', 'program', 'geo', 'mda', 'fiscal_year', 'period']
        ordering = ['fiscal_year', 'period', 'account__code']
        indexes = [
            models.Index(fields=['fiscal_year', 'period']),
            models.Index(fields=['account', 'fiscal_year']),
            models.Index(fields=['fund', 'fiscal_year', 'period']),
            models.Index(fields=['mda', 'fiscal_year', 'period']),
            models.Index(fields=['mda', 'account', 'fiscal_year']),
        ]
        # S5-03 — granular permission for IPSAS report access. Granting
        # ``view_journalheader`` implicitly grants this (see
        # ``accounting.permissions.CanViewFinancialStatements``) so
        # existing deployments remain unaffected, but new Auditor-General
        # and Finance Commissioner roles can be wired to this specific
        # permission without giving full ledger access.
        permissions = [
            (
                'view_financial_statements',
                'Can view IPSAS financial statements (SoFP, SoFPerformance, '
                'Cash Flow, Changes in Net Assets, Notes, Budget-vs-Actual)',
            ),
        ]

    @property
    def net_balance(self):
        """Net balance respecting account normal balance direction.

        Assets and Expenses normally carry debit balances (debit - credit).
        Liabilities, Equity, and Revenue normally carry credit balances (credit - debit).
        """
        if self.account and self.account.account_type in ('Liability', 'Equity', 'Income'):
            return self.credit_balance - self.debit_balance
        return self.debit_balance - self.credit_balance

    def __str__(self):
        return f"GL {self.account.code} FY{self.fiscal_year} P{self.period}"


class BudgetPeriod(models.Model):
    """
    Represents a fiscal period for budget and GL tracking.
    Supports monthly, quarterly, and annual periods with locking functionality.
    """
    fiscal_year = models.IntegerField(default=0, db_index=True)
    period_type = models.CharField(max_length=10, choices=[
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
        ('ANNUAL', 'Annual'),
    ])
    period_number = models.IntegerField(default=0)
    start_date = models.DateField(default=date.today)
    end_date = models.DateField(default=date.today)
    status = models.CharField(max_length=10, choices=[
        ('DRAFT', 'Draft'),
        ('OPEN', 'Open for Posting'),
        ('ADJUSTMENT', 'Adjustment Period'),
        ('CLOSED', 'Closed'),
        ('LOCKED', 'Locked (Final)'),
    ], default='DRAFT', db_index=True)

    # Lock tracking
    closed_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='budget_periods_closed'
    )
    closed_date = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='budget_periods_locked'
    )
    locked_date = models.DateTimeField(null=True, blank=True)

    # Period locking prevents all postings
    allow_postings = models.BooleanField(default=True)
    allow_adjustments = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        unique_together = ['fiscal_year', 'period_type', 'period_number']
        ordering = ['-fiscal_year', '-period_number']
        indexes = [
            models.Index(fields=['fiscal_year', 'period_type', 'status']),
        ]

    def __str__(self):
        return f"FY{self.fiscal_year} {self.get_period_type_display()} {self.period_number} ({self.get_status_display()})"

    def can_post(self):
        """Check if transactions can be posted to this period"""
        return self.status in ('OPEN', 'ADJUSTMENT') and self.allow_postings

    def can_adjust(self):
        """Check if adjustments can be made to this period"""
        return self.status in ('OPEN', 'ADJUSTMENT') and self.allow_adjustments

    def close(self, user):
        """Close the period - prevents new postings but allows adjustments if configured"""
        self.status = 'CLOSED'
        self.closed_by = user
        self.closed_date = timezone.now()
        self.allow_postings = False
        self.save()

    def lock(self, user):
        """Lock the period - prevents all changes including adjustments"""
        self.status = 'LOCKED'
        self.locked_by = user
        self.locked_date = timezone.now()
        self.allow_postings = False
        self.allow_adjustments = False
        self.save()

    def reopen(self, user, reason=''):
        """Reopen a closed/locked period (requires authorization)"""
        if self.status == 'LOCKED':
            # Only allow reopening locked periods with special permission
            raise PermissionError("Cannot reopen a locked period. Contact system administrator.")
        self.status = 'OPEN'
        self.allow_postings = True
        self.notes = f"{self.notes}\nReopened by {user} on {timezone.now()}: {reason}".strip()
        self.save()

    @classmethod
    def get_current_period(cls, fiscal_year=None, period_type='MONTHLY'):
        """Get the current active period"""
        from django.utils import timezone as tz
        today = tz.now().date()
        return cls.objects.filter(
            start_date__lte=today,
            end_date__gte=today,
            period_type=period_type,
            status__in=['OPEN', 'ADJUSTMENT']
        ).first()

    @classmethod
    def get_period_for_date(cls, posting_date, period_type='MONTHLY'):
        """Get the period that contains the given date"""
        return cls.objects.filter(
            start_date__lte=posting_date,
            end_date__gte=posting_date,
            period_type=period_type
        ).first()
        return f"FY{self.fiscal_year} - {self.get_period_type_display()} {self.period_number}"


class Budget(models.Model):
    budget_code = models.CharField(max_length=50, unique=True, db_index=True, default='')
    period = models.ForeignKey(BudgetPeriod, on_delete=models.CASCADE, related_name='budgets', null=True, blank=True)
    mda = models.ForeignKey('accounting.MDA', on_delete=models.CASCADE, related_name='budgets', null=True, blank=True)
    account = models.ForeignKey('accounting.Account', on_delete=models.CASCADE, null=True, blank=True)
    fund = models.ForeignKey('accounting.Fund', on_delete=models.SET_NULL, null=True, blank=True)
    function = models.ForeignKey('accounting.Function', on_delete=models.SET_NULL, null=True, blank=True)
    program = models.ForeignKey('accounting.Program', on_delete=models.SET_NULL, null=True, blank=True)
    geo = models.ForeignKey('accounting.Geo', on_delete=models.SET_NULL, null=True, blank=True)
    cost_center = models.ForeignKey('accounting.CostCenter', on_delete=models.SET_NULL, null=True, blank=True, related_name='budgets')
    allocated_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    revised_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    control_level = models.CharField(max_length=10, choices=[
        ('NONE', 'No Control'),
        ('WARNING', 'Warning Only'),
        ('HARD_STOP', 'Hard Stop'),
    ], default='HARD_STOP')
    enable_encumbrance = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='budgets_created')

    class Meta:
        unique_together = ['period', 'mda', 'account', 'fund', 'function', 'program', 'geo']
        ordering = ['budget_code']
        permissions = [
            ('approve_budget', 'Can approve budgets'),
        ]

    def __str__(self):
        return self.budget_code

    @property
    def encumbered_amount(self):
        # Use pre-annotated value when available (avoids N+1 queries in list views)
        if hasattr(self, '_encumbered') and self._encumbered is not None:
            return self._encumbered
        from django.db.models import Sum
        total = self.encumbrances.filter(
            status__in=['ACTIVE', 'PARTIALLY_LIQUIDATED']
        ).aggregate(
            total=Sum(models.F('amount') - models.F('liquidated_amount'))
        )['total']
        return total or 0

    @property
    def expended_amount(self):
        # Use pre-annotated value when available (avoids N+1 queries in list views)
        if hasattr(self, '_expended') and self._expended is not None:
            return self._expended
        from django.db.models import Sum
        from accounting.models.balances import GLBalance  # direct sub-module — avoids circular import via __init__
        total = GLBalance.objects.filter(
            account=self.account,
            fund=self.fund,
            function=self.function,
            program=self.program,
            geo=self.geo,
            fiscal_year=self.period.fiscal_year,
            period=self.period.period_number
        ).aggregate(total=Sum('debit_balance'))['total']
        return total or 0

    @property
    def available_amount(self):
        allocated = self.revised_amount or self.allocated_amount
        return allocated - self.encumbered_amount - self.expended_amount

    @property
    def utilization_rate(self):
        allocated = self.revised_amount or self.allocated_amount
        if allocated == 0:
            return 0
        return ((self.encumbered_amount + self.expended_amount) / allocated) * 100

    def check_availability(self, amount):
        available = self.available_amount
        if available >= amount:
            return True, "Budget available", available
        elif self.control_level == 'NONE':
            return True, f"Warning: Only {available} available, but no control enforced", available
        elif self.control_level == 'WARNING':
            return True, f"Warning: Only {available} available", available
        else:
            return False, f"Insufficient budget. Available: {available}, Requested: {amount}", available


class BudgetEncumbrance(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='encumbrances', null=True, blank=True)
    reference_type = models.CharField(max_length=20, choices=[
        ('PR', 'Purchase Requisition'),
        ('PO', 'Purchase Order'),
        ('CONTRACT', 'Contract'),
    ])
    reference_id = models.IntegerField(default=0)
    encumbrance_date = models.DateField(default=date.today)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    liquidated_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=25, choices=[
        ('ACTIVE', 'Active'),
        ('PARTIALLY_LIQUIDATED', 'Partially Liquidated'),
        ('FULLY_LIQUIDATED', 'Fully Liquidated'),
        ('CANCELLED', 'Cancelled'),
    ], default='ACTIVE')
    description = models.TextField(default='')

    class Meta:
        ordering = ['-encumbrance_date']

    def __str__(self):
        return f"{self.reference_type} #{self.reference_id} - {self.amount}"


class BankAccount(AuditBaseModel):
    ACCOUNT_TYPE_CHOICES = [
        ('Bank', 'Bank'),
        ('Cash', 'Cash'),
        ('Petty Cash', 'Petty Cash'),
        ('Imprest', 'Imprest'),
    ]

    name = models.CharField(max_length=100, default='')
    account_number = models.CharField(max_length=50, default='')
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, default='')
    gl_account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT, related_name='bank_accounts',
        limit_choices_to={'reconciliation_type': 'bank_accounting'}
    , null=True, blank=True)
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    currency = models.ForeignKey('accounting.Currency', on_delete=models.PROTECT, default=1, null=True, blank=True)
    bank_name = models.CharField(max_length=100, blank=True, default='')
    branch_name = models.CharField(max_length=100, blank=True, default='')
    swift_code = models.CharField(max_length=20, blank=True, default='')
    iban = models.CharField(max_length=50, blank=True, default='')
    advance_customer_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    advance_supplier_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.account_number}"

    @property
    def total_balance(self):
        return self.current_balance

    @property
    def available_balance(self):
        return self.current_balance + self.advance_customer_balance - self.advance_supplier_balance


class BudgetCheckLog(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='check_logs', null=True, blank=True)
    transaction_type = models.CharField(max_length=20, default='')
    transaction_id = models.IntegerField(default=0)
    requested_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    available_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    check_result = models.CharField(max_length=10, choices=[
        ('PASSED', 'Passed'),
        ('WARNING', 'Warning'),
        ('BLOCKED', 'Blocked'),
    ])
    override_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    override_reason = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type} #{self.transaction_id} - {self.check_result}"


class BudgetAmendment(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='amendments', null=True, blank=True)
    amendment_type = models.CharField(max_length=10, choices=[
        ('INCREASE', 'Increase'),
        ('DECREASE', 'Decrease'),
        ('TRANSFER', 'Transfer'),
    ])
    original_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    new_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    reason = models.TextField(default='')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='amendments_requested')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='amendments_approved')
    status = models.CharField(max_length=10, choices=[
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ], default='PENDING')
    requested_date = models.DateTimeField(auto_now_add=True)
    approved_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_date']

    def __str__(self):
        return f"{self.amendment_type} - {self.status}"


class BudgetTransfer(models.Model):
    from_budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='transfers_out', null=True, blank=True)
    to_budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='transfers_in', null=True, blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    reason = models.TextField(default='')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='transfers_requested')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='budget_transfers_approved')
    status = models.CharField(max_length=10, choices=[
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ], default='PENDING')
    transfer_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-transfer_date']
        permissions = [
            ('approve_budgettransfer', 'Can approve budget transfers'),
        ]

    def __str__(self):
        return f"Transfer {self.amount} - {self.status}"


class BudgetForecast(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, null=True, blank=True)
    forecast_date = models.DateField(default=date.today)
    projected_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    projected_expense = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-forecast_date']

    def __str__(self):
        return f"Forecast {self.forecast_date}"


class BudgetAnomaly(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, null=True, blank=True)
    anomaly_type = models.CharField(max_length=20, default='')
    detected_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    expected_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    description = models.TextField(default='')
    detected_date = models.DateField(default=date.today)
    reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-detected_date']

    def __str__(self):
        return f"{self.anomaly_type} - {self.detected_date}"
