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

from decimal import Decimal
from rest_framework import serializers

from contracts.models import (
    CompletionCertificate,
    Contract,
    ContractApprovalStep,
    ContractBalance,
    ContractDocument,
    ContractVariation,
    ContractYearPlan,
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


# ── ContractYearPlan ───────────────────────────────────────────────────

class ContractYearPlanSerializer(serializers.ModelSerializer):
    """Multi-year contract payment-plan slice.

    Read fields are denormalised so the frontend's Year-Plan tab can
    render planned-vs-actual without an N+1 chain:
      - ``fiscal_year_label`` — display string (e.g. "FY 2027")
      - ``appropriation_label`` — display string (e.g. "Health · Capital")
      - ``total_authorised_for_year`` — planned + carried-forward
    """

    fiscal_year_label = serializers.SerializerMethodField()
    appropriation_label = serializers.SerializerMethodField()
    total_authorised_for_year = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )

    class Meta:
        model = ContractYearPlan
        fields = [
            "id",
            "contract",
            "fiscal_year",
            "fiscal_year_label",
            "appropriation",
            "appropriation_label",
            "planned_amount",
            "carried_forward_from_prior_year",
            "total_authorised_for_year",
            "sequence",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_fiscal_year_label(self, obj: ContractYearPlan) -> str:
        fy = getattr(obj, "fiscal_year", None)
        if fy is None:
            return ""
        # Most FiscalYear models have a ``year`` int; fall back to str().
        year = getattr(fy, "year", None)
        return f"FY {year}" if year is not None else str(fy)

    def get_appropriation_label(self, obj: ContractYearPlan) -> str:
        appr = getattr(obj, "appropriation", None)
        if appr is None:
            return ""
        # Tolerant: appropriation models in this codebase don't have a
        # uniform ``__str__`` shape, so fall back through several fields.
        for attr in ("display_label", "name", "appropriation_number"):
            val = getattr(appr, attr, None)
            if val:
                return str(val)
        return f"Appropriation #{appr.pk}"


# ── Milestones ────────────────────────────────────────────────────────

class MilestoneScheduleSerializer(serializers.ModelSerializer):
    # ── IPC linkage (read-only) ───────────────────────────────────────
    # ``InterimPaymentCertificate.milestone`` is a OneToOneField with
    # ``related_name="ipc"``, so ``milestone.ipc`` resolves to the
    # single IPC raised against this milestone — or raises
    # ``InterimPaymentCertificate.DoesNotExist`` for the common case
    # where no IPC has been raised yet. Method fields with a guarded
    # ``hasattr`` check are the simplest way to flatten that into a
    # nullable JSON value the frontend can consume.
    #
    # Why both ``ipc`` AND ``ipc_number``: the contract detail UI uses
    # ``ipc`` (truthy id) as the visibility gate for the "Convert to
    # IPC" button, and ``ipc_number`` (e.g. ``DSG/WORKS/2026/001/IPC/01``)
    # as the human-readable audit pointer next to the row.
    ipc = serializers.SerializerMethodField()
    ipc_number = serializers.SerializerMethodField()

    class Meta:
        model = MilestoneSchedule
        fields = [
            "id", "contract", "milestone_number", "description",
            "scheduled_value", "percentage_weight",
            "target_date", "actual_completion_date",
            "status", "notes",
            "ipc", "ipc_number",
        ]
        read_only_fields = ["id"]

    def get_ipc(self, obj):
        # ``hasattr`` returns False for an unset reverse OneToOne in
        # Django, so this is safe and side-effect-free (no query
        # beyond what select_related already prefetched).
        ipc = getattr(obj, "ipc", None) if hasattr(obj, "ipc") else None
        return ipc.pk if ipc else None

    def get_ipc_number(self, obj):
        ipc = getattr(obj, "ipc", None) if hasattr(obj, "ipc") else None
        return ipc.ipc_number if ipc else None


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
    # Lump-sum retention reserved upfront off the contract sum.
    # original_sum × retention_rate / 100. Held in
    # balance.retention_held from activation; released at completion.
    # Surfaced here so the contract detail UI can show the breakdown:
    #   Contract Sum: ₦100,000  −  Retention Reserve: ₦5,000  =
    #   Processable: ₦95,000 (== contract_ceiling).
    retention_reserve = serializers.DecimalField(
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

    # Mobilization status surfaced on the contracts list so operators
    # can scan "which contracts have a pending mobilization that needs
    # treasury action" without drilling into each row. Returns the
    # MobilizationPayment.status when one exists, or '' when no advance
    # has been issued (so the column reads as blank — distinct from
    # an explicit PENDING/APPROVED/PAID value). The relation is the
    # ``mobilization_payment`` reverse OneToOne; ``hasattr`` returns
    # False when the row doesn't exist (Django reverse-OneToOne semantics).
    mobilization_status = serializers.SerializerMethodField()
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

    def get_mobilization_status(self, obj):
        # Reverse OneToOne — ``mobilization_payment`` is set on Contract
        # via ``MobilizationPayment.contract = OneToOneField(...,
        # related_name="mobilization_payment")``. ``hasattr`` correctly
        # returns False when no related row exists. Side-effect-free
        # when the queryset prefetched the relation (which it should —
        # see ContractViewSet); otherwise one extra SELECT per row.
        if hasattr(obj, 'mobilization_payment'):
            try:
                return obj.mobilization_payment.status
            except Exception:
                return ''
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
            "retention_reserve",
            "mobilization_status",
            # Embedded
            "milestones", "balance",
        ]
        read_only_fields = [
            "id", "contract_number", "status",
            "created_at", "updated_at",
            "mobilization_amount", "approved_variations_total", "contract_ceiling",
            "retention_reserve",
            "mobilization_status",
            "milestones", "balance",
            "ncoa_code_economic_id", "ncoa_code_fund_id",
            "ncoa_code_programme_id", "ncoa_code_functional_id",
            "ncoa_code_geographic_id",
            "ncoa_economic_code", "ncoa_economic_name",
            "vendor_ap_code", "vendor_ap_name",
            "withholding_account_code", "input_tax_account_code",
        ]
        # ``retention_rate`` is a contract clause that is contractually
        # optional. Many consultancy / supply / service contracts
        # carry no retention at all; only works contracts typically
        # do. At the API surface we treat "blank / null / omitted"
        # as the operator's explicit "no retention" intent — saved
        # as 0.00, not silently coerced back to a 5% default they
        # may have just deliberately removed.
        #
        # The model still keeps ``default=Decimal('5.00')`` for ORM-
        # direct callers (admin, fixtures, service scripts) so their
        # existing behaviour is unchanged — that path is unaffected
        # by serializer-level defaults.
        extra_kwargs = {
            "retention_rate": {
                "required": False,
                "allow_null": True,
                "default": Decimal("0.00"),
            },
        }

    def validate(self, attrs):
        # ``retention_rate=null`` from the form means "no retention on
        # this contract". Coerce to 0.00 so the DB column (which is
        # not-null) holds a real value, but DO NOT silently re-apply
        # a 5% default the operator just deleted.
        if "retention_rate" in attrs and attrs["retention_rate"] is None:
            attrs["retention_rate"] = Decimal("0.00")

        # Lock financial / structural fields after activation. The
        # canonical path for changes after activation is
        # ``ContractVariation`` (with tier-based approval).  Allowing
        # PATCH on these fields would bypass the variation workflow
        # entirely, mutating contract value with no audit trail and
        # invalidating retention / mobilization formulas already
        # applied to past IPCs.
        attrs = super().validate(attrs)
        if self.instance and self.instance.status not in ('DRAFT', None):
            locked_fields = (
                'original_sum',
                'mobilization_rate',
                'retention_rate',
                'vendor',
                'fiscal_year',
                'ncoa_code',
                'mda',
            )
            attempted_changes = {
                f: attrs[f] for f in locked_fields
                if f in attrs and getattr(self.instance, f, None) != attrs[f]
            }
            if attempted_changes:
                raise serializers.ValidationError({
                    'error': (
                        f'Cannot modify contract {self.instance.contract_number} '
                        f'fields after activation: {sorted(attempted_changes)}. '
                        f'Use a Contract Variation (with tier approval) to change '
                        f'contract value, deduction rates, or party assignments.'
                    ),
                    'locked_fields': sorted(attempted_changes),
                    'contract_status': self.instance.status,
                })
        return attrs


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
    # Lock affordance: surfaced so the SPA can hide the Reject button
    # when the linked PaymentVoucherGov is still active. The lock
    # releases automatically when the PV is CANCELLED or REVERSED.
    payment_voucher_number = serializers.CharField(
        source='payment_voucher.voucher_number', read_only=True, default=None,
    )
    payment_voucher_status = serializers.CharField(
        source='payment_voucher.status', read_only=True, default=None,
    )

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
            "payment_voucher_number", "payment_voucher_status",
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
            "payment_voucher_number", "payment_voucher_status",
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
    # Human-readable display fields so the cross-contract list page
    # (see ``MobilizationPaymentList`` in the frontend) can show
    # contract number / vendor / voucher info without N+1 round-trips.
    # All pull via ``source=`` so they cost nothing extra when the
    # viewset's queryset has ``select_related('contract__vendor',
    # 'payment_voucher')`` — which the ViewSet already does.
    contract_number = serializers.CharField(
        source="contract.contract_number", read_only=True, default="",
    )
    contract_title = serializers.CharField(
        source="contract.title", read_only=True, default="",
    )
    vendor_name = serializers.CharField(
        source="contract.vendor.name", read_only=True, default="",
    )
    payment_voucher_number = serializers.CharField(
        source="payment_voucher.voucher_number", read_only=True, default="",
    )
    # The PV's status — operators on the Mobilization list want to see
    # whether the linked PV is still DRAFT, APPROVED, SCHEDULED, or
    # PAID without having to drill into the PV detail page.
    payment_voucher_status = serializers.CharField(
        source="payment_voucher.status", read_only=True, default="",
    )
    # Journal id when the disbursement journal exists — surfaced so
    # the Mobilization contract tab can link directly to "view the
    # accounting entries" without an extra round trip.
    payment_voucher_journal_id = serializers.IntegerField(
        source="payment_voucher.journal_id", read_only=True, default=None, allow_null=True,
    )

    class Meta:
        model = MobilizationPayment
        fields = [
            "id", "contract", "contract_number", "contract_title", "vendor_name",
            "amount",
            "payment_voucher", "payment_voucher_number",
            "payment_voucher_status", "payment_voucher_journal_id",
            "payment_date",
            "status", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "amount", "payment_voucher", "payment_date",
            "status", "created_at", "updated_at",
            "contract_number", "contract_title", "vendor_name",
            "payment_voucher_number",
            "payment_voucher_status", "payment_voucher_journal_id",
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

# Contract attachments are operator-facing evidence (BPP no-objection
# letters, signed PV scans, contractor bank letters). Browsers report
# ``Content-Type`` from the local OS guess — trivially spoofable.
# Match against the project's shared magic-byte catalogue so a
# renamed .exe can't pose as a .pdf in the audit trail.
_CONTRACT_DOC_ALLOWED_EXT = {
    '.pdf', '.jpg', '.jpeg', '.png',
    '.doc', '.docx', '.xlsx',
}
# 25 MB ceiling — scanned PDFs of full contracts can be large but
# anything beyond this is almost certainly a misclick (raw bitmap)
# and we want to fail fast before chewing through TSA storage.
_CONTRACT_DOC_MAX_BYTES = 25 * 1024 * 1024


class ContractDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDocument
        fields = [
            "id", "contract", "document_type", "title",
            "file", "description", "uploaded_by",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "uploaded_by", "created_at", "updated_at"]

    def validate_file(self, value):
        """Magic-byte + extension + size validation.

        Was: no validation at all — any authenticated user could
        upload an arbitrary binary disguised as a PDF/DOCX. The
        shared ``core.file_validation.validate_uploaded_file`` helper
        runs the same checks the tenant onboarding flow uses, so the
        rules can't drift between upload surfaces.
        """
        from core.file_validation import validate_uploaded_file
        is_valid, err = validate_uploaded_file(
            value,
            allowed_extensions=_CONTRACT_DOC_ALLOWED_EXT,
            max_bytes=_CONTRACT_DOC_MAX_BYTES,
        )
        if not is_valid:
            raise serializers.ValidationError(err)
        return value
