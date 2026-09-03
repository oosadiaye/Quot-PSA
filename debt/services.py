"""
debt — public debt service GL posting.

FUTURE_MODULES §5.4 required that a debt-service coupon reaches the GL when
paid (invariant 2), but the module shipped with only a ``budget.Warrant`` FK on
``AmortisationCoupon`` and no posting path — nothing ever booked the
principal/interest/fee actuals. This closes that gap (review finding 3):

  * ``DebtServiceGLService.pay_coupon`` marks a coupon Paid and posts its
    debt-service journal:
        DR  Debt Service Expense                     total
        CR  Debt Service Payable (Special GL)               total
    The eventual settlement flows through the existing payment/warrant
    pipeline; the obligation stays in the GL even if ``debt`` is later
    disabled.

  * It records the fiscal-year actuals in ``DebtServiceCost`` (feeding
    ``cash_planning`` and IPSAS/GFS disclosures) and an audit trail row in
    ``AmortisationLedger`` (event='paid', pinned to the warrant when given).

Posting routes through the canonical ``IPSASJournalService.post_journal``
pipeline (validate → balance → period gate → post → GL balances → audit), so a
debt-service payment cannot silently drop out of the ledger.

Idempotency: a coupon already Paid / already carrying ledger 'paid' rejected.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services.base_posting import TransactionPostingError, get_gl_account
from accounting.services.ipsas_journal_service import IPSASJournalService

ZERO = Decimal("0.00")


class DebtServiceGLService:
    """Stateless debt-service GL service. All methods are class-methods."""

    @staticmethod
    def resolve_expense_account() -> Optional[Account]:
        """Debit leg — the Debt Service Expense GL. Tagged
        ``reconciliation_type='debt_service_expense'`` or
        ``DEFAULT_GL_ACCOUNTS['DEBT_SERVICE_EXPENSE']``."""
        expense = (
            Account.objects.filter(
                reconciliation_type="debt_service_expense",
                is_active=True,
            )
            .order_by("code")
            .first()
        )
        if expense is not None:
            return expense
        return get_gl_account("DEBT_SERVICE_EXPENSE", "Expense", "Debt")

    @staticmethod
    def resolve_payable_account() -> Optional[Account]:
        """Credit leg — the Debt Service Payable Special-GL recon. Tagged
        ``reconciliation_type='debt_service'`` or
        ``DEFAULT_GL_ACCOUNTS['DEBT_SERVICE_PAYABLE']``."""
        payable = (
            Account.objects.filter(
                reconciliation_type="debt_service",
                is_active=True,
            )
            .order_by("code")
            .first()
        )
        if payable is not None:
            return payable
        return get_gl_account("DEBT_SERVICE_PAYABLE", "Liability", "Debt")

    @classmethod
    @transaction.atomic
    def pay_coupon(
        cls, *,
        coupon,
        actor,
        warrant=None,
        paid_date=None,
        description: str = "",
    ) -> JournalHeader:
        """Mark an AmortisationCoupon paid and post its debt-service journal.

        Drives the coupon's instrument (via schedule) only for the reference /
        cost rows. Raises ``TransactionPostingError`` when:
          * the coupon is already paid / already carries a 'paid' ledger event
          * no Debt Service Expense GL is configured
          * no Debt Service Payable GL is configured
          * the coupon total is non-positive
        """
        from .models import AmortisationLedger, DebtServiceCost

        if coupon.status == "paid":
            raise TransactionPostingError(
                f"Amortisation coupon {coupon.pk} is already paid.",
            )
        if AmortisationLedger.objects.filter(
            coupon=coupon, event="paid",
        ).exists():
            raise TransactionPostingError(
                f"Amortisation coupon {coupon.pk} already has a paid ledger "
                "event. Refusing to double-post debt service.",
            )

        principal = Decimal(str(coupon.principal_amount or 0))
        interest = Decimal(str(coupon.interest_amount or 0))
        fees = Decimal(str(coupon.commitment_fee or 0))
        total = principal + interest + fees
        if total <= ZERO:
            raise TransactionPostingError(
                f"Amortisation coupon {coupon.pk} has no payable amount.",
            )

        expense = cls.resolve_expense_account()
        if expense is None:
            raise TransactionPostingError(
                "No Debt Service Expense GL configured. Tag an Expense account "
                "with reconciliation_type='debt_service_expense' or set "
                "DEFAULT_GL_ACCOUNTS['DEBT_SERVICE_EXPENSE'].",
            )
        payable = cls.resolve_payable_account()
        if payable is None:
            raise TransactionPostingError(
                "No Debt Service Payable GL configured. Tag a Liability account "
                "with reconciliation_type='debt_service' or set "
                "DEFAULT_GL_ACCOUNTS['DEBT_SERVICE_PAYABLE'].",
            )

        instrument = coupon.schedule.instrument if coupon.schedule else None
        posting_date = paid_date or timezone.now().date()
        ref = f"DS-{instrument.instrument_number if instrument else coupon.pk}-{coupon.pk:04d}"

        journal = JournalHeader.objects.create(
            posting_date=posting_date,
            reference_number=ref,
            description=(
                description
                or f"Debt service — {instrument.instrument_number if instrument else coupon.pk}"
            ),
            status="Draft",
            source_module="debt_service",
            source_document_id=coupon.pk,
            posted_by=actor,
        )
        JournalLine.objects.create(
            header=journal, account=expense,
            debit=total, credit=ZERO,
            memo=f"Debt service — {ref}",
        )
        JournalLine.objects.create(
            header=journal, account=payable,
            debit=ZERO, credit=total,
            memo=f"Debt service payable — {ref}",
        )
        # FAIL CLOSED — see VendorAdvanceService for rationale.
        IPSASJournalService.post_journal(journal, actor)

        # Pin the coupon paid (memoises the warrant; invariant 2).
        coupon.warrant = warrant
        coupon.status = "paid"
        coupon.paid_at = timezone.now()
        coupon.save(update_fields=["warrant", "status", "paid_at", "updated_at"])

        # Fiscal-year actuals feed cash_planning + IPSAS/GFS disclosures.
        actuals, created = DebtServiceCost.objects.get_or_create(
            fiscal_year=posting_date.year,
            month=posting_date.month,
            instrument=instrument,
            defaults={
                "principal_paid": principal,
                "interest_paid": interest,
                "fees_paid": fees,
            },
        )
        if not created:
            actuals.principal_paid = (actuals.principal_paid or ZERO) + principal
            actuals.interest_paid = (actuals.interest_paid or ZERO) + interest
            actuals.fees_paid = (actuals.fees_paid or ZERO) + fees
            actuals.save(update_fields=["principal_paid", "interest_paid", "fees_paid"])

        AmortisationLedger.objects.create(
            coupon=coupon,
            event="paid",
            amount=total,
            warrant=warrant,
            description=f"Paid via {journal.reference_number}",
            recorded_by=actor,
        )

        return journal
