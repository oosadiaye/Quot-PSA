"""
budget_prep viewsets — module_key = 'budget_prep'.
"""
from django.db import transaction
from datetime import date, timedelta

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsApprover, ModuleEnabled, RBACPermission
from .models import (
    BudgetMilestone,
    CallCircular,
    MTEFProjection,
    MDACeiling,
    BudgetSubmission,
    SubmissionLine,
    ReviewComment,
)
from .services.adoption import BASES, AdoptionError, adopt_actuals, baseline_rows
from .services.calendar import CalendarError, DUE_SOON_DAYS, seed_standard_calendar
from .services.ceilings import SubmissionError, check_ceiling, refresh_totals, submit_submission
from .services.incorporation import IncorporationError, incorporate_submission
from .serializers import (
    BudgetMilestoneSerializer,
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

    @action(detail=True, methods=['get'], url_path='ceiling-check')
    def ceiling_check(self, request, pk=None):
        """Proposed totals per line type against this MDA's ceiling for the year. Writes nothing."""
        return Response(check_ceiling(self.get_object()).as_dict())

    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        """Send a draft (or sent-back) submission to the Budget Office, enforcing the MDA ceiling.

        Over a ceiling it is refused unless ``override_reason`` is given; the reason is kept as a flagged review comment.
        """
        submission = self.get_object()
        user = request.user
        try:
            check = submit_submission(
                submission, override_reason=str(request.data.get('override_reason') or ''),
                actor_name=(user.get_full_name() or user.get_username()) if user and user.is_authenticated else '')
        except SubmissionError as exc:
            body = {'error': str(exc)}
            if exc.check is not None:
                body['check'] = exc.check.as_dict()
            return Response(body, status=status.HTTP_400_BAD_REQUEST)
        return Response({'stage': submission.stage, 'submitted_at': submission.submitted_at, 'check': check.as_dict()})

    @action(detail=True, methods=['get'], url_path='adoption-preview')
    def adoption_preview(self, request, pk=None):
        """The baseline each basis would give for this MDA, without writing anything."""
        submission = self.get_object()
        basis = request.query_params.get('basis', 'outturn')
        try:
            rows, source_year = baseline_rows(submission, basis)
        except AdoptionError as exc:
            return Response({'error': str(exc), 'bases': list(BASES)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'basis': basis, 'source_year': source_year,
            'rows': [{'economic_code': r['code'], 'baseline': str(r['amount'])} for r in rows],
            'total': str(sum(r['amount'] for r in rows)),
        })

    @action(detail=True, methods=['post'], url_path='adopt-actuals')
    def adopt_actuals(self, request, pk=None):
        """Seed this draft submission from prior-year outturn, approved appropriation or run rate, plus a growth adjustment.

        Body: ``basis`` (outturn | appropriation | run_rate), ``growth_pct``, ``class_adjustments`` ({account-code prefix: pct}).
        Re-running replaces the previously adopted lines and leaves hand-entered lines alone.
        """
        submission = self.get_object()
        try:
            result = adopt_actuals(
                submission, basis=request.data.get('basis', 'outturn'), growth_pct=request.data.get('growth_pct') or 0,
                class_adjustments=request.data.get('class_adjustments') or {})
        except AdoptionError as exc:
            return Response({'error': str(exc), 'bases': list(BASES)}, status=status.HTTP_400_BAD_REQUEST)
        except ArithmeticError:
            return Response({'error': 'growth_pct and class_adjustments must be numbers.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'basis': result.basis, 'source_year': result.source_year, 'created': result.created,
            'replaced': result.replaced, 'total_proposed': str(result.total_proposed), 'skipped': result.skipped,
        })

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

    # A submission's totals are the sum of its lines, so they are recomputed whenever a line changes.
    def perform_create(self, serializer):
        line = serializer.save()
        refresh_totals(line.submission)

    def perform_update(self, serializer):
        line = serializer.save()
        refresh_totals(line.submission)

    def perform_destroy(self, instance):
        submission = instance.submission
        instance.delete()
        refresh_totals(submission)


class ReviewCommentViewSet(viewsets.ModelViewSet):
    module_key = 'budget_prep'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = ReviewComment.objects.all()
    serializer_class = ReviewCommentSerializer


class BudgetMilestoneViewSet(viewsets.ModelViewSet):
    module_key = 'budget_prep'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = BudgetMilestone.objects.all()
    serializer_class = BudgetMilestoneSerializer
    filterset_fields = ['fiscal_year']

    @action(detail=False, methods=['post'], url_path='seed-standard')
    def seed_standard(self, request):
        """Create the standard budget-cycle steps for a year, counted from the call circular's issue date.

        Body: ``fiscal_year`` (required) and optionally ``anchor_date`` (YYYY-MM-DD) when no circular exists yet.
        Safe to repeat: existing steps are never moved or duplicated.
        """
        try:
            fiscal_year = int(request.data.get('fiscal_year'))
        except (TypeError, ValueError):
            return Response({'error': 'fiscal_year is required and must be a year.'}, status=status.HTTP_400_BAD_REQUEST)
        anchor = None
        if request.data.get('anchor_date'):
            try:
                anchor = date.fromisoformat(str(request.data['anchor_date']))
            except ValueError:
                return Response({'error': 'anchor_date must be a date like 2026-09-01.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = seed_standard_calendar(fiscal_year, anchor=anchor)
        except CalendarError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'created': result.created, 'existing': result.existing, 'anchor': result.anchor.isoformat()})

    @action(detail=False, methods=['get'], url_path='upcoming')
    def upcoming(self, request):
        """Open steps that are overdue or due within ``days`` (default the due-soon window), soonest first."""
        try:
            days = int(request.query_params.get('days', DUE_SOON_DAYS))
        except ValueError:
            return Response({'error': 'days must be a whole number.'}, status=status.HTTP_400_BAD_REQUEST)
        horizon = timezone.localdate() + timedelta(days=days)
        rows = self.get_queryset().filter(completed_on__isnull=True, due_date__lte=horizon).order_by('due_date', 'sequence')
        return Response(self.get_serializer(rows, many=True).data)

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        """Mark a step done today (or on ``completed_on``)."""
        milestone = self.get_object()
        milestone.completed_on = request.data.get('completed_on') or timezone.localdate()
        milestone.save(update_fields=['completed_on', 'updated_at'])
        milestone.refresh_from_db()
        return Response(self.get_serializer(milestone).data)
