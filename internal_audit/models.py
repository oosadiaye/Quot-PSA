"""
internal_audit — Internal Audit Management (G11 / FreeBalance GPIA).

FUTURE_MODULES §5.11: Quot PSA has a complete audit *trail*
(``TransactionAuditLog``, plus simple_history on tenant models) and a viewer.
It has no audit *practice*: no universe, no plan, no working papers, no
findings register. This module adds the practice — a second buyer inside the
OAG (the internal audit unit).
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel


class AuditUniverse(AuditBaseModel):
    """Auditable entities with risk scoring."""

    entity_name = models.CharField(max_length=255)
    entity_ref = models.CharField(max_length=100, blank=True, default='')
    risk_score = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-risk_score']


class AuditPlan(AuditBaseModel):
    """Risk-based annual plan with resource allocation."""

    PLAN_STATUS_CHOICES = [
        ('draft', 'Draft'), ('approved', 'Approved'), ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    fiscal_year = models.IntegerField(db_index=True)
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=PLAN_STATUS_CHOICES, default='draft')
    total_engagements = models.PositiveIntegerField(default=0)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-fiscal_year']


class AuditEngagement(AuditBaseModel):
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('fieldwork', 'Fieldwork'),
        ('drafting', 'Drafting'),
        ('reviewed', 'Reviewed'),
        ('issued', 'Issued'),
        ('cancelled', 'Cancelled'),
    ]

    plan = models.ForeignKey(AuditPlan, on_delete=models.CASCADE, related_name='engagements')
    universe = models.ForeignKey(
        AuditUniverse, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
    )
    title = models.CharField(max_length=255)
    scope = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    team = models.JSONField(default=list, blank=True)
    planned_start = models.DateField(null=True, blank=True)
    planned_end = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['plan', 'title']


class WorkingPaper(AuditBaseModel):
    """Evidence with immutable attachment references."""

    engagement = models.ForeignKey(
        AuditEngagement, on_delete=models.CASCADE, related_name='working_papers',
    )
    title = models.CharField(max_length=255)
    reference = models.CharField(max_length=100, blank=True, default='')
    description = models.TextField(blank=True, default='')
    attachment = models.FileField(upload_to='internal_audit/papers/%Y/', null=True, blank=True)
    attachment_hash = models.CharField(max_length=64, blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )

    class Meta:
        ordering = ['engagement', 'title']


class AuditFinding(AuditBaseModel):
    RATING_CHOICES = [
        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical'),
    ]

    STATUS_CHOICES = [
        ('open', 'Open'), ('agreed', 'Agreed'), ('implemented', 'Implemented'),
        ('closed', 'Closed'), ('accepted_risk', 'Accepted Risk'),
    ]

    engagement = models.ForeignKey(
        AuditEngagement, on_delete=models.CASCADE, related_name='findings',
    )
    title = models.CharField(max_length=255)
    rating = models.CharField(max_length=20, choices=RATING_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    recommendation = models.TextField(blank=True, default='')
    management_response = models.TextField(blank=True, default='')
    agreed_action = models.TextField(blank=True, default='')
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['engagement', '-rating']


class FollowUp(AuditBaseModel):
    """Implementation tracking and overdue escalation."""

    finding = models.ForeignKey(
        AuditFinding, on_delete=models.CASCADE, related_name='follow_ups',
    )
    follow_up_date = models.DateField(default=timezone.now)
    note = models.TextField(blank=True, default='')
    is_overdue = models.BooleanField(default=False)
    escalated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )

    class Meta:
        ordering = ['-follow_up_date']


class ContinuousAuditRule(AuditBaseModel):
    """Continuous-auditing hook definitions querying the existing audit trail.

    Example exception patterns per spec: split purchases below threshold,
    weekend postings, dormant-vendor payments, SoD override usage.
    """

    name = models.CharField(max_length=255)
    sql_hint = models.TextField(
        blank=True, default='',
        help_text='Human-readable description of the exception query. Actual '
                  'reflex query implementation added in build phase.',
    )
    schedule = models.CharField(max_length=50, default='monthly')
    is_active = models.BooleanField(default=True)