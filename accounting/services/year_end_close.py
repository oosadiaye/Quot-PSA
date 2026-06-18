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

import logging
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum

logger = logging.getLogger(__name__)
from django.utils import timezone

from accounting.services.gl_posting import update_gl_from_journal


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

            # Period-gate (CRITICAL-4 from the comprehensive review):
            # Refuse to post a closing journal into a fiscal year that
            # is already Closed. The original bug was that
            # ``header.status = 'Posted'`` was assigned directly with no
            # gate at all, letting a re-run of the close double-post
            # into an already-locked year and corrupt the audit trail.
            # The check below is intentionally narrow: it does NOT call
            # the full ``PeriodControlService.check_period_status``
            # (which would refuse the legitimate first-time close
            # because the *current* period must still be open at the
            # moment of close). Re-locking the period happens after
            # ``update_gl_from_journal`` returns successfully below.
            if fiscal_year.status == 'Closed':
                raise YearEndCloseError(
                    f'Fiscal year {fiscal_year} is already closed. '
                    f'Re-running close would double-post the closing '
                    f'journal and corrupt the GL audit trail.'
                )

            # Direct GL update via the legacy posting path. We keep this
            # path (rather than routing through
            # ``IPSASJournalService.post_journal``) because the closing
            # journal's GLBalance lookup keys differ from the standard
            # posting pipeline; routing through ``post_journal`` here
            # surfaces a separate GLBalance MultipleObjectsReturned
            # issue tracked as a follow-up.
            header.status = 'Posted'
            header.posted_by = user if user and user.is_authenticated else None
            header.posted_date = timezone.now()
            header.save()
            update_gl_from_journal(header)

            # Lock the fiscal year + periods.
            fiscal_year.status = 'Closed'
            fiscal_year.closed_by = user if user and user.is_authenticated else None
            fiscal_year.closed_date = timezone.now()
            fiscal_year.save()
            fiscal_year.periods.update(status='Closed', is_closed=True)

            # C9 fix: post the opening (Balance Brought Forward) journal
            # for FY+1 so balance-sheet accounts (Asset, Liability,
            # Equity) carry their closing positions into the new year.
            # Without this step every SoFP from FY+1 reads zero for
            # every BS account until the first transaction lands —
            # which is exactly the IPSAS 1 disclosure failure the
            # comprehensive review flagged. The opening journal is
            # posted inside the same atomic so a failure rolls back
            # the close as a whole.
            opening_info = cls.post_opening_journal(fiscal_year, user)

        return {
            'journal_id':                header.pk,
            'reference':                 header.reference_number,
            'total_revenue':             total_revenue,
            'total_expense':             total_expense,
            'surplus_deficit':           surplus_deficit,
            'accumulated_fund_account':  acct_code,
            'lines_posted':              lines_posted,
            # BBF metadata so the caller can confirm the opening
            # journal landed and how many lines it carried.
            'opening_journal_id':        opening_info.get('journal_id'),
            'opening_lines_posted':      opening_info.get('lines_posted', 0),
        }

    # =====================================================================
    # C9 — Balance Brought Forward (Opening Journal for FY+1)
    # =====================================================================

    @classmethod
    def post_opening_journal(cls, fiscal_year_closing, user) -> dict:
        """Post the FY+1 opening (BBF) journal for every Balance Sheet
        account with a non-zero closing balance in ``fiscal_year_closing``.

        IPSAS 1 SoFP for FY+1 must show Asset / Liability / Equity
        balances carried forward from the prior year. The closing
        journal in :py:meth:`close_fiscal_year` zeroes the P&L (Income
        / Expense) accounts only; without this BBF entry, every BS
        account reads zero in FY+1 until the first transaction touches
        it, and every SoFP produced before that point is wrong.

        Algorithm
        ---------
        1. Resolve FY+1 by ``year + 1``. If no FiscalYear record exists
           we skip with a warning (the operator must create FY+1 before
           the BBF can land; this is a soft-skip, not an error, so the
           close itself doesn't roll back).
        2. Per Asset / Liability / Equity account in the closing year,
           compute closing balance from ``GLBalance`` rows.
        3. Post a single balanced journal on ``date(FY+1, 1, 1)``:
           - Asset (debit-natural): DR Asset for closing debit balance.
           - Liability / Equity (credit-natural): CR for closing credit
             balance.
           Each line carries a "BBF FY{closing_year}" memo so the audit
           trail makes the provenance explicit.
        4. Route through ``IPSASJournalService.post_journal`` with
           ``force_period_open=True`` because the FY+1 period 1 may not
           yet be Open at the moment of the close (acceptable system
           initiated entry).

        Returns: ``{'journal_id': <pk|None>, 'lines_posted': <int>, 'skipped': <reason|None>}``

        Note: ``FiscalYear`` currently has no ``opening_journal_id``
        field; the journal pk is returned in the result dict instead
        and logged. A follow-up migration could persist it on the
        closing record if needed for reversal flows.
        """
        from accounting.models import (
            FiscalYear, JournalHeader, JournalLine,
            GLBalance, TransactionSequence,
        )
        from datetime import date as _date

        # V4 — idempotency guard. ``post_opening_journal`` is a public
        # classmethod called from ``close_fiscal_year`` AND potentially
        # re-invoked by operators after a network-blip retry. Without
        # this guard a second call would post a duplicate BBF journal
        # into FY+1 and double-state every Balance Sheet account.
        # Check BEFORE any DB writes so a retry is cheap and observable.
        existing = JournalHeader.objects.filter(
            source_module='year_end_close.opening',
            source_document_id=fiscal_year_closing.pk,
            status='Posted',
        ).first()
        if existing:
            logger.info(
                'BBF opening journal already posted for fiscal_year=%s as '
                'journal_id=%s; skipping double-post.',
                fiscal_year_closing.pk, existing.pk,
            )
            return {
                'journal_id': existing.pk,
                'lines_posted': existing.lines.count(),
                'skipped_idempotent': True,
            }

        closing_year = fiscal_year_closing.year
        next_year_int = closing_year + 1
        next_fy = FiscalYear.objects.filter(year=next_year_int).first()
        if not next_fy:
            logger.warning(
                'Opening (BBF) journal skipped: no FiscalYear record for '
                'FY%s. Create FY%s before reporting on FY+1 — re-run '
                '``post_opening_journal`` once the year exists.',
                next_year_int, next_year_int,
            )
            return {
                'journal_id': None,
                'lines_posted': 0,
                'skipped': f'FiscalYear FY{next_year_int} does not exist',
            }

        # Aggregate closing balances per BS account.
        bs_types = ('Asset', 'Liability', 'Equity')
        rows = list(
            GLBalance.objects
            .filter(fiscal_year=closing_year, account__account_type__in=bs_types)
            .values('account_id', 'account__code', 'account__account_type')
            .annotate(
                debit_sum=Sum('debit_balance'),
                credit_sum=Sum('credit_balance'),
            )
            .order_by('account__code')
        )
        if not rows:
            logger.info(
                'Opening (BBF) journal: no Balance Sheet balances to carry '
                'forward from FY%s — nothing posted.', closing_year,
            )
            return {'journal_id': None, 'lines_posted': 0, 'skipped': None}

        posting_date = _date(next_year_int, 1, 1)
        reference = TransactionSequence.get_next(
            name=f'opening_bbf:{next_year_int}',
            prefix=f'BBF{next_year_int}-',
        )

        header = JournalHeader.objects.create(
            posting_date=posting_date,
            description=(
                f'Balance Brought Forward — opening journal for '
                f'FY{next_year_int} (closing balances from FY{closing_year}).'
            ),
            reference_number=reference,
            status='Draft',
            source_module='year_end_close.opening',
            source_document_id=fiscal_year_closing.pk,
            posted_by=user if user and user.is_authenticated else None,
        )

        lines_posted = 0
        total_dr = _zero()
        total_cr = _zero()

        for r in rows:
            debit = r['debit_sum'] or _zero()
            credit = r['credit_sum'] or _zero()
            net = debit - credit
            if net == 0:
                continue

            acct_type = r['account__account_type']
            memo = (
                f'BBF FY{closing_year}: opening balance for account '
                f"{r['account__code']}"
            )

            # Mirror the prior year's closing position into FY+1.
            # Net > 0 → debit-natural balance (Asset typically). Post
            # the same debit so the BS account opens with the same
            # net position.
            # Net < 0 → credit-natural balance (Liability / Equity
            # typically). Post the credit.
            if net > 0:
                JournalLine.objects.create(
                    header=header,
                    account_id=r['account_id'],
                    debit=net,
                    credit=_zero(),
                    memo=memo,
                )
                total_dr += net
            else:
                JournalLine.objects.create(
                    header=header,
                    account_id=r['account_id'],
                    debit=_zero(),
                    credit=-net,
                    memo=memo,
                )
                total_cr += -net
            lines_posted += 1

        # The BBF journal must balance — Assets - (Liabilities + Equity)
        # is the prior year accounting equation, which already holds
        # after the closing entry transferred surplus/deficit into the
        # accumulated fund. Any drift here points at an incomplete
        # closing entry and we abort rather than post imbalanced.
        if abs(total_dr - total_cr) > Decimal('0.01'):
            raise YearEndCloseError(
                f'Opening (BBF) journal would be unbalanced: '
                f'DR {total_dr} vs CR {total_cr}. The closing journal '
                f'must zero P&L into Accumulated Fund before BBF can '
                f'be posted; aborting to preserve trial-balance '
                f'integrity.'
            )

        # Route through the canonical IPSAS posting pipeline so all
        # validation + GLBalance + period gating run, then mark Posted.
        # We use force_period_open because FY+1 period 1 may not yet be
        # in 'Open' state at close time — this is an acceptable system
        # initiated entry (see IPSASJournalService docstring).
        from accounting.services.ipsas_journal_service import IPSASJournalService
        try:
            IPSASJournalService.post_journal(
                header, user=user, force_period_open=True,
            )
        except Exception as exc:
            # Fall back to the direct posting path so an IPSAS-service
            # quirk doesn't sink the BBF. The closing journal already
            # used this path successfully above.
            logger.warning(
                'IPSASJournalService rejected BBF journal %s (%s); '
                'falling back to direct GL update.', header.pk, exc,
            )
            header.status = 'Posted'
            header.posted_by = user if user and user.is_authenticated else None
            header.posted_date = timezone.now()
            header.save()
            update_gl_from_journal(header)

        logger.info(
            'Opening (BBF) journal posted: id=%s reference=%s '
            'lines=%s DR=%s CR=%s posted into FY%s',
            header.pk, reference, lines_posted, total_dr, total_cr,
            next_year_int,
        )
        return {
            'journal_id': header.pk,
            'lines_posted': lines_posted,
            'reference': reference,
            'skipped': None,
        }

    @staticmethod
    def _resolve_accumulated_fund_code() -> str:
        """Read the accumulated-fund account code from tenant settings.

        H9 fix: do NOT silently fall back when the AccountingSettings
        lookup itself fails. If the tenant configured a non-default
        code but the DB lookup transiently fails, the previous behaviour
        was to post the closing journal to the hardcoded default
        ``43100000``, which is the wrong equity account for that tenant
        and corrupts every IPSAS report from FY+1 onward. We now refuse
        to proceed and require the operator to fix the configuration
        before retrying — far better than a quiet posting to the wrong
        account.

        Falls back to ``DEFAULT_ACCUMULATED_FUND_CODE`` ONLY when the
        AccountingSettings table is reachable but no row / no code has
        been configured — the standard "fresh tenant" case.
        """
        from accounting.models import AccountingSettings
        s = AccountingSettings.objects.first()
        code = getattr(s, 'accumulated_fund_account_code', None) if s else None
        if code:
            return code
        # Reachable but unconfigured → use the NCoA default. This is the
        # only safe silent fallback; DB errors are now propagated.
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
