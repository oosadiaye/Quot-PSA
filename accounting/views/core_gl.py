from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from core.permissions import IsApprover
from django.db.models import Sum, DecimalField
from django.db.models.functions import Coalesce
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
import pandas as pd
from django.utils import timezone
from .common import AccountingPagination
from ..models import (
    Account, JournalHeader, JournalLine, Currency, GLBalance, MDA,
    ExchangeRateHistory, AccountingSettings, TransactionSequence,
)
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from ..filters import JournalFilter
from ..serializers import (
    AccountSerializer, JournalHeaderSerializer, JournalDetailSerializer,
    CurrencySerializer, GLBalanceSerializer, MDASerializer,
    AccountingSettingsSerializer,
)


class AccountViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    filterset_fields = ['account_type', 'is_active', 'is_reconciliation', 'reconciliation_type']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination

    def destroy(self, request, *args, **kwargs):
        """Override destroy to catch PROTECT errors and return a clean 400."""
        instance = self.get_object()
        if instance.journalline_set.exists():
            return Response(
                {'detail': f'Cannot delete account "{instance.code} - {instance.name}" because it has journal entries.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.query_params.get('include_inactive'):
            queryset = queryset.filter(is_active=True)
        # Annotate total debit/credit from GLBalance to avoid N+1 in serializer
        queryset = queryset.annotate(
            _total_debit=Coalesce(Sum('glbalance__debit_balance'), Decimal('0'), output_field=DecimalField()),
            _total_credit=Coalesce(Sum('glbalance__credit_balance'), Decimal('0'), output_field=DecimalField()),
        )
        return queryset

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download a CSV template for account imports."""
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['code', 'name', 'account_type', 'is_active', 'is_reconciliation', 'reconciliation_type'])
        writer.writerow(['10100000', 'Cash and Cash Equivalents', 'Asset', 'true', 'true', 'bank_accounting'])
        writer.writerow(['10200000', 'Accounts Receivable', 'Asset', 'true', 'true', 'accounts_receivable'])
        writer.writerow(['20100000', 'Accounts Payable', 'Liability', 'true', 'true', 'accounts_payable'])
        writer.writerow(['30100000', 'Fund Balance', 'Equity', 'true', 'false', ''])
        writer.writerow(['40100000', 'Sales Revenue', 'Income', 'true', 'false', ''])
        writer.writerow(['60100000', 'Salaries and Wages', 'Expense', 'true', 'false', ''])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="account_import_template.csv"'
        return response

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        """Import accounts from CSV/Excel file."""
        file = request.FILES.get('file')
        if not file:
            return Response(
                {"error": "A CSV or Excel file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024  # 5MB
        if file.size > MAX_IMPORT_FILE_SIZE:
            return Response(
                {"error": "File too large. Maximum 5MB allowed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file, nrows=10000)
            else:
                df = pd.read_csv(file, nrows=10000)
        except Exception as e:
            return Response(
                {"error": f"Failed to parse file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Normalize column names
        df.columns = df.columns.str.strip().str.lower()

        required_columns = {'code', 'name', 'account_type'}
        missing = required_columns - set(df.columns)
        if missing:
            return Response(
                {"error": f"Missing required columns: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_types = {'Asset', 'Liability', 'Equity', 'Income', 'Expense'}
        created_count = 0
        skipped_count = 0
        errors = []

        # Load accounting settings for digit/series enforcement
        from ..models import AccountingSettings
        acct_settings = AccountingSettings.objects.first()

        for index, row in df.iterrows():
            row_num = index + 2  # header row + 0-based index
            try:
                code = str(row['code']).strip()
                name = str(row['name']).strip()
                account_type = str(row['account_type']).strip()

                if not code or len(code) > 20:
                    errors.append(f"Row {row_num}: Invalid code '{code}' (must be 1-20 characters).")
                    continue

                if not name or len(name) > 150:
                    errors.append(f"Row {row_num}: Invalid name (must be 1-150 characters).")
                    continue

                matched_type = None
                for vt in valid_types:
                    if account_type.lower() == vt.lower():
                        matched_type = vt
                        break
                if not matched_type:
                    errors.append(f"Row {row_num}: Invalid account_type '{account_type}'. Must be one of: {', '.join(sorted(valid_types))}.")
                    continue

                # Validate against digit enforcement and number series
                if acct_settings:
                    is_valid, code_errors = acct_settings.validate_account_code(code, matched_type)
                    if not is_valid:
                        errors.append(f"Row {row_num}: {'; '.join(code_errors)}")
                        continue

                is_active = True
                if 'is_active' in df.columns:
                    raw = str(row.get('is_active', 'true')).strip().lower()
                    is_active = raw in ('true', '1', 'yes', 'active')

                is_reconciliation = False
                if 'is_reconciliation' in df.columns:
                    raw_recon = str(row.get('is_reconciliation', 'false')).strip().lower()
                    is_reconciliation = raw_recon in ('true', '1', 'yes')

                reconciliation_type = ''
                if 'reconciliation_type' in df.columns:
                    recon_val = row.get('reconciliation_type', '')
                    reconciliation_type = '' if pd.isna(recon_val) else str(recon_val).strip()

                valid_recon_types = {
                    'accounts_payable', 'accounts_receivable',
                    'inventory', 'asset_accounting', 'bank_accounting',
                }

                if is_reconciliation and matched_type not in ('Asset', 'Liability'):
                    errors.append(f"Row {row_num}: Reconciliation is only valid for Asset or Liability accounts.")
                    continue

                if is_reconciliation and reconciliation_type not in valid_recon_types:
                    errors.append(f"Row {row_num}: Invalid reconciliation_type '{reconciliation_type}'.")
                    continue

                if not is_reconciliation:
                    reconciliation_type = ''

                if Account.objects.filter(code=code).exists():
                    skipped_count += 1
                    continue

                Account.objects.create(
                    code=code,
                    name=name,
                    account_type=matched_type,
                    is_active=is_active,
                    is_reconciliation=is_reconciliation,
                    reconciliation_type=reconciliation_type,
                )
                created_count += 1

            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

        return Response({
            'success': True,
            'created': created_count,
            'skipped': skipped_count,
            'errors': errors,
        })

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        """Delete multiple GL accounts. Only accounts with no journal lines can be deleted."""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': 'No account IDs provided.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > 100:
            return Response({'error': 'Maximum 100 items per bulk delete.'}, status=status.HTTP_400_BAD_REQUEST)

        accounts = Account.objects.filter(id__in=ids)
        in_use = accounts.filter(journalline__isnull=False).distinct()
        if in_use.exists():
            names = ', '.join(f"{a.code} - {a.name}" for a in in_use[:5])
            return Response(
                {'error': f'Cannot delete accounts with journal entries: {names}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        count = accounts.count()
        accounts.delete()
        return Response({'status': f'{count} account(s) deleted successfully.', 'deleted': count})

class JournalViewSet(viewsets.ModelViewSet):
    queryset = JournalHeader.objects.select_related(
        'fund', 'function', 'program', 'geo'
    ).prefetch_related('lines', 'lines__account')
    serializer_class = JournalHeaderSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_class = JournalFilter
    ordering_fields = ['posting_date', 'reference_number', 'document_number', 'total_debit', 'total_credit', 'status']
    search_fields = ['reference_number', 'document_number', 'description']
    pagination_class = AccountingPagination

    def get_queryset(self):
        # Annotate total_debit and total_credit for ordering support
        return super().get_queryset().annotate(
            total_debit=Coalesce(Sum('lines__debit'), Decimal('0'), output_field=DecimalField()),
            total_credit=Coalesce(Sum('lines__credit'), Decimal('0'), output_field=DecimalField())
        )

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return JournalDetailSerializer
        return JournalHeaderSerializer

    def get_permissions(self):
        if self.action == 'post_journal':
            return [IsApprover('post')]
        if self.action == 'approve':
            return [IsApprover()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # ── Period lock enforcement ──────────────────────────────
        posting_date = serializer.validated_data.get('posting_date')
        if posting_date:
            from accounting.models.advanced import FiscalPeriod
            period = FiscalPeriod.objects.filter(
                start_date__lte=posting_date,
                end_date__gte=posting_date,
                period_type='Monthly',
            ).first()
            if period and (period.is_closed or period.is_locked):
                if not period.allow_journal_entry:
                    return Response(
                        {"error": f"Period {period.period_number}/{period.fiscal_year} is {period.status}. "
                                  f"Journal entries are not allowed in this period. "
                                  f"Contact the Accountant General to request access."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        lines_data = request.data.get('lines', [])

        # Validate debits equal credits
        total_debit = sum(Decimal(str(line.get('debit', 0))) for line in lines_data)
        total_credit = sum(Decimal(str(line.get('credit', 0))) for line in lines_data)

        if total_debit != total_credit:
            return Response(
                {"error": f"Journal is not balanced. Debits: {total_debit}, Credits: {total_credit}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # Create journal header
            journal = serializer.save()

            # Create journal lines
            for line_data in lines_data:
                JournalLine.objects.create(
                    header=journal,
                    account_id=line_data.get('account'),
                    debit=line_data.get('debit', 0),
                    credit=line_data.get('credit', 0),
                    memo=line_data.get('memo', '')
                )

            # Auto-post if status is Posted
            if journal.status == 'Posted':
                self._post_to_gl(journal, request.user)

        headers_serializer = JournalHeaderSerializer(journal)
        return Response(headers_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.status == 'Posted':
            return Response(
                {"error": "Cannot modify a posted journal entry. Use update_description to change its description."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)

        lines_data = request.data.get('lines', None)

        # If lines provided, validate and update
        if lines_data:
            total_debit = sum(Decimal(str(line.get('debit', 0))) for line in lines_data)
            total_credit = sum(Decimal(str(line.get('credit', 0))) for line in lines_data)

            if total_debit != total_credit:
                return Response(
                    {"error": f"Journal is not balanced. Debits: {total_debit}, Credits: {total_credit}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        with transaction.atomic():
            if lines_data:
                # Delete existing lines and create new ones
                instance.lines.all().delete()

                for line_data in lines_data:
                    JournalLine.objects.create(
                        header=instance,
                        account_id=line_data.get('account'),
                        debit=line_data.get('debit', 0),
                        credit=line_data.get('credit', 0),
                        memo=line_data.get('memo', '')
                    )

            journal = serializer.save()

            # Auto-post if status is Posted
            if journal.status == 'Posted':
                self._post_to_gl(journal, request.user)

        headers_serializer = JournalHeaderSerializer(journal)
        return Response(headers_serializer.data)

    @action(detail=True, methods=['patch'])
    def update_description(self, request, pk=None):
        """Update only the description of a journal entry, regardless of its status."""
        journal = self.get_object()
        new_description = request.data.get('description')

        if new_description is None:
            return Response(
                {"error": "Please provide a 'description' field."},
                status=status.HTTP_400_BAD_REQUEST
            )

        journal.description = new_description
        journal.save(update_fields=['description'], _allow_status_change=True)

        return Response({
            "status": "Journal description updated successfully.",
            "id": journal.id,
            "description": journal.description
        })

    def _post_to_gl(self, journal, user, skip_budget_check=False):
        """Post journal entries to GL balances in real-time with optional budget validation."""
        from django.db import transaction
        # Canonical budget system: use budget.models.UnifiedBudget for all budget checks.
        # accounting.budget_logic is the legacy wrapper; budget.models is the source of truth.
        from budget.models import UnifiedBudget
        from budget.models import UnifiedBudgetEncumbrance

        with transaction.atomic():
            fiscal_year = journal.posting_date.year
            period = journal.posting_date.month

            # Generate Sequential Document Number for the Header
            if not journal.document_number:
                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

            # Budget validation for expense transactions (debits)
            budget_violations = []

            for line in journal.lines.all():
                if not line.document_number:
                    line.document_number = journal.document_number
                    line.save(update_fields=['document_number'])

                # Budget check for expense accounts with debit amounts
                if not skip_budget_check and line.account.account_type == 'Expense' and line.debit and line.debit > 0:
                    # Find matching budget
                    # Budget control: MDA + Account (Economic) + Fund only
                    budget = UnifiedBudget.get_budget_for_transaction(
                        dimensions={
                            'fund': journal.fund,
                            'mda': journal.mda,
                        },
                        account=line.account,
                        fiscal_year=str(fiscal_year),
                        period_type='MONTHLY',
                        period_number=period
                    )

                    if budget:
                        is_allowed, message, available = budget.check_availability(line.debit, 'JOURNAL')

                        if not is_allowed and budget.control_level == 'HARD_STOP':
                            budget_violations.append({
                                'account': line.account.code,
                                'account_name': line.account.name,
                                'requested': str(line.debit),
                                'available': str(available),
                                'message': message
                            })
                        elif is_allowed and budget.enable_encumbrance:
                            UnifiedBudgetEncumbrance.objects.create(
                                budget=budget,
                                reference_type='GENERAL',
                                reference_id=journal.id,
                                reference_number=journal.document_number or '',
                                encumbrance_date=journal.posting_date,
                                amount=line.debit,
                                status='ACTIVE',
                                description=f"Journal {journal.document_number}: {journal.description[:100]}",
                                created_by=user
                            )

            # If there are hard-stop budget violations, abort
            if budget_violations:
                raise ValidationError({
                    'budget_violations': budget_violations,
                    'message': 'Budget check failed. Cannot post journal.'
                })

            # Post to GL balances (atomic F()-based)
            from accounting.services import update_gl_from_journal
            update_gl_from_journal(journal)

    @action(detail=True, methods=['post'])
    def post_journal(self, request, pk=None):
        """Post journal entry to GL balances in real-time."""
        from accounting.models import BudgetPeriod

        journal = self.get_object()

        if journal.status == 'Posted':
            return Response(
                {"error": "Journal is already posted."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate period is open for posting
        period = BudgetPeriod.get_period_for_date(journal.posting_date)
        if period and not period.can_post():
            return Response(
                {"error": f"Cannot post to period {period}. Period status is: {period.get_status_display()}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate journal is balanced
        total_debit = journal.lines.aggregate(total=Sum('debit'))['total'] or 0
        total_credit = journal.lines.aggregate(total=Sum('credit'))['total'] or 0

        if total_debit != total_credit:
            return Response(
                {"error": f"Cannot post unbalanced journal. Debits: {total_debit}, Credits: {total_credit}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate journal has lines
        if not journal.lines.exists():
            return Response(
                {"error": "Cannot post journal with no lines."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Post to GL
            self._post_to_gl(journal, request.user)

            # Update status
            journal.status = 'Posted'
            journal.save(_allow_status_change=True)

            # P6-T4 — bust cached reports for this fiscal year so the next
            # dashboard load reflects the newly-posted journal.
            try:
                from accounting.services.report_cache import invalidate_period_reports
                invalidate_period_reports(fiscal_year=journal.posting_date.year)
            except Exception:
                pass

            return Response({
                "status": "Journal posted successfully.",
                "journal_id": journal.id,
                "total_debit": total_debit,
                "total_credit": total_credit,
                "fiscal_year": journal.posting_date.year,
                "period": journal.posting_date.month
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def unpost_journal(self, request, pk=None):
        """Unpost journal entry and reverse GL balances."""
        from ..models import JournalReversal

        journal = self.get_object()

        if journal.status != 'Posted':
            return Response(
                {"error": "Only posted journals can be unposted."},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get('reason', 'Manual unpost')
        reversal_type = request.data.get('reversal_type', 'Unpost')

        try:
            fiscal_year = journal.posting_date.year
            period = journal.posting_date.month

            reversed_balances = []

            with transaction.atomic():
                for line in journal.lines.all():
                    gl_balance = GLBalance.objects.filter(
                        account=line.account,
                        fund=journal.fund,
                        function=journal.function,
                        program=journal.program,
                        geo=journal.geo,
                        fiscal_year=fiscal_year,
                        period=period
                    ).first()

                    if gl_balance:
                        old_debit = gl_balance.debit_balance
                        old_credit = gl_balance.credit_balance

                        if line.debit > 0:
                            gl_balance.debit_balance -= line.debit
                        if line.credit > 0:
                            gl_balance.credit_balance -= line.credit
                        gl_balance.save()

                        reversed_balances.append({
                            'account': str(line.account),
                            'old_debit': str(old_debit),
                            'old_credit': str(old_credit),
                            'new_debit': str(gl_balance.debit_balance),
                            'new_credit': str(gl_balance.credit_balance)
                        })

                journal.status = 'Approved'
                journal.save(_allow_status_change=True)

                JournalReversal.objects.create(
                    original_journal=journal,
                    reversal_type=reversal_type,
                    reason=reason,
                    reversed_by=request.user,
                    gl_balances_reversed=reversed_balances
                )

            # P6-T4 — bust cached reports; the unpost removed GL balances.
            try:
                from accounting.services.report_cache import invalidate_period_reports
                invalidate_period_reports(fiscal_year=fiscal_year)
            except Exception:
                pass

            return Response({"status": "Journal unposted successfully."})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        """Delete multiple journal entries. Only Draft journals can be deleted."""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': 'No journal IDs provided'}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > 100:
            return Response({'error': 'Maximum 100 items per bulk delete.'}, status=status.HTTP_400_BAD_REQUEST)

        journals = JournalHeader.objects.filter(id__in=ids)
        posted = journals.filter(status='Posted').count()
        if posted > 0:
            return Response(
                {'error': f'{posted} journal(s) are Posted and cannot be deleted. Only Draft journals can be deleted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        count = journals.count()
        journals.delete()
        return Response({'status': f'{count} journal(s) deleted successfully', 'deleted': count})

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download a CSV template for bulk journal import."""
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'reference_number', 'posting_date', 'description',
            'account_code', 'debit', 'credit', 'memo',
        ])
        # Two balanced example journals
        writer.writerow(['JV-2024-001', '2024-01-15', 'Salary Payment',    '50200000', '50000', '0',     'Salary expense'])
        writer.writerow(['JV-2024-001', '2024-01-15', 'Salary Payment',    '20200000', '0',     '50000', 'Payroll liability'])
        writer.writerow(['JV-2024-002', '2024-01-16', 'Office Supplies',   '50100000', '5000',  '0',     'Office supplies'])
        writer.writerow(['JV-2024-002', '2024-01-16', 'Office Supplies',   '10100000', '0',     '5000',  'Cash payment'])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="journal_import_template.csv"'
        return response

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        """Import multiple journals from a CSV or Excel file.

        Format: one row per journal line; rows sharing the same reference_number
        are grouped into one JournalHeader.  Each group must be balanced
        (total debits == total credits).  Duplicate reference numbers that
        already exist in the DB are skipped with an error message.
        """
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'A CSV or Excel file is required.'}, status=status.HTTP_400_BAD_REQUEST)

        MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
        if file.size > MAX_IMPORT_FILE_SIZE:
            return Response({'error': 'File too large. Maximum 5 MB allowed.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file, nrows=5000)
            else:
                df = pd.read_csv(file, nrows=5000)
        except Exception as exc:
            return Response({'error': f'Failed to parse file: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

        df.columns = df.columns.str.strip().str.lower()

        required_cols = {'reference_number', 'posting_date', 'account_code', 'debit', 'credit'}
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            return Response(
                {'error': f'Missing required columns: {", ".join(sorted(missing_cols))}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Normalise nulls
        df['debit']  = pd.to_numeric(df['debit'],  errors='coerce').fillna(0)
        df['credit'] = pd.to_numeric(df['credit'], errors='coerce').fillna(0)
        df['memo']   = df['memo'].fillna('') if 'memo' in df.columns else ''
        df['description'] = df.get('description', df['reference_number']).fillna('')

        created_count = 0
        skipped_count = 0
        errors = []

        for ref_num, group in df.groupby('reference_number', sort=False):
            ref_num = str(ref_num).strip()
            try:
                with transaction.atomic():
                    # Skip duplicate reference numbers
                    if JournalHeader.objects.filter(reference_number=ref_num).exists():
                        errors.append(f'{ref_num}: reference number already exists — skipped.')
                        skipped_count += 1
                        continue

                    first = group.iloc[0]
                    posting_date = str(first.get('posting_date', '')).strip()
                    description  = str(first.get('description',  ref_num)).strip() or ref_num

                    total_debit  = Decimal('0')
                    total_credit = Decimal('0')
                    lines_to_create = []

                    for _, row in group.iterrows():
                        account_code = str(row.get('account_code', '')).strip()
                        try:
                            account = Account.objects.get(code=account_code)
                        except Account.DoesNotExist:
                            raise ValueError(f'account code "{account_code}" not found')

                        debit  = Decimal(str(row['debit']  or 0))
                        credit = Decimal(str(row['credit'] or 0))
                        memo   = str(row.get('memo', '') or '')
                        total_debit  += debit
                        total_credit += credit
                        lines_to_create.append({'account': account, 'debit': debit, 'credit': credit, 'memo': memo})

                    if abs(total_debit - total_credit) >= Decimal('0.01'):
                        raise ValueError(
                            f'not balanced — debits {total_debit}, credits {total_credit}'
                        )

                    # Create header via serializer for field validation
                    serializer = JournalHeaderSerializer(data={
                        'posting_date':    posting_date,
                        'reference_number': ref_num,
                        'description':     description,
                        'status':          'Draft',
                    })
                    serializer.is_valid(raise_exception=True)
                    journal = serializer.save()

                    JournalLine.objects.bulk_create([
                        JournalLine(
                            header=journal,
                            account=line['account'],
                            debit=line['debit'],
                            credit=line['credit'],
                            memo=line['memo'],
                        )
                        for line in lines_to_create
                    ])

                    created_count += 1

            except Exception as exc:
                errors.append(f'{ref_num}: {exc}')
                skipped_count += 1

        return Response({
            'created': created_count,
            'skipped': skipped_count,
            'errors':  errors,
        }, status=status.HTTP_201_CREATED if created_count else status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def trial_balance(self, request):
        """Get trial balance for a period."""
        from django.db.models import Sum

        fiscal_year = int(request.query_params.get('year', timezone.now().year))
        period = int(request.query_params.get('period', timezone.now().month))

        # PF-13: Aggregate across ALL periods in the fiscal year up to
        # the selected period for cumulative YTD trial balance.
        balances = (
            GLBalance.objects.filter(
                fiscal_year=fiscal_year,
                period__lte=period
            )
            .values('account__id', 'account__code', 'account__name', 'account__account_type')
            .annotate(
                total_debit=Sum('debit_balance'),
                total_credit=Sum('credit_balance'),
            )
            .order_by('account__code')
        )

        data = []
        total_debit = 0
        total_credit = 0

        for bal in balances:
            net = bal['total_debit'] - bal['total_credit']
            if net >= 0:
                debit = net
                credit = 0
            else:
                debit = 0
                credit = abs(net)

            data.append({
                'account_code': bal['account__code'],
                'account_name': bal['account__name'],
                'account_type': bal['account__account_type'],
                'debit': debit,
                'credit': credit
            })
            total_debit += debit
            total_credit += credit

        return Response({
            'fiscal_year': fiscal_year,
            'period': period,
            'accounts': data,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'difference': total_debit - total_credit
        })

    @action(detail=False, methods=['get'])
    def gl_report(self, request):
        """Get general ledger report."""

        account_id = request.query_params.get('account')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not account_id:
            return Response({"error": "account parameter required"}, status=status.HTTP_400_BAD_REQUEST)

        journals = JournalHeader.objects.filter(
            lines__account_id=account_id,
            status='Posted'
        )

        if start_date:
            journals = journals.filter(posting_date__gte=start_date)
        if end_date:
            journals = journals.filter(posting_date__lte=end_date)

        journals = journals.distinct().prefetch_related('lines')

        data = []
        running_balance = 0

        for journal in journals:
            for line in journal.lines.filter(account_id=account_id):
                debit = line.debit or 0
                credit = line.credit or 0
                movement = debit - credit
                running_balance += movement

                data.append({
                    'date': journal.posting_date,
                    'reference': journal.reference_number,
                    'description': journal.description,
                    'debit': debit,
                    'credit': credit,
                    'balance': running_balance
                })

        return Response({
            'account_id': account_id,
            'entries': data,
            'ending_balance': running_balance
        })

# ============================================================================
# MULTI-CURRENCY VIEWSETS
# ============================================================================

class CurrencyViewSet(viewsets.ModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    filterset_fields = ['is_active', 'is_base_currency']
    pagination_class = AccountingPagination

    @action(detail=False, methods=['post'], url_path='convert')
    def convert(self, request):
        """Convert an amount between two currencies using ExchangeRateHistory or fallback to spot rates."""
        amount = request.data.get('amount')
        from_code = request.data.get('from_currency')
        to_code = request.data.get('to_currency')
        rate_date = request.data.get('date')

        if amount is None or not from_code or not to_code:
            return Response({'error': 'amount, from_currency, and to_currency are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = Decimal(str(amount))
        except Exception:
            return Response({'error': 'Invalid amount.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from_cur = Currency.objects.get(code=from_code)
            to_cur = Currency.objects.get(code=to_code)
        except Currency.DoesNotExist:
            return Response({'error': 'Currency not found.'}, status=status.HTTP_404_NOT_FOUND)

        if from_cur.id == to_cur.id:
            return Response({'converted_amount': str(amount), 'rate': '1.000000'})

        # Try ExchangeRateHistory for the given date
        rate_entry = None
        if rate_date:
            rate_entry = ExchangeRateHistory.objects.filter(
                from_currency=from_cur, to_currency=to_cur, rate_date=rate_date
            ).first()
            if not rate_entry:
                # Try reverse direction
                reverse = ExchangeRateHistory.objects.filter(
                    from_currency=to_cur, to_currency=from_cur, rate_date=rate_date
                ).first()
                if reverse and reverse.exchange_rate:
                    converted = amount * (Decimal(1) / reverse.exchange_rate)
                    return Response({'converted_amount': str(converted.quantize(Decimal('0.01'))), 'rate': str((Decimal(1) / reverse.exchange_rate).quantize(Decimal('0.000001')))})

        if not rate_entry:
            # Try latest rate from ExchangeRateHistory
            rate_entry = ExchangeRateHistory.objects.filter(
                from_currency=from_cur, to_currency=to_cur
            ).first()

        if rate_entry and rate_entry.exchange_rate:
            converted = amount * rate_entry.exchange_rate
            return Response({'converted_amount': str(converted.quantize(Decimal('0.01'))), 'rate': str(rate_entry.exchange_rate)})

        # Fallback: use Currency.exchange_rate (rates relative to base)
        if from_cur.exchange_rate and to_cur.exchange_rate:
            cross_rate = to_cur.exchange_rate / from_cur.exchange_rate
            converted = amount * cross_rate
            return Response({'converted_amount': str(converted.quantize(Decimal('0.01'))), 'rate': str(cross_rate.quantize(Decimal('0.000001')))})

        return Response({'error': 'No exchange rate available for this currency pair.'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get', 'put'], url_path='defaults')
    def defaults(self, request):
        """GET/PUT the default currency configuration."""
        settings_obj, _ = AccountingSettings.objects.get_or_create(pk=1)

        if request.method == 'GET':
            serializer = AccountingSettingsSerializer(settings_obj)
            return Response(serializer.data)

        serializer = AccountingSettingsSerializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

# ============================================================================
# GL REPORTING VIEWSETS
# ============================================================================

class GLBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset for GL balance reporting."""
    serializer_class = GLBalanceSerializer
    filterset_fields = ['fiscal_year', 'period', 'account', 'fund', 'function', 'program', 'geo']
    search_fields = ['account__code', 'account__name']

    def get_queryset(self):
        from django.db.models import Subquery, OuterRef, CharField, Value
        from django.db.models.functions import Cast

        qs = GLBalance.objects.all().select_related('account', 'fund', 'function', 'program', 'geo')

        # Annotate reference and journal_number from the most recent journal line
        # to avoid N+1 queries in the serializer
        latest_line = JournalLine.objects.filter(
            account=OuterRef('account'),
            header__posting_date__year=OuterRef('fiscal_year'),
            header__posting_date__month=OuterRef('period'),
        ).order_by('-header__posting_date', '-header__id')

        qs = qs.annotate(
            reference=Coalesce(
                Subquery(latest_line.values('header__reference_number')[:1]),
                Value(''),
                output_field=CharField(),
            ),
            journal_number=Coalesce(
                Cast(Subquery(latest_line.values('header__id')[:1]), output_field=CharField()),
                Value(''),
                output_field=CharField(),
            ),
        )
        return qs

    @action(detail=False, methods=['get'])
    def financial_statements(self, request):
        """PF-14: Return Balance Sheet and Income Statement data.

        Query params:
            year  – fiscal year (default: current year)
            period – up to this period for YTD (default: current month)

        Returns structured data grouped by account_type.
        """
        from django.db.models import Sum

        fiscal_year = int(request.query_params.get('year', timezone.now().year))
        period = int(request.query_params.get('period', timezone.now().month))

        balances = (
            GLBalance.objects.filter(fiscal_year=fiscal_year, period__lte=period)
            .values('account__account_type')
            .annotate(
                total_debit=Sum('debit_balance'),
                total_credit=Sum('credit_balance'),
            )
        )

        summary = {}
        for row in balances:
            acct_type = row['account__account_type']
            summary[acct_type] = {
                'total_debit': row['total_debit'] or Decimal('0'),
                'total_credit': row['total_credit'] or Decimal('0'),
                'net': (row['total_debit'] or Decimal('0')) - (row['total_credit'] or Decimal('0')),
            }

        assets = summary.get('Asset', {}).get('net', Decimal('0'))
        liabilities = summary.get('Liability', {}).get('net', Decimal('0'))
        equity = summary.get('Equity', {}).get('net', Decimal('0'))
        income = (summary.get('Income', {}).get('total_credit', Decimal('0'))
                  - summary.get('Income', {}).get('total_debit', Decimal('0')))
        expenses = (summary.get('Expense', {}).get('total_debit', Decimal('0'))
                    - summary.get('Expense', {}).get('total_credit', Decimal('0')))
        net_income = income - expenses

        return Response({
            'fiscal_year': fiscal_year,
            'period': period,
            'balance_sheet': {
                'assets': str(assets),
                'liabilities': str(abs(liabilities)),
                'equity': str(abs(equity)),
                'total_liabilities_and_equity': str(abs(liabilities) + abs(equity)),
            },
            'income_statement': {
                'income': str(income),
                'expenses': str(expenses),
                'net_income': str(net_income),
            },
            'detail_by_type': {k: {kk: str(vv) for kk, vv in v.items()} for k, v in summary.items()},
        })


# ============================================================================
# BUDGET MANAGEMENT VIEWSETS
# ============================================================================

class MDAViewSet(viewsets.ModelViewSet):
    queryset = MDA.objects.all()
    serializer_class = MDASerializer
    filterset_fields = ['mda_type', 'is_active', 'parent_mda']
    search_fields = ['code', 'name']
