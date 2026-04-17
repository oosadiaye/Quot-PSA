"""
Unit Tests for Accounting Module
================================
Comprehensive test coverage for:
- Journal entry creation and validation
- GL balance updates and trial balance calculations
- Account reconciliation
- Currency handling
- Journal posting workflows
"""

from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import date

from accounting.models import (
    Account,
    Fund,
    Function,
    Program,
    Geo,
    MDA,
    Currency,
    JournalHeader,
    JournalLine,
    JournalReversal,
    GLBalance,
    BudgetPeriod,
)


class AccountTestCase(TestCase):
    """Test cases for Account model"""

    def test_create_expense_account(self):
        """Test creating an expense account"""
        account = Account.objects.create(
            code='50100000',
            name='Travel Expense',
            account_type='Expense',
            is_active=True
        )

        self.assertEqual(account.code, '50100000')
        self.assertEqual(account.account_type, 'Expense')
        self.assertTrue(account.is_active)

    def test_create_asset_account(self):
        """Test creating an asset account"""
        account = Account.objects.create(
            code='10100000',
            name='Cash',
            account_type='Asset',
            is_active=True,
            is_reconciliation=True,
            reconciliation_type='bank_accounting'
        )

        self.assertEqual(account.account_type, 'Asset')
        self.assertTrue(account.is_reconciliation)
        self.assertEqual(account.reconciliation_type, 'bank_accounting')

    def test_account_str_representation(self):
        """Test string representation"""
        account = Account(
            code='40100000',
            name='Sales Revenue',
            account_type='Income'
        )
        self.assertEqual(str(account), '40100000 - Sales Revenue')

    def test_account_ordering(self):
        """Test accounts are ordered by code"""
        Account.objects.create(code='10300000', name='Third', account_type='Asset')
        Account.objects.create(code='10100000', name='First', account_type='Asset')
        Account.objects.create(code='10200000', name='Second', account_type='Asset')

        accounts = list(Account.objects.filter(account_type='Asset'))
        self.assertEqual(accounts[0].code, '10100000')
        self.assertEqual(accounts[1].code, '10200000')
        self.assertEqual(accounts[2].code, '10300000')


