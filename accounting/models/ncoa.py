"""
Nigeria National Chart of Accounts (NCoA) — 52-digit, 6-segment classification.
All government financial transactions must carry a full NCoA composite code.
Reference: OAGF NCoA Implementation Guide (2014) + NGF GIFMIS Standards.
"""
from django.db import models
from django.core.exceptions import ValidationError
from core.models import AuditBaseModel


# ─── Segment 1: Administrative (12 digits) ──────────────────────────────

class AdministrativeSegment(AuditBaseModel):
    """
    NCoA Segment 1 — Administrative (12 digits)
    Format: XX-XX-XXX-XXX-XX
    Represents the MDA (Ministry, Department, Agency) hierarchy.
    Hierarchy: Sector(2) → Organization(2) → Sub-Org(3) → Sub-Sub-Org(3) → Unit(2)
    """
    LEVEL_CHOICES = [
        ('SECTOR',       'Sector'),
        ('ORGANIZATION', 'Organization'),
        ('SUB_ORG',      'Sub-Organization'),
        ('SUB_SUB_ORG',  'Sub-Sub-Organization'),
        ('UNIT',         'Unit'),
    ]
    SECTOR_CHOICES = [
        ('01', 'Administrative Sector'),
        ('02', 'Economic Sector'),
        ('03', 'Law and Justice Sector'),
        ('04', 'Regional Sector'),
        ('05', 'Social Sector'),
    ]
    MDA_TYPE_CHOICES = [
        ('MINISTRY',   'Ministry'),
        ('DEPARTMENT', 'Department'),
        ('AGENCY',     'Agency / Parastatal'),
        ('UNIT',       'Unit / Division'),
    ]

    code              = models.CharField(max_length=12, unique=True, db_index=True)
    name              = models.CharField(max_length=200)
    short_name        = models.CharField(max_length=50, blank=True, default='')
    level             = models.CharField(max_length=15, choices=LEVEL_CHOICES)
    sector_code       = models.CharField(max_length=2, choices=SECTOR_CHOICES)
    organization_code = models.CharField(max_length=2, blank=True, default='')
    sub_org_code      = models.CharField(max_length=3, blank=True, default='')
    sub_sub_org_code  = models.CharField(max_length=3, blank=True, default='')
    unit_code         = models.CharField(max_length=2, blank=True, default='')
    parent            = models.ForeignKey(
                            'self', null=True, blank=True,
                            on_delete=models.PROTECT, related_name='children',
                        )
    is_active         = models.BooleanField(default=True, db_index=True)
    is_mda            = models.BooleanField(default=False)
    mda_type          = models.CharField(max_length=15, choices=MDA_TYPE_CHOICES, blank=True, default='')
    description       = models.TextField(blank=True, default='')
    # Bridge to legacy MDA model for backward compatibility
    legacy_mda        = models.OneToOneField(
        'accounting.MDA', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ncoa_segment',
        help_text="Maps this NCoA segment to legacy MDA for GL compatibility",
    )

    class Meta:
        ordering = ['code']
        verbose_name = 'Administrative Segment (MDA)'
        verbose_name_plural = 'Administrative Segments (MDA)'
        indexes = [
            models.Index(fields=['sector_code', 'is_active']),
            models.Index(fields=['level', 'is_active']),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"

    def get_ancestors(self):
        """Return list of ancestor nodes from root to parent."""
        ancestors = []
        node = self.parent
        while node:
            ancestors.insert(0, node)
            node = node.parent
        return ancestors

    def get_full_path(self):
        parts = [a.name for a in self.get_ancestors()]
        parts.append(self.name)
        return ' > '.join(parts)

    def clean(self):
        super().clean()
        if not self.code:
            raise ValidationError("Code is required.")


# ─── Segment 2: Economic — THE HUB SEGMENT — is the Chart of Accounts ──
#
# In public-sector accounting the NCoA economic segment and the general
# ledger's chart of accounts are one classifier: the same 8-digit codes,
# the same names, the same hierarchy, the same posting rules. This file
# used to carry an ``EconomicSegment`` model that mirrored
# ``accounting.Account`` row for row, kept level by a sync service and a
# post_save signal.
#
# It is gone. ``accounting.gl.Account`` is the economic segment, and
# everything that classified economically — ``NCoACode.economic``,
# ``Appropriation.economic``, ``RevenueBudget.economic``,
# ``RevenueHead.economic_segment``, ``TreasuryAccount.ncoa_cash_code`` —
# points at it directly. The NCoA vocabulary maps on as:
#
#     account_type_code   -> code[0]   (1 Revenue, 2 Expenditure,
#                                       3 Assets, 4 Liabilities & Net Assets)
#     is_posting_level    -> Account.is_postable
#     is_control_account  -> Account.is_reconciliation
#     sub/class/line item -> substrings of ``code`` — never independent data
#
# The other five segments keep their own models below, because
# administrative, functional, programme, fund and geographic classify
# things the general ledger does not.


# ─── Segment 3: Functional (5 digits) — COFOG ──────────────────────────

class FunctionalSegment(AuditBaseModel):
    """
    NCoA Segment 3 — Functional (5 digits) — UN COFOG Aligned
    Format: XXX-X-X
    Division(3) → Group(1) → Class(1)
    Used for FAAC reporting and COFOG-aligned expenditure analysis.
    """
    COFOG_DIVISIONS = [
        ('701', 'General Public Services'),
        ('702', 'Defence'),
        ('703', 'Public Order and Safety'),
        ('704', 'Economic Affairs'),
        ('705', 'Environmental Protection'),
        ('706', 'Housing and Community Amenities'),
        ('707', 'Health'),
        ('708', 'Recreation, Culture and Religion'),
        ('709', 'Education'),
        ('710', 'Social Protection'),
    ]

    code          = models.CharField(max_length=5, unique=True, db_index=True)
    name          = models.CharField(max_length=200)
    division_code = models.CharField(max_length=3, choices=COFOG_DIVISIONS, db_index=True)
    group_code    = models.CharField(max_length=1, blank=True, default='0')
    class_code    = models.CharField(max_length=1, blank=True, default='0')
    parent        = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.PROTECT, related_name='children',
    )
    is_active     = models.BooleanField(default=True, db_index=True)
    description   = models.TextField(blank=True, default='')
    legacy_function = models.OneToOneField(
        'accounting.Function', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ncoa_segment',
        help_text="Maps to legacy Function for GL compatibility",
    )

    class Meta:
        ordering = ['code']
        verbose_name = 'Functional Segment (COFOG)'
        verbose_name_plural = 'Functional Segments (COFOG)'

    def __str__(self):
        return f"{self.code} — {self.name}"


