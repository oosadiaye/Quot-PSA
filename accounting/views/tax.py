from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, F, Q
from django.db.models.functions import Coalesce
from django.db import transaction
from decimal import Decimal
from .common import AccountingPagination
from ..models import (
    TaxRegistration, TaxExemption, TaxReturn, WithholdingTax, TaxCode,
)
from ..serializers import (
    TaxRegistrationSerializer, TaxExemptionSerializer, TaxReturnSerializer,
    WithholdingTaxSerializer, TaxCodeSerializer,
)


class TaxRegistrationViewSet(viewsets.ModelViewSet):
    queryset = TaxRegistration.objects.all()
    serializer_class = TaxRegistrationSerializer
    filterset_fields = ['tax_type', 'is_active']


class TaxExemptionViewSet(viewsets.ModelViewSet):
    queryset = TaxExemption.objects.all().select_related('tax_registration', 'vendor', 'customer')
    serializer_class = TaxExemptionSerializer
    filterset_fields = ['tax_registration', 'is_active']


class TaxReturnViewSet(viewsets.ModelViewSet):
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
    queryset = WithholdingTax.objects.all().select_related('withholding_account')
    serializer_class = WithholdingTaxSerializer
    filterset_fields = ['income_type', 'is_active']
    search_fields = ['code', 'name', 'income_type']
    pagination_class = AccountingPagination


class TaxCodeViewSet(viewsets.ModelViewSet):
    queryset = TaxCode.objects.all().select_related('tax_account')
    serializer_class = TaxCodeSerializer
    filterset_fields = ['tax_type', 'direction', 'is_active']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination
