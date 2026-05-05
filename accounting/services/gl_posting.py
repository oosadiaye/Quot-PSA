from django.db import transaction
from django.db.models import F
from django.utils import timezone
from decimal import Decimal
from accounting.services.base_posting import BasePostingService, get_gl_account

# Alias for backward-compatibility with any callers inside this module
# that reference TransactionPostingService._validate_journal_balanced.
TransactionPostingService = BasePostingService


def update_gl_from_journal(journal, fund=None, function=None, program=None, geo=None):
    """
    Atomic GL balance update using F() expressions to prevent race conditions.

    Uses UPDATE ... SET debit_balance = debit_balance + X instead of
    read-modify-write, which is safe under concurrent access.

    DOUBLE-ENTRY GUARD (mandatory): refuses to update GLBalance unless
    SUM(debits) == SUM(credits) on the supplied journal. This is the
    chokepoint that enforces the invariant for every posting flow —
    AR / AP / Payment / Receipt / Manual JE / GRN / Invoice
    Verification / IPC / Vendor Advance / Bank Transfer / Revenue.
    Bypass-by-skipping-the-validator-at-the-callsite is no longer
    possible.
    """
    from accounting.models import GLBalance
    from accounting.services.base_posting import BasePostingService

    # Mandatory double-entry assertion before any GL state mutates.
    BasePostingService.assert_balanced(journal)

    fiscal_year = journal.posting_date.year
    period = journal.posting_date.month
    j_fund = fund or journal.fund
    j_function = function or journal.function
    j_program = program or journal.program
    j_geo = geo or journal.geo
    # S3-05 — carry the MDA dimension onto each GLBalance bucket so
    # per-MDA reports (Trial Balance, Balance Sheet, Budget vs Actual)
    # attribute the spend correctly. The legacy per-line ``cost_center``
    # override has been removed from this project; the journal header's
    # MDA is now the single source.
    j_mda_header = journal.mda

    for line in journal.lines.select_related('account').all():
        debit = line.debit or Decimal('0.00')
        credit = line.credit or Decimal('0.00')
        line_mda = j_mda_header

        # Race-safe pattern:
        #   1. ``get_or_create`` with zero defaults atomically reserves
        #      the (account, dimensions, fy, period) bucket. The DB
        #      uniqueness constraint serialises concurrent inserts —
        #      only one thread wins the INSERT; the others fall
        #      through to a regular SELECT.
        #   2. A SINGLE ``UPDATE ... SET balance = balance + delta``
        #      then increments the row using F() expressions. Both
        #      the just-created (zero-balance) and the existing-row
        #      paths use the same additive update, so there's no
        #      branch where a non-additive UPDATE can stomp a
        #      concurrent increment.
        #
        # The previous implementation took a non-additive ``UPDATE
        # SET balance = <delta>`` on the just-created path, which
        # under concurrency could overwrite another thread's
        # increment.
        GLBalance.objects.get_or_create(
            account=line.account,
            fund=j_fund,
            function=j_function,
            program=j_program,
            geo=j_geo,
            mda=line_mda,
            fiscal_year=fiscal_year,
            period=period,
            defaults={
                'debit_balance': Decimal('0.00'),
                'credit_balance': Decimal('0.00'),
            },
        )
        GLBalance.objects.filter(
            account=line.account,
            fund=j_fund,
            function=j_function,
            program=j_program,
            geo=j_geo,
            mda=line_mda,
            fiscal_year=fiscal_year,
            period=period,
        ).update(
            debit_balance=F('debit_balance') + debit,
            credit_balance=F('credit_balance') + credit,
        )

    # ── Bust the IPSAS report cache for this fiscal year ───────────────
    # Every posting path (manual JE, AP/AR invoice, Payment, PV, IPC
    # accrual, Vendor Advance, Asset capitalisation/depreciation, etc.)
    # converges on this function. Bumping the generation counter HERE
    # means every IPSAS report (Financial Position, Financial
    # Performance, Cash Flow, Changes in Net Assets, Notes,
    # Budget vs Actual, Budget Performance, Revenue Performance,
    # TSA Cash Position, Functional / Programme / Geographic / Fund
    # Performance) drops its cached entry and recomputes on next read
    # — without any caller having to remember to invalidate.
    try:
        from accounting.services.report_cache import invalidate_period_reports
        invalidate_period_reports(fiscal_year=fiscal_year)
    except Exception:  # noqa: BLE001 — cache invalidation is best-effort
        pass


