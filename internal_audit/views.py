"""
internal_audit viewsets — module_key = 'internal_audit'.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import (
    AuditUniverse,
    AuditPlan,
    AuditEngagement,
    WorkingPaper,
    AuditFinding,
    FollowUp,
    ContinuousAuditRule,
)
from .serializers import (
    AuditUniverseSerializer,
    AuditPlanSerializer,
    AuditEngagementSerializer,
    WorkingPaperSerializer,
    AuditFindingSerializer,
    FollowUpSerializer,
    ContinuousAuditRuleSerializer,
)


class AuditUniverseViewSet(viewsets.ModelViewSet):
    module_key = 'internal_audit'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = AuditUniverse.objects.all()
    serializer_class = AuditUniverseSerializer


class AuditPlanViewSet(viewsets.ModelViewSet):
    module_key = 'internal_audit'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = AuditPlan.objects.all()
    serializer_class = AuditPlanSerializer


class AuditEngagementViewSet(viewsets.ModelViewSet):
    module_key = 'internal_audit'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = AuditEngagement.objects.all()
    serializer_class = AuditEngagementSerializer
    filterset_fields = ['plan', 'status']


class WorkingPaperViewSet(viewsets.ModelViewSet):
    module_key = 'internal_audit'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = WorkingPaper.objects.all()
    serializer_class = WorkingPaperSerializer


class AuditFindingViewSet(viewsets.ModelViewSet):
    module_key = 'internal_audit'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = AuditFinding.objects.all()
    serializer_class = AuditFindingSerializer
    filterset_fields = ['engagement', 'rating', 'status']


class FollowUpViewSet(viewsets.ModelViewSet):
    module_key = 'internal_audit'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = FollowUp.objects.all()
    serializer_class = FollowUpSerializer


class ContinuousAuditRuleViewSet(viewsets.ModelViewSet):
    module_key = 'internal_audit'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = ContinuousAuditRule.objects.all()
    serializer_class = ContinuousAuditRuleSerializer