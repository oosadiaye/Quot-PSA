"""
DRF serializers for the contracts module.

Design notes:
  • All money fields are DecimalField with max_digits=20, decimal_places=2
    to match the ORM.
  • Computed/derived fields are read-only — the service layer owns the
    write path.
  • "Action" serializers (e.g. ActivateContractSerializer) are used
    inside @action methods to validate request bodies for state
    transitions; they are deliberately NOT ModelSerializers.
"""
from __future__ import annotations

from rest_framework import serializers

from contracts.models import (
    CompletionCertificate,
    Contract,
    ContractApprovalStep,
    ContractBalance,
    ContractDocument,
    ContractVariation,
    InterimPaymentCertificate,
    MeasurementBook,
    MilestoneSchedule,
    MobilizationPayment,
    RetentionRelease,
)


# ── ContractBalance (read-only) ────────────────────────────────────────

class ContractBalanceSerializer(serializers.ModelSerializer):
    available_for_certification = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    mobilization_outstanding = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    retention_balance = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )

    class Meta:
        model = ContractBalance
        fields = [
            "contract_id",
            "contract_ceiling",
            "cumulative_gross_certified",
            "pending_voucher_amount",
            "cumulative_gross_paid",
            "mobilization_paid",
            "mobilization_recovered",
            "retention_held",
            "retention_released",
            "version",
            "updated_at",
            "available_for_certification",
            "mobilization_outstanding",
            "retention_balance",
        ]
        read_only_fields = fields


# ── Milestones ────────────────────────────────────────────────────────

class MilestoneScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MilestoneSchedule
        fields = [
            "id", "contract", "milestone_number", "description",
            "scheduled_value", "percentage_weight",
            "target_date", "actual_completion_date",
            "status", "notes",
        ]
        read_only_fields = ["id"]


# ── Contracts ─────────────────────────────────────────────────────────

class ContractSerializer(serializers.ModelSerializer):
    """Full Contract representation.

    ``contract_number`` is set by ContractActivationService on activation
    and is read-only on create; tests that need to preset a number
    should call the service directly.
    """

    mobilization_amount = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    approved_variations_total = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    contract_ceiling = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    milestones = MilestoneScheduleSerializer(many=True, read_only=True)
    balance = ContractBalanceSerializer(read_only=True)

    # ── NCoA segment IDs (read-only flatten) ───────────────────────────
    # The contract form lets the user pick each NCoA segment
    # independently (GL Account, Fund, Programme, Function, Geo). When
    # editing an existing contract, the form needs to PREFILL those 5
    # separate dropdowns from the single ``ncoa_code`` FK on the
    # underlying row. We expose each segment id as a flat top-level
    # field via ``source='ncoa_code.<seg>_id'`` so the React form can
    # read them without having to walk the nested NCoACode structure.
    ncoa_code_economic_id   = serializers.IntegerField(
        source='ncoa_code.economic_id',   read_only=True, default=None,
    )
    ncoa_code_fund_id       = serializers.IntegerField(
        source='ncoa_code.fund_id',       read_only=True, default=None,
    )
    ncoa_code_programme_id  = serializers.IntegerField(
        source='ncoa_code.programme_id',  read_only=True, default=None,
    )
    ncoa_code_functional_id = serializers.IntegerField(
        source='ncoa_code.functional_id', read_only=True, default=None,
    )
    ncoa_code_geographic_id = serializers.IntegerField(
        source='ncoa_code.geographic_id', read_only=True, default=None,
    )
    # ── GL code strings (for IPC ledger projected rows) ───────────────
    # The IPC detail page renders a "projected" GL ledger before the
    # accrual journal posts; it needs the actual account *codes* — not
    # just FK ids — so each row carries something meaningful in the
    # GL CODE column. Pulling the code through serializer ``source``
    # avoids extra round-trips and stays read-only by definition.
    ncoa_economic_code = serializers.CharField(
        source='ncoa_code.economic.code', read_only=True, default='',
    )
    ncoa_economic_name = serializers.CharField(
        source='ncoa_code.economic.name', read_only=True, default='',
    )
    vendor_ap_code = serializers.SerializerMethodField()
    vendor_ap_name = serializers.SerializerMethodField()
    withholding_account_code = serializers.CharField(
        source='vendor.withholding_tax_code.withholding_account.code',
        read_only=True, default='',
    )
    input_tax_account_code = serializers.CharField(
        source='vendor.tax_code.input_tax_account.code',
        read_only=True, default='',
    )

    def get_vendor_ap_code(self, obj):
        """Walk vendor → category → reconciliation_account → code.
        Returns '' when any link is missing rather than blowing up."""
        try:
            recon = (obj.vendor.category.reconciliation_account
                     if obj.vendor and obj.vendor.category else None)
            return recon.code if recon else ''
        except Exception:
            return ''

    def get_vendor_ap_name(self, obj):
        try:
            recon = (obj.vendor.category.reconciliation_account
                     if obj.vendor and obj.vendor.category else None)
            return recon.name if recon else ''
        except Exception:
            return ''

    class Meta:
        model = Contract
        fields = [
            "id", "contract_number",
            "title", "description", "reference",
            "contract_type", "procurement_method", "status",
            "vendor", "mda", "ncoa_code", "appropriation", "fiscal_year",
            # Per-segment ids (read-only) for form prefill on edit.
            "ncoa_code_economic_id", "ncoa_code_fund_id",
            "ncoa_code_programme_id", "ncoa_code_functional_id",
            "ncoa_code_geographic_id",
            # Resolved GL codes/names (for IPC projected ledger).
            "ncoa_economic_code", "ncoa_economic_name",
            "vendor_ap_code", "vendor_ap_name",
            "withholding_account_code", "input_tax_account_code",
            "original_sum", "mobilization_rate", "retention_rate",
            "bpp_no_objection_ref", "due_process_certificate",
            "signed_date", "commencement_date",
            "contract_start_date", "contract_end_date",
            "defects_liability_period_days",
            "notes",
            "created_at", "updated_at",
            # Computed
            "mobilization_amount", "approved_variations_total", "contract_ceiling",
            # Embedded
            "milestones", "balance",
        ]
        read_only_fields = [
            "id", "contract_number", "status",
            "created_at", "updated_at",
            "mobilization_amount", "approved_variations_total", "contract_ceiling",
            "milestones", "balance",
            "ncoa_code_economic_id", "ncoa_code_fund_id",
            "ncoa_code_programme_id", "ncoa_code_functional_id",
            "ncoa_code_geographic_id",
            "ncoa_economic_code", "ncoa_economic_name",
            "vendor_ap_code", "vendor_ap_name",
            "withholding_account_code", "input_tax_account_code",
        ]


class ActivateContractSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class CloseContractSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


# ── Variations ────────────────────────────────────────────────────────

class ContractVariationSerializer(serializers.ModelSerializer):
    approval_tier = serializers.CharField(read_only=True)
    delta_amount = serializers.SerializerMethodField()
    cumulative_pct = serializers.SerializerMethodField()
    contract_reference = serializers.CharField(
        source="contract.reference", read_only=True
    )
    supporting_reference = serializers.CharField(
        source="bpp_approval_ref", read_only=True
    )

    class Meta:
        model = ContractVariation
        fields = [
            "id", "contract", "contract_reference",
            "variation_number", "variation_type",
            "amount", "delta_amount", "cumulative_pct",
            "description", "justification",
            "time_extension_days", "bpp_approval_ref", "supporting_reference",
            "approval_tier", "status",
            "approved_by", "approved_at",
            "rejection_reason",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "variation_number", "approval_tier", "status",
            "approved_by", "approved_at", "rejection_reason",
            "delta_amount", "cumulative_pct", "contract_reference",
            "supporting_reference",
            "created_at", "updated_at",
        ]

    def get_delta_amount(self, obj: ContractVariation) -> str:
        # Delta applied to the ceiling: OMISSION is negative, others as stored.
        from decimal import Decimal
        amount = obj.amount or Decimal("0.00")
        if obj.variation_type == "OMISSION":
            amount = -abs(amount)
        return f"{amount:.2f}"

    def get_cumulative_pct(self, obj: ContractVariation) -> float:
        from decimal import Decimal
        contract = obj.contract
        original = contract.original_sum or Decimal("0.00")
        if not original:
            return 0.0
        approved_total = (
            ContractVariation.objects.filter(
                contract=contract,
                status="APPROVED",
                variation_number__lte=obj.variation_number,
            )
            .values_list("amount", flat=True)
        )
        total = sum((a or Decimal("0.00")) for a in approved_total)
        # If this variation isn't approved yet, its own amount contributes nothing.
        if obj.status != "APPROVED":
            total -= (obj.amount or Decimal("0.00"))
        return float((total / original) * Decimal("100"))


class VariationActionSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class VariationRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True)


# ── Measurement Books ─────────────────────────────────────────────────

class MeasurementBookSerializer(serializers.ModelSerializer):
    total_measured_value = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )

    class Meta:
        model = MeasurementBook
        fields = [
            "id", "contract", "mb_number", "measurement_date",
            "items", "total_measured_value",
            "status", "measured_by", "checked_by", "approved_by",
            "notes", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "mb_number", "total_measured_value", "status",
            "created_at", "updated_at",
        ]


# ── Interim Payment Certificates ──────────────────────────────────────

