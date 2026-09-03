"""
personnel_budget — Establishment & Personnel Cost Control (G3 / FreeBalance CSPL).

The single most valuable control module on the FUTURE_MODULES list: personnel
cost is the largest recurrent line in any State budget and is the only
expenditure stream that currently bypasses commitment control
(``accounting/services/payroll_posting.py`` writes salary expense straight to
the GL with no appropriation lookup and no budget-check).

Scope (FUTURE_MODULES §5.3):
  * EstablishmentPost  — approved post count per MDA per grade, with an
    approval chain. The nominal (filled) roll cannot exceed the establishment.
  * EstablishmentVariance — filled vs approved, by MDA and by grade.
  * Payroll budget gate — bind PayrollRun to its personnel appropriation
    lines; commit on approval through the existing BudgetCheckRule engine.
  * PersonnelCostForecast — projected payroll to year end against
    appropriation, including known increments and promotions.
  * Block or warn on establishment breach at appointment, promotion, transfer.

Hard dependency: hrm, budget, accounting. Activation without all three is
rejected at save time (see ModuleEnabled + dependency validation).

Default state per FUTURE_MODULES: ON for government tenants.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel


class EstablishmentPost(AuditBaseModel):
    """Approved post count for an MDA + grade combination.

    The nominal roll of filled posts may never exceed the approved
    establishment. Creating a post requires an approved EstablishmentPost
    row (or an explicit waiver) — enforced in the serializer/service layer.
    """

    GRADE_CHOICES = [
        ('Entry', 'Entry Level'),
        ('Mid', 'Mid Level'),
        ('Senior', 'Senior Level'),
        ('Manager', 'Manager'),
        ('Director', 'Director'),
        ('Executive', 'Executive'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    # Linked to the NCoA administrative segment (an MDA) when present,
    # otherwise a free-text MDA reference.
    mda_admin = models.ForeignKey(
        'accounting.AdministrativeSegment', on_delete=models.PROTECT,
        null=True, blank=True, related_name='+',
        help_text='NCoA administrative segment (MDA) this post belongs to.',
    )
    mda_name = models.CharField(
        max_length=200, blank=True, default='',
        help_text='Free-text MDA when no NCoA segment is linked.',
    )
    grade = models.CharField(max_length=20, choices=GRADE_CHOICES)
    approved_quantity = models.PositiveIntegerField(
        default=0,
        help_text='Total approved posts for this MDA + grade.',
    )
    effective_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='draft',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    comments = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['mda_name', 'grade']
        indexes = [
            models.Index(fields=['mda_name', 'grade']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.mda_name or self.mda_admin} — {self.grade} ({self.approved_quantity})'


class EstablishmentVariance(AuditBaseModel):
    """Filled vs approved establishment, by MDA and grade.

    Computed snapshot that surface headroom and breaches. Updated whenever
    an employee is appointed, promoted or transferred (service layer).
    """

    post = models.ForeignKey(
        EstablishmentPost, on_delete=models.CASCADE, related_name='variances',
    )
    filled_quantity = models.PositiveIntegerField(default=0)
    approved_quantity = models.PositiveIntegerField(default=0)
    variance = models.IntegerField(
        default=0,
        help_text='filled - approved. Negative = headroom; positive = breach.',
    )
    is_breach = models.BooleanField(default=False)
    computed_at = models.DateTimeField(auto_now=True)

    @property
    def utilisation_pct(self):
        if self.approved_quantity <= 0:
            return 0.0
        return round((self.filled_quantity / self.approved_quantity) * 100, 2)

    class Meta:
        ordering = ['post']


class PersonnelCostForecast(AuditBaseModel):
    """Projected payroll to year end against the personnel appropriation.

    Includes known increments and promotions. Feeds cash_planning and flags
    forecast over-expenditure against the approved personnel line.
    """

    fiscal_year = models.IntegerField(db_index=True)
    mda_name = models.CharField(max_length=200, blank=True, default='')
    appropriation_line = models.ForeignKey(
        'budget.Appropriation', on_delete=models.PROTECT, null=True, blank=True,
        related_name='personnel_forecasts',
    )
    month = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='1-12 for a monthly line; null for the annual total row.',
    )
    projected_payroll = models.DecimalField(
        max_digits=18, decimal_places=2, default=0,
    )
    approved_appropriation = models.DecimalField(
        max_digits=18, decimal_places=2, default=0,
    )
    projected_increment = models.DecimalField(
        max_digits=18, decimal_places=2, default=0,
        help_text='Known increments (anniversary) expected in this period.',
    )
    projected_promotion = models.DecimalField(
        max_digits=18, decimal_places=2, default=0,
        help_text='Known promotion-value changes in this period.',
    )
    notes = models.TextField(blank=True, default='')

    @property
    def total_projected(self):
        return (
            self.projected_payroll
            + self.projected_increment
            + self.projected_promotion
        )

    @property
    def over_appropriation(self):
        return self.total_projected > self.approved_appropriation

    class Meta:
        ordering = ['fiscal_year', 'month']
        indexes = [
            models.Index(fields=['fiscal_year', 'mda_name']),
        ]


class PayrollBudgetBinding(AuditBaseModel):
    """Binds a PayrollRun to its personnel appropriation line(s).

    When the personnel_budget module is active (default ON), a PayrollRun may
    not be approved (posting to GL) unless it has an approved binding to an
    appropriation line whose remaining balance covers the payroll amount.
    """

    payroll_run = models.OneToOneField(
        'hrm.PayrollRun', on_delete=models.CASCADE, related_name='budget_binding',
    )
    appropriation_line = models.ForeignKey(
        'budget.Appropriation', on_delete=models.PROTECT, related_name='+',
    )
    bound_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    remaining_at_binding = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    check_level = models.CharField(
        max_length=10, default='STRICT',
        help_text='Copied from the governing BudgetCheckRule at binding time.',
    )
    bound_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    bound_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-bound_at']
