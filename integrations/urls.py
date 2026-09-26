from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    IntegrationEndpointViewSet,
    IntegrationRunViewSet,
    IntegrationMessageViewSet,
)

router = DefaultRouter()
router.register(r'endpoints', IntegrationEndpointViewSet, basename='integration-endpoint')
router.register(r'runs', IntegrationRunViewSet, basename='integration-run')
router.register(r'messages', IntegrationMessageViewSet, basename='integration-message')

urlpatterns = [
    path('', include(router.urls)),
]
