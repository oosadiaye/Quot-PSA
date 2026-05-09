from rest_framework import serializers
from .models import (
    UnifiedBudget, UnifiedBudgetEncumbrance, UnifiedBudgetVariance,
    UnifiedBudgetAmendment, RevenueBudget, AppropriationVirement,
)


class UnifiedBudgetVarianceSerializer(serializers.ModelSerializer):
    budget_code = serializers.ReadOnlyField(source='budget.budget_code')
    period_variance_percent = serializers.ReadOnlyField()
    ytd_variance_percent = serializers.ReadOnlyField()

    class Meta:
        model = UnifiedBudgetVariance
        fields = [
            'id', 'budget', 'budget_code', 'fiscal_year', 'period_type', 'period_number',
            'variance_type', 'period_budget', 'period_actual', 'period_variance', 'period_variance_percent',
            'ytd_budget', 'ytd_actual', 'ytd_variance', 'ytd_variance_percent',
            'encumbered_amount', 'committed_amount', 'calculated_at'
        ]


class UnifiedBudgetEncumbranceSerializer(serializers.ModelSerializer):
    budget_code = serializers.ReadOnlyField(source='budget.budget_code')
    remaining_amount = serializers.ReadOnlyField()

    class Meta:
        model = UnifiedBudgetEncumbrance
        fields = [
            'id', 'budget', 'budget_code', 'reference_type', 'reference_id', 'reference_number',
            'encumbrance_date', 'amount', 'liquidated_amount', 'remaining_amount',
            'status', 'description', 'is_aggregate', 'created_by', 'created_at'
        ]


class UnifiedBudgetAmendmentSerializer(serializers.ModelSerializer):
    budget_code = serializers.ReadOnlyField(source='budget.budget_code')
    requested_by_name = serializers.ReadOnlyField(source='requested_by.username')
    approved_by_name = serializers.ReadOnlyField(source='approved_by.username')

    class Meta:
        model = UnifiedBudgetAmendment
        fields = [
            'id', 'budget', 'budget_code', 'amendment_number', 'amendment_type',
            'original_amount', 'new_amount', 'change_amount',
            'from_budget', 'to_budget', 'reason', 'status',
            'requested_by', 'requested_by_name', 'approved_by', 'approved_by_name',
            'approved_date', 'created_at'
        ]


