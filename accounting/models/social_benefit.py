"""
IPSAS 42 Social Benefits.

IPSAS 42 governs transfers from the public sector to individuals or
households where the entity does not receive anything of approximately
equal value directly in return. The standard narrows the scope: it
covers cash transfers, goods, and services provided to individuals to
**mitigate the effect of social risks** — unemployment, old age,
sickness, disability, etc. Welfare programmes, conditional cash
transfers (e.g. CCT under Nigeria's National Social Safety Net), and
food-security initiatives are all in scope.

Out of scope (handled elsewhere):
  * Employee benefits → IPSAS 39 (see ``pension.py``)
  * Fixed transfers under Memorandum of Understanding with NGOs →
    General IPSAS 23 non-exchange revenue recognition

Recognition
-----------
IPSAS 42 ¶31 requires a liability to be recognised when an individual
first becomes eligible per scheme rules. The amount recognised equals
the **next single payment** due under the scheme — NOT the present
value of all future payments, which was the previous treatment.

Models
------

* ``SocialBenefitScheme`` — name / description / eligibility rules /
  funding source / start + end dates.
* ``SocialBenefitClaim``  — per-beneficiary claim record with status
  lifecycle: PENDING → ELIGIBLE → APPROVED → PAID / REJECTED.
"""
from __future__ import annotations


from django.conf import settings
from django.db import models
from core.models import AuditBaseModel


SCHEME_CATEGORY_CHOICES = [
    ('CCT',              'Conditional Cash Transfer'),
    ('UNEMPLOYMENT',     'Unemployment Benefit'),
    ('DISABILITY',       'Disability Support'),
    ('OLD_AGE',          'Old-Age Grant (non-contributory)'),
    ('HEALTH_SUBSIDY',   'Healthcare Subsidy'),
    ('FOOD_SECURITY',    'Food / Nutrition Support'),
    ('EDUCATION',        'Education Grant / Bursary'),
    ('HOUSING',          'Housing Support'),
    ('OTHER',            'Other Social Benefit'),
]

SCHEME_STATUS_CHOICES = [
    ('ACTIVE',    'Active'),
    ('SUSPENDED', 'Suspended'),
    ('CLOSED',    'Closed'),
]

CLAIM_STATUS_CHOICES = [
    ('PENDING',  'Pending eligibility check'),
    ('ELIGIBLE', 'Eligible — awaiting approval'),
    ('APPROVED', 'Approved — awaiting payment'),
    ('PAID',     'Paid'),
    ('REJECTED', 'Rejected'),
    ('CANCELLED', 'Cancelled'),
]


class SocialBenefitScheme(AuditBaseModel):
    """A state-level (or federal) social-benefit scheme run by the entity."""

    code        = models.CharField(
        max_length=30, unique=True, db_index=True,
        help_text='e.g. DELTA-CCT-2026, LAGOS-CARE-ELDERLY.',
    )
    name        = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    category    = models.CharField(
        max_length=20, choices=SCHEME_CATEGORY_CHOICES, db_index=True,
    )

    # Eligibility captured as free-text; structured eligibility rules
    # would be a per-scheme implementation detail (income thresholds,
    # age ranges, etc.) and belong in the rules engine when one exists.
    eligibility_criteria = models.TextField(
        help_text='Plain-English description of who qualifies '
                  '(age, income, geography, etc.).',
    )

    # Benefit amount per eligible period. Per IPSAS 42 ¶31 the amount
    # recognised on a claim is the NEXT SINGLE PAYMENT — this field
    # is that value. Variable-amount schemes (means-tested) override
    # at the claim level.
    standard_benefit_amount = models.DecimalField(
        max_digits=20, decimal_places=2, default=0,
        help_text='Default amount per payment period. Per-claim '
                  'overrides allowed at SocialBenefitClaim.amount.',
    )
    payment_frequency = models.CharField(
        max_length=20, blank=True, default='MONTHLY',
        help_text='MONTHLY / QUARTERLY / ANNUAL / ONE_OFF.',
    )

    start_date          = models.DateField()
    end_date            = models.DateField(null=True, blank=True)
    total_budget        = models.DecimalField(
        max_digits=22, decimal_places=2, default=0,
        help_text='Annual or programme-total budget allocation.',
    )
    funding_source      = models.CharField(
        max_length=200, blank=True, default='',
        help_text='e.g. "State Consolidated Revenue Fund", '
                  '"Federal World-Bank CCT grant".',
    )

    status = models.CharField(
        max_length=10, choices=SCHEME_STATUS_CHOICES,
        default='ACTIVE', db_index=True,
    )
    notes  = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['code']
        indexes = [
            models.Index(fields=['category', 'status']),
        ]

    def __str__(self):
        return f'{self.code} — {self.name} ({self.get_category_display()})'


