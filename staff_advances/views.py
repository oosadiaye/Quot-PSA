"""
staff_advances viewsets — module_key = 'staff_advances'.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounting.models import Account
from accounting.services.base_posting import TransactionPostingError

from core.permissions import ModuleEnabled, RBACPermission
from . import lifecycle
from .models import (
    StaffAdvance,
    ImprestAccount,
    ImprestRetirement,
    PerDiemTable,
    TravelRequest,
    TravelAdvance,
    TravelRetirement,
)
from .services import StaffAdvanceGLService
from .serializers import (
    StaffAdvanceSerializer,
    ImprestAccountSerializer,
    ImprestRetirementSerializer,
    PerDiemTableSerializer,
    TravelRequestSerializer,
    TravelAdvanceSerializer,
    TravelRetirementSerializer,
)


def _refused(exc: Exception) -> Response:
    """A step the ledger or the workflow refuses is a 409 with the reason, never a 500."""
    message = '; '.join(exc.messages) if isinstance(exc, DjangoValidationError) else str(exc)
    return Response({'error': message}, status=status.HTTP_409_CONFLICT)


def _account(value):
    """An optional account id from a request body: None when absent, False when it names nothing."""
    if value in (None, ''):
        return None
    return Account.objects.filter(pk=value).first() or False


REFUSALS = (TransactionPostingError, lifecycle.AdvanceError, DjangoValidationError)
BAD_ACCOUNT = {'error': 'expense_account does not exist.'}


class StaffAdvanceViewSet(viewsets.ModelViewSet):
    module_key = 'staff_advances'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = StaffAdvance.objects.all()
    serializer_class = StaffAdvanceSerializer
    filterset_fields = ['employee', 'status', 'purpose']

    @action(detail=True, methods=['post'], url_path='disburse')
    def disburse(self, request, pk=None):
        """Pay the advance out: DR staff-advance recon / CR cash. Once only."""
        advance = self.get_object()
        try:
            journal = StaffAdvanceGLService.disburse(staff_advance=advance, actor=request.user)
        except REFUSALS as exc:
            return _refused(exc)
        return Response({'journal': journal.reference_number, 'status': advance.status})

    @action(detail=True, methods=['post'], url_path='recover')
    def recover(self, request, pk=None):
        """Record a recovery slice (DR expense or cash / CR recon). Body: amount, notes, optional expense_account."""
        advance = self.get_object()
        try:
            amount = Decimal(str(request.data.get('amount')))
        except (InvalidOperation, TypeError):
            return Response({'error': 'amount is required and must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
        account = _account(request.data.get('expense_account'))
        if account is False:
            return Response(BAD_ACCOUNT, status=status.HTTP_400_BAD_REQUEST)
        try:
            journal = StaffAdvanceGLService.record_recovery(
                staff_advance=advance, amount=amount, actor=request.user, expense_account=account,
                notes=str(request.data.get('notes') or ''))
        except REFUSALS as exc:
            return _refused(exc)
        advance.refresh_from_db()
        return Response({'journal': journal.reference_number, 'status': advance.status,
                         'recovered_amount': str(advance.recovered_amount)})


class ImprestAccountViewSet(viewsets.ModelViewSet):
    module_key = 'staff_advances'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = ImprestAccount.objects.all()
    serializer_class = ImprestAccountSerializer
    filterset_fields = ['employee', 'status']


class ImprestRetirementViewSet(viewsets.ModelViewSet):
    module_key = 'staff_advances'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = ImprestRetirement.objects.all()
    serializer_class = ImprestRetirementSerializer

    @action(detail=True, methods=['post'], url_path='post')
    def post(self, request, pk=None):
        """Post this retirement to the ledger and add it to the imprest's retired total. Once only."""
        retirement = self.get_object()
        account = _account(request.data.get('expense_account'))
        if account is False:
            return Response(BAD_ACCOUNT, status=status.HTTP_400_BAD_REQUEST)
        try:
            journal = StaffAdvanceGLService.retire_imprest(retirement=retirement, actor=request.user, expense_account=account)
        except REFUSALS as exc:
            return _refused(exc)
        return Response({'journal': journal.reference_number})


class PerDiemTableViewSet(viewsets.ModelViewSet):
    module_key = 'staff_advances'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = PerDiemTable.objects.all()
    serializer_class = PerDiemTableSerializer


class TravelRequestViewSet(viewsets.ModelViewSet):
    module_key = 'staff_advances'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TravelRequest.objects.all()
    serializer_class = TravelRequestSerializer

    def _step(self, fn, *args):
        try:
            return Response(TravelRequestSerializer(fn(self.get_object(), *args)).data)
        except REFUSALS as exc:
            return _refused(exc)

    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        return self._step(lifecycle.submit_travel_request)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        return self._step(lifecycle.approve_travel_request)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        return self._step(lifecycle.reject_travel_request, str(request.data.get('reason') or ''))

    @action(detail=True, methods=['post'], url_path='advance')
    def advance(self, request, pk=None):
        """Pay the approved request's advance (optional body: amount)."""
        raw = request.data.get('amount')
        try:
            amount = Decimal(str(raw)) if raw not in (None, '') else None
        except InvalidOperation:
            return Response({'error': 'amount must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            travel = lifecycle.advance_travel(self.get_object(), actor=request.user, amount=amount)
        except REFUSALS as exc:
            return _refused(exc)
        return Response(TravelAdvanceSerializer(travel).data, status=status.HTTP_201_CREATED)
    filterset_fields = ['employee', 'status']


class TravelAdvanceViewSet(viewsets.ModelViewSet):
    module_key = 'staff_advances'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TravelAdvance.objects.all()
    serializer_class = TravelAdvanceSerializer


class TravelRetirementViewSet(viewsets.ModelViewSet):
    module_key = 'staff_advances'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TravelRetirement.objects.all()
    serializer_class = TravelRetirementSerializer

    @action(detail=True, methods=['post'], url_path='post')
    def post(self, request, pk=None):
        """Post this retirement: what was spent to expenditure, what is left back to cash. Must clear the whole advance."""
        account = _account(request.data.get('expense_account'))
        if account is False:
            return Response(BAD_ACCOUNT, status=status.HTTP_400_BAD_REQUEST)
        try:
            lifecycle.retire_travel(self.get_object(), actor=request.user, expense_account=account)
        except REFUSALS as exc:
            return _refused(exc)
        return Response({'status': 'retired'})
