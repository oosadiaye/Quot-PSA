from datetime import date
from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone
from django.core.validators import MinValueValidator
from core.models import AuditBaseModel, ImmutableModelMixin
from django.contrib.auth.models import User


class FinancialReportTemplate(models.Model):
    name = models.CharField(max_length=100, default='')
    report_type = models.CharField(max_length=50, default='')
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.report_type})"


class FinancialReport(models.Model):
    template = models.ForeignKey(FinancialReportTemplate, on_delete=models.CASCADE, null=True, blank=True)
    report_date = models.DateField(default=date.today)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    data = models.JSONField(default=dict)

    class Meta:
        ordering = ['-report_date']

    def __str__(self):
        return f"{self.template} - {self.report_date}"


class ReportColumnConfig(models.Model):
    template = models.ForeignKey(FinancialReportTemplate, on_delete=models.CASCADE, null=True, blank=True)
    column_name = models.CharField(max_length=50, default='')
    column_type = models.CharField(max_length=20, default='')
    display_order = models.IntegerField(default=0)
    is_visible = models.BooleanField(default=True)

    def __str__(self):
        return self.column_name


class AccountingDocument(models.Model):
    document_type = models.CharField(max_length=30, default='')
    reference_number = models.CharField(max_length=100, default='')
    document_date = models.DateField(default=date.today)
    title = models.CharField(max_length=200, default='')
    description = models.TextField(default='')
    file = models.FileField(upload_to='tenants/documents/', null=True, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-document_date']

    def __str__(self):
        return f"{self.document_type} {self.reference_number} - {self.title}"


class DocumentSignature(models.Model):
    document = models.ForeignKey(AccountingDocument, on_delete=models.CASCADE, related_name='signatures', null=True, blank=True)
    signed_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    signed_at = models.DateTimeField(auto_now_add=True)
    signature_data = models.TextField(default='')

    def __str__(self):
        return f"Sig by {self.signed_by} at {self.signed_at}"


class FiscalPeriod(models.Model):
    PERIOD_TYPE_CHOICES = [
        ('Daily', 'Daily'),
        ('Monthly', 'Monthly'),
        ('Yearly', 'Yearly'),
    ]
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('Closed', 'Closed'),
        ('Locked', 'Locked'),
    ]

    # Audit fields — present in DB from original migration 0008; must stay to avoid NOT NULL errors
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fiscal_periods_created', db_column='created_by_id',
    )
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fiscal_periods_updated', db_column='updated_by_id',
    )

    name = models.CharField(max_length=100, blank=True, default='')
    is_adjustment_period = models.BooleanField(default=False)

    fiscal_year = models.IntegerField(default=0)
    period_number = models.IntegerField(default=0)
    period_type = models.CharField(max_length=10, choices=PERIOD_TYPE_CHOICES, default='Monthly')
    start_date = models.DateField(default=date.today)
    end_date = models.DateField(default=date.today)
    is_closed = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Open')
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='periods_closed')
    closed_date = models.DateTimeField(null=True, blank=True)
    closed_reason = models.TextField(blank=True, default='')
    allow_journal_entry = models.BooleanField(default=True)
    allow_invoice = models.BooleanField(default=True)
    allow_payment = models.BooleanField(default=True)
    allow_procurement = models.BooleanField(default=True)
    allow_inventory = models.BooleanField(default=True)
    allow_sales = models.BooleanField(default=True)

    class Meta:
        unique_together = ['fiscal_year', 'period_number', 'period_type']
        ordering = ['fiscal_year', 'period_number']

    def __str__(self):
        return f"FY{self.fiscal_year} - P{self.period_number} ({self.period_type})"


class FiscalYear(models.Model):
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('Closed', 'Closed'),
        ('Locked', 'Locked'),
    ]
    PERIOD_TYPE_CHOICES = [
        ('Daily', 'Daily'),
        ('Monthly', 'Monthly'),
        ('Yearly', 'Yearly'),
    ]

    year = models.IntegerField(unique=True, default=2026)
    name = models.CharField(max_length=100, default='')
    start_date = models.DateField(default=date.today)
    end_date = models.DateField(default=date.today)
    period_type = models.CharField(max_length=10, choices=PERIOD_TYPE_CHOICES, default='Monthly')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Open')
    is_active = models.BooleanField(default=False)
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='fiscal_years_closed')
    closed_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-year']

    def __str__(self):
        return f"FY {self.year} - {self.name}"

    @property
    def periods(self):
        return FiscalPeriod.objects.filter(fiscal_year=self.year).order_by('period_number')

    @property
    def open_periods(self):
        return self.periods.filter(status='Open')

    @property
    def closed_periods(self):
        return self.periods.filter(status='Closed')


