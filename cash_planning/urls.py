from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CashPlanViewSet,
    CashForecastLineViewSet,
    CashPositionViewSet,
    WarrantRecommendationViewSet,
    CashPlanVarianceViewSet,
)

router = DefaultRouter()
router.register(r'plans', CashPlanViewSet, basename='cash-plan')
router.register(r'lines', CashForecastLineViewSet, basename='cash-forecast-line')
router.register(r'positions', CashPositionViewSet, basename='cash-position')
router.register(r'recommendations', WarrantRecommendationViewSet, basename='warrant-recommendation')
router.register(r'variances', CashPlanVarianceViewSet, basename='cash-plan-variance')

urlpatterns = [
    path('', include(router.urls)),
]
