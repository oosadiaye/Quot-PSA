from decimal import Decimal
from django.db import models
from django.conf import settings
from core.models import AuditBaseModel, ImmutableModelMixin, StatusTransitionMixin, quantize_currency
from django.contrib.auth.models import User
from accounting.models import Account, Function, Fund, Geo, Program, MDA, WithholdingTax, TaxCode
from inventory.models import *


class CustomerCategory(AuditBaseModel):
    """
    Customer classification with a pre-configured AR GL account.
    Tenants create categories once (e.g. Corporate, NGO, Retail) and
    assign the correct AR account here — customers inherit it automatically.
    """
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True, default='')
    accounts_receivable_account = models.ForeignKey(
        Account,
        models.PROTECT,
        related_name='customer_category_ar_accounts',
        help_text='AR GL account debited when invoicing customers in this category',
    )

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Customer Categories'

    def __str__(self):
        return f"{self.code} — {self.name}"



class Customer(AuditBaseModel):

    id = models.BigAutoField(primary_key=True)

    PAYMENT_TERMS_CHOICES = [
        ('immediate', 'Due on Receipt (0 days)'),
        ('net_7',  'Net 7 (7 days)'),
        ('net_15', 'Net 15 (15 days)'),
        ('net_30', 'Net 30 (30 days)'),
        ('net_45', 'Net 45 (45 days)'),
        ('net_60', 'Net 60 (60 days)'),
        ('net_90', 'Net 90 (90 days)'),
    ]

    CREDIT_STATUS_CHOICES = [
        ('Good', 'Good Standing'),
        ('Warning', 'Credit Warning'),
        ('Exceeded', 'Credit Exceeded'),
        ('Blocked', 'Credit Blocked'),
    ]

    name = models.CharField(max_length=200)

    customer_code = models.CharField(unique=True, max_length=20)

    vat_number = models.CharField(max_length=50, blank=True, default='')

    credit_limit = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    credit_status = models.CharField(max_length=20, choices=CREDIT_STATUS_CHOICES, default='Good')

    credit_check_enabled = models.BooleanField(default=True)

    credit_warning_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=80.0)

    payment_terms = models.CharField(
        max_length=20,
        choices=PAYMENT_TERMS_CHOICES,
        default='net_30',
        blank=True,
    )

    @property
    def credit_available(self):
        return self.credit_limit - self.balance

    @property
    def credit_status_auto(self):
        if self.balance >= self.credit_limit:
            return "Exceeded"
        elif self.credit_limit > 0 and (self.balance / self.credit_limit * 100) >= self.credit_warning_threshold:
            return "Warning"
        return "Good"



    address = models.TextField(blank=True, default='')

    contact_email = models.EmailField(max_length=254, blank=True, default='')

    contact_person = models.CharField(max_length=200, blank=True, default='')

    contact_phone = models.CharField(max_length=20, blank=True, default='')

    industry = models.CharField(max_length=100, blank=True, default='')

    website = models.CharField(max_length=200, blank=True, default='')


    category = models.ForeignKey(
        CustomerCategory,
        models.PROTECT,
        related_name='customers',
        null=True,
        blank=True,
    )

    # Auto-synced from category on save
    accounts_receivable_account = models.ForeignKey(
        Account, models.PROTECT,
        related_name='customer_ar_accounts',
        blank=True, null=True,
    )

    is_active = models.BooleanField()

    withholding_tax_code = models.ForeignKey(
        WithholdingTax, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='customers',
        help_text='Default WHT code applied to this customer on transactions',
    )
    wht_exempt = models.BooleanField(default=False, help_text='Exempt this customer from withholding tax')

    @property
    def effective_ar_account(self):
        """AR GL account — resolved from category."""
        if self.category_id:
            return self.category.accounts_receivable_account
        return self.accounts_receivable_account

    class Meta:
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['credit_status']),
        ]










