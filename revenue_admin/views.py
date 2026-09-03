"""
revenue_admin viewsets — module_key = 'revenue_admin'.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import (
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


class BillingRunViewSet(viewsets.ModelViewSet):
    module_key = 'revenue_admin'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = BillingRun.objects.all()
    serializer_class = BillingRunSerializer


class DemandNoticeViewSet(viewsets.ModelViewSet):
    module_key = 'revenue_admin'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = DemandNotice.objects.all()
    serializer_class = DemandNoticeSerializer
    filterset_fields = ['taxpayer', 'status']


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
