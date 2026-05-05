"""
RetentionService
================
Handles deduction of retention on each IPC and its release at:
  • Practical Completion  — 50 % of held retention
  • Final Completion      — remaining 50 %
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
    ContractStatus,
    RetentionRelease,
    RetentionReleaseStatus,
    RetentionReleaseType,
    ApprovalAction,
    ApprovalObjectType,
)
from contracts.services.exceptions import (
    InvalidTransitionError,
    RetentionCapError,
    SegregationOfDutiesError,
)
from contracts.services.sod import actor_can_bypass_sod
from core.models import quantize_currency

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


User = get_user_model()
ZERO    = Decimal("0.00")
HALF    = Decimal("0.50")
HUNDRED = Decimal("100")


class RetentionService:

    # ── Deduction on each IPC ─────────────────────────────────────────

    @staticmethod
    def compute_deduction(
        *,
        contract: Contract,
        balance: ContractBalance,
        this_certificate_gross: Decimal,
    ) -> Decimal:
        """
        Compute retention to deduct on this IPC.
        deduction = retention_rate% × this_certificate_gross.

        Caller then calls apply_deduction under SELECT FOR UPDATE to
        increment balance.retention_held.
        """
        if contract.retention_rate <= ZERO:
            return ZERO
        return quantize_currency(this_certificate_gross * contract.retention_rate / HUNDRED)

    @staticmethod
    def apply_deduction(
        *,
        balance: ContractBalance,
        deduction_amount: Decimal,
    ) -> None:
        if deduction_amount < ZERO:
            raise RetentionCapError(
                "Retention deduction cannot be negative.",
                context={"amount": str(deduction_amount)},
            )
        balance.retention_held = quantize_currency(balance.retention_held + deduction_amount)

    # ── Release at completion ──────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def create_release(
        cls,
        *,
        contract: Contract,
        release_type: str,
        actor: "AbstractUser",
    ) -> RetentionRelease:
        """
        Create a PENDING RetentionRelease at Practical or Final completion.
        The actual payment is raised via PaymentVoucher; mark_paid() is
        called by the treasury workflow when disbursed.
        """
        # Status gate
        if release_type == RetentionReleaseType.PRACTICAL_COMPLETION:
            required_status = ContractStatus.PRACTICAL_COMPLETION
        elif release_type == RetentionReleaseType.FINAL_COMPLETION:
            required_status = ContractStatus.FINAL_COMPLETION
        else:
            raise InvalidTransitionError(
                f"Unknown release_type: {release_type}",
            )

        if contract.status != required_status:
            raise InvalidTransitionError(
                f"Contract must be in {required_status} to release "
                f"{release_type} retention (is {contract.status}).",
                context={"contract_id": contract.pk, "status": contract.status},
            )

        # Uniqueness at DB level too (unique_together), but friendlier error here
        if contract.retention_releases.filter(release_type=release_type).exists():
            raise InvalidTransitionError(
                f"A {release_type} release already exists for this contract.",
            )

        # ── No-open-IPCs guard ───────────────────────────────────────
        # Both PRACTICAL_COMPLETION and FINAL_COMPLETION releases must
        # only fire AFTER every IPC has been approved or rejected. If
        # an IPC is still in DRAFT / SUBMITTED / CERTIFIER_REVIEWED,
        # additional retention will be deducted on it later — releasing
        # 50 % of the *currently-held* amount now permanently traps the
        # difference because ``unique_together(contract, release_type)``
        # blocks a second release of the same type.
        from contracts.models import (
            InterimPaymentCertificate,
            IPCStatus,
        )
        OPEN_IPC_STATUSES = (
            IPCStatus.DRAFT,
            IPCStatus.SUBMITTED,
            IPCStatus.CERTIFIER_REVIEWED,
        )
        if InterimPaymentCertificate.objects.filter(
            contract=contract, status__in=OPEN_IPC_STATUSES,
        ).exists():
            raise InvalidTransitionError(
                "Cannot release retention while open IPCs exist on the "
                "contract. Approve or reject every Draft / Submitted / "
                "Certifier-Reviewed IPC before raising a retention release "
                "— otherwise additional retention deducted later would be "
                "permanently trapped (unique_together blocks a second "
                "release of the same type).",
                context={
                    "contract_id": contract.pk,
                    "release_type": release_type,
                    "open_ipc_count": InterimPaymentCertificate.objects.filter(
                        contract=contract, status__in=OPEN_IPC_STATUSES,
                    ).count(),
                },
            )

        # Lock balance, compute amount
        balance = ContractBalance.objects.select_for_update().get(pk=contract.pk)
        remaining = balance.retention_held - balance.retention_released
        if remaining <= ZERO:
            raise RetentionCapError(
                "No retention remaining to release.",
                context={"held": str(balance.retention_held), "released": str(balance.retention_released)},
            )

        # Compute 50 % of original held at practical, remainder at final
        if release_type == RetentionReleaseType.PRACTICAL_COMPLETION:
            amount = quantize_currency(balance.retention_held * HALF)
            # But don't exceed what's still held
            amount = min(amount, remaining)
        else:  # FINAL_COMPLETION
            amount = remaining

        release = RetentionRelease.objects.create(
            contract=contract,
            release_type=release_type,
            amount=amount,
            status=RetentionReleaseStatus.PENDING,
            created_by=actor,
            updated_by=actor,
        )
        cls._record_step(release, actor, ApprovalAction.REQUEST_INFO, "Release created")
        return release

    @classmethod
    @transaction.atomic
    def approve(
        cls,
        *,
        release: RetentionRelease,
        actor: "AbstractUser",
        notes: str = "",
    ) -> RetentionRelease:
        if release.status != RetentionReleaseStatus.PENDING:
            raise InvalidTransitionError(
                f"Release must be PENDING to approve (is {release.status})."
            )
        if release.created_by_id == actor.pk and not actor_can_bypass_sod(actor):
            raise SegregationOfDutiesError(
                "Approver cannot be the same user who created the release.",
            )
        release.status       = RetentionReleaseStatus.APPROVED
        release.approved_by  = actor
        release.updated_by   = actor
        release.save(update_fields=["status", "approved_by", "updated_by", "updated_at"])
        cls._record_step(release, actor, ApprovalAction.APPROVE, notes)
        return release

    @classmethod
    @transaction.atomic
    def mark_paid(
        cls,
        *,
        release: RetentionRelease,
        payment_voucher_id: int,
        payment_date,
        actor: "AbstractUser",
    ) -> RetentionRelease:
        if release.status != RetentionReleaseStatus.APPROVED:
            raise InvalidTransitionError(
                f"Release must be APPROVED to mark paid (is {release.status})."
            )

        balance = ContractBalance.objects.select_for_update().get(pk=release.contract_id)
        new_released = quantize_currency(balance.retention_released + release.amount)
        if new_released > balance.retention_held:
            raise RetentionCapError(
                "Release would exceed retention held.",
                context={
                    "held":          str(balance.retention_held),
                    "already_released": str(balance.retention_released),
                    "this_release":  str(release.amount),
                },
            )
        balance.retention_released = new_released
        balance.version            = balance.version + 1
        balance.save(update_fields=["retention_released", "version", "updated_at"])

        release.status             = RetentionReleaseStatus.PAID
        release.payment_voucher_id = payment_voucher_id
        release.payment_date       = payment_date
        release.updated_by         = actor
        release.save(update_fields=[
            "status", "payment_voucher", "payment_date", "updated_by", "updated_at",
        ])
        return release

    # ── Internal ───────────────────────────────────────────────────────

    @staticmethod
    def _record_step(
        release: RetentionRelease,
        actor: "AbstractUser",
        action: str,
        notes: str,
    ) -> None:
        next_step = (
            ContractApprovalStep.objects.filter(
                object_type=ApprovalObjectType.RETENTION,
                object_id=release.pk,
            ).count()
            + 1
        )
        ContractApprovalStep.objects.create(
            object_type=ApprovalObjectType.RETENTION,
            object_id=release.pk,
            contract=release.contract,
            step_number=next_step,
            role_required="contracts.approve_retention_release",
            assigned_to=actor,
            action=action,
            action_by=actor,
            notes=notes or action,
        )
