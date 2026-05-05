"""
Period-close and year-end-close services.

The Statement of Financial Position only balances when revenue/expense
accounts (which carry balances during the year) are transferred to the
Accumulated Fund (NCoA 43xx, credit-normal net-assets line). Without a
close entry, the SoFP `balance_check` reports ``is_balanced=False``
because Assets includes all the cash brought in by revenue, but
Liabilities + Net Assets hasn't absorbed the surplus.

This module provides:

* :func:`close_fiscal_year` — posts a single balanced journal that
  zeros every revenue (11xx–14xx) and expense (21xx–25xx) GLBalance
  row for the year and credits (or debits, if deficit) the configured
  Accumulated Fund account (usually 43100000). After this runs, the
  SoFP balance-check passes.

* :func:`preview_close` — dry-run variant: returns the computed
  journal lines without writing anything, so an Accountant General
  can inspect the close entry before executing.

Both are idempotent via a ``PERIOD-CLOSE:YYYY`` reference number
stamp. Re-running after a successful close returns ``already_closed``
without side effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


REV_PREFIXES = ('11', '12', '13', '14')
EXP_PREFIXES = ('21', '22', '23', '24', '25')


@dataclass
class CloseResult:
    fiscal_year: int
    already_closed: bool = False
    journal_id: Optional[int] = None
    journal_reference: str = ''
    total_revenue: Decimal = field(default_factory=lambda: Decimal('0'))
    total_expense: Decimal = field(default_factory=lambda: Decimal('0'))
    surplus_deficit: Decimal = field(default_factory=lambda: Decimal('0'))
    accumulated_fund_code: str = ''
    line_count: int = 0


class PeriodCloseError(Exception):
    """Raised when the close cannot proceed (missing config / bad state)."""


def preview_close(fiscal_year: int) -> dict:
    """Return what :func:`close_fiscal_year` would post, without writing.

    Accountant General can review the amounts before authorising the
    post. Structure mirrors the journal-line list the real close writes.
    """
    return _build_close_plan(fiscal_year, dry_run=True)


def close_fiscal_year(fiscal_year: int, *, user=None) -> CloseResult:
    """Post the fiscal-year close journal. Idempotent by reference stamp.

    Raises :class:`PeriodCloseError` if the configured Accumulated Fund
    account is missing from the chart of accounts.
    """
    plan = _build_close_plan(fiscal_year, dry_run=False)
    if plan.get('already_closed'):
        return CloseResult(
            fiscal_year=fiscal_year,
            already_closed=True,
            journal_reference=plan['reference'],
        )

    from django.db import transaction
    from django.utils import timezone
    from accounting.models import JournalHeader, JournalLine, GLBalance
    from django.db.models import F
    from accounting.services.base_posting import BasePostingService
    from accounting.services.report_cache import invalidate_period_reports

    with transaction.atomic():
        header = JournalHeader.objects.create(
            posting_date=date(fiscal_year, 12, 31),
            description=(
                f'Fiscal-year close FY {fiscal_year} — '
                f'transfer surplus/deficit to Accumulated Fund. '
                f'Net surplus: NGN {plan["surplus_deficit"]:,.2f}.'
            ),
            reference_number=plan['reference'],
            status='Posted',
            posted_at=timezone.now(),
            posted_by=user if (user and getattr(user, 'is_authenticated', False)) else None,
            source_module='period_close',
        )

        lines_to_insert: list[JournalLine] = []
        for line in plan['lines']:
            lines_to_insert.append(JournalLine(
                header=header,
                account=line['account'],
                debit=line['debit'],
                credit=line['credit'],
                memo=line['memo'],
            ))
        JournalLine.objects.bulk_create(lines_to_insert)

        # H1 fix: enforce the same chokepoint every other GL writer
        # respects. The plan is balanced by construction, but a future
        # change to ``_build_close_plan`` (e.g. rounding on surplus
        # calc) could silently emit unbalanced lines and corrupt
        # GLBalance. Failing fast here surfaces the bug at close time.
        BasePostingService.assert_balanced(header)

        # Update GLBalance so the SoFP sees the transferred balance.
        # For revenue/expense accounts we post the inverse of their
        # accrued balance — zeroing them. For Accumulated Fund we
        # credit (surplus) or debit (deficit) the net.
        for line in plan['lines']:
            bal, _ = GLBalance.objects.get_or_create(
                account=line['account'],
                fund=None, function=None, program=None, geo=None, mda=None,
                fiscal_year=fiscal_year, period=12,
                defaults={'debit_balance': Decimal('0'),
                          'credit_balance': Decimal('0')},
            )
            GLBalance.objects.filter(pk=bal.pk).update(
                debit_balance=F('debit_balance') + line['debit'],
                credit_balance=F('credit_balance') + line['credit'],
            )

        # H1 fix: bump the report-generation counter so cached IPSAS
        # / Trial Balance reads pick up the post-close picture
        # immediately instead of waiting for the 600s TTL to expire.
        invalidate_period_reports(fiscal_year=fiscal_year)

    return CloseResult(
        fiscal_year=fiscal_year,
        already_closed=False,
        journal_id=header.pk,
        journal_reference=header.reference_number,
        total_revenue=plan['total_revenue'],
        total_expense=plan['total_expense'],
        surplus_deficit=plan['surplus_deficit'],
        accumulated_fund_code=plan['accumulated_fund_code'],
        line_count=len(plan['lines']),
    )


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _build_close_plan(fiscal_year: int, *, dry_run: bool) -> dict:
    """Shared planner used by both preview and live close.

    Returns a dict with:
      * reference            — stable ``PERIOD-CLOSE:YYYY`` stamp
      * already_closed       — True if a header with that ref exists
      * lines                — list of {account, debit, credit, memo}
      * total_revenue        — sum of closing debits to revenue accounts
      * total_expense        — sum of closing credits to expense accounts
      * surplus_deficit      — net transferred to Accumulated Fund
      * accumulated_fund_code — code used for the balancing line
    """
    from accounting.models import (
        AccountingSettings, Account, GLBalance, JournalHeader,
    )
    from django.db.models import Q, Sum

    reference = f'PERIOD-CLOSE:{fiscal_year}'

    # Idempotency check.
    if JournalHeader.objects.filter(reference_number=reference).exists():
        return {
            'reference':       reference,
            'already_closed':  True,
            'lines':           [],
            'total_revenue':   Decimal('0'),
            'total_expense':   Decimal('0'),
            'surplus_deficit': Decimal('0'),
            'accumulated_fund_code': '',
        }

    # Resolve Accumulated Fund account.
    settings_obj = AccountingSettings.objects.first()
    code = _resolve_setting(
        settings_obj, 'accumulated_fund_account_code', '43100000',
    )
    af_account = Account.objects.filter(code=code, is_active=True).first()
    if af_account is None:
        raise PeriodCloseError(
            f'Accumulated Fund account {code!r} not found or inactive. '
            'Configure AccountingSettings.accumulated_fund_account_code '
            'or activate the referenced NCoA account.'
        )

    # Pull the aggregate balance per account for the FY (Σ across periods).
    rev_filter = Q()
    for p in REV_PREFIXES:
        rev_filter |= Q(account__code__startswith=p)
    exp_filter = Q()
    for p in EXP_PREFIXES:
        exp_filter |= Q(account__code__startswith=p)

    rev_rows = list(
        GLBalance.objects
        .filter(fiscal_year=fiscal_year)
        .filter(rev_filter)
        .values('account_id', 'account__code', 'account__name')
        .annotate(dr=Sum('debit_balance'), cr=Sum('credit_balance'))
    )
    exp_rows = list(
        GLBalance.objects
        .filter(fiscal_year=fiscal_year)
        .filter(exp_filter)
        .values('account_id', 'account__code', 'account__name')
        .annotate(dr=Sum('debit_balance'), cr=Sum('credit_balance'))
    )

    lines: list[dict] = []
    total_revenue = Decimal('0')
    total_expense = Decimal('0')
    accounts_by_id: dict[int, Account] = {}

    # Revenue accounts are credit-normal. Closing entry DRs the net
    # credit balance (= credit − debit) to zero it, then the plug goes
    # to Accumulated Fund as a CR.
    for r in rev_rows:
        net_credit = (r['cr'] or Decimal('0')) - (r['dr'] or Decimal('0'))
        if net_credit == 0:
            continue
        acc = _get_account(accounts_by_id, r['account_id'])
        lines.append({
            'account': acc,
            'debit':   net_credit if net_credit > 0 else Decimal('0'),
            'credit':  (-net_credit) if net_credit < 0 else Decimal('0'),
            'memo':    f'Close revenue account {r["account__code"]} for FY {fiscal_year}',
        })
        total_revenue += net_credit

    # Expense accounts are debit-normal. Closing entry CRs the net
    # debit balance to zero it.
    for e in exp_rows:
        net_debit = (e['dr'] or Decimal('0')) - (e['cr'] or Decimal('0'))
        if net_debit == 0:
            continue
        acc = _get_account(accounts_by_id, e['account_id'])
        lines.append({
            'account': acc,
            'debit':   (-net_debit) if net_debit < 0 else Decimal('0'),
            'credit':  net_debit if net_debit > 0 else Decimal('0'),
            'memo':    f'Close expense account {e["account__code"]} for FY {fiscal_year}',
        })
        total_expense += net_debit

    surplus_deficit = total_revenue - total_expense

    # Balancing line to Accumulated Fund.
    # Surplus (revenue > expense) → CR Accumulated Fund.
    # Deficit                     → DR Accumulated Fund.
    if surplus_deficit > 0:
        lines.append({
            'account': af_account,
            'debit':   Decimal('0'),
            'credit':  surplus_deficit,
            'memo':    f'Transfer FY {fiscal_year} surplus to Accumulated Fund',
        })
    elif surplus_deficit < 0:
        lines.append({
            'account': af_account,
            'debit':   -surplus_deficit,
            'credit':  Decimal('0'),
            'memo':    f'Absorb FY {fiscal_year} deficit against Accumulated Fund',
        })
    # If exactly zero (unusual), no balancing line needed.

    return {
        'reference':             reference,
        'already_closed':        False,
        'lines':                 lines,
        'total_revenue':         total_revenue,
        'total_expense':         total_expense,
        'surplus_deficit':       surplus_deficit,
        'accumulated_fund_code': af_account.code,
    }


def _get_account(cache: dict, account_id):
    from accounting.models import Account
    if account_id not in cache:
        cache[account_id] = Account.objects.get(pk=account_id)
    return cache[account_id]


def _resolve_setting(settings_obj, attr: str, default: str) -> str:
    if settings_obj is None:
        return default
    val = getattr(settings_obj, attr, None)
    if val is None:
        return default
    stripped = str(val).strip()
    return stripped or default