# ─── Segment 4: Programme (14 digits) ──────────────────────────────────

class ProgrammeSegment(AuditBaseModel):
    """
    NCoA Segment 4 — Programme (14 digits)
    Format: XX-XX-XXXXXX-XX-XX
    Policy(2) → Programme(2) → Project(6, capital only) → Objective(2) → Activity(2)
    """
    code           = models.CharField(max_length=14, unique=True, db_index=True)
    name           = models.CharField(max_length=200)
    policy_code    = models.CharField(max_length=2)
    programme_code = models.CharField(max_length=2)
    project_code   = models.CharField(max_length=6, blank=True, default='')
    objective_code = models.CharField(max_length=2, blank=True, default='')
    activity_code  = models.CharField(max_length=2, blank=True, default='')
    parent         = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.PROTECT, related_name='children',
    )
    is_active      = models.BooleanField(default=True, db_index=True)
    is_capital     = models.BooleanField(default=False, db_index=True)
    project_start  = models.DateField(null=True, blank=True)
    project_end    = models.DateField(null=True, blank=True)
    total_project_cost = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True,
    )
    description    = models.TextField(blank=True, default='')
    legacy_program = models.OneToOneField(
        'accounting.Program', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ncoa_segment',
        help_text="Maps to legacy Program for GL compatibility",
    )

    class Meta:
        ordering = ['code']
        verbose_name = 'Programme Segment'
        verbose_name_plural = 'Programme Segments'

    def __str__(self):
        return f"{self.code} — {self.name}"


# ─── Segment 5: Fund (5 digits) ────────────────────────────────────────

class FundSegment(AuditBaseModel):
    """
    NCoA Segment 5 — Fund (5 digits)
    Format: XX-X-XX
    Main Fund(2) → Sub-Fund(1) → Fund Source(2)
    Tracks the source of government funding for every transaction.
    """
    MAIN_FUND_CHOICES = [
        ('01', 'Federation Account (FAAC — Statutory)'),
        ('02', 'Capital Development Fund'),
        ('03', 'Contingency Fund'),
        ('04', 'Education Tax / UBEC Fund'),
        ('05', 'Donor / Grant Funds'),
        ('06', 'Domestic Loans'),
        ('07', 'Foreign Loans'),
        ('08', 'Internally Generated Revenue (IGR)'),
        ('09', 'Other Government Receipts'),
    ]

    code             = models.CharField(max_length=5, unique=True, db_index=True)
    name             = models.CharField(max_length=200)
    main_fund_code   = models.CharField(max_length=2, choices=MAIN_FUND_CHOICES, db_index=True)
    sub_fund_code    = models.CharField(max_length=1, blank=True, default='0')
    fund_source_code = models.CharField(max_length=2, blank=True, default='00')
    donor_name       = models.CharField(max_length=200, blank=True, default='')
    parent           = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.PROTECT, related_name='children',
    )
    is_active        = models.BooleanField(default=True, db_index=True)
    is_restricted    = models.BooleanField(default=False)
    description      = models.TextField(blank=True, default='')
    legacy_fund      = models.OneToOneField(
        'accounting.Fund', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ncoa_segment',
        help_text="Maps to legacy Fund for GL compatibility",
    )

    class Meta:
        ordering = ['code']
        verbose_name = 'Fund Segment'
        verbose_name_plural = 'Fund Segments'

    def __str__(self):
        return f"{self.code} — {self.name}"


