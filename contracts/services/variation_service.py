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
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from contracts.services.exceptions import ConcurrencyError

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
        """Create a DRAFT variation.  Tier is auto-computed in model.save().

        A ceiling-increasing write-up is capped at the contract's budget
        appropriation — it may not exceed the available balance (raises
        ``InvalidTransitionError``). No-op for omissions / EOT / when no
        appropriation resolves.
        """
        cls.assert_increase_within_budget(contract, amount)
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
        # SoD via access + role permissions (no transaction-level
        # "reviewer ≠ submitter" block) — admin has full access.
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

        # SoD via access + role permissions (no transaction-level
        # "approver ≠ drafter/reviewer" block) — admin has full access.

        # Approve + refresh ceiling atomically.
        #
        # Race-safe: acquire the ContractBalance row lock BEFORE
        # flipping the variation status. Any concurrent IPC
        # submission on this contract reads the same balance row
        # (also via select_for_update inside ``submit_ipc``) and
        # blocks until this approve commits — so the IPC's ceiling
        # check always sees the final ceiling, never an in-flight
        # snapshot.
        #
        # Previously the variation's status save (and the
        # ``approved_variations_total`` aggregate it feeds) committed
        # before the lock was taken. An IPC submission that started
        # mid-approve could read the *new* aggregate ceiling but the
        # *old* persisted snapshot, or vice versa, depending on
        # interleaving — both directions caused incorrect ceiling
        # decisions.
        ContractBalance.objects.select_for_update().filter(
            pk=variation.contract_id,
        ).exists()  # acquire row lock without re-fetching for use

        variation.status = VariationStatus.APPROVED
        variation.approved_by = actor
        variation.approved_at = timezone.now()
        variation.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])

        cls._refresh_contract_ceiling(variation.contract)

        # ── Appropriation cap for ceiling-increasing variations ──
        # A write-up that INCREASES the contract ceiling (amount > 0) must not
        # exceed the budget available on the contract's appropriation. This is a
        # HARD gate now — an over-budget approval rolls back the whole atomic
        # transaction (ceiling refresh included). No-op on omission/EOT or when
        # no appropriation resolves; the IPC-time gate remains a later backstop.
        cls.assert_increase_within_budget(variation.contract, variation.amount)

        cls._record_step(
            variation, actor, ApprovalAction.APPROVE, notes or f"Approved at tier {variation.approval_tier}",
        )
        return variation

    @staticmethod
    def _resolve_appropriation(contract):
        """Resolve the ACTIVE budget appropriation for a contract, or ``None``.

        ``Contract.appropriation`` is intentionally unset; the budget line is
        found dynamically by matching the appropriation's segment FKs to the
        contract's MDA × (NCoA economic/fund) × fiscal year — the same match
        the contract detail page makes via ``/budget/appropriations/``.
        """
        from budget.models import Appropriation
        ncoa = getattr(contract, 'ncoa_code', None)
        if ncoa is None or contract.mda_id is None or contract.fiscal_year_id is None:
            return None
        econ_id = getattr(ncoa, 'economic_id', None)
        fund_id = getattr(ncoa, 'fund_id', None)
        if econ_id is None or fund_id is None:
            return None
        return (
            Appropriation.objects
            .filter(
                administrative_id=contract.mda_id,
                fund_id=fund_id,
                economic_id=econ_id,
                fiscal_year_id=contract.fiscal_year_id,
                status='ACTIVE',
            )
            .order_by('-id')
            .first()
        )

    @classmethod
    def appropriation_headroom(cls, contract):
        """The available balance on the contract's appropriation (a Decimal),
        or ``None`` when no appropriation resolves (cap not enforceable).

        ``available_balance = amount_approved − committed − expended`` — the
        budget still free to commit against this line.
        """
        appropriation = cls._resolve_appropriation(contract)
        return appropriation.available_balance if appropriation is not None else None

    @classmethod
    def assert_increase_within_budget(cls, contract, delta) -> None:
        """Hard cap: a positive write-up ``delta`` may not exceed the
        appropriation's available balance. Raises ``InvalidTransitionError``
        when it would. No-op for omissions/EOT (delta ≤ 0) or when no
        appropriation resolves.
        """
        delta = Decimal(str(delta or 0))
        if delta <= Decimal('0'):
            return
        headroom = cls.appropriation_headroom(contract)
        if headroom is not None and delta > headroom:
            raise InvalidTransitionError(
                f'Write-up of ₦{delta:,.2f} exceeds the budget available on '
                f"this contract's appropriation (₦{headroom:,.2f} remaining). "
                f'Reduce the write-up or raise a supplementary budget first.',
                context={
                    'requested': str(delta),
                    'available': str(headroom),
                },
            )

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
            # H6 fix: F('version')+1 server-side increment.
            try:
                ContractBalance.objects.filter(pk=balance.pk).update(
                    contract_ceiling=new_ceiling,
                    version=F('version') + 1,
                    updated_at=timezone.now(),
                )
            except IntegrityError as exc:
                raise ConcurrencyError(
                    "ContractBalance update rejected by DB trigger; retry.",
                    context={"contract_id": balance.pk},
                ) from exc
            balance.refresh_from_db()

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
