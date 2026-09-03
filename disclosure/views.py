"""
disclosure viewsets — module_key = 'disclosure'.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import DeclarationCycle, AssetDeclaration, DeclarationItem, DisclosureAccessLog
from .serializers import (
    DeclarationCycleSerializer,
    AssetDeclarationSerializer,
    DeclarationItemSerializer,
    DisclosureAccessLogSerializer,
)


class DeclarationCycleViewSet(viewsets.ModelViewSet):
    module_key = 'disclosure'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = DeclarationCycle.objects.all()
    serializer_class = DeclarationCycleSerializer


class AssetDeclarationViewSet(viewsets.ModelViewSet):
    module_key = 'disclosure'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = AssetDeclaration.objects.all()
    serializer_class = AssetDeclarationSerializer
    filterset_fields = ['cycle', 'employee', 'status']


class DeclarationItemViewSet(viewsets.ModelViewSet):
    module_key = 'disclosure'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = DeclarationItem.objects.all()
    serializer_class = DeclarationItemSerializer


class DisclosureAccessLogViewSet(viewsets.ModelViewSet):
    module_key = 'disclosure'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = DisclosureAccessLog.objects.all()
    serializer_class = DisclosureAccessLogSerializer
    filterset_fields = ['declaration']
