"""
ContractActivationService
==========================
Moves a contract from DRAFT → ACTIVATED and bootstraps its
ContractBalance row.

Called when:
  • BPP no-objection is received (for >= BOARD tier awards)
  • Due Process Certificate is in hand
  • Performance bond has been lodged
  • Signed contract is on file

Once activated, milestones and IPCs can be created.
Activation is a one-way transition (reversal requires a separate
ContractCancellationService, not in scope for v1).
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from contracts.models import (
    Contract,
    ContractApprovalStep,
    ContractBalance,
    ContractStatus,
    ApprovalAction,
    ApprovalObjectType,
)
from contracts.services.exceptions import (
    InvalidTransitionError,
    SegregationOfDutiesError,
)
from contracts.services.numbering import next_contract_number
from contracts.services.sod import actor_can_bypass_sod

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


User = get_user_model()


class ContractActivationService:
    """Stateless service — all methods are class-methods."""

    @classmethod
    @transaction.atomic
    def activate(
        cls,
        *,
        contract: Contract,
        actor: "AbstractUser",
        notes: str = "",
    ) -> Contract:
        """
        Move contract from DRAFT → ACTIVATED.

        Raises:
            InvalidTransitionError if not currently in DRAFT
            SegregationOfDutiesError if the activator created the contract
            ValidationError        if required fields are missing
        """
        # 1. Status gate
        if contract.status != ContractStatus.DRAFT:
            raise InvalidTransitionError(
                f"Contract must be in DRAFT to activate (currently {contract.status}).",
                context={"contract_id": contract.pk, "status": contract.status},
            )

        # 2. Segregation of duties — activator must not be the creator,
        #    unless the actor has explicit SoD-bypass (SAP-style override)
        #    or is a Django superuser. Every bypass is audit-logged on
        #    the ContractApprovalStep row below (`sod_bypassed=True`).
        sod_bypassed = actor_can_bypass_sod(actor)
        if contract.created_by_id == actor.pk and not sod_bypassed:
            raise SegregationOfDutiesError(
                "Contract activator cannot be the same user who created the contract. "
                "Grant the user 'contracts.bypass_sod' if your governance model allows "
                "the same actor to draft and activate.",
                context={
                    "creator_id": contract.created_by_id,
                    "actor_id": actor.pk,
                    "contract_id": contract.pk,
                },
            )

        # 3. Required fields sanity
        missing = []
        if not contract.signed_date:        missing.append("signed_date")
        if not contract.contract_start_date: missing.append("contract_start_date")
        if not contract.contract_end_date:   missing.append("contract_end_date")
        if not contract.vendor_id:           missing.append("vendor")
        if not contract.mda_id:              missing.append("mda")
        if not contract.ncoa_code_id:        missing.append("ncoa_code")
        if missing:
            raise ValidationError(
                {f: "Required for contract activation." for f in missing},
            )

        # 4. Assign contract number if still blank (DRAFT may not have one)
        if not contract.contract_number:
            contract.contract_number = next_contract_number(
                contract_type=contract.contract_type,
                fiscal_year=contract.fiscal_year.year if hasattr(contract.fiscal_year, "year") else contract.fiscal_year_id,
            )

        # 5. Create or refresh the ContractBalance row.
        # NOTE: using get_or_create so re-running activation is idempotent
        # for the balance creation — important during manual recoveries.
        ceiling = contract.contract_ceiling
        balance, created = ContractBalance.objects.get_or_create(
            contract=contract,
            defaults={
                "contract_ceiling":            ceiling,
                "cumulative_gross_certified":  Decimal("0.00"),
                "pending_voucher_amount":      Decimal("0.00"),
                "cumulative_gross_paid":       Decimal("0.00"),
                "mobilization_paid":           Decimal("0.00"),
                "mobilization_recovered":      Decimal("0.00"),
                "retention_held":              Decimal("0.00"),
                "retention_released":          Decimal("0.00"),
                "version":                     1,
            },
        )
        if not created:
            # Keep the ceiling in sync if variations were approved before activation
            if balance.contract_ceiling != ceiling:
                balance.contract_ceiling = ceiling
                balance.version = balance.version + 1
                balance.save(update_fields=["contract_ceiling", "version", "updated_at"])

        # 6. Flip status
        contract.transition_to(ContractStatus.ACTIVATED, actor=actor)
        contract.save(update_fields=["contract_number", "status", "updated_at"])

        # 7. Write immutable audit step
        ContractApprovalStep.objects.create(
            object_type=ApprovalObjectType.CONTRACT,
            object_id=contract.pk,
            contract=contract,
            step_number=1,
            role_required="contracts.activate_contract",
            assigned_to=actor,
            action=ApprovalAction.APPROVE,
            action_by=actor,
            notes=(
                (notes or "Contract activated.")
                + ("  [SoD bypassed — same user drafted and activated]" if sod_bypassed else "")
            ),
        )

        return contract


# SoD bypass logic now lives in contracts.services.sod (shared across
# activation, IPC workflow, variations, retention release, etc.) so all
# services agree on who is considered an admin.
