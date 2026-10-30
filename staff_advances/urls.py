from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    StaffAdvanceViewSet,
    ImprestAccountViewSet,
    ImprestRetirementViewSet,
    PerDiemTableViewSet,
    TravelRequestViewSet,
    TravelAdvanceViewSet,
    TravelRetirementViewSet,
)

router = DefaultRouter()
router.register(r'staff-advances', StaffAdvanceViewSet, basename='staff-advance')
router.register(r'imprest-accounts', ImprestAccountViewSet, basename='imprest-account')
router.register(r'imprest-retirements', ImprestRetirementViewSet, basename='imprest-retirement')
router.register(r'per-diem', PerDiemTableViewSet, basename='per-diem')
router.register(r'travel-requests', TravelRequestViewSet, basename='travel-request')
router.register(r'travel-advances', TravelAdvanceViewSet, basename='travel-advance')
router.register(r'travel-retirements', TravelRetirementViewSet, basename='travel-retirement')

urlpatterns = [
    path('', include(router.urls)),
]
