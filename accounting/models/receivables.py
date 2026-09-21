from datetime import date
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from core.models import AuditBaseModel, ImmutableModelMixin
from django.contrib.auth.models import User
from accounting.models.gl import SoftDeleteMixin, SoftDeleteManager


def tenant_upload_path(instance, filename):
    """Generate a tenant-aware upload path for file fields."""
    from django.db import connection
    schema = getattr(connection, 'schema_name', 'public')
    return f'tenants/{schema}/documents/{filename}'


class VendorInvoice(SoftDeleteMixin, AuditBaseModel, ImmutableModelMixin):
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    # Unique per vendor, not globally — see the constraint in Meta.
    invoice_number = models.CharField(max_length=50, db_index=True, default='')
    reference = models.CharField(max_length=100, blank=True, default='')
    description = models.TextField(blank=True, default='')
    vendor = models.ForeignKey('procurement.Vendor', on_delete=models.PROTECT, related_name='invoices', null=True, blank=True)
    invoice_date = models.DateField(default=date.today)
    due_date = models.DateField(default=date.today)
    purchase_order = models.ForeignKey('procurement.PurchaseOrder', on_delete=models.SET_NULL, null=True, blank=True)
    account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, null=True, blank=True)
    mda = models.ForeignKey('accounting.MDA', on_delete=models.PROTECT, null=True, blank=True)
    fund = models.ForeignKey('accounting.Fund', on_delete=models.PROTECT, null=True, blank=True)
    function = models.ForeignKey('accounting.Function', on_delete=models.PROTECT, null=True, blank=True)
    program = models.ForeignKey('accounting.Program', on_delete=models.PROTECT, null=True, blank=True)
    geo = models.ForeignKey('accounting.Geo', on_delete=models.PROTECT, null=True, blank=True)
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.ForeignKey('accounting.Currency', on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        # Lifecycle for AP Vendor Invoices:
        #   Draft    – created, 3-pillar budget validation passed at save time
        #   Approved – transient state during approve_invoice action
        #              (fliped by the view; usually never visible in the list
        #              because post_invoice runs immediately after)
        #   Posted   – GL journal created (DR Expense / CR AP), AP recognised,
        #              appropriation's Expended column reflects this invoice.
        #              Awaiting payment voucher from Treasury.
        #   Partially Paid / Paid – payment voucher applied (treasury)
        #   Void – cancelled/reversed
        ('Draft', 'Draft'),
        ('Approved', 'Approved'),
        ('Posted', 'Posted'),
        ('Partially Paid', 'Partially Paid'),
        ('Paid', 'Paid'),
        ('Void', 'Void'),
    ], default='Draft')
    journal_entry = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True)
    attachment = models.FileField(upload_to=tenant_upload_path, null=True, blank=True)
    document_number = models.CharField(max_length=50, blank=True, db_index=True, null=True)
    document_type = models.CharField(
        max_length=20,
        choices=[('Invoice', 'Invoice'), ('Credit Memo', 'Credit Memo')],
        default='Invoice',
        blank=True,
    )

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            today = date.today()
            prefix = f"VINV-{today.strftime('%Y%m')}"
            last = VendorInvoice.objects.filter(
                invoice_number__startswith=prefix
            ).order_by('-invoice_number').first()
            if last:
                try:
                    seq = int(last.invoice_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1
            self.invoice_number = f"{prefix}-{seq:04d}"
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-invoice_date', '-invoice_number']
        indexes = [
            models.Index(fields=['status', 'invoice_date'], name='vi_status_date_idx'),
        ]
        constraints = [
            # Scoped to the vendor, not global.
            #
            # ``invoice_number`` used to be ``unique=True`` across the whole
            # table, which is wrong in both directions. Two different
            # suppliers legitimately issue "INV-001", and rejecting the
            # second teaches staff to mangle it into "INV-001-A" — which
            # destroys the very signal the constraint exists to protect.
            # Meanwhile the duplicate that actually costs money — the same
            # work re-submitted under a fresh number — passed straight
            # through either way.
            #
            # Blank numbers are excluded: the old global rule allowed
            # exactly ONE invoice in the entire system to have no number,
            # which is an accident of the constraint rather than a policy.
            # Soft-deleted rows are excluded so a mistaken capture can be
            # deleted and re-entered with the same number.
            models.UniqueConstraint(
                fields=['vendor', 'invoice_number'],
                condition=models.Q(is_deleted=False) & ~models.Q(invoice_number=''),
                name='uniq_vendor_invoice_number',
            ),
        ]

    @property
    def balance_due(self):
        return self.total_amount - self.paid_amount

    def __str__(self):
        return f"{self.invoice_number} - {self.vendor.name} ({self.total_amount})"


class VendorInvoiceLine(models.Model):
    invoice = models.ForeignKey(VendorInvoice, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT)
    description = models.CharField(max_length=255, blank=True, default='')
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_code = models.ForeignKey('accounting.TaxCode', on_delete=models.SET_NULL, null=True, blank=True)
    withholding_tax = models.ForeignKey('accounting.WithholdingTax', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.account.name} ({self.amount})"


class Payment(SoftDeleteMixin, AuditBaseModel, ImmutableModelMixin):
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    ADVANCE_TYPE_CHOICES = [
        ('', 'None'),
        ('Supplier Advance', 'Supplier Advance'),
        ('Supplier Deposit', 'Supplier Deposit'),
    ]

    payment_number = models.CharField(max_length=50, unique=True, default='')
    payment_date = models.DateField(default=date.today)
    payment_method = models.CharField(max_length=20, choices=[
        ('Check', 'Check'),
        ('Wire', 'Wire Transfer'),
        ('ACH', 'ACH'),
        ('Cash', 'Cash'),
    ])
    reference_number = models.CharField(max_length=100, blank=True, default='')
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    currency = models.ForeignKey('accounting.Currency', on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        ('Draft', 'Draft'),
        ('Posted', 'Posted'),
        ('Void', 'Void'),
    ], default='Draft')
    journal_entry = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True)
    bank_account = models.ForeignKey('accounting.BankAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='outgoing_payments')
    vendor = models.ForeignKey('procurement.Vendor', on_delete=models.PROTECT, null=True, blank=True, related_name='payments')
    # Optional back-link to the Payment Voucher (PV) that authorised this
    # payment. When AccountingSettings.require_pv_before_payment is True
    # the PaymentSerializer makes this mandatory — the PV becomes the
    # authoritative "authority to pay" document and every outgoing cash
    # must reference one. When the flag is False the field stays
    # nullable and direct vendor-invoice payments remain possible.
    payment_voucher = models.ForeignKey(
        'accounting.PaymentVoucherGov', on_delete=models.PROTECT,
        null=True, blank=True, related_name='cash_payments',
        help_text='PV that authorises this payment. Required when '
                  'require_pv_before_payment setting is True.',
    )
    # The cheque covering this posted payment (Cheque Register). One cheque
    # may cover several posted payments (bulk). SET_NULL so voiding/deleting a
    # cheque just unlinks its payments rather than cascading.
    cheque = models.ForeignKey(
        'accounting.Check', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='payments',
    )
    is_advance = models.BooleanField(default=False)
    advance_type = models.CharField(max_length=20, choices=ADVANCE_TYPE_CHOICES, blank=True, default='')
    advance_remaining = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    document_number = models.CharField(max_length=50, blank=True, db_index=True, null=True)
    is_reconciled = models.BooleanField(default=False, db_index=True,
        help_text="Set to True when this payment has been matched in a completed bank reconciliation.")
    bank_reconciliation = models.ForeignKey(
        'BankReconciliation', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='matched_payments',
        help_text="The bank reconciliation that cleared this payment.",
    )

    class Meta:
        ordering = ['-payment_date', '-payment_number']
        constraints = [
            # At most ONE live (non-Void, not soft-deleted) Payment per
            # Payment Voucher. Backstops the check-then-create in
            # ``ensure_draft_payment_for_pv`` so a race (double-submit /
            # workflow receiver vs. approve) can't materialise two draft
            # Payments for one PV and disburse the voucher twice. Standalone
            # payments (payment_voucher NULL) are unaffected.
            #
            # ``is_deleted=False`` is REQUIRED in the condition: a draft
            # Payment is soft-deleted (is_deleted=True, status stays 'Draft'),
            # and without this a deleted draft would keep occupying the slot —
            # blocking re-scheduling the PV ("duplicate key … uniq_live_
            # payment_per_pv"). A deleted draft frees the PV to be re-scheduled
            # (only a POSTED payment needs a reversal, not a re-schedule).
            models.UniqueConstraint(
                fields=['payment_voucher'],
                condition=(
                    models.Q(payment_voucher__isnull=False)
                    & ~models.Q(status='Void')
                    & models.Q(is_deleted=False)
                ),
                name='uniq_live_payment_per_pv',
            ),
        ]

    def __str__(self):
        return f"{self.payment_number} - {self.payment_date} ({self.total_amount})"


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='allocations', null=True, blank=True)
    invoice = models.ForeignKey(VendorInvoice, on_delete=models.PROTECT, related_name='payment_allocations', null=True, blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.payment.payment_number} -> {self.invoice.invoice_number} ({self.amount})"


