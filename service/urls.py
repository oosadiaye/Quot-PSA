from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ServiceAssetViewSet, TechnicianViewSet, ServiceTicketViewSet, MaintenanceScheduleViewSet, WorkOrderViewSet, WorkOrderMaterialViewSet, CitizenRequestViewSet, ServiceMetricViewSet

router = DefaultRouter()
router.register(r'assets', ServiceAssetViewSet)
router.register(r'technicians', TechnicianViewSet)
router.register(r'tickets', ServiceTicketViewSet)
router.register(r'schedules', MaintenanceScheduleViewSet)
router.register(r'work-orders', WorkOrderViewSet)
router.register(r'work-order-materials', WorkOrderMaterialViewSet)
router.register(r'citizen-requests', CitizenRequestViewSet)
router.register(r'metrics', ServiceMetricViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
