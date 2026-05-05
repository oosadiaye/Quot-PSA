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
from django.db import transaction

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

        appr = (
            Appropriation.objects
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
        if payment.status != MobilizationPaymentStatus.PENDING:
            raise InvalidTransitionError(
                f"Mobilization payment is already {payment.status}.",
            )

        # Update the balance under row lock
        balance = (
            ContractBalance.objects
            .select_for_update()
            .get(pk=payment.contract_id)
        )
        balance.mobilization_paid = quantize_currency(balance.mobilization_paid + payment.amount)
        balance.version = balance.version + 1
        balance.save(update_fields=["mobilization_paid", "version", "updated_at"])

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
            reference=(
                f"{contract.contract_number or f'CONTRACT-{contract.pk}'}"
                f"-MOB"
            ),
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

        recovery = mobilization_rate% × this_certificate_gross

        But also capped so that cumulative mobilization_recovered never
        exceeds mobilization_paid.  Returns a non-negative Decimal.
        """
        if contract.mobilization_rate <= ZERO:
            return ZERO
        if balance.mobilization_paid <= ZERO:
            return ZERO

        outstanding = balance.mobilization_paid - balance.mobilization_recovered
        if outstanding <= ZERO:
            return ZERO

        raw_recovery = this_certificate_gross * contract.mobilization_rate / Decimal("100")
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

        balance = ContractBalance.objects.get(pk=contract.pk)
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