class PeriodAccess(models.Model):
    ACCESS_TYPE_CHOICES = [
        ('Temporary', 'Temporary'),
        ('Permanent', 'Permanent'),
    ]

    period = models.ForeignKey(FiscalPeriod, on_delete=models.CASCADE, related_name='access_grants', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='period_access_grants', null=True, blank=True)
    access_type = models.CharField(max_length=20, choices=ACCESS_TYPE_CHOICES, default='Temporary')
    granted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='period_access_granted')
    start_date = models.DateField(default=date.today)
    end_date = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.period} ({self.access_type})"


class PeriodCloseCheck(models.Model):
    period = models.ForeignKey(FiscalPeriod, on_delete=models.CASCADE, null=True, blank=True)
    check_name = models.CharField(max_length=100, default='')
    check_result = models.CharField(max_length=10, default='')
    details = models.TextField(blank=True, default='')
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-checked_at']

    def __str__(self):
        return f"{self.check_name} - {self.check_result}"


class DeferredRevenue(models.Model):
    name = models.CharField(max_length=100, default='')
    customer = models.ForeignKey('sales.Customer', on_delete=models.CASCADE, null=True, blank=True)
    initial_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    start_date = models.DateField(default=date.today)
    recognition_periods = models.IntegerField(default=0)
    recognized_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return self.name


class DeferredExpense(models.Model):
    name = models.CharField(max_length=100, default='')
    vendor = models.ForeignKey('procurement.Vendor', on_delete=models.CASCADE, null=True, blank=True)
    initial_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    start_date = models.DateField(default=date.today)
    recognition_periods = models.IntegerField(default=0)
    recognized_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return self.name


class AmortizationSchedule(models.Model):
    deferred_revenue = models.ForeignKey(DeferredRevenue, on_delete=models.CASCADE, null=True, blank=True)
    deferred_expense = models.ForeignKey(DeferredExpense, on_delete=models.CASCADE, null=True, blank=True)
    period_date = models.DateField(default=date.today)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_posted = models.BooleanField(default=False)

    class Meta:
        ordering = ['period_date']

    def __str__(self):
        return f"Amortization {self.period_date} - {self.amount}"


