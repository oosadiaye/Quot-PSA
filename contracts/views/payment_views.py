"""
Payment-path viewsets.

* IPCViewSet             — Interim Payment Certificates (6-step workflow)
* MeasurementBookViewSet — on-site measurement records (prerequisite for IPCs)
* MobilizationPaymentViewSet — advance payments
* RetentionReleaseViewSet   — held-amount releases at completion

All state-changing @action methods delegate to the relevant service
layer; any structural-control violation bubbles as a 400/409 with a
machine-readable ``code``.
"""
from __future__ import annotations

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contracts.filters import (
    IPCFilter,
    MeasurementBookFilter,
    MobilizationPaymentFilter,
    RetentionReleaseFilter,
)
from contracts.models import (
    Contract,
    InterimPaymentCertificate,
    MeasurementBook,
    MobilizationPayment,
    RetentionRelease,
)
from contracts.permissions import (
    CanApproveIPC,
    CanApproveRetention,
    CanCertifyIPC,
    CanDraftIPC,
    CanMarkIPCPaid,
    CanPayRetention,
    CanRaiseVoucher,
    CanViewContracts,
)
from contracts.serializers import (
    IPCActionSerializer,
    IPCMarkPaidSerializer,
    IPCRaiseVoucherSerializer,
    IPCRejectSerializer,
    IPCSerializer,
    IPCSubmitSerializer,
    MeasurementBookSerializer,
    MobilizationMarkPaidSerializer,
    MobilizationPaymentSerializer,
    RetentionActionSerializer,
    RetentionCreateSerializer,
    RetentionMarkPaidSerializer,
    RetentionReleaseSerializer,
)
from contracts.services import (
    IPCService,
    MobilizationService,
    RetentionService,
)
from contracts.views._helpers import translate_service_errors


# ── Measurement Books ──────────────────────────────────────────────────

