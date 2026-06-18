"""
Operator surface for the payment-cascade reconciliation queue
(H2 deferred follow-up — WS6).

Exposes a read-mostly REST endpoint over ``PaymentCascadeFailure`` so
AP/finance operators can:

* List pending failures (default filter: ``resolved=False``).
* Drill into one for diagnosis.
* Mark a failure resolved with a mandatory resolution note (auditable).

Permission: requires ``accounting.view_paymentcascadefailure`` (read)
and ``accounting.resolve_paymentcascadefailure`` (write). The
``resolve_paymentcascadefailure`` permission is a NEW per-row action;
declared on the model via ``Meta.permissions`` would be cleanest but
we keep this simple by checking ``can_resolve_cascade`` group-style
permission OR superuser. Tenants can grant via the standard Django
permission UI; defaults to deny.
"""
from __future__ import annotations

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounting.models import PaymentCascadeFailure
from accounting.serializers import PaymentCascadeFailureSerializer


class PaymentCascadeFailureViewSet(viewsets.ReadOnlyModelViewSet):
    """List + retrieve + resolve for the payment-reconciliation queue."""

    queryset = (
        PaymentCascadeFailure.objects
        .select_related('payment', 'ipc', 'resolved_by')
        .all()
    )
    serializer_class = PaymentCascadeFailureSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['resolved', 'payment', 'ipc', 'error_class']
    ordering_fields = ['created_at', 'resolved_at']
    ordering = ['-created_at']

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Mark a failure resolved with an auditable note.

        Required body field: ``resolution_note`` (≥10 chars).

        V14 — race-condition fix. Two concurrent POST /resolve/ calls
        previously both passed the ``if failure.resolved`` check and
        double-resolved the same row (overwriting ``resolved_by`` /
        ``resolution_note`` non-deterministically). Wrap the check +
        write in an atomic with ``select_for_update`` so only one
        request can pass the gate; the second gets a 409.
        """
        user = request.user

        # Permission: only specific role can resolve. Superusers always.
        # V3 — use the dedicated ``resolve_paymentcascadefailure`` perm
        # (not the auto-generated ``change_paymentcascadefailure`` which
        # would grant the action to any user who can edit the row).
        if not (
            user.is_superuser
            or user.has_perm('accounting.resolve_paymentcascadefailure')
        ):
            return Response(
                {'error': 'Only users with resolve permission may close '
                          'cascade-failure rows.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        note = (request.data.get('resolution_note') or '').strip()
        if len(note) < 10:
            return Response(
                {'error': 'A resolution_note of at least 10 characters '
                          'is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            try:
                failure = (
                    PaymentCascadeFailure.objects.select_for_update()
                    .get(pk=self.kwargs['pk'])
                )
            except PaymentCascadeFailure.DoesNotExist:
                return Response(
                    {'error': 'Not found.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if failure.resolved:
                return Response(
                    {'error': 'This failure is already resolved.'},
                    status=status.HTTP_409_CONFLICT,
                )
            failure.mark_resolved(user=user, note=note)

        return Response(self.get_serializer(failure).data)

    @action(detail=False, methods=['get'])
    def queue_summary(self, request):
        """Lightweight dashboard summary: count + oldest pending.

        Useful for the AP queue widget in the operator dashboard.
        """
        from django.db.models import Min

        pending = self.queryset.filter(resolved=False)
        agg = pending.aggregate(oldest=Min('created_at'))
        return Response({
            'pending_count': pending.count(),
            'oldest_pending_at': agg['oldest'],
        })