class CustomerInvoice(SoftDeleteMixin, AuditBaseModel, ImmutableModelMixin):
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    invoice_number = models.CharField(max_length=50, unique=True, default='')
    reference = models.CharField(max_length=100, blank=True, default='')
    description = models.TextField(blank=True, default='')
    # Government context: "customer" = revenue payer / debtor
    customer_name = models.CharField(max_length=200, blank=True, default='',
        help_text="Payer/debtor name (replaces FK to deleted sales.Customer)")
    customer_tin = models.CharField(max_length=20, blank=True, default='',
        help_text="Tax Identification Number")
    invoice_date = models.DateField(default=date.today)
    due_date = models.DateField(default=date.today)
    mda = models.ForeignKey('accounting.MDA', on_delete=models.PROTECT, null=True, blank=True)
    fund = models.ForeignKey('accounting.Fund', on_delete=models.PROTECT, null=True, blank=True)
    function = models.ForeignKey('accounting.Function', on_delete=models.PROTECT, null=True, blank=True)
    program = models.ForeignKey('accounting.Program', on_delete=models.PROTECT, null=True, blank=True)
    geo = models.ForeignKey('accounting.Geo', on_delete=models.PROTECT, null=True, blank=True)
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    received_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.ForeignKey('accounting.Currency', on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        ('Draft', 'Draft'),
        ('Sent', 'Sent'),
        ('Partially Paid', 'Partially Paid'),
        ('Paid', 'Paid'),
        ('Overdue', 'Overdue'),
        ('Void', 'Void'),
    ], default='Draft')
    journal_entry = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True)
    document_number = models.CharField(max_length=50, blank=True, db_index=True, null=True)
    document_type = models.CharField(
        max_length=20,
        choices=[('Invoice', 'Invoice'), ('Credit Memo', 'Credit Memo')],
        default='Invoice',
        blank=True,
    )

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            today = date.today()
            prefix = f"CINV-{today.strftime('%Y%m')}"
            last = CustomerInvoice.objects.filter(
                invoice_number__startswith=prefix
            ).order_by('-invoice_number').first()
            if last:
                try:
                    seq = int(last.invoice_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1
            self.invoice_number = f"{prefix}-{seq:04d}"
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-invoice_date', '-invoice_number']
        indexes = [
            models.Index(fields=['status', 'invoice_date'], name='ci_status_date_idx'),
        ]

    @property
    def balance_due(self):
        return self.total_amount - self.received_amount

    def __str__(self):
        return f"{self.invoice_number} - {self.customer.name} ({self.total_amount})"


class CustomerInvoiceLine(models.Model):
    invoice = models.ForeignKey(CustomerInvoice, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT)
    description = models.CharField(max_length=255, blank=True, default='')
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_code = models.ForeignKey('accounting.TaxCode', on_delete=models.SET_NULL, null=True, blank=True)
    withholding_tax = models.ForeignKey('accounting.WithholdingTax', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.account.name} ({self.amount})"


class Receipt(SoftDeleteMixin, AuditBaseModel, ImmutableModelMixin):
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    ADVANCE_TYPE_CHOICES = [
        ('', 'None'),
        ('Customer Advance', 'Customer Advance'),
        ('Customer Deposit', 'Customer Deposit'),
    ]

    receipt_number = models.CharField(max_length=50, unique=True, default='')
    receipt_date = models.DateField(default=date.today)
    payment_method = models.CharField(max_length=20, choices=[
        ('Cash', 'Cash'),
        ('Check', 'Check'),
        ('Wire', 'Wire Transfer'),
        ('Credit Card', 'Credit Card'),
    ])
    reference_number = models.CharField(max_length=100, blank=True, default='')
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    currency = models.ForeignKey('accounting.Currency', on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        ('Draft', 'Draft'),
        ('Posted', 'Posted'),
        ('Void', 'Void'),
    ], default='Draft')
    journal_entry = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True)
    bank_account = models.ForeignKey('accounting.BankAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='incoming_payments')
    customer_name = models.CharField(max_length=200, blank=True, default='',
        help_text="Payer name (replaces FK to deleted sales.Customer)")
    is_advance = models.BooleanField(default=False)
    advance_type = models.CharField(max_length=20, choices=ADVANCE_TYPE_CHOICES, blank=True, default='')
    advance_remaining = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    document_number = models.CharField(max_length=50, blank=True, db_index=True, null=True)
    is_reconciled = models.BooleanField(default=False, db_index=True,
        help_text="Set to True when this receipt has been matched in a completed bank reconciliation.")
    bank_reconciliation = models.ForeignKey(
        'BankReconciliation', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='matched_receipts',
        help_text="The bank reconciliation that cleared this receipt.",
    )

    class Meta:
        ordering = ['-receipt_date', '-receipt_number']

    def __str__(self):
        return f"{self.receipt_number} - {self.receipt_date} ({self.total_amount})"


class ReceiptAllocation(models.Model):
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name='allocations', null=True, blank=True)
    invoice = models.ForeignKey(CustomerInvoice, on_delete=models.PROTECT, related_name='receipt_allocations', null=True, blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.receipt.receipt_number} -> {self.invoice.invoice_number} ({self.amount})"


