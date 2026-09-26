"""
integrations viewsets — module_key = 'integrations'.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import IntegrationEndpoint, IntegrationRun, IntegrationMessage
from .serializers import (
    IntegrationEndpointSerializer,
    IntegrationRunSerializer,
    IntegrationMessageSerializer,
)


class IntegrationEndpointViewSet(viewsets.ModelViewSet):
    module_key = 'integrations'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = IntegrationEndpoint.objects.all()
    serializer_class = IntegrationEndpointSerializer
    filterset_fields = ['connector_type', 'environment', 'is_enabled']


class IntegrationRunViewSet(viewsets.ModelViewSet):
    module_key = 'integrations'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = IntegrationRun.objects.all()
    serializer_class = IntegrationRunSerializer
    filterset_fields = ['endpoint', 'status']


class IntegrationMessageViewSet(viewsets.ModelViewSet):
    module_key = 'integrations'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = IntegrationMessage.objects.all()
    serializer_class = IntegrationMessageSerializer
    filterset_fields = ['run', 'status', 'direction', 'source_model']
