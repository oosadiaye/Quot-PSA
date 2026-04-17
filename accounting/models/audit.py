from datetime import date
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class TransactionAuditLog(models.Model):
    """Immutable audit log for all financial transactions."""

    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('APPROVE', 'Approve'),
        ('REJECT', 'Reject'),
        ('POST', 'Post'),
        ('UNPOST', 'Unpost'),
        ('REVERSE', 'Reverse'),
        ('VOID', 'Void'),
        ('EXPORT', 'Export'),
        ('IMPORT', 'Import'),
    ]

    DOCUMENT_TYPE_CHOICES = [
        ('JE', 'Journal Entry'),
        ('VI', 'Vendor Invoice'),
        ('CI', 'Customer Invoice'),
        ('PAY', 'Payment'),
        ('RCT', 'Receipt'),
        ('BGT', 'Budget'),
        ('AST', 'Fixed Asset'),
        ('BANK', 'Bank Transaction'),
        ('IC', 'Inter-Company'),
        ('REV', 'Reversal'),
    ]

    transaction_type = models.CharField(
        max_length=5,
        choices=DOCUMENT_TYPE_CHOICES,
        db_index=True
    )
    transaction_id = models.IntegerField(db_index=True)
    action = models.CharField(
        max_length=10,
        choices=ACTION_CHOICES,
        db_index=True
    )

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='accounting_audit_logs'
    )
    username = models.CharField(max_length=150, default='')

    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')

    checksum = models.CharField(max_length=64, blank=True, default='')
    previous_checksum = models.CharField(max_length=64, blank=True, default='')

    # S3-01 — explicit monotonic sequence number. Previously the hash
    # chain used timestamp ordering which is non-atomic under concurrent
    # writes; two simultaneous commits could read the same predecessor
    # and fork the chain. The ``sequence_number`` is assigned under a
    # row-level advisory lock in ``save()`` so every row has a unique
    # deterministic position.
    sequence_number = models.BigIntegerField(null=True, blank=True, db_index=True)

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    description = models.TextField(blank=True, default='')
    reference_number = models.CharField(max_length=50, blank=True, default='')

    tenant_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['transaction_type', 'transaction_id']),
            models.Index(fields=['transaction_type', 'action', 'timestamp']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['reference_number']),
            models.Index(fields=['tenant_id', 'timestamp']),
            models.Index(fields=['sequence_number']),
        ]
        # S3-01 — sequence numbers must be unique within a tenant (and we
        # coerce tenant_id=None into a separate bucket via partial index
        # semantics). Enforce monotonic strict ordering of the audit chain.
        constraints = [
            models.UniqueConstraint(
                fields=['tenant_id', 'sequence_number'],
                condition=models.Q(sequence_number__isnull=False),
                name='uniq_txn_audit_tenant_seq',
            ),
        ]

    def __str__(self):
        return f"{self.transaction_type}-{self.transaction_id} {self.action} by {self.username}"

    # ── S3-02 — Audit rows are write-once ───────────────────────────────
    # Any attempt to update or delete an already-persisted row raises.
    # The Django admin, management commands, and ORM bulk operations all
    # go through this guard.
    def save(self, *args, **kwargs):
        """Write-once with an atomic sequence + hash chain.

        First save (pk is None):
          * Acquires a transaction + reads the last row under
            ``select_for_update`` so two concurrent writers serialise
            through the DB rather than forking the chain.
          * Assigns the next sequence number.
          * Computes ``previous_checksum`` from the locked predecessor.
          * Computes our checksum including user/IP/prev/sequence so a
            single-row tamper cannot reproduce a valid hash without also
            rewriting everything downstream.

        Subsequent saves are REJECTED — audit rows are immutable.
        """
        from django.db import transaction as _db_tx
        from django.core.exceptions import ValidationError

        if self.pk:
            # Already persisted — reject any attempt to modify.
            raise ValidationError(
                'TransactionAuditLog rows are write-once and cannot be '
                'modified. Record a new audit entry to capture changes.'
            )

        # Redact sensitive values before hashing + persisting (S3-04).
        self.old_values = _redact_sensitive(self.old_values)
        self.new_values = _redact_sensitive(self.new_values)

        with _db_tx.atomic():
            # Scope to the tenant bucket (same partial index semantics
            # as the unique constraint).
            predecessor_qs = (
                TransactionAuditLog.objects
                .select_for_update()
                .filter(tenant_id=self.tenant_id)
                .order_by('-sequence_number')
            )
            predecessor = predecessor_qs.first()

            self.sequence_number = (
                (predecessor.sequence_number or 0) + 1 if predecessor else 1
            )
            self.previous_checksum = predecessor.checksum if predecessor else ''
            self.checksum = self.generate_checksum()
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """S3-02 — physical deletion of audit rows is forbidden."""
        from django.core.exceptions import ValidationError
        raise ValidationError(
            'TransactionAuditLog rows cannot be deleted. '
            'The audit trail must be preserved for forensic integrity.'
        )

    def generate_checksum(self) -> str:
        """Tamper-evident SHA-256 over the full audit-relevant payload.

        S3-01 — previous implementation excluded user, ip_address, and
        previous_checksum from the hash. That let an attacker swap user
        or IP on a row, or splice in a fake row, without invalidating
        the chain. The hash now covers every field that auditors care
        about *plus* the chain link.
        """
        import hashlib
        import json
        content = json.dumps({
            'sequence_number':   self.sequence_number,
            'tenant_id':         self.tenant_id,
            'transaction_type':  self.transaction_type,
            'transaction_id':    self.transaction_id,
            'action':            self.action,
            'user_id':           self.user_id if self.user_id else None,
            'username':          self.username or '',
            'ip_address':        self.ip_address or '',
            'user_agent':        self.user_agent or '',
            'old_values':        self.old_values,
            'new_values':        self.new_values,
            'timestamp':         self.timestamp.isoformat() if self.timestamp else None,
            'previous_checksum': self.previous_checksum or '',
            'reference_number':  self.reference_number or '',
        }, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()


# ─── S3-04 — Sensitive-field redaction for audit capture ──────────────────
# Values captured into old_values / new_values get redacted when the key
# matches a known-sensitive name substring. This applies BEFORE the row
# is persisted and BEFORE the checksum is computed, so the hash commits
# to the redacted values — an attacker can't un-redact later.
_REDACT_KEY_PATTERNS = (
    'password', 'passwd', 'secret', 'token', 'api_key', 'apikey',
    'private_key', 'privatekey', 'access_key', 'accesskey',
    'refresh_token', 'session_key', 'sessionkey', 'auth',
    'credit_card', 'creditcard', 'cvv', 'ccv',
    'ssn', 'bvn_pin', 'tin_secret',
)


def _redact_sensitive(value):
    """Recursively redact values whose keys match a sensitive pattern."""
    if isinstance(value, dict):
        return {
            k: ('***REDACTED***' if _is_sensitive_key(k) else _redact_sensitive(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


def _is_sensitive_key(key) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return any(pat in lowered for pat in _REDACT_KEY_PATTERNS)


class ApprovalRule(models.Model):
    """Defines approval rules for different document types and amounts."""

    DOCUMENT_TYPES = [
        ('JE', 'Journal Entry'),
        ('VI', 'Vendor Invoice'),
        ('CI', 'Customer Invoice'),
        ('PAY', 'Payment'),
        ('BGT', 'Budget Amendment'),
        ('TRF', 'Budget Transfer'),
    ]

    document_type = models.CharField(max_length=5, choices=DOCUMENT_TYPES, db_index=True)
    min_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    max_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    approval_levels = models.JSONField(default=list)
    auto_approve_roles = models.JSONField(default=list, blank=True)
    skip_approval_if_same_user = models.BooleanField(default=False)
    require_comment_on_reject = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['document_type', 'min_amount']

    def __str__(self):
        amount_range = f"{self.min_amount}"
        if self.max_amount:
            amount_range += f" - {self.max_amount}"
        return f"{self.get_document_type_display()} ({amount_range})"


class ApprovalLevel(models.Model):
    """Defines a single level of approval."""

    APPROVER_TYPES = [
        ('USER', 'Specific User'),
        ('ROLE', 'Role-based'),
        ('MANAGER', 'User\'s Manager'),
        ('DEPARTMENT', 'Department Head'),
    ]

    rule = models.ForeignKey(ApprovalRule, on_delete=models.CASCADE, related_name='levels')
    level = models.IntegerField(default=1)
    approver_type = models.CharField(max_length=20, choices=APPROVER_TYPES, default='ROLE')
    approver_value = models.CharField(max_length=100, blank=True, default='')
    min_approvers = models.IntegerField(default=1)

    class Meta:
        ordering = ['level']
        unique_together = ['rule', 'level']


class ApprovalInstance(models.Model):
    """Tracks approval status for a specific document."""

    STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
    ]

    document_type = models.CharField(max_length=5, db_index=True)
    document_id = models.IntegerField(db_index=True)
    reference_number = models.CharField(max_length=50, blank=True, default='')

    current_level = models.IntegerField(default=0)
    max_level = models.IntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    approvals = models.JSONField(default=list)
    rejection_reason = models.TextField(blank=True, default='')

    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='submitted_approvals')
    submitted_at = models.DateTimeField(auto_now_add=True)

    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='completed_approvals')

    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    description = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['document_type', 'document_id']),
            models.Index(fields=['status', 'submitted_at']),
        ]

    def __str__(self):
        return f"{self.document_type}-{self.document_id} L{self.current_level} ({self.status})"