class DeliveryNote(AuditBaseModel):

    id = models.BigAutoField(primary_key=True)



    delivery_number = models.CharField(unique=True, max_length=50)

    delivery_date = models.DateField()

    delivered_by = models.CharField(max_length=100)

    status = models.CharField(max_length=20)

    driver_name = models.CharField(max_length=100)

    vehicle_number = models.CharField(max_length=50)

    notes = models.TextField()


    sales_order = models.ForeignKey('SalesOrder', models.PROTECT)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['sales_order']),
            models.Index(fields=['delivery_date']),
        ]











class DeliveryNoteLine(models.Model):

    id = models.BigAutoField(primary_key=True)

    quantity_delivered = models.DecimalField(max_digits=12, decimal_places=2)

    delivery_note = models.ForeignKey(DeliveryNote, models.PROTECT, related_name='lines')

    so_line = models.ForeignKey('SalesOrderLine', models.PROTECT)












class Lead(AuditBaseModel):

    id = models.BigAutoField(primary_key=True)



    name = models.CharField(max_length=200)

    company = models.CharField(max_length=200)

    email = models.CharField(max_length=254)

    phone = models.CharField(max_length=20)

    source = models.CharField(max_length=100)

    status = models.CharField(max_length=20)

    estimated_value = models.DecimalField(max_digits=15, decimal_places=2)

    notes = models.TextField()

    converted_date = models.DateTimeField(blank=True, null=True)

    converted_to_customer = models.ForeignKey(Customer, models.PROTECT, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['source']),
        ]












class Opportunity(AuditBaseModel):

    id = models.BigAutoField(primary_key=True)


    STAGE_CHOICES = [
        ('Prospecting', 'Prospecting'),
        ('Qualification', 'Qualification'),
        ('Proposal', 'Proposal'),
        ('Negotiation', 'Negotiation'),
        ('Closed_Won', 'Closed Won'),
        ('Closed_Lost', 'Closed Lost'),
    ]

    name = models.CharField(max_length=200)

    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='Prospecting')

    stage_duration_days = models.IntegerField(default=0)

    last_stage_change = models.DateTimeField(auto_now=True)

    expected_close_date = models.DateField(blank=True, null=True)

    probability = models.IntegerField()

    expected_value = models.DecimalField(max_digits=15, decimal_places=2)

    notes = models.TextField()


    customer = models.ForeignKey(Customer, models.PROTECT)

    lead = models.ForeignKey(Lead, models.PROTECT, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['stage']),
            models.Index(fields=['customer']),
            models.Index(fields=['expected_close_date']),
        ]











class Quotation(AuditBaseModel):

    id = models.BigAutoField(primary_key=True)



    quotation_number = models.CharField(unique=True, max_length=50)

    quotation_date = models.DateField()

    valid_until = models.DateField()

    status = models.CharField(max_length=20)

    notes = models.TextField()

    terms = models.TextField()


    customer = models.ForeignKey(Customer, models.PROTECT)

    function = models.ForeignKey(Function, models.PROTECT, blank=True, null=True)

    fund = models.ForeignKey(Fund, models.PROTECT, blank=True, null=True)

    geo = models.ForeignKey(Geo, models.PROTECT, blank=True, null=True)

    program = models.ForeignKey(Program, models.PROTECT, blank=True, null=True)


    mda = models.ForeignKey(MDA, models.PROTECT, blank=True, null=True)

    price_list = models.ForeignKey(
        'PriceList', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='quotations'
    )

    tax_code = models.ForeignKey(
        TaxCode, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='quotations',
    )
    wht_exempt = models.BooleanField(default=False, help_text='Exempt this transaction from withholding tax')

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['customer']),
            models.Index(fields=['valid_until']),
        ]










