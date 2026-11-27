"""
revenue_admin viewsets — module_key = 'revenue_admin'.
"""
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import ModuleEnabled, RBACPermission
from . import lifecycle
from .models import (
    CollectionApplication,
    Taxpayer,
    TaxAccount,
    Assessment,
    BillingRun,
    DemandNotice,
    ArrearsLedger,
    EnforcementCase,
    TaxClearanceCertificate,
)
from .serializers import (
    CollectionApplicationSerializer,
    TaxpayerSerializer,
    TaxAccountSerializer,
    AssessmentSerializer,
    BillingRunSerializer,
    DemandNoticeSerializer,
    ArrearsLedgerSerializer,
    EnforcementCaseSerializer,
    TaxClearanceCertificateSerializer,
)


class TaxpayerViewSet(viewsets.ModelViewSet):
    module_key = 'revenue_admin'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = Taxpayer.objects.all()
    serializer_class = TaxpayerSerializer
    filterset_fields = ['case_type', 'is_active', 'tin']


class TaxAccountViewSet(viewsets.ModelViewSet):
    module_key = 'revenue_admin'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TaxAccount.objects.all()
    serializer_class = TaxAccountSerializer


class AssessmentViewSet(viewsets.ModelViewSet):
    module_key = 'revenue_admin'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = Assessment.objects.all()
    serializer_class = AssessmentSerializer
    filterset_fields = ['taxpayer', 'fiscal_year', 'status']

    @action(detail=True, methods=['post'], url_path='issue')
    def issue(self, request, pk=None):
        """Issue this draft assessment: raises its demand notice and the taxpayer's liability (idempotent)."""
        try:
            notice = lifecycle.issue_assessment(self.get_object())
        except lifecycle.LifecycleError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DemandNoticeSerializer(notice).data)


class BillingRunViewSet(viewsets.ModelViewSet):
    module_key = 'revenue_admin'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = BillingRun.objects.all()
    serializer_class = BillingRunSerializer

    @action(detail=True, methods=['post'], url_path='process')
    def process(self, request, pk=None):
        """Issue every draft assessment of this run's revenue head and fiscal year. A run can be processed once."""
        try:
            run = lifecycle.process_billing_run(self.get_object())
        except lifecycle.LifecycleError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BillingRunSerializer(run).data)


class DemandNoticeViewSet(viewsets.ModelViewSet):
    module_key = 'revenue_admin'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = DemandNotice.objects.all()
    serializer_class = DemandNoticeSerializer
    filterset_fields = ['taxpayer', 'status']

    @action(detail=False, methods=['post'], url_path='update-ageing')
    def update_ageing(self, request):
        """Mark unpaid notices past their due date overdue and refresh the age of unsettled arrears."""
        summary = lifecycle.update_ageing()
        return Response({'notices_marked_overdue': summary.notices_marked_overdue, 'arrears_aged': summary.arrears_aged})


class ArrearsLedgerViewSet(viewsets.ModelViewSet):
    module_key = 'revenue_admin'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = ArrearsLedger.objects.all()
    serializer_class = ArrearsLedgerSerializer


class EnforcementCaseViewSet(viewsets.ModelViewSet):
    module_key = 'revenue_admin'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = EnforcementCase.objects.all()
    serializer_class = EnforcementCaseSerializer
    filterset_fields = ['taxpayer', 'status']


class TaxClearanceCertificateViewSet(viewsets.ModelViewSet):
    module_key = 'revenue_admin'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TaxClearanceCertificate.objects.all()
    serializer_class = TaxClearanceCertificateSerializer
    filterset_fields = ['taxpayer', 'status']

    @action(detail=False, methods=['post'], url_path='issue')
    def issue(self, request):
        """Issue a certificate for a taxpayer and fiscal year, but only if they owe nothing that is due (else 409)."""
        taxpayer = Taxpayer.objects.filter(pk=request.data.get('taxpayer')).first()
        try:
            fiscal_year = int(request.data.get('fiscal_year'))
        except (TypeError, ValueError):
            fiscal_year = None
        if taxpayer is None or fiscal_year is None:
            return Response({'error': 'taxpayer and fiscal_year are required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            certificate = lifecycle.issue_clearance_certificate(taxpayer, fiscal_year=fiscal_year)
        except lifecycle.ClearanceRefused as exc:
            return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(TaxClearanceCertificateSerializer(certificate).data, status=status.HTTP_201_CREATED)


class CollectionApplicationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """How each posted revenue collection was applied. Read-only: only the ledger event writes these rows."""
    module_key = 'revenue_admin'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = CollectionApplication.objects.all()
    serializer_class = CollectionApplicationSerializer
    filterset_fields = ['taxpayer', 'collection_receipt']
