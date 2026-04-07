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
    JournalHeader, JournalLine, Account, GLBalance,
    Fund, Function, Program, Geo, MDA
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
    def _validate_fiscal_period(posting_date):
        """Validate that the fiscal period is open for posting.

        If fiscal periods have been configured (i.e. at least one period
        exists in the system) but *none* covers the posting_date, we
        reject the transaction — the date falls outside any defined
        period.  If no periods are configured at all we silently allow
        posting so the system remains usable before period setup.
        """
        from accounting.models import FiscalPeriod

        period = FiscalPeriod.objects.filter(
            start_date__lte=posting_date,
            end_date__gte=posting_date,
        ).first()

        if period is not None:
            if period.status in ('Closed', 'Locked'):
                raise TransactionPostingError(
                    f"Fiscal period {period} is {period.status}. "
                    f"Cannot post to a closed/locked period."
                )
            return  # period exists and is open — OK

        # No matching period.  If periods exist at all, the date is invalid.
        if FiscalPeriod.objects.exists():
            raise TransactionPostingError(
                f"No open fiscal period found for date {posting_date}. "
                f"Please ensure a fiscal period covering this date exists and is open."
            )

    @staticmethod
    def _validate_journal_balanced(journal):
        """Ensure journal has >= 2 lines and debits equal credits."""
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
        """
        fiscal_year = journal.posting_date.year
        period = journal.posting_date.month

        for line in journal.lines.all():
            # Try to get existing balance
            balance, created = GLBalance.objects.get_or_create(
                account=line.account,
                fund=journal.fund,
                function=journal.function,
                program=journal.program,
                geo=journal.geo,
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
