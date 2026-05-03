"""
Variation + Completion-certificate viewsets.

Variation approval tiers (LOCAL ≤15% / BOARD ≤25% / BPP_REQUIRED >25%)
are computed at the model layer; the view layer only exposes the
workflow transitions.
"""
from __future__ import annotations

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contracts.filters import CompletionCertificateFilter, VariationFilter
from contracts.models import CompletionCertificate, ContractVariation
from contracts.permissions import (
    CanApproveVariation,
    CanDraftVariation,
    CanIssueCompletion,
    CanReviewVariation,
    CanViewContracts,
)
from contracts.serializers import (
    CompletionCertificateSerializer,
    CompletionIssueSerializer,
    ContractVariationSerializer,
    VariationActionSerializer,
    VariationRejectSerializer,
)
from contracts.services import ContractClosureService, VariationService
from contracts.views._helpers import translate_service_errors


class ContractVariationViewSet(viewsets.ModelViewSet):
    queryset = (
        ContractVariation.objects
        .select_related("contract", "approved_by")
        .order_by("-created_at")
    )
    serializer_class = ContractVariationSerializer
    permission_classes = [CanViewContracts]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = VariationFilter
    ordering_fields = ["created_at", "amount", "variation_number"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [CanDraftVariation()]
        if self.action == "submit":
            return [CanDraftVariation()]
        if self.action == "review":
            return [CanReviewVariation()]
        if self.action in ("approve", "reject"):
            return [CanApproveVariation()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        variation = self.get_object()
        payload = VariationActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with translate_service_errors():
            variation = VariationService.submit(
                variation=variation, actor=request.user,
                notes=payload.validated_data.get("notes", ""),
            )
        return Response(ContractVariationSerializer(variation).data)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        variation = self.get_object()
        payload = VariationActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with translate_service_errors():
            variation = VariationService.review(
                variation=variation, actor=request.user,
                notes=payload.validated_data.get("notes", ""),
            )
        return Response(ContractVariationSerializer(variation).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        variation = self.get_object()
        payload = VariationActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with translate_service_errors():
            variation = VariationService.approve(
                variation=variation, actor=request.user,
                notes=payload.validated_data.get("notes", ""),
            )
        return Response(ContractVariationSerializer(variation).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        variation = self.get_object()
        payload = VariationRejectSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with translate_service_errors():
            variation = VariationService.reject(
                variation=variation, actor=request.user,
                reason=payload.validated_data["reason"],
            )
        return Response(ContractVariationSerializer(variation).data)


class CompletionCertificateViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        CompletionCertificate.objects
        .select_related("contract", "certified_by")
        .order_by("-issued_date", "-id")
    )
    serializer_class = CompletionCertificateSerializer
    permission_classes = [CanViewContracts]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CompletionCertificateFilter

    @action(detail=False, methods=["post"],
            url_path="issue-practical/(?P<contract_pk>[^/.]+)",
            permission_classes=[CanIssueCompletion])
    def issue_practical(self, request, contract_pk=None):
        from contracts.models import Contract
        contract = Contract.objects.get(pk=contract_pk)
        payload = CompletionIssueSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        with translate_service_errors():
            cert = ContractClosureService.issue_practical_completion(
                contract=contract,
                issued_date=data["issued_date"],
                effective_date=data["effective_date"],
                actor=request.user,
                notes=data.get("notes", ""),
            )
        return Response(CompletionCertificateSerializer(cert).data, status=201)

    @action(detail=False, methods=["post"],
            url_path="issue-final/(?P<contract_pk>[^/.]+)",
            permission_classes=[CanIssueCompletion])
    def issue_final(self, request, contract_pk=None):
        from contracts.models import Contract
        contract = Contract.objects.get(pk=contract_pk)
        payload = CompletionIssueSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        with translate_service_errors():
            cert = ContractClosureService.issue_final_completion(
                contract=contract,
                issued_date=data["issued_date"],
                effective_date=data["effective_date"],
                actor=request.user,
                notes=data.get("notes", ""),
            )
        return Response(CompletionCertificateSerializer(cert).data, status=201)

    @action(detail=False, methods=["post"],
            url_path="enter-defects-liability/(?P<contract_pk>[^/.]+)",
            permission_classes=[CanIssueCompletion])
    def enter_defects_liability(self, request, contract_pk=None):
        from contracts.models import Contract
        contract = Contract.objects.get(pk=contract_pk)
        payload = VariationActionSerializer(data=request.data)  # reuses notes-only shape
        payload.is_valid(raise_exception=True)
        with translate_service_errors():
            contract = ContractClosureService.enter_defects_liability(
                contract=contract,
                actor=request.user,
                notes=payload.validated_data.get("notes", ""),
            )
        from contracts.serializers import ContractSerializer
        return Response(ContractSerializer(contract).data)
