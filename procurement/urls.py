from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import VendorCategoryViewSet, VendorViewSet, PurchaseRequestViewSet, PurchaseOrderViewSet, GoodsReceivedNoteViewSet, InvoiceMatchingViewSet, VendorCreditNoteViewSet, VendorDebitNoteViewSet, PurchaseReturnViewSet, DownPaymentRequestViewSet


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

urlpatterns = [
    path('', include(router.urls)),
]
