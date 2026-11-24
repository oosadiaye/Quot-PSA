"""
personnel_budget viewsets — all declare ``module_key = 'personnel_budget'`` so
core.permissions.ModuleEnabled refuses requests when the module is toggled off.
Composed with RBACPermission for per-role authorisation.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import ModuleEnabled, RBACPermission
from .models import (
    EstablishmentPost,
    EstablishmentVariance,
    PersonnelCostForecast,
    PayrollBudgetBinding,
)
from .services import BindingError, bind_checked, personnel_candidates
from .serializers import (
    EstablishmentPostSerializer,
    EstablishmentVarianceSerializer,
    PersonnelCostForecastSerializer,
    PayrollBudgetBindingSerializer,
)


class EstablishmentPostViewSet(viewsets.ModelViewSet):
    module_key = 'personnel_budget'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = EstablishmentPost.objects.all()
    serializer_class = EstablishmentPostSerializer
    filterset_fields = ['status', 'grade', 'mda_name', 'mda_admin']


class EstablishmentVarianceViewSet(viewsets.ModelViewSet):
    module_key = 'personnel_budget'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = EstablishmentVariance.objects.all()
    serializer_class = EstablishmentVarianceSerializer
    filterset_fields = ['post', 'is_breach']


class PersonnelCostForecastViewSet(viewsets.ModelViewSet):
    module_key = 'personnel_budget'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = PersonnelCostForecast.objects.all()
    serializer_class = PersonnelCostForecastSerializer
    filterset_fields = ['fiscal_year', 'mda_name', 'appropriation_line']


class PayrollBudgetBindingViewSet(viewsets.ModelViewSet):
    module_key = 'personnel_budget'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = PayrollBudgetBinding.objects.all()
    serializer_class = PayrollBudgetBindingSerializer
    filterset_fields = ['payroll_run', 'appropriation_line']

    # Creating or changing a binding always goes through the service, which checks the run and the appropriation and
    # takes the control snapshot; the stored figures are never taken from the request.
    def _bound(self, request, run, appropriation):
        try:
            return bind_checked(run, appropriation, bound_by=request.user)
        except BindingError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        bound = self._bound(request, data['payroll_run'], data['appropriation_line'])
        if isinstance(bound, Response):
            return bound
        return Response(self.get_serializer(bound).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        appropriation = serializer.validated_data.get('appropriation_line', instance.appropriation_line)
        bound = self._bound(request, instance.payroll_run, appropriation)
        if isinstance(bound, Response):
            return bound
        return Response(self.get_serializer(bound).data)

    def perform_destroy(self, instance):
        run = instance.payroll_run
        if run.status in ('Paid', 'Cancelled') or run.journal_entry_id:
            raise ValidationError({'error': 'This payroll run has already been paid, cancelled or posted, so its binding stays as the record.'})
        instance.delete()

    @action(detail=False, methods=['get'], url_path='suggest')
    def suggest(self, request):
        """Personnel appropriations a payroll run could be funded from, ones with enough balance first."""
        from hrm.models import PayrollRun

        raw = str(request.query_params.get('payroll_run', ''))
        run = PayrollRun.objects.select_related('period').filter(pk=raw).first() if raw.isdigit() else None
        if run is None:
            return Response({'error': 'payroll_run is required and must be an existing payroll run.'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'payroll_run': run.pk, 'run_number': run.run_number, 'gross': str(run.total_gross),
                         'candidates': personnel_candidates(run)})
