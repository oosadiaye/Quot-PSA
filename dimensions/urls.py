from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DimensionTagViewSet, DimensionTypeViewSet, DimensionValueViewSet

router = DefaultRouter()
router.register(r'types', DimensionTypeViewSet, basename='dimension-type')
router.register(r'values', DimensionValueViewSet, basename='dimension-value')
router.register(r'tags', DimensionTagViewSet, basename='dimension-tag')

urlpatterns = [path('', include(router.urls))]