class IPCSerializer(serializers.ModelSerializer):
    net_payable = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    integrity_hash = serializers.CharField(read_only=True)

    class Meta:
        model = InterimPaymentCertificate
        fields = [
            "id", "contract", "ipc_number", "measurement_book",
            "milestone",
            "tax_code", "withholding_tax", "wht_exempt",
            "posting_date",
            "cumulative_work_done_to_date",
            "previous_certified", "this_certificate_gross",
            "mobilization_recovery_this_cert",
            "retention_deduction_this_cert",
            "ld_deduction", "variation_claims",
            "vat_amount", "wht_amount",
            "net_payable",
            "status", "certifying_engineer",
            "integrity_hash",
            "accrual_journal", "payment_voucher",
            "rejection_reason", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "ipc_number", "status",
            "milestone",
            "previous_certified", "this_certificate_gross",
            "mobilization_recovery_this_cert",
            "retention_deduction_this_cert",
            "vat_amount", "wht_amount", "net_payable",
            "certifying_engineer", "integrity_hash",
            "accrual_journal", "payment_voucher",
            "rejection_reason",
            "created_at", "updated_at",
        ]


class IPCSubmitSerializer(serializers.Serializer):
    contract = serializers.PrimaryKeyRelatedField(queryset=Contract.objects.all())
    measurement_book = serializers.PrimaryKeyRelatedField(
        queryset=MeasurementBook.objects.all(),
        required=False, allow_null=True,
    )
    posting_date = serializers.DateField()
    cumulative_work_done_to_date = serializers.DecimalField(
        max_digits=20, decimal_places=2, min_value=0,
    )
    variation_claims = serializers.DecimalField(
        max_digits=20, decimal_places=2, min_value=0,
        required=False, default=0,
    )
    ld_deduction = serializers.DecimalField(
        max_digits=20, decimal_places=2, min_value=0,
        required=False, default=0,
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class IPCActionSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class IPCRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True)


class IPCRaiseVoucherSerializer(serializers.Serializer):
    payment_voucher_id = serializers.IntegerField()
    voucher_gross = serializers.DecimalField(max_digits=20, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class IPCMarkPaidSerializer(serializers.Serializer):
    payment_date = serializers.DateField()
    vat_amount = serializers.DecimalField(
        max_digits=20, decimal_places=2, min_value=0, default=0,
    )
    wht_amount = serializers.DecimalField(
        max_digits=20, decimal_places=2, min_value=0, default=0,
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")


# ── Mobilization payments ─────────────────────────────────────────────

class MobilizationPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobilizationPayment
        fields = [
            "id", "contract", "amount",
            "payment_voucher", "payment_date",
            "status", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "amount", "payment_voucher", "payment_date",
            "status", "created_at", "updated_at",
        ]


class MobilizationMarkPaidSerializer(serializers.Serializer):
    payment_voucher_id = serializers.IntegerField()
    payment_date = serializers.DateField()


# ── Retention releases ────────────────────────────────────────────────

class RetentionReleaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = RetentionRelease
        fields = [
            "id", "contract", "release_type", "amount",
            "payment_voucher", "payment_date",
            "status", "approved_by", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "amount", "payment_voucher", "payment_date",
            "status", "approved_by", "created_at", "updated_at",
        ]


class RetentionCreateSerializer(serializers.Serializer):
    contract = serializers.PrimaryKeyRelatedField(queryset=Contract.objects.all())
    release_type = serializers.CharField()


class RetentionActionSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class RetentionMarkPaidSerializer(serializers.Serializer):
    payment_voucher_id = serializers.IntegerField()
    payment_date = serializers.DateField()


# ── Completion certificates ───────────────────────────────────────────

class CompletionCertificateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompletionCertificate
        fields = [
            "id", "contract", "certificate_type",
            "issued_date", "effective_date",
            "certified_by", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CompletionIssueSerializer(serializers.Serializer):
    issued_date = serializers.DateField()
    effective_date = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")


# ── Approval Steps (read-only audit) ──────────────────────────────────

class ContractApprovalStepSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(
        source="get_action_display", read_only=True,
    )
    object_type_display = serializers.CharField(
        source="get_object_type_display", read_only=True,
    )

    class Meta:
        model = ContractApprovalStep
        fields = [
            "id", "object_type", "object_type_display",
            "object_id", "contract",
            "step_number", "role_required",
            "assigned_to", "action", "action_display",
            "action_by", "action_at", "notes",
        ]
        read_only_fields = fields


# ── Contract documents ────────────────────────────────────────────────

class ContractDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDocument
        fields = [
            "id", "contract", "document_type", "title",
            "file", "description", "uploaded_by",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "uploaded_by", "created_at", "updated_at"]
