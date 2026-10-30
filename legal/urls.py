from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LegalCaseViewSet,
    HearingDiaryViewSet,
    CaseCostViewSet,
    RiskRegisterViewSet,
    LitigationProvisionLinkViewSet,
)

router = DefaultRouter()
router.register(r'cases', LegalCaseViewSet, basename='legal-case')
router.register(r'hearings', HearingDiaryViewSet, basename='hearing-diary')
router.register(r'costs', CaseCostViewSet, basename='case-cost')
router.register(r'risks', RiskRegisterViewSet, basename='risk-register')
router.register(r'provision-links', LitigationProvisionLinkViewSet, basename='provision-link')

urlpatterns = [
    path('', include(router.urls)),
]
