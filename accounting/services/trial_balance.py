"""Trial Balance Service

Generates trial balance reports for verifying debit/credit equality.
"""
from datetime import date
from decimal import Decimal
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from django.db.models import Sum
from accounting.models import (
    Account, GLBalance, JournalHeader, FiscalPeriod
)


@dataclass
class TrialBalanceAccount:
    """Account line in trial balance."""
    account_code: str
    account_name: str
    account_type: str
    debit_balance: Decimal
    credit_balance: Decimal
    cost_center: Optional[str]
    currency_code: str


@dataclass
class TrialBalanceResult:
    """Complete trial balance report."""
    fiscal_year: int
    period: int
    as_of_date: date
    period_start: date
    period_end: date

    total_debit: Decimal
    total_credit: Decimal
    difference: Decimal
    is_balanced: bool

    accounts: List[Dict[str, Any]]

    asset_total: Decimal
    liability_total: Decimal
    equity_total: Decimal
    income_total: Decimal
    expense_total: Decimal

    currency_code: str


class TrialBalanceService:
    """Service for generating trial balance reports."""

    @classmethod
    def generate_trial_balance(
        cls,
        fiscal_year: int,
        period: int,
        as_of_date: date = None,
        cost_center_id: int = None,
        account_type: str = None,
        include_zero_balances: bool = False,
        currency_code: str = None
    ) -> TrialBalanceResult:
        """
        Generate trial balance for a specific period.

        Args:
            fiscal_year: Fiscal year
            period: Period number (1-12)
            as_of_date: Optional date for point-in-time balance
            cost_center_id: Optional cost center filter
            account_type: Optional account type filter
            include_zero_balances: Include accounts with zero balance
            currency_code: Currency code (defaults to tenant base currency)

        Returns:
            TrialBalanceResult with all account balances
        """
        if currency_code is None:
            from accounting.utils import get_base_currency_code
            currency_code = get_base_currency_code()

        if as_of_date is None:
            as_of_date = date.today()

        fiscal_period = FiscalPeriod.objects.filter(
            fiscal_year=fiscal_year,
            period=period
        ).first()

        period_start = fiscal_period.start_date if fiscal_period else date(fiscal_year, 1, 1)
        period_end = fiscal_period.end_date if fiscal_period else date(fiscal_year, 12, 31)

        accounts = Account.objects.filter(is_active=True)
        if account_type:
            accounts = accounts.filter(account_type=account_type)

        trial_balances = []
        total_debit = Decimal('0')
        total_credit = Decimal('0')

        asset_total = Decimal('0')
        liability_total = Decimal('0')
        equity_total = Decimal('0')
        income_total = Decimal('0')
        expense_total = Decimal('0')

        for account in accounts:
            if cost_center_id:
                balances = GLBalance.objects.filter(
                    account=account,
                    fiscal_year=fiscal_year,
                    period=period,
                    cost_center_id=cost_center_id
                )
            else:
                balances = GLBalance.objects.filter(
                    account=account,
                    fiscal_year=fiscal_year,
                    period=period
                )

            balance_sum = balances.aggregate(
                total_debit=Sum('debit_amount'),
                total_credit=Sum('credit_amount')
            )

            debit = balance_sum['total_debit'] or Decimal('0')
            credit = balance_sum['total_credit'] or Decimal('0')

            if account.account_type in ['Asset', 'Expense']:
                debit_balance = debit - credit
                credit_balance = Decimal('0')
                if debit_balance < 0:
                    credit_balance = abs(debit_balance)
                    debit_balance = Decimal('0')
            else:
                credit_balance = credit - debit
                debit_balance = Decimal('0')
                if credit_balance < 0:
                    debit_balance = abs(credit_balance)
                    credit_balance = Decimal('0')

            if not include_zero_balances and debit_balance == 0 and credit_balance == 0:
                continue

            trial_balances.append({
                'account_code': account.code,
                'account_name': account.name,
                'account_type': account.account_type,
                'debit_balance': debit_balance,
                'credit_balance': credit_balance,
                'cost_center': None,
                'currency_code': currency_code,
            })

            total_debit += debit_balance
            total_credit += credit_balance

            if account.account_type == 'Asset':
                asset_total += debit_balance - credit_balance
            elif account.account_type == 'Liability':
                liability_total += credit_balance - debit_balance
            elif account.account_type == 'Equity':
                equity_total += credit_balance - debit_balance
            elif account.account_type == 'Income':
                income_total += credit_balance - debit_balance
            elif account.account_type == 'Expense':
                expense_total += debit_balance - credit_balance

        trial_balances.sort(key=lambda x: x['account_code'])

        # S2-08 — ±0.01 tolerance on trial-balance equality so legitimate
        # rounding from revaluation/depreciation doesn't flip the flag.
        _tolerance = Decimal('0.01')
        return TrialBalanceResult(
            fiscal_year=fiscal_year,
            period=period,
            as_of_date=as_of_date,
            period_start=period_start,
            period_end=period_end,
            total_debit=total_debit,
            total_credit=total_credit,
            difference=total_debit - total_credit,
            is_balanced=abs(total_debit - total_credit) <= _tolerance,
            accounts=trial_balances,
            asset_total=asset_total,
            liability_total=liability_total,
            equity_total=equity_total,
            income_total=income_total,
            expense_total=expense_total,
            currency_code=currency_code,
        )

    @classmethod
    def generate_trial_balance_from_journals(
        cls,
        fiscal_year: int,
        period: int,
        as_of_date: date = None,
        currency_code: str = None,
    ) -> TrialBalanceResult:
        """
        Generate trial balance directly from posted journals.
        Useful for verification against the aggregated GLBalance version.

        S2-08 fixes:
          * ``currency_code`` is now accepted + defaults to tenant base
            currency (was UndefinedNameError when used at line 266/290).
          * Filter is by ``posting_date`` range (not non-existent
            ``fiscal_year``/``period`` fields on JournalHeader).
          * Status filter uses the actual choice value 'Posted' (title
            case) not 'POSTED' — otherwise the query silently returned
            zero journals on every tenant.
          * Uses ``line.debit`` / ``line.credit`` (actual field names);
            the previous ``debit_amount`` / ``credit_amount`` would
            raise AttributeError on every line.
          * Line lookup uses ``header=journal`` (the actual FK name).
          * Balance equality uses ±0.01 tolerance.
        """
        # Default currency to tenant base.
        if currency_code is None:
            try:
                from accounting.utils import get_base_currency_code
                currency_code = get_base_currency_code()
            except Exception:
                currency_code = 'NGN'

        if as_of_date is None:
            as_of_date = date.today()

        fiscal_period = FiscalPeriod.objects.filter(
            fiscal_year=fiscal_year,
            period=period,
        ).first()

        period_start = fiscal_period.start_date if fiscal_period else date(fiscal_year, 1, 1)
        period_end = fiscal_period.end_date if fiscal_period else date(fiscal_year, 12, 31)

        # JournalHeader has posting_date + status; no fiscal_year / period
        # columns. Filter by posting_date window in the period.
        journals = JournalHeader.objects.filter(
            posting_date__gte=period_start,
            posting_date__lte=period_end,
            status='Posted',
        )

        accounts_data = {}

        # Use prefetch to avoid N+1 across journals/lines.
        for journal in journals.prefetch_related('lines__account'):
            for line in journal.lines.all():
                account = line.account
                if account.id not in accounts_data:
                    accounts_data[account.id] = {
                        'account_code': account.code,
                        'account_name': account.name,
                        'account_type': account.account_type,
                        'debit':  Decimal('0'),
                        'credit': Decimal('0'),
                    }
                accounts_data[account.id]['debit']  += line.debit  or Decimal('0')
                accounts_data[account.id]['credit'] += line.credit or Decimal('0')

        trial_balances = []
        total_debit = Decimal('0')
        total_credit = Decimal('0')

        for account_id, data in accounts_data.items():
            if data['account_type'] in ['Asset', 'Expense']:
                debit_balance = data['debit'] - data['credit']
                credit_balance = Decimal('0')
                if debit_balance < 0:
                    credit_balance = abs(debit_balance)
                    debit_balance = Decimal('0')
            else:
                credit_balance = data['credit'] - data['debit']
                debit_balance = Decimal('0')
                if credit_balance < 0:
                    debit_balance = abs(credit_balance)
                    credit_balance = Decimal('0')

            trial_balances.append({
                'account_code': data['account_code'],
                'account_name': data['account_name'],
                'account_type': data['account_type'],
                'debit_balance': debit_balance,
                'credit_balance': credit_balance,
                'cost_center': None,
                'currency_code': currency_code,
            })

            total_debit += debit_balance
            total_credit += credit_balance

        trial_balances.sort(key=lambda x: x['account_code'])

        # ±0.01 tolerance for Decimal balance equality (S2-08).
        _tolerance = Decimal('0.01')
        return TrialBalanceResult(
            fiscal_year=fiscal_year,
            period=period,
            as_of_date=as_of_date,
            period_start=period_start,
            period_end=period_end,
            total_debit=total_debit,
            total_credit=total_credit,
            difference=total_debit - total_credit,
            is_balanced=abs(total_debit - total_credit) <= _tolerance,
            accounts=trial_balances,
            asset_total=Decimal('0'),
            liability_total=Decimal('0'),
            equity_total=Decimal('0'),
            income_total=Decimal('0'),
            expense_total=Decimal('0'),
            currency_code=currency_code,
        )

    @classmethod
    def get_trial_balance_summary(cls, fiscal_year: int, period: int) -> Dict[str, Any]:
        """Get summary of trial balance with totals by account type."""
        result = cls.generate_trial_balance(fiscal_year, period)

        return {
            'fiscal_year': fiscal_year,
            'period': period,
            'as_of_date': result.as_of_date,
            'is_balanced': result.is_balanced,
            'total_debit': result.total_debit,
            'total_credit': result.total_credit,
            'difference': result.difference,
            'account_type_summary': {
                'Assets': result.asset_total,
                'Liabilities': result.liability_total,
                'Equity': result.equity_total,
                'Income': result.income_total,
                'Expenses': result.expense_total,
            },
            'account_count': len(result.accounts),
        }

    @classmethod
    def verify_trial_balance(cls, fiscal_year: int, period: int) -> Dict[str, Any]:
        """
        Verify trial balance integrity and return any discrepancies.
        """
        result = cls.generate_trial_balance(fiscal_year, period)
        journal_result = cls.generate_trial_balance_from_journals(fiscal_year, period)

        discrepancies = []

        if not result.is_balanced:
            discrepancies.append({
                'type': 'UNBALANCED',
                'message': f'Trial balance is not balanced. Difference: {result.difference}',
                'severity': 'ERROR',
            })

        if result.total_debit != journal_result.total_debit:
            discrepancies.append({
                'type': 'DEBIT_MISMATCH',
                'message': f'GL Balance debit ({result.total_debit}) != Journal debit ({journal_result.total_debit})',
                'severity': 'WARNING',
            })

        if result.total_credit != journal_result.total_credit:
            discrepancies.append({
                'type': 'CREDIT_MISMATCH',
                'message': f'GL Balance credit ({result.total_credit}) != Journal credit ({journal_result.total_credit})',
                'severity': 'WARNING',
            })

        return {
            'fiscal_year': fiscal_year,
            'period': period,
            'is_balanced': result.is_balanced,
            'discrepancies': discrepancies,
            'gl_total_debit': result.total_debit,
            'gl_total_credit': result.total_credit,
            'journal_total_debit': journal_result.total_debit,
            'journal_total_credit': journal_result.total_credit,
        }