# ─── Segment 6: Geographic (8 digits) ──────────────────────────────────

class GeographicSegment(AuditBaseModel):
    """
    NCoA Segment 6 — Geographic (8 digits)
    Format: X-XX-X-XX-XX
    Zone(1) → State(2) → Senatorial District(1) → LGA(2) → Ward(2)
    36 States + FCT, 774 LGAs per INEC/NBS codes.
    """
    GEO_ZONE_CHOICES = [
        ('1', 'North-Central'),
        ('2', 'North-East'),
        ('3', 'North-West'),
        ('4', 'South-East'),
        ('5', 'South-South'),
        ('6', 'South-West'),
    ]

    code            = models.CharField(max_length=8, unique=True, db_index=True)
    name            = models.CharField(max_length=200)
    zone_code       = models.CharField(max_length=1, choices=GEO_ZONE_CHOICES, db_index=True)
    state_code      = models.CharField(max_length=2, db_index=True, default='00')
    senatorial_code = models.CharField(max_length=1, blank=True, default='0')
    lga_code        = models.CharField(max_length=2, blank=True, default='00')
    ward_code       = models.CharField(max_length=2, blank=True, default='00')
    parent          = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.PROTECT, related_name='children',
    )
    is_active       = models.BooleanField(default=True, db_index=True)
    description     = models.TextField(blank=True, default='')
    legacy_geo      = models.OneToOneField(
        'accounting.Geo', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ncoa_segment',
        help_text="Maps to legacy Geo for GL compatibility",
    )

    class Meta:
        ordering = ['zone_code', 'state_code', 'code']
        verbose_name = 'Geographic Segment'
        verbose_name_plural = 'Geographic Segments'
        indexes = [
            models.Index(fields=['zone_code', 'state_code', 'is_active']),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"


# ─── Composite NCoA Code ───────────────────────────────────────────────

class NCoACode(AuditBaseModel):
    """
    Full 52-digit NCoA Composite Code.
    Every JournalLine MUST reference one of these.
    This is the financial DNA of every government transaction.
    Created on-demand when a unique combination is first used.
    """
    administrative = models.ForeignKey(AdministrativeSegment, on_delete=models.PROTECT)
    # The economic dimension is the chart of accounts itself.
    #
    # In public-sector accounting the NCoA economic segment and the GL
    # account are the same classifier — same codes, same names, same
    # hierarchy. They were kept in two tables with a sync service and a
    # signal to hold them level, which is a lot of machinery to maintain a
    # copy. ``Account`` is the survivor; the other five segments keep
    # their own models because they classify things the GL does not.
    economic       = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT,
        related_name='ncoa_codes',
    )
    functional     = models.ForeignKey(FunctionalSegment, on_delete=models.PROTECT)
    programme      = models.ForeignKey(ProgrammeSegment, on_delete=models.PROTECT)
    fund           = models.ForeignKey(FundSegment, on_delete=models.PROTECT)
    geographic     = models.ForeignKey(GeographicSegment, on_delete=models.PROTECT)
    is_active      = models.BooleanField(default=True)
    description    = models.CharField(max_length=500, blank=True, default='')

    class Meta:
        unique_together = [
            ['administrative', 'economic', 'functional',
             'programme', 'fund', 'geographic']
        ]
        indexes = [
            models.Index(fields=['economic', 'administrative']),
            models.Index(fields=['fund', 'programme']),
            models.Index(fields=['economic', 'functional']),
        ]
        verbose_name = 'NCoA Code'
        verbose_name_plural = 'NCoA Codes'

    @property
    def full_code(self):
        """Full 52-digit NCoA string with segment separators."""
        return (
            f"{self.administrative.code}-"
            f"{self.economic.code}-"
            f"{self.functional.code}-"
            f"{self.programme.code}-"
            f"{self.fund.code}-"
            f"{self.geographic.code}"
        )

    @property
    def account_name(self):
        return self.economic.name

    @property
    def mda_name(self):
        return self.administrative.name

    def __str__(self):
        return f"{self.full_code} | {self.economic.name}"

    @classmethod
    def get_or_create_code(cls, admin_id, economic_id, functional_id,
                           programme_id, fund_id, geo_id):
        """
        Thread-safe get-or-create for NCoA combinations.
        Use this in all service layers instead of direct .create().
        """
        obj, created = cls.objects.get_or_create(
            administrative_id=admin_id,
            economic_id=economic_id,
            functional_id=functional_id,
            programme_id=programme_id,
            fund_id=fund_id,
            geographic_id=geo_id,
            defaults={'is_active': True},
        )
        return obj
