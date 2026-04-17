from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VendorCategoryViewSet, VendorViewSet, PurchaseRequestViewSet,
    PurchaseOrderViewSet, GoodsReceivedNoteViewSet, InvoiceMatchingViewSet,
    VendorCreditNoteViewSet, VendorDebitNoteViewSet, PurchaseReturnViewSet,
    DownPaymentRequestViewSet,
    # BPP Due Process (Phase 5)
    ProcurementThresholdViewSet, CertificateOfNoObjectionViewSet,
    ProcurementBudgetLinkViewSet, ThresholdCheckView,
)

router = DefaultRouter()
router.register(r'vendor-categories', VendorCategoryViewSet)
router.register(r'vendors', VendorViewSet)
router.register(r'requests', PurchaseRequestViewSet)
router.register(r'orders', PurchaseOrderViewSet)
router.register(r'grns', GoodsReceivedNoteViewSet)
router.register(r'invoice-matching', InvoiceMatchingViewSet)
router.register(r'credit-notes', VendorCreditNoteViewSet)
router.register(r'debit-notes', VendorDebitNoteViewSet)
router.register(r'purchase-returns', PurchaseReturnViewSet)
router.register(r'down-payment-requests', DownPaymentRequestViewSet, basename='down-payment-request')

# BPP Due Process (Quot PSE Phase 5)
router.register(r'thresholds', ProcurementThresholdViewSet, basename='procurement-threshold')
router.register(r'no-objection', CertificateOfNoObjectionViewSet, basename='no-objection')
router.register(r'budget-links', ProcurementBudgetLinkViewSet, basename='budget-link')

urlpatterns = [
    path('', include(router.urls)),
    path('threshold-check/', ThresholdCheckView.as_view(), name='threshold-check'),
]
