"""The supplier's catalogue, ``/api/v1/supplier-portal/catalogue/``, and the office's side of its price proposals.

Both sides sit behind the catalogue module's switch: with it off, the portal tab disappears and this answers ``module_disabled``.
"""
from __future__ import annotations

from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsApprover, ModuleEnabled, RBACPermission
from inventory.models import Item
from procurement.views_portal import IsSupplier

from . import portal_service as service
from .models import CataloguePriceProposal

MAX_ITEM_MATCHES = 20


class ProposalSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_code = serializers.CharField(source='item.sku', read_only=True)

    class Meta:
        model = CataloguePriceProposal
        fields = ['id', 'item', 'item_code', 'item_name', 'proposed_price', 'current_price', 'specification', 'status', 'reason',
                  'created_at', 'decided_at']
        read_only_fields = ['current_price', 'status', 'reason', 'created_at', 'decided_at']


class _SupplierView(APIView):
    module_key = 'catalogue'
    permission_classes = [IsAuthenticated, ModuleEnabled, IsSupplier]


class MyCatalogue(_SupplierView):
    def get(self, request):
        return Response([{
            'id': line.pk, 'item': line.item_id, 'item_code': line.item.sku, 'item_name': line.item.name,
            'unit_price': str(line.unit_price), 'specification': line.specification, 'effective_date': line.price_effective_date,
            'valid_to': line.catalogue.valid_to,
        } for line in service.current_items(request.vendor)])


class ItemSearch(_SupplierView):
    """Items a supplier can name when proposing a price. Only the code and name leave: nothing about stock or cost."""

    def get(self, request):
        q = (request.query_params.get('search') or '').strip()
        if len(q) < 2:
            return Response([])
        rows = Item.objects.filter(is_active=True).filter(name__icontains=q)[:MAX_ITEM_MATCHES]
        rows = list(rows) or list(Item.objects.filter(is_active=True, sku__icontains=q)[:MAX_ITEM_MATCHES])
        return Response([{'id': i.pk, 'code': i.sku, 'name': i.name, 'unit': i.unit_of_measure} for i in rows])


class MyProposals(_SupplierView):
    def get(self, request):
        rows = CataloguePriceProposal.objects.filter(supplier=request.vendor).select_related('item')
        return Response(ProposalSerializer(rows, many=True).data)

    def post(self, request):
        body = ProposalSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            proposal = service.propose(request.vendor, request.user, item=data['item'], unit_price=data['proposed_price'],
                                       specification=data.get('specification', ''))
        except service.ProposalError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ProposalSerializer(proposal).data, status=status.HTTP_201_CREATED)


class StaffProposalSerializer(ProposalSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)

    class Meta(ProposalSerializer.Meta):
        fields = [*ProposalSerializer.Meta.fields, 'supplier', 'supplier_name']
        read_only_fields = fields


class PriceProposalViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Prices suppliers have proposed. Accepting one binds the government to it, so it is an approver's act."""
    module_key = 'catalogue'
    queryset = CataloguePriceProposal.objects.select_related('item', 'supplier').all()
    serializer_class = StaffProposalSerializer
    filterset_fields = ['status', 'supplier', 'item']

    def get_permissions(self):
        if self.action in ('approve', 'reject'):
            return [IsAuthenticated(), ModuleEnabled(), RBACPermission(), IsApprover('post')]
        return [IsAuthenticated(), ModuleEnabled(), RBACPermission()]

    def _decide(self, request, *, approve: bool):
        proposal = self.get_object()
        try:
            service.decide(proposal, request.user, approve=approve, reason=str(request.data.get('reason', '')))
        except service.ProposalError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(proposal).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        return self._decide(request, approve=True)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        return self._decide(request, approve=False)
