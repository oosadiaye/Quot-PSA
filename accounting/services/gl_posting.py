from django.db import transaction
from django.db.models import F, Q
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


# InterCompanyPostingService has been removed — this is a public-sector
# IFMIS, not a multi-company commercial ERP. Inter-company posting is
# not a supported workflow. Parastatals that need cross-entity posting
# should model it as inter-MDA transfers via the standard journal flow.


class ConsolidationService:
    """Service for consolidation operations"""

    @staticmethod
    def run_consolidation(group_id, period_id, user):
        """Run consolidation for a group in a given period.

        Two-phase atomicity: the run row is created in its own
        transaction so it persists regardless of whether the work
        succeeds; the work itself runs in a savepoint so a failure
        rolls back partial computation without poisoning the outer
        transaction (which the prior single @transaction.atomic
        decorator caused — a failure marked the transaction for
        rollback and the ``run.status='Failed'; run.save()`` in the
        except handler raised ``TransactionManagementError``, hiding
        the real error from the operator).
        """
        from accounting.models import ConsolidationRun, ConsolidationGroup, FiscalPeriod
        from django.db.models import Sum
        from accounting.models import JournalHeader, CustomerInvoice, VendorInvoice

        try:
            group = ConsolidationGroup.objects.get(id=group_id)
            period = FiscalPeriod.objects.get(id=period_id)
        except (ConsolidationGroup.DoesNotExist, FiscalPeriod.DoesNotExist):
            return {'success': False, 'message': 'Group or period not found'}

        # Phase 1: create the run row in its own transaction. This row
        # must survive any subsequent failure so operators can see the
        # failed run in the audit log.
        with transaction.atomic():
            run = ConsolidationRun.objects.create(
                group=group,
                period=period,
                status='In Progress',
                run_by=user
            )

        # Phase 2: run the computation in a savepoint. On failure the
        # savepoint rolls back cleanly and the outer ``run`` row update
        # in the except handler executes against a healthy transaction.
        try:
            with transaction.atomic():
                # Materialise the companies list ONCE. The previous code
                # iterated the queryset (1 query) and then called
                # .count() on it again (a second query against the same
                # rows) — and inside the loop ran 2 aggregate queries
                # per company without actually filtering journals by
                # company, producing identical totals N times. The new
                # shape: list() once, single aggregate outside the loop.
                companies = list(group.companies.all())
                total_assets = Decimal('0')
                total_liabilities = Decimal('0')
                eliminations = []

                # Single aggregate for revenue and expenses across the
                # whole period. JournalHeader in this codebase has no
                # ``company`` FK (consolidation is by MDA, not company),
                # so per-company filtering is a no-op; running the
                # aggregate once is both correct and N times cheaper.
                period_journals = JournalHeader.objects.filter(
                    posting_date__gte=period.start_date,
                    posting_date__lte=period.end_date,
                    status='Posted',
                )
                totals = period_journals.aggregate(
                    revenue=Sum(
                        'journalline__debit',
                        filter=Q(journalline__account__account_type='Income'),
                    ),
                    expenses=Sum(
                        'journalline__credit',
                        filter=Q(journalline__account__account_type='Expense'),
                    ),
                )
                total_revenue = totals['revenue'] or Decimal('0')
                total_expenses = totals['expenses'] or Decimal('0')

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
                    'companies_count': len(companies),
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
            # Outer transaction is clean (the savepoint rolled back),
            # so we can safely update the run row to record the failure.
            run.status = 'Failed'
            run.error_message = str(e)
            run.save()
            return {'success': False, 'message': str(e)}
