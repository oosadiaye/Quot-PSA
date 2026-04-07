from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    WorkCenterViewSet, BillOfMaterialsViewSet, BOMLineViewSet,
    ProductionOrderViewSet, MaterialIssueViewSet, MaterialReceiptViewSet,
    JobCardViewSet, RoutingViewSet
)

router = DefaultRouter()
router.register(r'work-centers', WorkCenterViewSet)
router.register(r'bills-of-materials', BillOfMaterialsViewSet)
router.register(r'bom-lines', BOMLineViewSet)
router.register(r'production-orders', ProductionOrderViewSet)
router.register(r'material-issues', MaterialIssueViewSet)
router.register(r'material-receipts', MaterialReceiptViewSet)
router.register(r'job-cards', JobCardViewSet)
router.register(r'routings', RoutingViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
