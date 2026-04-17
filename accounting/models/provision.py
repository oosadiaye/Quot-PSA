"""
IPSAS 19 Provisions + Contingent Liabilities / Contingent Assets.

IPSAS 19 (Provisions, Contingent Liabilities and Contingent Assets)
requires public-sector entities to disclose:

  * **Provisions** — present obligations whose settlement is probable
    and can be reliably measured (pension arrears, litigation damages,
    restructuring costs, onerous contracts, environmental remediation).

  * **Contingent Liabilities** — possible obligations whose realisation
    depends on uncertain future events, OR present obligations that
    cannot be reliably measured. Disclosed in notes, NOT recognised
    on the balance sheet.

  * **Contingent Assets** — possible assets whose inflow is uncertain.
    Disclosed only when realisation is probable; NOT recognised.

This module provides the registry that underpins Note 6 of the IPSAS
Notes to Financial Statements. Users at the AG office enter
provisions manually (or receive them from MDA submissions); the
IPSAS reports service reads the registry when generating notes.

Design choices
--------------
One model class per concept is clearer than a generic "ContingentItem"
with a type discriminator: the three concepts have different
recognition/measurement rules and different disclosure templates. A
small amount of field duplication is worth the clarity.

All three are soft-delete friendly (status='Cancelled') so a provision
that's reassessed as no-longer-probable can be removed from the
balance sheet without losing history.
"""
from __future__ import annotations


from django.conf import settings
from django.db import models
from core.models import AuditBaseModel


PROVISION_CATEGORY_CHOICES = [
    ('LITIGATION',     'Litigation / Legal Damages'),
    ('PENSION',        'Pension Arrears'),
    ('RESTRUCTURING', 'Restructuring / Reorganisation'),
    ('ONEROUS',        'Onerous Contract'),
    ('ENVIRONMENTAL', 'Environmental Remediation'),
    ('WARRANTY',       'Warranty / Guarantee'),
    ('OTHER',          'Other'),
]

PROVISION_STATUS_CHOICES = [
    ('DRAFT',      'Draft'),
    ('RECOGNISED', 'Recognised'),
    ('SETTLED',    'Settled'),
    ('REVERSED',   'Reversed (no longer probable)'),
    ('CANCELLED',  'Cancelled'),
]

LIKELIHOOD_CHOICES = [
    ('REMOTE',   'Remote (< 10%)'),
    ('POSSIBLE', 'Possible (10-50%)'),
    ('PROBABLE', 'Probable (> 50%)'),
    ('CERTAIN',  'Virtually certain'),
]


class Provision(AuditBaseModel):
    """IPSAS 19 provision — probable outflow, reliable measurement.

    A provision is RECOGNISED on the Statement of Financial Position as
    a liability. Changes in the estimate (up or down) flow through
    the Statement of Financial Performance as gain/loss on the
    relevant line.
    """

    reference       = models.CharField(
        max_length=32, unique=True, db_index=True,
        help_text='Unique reference for the provision, e.g. PROV-2026-001.',
    )
    category        = models.CharField(
        max_length=20, choices=PROVISION_CATEGORY_CHOICES, db_index=True,
    )
    title           = models.CharField(max_length=200)
    description     = models.TextField(
        help_text='Nature of the obligation and its basis. Appears in '
                  'Note 6 of the IPSAS Notes.',
    )

    # Present value of the obligation. IPSAS 19 ¶53: discount when the
    # effect of time value of money is material. The discounted amount
    # goes here; the undiscounted amount is informational.
    amount          = models.DecimalField(max_digits=20, decimal_places=2)
    undiscounted_amount = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True,
        help_text='Undiscounted expected outflow, if different from amount.',
    )
    discount_rate   = models.DecimalField(
        max_digits=6, decimal_places=4, null=True, blank=True,
        help_text='Discount rate applied, e.g. 0.1250 for 12.5%.',
    )

    recognition_date = models.DateField(
        help_text='Date the provision was first recognised.',
    )
    expected_settlement_date = models.DateField(
        null=True, blank=True,
        help_text='Best estimate of when settlement will occur.',
    )
    likelihood = models.CharField(
        max_length=10, choices=LIKELIHOOD_CHOICES, default='PROBABLE',
        help_text='IPSAS 19 recognition requires "Probable" or above.',
    )

    # GL link so the posting that recognised the provision can be
    # traced from the register.
    journal_entry = models.ForeignKey(
        'accounting.JournalHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='provisions',
        help_text='Journal that posted the provision to the GL.',
    )
    # The MDA / administrative unit this provision belongs to.
    mda = models.ForeignKey(
        'accounting.MDA', on_delete=models.PROTECT,
        null=True, blank=True, related_name='provisions',
    )

    status = models.CharField(
        max_length=12, choices=PROVISION_STATUS_CHOICES,
        default='DRAFT', db_index=True,
    )
    settled_at     = models.DateTimeField(null=True, blank=True)
    settled_by     = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='provisions_settled',
    )
    notes          = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-recognition_date', 'reference']
        indexes = [
            models.Index(fields=['status', '-recognition_date']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['mda', 'status']),
        ]
        permissions = [
            ('recognise_provision', 'Can recognise (post) a provision'),
            ('reverse_provision',   'Can reverse a provision when no longer probable'),
        ]

    def __str__(self):
        return f'{self.reference} — {self.title} (NGN {self.amount:,.2f})'

    @property
    def is_recognisable(self) -> bool:
        """IPSAS 19 ¶22: recognition requires all three of:
          (a) present obligation (legal or constructive),
          (b) probable outflow,
          (c) reliable measurement.
        We check (b) and (c) here; (a) is a human judgment captured
        in the ``description`` field.
        """
        if self.likelihood not in ('PROBABLE', 'CERTAIN'):
            return False
        if self.amount is None or self.amount <= 0:
            return False
        return True


