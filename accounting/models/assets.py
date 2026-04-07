from datetime import date
from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone
from django.core.validators import MinValueValidator
from core.models import AuditBaseModel, ImmutableModelMixin
from django.contrib.auth.models import User


class CostCenter(AuditBaseModel):
    name = models.CharField(max_length=100, default='')
    code = models.CharField(max_length=20, unique=True, default='')
    center_type = models.CharField(max_length=20, choices=[
        ('Department', 'Department'),
        ('Project', 'Project'),
        ('Activity', 'Activity'),
        ('Location', 'Location'),
    ])
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_operational = models.BooleanField(default=True)
    gl_account = models.ForeignKey('accounting.Account', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class JournalLineCostCenter(models.Model):
    journal_line = models.ForeignKey('accounting.JournalLine', on_delete=models.CASCADE, related_name='cost_centers', null=True, blank=True)
    cost_center = models.ForeignKey(CostCenter, on_delete=models.CASCADE, null=True, blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        unique_together = ['journal_line', 'cost_center']

    def __str__(self):
        return f"JL{self.journal_line_id} - {self.cost_center} ({self.amount})"


class ProfitCenter(models.Model):
    name = models.CharField(max_length=100, default='')
    code = models.CharField(max_length=20, default='', unique=True)
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class CostAllocationRule(models.Model):
    name = models.CharField(max_length=100, default='')
    source_cost_center = models.ForeignKey(CostCenter, on_delete=models.CASCADE, related_name='allocation_rules_from', null=True, blank=True)
    source_account = models.ForeignKey('accounting.Account', on_delete=models.CASCADE, null=True, blank=True)
    target_cost_center = models.ForeignKey(CostCenter, on_delete=models.CASCADE, related_name='allocation_rules_to', null=True, blank=True)
    allocation_method = models.CharField(max_length=20, default='')
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class AssetClass(models.Model):
    name = models.CharField(max_length=100, default='')
    code = models.CharField(max_length=20, default='')
    default_life = models.IntegerField(default=5)
    depreciation_method = models.CharField(max_length=20, default='Straight-Line')

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class AssetCategory(models.Model):
    DEPRECIATION_METHOD_CHOICES = [
        ('Straight-Line', 'Straight-Line'),
        ('Declining Balance', 'Declining Balance'),
        ('Double Declining Balance', 'Double Declining Balance'),
        ('Sum of Years Digits', 'Sum of Years Digits'),
        ('Units of Production', 'Units of Production'),
    ]
    RESIDUAL_VALUE_TYPE_CHOICES = [
        ('percentage', 'Percentage of Cost'),
        ('amount', 'Fixed Amount'),
    ]

    name = models.CharField(max_length=100, default='')
    code = models.CharField(max_length=20, unique=True, default='')
    asset_class = models.ForeignKey(AssetClass, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    # GL Account assignments
    cost_account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT,
        related_name='category_cost_accounts',
        null=True, blank=True,
    )
    accumulated_depreciation_account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT,
        related_name='category_accum_depr_accounts',
        null=True, blank=True,
    )
    depreciation_expense_account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT,
        related_name='category_depr_expense_accounts',
        null=True, blank=True,
    )

    # Depreciation configuration
    depreciation_method = models.CharField(
        max_length=30, choices=DEPRECIATION_METHOD_CHOICES, default='Straight-Line',
    )
    default_life_years = models.IntegerField(default=5)

    # Residual value configuration
    residual_value_type = models.CharField(
        max_length=15, choices=RESIDUAL_VALUE_TYPE_CHOICES, default='percentage',
    )
    residual_value = models.DecimalField(max_digits=15, decimal_places=4, default=0)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class AssetConfiguration(models.Model):
    name = models.CharField(max_length=100, default='')
    default_useful_life = models.IntegerField(default=5)
    default_depreciation_method = models.CharField(max_length=20, default='')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class AssetLocation(models.Model):
    name = models.CharField(max_length=100, default='')
    code = models.CharField(max_length=20, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class FixedAsset(AuditBaseModel):
    asset_number = models.CharField(max_length=50, unique=True, default='')
    name = models.CharField(max_length=200, default='')
    description = models.TextField(blank=True, default='')
    asset_category = models.CharField(max_length=20, choices=[
        ('Building', 'Building'),
        ('Equipment', 'Equipment'),
        ('Vehicle', 'Vehicle'),
        ('IT', 'IT Equipment'),
        ('Furniture', 'Furniture'),
        ('Land', 'Land'),
    ])
    acquisition_date = models.DateField(default=date.today)
    acquisition_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    salvage_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    useful_life_years = models.IntegerField(default=0)
    depreciation_method = models.CharField(max_length=20, choices=[
        ('Straight-Line', 'Straight-Line'),
        ('Declining Balance', 'Declining Balance'),
    ], default='Straight-Line')
    accumulated_depreciation = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    asset_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='fixed_assets', null=True, blank=True)
    depreciation_expense_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='depreciation_expenses', null=True, blank=True)
    accumulated_depreciation_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='accumulated_depreciation', null=True, blank=True)
    mda = models.ForeignKey('accounting.MDA', on_delete=models.PROTECT, null=True, blank=True)
    fund = models.ForeignKey('accounting.Fund', on_delete=models.PROTECT, null=True, blank=True)
    function = models.ForeignKey('accounting.Function', on_delete=models.PROTECT, null=True, blank=True)
    program = models.ForeignKey('accounting.Program', on_delete=models.PROTECT, null=True, blank=True)
    geo = models.ForeignKey('accounting.Geo', on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        ('Active', 'Active'),
        ('Disposed', 'Disposed'),
        ('Retired', 'Retired'),
    ], default='Active')

    class Meta:
        ordering = ['asset_number']

    @property
    def net_book_value(self):
        return self.acquisition_cost - self.accumulated_depreciation

    def calculate_annual_depreciation(self):
        """Calculate annual depreciation based on method."""
        depreciable_amount = self.acquisition_cost - self.salvage_value
        if self.useful_life_years <= 0 or depreciable_amount <= 0:
            return Decimal('0.00')
        if self.depreciation_method == 'Straight-Line':
            return (depreciable_amount / self.useful_life_years).quantize(Decimal('0.01'))
        elif self.depreciation_method == 'Declining Balance':
            rate = Decimal('2') / self.useful_life_years
            nbv = self.net_book_value
            if nbv <= self.salvage_value:
                return Decimal('0.00')
            depreciation = (nbv * rate).quantize(Decimal('0.01'))
            if nbv - depreciation < self.salvage_value:
                return nbv - self.salvage_value
            return depreciation
        return Decimal('0.00')

    def __str__(self):
        return f"{self.asset_number} - {self.name}"


