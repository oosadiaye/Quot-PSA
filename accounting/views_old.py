from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes as perm_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsApprover
from django.db.models import Sum, F
from django.db.models.functions import Coalesce
from django.db import transaction
from decimal import Decimal
import pandas as pd
from datetime import datetime, timedelta
from django.utils import timezone
from .models import (
    Fund, Function, Program, Geo, Account, JournalHeader, JournalLine,
    Currency, GLBalance, VendorInvoice, Payment, CustomerInvoice, Receipt, FixedAsset,
    MDA, BudgetPeriod, Budget, BudgetEncumbrance, BudgetAmendment, BudgetTransfer,
    BudgetCheckLog, BudgetForecast, BudgetAnomaly,
    BankAccount, Checkbook, Check, BankReconciliation,
    CashFlowCategory, CashFlowForecast,
    TaxRegistration, TaxExemption, TaxReturn, WithholdingTax, TaxCode,
    CostCenter, ProfitCenter, CostAllocationRule, InterCompany, InterCompanyTransaction, FinancialReportTemplate, FinancialReport, AccountingDocument, ConsolidationGroup, Consolidation,
    DeferredRevenue, DeferredExpense, Lease, LeasePayment,
    TreasuryForecast, Investment, Loan, LoanRepayment,
    ExchangeRateHistory, ForeignCurrencyRevaluation,
    FiscalPeriod, PeriodCloseCheck, FiscalYear, PeriodAccess,
    AssetClass, AssetCategory, AssetConfiguration, AssetLocation, AssetInsurance,
    AssetMaintenance, AssetTransfer, AssetDepreciationSchedule, AssetRevaluation,
    AssetDisposal, AssetImpairment,
    JournalReversal,
    RecurringJournal, RecurringJournalRun,
    Accrual, Deferral, PeriodStatus, YearEndClosing, CurrencyRevaluation, RetainedEarnings,
    AccountingSettings,
    Company, InterCompanyConfig, InterCompanyInvoice,
    InterCompanyTransfer, InterCompanyAllocation, InterCompanyCashTransfer,
    ConsolidationRun,
)
from .serializers import (
    FundSerializer, FunctionSerializer, ProgramSerializer,
    GeoSerializer, AccountSerializer, JournalHeaderSerializer,
    CurrencySerializer, VendorInvoiceSerializer, PaymentSerializer,
    CustomerInvoiceSerializer, ReceiptSerializer, FixedAssetSerializer,
    GLBalanceSerializer,
    MDASerializer, BudgetPeriodSerializer, BudgetSerializer, BudgetEncumbranceSerializer,
    BudgetAmendmentSerializer, BudgetTransferSerializer, BudgetCheckLogSerializer,
    BankAccountSerializer, CheckbookSerializer, CheckSerializer, BankReconciliationSerializer,
    CashFlowCategorySerializer, CashFlowForecastSerializer,
    TaxRegistrationSerializer, TaxExemptionSerializer, TaxReturnSerializer, WithholdingTaxSerializer, TaxCodeSerializer,
    CostCenterSerializer, ProfitCenterSerializer, CostAllocationRuleSerializer,
    InterCompanySerializer, InterCompanyTransactionSerializer,
    FinancialReportTemplateSerializer, FinancialReportSerializer,
    AccountingDocumentSerializer,
    ConsolidationGroupSerializer, ConsolidationSerializer,
    DeferredRevenueSerializer, DeferredExpenseSerializer,
    LeaseSerializer, LeasePaymentSerializer,
    TreasuryForecastSerializer, InvestmentSerializer, LoanSerializer, LoanRepaymentSerializer,
    ExchangeRateHistorySerializer, ForeignCurrencyRevaluationSerializer,
    FiscalPeriodSerializer, PeriodCloseCheckSerializer, FiscalYearSerializer, PeriodAccessSerializer,
    AssetClassSerializer, AssetCategorySerializer, AssetConfigurationSerializer, AssetLocationSerializer, AssetInsuranceSerializer,
    AssetMaintenanceSerializer, AssetTransferSerializer, AssetDepreciationScheduleSerializer,
    AssetRevaluationSerializer, AssetDisposalSerializer, AssetImpairmentSerializer,
    BudgetForecastSerializer, BudgetAnomalySerializer,
    RecurringJournalSerializer, RecurringJournalRunSerializer,
    AccrualSerializer, DeferralSerializer, PeriodStatusSerializer, YearEndClosingSerializer, RetainedEarningsSerializer,
    CurrencyRevaluationSerializer,
    CompanySerializer, InterCompanyConfigSerializer, InterCompanyInvoiceSerializer,
    InterCompanyTransferSerializer, InterCompanyAllocationSerializer, InterCompanyCashTransferSerializer,
    ConsolidationRunSerializer,
    AccountingSettingsSerializer,
)


class AccountingPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class DimensionImportExportMixin:
    """Reusable mixin providing import-template, bulk-import, and export actions for dimension models."""

    dimension_label = 'dimension'
    dimension_example_rows = []

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download a CSV template for dimension imports."""
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['code', 'name', 'description', 'is_active'])
        for row in self.dimension_example_rows:
            writer.writerow(row)

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{self.dimension_label}_import_template.csv"'
        return response

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        """Import dimensions from CSV/Excel file."""
        file = request.FILES.get('file')
        if not file:
            return Response(
                {"error": "A CSV or Excel file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file)
            else:
                df = pd.read_csv(file)
        except Exception as e:
            return Response(
                {"error": f"Failed to parse file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        df.columns = df.columns.str.strip().str.lower()

        required_columns = {'code', 'name'}
        missing = required_columns - set(df.columns)
        if missing:
            return Response(
                {"error": f"Missing required columns: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        model_class = self.queryset.model
        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []

        for index, row in df.iterrows():
            row_num = index + 2
            try:
                code = str(row['code']).strip()
                name = str(row['name']).strip()

                if not code or len(code) > 20:
                    errors.append(f"Row {row_num}: Invalid code '{code}' (must be 1-20 characters).")
                    continue

                if not name or len(name) > 100:
                    errors.append(f"Row {row_num}: Invalid name (must be 1-100 characters).")
                    continue

                description = ''
                if 'description' in df.columns:
                    desc_val = row.get('description', '')
                    description = '' if pd.isna(desc_val) else str(desc_val).strip()

                is_active = True
                if 'is_active' in df.columns:
                    raw = str(row.get('is_active', 'true')).strip().lower()
                    is_active = raw in ('true', '1', 'yes', 'active')

                existing = model_class.objects.filter(code=code).first()
                if existing:
                    existing.name = name
                    existing.description = description
                    existing.is_active = is_active
                    existing.save()
                    updated_count += 1
                else:
                    model_class.objects.create(
                        code=code,
                        name=name,
                        description=description,
                        is_active=is_active,
                    )
                    created_count += 1

            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

        return Response({
            'success': True,
            'created': created_count,
            'updated': updated_count,
            'skipped': skipped_count,
            'errors': errors,
        })

    @action(detail=False, methods=['get'], url_path='export')
    def export_data(self, request):
        """Export all dimension records as CSV or Excel."""
        import io
        import csv
        from django.http import HttpResponse

        queryset = self.queryset.all()
        fmt = request.query_params.get('format', 'csv')

        if fmt == 'xlsx':
            data = []
            for obj in queryset:
                data.append({
                    'code': obj.code,
                    'name': obj.name,
                    'description': obj.description or '',
                    'is_active': obj.is_active,
                })
            df = pd.DataFrame(data)
            output = io.BytesIO()
            df.to_excel(output, index=False, engine='openpyxl')
            output.seek(0)
            response = HttpResponse(
                output.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            response['Content-Disposition'] = f'attachment; filename="{self.dimension_label}_export.xlsx"'
            return response

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['code', 'name', 'description', 'is_active'])
        for obj in queryset:
            writer.writerow([obj.code, obj.name, obj.description or '', obj.is_active])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{self.dimension_label}_export.csv"'
        return response


class FundViewSet(DimensionImportExportMixin, viewsets.ModelViewSet):
    """Full CRUD operations for Fund dimension."""
    queryset = Fund.objects.all()
    serializer_class = FundSerializer
    filterset_fields = ['is_active']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination
    dimension_label = 'fund'
    dimension_example_rows = [
        ['FUND001', 'General Fund', 'Main operating fund', 'true'],
        ['FUND002', 'Capital Fund', 'Capital projects fund', 'true'],
    ]

class FunctionViewSet(DimensionImportExportMixin, viewsets.ModelViewSet):
    """Full CRUD operations for Function dimension."""
    queryset = Function.objects.all()
    serializer_class = FunctionSerializer
    filterset_fields = ['is_active']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination
    dimension_label = 'function'
    dimension_example_rows = [
        ['FUNC001', 'Administration', 'General administration function', 'true'],
        ['FUNC002', 'Education', 'Education and training function', 'true'],
    ]

class ProgramViewSet(DimensionImportExportMixin, viewsets.ModelViewSet):
    """Full CRUD operations for Program dimension."""
    queryset = Program.objects.all()
    serializer_class = ProgramSerializer
    filterset_fields = ['is_active']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination
    dimension_label = 'program'
    dimension_example_rows = [
        ['PROG001', 'Health Services', 'Public health services program', 'true'],
        ['PROG002', 'Infrastructure', 'Infrastructure development program', 'true'],
    ]

class GeoViewSet(DimensionImportExportMixin, viewsets.ModelViewSet):
    """Full CRUD operations for Geo dimension."""
    queryset = Geo.objects.all()
    serializer_class = GeoSerializer
    filterset_fields = ['is_active']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination
    dimension_label = 'geo'
    dimension_example_rows = [
        ['GEO001', 'Headquarters', 'Main office location', 'true'],
        ['GEO002', 'Regional Office', 'Regional satellite office', 'true'],
    ]

class AccountViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    filterset_fields = ['account_type', 'is_active', 'is_reconciliation', 'reconciliation_type']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.query_params.get('include_inactive'):
            queryset = queryset.filter(is_active=True)
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

        try:
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file)
            else:
                df = pd.read_csv(file)
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

class JournalViewSet(viewsets.ModelViewSet):
    queryset = JournalHeader.objects.select_related(
        'fund', 'function', 'program', 'geo'
    ).prefetch_related('lines')
    serializer_class = JournalHeaderSerializer
    filterset_fields = ['status', 'posting_date']
    pagination_class = AccountingPagination

    def get_permissions(self):
        if self.action == 'post_journal':
            return [IsApprover('post')]
        if self.action == 'approve':
            return [IsApprover()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        lines_data = serializer.validated_data.pop('lines', [])

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
                    account=line_data.get('account'),
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
                {"error": "Cannot modify a posted journal entry."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)

        lines_data = serializer.validated_data.pop('lines', None)

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
                        account=line_data.get('account'),
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

    def _post_to_gl(self, journal, user):
        """Post journal entries to GL balances in real-time."""
        from django.db import transaction

        with transaction.atomic():
            fiscal_year = journal.posting_date.year
            period = journal.posting_date.month

            for line in journal.lines.all():
                gl_balance, created = GLBalance.objects.get_or_create(
                    account=line.account,
                    fund=journal.fund,
                    function=journal.function,
                    program=journal.program,
                    geo=journal.geo,
                    fiscal_year=fiscal_year,
                    period=period,
                    defaults={
                        'debit_balance': Decimal('0.00'),
                        'credit_balance': Decimal('0.00')
                    }
                )

                account_type = line.account.account_type
                debit = Decimal(str(line.debit)) if line.debit else Decimal('0.00')
                credit = Decimal(str(line.credit)) if line.credit else Decimal('0.00')

                if account_type in ['Asset', 'Expense']:
                    gl_balance.debit_balance += debit
                    gl_balance.credit_balance += credit
                else:
                    gl_balance.credit_balance += credit
                    gl_balance.debit_balance += debit

                gl_balance.save()

    @action(detail=True, methods=['post'])
    def post_journal(self, request, pk=None):
        """Post journal entry to GL balances in real-time."""
        journal = self.get_object()

        if journal.status == 'Posted':
            return Response(
                {"error": "Journal is already posted."},
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
            journal.save()

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
                journal.save()

                JournalReversal.objects.create(
                    original_journal=journal,
                    reversal_type=reversal_type,
                    reason=reason,
                    reversed_by=request.user,
                    gl_balances_reversed=reversed_balances
                )

            return Response({"status": "Journal unposted successfully."})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def trial_balance(self, request):
        """Get trial balance for a period."""

        fiscal_year = int(request.query_params.get('year', timezone.now().year))
        period = int(request.query_params.get('period', timezone.now().month))

        balances = GLBalance.objects.filter(
            fiscal_year=fiscal_year,
            period=period
        ).select_related('account').order_by('account__code')

        data = []
        total_debit = 0
        total_credit = 0

        for bal in balances:
            net = bal.debit_balance - bal.credit_balance
            if net >= 0:
                debit = net
                credit = 0
            else:
                debit = 0
                credit = abs(net)

            data.append({
                'account_code': bal.account.code,
                'account_name': bal.account.name,
                'account_type': bal.account.account_type,
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
        from .serializers import AccountingSettingsSerializer
        settings_obj, _ = AccountingSettings.objects.get_or_create(pk=1)

        if request.method == 'GET':
            serializer = AccountingSettingsSerializer(settings_obj)
            return Response(serializer.data)

        serializer = AccountingSettingsSerializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

# ============================================================================
# ACCOUNTS PAYABLE VIEWSETS
# ============================================================================

class VendorInvoiceViewSet(viewsets.ModelViewSet):
    queryset = VendorInvoice.objects.all().select_related('vendor', 'fund', 'function', 'program', 'geo', 'currency', 'account')
    serializer_class = VendorInvoiceSerializer
    filterset_fields = ['status', 'vendor', 'invoice_date']
    pagination_class = AccountingPagination

    def get_permissions(self):
        if self.action == 'post_invoice':
            return [IsApprover('post')]
        return super().get_permissions()

    def perform_destroy(self, instance):
        if instance.status != 'Draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Only draft vendor invoices can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def approve_invoice(self, request, pk=None):
        """Approve vendor invoice."""
        invoice = self.get_object()
        if invoice.status != 'Draft':
            return Response({"error": "Only draft invoices can be approved."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invoice.status = 'Approved'
            invoice.save()
            return Response({"status": "Invoice approved successfully."})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def post_invoice(self, request, pk=None):
        """Post vendor invoice — creates journal entry with separate expense + AP accounts."""
        invoice = self.get_object()

        if invoice.status == 'Posted':
            return Response({"error": "Invoice already posted."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from django.conf import settings as django_settings
            default_gl = getattr(django_settings, 'DEFAULT_GL_ACCOUNTS', {})

            with transaction.atomic():
                # Expense account: use invoice.account or fallback to settings
                expense_account = invoice.account
                if not expense_account:
                    exp_code = default_gl.get('PURCHASE_EXPENSE', '50100000')
                    expense_account = Account.objects.filter(code=exp_code).first()
                    if not expense_account:
                        expense_account = Account.objects.filter(account_type='Expense', name__icontains='Purchase').first()

                # AP account: ALWAYS from settings (separate from expense)
                ap_code = default_gl.get('ACCOUNTS_PAYABLE', '20100000')
                ap_account = Account.objects.filter(code=ap_code).first()
                if not ap_account:
                    ap_account = Account.objects.filter(account_type='Liability', name__icontains='Payable').first()

                if not expense_account or not ap_account:
                    return Response({"error": "Required GL accounts (Expense / AP) not found."}, status=status.HTTP_400_BAD_REQUEST)

                amount = invoice.total_amount

                # Create journal entry
                journal = JournalHeader.objects.create(
                    reference_number=f"VINV-{invoice.invoice_number}",
                    description=f"Vendor Invoice: {invoice.invoice_number}",
                    posting_date=invoice.invoice_date,
                    fund=invoice.fund,
                    function=invoice.function,
                    program=invoice.program,
                    geo=invoice.geo,
                    status='Posted'
                )

                # Debit Expense
                JournalLine.objects.create(
                    header=journal,
                    account=expense_account,
                    debit=amount,
                    credit=Decimal('0.00'),
                    memo=f"Vendor invoice {invoice.invoice_number}"
                )

                # Credit AP
                JournalLine.objects.create(
                    header=journal,
                    account=ap_account,
                    debit=Decimal('0.00'),
                    credit=amount,
                    memo=f"AP: {invoice.vendor.name if invoice.vendor else 'vendor'}"
                )

                # Update GL balances
                fiscal_year = journal.posting_date.year
                period = journal.posting_date.month
                for line in journal.lines.all():
                    gl_bal, _ = GLBalance.objects.get_or_create(
                        account=line.account,
                        fund=invoice.fund,
                        function=invoice.function,
                        program=invoice.program,
                        geo=invoice.geo,
                        fiscal_year=fiscal_year,
                        period=period,
                        defaults={'debit_balance': Decimal('0.00'), 'credit_balance': Decimal('0.00')}
                    )
                    gl_bal.debit_balance += line.debit
                    gl_bal.credit_balance += line.credit
                    gl_bal.save()

                invoice.status = 'Posted'
                invoice.save()

            return Response({
                "status": "Invoice posted to GL successfully.",
                "journal_id": journal.id,
                "invoice_id": invoice.id,
                "amount": str(amount)
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def aging_report(self, request):
        """Get accounts payable aging report"""
        from django.utils import timezone

        as_of_date = request.query_params.get('as_of_date')
        if as_of_date:
            from datetime import datetime
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
        else:
            as_of_date = timezone.now().date()

        invoices = VendorInvoice.objects.filter(
            status__in=['Approved', 'Partially Paid'],
            invoice_date__lte=as_of_date
        ).select_related('vendor')

        aging_data = {}
        for invoice in invoices:
            vendor_id = invoice.vendor.id
            if vendor_id not in aging_data:
                aging_data[vendor_id] = {
                    'vendor_id': vendor_id,
                    'vendor_name': invoice.vendor.name,
                    'current': Decimal('0'),
                    'days_1_30': Decimal('0'),
                    'days_31_60': Decimal('0'),
                    'days_61_90': Decimal('0'),
                    'days_91_plus': Decimal('0'),
                    'total_due': Decimal('0')
                }

            balance = invoice.balance_due
            days_overdue = (as_of_date - invoice.due_date).days

            if days_overdue <= 0:
                aging_data[vendor_id]['current'] += balance
            elif days_overdue <= 30:
                aging_data[vendor_id]['days_1_30'] += balance
            elif days_overdue <= 60:
                aging_data[vendor_id]['days_31_60'] += balance
            elif days_overdue <= 90:
                aging_data[vendor_id]['days_61_90'] += balance
            else:
                aging_data[vendor_id]['days_91_plus'] += balance

            aging_data[vendor_id]['total_due'] += balance

        total_current = sum(d['current'] for d in aging_data.values())
        total_1_30 = sum(d['days_1_30'] for d in aging_data.values())
        total_31_60 = sum(d['days_31_60'] for d in aging_data.values())
        total_61_90 = sum(d['days_61_90'] for d in aging_data.values())
        total_91_plus = sum(d['days_91_plus'] for d in aging_data.values())

        return Response({
            'as_of_date': as_of_date,
            'vendors': list(aging_data.values()),
            'summary': {
                'current': float(total_current),
                'days_1_30': float(total_1_30),
                'days_31_60': float(total_31_60),
                'days_61_90': float(total_61_90),
                'days_91_plus': float(total_91_plus),
                'total_due': float(total_current + total_1_30 + total_31_60 + total_61_90 + total_91_plus)
            }
        })


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all().select_related(
        'vendor', 'bank_account', 'currency', 'journal_entry'
    ).prefetch_related('allocations')
    serializer_class = PaymentSerializer
    filterset_fields = ['status', 'payment_date', 'payment_method']

    def get_permissions(self):
        if self.action == 'post_payment':
            return [IsApprover('post')]
        return super().get_permissions()

    def perform_destroy(self, instance):
        if instance.status != 'Draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Only draft payments can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def post_payment(self, request, pk=None):
        """Post payment — creates journal entry + updates GL balances + vendor balance."""
        payment = self.get_object()
        if payment.status == 'Posted':
            return Response({"error": "Payment already posted."}, status=status.HTTP_400_BAD_REQUEST)

        if not payment.allocations.exists():
            return Response({"error": "Payment has no allocations."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from django.conf import settings as django_settings
            default_gl = getattr(django_settings, 'DEFAULT_GL_ACCOUNTS', {})

            with transaction.atomic():
                # Resolve GL accounts
                ap_code = default_gl.get('ACCOUNTS_PAYABLE', '20100000')
                ap_account = Account.objects.filter(code=ap_code).first()
                if not ap_account:
                    ap_account = Account.objects.filter(account_type='Liability', name__icontains='Payable').first()

                bank_gl_account = None
                if payment.bank_account:
                    bank_gl_account = payment.bank_account.gl_account
                if not bank_gl_account:
                    cash_code = default_gl.get('CASH_ACCOUNT', '10100000')
                    bank_gl_account = Account.objects.filter(code=cash_code).first()
                    if not bank_gl_account:
                        bank_gl_account = Account.objects.filter(account_type='Asset', name__icontains='Bank').first()

                if not ap_account or not bank_gl_account:
                    return Response({"error": "Required GL accounts (AP / Bank) not found."}, status=status.HTTP_400_BAD_REQUEST)

                amount = payment.total_amount

                # Create journal entry
                journal = JournalHeader.objects.create(
                    reference_number=f"PAY-{payment.payment_number}",
                    description=f"Payment: {payment.payment_number}",
                    posting_date=payment.payment_date,
                    status='Posted'
                )

                # Debit AP (reduce liability)
                JournalLine.objects.create(
                    header=journal,
                    account=ap_account,
                    debit=amount,
                    credit=Decimal('0.00'),
                    memo=f"Payment to {payment.vendor.name if payment.vendor else 'vendor'}"
                )

                # Credit Bank (reduce asset)
                JournalLine.objects.create(
                    header=journal,
                    account=bank_gl_account,
                    debit=Decimal('0.00'),
                    credit=amount,
                    memo=f"Bank payment {payment.payment_number}"
                )

                # Update GL balances
                self._update_gl_from_journal(journal)

                # Link journal to payment and update status
                payment.journal_entry = journal
                payment.status = 'Posted'
                payment.save()

                # Update invoice paid amounts
                for allocation in payment.allocations.select_related('invoice').all():
                    invoice = allocation.invoice
                    invoice.paid_amount += allocation.amount
                    if invoice.paid_amount >= invoice.total_amount:
                        invoice.status = 'Paid'
                    else:
                        invoice.status = 'Partially Paid'
                    invoice.save()

                # Update vendor balance
                if payment.vendor:
                    payment.vendor.balance -= amount
                    payment.vendor.save()

            return Response({
                "status": "Payment posted successfully.",
                "journal_id": journal.id,
                "amount": str(amount)
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _update_gl_from_journal(journal):
        """Update GLBalance from journal lines."""
        fiscal_year = journal.posting_date.year
        period = journal.posting_date.month
        for line in journal.lines.all():
            gl_bal, _ = GLBalance.objects.get_or_create(
                account=line.account,
                fund=journal.fund,
                function=journal.function,
                program=journal.program,
                geo=journal.geo,
                fiscal_year=fiscal_year,
                period=period,
                defaults={'debit_balance': Decimal('0.00'), 'credit_balance': Decimal('0.00')}
            )
            gl_bal.debit_balance += line.debit
            gl_bal.credit_balance += line.credit
            gl_bal.save()

# ============================================================================
# ACCOUNTS RECEIVABLE VIEWSETS
# ============================================================================

class CustomerInvoiceViewSet(viewsets.ModelViewSet):
    queryset = CustomerInvoice.objects.all().select_related('customer', 'fund', 'function', 'program', 'geo', 'currency')
    serializer_class = CustomerInvoiceSerializer
    filterset_fields = ['status', 'customer', 'invoice_date']

    def perform_destroy(self, instance):
        if instance.status != 'Draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Only draft customer invoices can be deleted.")
        super().perform_destroy(instance)

    def _post_to_gl(self, invoice, user):
        """Post customer invoice to GL in real-time."""
        from django.conf import settings

        fiscal_year = invoice.invoice_date.year
        period = invoice.invoice_date.month

        default_gl = getattr(settings, 'DEFAULT_GL_ACCOUNTS', {})

        ar_code = default_gl.get('ACCOUNTS_RECEIVABLE', '10200000')
        ar_account = Account.objects.filter(code=ar_code).first()

        with transaction.atomic():
            if ar_account:
                gl_bal, _ = GLBalance.objects.get_or_create(
                    account=ar_account,
                    fund=invoice.fund,
                    function=invoice.function,
                    program=invoice.program,
                    geo=invoice.geo,
                    fiscal_year=fiscal_year,
                    period=period,
                    defaults={'debit_balance': 0, 'credit_balance': 0}
                )
                gl_bal.debit_balance += invoice.total_amount
                gl_bal.save()

            rev_code = default_gl.get('SALES_REVENUE', '40100000')
            revenue_account = Account.objects.filter(code=rev_code).first()
            if revenue_account:
                gl_bal, _ = GLBalance.objects.get_or_create(
                    account=revenue_account,
                    fund=invoice.fund,
                    function=invoice.function,
                    program=invoice.program,
                    geo=invoice.geo,
                    fiscal_year=fiscal_year,
                    period=period,
                    defaults={'debit_balance': 0, 'credit_balance': 0}
                )
                gl_bal.credit_balance += invoice.total_amount
                gl_bal.save()

    @action(detail=True, methods=['post'])
    def send_invoice(self, request, pk=None):
        """Mark invoice as sent to customer."""
        invoice = self.get_object()
        if invoice.status != 'Draft':
            return Response({"error": "Only draft invoices can be sent."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invoice.status = 'Sent'
            invoice.save()
            return Response({"status": "Invoice sent successfully."})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def post_invoice(self, request, pk=None):
        """Post customer invoice to GL in real-time."""
        invoice = self.get_object()

        if invoice.status == 'Posted':
            return Response({"error": "Invoice already posted."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            self._post_to_gl(invoice, request.user)

            invoice.status = 'Posted'
            invoice.save()

            return Response({
                "status": "Invoice posted to GL successfully.",
                "invoice_id": invoice.id,
                "amount": str(invoice.total_amount),
                "fiscal_year": invoice.invoice_date.year,
                "period": invoice.invoice_date.month
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def aging_report(self, request):
        """Get accounts receivable aging report"""
        from django.utils import timezone

        as_of_date = request.query_params.get('as_of_date')
        if as_of_date:
            from datetime import datetime
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
        else:
            as_of_date = timezone.now().date()

        invoices = CustomerInvoice.objects.filter(
            status__in=['Sent', 'Partially Paid', 'Overdue'],
            invoice_date__lte=as_of_date
        ).select_related('customer')

        aging_data = {}
        for invoice in invoices:
            customer_id = invoice.customer.id
            if customer_id not in aging_data:
                aging_data[customer_id] = {
                    'customer_id': customer_id,
                    'customer_name': invoice.customer.name,
                    'current': Decimal('0'),
                    'days_1_30': Decimal('0'),
                    'days_31_60': Decimal('0'),
                    'days_61_90': Decimal('0'),
                    'days_91_plus': Decimal('0'),
                    'total_due': Decimal('0')
                }

            balance = invoice.balance_due
            days_overdue = (as_of_date - invoice.due_date).days

            if days_overdue <= 0:
                aging_data[customer_id]['current'] += balance
            elif days_overdue <= 30:
                aging_data[customer_id]['days_1_30'] += balance
            elif days_overdue <= 60:
                aging_data[customer_id]['days_31_60'] += balance
            elif days_overdue <= 90:
                aging_data[customer_id]['days_61_90'] += balance
            else:
                aging_data[customer_id]['days_91_plus'] += balance

            aging_data[customer_id]['total_due'] += balance

        total_current = sum(d['current'] for d in aging_data.values())
        total_1_30 = sum(d['days_1_30'] for d in aging_data.values())
        total_31_60 = sum(d['days_31_60'] for d in aging_data.values())
        total_61_90 = sum(d['days_61_90'] for d in aging_data.values())
        total_91_plus = sum(d['days_91_plus'] for d in aging_data.values())

        return Response({
            'as_of_date': as_of_date,
            'customers': list(aging_data.values()),
            'summary': {
                'current': float(total_current),
                'days_1_30': float(total_1_30),
                'days_31_60': float(total_31_60),
                'days_61_90': float(total_61_90),
                'days_91_plus': float(total_91_plus),
                'total_due': float(total_current + total_1_30 + total_31_60 + total_61_90 + total_91_plus)
            }
        })


class ReceiptViewSet(viewsets.ModelViewSet):
    queryset = Receipt.objects.all().select_related(
        'customer', 'bank_account', 'currency', 'journal_entry'
    ).prefetch_related('allocations')
    serializer_class = ReceiptSerializer
    filterset_fields = ['status', 'receipt_date', 'payment_method']

    def get_permissions(self):
        if self.action == 'post_receipt':
            return [IsApprover('post')]
        return super().get_permissions()

    def perform_destroy(self, instance):
        if instance.status != 'Draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Only draft receipts can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def post_receipt(self, request, pk=None):
        """Post receipt — creates journal entry + updates GL balances + customer balance."""
        receipt = self.get_object()
        if receipt.status == 'Posted':
            return Response({"error": "Receipt already posted."}, status=status.HTTP_400_BAD_REQUEST)

        if not receipt.allocations.exists():
            return Response({"error": "Receipt has no allocations."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from django.conf import settings as django_settings
            default_gl = getattr(django_settings, 'DEFAULT_GL_ACCOUNTS', {})

            with transaction.atomic():
                # Resolve GL accounts
                ar_code = default_gl.get('ACCOUNTS_RECEIVABLE', '10200000')
                ar_account = Account.objects.filter(code=ar_code).first()
                if not ar_account:
                    ar_account = Account.objects.filter(account_type='Asset', name__icontains='Receivable').first()

                bank_gl_account = None
                if receipt.bank_account:
                    bank_gl_account = receipt.bank_account.gl_account
                if not bank_gl_account:
                    cash_code = default_gl.get('CASH_ACCOUNT', '10100000')
                    bank_gl_account = Account.objects.filter(code=cash_code).first()
                    if not bank_gl_account:
                        bank_gl_account = Account.objects.filter(account_type='Asset', name__icontains='Bank').first()

                if not ar_account or not bank_gl_account:
                    return Response({"error": "Required GL accounts (AR / Bank) not found."}, status=status.HTTP_400_BAD_REQUEST)

                amount = receipt.total_amount

                # Create journal entry
                journal = JournalHeader.objects.create(
                    reference_number=f"RCT-{receipt.receipt_number}",
                    description=f"Receipt: {receipt.receipt_number}",
                    posting_date=receipt.receipt_date,
                    status='Posted'
                )

                # Debit Bank (increase asset)
                JournalLine.objects.create(
                    header=journal,
                    account=bank_gl_account,
                    debit=amount,
                    credit=Decimal('0.00'),
                    memo=f"Bank receipt {receipt.receipt_number}"
                )

                # Credit AR (reduce receivable)
                JournalLine.objects.create(
                    header=journal,
                    account=ar_account,
                    debit=Decimal('0.00'),
                    credit=amount,
                    memo=f"Receipt from {receipt.customer.name if receipt.customer else 'customer'}"
                )

                # Update GL balances
                self._update_gl_from_journal(journal)

                # Link journal to receipt and update status
                receipt.journal_entry = journal
                receipt.status = 'Posted'
                receipt.save()

                # Update invoice received amounts
                for allocation in receipt.allocations.select_related('invoice').all():
                    invoice = allocation.invoice
                    invoice.received_amount += allocation.amount
                    if invoice.received_amount >= invoice.total_amount:
                        invoice.status = 'Paid'
                    else:
                        invoice.status = 'Partially Paid'
                    invoice.save()

                # Update customer balance
                if receipt.customer:
                    receipt.customer.balance -= amount
                    receipt.customer.save()

            return Response({
                "status": "Receipt posted to GL successfully.",
                "journal_id": journal.id,
                "receipt_id": receipt.id,
                "amount": str(amount)
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _update_gl_from_journal(journal):
        """Update GLBalance from journal lines."""
        fiscal_year = journal.posting_date.year
        period = journal.posting_date.month
        for line in journal.lines.all():
            gl_bal, _ = GLBalance.objects.get_or_create(
                account=line.account,
                fund=journal.fund,
                function=journal.function,
                program=journal.program,
                geo=journal.geo,
                fiscal_year=fiscal_year,
                period=period,
                defaults={'debit_balance': Decimal('0.00'), 'credit_balance': Decimal('0.00')}
            )
            gl_bal.debit_balance += line.debit
            gl_bal.credit_balance += line.credit
            gl_bal.save()

# ============================================================================
# FIXED ASSETS VIEWSETS
# ============================================================================

class FixedAssetViewSet(viewsets.ModelViewSet):
    queryset = FixedAsset.objects.all().select_related(
        'fund', 'function', 'program', 'geo',
        'asset_account', 'depreciation_expense_account', 'accumulated_depreciation_account'
    )
    serializer_class = FixedAssetSerializer
    filterset_fields = ['status', 'asset_category']

    @action(detail=True, methods=['post'])
    def calculate_depreciation(self, request, pk=None):
        """Calculate and create depreciation schedule for an asset."""
        asset = self.get_object()
        period_date = request.data.get('period_date')

        if not period_date:
            return Response({"error": "period_date is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from datetime import datetime
            if isinstance(period_date, str):
                period_date = datetime.strptime(period_date, '%Y-%m-%d').date()

            annual_depreciation = asset.calculate_annual_depreciation()
            monthly_depreciation = annual_depreciation / 12

            from .models import DepreciationSchedule
            schedule, created = DepreciationSchedule.objects.get_or_create(
                asset=asset,
                period_date=period_date,
                defaults={'depreciation_amount': monthly_depreciation}
            )

            if created:
                return Response({
                    "status": "Depreciation schedule created.",
                    "amount": str(monthly_depreciation)
                })
            else:
                return Response({"error": "Schedule already exists for this period."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def post_depreciation(self, request, pk=None):
        """Post depreciation — creates journal entry + updates GL balances."""
        asset = self.get_object()
        period_date = request.data.get('period_date')

        if not period_date:
            return Response({"error": "period_date is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not asset.depreciation_expense_account or not asset.accumulated_depreciation_account:
            return Response(
                {"error": "Asset must have both depreciation expense and accumulated depreciation accounts configured."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from datetime import datetime
            if isinstance(period_date, str):
                period_date = datetime.strptime(period_date, '%Y-%m-%d').date()

            from .models import DepreciationSchedule
            schedule, created = DepreciationSchedule.objects.get_or_create(
                asset=asset,
                period_date=period_date,
                defaults={'depreciation_amount': asset.calculate_annual_depreciation() / 12}
            )

            if schedule.is_posted:
                return Response({"error": "Depreciation already posted for this period."}, status=status.HTTP_400_BAD_REQUEST)

            depreciation_amount = schedule.depreciation_amount

            with transaction.atomic():
                # Create journal entry for audit trail
                journal = JournalHeader.objects.create(
                    reference_number=f"DEP-{asset.asset_code}-{period_date.strftime('%Y%m')}",
                    description=f"Depreciation: {asset.asset_name} ({period_date.strftime('%b %Y')})",
                    posting_date=period_date,
                    fund=asset.fund,
                    function=asset.function,
                    program=asset.program,
                    geo=asset.geo,
                    status='Posted'
                )

                # Debit: Depreciation Expense
                JournalLine.objects.create(
                    header=journal,
                    account=asset.depreciation_expense_account,
                    debit=depreciation_amount,
                    credit=Decimal('0.00'),
                    memo=f"Depreciation expense: {asset.asset_name}"
                )

                # Credit: Accumulated Depreciation
                JournalLine.objects.create(
                    header=journal,
                    account=asset.accumulated_depreciation_account,
                    debit=Decimal('0.00'),
                    credit=depreciation_amount,
                    memo=f"Accumulated depreciation: {asset.asset_name}"
                )

                # Update GL balances
                fiscal_year = period_date.year
                period = period_date.month
                for line in journal.lines.all():
                    gl_bal, _ = GLBalance.objects.get_or_create(
                        account=line.account,
                        fund=asset.fund,
                        function=asset.function,
                        program=asset.program,
                        geo=asset.geo,
                        fiscal_year=fiscal_year,
                        period=period,
                        defaults={'debit_balance': Decimal('0.00'), 'credit_balance': Decimal('0.00')}
                    )
                    gl_bal.debit_balance += line.debit
                    gl_bal.credit_balance += line.credit
                    gl_bal.save()

                # Update asset accumulated depreciation
                asset.accumulated_depreciation += depreciation_amount
                asset.save()

                # Link journal to schedule and mark posted
                schedule.journal_entry = journal
                schedule.is_posted = True
                schedule.save()

            return Response({
                "status": "Depreciation posted to GL successfully.",
                "journal_id": journal.id,
                "asset_id": asset.id,
                "amount": str(depreciation_amount),
                "accumulated": str(asset.accumulated_depreciation),
                "fiscal_year": period_date.year,
                "period": period_date.month
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

# ============================================================================
# GL REPORTING VIEWSETS
# ============================================================================

class GLBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset for GL balance reporting."""
    queryset = GLBalance.objects.all().select_related('account', 'fund', 'function', 'program', 'geo')
    serializer_class = GLBalanceSerializer
    filterset_fields = ['fiscal_year', 'period', 'account', 'fund', 'function', 'program', 'geo']


