from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UnifiedBudgetViewSet, UnifiedBudgetEncumbranceViewSet,
    UnifiedBudgetVarianceViewSet, UnifiedBudgetAmendmentViewSet,
    AppropriationViewSet, WarrantViewSet, BudgetExecutionView,
    CommitmentReportView, RevenueBudgetViewSet,
)

router = DefaultRouter()

# Legacy unified budget (explicit prefix to avoid shadowing)
router.register(r'unified', UnifiedBudgetViewSet, basename='unified-budget')
router.register(r'encumbrances', UnifiedBudgetEncumbranceViewSet, basename='budget-encumbrance')
router.register(r'variances', UnifiedBudgetVarianceViewSet, basename='budget-variance')
router.register(r'amendments', UnifiedBudgetAmendmentViewSet, basename='budget-amendment')

# Government Appropriation & Warrant (Quot PSE)
router.register(r'appropriations', AppropriationViewSet, basename='appropriation')
router.register(r'warrants', WarrantViewSet, basename='warrant')
router.register(r'revenue-budgets', RevenueBudgetViewSet, basename='revenue-budget')

urlpatterns = [
    path('', include(router.urls)),
    path('execution-report/', BudgetExecutionView.as_view(), name='budget-execution'),
    path('validate/', BudgetExecutionView.as_view(), name='budget-validate'),
    path('commitment-report/', CommitmentReportView.as_view(), name='commitment-report'),
]