# InterCompanyPostingService and ConsolidationService — REMOVED for public sector
# These classes are disabled but preserved for reference in case parastatals need them.
class _DisabledInterCompanyPostingService:
    """Service for handling inter-company posting operations"""

    @staticmethod
    @transaction.atomic
    def post_ic_invoice(ic_invoice):
        """Auto-create journal entries for IC invoice"""
        from accounting.models import JournalHeader, JournalLine, InterCompanyConfig

        BasePostingService._validate_fiscal_period(timezone.now().date())

        if ic_invoice.auto_posted:
            return {'success': False, 'message': 'Invoice already posted'}

        config = InterCompanyConfig.objects.filter(
            company=ic_invoice.from_company,
            partner_company=ic_invoice.to_company,
            auto_post=True
        ).first()

        if not config:
            return {'success': False, 'message': 'No IC config found'}

        if not config.ar_account or not config.revenue_account:
            return {'success': False, 'message': 'AR or Revenue account not configured'}

        journal = JournalHeader.objects.create(
            description=f"IC Invoice {ic_invoice.invoice_number}",
            posting_date=timezone.now().date(),
            status='Posted',
            source_module='intercompany',
            source_document_id=ic_invoice.pk,
            posted_at=timezone.now(),
        )

        JournalLine.objects.create(
            header=journal,
            account=config.ar_account,
            debit=ic_invoice.total_amount,
            credit=Decimal('0'),
            description=f"IC Receivable from {ic_invoice.to_company.name}"
        )

        JournalLine.objects.create(
            header=journal,
            account=config.revenue_account,
            debit=Decimal('0'),
            credit=ic_invoice.total_amount,
            description=f"IC Revenue from {ic_invoice.to_company.name}"
        )

        TransactionPostingService._validate_journal_balanced(journal)
        update_gl_from_journal(journal)

        ic_invoice.auto_posted = True
        ic_invoice.status = 'Approved'
        ic_invoice.linked_journal = journal
        ic_invoice.save()

        return {'success': True, 'message': 'IC invoice posted', 'journal_id': journal.id}

    @staticmethod
    @transaction.atomic
    def post_ic_transfer(ic_transfer):
        """Auto-post inventory transfer between companies"""
        from accounting.models import JournalHeader, JournalLine, InterCompanyConfig

        BasePostingService._validate_fiscal_period(ic_transfer.transfer_date)

        if ic_transfer.auto_posted:
            return {'success': False, 'message': 'Transfer already posted'}

        config = InterCompanyConfig.objects.filter(
            company=ic_transfer.from_company,
            partner_company=ic_transfer.to_company,
            auto_post=True
        ).first()

        if not config or not config.expense_account:
            return {'success': False, 'message': 'No IC config found'}

        journal = JournalHeader.objects.create(
            description=f"IC Transfer {ic_transfer.transfer_number}",
            posting_date=ic_transfer.transfer_date,
            status='Posted',
            source_module='intercompany',
            source_document_id=ic_transfer.pk,
            posted_at=timezone.now(),
        )

        JournalLine.objects.create(
            header=journal,
            account=config.expense_account,
            debit=ic_transfer.total_value,
            credit=Decimal('0'),
            description=f"IC Transfer from {ic_transfer.from_company.name}"
        )

        # Credit inter-company payable (AP) to balance the journal.
        # This records the liability to the source company until settlement.
        ap_account = (
            getattr(config, 'ap_account', None)
            or get_gl_account('ACCOUNTS_PAYABLE', 'Liability', 'Payable')
        )
        if not ap_account:
            raise ValueError(
                "Accounts Payable account not found for IC transfer credit leg. "
                "Configure ACCOUNTS_PAYABLE in DEFAULT_GL_ACCOUNTS."
            )
        JournalLine.objects.create(
            header=journal,
            account=ap_account,
            debit=Decimal('0'),
            credit=ic_transfer.total_value,
            description=f"IC Payable to {ic_transfer.from_company.name}"
        )

        TransactionPostingService._validate_journal_balanced(journal)
        update_gl_from_journal(journal)

        ic_transfer.auto_posted = True
        ic_transfer.status = 'In Transit'
        ic_transfer.save()

        return {'success': True, 'message': 'IC transfer posted'}

    @staticmethod
    @transaction.atomic
    def post_ic_cash_transfer(ic_cash):
        """Auto-post cash transfer between companies"""
        from accounting.models import JournalHeader, JournalLine, BankAccount

        BasePostingService._validate_fiscal_period(ic_cash.transfer_date)

        if ic_cash.auto_posted:
            return {'success': False, 'message': 'Cash transfer already posted'}

        journal = JournalHeader.objects.create(
            description=f"IC Cash Transfer {ic_cash.transfer_number}",
            posting_date=ic_cash.transfer_date,
            status='Posted',
            source_module='intercompany',
            source_document_id=ic_cash.pk,
            posted_at=timezone.now(),
        )

        # PF-17: Look up the actual cash/bank GL account instead of
        # hardcoding account_id=1. Prefer the company's default bank
        # account, then fall back to settings, then to any active bank account.
        from django.conf import settings as django_settings
        default_gl = getattr(django_settings, 'DEFAULT_GL_ACCOUNTS', {})

        cash_account = None
        default_bank = BankAccount.objects.filter(is_default=True, is_active=True).first()
        if default_bank and default_bank.gl_account:
            cash_account = default_bank.gl_account
        if not cash_account:
            from accounting.models import Account
            cash_code = default_gl.get('CASH_ACCOUNT', '10100000')
            cash_account = Account.objects.filter(code=cash_code).first()
        if not cash_account:
            from accounting.models import Account
            cash_account = Account.objects.filter(account_type='Asset', name__icontains='Cash').first()
        if not cash_account:
            from accounting.models import Account
            cash_account = Account.objects.filter(account_type='Asset').first()
            if not cash_account:
                raise ValueError("GL posting failed: no cash/asset account found for inter-company transfer")

        JournalLine.objects.create(
            header=journal,
            account=cash_account,
            debit=ic_cash.amount,
            credit=Decimal('0'),
            description=f"Cash out to {ic_cash.to_company.name}"
        )

        JournalLine.objects.create(
            header=journal,
            account=cash_account,
            debit=Decimal('0'),
            credit=ic_cash.amount,
            description=f"Cash in from {ic_cash.from_company.name}"
        )

        TransactionPostingService._validate_journal_balanced(journal)
        update_gl_from_journal(journal)

        ic_cash.auto_posted = True
        ic_cash.status = 'Completed'
        ic_cash.save()

        return {'success': True, 'message': 'Cash transfer posted'}