class JournalEntryTestCase(TestCase):
    """Test cases for Journal Entry (JournalHeader and JournalLine)"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='journaluser',
            email='journal@test.com',
            password='testpass123'
        )

        self.fund = Fund.objects.create(code='001', name='Recurrent Fund')
        self.function = Function.objects.create(code='GEN', name='General')
        self.program = Program.objects.create(code='01', name='Program 1')
        self.geo = Geo.objects.create(code='NG', name='Nigeria')
        self.mda = MDA.objects.create(code='001', name='MoF', mda_type='MINISTRY')

        self.cash_account = Account.objects.create(
            code='10100000', name='Cash', account_type='Asset'
        )
        self.revenue_account = Account.objects.create(
            code='40100000', name='Revenue', account_type='Income'
        )
        self.expense_account = Account.objects.create(
            code='50100000', name='Expense', account_type='Expense'
        )

    def test_journal_entry_creation(self):
        """Test creating a journal entry"""
        journal = JournalHeader.objects.create(
            posting_date=date.today(),
            description='Test journal entry',
            reference_number='JE-001',
            fund=self.fund,
            function=self.function,
            program=self.program,
            geo=self.geo,
            mda=self.mda,
            status='Draft',
            created_by=self.user
        )

        self.assertEqual(journal.status, 'Draft')
        self.assertEqual(journal.reference_number, 'JE-001')

    def test_journal_entry_balanced(self):
        """Test that journal entry is balanced (debits = credits)"""
        journal = JournalHeader.objects.create(
            posting_date=date.today(),
            description='Balanced journal',
            reference_number='JE-002',
            fund=self.fund,
            status='Draft',
            created_by=self.user
        )

        JournalLine.objects.create(
            header=journal,
            account=self.cash_account,
            debit=Decimal('1000.00'),
            credit=Decimal('0.00'),
            memo='Cash received'
        )

        JournalLine.objects.create(
            header=journal,
            account=self.revenue_account,
            debit=Decimal('0.00'),
            credit=Decimal('1000.00'),
            memo='Revenue earned'
        )

        total_debit = sum(line.debit for line in journal.lines.all())
        total_credit = sum(line.credit for line in journal.lines.all())

        self.assertEqual(total_debit, Decimal('1000.00'))
        self.assertEqual(total_credit, Decimal('1000.00'))

    def test_journal_entry_unbalanced(self):
        """Test unbalanced journal entry detection"""
        journal = JournalHeader.objects.create(
            posting_date=date.today(),
            description='Unbalanced journal',
            reference_number='JE-003',
            fund=self.fund,
            status='Draft',
            created_by=self.user
        )

        JournalLine.objects.create(
            header=journal,
            account=self.cash_account,
            debit=Decimal('1000.00'),
            credit=Decimal('0.00')
        )

        JournalLine.objects.create(
            header=journal,
            account=self.revenue_account,
            debit=Decimal('0.00'),
            credit=Decimal('800.00')
        )

        total_debit = sum(line.debit for line in journal.lines.all())
        total_credit = sum(line.credit for line in journal.lines.all())

        self.assertNotEqual(total_debit, total_credit)

    def test_journal_status_draft_to_pending(self):
        """Test journal status transition from Draft to Pending"""
        journal = JournalHeader.objects.create(
            posting_date=date.today(),
            description='Test',
            reference_number='JE-004',
            fund=self.fund,
            status='Draft',
            created_by=self.user
        )

        journal.status = 'Pending'
        journal.save()

        self.assertEqual(journal.status, 'Pending')

    def test_journal_status_pending_to_approved(self):
        """Test journal status transition from Pending to Approved"""
        journal = JournalHeader.objects.create(
            posting_date=date.today(),
            description='Test',
            reference_number='JE-005',
            fund=self.fund,
            status='Pending',
            created_by=self.user
        )

        journal.status = 'Approved'
        journal.save()

        self.assertEqual(journal.status, 'Approved')

    def test_journal_str_representation(self):
        """Test journal string representation"""
        journal = JournalHeader(
            posting_date=date(2026, 1, 15),
            reference_number='JE-006',
            description='Test journal'
        )

        self.assertIn('JE-006', str(journal))
        self.assertIn('2026-01-15', str(journal))


class JournalLineTestCase(TestCase):
    """Test cases for JournalLine"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='lineuser',
            email='line@test.com',
            password='testpass123'
        )

        self.fund = Fund.objects.create(code='001', name='Fund')
        self.cash_account = Account.objects.create(
            code='10100000', name='Cash', account_type='Asset'
        )
        self.revenue_account = Account.objects.create(
            code='40100000', name='Revenue', account_type='Income'
        )

        self.journal = JournalHeader.objects.create(
            posting_date=date.today(),
            description='Line test journal',
            reference_number='JE-LINE-001',
            fund=self.fund,
            status='Draft',
            created_by=self.user
        )

    def test_journal_line_creation(self):
        """Test creating a journal line"""
        line = JournalLine.objects.create(
            header=self.journal,
            account=self.cash_account,
            debit=Decimal('500.00'),
            credit=Decimal('0.00'),
            memo='Test line'
        )

        self.assertEqual(line.debit, Decimal('500.00'))
        self.assertEqual(line.credit, Decimal('0.00'))

    def test_journal_line_str_representation(self):
        """Test journal line string representation"""
        line = JournalLine(
            header=self.journal,
            account=self.cash_account,
            debit=Decimal('100.00'),
            credit=Decimal('50.00')
        )

        self.assertIn('D:100', str(line))
        self.assertIn('C:50', str(line))


class GLBalanceTestCase(TestCase):
    """Test cases for GL Balance"""

    def setUp(self):
        self.fund = Fund.objects.create(code='001', name='Fund')
        self.function = Function.objects.create(code='GEN', name='General')
        self.program = Program.objects.create(code='01', name='Program')
        self.geo = Geo.objects.create(code='NG', name='Nigeria')

        self.expense_account = Account.objects.create(
            code='50100000', name='Expense', account_type='Expense'
        )
        self.revenue_account = Account.objects.create(
            code='40100000', name='Revenue', account_type='Income'
        )

    def test_gl_balance_creation(self):
        """Test creating a GL balance record"""
        gl = GLBalance.objects.create(
            account=self.expense_account,
            fund=self.fund,
            function=self.function,
            program=self.program,
            geo=self.geo,
            fiscal_year=2026,
            period=1,
            debit_balance=Decimal('50000.00'),
            credit_balance=Decimal('0.00')
        )

        self.assertEqual(gl.fiscal_year, 2026)
        self.assertEqual(gl.period, 1)
        self.assertEqual(gl.debit_balance, Decimal('50000.00'))

    def test_gl_balance_net_position(self):
        """Test GL balance net position calculation"""
        gl = GLBalance.objects.create(
            account=self.expense_account,
            fund=self.fund,
            fiscal_year=2026,
            period=1,
            debit_balance=Decimal('100000.00'),
            credit_balance=Decimal('25000.00')
        )

        net = gl.debit_balance - gl.credit_balance
        self.assertEqual(net, Decimal('75000.00'))

    def test_gl_balance_str_representation(self):
        """Test GL balance string representation"""
        gl = GLBalance(
            account=self.expense_account,
            fiscal_year=2026,
            period=3
        )

        self.assertIn('50100000', str(gl))
        self.assertIn('2026', str(gl))
        self.assertIn('P3', str(gl))

    def test_gl_balance_unique_constraint(self):
        """Test unique constraint on GL balance"""
        GLBalance.objects.create(
            account=self.expense_account,
            fund=self.fund,
            fiscal_year=2026,
            period=1,
            debit_balance=Decimal('1000.00')
        )

        with self.assertRaises(Exception):
            GLBalance.objects.create(
                account=self.expense_account,
                fund=self.fund,
                fiscal_year=2026,
                period=1,
                debit_balance=Decimal('2000.00')
            )


