from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DeclarationCycleViewSet,
    AssetDeclarationViewSet,
    DeclarationItemViewSet,
    DisclosureAccessLogViewSet,
)

router = DefaultRouter()
router.register(r'cycles', DeclarationCycleViewSet, basename='declaration-cycle')
router.register(r'declarations', AssetDeclarationViewSet, basename='asset-declaration')
router.register(r'items', DeclarationItemViewSet, basename='declaration-item')
router.register(r'access-log', DisclosureAccessLogViewSet, basename='disclosure-access-log')

urlpatterns = [
    path('', include(router.urls)),
]
