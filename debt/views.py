"""
debt viewsets — module_key = 'debt'.
"""
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounting.models import BankAccount
from accounting.services.base_posting import TransactionPostingError
from core.permissions import IsApprover, ModuleEnabled, RBACPermission
from . import gl
from .models import (
    DebtDrawdown,
    DebtInstrument,
    AmortisationSchedule,
    AmortisationCoupon,
    AmortisationLedger,
    DebtServiceCost,
    DebtAversionStatement,
)
from .serializers import (
    DebtClassificationSerializer,
    DebtDrawdownSerializer,
    DebtInstrumentSerializer,
    AmortisationScheduleSerializer,
    AmortisationCouponSerializer,
    AmortisationLedgerSerializer,
    DebtServiceCostSerializer,
    DebtAversionStatementSerializer,
)


logger = logging.getLogger(__name__)


def _fail(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({'error': str(message)}, status=code)


def _date(raw, label):
    if raw in (None, ''):
        return None
    if isinstance(raw, date):
        return raw
    try:
        return datetime.strptime(str(raw)[:10], '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'{label} must be a date (YYYY-MM-DD).')


def _bank(raw):
    if raw in (None, ''):
        return None
    bank = BankAccount.objects.filter(pk=raw).first()
    if bank is None:
        raise ValueError('That bank account does not exist.')
    return bank


def _run(work):
    """Run a GL action and turn its refusals into a 400 the user can read."""
    try:
        return work()
    except (TransactionPostingError, ValueError) as exc:
        return _fail(exc)
    except DjangoValidationError as exc:
        return _fail('; '.join(exc.messages))
    except Exception as exc:  # noqa: BLE001 - JournalPostingError and friends carry a sentence for the user
        if exc.__class__.__name__ in ('JournalPostingError', 'BudgetExceededError', 'PeriodClosedError'):
            return _fail(exc)
        logger.exception('Debt GL action failed')
        return _fail('The action could not be completed. The error has been logged.', status.HTTP_500_INTERNAL_SERVER_ERROR)


class DebtInstrumentViewSet(viewsets.ModelViewSet):
    module_key = 'debt'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = DebtInstrument.objects.select_related(
        'liability_account', 'current_portion_account', 'interest_expense_account', 'bank_account')
    serializer_class = DebtInstrumentSerializer
    filterset_fields = ['instrument_type', 'status', 'creditor']

    def get_permissions(self):
        if self.action in ('drawdown', 'reclassify'):
            return [IsAuthenticated(), ModuleEnabled(), RBACPermission(), IsApprover('post')]
        return super().get_permissions()

    def destroy(self, request, *args, **kwargs):
        # Money already received or reclassified is in the general ledger: the instrument cannot simply disappear.
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return _fail('This instrument has drawdowns or classifications posted to the ledger, so it cannot be deleted. '
                         'Close it instead.', status.HTTP_409_CONFLICT)

    @action(detail=True, methods=['post'], url_path='standard-accounts')
    def standard_accounts(self, request, pk=None):
        """Fill the GL mapping from the chart of accounts (long-term borrowings, current portion, interest)."""
        instrument = self.get_object()
        return _run(lambda: Response({**gl.apply_standard_accounts(instrument), 'status': 'Standard accounts applied.'}))

    @action(detail=True, methods=['get'])
    def position(self, request, pk=None):
        """Outstanding principal split into current and non-current, with what a reclassification would move."""
        instrument = self.get_object()

        def work():
            as_of = _date(request.query_params.get('as_of'), 'The date')
            data = gl.position(instrument, as_of)
            return Response({k: (str(v) if isinstance(v, Decimal) else v) for k, v in data.items()})
        return _run(work)

    @action(detail=True, methods=['post'])
    def drawdown(self, request, pk=None):
        """Record money received: Dr bank / Cr non-current liability. Body: amount, bank_account, drawdown_date, reference."""
        instrument = self.get_object()

        def work():
            try:
                amount = Decimal(str(request.data.get('amount')))
                if not amount.is_finite():
                    raise InvalidOperation
            except (InvalidOperation, TypeError):
                raise ValueError('Enter the amount drawn as a number.')
            drawdown = gl.record_drawdown(
                instrument, amount=amount, bank_account=_bank(request.data.get('bank_account')),
                drawdown_date=_date(request.data.get('drawdown_date'), 'The drawdown date'), actor=request.user,
                reference=str(request.data.get('reference') or ''))
            return Response(DebtDrawdownSerializer(drawdown).data, status=status.HTTP_201_CREATED)
        return _run(work)

    @action(detail=True, methods=['post'])
    def reclassify(self, request, pk=None):
        """Move principal due within twelve months to current liabilities. Body: as_of (default today)."""
        instrument = self.get_object()

        def work():
            row = gl.reclassify_current_portion(instrument, as_of=_date(request.data.get('as_of'), 'The date'), actor=request.user)
            return Response(DebtClassificationSerializer(row).data, status=status.HTTP_201_CREATED)
        return _run(work)

    @action(detail=True, methods=['get'])
    def drawdowns(self, request, pk=None):
        rows = self.get_object().drawdowns.select_related('bank_account', 'journal')
        return Response(DebtDrawdownSerializer(rows, many=True).data)

    @action(detail=True, methods=['get'])
    def classifications(self, request, pk=None):
        rows = self.get_object().classifications.select_related('journal')
        return Response(DebtClassificationSerializer(rows, many=True).data)


class AmortisationScheduleViewSet(viewsets.ModelViewSet):
    module_key = 'debt'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = AmortisationSchedule.objects.all()
    serializer_class = AmortisationScheduleSerializer


class AmortisationCouponViewSet(viewsets.ModelViewSet):
    module_key = 'debt'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = AmortisationCoupon.objects.all()
    serializer_class = AmortisationCouponSerializer
    filterset_fields = ['status', 'schedule', 'schedule__instrument']

    def get_permissions(self):
        if self.action == 'pay':
            return [IsAuthenticated(), ModuleEnabled(), RBACPermission(), IsApprover('post')]
        return super().get_permissions()

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        """Pay the coupon from a bank account and post it. Body: bank_account (default: the instrument's), paid_date."""
        from .services import DebtServiceGLService
        coupon = self.get_object()

        def work():
            journal = DebtServiceGLService.pay_coupon(
                coupon=coupon, actor=request.user, bank_account=_bank(request.data.get('bank_account')),
                paid_date=_date(request.data.get('paid_date'), 'The payment date'))
            coupon.refresh_from_db()
            data = AmortisationCouponSerializer(coupon).data
            data['journal_number'] = journal.document_number
            return Response(data)
        return _run(work)


class AmortisationLedgerViewSet(viewsets.ModelViewSet):
    module_key = 'debt'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = AmortisationLedger.objects.all()
    serializer_class = AmortisationLedgerSerializer


class DebtServiceCostViewSet(viewsets.ModelViewSet):
    module_key = 'debt'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = DebtServiceCost.objects.all()
    serializer_class = DebtServiceCostSerializer


class DebtAversionStatementViewSet(viewsets.ModelViewSet):
    module_key = 'debt'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = DebtAversionStatement.objects.all()
    serializer_class = DebtAversionStatementSerializer


class DebtDrawdownViewSet(viewsets.ReadOnlyModelViewSet):
    module_key = 'debt'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = DebtDrawdown.objects.select_related('instrument', 'bank_account', 'journal')
    serializer_class = DebtDrawdownSerializer
    filterset_fields = ['instrument']
