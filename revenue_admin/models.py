"""
revenue_admin — Revenue Administration / IGR (G8 / FreeBalance GRM pillar).

FUTURE_MODULES §5.8: Quot PSA records revenue (``RevenueHead``,
``RevenueCollection``) but cannot administer it — no taxpayer account,
assessment, demand notice, arrears ledger or enforcement case. This module
adds the taxpayer-centric administration layer.

Scope:
  * Taxpayer            — registry keyed on TIN, individual/corporate profiles.
  * TaxAccount          — per taxpayer per revenue type, running balance.
  * Assessment          — self-assessment and best-of-judgement with objection
                          and appeal states.
  * DemandNotice + BillingRun — property tax & licence renewal cycles.
  * ArrearsLedger       — with ageing.
  * EnforcementCase     — distraint workflow.
  * TaxClearanceCertificate — issue + verification, consumed by ``egp``.

Per spec's commercial recommendation this is the largest build and the
strongest candidate for partnership over build; if partnering, it becomes a
connector inside ``integrations`` instead. This app provides the full native
model surface either way.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel


class Taxpayer(AuditBaseModel):
    CASETYPE_CHOICES = [
        ('individual', 'Individual'),
        ('corporate', 'Corporate'),
    ]

    tin = models.CharField(max_length=30, unique=True, db_index=True)
    case_type = models.CharField(max_length=20, choices=CASETYPE_CHOICES, default='individual')
    full_name = models.CharField(max_length=255, blank=True, default='')
    business_name = models.CharField(max_length=255, blank=True, default='')
    bvn = models.CharField(max_length=30, blank=True, default='', help_text='Linked via integrations where available.')
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=30, blank=True, default='')
    address = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)

    @property
    def display_name(self):
        return self.business_name or self.full_name or self.tin

    class Meta:
        ordering = ['tin']


class TaxAccount(AuditBaseModel):
    taxpayer = models.ForeignKey(
        Taxpayer, on_delete=models.CASCADE, related_name='accounts',
    )
    revenue_head = models.ForeignKey(
        'accounting.RevenueHead', on_delete=models.PROTECT, related_name='+',
    )
    running_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    class Meta:
        ordering = ['taxpayer', 'revenue_head']
        constraints = [
            models.UniqueConstraint(
                fields=['taxpayer', 'revenue_head'], name='unique_taxaccount_per_taxpayer_head',
            ),
        ]


class Assessment(AuditBaseModel):
    ASSESSMENT_TYPE_CHOICES = [
        ('self', 'Self-Assessment'),
        ('boj', 'Best of Judgement'),
        ('amended', 'Amended'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('objected', 'Objected'),
        ('appealed', 'Appealed'),
        ('settled', 'Settled'),
    ]

    taxpayer = models.ForeignKey(
        Taxpayer, on_delete=models.CASCADE, related_name='assessments',
    )
    revenue_head = models.ForeignKey(
        'accounting.RevenueHead', on_delete=models.PROTECT, related_name='+',
    )
    fiscal_year = models.IntegerField(db_index=True)
    assessment_type = models.CharField(max_length=20, choices=ASSESSMENT_TYPE_CHOICES, default='self')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    assessed_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    objection = models.TextField(blank=True, default='')
    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['taxpayer', 'fiscal_year']


class BillingRun(AuditBaseModel):
    """Cyclical billing run (property tax / licence renewals)."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('completed', 'Completed'),
    ]

    revenue_head = models.ForeignKey(
        'accounting.RevenueHead', on_delete=models.PROTECT, related_name='+',
    )
    fiscal_year = models.IntegerField(db_index=True)
    cycle = models.CharField(max_length=60, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notices_created = models.PositiveIntegerField(default=0)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-fiscal_year']


class DemandNotice(AuditBaseModel):
    STATUS_CHOICES = [
        ('issued', 'Issued'),
        ('paid', 'Paid'),
        ('partial', 'Partially Paid'),
        ('disputed', 'Disputed'),
        ('overdue', 'Overdue'),
    ]

    taxpayer = models.ForeignKey(
        Taxpayer, on_delete=models.CASCADE, related_name='demand_notices',
    )
    billing_run = models.ForeignKey(
        BillingRun, on_delete=models.SET_NULL, null=True, blank=True, related_name='notices',
    )
    assessment = models.ForeignKey(
        Assessment, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    notice_number = models.CharField(max_length=60, unique=True)
    amount_due = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    due_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='issued')
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issued_at']


class ArrearsLedger(AuditBaseModel):
    taxpayer = models.ForeignKey(
        Taxpayer, on_delete=models.CASCADE, related_name='arrears',
    )
    fiscal_year = models.IntegerField(db_index=True)
    revenue_head = models.ForeignKey(
        'accounting.RevenueHead', on_delete=models.PROTECT, null=True, blank=True,
        related_name='+',
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    arrears_date = models.DateField(default=timezone.now)
    ageing_days = models.PositiveIntegerField(default=0)
    is_settled = models.BooleanField(default=False)

    class Meta:
        ordering = ['-arrears_date']


class EnforcementCase(AuditBaseModel):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('distraint', 'Distraint Ordered'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]

    taxpayer = models.ForeignKey(
        Taxpayer, on_delete=models.CASCADE, related_name='enforcement_cases',
    )
    arrears = models.ForeignKey(
        ArrearsLedger, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    amount_in_dispute = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    distraint_order = models.CharField(max_length=100, blank=True, default='')
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-opened_at']


class TaxClearanceCertificate(AuditBaseModel):
    STATUS_CHOICES = [
        ('issued', 'Issued'),
        ('verified', 'Verified'),
        ('expired', 'Expired'),
    ]

    taxpayer = models.ForeignKey(
        Taxpayer, on_delete=models.CASCADE, related_name='clearance_certificates',
    )
    certificate_number = models.CharField(max_length=60, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='issued')
    fiscal_year = models.IntegerField(db_index=True)
    issue_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-issue_date']
