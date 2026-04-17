"""
Advanced Accounting Services

This module provides:
- Recurring journal generation
- Accruals and deferrals with auto-reversal
- Foreign currency revaluation
- Period opening and closing
- Year-end closing with balance carry forward
"""

from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone
from django.db.models import Sum
from datetime import timedelta
from dateutil.relativedelta import relativedelta


class AdvancedAccountingError(Exception):
    """Custom exception for advanced accounting errors"""
    pass


class RecurringJournalService:
    """Service for managing recurring journals"""

    @staticmethod
    @transaction.atomic
    def generate_journals():
        """Generate journal entries from all due recurring templates"""
        from accounting.models import (
            RecurringJournal, RecurringJournalRun,
        )

        today = timezone.now().date()
        generated = []
        errors = []

        recurring_journals = RecurringJournal.objects.filter(
            is_active=True,
            next_run_date__lte=today,
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=today)
        )

        for template in recurring_journals:
            try:
                journal = RecurringJournalService._create_journal_from_template(
                    template, today
                )
                # Track run
                RecurringJournalRun.objects.create(
                    recurring_journal=template,
                    journal=journal,
                    run_date=today,
                    status='Generated',
                )
                # Advance next run date
                template.next_run_date = RecurringJournalService._calculate_next_run(
                    template.frequency, template.next_run_date
                )
                template.save(update_fields=['next_run_date'])
                generated.append(journal.reference_number or str(journal.id))
            except Exception as e:
                RecurringJournalRun.objects.create(
                    recurring_journal=template,
                    run_date=today,
                    status='Error',
                    error_message=str(e),
                )
                errors.append(f"{template.name}: {str(e)}")

        return {'generated': generated, 'errors': errors}

    @staticmethod
    @transaction.atomic
    def generate_single_journal(template, user):
        """Generate a single journal from a recurring template immediately"""
        from accounting.models import RecurringJournalRun

        today = timezone.now().date()
        journal = RecurringJournalService._create_journal_from_template(template, today)

        RecurringJournalRun.objects.create(
            recurring_journal=template,
            journal=journal,
            run_date=today,
            status='Generated',
        )

        # Advance next run date
        template.next_run_date = RecurringJournalService._calculate_next_run(
            template.frequency, template.next_run_date or today
        )
        template.save(update_fields=['next_run_date'])

        return journal

    @staticmethod
    def _create_journal_from_template(template, posting_date):
        """Create a JournalHeader + JournalLines from a recurring template."""
        from accounting.models import (
            JournalHeader, JournalLine, TransactionSequence,
        )

        ref = f"REC-{template.code}-{posting_date.strftime('%Y%m%d')}"

        journal = JournalHeader.objects.create(
            reference_number=ref,
            description=f"{template.name} - Auto-generated",
            posting_date=posting_date,
            fund=template.fund,
            function=template.function,
            program=template.program,
            geo=template.geo,
            status='Posted' if template.auto_post else 'Draft',
        )

        # Assign document number
        journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
        journal.save(update_fields=['document_number'])

        for line in template.lines.all():
            JournalLine.objects.create(
                header=journal,
                account=line.account,
                debit=line.debit or Decimal('0.00'),
                credit=line.credit or Decimal('0.00'),
                memo=line.description or '',
                document_number=journal.document_number,
            )

        # If auto-posted, update GL balances
        if journal.status == 'Posted':
            RecurringJournalService._update_gl(journal)

        return journal

    @staticmethod
    def _update_gl(journal):
        """Update GLBalance from journal lines."""

        fiscal_year = journal.posting_date.year
        period = journal.posting_date.month

        from accounting.services import update_gl_from_journal
        update_gl_from_journal(journal)

    @staticmethod
    def _calculate_next_run(frequency, current_date):
        """Calculate next run date based on frequency"""
        if frequency == 'daily':
            return current_date + timedelta(days=1)
        elif frequency == 'weekly':
            return current_date + timedelta(weeks=1)
        elif frequency == 'biweekly':
            return current_date + timedelta(weeks=2)
        elif frequency == 'monthly':
            return current_date + relativedelta(months=1)
        elif frequency == 'quarterly':
            return current_date + relativedelta(months=3)
        elif frequency == 'annually':
            return current_date + relativedelta(years=1)
        return current_date


