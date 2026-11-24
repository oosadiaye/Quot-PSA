"""
legal viewsets — module_key = 'legal'.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import (
    LegalCase,
    HearingDiary,
    CaseCost,
    RiskRegister,
    LitigationProvisionLink,
)
from .serializers import (
    LegalCaseSerializer,
    HearingDiarySerializer,
    CaseCostSerializer,
    RiskRegisterSerializer,
    LitigationProvisionLinkSerializer,
)


class LegalCaseViewSet(viewsets.ModelViewSet):
    module_key = 'legal'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = LegalCase.objects.all()
    serializer_class = LegalCaseSerializer
    filterset_fields = ['stage', 'court']


class HearingDiaryViewSet(viewsets.ModelViewSet):
    module_key = 'legal'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = HearingDiary.objects.all()
    serializer_class = HearingDiarySerializer


class CaseCostViewSet(viewsets.ModelViewSet):
    module_key = 'legal'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = CaseCost.objects.all()
    serializer_class = CaseCostSerializer


class RiskRegisterViewSet(viewsets.ModelViewSet):
    module_key = 'legal'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = RiskRegister.objects.all()
    serializer_class = RiskRegisterSerializer
    filterset_fields = ['category', 'is_active', 'case']


class LitigationProvisionLinkViewSet(viewsets.ModelViewSet):
    module_key = 'legal'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = LitigationProvisionLink.objects.all()
    serializer_class = LitigationProvisionLinkSerializer
