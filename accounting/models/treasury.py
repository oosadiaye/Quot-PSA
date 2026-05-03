"""
Treasury & TSA Module
=====================
Implements Treasury Single Account (TSA) architecture as mandated by CBN.
All government payments and receipts flow through the TSA structure.

TSA Architecture:
  Main TSA (CBN) -> Consolidated Revenue Fund -> MDA Sub-Accounts -> Zero-Balance Accounts
"""

from decimal import Decimal
from django.db import models
from core.models import AuditBaseModel


class TreasuryAccount(AuditBaseModel):
    """
    Treasury Single Account structure.
    Main TSA at CBN -> State Sub-Accounts -> MDA Zero-Balance Accounts.

    Per CBN guidelines:
    - Main TSA held at CBN
    - Sub-accounts for MDAs with zero-balance sweep
    - Daily sweep of all sub-accounts to main TSA
    """
    ACCOUNT_TYPE_CHOICES = [
        ('MAIN_TSA',      'Main TSA (CBN)'),
        ('CONSOLIDATED',  'Consolidated Revenue Fund'),
        ('SUB_ACCOUNT',   'MDA Sub-Account'),
        ('ZERO_BALANCE',  'Zero Balance Account (MDA)'),
        ('HOLDING',       'Holding Account'),
        ('REVENUE',       'Revenue Collection Account'),
    ]

    account_number  = models.CharField(max_length=20, unique=True, db_index=True)
    account_name    = models.CharField(max_length=200)
    bank            = models.CharField(max_length=100, help_text="CBN or designated bank")
    sort_code       = models.CharField(max_length=10, blank=True, default='')
    account_type    = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    mda             = models.ForeignKey(
        'accounting.AdministrativeSegment',
        null=True, blank=True, on_delete=models.PROTECT,
        related_name='tsa_accounts',
        help_text="MDA that owns this sub-account",
    )
    fund_segment    = models.ForeignKey(
        'accounting.FundSegment', null=True, blank=True,
        on_delete=models.PROTECT,
    )
    parent_account  = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.PROTECT, related_name='sub_accounts',
    )
    gl_cash_account = models.ForeignKey(
        'accounting.Account',
        null=True, blank=True,  # nullable for backfill; service layer warns if unset
        on_delete=models.PROTECT,
        related_name='tsa_accounts',
        limit_choices_to={'account_type': 'Asset', 'is_active': True},
        help_text=(
            "GL control account for this TSA. Every cash-side posting against "
            "this treasury account should hit this GL account. Required for "
            "IPSAS-compliant cash flow reporting."
        ),
    )
    ncoa_cash_code  = models.ForeignKey(
        # Was: 'accounting.NCoACode' (the 52-digit composite store) —
        # mistargeted: that model is created on-demand from journal lines
        # and is empty until transactions exist. The intent (per the
        # original help text) was the *economic segment* classifier so
        # cash-flow reports can group TSAs by NCoA economic code. Re-
        # targeting to EconomicSegment makes the dropdown selectable
        # against the live 1,147-row taxonomy and keeps the field
        # name backward-compatible.
        'accounting.EconomicSegment',
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='tsa_accounts',
        help_text=(
            "NCoA Economic Segment classification for this TSA's cash "
            "position (e.g. '31030205 — Cash Transfer / JAAC Direct "
            "Allocation'). Used by IPSAS Cash Flow Statement to group "
            "treasury accounts by economic classification."
        ),
    )
    is_active       = models.BooleanField(default=True)
    current_balance = models.DecimalField(
        max_digits=22, decimal_places=2, default=0,
        help_text="Current balance (updated by payment/receipt postings)",
    )
    last_reconciled = models.DateField(null=True, blank=True)
    description     = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['account_type', 'account_number']
        verbose_name = 'TSA Account'
        verbose_name_plural = 'TSA Accounts'

    def __str__(self):
        return f"{self.account_number} - {self.account_name}"


