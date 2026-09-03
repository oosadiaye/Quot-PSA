"""
budget_prep — Budget Preparation (G2 / FreeBalance BPRE).

FUTURE_MODULES §5.2: 'budget' already covers the enacted-legislation side
(Appropriation). There is no system for the *preparation* side — the call
circular, MDA ceilings, MTEF, and the multi-stage submission before anything
becomes an Appropriation. That work runs on spreadsheets and email today.

Scope:
  * CallCircular          — annual Budget Call Circular with ceilings and
    submission deadlines per MDA.
  * MTEFProjection        — three-year Medium Term Expenditure Framework.
  * MDACeiling            — spending ceiling assigned per MDA (from the call
    circular); the preparation base line.
  * BudgetSubmission      — the MDA's proposed budget, carrying a stage
    through the review lifecycle (draft → review → incorporate).
  * SubmissionLine        — a proposed line against NCoA + a personnel
    establishment note. Bound to ceilings (no line above its ceiling).
  * ReviewComment         — Ministry of Budget review notes on a submission.

The ``stage`` field on BudgetSubmission advances through the budget calendar;
an incorporated submission may be passed to the 'budget' app as a draft
Appropriation (a hand-off, not an automatic flip — the legislature flow stays
in 'budget').
"""
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel


class CallCircular(AuditBaseModel):
    """Annual Budget Call Circular."""

    fiscal_year = models.IntegerField(db_index=True)
    issue_date = models.DateField(default=timezone.now)
    submission_deadline = models.DateField(null=True, blank=True)
    guidelines = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=False)
    document = models.FileField(
        upload_to='budget_prep/circular/%Y/', null=True, blank=True,
    )

    class Meta:
        ordering = ['-fiscal_year']


class MTEFProjection(AuditBaseModel):
    """Three-year Medium Term Expenditure Framework projection."""

    fiscal_year = models.IntegerField(db_index=True)
    inflation_assumption = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    exchange_rate_assumption = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    oil_price_assumption = models.DecimalField(max_digits=12, decimal_places=2, default=0, null=True, blank=True)
    aggregate_revenue = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    aggregate_expenditure = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    fiscal_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    class Meta:
        ordering = ['-fiscal_year']


class MDACeiling(AuditBaseModel):
    """Spending ceiling assigned per MDA for a budget year."""

    fiscal_year = models.IntegerField(db_index=True)
    mda_name = models.CharField(max_length=200, db_index=True)
    personnel_ceiling = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    overhead_ceiling = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    capital_ceiling = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    @property
    def total_ceiling(self):
        return self.personnel_ceiling + self.overhead_ceiling + self.capital_ceiling

    class Meta:
        ordering = ['fiscal_year', 'mda_name']


class BudgetSubmission(AuditBaseModel):
    """MDA proposed budget, carrying a stage through review."""

    STAGE_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted to Budget Office'),
        ('in_review', 'Under Review'),
        ('revised', 'Revision Requested'),
        ('incorporated', 'Incorporated / Adopted'),
        ('rejected', 'Rejected'),
    ]

    fiscal_year = models.IntegerField(db_index=True)
    mda_name = models.CharField(max_length=200, db_index=True)
    circular = models.ForeignKey(
        CallCircular, on_delete=models.PROTECT, null=True, blank=True,
        related_name='submissions',
    )
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='draft')
    submitted_at = models.DateTimeField(null=True, blank=True)
    total_personnel = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_overhead = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_capital = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['fiscal_year', 'mda_name']


class SubmissionLine(AuditBaseModel):
    """A proposed line against NCoA, bound to the MDA ceiling."""

    LINE_TYPE_CHOICES = [
        ('personnel', 'Personnel'),
        ('overhead', 'Overhead'),
        ('capital', 'Capital'),
    ]

    submission = models.ForeignKey(
        BudgetSubmission, on_delete=models.CASCADE, related_name='lines',
    )
    line_type = models.CharField(max_length=20, choices=LINE_TYPE_CHOICES)
    administrative = models.ForeignKey(
        'accounting.AdministrativeSegment', on_delete=models.PROTECT, null=True, blank=True,
        related_name='+',
    )
    economic = models.ForeignKey(
        'accounting.EconomicSegment', on_delete=models.PROTECT, null=True, blank=True,
        related_name='+',
    )
    functional = models.ForeignKey(
        'accounting.FunctionalSegment', on_delete=models.PROTECT, null=True, blank=True,
        related_name='+',
    )
    description = models.CharField(max_length=255, blank=True, default='')
    proposed_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    ceiling_reference = models.ForeignKey(
        MDACeiling, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )

    class Meta:
        ordering = ['submission', 'line_type']


class ReviewComment(AuditBaseModel):
    """Ministry of Budget review note on a submission."""

    submission = models.ForeignKey(
        BudgetSubmission, on_delete=models.CASCADE, related_name='review_comments',
    )
    comment = models.TextField(blank=True, default='')
    action_required = models.BooleanField(default=False)
    commented_by = models.CharField(max_length=200, blank=True, default='')
    commented_at = models.DateTimeField(auto_now_add=True)
