from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomerCategoryViewSet, CustomerViewSet, LeadViewSet, OpportunityViewSet, QuotationViewSet, SalesOrderViewSet, DeliveryNoteViewSet, SalesReturnViewSet, CreditNoteViewSet, SalesAnalyticsViewSet

router = DefaultRouter()
router.register(r'customer-categories', CustomerCategoryViewSet)
router.register(r'customers', CustomerViewSet)
router.register(r'leads', LeadViewSet)
router.register(r'opportunities', OpportunityViewSet)
router.register(r'quotations', QuotationViewSet)
router.register(r'orders', SalesOrderViewSet)
router.register(r'delivery-notes', DeliveryNoteViewSet)
router.register(r'returns', SalesReturnViewSet)
router.register(r'credit-notes', CreditNoteViewSet)
router.register(r'analytics', SalesAnalyticsViewSet, basename='sales-analytics')

urlpatterns = [
    path('', include(router.urls)),
]
