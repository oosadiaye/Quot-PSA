"""
Contract + Milestone + Balance viewsets.

Write paths delegate to the service layer — the viewset validates
input, calls a classmethod, and returns the updated resource. No
business logic lives here.
"""
from __future__ import annotations

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contracts.filters import ContractFilter
from contracts.models import (
    Contract,
    ContractApprovalStep,
    ContractBalance,
    MilestoneSchedule,
)
from contracts.permissions import (
    CanActivateContract,
    CanApproveMilestone,
    CanCloseContract,
    CanManageContracts,
    CanViewContracts,
)
from contracts.serializers import (
    ActivateContractSerializer,
    CloseContractSerializer,
    ContractApprovalStepSerializer,
    ContractBalanceSerializer,
    ContractSerializer,
    MilestoneScheduleSerializer,
)
from contracts.services import (
    ContractActivationService,
    ContractClosureService,
)
from contracts.views._helpers import translate_service_errors


class ContractViewSet(viewsets.ModelViewSet):
    """CRUD for Contract headers + state-transition actions."""

    queryset = (
        Contract.objects
        .select_related("vendor", "mda", "fiscal_year", "ncoa_code")
        .prefetch_related("milestones")
        .order_by("-created_at")
    )
    serializer_class = ContractSerializer
    permission_classes = [CanViewContracts]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ContractFilter
    search_fields = ["contract_number", "title", "reference"]
    ordering_fields = ["created_at", "signed_date", "original_sum"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [CanManageContracts()]
        if self.action == "activate":
            return [CanActivateContract()]
        if self.action == "close":
            return [CanCloseContract()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    # ── State transitions ─────────────────────────────────────────────

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        contract = self.get_object()
        payload = ActivateContractSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with translate_service_errors():
            contract = ContractActivationService.activate(
                contract=contract,
                actor=request.user,
                notes=payload.validated_data.get("notes", ""),
            )
        return Response(ContractSerializer(contract).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        contract = self.get_object()
        payload = CloseContractSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with translate_service_errors():
            contract = ContractClosureService.close(
                contract=contract,
                actor=request.user,
                notes=payload.validated_data.get("notes", ""),
            )
        return Response(ContractSerializer(contract).data)

    # ── Read-only projections ─────────────────────────────────────────

    @action(detail=True, methods=["get"])
    def balance(self, request, pk=None):
        contract = self.get_object()
        try:
            balance = contract.balance
        except ContractBalance.DoesNotExist:
            return Response(
                {"code": "BALANCE_NOT_INITIALIZED",
                 "message": "ContractBalance row not yet created."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(ContractBalanceSerializer(balance).data)

    @action(detail=True, methods=["get"], url_path="approval-steps")
    def approval_steps(self, request, pk=None):
        contract = self.get_object()
        steps = (
            ContractApprovalStep.objects
            .filter(contract=contract)
            .select_related("action_by", "assigned_to")
            .order_by("-action_at", "-id")
        )
        page = self.paginate_queryset(steps)
        serializer = ContractApprovalStepSerializer(page or steps, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class MilestoneScheduleViewSet(viewsets.ModelViewSet):
    """Milestone rows — creatable only before activation."""

    queryset = MilestoneSchedule.objects.select_related("contract").order_by(
        "contract_id", "milestone_number",
    )
    serializer_class = MilestoneScheduleSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["contract", "status"]
    ordering_fields = ["milestone_number", "target_date"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    # ── Milestone approval / state transitions ────────────────────────
    # Three actions covering the full lifecycle:
    #   start      — PENDING → IN_PROGRESS  (work has begun on site)
    #   approve    — anything → COMPLETED   (engineer certifies done)
    #   reopen     — COMPLETED → IN_PROGRESS (defect found post-cert)
    # ``approve`` is the most common — it's the "approve milestone"
    # action the user asked for. Once COMPLETED, an IPC may be raised
    # against this milestone for payment.

    def get_permissions(self):
        # Custom transition actions need the certification permission.
        # Tenant admins and superusers always pass via ``_BaseContractsPermission``.
        if self.action in {"approve", "start", "reopen"}:
            return [CanApproveMilestone()]
        if self.action == "convert_to_ipc":
            # Conversion creates an IPC — same permission tier as
            # drafting an IPC. ``CanDraftIPC`` accepts tenant admins
            # and users with ``contracts.add_interimpaymentcertificate``.
            from contracts.permissions import CanDraftIPC
            return [CanDraftIPC()]
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Transition PENDING → IN_PROGRESS. Idempotent for IN_PROGRESS."""
        milestone = self.get_object()
        if milestone.status == "COMPLETED":
            return Response(
                {"error": "Milestone is already COMPLETED — use reopen first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        milestone.status = "IN_PROGRESS"
        milestone.updated_by = request.user
        milestone.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(MilestoneScheduleSerializer(milestone).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approve / certify a milestone — sets status COMPLETED.

        Body (all optional):
            actual_completion_date  YYYY-MM-DD; defaults to today
            notes                   free-text approval narrative

        Permission: ``CanApproveMilestone`` — tenant admins always
        pass; otherwise the user needs ``contracts.certify_milestone``
        or ``contracts.certify_ipc``.
        """
        from datetime import date as _date

        milestone = self.get_object()
        if milestone.status == "COMPLETED":
            return Response(
                {
                    "error": "Milestone is already COMPLETED.",
                    "actual_completion_date": milestone.actual_completion_date,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        completion_raw = request.data.get("actual_completion_date")
        if completion_raw:
            from datetime import datetime as _dt
            try:
                completion_date = _dt.strptime(completion_raw, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"error": "actual_completion_date must be YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            completion_date = _date.today()

        notes_addendum = (request.data.get("notes") or "").strip()
        if notes_addendum:
            existing = (milestone.notes or "").strip()
            stamp = (
                f"\n[Approved by {request.user.get_username()} "
                f"on {completion_date.isoformat()}] {notes_addendum}"
            )
            milestone.notes = (existing + stamp).strip()

        milestone.status = "COMPLETED"
        milestone.actual_completion_date = completion_date
        milestone.updated_by = request.user
        milestone.save(update_fields=[
            "status", "actual_completion_date", "notes",
            "updated_by", "updated_at",
        ])
        return Response(MilestoneScheduleSerializer(milestone).data)

    @action(detail=True, methods=["post"], url_path="convert-to-ipc")
    def convert_to_ipc(self, request, pk=None):
        """Convert an approved (COMPLETED) milestone into an IPC.

        Body (all optional):
            posting_date  YYYY-MM-DD; defaults to today
            notes         optional narrative attached to the IPC

        The IPC is created in SUBMITTED status (per the existing IPC
        lifecycle) and inherits tax_code / withholding_tax / wht_exempt
        from the contract's vendor master so downstream PV creation
        applies the correct deductions automatically. The contract
        ceiling is enforced strictly via ``IPCService.submit_ipc``.

        Returns the created IPC's serialised representation. The
        frontend redirects the user to the IPC detail page so they can
        progress it through certification/approval/voucher.
        """
        from contracts.services.ipc_service import IPCService
        from contracts.serializers import IPCSerializer
        from contracts.views._helpers import translate_service_errors

        milestone = self.get_object()
        posting_date_raw = request.data.get("posting_date")
        posting_date = None
        if posting_date_raw:
            from datetime import datetime as _dt
            try:
                posting_date = _dt.strptime(posting_date_raw, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"error": "posting_date must be YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        with translate_service_errors():
            ipc = IPCService.create_from_milestone(
                milestone=milestone,
                actor=request.user,
                posting_date=posting_date,
                notes=(request.data.get("notes") or "").strip(),
            )
        return Response(IPCSerializer(ipc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        """COMPLETED → IN_PROGRESS — when a defect is found after cert.

        Clears actual_completion_date so re-certification produces a
        fresh dated record. Notes carry an audit stamp of who reopened.
        """
        milestone = self.get_object()
        if milestone.status != "COMPLETED":
            return Response(
                {"error": "Only COMPLETED milestones can be reopened."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from datetime import date as _date
        reason = (request.data.get("reason") or "").strip() or "no reason given"
        existing = (milestone.notes or "").strip()
        stamp = (
            f"\n[Reopened by {request.user.get_username()} "
            f"on {_date.today().isoformat()}] {reason}"
        )
        milestone.notes = (existing + stamp).strip()
        milestone.status = "IN_PROGRESS"
        milestone.actual_completion_date = None
        milestone.updated_by = request.user
        milestone.save(update_fields=[
            "status", "actual_completion_date", "notes",
            "updated_by", "updated_at",
        ])
        return Response(MilestoneScheduleSerializer(milestone).data)


class ContractBalanceViewSet(mixins.ListModelMixin,
                             mixins.RetrieveModelMixin,
                             viewsets.GenericViewSet):
    """Read-only financial snapshot per contract."""

    queryset = ContractBalance.objects.select_related("contract").order_by("-updated_at")
    serializer_class = ContractBalanceSerializer
    permission_classes = [CanViewContracts]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["contract"]
