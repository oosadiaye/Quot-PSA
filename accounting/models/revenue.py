"""
Revenue Collection Module (IGR)
================================
Manages Internally Generated Revenue (IGR) for state governments.
Covers PAYE, direct assessment, fees, fines, licenses, and other revenue streams.

All collections sweep to TSA via e-collection platforms (Remita, JCHUB, etc.).
"""

from django.db import models
from core.models import AuditBaseModel


class RevenueHead(AuditBaseModel):
    """
    IGR Revenue Classification — maps to NCoA Economic Segment.
    Each revenue type has a corresponding NCoA economic code in the 1xxxxxxx range.
    """
    REVENUE_TYPE_CHOICES = [
        ('PAYE',              'Pay As You Earn (PAYE)'),
        ('DIRECT_ASSESSMENT', 'Direct Assessment'),
        ('ROAD_TAX',          'Road Tax / Vehicle License'),
        ('STAMP_DUTY',        'Stamp Duty'),
        ('CGT',               'Capital Gains Tax'),
        ('WHT',               'Withholding Tax'),
        ('FEES_FINES',        'Fees and Fines'),
        ('LICENSE',           'Licenses and Permits'),
        ('RENT',              'Rent on Government Property'),
        ('DIVIDEND',          'Dividends from Government Companies'),
        ('INVESTMENT',        'Investment Income'),
        ('GRANT',             'Grants and Transfers'),
        ('FAAC',              'Federation Account Allocation'),
        ('OTHER',             'Other IGR'),
    ]

    code             = models.CharField(max_length=20, unique=True, db_index=True)
    name             = models.CharField(max_length=200)
    economic_segment = models.ForeignKey(
        'accounting.EconomicSegment', on_delete=models.PROTECT,
        related_name='revenue_heads',
        help_text="NCoA economic code for this revenue type",
    )
    revenue_type     = models.CharField(max_length=30, choices=REVENUE_TYPE_CHOICES)
    collection_mda   = models.ForeignKey(
        'accounting.AdministrativeSegment',
        on_delete=models.PROTECT, null=True, blank=True,
        related_name='revenue_heads',
        help_text="MDA responsible for collecting this revenue",
    )
    remittance_rate  = models.DecimalField(
        max_digits=5, decimal_places=2, default=100,
        help_text="Percentage of collection remitted to TSA (default 100%)",
    )
    is_active        = models.BooleanField(default=True)
    description      = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['code']
        verbose_name = 'Revenue Head'
        verbose_name_plural = 'Revenue Heads'

    def __str__(self):
        return f"{self.code} - {self.name}"


class RevenueCollection(AuditBaseModel):
    """
    IGR Revenue Receipt — individual revenue transaction.
    Collected via e-collection platforms (Remita, JCHUB, etc.).
    All collections sweep to TSA automatically.

    IPSAS Accrual Treatment:
    - Cash receipt: DR TSA / CR Revenue Account
    - Accrual: DR Receivables / CR Revenue Account
    """
    STATUS_CHOICES = [
        ('PENDING',    'Pending Confirmation'),
        ('CONFIRMED',  'Confirmed'),
        ('POSTED',     'Posted to GL'),
        ('REVERSED',   'Reversed'),
        ('CANCELLED',  'Cancelled'),
    ]
    COLLECTION_CHANNEL_CHOICES = [
        ('BANK',    'Bank Branch'),
        ('ONLINE',  'Online Payment'),
        ('USSD',    'USSD / Mobile'),
        ('AGENT',   'Agent Banking'),
        ('COUNTER', 'Government Counter'),
        ('POS',     'Point of Sale'),
    ]

    receipt_number     = models.CharField(max_length=30, unique=True, db_index=True)
    revenue_head       = models.ForeignKey(
        RevenueHead, on_delete=models.PROTECT,
        related_name='collections',
    )
    ncoa_code          = models.ForeignKey(
        'accounting.NCoACode', on_delete=models.PROTECT,
        related_name='revenue_collections',
    )
    payer_name         = models.CharField(max_length=200)
    payer_tin          = models.CharField(
        max_length=20, blank=True, default='',
        help_text="Taxpayer Identification Number",
    )
    payer_phone        = models.CharField(max_length=20, blank=True, default='')
    payer_address      = models.CharField(max_length=500, blank=True, default='')
    amount             = models.DecimalField(max_digits=20, decimal_places=2)
    payment_reference  = models.CharField(max_length=50, unique=True)
    rrr                = models.CharField(
        max_length=20, blank=True, default='',
        help_text="Remita Retrieval Reference",
    )
    tsa_account        = models.ForeignKey(
        'accounting.TreasuryAccount', on_delete=models.PROTECT,
        related_name='revenue_collections',
    )
    collection_date    = models.DateField()
    value_date         = models.DateField(
        null=True, blank=True,
        help_text="Date funds actually credited to TSA",
    )
    collection_channel = models.CharField(
        max_length=10, choices=COLLECTION_CHANNEL_CHOICES, default='BANK',
    )
    collecting_mda     = models.ForeignKey(
        'accounting.AdministrativeSegment',
        on_delete=models.PROTECT, null=True, blank=True,
        related_name='revenue_collections',
    )
    status             = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='PENDING',
    )
    journal            = models.ForeignKey(
        'accounting.JournalHeader', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='revenue_collections',
    )
    period_month       = models.IntegerField(
        null=True, blank=True,
        help_text="Assessment period month (for PAYE)",
    )
    period_year        = models.IntegerField(
        null=True, blank=True,
        help_text="Assessment period year (for PAYE)",
    )
    description        = models.CharField(max_length=500, blank=True, default='')
    # ── Bank reconciliation flags (H1) ───────────────────────────────────
    # Flipped by TSAReconciliation.complete(); used by aging/report queries
    # to exclude already-reconciled rows. The FK preserves who/when.
    is_reconciled      = models.BooleanField(default=False, db_index=True)
    reconciliation     = models.ForeignKey(
        'accounting.TSAReconciliation', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reconciled_revenues',
    )

    class Meta:
        ordering = ['-collection_date', '-created_at']
        verbose_name = 'Revenue Collection'
        verbose_name_plural = 'Revenue Collections'
        indexes = [
            models.Index(fields=['revenue_head', 'collection_date']),
            models.Index(fields=['status', 'collection_date']),
            models.Index(fields=['payer_tin']),
        ]

    def __str__(self):
        return f"OR {self.receipt_number} - {self.payer_name} - NGN {self.amount:,.2f}"
