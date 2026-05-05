"""
Base Posting Service — accounting domain.

Contains the shared exception class, the get_gl_account() utility function,
and BasePostingService with infrastructure-level static methods used by all
domain posting services.
"""

import logging
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.conf import settings
from accounting.models import (
    JournalHeader, Account, GLBalance
)

logger = logging.getLogger(__name__)


class TransactionPostingError(Exception):
    """Custom exception for transaction posting errors"""
    pass


def get_gl_account(account_key, account_type=None, fallback_name_contains=None):
    """
    Get a GL account using configured defaults or fallback to name search.

    Args:
        account_key: Key in DEFAULT_GL_ACCOUNTS settings (e.g., 'CASH_ACCOUNT')
        account_type: Optional account_type filter
        fallback_name_contains: Fallback search term if not in settings

    Returns:
        Account instance or None
    """
    default_gl = getattr(settings, 'DEFAULT_GL_ACCOUNTS', {})

    account_code = default_gl.get(account_key)
    if account_code:
        account = Account.objects.filter(code=account_code).first()
        if account:
            return account

    if fallback_name_contains and account_type:
        return Account.objects.filter(
            account_type=account_type,
            name__icontains=fallback_name_contains
        ).first()
    elif fallback_name_contains:
        return Account.objects.filter(
            name__icontains=fallback_name_contains
        ).first()

    return None


