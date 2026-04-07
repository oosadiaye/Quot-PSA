from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    WarehouseViewSet, ProductTypeViewSet, ProductCategoryViewSet,
    ItemCategoryViewSet, ItemViewSet,
    ItemStockViewSet, ItemBatchViewSet, StockMovementViewSet,
    StockReconciliationViewSet, ReorderAlertViewSet,
    ItemSerialNumberViewSet, BatchExpiryAlertViewSet,
    InventorySettingsView,
)

router = DefaultRouter()
router.register(r'warehouses', WarehouseViewSet)
router.register(r'product-types', ProductTypeViewSet)
router.register(r'product-categories', ProductCategoryViewSet)
router.register(r'categories', ItemCategoryViewSet)  # Legacy
router.register(r'items', ItemViewSet)
router.register(r'stocks', ItemStockViewSet)
router.register(r'batches', ItemBatchViewSet)
router.register(r'movements', StockMovementViewSet)
router.register(r'reconciliations', StockReconciliationViewSet)
router.register(r'reorder-alerts', ReorderAlertViewSet)
router.register(r'serial-numbers', ItemSerialNumberViewSet)
router.register(r'expiry-alerts', BatchExpiryAlertViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('settings/', InventorySettingsView.as_view(), name='inventory-settings'),
]