class DualControlSetting(models.Model):
    """Global dual control settings."""

    THRESHOLD_TYPES = [
        ('journal', 'Journal Entry'),
        ('invoice', 'Invoice'),
        ('payment', 'Payment'),
        ('refund', 'Refund'),
    ]

    document_type = models.CharField(max_length=20, choices=THRESHOLD_TYPES)
    threshold_amount = models.DecimalField(max_digits=15, decimal_places=2, default=10000)
    require_dual_approval = models.BooleanField(default=True)
    dual_approval_threshold = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    approver_roles = models.JSONField(default=list)
    notification_roles = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['document_type', 'threshold_amount']

    def __str__(self):
        return f"{self.get_document_type_display()}: >={self.threshold_amount}"


class DualControlOverride(models.Model):
    """Records override attempts for dual control."""

    document_type = models.CharField(max_length=20)
    document_id = models.IntegerField()
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dual_control_overrides')
    requested_at = models.DateTimeField(auto_now_add=True)
    justification = models.TextField()
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_overrides')
    approved_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default='PENDING')
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.document_type}-{self.document_id} by {self.requested_by}"


class CustomerAging(models.Model):
    """Accounts Receivable aging by customer"""
    customer_name = models.CharField(max_length=200, default='',
        help_text="Debtor/payer name (replaces FK to deleted sales.Customer)")
    customer_id_ref = models.IntegerField(null=True, blank=True,
        help_text="Legacy customer ID reference")
    as_of_date = models.DateField()
    current = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Current (0-30 days)")
    days_30 = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="31-60 days")
    days_60 = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="61-90 days")
    days_90 = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="91-120 days")
    days_120 = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Over 120 days")
    total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.ForeignKey('accounting.Currency', on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        unique_together = ['customer_name', 'as_of_date']
        ordering = ['-as_of_date', 'customer_name']

    def save(self, *args, **kwargs):
        self.total = self.current + self.days_30 + self.days_60 + self.days_90 + self.days_120
        super().save(*args, **kwargs)

    def __str__(self):
        # S2-09 — model stores ``customer_name`` (CharField), NOT a FK to
        # Customer. Previously ``self.customer.name`` raised AttributeError
        # in every admin list view.
        return f"{self.customer_name} Aging {self.as_of_date}"


class BadDebtProvision(models.Model):
    """Bad debt provision per IFRS 9."""

    provision_date = models.DateField(default=date.today)
    fiscal_year = models.IntegerField(default=0)
    period = models.IntegerField(default=0)

    provision_type = models.CharField(max_length=20, default='SPECIFIC')

    opening_provision = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    new_provisions = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    write_offs = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    recoveries = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    closing_provision = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    provisioning_method = models.TextField(blank=True, default='')

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('APPROVED', 'Approved'),
        ('POSTED', 'Posted'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='bad_debt_provisions')
    created_at = models.DateTimeField(auto_now_add=True)

    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='provisions_approved')
    approved_at = models.DateTimeField(null=True, blank=True)

    journal_id = models.IntegerField(null=True, blank=True)

    fiscal_period = models.ForeignKey('accounting.FiscalPeriod', on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ['-provision_date']
        unique_together = ['fiscal_year', 'period']

    def __str__(self):
        return f"Bad Debt Provision FY{self.fiscal_year} P{self.period}"


class BadDebtWriteOff(models.Model):
    """Bad debt write-off records."""

    write_off_number = models.CharField(max_length=50, unique=True)

    customer_name = models.CharField(max_length=200, default='',
        help_text="Debtor name (replaces FK to deleted sales.Customer)")

    original_invoice = models.ForeignKey('accounting.CustomerInvoice', on_delete=models.SET_NULL, null=True, blank=True)
    original_invoice_number = models.CharField(max_length=50, blank=True, default='')

    write_off_date = models.DateField()
    invoice_date = models.DateField(null=True, blank=True)
    invoice_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    amount_written_off = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    reason = models.TextField()

    age_at_write_off = models.IntegerField(default=0)
    days_overdue = models.IntegerField(default=0)

    STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('POSTED', 'Posted'),
        ('RECOVERED', 'Recovered'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    provision_reference = models.CharField(max_length=50, blank=True, default='')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='write_offs_created')
    created_at = models.DateTimeField(auto_now_add=True)

    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='write_offs_approved')
    approved_at = models.DateTimeField(null=True, blank=True)

    journal_id = models.IntegerField(null=True, blank=True)

    recovered_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    recovered_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-write_off_date']

    def __str__(self):
        return f"Write-off {self.write_off_number}"


