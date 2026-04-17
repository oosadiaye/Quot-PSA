from datetime import date
from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone
from django.core.validators import MinValueValidator
from core.models import AuditBaseModel, ImmutableModelMixin
from django.contrib.auth.models import User


# ---------------------------------------------------------------------------
# Soft-Delete infrastructure
# ---------------------------------------------------------------------------

class SoftDeleteManager(models.Manager):
    """
    Default manager that hides soft-deleted records.

    Use ``Model.all_objects.all()`` (the unfiltered manager) to include
    deleted records in admin, reporting, or audit queries.
    """
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class SoftDeleteMixin(models.Model):
    """
    Mixin that adds is_deleted / deleted_at / deleted_by fields and overrides
    .delete() to perform a soft-delete rather than a hard-delete.

    Financial records (journals, invoices, payments) MUST NOT be permanently
    deleted to preserve the audit trail required by IFRS/GAAP and local law.

    Usage:
        class JournalHeader(SoftDeleteMixin, AuditBaseModel, ...):
            objects = SoftDeleteManager()       # default — hides deleted
            all_objects = models.Manager()      # bypass filter for admin/audit
            ...

        # Soft-delete
        journal.delete()                        # sets is_deleted=True

        # Hard-delete (only if absolutely necessary with explicit intent)
        journal.delete(hard=True)
    """
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',  # no reverse accessor — avoids clash across models
    )

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, hard=False, deleted_by_user=None):
        """
        Soft-delete by default. Pass hard=True only for explicit permanent deletion.
        """
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.is_deleted = True
        self.deleted_at = timezone.now()
        if deleted_by_user:
            self.deleted_by = deleted_by_user
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])


def tenant_upload_path(instance, filename):
    """Generate a tenant-aware upload path for file fields."""
    from django.db import connection
    schema = getattr(connection, 'schema_name', 'public')
    return f'tenants/{schema}/documents/{filename}'


class Fund(models.Model):
    code = models.CharField(max_length=20, unique=True, db_index=True, default='')
    name = models.CharField(max_length=100, db_index=True, default='')
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Function(models.Model):
    code = models.CharField(max_length=20, unique=True, db_index=True, default='')
    name = models.CharField(max_length=100, db_index=True, default='')
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Program(models.Model):
    code = models.CharField(max_length=20, unique=True, db_index=True, default='')
    name = models.CharField(max_length=100, db_index=True, default='')
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Geo(models.Model):
    code = models.CharField(max_length=20, unique=True, db_index=True, default='')
    name = models.CharField(max_length=100, db_index=True, default='')
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Account(models.Model):
    RECONCILIATION_TYPE_CHOICES = [
        ('accounts_payable', 'Account Payable'),
        ('accounts_receivable', 'Account Receivable'),
        ('inventory', 'Inventory'),
        ('asset_accounting', 'Asset Accounting'),
        ('bank_accounting', 'Bank Accounting'),
    ]

    code = models.CharField(max_length=20, unique=True, db_index=True, default='')
    name = models.CharField(max_length=150, db_index=True, default='')
    account_type = models.CharField(max_length=20, choices=[
        ('Asset', 'Asset'),
        ('Liability', 'Liability'),
        ('Equity', 'Equity'),
        ('Income', 'Income'),
        ('Expense', 'Expense'),
    ], db_index=True)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='children',
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_reconciliation = models.BooleanField(default=False)
    reconciliation_type = models.CharField(
        max_length=30, choices=RECONCILIATION_TYPE_CHOICES, blank=True, default='',
    )

    class Meta:
        ordering = ['code']

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if self.parent:
            # Check for circular parent reference
            visited = set()
            current = self.parent
            while current:
                if current.pk == self.pk:
                    raise ValidationError("Circular parent reference detected.")
                if current.pk in visited:
                    break
                visited.add(current.pk)
                current = current.parent

    def __str__(self):
        return f"{self.code} - {self.name}"


