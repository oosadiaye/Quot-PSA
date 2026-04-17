from datetime import date
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class TaxRegistration(models.Model):
    tax_type = models.CharField(max_length=20, default='')
    registration_number = models.CharField(max_length=50, default='')
    effective_date = models.DateField(default=date.today)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['tax_type']

    def __str__(self):
        return f"{self.tax_type} - {self.registration_number}"


class TaxExemption(models.Model):
    tax_registration = models.ForeignKey(TaxRegistration, on_delete=models.CASCADE, null=True, blank=True)
    entity_name = models.CharField(max_length=200, blank=True, default='',
        help_text="Exempt entity name (replaces FK to deleted sales.Customer)")
    vendor = models.ForeignKey('procurement.Vendor', on_delete=models.CASCADE, null=True, blank=True)
    exemption_certificate = models.CharField(max_length=50, default='')
    valid_from = models.DateField(default=date.today)
    valid_until = models.DateField(default=date.today)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.exemption_certificate


class TaxReturn(models.Model):
    tax_registration = models.ForeignKey(TaxRegistration, on_delete=models.CASCADE, null=True, blank=True)
    period_start = models.DateField(default=date.today)
    period_end = models.DateField(default=date.today)
    status = models.CharField(max_length=20, default='Draft')
    tax_type = models.CharField(max_length=20, default='')
    output_tax = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    input_tax = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_due = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        ordering = ['-period_end']

    def __str__(self):
        return f"{self.tax_type} Return {self.period_start} - {self.period_end}"


class WithholdingTax(models.Model):
    code = models.CharField(max_length=20, unique=True, db_index=True, default='')
    name = models.CharField(max_length=150, default='')
    income_type = models.CharField(max_length=50, default='')
    rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    withholding_account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT, null=True, blank=True,
        related_name='withholding_tax_codes',
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} — {self.name}"


class TaxCode(models.Model):
    TAX_TYPE_CHOICES = [
        ('vat', 'VAT'),
        ('sales_tax', 'Sales Tax'),
        ('service_tax', 'Service Tax'),
        ('excise_duty', 'Excise Duty'),
        ('customs_duty', 'Customs Duty'),
    ]
    DIRECTION_CHOICES = [
        ('purchase', 'Purchase (Input)'),
        ('sales', 'Sales (Output)'),
        ('both', 'Both'),
    ]

    code = models.CharField(max_length=20, unique=True, db_index=True, default='')
    name = models.CharField(max_length=150, default='')
    tax_type = models.CharField(max_length=20, choices=TAX_TYPE_CHOICES, db_index=True, default='')
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, db_index=True, default='')
    rate = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    tax_account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT, related_name='tax_codes', null=True, blank=True)
    input_tax_account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT,
        related_name='input_tax_codes', null=True, blank=True,
        help_text='GL account for input/purchase tax (e.g. Input VAT Receivable)',
    )
    output_tax_account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT,
        related_name='output_tax_codes', null=True, blank=True,
        help_text='GL account for output/sales tax (e.g. Output VAT Payable)',
    )
    is_active = models.BooleanField(default=True, db_index=True)
    description = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} — {self.name} ({self.rate}%)"


class TaxRate(models.Model):
    """Defines VAT and other tax rates per FIRS requirements."""

    TAX_TYPE_CHOICES = [
        ('VAT', 'Value Added Tax'),
        ('WHT', 'Withholding Tax'),
        ('ST', 'Sales Tax'),
        ('EXC', 'Excise Duty'),
        ('CET', 'Customs & Excise'),
    ]

    name = models.CharField(max_length=100, default='')
    code = models.CharField(max_length=20, unique=True, default='')
    tax_type = models.CharField(max_length=10, choices=TAX_TYPE_CHOICES, default='VAT')
    rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    effective_date = models.DateField(default=date.today)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    applies_to_imports = models.BooleanField(default=False)
    applies_to_domestic = models.BooleanField(default=True)

    account_code = models.CharField(max_length=20, blank=True, default='')

    class Meta:
        ordering = ['tax_type', '-effective_date']

    def __str__(self):
        return f"{self.code} - {self.name}"


