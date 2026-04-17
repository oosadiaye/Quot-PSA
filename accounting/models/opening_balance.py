"""
IPSAS 33 First-time Adoption of Accrual Basis IPSAS — Opening
Balance Sheet.

Nigeria is still transitioning many state-level tenants from cash-
basis to accrual-basis IPSAS. IPSAS 33 governs that transition:

  * Each first-time adopter prepares an **opening statement of
    financial position** at the date of transition. This is the
    accrual starting point — every subsequent financial statement
    derives from it.
  * Certain **deemed-cost elections** (IPSAS 33 ¶64–¶70) let the
    adopter value PPE, intangibles, and investment property at fair
    value or previous GAAP carrying amount in lieu of reconstructing
    historical cost. Each election MUST be documented: asset class,
    basis used, rationale.
  * **Transition disclosures** (IPSAS 33 ¶142) require an explanatory
    note reconciling the prior (cash-basis) closing position to the
    accrual opening position.

Models
------

``OpeningBalanceSheet``  — one per tenant per transition date. Holds
    the meta-state: transition date, description, completion status,
    totals.

``OpeningBalanceItem``   — per-account opening balance line. Captures:
    account, debit, credit, deemed-cost election, rationale, supporting
    documentation reference.

``DeemedCostElection``   — structured catalogue of the elections made
    (one row per asset-class election) with rationale text.

Finalising the OBS
------------------
When the AG is satisfied with the opening balances, the
``OpeningBalanceSheet.finalise()`` service (on the viewset) posts a
single JournalHeader with every item as a JournalLine, dated on the
transition date, sourced as ``source_module='ipsas_33_transition'``.
That journal is immutable by the Sprint 1 posting rules — the opening
position is preserved forever.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from core.models import AuditBaseModel


OBS_STATUS_CHOICES = [
    ('DRAFT',      'Draft — being assembled'),
    ('REVIEWED',   'Reviewed — items frozen pending finalisation'),
    ('FINALISED',  'Finalised — posted to GL; immutable'),
]

DEEMED_COST_BASIS_CHOICES = [
    ('HISTORICAL',     'Historical cost (traced)'),
    ('FAIR_VALUE',     'Fair value at transition date (¶64)'),
    ('PREVIOUS_GAAP',  'Previous GAAP carrying amount (¶66)'),
    ('INDEXED_COST',   'Indexed historical cost (¶68)'),
    ('REVALUATION',    'Prior revaluation (¶70)'),
]


class OpeningBalanceSheet(AuditBaseModel):
    """IPSAS 33 opening balance sheet — one per tenant per transition."""

    transition_date = models.DateField(
        unique=True,
        help_text='Date of transition to accrual-basis IPSAS. '
                  'Opening balances are stated as at the END of the day '
                  'before this date.',
    )
    description = models.TextField(
        blank=True, default='',
        help_text='Narrative context for the transition (e.g. '
                  '"State of Delta: transition from cash IPSAS to '
                  'accrual IPSAS effective 1 January 2026").',
    )
    status = models.CharField(
        max_length=12, choices=OBS_STATUS_CHOICES,
        default='DRAFT', db_index=True,
    )

    # Totals recorded at finalisation time so auditors can verify the
    # sheet balanced at the moment of posting without re-summing all
    # items.
    total_assets           = models.DecimalField(max_digits=22, decimal_places=2, default=0)
    total_liabilities      = models.DecimalField(max_digits=22, decimal_places=2, default=0)
    total_net_assets       = models.DecimalField(max_digits=22, decimal_places=2, default=0)

    finalised_at    = models.DateTimeField(null=True, blank=True)
    finalised_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='opening_balance_sheets_finalised',
    )
    finalisation_journal = models.ForeignKey(
        'accounting.JournalHeader', on_delete=models.PROTECT,
        null=True, blank=True, related_name='opening_balance_sheet',
        help_text='The single JournalHeader that posted the opening '
                  'balances to the GL.',
    )
    transition_notes = models.TextField(
        blank=True, default='',
        help_text='IPSAS 33 ¶142 transition reconciliation — how the '
                  'prior cash-basis closing position reconciles to this '
                  'accrual opening position.',
    )

    class Meta:
        ordering = ['-transition_date']
        verbose_name = 'Opening Balance Sheet (IPSAS 33)'
        verbose_name_plural = 'Opening Balance Sheets (IPSAS 33)'
        permissions = [
            ('finalise_opening_balance_sheet',
             'Can finalise (post) an opening balance sheet'),
        ]

    def __str__(self):
        return f'Opening Balance Sheet @ {self.transition_date} ({self.status})'

    @property
    def is_balanced(self) -> bool:
        """Debits = Credits across all items, within 0.01 tolerance."""
        return abs(
            (self.total_assets or Decimal('0'))
            - (self.total_liabilities or Decimal('0'))
            - (self.total_net_assets or Decimal('0'))
        ) <= Decimal('0.01')


class OpeningBalanceItem(models.Model):
    """One per-account opening balance line."""

    sheet = models.ForeignKey(
        OpeningBalanceSheet, on_delete=models.CASCADE,
        related_name='items',
    )
    account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT,
        related_name='opening_balance_items',
    )
    debit   = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    credit  = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    # Deemed-cost election (only material for PPE / intangibles / lease
    # right-of-use assets per ¶64–¶70). Null means traced historical
    # cost was used.
    deemed_cost_basis = models.CharField(
        max_length=16, choices=DEEMED_COST_BASIS_CHOICES,
        blank=True, default='HISTORICAL',
    )
    deemed_cost_rationale = models.TextField(
        blank=True, default='',
        help_text='When deemed_cost_basis != HISTORICAL, IPSAS 33 ¶142 '
                  'requires disclosure of the rationale + valuation '
                  'approach.',
    )
    supporting_document_ref = models.CharField(
        max_length=200, blank=True, default='',
        help_text='Reference to the external valuation report, '
                  'photo index, or other supporting evidence.',
    )
    memo = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['account__code']
        constraints = [
            # One line per (sheet, account). Two opening balances on the
            # same account would silently corrupt the posting.
            models.UniqueConstraint(
                fields=['sheet', 'account'],
                name='uniq_obs_sheet_account',
            ),
            # Debit/credit mutually exclusive (same DB invariant as
            # JournalLine).
            models.CheckConstraint(
                check=models.Q(debit__gte=0),
                name='obs_item_debit_nonneg',
            ),
            models.CheckConstraint(
                check=models.Q(credit__gte=0),
                name='obs_item_credit_nonneg',
            ),
            models.CheckConstraint(
                check=~(models.Q(debit__gt=0) & models.Q(credit__gt=0)),
                name='obs_item_not_both_sides',
            ),
        ]

    def __str__(self):
        if self.debit > 0:
            return f'{self.account.code} — DR {self.debit:,.2f}'
        return f'{self.account.code} — CR {self.credit:,.2f}'

    @property
    def amount(self) -> Decimal:
        """Signed amount: debit positive, credit negative."""
        return (self.debit or Decimal('0')) - (self.credit or Decimal('0'))