class AccrualDeferralService:
    """Service for managing accruals and deferrals"""

    @staticmethod
    @transaction.atomic
    def post_accrual(accrual, user):
        """Post an accrual entry to create its journal entry and update GL."""
        from accounting.models import JournalHeader, JournalLine, TransactionSequence

        if accrual.is_posted:
            raise AdvancedAccountingError("Accrual is already posted")

        ref = f"ACCR-{accrual.code}"
        posting_date = accrual.posting_date or timezone.now().date()

        journal = JournalHeader.objects.create(
            reference_number=ref,
            description=f"Accrual: {accrual.name}",
            posting_date=posting_date,
            status='Posted',
        )
        journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
        journal.save(update_fields=['document_number'])

        amount = accrual.amount

        if accrual.accrual_type == 'expense':
            JournalLine.objects.create(
                header=journal, account=accrual.account,
                debit=amount, credit=Decimal('0.00'),
                memo=f"Accrual: {accrual.name}", document_number=journal.document_number,
            )
            JournalLine.objects.create(
                header=journal, account=accrual.counterpart_account,
                debit=Decimal('0.00'), credit=amount,
                memo=f"Accrual: {accrual.name}", document_number=journal.document_number,
            )
        else:  # revenue
            JournalLine.objects.create(
                header=journal, account=accrual.account,
                debit=Decimal('0.00'), credit=amount,
                memo=f"Accrual: {accrual.name}", document_number=journal.document_number,
            )
            JournalLine.objects.create(
                header=journal, account=accrual.counterpart_account,
                debit=amount, credit=Decimal('0.00'),
                memo=f"Accrual: {accrual.name}", document_number=journal.document_number,
            )

        # Update GL
        RecurringJournalService._update_gl(journal)

        accrual.is_posted = True
        accrual.journal_entry = journal
        accrual.save(update_fields=['is_posted', 'journal_entry'])

        return journal

    @staticmethod
    @transaction.atomic
    def reverse_accrual(accrual, user):
        """Reverse a single posted accrual."""
        from accounting.models import JournalHeader, JournalLine, TransactionSequence

        if accrual.is_reversed:
            raise AdvancedAccountingError("Accrual is already reversed")
        if not accrual.is_posted:
            raise AdvancedAccountingError("Cannot reverse an unposted accrual")

        reversal_date = accrual.reversal_date or timezone.now().date()
        ref = f"ACCR-REV-{accrual.code}"

        journal = JournalHeader.objects.create(
            reference_number=ref,
            description=f"Reversal: {accrual.name}",
            posting_date=reversal_date,
            status='Posted',
        )
        journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
        journal.save(update_fields=['document_number'])

        amount = accrual.amount

        # Reverse the original entries
        if accrual.accrual_type == 'expense':
            JournalLine.objects.create(
                header=journal, account=accrual.counterpart_account,
                debit=amount, credit=Decimal('0.00'),
                memo=f"Reversal: {accrual.name}", document_number=journal.document_number,
            )
            JournalLine.objects.create(
                header=journal, account=accrual.account,
                debit=Decimal('0.00'), credit=amount,
                memo=f"Reversal: {accrual.name}", document_number=journal.document_number,
            )
        else:
            JournalLine.objects.create(
                header=journal, account=accrual.account,
                debit=amount, credit=Decimal('0.00'),
                memo=f"Reversal: {accrual.name}", document_number=journal.document_number,
            )
            JournalLine.objects.create(
                header=journal, account=accrual.counterpart_account,
                debit=Decimal('0.00'), credit=amount,
                memo=f"Reversal: {accrual.name}", document_number=journal.document_number,
            )

        RecurringJournalService._update_gl(journal)

        accrual.is_reversed = True
        accrual.reversal_journal = journal
        accrual.save(update_fields=['is_reversed', 'reversal_journal'])

        return journal

    @staticmethod
    @transaction.atomic
    def reverse_accruals(period):
        """Reverse all accruals that are due for reversal in the given period"""
        from accounting.models import Accrual

        reversed_count = 0
        accruals = Accrual.objects.filter(
            period=period,
            is_reversed=False,
            auto_reverse=True,
            is_posted=True,
        )

        for accrual in accruals:
            try:
                AccrualDeferralService.reverse_accrual(accrual, user=None)
                reversed_count += 1
            except Exception as e:
                import logging
                logging.getLogger('accounting').error(f"Error reversing accrual {accrual.name}: {e}")

        return reversed_count

    @staticmethod
    @transaction.atomic
    def recognize_deferrals(period):
        """Recognize deferrals for a period"""
        from accounting.models import DeferralRecognition, JournalHeader, JournalLine, TransactionSequence

        recognized_count = 0

        recognitions = DeferralRecognition.objects.filter(
            period=period,
            is_posted=False,
        ).select_related('deferral', 'deferral__account', 'deferral__counterpart_account')

        for recognition in recognitions:
            try:
                deferral = recognition.deferral
                ref = f"DEF-REC-{deferral.code}-{recognition.recognition_date.strftime('%Y%m')}"

                journal = JournalHeader.objects.create(
                    reference_number=ref,
                    description=f"Recognition: {deferral.name}",
                    posting_date=recognition.recognition_date,
                    status='Posted',
                )
                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'])

                amount = recognition.amount

                if deferral.deferral_type == 'prepaid_expense':
                    # Recognize expense: Dr Expense, Cr Prepaid Asset
                    JournalLine.objects.create(
                        header=journal, account=deferral.counterpart_account,
                        debit=amount, credit=Decimal('0.00'),
                        memo=f"Expense Recognition: {deferral.name}",
                        document_number=journal.document_number,
                    )
                    JournalLine.objects.create(
                        header=journal, account=deferral.account,
                        debit=Decimal('0.00'), credit=amount,
                        memo=f"Prepaid Amortization: {deferral.name}",
                        document_number=journal.document_number,
                    )
                else:  # deferred_revenue
                    # Recognize revenue: Dr Deferred Revenue, Cr Revenue
                    JournalLine.objects.create(
                        header=journal, account=deferral.account,
                        debit=amount, credit=Decimal('0.00'),
                        memo=f"Deferred Revenue Recognition: {deferral.name}",
                        document_number=journal.document_number,
                    )
                    JournalLine.objects.create(
                        header=journal, account=deferral.counterpart_account,
                        debit=Decimal('0.00'), credit=amount,
                        memo=f"Revenue Recognition: {deferral.name}",
                        document_number=journal.document_number,
                    )

                RecurringJournalService._update_gl(journal)

                recognition.is_posted = True
                recognition.journal_entry = journal
                recognition.save(update_fields=['is_posted', 'journal_entry'])

                deferral.remaining_amount -= amount
                deferral.current_period += 1
                update_fields = ['remaining_amount', 'current_period']
                if deferral.current_period >= deferral.recognition_periods:
                    deferral.is_fully_recognized = True
                    deferral.is_active = False
                    update_fields += ['is_fully_recognized', 'is_active']
                deferral.save(update_fields=update_fields)

                recognized_count += 1
            except Exception as e:
                import logging
                logging.getLogger('accounting').error(f"Error recognizing deferral: {e}")

        return recognized_count

    @staticmethod
    @transaction.atomic
    def recognize_deferral(deferral, user):
        """Recognize the next period for a single deferral immediately."""
        from accounting.models import DeferralRecognition, JournalHeader, JournalLine, TransactionSequence

        if not deferral.is_active:
            raise AdvancedAccountingError("Deferral is no longer active.")
        if deferral.is_fully_recognized:
            raise AdvancedAccountingError("Deferral is already fully recognized.")

        # Amount to recognize this period
        periods_remaining = deferral.recognition_periods - deferral.current_period
        if periods_remaining <= 1:
            amount = deferral.remaining_amount
        else:
            amount = deferral.recognition_amount

        if amount <= Decimal('0'):
            raise AdvancedAccountingError("No remaining amount to recognize.")

        from django.utils.timezone import now
        rec_date = now().date()
        ref = f"DEF-REC-{deferral.code}-{rec_date.strftime('%Y%m%d')}"

        journal = JournalHeader.objects.create(
            reference_number=ref,
            description=f"Recognition: {deferral.name}",
            posting_date=rec_date,
            status='Posted',
        )
        journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
        journal.save(update_fields=['document_number'])

        if deferral.deferral_type == 'prepaid_expense':
            JournalLine.objects.create(
                header=journal, account=deferral.counterpart_account,
                debit=amount, credit=Decimal('0.00'),
                memo=f"Expense Recognition: {deferral.name}",
                document_number=journal.document_number,
            )
            JournalLine.objects.create(
                header=journal, account=deferral.account,
                debit=Decimal('0.00'), credit=amount,
                memo=f"Prepaid Amortization: {deferral.name}",
                document_number=journal.document_number,
            )
        else:
            JournalLine.objects.create(
                header=journal, account=deferral.account,
                debit=amount, credit=Decimal('0.00'),
                memo=f"Deferred Revenue Recognition: {deferral.name}",
                document_number=journal.document_number,
            )
            JournalLine.objects.create(
                header=journal, account=deferral.counterpart_account,
                debit=Decimal('0.00'), credit=amount,
                memo=f"Revenue Recognition: {deferral.name}",
                document_number=journal.document_number,
            )

        RecurringJournalService._update_gl(journal)

        DeferralRecognition.objects.create(
            deferral=deferral,
            recognition_date=rec_date,
            amount=amount,
            journal_entry=journal,
            is_posted=True,
        )

        deferral.remaining_amount -= amount
        deferral.current_period += 1
        update_fields = ['remaining_amount', 'current_period']
        if deferral.current_period >= deferral.recognition_periods:
            deferral.is_fully_recognized = True
            deferral.is_active = False
            update_fields += ['is_fully_recognized', 'is_active']
        deferral.save(update_fields=update_fields)

        return journal


