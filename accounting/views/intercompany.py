from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from .common import AccountingPagination
from ..models import (
    InterCompany, InterCompanyTransaction, Company, InterCompanyConfig,
    InterCompanyInvoice, InterCompanyTransfer, InterCompanyAllocation,
    InterCompanyCashTransfer, ConsolidationRun,
    FinancialReportTemplate, FinancialReport,
    AccountingDocument,
    ConsolidationGroup, Consolidation,
)
from ..serializers import (
    InterCompanySerializer, InterCompanyTransactionSerializer,
    CompanySerializer, InterCompanyConfigSerializer,
    InterCompanyInvoiceSerializer, InterCompanyTransferSerializer,
    InterCompanyAllocationSerializer, InterCompanyCashTransferSerializer,
    ConsolidationRunSerializer,
    FinancialReportTemplateSerializer, FinancialReportSerializer,
    AccountingDocumentSerializer,
    ConsolidationGroupSerializer, ConsolidationSerializer,
)


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
        from ..services import InterCompanyPostingService
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
        from ..services import ConsolidationService
        group_id = request.data.get('group_id')
        period_id = request.data.get('period_id')
        result = ConsolidationService.run_consolidation(group_id, period_id, request.user)
        return Response(result)


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


class AccountingDocumentViewSet(viewsets.ModelViewSet):
    queryset = AccountingDocument.objects.all().select_related('uploaded_by', 'verified_by', 'linked_journal')
    serializer_class = AccountingDocumentSerializer
    filterset_fields = ['document_type', 'is_verified']
    search_fields = ['title', 'reference_number']


class ConsolidationGroupViewSet(viewsets.ModelViewSet):
    queryset = ConsolidationGroup.objects.all().select_related('parent_company').prefetch_related('companies')
    serializer_class = ConsolidationGroupSerializer
    filterset_fields = ['is_active', 'consolidation_method']


class ConsolidationViewSet(viewsets.ModelViewSet):
    queryset = Consolidation.objects.all().select_related('consolidation_group', 'prepared_by', 'approved_by')
    serializer_class = ConsolidationSerializer
    filterset_fields = ['consolidation_group', 'status', 'fiscal_year']