class Lease(models.Model):
    lease_number = models.CharField(max_length=50, default='')
    lessor = models.CharField(max_length=200, default='')
    start_date = models.DateField(default=date.today)
    end_date = models.DateField(default=date.today)
    lease_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    payment_frequency = models.CharField(max_length=20, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['lease_number']

    def __str__(self):
        return f"{self.lease_number} - {self.lessor}"


class LeasePayment(models.Model):
    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    payment_date = models.DateField(default=date.today)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_paid = models.BooleanField(default=False)

    class Meta:
        ordering = ['payment_date']

    def __str__(self):
        return f"{self.lease} - {self.payment_date} ({self.amount})"


class TreasuryForecast(models.Model):
    forecast_date = models.DateField(default=date.today)
    projected_cash_inflow = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    projected_cash_outflow = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-forecast_date']

    def __str__(self):
        return f"Treasury {self.forecast_date}"


class Investment(models.Model):
    investment_number = models.CharField(max_length=50, default='')
    investment_type = models.CharField(max_length=20, default='')
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    purchase_date = models.DateField(default=date.today)
    maturity_date = models.DateField(null=True, blank=True)
    expected_return = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['investment_number']

    def __str__(self):
        return f"{self.investment_number} ({self.investment_type})"


class Loan(models.Model):
    loan_number = models.CharField(max_length=50, default='')
    lender = models.CharField(max_length=200, default='')
    principal_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    start_date = models.DateField(default=date.today)
    end_date = models.DateField(default=date.today)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['loan_number']

    def __str__(self):
        return f"{self.loan_number} - {self.lender}"


class LoanRepayment(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='repayments', null=True, blank=True)
    repayment_date = models.DateField(default=date.today)
    principal_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    interest_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_paid = models.BooleanField(default=False)

    class Meta:
        ordering = ['repayment_date']

    def __str__(self):
        return f"{self.loan} - {self.repayment_date} ({self.principal_amount})"


class ExchangeRateHistory(models.Model):
    from_currency = models.ForeignKey('accounting.Currency', on_delete=models.CASCADE, related_name='exchange_from', null=True, blank=True)
    to_currency = models.ForeignKey('accounting.Currency', on_delete=models.CASCADE, related_name='exchange_to', null=True, blank=True)
    rate_date = models.DateField(default=date.today)
    exchange_rate = models.DecimalField(max_digits=15, decimal_places=6, default=0)

    class Meta:
        unique_together = ['from_currency', 'to_currency', 'rate_date']
        ordering = ['-rate_date']

    def __str__(self):
        return f"{self.from_currency}/{self.to_currency} - {self.rate_date}"


class ForeignCurrencyRevaluation(models.Model):
    revaluation_date = models.DateField(default=date.today)
    currency = models.ForeignKey('accounting.Currency', on_delete=models.CASCADE, null=True, blank=True)
    revalued_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    exchange_rate = models.DecimalField(max_digits=15, decimal_places=6, default=0)
    gain_loss = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_posted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-revaluation_date']

    def __str__(self):
        return f"Reval {self.currency} {self.revaluation_date}"


class RecurringJournal(AuditBaseModel):
    """Recurring journal templates that can be自动 generated"""
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('biweekly', 'Bi-Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annually', 'Annually'),
    ]

    START_TYPE_CHOICES = [
        ('now', 'Start Now'),
        ('scheduled', 'Schedule Future'),
    ]

    name = models.CharField(max_length=100, default='')
    code = models.CharField(max_length=50, unique=True, default='')
    description = models.TextField(blank=True, default='')

    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='monthly')
    start_date = models.DateField(default=date.today)
    start_type = models.CharField(max_length=20, choices=START_TYPE_CHOICES, default='now')
    scheduled_posting_date = models.DateField(null=True, blank=True, help_text="Future posting date when start_type is 'scheduled'")
    end_date = models.DateField(null=True, blank=True)
    next_run_date = models.DateField(default=date.today)

    is_active = models.BooleanField(default=True)
    auto_post = models.BooleanField(default=False, help_text="Auto-post when generated")

    # New fields for month-end defaults
    use_month_end_default = models.BooleanField(default=False, help_text="Auto-set posting date to last day of month")
    auto_reverse_on_month_start = models.BooleanField(default=False, help_text="Auto-reverse on 1st day of next month")
    code_prefix = models.CharField(max_length=10, default='REC', help_text="Code prefix for identification")

    fund = models.ForeignKey('accounting.Fund', on_delete=models.SET_NULL, null=True, blank=True)
    function = models.ForeignKey('accounting.Function', on_delete=models.SET_NULL, null=True, blank=True)
    program = models.ForeignKey('accounting.Program', on_delete=models.SET_NULL, null=True, blank=True)
    geo = models.ForeignKey('accounting.Geo', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.code:
            from datetime import datetime
            prefix = self.code_prefix or 'REC'
            today = datetime.now().strftime('%Y%m%d')
            with transaction.atomic():
                last_rec = (
                    RecurringJournal.objects
                    .select_for_update()
                    .filter(code__startswith=f"{prefix}-{today}")
                    .order_by('-code')
                    .first()
                )
                seq = int(last_rec.code.split('-')[-1]) + 1 if last_rec else 1
                self.code = f"{prefix}-{today}-{seq:03d}"
        super().save(*args, **kwargs)


class RecurringJournalLine(models.Model):
    """Lines for recurring journal template"""
    recurring_journal = models.ForeignKey(RecurringJournal, on_delete=models.CASCADE, related_name='lines', null=True, blank=True)
    account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, null=True, blank=True)
    description = models.CharField(max_length=200, default='')
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.account} - {self.description}"


class RecurringJournalRun(models.Model):
    """Log of generated recurring journals"""
    recurring_journal = models.ForeignKey(RecurringJournal, on_delete=models.CASCADE, related_name='runs', null=True, blank=True)
    journal = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True)
    run_date = models.DateField(default=date.today)
    status = models.CharField(max_length=20, default='Generated')
    error_message = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-run_date']

    def __str__(self):
        return f"{self.recurring_journal} - {self.run_date} ({self.status})"


