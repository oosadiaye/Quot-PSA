from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SupplierCatalogueViewSet,
    CatalogueItemViewSet,
    PriceHistoryViewSet,
)

router = DefaultRouter()
router.register(r'supplier-catalogues', SupplierCatalogueViewSet, basename='supplier-catalogue')
router.register(r'items', CatalogueItemViewSet, basename='catalogue-item')
router.register(r'price-history', PriceHistoryViewSet, basename='price-history')

urlpatterns = [
    path('', include(router.urls)),
]
