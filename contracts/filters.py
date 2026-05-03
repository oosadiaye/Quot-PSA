"""
django-filter FilterSet classes for the contracts API.

Exposes only the safe, indexed query dimensions — no full-table scans
on free-text columns. Order/pagination is configured at the viewset
level via DRF's standard filter_backends stack.
"""
from __future__ import annotations

import django_filters as df

from contracts.models import (
    CompletionCertificate,
    Contract,
    ContractApprovalStep,
    ContractVariation,
    InterimPaymentCertificate,
    MeasurementBook,
    MobilizationPayment,
    RetentionRelease,
)


class ContractFilter(df.FilterSet):
    status          = df.CharFilter(field_name="status")
    contract_type   = df.CharFilter(field_name="contract_type")
    mda             = df.NumberFilter(field_name="mda_id")
    vendor          = df.NumberFilter(field_name="vendor_id")
    fiscal_year     = df.NumberFilter(field_name="fiscal_year_id")
    signed_after    = df.DateFilter(field_name="signed_date", lookup_expr="gte")
    signed_before   = df.DateFilter(field_name="signed_date", lookup_expr="lte")

    class Meta:
        model = Contract
        fields = [
            "status", "contract_type", "mda", "vendor",
            "fiscal_year", "signed_after", "signed_before",
        ]


class IPCFilter(df.FilterSet):
    contract  = df.NumberFilter(field_name="contract_id")
    status    = df.CharFilter(field_name="status")
    posted_after  = df.DateFilter(field_name="posting_date", lookup_expr="gte")
    posted_before = df.DateFilter(field_name="posting_date", lookup_expr="lte")

    class Meta:
        model = InterimPaymentCertificate
        fields = ["contract", "status", "posted_after", "posted_before"]


class VariationFilter(df.FilterSet):
    contract = df.NumberFilter(field_name="contract_id")
    status   = df.CharFilter(field_name="status")
    tier     = df.CharFilter(field_name="approval_tier")

    class Meta:
        model = ContractVariation
        fields = ["contract", "status", "tier"]


class MeasurementBookFilter(df.FilterSet):
    contract = df.NumberFilter(field_name="contract_id")
    status   = df.CharFilter(field_name="status")

    class Meta:
        model = MeasurementBook
        fields = ["contract", "status"]


class MobilizationPaymentFilter(df.FilterSet):
    contract = df.NumberFilter(field_name="contract_id")
    status   = df.CharFilter(field_name="status")

    class Meta:
        model = MobilizationPayment
        fields = ["contract", "status"]


class RetentionReleaseFilter(df.FilterSet):
    contract     = df.NumberFilter(field_name="contract_id")
    status       = df.CharFilter(field_name="status")
    release_type = df.CharFilter(field_name="release_type")

    class Meta:
        model = RetentionRelease
        fields = ["contract", "status", "release_type"]


class CompletionCertificateFilter(df.FilterSet):
    contract         = df.NumberFilter(field_name="contract_id")
    certificate_type = df.CharFilter(field_name="certificate_type")

    class Meta:
        model = CompletionCertificate
        fields = ["contract", "certificate_type"]


class ApprovalStepFilter(df.FilterSet):
    contract    = df.NumberFilter(field_name="contract_id")
    object_type = df.CharFilter(field_name="object_type")
    object_id   = df.NumberFilter(field_name="object_id")
    action      = df.CharFilter(field_name="action")
    actor       = df.NumberFilter(field_name="action_by_id")

    class Meta:
        model = ContractApprovalStep
        fields = ["contract", "object_type", "object_id", "action", "actor"]
