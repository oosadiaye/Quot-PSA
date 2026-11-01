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
    issue_date = models.DateField(default=timezone.localdate)
    submission_deadline = models.DateField(null=True, blank=True)
    guidelines = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=False)
    document = models.FileField(
        upload_to='budget_prep/circular/%Y/', null=True, blank=True,
    )

    class Meta:
        ordering = ['-fiscal_year']


def _money(**kw):
    return models.DecimalField(max_digits=20, decimal_places=2, default=0, **kw)


class MTEFProjection(AuditBaseModel):
    """One year of the Medium Term Expenditure Framework: the resource envelope and how it is spent and financed.

    A framework is three consecutive years (the budget year and two outer years), each its own row. Revenue, expenditure
    and financing are entered by source or category; the totals and the fiscal balance are always worked out from them,
    never typed, so the three can never disagree. ``budget_prep.services.mtef`` assesses a year against the fiscal rules.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('reviewed', 'Reviewed'),
        ('approved', 'Approved'),
    ]
    #: Revenue that recurs every year; grants and capital receipts are one-off or capital in nature.
    RECURRENT_REVENUE = ('rev_statutory', 'rev_vat', 'rev_igr', 'rev_other')
    CAPITAL_REVENUE = ('rev_grants', 'rev_capital_receipts')
    REVENUE_FIELDS = RECURRENT_REVENUE + CAPITAL_REVENUE
    RECURRENT_EXPENDITURE = ('exp_debt_service', 'exp_personnel', 'exp_overhead', 'exp_other_recurrent')
    EXPENDITURE_FIELDS = RECURRENT_EXPENDITURE + ('exp_capital',)
    FINANCING_FIELDS = ('fin_domestic', 'fin_external', 'fin_other')

    fiscal_year = models.IntegerField(db_index=True)

    # Assumptions behind the numbers
    inflation_assumption = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    exchange_rate_assumption = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    oil_price_assumption = models.DecimalField(max_digits=12, decimal_places=2, default=0, null=True, blank=True)
    # How strongly the statutory allocation and VAT follow the oil price: 1 = one for one, 0 = not at all.
    oil_sensitivity = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    # The size of the economy (nominal GDP, or GSDP for a state) and the public debt owed at the start of the year: the base
    # against which the deficit and the debt stock are held. Left at 0 they are simply not judged.
    gdp_assumption = models.DecimalField(max_digits=22, decimal_places=2, default=0)
    opening_debt_stock = models.DecimalField(max_digits=22, decimal_places=2, default=0)

    # Resource envelope, by source
    rev_statutory = _money()            # statutory (FAAC) allocation
    rev_vat = _money()                  # VAT allocation
    rev_igr = _money()                  # internally generated revenue
    rev_other = _money()                # other recurrent revenue
    rev_grants = _money()               # grants and aid
    rev_capital_receipts = _money()     # asset sales and other capital receipts

    # Expenditure, by economic category (debt service is the first charge on revenue)
    exp_debt_service = _money()
    exp_personnel = _money()
    exp_overhead = _money()
    exp_other_recurrent = _money()      # statutory transfers, pensions and other recurrent items
    exp_capital = _money()

    # How a deficit is financed
    fin_domestic = _money()
    fin_external = _money()
    fin_other = _money()                # balances brought forward and other financing

    # Worked out on save from the parts above (a row holding only these legacy totals keeps them until parts are entered)
    aggregate_revenue = models.DecimalField(max_digits=20, decimal_places=2, default=0, editable=False)
    aggregate_expenditure = models.DecimalField(max_digits=20, decimal_places=2, default=0, editable=False)
    fiscal_balance = models.DecimalField(max_digits=20, decimal_places=2, default=0, editable=False)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft', db_index=True)
    approved_by = models.CharField(max_length=200, blank=True, default='')
    approved_at = models.DateTimeField(null=True, blank=True)
    override_reason = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-fiscal_year']
        constraints = [models.UniqueConstraint(fields=['fiscal_year'], name='uniq_mtef_projection_per_year')]

    def __str__(self):
        return f'MTEF {self.fiscal_year}'

    def _sum(self, names):
        return sum((getattr(self, n) or 0 for n in names), 0)

    @property
    def total_revenue(self):
        return self._sum(self.REVENUE_FIELDS)

    @property
    def recurrent_revenue(self):
        return self._sum(self.RECURRENT_REVENUE)

    @property
    def total_expenditure(self):
        return self._sum(self.EXPENDITURE_FIELDS)

    @property
    def recurrent_expenditure(self):
        return self._sum(self.RECURRENT_EXPENDITURE)

    @property
    def total_financing(self):
        return self._sum(self.FINANCING_FIELDS)

    @property
    def unfinanced_gap(self):
        """The part of a deficit that nothing finances (zero when the budget is in surplus or fully financed)."""
        return max(0, -self.fiscal_balance - self.total_financing)

    def save(self, *args, **kwargs):
        if self.total_revenue or self.total_expenditure:      # parts entered: they are the truth
            self.aggregate_revenue = self.total_revenue
            self.aggregate_expenditure = self.total_expenditure
        self.fiscal_balance = self.aggregate_revenue - self.aggregate_expenditure
        super().save(*args, **kwargs)


class MTEFPolicy(AuditBaseModel):
    """The fiscal rules a framework is held to. One row per tenant; the defaults are a starting point for the
    government's own fiscal policy, not a statutory text, so each limit is meant to be set by the Budget Office."""

    max_debt_service_pct = models.DecimalField(max_digits=5, decimal_places=2, default=30,
                                               help_text='Debt service as a % of total revenue.')
    max_personnel_pct = models.DecimalField(max_digits=5, decimal_places=2, default=50,
                                            help_text='Personnel cost as a % of recurrent revenue.')
    min_capital_pct = models.DecimalField(max_digits=5, decimal_places=2, default=30,
                                          help_text='Capital expenditure as a % of total expenditure (a floor).')
    max_borrowing_pct = models.DecimalField(max_digits=5, decimal_places=2, default=15,
                                            help_text='New borrowing as a % of total revenue.')
    max_revenue_growth_pct = models.DecimalField(max_digits=5, decimal_places=2, default=10,
                                                 help_text='How far a year-on-year revenue growth may exceed inflation.')
    max_outturn_jump_pct = models.DecimalField(max_digits=5, decimal_places=2, default=25,
                                               help_text='How far the budget year may exceed last year\'s actual spending, '
                                                         'above inflation.')
    max_deficit_pct_gdp = models.DecimalField(max_digits=5, decimal_places=2, default=3,
                                              help_text='The fiscal deficit as a % of GDP (the Fiscal Responsibility Act sets 3).')
    max_debt_stock_pct_gdp = models.DecimalField(max_digits=5, decimal_places=2, default=25,
                                                 help_text='Closing public debt as a % of GDP.')
    enforce_golden_rule = models.BooleanField(default=True, help_text='Recurrent spending must fit within recurrent revenue.')

    def __str__(self):
        return 'MTEF fiscal rules'


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
    KIND_CHOICES = [
        ('original', 'Original budget'),
        ('supplementary', 'Supplementary budget'),
    ]
    # A supplementary is its own set of lines (the user picks the economic code) and becomes SUPPLEMENTARY
    # appropriations on hand-over; it is not measured against the original ceilings.
    kind = models.CharField(max_length=15, choices=KIND_CHOICES, default='original', db_index=True)
    justification = models.TextField(blank=True, default='')
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
        'accounting.Account', on_delete=models.PROTECT, null=True, blank=True,
        related_name='+',
    )
    functional = models.ForeignKey(
        'accounting.FunctionalSegment', on_delete=models.PROTECT, null=True, blank=True,
        related_name='+',
    )
    # Needed to hand the line over as an appropriation; optional on entry, resolved at hand-off.
    fund = models.ForeignKey(
        'accounting.FundSegment', on_delete=models.PROTECT, null=True, blank=True,
        related_name='+',
    )
    programme = models.ForeignKey(
        'accounting.ProgrammeSegment', on_delete=models.PROTECT, null=True, blank=True,
        related_name='+',
    )
    description = models.CharField(max_length=255, blank=True, default='')
    proposed_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    # Audit trail for a figure seeded from actuals ("adopt actuals to plan"). Blank on hand-entered lines.
    adopted_basis = models.CharField(max_length=20, blank=True, default='')
    baseline_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    adjustment_pct = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
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


class BudgetMilestone(AuditBaseModel):
    """One dated step in a year's budget calendar (call circular, submissions due, defence, enactment ...).

    ``std_key`` marks a step seeded from the standard template, so seeding again never duplicates it and never moves a
    date someone has already changed. Steps added by hand leave it blank.
    """
    fiscal_year = models.IntegerField(db_index=True)
    sequence = models.PositiveSmallIntegerField(default=0)
    name = models.CharField(max_length=200)
    due_date = models.DateField()
    completed_on = models.DateField(null=True, blank=True)
    owner = models.CharField(max_length=200, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    std_key = models.CharField(max_length=40, blank=True, default='')

    class Meta:
        ordering = ['fiscal_year', 'due_date', 'sequence', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['fiscal_year', 'std_key'], condition=~models.Q(std_key=''),
                name='uniq_budget_milestone_std_key_per_year'),
        ]

    def __str__(self):
        return f'{self.fiscal_year} {self.name} ({self.due_date})'
