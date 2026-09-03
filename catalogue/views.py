"""
catalogue viewsets — module_key = 'catalogue'.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import SupplierCatalogue, CatalogueItem, PriceHistory
from .serializers import (
    SupplierCatalogueSerializer,
    CatalogueItemSerializer,
    PriceHistorySerializer,
)


class SupplierCatalogueViewSet(viewsets.ModelViewSet):
    module_key = 'catalogue'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = SupplierCatalogue.objects.all()
    serializer_class = SupplierCatalogueSerializer
    filterset_fields = ['supplier', 'status']


class CatalogueItemViewSet(viewsets.ModelViewSet):
    module_key = 'catalogue'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = CatalogueItem.objects.all()
    serializer_class = CatalogueItemSerializer
    filterset_fields = ['catalogue', 'item', 'is_active']


class PriceHistoryViewSet(viewsets.ModelViewSet):
    module_key = 'catalogue'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = PriceHistory.objects.all()
    serializer_class = PriceHistorySerializer