class Accrual(AuditBaseModel):
    """Accruals - expenses incurred but not yet paid"""
    ACCRUAL_TYPE_CHOICES = [
        ('expense', 'Expense Accrual'),
        ('revenue', 'Revenue Accrual'),
    ]

    name = models.CharField(max_length=100, default='')
    code = models.CharField(max_length=50, unique=True, default='')
    accrual_type = models.CharField(max_length=20, choices=ACCRUAL_TYPE_CHOICES, default='expense')
    account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='accruals', null=True, blank=True)
    counterpart_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='accrual_counterparts', null=True, blank=True)

    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    period = models.ForeignKey('accounting.BudgetPeriod', on_delete=models.CASCADE, null=True, blank=True)

    description = models.TextField(blank=True, default='')
    source_document = models.CharField(max_length=100, blank=True, default='')

    # Posting and reversal dates
    posting_date = models.DateField(default=date.today, help_text="Date when the accrual journal will be posted")
    reversal_date = models.DateField(null=True, blank=True, help_text="Date when the reversal will be posted")

    # Auto-reverse options
    is_reversed = models.BooleanField(default=False)
    reversal_journal = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='reversed_accruals')
    auto_reverse = models.BooleanField(default=True, help_text="Auto-reverse in next period")
    auto_reverse_on_month_start = models.BooleanField(default=True, help_text="Automatically reverse on the 1st day of the next month")
    use_default_dates = models.BooleanField(default=False, help_text="Auto-calculate posting date (month-end) and reversal date (1st of next month)")

    is_posted = models.BooleanField(default=False)
    journal_entry = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='accrual_entries')

    # Link to recurring journal (optional)
    recurring_journal = models.ForeignKey(RecurringJournal, on_delete=models.SET_NULL, null=True, blank=True, related_name='accruals')

    class Meta:
        ordering = ['-period']

    def __str__(self):
        return f"{self.code} - {self.name} - {self.amount}"

    def save(self, *args, **kwargs):
        if not self.code:
            from datetime import datetime
            today = datetime.now().strftime('%Y%m%d')
            with transaction.atomic():
                last_accrual = (
                    Accrual.objects
                    .select_for_update()
                    .filter(code__startswith=f"ACR-{today}")
                    .order_by('-code')
                    .first()
                )
                seq = int(last_accrual.code.split('-')[-1]) + 1 if last_accrual else 1
                self.code = f"ACR-{today}-{seq:03d}"

        # Auto-calculate dates if use_default_dates is True
        if self.use_default_dates and not self.posting_date:
            from accounting.utils import get_month_end_date, get_next_month_first_day
            self.posting_date = get_month_end_date()
            self.reversal_date = get_next_month_first_day()

        super().save(*args, **kwargs)


class Deferral(AuditBaseModel):
    """Deferrals - expenses paid in advance or revenue received in advance"""
    DEFERRAL_TYPE_CHOICES = [
        ('prepaid_expense', 'Prepaid Expense'),
        ('deferred_revenue', 'Deferred Revenue'),
    ]

    name = models.CharField(max_length=100, default='')
    code = models.CharField(max_length=50, unique=True, default='')
    deferral_type = models.CharField(max_length=20, choices=DEFERRAL_TYPE_CHOICES, default='prepaid_expense')
    account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='deferrals', null=True, blank=True)
    counterpart_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='deferral_counterparts', null=True, blank=True)

    original_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    recognition_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    start_date = models.DateField(default=date.today, help_text="Date when the deferral starts")
    recognition_periods = models.IntegerField(default=1)
    current_period = models.IntegerField(default=0)

    # Auto-recognition options
    auto_recognize = models.BooleanField(default=True, help_text="Auto-recognize each period")
    auto_recognize_on_month_start = models.BooleanField(default=True, help_text="Automatically recognize on the 1st day of each month")

    description = models.TextField(blank=True, default='')
    source_document = models.CharField(max_length=100, blank=True, default='')

    is_active = models.BooleanField(default=True)
    is_fully_recognized = models.BooleanField(default=False)

    # Link to recurring journal (optional)
    recurring_journal = models.ForeignKey(RecurringJournal, on_delete=models.SET_NULL, null=True, blank=True, related_name='deferrals')

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.code} - {self.name} - {self.remaining_amount} remaining"

    def save(self, *args, **kwargs):
        if not self.code:
            from datetime import datetime
            today = datetime.now().strftime('%Y%m%d')
            with transaction.atomic():
                last_deferral = (
                    Deferral.objects
                    .select_for_update()
                    .filter(code__startswith=f"DEF-{today}")
                    .order_by('-code')
                    .first()
                )
                seq = int(last_deferral.code.split('-')[-1]) + 1 if last_deferral else 1
                self.code = f"DEF-{today}-{seq:03d}"
        super().save(*args, **kwargs)


class DeferralRecognition(models.Model):
    """Recognition entries for deferrals"""
    deferral = models.ForeignKey(Deferral, on_delete=models.CASCADE, related_name='recognitions', null=True, blank=True)
    period = models.ForeignKey('accounting.BudgetPeriod', on_delete=models.CASCADE, null=True, blank=True)
    recognition_date = models.DateField(default=date.today)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    journal_entry = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True)
    is_posted = models.BooleanField(default=False)

    class Meta:
        ordering = ['recognition_date']

    def __str__(self):
        return f"{self.deferral} - {self.recognition_date} ({self.amount})"


class PeriodStatus(AuditBaseModel):
    """Track period opening and closing status"""
    period = models.OneToOneField('accounting.BudgetPeriod', on_delete=models.CASCADE, related_name='period_status')

    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('Closed', 'Closed'),
        ('Locked', 'Locked'),
        ('YearEnd', 'Year-End Processing'),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='periods_closed_by')
    closed_date = models.DateTimeField(null=True, blank=True)
    lock_reason = models.TextField(blank=True, default='')

    allow_journal_entry = models.BooleanField(default=True)
    allow_invoice = models.BooleanField(default=True)
    allow_payment = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.period} - {self.status}"


class CurrencyRevaluation(AuditBaseModel):
    """Foreign currency revaluation records"""
    revaluation_date = models.DateField(default=date.today)
    currency = models.ForeignKey('accounting.Currency', on_delete=models.CASCADE, null=True, blank=True)

    exchange_rate = models.DecimalField(max_digits=15, decimal_places=6, default=1)

    total_assets = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_liabilities = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    unrealized_gain = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    unrealized_loss = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Calculated', 'Calculated'),
        ('Posted', 'Posted'),
        ('Reversed', 'Reversed'),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    journal_entry = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='revaluations')

    class Meta:
        ordering = ['-revaluation_date']

    def __str__(self):
        return f"Revaluation {self.currency} - {self.revaluation_date}"


class RetainedEarnings(AuditBaseModel):
    """Track retained earnings by year"""
    fiscal_year = models.IntegerField(unique=True, default=0)
    beginning_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_income = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    dividends = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    ending_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    closing_journal = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-fiscal_year']

    def __str__(self):
        return f"Retained Earnings {self.fiscal_year}: {self.ending_balance}"


class AccountingSettings(models.Model):
    """Per-tenant accounting configuration (singleton per schema)."""
    DIGIT_CHOICES = [(i, str(i)) for i in range(4, 11)]

    # Default number series mapping: first digit(s) of account code → account type.
    # get_expected_type_for_code() tries longest prefix first (up to 4 chars),
    # so '901' overrides '90' which overrides '9'.
    DEFAULT_NUMBER_SERIES = {
        '1':   'Asset',
        '2':   'Liability',
        '3':   'Equity',
        '4':   'Income',
        '5':   'Expense',
        '6':   'Expense',
        '7':   'Expense',
        '8':   'Expense',
        # 901x-904x — Service Revenue sub-accounts (Income) e.g. 90100000-90400000
        '901': 'Income',
        '902': 'Income',
        '903': 'Income',
        '904': 'Income',
        # 90x (catches 905x-909x service costs), 91x-92x service/quality costs
        '90':  'Expense',
        # 95x — Capital/Fixed Asset module accounts
        '95':  'Asset',
        # All other 9x ranges default to Expense
        '9':   'Expense',
    }

    account_code_digits = models.IntegerField(choices=DIGIT_CHOICES, default=8)
    is_digit_enforcement_active = models.BooleanField(default=False)
    account_number_series = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Maps account code prefix to account type. '
            'E.g. {"1": "Asset", "2": "Liability", "3": "Equity", "4": "Income", "5": "Expense"}'
        ),
    )

    # Default currencies (up to 4 slots)
    default_currency_1 = models.ForeignKey(
        'accounting.Currency', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='settings_slot1',
        help_text='Local / base currency',
    )
    default_currency_2 = models.ForeignKey(
        'accounting.Currency', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='settings_slot2',
        help_text='Document currency',
    )
    default_currency_3 = models.ForeignKey(
        'accounting.Currency', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='settings_slot3',
        help_text='Reporting currency (optional)',
    )
    default_currency_4 = models.ForeignKey(
        'accounting.Currency', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='settings_slot4',
        help_text='Reporting currency (optional)',
    )

    # ── Sales Downpayment ──────────────────────────────────────
    enable_sales_downpayment = models.BooleanField(
        default=False,
        help_text='Allow downpayment requests to be created on sales orders',
    )
    downpayment_default_type = models.CharField(
        max_length=20,
        choices=[('percentage', 'Percentage'), ('amount', 'Fixed Amount')],
        default='percentage',
        help_text='Default calculation type for sales downpayment requests',
    )
    downpayment_default_value = models.DecimalField(
        max_digits=10, decimal_places=4, default=30,
        help_text='Default downpayment percentage or amount',
    )
    downpayment_gl_account = models.ForeignKey(
        'accounting.Account', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='downpayment_settings',
        help_text='GL account to credit when a customer downpayment is posted',
    )

    class Meta:
        verbose_name = 'Accounting Settings'
        verbose_name_plural = 'Accounting Settings'

    def save(self, *args, **kwargs):
        # Populate default number series if empty
        if not self.account_number_series:
            self.account_number_series = dict(self.DEFAULT_NUMBER_SERIES)
        super().save(*args, **kwargs)

    def get_number_series(self):
        """Return the active number series mapping (prefix → account_type)."""
        return self.account_number_series or dict(self.DEFAULT_NUMBER_SERIES)

    def get_expected_type_for_code(self, code):
        """Return the expected account type for a given account code, or None if no match."""
        series = self.get_number_series()
        # Try longest prefix first for specificity (e.g. '10' before '1')
        for length in range(min(len(code), 4), 0, -1):
            prefix = code[:length]
            if prefix in series:
                return series[prefix]
        return None

    def validate_account_code(self, code, account_type):
        """
        Validate an account code against digit enforcement and number series.
        Returns (is_valid, error_message).
        """
        errors = []

        # Digit enforcement
        if self.is_digit_enforcement_active:
            if not code.isdigit():
                errors.append(f"Account code must contain only digits when digit enforcement is active.")
            if len(code) != self.account_code_digits:
                errors.append(
                    f"Account code must be exactly {self.account_code_digits} digits "
                    f"(got {len(code)})."
                )

        # Number series validation
        if self.account_number_series and code:
            expected_type = self.get_expected_type_for_code(code)
            if expected_type and expected_type != account_type:
                errors.append(
                    f"Account code '{code}' belongs to the "
                    f"'{expected_type}' number series (prefix '{code[0]}'), "
                    f"but account type is '{account_type}'."
                )

        if errors:
            return False, errors
        return True, []

    def __str__(self):
        return f"Accounting Settings (digits={self.account_code_digits}, enforced={self.is_digit_enforcement_active})"