class PaymentVoucherGov(AuditBaseModel):
    """
    Government Payment Voucher (PV) — the primary payment document.
    Created after goods/services receipt. Approved per workflow. Paid via TSA.

    Every PV must:
    1. Reference a valid NCoA code
    2. Have approved appropriation with available balance
    3. Have released warrant for the quarter
    4. Pass workflow approval chain
    5. Generate PaymentInstruction for TSA settlement
    """
    STATUS_CHOICES = [
        ('DRAFT',       'Draft'),
        ('CHECKED',     'Checked'),
        ('AUDITED',     'Internal Audit Verified'),
        ('APPROVED',    'Approved by Accounting Officer'),
        ('SCHEDULED',   'Scheduled for Payment'),
        ('PAID',        'Paid'),
        ('CANCELLED',   'Cancelled'),
        ('REVERSED',    'Reversed'),
    ]
    PAYMENT_TYPE_CHOICES = [
        ('VENDOR',      'Vendor / Contractor Payment'),
        ('SALARY',      'Salary Payment'),
        ('ALLOWANCE',   'Allowance / Honorarium'),
        ('PENSION',     'Pension Remittance'),
        ('STATUTORY',   'Statutory Deduction Remittance'),
        ('REFUND',      'Revenue Refund'),
        ('TRANSFER',    'Inter-Account Transfer'),
        ('PETTY_CASH',  'Petty Cash Replenishment'),
        ('SUBVENTION',  'Subvention / Transfer'),
        ('DEBT',        'Debt Service Payment'),
    ]

    voucher_number   = models.CharField(max_length=30, unique=True, db_index=True)
    payment_type     = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES)
    ncoa_code        = models.ForeignKey(
        'accounting.NCoACode', on_delete=models.PROTECT,
        related_name='payment_vouchers',
    )
    appropriation    = models.ForeignKey(
        'budget.Appropriation', on_delete=models.PROTECT,
        related_name='payment_vouchers', null=True, blank=True,
    )
    warrant          = models.ForeignKey(
        'budget.Warrant', on_delete=models.PROTECT,
        null=True, blank=True, related_name='payment_vouchers',
    )
    payee_name       = models.CharField(max_length=200)
    payee_account    = models.CharField(max_length=20)
    payee_bank       = models.CharField(max_length=100)
    payee_sort_code  = models.CharField(max_length=10, blank=True, default='')
    gross_amount     = models.DecimalField(max_digits=20, decimal_places=2)
    wht_amount       = models.DecimalField(
        max_digits=20, decimal_places=2, default=0,
        help_text="Withholding Tax deduction",
    )
    net_amount       = models.DecimalField(max_digits=20, decimal_places=2)
    narration        = models.CharField(max_length=500)
    tsa_account      = models.ForeignKey(
        TreasuryAccount, on_delete=models.PROTECT,
        related_name='payment_vouchers',
    )
    source_document  = models.CharField(
        max_length=100, blank=True, default='',
        help_text="PO/Contract reference number",
    )
    invoice_number   = models.CharField(max_length=50, blank=True, default='')
    invoice_date     = models.DateField(null=True, blank=True)
    status           = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='DRAFT',
    )
    journal          = models.ForeignKey(
        'accounting.JournalHeader', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='payment_vouchers',
    )
    notes            = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payment Voucher'
        verbose_name_plural = 'Payment Vouchers'
        indexes = [
            models.Index(fields=['status', 'payment_type']),
            models.Index(fields=['voucher_number']),
        ]

    def __str__(self):
        return f"PV {self.voucher_number} - {self.payee_name} - NGN {self.net_amount:,.2f}"

    def save(self, *args, **kwargs):
        # Ensure net_amount = gross - (wht + all other deductions).
        # When deduction lines exist they are authoritative; wht_amount on
        # the header is kept in sync for backward-compat with callers that
        # only know about the single-WHT model.
        total_deductions = self.wht_amount or Decimal('0')
        if self.pk:
            extra = self.deductions.aggregate(
                s=models.Sum('amount')
            )['s'] or Decimal('0')
            # If deduction lines exist, trust them as the source of truth.
            if extra:
                total_deductions = extra
                # Mirror the sum of WHT-typed deductions onto wht_amount for
                # reports that still read the flat field.
                wht_sum = self.deductions.filter(
                    deduction_type='WHT'
                ).aggregate(s=models.Sum('amount'))['s'] or Decimal('0')
                self.wht_amount = wht_sum
        self.net_amount = (self.gross_amount or Decimal('0')) - total_deductions
        super().save(*args, **kwargs)