class DepreciationSchedule(models.Model):
    asset = models.ForeignKey(FixedAsset, on_delete=models.CASCADE, related_name='depreciation_schedules', null=True, blank=True)
    period_date = models.DateField(default=date.today)
    depreciation_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    journal_entry = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True)
    is_posted = models.BooleanField(default=False)

    class Meta:
        ordering = ['period_date']
        unique_together = ['asset', 'period_date']

    def __str__(self):
        return f"{self.asset.asset_number} - {self.period_date} ({self.depreciation_amount})"


class AssetInsurance(models.Model):
    asset = models.ForeignKey(FixedAsset, on_delete=models.CASCADE, related_name='insurances', null=True, blank=True)
    provider = models.CharField(max_length=200, default='')
    policy_number = models.CharField(max_length=50, default='')
    start_date = models.DateField(default=date.today)
    end_date = models.DateField(default=date.today)
    premium_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.policy_number} - {self.provider}"


class AssetMaintenance(models.Model):
    """Enhanced maintenance tracking with full cost integration"""

    MAINTENANCE_TYPE_CHOICES = [
        ('Preventive', 'Preventive - Scheduled maintenance'),
        ('Corrective', 'Corrective - Break/fix'),
        ('Predictive', 'Predictive - Condition-based'),
        ('Emergency', 'Emergency - Urgent repair'),
        ('Inspection', 'Inspection - Safety/compliance'),
        ('Overhaul', 'Overhaul - Major restoration'),
    ]

    STATUS_CHOICES = [
        ('Scheduled', 'Scheduled'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]

    asset = models.ForeignKey('FixedAsset', on_delete=models.CASCADE, related_name='maintenances', null=True, blank=True)
    maintenance_type = models.CharField(max_length=20, choices=MAINTENANCE_TYPE_CHOICES, default='Preventive')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Scheduled')

    scheduled_date = models.DateField(default=date.today)
    completed_date = models.DateField(null=True, blank=True)

    labor_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    parts_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    external_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    vendor = models.ForeignKey('procurement.Vendor', on_delete=models.SET_NULL, null=True, blank=True, related_name='maintenances')

    description = models.TextField(default='')
    notes = models.TextField(blank=True, default='')

    journal_entry = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='maintenance_entries')

    class Meta:
        ordering = ['-scheduled_date']
        permissions = [
            ('approve_assetmaintenance', 'Can approve maintenance'),
        ]

    def save(self, *args, **kwargs):
        self.total_cost = self.labor_cost + self.parts_cost + self.external_cost
        super().save(*args, **kwargs)

    def post_to_gl(self):
        """Post maintenance costs to General Ledger.

        Delegates to TransactionPostingService to keep GL logic out of models.
        Uses lazy import to avoid circular dependency at module load time.
        """
        if self.status != 'Completed' or self.journal_entry:
            return None

        # Lazy import — TransactionPostingService lives in accounting.services
        # which imports from accounting.models; importing at call-time (not
        # module-load time) breaks the circular dependency.
        from accounting.transaction_posting import TransactionPostingService
        journal = TransactionPostingService.post_asset_maintenance(self)
        if journal:
            self.journal_entry = journal
            self.save(update_fields=['journal_entry'])
        return journal

    def __str__(self):
        return f"{self.asset} {self.get_maintenance_type_display()} - {self.scheduled_date}"


