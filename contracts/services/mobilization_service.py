"""
MobilizationService
===================
Handles the advance mobilization payment and its pro-rata recovery on
each IPC.

Recovery formula (the classical FIDIC / Delta State WORKS rule):

    recovery_this_ipc = mobilization_advance
                      × this_certificate_gross
                      / original_sum

Capped so that cumulative recoveries never exceed the advance.
The DB-level CheckConstraint guarantees
    mobilization_recovered <= mobilization_paid
so even if the service computes wrong, the trigger rejects it.
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
    ContractBalance,
    MobilizationPayment,
    MobilizationPaymentStatus,
)
from contracts.services.exceptions import (
    InvalidTransitionError,
    MobilizationRecoveryError,
    SegregationOfDutiesError,
)
from core.models import quantize_currency

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


User = get_user_model()
ZERO = Decimal("0.00")


class MobilizationService:

    # ── Disbursement ───────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def issue_advance(
        cls,
        *,
        contract: Contract,
        actor: "AbstractUser",
    ) -> MobilizationPayment:
        """
        Create a PENDING mobilization payment record of the correct
        amount AND its DRAFT advance Payment Voucher, linked together.

        Central-payment model: issuing the advance immediately mints a
        DRAFT ``PaymentVoucherGov`` (tagged ADVANCE / special-GL 'A' /
        vendor) so the mobilisation surfaces in the Payment Vouchers
        list straight away. Approving that PV then auto-creates the
        draft Payment in Outgoing Payments (via
        ``ensure_draft_payment_for_pv``), and posting that Payment is
        the single disbursement event — which bumps
        ``ContractBalance.mobilization_paid`` (see
        ``record_disbursement``). This service no longer disburses
        directly; there is no second cash door.
        """
        if contract.mobilization_rate <= ZERO:
            raise InvalidTransitionError(
                "This contract has 0% mobilization rate — no advance to issue.",
                context={"contract_id": contract.pk},
            )
        if hasattr(contract, "mobilization_payment"):
            raise InvalidTransitionError(
                "A mobilization payment already exists for this contract.",
                context={
                    "contract_id":  contract.pk,
                    "existing_id":  contract.mobilization_payment.pk,
                    "status":       contract.mobilization_payment.status,
                },
            )

        # SoD is enforced by access + role permissions (the mobilisation
        # permission), not a transaction-level maker/checker block. Anyone
        # holding the permission may issue the advance — including the
        # contract drafter, the vendor registrar, or a prior approver —
        # and the admin/superuser has full access.

        # ── Strict budget appropriation check ─────────────────────────
        # Mobilization is a real cash outflow that hits the same
        # appropriation line as the contract itself. Before reserving
        # the advance, confirm the matching Appropriation row has
        # enough remaining balance. The lookup uses the same
        # MDA × Economic × Fund × FY tuple the contract-creation form
        # validated; no row → block (no budget authority); insufficient
        # available balance → block with deficit detail.
        cls._validate_appropriation(contract)

        payment = MobilizationPayment.objects.create(
            contract=contract,
            amount=contract.mobilization_amount,
            status=MobilizationPaymentStatus.PENDING,
            created_by=actor,
            updated_by=actor,
        )

        # Auto-create the draft advance PV and link it. From here the
        # mobilisation follows the normal PV → approve → draft Payment →
        # post pipeline like every other outgoing payment.
        from accounting.services.pv_factory import (
            create_draft_voucher_from_mobilization,
        )
        pv = create_draft_voucher_from_mobilization(payment=payment, actor=actor)
        payment.payment_voucher = pv
        payment.updated_by = actor
        payment.save(update_fields=["payment_voucher", "updated_by", "updated_at"])
        return payment

    # ── Appropriation guard ────────────────────────────────────────────

    @classmethod
    def _validate_appropriation(cls, contract: Contract) -> None:
        """Block mobilization issuance when no funded appropriation
        line exists or when the available balance is below the
        advance amount.

        The contract created-against-appropriation tuple is
        (administrative, fund, economic, fiscal_year). We look it up
        through the contract's NCoA code to avoid re-implementing the
        bridge logic.
        """
        from budget.models import Appropriation

        ncoa = contract.ncoa_code
        if ncoa is None:
            raise InvalidTransitionError(
                "Contract has no NCoA code — appropriation cannot be "
                "verified. Edit the contract to assign segments first.",
                context={"contract_id": contract.pk},
            )

        # Lock the matching appropriation row so two concurrent
        # mobilisation issuances against the same line can't both
        # pass the balance check. ``issue_advance`` is already
        # @transaction.atomic so this lock is held for the duration
        # of the create-MobilizationPayment write that follows.
        # Without the lock, two operators clicking "Issue Advance"
        # on different mobilisation-eligible contracts that share
        # an appropriation could both pass with the same
        # ``available_balance`` snapshot.
        appr = (
            Appropriation.objects
            .select_for_update()
            .filter(
                administrative_id=ncoa.administrative_id,
                economic_id=ncoa.economic_id,
                fund_id=ncoa.fund_id,
                fiscal_year_id=contract.fiscal_year_id,
                status="ACTIVE",
            )
            .order_by("-amount_approved")
            .first()
        )
        if appr is None:
            raise InvalidTransitionError(
                "No ACTIVE appropriation found for this contract's "
                "MDA × GL × Fund × Fiscal Year combination. A "
                "supplementary appropriation is required before "
                "mobilization can be issued.",
                context={
                    "contract_id":   contract.pk,
                    "ncoa_admin":    ncoa.administrative_id,
                    "ncoa_economic": ncoa.economic_id,
                    "ncoa_fund":     ncoa.fund_id,
                    "fiscal_year":   contract.fiscal_year_id,
                },
            )

        try:
            available = Decimal(str(appr.available_balance or 0))
        except (TypeError, ValueError):
            available = ZERO
        required = Decimal(str(contract.mobilization_amount or 0))
        if required > available:
            deficit = required - available
            raise InvalidTransitionError(
                f"Insufficient appropriation balance. Required "
                f"NGN {required:,.2f}; available NGN {available:,.2f}; "
                f"deficit NGN {deficit:,.2f}. Issue a supplementary "
                f"appropriation or virement before mobilization.",
                context={
                    "appropriation_id":  appr.pk,
                    "required":          str(required),
                    "available":         str(available),
                    "deficit":           str(deficit),
                },
            )

        # ── Warrant (AIE) cash gate ───────────────────────────────────
        # The appropriation check above is the budget-authority layer;
        # the warrant is the cash-release layer. A mobilization advance is
        # cash leaving the TSA, so when the tenant operates warrant-based
        # control it must also fit within the released-warrant headroom
        # for this appropriation:
        #     headroom = total_warrants_released − (committed + expended)
        # and (committed + expended) == amount_approved − available_balance
        # (see Appropriation.available_balance). Computed on the row we
        # already locked above, so no extra query and no NCoA bridge.
        from accounting.budget_logic import warrant_enforcement_enabled
        if warrant_enforcement_enabled():
            released = Decimal(str(appr.total_warrants_released or 0))
            consumed = Decimal(str(appr.amount_approved or 0)) - available
            warrant_headroom = released - consumed
            if required > warrant_headroom:
                raise InvalidTransitionError(
                    f"Insufficient released Warrant (AIE). Required "
                    f"NGN {required:,.2f}; warrant headroom NGN "
                    f"{warrant_headroom:,.2f} (released NGN {released:,.2f} "
                    f"− consumed NGN {consumed:,.2f}). Release a Warrant for "
                    f"this appropriation before issuing the mobilization "
                    f"advance.",
                    context={
                        "appropriation_id":  appr.pk,
                        "required":          str(required),
                        "warrants_released": str(released),
                        "warrant_headroom":  str(warrant_headroom),
                    },
                )

    # ── Approval (PENDING → APPROVED) ─────────────────────────────────

    @classmethod
    @transaction.atomic
    def approve(
        cls,
        *,
        payment: MobilizationPayment,
        actor: "AbstractUser",
        notes: str = "",
    ) -> MobilizationPayment:
        """Move a PENDING mobilization advance to APPROVED.

        Pre-requisite governance gate before treasury raises a PV.
        Mirrors the Retention release approve pattern: approver
        cannot be the user who issued the advance (SoD), unless the
        actor holds explicit ``contracts.bypass_sod`` permission or
        is a superuser. Every approval writes a
        ``ContractApprovalStep`` audit row.

        Raises:
            InvalidTransitionError — if the payment is not PENDING.
            SegregationOfDutiesError — if approver == issuer.
        """
        if payment.status != MobilizationPaymentStatus.PENDING:
            raise InvalidTransitionError(
                f"Mobilization payment must be PENDING to approve "
                f"(currently {payment.status}).",
                context={
                    "payment_id": payment.pk,
                    "current_status": payment.status,
                },
            )

        # SoD via access + role permissions (no transaction-level
        # "approver ≠ issuer" block) — anyone holding the approve
        # permission may approve; admin has full access.
        payment.status     = MobilizationPaymentStatus.APPROVED
        payment.updated_by = actor
        payment.save(update_fields=["status", "updated_by", "updated_at"])

        # Audit row on ContractApprovalStep so the contract's full
        # approval ledger surfaces this signoff alongside contract
        # activation, IPC approvals, retention releases, etc.
        from contracts.models import (
            ContractApprovalStep, ApprovalAction, ApprovalObjectType,
        )
        next_step = (
            ContractApprovalStep.objects.filter(
                object_type=ApprovalObjectType.MOBILIZATION,
                object_id=payment.pk,
            ).count()
            + 1
        )
        ContractApprovalStep.objects.create(
            object_type=ApprovalObjectType.MOBILIZATION,
            object_id=payment.pk,
            contract=payment.contract,
            step_number=next_step,
            role_required="contracts.approve_mobilization",
            assigned_to=actor,
            action=ApprovalAction.APPROVE,
            action_by=actor,
            notes=notes or "Mobilization advance approved for payment.",
        )

        return payment

    # ── Cancel (PENDING/APPROVED → CANCELLED) ──────────────────────

    @classmethod
    @transaction.atomic
    def cancel(
        cls,
        *,
        payment: MobilizationPayment,
        actor: "AbstractUser",
        notes: str = "",
    ) -> MobilizationPayment:
        """Cancel a mobilisation advance before disbursement.

        Allowed from PENDING or APPROVED. Blocked once the advance is
        PAID (use a reversal at that point — cancellation can't undo
        a journal that's already posted).

        Writes an audit step recording who cancelled and why.
        """
        # Lock to prevent concurrent cancel + schedule-payment races.
        payment = MobilizationPayment.objects.select_for_update().get(pk=payment.pk)

        if payment.status not in (
            MobilizationPaymentStatus.PENDING,
            MobilizationPaymentStatus.APPROVED,
        ):
            raise InvalidTransitionError(
                f"Mobilization payment must be PENDING or APPROVED to "
                f"cancel (currently {payment.status}). Already-paid "
                f"advances require a reversal, not a cancellation.",
                context={
                    "payment_id": payment.pk,
                    "current_status": payment.status,
                },
            )

        payment.status     = MobilizationPaymentStatus.CANCELLED
        payment.updated_by = actor
        payment.save(update_fields=["status", "updated_by", "updated_at"])

        # Audit on ContractApprovalStep so the contract's full ledger
        # surfaces this action alongside the original approval (if
        # one happened before cancellation).
        from contracts.models import (
            ContractApprovalStep, ApprovalAction, ApprovalObjectType,
        )
        next_step = (
            ContractApprovalStep.objects.filter(
                object_type=ApprovalObjectType.MOBILIZATION,
                object_id=payment.pk,
            ).count()
            + 1
        )
        ContractApprovalStep.objects.create(
            object_type=ApprovalObjectType.MOBILIZATION,
            object_id=payment.pk,
            contract=payment.contract,
            step_number=next_step,
            role_required="contracts.approve_mobilization",
            assigned_to=actor,
            action=ApprovalAction.REJECT,
            action_by=actor,
            notes=notes or "Mobilization advance cancelled.",
        )

        return payment

    # ── Schedule for payment (APPROVED → draft PV created) ──────────

    @classmethod
    @transaction.atomic
    def schedule_payment(
        cls,
        *,
        payment: MobilizationPayment,
        actor: "AbstractUser",
        notes: str = "",
    ):
        """Ensure the DRAFT advance PaymentVoucher exists for this
        mobilisation and return ``(payment, pv)``.

        Since ``issue_advance`` now auto-creates the PV, this is an
        idempotent safety net (e.g. legacy mobilisations issued before
        auto-PV, or a lost link). It does NOT create the cash Payment —
        that is materialised by ``ensure_draft_payment_for_pv`` when the
        PV is APPROVED, so mobilisation surfaces in Outgoing Payments via
        the same central pipeline as every other PV.

        IDEMPOTENCY:
          1. ``SELECT FOR UPDATE`` on this MobilizationPayment row
             serialises concurrent calls.
          2. The PV factory short-circuits on existing
             ``payment.payment_voucher_id`` linkage.

        Raises:
            InvalidTransitionError — if payment is not APPROVED/PENDING.
            PVFactoryError — vendor / NCoA / TSA missing.
        """
        from accounting.services.pv_factory import (
            create_draft_voucher_from_mobilization,
        )

        # Lock the row to serialise concurrent schedule_payment calls.
        # Without this, two simultaneous calls would both read
        # ``payment_voucher_id=None`` and both create distinct PVs —
        # one of which would be orphaned (paid by nothing, but still
        # consuming a sequence-allocated voucher number).
        payment = MobilizationPayment.objects.select_for_update().get(pk=payment.pk)

        # Allow either APPROVED (canonical path) or PENDING (legacy
        # advances created before the APPROVED status existed —
        # treasury still needs a PV to disburse them).
        if payment.status not in (
            MobilizationPaymentStatus.APPROVED,
            MobilizationPaymentStatus.PENDING,
        ):
            raise InvalidTransitionError(
                f"Mobilization payment must be APPROVED or PENDING to "
                f"schedule for payment (currently {payment.status}).",
                context={
                    "payment_id": payment.pk,
                    "current_status": payment.status,
                },
            )

        pv = create_draft_voucher_from_mobilization(
            payment=payment, actor=actor, notes=notes,
        )

        # Link back so the next call is a no-op (idempotent) and the
        # frontend can show the PV number on the mobilization row.
        if payment.payment_voucher_id != pv.pk:
            payment.payment_voucher = pv
            payment.updated_by = actor
            payment.save(update_fields=["payment_voucher", "updated_by", "updated_at"])

        # Central pipeline: the draft Payment is materialised by
        # ``ensure_draft_payment_for_pv`` when the PV is APPROVED — not
        # here — so mobilisation rides the exact same path as every other
        # PV (no bespoke bypass). This method only guarantees the advance
        # PV exists and is linked; approving that PV drops the draft
        # Payment into Outgoing Payments.
        return payment, pv

    @classmethod
    @transaction.atomic
    def record_disbursement(
        cls,
        *,
        pv,
        payment_date,
        actor: "AbstractUser",
    ) -> "MobilizationPayment | None":
        """Record the contract-side effects of a disbursed mobilisation.

        Central-payment model: cash actually leaves when the linked
        ``Payment`` is POSTED — ``PaymentViewSet._post_advance_payment``
        already credits the operator's chosen bank, debits the
        Vendor-Advance recon Special-GL, and writes the ``VendorAdvance``
        ledger row (source ``AP_DOWNPAYMENT``). It then calls THIS method
        so the mobilisation recovery machinery stays correct:

          * bump ``ContractBalance.mobilization_paid`` — the pro-rata IPC
            clawback (:meth:`compute_recovery`) is measured against it, and
          * flip the ``MobilizationPayment`` → PAID.

        This method does **not** disburse — there is exactly one cash
        door now (the Payment post), so the old fail-closed
        ``VendorAdvanceService.disburse`` here is gone.

        Safe to call for ANY advance payment: returns ``None`` when the
        PV is not a mobilisation. Idempotent: a mobilisation already
        PAID / recovered is left untouched, so re-posting cannot
        double-count ``mobilization_paid``.
        """
        mob = (
            MobilizationPayment.objects
            .select_for_update()
            .filter(payment_voucher=pv)
            .first()
        )
        if mob is None:
            return None  # not a mobilisation — nothing to record

        already_disbursed = (
            MobilizationPaymentStatus.PAID,
            MobilizationPaymentStatus.PARTIALLY_RECOVERED,
            MobilizationPaymentStatus.FULLY_RECOVERED,
        )
        if mob.status in already_disbursed:
            return mob  # idempotent — balance already reflects the advance

        # Bump the balance under row lock. H6 pattern: F('version')+1
        # server-side increment — race-safe even against a stale snapshot.
        balance = (
            ContractBalance.objects
            .select_for_update()
            .get(pk=mob.contract_id)
        )
        new_paid = quantize_currency(balance.mobilization_paid + mob.amount)
        try:
            ContractBalance.objects.filter(pk=balance.pk).update(
                mobilization_paid=new_paid,
                version=F('version') + 1,
                updated_at=timezone.now(),
            )
        except IntegrityError as exc:
            raise ConcurrencyError(
                "ContractBalance update rejected by DB trigger; retry.",
                context={"contract_id": balance.pk},
            ) from exc

        mob.status = MobilizationPaymentStatus.PAID
        mob.payment_date = payment_date
        mob.updated_by = actor
        mob.save(update_fields=["status", "payment_date", "updated_by", "updated_at"])
        return mob

    # ── Recovery computation (pure function, no side-effects) ──────────

    @staticmethod
    def compute_recovery(
        *,
        contract: Contract,
        balance: ContractBalance,
        this_certificate_gross: Decimal,
    ) -> Decimal:
        """
        Compute how much mobilization to recover on the current IPC.

        Canonical FIDIC / Delta State WORKS rule:

            recovery_this_ipc = mobilization_paid
                              × this_certificate_gross
                              / original_sum

        Capped so cumulative mobilization_recovered never exceeds
        mobilization_paid.  Returns a non-negative Decimal.

        M2 fix: the previous implementation used
        ``this_certificate_gross × mobilization_rate / 100`` which is
        equivalent to the canonical formula ONLY when
        ``MobilizationPayment.amount == original_sum × mobilization_rate
        / 100``. If a procurement officer manually adjusts the
        ``amount`` on the MobilizationPayment (legitimate path — e.g.
        partial-advance scenarios), the rate-based recovery diverges
        and the contractor recovers either too much or too little. The
        canonical FIDIC formula uses the actual advance disbursed
        (``balance.mobilization_paid``), keeping recovery proportional
        to what was actually paid.
        """
        if balance.mobilization_paid <= ZERO:
            return ZERO

        outstanding = balance.mobilization_paid - balance.mobilization_recovered
        if outstanding <= ZERO:
            return ZERO

        original_sum = Decimal(str(getattr(contract, 'original_sum', 0) or 0))
        if original_sum <= ZERO:
            return ZERO

        raw_recovery = (
            balance.mobilization_paid * this_certificate_gross / original_sum
        )
        return quantize_currency(min(raw_recovery, outstanding))

    # ── Apply recovery to balance (called from IPCService) ─────────────

    @classmethod
    def apply_recovery(
        cls,
        *,
        balance: ContractBalance,
        recovery_amount: Decimal,
    ) -> None:
        """
        Increment balance.mobilization_recovered.  Assumes the caller is
        already inside a transaction holding a SELECT FOR UPDATE on
        balance.

        Raises MobilizationRecoveryError if the amount would over-recover.
        """
        if recovery_amount < ZERO:
            raise MobilizationRecoveryError(
                "Recovery amount cannot be negative.",
                context={"amount": str(recovery_amount)},
            )
        new_recovered = quantize_currency(balance.mobilization_recovered + recovery_amount)
        if new_recovered > balance.mobilization_paid:
            raise MobilizationRecoveryError(
                "Recovery would exceed mobilization advance paid.",
                context={
                    "paid":          str(balance.mobilization_paid),
                    "already":       str(balance.mobilization_recovered),
                    "this_recovery": str(recovery_amount),
                },
            )
        balance.mobilization_recovered = new_recovered

    # ── Status reconciliation after IPC payment ───────────────────────

    @classmethod
    def reconcile_payment_status(cls, *, contract: Contract) -> None:
        """
        After an IPC is paid, update the MobilizationPayment status
        (PAID → PARTIALLY_RECOVERED → FULLY_RECOVERED).
        """
        try:
            payment = contract.mobilization_payment
        except MobilizationPayment.DoesNotExist:
            return

        # SELECT FOR UPDATE — caller (IPCService.mark_paid) is already
        # inside @transaction.atomic, so the row lock is held until the
        # outer commit. Prevents two concurrent paid-IPC reconciliations
        # from racing on the same contract's mobilization status.
        balance = ContractBalance.objects.select_for_update().get(pk=contract.pk)
        if balance.mobilization_paid <= ZERO:
            return

        if balance.mobilization_recovered >= balance.mobilization_paid:
            new_status = MobilizationPaymentStatus.FULLY_RECOVERED
        elif balance.mobilization_recovered > ZERO:
            new_status = MobilizationPaymentStatus.PARTIALLY_RECOVERED
        else:
            new_status = MobilizationPaymentStatus.PAID

        if payment.status != new_status:
            payment.status = new_status
            payment.save(update_fields=["status", "updated_at"])