class QuotationLine(models.Model):

    id = models.BigAutoField(primary_key=True)

    item = models.ForeignKey(
        'inventory.Item', on_delete=models.PROTECT, null=True, blank=True,
        related_name='quotation_lines'
    )

    item_description = models.CharField(max_length=255)

    quantity = models.DecimalField(max_digits=12, decimal_places=2)

    unit_price = models.DecimalField(max_digits=15, decimal_places=2)

    discount_percent = models.DecimalField(max_digits=5, decimal_places=2)

    quotation = models.ForeignKey(Quotation, models.PROTECT, related_name='lines')

    @property
    def total_price(self):
        base_price = self.quantity * self.unit_price
        discount = base_price * (self.discount_percent / 100)
        return quantize_currency(base_price - discount)












class SalesOrder(StatusTransitionMixin, AuditBaseModel):
    ALLOWED_TRANSITIONS = {
        'Draft': ['Pending', 'Approved'],
        'Pending': ['Approved', 'Rejected'],
        'Approved': ['Posted', 'Rejected'],
        'Posted': ['Closed'],
        'Rejected': ['Draft'],
        'Closed': [],
    }

    id = models.BigAutoField(primary_key=True)



    status = models.CharField(max_length=20)

    order_number = models.CharField(unique=True, max_length=50)

    order_date = models.DateField()


    customer = models.ForeignKey(Customer, models.PROTECT)

    function = models.ForeignKey(Function, models.PROTECT, blank=True, null=True)

    fund = models.ForeignKey(Fund, models.PROTECT, blank=True, null=True)

    geo = models.ForeignKey(Geo, models.PROTECT, blank=True, null=True)

    program = models.ForeignKey(Program, models.PROTECT, blank=True, null=True)

    revenue_account = models.ForeignKey(Account, models.PROTECT, blank=True, null=True)


    quotation = models.ForeignKey(Quotation, models.PROTECT, blank=True, null=True)

    delivery_address = models.TextField()

    delivery_contact = models.CharField(max_length=100)

    expected_delivery_date = models.DateField(blank=True, null=True)

    mda = models.ForeignKey(MDA, models.PROTECT, blank=True, null=True)

    notes = models.TextField()

    payment_terms = models.CharField(max_length=20)

    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    tax_code = models.ForeignKey(
        TaxCode, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sales_orders',
    )
    wht_exempt = models.BooleanField(default=False, help_text='Exempt this transaction from withholding tax')

    terms_and_conditions = models.TextField()

    linked_purchase_order = models.ForeignKey(
        'procurement.PurchaseOrder', 
        models.PROTECT, 
        blank=True, 
        null=True,
        related_name='linked_sales_orders'
    )

    is_drop_ship = models.BooleanField(default=False)

    drop_ship_vendor = models.ForeignKey(
        'procurement.Vendor',
        models.PROTECT,
        blank=True,
        null=True,
        related_name='drop_ship_orders'
    )

    discount_type = models.CharField(
        max_length=10,
        choices=[('Percentage', 'Percentage'), ('Fixed', 'Fixed Amount')],
        blank=True, null=True,
        help_text="O2C-M1: Order-level discount type"
    )
    discount_value = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="O2C-M1: Discount value (percentage or fixed amount)"
    )
    discount_reason = models.TextField(
        blank=True,
        help_text="O2C-M1: Reason for discount"
    )

    @property
    def discount_amount(self):
        """O2C-M1: Calculate actual discount amount."""
        if not self.discount_type or not self.discount_value:
            return Decimal('0.00')
        subtotal = self.subtotal
        if self.discount_type == 'Percentage':
            return (subtotal * self.discount_value / Decimal('100')).quantize(Decimal('0.01'))
        return min(self.discount_value, subtotal)

    @property
    def subtotal(self):
        return sum(line.total_price for line in self.lines.all())
    
    @property
    def subtotal_after_discount(self):
        """O2C-M1: Subtotal after order-level discount."""
        return self.subtotal - self.discount_amount
    
    @property
    def total_amount(self):
        """O2C-M1: Total including discount and tax."""
        base = self.subtotal_after_discount
        tax = (base * self.tax_rate / Decimal('100')).quantize(Decimal('0.01')) if self.tax_rate else Decimal('0.00')
        return base + tax

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['customer']),
            models.Index(fields=['order_date']),
        ]










