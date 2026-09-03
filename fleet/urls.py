from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VehicleViewSet,
    VehicleAssignmentViewSet,
    FuelLogViewSet,
    MileageLogViewSet,
    MaintenanceRecordViewSet,
)

router = DefaultRouter()
router.register(r'vehicles', VehicleViewSet, basename='vehicle')
router.register(r'assignments', VehicleAssignmentViewSet, basename='vehicle-assignment')
router.register(r'fuel-logs', FuelLogViewSet, basename='fuel-log')
router.register(r'mileage-logs', MileageLogViewSet, basename='mileage-log')
router.register(r'maintenance', MaintenanceRecordViewSet, basename='maintenance-record')

urlpatterns = [
    path('', include(router.urls)),
]
