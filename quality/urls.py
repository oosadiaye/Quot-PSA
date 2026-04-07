from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    QualityInspectionViewSet, InspectionLineViewSet,
    NonConformanceViewSet, CustomerComplaintViewSet,
    QualityChecklistViewSet, QualityChecklistLineViewSet,
    CalibrationRecordViewSet, SupplierQualityViewSet,
    QAConfigurationViewSet
)

router = DefaultRouter()
router.register(r'inspections', QualityInspectionViewSet)
router.register(r'inspection-lines', InspectionLineViewSet)
router.register(r'non-conformances', NonConformanceViewSet)
router.register(r'complaints', CustomerComplaintViewSet)
router.register(r'checklists', QualityChecklistViewSet)
router.register(r'checklist-lines', QualityChecklistLineViewSet)
router.register(r'calibrations', CalibrationRecordViewSet)
router.register(r'supplier-quality', SupplierQualityViewSet)
router.register(r'configurations', QAConfigurationViewSet, basename='qa-configurations')

urlpatterns = [
    path('', include(router.urls)),
]
