from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from .common import AccountingPagination
from ..models import (
    TaxRegistration, TaxExemption, TaxReturn, WithholdingTax, TaxCode,
)
from ..serializers import (
    TaxRegistrationSerializer, TaxExemptionSerializer, TaxReturnSerializer,
    WithholdingTaxSerializer, TaxCodeSerializer,
)
from core.permissions import ModuleEnabled, RBACPermission
from rest_framework.permissions import IsAuthenticated


class TaxRegistrationViewSet(viewsets.ModelViewSet):
    module_key = "accounting"
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TaxRegistration.objects.all()
    serializer_class = TaxRegistrationSerializer
    filterset_fields = ['tax_type', 'is_active']


class TaxExemptionViewSet(viewsets.ModelViewSet):
    module_key = "accounting"
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TaxExemption.objects.all().select_related('tax_registration', 'vendor')
    serializer_class = TaxExemptionSerializer
    filterset_fields = ['tax_registration', 'is_active']


class TaxReturnViewSet(viewsets.ModelViewSet):
    module_key = "accounting"
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TaxReturn.objects.all().select_related('tax_registration')
    serializer_class = TaxReturnSerializer
    filterset_fields = ['tax_registration', 'status', 'tax_type']

    @action(detail=True, methods=['post'])
    def calculate(self, request, pk=None):
        tax_return = self.get_object()
        tax_return.tax_due = tax_return.output_tax - tax_return.input_tax
        tax_return.save()
        return Response(TaxReturnSerializer(tax_return).data)


class WithholdingTaxViewSet(viewsets.ModelViewSet):
    module_key = "accounting"
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = WithholdingTax.objects.all().select_related('withholding_account')
    serializer_class = WithholdingTaxSerializer
    filterset_fields = ['income_type', 'is_active']
    search_fields = ['code', 'name', 'income_type']
    pagination_class = AccountingPagination


class TaxCodeViewSet(viewsets.ModelViewSet):
    module_key = "accounting"
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = TaxCode.objects.all().select_related('tax_account')
    serializer_class = TaxCodeSerializer
    filterset_fields = ['tax_type', 'direction', 'is_active']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination
