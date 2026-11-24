"""The supplier-facing API, mounted at ``/api/v1/supplier-portal/``.

Every view answers for exactly one supplier: the one the signed-in user is linked to. Nothing here uses the staff
permission classes, and every query starts from that supplier, so another supplier's record is simply not found (404),
not forbidden. Purchase orders are visible once they have been approved: a draft is internal.
"""
from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from procurement.models import PurchaseOrder, PurchaseOrderAcknowledgement, VendorBankChangeRequest
from procurement.services import supplier_portal as portal
from procurement.validators import validate_nuban

#: What a supplier may see of an order: not drafts, and not orders still waiting on internal approval.
VISIBLE_PO_STATUSES = ('Approved', 'Posted', 'Closed')
#: What a supplier may change about itself directly; anything touching money goes through a request.
EDITABLE_PROFILE_FIELDS = ('email', 'phone', 'address')


class IsSupplier(BasePermission):
    """A signed-in user who speaks for an active supplier, while the portal is on."""
    message = 'You do not have access to the supplier portal.'

    def has_permission(self, request, view):
        request.vendor = portal.supplier_for(request.user)
        return request.vendor is not None


def _mask(number: str) -> str:
    return f'••••••{number[-4:]}' if number else ''


class BankChangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorBankChangeRequest
        fields = ['id', 'bank_name', 'bank_account_number', 'bank_sort_code', 'status', 'reason', 'created_at', 'decided_at']
        read_only_fields = ['status', 'reason', 'created_at', 'decided_at']

    def validate_bank_account_number(self, value):
        validate_nuban(value)
        return value


def _profile(vendor) -> dict:
    pending = vendor.bank_change_requests.filter(status='pending').first()
    return {
        'name': vendor.name, 'code': vendor.code, 'tax_id': vendor.tax_id, 'email': vendor.email, 'phone': vendor.phone,
        'address': vendor.address, 'registration_number': vendor.registration_number, 'registration_status': vendor.registration_status,
        'expiry_date': vendor.expiry_date, 'bank_name': vendor.bank_name, 'bank_account_masked': _mask(vendor.bank_account_number),
        'bank_sort_code': vendor.bank_sort_code,
        'pending_bank_change': BankChangeSerializer(pending).data if pending else None,
    }


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsSupplier])
def my_profile(request):
    vendor = request.vendor
    if request.method == 'PATCH':
        extra = set(request.data) - set(EDITABLE_PROFILE_FIELDS)
        if extra:
            return Response({'error': f'You cannot change {", ".join(sorted(extra))} here. Bank details go through a change request.'},
                            status=status.HTTP_400_BAD_REQUEST)
        for name in EDITABLE_PROFILE_FIELDS:
            if name in request.data:
                setattr(vendor, name, str(request.data[name]).strip())
        vendor.save(update_fields=[*(n for n in EDITABLE_PROFILE_FIELDS if n in request.data), 'updated_at'])
    return Response(_profile(vendor))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSupplier])
def my_bank_changes(request):
    if request.method == 'GET':
        return Response(BankChangeSerializer(request.vendor.bank_change_requests.all(), many=True).data)
    body = BankChangeSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    try:
        change = portal.request_bank_change(request.vendor, request.user, **body.validated_data)
    except portal.PortalError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(BankChangeSerializer(change).data, status=status.HTTP_201_CREATED)


def _order_summary(po) -> dict:
    ack = getattr(po, 'acknowledgement', None)
    return {
        'id': po.pk, 'po_number': po.po_number, 'order_date': po.order_date, 'expected_delivery_date': po.expected_delivery_date,
        'status': po.status, 'total_amount': po.total_amount, 'acknowledged_at': ack.acknowledged_at if ack else None,
    }


def _my_orders(vendor):
    return (PurchaseOrder.objects.filter(vendor=vendor, status__in=VISIBLE_PO_STATUSES)
            .select_related('acknowledgement').prefetch_related('lines').order_by('-order_date', '-pk'))


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSupplier])
def my_orders(request):
    return Response([_order_summary(po) for po in _my_orders(request.vendor)])


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSupplier])
def my_order(request, pk):
    po = _my_orders(request.vendor).filter(pk=pk).first()
    if po is None:
        return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    lines = [{'description': l.item_description, 'quantity': l.quantity, 'quantity_received': l.quantity_received,
              'unit_price': l.unit_price, 'total_price': l.total_price} for l in po.lines.all()]
    return Response({**_order_summary(po), 'delivery_address': po.delivery_address, 'payment_terms': po.payment_terms,
                     'terms_and_conditions': po.terms_and_conditions, 'lines': lines})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSupplier])
def acknowledge_order(request, pk):
    po = _my_orders(request.vendor).filter(pk=pk).first()
    if po is None:
        return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if po.status == 'Closed':
        return Response({'error': 'This order is closed.'}, status=status.HTTP_400_BAD_REQUEST)
    _, created = PurchaseOrderAcknowledgement.objects.get_or_create(
        purchase_order=po, defaults={'acknowledged_by': request.user, 'note': str(request.data.get('note', ''))[:300]})
    po = _my_orders(request.vendor).get(pk=pk)
    return Response(_order_summary(po), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSupplier])
def my_invoices(request):
    from accounting.models import VendorInvoice

    rows = VendorInvoice.objects.filter(vendor=request.vendor).exclude(status='Draft').order_by('-invoice_date', '-pk')
    return Response([{'id': i.pk, 'invoice_number': i.invoice_number, 'invoice_date': i.invoice_date, 'due_date': i.due_date,
                      'total_amount': i.total_amount, 'paid_amount': i.paid_amount, 'status': i.status} for i in rows])


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSupplier])
def my_payments(request):
    from accounting.models import Payment

    rows = Payment.objects.filter(vendor=request.vendor, status='Posted').order_by('-payment_date', '-pk')
    return Response([{'id': p.pk, 'payment_number': p.payment_number, 'payment_date': p.payment_date,
                      'total_amount': p.total_amount, 'status': p.status} for p in rows])
