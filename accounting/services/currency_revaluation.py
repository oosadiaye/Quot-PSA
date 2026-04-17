"""Currency Revaluation Service

Provides scheduled foreign currency revaluation:
- Month-end revaluation processing
- Unrealized gain/loss calculation
- FX journal generation
"""
from datetime import date
from decimal import Decimal
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass
from django.db import transaction
from django.contrib.auth.models import User
from accounting.models import CurrencyRevaluationRun, CurrencyRevaluationDetail


@dataclass
class RevaluationResult:
    """Result of a revaluation run."""
    run_id: int
    currencies_processed: int
    accounts_processed: int
    total_gain: Decimal
    total_loss: Decimal
    net_effect: Decimal
    journal_ids: List[int]
    status: str


class CurrencyRevaluationService:
    """Service for currency revaluation operations."""

    GAIN_ACCOUNT_CODE = '7100'
    LOSS_ACCOUNT_CODE = '8100'

    @classmethod
    def get_revaluation_rate(
        cls,
        currency_code: str,
        revaluation_date: date
    ) -> Decimal:
        """
        Get the exchange rate for revaluation.

        Args:
            currency_code: Currency code
            revaluation_date: Date for rate lookup

        Returns:
            Exchange rate to base currency
        """
        from accounting.models import Currency, ExchangeRateHistory

        currency = Currency.objects.filter(code=currency_code).first()
        if not currency:
            return Decimal('1')

        historical_rate = ExchangeRateHistory.objects.filter(
            from_currency=currency,
            rate_date__lte=revaluation_date
        ).order_by('-rate_date').first()

        if historical_rate:
            return historical_rate.exchange_rate

        return currency.exchange_rate

    @classmethod
    def get_accounts_to_revalue(
        cls,
        currency_code: str,
        fiscal_year: int,
        period: int
    ) -> List[Dict[str, Any]]:
        """
        Get all account balances that need revaluation for a currency.

        Args:
            currency_code: Currency code
            fiscal_year: Fiscal year
            period: Period number

        Returns:
            List of account balance dictionaries
        """
        from accounting.models import GLBalance

        balances = GLBalance.objects.filter(
            account__is_active=True,
            fiscal_year=fiscal_year,
            period=period,
        ).select_related('account')

        result = []
        for balance in balances:
            account = balance.account

            if hasattr(account, 'currency') and account.currency and account.currency.code == currency_code:
                result.append({
                    'account_id': account.id,
                    'account_code': account.code,
                    'account_name': account.name,
                    'debit_balance': balance.debit_balance,
                    'credit_balance': balance.credit_balance,
                    'net_balance': balance.debit_balance - balance.credit_balance,
                })

        return result

    @classmethod
    def calculate_revaluation(
        cls,
        revaluation_date: date,
        currency_code: str = None,
        fiscal_year: int = None,
        period: int = None,
        user: User = None
    ) -> CurrencyRevaluationRun:
        """
        Calculate currency revaluation for all or specific currencies.

        Args:
            revaluation_date: Date of revaluation
            currency_code: Optional specific currency
            fiscal_year: Fiscal year
            period: Period number
            user: User performing revaluation

        Returns:
            CurrencyRevaluationRun with calculated values
        """
        from accounting.models import Currency

        if not fiscal_year:
            fiscal_year = revaluation_date.year
        if not period:
            period = revaluation_date.month

        run = CurrencyRevaluationRun.objects.create(
            revaluation_date=revaluation_date,
            created_by=user,
            status='DRAFT',
        )

        currencies = Currency.objects.filter(is_active=True, is_base_currency=False)
        if currency_code:
            currencies = currencies.filter(code=currency_code)

        currencies_processed = []
        total_gain = Decimal('0')
        total_loss = Decimal('0')

        for currency in currencies:
            current_rate = cls.get_revaluation_rate(currency.code, revaluation_date)

            if currency.exchange_rate == current_rate:
                continue

            accounts = cls.get_accounts_to_revalue(currency.code, fiscal_year, period)

            for account_data in accounts:
                balance = account_data['net_balance']
                current_value = balance * currency.exchange_rate
                revalued_value = balance * current_rate
                difference = revalued_value - current_value

                detail = CurrencyRevaluationDetail.objects.create(
                    run=run,
                    currency=currency,
                    account_id=account_data['account_id'],
                    exchange_rate_before=currency.exchange_rate,
                    exchange_rate_after=current_rate,
                    balance_in_currency=balance,
                    balance_in_base=current_value,
                    revalued_balance=revalued_value,
                    gain_amount=difference if difference > 0 else Decimal('0'),
                    loss_amount=abs(difference) if difference < 0 else Decimal('0'),
                )

                if difference > 0:
                    total_gain += difference
                else:
                    total_loss += abs(difference)

            currencies_processed.append(currency.code)

            currency.exchange_rate = current_rate
            currency.save()

        run.currencies_processed = currencies_processed
        run.total_gain = total_gain
        run.total_loss = total_loss
        run.net_effect = total_gain - total_loss
        run.status = 'CALCULATED'
        run.save()

        return run

    @classmethod
    def post_revaluation(
        cls,
        run_id: int,
        user: User
    ) -> Tuple[bool, str, List[int]]:
        """
        Post revaluation journal entries.

        Args:
            run_id: CurrencyRevaluationRun ID
            user: User posting

        Returns:
            Tuple of (success, message, journal_ids)
        """
        from accounting.models import (
            JournalHeader, JournalLine, Account
        )

        try:
            run = CurrencyRevaluationRun.objects.get(id=run_id)
        except CurrencyRevaluationRun.DoesNotExist:
            return False, "Revaluation run not found", []

        if run.status != 'CALCULATED':
            return False, f"Cannot post: status is {run.status}", []

        gain_account = Account.objects.filter(
            code=cls.GAIN_ACCOUNT_CODE
        ).first()

        loss_account = Account.objects.filter(
            code=cls.LOSS_ACCOUNT_CODE
        ).first()

        if not gain_account or not loss_account:
            return False, "Gain/Loss accounts not configured", []

        journal_ids = []

        with transaction.atomic():
            journal = JournalHeader.objects.create(
                posting_date=run.revaluation_date,
                description=f"Currency Revaluation - {run.revaluation_date}",
                reference_number=f"FX-REV-{run.id}",
                status='Draft',
                source_module='accounting',
                source_document_id=run.pk,
            )

            for detail in run.details.all():
                if detail.gain_amount > 0:
                    JournalLine.objects.create(
                        header=journal,
                        account=detail.account,
                        debit=detail.gain_amount,
                        memo=f"FX Gain - {detail.currency.code}"
                    )
                    detail.journal_line_id = journal.id
                    detail.save()

                elif detail.loss_amount > 0:
                    JournalLine.objects.create(
                        header=journal,
                        account=detail.account,
                        credit=detail.loss_amount,
                        memo=f"FX Loss - {detail.currency.code}"
                    )
                    detail.journal_line_id = journal.id
                    detail.save()

            if run.total_gain > 0:
                JournalLine.objects.create(
                    header=journal,
                    account=gain_account,
                    credit=run.total_gain,
                    memo="Total FX Gain"
                )

            if run.total_loss > 0:
                JournalLine.objects.create(
                    header=journal,
                    account=loss_account,
                    debit=run.total_loss,
                    memo="Total FX Loss"
                )

            journal.status = 'Posted'
            journal.save()

            run.status = 'POSTED'
            run.posted_at = timezone.now()
            run.posted_by = user
            run.journals_created = [journal.id]
            run.save()

            journal_ids.append(journal.id)

        return True, f"Posted {len(journal_ids)} journal(s)", journal_ids

    @classmethod
    def reverse_revaluation(
        cls,
        run_id: int,
        user: User
    ) -> Tuple[bool, str]:
        """
        Reverse a posted revaluation.

        Args:
            run_id: CurrencyRevaluationRun ID
            user: User reversing

        Returns:
            Tuple of (success, message)
        """
        try:
            run = CurrencyRevaluationRun.objects.get(id=run_id)
        except CurrencyRevaluationRun.DoesNotExist:
            return False, "Revaluation run not found"

        if run.status != 'POSTED':
            return False, f"Cannot reverse: status is {run.status}"

        for detail in run.details.all():
            if detail.account:
                detail.account.exchange_rate = detail.exchange_rate_before
                detail.account.save()

        run.status = 'REVERSED'
        run.notes = f"Reversed by {user.username} on {timezone.now()}"
        run.save()

        return True, "Revaluation reversed successfully"

    @classmethod
    def generate_revaluation_report(
        cls,
        run_id: int
    ) -> Dict[str, Any]:
        """
        Generate a detailed revaluation report.

        Args:
            run_id: CurrencyRevaluationRun ID

        Returns:
            Dictionary with report data
        """
        try:
            run = CurrencyRevaluationRun.objects.get(id=run_id)
        except CurrencyRevaluationRun.DoesNotExist:
            return {'error': 'Run not found'}

        details = []
        for detail in run.details.all():
            details.append({
                'currency': detail.currency.code,
                'currency_name': detail.currency.name,
                'account_code': detail.account.code if detail.account else 'N/A',
                'account_name': detail.account.name if detail.account else 'N/A',
                'exchange_rate_before': float(detail.exchange_rate_before),
                'exchange_rate_after': float(detail.exchange_rate_after),
                'balance_in_currency': float(detail.balance_in_currency),
                'balance_in_base': float(detail.balance_in_base),
                'revalued_balance': float(detail.revalued_balance),
                'gain': float(detail.gain_amount),
                'loss': float(detail.loss_amount),
            })

        return {
            'run_id': run.id,
            'revaluation_date': str(run.revaluation_date),
            'status': run.status,
            'currencies_processed': run.currencies_processed,
            'total_gain': float(run.total_gain),
            'total_loss': float(run.total_loss),
            'net_effect': float(run.net_effect),
            'journals_created': run.journals_created,
            'details': details,
            'created_by': run.created_by.username if run.created_by else 'Unknown',
            'created_at': run.created_at.isoformat() if run.created_at else None,
        }


try:
    from django.utils import timezone
except ImportError:
    timezone = None
