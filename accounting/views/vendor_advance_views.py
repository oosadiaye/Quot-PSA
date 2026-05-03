"""
Vendor Advance Special-GL viewsets.

Endpoints:
  GET  /api/v1/accounting/vendor-advances/
       List advances. Filter by ``vendor``, ``status``, ``source_type``.

  GET  /api/v1/accounting/vendor-advances/{id}/
       Single advance detail (with embedded clearance history).

  GET  /api/v1/accounting/vendor-advances/outstanding-for-vendor/?vendor=<id>
       Compact summary the popup uses to gate AP / PV / IPC posting.

  POST /api/v1/accounting/vendor-advances/{id}/clear/
       The "Clear Advance" action — body: { amount, posting_date,
       cleared_against_type, cleared_against_id, cleared_against_reference,
       notes }. Posts the contra journal and returns the updated row.
"""
from __future__ import annotations

from datetime import date as _date
from decimal import Decimal

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters as drf_filters, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounting.models import (
    VendorAdvance,
    VendorAdvanceClearance,
    VendorAdvanceStatus,
)
from accounting.services.vendor_advance import VendorAdvanceService


# ── Serializers ────────────────────────────────────────────────────────


class VendorAdvanceClearanceSerializer(serializers.ModelSerializer):
    journal_reference = serializers.CharField(
        source="clearing_journal.reference_number", read_only=True, default="",
    )

    class Meta:
        model = VendorAdvanceClearance
        fields = [
            "id", "amount", "posting_date",
            "cleared_against_type", "cleared_against_id",
            "cleared_against_reference", "notes",
            "clearing_journal", "journal_reference",
            "created_at",
        ]
        read_only_fields = fields


class VendorAdvanceSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.name", read_only=True, default="")
    vendor_code = serializers.CharField(source="vendor.code", read_only=True, default="")
    recon_account_code = serializers.CharField(
        source="recon_account.code", read_only=True, default="",
    )
    recon_account_name = serializers.CharField(
        source="recon_account.name", read_only=True, default="",
    )
    disbursement_journal_reference = serializers.CharField(
        source="disbursement_journal.reference_number",
        read_only=True, default="",
    )
    amount_outstanding = serializers.SerializerMethodField()
    clearances = VendorAdvanceClearanceSerializer(many=True, read_only=True)

    class Meta:
        model = VendorAdvance
        fields = [
            "id",
            "vendor", "vendor_name", "vendor_code",
            "recon_account", "recon_account_code", "recon_account_name",
            "source_type", "source_id", "reference",
            "amount_paid", "amount_recovered", "amount_outstanding",
            "status",
            "posting_date",
            "disbursement_journal", "disbursement_journal_reference",
            "notes",
            "clearances",
            "created_at", "updated_at",
        ]
        read_only_fields = fields  # all writes go through the service

    def get_amount_outstanding(self, obj: VendorAdvance) -> str:
        return str(obj.amount_outstanding)


class ClearAdvanceSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, min_value=Decimal("0.01"))
    posting_date = serializers.DateField(required=False)
    cleared_against_type = serializers.CharField(required=False, allow_blank=True, default="")
    cleared_against_id = serializers.IntegerField(required=False, allow_null=True)
    cleared_against_reference = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


# ── ViewSet ────────────────────────────────────────────────────────────


class VendorAdvanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only collection + state-transition actions.

    Disbursement is never POSTed to the collection — that comes from
    the originating flow (mobilisation, PO down-payment, AP advance).
    Clearance is the only mutating action and is exposed as a
    detail-level @action.
    """

    queryset = (
        VendorAdvance.objects
        .select_related("vendor", "recon_account", "disbursement_journal")
        .prefetch_related("clearances")
        .order_by("-posting_date", "-created_at")
    )
    serializer_class = VendorAdvanceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter]
    filterset_fields = ["vendor", "status", "source_type"]
    search_fields = ["reference", "vendor__name", "vendor__code"]

    @action(detail=False, methods=["get"], url_path="outstanding-for-vendor")
    def outstanding_for_vendor(self, request):
        """Compact summary the frontend popup uses.

        Returns:
            {
              "vendor_id": <int>,
              "outstanding_total": "<NGN>",
              "open_advances": [ <serialized advance>, ... ]
            }

        ``open_advances`` covers OUTSTANDING + PARTIAL — the rows the
        operator should be aware of. CLEARED rows are intentionally
        excluded; viewing those is via the standard list endpoint.
        """
        vendor_id = request.query_params.get("vendor")
        if not vendor_id:
            return Response(
                {"error": "vendor query param is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            vendor_id_int = int(vendor_id)
        except (TypeError, ValueError):
            return Response(
                {"error": "vendor must be an integer FK id."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from procurement.models import Vendor
        try:
            vendor = Vendor.objects.get(pk=vendor_id_int)
        except Vendor.DoesNotExist:
            return Response(
                {"error": f"Vendor id={vendor_id_int} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        outstanding = VendorAdvanceService.outstanding_for_vendor(vendor)
        open_rows = VendorAdvanceService.list_outstanding(vendor)
        ser = self.get_serializer(open_rows, many=True)
        return Response({
            "vendor_id": vendor.pk,
            "vendor_name": vendor.name,
            "outstanding_total": str(outstanding),
            "open_advances": ser.data,
        })

    @action(detail=True, methods=["post"])
    def clear(self, request, pk=None):
        """Clear (recover) some or all of the outstanding advance.

        Body schema: ``ClearAdvanceSerializer``. Posts the contra
        journal (DR Real-AP / CR Vendor-Advance) and returns the
        updated advance row with its new clearance history.
        """
        advance = self.get_object()
        if advance.status == VendorAdvanceStatus.CLEARED:
            return Response(
                {"error": "This advance is already fully cleared."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = ClearAdvanceSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        try:
            VendorAdvanceService.clear(
                advance=advance,
                amount=data["amount"],
                posting_date=data.get("posting_date") or _date.today(),
                actor=request.user,
                cleared_against_type=data.get("cleared_against_type", ""),
                cleared_against_id=data.get("cleared_against_id"),
                cleared_against_reference=data.get("cleared_against_reference", ""),
                notes=data.get("notes", ""),
            )
        except Exception as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        advance.refresh_from_db()
        return Response(self.get_serializer(advance).data)
