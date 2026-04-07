from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UnifiedBudgetViewSet, UnifiedBudgetEncumbranceViewSet, UnifiedBudgetVarianceViewSet, UnifiedBudgetAmendmentViewSet

router = DefaultRouter()
router.register(r'', UnifiedBudgetViewSet, basename='unified-budget')
router.register(r'encumbrances', UnifiedBudgetEncumbranceViewSet, basename='budget-encumbrance')
router.register(r'variances', UnifiedBudgetVarianceViewSet, basename='budget-variance')
router.register(r'amendments', UnifiedBudgetAmendmentViewSet, basename='budget-amendment')

urlpatterns = [
    path('', include(router.urls)),
]