class VATReturn(models.Model):
    """VAT Return submissions per FIRS requirements."""

    RETURN_TYPE_CHOICES = [
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
    ]

    period_start = models.DateField(default=date.today)
    period_end = models.DateField(default=date.today)
    return_type = models.CharField(max_length=20, choices=RETURN_TYPE_CHOICES, default='MONTHLY')

    total_output_vat = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_input_vat = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_vat_payable = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_vat_refundable = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    zero_rated_sales = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    exempt_sales = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('ASSESSED', 'Assessed'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    filing_reference = models.CharField(max_length=50, blank=True, default='')
    filing_date = models.DateField(null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='vat_returns')
    created_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-period_end']
        unique_together = ['period_start', 'period_end']

    def __str__(self):
        return f"VAT Return {self.period_start} to {self.period_end}"


class VATReturnDetail(models.Model):
    """Line items for VAT Return."""

    vat_return = models.ForeignKey(VATReturn, on_delete=models.CASCADE, related_name='details')

    DOCUMENT_TYPES = [
        ('VI', 'Vendor Invoice'),
        ('CI', 'Customer Invoice'),
        ('JE', 'Journal Entry'),
    ]
    document_type = models.CharField(max_length=5, choices=DOCUMENT_TYPES, default='JE')
    document_id = models.IntegerField(default=0)
    document_number = models.CharField(max_length=50, default='')
    document_date = models.DateField(default=date.today)

    taxable_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    vat_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    IS_OUTPUT_CHOICES = [
        ('OUTPUT', 'Output VAT'),
        ('INPUT', 'Input VAT'),
    ]
    is_output = models.CharField(max_length=10, choices=IS_OUTPUT_CHOICES, default='OUTPUT')

    tax_code = models.CharField(max_length=20, blank=True, default='')

    counterparty_name = models.CharField(max_length=200, blank=True, default='')
    counterparty_tax_id = models.CharField(max_length=50, blank=True, default='')

    class Meta:
        ordering = ['document_date']

    def __str__(self):
        return f"{self.document_number} - {self.vat_amount}"


class WHTCertificate(models.Model):
    """Withholding Tax Certificates (Form WHT 1A)."""

    CERTIFICATE_TYPE_CHOICES = [
        ('ROYALTY', 'Royalty'),
        ('SERVICE', 'Service Fee'),
        ('RENT', 'Rent'),
        ('DIVIDEND', 'Dividend'),
        ('INTEREST', 'Interest'),
        ('CONTRACT', 'Contract Payment'),
    ]

    certificate_number = models.CharField(max_length=50, unique=True, default='')
    certificate_type = models.CharField(max_length=20, choices=CERTIFICATE_TYPE_CHOICES, default='SERVICE')

    vendor = models.ForeignKey('procurement.Vendor', on_delete=models.PROTECT, null=True, blank=True)
    vendor_name = models.CharField(max_length=200, default='')
    vendor_address = models.TextField(blank=True, default='')
    vendor_tax_id = models.CharField(max_length=50, blank=True, default='')

    certificate_date = models.DateField(default=date.today)
    payment_date = models.DateField(default=date.today)

    invoice_number = models.CharField(max_length=50, blank=True, default='')
    invoice_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    gross_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    withholding_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    withholding_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    nature_of_payment = models.CharField(max_length=200, blank=True, default='')
    contract_reference = models.CharField(max_length=50, blank=True, default='')

    STATUS_CHOICES = [
        ('ISSUED', 'Issued'),
        ('DELIVERED', 'Delivered'),
        ('UTILIZED', 'Utilized'),
        ('CANCELLED', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ISSUED')

    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='wht_certificates')
    issued_at = models.DateTimeField(default=timezone.now)

    fiscal_year = models.IntegerField(default=0)
    period = models.IntegerField(default=0)

    class Meta:
        ordering = ['-certificate_date']
        indexes = [
            models.Index(fields=['vendor', 'fiscal_year']),
            models.Index(fields=['certificate_date']),
        ]

    def __str__(self):
        return f"WHT {self.certificate_number} - {self.withholding_amount}"
