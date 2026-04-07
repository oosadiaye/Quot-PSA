"""
Payroll Posting Service — accounting domain.

Handles GL posting for all payroll/HRM transactions:
Payroll Runs and Payroll Journal Reversals.
"""

import logging
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from accounting.models import JournalHeader, JournalLine
from accounting.services.base_posting import BasePostingService, TransactionPostingError, get_gl_account

logger = logging.getLogger(__name__)


class PayrollPostingService(BasePostingService):
    """
    GL posting service for the Payroll/HRM domain.
    """

    @staticmethod
    @transaction.atomic
    def post_payroll_run(payroll_run):
        """
        Post a Payroll Run to the GL.

        Creates journal entry for:
        - Salary Expense (debit) — total gross
        - Payroll Liability (credit) — net pay to employees
        - Tax Payable (credit) — tax deductions
        - Pension Payable (credit) — pension deductions

        Args:
            payroll_run: PayrollRun instance
        """
        if payroll_run.status != 'Approved':
            raise TransactionPostingError("Payroll must be approved before posting")

        PayrollPostingService._check_duplicate_posting(
            f"PAYROLL-{payroll_run.id}"
        )
        if hasattr(payroll_run, 'pay_date') and payroll_run.pay_date:
            PayrollPostingService._validate_fiscal_period(payroll_run.pay_date)

        # Resolve GL accounts: per-run FK override → DEFAULT_GL_ACCOUNTS fallback
        salary_expense = (
            (payroll_run.payroll_expense_account_id and payroll_run.payroll_expense_account)
            or get_gl_account('SALARY_EXPENSE', 'Expense', 'Salary')
        )
        if not salary_expense:
            raise TransactionPostingError("Salary expense account not found")

        payroll_liability = (
            (payroll_run.payroll_liability_account_id and payroll_run.payroll_liability_account)
            or get_gl_account('PAYROLL_LIABILITY', 'Liability', 'Payroll')
        )
        if not payroll_liability:
            raise TransactionPostingError("Payroll liability account not found")

        journal_number = f"PR-{payroll_run.run_number or timezone.now().strftime('%Y%m%d')}"

        # HR-M4: Build per-department salary totals BEFORE creating journal lines so
        # we can post one DR line per cost-centre (MDA/department) instead of a single
        # summary line. This replaces the defunct JournalLineCostCenter sub-allocation
        # approach and produces standard multi-dimensional GL entries.
        dept_totals = {}
        unallocated_gross = Decimal(str(payroll_run.total_gross or 0))
        try:
            for line in payroll_run.lines.select_related('employee__department').all():
                dept = getattr(line.employee, 'department', None) if line.employee else None
                line_gross = Decimal(str(line.gross_salary or 0))
                if dept and getattr(dept, 'cost_center', None) and line_gross > 0:
                    dept_id = dept.id
                    if dept_id not in dept_totals:
                        dept_totals[dept_id] = {
                            'cost_center': dept.cost_center,
                            'label': str(dept.cost_center),
                            'gross': Decimal('0.00'),
                        }
                    dept_totals[dept_id]['gross'] += line_gross
                    unallocated_gross -= line_gross
        except Exception:
            # If employee/department traversal fails fall back to single summary line
            dept_totals = {}
            unallocated_gross = Decimal(str(payroll_run.total_gross or 0))

        total_gross = Decimal(str(payroll_run.total_gross or 0))
        total_deductions = Decimal(str(payroll_run.total_deductions or 0))
        total_net = Decimal(str(payroll_run.total_net or 0)) or (total_gross - total_deductions)

        # Aggregate tax and pension from payroll lines
        line_totals = payroll_run.lines.aggregate(
            total_tax=Sum('tax_deduction'),
            total_pension=Sum('pension_deduction'),
        )
        total_tax = Decimal(str(line_totals['total_tax'] or 0))
        total_pension = Decimal(str(line_totals['total_pension'] or 0))
        total_other = total_deductions - total_tax - total_pension

        journal = JournalHeader.objects.create(
            reference_number=journal_number,
            description=f"Payroll Run: {payroll_run.run_number}",
            posting_date=payroll_run.period.payment_date,
            status='Posted',
            created_by=payroll_run.created_by,
            source_module='hrm',
            source_document_id=payroll_run.id,
            posted_at=timezone.now(),
        )

        # Debit: Salary Expense — one line per department cost centre, plus a
        # catch-all line for employees not linked to a department.
        if dept_totals:
            for dept_data in dept_totals.values():
                if dept_data['gross'] > 0:
                    JournalLine.objects.create(
                        header=journal,
                        account=salary_expense,
                        debit=dept_data['gross'],
                        credit=Decimal('0.00'),
                        cost_center=dept_data['cost_center'],
                        memo=f"Salary Expense — {dept_data['label']}",
                    )
            if unallocated_gross > 0:
                JournalLine.objects.create(
                    header=journal,
                    account=salary_expense,
                    debit=unallocated_gross,
                    credit=Decimal('0.00'),
                    memo="Salary Expense — Unallocated",
                )
        else:
            # No department breakdown available — single summary debit line
            JournalLine.objects.create(
                header=journal,
                account=salary_expense,
                debit=total_gross,
                credit=Decimal('0.00'),
                memo="Salary Expense",
            )

        # Credit: Payroll Liability (net pay)
        JournalLine.objects.create(
            header=journal,
            account=payroll_liability,
            debit=Decimal('0.00'),
            credit=total_net,
            memo="Net Pay - Payroll Liability"
        )

        # Credit: Tax Payable
        if total_tax > 0:
            tax_account = get_gl_account('TAX_PAYABLE', 'Liability', 'Tax')
            if not tax_account:
                raise TransactionPostingError(
                    "Tax Payable account not found. "
                    "Configure DEFAULT_GL_ACCOUNTS['TAX_PAYABLE'] in settings."
                )
            JournalLine.objects.create(
                header=journal,
                account=tax_account,
                debit=Decimal('0.00'),
                credit=total_tax,
                memo="Tax Deductions Payable"
            )

        # Credit: Pension Payable — per-run FK override → DEFAULT_GL_ACCOUNTS fallback
        if total_pension > 0:
            pension_account = (
                (payroll_run.pension_account_id and payroll_run.pension_account)
                or get_gl_account('PENSION_PAYABLE', 'Liability', 'Pension')
            )
            if not pension_account:
                raise TransactionPostingError(
                    "Pension Payable account not found. "
                    "Configure DEFAULT_GL_ACCOUNTS['PENSION_PAYABLE'] in settings."
                )
            JournalLine.objects.create(
                header=journal,
                account=pension_account,
                debit=Decimal('0.00'),
                credit=total_pension,
                memo="Pension Deductions Payable"
            )

        # Credit: Other deductions to payroll liability
        if total_other > 0:
            JournalLine.objects.create(
                header=journal,
                account=payroll_liability,
                debit=Decimal('0.00'),
                credit=total_other,
                memo="Other Payroll Deductions"
            )

        PayrollPostingService._validate_journal_balanced(journal)
        PayrollPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def reverse_payroll_journal(original_journal, reversal_date=None, reason=''):
        """
        HR-L1: Create month-end reversal entries for payroll.

        Args:
            original_journal: The original JournalHeader to reverse
            reversal_date: Date for the reversal entry (defaults to today)
            reason: Reason for the reversal

        Returns:
            JournalHeader: The reversal journal entry
        """
        if reversal_date is None:
            reversal_date = timezone.now().date()

        PayrollPostingService._validate_fiscal_period(reversal_date)

        # Create reversal journal
        reversal_journal = JournalHeader.objects.create(
            reference_number=f"RVS-{original_journal.reference_number}",
            description=f"REVERSAL: {original_journal.description} - {reason}",
            posting_date=reversal_date,
            status='Posted',
            source_module='hrm',
            source_document_id=original_journal.source_document_id,
            posted_at=timezone.now(),
        )

        # Create reversed lines
        for line in original_journal.lines.all():
            # Swap debits and credits
            JournalLine.objects.create(
                header=reversal_journal,
                account=line.account,
                debit=line.credit,
                credit=line.debit,
                memo=f"Reversal: {line.memo}"
            )

        # Mark original journal as reversed
        original_journal.is_reversed = True
        original_journal.save(update_fields=['is_reversed'])

        # Update GL balances
        PayrollPostingService._validate_journal_balanced(reversal_journal)
        PayrollPostingService._update_gl_balances(reversal_journal)

        logger.info(f"Created payroll reversal journal {reversal_journal.reference_number} for {original_journal.reference_number}")

        return reversal_journal