class UnifiedBudgetSerializer(serializers.ModelSerializer):
    """Serializer for Unified Budget - supports both Public and Private Sector"""
    allocated_amount = serializers.ReadOnlyField()
    encumbered_amount = serializers.ReadOnlyField()
    actual_expended = serializers.ReadOnlyField()
    available_amount = serializers.ReadOnlyField()
    utilization_rate = serializers.ReadOnlyField()
    variance_amount = serializers.ReadOnlyField()
    variance_percent = serializers.ReadOnlyField()

    mda_name = serializers.ReadOnlyField(source='mda.name')
    cost_center_name = serializers.ReadOnlyField(source='cost_center.name')
    fund_name = serializers.ReadOnlyField(source='fund.name')
    function_name = serializers.ReadOnlyField(source='function.name')
    program_name = serializers.ReadOnlyField(source='program.name')
    geo_name = serializers.ReadOnlyField(source='geo.name')
    account_code = serializers.ReadOnlyField(source='account.code')
    account_name = serializers.ReadOnlyField(source='account.name')

    class Meta:
        model = UnifiedBudget
        fields = [
            'id', 'budget_code', 'name', 'description', 'budget_type',
            'fiscal_year', 'period_type', 'period_number', 'status',
            'mda', 'mda_name', 'fund', 'fund_name', 'function', 'function_name',
            'program', 'program_name', 'geo', 'geo_name', 'cost_center', 'cost_center_name',
            'account', 'account_code', 'account_name',
            'original_amount', 'revised_amount', 'supplemental_amount', 'allocated_amount',
            'control_level', 'enable_encumbrance', 'allow_over_expenditure', 'over_expenditure_limit_percent',
            'approved_by', 'approved_date', 'closed_date',
            'encumbered_amount', 'actual_expended', 'available_amount',
            'utilization_rate', 'variance_amount', 'variance_percent',
            'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'approved_date', 'closed_date']


# Legacy aliases for backward compatibility
BudgetVarianceSerializer = UnifiedBudgetVarianceSerializer
BudgetLineSerializer = UnifiedBudgetEncumbranceSerializer
BudgetAllocationSerializer = UnifiedBudgetSerializer


# ─── Government Appropriation & Warrant (Quot PSE Phase 3) ───────────

from .models import Appropriation, Warrant, WarrantPrintoutSettings


class AppropriationSerializer(serializers.ModelSerializer):
    # ── Segment codes (for audit / cross-reference) ──────────
    administrative_code = serializers.CharField(source='administrative.code', read_only=True)
    administrative_name = serializers.CharField(source='administrative.name', read_only=True)
    economic_code = serializers.CharField(source='economic.code', read_only=True)
    economic_name = serializers.CharField(source='economic.name', read_only=True)
    functional_code = serializers.CharField(source='functional.code', read_only=True)
    functional_name = serializers.CharField(source='functional.name', read_only=True)
    programme_code = serializers.CharField(source='programme.code', read_only=True)
    programme_name = serializers.CharField(source='programme.name', read_only=True)
    fund_code = serializers.CharField(source='fund.code', read_only=True)
    fund_name = serializers.CharField(source='fund.name', read_only=True)
    geographic_code = serializers.CharField(source='geographic.code', read_only=True)
    geographic_name = serializers.CharField(source='geographic.name', read_only=True)

    fiscal_year_label = serializers.SerializerMethodField()
    total_warrants_released = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    # PO-only commitment total — read by budget-check rules & virement
    # services. Kept as-is for backwards compatibility with those callers.
    total_committed = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    # Live recompute of total_committed (bypasses cached_total_committed).
    # Used by E2E invariants to detect cache drift; ops should compare
    # this to ``total_committed`` and alert on mismatch.
    total_committed_live = serializers.SerializerMethodField()
    cached_total_committed = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True, allow_null=True,
    )
    # Contract-driven commitments (live aggregate of ContractYearPlan rows
    # referencing this appropriation). New in the multi-year contract
    # feature; surfaces commitments that ``total_committed`` doesn't see.
    total_contract_committed = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    # Combined PO + Contract commitments — what the appropriation
    # dashboard's "Committed" column should render.
    total_all_committed = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    total_expended = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    available_balance = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    execution_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = Appropriation
        fields = [
            'id', 'fiscal_year', 'fiscal_year_label',
            'administrative', 'administrative_code', 'administrative_name',
            'economic', 'economic_code', 'economic_name',
            'functional', 'functional_code', 'functional_name',
            'programme', 'programme_code', 'programme_name',
            'fund', 'fund_code', 'fund_name',
            'geographic', 'geographic_code', 'geographic_name',
            'amount_approved', 'appropriation_type', 'status',
            'law_reference', 'enactment_date', 'description', 'notes',
            'total_warrants_released',
            'total_committed', 'cached_total_committed', 'total_committed_live',
            'total_contract_committed', 'total_all_committed',
            'total_expended', 'available_balance', 'execution_rate',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_total_committed_live(self, obj: Appropriation) -> str:
        """Live aggregate of open commitments — bypasses cache."""
        from decimal import Decimal
        from django.db.models import Sum
        live = obj.commitments.filter(
            status__in=['ACTIVE', 'INVOICED'],
        ).aggregate(total=Sum('committed_amount'))['total'] or Decimal('0')
        return str(live)

    def validate(self, attrs):
        """Business-rule pre-check: one active row per dimension tuple.

        The DB constraint is the ultimate guard, but catching the clash
        here gives the UI an actionable error — "use supplementary
        amendment instead of creating a new row" — rather than a raw
        IntegrityError.
        """
        # Only enforce on create or when status stays ACTIVE
        status_value = attrs.get('status') or (
            self.instance.status if self.instance else 'DRAFT'
        )
        if status_value != 'ACTIVE':
            return attrs

        keys = {
            'administrative': attrs.get('administrative') or (self.instance and self.instance.administrative),
            'economic':       attrs.get('economic')       or (self.instance and self.instance.economic),
            'fund':           attrs.get('fund')           or (self.instance and self.instance.fund),
            'fiscal_year':    attrs.get('fiscal_year')    or (self.instance and self.instance.fiscal_year),
        }
        if not all(keys.values()):
            return attrs

        clash_qs = Appropriation.objects.filter(
            status='ACTIVE', **keys,
        )
        if self.instance is not None:
            clash_qs = clash_qs.exclude(pk=self.instance.pk)
        existing = clash_qs.first()
        if existing is not None:
            raise serializers.ValidationError({
                'non_field_errors': [
                    f"An active appropriation already exists for "
                    f"{existing.administrative.code}/{existing.economic.code}/"
                    f"{existing.fund.code} in FY {existing.fiscal_year}. "
                    f"Use Supplementary Appropriation / Virement / Amendment "
                    f"to change the approved amount (NGN "
                    f"{existing.amount_approved:,.2f}) instead of creating a "
                    f"new row."
                ],
                'existing_appropriation_id': existing.pk,
            })
        return attrs

    def get_fiscal_year_label(self, obj: Appropriation) -> str:
        return str(obj.fiscal_year) if obj.fiscal_year else ''


class WarrantSerializer(serializers.ModelSerializer):
    appropriation_mda = serializers.CharField(
        source='appropriation.administrative.name', read_only=True,
    )
    appropriation_mda_code = serializers.CharField(
        source='appropriation.administrative.code', read_only=True,
    )
    appropriation_account = serializers.CharField(
        source='appropriation.economic.name', read_only=True,
    )
    # Economic code surfaces in the printout's Code column. Without
    # this, multi-line composite warrants would only show the name.
    appropriation_economic_code = serializers.CharField(
        source='appropriation.economic.code', read_only=True,
    )
    attachment_url = serializers.SerializerMethodField()
    # ── Live appropriation snapshot ────────────────────────────────────
    # Surfaces the fresh approved / committed / expended / available
    # figures alongside the warrant so list rows can render the
    # full budget context next to each AIE without a second round-trip.
    # Read from the denormalised cache columns when present, falling
    # through to the live aggregate properties when the cache is empty
    # (mirrors the model property behaviour).
    appropriation_amount_approved = serializers.SerializerMethodField()
    appropriation_total_committed = serializers.SerializerMethodField()
    appropriation_total_expended = serializers.SerializerMethodField()
    appropriation_available_balance = serializers.SerializerMethodField()
    appropriation_total_warrants_released = serializers.SerializerMethodField()

    # Real-time expiry overlay — see ``Warrant.effective_status`` for
    # the rules. Surfaced separately from ``status`` so the UI can
    # render the live state without losing the persisted value (useful
    # in audit views that want to see when a row was *last* persisted
    # vs. its current effective state).
    effective_status = serializers.CharField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    # Effective period bounds — used by the create form's date pickers
    # and the print layout's title block. ``required=False`` so legacy
    # rows with only a ``quarter`` value still serialize; the
    # ``fiscal_year_start_date`` / ``_end_date`` derived from the
    # appropriation are exposed so the frontend can default new
    # warrants to the full fiscal year (the "annual" default).
    effective_from = serializers.DateField(required=False)
    effective_to = serializers.DateField(required=False)
    fiscal_year_start_date = serializers.DateField(
        source='appropriation.fiscal_year.start_date', read_only=True,
    )
    fiscal_year_end_date = serializers.DateField(
        source='appropriation.fiscal_year.end_date', read_only=True,
    )

    class Meta:
        model = Warrant
        fields = [
            'id', 'appropriation', 'appropriation_mda', 'appropriation_mda_code',
            'appropriation_account', 'appropriation_economic_code',
            'quarter', 'effective_from', 'effective_to',
            'fiscal_year_start_date', 'fiscal_year_end_date',
            'amount_released', 'release_date',
            'authority_reference', 'issued_by', 'status',
            'effective_status', 'is_expired',
            'attachment', 'attachment_url', 'notes',
            'appropriation_amount_approved',
            'appropriation_total_committed',
            'appropriation_total_expended',
            'appropriation_available_balance',
            'appropriation_total_warrants_released',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'attachment_url',
            'effective_status', 'is_expired',
            'fiscal_year_start_date', 'fiscal_year_end_date',
            'appropriation_amount_approved',
            'appropriation_total_committed',
            'appropriation_total_expended',
            'appropriation_available_balance',
            'appropriation_total_warrants_released',
        ]

    def validate(self, attrs):
        """Run the model's clean() so ``effective_to >= effective_from``,
        the range-overlap rule and the cumulative-budget ceiling are
        enforced consistently across single-create, bulk-create and
        admin writes."""
        attrs = super().validate(attrs)
        instance = Warrant(
            **{k: v for k, v in attrs.items() if k != 'attachment'}
        )
        # Carry the existing pk on update so clean() excludes self
        # from the overlap check.
        if self.instance is not None:
            instance.pk = self.instance.pk
        instance.clean()
        return attrs

    def _appr(self, obj):
        return getattr(obj, 'appropriation', None)

    def get_appropriation_amount_approved(self, obj: Warrant) -> str:
        appr = self._appr(obj)
        return str(getattr(appr, 'amount_approved', '0') or '0')

    def get_appropriation_total_committed(self, obj: Warrant) -> str:
        appr = self._appr(obj)
        return str(getattr(appr, 'total_committed', '0') or '0')

    def get_appropriation_total_expended(self, obj: Warrant) -> str:
        appr = self._appr(obj)
        return str(getattr(appr, 'total_expended', '0') or '0')

    def get_appropriation_available_balance(self, obj: Warrant) -> str:
        appr = self._appr(obj)
        return str(getattr(appr, 'available_balance', '0') or '0')

    def get_appropriation_total_warrants_released(self, obj: Warrant) -> str:
        appr = self._appr(obj)
        return str(getattr(appr, 'total_warrants_released', '0') or '0')

    def get_attachment_url(self, obj: Warrant) -> str | None:
        if obj.attachment:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.attachment.url)
            return obj.attachment.url
        return None