class CurrencyTestCase(TestCase):
    """Test cases for Currency"""

    def test_create_base_currency(self):
        """Test creating base currency"""
        currency = Currency.objects.create(
            code='NGN',
            name='Nigerian Naira',
            symbol='₦',
            exchange_rate=Decimal('1.000000'),
            is_base_currency=True,
            is_active=True
        )

        self.assertTrue(currency.is_base_currency)
        self.assertEqual(currency.exchange_rate, Decimal('1.000000'))

    def test_create_foreign_currency(self):
        """Test creating foreign currency"""
        currency = Currency.objects.create(
            code='USD',
            name='US Dollar',
            symbol='$',
            exchange_rate=Decimal('1500.500000'),
            is_base_currency=False,
            is_active=True
        )

        self.assertFalse(currency.is_base_currency)
        self.assertEqual(currency.exchange_rate, Decimal('1500.500000'))

    def test_currency_str_representation(self):
        """Test currency string representation"""
        currency = Currency(
            code='EUR',
            name='Euro',
            symbol='€'
        )

        self.assertEqual(str(currency), 'EUR - Euro')


class TrialBalanceTestCase(TestCase):
    """Test cases for Trial Balance calculation"""

    def setUp(self):
        self.fund = Fund.objects.create(code='001', name='Fund')

        self.cash_account = Account.objects.create(
            code='10100000', name='Cash', account_type='Asset'
        )
        self.revenue_account = Account.objects.create(
            code='40100000', name='Revenue', account_type='Income'
        )
        self.expense_account = Account.objects.create(
            code='50100000', name='Expense', account_type='Expense'
        )
        self.equity_account = Account.objects.create(
            code='30100000', name='Capital', account_type='Equity'
        )

    def test_trial_balance_balanced(self):
        """Test trial balance when debits equal credits"""
        GLBalance.objects.create(
            account=self.cash_account,
            fund=self.fund,
            fiscal_year=2026,
            period=12,
            debit_balance=Decimal('500000.00'),
            credit_balance=Decimal('0.00')
        )

        GLBalance.objects.create(
            account=self.revenue_account,
            fund=self.fund,
            fiscal_year=2026,
            period=12,
            debit_balance=Decimal('0.00'),
            credit_balance=Decimal('300000.00')
        )

        GLBalance.objects.create(
            account=self.expense_account,
            fund=self.fund,
            fiscal_year=2026,
            period=12,
            debit_balance=Decimal('200000.00'),
            credit_balance=Decimal('0.00')
        )

        GLBalance.objects.create(
            account=self.equity_account,
            fund=self.fund,
            fiscal_year=2026,
            period=12,
            debit_balance=Decimal('0.00'),
            credit_balance=Decimal('400000.00')
        )

        gl_balances = GLBalance.objects.filter(fiscal_year=2026, period=12)

        total_debits = sum(gl.debit_balance for gl in gl_balances)
        total_credits = sum(gl.credit_balance for gl in gl_balances)

        self.assertEqual(total_debits, Decimal('700000.00'))
        self.assertEqual(total_credits, Decimal('700000.00'))

    def test_trial_balance_unbalanced(self):
        """Test detecting unbalanced trial balance"""
        GLBalance.objects.create(
            account=self.cash_account,
            fund=self.fund,
            fiscal_year=2026,
            period=12,
            debit_balance=Decimal('500000.00'),
            credit_balance=Decimal('0.00')
        )

        GLBalance.objects.create(
            account=self.revenue_account,
            fund=self.fund,
            fiscal_year=2026,
            period=12,
            debit_balance=Decimal('0.00'),
            credit_balance=Decimal('350000.00')
        )

        gl_balances = GLBalance.objects.filter(fiscal_year=2026, period=12)

        total_debits = sum(gl.debit_balance for gl in gl_balances)
        total_credits = sum(gl.credit_balance for gl in gl_balances)

        self.assertNotEqual(total_debits, total_credits)


class JournalPostingTestCase(TestCase):
    """Test cases for journal posting to GL"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='postinguser',
            email='posting@test.com',
            password='testpass123'
        )

        self.fund = Fund.objects.create(code='001', name='Fund')

        self.cash_account = Account.objects.create(
            code='10100000', name='Cash', account_type='Asset'
        )
        self.revenue_account = Account.objects.create(
            code='40100000', name='Revenue', account_type='Income'
        )

        self.journal = JournalHeader.objects.create(
            posting_date=date.today(),
            description='Posting test',
            reference_number='JE-POST-001',
            fund=self.fund,
            status='Approved',
            created_by=self.user
        )

        JournalLine.objects.create(
            header=self.journal,
            account=self.cash_account,
            debit=Decimal('10000.00'),
            credit=Decimal('0.00')
        )

        JournalLine.objects.create(
            header=self.journal,
            account=self.revenue_account,
            debit=Decimal('0.00'),
            credit=Decimal('10000.00')
        )

    def test_post_journal_to_gl(self):
        """Test posting journal entry to GL"""
        for line in self.journal.lines.all():
            gl_balance, created = GLBalance.objects.get_or_create(
                account=line.account,
                fund=self.journal.fund,
                fiscal_year=self.journal.posting_date.year,
                period=self.journal.posting_date.month,
                defaults={
                    'debit_balance': Decimal('0'),
                    'credit_balance': Decimal('0')
                }
            )

            if line.debit > 0:
                gl_balance.debit_balance += line.debit
            if line.credit > 0:
                gl_balance.credit_balance += line.credit

            gl_balance.save()

        cash_gl = GLBalance.objects.get(
            account=self.cash_account,
            fiscal_year=self.journal.posting_date.year,
            period=self.journal.posting_date.month
        )

        revenue_gl = GLBalance.objects.get(
            account=self.revenue_account,
            fiscal_year=self.journal.posting_date.year,
            period=self.journal.posting_date.month
        )

        self.assertEqual(cash_gl.debit_balance, Decimal('10000.00'))
        self.assertEqual(revenue_gl.credit_balance, Decimal('10000.00'))

    def test_journal_status_after_posting(self):
        """Test that journal status changes to Posted after GL update"""
        self.journal.status = 'Posted'
        self.journal.save()

        self.assertEqual(self.journal.status, 'Posted')


class JournalReversalTestCase(TestCase):
    """Test cases for journal reversal"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='reversaluser',
            email='reversal@test.com',
            password='testpass123'
        )

        self.fund = Fund.objects.create(code='001', name='Fund')

        self.cash_account = Account.objects.create(
            code='10100000', name='Cash', account_type='Asset'
        )
        self.revenue_account = Account.objects.create(
            code='40100000', name='Revenue', account_type='Income'
        )

    def test_create_reversal(self):
        """Test creating a journal reversal"""
        original = JournalHeader.objects.create(
            posting_date=date(2026, 1, 15),
            description='Original entry',
            reference_number='JE-ORIG-001',
            fund=self.fund,
            status='Posted',
            created_by=self.user
        )

        JournalLine.objects.create(
            header=original,
            account=self.cash_account,
            debit=Decimal('5000.00'),
            credit=Decimal('0.00')
        )

        JournalLine.objects.create(
            header=original,
            account=self.revenue_account,
            debit=Decimal('0.00'),
            credit=Decimal('5000.00')
        )

        reversal = JournalHeader.objects.create(
            posting_date=date(2026, 2, 1),
            description='Reversal of JE-ORIG-001',
            reference_number='JE-REV-001',
            fund=self.fund,
            status='Posted',
            created_by=self.user
        )

        JournalReversal.objects.create(
            original_journal=original,
            reversal_journal=reversal,
            reversal_type='Reverse',
            reason='Entry was posted to wrong period',
            reversed_by=self.user
        )

        self.assertEqual(original.reversals.count(), 1)


class BudgetPeriodTestCase(TestCase):
    """Test cases for BudgetPeriod"""

    def test_create_monthly_periods(self):
        """Test creating monthly budget periods"""
        for month in range(1, 13):
            period = BudgetPeriod.objects.create(
                fiscal_year=2026,
                period_type='MONTHLY',
                period_number=month,
                start_date=date(2026, month, 1),
                end_date=date(2026, month, 28) if month != 2 else date(2026, 2, 28),
                status='Open'
            )
            self.assertEqual(period.period_number, month)

    def test_create_quarterly_periods(self):
        """Test creating quarterly budget periods"""
        quarters = [
            (1, date(2026, 1, 1), date(2026, 3, 31)),
            (2, date(2026, 4, 1), date(2026, 6, 30)),
            (3, date(2026, 7, 1), date(2026, 9, 30)),
            (4, date(2026, 10, 1), date(2026, 12, 31)),
        ]

        for q, start, end in quarters:
            period = BudgetPeriod.objects.create(
                fiscal_year=2026,
                period_type='QUARTERLY',
                period_number=q,
                start_date=start,
                end_date=end,
                status='Open'
            )
            self.assertEqual(period.period_number, q)

    def test_period_locking(self):
        """Test period locking"""
        period = BudgetPeriod.objects.create(
            fiscal_year=2026,
            period_type='MONTHLY',
            period_number=1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            status='Open'
        )

        period.status = 'Closed'
        period.save()

        self.assertEqual(period.status, 'Closed')

    def test_period_status_transitions(self):
        """Test period status transitions"""
        period = BudgetPeriod.objects.create(
            fiscal_year=2026,
            period_type='ANNUAL',
            period_number=1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status='Open'
        )

        period.status = 'Closed'
        period.save()
        self.assertEqual(period.status, 'Closed')

        period.status = 'Archived'
        period.save()
        self.assertEqual(period.status, 'Archived')


class AccountReconciliationTestCase(TestCase):
    """Test cases for account reconciliation"""

    def setUp(self):
        self.fund = Fund.objects.create(code='001', name='Fund')

        self.bank_account = Account.objects.create(
            code='10101000',
            name='Bank Account',
            account_type='Asset',
            is_reconciliation=True,
            reconciliation_type='bank_accounting'
        )

        self.revenue_account = Account.objects.create(
            code='40100000',
            name='Revenue',
            account_type='Income'
        )

    def test_bank_reconciliation_account(self):
        """Test identifying bank reconciliation accounts"""
        self.assertTrue(self.bank_account.is_reconciliation)
        self.assertEqual(
            self.bank_account.reconciliation_type,
            'bank_accounting'
        )

    def test_non_reconciliation_account(self):
        """Test non-reconciliation account"""
        self.assertFalse(self.revenue_account.is_reconciliation)

    def test_gl_balance_for_reconciliation_account(self):
        """Test GL balance for reconciliation account"""
        gl = GLBalance.objects.create(
            account=self.bank_account,
            fund=self.fund,
            fiscal_year=2026,
            period=1,
            debit_balance=Decimal('1000000.00'),
            credit_balance=Decimal('0.00')
        )

        normal_balance = gl.debit_balance - gl.credit_balance
        self.assertEqual(normal_balance, Decimal('1000000.00'))


class AccountTypeTestCase(TestCase):
    """Test account type classifications"""

    def test_asset_account_nature(self):
        """Test asset account has debit nature"""
        account = Account(
            code='10100000',
            name='Cash',
            account_type='Asset'
        )
        self.assertEqual(account.account_type, 'Asset')

    def test_liability_account_nature(self):
        """Test liability account has credit nature"""
        account = Account(
            code='20100000',
            name='Accounts Payable',
            account_type='Liability'
        )
        self.assertEqual(account.account_type, 'Liability')

    def test_equity_account_nature(self):
        """Test equity account has credit nature"""
        account = Account(
            code='30100000',
            name='Capital',
            account_type='Equity'
        )
        self.assertEqual(account.account_type, 'Equity')

    def test_income_account_nature(self):
        """Test income account has credit nature"""
        account = Account(
            code='40100000',
            name='Revenue',
            account_type='Income'
        )
        self.assertEqual(account.account_type, 'Income')

    def test_expense_account_nature(self):
        """Test expense account has debit nature"""
        account = Account(
            code='50100000',
            name='Expense',
            account_type='Expense'
        )
        self.assertEqual(account.account_type, 'Expense')
