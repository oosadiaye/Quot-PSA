"""
staff_advances — Special-GL disbursement & retirement services.

FUTURE_MODULES §5.10 documented that StaffAdvance would "reuse the proven
VendorAdvance special-GL pattern", but the module shipped with only a
``journal`` FK and nothing ever posted to it — advances left the system
unrecorded in the GL. This closes that gap (review finding 3) by mirroring
``accounting.services.vendor_advance.VendorAdvanceService`` exactly:

  * ``disburse``          — DR Staff-Advance Recon / CR Cash, pins
                            ``StaffAdvance.journal``, status OUTSTANDING.
  * ``retire_imprest``    — DR Expense / CR Recon, pins
                            ``ImprestRetirement.journal``.
  * ``record_recovery``   — DR Expense / CR Recon, bumps ``recovered_amount``
                            and rolls status OUTSTANDING → PARTIAL → CLEARED.

Every operation routes through the canonical
``IPSASJournalService.post_journal`` pipeline (validate → balance → period
gate → post → update GL balances → audit), so a staff advance is held to the
same ledger discipline as a vendor advance, journal, PO, or payment voucher.
The ``journal`` FK memoises the pin so the obligation stays in the GL even if
the module is later disabled (invariant 2).

Retirement journal reference is unique per event (``CLR-<advance>-NN``-style)
because ``JournalHeader.reference_number`` is uniquely indexed and an imprest /
advance may be retired in several slices.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services.base_posting import TransactionPostingError, get_gl_account
from accounting.services.ipsas_journal_service import IPSASJournalService
from core.models import quantize_currency

ZERO = Decimal("0.00")


class StaffAdvanceGLService:
    """Stateless staff-advance GL service. All methods are class-methods."""

    # ── Account resolution ────────────────────────────────────────────

    @staticmethod
    def resolve_recon_account() -> Optional[Account]:
        """Find the tenant's Staff-Advance Special-GL recon account.

        Order:
          1. Active Account flagged ``reconciliation_type='staff_advance'``.
          2. Settings ``DEFAULT_GL_ACCOUNTS['STAFF_ADVANCE']`` code.
          3. None — caller surfaces a clear "configure first" error.
        """
        recon = (
            Account.objects.filter(
                reconciliation_type="staff_advance",
                is_active=True,
            )
            .order_by("code")
            .first()
        )
        if recon is not None:
            return recon
        return get_gl_account("STAFF_ADVANCE", "Asset", "Advance")

    @staticmethod
    def _resolve_cash_account(bank_account=None) -> Account:
        """Resolve the cash credit leg: explicit BankAccount→TSA cash ladder,
        identical to VendorAdvanceService."""
        if bank_account is not None and getattr(bank_account, "gl_account", None):
            return bank_account.gl_account
        from accounting.services.tsa_gl_resolver import resolve_tsa_cash_gl
        return resolve_tsa_cash_gl()

    @staticmethod
    def _resolve_recovery_expense(expense_account=None) -> Account:
        """Debit leg for a recovery/retirement: explicit expense account, else
        the tenant's default Payroll/Claims expense GL."""
        if expense_account is not None:
            return expense_account
        return get_gl_account("STAFF_ADVANCE_EXPENSE", "Expense", "Advance")

    # ── Disburse (post: DR Special-GL / CR Cash) ──────────────────────

    @classmethod
    @transaction.atomic
    def disburse(cls, *, staff_advance, actor, bank_account=None) -> JournalHeader:
        """Post the disbursement journal for a StaffAdvance and pin it.

        DR  Staff-Advance Recon (Special GL)    amount
        CR  Cash / TSA                                       amount

        Returns the posted ``JournalHeader`` (also stored on
        ``staff_advance.journal``). Raises ``TransactionPostingError`` when
        the advance is already recorded in the GL, no recon GL is configured,
        no cash GL is resolvable, or the amount is non-positive.
        """
        if staff_advance.journal_id:
            raise TransactionPostingError(
                f"Staff advance {staff_advance.pk} already has a disbursement "
                f"journal ({staff_advance.journal_id}). Refusing to double-post.",
            )
        amount = Decimal(str(staff_advance.amount or 0))
        if amount <= ZERO:
            raise TransactionPostingError(
                "Staff advance amount must be greater than zero.",
            )

        recon = cls.resolve_recon_account()
        if recon is None:
            raise TransactionPostingError(
                "No Staff-Advance Special-GL recon account configured. "
                "Open Chart of Accounts → tag an Asset GL with "
                "reconciliation_type='staff_advance', or set "
                "DEFAULT_GL_ACCOUNTS['STAFF_ADVANCE'] in settings.",
            )
        cash_account = cls._resolve_cash_account(bank_account)

        reference = staff_advance.reference or f"STAFFADV-{staff_advance.pk:04d}"
        journal = JournalHeader.objects.create(
            posting_date=staff_advance.advance_date,
            reference_number=reference,
            description=f"Staff advance disbursement — {reference}",
            status="Draft",
            source_module="staff_advance",
            source_document_id=staff_advance.pk,
            posted_by=actor,
        )
        JournalLine.objects.create(
            header=journal, account=recon,
            debit=amount, credit=ZERO,
            memo=f"Staff advance — {reference}",
        )
        JournalLine.objects.create(
            header=journal, account=cash_account,
            debit=ZERO, credit=amount,
            memo=f"Cash out — {reference}",
        )
        # FAIL CLOSED — see VendorAdvanceService.disburse for rationale.
        IPSASJournalService.post_journal(journal, actor)

        staff_advance.journal = journal
        staff_advance.status = "OUTSTANDING"
        staff_advance.updated_by = actor
        staff_advance.save(update_fields=["journal", "status", "updated_by", "updated_at"])
        return journal

    # ── Recovery (post: DR Expense / CR Recon) ────────────────────────

    @classmethod
    @transaction.atomic
    def record_recovery(
        cls, *,
        staff_advance,
        amount: Decimal,
        actor,
        posting_date=None,
        expense_account=None,
        notes: str = "",
    ) -> JournalHeader:
        """Record a recovery slice against an advance.

        DR  Expense (recovery)                    amount
        CR  Staff-Advance Special-GL Recon                amount

        Bumps ``recovered_amount`` under row lock and rolls status
        OUTSTANDING → PARTIAL → CLEARED. Returns the posted journal.
        """
        amount = Decimal(str(amount or 0))
        if amount <= ZERO:
            raise TransactionPostingError("Recovery amount must be > 0.")

        if staff_advance.journal_id is None:
            # A recovery on an advance that was never disbursed to the GL is
            # inconsistent — require the disbursement pin first.
            raise TransactionPostingError(
                f"Staff advance {staff_advance.pk} has no disbursement journal; "
                "recover it only after disbursing to the GL.",
            )

        outstanding = Decimal(str(staff_advance.amount or 0)) - Decimal(
            str(staff_advance.recovered_amount or 0)
        )
        if amount > outstanding:
            raise TransactionPostingError(
                f"Cannot recover {amount:,.2f} — only {outstanding:,.2f} "
                f"outstanding on advance {staff_advance.pk}.",
            )

        recon = cls.resolve_recon_account()
        if recon is None:
            raise TransactionPostingError(
                "No Staff-Advance Special-GL recon account configured.",
            )
        expense = cls._resolve_recovery_expense(expense_account)

        posting_date = posting_date or timezone.now().date()
        ref = staff_advance.reference or f"STAFFADV-{staff_advance.pk:04d}"
        # Unique reference per recovery slice (JournalHeader.reference_number
        # is uniquely indexed) — count prior recovery journals for this app.
        from accounting.models import JournalHeader as _JH
        n = _JH.objects.filter(
            source_module="staff_advance_recovery",
            source_document_id=staff_advance.pk,
        ).count()
        recovery_ref = f"REC-{ref}-{n + 1:02d}"

        journal = JournalHeader.objects.create(
            posting_date=posting_date,
            reference_number=recovery_ref,
            description=f"Staff advance recovery — {ref} ({notes})",
            status="Draft",
            source_module="staff_advance_recovery",
            source_document_id=staff_advance.pk,
            posted_by=actor,
        )
        JournalLine.objects.create(
            header=journal, account=expense,
            debit=amount, credit=ZERO,
            memo=f"Recover advance — {ref}",
        )
        JournalLine.objects.create(
            header=journal, account=recon,
            debit=ZERO, credit=amount,
            memo=f"Clear advance — {ref}",
        )
        IPSASJournalService.post_journal(journal, actor)

        locked = type(staff_advance).objects.select_for_update().get(pk=staff_advance.pk)
        locked.recovered_amount = quantize_currency(
            (locked.recovered_amount or ZERO) + amount,
        )
        locked.status = (
            "CLEARED"
            if locked.recovered_amount >= Decimal(str(locked.amount or 0))
            else "PARTIAL"
        )
        locked.updated_by = actor
        locked.save(update_fields=["recovered_amount", "status", "updated_by", "updated_at"])
        return journal

    # ── Imprest retirement (post: DR Expense / CR Recon) ──────────────

    @classmethod
    @transaction.atomic
    def retire_imprest(
        cls, *,
        retirement,
        actor,
        expense_account=None,
    ) -> JournalHeader:
        """Post the retirement journal for an ImprestRetirement and pin it.

        DR  Expense (retired amount)              amount
        CR  Recon / Bank account                         amount

        Returns the posted journal (also stored on ``retirement.journal``).
        Uses the imprest recon account when resolvable, else the explicit
        retirement GL; the credit leg is the advance/recon account.
        """
        amount = Decimal(str(retirement.amount or 0))
        if amount <= ZERO:
            raise TransactionPostingError("Retirement amount must be > 0.")
        if retirement.journal_id:
            raise TransactionPostingError(
                f"Imprest retirement {retirement.pk} already recorded "
                f"(journal {retirement.journal_id}).",
            )

        imprest = retirement.imprest
        # Reuse the same recon-account convention; if none, fail loudly.
        recon = cls.resolve_recon_account()
        if recon is None:
            raise TransactionPostingError(
                "No Staff-Advance Special-GL recon account configured.",
            )
        expense = cls._resolve_recovery_expense(expense_account)

        ref = imprest.reference or f"IMPREST-{imprest.pk:04d}"
        n = imprest.retirements.count()
        ret_ref = f"RET-{ref}-{n + 1:02d}"

        journal = JournalHeader.objects.create(
            posting_date=retirement.retirement_date,
            reference_number=ret_ref,
            description=f"Imprest retirement — {ref}",
            status="Draft",
            source_module="staff_advance_retirement",
            source_document_id=retirement.pk,
            posted_by=actor,
        )
        JournalLine.objects.create(
            header=journal, account=expense,
            debit=amount, credit=ZERO,
            memo=f"Retire imprest — {ref}",
        )
        JournalLine.objects.create(
            header=journal, account=recon,
            debit=ZERO, credit=amount,
            memo=f"Credit recon — {ref}",
        )
        IPSASJournalService.post_journal(journal, actor)

        retirement.journal = journal
        retirement.approved_by = actor
        retirement.approved_at = timezone.now()
        retirement.save(update_fields=["journal", "approved_by", "approved_at", "updated_at"])

        locked = type(imprest).objects.select_for_update().get(pk=imprest.pk)
        locked.retired_amount = quantize_currency(
            (locked.retired_amount or ZERO) + amount,
        )
        locked.save(update_fields=["retired_amount", "updated_at"])
        return journal