class MDA(models.Model):
    code = models.CharField(max_length=20, unique=True, default='')
    name = models.CharField(max_length=200, default='')
    short_name = models.CharField(max_length=50, default='')
    mda_type = models.CharField(max_length=20, choices=[
        ('MINISTRY', 'Ministry'),
        ('DEPARTMENT', 'Department'),
        ('AGENCY', 'Agency'),
        ('PARASTATAL', 'Parastatal'),
    ])
    parent_mda = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class TransactionSequence(models.Model):
    name = models.CharField(max_length=50, unique=True)
    prefix = models.CharField(max_length=10, blank=True)
    next_value = models.PositiveIntegerField(default=1)

    @classmethod
    def get_next(cls, name, prefix=""):
        with transaction.atomic():
            seq, created = cls.objects.select_for_update().get_or_create(
                name=name, defaults={'prefix': prefix}
            )
            val = seq.next_value
            seq.next_value += 1
            seq.save()
            return f"{seq.prefix}{val:06d}"

    def __str__(self):
        return f"{self.name} (Next: {self.next_value})"


class JournalHeader(SoftDeleteMixin, AuditBaseModel, ImmutableModelMixin):
    # Managers — soft-delete aware
    objects = SoftDeleteManager()      # default: excludes is_deleted=True records
    all_objects = models.Manager()     # unfiltered: use in admin/audit reports only

    posting_date = models.DateField(db_index=True, default=date.today)
    description = models.TextField(default='')
    reference_number = models.CharField(max_length=50, blank=True, db_index=True, default='')
    mda = models.ForeignKey(MDA, on_delete=models.PROTECT, null=True, blank=True)
    fund = models.ForeignKey(Fund, on_delete=models.PROTECT, null=True, blank=True)
    function = models.ForeignKey(Function, on_delete=models.PROTECT, null=True, blank=True)
    program = models.ForeignKey(Program, on_delete=models.PROTECT, null=True, blank=True)
    geo = models.ForeignKey(Geo, on_delete=models.PROTECT, null=True, blank=True)
    document_number = models.CharField(max_length=50, blank=True, db_index=True, null=True)
    status = models.CharField(max_length=20, choices=[
        ('Draft', 'Draft'),
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Posted', 'Posted'),
        ('Rejected', 'Rejected'),
    ], default='Draft', db_index=True)

    # Audit / source tracing — links every journal entry back to the originating
    # module and document for reconciliation, regulatory compliance, and debugging.
    source_module = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="Originating module: 'sales', 'procurement', 'hrm', 'inventory', etc."
    )
    source_document_id = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="PK of the source record (SalesOrder.pk, PayrollRun.pk, etc.)"
    )
    posted_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='journals_posted',
        help_text="User who triggered the GL posting action."
    )
    posted_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Timestamp when the journal was posted to the GL."
    )
    is_reversed = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ['-posting_date', '-id']
        indexes = [
            models.Index(fields=['posting_date', 'status']),
            models.Index(fields=['status', 'fund']),
            models.Index(fields=['posting_date', 'status', 'fund']),
            models.Index(fields=['status', 'mda']),
            models.Index(fields=['document_number']),
            models.Index(fields=['reference_number']),
            models.Index(fields=['source_module', 'source_document_id']),
        ]
        permissions = [
            ('post_journalheader', 'Can post journal entries to GL'),
            ('approve_journalheader', 'Can approve journal entries'),
        ]
        # S1-02 — integrity constraints.
        #   * reference_number must be unique when non-blank (duplicate
        #     references break auditor traceability).
        #   * (source_module, source_document_id, status='Posted') must be
        #     unique so the same source cannot be posted twice — prevents the
        #     race condition in _check_duplicate_posting.
        constraints = [
            models.UniqueConstraint(
                fields=['reference_number'],
                condition=models.Q(reference_number__gt=''),
                name='uniq_journalheader_reference_number',
            ),
            models.UniqueConstraint(
                fields=['source_module', 'source_document_id'],
                condition=models.Q(status='Posted')
                          & models.Q(source_module__isnull=False)
                          & models.Q(source_document_id__isnull=False),
                name='uniq_journalheader_source_doc_posted',
            ),
        ]

    def __str__(self):
        return f"Journal {self.reference_number} ({self.posting_date})"

    # ── S1-03 — Posted-immutability guard ─────────────────────────────────
    # Fields that may still change after posting (purely audit metadata that
    # reversal/undelete flows legitimately need to update). Everything else
    # is frozen once status='Posted'.
    POST_POSTING_MUTABLE_FIELDS = frozenset({
        'status',                 # only transitions to 'Posted' / 'Reversed' allowed
        'posted_by', 'posted_at',
        'is_reversed',
        'is_deleted', 'deleted_at', 'deleted_by',
        'updated_at', 'modified_at',
    })

    def save(self, *args, **kwargs):
        """Reject edits to fields on a journal that is already Posted.

        The only legitimate mutations on a Posted journal are:
          • status → 'Reversed' (via JournalReversal flow)
          • is_reversed flag flip
          • soft-delete metadata
          • auto-managed audit timestamps

        Anything else must be prevented to preserve the audit trail. Raises
        ``ValidationError`` so callers trying to do this surface it cleanly.
        """
        from django.core.exceptions import ValidationError
        # Trust callers that pass update_fields — we still intersect with the
        # mutable allow-list.
        update_fields = kwargs.get('update_fields')
        if self.pk:
            try:
                prior = type(self).all_objects.get(pk=self.pk)
            except type(self).DoesNotExist:
                prior = None
            if prior and prior.status == 'Posted':
                if update_fields is not None:
                    disallowed = set(update_fields) - self.POST_POSTING_MUTABLE_FIELDS
                    if disallowed:
                        raise ValidationError(
                            f"Cannot modify posted journal {prior.reference_number}: "
                            f"attempted to change {sorted(disallowed)}"
                        )
                else:
                    # Compare persisted snapshot to current instance field-by-field.
                    changed = []
                    for f in self._meta.concrete_fields:
                        name = f.attname
                        if name in self.POST_POSTING_MUTABLE_FIELDS:
                            continue
                        if getattr(prior, name, None) != getattr(self, name, None):
                            changed.append(f.name)
                    if changed:
                        raise ValidationError(
                            f"Cannot modify posted journal {prior.reference_number}: "
                            f"attempted to change {changed}. Reverse the journal instead."
                        )
        return super().save(*args, **kwargs)


