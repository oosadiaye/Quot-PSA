"""
IPSAS 19 registry endpoints.

Three viewsets for the three register kinds:

  * ``ProvisionViewSet``           — recognised liability (balance-sheet)
  * ``ContingentLiabilityViewSet`` — disclosed, not recognised
  * ``ContingentAssetViewSet``     — disclosed only when probable

All three support list/retrieve/create/update/destroy with standard
DRF CRUD, plus custom lifecycle actions:

  * ``POST /provisions/{id}/recognise/``  — move DRAFT → RECOGNISED
                                            (requires is_recognisable)
  * ``POST /provisions/{id}/settle/``     — RECOGNISED → SETTLED
  * ``POST /provisions/{id}/reverse/``    — RECOGNISED → REVERSED
                                            (no longer probable)

Deletion is discouraged: use the ``cancel`` status transition instead.
Destroy is permitted only while the provision is still DRAFT.
"""
from __future__ import annotations

from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounting.models import Provision, ContingentLiability, ContingentAsset


# =============================================================================
# Serializers
# =============================================================================

class ProvisionSerializer(serializers.ModelSerializer):
    """Full Provision payload for the registry UI."""
    is_recognisable = serializers.BooleanField(read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    likelihood_display = serializers.CharField(source='get_likelihood_display', read_only=True)
    mda_code = serializers.CharField(source='mda.code', read_only=True, default=None)
    mda_name = serializers.CharField(source='mda.name', read_only=True, default=None)

    class Meta:
        model = Provision
        fields = [
            'id', 'reference',
            'category', 'category_display',
            'title', 'description',
            'amount', 'undiscounted_amount', 'discount_rate',
            'recognition_date', 'expected_settlement_date',
            'likelihood', 'likelihood_display',
            'journal_entry',
            'mda', 'mda_code', 'mda_name',
            'status', 'status_display',
            'settled_at', 'settled_by',
            'notes',
            'is_recognisable',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id',
            'category_display', 'status_display', 'likelihood_display',
            'mda_code', 'mda_name',
            'settled_at', 'settled_by',
            'is_recognisable',
            'created_at', 'updated_at',
        ]


class ContingentLiabilitySerializer(serializers.ModelSerializer):
    likelihood_display = serializers.CharField(source='get_likelihood_display', read_only=True)
    mda_code = serializers.CharField(source='mda.code', read_only=True, default=None)
    mda_name = serializers.CharField(source='mda.name', read_only=True, default=None)

    class Meta:
        model = ContingentLiability
        fields = [
            'id', 'reference', 'title', 'description',
            'estimated_amount',
            'likelihood', 'likelihood_display',
            'arising_date', 'expected_resolution_date',
            'mda', 'mda_code', 'mda_name',
            'is_disclosed',
            'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'likelihood_display', 'mda_code', 'mda_name',
            'created_at', 'updated_at',
        ]


class ContingentAssetSerializer(serializers.ModelSerializer):
    is_disclosable = serializers.BooleanField(read_only=True)
    likelihood_display = serializers.CharField(source='get_likelihood_display', read_only=True)
    mda_code = serializers.CharField(source='mda.code', read_only=True, default=None)
    mda_name = serializers.CharField(source='mda.name', read_only=True, default=None)

    class Meta:
        model = ContingentAsset
        fields = [
            'id', 'reference', 'title', 'description',
            'estimated_amount',
            'likelihood', 'likelihood_display',
            'arising_date', 'expected_realisation_date',
            'mda', 'mda_code', 'mda_name',
            'notes',
            'is_disclosable',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'likelihood_display', 'mda_code', 'mda_name',
            'is_disclosable',
            'created_at', 'updated_at',
        ]


# =============================================================================
# ViewSets
# =============================================================================

class ProvisionViewSet(viewsets.ModelViewSet):
    """Manage IPSAS 19 Provisions + their lifecycle."""
    queryset = Provision.objects.all().select_related('mda', 'journal_entry')
    serializer_class = ProvisionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'category', 'likelihood', 'mda']
    ordering_fields = ['recognition_date', 'amount', 'reference']
    ordering = ['-recognition_date']

    def perform_destroy(self, instance: Provision):
        """Only DRAFT provisions can be hard-deleted. Recognised
        provisions must transition through the ``reverse`` or
        ``settle`` actions so the balance-sheet impact is properly
        logged."""
        if instance.status != 'DRAFT':
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                'Only DRAFT provisions can be deleted. For recognised '
                'provisions, use the /reverse/ or /settle/ action.'
            )
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def recognise(self, request, pk=None):
        """Move a Provision from DRAFT to RECOGNISED.

        Enforces IPSAS 19 ¶22: recognition requires probable outflow
        + reliable measurement. The ``is_recognisable`` property
        captures this check; if it returns False we refuse.
        """
        prov: Provision = self.get_object()
        if prov.status != 'DRAFT':
            return Response(
                {'error': f'Cannot recognise: provision status is {prov.status!r}, expected DRAFT.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not prov.is_recognisable:
            return Response(
                {'error': (
                    'IPSAS 19 ¶22 recognition gate failed: likelihood '
                    'must be PROBABLE or CERTAIN, and amount must be '
                    'positive and reliably measurable.'
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )
        prov.status = 'RECOGNISED'
        prov.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(prov).data)

    @action(detail=True, methods=['post'])
    def settle(self, request, pk=None):
        """Close a Provision after the obligation has been discharged."""
        from django.utils import timezone
        prov: Provision = self.get_object()
        if prov.status != 'RECOGNISED':
            return Response(
                {'error': f'Only RECOGNISED provisions can be settled. Current: {prov.status!r}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        prov.status = 'SETTLED'
        prov.settled_at = timezone.now()
        prov.settled_by = request.user if request.user.is_authenticated else None
        prov.notes = (prov.notes + '\n' if prov.notes else '') + (
            f'Settled on {prov.settled_at.date().isoformat()} '
            f'by {getattr(prov.settled_by, "username", "system")}.'
        )
        prov.save(update_fields=['status', 'settled_at', 'settled_by', 'notes', 'updated_at'])
        return Response(self.get_serializer(prov).data)

    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        """Reverse a Provision when the obligation is no longer probable.

        IPSAS 19 ¶60: reassess provisions at each reporting date and
        reverse if outflow becomes less than probable.
        """
        prov: Provision = self.get_object()
        if prov.status != 'RECOGNISED':
            return Response(
                {'error': f'Only RECOGNISED provisions can be reversed. Current: {prov.status!r}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reason = (request.data.get('reason') or '').strip()
        if len(reason) < 10:
            return Response(
                {'error': 'A reason of at least 10 characters is required for reversal.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        prov.status = 'REVERSED'
        prov.notes = (prov.notes + '\n' if prov.notes else '') + (
            f'Reversed per IPSAS 19 ¶60 by '
            f'{getattr(request.user, "username", "system")}: {reason}'
        )
        prov.save(update_fields=['status', 'notes', 'updated_at'])
        return Response(self.get_serializer(prov).data)


class ContingentLiabilityViewSet(viewsets.ModelViewSet):
    """Manage IPSAS 19 Contingent Liabilities register."""
    queryset = ContingentLiability.objects.all().select_related('mda')
    serializer_class = ContingentLiabilitySerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['likelihood', 'is_disclosed', 'mda']
    ordering_fields = ['arising_date', 'estimated_amount']
    ordering = ['-arising_date']


class ContingentAssetViewSet(viewsets.ModelViewSet):
    """Manage IPSAS 19 Contingent Assets register."""
    queryset = ContingentAsset.objects.all().select_related('mda')
    serializer_class = ContingentAssetSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['likelihood', 'mda']
    ordering_fields = ['arising_date', 'estimated_amount']
    ordering = ['-arising_date']