class CurrencyRevaluationRun(models.Model):
    """Tracks each currency revaluation execution."""

    revaluation_date = models.DateField()
    fiscal_period = models.ForeignKey('accounting.FiscalPeriod', on_delete=models.PROTECT, null=True, blank=True)

    currencies_processed = models.JSONField(default=list)
    total_gain = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_loss = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_effect = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    journals_created = models.JSONField(default=list)

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('CALCULATED', 'Calculated'),
        ('POSTED', 'Posted'),
        ('REVERSED', 'Reversed'),
        ('FAILED', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='revaluations_posted')

    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-revaluation_date']

    def __str__(self):
        return f"Revaluation {self.revaluation_date} ({self.status})"


class CurrencyRevaluationDetail(models.Model):
    """Details of revaluation for each currency/account combination."""

    run = models.ForeignKey(CurrencyRevaluationRun, on_delete=models.CASCADE, related_name='details')
    currency = models.ForeignKey('accounting.Currency', on_delete=models.PROTECT)

    account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, null=True, blank=True)

    exchange_rate_before = models.DecimalField(max_digits=15, decimal_places=6, default=1)
    exchange_rate_after = models.DecimalField(max_digits=15, decimal_places=6, default=1)

    balance_in_currency = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    balance_in_base = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    revalued_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    gain_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    loss_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    journal_line_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['currency', 'account']

    def __str__(self):
        return f"{self.currency} - {self.account} ({self.gain_amount - self.loss_amount})"


class CostAllocationRun(models.Model):
    """Tracks each cost allocation execution."""

    run_date = models.DateField()
    fiscal_period = models.ForeignKey('accounting.FiscalPeriod', on_delete=models.PROTECT, null=True, blank=True)
    fiscal_year = models.IntegerField(default=0)
    period = models.IntegerField(default=0)

    rules_processed = models.IntegerField(default=0)
    total_allocated = models.DecimalField(max_digits=15, decimal_places=2, default=0)

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
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='allocations_posted')

    class Meta:
        ordering = ['-run_date']

    def __str__(self):
        return f"Cost Allocation {self.run_date} ({self.status})"


class CostAllocationDetail(models.Model):
    """Details of allocation for each rule/target."""

    run = models.ForeignKey(CostAllocationRun, on_delete=models.CASCADE, related_name='details')

    rule = models.ForeignKey('accounting.CostAllocationRule', on_delete=models.PROTECT, null=True, blank=True)
    rule_name = models.CharField(max_length=100, blank=True, default='')

    source_cost_center = models.ForeignKey('accounting.CostCenter', on_delete=models.PROTECT, null=True, blank=True, related_name='allocation_sources')
    source_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, null=True, blank=True, related_name='allocation_sources')
    source_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    target_cost_center = models.ForeignKey('accounting.CostCenter', on_delete=models.PROTECT, null=True, blank=True, related_name='allocation_targets')
    target_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, null=True, blank=True, related_name='allocation_targets')
    allocated_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    allocation_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    journal_line_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['rule_name', 'target_cost_center']

    def __str__(self):
        return f"{self.source_cost_center} -> {self.target_cost_center}: {self.allocated_amount}"


class XBRLReport(models.Model):
    """Stores generated XBRL reports."""

    report_type = models.CharField(max_length=50, default='')
    report_name = models.CharField(max_length=200, default='')

    fiscal_year = models.IntegerField(default=0)
    period_start = models.DateField(default=date.today)
    period_end = models.DateField(default=date.today)

    taxonomy = models.CharField(max_length=100, default='DTSG-GAAP')

    content = models.TextField()
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    file_format = models.CharField(max_length=10, default='XHTML')
    file_size = models.IntegerField(default=0)

    class Meta:
        ordering = ['-generated_at']

    def __str__(self):
        return f"{self.report_name} FY{self.fiscal_year}"


