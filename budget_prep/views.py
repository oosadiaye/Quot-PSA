"""
budget_prep viewsets — module_key = 'budget_prep'.
"""
from django.db import transaction
from datetime import date, timedelta

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsApprover, ModuleEnabled, RBACPermission
from .models import (
    BudgetMilestone,
    CallCircular,
    MTEFPolicy,
    MTEFProjection,
    MDACeiling,
    BudgetSubmission,
    SubmissionLine,
    ReviewComment,
)
from .services.adoption import BASES, AdoptionError, adopt_actuals, baseline_rows
from .services import mtef as mtef_service
from .services.calendar import CalendarError, DUE_SOON_DAYS, seed_standard_calendar
from .services.ceilings import SubmissionError, check_ceiling, refresh_totals, submit_submission
from .services.supplementary import supplementary_report
from .services.incorporation import IncorporationError, incorporate_submission
from .serializers import (
    BudgetMilestoneSerializer,
    CallCircularSerializer,
    MTEFPolicySerializer,
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
    filterset_fields = ['fiscal_year', 'status']

    def get_permissions(self):
        # Approving a framework releases the envelope MDA ceilings are drawn from, so it is an approver's act.
        if self.action in ('approve', 'reopen'):
            return [IsAuthenticated(), ModuleEnabled(), RBACPermission(), IsApprover('post')]
        return super().get_permissions()

    def _refuse_if_approved(self, instance):
        if instance.status == 'approved':
            raise ValidationError({'detail': f'The {instance.fiscal_year} MTEF is approved and locked. Reopen it, with a reason, to change it.'})

    def perform_update(self, serializer):
        self._refuse_if_approved(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._refuse_if_approved(instance)
        instance.delete()

    @staticmethod
    def _year(request, source='query_params'):
        try:
            return int(getattr(request, source).get('base_year'))
        except (TypeError, ValueError):
            return None

    @action(detail=False, methods=['get'], url_path='framework')
    def framework(self, request):
        """The three-year framework from a base year: figures, ratios, rule findings, last year's outturn and the ceilings."""
        year = self._year(request)
        if year is None:
            return Response({'error': 'base_year is required and must be a year.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(mtef_service.framework(year))

    @action(detail=False, methods=['post'], url_path='scenario')
    def scenario(self, request):
        """What the framework looks like if the oil price, IGR or costs move. Nothing is saved."""
        year = self._year(request, 'data')
        if year is None:
            return Response({'error': 'base_year is required and must be a year.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            return Response(mtef_service.scenario(
                year, oil_price_change_pct=request.data.get('oil_price_change_pct'),
                igr_change_pct=request.data.get('igr_change_pct'), cost_change_pct=request.data.get('cost_change_pct')))
        except ArithmeticError:
            return Response({'error': 'The shock percentages must be numbers.'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='roll-forward')
    def roll_forward(self, request):
        """Create the two outer years from the budget year; a year that already exists is left alone."""
        year = self._year(request, 'data')
        if year is None:
            return Response({'error': 'base_year is required and must be a year.'}, status=status.HTTP_400_BAD_REQUEST)
        growth = {k: request.data.get(k) for k in ('revenue_growth_pct', 'debt_service_growth_pct', 'personnel_growth_pct',
                                                   'overhead_growth_pct', 'capital_growth_pct')}
        try:
            result = mtef_service.roll_forward(year, growth=growth)
        except ArithmeticError:
            return Response({'error': 'The growth rates must be numbers.'}, status=status.HTTP_400_BAD_REQUEST)
        except mtef_service.MTEFError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'created': result.created, 'kept': result.kept})

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        """Approve this year. A broken fiscal rule blocks it unless ``override_reason`` is given; the reason is kept."""
        projection = self.get_object()
        user = request.user
        try:
            findings = mtef_service.approve(
                projection, override_reason=str(request.data.get('override_reason') or ''),
                actor_name=(user.get_full_name() or user.get_username()) if user.is_authenticated else '')
        except mtef_service.MTEFError as exc:
            return Response({'error': str(exc), 'findings': [f.as_dict() for f in exc.findings]}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'status': projection.status, 'findings': [f.as_dict() for f in findings]})

    @action(detail=True, methods=['post'], url_path='reopen')
    def reopen(self, request, pk=None):
        projection = self.get_object()
        try:
            mtef_service.reopen(projection, reason=str(request.data.get('reason') or ''))
        except mtef_service.MTEFError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'status': projection.status})


class MTEFPolicyViewSet(viewsets.ModelViewSet):
    """The fiscal rules the MTEF is held to. There is one set per government; use ``current``."""
    module_key = 'budget_prep'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = MTEFPolicy.objects.all()
    serializer_class = MTEFPolicySerializer

    @action(detail=False, methods=['get', 'patch'], url_path='current')
    def current(self, request):
        policy = mtef_service.get_policy()
        if request.method == 'PATCH':
            serializer = self.get_serializer(policy, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(self.get_serializer(policy).data)


class MDACeilingViewSet(viewsets.ModelViewSet):
    module_key = 'budget_prep'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = MDACeiling.objects.all()
    serializer_class = MDACeilingSerializer
    filterset_fields = ['fiscal_year', 'mda_name']

    # A ceiling is drawn from the MTEF envelope, so it is checked against the approved framework for its year.
    def _check(self, serializer, exclude_pk=None):
        fields = ('fiscal_year', 'personnel_ceiling', 'overhead_ceiling', 'capital_ceiling')
        current = {n: getattr(serializer.instance, n) for n in fields} if serializer.instance is not None else {}
        data = {**current, **serializer.validated_data}
        try:
            mtef_service.check_ceiling_fits(
                data['fiscal_year'], personnel=data.get('personnel_ceiling'), overhead=data.get('overhead_ceiling'),
                capital=data.get('capital_ceiling'), exclude_pk=exclude_pk)
        except mtef_service.MTEFError as exc:
            raise ValidationError({'detail': str(exc)})

    def perform_create(self, serializer):
        self._check(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self._check(serializer, exclude_pk=serializer.instance.pk)
        serializer.save()


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

    @action(detail=False, methods=['get'], url_path='supplementary-report')
    def supplementary(self, request):
        """Supplementary budgets for a year, per MDA and by stage, against the original appropriation. Read-only."""
        try:
            fiscal_year = int(request.query_params.get('fiscal_year'))
        except (TypeError, ValueError):
            return Response({'error': 'fiscal_year is required and must be a year.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(supplementary_report(fiscal_year))

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
