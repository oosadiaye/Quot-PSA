"""
Sprint-3 regression tests: year-end close.

Covers S3-06 — ``YearEndCloseService`` posts a real closing journal that
zeroes Revenue + Expense and transfers net surplus/deficit to the
Accumulated Fund account.

Without year-end close, nominal accounts carry balances into the next
fiscal year and every SoFP is wrong from FY+1 onwards.
"""
from datetime import date
from decimal import Decimal

import pytest


@pytest.mark.ipsas
@pytest.mark.django_db(transaction=True)
class TestYearEndClose:

    @pytest.fixture
    def fiscal_year_2022(self, db):
        """A prior fiscal year we can close without disturbing current work."""
        from accounting.models import FiscalYear
        fy, _ = FiscalYear.objects.get_or_create(
            year=2022,
            defaults={
                'start_date': date(2022, 1, 1),
                'end_date': date(2022, 12, 31),
                'status': 'Open',
            },
        )
        return fy

    @pytest.fixture
    def seed_balances(
        self, db, revenue_account, expense_account, fiscal_year_2022,
    ):
        """Seed GLBalance with 10M revenue and 7M expense for FY2022."""
        from accounting.models import GLBalance
        GLBalance.objects.create(
            account=revenue_account,
            fiscal_year=2022, period=12,
            debit_balance=Decimal('0'),
            credit_balance=Decimal('10000000'),
        )
        GLBalance.objects.create(
            account=expense_account,
            fiscal_year=2022, period=12,
            debit_balance=Decimal('7000000'),
            credit_balance=Decimal('0'),
        )
        return True

    def test_close_year_posts_balanced_closing_journal(
        self, superuser, fiscal_year_2022, seed_balances,
        accumulated_fund_account, revenue_account, expense_account,
    ):
        """Closing journal: DR revenue 10M, CR expense 7M, CR accumulated 3M.
        Total DR must equal total CR."""
        from accounting.services.year_end_close import YearEndCloseService
        from accounting.models import JournalHeader
        from django.db.models import Sum

        summary = YearEndCloseService.close_fiscal_year(
            fiscal_year_2022, user=superuser, force=True,
        )

        # 3M net surplus (10M revenue − 7M expense).
        assert summary['total_revenue'] == Decimal('10000000')
        assert summary['total_expense'] == Decimal('7000000')
        assert summary['surplus_deficit'] == Decimal('3000000')

        # Closing journal must be balanced (S1-01 DB constraint would
        # also catch this, but belt-and-suspenders).
        journal = JournalHeader.objects.get(pk=summary['journal_id'])
        agg = journal.lines.aggregate(d=Sum('debit'), c=Sum('credit'))
        assert agg['d'] == agg['c']

    def test_close_year_locks_fiscal_year(
        self, superuser, fiscal_year_2022, seed_balances, accumulated_fund_account,
    ):
        """After successful close, FiscalYear.status == 'Closed'."""
        from accounting.services.year_end_close import YearEndCloseService
        YearEndCloseService.close_fiscal_year(
            fiscal_year_2022, user=superuser, force=True,
        )
        fiscal_year_2022.refresh_from_db()
        assert fiscal_year_2022.status == 'Closed'

    def test_close_year_rejects_already_closed(
        self, superuser, fiscal_year_2022, seed_balances, accumulated_fund_account,
    ):
        """Calling close a second time raises YearEndCloseError."""
        from accounting.services.year_end_close import (
            YearEndCloseService, YearEndCloseError,
        )
        YearEndCloseService.close_fiscal_year(
            fiscal_year_2022, user=superuser, force=True,
        )
        with pytest.raises(YearEndCloseError):
            YearEndCloseService.close_fiscal_year(
                fiscal_year_2022, user=superuser, force=True,
            )

    def test_close_year_rejects_missing_accumulated_fund_account(
        self, superuser, fiscal_year_2022, seed_balances,
    ):
        """When the accumulated-fund account doesn't exist, close aborts
        without touching any other state."""
        from accounting.services.year_end_close import (
            YearEndCloseService, YearEndCloseError,
        )
        # Ensure the 43100000 account is NOT present in this test.
        from accounting.models import Account
        Account.objects.filter(code='43100000').delete()

        with pytest.raises(YearEndCloseError):
            YearEndCloseService.close_fiscal_year(
                fiscal_year_2022, user=superuser, force=True,
            )
        fiscal_year_2022.refresh_from_db()
        assert fiscal_year_2022.status == 'Open'  # not locked on failure
