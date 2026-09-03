"""
legal — Legal, Risk & Case Tracking (G13 / FreeBalance GPLR+GPCT).

FUTURE_MODULES §5.15: ``LegalCase`` with parties, court, stage and hearing
diary; ``CaseCost`` for legal fees and awards; ``RiskRegister`` with
likelihood, impact and mitigation owner; automatic linkage to ``Provision``
and ``ContingentLiability`` (accounting.models.provision), which already
implement IPSAS 19 — so a judgement debt raises the provision rather than
being tracked separately.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import AuditBaseModel


class LegalCase(AuditBaseModel):
    STAGE_CHOICES = [
        ('intake', 'Intake'),
        ('pleadings', 'Pleadings'),
        ('hearing', 'Hearing'),
        ('judgement', 'Judgement'),
        ('appeal', 'Appeal'),
        ('closed', 'Closed'),
    ]

    case_number = models.CharField(max_length=60, unique=True, db_index=True)
    title = models.CharField(max_length=255)
    court = models.CharField(max_length=255, blank=True, default='')
    claimant = models.CharField(max_length=255, blank=True, default='')
    defendant = models.CharField(max_length=255, blank=True, default='')
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='intake')
    next_hearing_date = models.DateField(null=True, blank=True)
    assigned_counsel = models.CharField(max_length=255, blank=True, default='')
    summary = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-id']


class HearingDiary(AuditBaseModel):
    case = models.ForeignKey(LegalCase, on_delete=models.CASCADE, related_name='hearings')
    hearing_date = models.DateField(default=timezone.now)
    outcome = models.TextField(blank=True, default='')
    next_hearing_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-hearing_date']


class CaseCost(AuditBaseModel):
    case = models.ForeignKey(LegalCase, on_delete=models.CASCADE, related_name='costs')
    cost_date = models.DateField(default=timezone.now)
    description = models.CharField(max_length=255, blank=True, default='')
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    cost_type = models.CharField(max_length=50, blank=True, default='fee')
    is_award = models.BooleanField(
        default=False,
        help_text='True for a judgement award that should raise the IPSAS 19 provision.',
    )

    class Meta:
        ordering = ['-cost_date']


class RiskRegister(AuditBaseModel):
    LIKELIHOOD_CHOICES = [
        ('rare', 'Rare'), ('unlikely', 'Unlikely'), ('possible', 'Possible'),
        ('likely', 'Likely'), ('almost_certain', 'Almost Certain'),
    ]
    IMPACT_CHOICES = [
        ('negligible', 'Negligible'), ('minor', 'Minor'), ('moderate', 'Moderate'),
        ('major', 'Major'), ('severe', 'Severe'),
    ]

    CATEGORY_CHOICES = [
        ('legal', 'Legal'),
        ('financial', 'Financial'),
        ('operational', 'Operational'),
        ('compliance', 'Compliance'),
        ('reputational', 'Reputational'),
    ]

    title = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='legal')
    likelihood = models.CharField(max_length=20, choices=LIKELIHOOD_CHOICES, default='possible')
    impact = models.CharField(max_length=20, choices=IMPACT_CHOICES, default='moderate')
    mitigation = models.TextField(blank=True, default='')
    mitigation_owner = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    case = models.ForeignKey(
        LegalCase, on_delete=models.SET_NULL, null=True, blank=True, related_name='risks',
    )

    class Meta:
        ordering = ['category', 'title']


class LitigationProvisionLink(AuditBaseModel):
    """Links a legal case cost/award to the IPSAS 19 Provision."""

    case = models.ForeignKey(LegalCase, on_delete=models.CASCADE, related_name='prov_links')
    provision = models.ForeignKey(
        'accounting.Provision', on_delete=models.CASCADE, related_name='+',
    )
    contingent_liability = models.ForeignKey(
        'accounting.ContingentLiability', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-linked_at']