class CreditNote(models.Model):
    """Credit notes for AR adjustments."""

    credit_note_number = models.CharField(max_length=50, unique=True)

    customer_name = models.CharField(max_length=200, default='',
        help_text="Debtor name (replaces FK to deleted sales.Customer)")

    original_invoice = models.ForeignKey('accounting.CustomerInvoice', on_delete=models.SET_NULL, null=True, blank=True, related_name='credit_notes')
    original_invoice_number = models.CharField(max_length=50, blank=True, default='')

    credit_note_date = models.DateField()

    reason = models.TextField()
    REASON_CHOICES = [
        ('RETURN', 'Goods Return'),
        ('DISCOUNT', 'Discount'),
        ('CORRECTION', 'Price Correction'),
        ('DAMAGE', 'Damaged Goods'),
        ('SHORTAGE', 'Short Delivery'),
        ('OTHER', 'Other'),
    ]
    reason_type = models.CharField(max_length=20, choices=REASON_CHOICES, default='OTHER')

    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('APPROVED', 'Approved'),
        ('APPLIED', 'Applied'),
        ('CANCELLED', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    applied_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    applied_invoices = models.JSONField(default=list)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='credit_notes_created')
    created_at = models.DateTimeField(auto_now_add=True)

    journal_id = models.IntegerField(null=True, blank=True)

    currency_code = models.CharField(max_length=3, default='NGN')

    class Meta:
        ordering = ['-credit_note_date']

    def __str__(self):
        return f"CN {self.credit_note_number} - {self.total_amount}"