class MeasurementBookViewSet(viewsets.ModelViewSet):
    queryset = MeasurementBook.objects.select_related("contract").order_by(
        "-measurement_date", "-id",
    )
    serializer_class = MeasurementBookSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = MeasurementBookFilter
    ordering_fields = ["measurement_date", "created_at"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


# ── Interim Payment Certificates ──────────────────────────────────────

class IPCViewSet(viewsets.ReadOnlyModelViewSet):
    """IPCs are never created via POST to the collection endpoint;
    they are always born through ``/ipcs/submit/`` which runs the full
    ceiling + monotonicity + fiscal-year guard set.
    """

    queryset = (
        InterimPaymentCertificate.objects
        .select_related("contract", "measurement_book", "certifying_engineer")
        .order_by("-created_at")
    )
    serializer_class = IPCSerializer
    permission_classes = [CanViewContracts]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = IPCFilter
    ordering_fields = ["created_at", "posting_date", "this_certificate_gross"]

    # ── Create (DRAFT → SUBMITTED in a single step) ───────────────────

    @action(detail=False, methods=["post"], permission_classes=[CanDraftIPC])
    def submit(self, request):
        payload = IPCSubmitSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        with translate_service_errors():
            ipc = IPCService.submit_ipc(
                contract=data["contract"],
                posting_date=data["posting_date"],
                cumulative_work_done_to_date=data["cumulative_work_done_to_date"],
                measurement_book=data.get("measurement_book"),
                variation_claims=data.get("variation_claims", 0),
                ld_deduction=data.get("ld_deduction", 0),
                actor=request.user,
                notes=data.get("notes", ""),
            )
        return Response(IPCSerializer(ipc).data, status=201)

    # ── State transitions ─────────────────────────────────────────────

    @action(detail=True, methods=["post"], permission_classes=[CanCertifyIPC])
    def certify(self, request, pk=None):
        ipc = self.get_object()
        payload = IPCActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with translate_service_errors():
            ipc = IPCService.certify(
                ipc=ipc, actor=request.user,
                notes=payload.validated_data.get("notes", ""),
            )
        return Response(IPCSerializer(ipc).data)

    @action(detail=True, methods=["post"], permission_classes=[CanApproveIPC])
    def approve(self, request, pk=None):
        ipc = self.get_object()
        payload = IPCActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with translate_service_errors():
            ipc = IPCService.approve(
                ipc=ipc, actor=request.user,
                notes=payload.validated_data.get("notes", ""),
            )
        return Response(IPCSerializer(ipc).data)

    @action(detail=True, methods=["post"], url_path="create-draft-voucher",
            permission_classes=[CanRaiseVoucher])
    def create_draft_voucher(self, request, pk=None):
        """Auto-create a draft PaymentVoucherGov pre-populated from this
        IPC + contract + vendor, link it, and transition the IPC to
        VOUCHER_RAISED. Idempotent — re-calling returns the existing PV.

        Returns: ``{ipc: <IPC>, payment_voucher: {id, voucher_number, status}}``
        so the frontend can navigate straight to the new PV for review.
        """
        ipc = self.get_object()
        with translate_service_errors():
            pv = IPCService.create_draft_voucher(
                ipc=ipc, actor=request.user,
                notes=request.data.get("notes", ""),
            )
        ipc.refresh_from_db()
        return Response({
            "ipc": IPCSerializer(ipc).data,
            "payment_voucher": {
                "id": pv.pk,
                "voucher_number": pv.voucher_number,
                "status": pv.status,
                "gross_amount": str(pv.gross_amount),
                "net_amount": str(pv.net_amount),
            },
        })

    @action(detail=True, methods=["post"], url_path="raise-voucher",
            permission_classes=[CanRaiseVoucher])
    def raise_voucher(self, request, pk=None):
        ipc = self.get_object()
        payload = IPCRaiseVoucherSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        with translate_service_errors():
            ipc = IPCService.raise_voucher(
                ipc=ipc,
                payment_voucher_id=data["payment_voucher_id"],
                voucher_gross=data["voucher_gross"],
                actor=request.user,
                notes=data.get("notes", ""),
            )
        return Response(IPCSerializer(ipc).data)

    @action(detail=True, methods=["post"], url_path="mark-paid",
            permission_classes=[CanMarkIPCPaid])
    def mark_paid(self, request, pk=None):
        """Deprecated direct path. Marking an IPC paid now happens
        automatically when the linked Payment Voucher's outgoing
        Payment is posted in Treasury — that's the canonical
        cash-control event. Posting the cash there cascades to:

          1. Flip the PV → PAID
          2. Mark the source VendorInvoice → Paid
          3. Call ``IPCService.mark_paid`` to flip every linked IPC

        This API endpoint is preserved as a fallback for ops that
        need to recover from a cascade failure (the cascade catches
        and logs IPC-side errors so cash movement isn't blocked, but
        leaves the IPC in VOUCHER_RAISED). When invoked, it still
        runs through ``IPCService.mark_paid`` — same SoD checks, same
        ContractBalance updates, same audit trail.
        """
        ipc = self.get_object()
        payload = IPCMarkPaidSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        with translate_service_errors():
            ipc = IPCService.mark_paid(
                ipc=ipc,
                payment_date=data["payment_date"],
                vat_amount=data["vat_amount"],
                wht_amount=data["wht_amount"],
                actor=request.user,
                notes=data.get("notes", ""),
            )
        return Response(IPCSerializer(ipc).data)

    @action(detail=True, methods=["post"], permission_classes=[CanCertifyIPC])
    def reject(self, request, pk=None):
        ipc = self.get_object()
        # Lock against rejection once a Payment Voucher has been
        # raised against this IPC — except when that PV has been
        # cancelled / reversed, in which case the IPC is unlocked
        # again and a fresh attempt is legitimate.
        if ipc.payment_voucher_id:
            pv = ipc.payment_voucher
            if pv.status not in ('CANCELLED', 'REVERSED'):
                return Response(
                    {
                        'error': (
                            f'Cannot reject this IPC: a Payment Voucher '
                            f'({pv.voucher_number}, status {pv.status}) '
                            f'has been raised against it. Cancel or '
                            f'reverse the PV first.'
                        ),
                        'pv_link_locked': True,
                        'payment_voucher_number': pv.voucher_number,
                        'payment_voucher_status': pv.status,
                    },
                    status=400,
                )

        payload = IPCRejectSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with translate_service_errors():
            ipc = IPCService.reject(
                ipc=ipc, actor=request.user,
                reason=payload.validated_data["reason"],
            )
        return Response(IPCSerializer(ipc).data)

    # ── WHT determination override (parity with Invoice Verification) ─
    @action(
        detail=True, methods=["post"], url_path="set-wht-exemption",
        permission_classes=[CanCertifyIPC],
    )
    def set_wht_exemption(self, request, pk=None):
        """Toggle the per-IPC withholding-tax exemption flag.

        Body:
            wht_exempt   bool — True exempts this IPC from WHT at
                                payment time, overriding the vendor
                                master default. False clears the
                                override (vendor master applies).

        Refuses to mutate IPCs in terminal states (PAID, REJECTED).
        """
        ipc = self.get_object()
        if ipc.status in ("PAID", "REJECTED"):
            return Response(
                {"error": f"Cannot adjust WHT on a {ipc.status} IPC."},
                status=400,
            )
        raw = request.data.get("wht_exempt")
        if raw is None:
            return Response(
                {"error": "wht_exempt (bool) is required."},
                status=400,
            )
        ipc.wht_exempt = bool(raw)
        ipc.updated_by = request.user
        ipc.save(update_fields=["wht_exempt", "updated_by", "updated_at"])
        return Response(IPCSerializer(ipc).data)


# ── Mobilization payments ─────────────────────────────────────────────

class MobilizationPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MobilizationPayment.objects.select_related("contract").order_by(
        "-created_at",
    )
    serializer_class = MobilizationPaymentSerializer
    permission_classes = [CanViewContracts]
    filter_backends = [DjangoFilterBackend]
    filterset_class = MobilizationPaymentFilter

    @action(
        detail=False, methods=["post"],
        url_path="issue/(?P<contract_pk>[^/.]+)",
        # Mobilization issuance is itself a budget-affecting commitment
        # (it reserves the advance against the appropriation), so we
        # require the same permission tier as drafting an IPC. Tenant
        # admins always pass via ``_BaseContractsPermission``.
        permission_classes=[CanDraftIPC],
    )
    def issue(self, request, contract_pk=None):
        try:
            contract = Contract.objects.get(pk=contract_pk)
        except Contract.DoesNotExist:
            return Response(
                {"error": f"Contract id={contract_pk} not found."},
                status=404,
            )
        with translate_service_errors():
            payment = MobilizationService.issue_advance(
                contract=contract, actor=request.user,
            )
        return Response(MobilizationPaymentSerializer(payment).data, status=201)

    @action(detail=True, methods=["post"], url_path="mark-paid",
            permission_classes=[CanMarkIPCPaid])
    def mark_paid(self, request, pk=None):
        payment = self.get_object()
        payload = MobilizationMarkPaidSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        with translate_service_errors():
            payment = MobilizationService.mark_paid(
                payment=payment,
                payment_voucher_id=data["payment_voucher_id"],
                payment_date=data["payment_date"],
                actor=request.user,
            )
        return Response(MobilizationPaymentSerializer(payment).data)


# ── Retention releases ────────────────────────────────────────────────

class RetentionReleaseViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RetentionRelease.objects.select_related("contract").order_by(
        "-created_at",
    )
    serializer_class = RetentionReleaseSerializer
    permission_classes = [CanViewContracts]
    filter_backends = [DjangoFilterBackend]
    filterset_class = RetentionReleaseFilter

    @action(detail=False, methods=["post"], url_path="create-release")
    def create_release(self, request):
        payload = RetentionCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with translate_service_errors():
            release = RetentionService.create_release(
                contract=payload.validated_data["contract"],
                release_type=payload.validated_data["release_type"],
                actor=request.user,
            )
        return Response(RetentionReleaseSerializer(release).data, status=201)

    @action(detail=True, methods=["post"], permission_classes=[CanApproveRetention])
    def approve(self, request, pk=None):
        release = self.get_object()
        payload = RetentionActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with translate_service_errors():
            release = RetentionService.approve(
                release=release, actor=request.user,
                notes=payload.validated_data.get("notes", ""),
            )
        return Response(RetentionReleaseSerializer(release).data)

    @action(detail=True, methods=["post"], url_path="mark-paid",
            permission_classes=[CanPayRetention])
    def mark_paid(self, request, pk=None):
        release = self.get_object()
        payload = RetentionMarkPaidSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        with translate_service_errors():
            release = RetentionService.mark_paid(
                release=release,
                payment_voucher_id=data["payment_voucher_id"],
                payment_date=data["payment_date"],
                actor=request.user,
            )
        return Response(RetentionReleaseSerializer(release).data)
