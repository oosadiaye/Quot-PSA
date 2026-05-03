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
from rest_framework.permissions import IsAuthenticated

from contracts.filters import ApprovalStepFilter
from contracts.models import ContractApprovalStep, ContractDocument
from contracts.permissions import CanViewContracts
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
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["contract", "document_type"]

    def perform_create(self, serializer):
        serializer.save(
            uploaded_by=self.request.user,
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
