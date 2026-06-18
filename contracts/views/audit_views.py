"""
Audit-trail viewsets.

* ContractApprovalStepViewSet — immutable, read-only log of every
  SoD-relevant action (submit/certify/approve/reject/pay/close).
* ContractDocumentViewSet — uploaded attachments (PDF scans of PV, MB,
  BPP no-objection, etc.).
"""
from __future__ import annotations

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.permissions import SAFE_METHODS

from contracts.filters import ApprovalStepFilter
from contracts.models import ContractApprovalStep, ContractDocument
from contracts.permissions import CanManageContracts, CanViewContracts
from contracts.serializers import (
    ContractApprovalStepSerializer,
    ContractDocumentSerializer,
)


class ContractApprovalStepViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only audit trail. Rows are ONLY written by the service
    layer — no POST endpoint is exposed on purpose."""

    queryset = (
        ContractApprovalStep.objects
        .select_related("action_by", "assigned_to", "contract")
        .order_by("-action_at", "-id")
    )
    serializer_class = ContractApprovalStepSerializer
    permission_classes = [CanViewContracts]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = ApprovalStepFilter
    ordering_fields = ["action_at", "step_number"]


class ContractDocumentViewSet(viewsets.ModelViewSet):
    queryset = ContractDocument.objects.select_related(
        "contract", "uploaded_by",
    ).order_by("-created_at")
    serializer_class = ContractDocumentSerializer
    # Was: ``IsAuthenticated`` only. Any authenticated user in the
    # tenant could attach a forged PDF (signed BPP no-objection,
    # contractor's bank-letter) to any contract — a real audit-trail
    # risk because operators often trust attached docs at face value
    # when approving IPCs. Reads require ``view_contract``; writes
    # require ``add_contract``/``change_contract`` so only users
    # authorised on the underlying contract can attach docs.
    #
    # Previously ``permission_classes = [CanViewContracts, CanManageContracts]``
    # evaluated as logical AND on every request, blocking legitimate
    # read-only users who lack manage permission. ``get_permissions``
    # now picks the right gate per HTTP method.
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["contract", "document_type"]

    def get_permissions(self):
        if self.request and self.request.method in SAFE_METHODS:
            return [CanViewContracts()]
        return [CanManageContracts()]

    def perform_create(self, serializer):
        serializer.save(
            uploaded_by=self.request.user,
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
