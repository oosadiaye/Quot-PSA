"""
cash_planning viewsets — module_key = 'cash_planning'.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import (
    CashPlan,
    CashForecastLine,
    CashPosition,
    WarrantRecommendation,
    CashPlanVariance,
)
from .serializers import (
    CashPlanSerializer,
    CashForecastLineSerializer,
    CashPositionSerializer,
    WarrantRecommendationSerializer,
    CashPlanVarianceSerializer,
)


class CashPlanViewSet(viewsets.ModelViewSet):
    module_key = 'cash_planning'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = CashPlan.objects.all()
    serializer_class = CashPlanSerializer


class CashForecastLineViewSet(viewsets.ModelViewSet):
    module_key = 'cash_planning'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = CashForecastLine.objects.all()
    serializer_class = CashForecastLineSerializer


class CashPositionViewSet(viewsets.ModelViewSet):
    module_key = 'cash_planning'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = CashPosition.objects.all()
    serializer_class = CashPositionSerializer


class WarrantRecommendationViewSet(viewsets.ModelViewSet):
    module_key = 'cash_planning'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = WarrantRecommendation.objects.all()
    serializer_class = WarrantRecommendationSerializer


class CashPlanVarianceViewSet(viewsets.ModelViewSet):
    module_key = 'cash_planning'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = CashPlanVariance.objects.all()
    serializer_class = CashPlanVarianceSerializer
