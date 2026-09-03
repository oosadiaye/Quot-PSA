"""
transparency viewsets — module_key = 'transparency'.

The gated views here are the *governance* side (policy + publish actions).
The public, unauthenticated read-only surface is NOT routed through these
viewsets — per FUTURE_MODULES §5.5 "off" for the public portal is enforced at
the routing layer via a separate URL namespace, which is intentionally not
registered here.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import PublicationPolicy, Publication, RedactionRule, DataExport
from .serializers import (
    PublicationPolicySerializer,
    PublicationSerializer,
    RedactionRuleSerializer,
    DataExportSerializer,
)


class PublicationPolicyViewSet(viewsets.ModelViewSet):
    module_key = 'transparency'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = PublicationPolicy.objects.all()
    serializer_class = PublicationPolicySerializer
    filterset_fields = ['dataset', 'status']


class PublicationViewSet(viewsets.ModelViewSet):
    module_key = 'transparency'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = Publication.objects.all()
    serializer_class = PublicationSerializer
    filterset_fields = ['dataset_key', 'status', 'policy']


class RedactionRuleViewSet(viewsets.ModelViewSet):
    module_key = 'transparency'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = RedactionRule.objects.all()
    serializer_class = RedactionRuleSerializer
    filterset_fields = ['field_name', 'is_active']


class DataExportViewSet(viewsets.ModelViewSet):
    module_key = 'transparency'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = DataExport.objects.all()
    serializer_class = DataExportSerializer