class JournalLine(models.Model):
    header = models.ForeignKey(JournalHeader, related_name='lines', on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    memo = models.CharField(max_length=255, blank=True, default='')
    document_number = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    # Cost-centre dimension — allows per-department GL line allocation (e.g. payroll split)
    cost_center = models.ForeignKey(
        MDA, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='journal_lines',
        help_text="MDA / Department cost centre this line is allocated to."
    )

    # ─── NCoA fields (nullable for migration safety) ──────────────
    # Once seed data exists and journals are backfilled, these will become required.
    # The economic segment is derived from ncoa_code.economic — no standalone FK
    # to avoid drift between ncoa_code.economic and a separate economic_segment field.
    ncoa_code = models.ForeignKey(
        'accounting.NCoACode', on_delete=models.PROTECT,
        null=True, blank=True, related_name='journal_lines',
        help_text="Full 52-digit NCoA composite code",
    )

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if self.debit > 0 and self.credit > 0:
            raise ValidationError("A journal line cannot have both debit and credit amounts.")
        if self.debit == 0 and self.credit == 0:
            raise ValidationError("A journal line must have either a debit or credit amount.")

    # ── S1-01 — DB-level amount constraints ───────────────────────────────
    # Enforces the double-entry invariants at the database layer so bulk
    # imports, raw SQL, and admin actions cannot persist invalid lines:
    #   * debit and credit are both non-negative
    #   * at most one of (debit, credit) is non-zero
    #   * at least one of (debit, credit) is non-zero
    class Meta:
        indexes = [
            # P6-T1 — hot paths on JournalLine (see docs/PERFORMANCE_AUDIT.md)
            models.Index(fields=['header', 'account'], name='jrn_line_header_account_idx'),
            models.Index(fields=['header', 'ncoa_code'], name='jrn_line_header_ncoa_idx'),
            models.Index(fields=['header', 'cost_center'], name='jrn_line_header_cc_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(debit__gte=0),
                name='jrn_line_debit_nonneg',
            ),
            models.CheckConstraint(
                check=models.Q(credit__gte=0),
                name='jrn_line_credit_nonneg',
            ),
            models.CheckConstraint(
                check=~(models.Q(debit__gt=0) & models.Q(credit__gt=0)),
                name='jrn_line_not_both_sides',
            ),
            models.CheckConstraint(
                check=models.Q(debit__gt=0) | models.Q(credit__gt=0),
                name='jrn_line_at_least_one_side',
            ),
        ]

    # ── S1-03 — reject edits on lines belonging to a Posted journal ───────
    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        if self.pk and self.header_id:
            try:
                header_status = (
                    JournalHeader.all_objects
                    .filter(pk=self.header_id)
                    .values_list('status', flat=True)
                    .first()
                )
            except Exception:
                header_status = None
            if header_status == 'Posted':
                # Allow a read-modify-write that doesn't actually change
                # anything (rare, but e.g. from serializer round-trips).
                try:
                    prior = type(self).objects.get(pk=self.pk)
                    dirty = any(
                        getattr(prior, f.attname, None) != getattr(self, f.attname, None)
                        for f in self._meta.concrete_fields
                    )
                except type(self).DoesNotExist:
                    dirty = True
                if dirty:
                    raise ValidationError(
                        'Cannot modify a line on a posted journal. '
                        'Reverse the journal and re-post to correct.'
                    )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of lines on posted journals."""
        from django.core.exceptions import ValidationError
        if self.header_id:
            header_status = (
                JournalHeader.all_objects
                .filter(pk=self.header_id)
                .values_list('status', flat=True)
                .first()
            )
            if header_status == 'Posted':
                raise ValidationError(
                    'Cannot delete a line on a posted journal. '
                    'Reverse the journal instead.'
                )
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.header} - {self.account} (D:{self.debit}, C:{self.credit})"


class JournalReversal(AuditBaseModel):
    # S1-04 — PROTECT instead of CASCADE so deleting an original journal
    # cannot silently wipe its reversal record. The reversal *must* remain
    # on disk to preserve the audit trail.
    original_journal = models.ForeignKey(JournalHeader, on_delete=models.PROTECT, related_name='reversals', null=True, blank=True)
    reversal_journal = models.ForeignKey(JournalHeader, on_delete=models.SET_NULL, null=True, blank=True, related_name='reversal_of')
    reversal_type = models.CharField(max_length=20, choices=[
        ('Unpost', 'Unpost'),
        ('Reverse', 'Reverse'),
        ('Correct', 'Correct'),
    ], default='Reverse')
    reason = models.TextField(default='')
    reversed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='journal_reversals')
    gl_balances_reversed = models.JSONField(default=list)

    def __str__(self):
        return f"Reversal of {self.original_journal.reference_number}"


class Currency(models.Model):
    code = models.CharField(max_length=3, unique=True, default='')
    name = models.CharField(max_length=100, default='')
    symbol = models.CharField(max_length=5, default='')
    exchange_rate = models.DecimalField(max_digits=15, decimal_places=6, default=1.0)
    is_base_currency = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Currencies"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"
