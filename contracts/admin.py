"""
Django Admin registrations for the contracts module.
"""
from django.contrib import admin
from django.utils.html import format_html

from contracts.models import (
    Contract,
    ContractBalance,
    ContractVariation,
    MilestoneSchedule,
    MeasurementBook,
    InterimPaymentCertificate,
    MobilizationPayment,
    RetentionRelease,
    CompletionCertificate,
    ContractApprovalStep,
    ContractDocument,
)


class MilestoneInline(admin.TabularInline):
    model = MilestoneSchedule
    extra = 0
    fields = ["milestone_number", "description", "scheduled_value", "percentage_weight",
              "target_date", "status"]
    readonly_fields = ["milestone_number"]


class ContractVariationInline(admin.TabularInline):
    model = ContractVariation
    extra = 0
    fields = ["variation_number", "variation_type", "amount", "status", "approval_tier"]
    readonly_fields = ["variation_number", "approval_tier"]


class ContractDocumentInline(admin.TabularInline):
    model = ContractDocument
    extra = 0
    fields = ["document_type", "title", "file", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = [
        "contract_number", "title", "contract_type", "status",
        "vendor", "mda", "original_sum", "contract_ceiling_display", "created_at",
    ]
    list_filter  = ["status", "contract_type", "procurement_method", "fiscal_year"]
    search_fields = ["contract_number", "title", "vendor__name", "reference"]
    readonly_fields = [
        "contract_number", "created_at", "updated_at",
        "contract_ceiling_display", "mobilization_amount_display",
    ]
    inlines = [MilestoneInline, ContractVariationInline, ContractDocumentInline]

    @admin.display(description="Contract Ceiling (₦)")
    def contract_ceiling_display(self, obj: Contract) -> str:
        return f"₦{obj.contract_ceiling:,.2f}"

    @admin.display(description="Mobilization Amount (₦)")
    def mobilization_amount_display(self, obj: Contract) -> str:
        return f"₦{obj.mobilization_amount:,.2f}"


@admin.register(ContractBalance)
class ContractBalanceAdmin(admin.ModelAdmin):
    list_display = [
        "contract", "contract_ceiling", "cumulative_gross_certified",
        "cumulative_gross_paid", "version",
    ]
    readonly_fields = [field.name for field in ContractBalance._meta.fields]


@admin.register(InterimPaymentCertificate)
class IPCAdmin(admin.ModelAdmin):
    list_display = [
        "ipc_number", "contract", "posting_date",
        "this_certificate_gross", "net_payable", "status",
    ]
    list_filter  = ["status"]
    search_fields = ["ipc_number", "contract__contract_number"]
    readonly_fields = [
        "ipc_number", "previous_certified", "this_certificate_gross",
        "net_payable", "integrity_hash", "created_at", "updated_at",
    ]


@admin.register(ContractVariation)
class VariationAdmin(admin.ModelAdmin):
    list_display = [
        "variation_number", "contract", "variation_type", "amount",
        "approval_tier", "status",
    ]
    list_filter  = ["status", "variation_type", "approval_tier"]
    readonly_fields = ["variation_number", "approval_tier", "created_at", "updated_at"]


@admin.register(MeasurementBook)
class MeasurementBookAdmin(admin.ModelAdmin):
    list_display = [
        "mb_number", "contract", "measurement_date",
        "total_measured_value", "status",
    ]
    list_filter  = ["status"]


@admin.register(MobilizationPayment)
class MobilizationPaymentAdmin(admin.ModelAdmin):
    list_display = ["contract", "amount", "status", "payment_date"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(RetentionRelease)
class RetentionReleaseAdmin(admin.ModelAdmin):
    list_display = ["contract", "release_type", "amount", "status", "payment_date"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(CompletionCertificate)
class CompletionCertificateAdmin(admin.ModelAdmin):
    list_display = ["contract", "certificate_type", "issued_date", "effective_date", "certified_by"]
    list_filter  = ["certificate_type"]


@admin.register(ContractApprovalStep)
class ContractApprovalStepAdmin(admin.ModelAdmin):
    list_display = [
        "contract", "object_type", "object_id", "step_number",
        "action", "action_by", "action_at",
    ]
    list_filter  = ["object_type", "action"]
    readonly_fields = [field.name for field in ContractApprovalStep._meta.fields]

    def has_change_permission(self, request, obj=None) -> bool:
        return False  # immutable

    def has_delete_permission(self, request, obj=None) -> bool:
        return False  # immutable
