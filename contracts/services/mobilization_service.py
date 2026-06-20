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
from contracts.services.sod import actor_can_bypass_sod

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
        Create a PENDING mobilization payment record of the correct amount.

        The actual disbursement journal entry is raised by the
        PaymentVoucher flow (accounting.PaymentVoucherGov); this service
        only creates the tracking record and updates the balance's
        mobilization_paid field once the PV is marked PAID.
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

        # ── SoD: contract creator cannot issue mobilisation ─────────
        # Mobilisation is the single largest upfront cash outflow on
        # most contracts (typically 10-25% of contract value paid
        # before any work starts).
        #
        # H16 fix: the previous check only blocked the contract
        # drafter. A vendor-registration officer or any prior contract
        # approver could still issue mobilisation through a different
        # route, defeating the SoD intent. The expanded check now
        # blocks:
        #   1. The user who drafted the contract.
        #   2. The user who registered the vendor (vendor.created_by).
        #   3. Any user who acted on a previous ContractApprovalStep
        #      for this contract.
        #
        # Bypass paths (superuser, tenant admin, explicit
        # contracts.bypass_sod permission) preserved via the existing
        # ``actor_can_bypass_sod`` helper.
        actor_pk = getattr(actor, 'pk', None)
        if actor_pk and not actor_can_bypass_sod(actor):
            # 1. Contract drafter
            if contract.created_by_id and contract.created_by_id == actor_pk:
                raise InvalidTransitionError(
                    "Segregation of duties: the user who drafted the contract "
                    "cannot also issue its mobilisation advance. Have a "
                    "different officer perform this action.",
                    context={
                        "contract_id":   contract.pk,
                        "conflict":      "contract_drafter",
                        "contract_drafter_id": contract.created_by_id,
                        "actor_id":      actor_pk,
                    },
                )

            # 2. Vendor registrar — the officer who created the Vendor
            # master record cannot also disburse advance funds to that
            # vendor (classic vendor-master / payments SoD split).
            vendor = getattr(contract, 'vendor', None)
            vendor_creator_id = getattr(vendor, 'created_by_id', None) if vendor else None
            if vendor_creator_id and vendor_creator_id == actor_pk:
                raise InvalidTransitionError(
                    "Segregation of duties: the user who registered this "
                    "vendor cannot also issue mobilisation advances to "
                    "that vendor. Have a different officer perform this "
                    "action.",
                    context={
                        "contract_id":  contract.pk,
                        "conflict":     "vendor_registrar",
                        "vendor_id":    getattr(vendor, 'pk', None),
                        "vendor_registrar_id": vendor_creator_id,
                        "actor_id":     actor_pk,
                    },
                )

            # 3. Prior contract approver — anyone who has signed an
            # approval step on this contract cannot also disburse the
            # advance. Catches the case where the same officer
            # approves the contract and then immediately issues
            # mobilisation through a different route.
            from contracts.models.audit import ContractApprovalStep
            prior_approver_ids = set(
                ContractApprovalStep.objects
                .filter(contract=contract)
                .values_list('action_by_id', flat=True)
            )
            if actor_pk in prior_approver_ids:
                raise InvalidTransitionError(
                    "Segregation of duties: a user who has already "
                    "approved this contract cannot also issue its "
                    "mobilisation advance. Have a different officer "
                    "perform this action.",
                    context={
                        "contract_id":  contract.pk,
                        "conflict":     "prior_contract_approver",
                        "actor_id":     actor_pk,
                    },
                )

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

        # SoD: approver ≠ issuer (created_by). Same governance shape as
        # ``RetentionService.approve``. ``actor_can_bypass_sod`` covers
        # superusers and tenant admins with the explicit bypass perm.
        if (
            payment.created_by_id
            and payment.created_by_id == getattr(actor, "pk", None)
            and not actor_can_bypass_sod(actor)
        ):
            raise SegregationOfDutiesError(
                "Segregation of duties: the user who issued the "
                "mobilisation advance cannot also approve it. Have a "
                "different officer approve before treasury raises the PV.",
                context={
                    "payment_id":   payment.pk,
                    "issuer_id":    payment.created_by_id,
                    "actor_id":     getattr(actor, "pk", None),
                },
            )

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
        """Create a DRAFT PaymentVoucher AND a DRAFT Payment for an
        APPROVED mobilisation advance, linking both. Returns
        ``(payment, pv, draft_payment)``.

        Two records get created so the advance surfaces in BOTH the
        Payment Vouchers list (the document) and the Outgoing Payments
        page (the cash event). Treasury can then review and post the
        Payment via the normal AP cascade.

        IDEMPOTENCY — defended at multiple layers so duplicate posts
        from network retries / double-clicks / concurrent calls cannot
        happen:
          1. ``SELECT FOR UPDATE`` on this MobilizationPayment row
             serialises concurrent schedule_payment calls.
          2. The PV factory short-circuits on existing
             ``payment.payment_voucher_id`` linkage.
          3. The Payment lookup uses ``payment.reference_number`` as
             the deterministic key — a second call finds the existing
             draft and returns it instead of minting a new one.

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

        draft_payment = cls._ensure_draft_payment(payment=payment, pv=pv, actor=actor)
        return payment, pv, draft_payment

    @classmethod
    def _ensure_draft_payment(cls, *, payment, pv, actor):
        """Lookup-or-create the AP cash Payment row that materialises
        this mobilization in the Outgoing Payments page.

        Idempotent by ``Payment.reference_number == payment.reference_number``.
        The two-step (lookup → create) is safe under the
        ``select_for_update`` lock acquired in ``schedule_payment``
        — two concurrent calls would block at the lock, then the
        second one sees the existing row and returns it.
        """
        from accounting.models.receivables import Payment
        from accounting.models.gl import TransactionSequence
        from datetime import date as _date

        ref = payment.reference_number

        # Lookup includes soft-deleted via ``all_objects`` so a
        # previously-cancelled draft can't be re-created on top of
        # itself (operator would need to undelete first).
        existing = Payment.all_objects.filter(reference_number=ref).first()
        if existing is not None:
            return existing

        payment_number = TransactionSequence.get_next("payment", "PAY-")
        vendor = payment.contract.vendor if payment.contract else None
        return Payment.objects.create(
            payment_number=payment_number,
            payment_date=_date.today(),
            payment_method="Wire",
            # Canonical reference — this is the IDEMPOTENCY KEY. Any
            # future schedule_payment call for this MobilizationPayment
            # finds this row via filter(reference_number=ref) and
            # returns it unchanged.
            reference_number=ref,
            total_amount=payment.amount,
            status="Draft",
            payment_voucher=pv,
            vendor=vendor,
            is_advance=True,
            advance_type="Supplier Advance",
            advance_remaining=payment.amount,
            document_number=payment_number,
            created_by=actor,
            updated_by=actor,
        )

    @classmethod
    @transaction.atomic
    def mark_paid(
        cls,
        *,
        payment: MobilizationPayment,
        payment_voucher_id: int,
        payment_date,
        actor: "AbstractUser",
    ) -> MobilizationPayment:
        """
        Mark the advance as paid and bump ContractBalance.mobilization_paid.

        Phase 1 (SAP Special-GL pattern): also creates a ``VendorAdvance``
        ledger row in the central advance ledger so the popup
        ("uncleared advance exists") can gate every downstream
        AP / PV / IPC posting against this vendor. The advance
        disbursement journal (DR Vendor-Advance recon / CR Cash) is
        posted by ``VendorAdvanceService.disburse`` — replaces the
        old "DR Mobilization Advance Receivable / CR Cash" pattern.

        Called by the payment-voucher / treasury workflow when the PV
        actually disburses. Wrapped in SELECT FOR UPDATE on the balance.
        """
        # Accept PENDING for backward-compat with mobilization rows
        # created before the APPROVED status was introduced (legacy
        # records sit at PENDING but the cash event genuinely
        # happened). New advances should go via APPROVED — the
        # frontend gates the Approve button on PENDING and the PV
        # creation pathway encourages the approval step, but we
        # don't hard-block the cash transition here.
        valid_pre_states = (
            MobilizationPaymentStatus.PENDING,
            MobilizationPaymentStatus.APPROVED,
        )
        if payment.status not in valid_pre_states:
            raise InvalidTransitionError(
                f"Mobilization payment must be PENDING or APPROVED to "
                f"mark paid (currently {payment.status}).",
                context={
                    "payment_id":   payment.pk,
                    "current_status": payment.status,
                    "valid_states": [s.value for s in valid_pre_states],
                },
            )

        # Update the balance under row lock
        balance = (
            ContractBalance.objects
            .select_for_update()
            .get(pk=payment.contract_id)
        )
        # H6 fix: F('version')+1 server-side increment — race-safe even
        # if a future caller passes a stale ``balance`` from outside the
        # SELECT FOR UPDATE.
        new_paid = quantize_currency(balance.mobilization_paid + payment.amount)
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
        balance.refresh_from_db()

        payment.status          = MobilizationPaymentStatus.PAID
        payment.payment_voucher_id = payment_voucher_id
        payment.payment_date    = payment_date
        payment.updated_by      = actor
        payment.save(update_fields=["status", "payment_voucher", "payment_date", "updated_at"])

        # ── Special-GL ledger row + disbursement journal ─────────────
        # FAIL-CLOSED. The previous try/except let
        # ``ContractBalance.mobilization_paid`` commit while
        # ``VendorAdvanceService.disburse`` silently failed — leaving
        # the balance flagged as paid without a journal posting and
        # without a Special-GL ledger row. Downstream IPC ceiling
        # checks then computed mobilization recovery against an
        # advance that was never journalized, creating a phantom
        # offset in the books.
        #
        # Now any disburse error bubbles, the surrounding
        # @transaction.atomic on this method rolls back the
        # mobilization_paid increment, and the operator must fix the
        # CoA gap before retrying. The error message identifies the
        # blocking configuration item directly.
        from accounting.services.vendor_advance import VendorAdvanceService
        contract = payment.contract
        VendorAdvanceService.disburse(
            vendor=contract.vendor,
            amount=payment.amount,
            source_type="MOBILIZATION",
            source_id=payment.pk,
            # ``payment.reference_number`` is the canonical idempotency
            # key (e.g. MOB-DSG/WORKS/2026/003) — same reference is
            # used by the PV (source_document), the AP Payment
            # (reference_number), and now the GL disbursement journal.
            # JournalHeader.reference_number is uniquely indexed, so a
            # retry of mark_paid against the same advance trips the
            # IntegrityError instead of silently creating a duplicate
            # DR/CR pair. (VendorAdvanceService.disburse also has its
            # own (source_type, source_id) idempotency guard above
            # this — defence in depth.)
            reference=payment.reference_number,
            posting_date=payment_date,
            actor=actor,
            notes=(
                f"Mobilisation advance per contract "
                f"{contract.contract_number or contract.pk}."
            ),
        )

        return payment

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