class PettyCashFund(models.Model):
    """Petty cash fund management."""

    name = models.CharField(max_length=100, default='')
    code = models.CharField(max_length=20, unique=True, default='')

    bank_account = models.ForeignKey('accounting.BankAccount', on_delete=models.PROTECT, related_name='petty_cash_accounts', null=True, blank=True)
    float_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    custodian = models.ForeignKey(User, on_delete=models.PROTECT, related_name='petty_cash_custodian', null=True, blank=True)

    is_active = models.BooleanField(default=True)
    minimum_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.name} - {self.current_balance}"


class PettyCashVoucher(models.Model):
    """Petty cash payment vouchers."""

    voucher_number = models.CharField(max_length=50, unique=True, default='')
    petty_cash_fund = models.ForeignKey(PettyCashFund, on_delete=models.PROTECT, related_name='vouchers', null=True, blank=True)

    voucher_date = models.DateField(default=date.today)

    payee = models.CharField(max_length=200, default='')
    description = models.TextField(default='')

    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='petty_cash_vouchers', null=True, blank=True)
    cost_center = models.ForeignKey('accounting.CostCenter', on_delete=models.PROTECT, null=True, blank=True)

    APPROVAL_STATUS = [
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('PAID', 'Paid'),
    ]
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS, default='PENDING')

    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='petty_cash_approved')
    approved_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='petty_cash_created')
    created_at = models.DateTimeField(default=timezone.now)

    receipt_attached = models.BooleanField(default=False)

    journal_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-voucher_date']
        indexes = [
            models.Index(fields=['petty_cash_fund', 'voucher_date']),
        ]

    def __str__(self):
        return f"PCV {self.voucher_number} - {self.amount}"


class PettyCashReplenishment(models.Model):
    """Petty cash replenishment records."""

    replenishment_number = models.CharField(max_length=50, unique=True)
    petty_cash_fund = models.ForeignKey(PettyCashFund, on_delete=models.PROTECT, related_name='replenishments')

    replenishment_date = models.DateField()

    vouchers_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    reimbursement_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    bank_account = models.ForeignKey('accounting.BankAccount', on_delete=models.PROTECT, related_name='petty_replenishments')

    vouchers = models.JSONField(default=list)

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('APPROVED', 'Approved'),
        ('POSTED', 'Posted'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    journal_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-replenishment_date']

    def __str__(self):
        return f"Replenishment {self.replenishment_number}"


class ChequeRegister(models.Model):
    """Cheque issuance and tracking register."""

    cheque_number = models.CharField(max_length=50, default='')
    bank_account = models.ForeignKey('accounting.BankAccount', on_delete=models.PROTECT, related_name='cheques', null=True, blank=True)

    CHEQUE_TYPE_CHOICES = [
        ('CASH', 'Cash Cheque'),
        ('PAYMENT', 'Payment Cheque'),
        ('POSTDATED', 'Post-Dated'),
    ]
    cheque_type = models.CharField(max_length=20, choices=CHEQUE_TYPE_CHOICES, default='PAYMENT')

    payee = models.CharField(max_length=200, default='')
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    issue_date = models.DateField(default=date.today)
    presentation_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    reference_document = models.CharField(max_length=50, blank=True, default='')

    STATUS_CHOICES = [
        ('ISSUED', 'Issued'),
        ('PRESENTED', 'Presented'),
        ('PAID', 'Paid'),
        ('BOUNCED', 'Bounced'),
        ('CANCELLED', 'Cancelled'),
        ('STOPPED', 'Stopped'),
        ('EXPIRED', 'Expired'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ISSUED')

    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cheques_issued')
    presented_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cheques_presented')
    presented_at = models.DateTimeField(null=True, blank=True)

    bounce_reason = models.TextField(blank=True, default='')
    stop_reason = models.TextField(blank=True, default='')

    journal_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-issue_date']
        unique_together = ['bank_account', 'cheque_number']
        indexes = [
            models.Index(fields=['payee', 'status']),
        ]

    def __str__(self):
        return f"Cheque {self.cheque_number} - {self.payee}"


class PaymentVoucher(models.Model):
    """Payment voucher for authorization workflow."""

    voucher_number = models.CharField(max_length=50, unique=True)

    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'Cash'),
        ('CHEQUE', 'Cheque'),
        ('TRANSFER', 'Bank Transfer'),
        ('EFT', 'Electronic Fund Transfer'),
    ]
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='TRANSFER')

    bank_account = models.ForeignKey('accounting.BankAccount', on_delete=models.PROTECT, null=True, blank=True)
    cheque_number = models.CharField(max_length=50, blank=True, default='')

    payee_type = models.CharField(max_length=20, blank=True, default='')
    payee_id = models.IntegerField(null=True, blank=True)
    payee_name = models.CharField(max_length=200, default='')

    voucher_date = models.DateField(default=date.today)
    payment_date = models.DateField(null=True, blank=True)

    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency_code = models.CharField(max_length=3, default='NGN')

    description = models.TextField(default='')

    account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='payment_vouchers', null=True, blank=True)
    cost_center = models.ForeignKey('accounting.CostCenter', on_delete=models.PROTECT, null=True, blank=True)

    reference_number = models.CharField(max_length=50, blank=True, default='')

    APPROVAL_STATUS = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
    ]
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS, default='PENDING')

    approvers = models.JSONField(default=list)
    approval_history = models.JSONField(default=list)

    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='pv_approved')
    approved_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='pv_created')
    created_at = models.DateTimeField(default=timezone.now)

    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='pv_posted')

    is_reconciled = models.BooleanField(default=False)
    reconciliation_date = models.DateField(null=True, blank=True)

    journal_id = models.IntegerField(null=True, blank=True)

    attachments = models.JSONField(default=list)

    class Meta:
        ordering = ['-voucher_date']
        indexes = [
            models.Index(fields=['payee_name', 'voucher_date']),
            models.Index(fields=['approval_status']),
        ]

    def __str__(self):
        return f"PV {self.voucher_number} - {self.payee_name} - {self.amount}"


