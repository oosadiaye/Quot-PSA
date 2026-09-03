from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ResultsFrameworkViewSet,
    OutcomeViewSet,
    OutputViewSet,
    IndicatorViewSet,
    IndicatorTargetViewSet,
    IndicatorActualViewSet,
    PerformanceReportViewSet,
)

router = DefaultRouter()
router.register(r'frameworks', ResultsFrameworkViewSet, basename='results-framework')
router.register(r'outcomes', OutcomeViewSet, basename='outcome')
router.register(r'outputs', OutputViewSet, basename='output')
router.register(r'indicators', IndicatorViewSet, basename='indicator')
router.register(r'targets', IndicatorTargetViewSet, basename='indicator-target')
router.register(r'actuals', IndicatorActualViewSet, basename='indicator-actual')
router.register(r'performance-reports', PerformanceReportViewSet, basename='performance-report')

urlpatterns = [
    path('', include(router.urls)),
]