class ContingentLiability(AuditBaseModel):
    """IPSAS 19 contingent liability — disclosed, NOT recognised."""

    reference    = models.CharField(max_length=32, unique=True, db_index=True)
    title        = models.CharField(max_length=200)
    description  = models.TextField()

    estimated_amount = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True,
        help_text='Best estimate of the possible obligation; may be None '
                  'when no reliable estimate is possible.',
    )
    likelihood = models.CharField(
        max_length=10, choices=LIKELIHOOD_CHOICES, default='POSSIBLE',
    )
    arising_date = models.DateField()
    expected_resolution_date = models.DateField(null=True, blank=True)

    mda = models.ForeignKey(
        'accounting.MDA', on_delete=models.PROTECT,
        null=True, blank=True, related_name='contingent_liabilities',
    )
    is_disclosed = models.BooleanField(
        default=True,
        help_text='Include in Note 6 of the financial statements.',
    )
    notes        = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-arising_date', 'reference']
        verbose_name_plural = 'Contingent liabilities'
        indexes = [
            models.Index(fields=['is_disclosed', '-arising_date']),
            models.Index(fields=['mda', 'likelihood']),
        ]

    def __str__(self):
        amount = (
            f'NGN {self.estimated_amount:,.2f}'
            if self.estimated_amount is not None
            else '(not reliably measurable)'
        )
        return f'{self.reference} — {self.title} — {amount}'


class ContingentAsset(AuditBaseModel):
    """IPSAS 19 contingent asset — disclosed only when probable."""

    reference    = models.CharField(max_length=32, unique=True, db_index=True)
    title        = models.CharField(max_length=200)
    description  = models.TextField()

    estimated_amount = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True,
    )
    likelihood = models.CharField(
        max_length=10, choices=LIKELIHOOD_CHOICES, default='POSSIBLE',
    )
    arising_date = models.DateField()
    expected_realisation_date = models.DateField(null=True, blank=True)

    mda = models.ForeignKey(
        'accounting.MDA', on_delete=models.PROTECT,
        null=True, blank=True, related_name='contingent_assets',
    )
    notes        = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-arising_date', 'reference']
        verbose_name_plural = 'Contingent assets'
        indexes = [
            models.Index(fields=['likelihood', '-arising_date']),
        ]

    def __str__(self):
        amount = (
            f'NGN {self.estimated_amount:,.2f}'
            if self.estimated_amount is not None
            else '(not reliably measurable)'
        )
        return f'{self.reference} — {self.title} — {amount}'

    @property
    def is_disclosable(self) -> bool:
        """IPSAS 19 ¶39: contingent assets disclosed only when probable."""
        return self.likelihood in ('PROBABLE', 'CERTAIN')