class BankStatement(models.Model):
    """Imported bank statement."""

    bank_account = models.ForeignKey(
        'accounting.BankAccount',
        on_delete=models.CASCADE,
        related_name='statements'
    )
    statement_number = models.CharField(max_length=50)
    statement_date = models.DateField()
    start_date = models.DateField()
    end_date = models.DateField()
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    closing_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency_code = models.CharField(max_length=3, default='USD')

    import_date = models.DateTimeField(auto_now_add=True)
    imported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    file_name = models.CharField(max_length=255, blank=True, default='')

    STATUS_CHOICES = [
        ('IMPORTED', 'Imported'),
        ('PROCESSING', 'Processing'),
        ('RECONCILED', 'Reconciled'),
        ('FAILED', 'Import Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IMPORTED')

    class Meta:
        ordering = ['-statement_date']
        unique_together = ['bank_account', 'statement_number']

    def __str__(self):
        return f"{self.bank_account} - {self.statement_number} ({self.statement_date})"


class BankStatementLine(models.Model):
    """Individual line from a bank statement."""

    statement = models.ForeignKey(BankStatement, on_delete=models.CASCADE, related_name='lines')
    line_number = models.IntegerField()
    transaction_date = models.DateField()
    value_date = models.DateField(null=True, blank=True)
    description = models.TextField()
    reference = models.CharField(max_length=100, blank=True, default='')
    debit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    transaction_type = models.CharField(max_length=50, blank=True, default='')

    MATCH_STATUS_CHOICES = [
        ('UNMATCHED', 'Unmatched'),
        ('MATCHED', 'Matched'),
        ('MANUAL', 'Manually Matched'),
        ('DISPUTED', 'Disputed'),
    ]
    match_status = models.CharField(max_length=20, choices=MATCH_STATUS_CHOICES, default='UNMATCHED')
    matched_transaction_type = models.CharField(max_length=20, blank=True, default='')
    matched_transaction_id = models.IntegerField(null=True, blank=True)
    matched_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['transaction_date', 'line_number']

    @property
    def amount(self):
        return self.debit_amount or self.credit_amount

    @property
    def is_credit(self):
        return self.credit_amount > 0

    def __str__(self):
        return f"{self.transaction_date} - {self.description[:30]}"


class CashFlowEntry(models.Model):
    """Cash flow statement entries."""

    fiscal_year = models.IntegerField(default=0)
    period = models.IntegerField(default=0)
    entry_date = models.DateField(default=date.today)

    CASH_FLOW_TYPE_CHOICES = [
        ('OPERATING', 'Operating Activities'),
        ('INVESTING', 'Investing Activities'),
        ('FINANCING', 'Financing Activities'),
    ]
    cash_flow_type = models.CharField(max_length=20, choices=CASH_FLOW_TYPE_CHOICES, default='OPERATING')

    account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='cash_flow_entries', null=True, blank=True)
    account_code = models.CharField(max_length=20, default='')
    account_name = models.CharField(max_length=200, default='')

    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    description = models.TextField(blank=True, default='')

    journal_id = models.IntegerField(null=True, blank=True)

    fiscal_period = models.ForeignKey('accounting.FiscalPeriod', on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ['-entry_date']
        indexes = [
            models.Index(fields=['fiscal_year', 'period', 'cash_flow_type']),
        ]

    def __str__(self):
        return f"{self.cash_flow_type} - {self.account_code}"