class Checkbook(models.Model):
    bank_account = models.ForeignKey('accounting.BankAccount', on_delete=models.CASCADE, null=True, blank=True)
    checkbook_number = models.CharField(max_length=50, default='')
    start_number = models.IntegerField(default=0)
    end_number = models.IntegerField(default=0)
    next_number = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default='Active')

    class Meta:
        unique_together = ['bank_account', 'checkbook_number']

    def __str__(self):
        return self.checkbook_number


class Check(models.Model):
    checkbook = models.ForeignKey(Checkbook, on_delete=models.CASCADE, null=True, blank=True)
    check_number = models.CharField(max_length=20, default='')
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, null=True, blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    payee = models.CharField(max_length=200, blank=True, default='')
    date_issued = models.DateField(null=True, blank=True)
    # When the payee physically collected the cheque (Cheque Register).
    date_collected = models.DateField(null=True, blank=True)
    date_cleared = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, default='Issued')

    class Meta:
        unique_together = ['checkbook', 'check_number']

    def __str__(self):
        return f"Check #{self.check_number} - {self.payee}"


class BankReconciliation(models.Model):
    bank_account = models.ForeignKey('accounting.BankAccount', on_delete=models.CASCADE, null=True, blank=True)
    statement_date = models.DateField(default=date.today)
    statement_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    book_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    reconciled_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    deposits_in_transit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    outstanding_checks = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    bank_charges = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    difference = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    reconciled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='bank_reconciliations_approved')
    status = models.CharField(max_length=20, default='Draft')
    reconciliation_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-statement_date']

    def complete(self, approved_by_user=None):
        """
        Mark this reconciliation as Completed and bulk-update all linked
        Payment and Receipt records to is_reconciled=True.

        This is the single authoritative place to finalise a reconciliation so
        the AP/AR aging reports can correctly exclude reconciled items.
        """
        from django.db import transaction as db_transaction
        from django.utils import timezone as tz

        with db_transaction.atomic():
            self.status = 'Completed'
            self.reconciliation_date = tz.now()
            if approved_by_user:
                self.approved_by = approved_by_user
            self.save(update_fields=['status', 'reconciliation_date', 'approved_by'])

            # Mark all payments/receipts that were explicitly linked to this recon
            Payment.objects.filter(bank_reconciliation=self).update(is_reconciled=True)
            Receipt.objects.filter(bank_reconciliation=self).update(is_reconciled=True)

    def __str__(self):
        return f"{self.bank_account} - {self.statement_date} ({self.status})"


class CashFlowCategory(models.Model):
    name = models.CharField(max_length=100, default='')
    category_type = models.CharField(max_length=20, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.category_type})"


class CashFlowForecast(models.Model):
    bank_account = models.ForeignKey('accounting.BankAccount', on_delete=models.CASCADE, null=True, blank=True)
    forecast_date = models.DateField(default=date.today)
    projected_inflow = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    projected_outflow = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-forecast_date']

    def __str__(self):
        return f"{self.bank_account} - {self.forecast_date}"