class RevenueBudgetSerializer(serializers.ModelSerializer):
    administrative_name = serializers.CharField(
        source='administrative.name', read_only=True,
    )
    administrative_code = serializers.CharField(
        source='administrative.code', read_only=True,
    )
    economic_name = serializers.CharField(
        source='economic.name', read_only=True,
    )
    # Emit the economic code so the Revenue Budget list can render
    # "10000000 — Revenue" instead of just the bare name. Mirrors the
    # dual-identifier pattern used in Appropriation / Commitment /
    # Execution reports across the app.
    economic_code = serializers.CharField(
        source='economic.code', read_only=True,
    )
    fund_name = serializers.CharField(
        source='fund.name', read_only=True,
    )
    fund_code = serializers.CharField(
        source='fund.code', read_only=True,
    )
    actual_collected = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    variance = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True,
    )
    performance_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = RevenueBudget
        fields = [
            'id', 'fiscal_year', 'administrative', 'administrative_name', 'administrative_code',
            'economic', 'economic_name', 'economic_code', 'fund', 'fund_name', 'fund_code',
            'estimated_amount', 'monthly_spread', 'status',
            'actual_collected', 'variance', 'performance_rate',
            'description', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'administrative_code', 'administrative_name',
            'economic_code', 'economic_name',
            'fund_code', 'fund_name',
            'actual_collected', 'variance', 'performance_rate',
        ]