class MaintenanceBudget(models.Model):
    """Track maintenance spending against budget"""

    fiscal_year = models.IntegerField()
    mda = models.ForeignKey('accounting.MDA', on_delete=models.CASCADE, null=True, blank=True, related_name='maintenance_budgets')
    cost_center = models.ForeignKey('CostCenter', on_delete=models.CASCADE, null=True, blank=True, related_name='maintenance_budgets')

    budget_amount = models.DecimalField(max_digits=15, decimal_places=2)
    spent_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        unique_together = ['fiscal_year', 'mda', 'cost_center']

    @property
    def remaining(self):
        return self.budget_amount - self.spent_amount

    @property
    def utilization_percent(self):
        if self.budget_amount > 0:
            return (self.spent_amount / self.budget_amount) * 100
        return 0

    def add_expense(self, amount):
        from django.core.exceptions import ValidationError
        if self.utilization_percent >= 100:
            raise ValidationError("Maintenance budget exhausted")
        self.spent_amount += amount
        self.save()


class AssetTransfer(models.Model):
    asset = models.ForeignKey(FixedAsset, on_delete=models.CASCADE, null=True, blank=True)
    from_location = models.ForeignKey(AssetLocation, on_delete=models.CASCADE, related_name='transfers_from', null=True, blank=True)
    to_location = models.ForeignKey(AssetLocation, on_delete=models.CASCADE, related_name='transfers_to', null=True, blank=True)
    transfer_date = models.DateField(default=date.today)
    transferred_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-transfer_date']

    def __str__(self):
        return f"Transfer {self.asset} {self.transfer_date}"