class PaymentVoucherDeduction(AuditBaseModel):
    """
    Deduction / charge line applied at payment time on a PaymentVoucher.

    Nigerian IFMIS recognises several statutory / operational deductions
    on outgoing payments, all at the point of disbursement (cash basis):
        WHT           — Withholding Tax (FIRS schedule)
        STAMP_DUTY    — Stamp duty. NOTE: abolished on Delta State
                        contractor/vendor payments by Circular
                        AG/CIR/54/C/Vol.10/1/134 (April 2026). Retained
                        as a type for historical records only; rate = 0.
        VAT_WITHHELD  — VAT withheld at source by the MDA
        HANDLING      — 0.5 % Handling Charge on contract payments.
                        Deducted at point of FIRST payment only
                        (Circular AG/CIR/54/C/Vol.10/1/134, Apr 2026).
                        Factor = 0.5 / 107.5 = 0.004651.
        INSURANCE     — Insurance premium deducted at source
        RETENTION     — Contract retention money
        OTHER         — Any other documented deduction

    Each line generates a separate credit row at payment time, crediting
    the associated liability / revenue account.
    """

    DEDUCTION_TYPE_CHOICES = [
        ('WHT',          'Withholding Tax'),
        ('STAMP_DUTY',   'Stamp Duty'),
        ('VAT_WITHHELD', 'VAT Withheld at Source'),
        ('HANDLING',     'Bank / Handling Charges'),
        ('INSURANCE',    'Insurance Premium'),
        ('RETENTION',    'Contract Retention'),
        ('OTHER',        'Other Deduction'),
    ]

    payment_voucher = models.ForeignKey(
        PaymentVoucherGov, on_delete=models.CASCADE,
        related_name='deductions',
    )
    deduction_type = models.CharField(
        max_length=15, choices=DEDUCTION_TYPE_CHOICES,
    )
    description = models.CharField(max_length=200, blank=True, default='')
    # FK helpers — optional, used when the deduction type maps to a
    # registered tax/rate code. Leave null for ad-hoc charges.
    withholding_tax = models.ForeignKey(
        'accounting.WithholdingTax', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pv_deductions',
    )
    rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Rate used to compute amount (informational).',
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    gl_account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT,
        related_name='pv_deductions',
        help_text='GL liability/revenue account credited at payment time.',
    )

    class Meta:
        ordering = ['payment_voucher', 'id']
        indexes = [models.Index(fields=['deduction_type'])]

    def __str__(self):
        return (
            f"{self.payment_voucher.voucher_number} · "
            f"{self.get_deduction_type_display()} · NGN {self.amount:,.2f}"
        )


class PaymentInstruction(AuditBaseModel):
    """
    Electronic payment instruction sent to CBN/TSA gateway.
    Generated from approved PaymentVoucher.
    Tracks the actual bank settlement status.
    """
    STATUS_CHOICES = [
        ('PENDING',    'Pending Submission'),
        ('SUBMITTED',  'Submitted to CBN/Bank'),
        ('PROCESSING', 'Processing'),
        ('PROCESSED',  'Processed / Paid'),
        ('FAILED',     'Failed'),
        ('REVERSED',   'Reversed'),
    ]

    payment_voucher     = models.OneToOneField(
        PaymentVoucherGov, on_delete=models.PROTECT,
        related_name='payment_instruction',
    )
    tsa_account         = models.ForeignKey(
        TreasuryAccount, on_delete=models.PROTECT,
        related_name='payment_instructions',
    )
    beneficiary_name    = models.CharField(max_length=200)
    beneficiary_account = models.CharField(max_length=20)
    beneficiary_bank    = models.CharField(max_length=100)
    beneficiary_sort    = models.CharField(max_length=10, blank=True, default='')
    amount              = models.DecimalField(max_digits=20, decimal_places=2)
    narration           = models.CharField(max_length=200)
    batch_reference     = models.CharField(max_length=50, blank=True, default='')
    bank_reference      = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Bank settlement reference (populated after processing)",
    )
    submitted_at        = models.DateTimeField(null=True, blank=True)
    processed_at        = models.DateTimeField(null=True, blank=True)
    status              = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='PENDING',
    )
    failure_reason      = models.TextField(blank=True, default='')
    # ── Bank reconciliation flags ────────────────────────────────────────
    # Flipped to True by TSAReconciliation.complete(); used by reports to
    # filter out already-reconciled settlements. The FK links back to the
    # session that reconciled it for audit trail.
    is_reconciled       = models.BooleanField(default=False, db_index=True)
    reconciliation      = models.ForeignKey(
        'accounting.TSAReconciliation', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reconciled_payments',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payment Instruction'
        verbose_name_plural = 'Payment Instructions'

    def __str__(self):
        return f"PI {self.batch_reference} - {self.beneficiary_name} - NGN {self.amount:,.2f}"