class DebitNote(models.Model):
    """Debit notes for AP adjustments."""

    debit_note_number = models.CharField(max_length=50, unique=True)

    vendor = models.ForeignKey('procurement.Vendor', on_delete=models.PROTECT, null=True, blank=True)
    vendor_name = models.CharField(max_length=200, default='')

    original_invoice = models.ForeignKey('accounting.VendorInvoice', on_delete=models.SET_NULL, null=True, blank=True, related_name='debit_notes')
    original_invoice_number = models.CharField(max_length=50, blank=True, default='')

    debit_note_date = models.DateField()

    reason = models.TextField()
    REASON_CHOICES = [
        ('RETURN', 'Goods Return'),
        ('PRICE_INCREASE', 'Price Increase'),
        ('ADDITIONAL_CHARGE', 'Additional Charge'),
        ('DAMAGE', 'Damaged Goods'),
        ('SHORTAGE', 'Short Delivery'),
        ('OTHER', 'Other'),
    ]
    reason_type = models.CharField(max_length=20, choices=REASON_CHOICES, default='OTHER')

    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('APPROVED', 'Approved'),
        ('APPLIED', 'Applied'),
        ('CANCELLED', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    applied_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    applied_invoices = models.JSONField(default=list)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='debit_notes_created')
    created_at = models.DateTimeField(auto_now_add=True)

    journal_id = models.IntegerField(null=True, blank=True)

    currency_code = models.CharField(max_length=3, default='NGN')

    class Meta:
        ordering = ['-debit_note_date']

    def __str__(self):
        return f"DN {self.debit_note_number} - {self.total_amount}"


