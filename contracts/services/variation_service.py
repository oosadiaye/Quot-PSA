"""
VariationService
================
Manages the lifecycle of a ContractVariation:

    DRAFT  →  SUBMITTED  →  REVIEWED  →  APPROVED   (ceiling updated)
                                      →  REJECTED

Tier rules on approval:
  LOCAL         (<= 15 %): MDA head + Finance          (permission: approve_variation_local)
  BOARD         (15–25 %): State Executive Council    (permission: approve_variation_board)
  BPP_REQUIRED  (>  25 %): BPP No-Objection mandatory (permission: approve_variation_bpp
                                                       AND bpp_approval_ref populated)
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from contracts.models import (
    Contract,
    ContractApprovalStep,
    ContractBalance,
    ContractVariation,
    VariationStatus,
    VariationApprovalTier,
    ApprovalAction,
    ApprovalObjectType,
)
from contracts.services.exceptions import (
    InvalidTransitionError,
    SegregationOfDutiesError,
    VariationApprovalError,
)
from contracts.services.numbering import next_variation_number
from contracts.services.sod import actor_can_bypass_sod

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


User = get_user_model()


# Mapping from tier → required permission codename.
TIER_PERMISSION = {
    VariationApprovalTier.LOCAL:        "contracts.approve_variation_local",
    VariationApprovalTier.BOARD:        "contracts.approve_variation_board",
    VariationApprovalTier.BPP_REQUIRED: "contracts.approve_variation_bpp",
}


class VariationService:

    # ── Create / submit ────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def create_draft(
        cls,
        *,
        contract: Contract,
        variation_type: str,
        amount: Decimal,
        description: str,
        justification: str,
        actor: "AbstractUser",
        time_extension_days: int = 0,
        bpp_approval_ref: str = "",
    ) -> ContractVariation:
        """Create a DRAFT variation.  Tier is auto-computed in model.save()."""
        variation = ContractVariation.objects.create(
            contract=contract,
            variation_number=next_variation_number(contract),
            variation_type=variation_type,
            amount=amount,
            description=description,
            justification=justification,
            time_extension_days=time_extension_days,
            bpp_approval_ref=bpp_approval_ref,
            status=VariationStatus.DRAFT,
            created_by=actor,
            updated_by=actor,
        )
        return variation

    @classmethod
    @transaction.atomic
    def submit(
        cls,
        *,
        variation: ContractVariation,
        actor: "AbstractUser",
        notes: str = "",
    ) -> ContractVariation:
        """DRAFT → SUBMITTED."""
        if variation.status != VariationStatus.DRAFT:
            raise InvalidTransitionError(
                f"Variation must be DRAFT to submit (is {variation.status})."
            )
        variation.transition_to(VariationStatus.SUBMITTED)
        cls._record_step(variation, actor, ApprovalAction.REQUEST_INFO, notes or "Submitted for review")
        return variation

    @classmethod
    @transaction.atomic
    def review(
        cls,
        *,
        variation: ContractVariation,
        actor: "AbstractUser",
        notes: str = "",
    ) -> ContractVariation:
        """SUBMITTED → REVIEWED (technical review complete)."""
        if variation.status != VariationStatus.SUBMITTED:
            raise InvalidTransitionError(
                f"Variation must be SUBMITTED to review (is {variation.status})."
            )
        # SoD: reviewer != submitter (submitter = created_by for DRAFT,
        # but we track the submit action in ApprovalStep; re-use that).
        if variation.created_by_id == actor.pk and not actor_can_bypass_sod(actor):
            raise SegregationOfDutiesError(
                "Reviewer cannot be the same user who drafted the variation."
            )
        variation.transition_to(VariationStatus.REVIEWED)
        cls._record_step(variation, actor, ApprovalAction.VERIFY, notes or "Technical review complete")
        return variation

    # ── Approve / reject ───────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def approve(
        cls,
        *,
        variation: ContractVariation,
        actor: "AbstractUser",
        notes: str = "",
    ) -> ContractVariation:
        """
        REVIEWED → APPROVED.

        On approval the contract ceiling increases by the variation amount
        (can be negative for an omission).  The ContractBalance.contract_ceiling
        is refreshed with the new value under SELECT FOR UPDATE.
        """
        if variation.status != VariationStatus.REVIEWED:
            raise InvalidTransitionError(
                f"Variation must be REVIEWED to approve (is {variation.status})."
            )

        # Tier / permission check
        required_perm = TIER_PERMISSION[variation.approval_tier]
        if not actor.has_perm(required_perm):
            raise VariationApprovalError(
                f"Actor lacks required permission for {variation.approval_tier} tier.",
                context={
                    "required_permission": required_perm,
                    "tier": variation.approval_tier,
                },
            )
        if (
            variation.approval_tier == VariationApprovalTier.BPP_REQUIRED
            and not variation.bpp_approval_ref.strip()
        ):
            raise VariationApprovalError(
                "BPP approval reference is mandatory for variations >25% of original sum.",
                context={"tier": variation.approval_tier},
            )

        # Segregation of duties — approver distinct from drafter AND reviewer
        prior_actors = set(
            ContractApprovalStep.objects.filter(
                object_type=ApprovalObjectType.VARIATION,
                object_id=variation.pk,
            ).values_list("action_by_id", flat=True)
        )
        prior_actors.add(variation.created_by_id)
        if actor.pk in prior_actors and not actor_can_bypass_sod(actor):
            raise SegregationOfDutiesError(
                "Approver cannot also be the drafter or reviewer of this variation.",
                context={"prior_actors": list(prior_actors), "approver": actor.pk},
            )

        # Approve + refresh ceiling atomically
        variation.status = VariationStatus.APPROVED
        variation.approved_by = actor
        variation.approved_at = timezone.now()
        variation.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])

        cls._refresh_contract_ceiling(variation.contract)

        cls._record_step(
            variation, actor, ApprovalAction.APPROVE, notes or f"Approved at tier {variation.approval_tier}",
        )
        return variation

    @classmethod
    @transaction.atomic
    def reject(
        cls,
        *,
        variation: ContractVariation,
        actor: "AbstractUser",
        reason: str,
    ) -> ContractVariation:
        if variation.status in (VariationStatus.APPROVED, VariationStatus.REJECTED):
            raise InvalidTransitionError(
                f"Cannot reject a variation that is already {variation.status}."
            )
        variation.status = VariationStatus.REJECTED
        variation.rejection_reason = reason
        variation.save(update_fields=["status", "rejection_reason", "updated_at"])
        cls._record_step(variation, actor, ApprovalAction.REJECT, reason)
        return variation

    # ── Internal ───────────────────────────────────────────────────────

    @staticmethod
    def _refresh_contract_ceiling(contract: Contract) -> None:
        """Re-compute and persist ContractBalance.contract_ceiling."""
        new_ceiling = contract.contract_ceiling  # property re-aggregates approved variations
        balance = (
            ContractBalance.objects
            .select_for_update()
            .filter(pk=contract.pk)
            .first()
        )
        if balance is None:
            return  # contract not yet activated; ceiling will be set at activation
        if balance.contract_ceiling != new_ceiling:
            balance.contract_ceiling = new_ceiling
            balance.version = balance.version + 1
            balance.save(update_fields=["contract_ceiling", "version", "updated_at"])

    @staticmethod
    def _record_step(
        variation: ContractVariation,
        actor: "AbstractUser",
        action: str,
        notes: str,
    ) -> None:
        next_step = (
            ContractApprovalStep.objects.filter(
                object_type=ApprovalObjectType.VARIATION,
                object_id=variation.pk,
            ).count()
            + 1
        )
        ContractApprovalStep.objects.create(
            object_type=ApprovalObjectType.VARIATION,
            object_id=variation.pk,
            contract=variation.contract,
            step_number=next_step,
            role_required=TIER_PERMISSION.get(variation.approval_tier, ""),
            assigned_to=actor,
            action=action,
            action_by=actor,
            notes=notes,
        )
