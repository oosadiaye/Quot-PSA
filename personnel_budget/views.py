"""
personnel_budget viewsets — all declare ``module_key = 'personnel_budget'`` so
core.permissions.ModuleEnabled refuses requests when the module is toggled off.
Composed with RBACPermission for per-role authorisation.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import (
    EstablishmentPost,
    EstablishmentVariance,
    PersonnelCostForecast,
    PayrollBudgetBinding,
)
from .serializers import (
    EstablishmentPostSerializer,
    EstablishmentVarianceSerializer,
    PersonnelCostForecastSerializer,
    PayrollBudgetBindingSerializer,
)


class EstablishmentPostViewSet(viewsets.ModelViewSet):
    module_key = 'personnel_budget'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = EstablishmentPost.objects.all()
    serializer_class = EstablishmentPostSerializer
    filterset_fields = ['status', 'grade', 'mda_name', 'mda_admin']


class EstablishmentVarianceViewSet(viewsets.ModelViewSet):
    module_key = 'personnel_budget'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = EstablishmentVariance.objects.all()
    serializer_class = EstablishmentVarianceSerializer
    filterset_fields = ['post', 'is_breach']


class PersonnelCostForecastViewSet(viewsets.ModelViewSet):
    module_key = 'personnel_budget'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = PersonnelCostForecast.objects.all()
    serializer_class = PersonnelCostForecastSerializer
    filterset_fields = ['fiscal_year', 'mda_name', 'appropriation_line']


class PayrollBudgetBindingViewSet(viewsets.ModelViewSet):
    module_key = 'personnel_budget'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = PayrollBudgetBinding.objects.all()
    serializer_class = PayrollBudgetBindingSerializer
    filterset_fields = ['payroll_run', 'appropriation_line']
