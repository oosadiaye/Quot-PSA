from datetime import date
from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from core.models import AuditBaseModel, ImmutableModelMixin
from django.contrib.auth.models import User


class Company(models.Model):
    """Company/Entity master data - shared across all modules"""
    COMPANY_TYPE_CHOICES = [
        ('Holding', 'Holding Company'),
        ('Subsidiary', 'Subsidiary'),
        ('Branch', 'Branch'),
        ('Division', 'Division'),
    ]

    name = models.CharField(max_length=200, default='')
    company_code = models.CharField(max_length=20, unique=True, default='')
    company_type = models.CharField(max_length=20, choices=COMPANY_TYPE_CHOICES, default='Subsidiary')
    parent_company = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subsidiaries')
    registration_number = models.CharField(max_length=50, blank=True, default='')
    tax_id = models.CharField(max_length=50, blank=True, default='')
    currency = models.ForeignKey('accounting.Currency', on_delete=models.PROTECT, related_name='companies', null=True, blank=True)
    address = models.TextField(blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    is_internal = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company_code']

    def __str__(self):
        return f"{self.company_code} - {self.name}"


class InterCompanyConfig(models.Model):
    """Configuration for inter-company relationships"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='ic_configs', null=True, blank=True)
    partner_company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='partner_configs', null=True, blank=True)
    ar_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='ic_ar_configs', null=True, blank=True)
    ap_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='ic_ap_configs', null=True, blank=True)
    expense_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='ic_expense_configs', null=True, blank=True)
    revenue_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='ic_revenue_configs', null=True, blank=True)
    auto_post = models.BooleanField(default=True)
    auto_match = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['company', 'partner_company']

    def __str__(self):
        return f"{self.company.name} ↔ {self.partner_company.name}"


class InterCompanyInvoice(models.Model):
    """IC Invoice - Sale from one company to another"""
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Sent', 'Sent'),
        ('Approved', 'Approved'),
        ('Paid', 'Paid'),
        ('Cancelled', 'Cancelled'),
    ]

    invoice_number = models.CharField(max_length=50, unique=True, default='')
    from_company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='ic_sales', null=True, blank=True)
    to_company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='ic_purchases', null=True, blank=True)
    invoice_date = models.DateField(default=date.today)
    due_date = models.DateField(default=date.today)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.ForeignKey('accounting.Currency', on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    description = models.TextField(blank=True, default='')
    auto_posted = models.BooleanField(default=False)
    linked_journal = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='ic_invoices')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-invoice_date']

    def __str__(self):
        return f"IC-{self.invoice_number} ({self.from_company.company_code} → {self.to_company.company_code})"


class InterCompanyTransfer(models.Model):
    """Transfer inventory between companies"""
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Transit', 'In Transit'),
        ('Received', 'Received'),
        ('Cancelled', 'Cancelled'),
    ]

    transfer_number = models.CharField(max_length=50, unique=True, default='')
    from_company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='ic_issues', null=True, blank=True)
    to_company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='ic_receipts', null=True, blank=True)
    transfer_date = models.DateField(default=date.today)
    items = models.JSONField(default=list)
    total_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    auto_posted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        """INT-13: Validate that items JSONField entries have required structure."""
        super().clean()
        if self.items:
            for idx, item in enumerate(self.items):
                if not isinstance(item, dict) or 'description' not in item or 'amount' not in item:
                    raise ValidationError(
                        f"Item at index {idx} must be a dict with 'description' and 'amount' fields."
                    )

    def __str__(self):
        return f"IC-TRANS-{self.transfer_number}"


class InterCompanyAllocation(models.Model):
    """Allocate expenses across companies"""
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Approved', 'Approved'),
        ('Posted', 'Posted'),
    ]

    allocation_number = models.CharField(max_length=50, unique=True, default='')
    source_company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='allocations_out', null=True, blank=True)
    allocation_date = models.DateField(default=date.today)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.ForeignKey('accounting.Currency', on_delete=models.PROTECT, null=True, blank=True)
    allocation_method = models.CharField(max_length=20, choices=[
        ('Percentage', 'Percentage'),
        ('Equal', 'Equal'),
        ('Custom', 'Custom'),
    ], default='Percentage')
    allocations = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    auto_posted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"IC-ALLOC-{self.allocation_number}"


class InterCompanyCashTransfer(models.Model):
    """Transfer cash between companies"""
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Transit', 'In Transit'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]

    transfer_number = models.CharField(max_length=50, unique=True, default='')
    from_company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='cash_transfers_out', null=True, blank=True)
    to_company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='cash_transfers_in', null=True, blank=True)
    transfer_date = models.DateField(default=date.today)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.ForeignKey('accounting.Currency', on_delete=models.PROTECT, null=True, blank=True)
    exchange_rate = models.DecimalField(max_digits=15, decimal_places=6, default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    auto_posted = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"IC-CASH-{self.transfer_number}"


class ConsolidationGroup(models.Model):
    """Group of companies for consolidation"""
    CONSOLIDATION_METHOD_CHOICES = [
        ('Full', 'Full Consolidation'),
        ('Line-by-Line', 'Line-by-Line'),
        ('Equity', 'Equity Method'),
    ]

    name = models.CharField(max_length=100, default='')
    companies = models.ManyToManyField(Company, related_name='consolidation_groups')
    consolidation_method = models.CharField(max_length=20, choices=CONSOLIDATION_METHOD_CHOICES, default='Full')
    reporting_currency = models.ForeignKey('accounting.Currency', on_delete=models.PROTECT, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ConsolidationRun(models.Model):
    """Each consolidation execution"""
    STATUS_CHOICES = [
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
    ]

    group = models.ForeignKey(ConsolidationGroup, on_delete=models.CASCADE, related_name='runs', null=True, blank=True)
    period = models.ForeignKey('accounting.FiscalPeriod', on_delete=models.PROTECT, null=True, blank=True)
    run_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='In Progress')
    total_assets = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_liabilities = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_equity = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_expenses = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    elimination_entries = models.JSONField(default=list)
    consolidated_data = models.JSONField(default=dict)
    error_message = models.TextField(blank=True, default='')
    run_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-run_date']

    def __str__(self):
        return f"{self.group.name} - {self.period}"


class InterCompany(models.Model):
    name = models.CharField(max_length=100, default='')
    company_code = models.CharField(max_length=20, default='')
    default_currency = models.ForeignKey('accounting.Currency', on_delete=models.PROTECT, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['company_code']

    def __str__(self):
        return f"{self.company_code} - {self.name}"


class InterCompanyAccountMapping(models.Model):
    inter_company = models.ForeignKey(InterCompany, on_delete=models.CASCADE, null=True, blank=True)
    local_account = models.ForeignKey('accounting.Account', on_delete=models.CASCADE, related_name='inter_company_mappings', null=True, blank=True)
    counterpart_account = models.CharField(max_length=50, default='')

    class Meta:
        unique_together = ['inter_company', 'local_account']

    def __str__(self):
        return f"{self.local_account} -> {self.counterpart_account}"


class InterCompanyTransaction(models.Model):
    inter_company = models.ForeignKey(InterCompany, on_delete=models.CASCADE, null=True, blank=True)
    transaction_type = models.CharField(max_length=20, default='')
    transaction_date = models.DateField(default=date.today)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.ForeignKey('accounting.Currency', on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=20, default='Pending')
    description = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-transaction_date']

    def __str__(self):
        return f"{self.transaction_type} - {self.transaction_date} ({self.amount})"


class InterCompanyElimination(models.Model):
    period = models.ForeignKey('accounting.BudgetPeriod', on_delete=models.CASCADE, null=True, blank=True)
    elimination_date = models.DateField(default=date.today)
    total_elimination = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=20, default='Draft')

    def __str__(self):
        return f"Elimination {self.elimination_date} ({self.status})"


class Consolidation(models.Model):
    group = models.ForeignKey(ConsolidationGroup, on_delete=models.CASCADE, null=True, blank=True)
    period = models.ForeignKey('accounting.BudgetPeriod', on_delete=models.CASCADE, null=True, blank=True)
    consolidation_date = models.DateField(default=date.today)
    status = models.CharField(max_length=20, default='Draft')
    total_assets = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_liabilities = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_equity = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        ordering = ['-consolidation_date']

    def __str__(self):
        return f"Consolidation {self.consolidation_date} ({self.status})"