class PeriodClosingService:
    """Service for period opening and closing"""

    @staticmethod
    def close_period(period, user):
        """Close a budget period"""
        from accounting.models import PeriodStatus, JournalHeader

        # Check for unposted journals in the period date range
        unposted = JournalHeader.objects.filter(
            posting_date__gte=period.start_date,
            posting_date__lte=period.end_date,
            status__in=['Draft', 'Approved'],
        )

        if unposted.exists():
            raise AdvancedAccountingError(
                f"Cannot close period with {unposted.count()} unposted journals. "
                "Post or delete them first."
            )

        # Create or update period status
        status_obj, _ = PeriodStatus.objects.get_or_create(period=period)
        status_obj.status = 'Closed'
        status_obj.closed_by = user
        status_obj.closed_date = timezone.now()
        status_obj.allow_journal_entry = False
        status_obj.allow_invoice = False
        status_obj.allow_payment = False
        status_obj.save()

        # Also close the budget period itself
        period.status = 'CLOSED'
        period.allow_postings = False
        period.closed_by = user
        period.closed_date = timezone.now()
        period.save()

        return status_obj

    @staticmethod
    def open_period(period, user):
        """Reopen a closed period"""
        from accounting.models import PeriodStatus

        status_obj = PeriodStatus.objects.get(period=period)

        if status_obj.status == 'Locked':
            raise AdvancedAccountingError("Cannot reopen a locked period. Unlock first.")

        status_obj.status = 'Open'
        status_obj.closed_by = None
        status_obj.closed_date = None
        status_obj.allow_journal_entry = True
        status_obj.allow_invoice = True
        status_obj.allow_payment = True
        status_obj.save()

        # Also reopen the budget period
        period.status = 'OPEN'
        period.allow_postings = True
        period.save()

        return status_obj

    @staticmethod
    def lock_period(period, user, reason=''):
        """Lock a period permanently"""
        from accounting.models import PeriodStatus

        status_obj, _ = PeriodStatus.objects.get_or_create(period=period)
        status_obj.status = 'Locked'
        status_obj.closed_by = user
        status_obj.closed_date = timezone.now()
        status_obj.lock_reason = reason
        status_obj.allow_journal_entry = False
        status_obj.allow_invoice = False
        status_obj.allow_payment = False
        status_obj.save()

        period.status = 'LOCKED'
        period.allow_postings = False
        period.allow_adjustments = False
        period.locked_by = user
        period.locked_date = timezone.now()
        period.save()

        return status_obj


