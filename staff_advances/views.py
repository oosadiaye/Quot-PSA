"""
staff_advances viewsets — module_key = 'staff_advances'.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import (
    StaffAdvance,
    ImprestAccount,
    ImprestRetirement,
    PerDiemTable,
    TravelRequest,
    TravelAdvance,
    TravelRetirement,
)
from .serializers import (
    StaffAdvanceSerializer,
    ImprestAccountSerializer,
    ImprestRetirementSerializer,
    PerDiemTableSerializer,
    TravelRequestSerializer,
    TravelAdvanceSerializer,
    TravelRetirementSerializer,
)


class StaffAdvanceViewSet(viewsets.ModelViewSet):
    module_key = 'staff_advances'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = StaffAdvance.objects.all()
    serializer_class = StaffAdvanceSerializer
    filterset_fields = ['employee', 'status', 'purpose']


class ImprestAccountViewSet(viewsets.ModelViewSet):
    module_key = 'staff_advances'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = ImprestAccount.objects.all()
    serializer_class = ImprestAccountSerializer
    filterset_fields = ['employee', 'status']


class ImprestRetirementViewSet(viewsets.ModelViewSet):
    module_key = 'staff_advances'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = ImprestRetirement.objects.all()
    serializer_class = ImprestRetirementSerializer


class PerDiemTableViewSet(viewsets.ModelViewSet):
    module_key = 'staff_advances'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = PerDiemTable.objects.all()
    serializer_class = PerDiemTableSerializer


class TravelRequestViewSet(viewsets.ModelViewSet):
    module_key = 'staff_advances'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TravelRequest.objects.all()
    serializer_class = TravelRequestSerializer
    filterset_fields = ['employee', 'status']


class TravelAdvanceViewSet(viewsets.ModelViewSet):
    module_key = 'staff_advances'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TravelAdvance.objects.all()
    serializer_class = TravelAdvanceSerializer


class TravelRetirementViewSet(viewsets.ModelViewSet):
    module_key = 'staff_advances'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TravelRetirement.objects.all()
    serializer_class = TravelRetirementSerializer
