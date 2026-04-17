"""
Treasury Bank Reconciliation
============================
Models for reconciling a TSA (Treasury Single Account) with the bank's own
statement. Distinct from the commercial ``BankReconciliation`` model in
receivables.py, which pairs commercial Payments/Receipts with a
``BankAccount`` — this module operates on ``TreasuryAccount`` and pairs the
bank statement with ``PaymentInstruction`` (outflows) and
``RevenueCollection`` (inflows).

Flow:
 1. Treasurer uploads the bank statement file (CSV).
 2. We parse it into ``TSABankStatementLine`` rows under a
    ``TSABankStatement`` header.
 3. An auto-match pass fills ``matched_*`` FKs on each statement line.
 4. A ``TSAReconciliation`` session groups the results per period and tracks
    the difference: book balance vs statement balance.
 5. When closed, every matched side is flagged reconciled.
"""

from decimal import Decimal
from django.conf import settings
from django.db import models
from core.models import AuditBaseModel
from accounting.models.gl import tenant_upload_path


class TSABankStatement(AuditBaseModel):
    """
    Header for an uploaded bank statement file.

    One import = one file = one contiguous date window for one TSA.
    """
    STATUS_CHOICES = [
        ('PARSED',    'Parsed'),
        ('MATCHED',   'Auto-matched'),
        ('COMPLETED', 'Completed'),
        ('FAILED',    'Parse Failed'),
    ]

    tsa_account       = models.ForeignKey(
        'accounting.TreasuryAccount', on_delete=models.PROTECT,
        related_name='statement_imports',
    )
    statement_file    = models.FileField(upload_to=tenant_upload_path)
    original_filename = models.CharField(max_length=255)
    statement_from    = models.DateField(
        help_text='First transaction date covered by the statement',
    )
    statement_to      = models.DateField(
        help_text='Last transaction date covered by the statement',
    )
    opening_balance   = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    closing_balance   = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    total_debits      = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    total_credits     = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    line_count        = models.IntegerField(default=0)
    status            = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default='PARSED',
    )
    parse_errors      = models.JSONField(default=list, blank=True)
    uploaded_by       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bank_imports',
    )
    notes             = models.TextField(blank=True, default='')
    # SHA-256 of file bytes — used to short-circuit duplicate uploads (M2).
    file_hash         = models.CharField(max_length=64, blank=True, default='', db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Bank Statement Import'
        verbose_name_plural = 'Bank Statement Imports'
        indexes = [
            models.Index(fields=['tsa_account', '-statement_to']),
        ]

    def __str__(self):
        return f"{self.tsa_account.account_number} {self.statement_from}→{self.statement_to}"


class TSABankStatementLine(models.Model):
    """
    A single transaction line parsed from the uploaded statement.

    Each line is eventually matched to either a PaymentInstruction (debit) or
    a RevenueCollection (credit). Unmatched lines surface as reconciling
    items on the reconciliation session.
    """
    MATCH_STATUS_CHOICES = [
        ('UNMATCHED', 'Unmatched'),
        ('AUTO',      'Auto-matched'),
        ('MANUAL',    'Manually matched'),
        ('IGNORED',   'Ignored'),  # e.g. bank charge already booked separately
    ]

    statement        = models.ForeignKey(
        TSABankStatement, on_delete=models.CASCADE, related_name='lines',
    )
    line_number      = models.PositiveIntegerField(help_text='1-based row order from the file')
    transaction_date = models.DateField()
    value_date       = models.DateField(null=True, blank=True)
    description      = models.CharField(max_length=500, blank=True, default='')
    reference        = models.CharField(max_length=100, blank=True, default='')
    debit            = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    credit           = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    balance_after    = models.DecimalField(
        max_digits=22, decimal_places=2, null=True, blank=True,
    )

    match_status           = models.CharField(
        max_length=10, choices=MATCH_STATUS_CHOICES, default='UNMATCHED',
    )
    match_confidence       = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='0-100: how confident the auto-matcher was',
    )
    matched_payment        = models.ForeignKey(
        'accounting.PaymentInstruction', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='statement_lines',
    )
    matched_revenue        = models.ForeignKey(
        'accounting.RevenueCollection', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='statement_lines',
    )
    # ── Audit trail on match actions (M9, L7) ────────────────────────────
    # ``matched_by`` is set both by auto-match (system user, may be NULL)
    # and manual-match (the user who clicked Link). ``matched_at`` captures
    # when the match happened. ``updated_at`` tracks the last mutation of
    # any kind on this row.
    matched_by             = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='matched_statement_lines',
    )
    matched_at             = models.DateTimeField(null=True, blank=True)
    updated_at             = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['statement_id', 'line_number']
        indexes = [
            models.Index(fields=['statement', 'match_status']),
            models.Index(fields=['reference']),
        ]

    def __str__(self):
        direction = '-' if self.debit else '+'
        amount = self.debit if self.debit else self.credit
        return f"{self.transaction_date} {direction}{amount} {self.description[:30]}"

    @property
    def amount(self) -> Decimal:
        """Signed transaction amount: credits positive, debits negative."""
        return (self.credit or Decimal('0')) - (self.debit or Decimal('0'))


class TSAReconciliation(AuditBaseModel):
    """
    A reconciliation session for a TSA account over a date window.

    Holds the computed balances and tracks approval state. A single session
    can draw from one or more ``TSABankStatement`` records (e.g. mid-month
    + end-of-month files), so it references the imports via FK on the lines
    rather than directly.
    """
    STATUS_CHOICES = [
        ('DRAFT',     'Draft'),
        ('REVIEWED',  'Reviewed'),
        ('COMPLETED', 'Completed'),
    ]

    tsa_account        = models.ForeignKey(
        'accounting.TreasuryAccount', on_delete=models.PROTECT,
        related_name='reconciliations',
    )
    period_start       = models.DateField()
    period_end         = models.DateField()

    book_balance       = models.DecimalField(max_digits=22, decimal_places=2, default=0)
    statement_balance  = models.DecimalField(max_digits=22, decimal_places=2, default=0)
    adjusted_balance   = models.DecimalField(max_digits=22, decimal_places=2, default=0)
    unmatched_debits   = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    unmatched_credits  = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    # Convenience link; the authoritative data is on TSABankStatementLine.
    statement_import   = models.ForeignKey(
        TSABankStatement, on_delete=models.PROTECT,
        null=True, blank=True, related_name='reconciliations',
    )

    status             = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='DRAFT',
    )
    completed_at       = models.DateTimeField(null=True, blank=True)
    completed_by       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='tsa_reconciliations',
    )
    notes              = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-period_end']
        verbose_name = 'TSA Reconciliation'
        verbose_name_plural = 'TSA Reconciliations'
        indexes = [
            models.Index(fields=['tsa_account', '-period_end']),
            models.Index(fields=['status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tsa_account', 'period_start', 'period_end'],
                name='uniq_tsa_recon_period',
            ),
        ]

    @property
    def difference(self) -> Decimal:
        """Book vs statement — should be zero on completion."""
        return (self.book_balance or Decimal('0')) - (self.statement_balance or Decimal('0'))

    def __str__(self):
        return f"{self.tsa_account.account_number} {self.period_start}→{self.period_end} ({self.status})"
