"""HTTP layer for payment batching. All rules live in the service."""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounting.models import BankAccount, BankLetterSettings, PaymentBatch
from accounting.serializers import PaymentSerializer
from accounting.serializers_payment_batch import (
    AddLinesSerializer, BankLetterSettingsSerializer, CancelBatchSerializer,
    PaymentBatchCreateSerializer, PaymentBatchSerializer, RemoveLineSerializer,
)
from accounting.services.payment_batch import PaymentBatchService
from core.mixins import OrganizationFilterMixin


def _bad_request(exc: DjangoValidationError) -> Response:
    messages = exc.messages if hasattr(exc, 'messages') else [str(exc)]
    return Response({'error': ' '.join(messages)}, status=status.HTTP_400_BAD_REQUEST)


class PaymentBatchViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    """Bank payment/confirmation letters.

    MDA isolation mirrors PaymentViewSet: a batch is visible when any of
    its lines' payments allocate to an invoice in the operator's MDA.
    """

    org_filter_field = 'lines__payment__allocations__invoice__mda'
    queryset = (PaymentBatch.objects
                .select_related('source_bank_account')
                .prefetch_related('lines__payment')
                .distinct())
    serializer_class = PaymentBatchSerializer
    filterset_fields = ['status', 'batch_date', 'source_bank_account']

    def get_permissions(self):
        # Dispatching produces a signed instruction to a bank to move real
        # money — at least as sensitive as post_payment (S7-01). Without
        # this gate the batch would be a way around that control.
        if self.action == 'dispatch_batch':
            from accounting.permissions import RequiresMFA
            from core.permissions import IsApprover
            return [IsApprover('post'), RequiresMFA()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        payload = PaymentBatchCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        bank_account = BankAccount.objects.filter(
            pk=data['source_bank_account']).first()
        if bank_account is None:
            return Response({'error': 'Unknown bank account.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            batch = PaymentBatchService.create_batch(
                bank_account=bank_account,
                batch_date=data.get('batch_date'),
                payment_ids=data['payment_ids'],
                user=request.user,
            )
        except DjangoValidationError as exc:
            return _bad_request(exc)
        return Response(PaymentBatchSerializer(batch).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def eligible_payments(self, request):
        bank_account_id = request.query_params.get('bank_account')
        if not bank_account_id:
            return Response({'error': 'bank_account query parameter is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        bank_account = BankAccount.objects.filter(pk=bank_account_id).first()
        if bank_account is None:
            return Response({'error': 'Unknown bank account.'},
                            status=status.HTTP_400_BAD_REQUEST)
        qs = PaymentBatchService.eligible_payments(bank_account)
        return Response(PaymentSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'])
    def add_lines(self, request, pk=None):
        payload = AddLinesSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        batch = self.get_object()
        try:
            PaymentBatchService.add_payments(
                batch, payload.validated_data['payment_ids'], request.user)
        except DjangoValidationError as exc:
            return _bad_request(exc)
        batch.refresh_from_db()
        return Response(PaymentBatchSerializer(batch).data)

    @action(detail=True, methods=['post'])
    def remove_line(self, request, pk=None):
        payload = RemoveLineSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        batch = self.get_object()
        try:
            PaymentBatchService.remove_line(
                batch, payload.validated_data['line_id'], request.user)
        except DjangoValidationError as exc:
            return _bad_request(exc)
        batch.refresh_from_db()
        return Response(PaymentBatchSerializer(batch).data)

    # NOTE: named ``dispatch_batch`` — NOT ``dispatch``. ``ViewSetMixin``
    # (rest_framework/viewsets.py) builds a closure in ``as_view()`` that
    # calls ``self.dispatch(request, *args, **kwargs)`` for EVERY request
    # to this viewset, resolving to ``APIView.dispatch`` (rest_framework/
    # views.py). A method literally named ``dispatch`` defined here would
    # sit lower in the MRO than APIView and would shadow the real HTTP
    # dispatcher outright — breaking list/create/retrieve/every action,
    # not just this one. ``url_path='dispatch'`` keeps the public URL
    # unchanged while avoiding the name collision.
    @action(detail=True, methods=['post'], url_path='dispatch')
    def dispatch_batch(self, request, pk=None):
        batch = self.get_object()
        try:
            PaymentBatchService.dispatch(batch, request.user)
        except DjangoValidationError as exc:
            return _bad_request(exc)
        return Response(PaymentBatchSerializer(batch).data)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        batch = self.get_object()
        try:
            PaymentBatchService.confirm(batch, request.user)
        except DjangoValidationError as exc:
            return _bad_request(exc)
        return Response(PaymentBatchSerializer(batch).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        payload = CancelBatchSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        batch = self.get_object()
        try:
            PaymentBatchService.cancel(
                batch, request.user, payload.validated_data.get('reason', ''))
        except DjangoValidationError as exc:
            return _bad_request(exc)
        return Response(PaymentBatchSerializer(batch).data)

    @action(detail=True, methods=['get'])
    def letter(self, request, pk=None):
        """Everything the print view needs, in one request."""
        batch = self.get_object()
        return Response({
            'batch': PaymentBatchSerializer(batch).data,
            'settings': BankLetterSettingsSerializer(
                BankLetterSettings.get_singleton(),
                context={'request': request}).data,
        })


class BankLetterSettingsViewSet(viewsets.GenericViewSet):
    """Singleton settings — mirrors the warrant-printout-settings pattern."""

    queryset = BankLetterSettings.objects.all()
    serializer_class = BankLetterSettingsSerializer

    @action(detail=False, methods=['get', 'patch'])
    def current(self, request):
        settings_obj = BankLetterSettings.get_singleton()
        if request.method == 'PATCH':
            if not (request.user.is_staff or request.user.is_superuser):
                return Response(
                    {'error': 'Only staff or superusers can update bank-letter settings.'},
                    status=status.HTTP_403_FORBIDDEN)
            serializer = self.get_serializer(
                settings_obj, data=request.data, partial=True,
                context={'request': request})
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(self.get_serializer(
            settings_obj, context={'request': request}).data)
