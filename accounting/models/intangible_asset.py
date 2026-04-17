"""
IPSAS 31 IntangibleAsset.

IPSAS 31 (Intangible Assets) — identifiable non-monetary assets
without physical substance that an entity controls and from which
it expects future economic benefits or service potential. The most
common examples in Nigerian public-sector accounting are:

  * Software licences and purchased applications
  * Internally-developed software (capitalised when IPSAS 31 criteria
    are met: technical feasibility, intent to complete, ability to
    use, expected future benefits, available resources, reliable
    measurement)
  * Copyrights, patents, trademarks
  * Development expenditure in the research-to-development transition

Recognition
-----------
IPSAS 31 ¶28 requires ALL three of:
  (a) probable future economic benefits,
  (b) cost reliably measurable,
  (c) asset identifiable, controlled by the entity, and not an
      internally-generated goodwill (IPSAS 31 ¶52).

Measurement
-----------
  * Initial:      cost (IPSAS 31 ¶31–¶40)
  * Subsequent:   cost model OR revaluation model (¶65). Default here
                  is cost model — revaluation model requires an active
                  market which is rare for public-sector intangibles.

Amortisation
------------
Straight-line over useful life. The service ``monthly_amortisation``
exposes the period charge; an external scheduler posts it monthly.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from core.models import AuditBaseModel


INTANGIBLE_CATEGORY_CHOICES = [
    ('SOFTWARE_LICENCE',   'Software Licence'),
    ('SOFTWARE_DEVELOPED', 'Internally-Developed Software'),
    ('PATENT',             'Patent'),
    ('COPYRIGHT',          'Copyright'),
    ('TRADEMARK',          'Trademark'),
    ('DEVELOPMENT',        'Development Expenditure'),
    ('OTHER',              'Other'),
]

AMORTISATION_METHOD_CHOICES = [
    ('STRAIGHT_LINE',  'Straight-line'),
    ('REDUCING',       'Reducing balance'),
    ('UNITS_OF_USE',   'Units of use'),
    ('NOT_AMORTISED',  'Not amortised (indefinite useful life)'),
]

INTANGIBLE_STATUS_CHOICES = [
    ('ACTIVE',    'Active'),
    ('IMPAIRED',  'Impaired'),
    ('DISPOSED',  'Disposed'),
    ('RETIRED',   'Retired'),
]


class IntangibleAsset(AuditBaseModel):
    """IPSAS 31 intangible asset register entry."""

    # Identification.
    asset_number   = models.CharField(
        max_length=32, unique=True, db_index=True,
        help_text='e.g. INTAN-2026-001',
    )
    name           = models.CharField(max_length=200)
    description    = models.TextField(blank=True, default='')
    category       = models.CharField(
        max_length=20, choices=INTANGIBLE_CATEGORY_CHOICES, db_index=True,
    )

    # Measurement.
    acquisition_cost        = models.DecimalField(max_digits=20, decimal_places=2)
    acquisition_date        = models.DateField()
    useful_life_months      = models.IntegerField(
        null=True, blank=True,
        help_text='None = indefinite useful life (not amortised per ¶88).',
    )
    amortisation_method     = models.CharField(
        max_length=16, choices=AMORTISATION_METHOD_CHOICES,
        default='STRAIGHT_LINE',
    )
    accumulated_amortisation = models.DecimalField(
        max_digits=20, decimal_places=2, default=0,
    )
    residual_value          = models.DecimalField(
        max_digits=20, decimal_places=2, default=0,
        help_text='IPSAS 31 ¶100: usually zero for intangibles unless '
                  'there is an active market or third-party commitment.',
    )

    # Impairment tracking (IPSAS 26).
    impairment_loss          = models.DecimalField(
        max_digits=20, decimal_places=2, default=0,
    )
    last_impairment_review   = models.DateField(null=True, blank=True)

    # Relationships.
    mda = models.ForeignKey(
        'accounting.MDA', on_delete=models.PROTECT,
        null=True, blank=True, related_name='intangible_assets',
    )
    journal_entry = models.ForeignKey(
        'accounting.JournalHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='intangible_assets',
    )

    status       = models.CharField(
        max_length=12, choices=INTANGIBLE_STATUS_CHOICES,
        default='ACTIVE', db_index=True,
    )
    disposed_at  = models.DateTimeField(null=True, blank=True)
    disposed_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='intangible_assets_disposed',
    )
    notes        = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-acquisition_date', 'asset_number']
        indexes = [
            models.Index(fields=['status', '-acquisition_date']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['mda', 'status']),
        ]
        permissions = [
            ('amortise_intangible_asset', 'Can post amortisation for an intangible asset'),
            ('impair_intangible_asset',   'Can record an impairment'),
        ]

    def __str__(self):
        return f'{self.asset_number} — {self.name} (NGN {self.acquisition_cost:,.2f})'

    # ── Derived values ─────────────────────────────────────────────────

    @property
    def carrying_amount(self) -> Decimal:
        """Cost less accumulated amortisation less impairment."""
        cost = self.acquisition_cost or Decimal('0')
        amort = self.accumulated_amortisation or Decimal('0')
        impair = self.impairment_loss or Decimal('0')
        result = cost - amort - impair
        # Never below residual value.
        residual = self.residual_value or Decimal('0')
        return result if result > residual else residual

    @property
    def monthly_amortisation(self) -> Decimal:
        """Straight-line monthly charge.

        Returns ``Decimal('0')`` for indefinite useful life, reducing-
        balance (needs period-by-period computation), or units-of-use
        (caller provides the period units). Those cases are handled by
        dedicated services; this property stays simple for the common
        straight-line case.
        """
        if (
            self.amortisation_method != 'STRAIGHT_LINE'
            or not self.useful_life_months
            or self.useful_life_months <= 0
        ):
            return Decimal('0')
        cost = self.acquisition_cost or Decimal('0')
        residual = self.residual_value or Decimal('0')
        depreciable = cost - residual
        if depreciable <= 0:
            return Decimal('0')
        return (depreciable / Decimal(self.useful_life_months)).quantize(Decimal('0.01'))

    @property
    def is_fully_amortised(self) -> bool:
        """True when carrying amount has reached the residual value."""
        return self.carrying_amount <= (self.residual_value or Decimal('0'))
