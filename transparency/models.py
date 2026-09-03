"""
transparency — Fiscal Transparency Portal (G5 / FreeBalance GPTP+GPER).

FUTURE_MODULES §5.5: per spec the public, unauthenticated surface must be a
separate URL namespace with its own throttling and read-only DB role, served
from `ReportSnapshot` never from live transactional tables.

This Django app holds the *gated* backend that governs what is published:
  * PublicationPolicy — what is published, at what aggregation, on what lag,
    approved by a named officer. Nothing reaches the public surface without an
    explicit publish action.
  * Publication       — an immutable publish event referencing a ReportSnapshot.
  * RedactionRule     — redaction rules for personal data applied at export.
  * DataExport        — open data CSV/JSON export registration per dataset.

The public read-only surface itself lives elsewhere (a separate
``/public/`` namespace with its own throttling + read-only role); this app is
the governance & policy side, and is the part that toggles off with the
module (``module_key = 'transparency'``). The separate public namespace is not
routed here precisely so that its removal is enforced at the routing layer.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel


class PublicationPolicy(AuditBaseModel):
    """Governs what is published, at what aggregation, on what lag."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('superseded', 'Superseded'),
    ]

    DATASET_CHOICES = [
        ('enacted_budget', 'Enacted Budget'),
        ('budget_execution', 'Budget Execution'),
        ('contract_awards', 'Contract Awards'),
        ('payments', 'Payments Above Threshold'),
        ('revenue_performance', 'Revenue Performance'),
        ('citizen_budget', 'Citizen Budget Summary'),
    ]

    dataset = models.CharField(max_length=30, choices=DATASET_CHOICES, db_index=True)
    aggregation = models.CharField(max_length=100, default='MDA level')
    lag_days = models.PositiveIntegerField(
        default=30, help_text='Publication lag in days after period close.',
    )
    min_amount_threshold = models.DecimalField(
        max_digits=18, decimal_places=2, default=0,
        help_text='Only transactions at/above this amount are published.',
    )
    requires_snapshot = models.BooleanField(
        default=True,
        help_text='Never serve live tables; publish only from ReportSnapshot rows.',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    approved_by = models.CharField(max_length=200, blank=True, default='')
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['dataset']
        constraints = [
            models.UniqueConstraint(
                fields=['dataset'], condition=models.Q(status='approved'),
                name='unique_approved_policy_per_dataset',
            ),
        ]


class Publication(AuditBaseModel):
    """An immutable publish event referencing a ReportSnapshot."""

    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('published', 'Published'),
        ('retracted', 'Retracted'),
    ]

    policy = models.ForeignKey(
        PublicationPolicy, on_delete=models.PROTECT, related_name='publications',
    )
    snapshot = models.ForeignKey(
        'accounting.ReportSnapshot', on_delete=models.PROTECT, null=True, blank=True,
        related_name='+', help_text='Source snapshot; never live tables.',
    )
    title = models.CharField(max_length=255)
    dataset_key = models.CharField(max_length=30)
    fiscal_year = models.IntegerField(null=True, blank=True)
    period = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    published_at = models.DateTimeField(null=True, blank=True)
    published_url = models.URLField(blank=True, default='')
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )

    class Meta:
        ordering = ['-published_at']


class RedactionRule(AuditBaseModel):
    """Redaction rules for personal data applied at open-data export."""

    FIELD_CHOICES = [
        ('employee_name', 'Employee Name'),
        ('employee_number', 'Employee Number'),
        ('vendor_name', 'Vendor Name'),
        ('vendor_bvn', 'Vendor BVN'),
        ('vendor_tin', 'Vendor TIN'),
        ('phone', 'Phone Number'),
        ('email', 'Email Address'),
        ('address', 'Physical Address'),
        ('bank_account', 'Bank Account Number'),
    ]

    field_name = models.CharField(max_length=50, choices=FIELD_CHOICES)
    pattern = models.CharField(
        max_length=200, blank=True, default='',
        help_text='Optional regex identifying the sensitive value.',
    )
    replacement = models.CharField(
        max_length=50, default='***',
        help_text='Replacement text applied at export.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['field_name']


class DataExport(AuditBaseModel):
    """Registration of an open-data export per published dataset."""

    FORMAT_CHOICES = [
        ('csv', 'CSV'),
        ('json', 'JSON'),
    ]

    dataset_key = models.CharField(max_length=30)
    format = models.CharField(max_length=10, choices=FORMAT_CHOICES, default='csv')
    publication = models.ForeignKey(
        Publication, on_delete=models.CASCADE, related_name='exports',
    )
    file = models.FileField(upload_to='transparency/exports/%Y/', null=True, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
