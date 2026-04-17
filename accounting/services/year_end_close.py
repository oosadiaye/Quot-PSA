"""
Year-End Close Service — S3-06 / S1-07 deferred
================================================

Closes a fiscal year by:

1. Aggregating every Revenue and Expense account's net balance for the year.
2. Posting a closing journal entry that zeroes all P&L nominal accounts
   and credits/debits the net result to the Accumulated Surplus/Deficit
   equity account.
3. Locking the FiscalYear and all its periods to status='Closed'.

Without this step, nominal accounts carry their balance into the new
fiscal year and every IPSAS 1 statement produced thereafter is wrong.

The target equity account is read from ``AccountingSettings`` (key:
``accumulated_fund_account_code``). When the setting is missing, we
default to NCoA 43100000 ("General Reserve Fund") — the Nigerian NCoA
standard code for accumulated surplus.
"""
from __future__ import annotations

from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone


class YearEndCloseError(Exception):
    """Raised when the year cannot be closed (missing accounts, unbalanced,
    already closed, pending journals, etc.)."""


# Default NCoA code for Accumulated Surplus / Deficit if tenant-specific
# setting is not configured.
DEFAULT_ACCUMULATED_FUND_CODE = '43100000'


class YearEndCloseService:
    """Orchestrates the year-end closing journal + FiscalYear lock."""

    @classmethod
    def close_fiscal_year(cls, fiscal_year, user, force: bool = False):
        """Close ``fiscal_year`` atomically.

        Returns a dict::

            {
              'journal_id': int,
              'reference':  str,
              'total_revenue':   Decimal,
              'total_expense':   Decimal,
              'surplus_deficit': Decimal,
              'accumulated_fund_account': str,
              'lines_posted': int,
            }

        Raises :class:`YearEndCloseError` when blocked.
        """
        from accounting.models import (
            JournalHeader, JournalLine, Account, TransactionSequence,
        )

        if fiscal_year.status == 'Closed':
            raise YearEndCloseError(
                f'Fiscal year {fiscal_year.year} is already Closed.'
            )

        # Pre-flight: refuse if any Draft/Pending journals still exist
        # in the year, unless the caller explicitly forces.
        pending = JournalHeader.objects.filter(
            posting_date__year=fiscal_year.year,
            status__in=('Draft', 'Pending', 'Approved'),
        ).count()
        if pending and not force:
            raise YearEndCloseError(
                f'{pending} journal entries are still Draft/Pending/Approved '
                f'for FY {fiscal_year.year}. Post or reject them first, or '
                f'pass force=True to proceed.'
            )

        # Resolve the Accumulated Surplus/Deficit account.
        acct_code = cls._resolve_accumulated_fund_code()
        acc_fund_account = Account.objects.filter(code=acct_code).first()
        if not acc_fund_account:
            raise YearEndCloseError(
                f'Accumulated Surplus/Deficit account with code {acct_code} '
                f'not found in the chart of accounts. Configure '
                f'AccountingSettings.accumulated_fund_account_code or '
                f'create the account first.'
            )

        # ── Aggregate Revenue + Expense balances for the year ─────────
        revenue_totals = cls._aggregate_nominals(
            fiscal_year.year, ('Income', 'Revenue'),
        )
        expense_totals = cls._aggregate_nominals(
            fiscal_year.year, ('Expense', 'Expenditure'),
        )

        if not revenue_totals and not expense_totals:
            raise YearEndCloseError(
                f'No Revenue or Expense balances found for FY '
                f'{fiscal_year.year}. Nothing to close.'
            )

        # ── Build the closing journal ─────────────────────────────────
        from datetime import date as _date
        posting_date = _date(fiscal_year.year, 12, 31)
        reference = TransactionSequence.get_next(
            name=f'year_close:{fiscal_year.year}',
            prefix=f'YEC{fiscal_year.year}-',
        )

        total_revenue = _zero()
        total_expense = _zero()

        with transaction.atomic():
            header = JournalHeader.objects.create(
                posting_date=posting_date,
                description=(
                    f'Year-End Close FY{fiscal_year.year}: zero '
                    f'nominal accounts, transfer net surplus/deficit '
                    f'to Accumulated Fund ({acct_code}).'
                ),
                reference_number=reference,
                status='Draft',         # final flip to Posted after lines build
                source_module='year_end_close',
                source_document_id=fiscal_year.pk,
                posted_by=user if user and user.is_authenticated else None,
            )

            lines_posted = 0

            # Zero-out Revenue accounts: revenue normal-credit balance,
            # so debit them to clear.
            for rec in revenue_totals:
                net = (rec['credit_sum'] or _zero()) - (rec['debit_sum'] or _zero())
                if net == 0:
                    continue
                JournalLine.objects.create(
                    header=header,
                    account_id=rec['account_id'],
                    debit=net if net > 0 else _zero(),
                    credit=-net if net < 0 else _zero(),
                    memo=f'Close FY{fiscal_year.year} Revenue → Accumulated Fund',
                )
                total_revenue += net
                lines_posted += 1

            # Zero-out Expense accounts: expense normal-debit balance,
            # so credit them to clear.
            for rec in expense_totals:
                net = (rec['debit_sum'] or _zero()) - (rec['credit_sum'] or _zero())
                if net == 0:
                    continue
                JournalLine.objects.create(
                    header=header,
                    account_id=rec['account_id'],
                    debit=-net if net < 0 else _zero(),
                    credit=net if net > 0 else _zero(),
                    memo=f'Close FY{fiscal_year.year} Expense → Accumulated Fund',
                )
                total_expense += net
                lines_posted += 1

            # Balancing line to Accumulated Surplus/Deficit.
            surplus_deficit = total_revenue - total_expense
            # Net surplus (revenue > expense): CREDIT accumulated fund.
            # Net deficit (expense > revenue): DEBIT accumulated fund.
            if surplus_deficit > 0:
                JournalLine.objects.create(
                    header=header,
                    account=acc_fund_account,
                    debit=_zero(),
                    credit=surplus_deficit,
                    memo=f'Net surplus transferred to Accumulated Fund FY{fiscal_year.year}',
                )
                lines_posted += 1
            elif surplus_deficit < 0:
                JournalLine.objects.create(
                    header=header,
                    account=acc_fund_account,
                    debit=-surplus_deficit,
                    credit=_zero(),
                    memo=f'Net deficit transferred to Accumulated Fund FY{fiscal_year.year}',
                )
                lines_posted += 1

            # Balance check before flipping to Posted. The DB-level
            # CheckConstraints + the service-level check form a
            # belt-and-suspenders defence.
            agg = header.lines.aggregate(d=Sum('debit'), c=Sum('credit'))
            total_dr = agg['d'] or _zero()
            total_cr = agg['c'] or _zero()
            if abs(total_dr - total_cr) > Decimal('0.01'):
                raise YearEndCloseError(
                    f'Closing journal is unbalanced: '
                    f'DR {total_dr} vs CR {total_cr}. Aborted.'
                )

            # Flip status to Posted — this triggers the GLBalance update
            # on the new fiscal year the same way a normal journal post
            # would.
            header.status = 'Posted'
            header.posted_at = timezone.now()
            header.save(update_fields=['status', 'posted_at'])

            # Update GLBalance so the P&L accounts show zero for the
            # year going forward.
            from accounting.services.gl_posting import update_gl_from_journal
            update_gl_from_journal(header)

            # Lock the fiscal year + periods.
            fiscal_year.status = 'Closed'
            fiscal_year.closed_by = user if user and user.is_authenticated else None
            fiscal_year.closed_date = timezone.now()
            fiscal_year.save()
            fiscal_year.periods.update(status='Closed', is_closed=True)

        return {
            'journal_id':                header.pk,
            'reference':                 header.reference_number,
            'total_revenue':             total_revenue,
            'total_expense':             total_expense,
            'surplus_deficit':           surplus_deficit,
            'accumulated_fund_account':  acct_code,
            'lines_posted':              lines_posted,
        }

    @staticmethod
    def _resolve_accumulated_fund_code() -> str:
        """Read the accumulated-fund account code from tenant settings."""
        try:
            from accounting.models import AccountingSettings
            s = AccountingSettings.objects.first()
            code = getattr(s, 'accumulated_fund_account_code', None) if s else None
            if code:
                return code
        except Exception:
            pass
        return DEFAULT_ACCUMULATED_FUND_CODE

    @staticmethod
    def _aggregate_nominals(fiscal_year: int, account_types: tuple) -> list:
        """Sum debit/credit per account for the given year + types."""
        from accounting.models import GLBalance
        return list(
            GLBalance.objects
            .filter(
                fiscal_year=fiscal_year,
                account__account_type__in=account_types,
            )
            .values('account_id', 'account__code', 'account__name')
            .annotate(
                debit_sum=Sum('debit_balance'),
                credit_sum=Sum('credit_balance'),
            )
            .order_by('account__code')
        )


def _zero() -> Decimal:
    return Decimal('0')
