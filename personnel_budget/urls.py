from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EstablishmentPostViewSet,
    EstablishmentVarianceViewSet,
    PersonnelCostForecastViewSet,
    PayrollBudgetBindingViewSet,
)

router = DefaultRouter()
router.register(r'establishment-posts', EstablishmentPostViewSet, basename='personnel-post')
router.register(r'variances', EstablishmentVarianceViewSet, basename='personnel-variance')
router.register(r'forecasts', PersonnelCostForecastViewSet, basename='personnel-forecast')
router.register(r'payroll-bindings', PayrollBudgetBindingViewSet, basename='payroll-binding')

urlpatterns = [
    path('', include(router.urls)),
]
