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
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from contracts.services.exceptions import ConcurrencyError

from contracts.models import (
    Contract,
    ContractApprovalStep,
    ContractBalance,
    ContractStatus,
    ContractYearPlan,
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

        # 4b. Year-plan invariant — multi-year contract support.
        #
        # Every active contract MUST have at least one ContractYearPlan
        # row, because the IPC fiscal-year boundary control reads from
        # year_plans (not contract.fiscal_year) when deciding which
        # fiscal years can host IPCs. Two paths:
        #
        #   (a) Operator already added one or more year plans for a
        #       multi-year contract — validate that their
        #       planned_amount sums to original_sum (with a small
        #       rounding tolerance so two-decimal-place arithmetic
        #       doesn't false-trip).
        #   (b) No year plans exist — auto-create a single-year plan
        #       so the legacy single-year flow keeps working unchanged.
        #       Sequence=1, fiscal_year=contract.fiscal_year,
        #       appropriation=contract.appropriation,
        #       planned_amount=original_sum.
        cls._validate_or_create_year_plans(contract)

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
            # Keep the ceiling in sync if variations were approved before activation.
            # H6 fix: F('version')+1 server-side increment.
            if balance.contract_ceiling != ceiling:
                try:
                    ContractBalance.objects.filter(pk=balance.pk).update(
                        contract_ceiling=ceiling,
                        version=F('version') + 1,
                        updated_at=timezone.now(),
                    )
                except IntegrityError as exc:
                    raise ConcurrencyError(
                        "ContractBalance update rejected by DB trigger; retry.",
                        context={"contract_id": balance.pk},
                    ) from exc
                balance.refresh_from_db()

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

    # ── Year-plan invariant ─────────────────────────────────────────────
    # Tolerance for the planned_amount sum-check. Two-decimal-place
    # arithmetic over many year plans can drift by a kobo or two from
    # original_sum due to rounding; ₦0.10 is comfortably below any
    # number an auditor would flag as material.
    _SUM_TOLERANCE = Decimal("0.10")

    @classmethod
    def _validate_or_create_year_plans(cls, contract: Contract) -> None:
        """Enforce the multi-year invariant or auto-create a single-year plan.

        Called from ``activate`` after required-fields validation and
        before ``ContractBalance`` creation. Two outcomes:

          (a) Operator pre-populated year plans → sum must equal
              ``contract.original_sum`` (within ``_SUM_TOLERANCE``);
              raises ``ValidationError`` otherwise. Each plan must
              also reference a fiscal year that is consistent with the
              contract's start/end dates (defensive — nothing
              technically forbids a year-plan in a year the contract
              doesn't span, but it indicates a data-entry mistake).

          (b) No year plans exist → create exactly one matching the
              contract's primary ``fiscal_year`` for the full
              ``original_sum``. Preserves the legacy single-year
              behaviour for tenants that don't touch the new feature.

        Idempotent on re-run (e.g. recovery from a failed activation):
        if (b)'s auto-row was created on a previous attempt, this
        re-validates as case (a) and passes.
        """
        plans = list(contract.year_plans.all())

        if not plans:
            # Case (b): legacy single-year shape.
            #
            # Now that ``Contract.appropriation`` correctly points at
            # ``budget.Appropriation`` (audit fix #2 / migration 0010),
            # passing it through to the auto-created year_plan is
            # finally type-correct. Previously this assignment was a
            # latent bug: ``Contract.appropriation`` pointed at
            # ``accounting.BudgetEncumbrance`` while
            # ``ContractYearPlan.appropriation`` pointed at
            # ``budget.Appropriation``, so any non-None value would
            # have failed at write time. 0 of 4 production contracts
            # had it set, which is why the bug never surfaced.
            ContractYearPlan.objects.create(
                contract=contract,
                fiscal_year=contract.fiscal_year,
                appropriation=getattr(contract, "appropriation", None),
                planned_amount=contract.original_sum,
                carried_forward_from_prior_year=Decimal("0.00"),
                sequence=1,
                created_by=contract.updated_by_id and contract.updated_by,
                updated_by=contract.updated_by_id and contract.updated_by,
            )
            return

        # Case (a): validate the multi-year sum.
        total_planned = sum(
            (p.planned_amount or Decimal("0.00") for p in plans),
            Decimal("0.00"),
        )
        original_sum = contract.original_sum or Decimal("0.00")
        delta = abs(total_planned - original_sum)
        if delta > cls._SUM_TOLERANCE:
            raise ValidationError(
                {
                    "year_plans": (
                        f"Sum of year-plan planned_amount (₦{total_planned:,.2f}) "
                        f"does not equal contract original_sum (₦{original_sum:,.2f}). "
                        f"Delta: ₦{delta:,.2f} — adjust the year plans before "
                        f"activating."
                    )
                }
            )

        # Defensive: every plan must reference a fiscal_year — already
        # guaranteed by the FK NOT NULL, but assert here so a future
        # schema change can't quietly weaken this. Sequences must be
        # unique 1..N (the unique_together on contract+fiscal_year is
        # the canonical guarantee; this is a friendlier error path).
        sequences = [p.sequence for p in plans]
        if sorted(sequences) != list(range(1, len(plans) + 1)):
            raise ValidationError(
                {
                    "year_plans": (
                        f"Year plan sequences must be consecutive starting "
                        f"from 1 (got {sorted(sequences)}). Re-number the "
                        f"plans chronologically."
                    )
                }
            )


# SoD bypass logic now lives in contracts.services.sod (shared across
# activation, IPC workflow, variations, retention release, etc.) so all
# services agree on who is considered an admin.
