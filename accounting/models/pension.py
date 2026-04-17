"""
IPSAS 39 Employee Benefits (post-employment).

Covers two fundamentally different pension-accounting patterns in
Nigerian public-sector entities:

1. **Defined Contribution (DC)** — post-2004 civil servants under the
   Pension Reform Act 2004/2014 Contributory Pension Scheme (CPS).
   Accounting is simple: recognise expense when the contribution
   falls due; no future obligation beyond the contribution itself.

2. **Defined Benefit (DB)** — legacy pensioners (pre-2004 or special
   schemes). An annual actuarial valuation establishes the Defined
   Benefit Obligation (DBO); plan assets are netted against it to
   give the net liability on the Statement of Financial Position.
   Service cost + interest cost flow through the Statement of
   Financial Performance. Actuarial gains/losses go through the
   Statement of Changes in Net Assets (per IPSAS 39).

Models
------

* ``PensionScheme``       — header entity (one per scheme, DC or DB).
* ``ActuarialValuation``  — annual valuation record for a DB scheme.
* ``PensionContribution`` — monthly contribution record (either scheme
  type). Links to a ``PayrollRun`` or a manual/imported batch.

We model the **result** of an actuarial valuation (numbers the actuary
delivers), not the actuarial mathematics itself. The valuation's
methodology + assumptions are attached as narrative + report reference
so auditors can trace back to the actuary's report.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import models
from core.models import AuditBaseModel


SCHEME_TYPE_CHOICES = [
    ('DEFINED_CONTRIBUTION', 'Defined Contribution (DC)'),
    ('DEFINED_BENEFIT',      'Defined Benefit (DB)'),
]

SCHEME_STATUS_CHOICES = [
    ('ACTIVE',    'Active'),
    ('CLOSED',    'Closed to new members'),
    ('TERMINATED','Terminated'),
]

VALUATION_METHOD_CHOICES = [
    ('PROJECTED_UNIT_CREDIT', 'Projected Unit Credit (PUC) — IPSAS 39 ¶69'),
    ('ATTAINED_AGE',          'Attained Age method'),
    ('ENTRY_AGE_NORMAL',      'Entry Age Normal'),
    ('OTHER',                 'Other (document in methodology)'),
]


class PensionScheme(AuditBaseModel):
    """One row per pension scheme operated by or for the entity.

    A state government might operate two schemes simultaneously: legacy
    DB for pre-2004 civil servants, and participate in the federal CPS
    (DC) for post-2004 hires. Both get a row here.
    """

    code          = models.CharField(
        max_length=20, unique=True, db_index=True,
        help_text='e.g. DELTA-CPS, DELTA-LEGACY-DB.',
    )
    name          = models.CharField(max_length=200)
    description   = models.TextField(blank=True, default='')
    scheme_type   = models.CharField(
        max_length=22, choices=SCHEME_TYPE_CHOICES, db_index=True,
    )
    coverage_note = models.TextField(
        blank=True, default='',
        help_text='Which employee groups this scheme covers '
                  '(e.g. "All civil servants hired after 1 July 2004").',
    )

    # DC-only: statutory contribution rates. Redundant for DB (valuer
    # supplies actual figures) but populated for disclosure purposes.
    employee_contribution_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Employee contribution as % of pensionable pay. '
                  'DC only (typically 8%).',
    )
    employer_contribution_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Employer contribution as % of pensionable pay. '
                  'DC only (typically 10%).',
    )

    established_date = models.DateField(
        null=True, blank=True,
        help_text='When the scheme was established.',
    )
    status = models.CharField(
        max_length=12, choices=SCHEME_STATUS_CHOICES,
        default='ACTIVE', db_index=True,
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['code']
        indexes = [
            models.Index(fields=['scheme_type', 'status']),
        ]

    def __str__(self):
        return f'{self.code} — {self.name} ({self.get_scheme_type_display()})'

    @property
    def is_defined_benefit(self) -> bool:
        return self.scheme_type == 'DEFINED_BENEFIT'


class ActuarialValuation(AuditBaseModel):
    """Annual actuarial valuation snapshot for a DB scheme.

    IPSAS 39 ¶69 requires the projected-unit-credit method to determine
    the present value of the defined benefit obligation. The numbers
    this model stores are the actuary's outputs; we don't recompute
    them — we capture, disclose, and reconcile.
    """

    scheme         = models.ForeignKey(
        PensionScheme, on_delete=models.PROTECT,
        related_name='actuarial_valuations',
    )
    valuation_date = models.DateField(db_index=True)

    # ── Balance-sheet components (IPSAS 39 ¶63) ──────────────────────
    # Present value of defined benefit obligation (DBO) — what the
    # actuary says we owe future pensioners in today's money terms.
    dbo                    = models.DecimalField(
        max_digits=22, decimal_places=2,
        help_text='Present value of the defined benefit obligation. '
                  'IPSAS 39 ¶63(a).',
    )
    # Fair value of plan assets (if the scheme is funded). For unfunded
    # DB schemes — common in older Nigerian state schemes — this is 0.
    plan_assets            = models.DecimalField(
        max_digits=22, decimal_places=2, default=0,
        help_text='Fair value of plan assets. IPSAS 39 ¶63(b).',
    )

    # ── P&L components (IPSAS 39 ¶64) ─────────────────────────────────
    service_cost           = models.DecimalField(
        max_digits=20, decimal_places=2, default=0,
        help_text='Current service cost for the period. Goes to the '
                  'Statement of Financial Performance.',
    )
    interest_cost          = models.DecimalField(
        max_digits=20, decimal_places=2, default=0,
        help_text='Net interest on net defined benefit liability.',
    )
    past_service_cost      = models.DecimalField(
        max_digits=20, decimal_places=2, default=0,
        help_text='Past service cost from plan amendments.',
    )
    gain_on_settlement     = models.DecimalField(
        max_digits=20, decimal_places=2, default=0,
    )

    # ── Changes in Net Assets / Equity components (IPSAS 39 ¶68) ─────
    # Actuarial remeasurements — changes in assumptions or experience
    # adjustments. Under the current IPSAS standard these go through
    # net assets/equity, NOT through surplus/deficit.
    actuarial_gains_losses = models.DecimalField(
        max_digits=20, decimal_places=2, default=0,
        help_text='Remeasurements of the net defined benefit liability. '
                  'Positive = gain reducing the liability. Negative = '
                  'loss increasing it. Posted to net assets (IPSAS 39 ¶68).',
    )
    return_on_plan_assets  = models.DecimalField(
        max_digits=20, decimal_places=2, default=0,
        help_text='Actual return on plan assets (if funded). '
                  'Excluded interest component covered separately.',
    )

    # ── Assumptions for disclosure (IPSAS 39 ¶140) ────────────────────
    valuation_method = models.CharField(
        max_length=24, choices=VALUATION_METHOD_CHOICES,
        default='PROJECTED_UNIT_CREDIT',
    )
    discount_rate      = models.DecimalField(
        max_digits=6, decimal_places=4, null=True, blank=True,
        help_text='e.g. 0.1500 for 15%. Used for present-value '
                  'calculations of future benefit payments.',
    )
    salary_growth_rate = models.DecimalField(
        max_digits=6, decimal_places=4, null=True, blank=True,
    )
    pension_growth_rate = models.DecimalField(
        max_digits=6, decimal_places=4, null=True, blank=True,
    )
    mortality_table     = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Mortality table used, e.g. "A49/52 Ultimate".',
    )
    assumptions_narrative = models.TextField(
        blank=True, default='',
        help_text='Free-text summary of assumptions for Note 8 disclosure.',
    )

    # Provenance.
    valuer_firm        = models.CharField(max_length=200, blank=True, default='')
    valuer_fellow      = models.CharField(
        max_length=200, blank=True, default='',
        help_text='Name of the qualified actuary signing the report.',
    )
    report_reference   = models.CharField(
        max_length=200, blank=True, default='',
        help_text='Reference to the valuation report PDF / document.',
    )

    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-valuation_date']
        indexes = [
            models.Index(fields=['scheme', '-valuation_date']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['scheme', 'valuation_date'],
                name='uniq_actuarial_valuation_scheme_date',
            ),
        ]

    def __str__(self):
        return f'{self.scheme.code} valuation @ {self.valuation_date} DBO NGN {self.dbo:,.2f}'

    @property
    def net_defined_benefit_liability(self) -> Decimal:
        """IPSAS 39 ¶63: DBO − plan_assets.

        Positive = net liability on the balance sheet. Negative (rare:
        overfunded scheme) = asset subject to the asset ceiling (¶64).
        """
        return (self.dbo or Decimal('0')) - (self.plan_assets or Decimal('0'))

    @property
    def total_period_expense(self) -> Decimal:
        """Amount to post to the Statement of Financial Performance
        for this valuation period: service + interest + past-service
        − settlement gain (¶64)."""
        return (
            (self.service_cost or Decimal('0'))
            + (self.interest_cost or Decimal('0'))
            + (self.past_service_cost or Decimal('0'))
            - (self.gain_on_settlement or Decimal('0'))
        )


class PensionContribution(AuditBaseModel):
    """Monthly contribution record for either scheme type.

    For DC schemes this is an expense + payable posting. For DB schemes
    it reduces the net liability (credits plan assets when funded).
    """

    scheme          = models.ForeignKey(
        PensionScheme, on_delete=models.PROTECT,
        related_name='contributions',
    )
    period_year     = models.IntegerField(db_index=True)
    period_month    = models.IntegerField()

    # Aggregate headcount and amounts for the period. Individual-
    # employee rows already live in HRM payroll lines; this table
    # stores the summarised contribution-level view IPSAS Note 8
    # consumes.
    headcount           = models.IntegerField(default=0)
    employee_amount     = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    employer_amount     = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    journal_entry = models.ForeignKey(
        'accounting.JournalHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pension_contributions',
    )

    class Meta:
        ordering = ['-period_year', '-period_month']
        indexes = [
            models.Index(fields=['scheme', '-period_year', '-period_month']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['scheme', 'period_year', 'period_month'],
                name='uniq_pension_contribution_scheme_period',
            ),
        ]

    def __str__(self):
        return (
            f'{self.scheme.code} '
            f'{self.period_year:04d}-{self.period_month:02d} '
            f'EE NGN {self.employee_amount:,.2f} / ER NGN {self.employer_amount:,.2f}'
        )

    @property
    def total_amount(self) -> Decimal:
        return (self.employee_amount or Decimal('0')) + (self.employer_amount or Decimal('0'))