class BudgetValidationRequestSerializer(serializers.Serializer):
    """For the pre-expenditure validation endpoint."""
    administrative_id = serializers.IntegerField()
    economic_id = serializers.IntegerField()
    fund_id = serializers.IntegerField()
    fiscal_year_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)


class AppropriationVirementSerializer(serializers.ModelSerializer):
    """Virement — transfer approved amount between two Appropriation rows."""

    # Decorated labels for the list/detail view (user-facing strings)
    from_label = serializers.SerializerMethodField()
    to_label = serializers.SerializerMethodField()
    from_available = serializers.SerializerMethodField()
    to_available = serializers.SerializerMethodField()
    fiscal_year = serializers.IntegerField(
        source='from_appropriation.fiscal_year.year', read_only=True,
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = AppropriationVirement
        fields = [
            'id', 'reference_number',
            'from_appropriation', 'from_label', 'from_available',
            'to_appropriation', 'to_label', 'to_available',
            'amount', 'reason', 'fiscal_year',
            'status', 'status_display',
            'submitted_by', 'submitted_at',
            'approved_by', 'approved_at',
            'applied_at', 'rejection_reason',
            'from_balance_before', 'from_balance_after',
            'to_balance_before', 'to_balance_after',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'reference_number', 'status',
            'submitted_by', 'submitted_at',
            'approved_by', 'approved_at',
            'applied_at', 'rejection_reason',
            'from_balance_before', 'from_balance_after',
            'to_balance_before', 'to_balance_after',
            'created_at', 'updated_at',
        ]

    def get_from_label(self, obj):
        a = obj.from_appropriation
        return f"{a.administrative.code}/{a.economic.code}/{a.fund.code}"

    def get_to_label(self, obj):
        a = obj.to_appropriation
        return f"{a.administrative.code}/{a.economic.code}/{a.fund.code}"

    def get_from_available(self, obj):
        return str(obj.from_appropriation.available_balance)

    def get_to_available(self, obj):
        return str(obj.to_appropriation.available_balance)

    def validate(self, attrs):
        """Let the service do the heavy lifting — here we only catch
        the trivially wrong inputs so the user gets a DRF-shaped error."""
        src = attrs.get('from_appropriation')
        tgt = attrs.get('to_appropriation')
        if src and tgt and src.pk == tgt.pk:
            raise serializers.ValidationError({
                'to_appropriation':
                    'Source and target must be different appropriations.',
            })
        if src and tgt and src.fiscal_year_id != tgt.fiscal_year_id:
            raise serializers.ValidationError({
                'to_appropriation':
                    'Virement must be within the same fiscal year '
                    '(cross-year transfers require a Supplementary).',
            })
        amount = attrs.get('amount')
        if amount is not None and amount <= 0:
            raise serializers.ValidationError({
                'amount': 'Amount must be positive.',
            })
        if src and amount is not None and amount > src.available_balance:
            raise serializers.ValidationError({
                'amount': (
                    f'Source appropriation has only NGN {src.available_balance:,.2f} '
                    f'available (requested NGN {amount:,.2f}).'
                ),
            })
        return attrs


class WarrantPrintoutSettingsSerializer(serializers.ModelSerializer):
    """Tenant-wide warrant-printout configuration.

    All image fields ride alongside the JSON shape and accept multipart
    uploads on PATCH. The frontend renders the existing image as a small
    preview using the URL supplied on read; uploading a new file replaces
    it. Pass ``null`` (or an empty form value) to clear a slot.

    The reference PDF (``reference_pdf_template``) is a design artefact —
    operators upload the agreed sample warrant PDF so it stays linked to
    this configuration; the printout itself is rendered fresh from each
    warrant's actual data, never from the stored PDF.
    """

    letterhead_logo_url = serializers.SerializerMethodField()
    governor_signature_url = serializers.SerializerMethodField()
    finance_commissioner_signature_url = serializers.SerializerMethodField()
    accountant_general_signature_url = serializers.SerializerMethodField()
    reference_pdf_template_url = serializers.SerializerMethodField()

    class Meta:
        model = WarrantPrintoutSettings
        fields = [
            'id',
            # Letterhead
            'state_name', 'ministry_of_finance_name', 'office_address',
            'letterhead_logo', 'letterhead_logo_url',
            # Signatory: Governor
            'governor_name', 'governor_title',
            'governor_signature', 'governor_signature_url',
            # Signatory: Finance Commissioner
            'finance_commissioner_name', 'finance_commissioner_title',
            'finance_commissioner_signature',
            'finance_commissioner_signature_url',
            # Signatory: Accountant-General
            'accountant_general_name', 'accountant_general_title',
            'accountant_general_signature',
            'accountant_general_signature_url',
            # Footer + reference
            'footer_notes',
            'reference_pdf_template', 'reference_pdf_template_url',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        # Image / file fields are write-only on the form FK — read access
        # goes through the *_url method fields so the frontend gets a
        # ready-to-render absolute URL with the auth token.
        extra_kwargs = {
            'letterhead_logo': {'write_only': True, 'required': False},
            'governor_signature': {'write_only': True, 'required': False},
            'finance_commissioner_signature': {'write_only': True, 'required': False},
            'accountant_general_signature': {'write_only': True, 'required': False},
            'reference_pdf_template': {'write_only': True, 'required': False},
        }

    def _absolute(self, request, field):
        """Return absolute URL for an uploaded file, or None.

        Wrapping ``request.build_absolute_uri`` in a single helper keeps
        the five getters trivial and consistent. Falls back to a relative
        URL if no request is in context (rare — admin shell, mainly).
        """
        if not field:
            return None
        try:
            url = field.url
        except (ValueError, AttributeError):
            return None
        if request is None:
            return url
        return request.build_absolute_uri(url)

    def get_letterhead_logo_url(self, obj):
        return self._absolute(self.context.get('request'), obj.letterhead_logo)

    def get_governor_signature_url(self, obj):
        return self._absolute(self.context.get('request'), obj.governor_signature)

    def get_finance_commissioner_signature_url(self, obj):
        return self._absolute(
            self.context.get('request'),
            obj.finance_commissioner_signature,
        )

    def get_accountant_general_signature_url(self, obj):
        return self._absolute(
            self.context.get('request'),
            obj.accountant_general_signature,
        )

    def get_reference_pdf_template_url(self, obj):
        return self._absolute(
            self.context.get('request'),
            obj.reference_pdf_template,
        )
