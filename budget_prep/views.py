"""
budget_prep viewsets — module_key = 'budget_prep'.
"""
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsApprover, ModuleEnabled, RBACPermission
from .models import (
    CallCircular,
    MTEFProjection,
    MDACeiling,
    BudgetSubmission,
    SubmissionLine,
    ReviewComment,
)
from .services.incorporation import IncorporationError, incorporate_submission
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
    # Dimensions a line may leave blank; the caller can supply a default for each at hand-off.
    HANDOFF_DEFAULTS = ('fund', 'programme', 'functional', 'administrative', 'economic')

    def get_permissions(self):
        if self.action == 'incorporate':
            return [IsAuthenticated(), ModuleEnabled(), RBACPermission(), IsApprover('post')]
        return super().get_permissions()

    @action(detail=True, methods=['post'], url_path='incorporate')
    def incorporate(self, request, pk=None):
        """Hand this incorporated submission to Budget & Appropriation as DRAFT appropriations.

        One-way and optional: the appropriations stay when this module is switched off. Body may carry
        ``default_fund`` / ``default_programme`` / ... for lines that left that dimension blank.
        """
        submission = self.get_object()
        defaults = {name: request.data.get(f'default_{name}') for name in self.HANDOFF_DEFAULTS
                    if request.data.get(f'default_{name}')}
        try:
            with transaction.atomic():
                result = incorporate_submission(submission, defaults=defaults)
        except IncorporationError as exc:
            return Response({'error': str(exc), 'lines': exc.lines}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'created': result.created, 'updated': result.updated, 'removed': result.removed,
            'appropriation_ids': result.appropriation_ids, 'fiscal_year': submission.fiscal_year,
        })


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
