"""
budget_prep viewsets — module_key = 'budget_prep'.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import (
    CallCircular,
    MTEFProjection,
    MDACeiling,
    BudgetSubmission,
    SubmissionLine,
    ReviewComment,
)
from .serializers import (
    CallCircularSerializer,
    MTEFProjectionSerializer,
    MDACeilingSerializer,
    BudgetSubmissionSerializer,
    SubmissionLineSerializer,
    ReviewCommentSerializer,
)


class CallCircularViewSet(viewsets.ModelViewSet):
    module_key = 'budget_prep'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = CallCircular.objects.all()
    serializer_class = CallCircularSerializer


class MTEFProjectionViewSet(viewsets.ModelViewSet):
    module_key = 'budget_prep'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = MTEFProjection.objects.all()
    serializer_class = MTEFProjectionSerializer


class MDACeilingViewSet(viewsets.ModelViewSet):
    module_key = 'budget_prep'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = MDACeiling.objects.all()
    serializer_class = MDACeilingSerializer
    filterset_fields = ['fiscal_year', 'mda_name']


class BudgetSubmissionViewSet(viewsets.ModelViewSet):
    module_key = 'budget_prep'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = BudgetSubmission.objects.all()
    serializer_class = BudgetSubmissionSerializer
    filterset_fields = ['fiscal_year', 'mda_name', 'stage']


class SubmissionLineViewSet(viewsets.ModelViewSet):
    module_key = 'budget_prep'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = SubmissionLine.objects.all()
    serializer_class = SubmissionLineSerializer


class ReviewCommentViewSet(viewsets.ModelViewSet):
    module_key = 'budget_prep'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = ReviewComment.objects.all()
    serializer_class = ReviewCommentSerializer