class BasePostingService:
    """
    Shared infrastructure methods used by all domain posting services.
    """

    @staticmethod
    def _check_duplicate_posting(reference_number):
        """Check if a transaction has already been posted to prevent double-posting."""
        if JournalHeader.objects.filter(
            reference_number=reference_number,
            status='Posted'
        ).exists():
            raise TransactionPostingError(
                f"Transaction '{reference_number}' has already been posted to the GL."
            )

    @staticmethod
    def _validate_fiscal_period(posting_date, user=None):
        """Validate that the fiscal period is open for posting (S1-06).

        Strict mode: if NO fiscal period covers the posting_date, posting
        is rejected. The previous "no periods configured → silently allow"
        bypass is removed — a production tenant without period setup is
        misconfigured and must not be allowed to post.

        Delegates to :class:`PeriodControlService.can_post_to_period` so
        user-level override grants (via ``PeriodAccess``) are honoured
        consistently across every posting path.
        """
        from accounting.services.period_control import PeriodControlService

        allowed, message = PeriodControlService.can_post_to_period(
            posting_date, user=user,
        )
        if not allowed:
            raise TransactionPostingError(
                f"Posting to {posting_date} is not allowed: {message}"
            )

    @staticmethod
    def assert_balanced(journal):
        """Pure double-entry check — raises if SUM(DR) != SUM(CR).

        No side effects. This is the chokepoint invariant every
        GL-writer (``update_gl_from_journal``,
        ``BasePostingService._update_gl_balances``,
        ``IPSASJournalService._update_gl_balances``) calls before
        touching ``GLBalance``. It guarantees that no posting path —
        AR Invoice, AR Receipt, AP Invoice, AP Credit Memo, AP
        Payment, GRN, Invoice Verification, IPC Accrual, Vendor
        Advance, Asset Disposal, Manual JE, Bank Transfer, Revenue
        Collection — can produce an unbalanced GL.

        Differs from ``_validate_journal_balanced`` (which also runs
        asset capitalisation as a side-effect) in being a pure
        invariant assertion suitable for unconditional use inside
        the low-level writer.
        """
        agg = journal.lines.aggregate(
            d=Sum('debit'), c=Sum('credit'),
        )
        total_debit = agg['d'] or Decimal('0.00')
        total_credit = agg['c'] or Decimal('0.00')
        if total_debit != total_credit:
            raise TransactionPostingError(
                f"Journal {journal.reference_number} is unbalanced. "
                f"Debits: {total_debit}, Credits: {total_credit}, "
                f"Difference: {total_debit - total_credit}. "
                f"Double-entry violation — every posting must have "
                f"SUM(debits) == SUM(credits)."
            )

    @staticmethod
    def _validate_journal_balanced(journal):
        """Ensure journal has >= 2 lines and debits equal credits.

        Asset auto-capitalisation runs HERE before the balance check —
        every posting source (Journal, AP Invoice, GRN, PO, PV, Asset
        Disposal, …) flows through this method, so capitalisation is
        applied uniformly without per-source duplication. The contra +
        recon lines added by the service balance to zero on their own
        (DR recon = CR clearing = original debit), so the balance
        invariant still holds after capitalisation.
        """
        # Apply SAP-style auto-capitalisation. Idempotent — already-
        # capitalised lines (carrying _skip_auto_capitalize) are skipped.
        # Failures (missing category, missing cost account) raise
        # ValidationError, which the caller's @transaction.atomic
        # rolls back atomically.
        try:
            from accounting.services.asset_capitalization import apply_asset_capitalization
            apply_asset_capitalization(journal)
        except Exception as exc:  # noqa: BLE001
            # Surface as a posting error so the caller's standard
            # error path translates it for the UI.
            raise TransactionPostingError(
                f"Asset auto-capitalisation failed for {journal.reference_number}: {exc}"
            ) from exc

        line_count = journal.lines.count()
        if line_count < 2:
            raise TransactionPostingError(
                f"Journal {journal.reference_number} must have at least 2 lines "
                f"(has {line_count}). Double-entry requires both debit and credit sides."
            )

        total_debit = journal.lines.aggregate(
            total=Sum('debit')
        )['total'] or Decimal('0.00')
        total_credit = journal.lines.aggregate(
            total=Sum('credit')
        )['total'] or Decimal('0.00')
        if total_debit != total_credit:
            raise TransactionPostingError(
                f"Journal {journal.reference_number} is unbalanced. "
                f"Debits: {total_debit}, Credits: {total_credit}. "
                f"This may indicate a missing GL account configuration."
            )

    @staticmethod
    @transaction.atomic
    def _update_gl_balances(journal):
        """
        Update GL Balance records after posting a journal entry.

        Args:
            journal: JournalHeader instance

        Raises:
            TransactionPostingError if the journal isn't balanced
            (SUM(debit) != SUM(credit)). Mandatory double-entry
            invariant — see BasePostingService.assert_balanced.
        """
        # Mandatory double-entry assertion before any GL state mutates.
        BasePostingService.assert_balanced(journal)

        fiscal_year = journal.posting_date.year
        period = journal.posting_date.month
        # S3-05 — carry MDA dimension onto each GLBalance row so budget
        # execution reports can attribute actuals to the correct MDA.
        # The legacy per-line ``cost_center`` override has been removed
        # from this project; header MDA is the single source.
        j_mda_header = journal.mda

        for line in journal.lines.all():
            line_mda = j_mda_header
            # Try to get existing balance
            balance, created = GLBalance.objects.get_or_create(
                account=line.account,
                fund=journal.fund,
                function=journal.function,
                program=journal.program,
                geo=journal.geo,
                mda=line_mda,
                fiscal_year=fiscal_year,
                period=period,
                defaults={
                    'debit_balance': Decimal('0.00'),
                    'credit_balance': Decimal('0.00')
                }
            )

            # Atomic increment using F() expressions — no race condition
            from django.db.models import F
            GLBalance.objects.filter(pk=balance.pk).update(
                debit_balance=F('debit_balance') + line.debit,
                credit_balance=F('credit_balance') + line.credit
            )

        # Flip the journal to ``Posted`` if it isn't already.
        # Procurement callers (PO post, GRN post, Invoice Match post,
        # vendor return, etc.) don't flip status themselves — and
        # leaving the journal in Draft after GLBalance has been
        # incremented makes Trial Balance / Income Statement (which
        # filter ``header__status='Posted'``) miss these journals
        # while the IPSAS reports (which read from GLBalance) see
        # them. The two surfaces would disagree. Flipping here
        # finalises the contract.
        if journal.status != 'Posted':
            journal.status = 'Posted'
            journal.save(update_fields=['status'], _allow_status_change=True)

        # Bust the IPSAS report cache so every Financial Position /
        # Performance / Cash Flow / Notes / Budget Performance /
        # Functional / Programme / Geographic / Fund / Revenue
        # Performance report drops its cached entry. Mirrors the
        # invalidation hooks in ``gl_posting.update_gl_from_journal``
        # and ``IPSASJournalService._update_gl_balances`` — every
        # GLBalance writer must trigger this so reports stay live
        # regardless of which posting path ran.
        try:
            from accounting.services.report_cache import invalidate_period_reports
            invalidate_period_reports(fiscal_year=fiscal_year)
        except Exception:  # noqa: BLE001 — cache invalidation is best-effort
            pass
