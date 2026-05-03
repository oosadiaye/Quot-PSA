"""
ContractVariation model
========================
Variations (scope changes) must pass through tiered approval:

  Tier 1 — LOCAL:        variation ≤ 15 % of original sum → MDA head + Finance
  Tier 2 — BOARD:        15 % < variation ≤ 25 %          → State Executive Council
  Tier 3 — BPP_REQUIRED: variation > 25 %                 → Bureau of Public Procurement

Only APPROVED variations count toward the contract ceiling.
Rejected/pending variations have no financial effect.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from core.models import AuditBaseModel, quantize_currency

ZERO = Decimal("0.00")
HUNDRED = Decimal("100.00")


class VariationType(models.TextChoices):
    ADDITION         = "ADDITION",          "Addition (extra work / scope)"
    OMISSION         = "OMISSION",          "Omission (scope reduction)"
    SUBSTITUTION     = "SUBSTITUTION",      "Substitution (replace item)"
    EXTENSION_OF_TIME = "EXTENSION_OF_TIME","Extension of Time (no cost)"


class VariationStatus(models.TextChoices):
    DRAFT     = "DRAFT",     "Draft"
    SUBMITTED = "SUBMITTED", "Submitted for Review"
    REVIEWED  = "REVIEWED",  "Technical Review Complete"
    APPROVED  = "APPROVED",  "Approved"
    REJECTED  = "REJECTED",  "Rejected"


class VariationApprovalTier(models.TextChoices):
    LOCAL        = "LOCAL",        "Local (MDA level, ≤ 15%)"
    BOARD        = "BOARD",        "Board / Executive Council (15–25%)"
    BPP_REQUIRED = "BPP_REQUIRED", "BPP Approval Required (> 25%)"


ALLOWED_VARIATION_TRANSITIONS: dict[str, list[str]] = {
    VariationStatus.DRAFT:     [VariationStatus.SUBMITTED],
    VariationStatus.SUBMITTED: [VariationStatus.REVIEWED, VariationStatus.REJECTED],
    VariationStatus.REVIEWED:  [VariationStatus.APPROVED, VariationStatus.REJECTED],
    VariationStatus.APPROVED:  [],  # terminal
    VariationStatus.REJECTED:  [VariationStatus.DRAFT],  # allow rework
}

# Tier thresholds (% of original_sum)
TIER_LOCAL_MAX = Decimal("15.00")
TIER_BOARD_MAX = Decimal("25.00")


class ContractVariation(AuditBaseModel):
    """
    A single variation order on a contract.

    Financial effect:
      amount > 0  → adds to ceiling (ADDITION, SUBSTITUTION)
      amount < 0  → reduces ceiling (OMISSION, SUBSTITUTION with net reduction)
      amount = 0  → purely time-related (EXTENSION_OF_TIME)

    The approval_tier is computed automatically on save based on the
    cumulative variation % relative to original_sum.
    """

    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="variations",
    )
    variation_number = models.PositiveSmallIntegerField(
        help_text="Sequential within the contract, auto-assigned by IPCService",
    )
    variation_type = models.CharField(max_length=20, choices=VariationType.choices)
    status = models.CharField(
        max_length=20, choices=VariationStatus.choices,
        default=VariationStatus.DRAFT, db_index=True,
    )
    approval_tier = models.CharField(
        max_length=20, choices=VariationApprovalTier.choices,
        default=VariationApprovalTier.LOCAL,
        help_text="Computed automatically — do not set manually",
    )

    description  = models.CharField(max_length=500)
    justification = models.TextField(
        help_text="Technical / engineering justification for the variation",
    )

    # Financial
    amount = models.DecimalField(
        max_digits=20, decimal_places=2, default=ZERO,
        help_text="Net financial impact (positive=addition, negative=omission, 0=EOT only)",
    )
    time_extension_days = models.IntegerField(
        default=0,
        help_text="Additional calendar days granted (0 if no time extension)",
    )

    # BPP compliance
    bpp_approval_ref = models.CharField(
        max_length=100, blank=True, default="",
        help_text="BPP No-Objection certificate reference for BPP_REQUIRED tier",
    )

    # Approval trail
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_variations",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")

    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["contract", "variation_number"]
        unique_together = [["contract", "variation_number"]]
        constraints = [
            # EXTENSION_OF_TIME variations have zero financial amount — enforce.
            models.CheckConstraint(
                check=(
                    ~models.Q(variation_type="EXTENSION_OF_TIME")
                    | models.Q(amount=Decimal("0.00"))
                ),
                name="contracts_variation_eot_amount_zero",
            ),
            # Omissions must have negative (or zero) amount.
            models.CheckConstraint(
                check=(
                    ~models.Q(variation_type="OMISSION")
                    | models.Q(amount__lte=Decimal("0.00"))
                ),
                name="contracts_variation_omission_non_positive",
            ),
            # Additions must have positive amount.
            models.CheckConstraint(
                check=(
                    ~models.Q(variation_type="ADDITION")
                    | models.Q(amount__gte=Decimal("0.00"))
                ),
                name="contracts_variation_addition_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.contract.contract_number} / VO-{self.variation_number:03d} "
            f"({self.get_variation_type_display()})"
        )

    # ── Tier computation ────────────────────────────────────────────────

    def compute_approval_tier(self) -> str:
        """
        Determine the required approval tier based on this variation's amount
        as a percentage of the contract's original sum.
        """
        original = self.contract.original_sum
        if original <= ZERO:
            return VariationApprovalTier.BPP_REQUIRED
        pct = abs(self.amount) / original * HUNDRED
        if pct <= TIER_LOCAL_MAX:
            return VariationApprovalTier.LOCAL
        if pct <= TIER_BOARD_MAX:
            return VariationApprovalTier.BOARD
        return VariationApprovalTier.BPP_REQUIRED

    def save(self, *args, **kwargs) -> None:
        # Auto-compute approval tier on every save so it stays current.
        self.approval_tier = self.compute_approval_tier()
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if (
            self.status == VariationStatus.APPROVED
            and self.approval_tier == VariationApprovalTier.BPP_REQUIRED
            and not self.bpp_approval_ref.strip()
        ):
            raise ValidationError(
                {
                    "bpp_approval_ref": (
                        "BPP approval reference is mandatory for variations "
                        "exceeding 25% of the original contract sum."
                    )
                }
            )

    def transition_to(self, new_status: str) -> None:
        allowed = ALLOWED_VARIATION_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Cannot transition variation from '{self.status}' to '{new_status}'. "
                f"Allowed: {allowed}"
            )
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])
