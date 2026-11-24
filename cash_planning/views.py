"""
cash_planning viewsets — module_key = 'cash_planning'.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsApprover, ModuleEnabled, RBACPermission
from .models import (
    CashPlan,
    CashForecastLine,
    CashPosition,
    WarrantRecommendation,
    CashPlanVariance,
)
from .warrants import WarrantPlanError, convert_to_warrant, generate_recommendations
from .serializers import (
    CashPlanSerializer,
    CashForecastLineSerializer,
    CashPositionSerializer,
    WarrantRecommendationSerializer,
    CashPlanVarianceSerializer,
)


class CashPlanViewSet(viewsets.ModelViewSet):
    module_key = 'cash_planning'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = CashPlan.objects.all()
    serializer_class = CashPlanSerializer


class CashForecastLineViewSet(viewsets.ModelViewSet):
    module_key = 'cash_planning'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = CashForecastLine.objects.all()
    serializer_class = CashForecastLineSerializer


class CashPositionViewSet(viewsets.ModelViewSet):
    module_key = 'cash_planning'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = CashPosition.objects.all()
    serializer_class = CashPositionSerializer


class WarrantRecommendationViewSet(viewsets.ModelViewSet):
    module_key = 'cash_planning'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    # Every recommendation of a quarter shares one date, so the id is the tie-breaker that keeps pages from shuffling.
    queryset = WarrantRecommendation.objects.all().order_by('recommendation_date', 'id')
    serializer_class = WarrantRecommendationSerializer
    filterset_fields = ['fiscal_year', 'quarter', 'status', 'mda_name']

    def get_permissions(self):
        # Issuing a warrant releases authority to spend, so it is an approver's act.
        if self.action in ('generate', 'convert'):
            return [IsAuthenticated(), ModuleEnabled(), RBACPermission(), IsApprover('post')]
        return super().get_permissions()

    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        """Propose a warrant release per active appropriation for a quarter. Writes recommendations only, never warrants.

        Body: ``fiscal_year``, ``quarter`` (1-4), optional ``available_cash`` (scales proposals down to fit) and ``mda_name``.
        Running it again replaces the still-proposed recommendations for that quarter.
        """
        try:
            fiscal_year, quarter = int(request.data.get('fiscal_year')), int(request.data.get('quarter'))
        except (TypeError, ValueError):
            return Response({'error': 'fiscal_year and quarter are required whole numbers.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = generate_recommendations(
                fiscal_year, quarter, available_cash=request.data.get('available_cash'),
                mda_name=str(request.data.get('mda_name') or ''))
        except ArithmeticError:
            return Response({'error': 'available_cash must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
        except WarrantPlanError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'created': result.created, 'replaced': result.replaced, 'total': str(result.total),
            'scaled_to': None if result.scaled_to is None else str(result.scaled_to), 'skipped': result.skipped})

    @action(detail=True, methods=['post'], url_path='accept')
    def accept(self, request, pk=None):
        rec = self.get_object()
        if rec.status != 'proposed':
            return Response({'error': f'Only a proposed recommendation can be accepted; this one is {rec.status}.'},
                            status=status.HTTP_400_BAD_REQUEST)
        rec.status = 'accepted'
        rec.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(rec).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        rec = self.get_object()
        if rec.status not in ('proposed', 'accepted'):
            return Response({'error': f'This recommendation is already {rec.status}.'}, status=status.HTTP_400_BAD_REQUEST)
        reason = str(request.data.get('reason') or '').strip()
        rec.status = 'rejected'
        if reason:
            rec.rationale = f'{rec.rationale}\nRejected: {reason}'.strip()
        rec.save(update_fields=['status', 'rationale', 'updated_at'])
        return Response(self.get_serializer(rec).data)

    @action(detail=True, methods=['post'], url_path='convert')
    def convert(self, request, pk=None):
        """Issue a PENDING warrant from this recommendation. Needs the warrant letter's ``authority_reference``;
        ``amount`` may lower the recommended figure but never raise it. Budget's own overlap and ceiling rules apply."""
        rec = self.get_object()
        try:
            warrant = convert_to_warrant(
                rec, authority_reference=str(request.data.get('authority_reference') or ''), issued_by=request.user,
                amount=request.data.get('amount'))
        except ArithmeticError:
            return Response({'error': 'amount must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
        except WarrantPlanError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'warrant': warrant.pk, 'status': warrant.status, 'amount_released': str(warrant.amount_released),
                         'recommendation': self.get_serializer(rec).data}, status=status.HTTP_201_CREATED)


class CashPlanVarianceViewSet(viewsets.ModelViewSet):
    module_key = 'cash_planning'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = CashPlanVariance.objects.all()
    serializer_class = CashPlanVarianceSerializer