class AssetDepreciationSchedule(models.Model):
    asset = models.ForeignKey(FixedAsset, on_delete=models.CASCADE, related_name='asset_depreciation_schedules', null=True, blank=True)
    period_date = models.DateField(default=date.today)
    depreciation_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_posted = models.BooleanField(default=False)

    class Meta:
        ordering = ['period_date']

    def __str__(self):
        return f"{self.asset} - {self.period_date} ({self.depreciation_amount})"


class AssetImpairment(models.Model):
    asset = models.ForeignKey(FixedAsset, on_delete=models.CASCADE, null=True, blank=True)
    impairment_date = models.DateField(default=date.today)
    impairment_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    reason = models.TextField(blank=True, default='')
    documented_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-impairment_date']

    def __str__(self):
        return f"Impairment {self.asset} - {self.impairment_date} ({self.impairment_amount})"


class AssetRevaluationRun(models.Model):
    """Asset Revaluation per IAS 16 - Property, Plant & Equipment.

    NOTE: This is DIFFERENT from CurrencyRevaluation!
    - Currency Revaluation: Adjusts monetary items (cash, AR, AP) for FX changes
    - Asset Revaluation: Adjusts non-monetary assets (PPE) to fair value

    Asset Revaluation creates entries to Revaluation Surplus (Equity), not P&L.
    """

    revaluation_date = models.DateField()
    revaluation_number = models.CharField(max_length=50, unique=True)

    REVALUATION_METHOD_CHOICES = [
        ('FAIR_VALUE', 'Fair Value'),
        ('INDEXED_COST', 'Indexed Cost'),
        ('EXTERNAL_VALUATION', 'External Valuation'),
    ]
    revaluation_method = models.CharField(max_length=20, choices=REVALUATION_METHOD_CHOICES)

    valuator_name = models.CharField(max_length=200, blank=True, default='')
    valuator_qualification = models.CharField(max_length=200, blank=True, default='')
    valuation_report_reference = models.CharField(max_length=100, blank=True, default='')

    fiscal_period = models.ForeignKey('accounting.FiscalPeriod', on_delete=models.PROTECT, null=True, blank=True)

    total_cost_adjustment = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_accum_depr_adjustment = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_revaluation_surplus = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_revaluation_loss = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('APPROVED', 'Approved'),
        ('POSTED', 'Posted'),
        ('REVERSED', 'Reversed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    revaluation_gain_account = models.CharField(max_length=20, default='3101')
    revaluation_loss_account = models.CharField(max_length=20, default='8101')
    revaluation_surplus_account = models.CharField(max_length=20, default='3100')

    notes = models.TextField(blank=True, default='')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='asset_revaluations')
    created_at = models.DateTimeField(auto_now_add=True)

    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='revaluations_approved')
    approved_at = models.DateTimeField(null=True, blank=True)

    journal_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-revaluation_date']
        indexes = [
            models.Index(fields=['revaluation_date']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Asset Revaluation {self.revaluation_number}"


class AssetRevaluationDetail(models.Model):
    """Individual asset revaluation details per IAS 16."""

    revaluation = models.ForeignKey(AssetRevaluationRun, on_delete=models.CASCADE, related_name='details')
    asset = models.ForeignKey('FixedAsset', on_delete=models.PROTECT, related_name='revaluations')

    asset_code = models.CharField(max_length=50, blank=True, default='')
    asset_name = models.CharField(max_length=200, blank=True, default='')

    BEFORE_REVALUATION = 'Before'
    AFTER_REVALUATION = 'After'

    cost_before = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cost_after = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cost_adjustment = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    accum_depr_before = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    accum_depr_after = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    accum_depr_adjustment = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    nbv_before = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    nbv_after = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    revaluation_surplus = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    revaluation_loss = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    VALUATION_SOURCE_CHOICES = [
        ('INTERNAL', 'Internal Valuation'),
        ('EXTERNAL', 'External Valuer'),
        ('MARKET', 'Market Comparison'),
        ('INDEX', 'Cost Index'),
    ]
    valuation_source = models.CharField(max_length=20, choices=VALUATION_SOURCE_CHOICES, default='INTERNAL')

    justification = models.TextField(blank=True, default='')

    journal_line_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['asset_code']

    def __str__(self):
        return f"{self.asset_code}: {self.cost_adjustment}"


class AssetDisposal(models.Model):
    """Asset disposal with gain/loss calculation."""

    disposal_number = models.CharField(max_length=50, unique=True)
    asset = models.ForeignKey('FixedAsset', on_delete=models.PROTECT, related_name='disposals')

    disposal_date = models.DateField()
    disposal_reason = models.TextField()

    DISPOSAL_METHOD_CHOICES = [
        ('SALE', 'Sale'),
        ('SCRAP', 'Scrapped'),
        ('DONATION', 'Donated'),
        ('THEFT', 'Stolen'),
        ('LOSS', 'Lost'),
        ('TRADE_IN', 'Trade-in'),
    ]
    disposal_method = models.CharField(max_length=20, choices=DISPOSAL_METHOD_CHOICES)

    buyer_name = models.CharField(max_length=200, blank=True, default='')
    buyer_address = models.TextField(blank=True, default='')

    sale_proceeds = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    disposal_costs = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    net_proceeds = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    acquisition_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    accum_depreciation = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_book_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    gain_on_disposal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    loss_on_disposal = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('APPROVED', 'Approved'),
        ('POSTED', 'Posted'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    gain_account = models.CharField(max_length=20, default='7200')
    loss_account = models.CharField(max_length=20, default='8200')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='asset_disposals')
    created_at = models.DateTimeField(auto_now_add=True)

    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='disposals_approved')
    approved_at = models.DateTimeField(null=True, blank=True)

    journal_id = models.IntegerField(null=True, blank=True)

    fiscal_period = models.ForeignKey('accounting.FiscalPeriod', on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ['-disposal_date']

    def __str__(self):
        return f"Disposal {self.disposal_number} - {self.asset}"


class DepreciationRun(models.Model):
    """Tracks each depreciation execution."""

    run_date = models.DateField()
    fiscal_period = models.ForeignKey('accounting.FiscalPeriod', on_delete=models.PROTECT, null=True, blank=True)
    fiscal_year = models.IntegerField(default=0)
    period = models.IntegerField(default=0)

    assets_processed = models.IntegerField(default=0)
    total_depreciation = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_accumulated = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    journal_id = models.IntegerField(null=True, blank=True)

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('CALCULATED', 'Calculated'),
        ('POSTED', 'Posted'),
        ('FAILED', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='depreciations_posted')

    class Meta:
        ordering = ['-run_date']

    def __str__(self):
        return f"Depreciation {self.run_date} FY{self.fiscal_year} P{self.period}"


class DepreciationDetail(models.Model):
    """Details of depreciation for each asset."""

    run = models.ForeignKey(DepreciationRun, on_delete=models.CASCADE, related_name='details')
    asset = models.ForeignKey('FixedAsset', on_delete=models.PROTECT)

    asset_code = models.CharField(max_length=50, blank=True, default='')
    asset_name = models.CharField(max_length=200, blank=True, default='')

    acquisition_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    salvage_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    depreciable_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    useful_life_years = models.IntegerField(default=0)
    useful_life_months = models.IntegerField(default=0)

    depreciation_method = models.CharField(max_length=30, blank=True, default='')

    period_depreciation = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    accumulated_depreciation_before = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    accumulated_depreciation_after = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_book_value_before = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_book_value_after = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    is_in_use = models.BooleanField(default=True)
    remaining_life_months = models.IntegerField(default=0)

    schedule_line_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['asset']

    def __str__(self):
        return f"{self.asset_code} - {self.period_depreciation}"
