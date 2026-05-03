"""
ContractClosureService
=======================
Drives the closure stages of a contract:

  IN_PROGRESS          → PRACTICAL_COMPLETION  (via PRACTICAL cert)
  PRACTICAL_COMPLETION → DEFECTS_LIABILITY     (automatic on cert approval)
  DEFECTS_LIABILITY    → FINAL_COMPLETION      (via FINAL cert)
  FINAL_COMPLETION     → CLOSED                (via close())

Guarantees enforced here:
  • 50 % retention release must exist and be PAID before FINAL cert.
  • Remaining retention must be PAID before CLOSED.
  • No outstanding IPCs in SUBMITTED/CERTIFIER_REVIEWED/APPROVED/VOUCHER
    state may remain open at closure.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db import transaction

from contracts.models import (
    ApprovalAction,
    ApprovalObjectType,
    CertificateType,
    CompletionCertificate,
    Contract,
    ContractApprovalStep,
    ContractBalance,
    ContractStatus,
    IPCStatus,
    RetentionRelease,
    RetentionReleaseStatus,
    RetentionReleaseType,
)
from contracts.services.exceptions import (
    InvalidTransitionError,
    RetentionCapError,
    SegregationOfDutiesError,
)
from contracts.services.sod import actor_can_bypass_sod

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


User = get_user_model()

# IPC statuses that block closure (still in flight).
_OPEN_IPC_STATUSES = (
    IPCStatus.SUBMITTED,
    IPCStatus.CERTIFIER_REVIEWED,
    IPCStatus.APPROVED,
    IPCStatus.VOUCHER_RAISED,
)


class ContractClosureService:
    """Stateless service — all methods are class-methods."""

    # ── Practical completion ───────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def issue_practical_completion(
        cls,
        *,
        contract: Contract,
        issued_date,
        effective_date,
        actor: "AbstractUser",
        notes: str = "",
    ) -> CompletionCertificate:
        """IN_PROGRESS → PRACTICAL_COMPLETION via PRACTICAL cert."""
        if contract.status != ContractStatus.IN_PROGRESS:
            raise InvalidTransitionError(
                f"Contract must be IN_PROGRESS to issue practical "
                f"completion (is {contract.status}).",
                context={"contract_id": contract.pk, "status": contract.status},
            )
        cls._assert_no_open_ipcs(contract)

        cert = CompletionCertificate.objects.create(
            contract=contract,
            certificate_type=CertificateType.PRACTICAL,
            issued_date=issued_date,
            effective_date=effective_date,
            certified_by=actor,
            notes=notes,
            created_by=actor,
            updated_by=actor,
        )
        contract.transition_to(ContractStatus.PRACTICAL_COMPLETION, actor=actor)
        cls._record_step(
            contract, cert, actor,
            notes or "Practical completion certificate issued",
        )
        return cert

    # ── Defects liability (auto-advance) ───────────────────────────────

    @classmethod
    @transaction.atomic
    def enter_defects_liability(
        cls,
        *,
        contract: Contract,
        actor: "AbstractUser",
        notes: str = "",
    ) -> Contract:
        """PRACTICAL_COMPLETION → DEFECTS_LIABILITY."""
        if contract.status != ContractStatus.PRACTICAL_COMPLETION:
            raise InvalidTransitionError(
                f"Contract must be in PRACTICAL_COMPLETION to enter "
                f"defects liability (is {contract.status}).",
                context={"contract_id": contract.pk, "status": contract.status},
            )
        contract.transition_to(ContractStatus.DEFECTS_LIABILITY, actor=actor)
        cls._record_step(
            contract, None, actor,
            notes or "Entered defects liability period",
        )
        return contract

    # ── Final completion ───────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def issue_final_completion(
        cls,
        *,
        contract: Contract,
        issued_date,
        effective_date,
        actor: "AbstractUser",
        notes: str = "",
    ) -> CompletionCertificate:
        """DEFECTS_LIABILITY → FINAL_COMPLETION via FINAL cert."""
        if contract.status != ContractStatus.DEFECTS_LIABILITY:
            raise InvalidTransitionError(
                f"Contract must be in DEFECTS_LIABILITY to issue final "
                f"completion (is {contract.status}).",
                context={"contract_id": contract.pk, "status": contract.status},
            )
        cls._assert_no_open_ipcs(contract)

        # Require that the 50% practical retention release has actually
        # been PAID before we issue final completion — otherwise the
        # contractor has outstanding held money at the wrong gate.
        practical_release = (
            contract.retention_releases
            .filter(release_type=RetentionReleaseType.PRACTICAL_COMPLETION)
            .first()
        )
        if practical_release and practical_release.status != RetentionReleaseStatus.PAID:
            raise RetentionCapError(
                "Practical-completion retention release must be PAID before "
                "final completion certificate.",
                context={
                    "release_id": practical_release.pk,
                    "status": practical_release.status,
                },
            )

        cert = CompletionCertificate.objects.create(
            contract=contract,
            certificate_type=CertificateType.FINAL,
            issued_date=issued_date,
            effective_date=effective_date,
            certified_by=actor,
            notes=notes,
            created_by=actor,
            updated_by=actor,
        )
        contract.transition_to(ContractStatus.FINAL_COMPLETION, actor=actor)
        cls._record_step(
            contract, cert, actor,
            notes or "Final completion certificate issued",
        )
        return cert

    # ── Close ─────────────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def close(
        cls,
        *,
        contract: Contract,
        actor: "AbstractUser",
        notes: str = "",
    ) -> Contract:
        """
        FINAL_COMPLETION → CLOSED.

        Guard-rails:
          • All retention must be released AND paid.
          • No outstanding IPCs.
          • cumulative_gross_paid must equal cumulative_gross_certified.
          • Closer must not be the contract creator (SoD).
        """
        if contract.status != ContractStatus.FINAL_COMPLETION:
            raise InvalidTransitionError(
                f"Contract must be in FINAL_COMPLETION to close "
                f"(is {contract.status}).",
                context={"contract_id": contract.pk, "status": contract.status},
            )
        if contract.created_by_id == actor.pk and not actor_can_bypass_sod(actor):
            raise SegregationOfDutiesError(
                "Contract closer cannot be the same user who created the contract.",
                context={
                    "contract_id": contract.pk,
                    "creator_id": contract.created_by_id,
                    "actor_id": actor.pk,
                },
            )

        cls._assert_no_open_ipcs(contract)

        balance = (
            ContractBalance.objects
            .select_for_update()
            .get(pk=contract.pk)
        )
        # All retention released and paid.
        if balance.retention_released < balance.retention_held:
            raise RetentionCapError(
                "All retention must be released before closing.",
                context={
                    "held": str(balance.retention_held),
                    "released": str(balance.retention_released),
                },
            )
        unpaid_releases = contract.retention_releases.exclude(
            status=RetentionReleaseStatus.PAID,
        ).exists()
        if unpaid_releases:
            raise RetentionCapError(
                "All retention releases must be PAID before closing.",
            )

        # Paid-vs-certified reconciliation.
        if balance.cumulative_gross_paid != balance.cumulative_gross_certified:
            raise InvalidTransitionError(
                "Cannot close: cumulative_gross_paid ≠ cumulative_gross_certified.",
                context={
                    "certified": str(balance.cumulative_gross_certified),
                    "paid": str(balance.cumulative_gross_paid),
                },
            )

        contract.transition_to(ContractStatus.CLOSED, actor=actor)
        cls._record_step(
            contract, None, actor, notes or "Contract closed",
        )
        return contract

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _assert_no_open_ipcs(contract: Contract) -> None:
        if contract.ipcs.filter(status__in=_OPEN_IPC_STATUSES).exists():
            raise InvalidTransitionError(
                "Contract has IPCs still in flight; resolve them first.",
                context={"contract_id": contract.pk},
            )

    @staticmethod
    def _record_step(
        contract: Contract,
        cert: CompletionCertificate | None,
        actor: "AbstractUser",
        notes: str,
    ) -> None:
        object_type = (
            ApprovalObjectType.COMPLETION if cert else ApprovalObjectType.CONTRACT
        )
        object_id = cert.pk if cert else contract.pk
        next_step = (
            ContractApprovalStep.objects.filter(
                object_type=object_type,
                object_id=object_id,
            ).count()
            + 1
        )
        ContractApprovalStep.objects.create(
            object_type=object_type,
            object_id=object_id,
            contract=contract,
            step_number=next_step,
            role_required="contracts.close_contract",
            assigned_to=actor,
            action=ApprovalAction.APPROVE,
            action_by=actor,
            notes=notes,
        )
