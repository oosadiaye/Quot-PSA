from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DebtInstrumentViewSet,
    AmortisationScheduleViewSet,
    AmortisationCouponViewSet,
    AmortisationLedgerViewSet,
    DebtServiceCostViewSet,
    DebtAversionStatementViewSet,
)

router = DefaultRouter()
router.register(r'instruments', DebtInstrumentViewSet, basename='debt-instrument')
router.register(r'schedules', AmortisationScheduleViewSet, basename='amortisation-schedule')
router.register(r'coupons', AmortisationCouponViewSet, basename='amortisation-coupon')
router.register(r'ledger', AmortisationLedgerViewSet, basename='amortisation-ledger')
router.register(r'service-costs', DebtServiceCostViewSet, basename='debt-service-cost')
router.register(r'statements', DebtAversionStatementViewSet, basename='debt-aversion-statement')

urlpatterns = [
    path('', include(router.urls)),
]