class ConsolidationService:
    """Service for consolidation operations"""

    @staticmethod
    @transaction.atomic
    def run_consolidation(group_id, period_id, user):
        """Run consolidation for a group in a given period"""
        from accounting.models import ConsolidationRun, ConsolidationGroup, FiscalPeriod
        from django.db.models import Sum
        from accounting.models import JournalHeader, CustomerInvoice, VendorInvoice

        try:
            group = ConsolidationGroup.objects.get(id=group_id)
            period = FiscalPeriod.objects.get(id=period_id)
        except (ConsolidationGroup.DoesNotExist, FiscalPeriod.DoesNotExist):
            return {'success': False, 'message': 'Group or period not found'}

        run = ConsolidationRun.objects.create(
            group=group,
            period=period,
            status='In Progress',
            run_by=user
        )

        try:
            companies = group.companies.all()
            total_assets = Decimal('0')
            total_liabilities = Decimal('0')
            total_revenue = Decimal('0')
            total_expenses = Decimal('0')
            eliminations = []

            for company in companies:
                journals = JournalHeader.objects.filter(
                    posting_date__gte=period.start_date,
                    posting_date__lte=period.end_date,
                    status='Posted'
                )

                company_revenue = journals.filter(journalline__account__account_type='Income').aggregate(
                    total=Sum('journalline__debit')
                )['total'] or Decimal('0')

                company_expenses = journals.filter(journalline__account__account_type='Expense').aggregate(
                    total=Sum('journalline__credit')
                )['total'] or Decimal('0')

                total_revenue += company_revenue
                total_expenses += company_expenses

            ic_receivables = CustomerInvoice.objects.filter(
                status__in=['Partially Paid', 'Paid']
            ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

            ic_payables = VendorInvoice.objects.filter(
                status__in=['Partially Paid', 'Paid']
            ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

            elimination_amount = min(ic_receivables, ic_payables)
            eliminations.append({
                'type': 'IC Elimination',
                'amount': str(elimination_amount),
                'description': 'Inter-company receivables/payables elimination'
            })

            total_equity = total_revenue - total_expenses

            run.total_assets = total_assets
            run.total_liabilities = total_liabilities
            run.total_equity = total_equity
            run.total_revenue = total_revenue
            run.total_expenses = total_expenses
            run.elimination_entries = eliminations
            run.consolidated_data = {
                'companies_count': companies.count(),
                'period': f'FY{period.fiscal_year} P{period.period_number}'
            }
            run.status = 'Completed'
            run.save()

            return {
                'success': True,
                'message': 'Consolidation completed',
                'run_id': run.id,
                'total_revenue': str(total_revenue),
                'total_expenses': str(total_expenses)
            }

        except Exception as e:
            run.status = 'Failed'
            run.error_message = str(e)
            run.save()
            return {'success': False, 'message': str(e)}
