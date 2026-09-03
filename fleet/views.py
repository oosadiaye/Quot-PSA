"""
fleet viewsets — module_key = 'fleet'.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import Vehicle, VehicleAssignment, FuelLog, MileageLog, MaintenanceRecord
from .serializers import (
    VehicleSerializer,
    VehicleAssignmentSerializer,
    FuelLogSerializer,
    MileageLogSerializer,
    MaintenanceRecordSerializer,
)


class VehicleViewSet(viewsets.ModelViewSet):
    module_key = 'fleet'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    filterset_fields = ['status', 'make', 'model']


class VehicleAssignmentViewSet(viewsets.ModelViewSet):
    module_key = 'fleet'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = VehicleAssignment.objects.all()
    serializer_class = VehicleAssignmentSerializer


class FuelLogViewSet(viewsets.ModelViewSet):
    module_key = 'fleet'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = FuelLog.objects.all()
    serializer_class = FuelLogSerializer


class MileageLogViewSet(viewsets.ModelViewSet):
    module_key = 'fleet'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = MileageLog.objects.all()
    serializer_class = MileageLogSerializer


class MaintenanceRecordViewSet(viewsets.ModelViewSet):
    module_key = 'fleet'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = MaintenanceRecord.objects.all()
    serializer_class = MaintenanceRecordSerializer
