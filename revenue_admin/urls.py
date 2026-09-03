from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TaxpayerViewSet,
    TaxAccountViewSet,
    AssessmentViewSet,
    BillingRunViewSet,
    DemandNoticeViewSet,
    ArrearsLedgerViewSet,
    EnforcementCaseViewSet,
    TaxClearanceCertificateViewSet,
)

router = DefaultRouter()
router.register(r'taxpayers', TaxpayerViewSet, basename='taxpayer')
router.register(r'tax-accounts', TaxAccountViewSet, basename='tax-account')
router.register(r'assessments', AssessmentViewSet, basename='assessment')
router.register(r'billing-runs', BillingRunViewSet, basename='billing-run')
router.register(r'demand-notices', DemandNoticeViewSet, basename='demand-notice')
router.register(r'arrears', ArrearsLedgerViewSet, basename='arrears-ledger')
router.register(r'enforcement-cases', EnforcementCaseViewSet, basename='enforcement-case')
router.register(r'clearance-certificates', TaxClearanceCertificateViewSet, basename='clearance-certificate')

urlpatterns = [
    path('', include(router.urls)),
]