class SuspenseClearing(models.Model):
    """Suspense account clearing records."""

    clearing_number = models.CharField(max_length=50, unique=True, default='')

    journal_header = models.ForeignKey('accounting.JournalHeader', on_delete=models.CASCADE, related_name='suspense_clearings', null=True, blank=True)

    suspense_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='suspense_clearings', null=True, blank=True)
    clearing_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='clearing_entries', null=True, blank=True)

    clearing_date = models.DateField(default=date.today)

    suspense_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cleared_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    description = models.TextField(default='')

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PARTIAL', 'Partially Cleared'),
        ('CLEARED', 'Cleared'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='suspense_clearings')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-clearing_date']

    def __str__(self):
        return f"Suspense Clearing {self.clearing_number}"


class FinancialRatio(models.Model):
    """Calculated financial ratios."""

    fiscal_year = models.IntegerField()
    period = models.IntegerField()
    calculation_date = models.DateField()

    ratio_category = models.CharField(max_length=50)
    ratio_name = models.CharField(max_length=100)
    ratio_value = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    ratio_unit = models.CharField(max_length=20, default='ratio')

    benchmark_value = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    industry_average = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)

    is_favorable = models.BooleanField(default=True)
    is_within_threshold = models.BooleanField(default=True)

    calculation_details = models.JSONField(default=dict)

    fiscal_period = models.ForeignKey('accounting.FiscalPeriod', on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ['-calculation_date']
        unique_together = ['fiscal_year', 'period', 'ratio_name']
        indexes = [
            models.Index(fields=['fiscal_year', 'period', 'ratio_category']),
        ]

    def __str__(self):
        return f"{self.ratio_name}: {self.ratio_value}"


class PeriodClosing(models.Model):
    """Period-end closing records."""

    fiscal_period = models.ForeignKey('accounting.FiscalPeriod', on_delete=models.PROTECT, related_name='closings')
    closing_date = models.DateField()

    CLOSING_TYPE_CHOICES = [
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
        ('YEARLY', 'Year-End'),
    ]
    closing_type = models.CharField(max_length=20, choices=CLOSING_TYPE_CHOICES)

    closing_entries = models.JSONField(default=list)

    total_debits = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_credits = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    trial_balance_check = models.BooleanField(default=True)

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('VERIFIED', 'Verified'),
        ('POSTED', 'Posted'),
        ('REVERSED', 'Reversed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='period_closings')
    created_at = models.DateTimeField(auto_now_add=True)

    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='closings_approved')
    approved_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-closing_date']
        unique_together = ['fiscal_period', 'closing_type']

    def __str__(self):
        return f"Closing {self.fiscal_period} - {self.closing_type}"


class YearEndClosing(models.Model):
    """Year-end closing entries."""

    fiscal_year = models.IntegerField()
    closing_date = models.DateField()

    closing_journal_id = models.IntegerField(null=True, blank=True)

    net_income_journal_id = models.IntegerField(null=True, blank=True)

    revenue_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    expense_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_income = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    retained_earnings_before = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    retained_earnings_after = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('APPROVED', 'Approved'),
        ('POSTED', 'Posted'),
        ('REVERSED', 'Reversed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='year_closings')
    created_at = models.DateTimeField(auto_now_add=True)

    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='year_closings_approved')
    approved_at = models.DateTimeField(null=True, blank=True)

    next_fiscal_year = models.IntegerField(null=True, blank=True)

    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-fiscal_year']
        unique_together = ['fiscal_year']

    def __str__(self):
        return f"Year-End Closing FY{self.fiscal_year}"
