"""Budget check policy — per-tenant rules controlling how strictly
expense GL postings are gated against an active Appropriation.

Model lives in its own module so Account, Journal and the various
posting services can all import it without a circular dependency on
the big ``models/advanced.py`` monolith.

Policy model
────────────
Each row defines one rule covering a contiguous GL code range:

    gl_from   = '21000000'          (inclusive)
    gl_to     = '21999999'          (inclusive)
    check_level in {NONE, WARNING, STRICT}
    warning_threshold_pct  → only used when check_level == WARNING

Multiple rows MAY overlap. The resolver picks the NARROWEST range
whose `gl_from .. gl_to` contains the account in question. When two
ranges have identical widths, the one with the higher `priority`
wins. This lets tenants set a broad default (e.g. ``NONE`` for
everything) and then tighten specific code families (``STRICT`` on
personnel costs) without editing the default rule.

Check level semantics
─────────────────────
NONE     — never blocks; no logging, no warning. The transaction
           posts exactly as though no appropriation gate existed.
WARNING  — posts always succeed, but when the appropriation
           utilisation reaches ≥ ``warning_threshold_pct``, the
           serializer returns a non-blocking ``warnings=[...]``
           field the UI surfaces as a yellow banner.
STRICT   — posts blocked when no matching appropriation exists OR
           when the appropriation would be exceeded. Applies across
           every module: journal post, PO approval, 3-way match,
           vendor invoice posting, payment voucher.

Accounts outside every rule's range fall through to the
``BUDGET_DEFAULT_CONTROL_LEVEL`` Django setting (default: ``NONE``).
"""
from django.db import models


class BudgetCheckRule(models.Model):
    """A contiguous GL-code range + the check level to apply to it."""

    CHECK_LEVEL_CHOICES = [
        ('NONE', 'No check — posts without any appropriation check'),
        ('WARNING', 'Warning — flags when appropriation is over threshold'),
        ('STRICT', 'Strict — blocks posting without an active appropriation'),
    ]

    # Ranges are compared lexicographically on the *string* code (which
    # works because NCoA codes are zero-padded fixed-length numerics).
    gl_from = models.CharField(
        max_length=20, db_index=True,
        help_text='Lowest GL account code included in this rule (inclusive).',
    )
    gl_to = models.CharField(
        max_length=20, db_index=True,
        help_text='Highest GL account code included in this rule (inclusive).',
    )
    check_level = models.CharField(
        max_length=10, choices=CHECK_LEVEL_CHOICES, default='WARNING',
    )
    warning_threshold_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=80.00,
        help_text='Utilisation % at which a WARNING-level rule starts flagging '
                  '(ignored for NONE and STRICT). Default 80%.',
    )
    description = models.CharField(
        max_length=200, blank=True, default='',
        help_text='What this range represents (e.g. "Personnel Costs", '
                  '"Capital Expenditure"). Surfaced in the Settings UI and '
                  'in the warning message on the UI.',
    )
    priority = models.IntegerField(
        default=0,
        help_text='Tiebreaker when two rules have the same range width. '
                  'Higher priority wins.',
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['gl_from', '-priority']
        verbose_name = 'Budget Check Rule'
        verbose_name_plural = 'Budget Check Rules'
        indexes = [
            models.Index(fields=['is_active', 'gl_from', 'gl_to']),
        ]

    def __str__(self) -> str:
        label = self.description or f'{self.gl_from}–{self.gl_to}'
        return f'{label} [{self.check_level}]'

    # ── Helpers ────────────────────────────────────────────────

    def contains(self, code: str) -> bool:
        """True when ``code`` falls within [gl_from, gl_to] inclusive."""
        if not code:
            return False
        return self.gl_from <= code <= self.gl_to

    @property
    def width(self) -> int:
        """Range width — used by the resolver to pick the narrowest match."""
        try:
            return int(self.gl_to) - int(self.gl_from)
        except (TypeError, ValueError):
            # Non-numeric codes: fall back to lexicographic length.
            return len(self.gl_to) + len(self.gl_from)
