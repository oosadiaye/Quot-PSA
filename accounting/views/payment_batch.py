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
from core.permissions import RBACPermission
from core.services.sod_evaluator import SoDViolation
from rest_framework.permissions import IsAuthenticated


def _bad_request(exc: DjangoValidationError) -> Response:
    messages = exc.messages if hasattr(exc, 'messages') else [str(exc)]
    return Response({'error': ' '.join(messages)}, status=status.HTTP_400_BAD_REQUEST)


def _sod_forbidden(exc: SoDViolation) -> Response:
    """403 carrying each breached rule, so the UI can name them.

    The rules are tenant data — an admin can deactivate or re-scope any of
    them from the SoD-rules page — so the message must say WHICH rule
    blocked the action rather than asserting a fixed policy.
    """
    return Response(
        {
            'error': str(exc),
            'code': 'sod_violation',
            'violations': [
                {
                    'rule_code': v.rule_code,
                    'rule_name': v.rule_name,
                    'reason': v.reason,
                }
                for v in exc.violations
            ],
        },
        status=status.HTTP_403_FORBIDDEN,
    )


class PaymentBatchViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    """Bank payment/confirmation letters.

    MDA isolation mirrors PaymentViewSet: a batch is visible when any of
    its lines' payments allocate to an invoice in the operator's MDA.
    """

    # Stated explicitly rather than inherited from
    # ``DEFAULT_PERMISSION_CLASSES``. The effective gates are unchanged —
    # RBACPermission authenticates before it checks model permissions — but
    # an endpoint that instructs a bank to move public money should not
    # depend on a settings default staying what it is today, and
    # ``get_permissions`` below augments this list rather than replacing it.
    permission_classes = [IsAuthenticated, RBACPermission]

    org_filter_field = 'lines__payment__allocations__invoice__mda'
    queryset = (PaymentBatch.objects
                .select_related('source_bank_account')
                .prefetch_related('lines__payment')
                .distinct())
    serializer_class = PaymentBatchSerializer
    filterset_fields = ['status', 'batch_date', 'source_bank_account']

    # A batch is a lifecycle document driven by the service's guarded
    # transitions. PUT is not one of them — a wholesale replace would let a
    # caller rewrite a signed letter in a single call.
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        # Dispatching produces a signed instruction to a bank to move real
        # money — at least as sensitive as post_payment (S7-01).
        #
        # These are ADDED to the class-level permissions, never substituted
        # for them. Returning a bare list here previously discarded every
        # ordinary gate for this one action, so the endpoint that moves
        # money was the least guarded on the ViewSet — the opposite of the
        # intent, and the exact hole this gate exists to close.
        perms = super().get_permissions()
        if self.action == 'dispatch_batch':
            from accounting.permissions import RequiresMFA
            from core.permissions import IsApprover
            perms = perms + [IsApprover('post'), RequiresMFA()]
        return perms

    def update(self, request, *args, **kwargs):
        """Only a Draft batch may be edited.

        ``status``/``batch_number``/``addressee_*`` are already read-only on
        the serializer, but ``source_bank_account`` and ``batch_date`` are
        not — and repointing the source account on a Dispatched batch breaks
        the "one letter instructs one bank about one account" invariant the
        service enforces at add-time, while desyncing the batch from its
        frozen addressee snapshot.
        """
        batch = self.get_object()
        if batch.status != PaymentBatch.STATUS_DRAFT:
            return Response(
                {'error': f'{batch.batch_number} is {batch.status}; only Draft '
                          f'batches can be edited.'},
                status=status.HTTP_409_CONFLICT)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Refuse to delete a batch the bank has been told about.

        Deleting cascades to PaymentBatchLine, which releases the partial
        unique index on ``payment``, which returns those payments to the
        eligible pool. On a Dispatched or Confirmed batch that is a
        re-payment route around every control in this module: the bank has
        acted, and the payments become batchable again as though they never
        were. Cancel it instead — cancel keeps the record and its reason.
        """
        batch = self.get_object()
        if batch.status in (PaymentBatch.STATUS_DISPATCHED,
                            PaymentBatch.STATUS_CONFIRMED):
            return Response(
                {'error': f'{batch.batch_number} is {batch.status} — the bank '
                          f'has been instructed. Deleting it would release its '
                          f'payments for re-batching. Cancel the batch instead, '
                          f'recording why.'},
                status=status.HTTP_409_CONFLICT)
        return super().destroy(request, *args, **kwargs)

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
        # MDA isolation. The batch list is filtered through
        # ``org_filter_field``, but this action builds its own Payment
        # queryset — without the same filter an operator could see, and then
        # batch, payments belonging to another MDA. Mirrors
        # PaymentViewSet.org_filter_field exactly.
        qs = self.apply_org_filter(
            PaymentBatchService.eligible_payments(bank_account),
            field='allocations__invoice__mda',
        )
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
        except SoDViolation as exc:
            return _sod_forbidden(exc)
        except DjangoValidationError as exc:
            return _bad_request(exc)
        return Response(PaymentBatchSerializer(batch).data)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        batch = self.get_object()
        try:
            PaymentBatchService.confirm(batch, request.user)
        except SoDViolation as exc:
            return _sod_forbidden(exc)
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

    # Explicit for the same reason as PaymentBatchViewSet: this model holds
    # the signatory names and signature images that appear on the letter.
    permission_classes = [IsAuthenticated, RBACPermission]

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