class YearEndClosingService:
    """Service for year-end closing — closes temporary accounts to retained earnings"""

    @staticmethod
    @transaction.atomic
    def close_year(fiscal_year, user):
        """Perform year-end closing"""
        from accounting.models import (
            YearEndClosing, RetainedEarnings, JournalHeader, JournalLine,
            Account, GLBalance, TransactionSequence,
        )

        # Check if already closed
        if YearEndClosing.objects.filter(fiscal_year=fiscal_year, status='Posted').exists():
            raise AdvancedAccountingError(f"Year {fiscal_year} is already closed")

        # Calculate totals from GLBalance
        revenue_accounts = Account.objects.filter(account_type='Income')
        expense_accounts = Account.objects.filter(account_type='Expense')

        total_revenue = Decimal('0.00')
        total_expenses = Decimal('0.00')

        for account in revenue_accounts:
            bal = GLBalance.objects.filter(
                account=account, fiscal_year=fiscal_year,
            ).aggregate(
                total=Sum('credit_balance') - Sum('debit_balance')
            )['total'] or Decimal('0.00')
            total_revenue += Decimal(str(bal))

        for account in expense_accounts:
            bal = GLBalance.objects.filter(
                account=account, fiscal_year=fiscal_year,
            ).aggregate(
                total=Sum('debit_balance') - Sum('credit_balance')
            )['total'] or Decimal('0.00')
            total_expenses += Decimal(str(bal))

        net_income = total_revenue - total_expenses

        # Get or create Retained Earnings account
        retained_earnings = Account.objects.filter(
            account_type='Equity', name__icontains='Retained Earnings',
        ).first()
        if not retained_earnings:
            retained_earnings = Account.objects.create(
                code='30200000', name='Retained Earnings',
                account_type='Equity', is_active=True,
            )

        # Create closing journal
        closing_date = timezone.now().date()
        journal = JournalHeader.objects.create(
            reference_number=f"YEC-{fiscal_year}",
            description=f"Year-End Closing {fiscal_year}",
            posting_date=closing_date,
            status='Posted',
        )
        journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
        journal.save(update_fields=['document_number'])

        # Close revenue accounts (debit them to zero)
        for account in revenue_accounts:
            bal = GLBalance.objects.filter(
                account=account, fiscal_year=fiscal_year,
            ).aggregate(
                total=Sum('credit_balance') - Sum('debit_balance')
            )['total'] or Decimal('0.00')
            bal = Decimal(str(bal))
            if bal > 0:
                JournalLine.objects.create(
                    header=journal, account=account,
                    debit=bal, credit=Decimal('0.00'),
                    memo=f"Close {account.name}",
                    document_number=journal.document_number,
                )
            elif bal < 0:
                JournalLine.objects.create(
                    header=journal, account=account,
                    debit=Decimal('0.00'), credit=abs(bal),
                    memo=f"Close {account.name}",
                    document_number=journal.document_number,
                )

        # Close expense accounts (credit them to zero)
        for account in expense_accounts:
            bal = GLBalance.objects.filter(
                account=account, fiscal_year=fiscal_year,
            ).aggregate(
                total=Sum('debit_balance') - Sum('credit_balance')
            )['total'] or Decimal('0.00')
            bal = Decimal(str(bal))
            if bal > 0:
                JournalLine.objects.create(
                    header=journal, account=account,
                    debit=Decimal('0.00'), credit=bal,
                    memo=f"Close {account.name}",
                    document_number=journal.document_number,
                )
            elif bal < 0:
                JournalLine.objects.create(
                    header=journal, account=account,
                    debit=abs(bal), credit=Decimal('0.00'),
                    memo=f"Close {account.name}",
                    document_number=journal.document_number,
                )

        # Post net income to retained earnings
        if net_income > 0:
            JournalLine.objects.create(
                header=journal, account=retained_earnings,
                debit=Decimal('0.00'), credit=net_income,
                memo=f"Net Income for {fiscal_year}",
                document_number=journal.document_number,
            )
        elif net_income < 0:
            JournalLine.objects.create(
                header=journal, account=retained_earnings,
                debit=abs(net_income), credit=Decimal('0.00'),
                memo=f"Net Loss for {fiscal_year}",
                document_number=journal.document_number,
            )

        # Update GL from closing journal
        RecurringJournalService._update_gl(journal)

        # Create year-end closing record
        closing = YearEndClosing.objects.create(
            fiscal_year=fiscal_year,
            closing_date=closing_date,
            closing_journal_id=journal.id,
            revenue_total=total_revenue,
            expense_total=total_expenses,
            net_income=net_income,
            status='Posted',
            created_by=user,
        )

        # Create retained earnings record
        previous_re = RetainedEarnings.objects.filter(
            fiscal_year__lt=fiscal_year,
        ).order_by('-fiscal_year').first()

        beginning = previous_re.ending_balance if previous_re else Decimal('0.00')

        RetainedEarnings.objects.create(
            fiscal_year=fiscal_year,
            beginning_balance=beginning,
            net_income=net_income,
            dividends=Decimal('0.00'),
            ending_balance=beginning + net_income,
            closing_journal=journal,
        )

        # PF-12: Carry forward Balance Sheet account balances to the new fiscal year.
        # Create opening journal entries for Asset, Liability, and Equity accounts.
        new_year = fiscal_year + 1
        bs_account_types = ['Asset', 'Liability', 'Equity']
        bs_accounts = Account.objects.filter(account_type__in=bs_account_types, is_active=True)

        opening_journal = JournalHeader.objects.create(
            reference_number=f"OB-{new_year}",
            description=f"Opening Balances carried forward from {fiscal_year}",
            posting_date=closing_date.replace(year=new_year, month=1, day=1) if closing_date.month <= 12 else closing_date,
            status='Posted',
        )
        opening_journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
        opening_journal.save(update_fields=['document_number'])

        has_opening_lines = False
        for account in bs_accounts:
            bal = GLBalance.objects.filter(
                account=account, fiscal_year=fiscal_year,
            ).aggregate(
                net=Sum('debit_balance') - Sum('credit_balance')
            )['net'] or Decimal('0.00')
            bal = Decimal(str(bal))
            if bal == 0:
                continue
            has_opening_lines = True
            if bal > 0:
                JournalLine.objects.create(
                    header=opening_journal, account=account,
                    debit=bal, credit=Decimal('0.00'),
                    memo=f"Opening balance {new_year} from {account.name}",
                    document_number=opening_journal.document_number,
                )
            else:
                JournalLine.objects.create(
                    header=opening_journal, account=account,
                    debit=Decimal('0.00'), credit=abs(bal),
                    memo=f"Opening balance {new_year} from {account.name}",
                    document_number=opening_journal.document_number,
                )

        if has_opening_lines:
            RecurringJournalService._update_gl(opening_journal)
        else:
            opening_journal.delete()

        return closing


class CurrencyRevaluationService:
    """Service for foreign currency revaluation"""

    @staticmethod
    @transaction.atomic
    def revaluate(currency, exchange_rate, revaluation_date, user):
        """Perform currency revaluation for all accounts denominated in this currency"""
        from accounting.models import (
            CurrencyRevaluation,
        )

        old_rate = currency.exchange_rate
        rate_diff = exchange_rate - old_rate

        if rate_diff == 0:
            raise AdvancedAccountingError("New exchange rate is the same as current rate")

        # Update currency rate
        currency.exchange_rate = exchange_rate
        currency.save(update_fields=['exchange_rate'])

        # Create revaluation record
        reval = CurrencyRevaluation.objects.create(
            revaluation_date=revaluation_date,
            currency=currency,
            exchange_rate=exchange_rate,
            total_assets=Decimal('0.00'),
            total_liabilities=Decimal('0.00'),
            unrealized_gain=max(Decimal('0.00'), rate_diff * 100),
            unrealized_loss=max(Decimal('0.00'), -rate_diff * 100),
            status='Calculated',
        )

        return reval
