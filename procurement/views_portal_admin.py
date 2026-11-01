"""The procurement office's side of the supplier portal: switch it on, invite and suspend suppliers, decide bank changes."""
from __future__ import annotations

from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsApprover, ModuleEnabled, RBACPermission
from procurement.models import SupplierPortalSettings, Vendor, VendorBankChangeRequest
from procurement.services import supplier_portal as portal


class SupplierPortalSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierPortalSettings
        fields = ['id', 'enabled', 'auto_activate_on_payment']


class PortalSettingsViewSet(viewsets.GenericViewSet):
    """Whether the supplier portal is on, and whether suppliers are let in on paying registration. One set per government."""
    module_key = 'procurement'
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    queryset = SupplierPortalSettings.objects.all()
    serializer_class = SupplierPortalSettingsSerializer

    @action(detail=False, methods=['get', 'patch'], url_path='current')
    def current(self, request):
        cfg = portal.portal_settings()
        if request.method == 'PATCH':
            serializer = self.get_serializer(cfg, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(self.get_serializer(cfg).data)


class StaffBankChangeSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    vendor_code = serializers.CharField(source='vendor.code', read_only=True)
    current_bank_name = serializers.CharField(source='vendor.bank_name', read_only=True)

    class Meta:
        model = VendorBankChangeRequest
        fields = ['id', 'vendor', 'vendor_name', 'vendor_code', 'current_bank_name', 'bank_name', 'bank_account_number',
                  'bank_sort_code', 'status', 'reason', 'created_at', 'decided_at']
        read_only_fields = fields


class BankChangeRequestViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Supplier requests to change their bank details. Approving one changes where the supplier is paid, so it is an
    approver's act."""
    module_key = 'procurement'
    queryset = VendorBankChangeRequest.objects.select_related('vendor').all()
    serializer_class = StaffBankChangeSerializer
    filterset_fields = ['status', 'vendor']

    def get_permissions(self):
        if self.action in ('approve', 'reject'):
            return [IsAuthenticated(), ModuleEnabled(), RBACPermission(), IsApprover('post')]
        return [IsAuthenticated(), ModuleEnabled(), RBACPermission()]

    def _decide(self, request, *, approve: bool):
        change = self.get_object()
        try:
            portal.decide_bank_change(change, request.user, approve=approve, reason=str(request.data.get('reason', '')))
        except portal.PortalError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(change).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        return self._decide(request, approve=True)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        return self._decide(request, approve=False)


def vendor_portal_actions(viewset_cls):
    """Add invite / activate / suspend to the vendor viewset without growing views.py."""

    def make(name, url_path, fn):
        def handler(self, request, pk=None):
            vendor: Vendor = self.get_object()
            try:
                fn(vendor, request)
            except portal.PortalError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            vendor.refresh_from_db()
            return Response({'portal_status': vendor.portal_status})
        handler.__name__ = name                       # DRF requires an action's function name to match its attribute
        setattr(viewset_cls, name, action(detail=True, methods=['post'], url_path=url_path)(handler))

    make('portal_invite', 'portal-invite', lambda v, r: portal.invite(v, email=r.data.get('email')))
    make('portal_activate', 'portal-activate', lambda v, r: portal.activate(v))
    make('portal_suspend', 'portal-suspend', lambda v, r: portal.suspend(v))
    return viewset_cls
