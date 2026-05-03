"""
Contracts module — DRF router registration.

All routes are namespaced under ``contracts:`` and mounted at
``/api/contracts/...`` by the project URL conf.
"""
from __future__ import annotations

from rest_framework.routers import DefaultRouter

from contracts.views import (
    CompletionCertificateViewSet,
    ContractApprovalStepViewSet,
    ContractBalanceViewSet,
    ContractDocumentViewSet,
    ContractVariationViewSet,
    ContractViewSet,
    IPCViewSet,
    MeasurementBookViewSet,
    MilestoneScheduleViewSet,
    MobilizationPaymentViewSet,
    RetentionReleaseViewSet,
)

app_name = "contracts"

router = DefaultRouter()
router.register(r"contracts",               ContractViewSet,              basename="contract")
router.register(r"milestones",              MilestoneScheduleViewSet,     basename="milestone")
router.register(r"balances",                ContractBalanceViewSet,       basename="balance")
router.register(r"measurement-books",       MeasurementBookViewSet,       basename="measurement-book")
router.register(r"ipcs",                    IPCViewSet,                   basename="ipc")
router.register(r"mobilization-payments",   MobilizationPaymentViewSet,   basename="mobilization-payment")
router.register(r"retention-releases",      RetentionReleaseViewSet,      basename="retention-release")
router.register(r"variations",              ContractVariationViewSet,     basename="variation")
router.register(r"completion-certificates", CompletionCertificateViewSet, basename="completion-certificate")
router.register(r"approval-steps",          ContractApprovalStepViewSet,  basename="approval-step")
router.register(r"documents",               ContractDocumentViewSet,      basename="document")

urlpatterns = router.urls
