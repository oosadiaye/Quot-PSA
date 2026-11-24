"""
results viewsets — module_key = 'results'.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import (
    ResultsFramework,
    Outcome,
    Output,
    Indicator,
    IndicatorTarget,
    IndicatorActual,
    PerformanceReport,
)
from .serializers import (
    ResultsFrameworkSerializer,
    OutcomeSerializer,
    OutputSerializer,
    IndicatorSerializer,
    IndicatorTargetSerializer,
    IndicatorActualSerializer,
    PerformanceReportSerializer,
)


class ResultsFrameworkViewSet(viewsets.ModelViewSet):
    module_key = 'results'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = ResultsFramework.objects.all()
    serializer_class = ResultsFrameworkSerializer


class OutcomeViewSet(viewsets.ModelViewSet):
    module_key = 'results'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = Outcome.objects.all()
    serializer_class = OutcomeSerializer


class OutputViewSet(viewsets.ModelViewSet):
    module_key = 'results'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = Output.objects.all()
    serializer_class = OutputSerializer


class IndicatorViewSet(viewsets.ModelViewSet):
    module_key = 'results'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = Indicator.objects.all()
    serializer_class = IndicatorSerializer


class IndicatorTargetViewSet(viewsets.ModelViewSet):
    module_key = 'results'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = IndicatorTarget.objects.all()
    serializer_class = IndicatorTargetSerializer


class IndicatorActualViewSet(viewsets.ModelViewSet):
    module_key = 'results'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = IndicatorActual.objects.all()
    serializer_class = IndicatorActualSerializer


class PerformanceReportViewSet(viewsets.ModelViewSet):
    module_key = 'results'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = PerformanceReport.objects.all()
    serializer_class = PerformanceReportSerializer
    filterset_fields = ['scope', 'fiscal_year']