class SalesOrderLine(models.Model):

    id = models.BigAutoField(primary_key=True)

    item_description = models.CharField(max_length=255)

    quantity = models.DecimalField(max_digits=12, decimal_places=2)

    unit_price = models.DecimalField(max_digits=15, decimal_places=2)

    order = models.ForeignKey(SalesOrder, models.PROTECT, related_name='lines')

    discount_percent = models.DecimalField(max_digits=5, decimal_places=2)

    item = models.ForeignKey(Item, models.PROTECT, blank=True, null=True)

    product_category = models.ForeignKey(ProductCategory, models.PROTECT, blank=True, null=True)

    product_type = models.ForeignKey(ProductType, models.PROTECT, blank=True, null=True)

    @property
    def total_price(self):
        base_price = self.quantity * self.unit_price
        discount = base_price * (self.discount_percent / 100)
        return quantize_currency(base_price - discount)


class SalesReturn(StatusTransitionMixin, AuditBaseModel):
    """Records goods returned by customers."""
    ALLOWED_TRANSITIONS = {
        'Draft': ['Approved'],
        'Approved': ['Processed', 'Cancelled'],
        'Processed': [],
        'Cancelled': [],
    }
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Approved', 'Approved'),
        ('Processed', 'Processed'),
        ('Cancelled', 'Cancelled'),
    ]

    return_number = models.CharField(max_length=50, unique=True)
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name='returns')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='returns')
    return_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')

    class Meta:
        ordering = ['-return_date']

    def save(self, *args, **kwargs):
        self.validate_status_transition()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.return_number


class SalesReturnLine(models.Model):
    sales_return = models.ForeignKey(SalesReturn, on_delete=models.CASCADE, related_name='lines')
    sales_order_line = models.ForeignKey(SalesOrderLine, on_delete=models.PROTECT)
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT, null=True, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    reason = models.TextField(blank=True, default='')

    @property
    def total_amount(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"Return Line: {self.item or self.sales_order_line.item_description} x {self.quantity}"


class CreditNote(StatusTransitionMixin, AuditBaseModel):
    """Credit notes issued to customers (e.g. after a return or pricing error)."""
    ALLOWED_TRANSITIONS = {
        'Draft': ['Approved'],
        'Approved': ['Applied', 'Cancelled'],
        'Applied': [],
        'Cancelled': [],
    }
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Approved', 'Approved'),
        ('Applied', 'Applied'),
        ('Cancelled', 'Cancelled'),
    ]

    credit_note_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='credit_notes')
    sales_return = models.ForeignKey(
        SalesReturn, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='credit_notes',
    )
    issue_date = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')

    class Meta:
        ordering = ['-issue_date']

    def save(self, *args, **kwargs):
        self.validate_status_transition()
        self.total_amount = quantize_currency(self.amount + self.tax_amount)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.credit_note_number} - {self.customer}"


class PriceList(AuditBaseModel):
    """Named price list (e.g. Retail, Wholesale, VIP)."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default='')
    currency = models.ForeignKey(
        'accounting.Currency', on_delete=models.PROTECT, null=True, blank=True,
    )
    is_active = models.BooleanField(default=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class PriceListItem(models.Model):
    """Per-item pricing within a price list."""
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey('inventory.Item', on_delete=models.CASCADE, related_name='price_list_entries')
    unit_price = models.DecimalField(max_digits=19, decimal_places=4)
    min_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        unique_together = ['price_list', 'item', 'min_quantity']
        ordering = ['price_list', 'item', 'min_quantity']

    def __str__(self):
        return f"{self.price_list.name}: {self.item.name} @ {self.unit_price}"