class SocialBenefitClaim(AuditBaseModel):
    """One per beneficiary per period per scheme.

    ``SocialBenefitScheme.code + beneficiary_identifier + period`` is
    the natural key. Beneficiary data is stored as denormalised fields
    because the system doesn't (and shouldn't) maintain a master list
    of citizens — each scheme is responsible for its own beneficiary
    registry elsewhere. This model captures what's needed for the
    financial posting + IPSAS 42 disclosure.
    """

    scheme = models.ForeignKey(
        SocialBenefitScheme, on_delete=models.PROTECT,
        related_name='claims',
    )
    claim_reference = models.CharField(
        max_length=40, unique=True, db_index=True,
        help_text='Unique claim reference, e.g. DELTA-CCT-2026-000123.',
    )

    beneficiary_name        = models.CharField(max_length=200)
    beneficiary_identifier  = models.CharField(
        max_length=64, blank=True, default='',
        help_text='NIN / BVN / scheme-specific ID. Denormalised — '
                  'no FK to a citizen master.',
    )
    beneficiary_phone       = models.CharField(max_length=30, blank=True, default='')
    beneficiary_address     = models.TextField(blank=True, default='')

    # Period this claim covers. Most schemes pay monthly; one-off
    # grants use the same year+month as their disbursement date.
    period_year  = models.IntegerField(db_index=True)
    period_month = models.IntegerField()

    amount = models.DecimalField(
        max_digits=20, decimal_places=2,
        help_text='Payment amount for this period. Overrides the '
                  'scheme default when present.',
    )

    # Lifecycle.
    status = models.CharField(
        max_length=10, choices=CLAIM_STATUS_CHOICES,
        default='PENDING', db_index=True,
    )
    eligible_date = models.DateField(
        null=True, blank=True,
        help_text='Date the beneficiary first met eligibility per '
                  'scheme rules. IPSAS 42 ¶31: liability recognised at '
                  'this date for the next single payment.',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='social_benefit_claims_approved',
    )
    paid_at    = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Bank / mobile-money / voucher reference.',
    )

    journal_entry = models.ForeignKey(
        'accounting.JournalHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='social_benefit_claims',
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-period_year', '-period_month', 'claim_reference']
        indexes = [
            models.Index(fields=['scheme', 'status']),
            models.Index(fields=['scheme', '-period_year', '-period_month']),
            models.Index(fields=['beneficiary_identifier']),
        ]
        constraints = [
            # One claim per beneficiary per period per scheme.
            models.UniqueConstraint(
                fields=['scheme', 'beneficiary_identifier', 'period_year', 'period_month'],
                condition=models.Q(beneficiary_identifier__gt=''),
                name='uniq_social_claim_benef_period',
            ),
        ]

    def __str__(self):
        return (
            f'{self.claim_reference} — {self.beneficiary_name} '
            f'({self.scheme.code} {self.period_year:04d}-{self.period_month:02d}, '
            f'NGN {self.amount:,.2f})'
        )

    @property
    def is_recognisable(self) -> bool:
        """IPSAS 42 ¶31 recognition gate: the beneficiary must have
        reached the eligibility date, and the amount must be positive
        and reliably measurable (we treat "set" as measurable)."""
        return (
            self.eligible_date is not None
            and self.amount is not None
            and self.amount > 0
        )
