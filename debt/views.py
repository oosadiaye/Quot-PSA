"""
debt viewsets — module_key = 'debt'.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ModuleEnabled, RBACPermission
from .models import (
    DebtInstrument,
    AmortisationSchedule,
    AmortisationCoupon,
    AmortisationLedger,
    DebtServiceCost,
    DebtAversionStatement,
)
from .serializers import (
    DebtInstrumentSerializer,
    AmortisationScheduleSerializer,
    AmortisationCouponSerializer,
    AmortisationLedgerSerializer,
    DebtServiceCostSerializer,
    DebtAversionStatementSerializer,
)


class DebtInstrumentViewSet(viewsets.ModelViewSet):
    module_key = 'debt'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = DebtInstrument.objects.all()
    serializer_class = DebtInstrumentSerializer
    filterset_fields = ['instrument_type', 'status', 'creditor']


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
    filterset_fields = ['status', 'schedule']


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