# ============================================================================
# BUDGET MANAGEMENT VIEWSETS
# ============================================================================

class MDAViewSet(viewsets.ModelViewSet):
    queryset = MDA.objects.all()
    serializer_class = MDASerializer
    filterset_fields = ['mda_type', 'is_active', 'parent_mda']
    search_fields = ['code', 'name']

class BudgetPeriodViewSet(viewsets.ModelViewSet):
    queryset = BudgetPeriod.objects.all()
    serializer_class = BudgetPeriodSerializer
    filterset_fields = ['fiscal_year', 'period_type', 'status']

class BudgetViewSet(viewsets.ModelViewSet):
    queryset = Budget.objects.all().select_related('period', 'mda', 'account', 'fund', 'function', 'program', 'geo')
    serializer_class = BudgetSerializer
    filterset_fields = ['period', 'mda', 'account', 'fund', 'function', 'program', 'geo', 'control_level']
    search_fields = ['budget_code', 'notes']

    @action(detail=True, methods=['post'])
    def check_availability(self, request, pk=None):
        """Check budget availability for a transaction"""
        budget = self.get_object()
        amount = Decimal(str(request.data.get('amount', 0)))
        transaction_type = request.data.get('transaction_type', 'JOURNAL')
        transaction_id = request.data.get('transaction_id', 0)

        is_available, message, available = budget.check_availability(amount)

        # Log the check
        BudgetCheckLog.objects.create(
            budget=budget,
            transaction_type=transaction_type,
            transaction_id=transaction_id,
            requested_amount=amount,
            available_amount=available,
            check_result='PASSED' if is_available else ('WARNING' if budget.control_level == 'WARNING' else 'BLOCKED')
        )

        return Response({
            'is_available': is_available,
            'message': message,
            'available_amount': available,
            'requested_amount': amount,
            'control_level': budget.control_level
        })

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get budget summary for a period"""
        period_id = request.query_params.get('period')
        if not period_id:
            return Response({"error": "period parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        budgets = self.get_queryset().filter(period_id=period_id)

        total_allocated = budgets.aggregate(total=Sum('allocated_amount'))['total'] or Decimal('0.00')
        total_revised = budgets.aggregate(total=Sum(Coalesce('revised_amount', 'allocated_amount')))['total'] or Decimal('0.00')

        # Calculate totals from properties/related items
        total_encumbered = Decimal('0.00')
        total_expended = Decimal('0.00')

        for budget in budgets:
            total_encumbered += budget.encumbered_amount
            total_expended += budget.expended_amount

        total_available = total_revised - total_encumbered - total_expended
        utilization_rate = (total_encumbered + total_expended) / total_revised * 100 if total_revised > 0 else 0

        return Response({
            'total_allocated': total_allocated,
            'total_revised': total_revised,
            'total_encumbered': total_encumbered,
            'total_expended': total_expended,
            'total_available': total_available,
            'utilization_rate': round(utilization_rate, 2)
        })

    @action(detail=False, methods=['get'])
    def utilization(self, request):
        """Get budget utilization by account type"""
        period_id = request.query_params.get('period')
        if not period_id:
            return Response({"error": "period parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Group by account type
        utilization_data = []
        account_types = [
            ('PERSONNEL', 'Personnel Costs'),
            ('OVERHEAD', 'Overhead Costs'),
            ('CAPITAL', 'Capital Expenditure'),
            ('RECURRENT', 'Recurrent Expenditure'),
            ('OTHER', 'Other Expenditure')
        ]

        for type_code, type_display in account_types:
            type_budgets = self.get_queryset().filter(period_id=period_id, account__account_type=type_code)

            allocated = type_budgets.aggregate(total=Sum(Coalesce('revised_amount', 'allocated_amount')))['total'] or Decimal('0.00')
            encumbered = Decimal('0.00')
            expended = Decimal('0.00')

            for b in type_budgets:
                encumbered += b.encumbered_amount
                expended += b.expended_amount

            used = encumbered + expended
            percent = (used / allocated * 100) if allocated > 0 else 0

            utilization_data.append({
                'account_type': type_code,
                'account_type_display': type_display,
                'allocated': allocated,
                'encumbered': encumbered,
                'expended': expended,
                'utilization_percentage': round(percent, 2)
            })

        return Response(utilization_data)

    @action(detail=False, methods=['get'])
    def alerts(self, request):
        """Get budget alerts for a period"""
        period_id = request.query_params.get('period')
        if not period_id:
            return Response({"error": "period parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        budgets = self.get_queryset().filter(period_id=period_id)
        alerts = []

        for budget in budgets:
            utilization = budget.utilization_rate
            if utilization >= 95:
                alerts.append({
                    'id': budget.id,
                    'budget_code': budget.budget_code,
                    'account_name': budget.account.name,
                    'mda_name': budget.mda.name,
                    'alert_type': 'CRITICAL',
                    'message': f"Critical: Budget {budget.budget_code} is {utilization}% utilized.",
                    'utilization': round(utilization, 2)
                })
            elif utilization >= 80:
                alerts.append({
                    'id': budget.id,
                    'budget_code': budget.budget_code,
                    'account_name': budget.account.name,
                    'mda_name': budget.mda.name,
                    'alert_type': 'WARNING',
                    'message': f"Warning: Budget {budget.budget_code} is {utilization}% utilized.",
                    'utilization': round(utilization, 2)
                })

        return Response(alerts)

    @action(detail=False, methods=['get'])
    def top_spending(self, request):
        """Get top spending budgets for a period"""
        period_id = request.query_params.get('period')
        limit = int(request.query_params.get('limit', 10))

        if not period_id:
            return Response({"error": "period parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        budgets = self.get_queryset().filter(period_id=period_id)

        spending_list = []
        for budget in budgets:
            used = budget.expended_amount + budget.encumbered_amount
            spending_list.append({
                'id': budget.id,
                'budget_code': budget.budget_code,
                'account_code': budget.account.code,
                'account_name': budget.account.name,
                'mda_name': budget.mda.name,
                'allocated': budget.revised_amount or budget.allocated_amount,
                'used': used,
                'utilization_percentage': round(budget.utilization_rate, 2)
            })

        # Sort by used amount descending
        spending_list.sort(key=lambda x: x['used'], reverse=True)

        return Response(spending_list[:limit])

    @action(detail=False, methods=['get'])
    def variance_analysis(self, request):
        """Get budget vs actual variance analysis - Optimized with aggregation"""

        period_id = request.query_params.get('period')
        if not period_id:
            return Response({"error": "period parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Optimized: Use select_related to reduce queries
        budgets = self.get_queryset().filter(
            period_id=period_id
        ).select_related('account', 'mda', 'fund', 'function', 'program', 'geo')

        # Pre-fetch encumbrance totals in one query
        from .models import BudgetEncumbrance
        encumbrance_totals = BudgetEncumbrance.objects.filter(
            budget__period_id=period_id,
            status__in=['ACTIVE', 'PARTIALLY_LIQUIDATED']
        ).values('budget_id').annotate(
            total=Sum(F('amount') - F('liquidated_amount'))
        )
        encumbrance_map = {e['budget_id']: e['total'] or Decimal('0') for e in encumbrance_totals}

        analysis = []
        for budget in budgets:
            allocated = budget.revised_amount if budget.revised_amount else budget.allocated_amount
            encumbered = encumbrance_map.get(budget.id, Decimal('0'))

            # Calculate expended from property (this still has a query but less critical)
            expended = budget.expended_amount
            available = allocated - encumbered - expended
            variance_pct = (available / allocated * 100) if allocated else 0

            analysis.append({
                'id': budget.id,
                'budget_code': budget.budget_code,
                'account': budget.account.code,
                'account_name': budget.account.name,
                'mda': budget.mda.name,
                'allocated': allocated,
                'encumbered': encumbered,
                'expended': expended,
                'available': available,
                'variance': available,
                'variance_percentage': round(variance_pct, 2),
                'utilization_rate': round(((encumbered + expended) / allocated * 100) if allocated else 0, 2)
            })

        return Response(analysis)

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download a CSV template for budget imports."""
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'mda_id', 'account_id', 'allocated_amount',
            'fund_id', 'function_id', 'program_id', 'geo_id',
            'revised_amount', 'control_level',
        ])
        writer.writerow([1, 101, 500000, '', '', '', '', '', 'HARD_STOP'])
        writer.writerow([2, 102, 300000, 1, 1, 1, 1, 350000, 'WARNING'])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="budget_import_template.csv"'
        return response

    @action(detail=False, methods=['post'])
    def bulk_import(self, request):
        """Import budgets from Excel/CSV"""
        file = request.FILES.get('file')
        period_id = request.data.get('period_id')

        if not file or not period_id:
            return Response({"error": "file and period_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file)
            else:
                df = pd.read_csv(file)

            created_count = 0
            errors = []

            for index, row in df.iterrows():
                try:
                    Budget.objects.create(
                        period_id=period_id,
                        mda_id=row['mda_id'],
                        account_id=row['account_id'],
                        fund_id=row.get('fund_id'),
                        function_id=row.get('function_id'),
                        program_id=row.get('program_id'),
                        geo_id=row.get('geo_id'),
                        allocated_amount=row['allocated_amount'],
                        revised_amount=row.get('revised_amount', row['allocated_amount']),
                        control_level=row.get('control_level', 'HARD_STOP'),
                        created_by=request.user
                    )
                    created_count += 1
                except Exception as e:
                    errors.append(f"Row {index + 2}: {str(e)}")

            return Response({
                'success': True,
                'created': created_count,
                'errors': errors
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def predictive_analysis(self, request):
        """AI-powered predictive budget analysis"""
        period_id = request.query_params.get('period')
        if not period_id:
            return Response({"error": "period parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        budgets = self.get_queryset().filter(period_id=period_id)

        predictions = []
        for budget in budgets:
            days_elapsed = (datetime.now().date() - budget.period.start_date).days
            total_days = (budget.period.end_date - budget.period.start_date).days

            if days_elapsed > 0:
                daily_burn_rate = budget.expended_amount / Decimal(str(days_elapsed))
                projected_total = daily_burn_rate * Decimal(str(total_days))

                allocated = budget.revised_amount if budget.revised_amount else budget.allocated_amount

                if daily_burn_rate > 0:
                    days_to_exhaustion = budget.available_amount / daily_burn_rate
                    exhaustion_date = datetime.now().date() + timedelta(days=int(days_to_exhaustion))
                else:
                    exhaustion_date = None

                predictions.append({
                    'budget_id': budget.id,
                    'budget_code': budget.budget_code,
                    'account': budget.account.code,
                    'mda': budget.mda.name,
                    'current_utilization': round(budget.utilization_rate, 2),
                    'projected_utilization': round((projected_total / allocated * 100), 2) if allocated else 0,
                    'daily_burn_rate': round(daily_burn_rate, 2),
                    'projected_exhaustion_date': exhaustion_date,
                    'risk_level': 'HIGH' if projected_total > allocated else 'MEDIUM' if projected_total > allocated * Decimal('0.9') else 'LOW'
                })

        return Response(predictions)

class BudgetEncumbranceViewSet(viewsets.ModelViewSet):
    queryset = BudgetEncumbrance.objects.all().select_related('budget')
    serializer_class = BudgetEncumbranceSerializer
    filterset_fields = ['budget', 'reference_type', 'status']

class BudgetAmendmentViewSet(viewsets.ModelViewSet):
    queryset = BudgetAmendment.objects.all().select_related('budget', 'requested_by', 'approved_by')
    serializer_class = BudgetAmendmentSerializer
    filterset_fields = ['budget', 'amendment_type', 'status']

    def get_permissions(self):
        if self.action == 'approve':
            return [IsApprover()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(requested_by=self.request.user)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        amendment = self.get_object()
        if amendment.status != 'PENDING':
            return Response({"error": "Only pending amendments can be approved"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                budget = amendment.budget
                budget.revised_amount = amendment.new_amount
                budget.save()

                amendment.status = 'APPROVED'
                amendment.approved_by = request.user
                amendment.approved_date = datetime.now().date()
                amendment.save()

            return Response({"status": "Amendment approved and budget updated"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BudgetTransferViewSet(viewsets.ModelViewSet):
    queryset = BudgetTransfer.objects.all().select_related('from_budget', 'to_budget', 'requested_by', 'approved_by')
    serializer_class = BudgetTransferSerializer
    filterset_fields = ['status']

    def get_permissions(self):
        if self.action == 'approve':
            return [IsApprover()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(requested_by=self.request.user)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != 'PENDING':
            return Response({"error": "Only pending transfers can be approved"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                from_budget = transfer.from_budget
                to_budget = transfer.to_budget

                # Check availability on source
                is_available, message, available = from_budget.check_availability(transfer.amount)
                if not is_available:
                    return Response({"error": f"Source budget insufficient: {message}"}, status=status.HTTP_400_BAD_REQUEST)

                # Execute transfer
                from_budget.revised_amount = (from_budget.revised_amount or from_budget.allocated_amount) - transfer.amount
                to_budget.revised_amount = (to_budget.revised_amount or to_budget.allocated_amount) + transfer.amount

                from_budget.save()
                to_budget.save()

                transfer.status = 'APPROVED'
                transfer.approved_by = request.user
                transfer.save()

            return Response({"status": "Transfer approved and budgets updated"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BudgetCheckLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BudgetCheckLog.objects.all().select_related('budget', 'override_by')
    serializer_class = BudgetCheckLogSerializer
    filterset_fields = ['budget', 'check_result', 'transaction_type']

class BudgetForecastViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BudgetForecast.objects.all().select_related('budget')
    serializer_class = BudgetForecastSerializer
    filterset_fields = ['budget']

class BudgetAnomalyViewSet(viewsets.ModelViewSet):
    queryset = BudgetAnomaly.objects.all().select_related('budget', 'reviewed_by')
    serializer_class = BudgetAnomalySerializer
    filterset_fields = ['budget', 'anomaly_type', 'reviewed']

    @action(detail=True, methods=['post'])
    def mark_reviewed(self, request, pk=None):
        anomaly = self.get_object()
        anomaly.reviewed = True
        anomaly.reviewed_by = request.user
        anomaly.save()
        return Response({"status": "Anomaly marked as reviewed"})


# =============================================================================
# BANK & CASH MANAGEMENT VIEWS
# =============================================================================

class BankAccountViewSet(viewsets.ModelViewSet):
    queryset = BankAccount.objects.all().select_related('gl_account', 'currency')
    serializer_class = BankAccountSerializer
    filterset_fields = ['account_type', 'is_active', 'currency']
    search_fields = ['name', 'account_number', 'bank_name']

    def get_queryset(self):
        queryset = super().get_queryset()
        account_type = self.request.query_params.get('account_type')
        if account_type:
            if account_type == 'bank':
                queryset = queryset.filter(account_type='Bank')
            elif account_type == 'cash':
                queryset = queryset.filter(account_type__in=['Cash', 'Petty Cash', 'Imprest'])
        return queryset

    @action(detail=False, methods=['get'])
    def summary(self, request):
        bank_accounts = self.queryset.filter(is_active=True)
        total_bank = sum(ba.current_balance for ba in bank_accounts.filter(account_type='Bank'))
        total_cash = sum(ba.current_balance for ba in bank_accounts.filter(account_type__in=['Cash', 'Petty Cash', 'Imprest']))
        total_customer_advance = sum(ba.advance_customer_balance for ba in bank_accounts)
        total_supplier_advance = sum(ba.advance_supplier_balance for ba in bank_accounts)
        return Response({
            'total_bank_balance': total_bank,
            'total_cash_balance': total_cash,
            'total_customer_advance': total_customer_advance,
            'total_supplier_advance': total_supplier_advance,
            'bank_accounts_count': bank_accounts.filter(account_type='Bank').count(),
            'cash_accounts_count': bank_accounts.filter(account_type__in=['Cash', 'Petty Cash', 'Imprest']).count(),
        })

    @action(detail=True, methods=['get'])
    def transactions(self, request, pk=None):
        bank_account = self.get_object()
        incoming = bank_account.incoming_payments.all().select_related('customer', 'currency')
        outgoing = bank_account.outgoing_payments.all().select_related('vendor', 'currency')
        return Response({
            'incoming_payments': ReceiptSerializer(incoming, many=True).data,
            'outgoing_payments': PaymentSerializer(outgoing, many=True).data,
        })


class CheckbookViewSet(viewsets.ModelViewSet):
    queryset = Checkbook.objects.all().select_related('bank_account')
    serializer_class = CheckbookSerializer
    filterset_fields = ['bank_account', 'status']


class CheckViewSet(viewsets.ModelViewSet):
    queryset = Check.objects.all().select_related('checkbook', 'payment')
    serializer_class = CheckSerializer
    filterset_fields = ['checkbook', 'status']


class BankReconciliationViewSet(viewsets.ModelViewSet):
    queryset = BankReconciliation.objects.all().select_related('bank_account', 'reconciled_by', 'approved_by')
    serializer_class = BankReconciliationSerializer
    filterset_fields = ['bank_account', 'status']

    @action(detail=True, methods=['post'])
    def reconcile(self, request, pk=None):
        recon = self.get_object()
        book_balance = recon.bank_account.current_balance

        deposits_in_transit = request.data.get('deposits_in_transit', 0)
        outstanding_checks = request.data.get('outstanding_checks', 0)
        bank_charges = request.data.get('bank_charges', 0)

        reconciled_balance = book_balance + deposits_in_transit - outstanding_checks - bank_charges
        difference = reconciled_balance - recon.statement_balance

        with transaction.atomic():
            recon.book_balance = book_balance
            recon.deposits_in_transit = deposits_in_transit
            recon.outstanding_checks = outstanding_checks
            recon.bank_charges = bank_charges
            recon.reconciled_balance = reconciled_balance
            recon.difference = difference
            recon.status = 'Reconciled'
            recon.reconciled_by = request.user
            recon.save()

        return Response(BankReconciliationSerializer(recon).data)


class CashFlowCategoryViewSet(viewsets.ModelViewSet):
    queryset = CashFlowCategory.objects.all()
    serializer_class = CashFlowCategorySerializer
    filterset_fields = ['category_type', 'is_active']


class CashFlowForecastViewSet(viewsets.ModelViewSet):
    queryset = CashFlowForecast.objects.all().select_related('bank_account')
    serializer_class = CashFlowForecastSerializer
    filterset_fields = ['bank_account']


# =============================================================================
# TAX ENGINE VIEWS
# =============================================================================

class TaxRegistrationViewSet(viewsets.ModelViewSet):
    queryset = TaxRegistration.objects.all()
    serializer_class = TaxRegistrationSerializer
    filterset_fields = ['tax_type', 'is_active']


class TaxExemptionViewSet(viewsets.ModelViewSet):
    queryset = TaxExemption.objects.all().select_related('tax_registration', 'vendor', 'customer')
    serializer_class = TaxExemptionSerializer
    filterset_fields = ['tax_registration', 'is_active']


class TaxReturnViewSet(viewsets.ModelViewSet):
    queryset = TaxReturn.objects.all().select_related('tax_registration')
    serializer_class = TaxReturnSerializer
    filterset_fields = ['tax_registration', 'status', 'tax_type']

    @action(detail=True, methods=['post'])
    def calculate(self, request, pk=None):
        tax_return = self.get_object()
        tax_return.tax_due = tax_return.output_tax - tax_return.input_tax
        tax_return.save()
        return Response(TaxReturnSerializer(tax_return).data)


class WithholdingTaxViewSet(viewsets.ModelViewSet):
    queryset = WithholdingTax.objects.all().select_related('withholding_account')
    serializer_class = WithholdingTaxSerializer
    filterset_fields = ['income_type', 'is_active']
    search_fields = ['code', 'name', 'income_type']
    pagination_class = AccountingPagination


class TaxCodeViewSet(viewsets.ModelViewSet):
    queryset = TaxCode.objects.all().select_related('tax_account')
    serializer_class = TaxCodeSerializer
    filterset_fields = ['tax_type', 'direction', 'is_active']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination


# =============================================================================
# COST CENTER VIEWS
# =============================================================================

class CostCenterViewSet(viewsets.ModelViewSet):
    queryset = CostCenter.objects.all().select_related('parent', 'manager', 'gl_account')
    serializer_class = CostCenterSerializer
    filterset_fields = ['center_type', 'is_active']
    search_fields = ['name', 'code']


class ProfitCenterViewSet(viewsets.ModelViewSet):
    queryset = ProfitCenter.objects.all().select_related('manager').prefetch_related('cost_centers')
    serializer_class = ProfitCenterSerializer
    filterset_fields = ['is_active']


class CostAllocationRuleViewSet(viewsets.ModelViewSet):
    queryset = CostAllocationRule.objects.all().select_related('source_cost_center', 'source_account')
    serializer_class = CostAllocationRuleSerializer
    filterset_fields = ['allocation_method', 'is_active']


# =============================================================================
# INTERCOMPANY VIEWS
# =============================================================================

class InterCompanyViewSet(viewsets.ModelViewSet):
    queryset = InterCompany.objects.all().select_related('default_currency')
    serializer_class = InterCompanySerializer
    filterset_fields = ['is_active']


class InterCompanyTransactionViewSet(viewsets.ModelViewSet):
    queryset = InterCompanyTransaction.objects.all().select_related('inter_company', 'currency')
    serializer_class = InterCompanyTransactionSerializer
    filterset_fields = ['inter_company', 'transaction_type', 'status']


class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.all().select_related('currency', 'parent_company')
    serializer_class = CompanySerializer
    filterset_fields = ['company_type', 'is_active', 'is_internal']
    search_fields = ['name', 'company_code']


class InterCompanyConfigViewSet(viewsets.ModelViewSet):
    queryset = InterCompanyConfig.objects.all().select_related('company', 'partner_company', 'ar_account', 'ap_account', 'expense_account', 'revenue_account')
    serializer_class = InterCompanyConfigSerializer
    filterset_fields = ['company', 'partner_company', 'is_active']


class InterCompanyInvoiceViewSet(viewsets.ModelViewSet):
    queryset = InterCompanyInvoice.objects.all().select_related('from_company', 'to_company', 'currency', 'created_by')
    serializer_class = InterCompanyInvoiceSerializer
    filterset_fields = ['from_company', 'to_company', 'status']
    search_fields = ['invoice_number']

    @action(detail=True, methods=['post'])
    def post_invoice(self, request, pk=None):
        from .services import InterCompanyPostingService
        invoice = self.get_object()
        result = InterCompanyPostingService.post_ic_invoice(invoice)
        return Response(result)

    @action(detail=False, methods=['get'])
    def pending(self, request):
        pending = self.queryset.filter(status='Approved', auto_posted=False)
        return Response(InterCompanyInvoiceSerializer(pending, many=True).data)


class InterCompanyTransferViewSet(viewsets.ModelViewSet):
    queryset = InterCompanyTransfer.objects.all().select_related('from_company', 'to_company')
    serializer_class = InterCompanyTransferSerializer
    filterset_fields = ['from_company', 'to_company', 'status']
    search_fields = ['transfer_number']


class InterCompanyAllocationViewSet(viewsets.ModelViewSet):
    queryset = InterCompanyAllocation.objects.all().select_related('source_company', 'currency')
    serializer_class = InterCompanyAllocationSerializer
    filterset_fields = ['source_company', 'status']
    search_fields = ['allocation_number']


class InterCompanyCashTransferViewSet(viewsets.ModelViewSet):
    queryset = InterCompanyCashTransfer.objects.all().select_related('from_company', 'to_company', 'currency')
    serializer_class = InterCompanyCashTransferSerializer
    filterset_fields = ['from_company', 'to_company', 'status']
    search_fields = ['transfer_number']


class ConsolidationRunViewSet(viewsets.ModelViewSet):
    queryset = ConsolidationRun.objects.all().select_related('group', 'period', 'run_by')
    serializer_class = ConsolidationRunSerializer
    filterset_fields = ['group', 'status']

    @action(detail=False, methods=['post'])
    def run_consolidation(self, request):
        from .services import ConsolidationService
        group_id = request.data.get('group_id')
        period_id = request.data.get('period_id')
        result = ConsolidationService.run_consolidation(group_id, period_id, request.user)
        return Response(result)


# =============================================================================
# ADVANCED REPORTING VIEWS
# =============================================================================

class FinancialReportTemplateViewSet(viewsets.ModelViewSet):
    queryset = FinancialReportTemplate.objects.all()
    serializer_class = FinancialReportTemplateSerializer
    filterset_fields = ['report_type', 'is_active']


class FinancialReportViewSet(viewsets.ModelViewSet):
    queryset = FinancialReport.objects.all().select_related('template', 'prepared_by', 'approved_by')
    serializer_class = FinancialReportSerializer
    filterset_fields = ['report_type', 'status']

    @action(detail=True, methods=['post'])
    def generate(self, request, pk=None):
        report = self.get_object()
        # Generate report data based on type
        # This would typically call reporting logic
        report.status = 'Generated'
        report.save()
        return Response(FinancialReportSerializer(report).data)


# =============================================================================
# DOCUMENT MANAGEMENT VIEWS
# =============================================================================

class AccountingDocumentViewSet(viewsets.ModelViewSet):
    queryset = AccountingDocument.objects.all().select_related('uploaded_by', 'verified_by', 'linked_journal')
    serializer_class = AccountingDocumentSerializer
    filterset_fields = ['document_type', 'is_verified']
    search_fields = ['title', 'reference_number']


# =============================================================================
# CONSOLIDATION VIEWS
# =============================================================================

class ConsolidationGroupViewSet(viewsets.ModelViewSet):
    queryset = ConsolidationGroup.objects.all().select_related('parent_company').prefetch_related('companies')
    serializer_class = ConsolidationGroupSerializer
    filterset_fields = ['is_active', 'consolidation_method']


class ConsolidationViewSet(viewsets.ModelViewSet):
    queryset = Consolidation.objects.all().select_related('consolidation_group', 'prepared_by', 'approved_by')
    serializer_class = ConsolidationSerializer
    filterset_fields = ['consolidation_group', 'status', 'fiscal_year']


# =============================================================================
# DEFERRED REVENUE/EXPENSE VIEWS
# =============================================================================

class DeferredRevenueViewSet(viewsets.ModelViewSet):
    queryset = DeferredRevenue.objects.all().select_related('customer', 'revenue_account', 'unearned_revenue_account')
    serializer_class = DeferredRevenueSerializer
    filterset_fields = ['customer', 'is_fully_recognized']


class DeferredExpenseViewSet(viewsets.ModelViewSet):
    queryset = DeferredExpense.objects.all().select_related('vendor', 'expense_account', 'prepaid_account')
    serializer_class = DeferredExpenseSerializer
    filterset_fields = ['vendor', 'is_fully_recognized']


# =============================================================================
# LEASE VIEWS
# =============================================================================

class LeaseViewSet(viewsets.ModelViewSet):
    queryset = Lease.objects.all().select_related('lessor', 'right_of_use_asset', 'lease_liability_account')
    serializer_class = LeaseSerializer
    filterset_fields = ['lease_type', 'status']


class LeasePaymentViewSet(viewsets.ModelViewSet):
    queryset = LeasePayment.objects.all().select_related('lease')
    serializer_class = LeasePaymentSerializer
    filterset_fields = ['lease', 'status']


# =============================================================================
# TREASURY VIEWS
# =============================================================================

class TreasuryForecastViewSet(viewsets.ModelViewSet):
    queryset = TreasuryForecast.objects.all()
    serializer_class = TreasuryForecastSerializer


class InvestmentViewSet(viewsets.ModelViewSet):
    queryset = Investment.objects.all().select_related('bank_account')
    serializer_class = InvestmentSerializer
    filterset_fields = ['investment_type', 'status']


class LoanViewSet(viewsets.ModelViewSet):
    queryset = Loan.objects.all().select_related('lender', 'loan_account', 'interest_expense_account')
    serializer_class = LoanSerializer
    filterset_fields = ['loan_type', 'status']


class LoanRepaymentViewSet(viewsets.ModelViewSet):
    queryset = LoanRepayment.objects.all().select_related('loan')
    serializer_class = LoanRepaymentSerializer
    filterset_fields = ['loan', 'status']


# =============================================================================
# FOREIGN CURRENCY REVALUATION VIEWS
# =============================================================================

class ExchangeRateHistoryViewSet(viewsets.ModelViewSet):
    queryset = ExchangeRateHistory.objects.all().select_related('from_currency', 'to_currency')
    serializer_class = ExchangeRateHistorySerializer
    filterset_fields = ['from_currency', 'to_currency']

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download a CSV template for exchange rate imports."""
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['from_currency_code', 'to_currency_code', 'rate_date', 'exchange_rate'])
        writer.writerow(['USD', 'EUR', '2026-01-01', '0.920000'])
        writer.writerow(['USD', 'GBP', '2026-01-01', '0.790000'])
        writer.writerow(['EUR', 'GBP', '2026-01-01', '0.858700'])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="exchange_rate_import_template.csv"'
        return response

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        """Import exchange rates from CSV/Excel file."""
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "A CSV or Excel file is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file)
            else:
                df = pd.read_csv(file)
        except Exception as e:
            return Response({"error": f"Failed to parse file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        df.columns = df.columns.str.strip().str.lower()
        required = {'from_currency_code', 'to_currency_code', 'rate_date', 'exchange_rate'}
        missing = required - set(df.columns)
        if missing:
            return Response({"error": f"Missing required columns: {', '.join(missing)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Build currency code→id lookup
        currency_map = {c.code.upper(): c for c in Currency.objects.all()}

        created_count = 0
        updated_count = 0
        errors = []

        for index, row in df.iterrows():
            row_num = index + 2
            try:
                from_code = str(row['from_currency_code']).strip().upper()
                to_code = str(row['to_currency_code']).strip().upper()
                rate_date = str(row['rate_date']).strip()
                rate_val = float(row['exchange_rate'])

                if from_code not in currency_map:
                    errors.append(f"Row {row_num}: Unknown currency code '{from_code}'.")
                    continue
                if to_code not in currency_map:
                    errors.append(f"Row {row_num}: Unknown currency code '{to_code}'.")
                    continue
                if from_code == to_code:
                    errors.append(f"Row {row_num}: From and To currency cannot be the same.")
                    continue

                from_obj = currency_map[from_code]
                to_obj = currency_map[to_code]

                existing = ExchangeRateHistory.objects.filter(
                    from_currency=from_obj, to_currency=to_obj, rate_date=rate_date,
                ).first()
                if existing:
                    existing.exchange_rate = rate_val
                    existing.save()
                    updated_count += 1
                else:
                    ExchangeRateHistory.objects.create(
                        from_currency=from_obj, to_currency=to_obj,
                        rate_date=rate_date, exchange_rate=rate_val,
                    )
                    created_count += 1

            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

        return Response({
            "success": True,
            "created": created_count,
            "updated": updated_count,
            "errors": errors,
        })

    @action(detail=False, methods=['get'], url_path='export')
    def export_data(self, request):
        """Export exchange rates as CSV."""
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['from_currency_code', 'to_currency_code', 'rate_date', 'exchange_rate'])

        for r in self.get_queryset():
            writer.writerow([r.from_currency.code, r.to_currency.code, str(r.rate_date), str(r.exchange_rate)])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="exchange_rates_export.csv"'
        return response


class ForeignCurrencyRevaluationViewSet(viewsets.ModelViewSet):
    queryset = ForeignCurrencyRevaluation.objects.all().select_related('period', 'base_currency', 'gain_account', 'loss_account')
    serializer_class = ForeignCurrencyRevaluationSerializer
    filterset_fields = ['period', 'status']


# =============================================================================
# FISCAL PERIOD VIEWS
# =============================================================================

class FiscalPeriodViewSet(viewsets.ModelViewSet):
    queryset = FiscalPeriod.objects.all()
    serializer_class = FiscalPeriodSerializer
    filterset_fields = ['fiscal_year', 'period_type', 'status']
    ordering_fields = ['fiscal_year', 'period_number']

    def get_queryset(self):
        queryset = super().get_queryset()
        year = self.request.query_params.get('year')
        if year:
            queryset = queryset.filter(fiscal_year=int(year))
        return queryset

    @action(detail=False, methods=['post'])
    def close_periods(self, request):
        from django.utils import timezone
        close_type = request.data.get('close_type')  # 'daily', 'monthly', 'yearly'
        target_date = request.data.get('target_date')
        close_all_upto = request.data.get('close_all_upto', True)
        reason = request.data.get('reason', '')

        periods_to_close = []
        if close_type == 'daily':
            periods = self.queryset.filter(start_date__lte=target_date, status__in=['Open', 'Locked'])
            if close_all_upto:
                periods = periods.filter(end_date__lte=target_date)
        elif close_type == 'monthly':
            from datetime import datetime
            target = datetime.strptime(target_date, '%Y-%m-%d').date()
            periods = self.queryset.filter(
                fiscal_year=target.year,
                period_number=target.month,
                status__in=['Open', 'Locked']
            )
        elif close_type == 'yearly':
            periods = self.queryset.filter(fiscal_year=int(target_date), status__in=['Open', 'Locked'])
        else:
            return Response({'error': 'Invalid close_type'}, status=status.HTTP_400_BAD_REQUEST)

        for period in periods:
            period.is_closed = True
            period.status = 'Closed'
            period.closed_by = request.user
            period.closed_date = timezone.now()
            period.closed_reason = reason
            period.save()
            periods_to_close.append(period.id)

        return Response({
            'message': f'Closed {len(periods_to_close)} periods',
            'periods': periods_to_close
        })

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        from django.utils import timezone
        period = self.get_object()
        reason = request.data.get('reason', '')
        period.is_closed = True
        period.status = 'Closed'
        period.closed_by = request.user
        period.closed_date = timezone.now()
        period.closed_reason = reason
        period.save()
        return Response(FiscalPeriodSerializer(period).data)

    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        period = self.get_object()
        reason = request.data.get('reason', '')
        period.is_closed = False
        period.status = 'Open'
        period.closed_by = None
        period.closed_date = None
        period.closed_reason = reason
        period.save()
        return Response(FiscalPeriodSerializer(period).data)

    @action(detail=True, methods=['post'])
    def grant_access(self, request, pk=None):
        period = self.get_object()
        user_id = request.data.get('user_id')
        access_type = request.data.get('access_type', 'Temporary')
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        reason = request.data.get('reason', '')

        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        access = PeriodAccess.objects.create(
            period=period,
            user=user,
            access_type=access_type,
            start_date=start_date,
            end_date=end_date,
            granted_by=request.user,
            reason=reason,
            is_active=True
        )

        return Response(PeriodAccessSerializer(access).data)

    @action(detail=True, methods=['get'])
    def access_list(self, request, pk=None):
        period = self.get_object()
        accesses = period.access_grants.all()
        return Response(PeriodAccessSerializer(accesses, many=True).data)


class FiscalYearViewSet(viewsets.ModelViewSet):
    queryset = FiscalYear.objects.all()
    serializer_class = FiscalYearSerializer
    filterset_fields = ['year', 'status', 'period_type']
    ordering_fields = ['year']

    @action(detail=False, methods=['post'])
    def create_year(self, request):
        year = request.data.get('year')
        name = request.data.get('name')
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        period_type = request.data.get('period_type', 'Monthly')

        if FiscalYear.objects.filter(year=year).exists():
            return Response({'error': f'Fiscal year {year} already exists'}, status=status.HTTP_400_BAD_REQUEST)

        from datetime import date, timedelta

        with transaction.atomic():
            fiscal_year = FiscalYear.objects.create(
                year=year,
                name=name,
                start_date=start_date,
                end_date=end_date,
                period_type=period_type,
                status='Open'
            )

            periods = []
            if period_type == 'Daily':
                current_date = start_date if isinstance(start_date, date) else datetime.strptime(str(start_date), '%Y-%m-%d').date()
                end_dt = end_date if isinstance(end_date, date) else datetime.strptime(str(end_date), '%Y-%m-%d').date()
                period_num = 1
                while current_date <= end_dt:
                    periods.append(FiscalPeriod(
                        fiscal_year=year,
                        period_number=period_num,
                        period_type='Daily',
                        start_date=current_date,
                        end_date=current_date,
                        status='Open'
                    ))
                    current_date += timedelta(days=1)
                    period_num += 1
            elif period_type == 'Monthly':
                start = datetime.strptime(str(start_date), '%Y-%m-%d').date() if not isinstance(start_date, date) else start_date
                end = datetime.strptime(str(end_date), '%Y-%m-%d').date() if not isinstance(end_date, date) else end_date
                period_num = 1
                current_year = start.year
                current_month = start.month
                while (current_year, current_month) <= (end.year, end.month):
                    month_start = date(current_year, current_month, 1)
                    if current_month == 12:
                        month_end = date(current_year + 1, 1, 1) - timedelta(days=1)
                    else:
                        month_end = date(current_year, current_month + 1, 1) - timedelta(days=1)
                    periods.append(FiscalPeriod(
                        fiscal_year=year,
                        period_number=period_num,
                        period_type='Monthly',
                        start_date=month_start,
                        end_date=month_end,
                        status='Open'
                    ))
                    period_num += 1
                    if current_month == 12:
                        current_month = 1
                        current_year += 1
                    else:
                        current_month += 1
            else:
                periods.append(FiscalPeriod(
                    fiscal_year=year,
                    period_number=1,
                    period_type='Yearly',
                    start_date=start_date,
                    end_date=end_date,
                    status='Open'
                ))

            if periods:
                FiscalPeriod.objects.bulk_create(periods)

        return Response(FiscalYearSerializer(fiscal_year).data)

    @action(detail=True, methods=['post'])
    def set_active(self, request, pk=None):
        fiscal_year = self.get_object()
        FiscalYear.objects.filter(is_active=True).update(is_active=False)
        fiscal_year.is_active = True
        fiscal_year.save()
        return Response(FiscalYearSerializer(fiscal_year).data)

    @action(detail=True, methods=['post'])
    def close_year(self, request, pk=None):
        from django.utils import timezone
        fiscal_year = self.get_object()
        reason = request.data.get('reason', '')
        fiscal_year.status = 'Closed'
        fiscal_year.closed_by = request.user
        fiscal_year.closed_date = timezone.now()
        fiscal_year.save()

        fiscal_year.periods.update(status='Closed', is_closed=True)
        return Response(FiscalYearSerializer(fiscal_year).data)


class PeriodAccessViewSet(viewsets.ModelViewSet):
    queryset = PeriodAccess.objects.all()
    serializer_class = PeriodAccessSerializer
    filterset_fields = ['period', 'user', 'access_type', 'is_active']

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        access = self.get_object()
        access.is_active = False
        access.save()
        return Response(PeriodAccessSerializer(access).data)


class PeriodCloseCheckViewSet(viewsets.ModelViewSet):
    queryset = PeriodCloseCheck.objects.all().select_related('period', 'checked_by')
    serializer_class = PeriodCloseCheckSerializer
    filterset_fields = ['period', 'check_category', 'is_passed']


# =============================================================================
# ASSET ENHANCEMENT VIEWS
# =============================================================================

class AssetClassViewSet(viewsets.ModelViewSet):
    queryset = AssetClass.objects.all().select_related(
        'asset_account', 'accumulated_depreciation_account',
        'depreciation_expense_account', 'disposal_gain_account', 'disposal_loss_account'
    )
    serializer_class = AssetClassSerializer
    filterset_fields = ['is_active']
    search_fields = ['name', 'code']


class AssetConfigurationViewSet(viewsets.ModelViewSet):
    queryset = AssetConfiguration.objects.all()
    serializer_class = AssetConfigurationSerializer


class AssetCategoryViewSet(viewsets.ModelViewSet):
    queryset = AssetCategory.objects.all().select_related(
        'cost_account',
        'accumulated_depreciation_account', 'depreciation_expense_account',
    )
    serializer_class = AssetCategorySerializer
    filterset_fields = ['is_active', 'depreciation_method']
    search_fields = ['name', 'code']
    pagination_class = AccountingPagination


class AssetLocationViewSet(viewsets.ModelViewSet):
    queryset = AssetLocation.objects.all().select_related('parent', 'manager')
    serializer_class = AssetLocationSerializer
    filterset_fields = ['is_active']
    search_fields = ['name', 'code']


class AssetInsuranceViewSet(viewsets.ModelViewSet):
    queryset = AssetInsurance.objects.all().select_related('asset')
    serializer_class = AssetInsuranceSerializer
    filterset_fields = ['asset', 'is_active']


class AssetMaintenanceViewSet(viewsets.ModelViewSet):
    queryset = AssetMaintenance.objects.all().select_related('asset', 'vendor')
    serializer_class = AssetMaintenanceSerializer
    filterset_fields = ['asset', 'maintenance_type', 'status']


class AssetTransferViewSet(viewsets.ModelViewSet):
    queryset = AssetTransfer.objects.all().select_related(
        'asset', 'from_location', 'to_location',
        'from_employee', 'to_employee', 'approved_by'
    )
    serializer_class = AssetTransferSerializer
    filterset_fields = ['asset', 'status']


class AssetDepreciationScheduleViewSet(viewsets.ModelViewSet):
    queryset = AssetDepreciationSchedule.objects.all().select_related('asset', 'period')
    serializer_class = AssetDepreciationScheduleSerializer
    filterset_fields = ['asset', 'period', 'is_posted']


class AssetRevaluationViewSet(viewsets.ModelViewSet):
    queryset = AssetRevaluation.objects.all().select_related('asset', 'revaluation_account', 'approved_by')
    serializer_class = AssetRevaluationSerializer
    filterset_fields = ['asset', 'status']


class AssetDisposalViewSet(viewsets.ModelViewSet):
    queryset = AssetDisposal.objects.all().select_related('asset', 'approved_by')
    serializer_class = AssetDisposalSerializer
    filterset_fields = ['asset', 'status', 'disposal_method']


class AssetImpairmentViewSet(viewsets.ModelViewSet):
    queryset = AssetImpairment.objects.all().select_related('asset', 'impairment_account', 'approved_by')
    serializer_class = AssetImpairmentSerializer
    filterset_fields = ['asset', 'status']


# =============================================================================
# ADVANCED ACCOUNTING VIEWSETS
# =============================================================================

class RecurringJournalViewSet(viewsets.ModelViewSet):
    queryset = RecurringJournal.objects.all().prefetch_related('lines')
    serializer_class = RecurringJournalSerializer
    filterset_fields = ['frequency', 'is_active']
    search_fields = ['name', 'code']

    @action(detail=False, methods=['get'])
    def default_dates(self, request):
        """Get default posting and reversal dates"""
        from accounting.utils import get_default_posting_and_reversal_dates
        return Response(get_default_posting_and_reversal_dates())

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """Generate journals from recurring templates"""
        from .advanced_services import RecurringJournalService
        result = RecurringJournalService.generate_journals()
        return Response(result)

    @action(detail=True, methods=['post'])
    def generate_now(self, request, pk=None):
        """Generate a single journal from template immediately"""
        from .advanced_services import RecurringJournalService
        template = self.get_object()

        try:
            journal = RecurringJournalService.generate_single_journal(template, request.user)
            return Response({
                'status': 'success',
                'journal_id': journal.id,
                'journal_number': journal.reference_number
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def generate_once(self, request, pk=None):
        """Generate a single journal from template"""
        from .advanced_services import RecurringJournalService
        template = self.get_object()

        today = timezone.now().date()
        result = RecurringJournalService.generate_journals()

        if template.code in result.get('generated', []):
            return Response({'status': 'Journal generated successfully'})
        elif result.get('errors'):
            return Response({'error': result['errors']}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'status': 'No journals generated'})


class RecurringJournalRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RecurringJournalRun.objects.all().select_related('recurring_journal', 'journal')
    serializer_class = RecurringJournalRunSerializer
    filterset_fields = ['recurring_journal', 'status']


class AccrualViewSet(viewsets.ModelViewSet):
    queryset = Accrual.objects.all().select_related('account', 'counterpart_account', 'period', 'journal_entry')
    serializer_class = AccrualSerializer
    filterset_fields = ['accrual_type', 'is_reversed', 'is_posted', 'period']

    @action(detail=False, methods=['get'])
    def default_dates(self, request):
        """Get default posting and reversal dates"""
        from accounting.utils import get_default_posting_and_reversal_dates
        return Response(get_default_posting_and_reversal_dates())

    @action(detail=True, methods=['post'])
    def post(self, request, pk=None):
        """Post an accrual to create a journal entry"""
        from .advanced_services import AccrualDeferralService
        accrual = self.get_object()

        try:
            journal = AccrualDeferralService.post_accrual(accrual, request.user)
            return Response({
                'status': 'success',
                'journal_id': journal.id,
                'journal_number': journal.reference_number
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        """Reverse an accrual"""
        from .advanced_services import AccrualDeferralService
        accrual = self.get_object()

        try:
            journal = AccrualDeferralService.reverse_accrual(accrual, request.user)
            return Response({
                'status': 'success',
                'journal_id': journal.id,
                'journal_number': journal.reference_number
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def reverse_all(self, request):
        """Reverse all due accruals for a period"""
        from .advanced_services import AccrualDeferralService
        from .models import BudgetPeriod

        period_id = request.data.get('period_id')
        if not period_id:
            return Response({'error': 'period_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            period = BudgetPeriod.objects.get(pk=period_id)
            count = AccrualDeferralService.reverse_accruals(period)
            return Response({'status': f'{count} accruals reversed'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class DeferralViewSet(viewsets.ModelViewSet):
    queryset = Deferral.objects.all().select_related('account', 'counterpart_account')
    serializer_class = DeferralSerializer
    filterset_fields = ['deferral_type', 'is_active', 'is_fully_recognized']

    @action(detail=False, methods=['post'])
    def recognize_all(self, request):
        """Recognize deferrals for a period"""
        from .advanced_services import AccrualDeferralService
        from .models import BudgetPeriod

        period_id = request.data.get('period_id')
        if not period_id:
            return Response({'error': 'period_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            period = BudgetPeriod.objects.get(pk=period_id)
            count = AccrualDeferralService.recognize_deferrals(period)
            return Response({'status': f'{count} deferrals recognized'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PeriodStatusViewSet(viewsets.ModelViewSet):
    queryset = PeriodStatus.objects.all().select_related('period', 'closed_by')
    serializer_class = PeriodStatusSerializer
    filterset_fields = ['status']

    @action(detail=True, methods=['post'])
    def close_period(self, request, pk=None):
        """Close a period"""
        from .advanced_services import PeriodClosingService
        status_obj = self.get_object()

        try:
            result = PeriodClosingService.close_period(status_obj.period, request.user)
            return Response(PeriodStatusSerializer(result).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def open_period(self, request, pk=None):
        """Reopen a period"""
        from .advanced_services import PeriodClosingService
        status_obj = self.get_object()

        try:
            result = PeriodClosingService.open_period(status_obj.period, request.user)
            return Response(PeriodStatusSerializer(result).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def lock_period(self, request, pk=None):
        """Lock a period"""
        from .advanced_services import PeriodClosingService
        status_obj = self.get_object()

        reason = request.data.get('reason', 'Manual lock')

        try:
            result = PeriodClosingService.lock_period(status_obj.period, request.user, reason)
            return Response(PeriodStatusSerializer(result).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class YearEndClosingViewSet(viewsets.ModelViewSet):
    queryset = YearEndClosing.objects.all().select_related('closing_journal', 'opening_journal', 'closed_by')
    serializer_class = YearEndClosingSerializer
    filterset_fields = ['fiscal_year', 'status']

    @action(detail=False, methods=['post'])
    def close_year(self, request):
        """Close a fiscal year"""
        from .advanced_services import YearEndClosingService

        fiscal_year = request.data.get('fiscal_year')
        if not fiscal_year:
            return Response({'error': 'fiscal_year is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = YearEndClosingService.close_year(int(fiscal_year), request.user)
            return Response(YearEndClosingSerializer(result).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class RetainedEarningsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RetainedEarnings.objects.all()
    serializer_class = RetainedEarningsSerializer
    filterset_fields = ['fiscal_year']


class CurrencyRevaluationViewSet(viewsets.ModelViewSet):
    queryset = CurrencyRevaluation.objects.all().select_related('currency', 'journal_entry')
    serializer_class = CurrencyRevaluationSerializer
    filterset_fields = ['currency', 'status']

    @action(detail=False, methods=['post'])
    def revaluate(self, request):
        """Perform currency revaluation"""
        from .advanced_services import CurrencyRevaluationService
        from .models import Currency

        currency_id = request.data.get('currency_id')
        exchange_rate = request.data.get('exchange_rate')

        if not currency_id or not exchange_rate:
            return Response({'error': 'currency_id and exchange_rate are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            currency = Currency.objects.get(pk=currency_id)
            result = CurrencyRevaluationService.revaluate(
                currency,
                Decimal(str(exchange_rate)),
                timezone.now().date(),
                request.user
            )
            return Response(CurrencyRevaluationSerializer(result).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class BalanceSheetViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Balance Sheet report"""
        from .reports import FinancialReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = FinancialReportService.generate_balance_sheet(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class IncomeStatementViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Income Statement report"""
        from .reports import FinancialReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = FinancialReportService.generate_income_statement(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CashFlowStatementViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Cash Flow Statement report"""
        from .reports import FinancialReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        method = request.data.get('method', 'direct')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if method == 'indirect':
                report = FinancialReportService.generate_cash_flow_indirect(start, end)
            else:
                report = FinancialReportService.generate_cash_flow_direct(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BudgetVsActualViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Budget vs Actual report"""
        from .reports import BudgetReportService

        budget_period_id = request.data.get('budget_period_id')
        fund_id = request.data.get('fund_id')
        mda_id = request.data.get('mda_id')

        if not budget_period_id:
            return Response({'error': 'budget_period_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = BudgetReportService.generate_budget_vs_actual(
                budget_period_id=budget_period_id,
                fund_id=fund_id,
                mda_id=mda_id
            )
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BudgetPerformanceViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Budget Performance report"""
        from .reports import BudgetReportService

        fiscal_year = request.data.get('fiscal_year')
        fund_id = request.data.get('fund_id')

        if not fiscal_year:
            return Response({'error': 'fiscal_year is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = BudgetReportService.generate_budget_performance(
                fiscal_year=int(fiscal_year),
                fund_id=fund_id
            )
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CostCenterReportViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Cost Center report"""
        from .reports import CostCenterReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        cost_center_id = request.data.get('cost_center_id')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = CostCenterReportService.generate_cost_center_report(
                start_date=start,
                end_date=end,
                cost_center_id=cost_center_id
            )
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class IFRSComparisonViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate IFRS Comparison report"""
        from .reports import IFRSReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        fiscal_year = request.data.get('fiscal_year')

        if not start_date or not end_date or not fiscal_year:
            return Response({'error': 'start_date, end_date, and fiscal_year are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            year = int(fiscal_year)
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = IFRSReportService.generate_ifrs_comparison_report(
                start_date=start,
                end_date=end,
                fiscal_year=year
            )
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GeneralLedgerViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate General Ledger report"""
        from .reports import GeneralLedgerReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        account_code = request.data.get('account_code')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = GeneralLedgerReportService.generate_general_ledger(
                start_date=start,
                end_date=end,
                account_code=account_code
            )
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TrialBalanceViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Trial Balance report"""
        from .reports import TrialBalanceReportService
        from datetime import datetime

        end_date = request.data.get('end_date')
        start_date = request.data.get('start_date', '1900-01-01')

        if not end_date:
            return Response({'error': 'end_date is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = TrialBalanceReportService.generate_trial_balance(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InventoryStockValuationViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Inventory Stock Valuation report"""
        from .reports import InventoryReportService

        warehouse_id = request.data.get('warehouse_id')

        try:
            report = InventoryReportService.generate_stock_valuation(warehouse_id)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InventoryLowStockViewSet(viewsets.ViewSet):

    def list(self, request):
        """Generate Low Stock Alert report"""
        from .reports import InventoryReportService

        try:
            report = InventoryReportService.generate_low_stock_report()
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InventoryMovementViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Stock Movement report"""
        from .reports import InventoryReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = InventoryReportService.generate_stock_movement(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class HRHeadcountViewSet(viewsets.ViewSet):

    def list(self, request):
        """Generate Headcount Report"""
        from .reports import HRReportService

        try:
            report = HRReportService.generate_headcount_report()
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class HRPayrollSummaryViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Payroll Summary Report"""
        from .reports import HRReportService

        month = request.data.get('month')
        year = request.data.get('year')

        if not month or not year:
            return Response({'error': 'month and year are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = HRReportService.generate_payroll_summary(int(month), int(year))
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SalesSummaryViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Sales Summary Report"""
        from .reports import SalesReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = SalesReportService.generate_sales_summary(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SalesCustomersViewSet(viewsets.ViewSet):

    def list(self, request):
        """Generate Customers Report"""
        from .reports import SalesReportService

        try:
            report = SalesReportService.generate_customers_report()
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProcurementSummaryViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Purchase Summary Report"""
        from .reports import ProcurementReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = ProcurementReportService.generate_purchase_summary(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProcurementVendorsViewSet(viewsets.ViewSet):

    def list(self, request):
        """Generate Vendors Report"""
        from .reports import ProcurementReportService

        try:
            report = ProcurementReportService.generate_vendors_report()
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductionSummaryViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Production Summary Report"""
        from .reports import ProductionReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = ProductionReportService.generate_production_summary(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductionMaterialConsumptionViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Material Consumption Report"""
        from .reports import ProductionReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = ProductionReportService.generate_material_consumption(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductionCostReportViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Production Cost & Profitability Report"""
        from .reports import ProductionReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = ProductionReportService.generate_production_cost_report(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductProfitabilityViewSet(viewsets.ViewSet):

    def create(self, request):
        """Generate Product Profitability Analysis Report"""
        from .reports import ProductionReportService
        from datetime import datetime

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')

        if not start_date or not end_date:
            return Response({'error': 'start_date and end_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = ProductionReportService.generate_product_profitability(start, end)
            return Response(report)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===================== Accounting Settings =====================

@api_view(['GET', 'PUT'])
@perm_classes([IsAuthenticated])
def accounting_settings_api(request):
    """GET/PUT the per-tenant accounting settings (singleton)."""
    settings_obj, _ = AccountingSettings.objects.get_or_create(pk=1)

    if request.method == 'GET':
        serializer = AccountingSettingsSerializer(settings_obj)
        return Response(serializer.data)

    serializer = AccountingSettingsSerializer(settings_obj, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(['POST'])
@perm_classes([IsAuthenticated])
def seed_default_coa(request):
    """Auto-seed a default Chart of Accounts based on the configured digit count."""
    settings_obj, _ = AccountingSettings.objects.get_or_create(pk=1)
    digits = settings_obj.account_code_digits

    def pad(prefix, sub):
        """Build a zero-padded account code.
        e.g. digits=8, prefix='1', sub='001' → '10010000'
        """
        raw = prefix + sub
        return raw.ljust(digits, '0')[:digits]

    seed_accounts = [
        # 1-series: Assets
        (pad('1', '001'), 'Cash and Cash Equivalents', 'Asset'),
        (pad('1', '002'), 'Bank Accounts', 'Asset'),
        (pad('1', '003'), 'Accounts Receivable', 'Asset'),
        (pad('1', '004'), 'Prepaid Expenses', 'Asset'),
        (pad('1', '005'), 'Inventory', 'Asset'),
        (pad('1', '006'), 'Fixed Assets', 'Asset'),
        (pad('1', '007'), 'Accumulated Depreciation', 'Asset'),
        # 2-series: Liabilities
        (pad('2', '001'), 'Accounts Payable', 'Liability'),
        (pad('2', '002'), 'Accrued Liabilities', 'Liability'),
        (pad('2', '003'), 'Short-term Loans', 'Liability'),
        (pad('2', '004'), 'Long-term Debt', 'Liability'),
        # 3-series: Equity
        (pad('3', '001'), "Owner's Equity", 'Equity'),
        (pad('3', '002'), 'Retained Earnings', 'Equity'),
        (pad('3', '003'), 'Capital Reserves', 'Equity'),
        # 4-series: Income
        (pad('4', '001'), 'Service Revenue', 'Income'),
        (pad('4', '002'), 'Sales Revenue', 'Income'),
        (pad('4', '003'), 'Interest Income', 'Income'),
        (pad('4', '004'), 'Other Income', 'Income'),
        # 5-series: COGS / Production Expenses
        (pad('5', '001'), 'Cost of Goods Sold', 'Expense'),
        (pad('5', '002'), 'Materials', 'Expense'),
        (pad('5', '003'), 'Direct Labor', 'Expense'),
        # 6-series: General / Admin Expenses
        (pad('6', '001'), 'Salaries and Wages', 'Expense'),
        (pad('6', '002'), 'Rent Expense', 'Expense'),
        (pad('6', '003'), 'Utilities', 'Expense'),
        (pad('6', '004'), 'Office Supplies', 'Expense'),
        (pad('6', '005'), 'Depreciation Expense', 'Expense'),
        (pad('6', '006'), 'Travel Expense', 'Expense'),
        (pad('6', '007'), 'Insurance Expense', 'Expense'),
    ]

    existing_codes = set(Account.objects.values_list('code', flat=True))
    created = 0
    skipped = 0
    to_create = []

    for code, name, account_type in seed_accounts:
        if code in existing_codes:
            skipped += 1
        else:
            to_create.append(Account(code=code, name=name, account_type=account_type, is_active=True))
            created += 1

    if to_create:
        Account.objects.bulk_create(to_create)

    return Response({
        'success': True,
        'created': created,
        'skipped': skipped,
        'total_seed': len(seed_accounts),
    })
