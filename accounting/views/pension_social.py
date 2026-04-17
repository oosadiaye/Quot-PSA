"""
IPSAS 39 + IPSAS 42 register endpoints.

IPSAS 39 (pension):
  * ``PensionSchemeViewSet``       — scheme catalogue (DC + DB).
  * ``ActuarialValuationViewSet``  — annual valuations for DB schemes.
  * ``PensionContributionViewSet`` — monthly contribution records.

IPSAS 42 (social benefits):
  * ``SocialBenefitSchemeViewSet`` — welfare programmes.
  * ``SocialBenefitClaimViewSet``  — per-beneficiary claims with the
    PENDING → ELIGIBLE → APPROVED → PAID lifecycle.

All viewsets are standard DRF CRUD. The claim viewset adds three
lifecycle actions (``mark_eligible``, ``approve``, ``reject``) that
enforce the IPSAS 42 ¶31 recognition gate.
"""
from __future__ import annotations

from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounting.models import (
    PensionScheme, ActuarialValuation, PensionContribution,
    SocialBenefitScheme, SocialBenefitClaim,
)


# =============================================================================
# Pension (IPSAS 39)
# =============================================================================

class PensionSchemeSerializer(serializers.ModelSerializer):
    scheme_type_display = serializers.CharField(
        source='get_scheme_type_display', read_only=True,
    )
    status_display = serializers.CharField(
        source='get_status_display', read_only=True,
    )
    is_defined_benefit = serializers.BooleanField(read_only=True)

    class Meta:
        model = PensionScheme
        fields = [
            'id', 'code', 'name', 'description',
            'scheme_type', 'scheme_type_display',
            'coverage_note',
            'employee_contribution_rate', 'employer_contribution_rate',
            'established_date', 'status', 'status_display',
            'is_defined_benefit',
            'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'scheme_type_display', 'status_display',
            'is_defined_benefit', 'created_at', 'updated_at',
        ]


class PensionSchemeViewSet(viewsets.ModelViewSet):
    queryset = PensionScheme.objects.all()
    serializer_class = PensionSchemeSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['scheme_type', 'status']
    ordering = ['code']

    @action(detail=False, methods=['post'], url_path='run-monthly-accrual')
    def run_monthly_accrual(self, request):
        """Post the IPSAS 39 monthly pension accrual journal.

        Body: ``{"year": 2026, "month": 4, "dry_run": false}``.
        Runs across **all** active DB schemes — not per-scheme — since
        the accrual is a consolidated monthly posting.
        """
        from accounting.services.pension_accrual import (
            PensionAccrualService, PensionAccrualError,
        )

        try:
            year = int(request.data.get('year'))
            month = int(request.data.get('month'))
        except (TypeError, ValueError):
            return Response(
                {'error': 'year and month are required integers.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        dry_run = bool(request.data.get('dry_run', False))

        try:
            result = PensionAccrualService.run_monthly(
                year=year, month=month,
                user=request.user if request.user.is_authenticated else None,
                dry_run=dry_run,
            )
        except PensionAccrualError as exc:
            return Response(
                {'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'year':              result.year,
            'month':             result.month,
            'dry_run':           dry_run,
            'journal_id':        result.journal_id,
            'journal_reference': result.journal_reference,
            'schemes_posted':    result.schemes_posted,
            'schemes_skipped':   result.schemes_skipped,
            'total_accrual':     str(result.total_accrual),
            'skipped_details':   result.skipped_details,
        })


class ActuarialValuationSerializer(serializers.ModelSerializer):
    net_defined_benefit_liability = serializers.DecimalField(
        max_digits=22, decimal_places=2, read_only=True,
    )
    total_period_expense = serializers.DecimalField(
        max_digits=22, decimal_places=2, read_only=True,
    )
    scheme_code = serializers.CharField(source='scheme.code', read_only=True)
    scheme_name = serializers.CharField(source='scheme.name', read_only=True)
    valuation_method_display = serializers.CharField(
        source='get_valuation_method_display', read_only=True,
    )

    class Meta:
        model = ActuarialValuation
        fields = [
            'id', 'scheme', 'scheme_code', 'scheme_name',
            'valuation_date',
            'dbo', 'plan_assets',
            'service_cost', 'interest_cost',
            'past_service_cost', 'gain_on_settlement',
            'actuarial_gains_losses', 'return_on_plan_assets',
            'valuation_method', 'valuation_method_display',
            'discount_rate', 'salary_growth_rate',
            'pension_growth_rate', 'mortality_table',
            'assumptions_narrative',
            'valuer_firm', 'valuer_fellow', 'report_reference',
            'notes',
            # Derived.
            'net_defined_benefit_liability',
            'total_period_expense',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'scheme_code', 'scheme_name',
            'valuation_method_display',
            'net_defined_benefit_liability',
            'total_period_expense',
            'created_at', 'updated_at',
        ]

    def validate(self, attrs):
        """DB-only fields are ignored for DC schemes — flag if the user
        tries to record a valuation against a DC scheme."""
        scheme = attrs.get('scheme') or getattr(self.instance, 'scheme', None)
        if scheme and not scheme.is_defined_benefit:
            raise serializers.ValidationError({
                'scheme': (
                    f'Scheme {scheme.code!r} is Defined Contribution. '
                    f'Actuarial valuations only apply to Defined Benefit '
                    f'schemes (IPSAS 39 ¶30).'
                ),
            })
        return attrs


class ActuarialValuationViewSet(viewsets.ModelViewSet):
    queryset = ActuarialValuation.objects.all().select_related('scheme')
    serializer_class = ActuarialValuationSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['scheme', 'valuation_method', 'valuation_date']
    ordering = ['-valuation_date']


class PensionContributionSerializer(serializers.ModelSerializer):
    total_amount = serializers.DecimalField(
        max_digits=22, decimal_places=2, read_only=True,
    )
    scheme_code = serializers.CharField(source='scheme.code', read_only=True)

    class Meta:
        model = PensionContribution
        fields = [
            'id', 'scheme', 'scheme_code',
            'period_year', 'period_month',
            'headcount', 'employee_amount', 'employer_amount',
            'total_amount', 'journal_entry',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'scheme_code', 'total_amount', 'created_at', 'updated_at']


class PensionContributionViewSet(viewsets.ModelViewSet):
    queryset = PensionContribution.objects.all().select_related('scheme')
    serializer_class = PensionContributionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['scheme', 'period_year', 'period_month']
    ordering = ['-period_year', '-period_month']


# =============================================================================
# Social Benefits (IPSAS 42)
# =============================================================================

class SocialBenefitSchemeSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(
        source='get_category_display', read_only=True,
    )
    status_display = serializers.CharField(
        source='get_status_display', read_only=True,
    )

    class Meta:
        model = SocialBenefitScheme
        fields = [
            'id', 'code', 'name', 'description',
            'category', 'category_display',
            'eligibility_criteria',
            'standard_benefit_amount', 'payment_frequency',
            'start_date', 'end_date',
            'total_budget', 'funding_source',
            'status', 'status_display',
            'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'category_display', 'status_display',
            'created_at', 'updated_at',
        ]


class SocialBenefitSchemeViewSet(viewsets.ModelViewSet):
    queryset = SocialBenefitScheme.objects.all()
    serializer_class = SocialBenefitSchemeSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['category', 'status']
    ordering = ['code']


class SocialBenefitClaimSerializer(serializers.ModelSerializer):
    is_recognisable = serializers.BooleanField(read_only=True)
    scheme_code = serializers.CharField(source='scheme.code', read_only=True)
    scheme_name = serializers.CharField(source='scheme.name', read_only=True)
    status_display = serializers.CharField(
        source='get_status_display', read_only=True,
    )
    approved_by_username = serializers.SerializerMethodField()

    class Meta:
        model = SocialBenefitClaim
        fields = [
            'id', 'claim_reference',
            'scheme', 'scheme_code', 'scheme_name',
            'beneficiary_name', 'beneficiary_identifier',
            'beneficiary_phone', 'beneficiary_address',
            'period_year', 'period_month',
            'amount',
            'status', 'status_display',
            'eligible_date',
            'approved_at', 'approved_by', 'approved_by_username',
            'paid_at', 'payment_reference',
            'journal_entry',
            'notes',
            'is_recognisable',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'scheme_code', 'scheme_name', 'status_display',
            'approved_at', 'approved_by', 'approved_by_username',
            'paid_at', 'is_recognisable',
            'created_at', 'updated_at',
        ]

    def get_approved_by_username(self, obj):
        return getattr(obj.approved_by, 'username', None)


class SocialBenefitClaimViewSet(viewsets.ModelViewSet):
    queryset = SocialBenefitClaim.objects.all().select_related('scheme', 'approved_by')
    serializer_class = SocialBenefitClaimSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = [
        'scheme', 'status', 'period_year', 'period_month',
        'beneficiary_identifier',
    ]
    ordering = ['-period_year', '-period_month', 'claim_reference']

    @action(detail=True, methods=['post'])
    def mark_eligible(self, request, pk=None):
        """Flip PENDING → ELIGIBLE and stamp the eligible_date.

        IPSAS 42 ¶31 recognition starts at this point — the liability
        for the next single payment is now on the balance sheet.
        """
        claim: SocialBenefitClaim = self.get_object()
        if claim.status != 'PENDING':
            return Response(
                {'error': f'Claim status is {claim.status!r}, expected PENDING.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (claim.amount or Decimal('0')) <= 0:
            return Response(
                {'error': 'Claim amount must be positive to recognise.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        claim.status = 'ELIGIBLE'
        claim.eligible_date = timezone.now().date()
        claim.save(update_fields=['status', 'eligible_date', 'updated_at'])
        return Response(self.get_serializer(claim).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Flip ELIGIBLE → APPROVED. Ready for payment posting."""
        claim: SocialBenefitClaim = self.get_object()
        if claim.status != 'ELIGIBLE':
            return Response(
                {'error': f'Claim status is {claim.status!r}, expected ELIGIBLE.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        claim.status = 'APPROVED'
        claim.approved_at = timezone.now()
        claim.approved_by = request.user if request.user.is_authenticated else None
        claim.save(update_fields=[
            'status', 'approved_at', 'approved_by', 'updated_at',
        ])
        return Response(self.get_serializer(claim).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a claim at any pre-payment stage.

        Body: ``{"reason": "<non-empty>"}``. Rejection is terminal.
        """
        claim: SocialBenefitClaim = self.get_object()
        if claim.status in ('PAID', 'CANCELLED', 'REJECTED'):
            return Response(
                {'error': f'Cannot reject a claim in {claim.status!r} status.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reason = (request.data.get('reason') or '').strip()
        if len(reason) < 10:
            return Response(
                {'error': 'A reason of at least 10 characters is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        claim.status = 'REJECTED'
        claim.notes = (claim.notes + '\n' if claim.notes else '') + (
            f'Rejected by {getattr(request.user, "username", "system")} '
            f'on {timezone.now().date().isoformat()}: {reason}'
        )
        claim.save(update_fields=['status', 'notes', 'updated_at'])
        return Response(self.get_serializer(claim).data)

    @action(detail=False, methods=['post'], url_path='batch-pay')
    def batch_pay(self, request):
        """Combine APPROVED claims into one payment journal.

        Body::

            {
                "bank_account_code": "11101001",   # required
                "claim_ids": [1, 2, 3],            # optional; omit for "all approved"
                "posting_date": "2026-04-17",      # optional
                "payment_reference": "NIP-2026-000123",  # optional
                "dry_run": false
            }
        """
        from accounting.services.social_benefit_batch_pay import (
            SocialBenefitBatchPayService, SocialBenefitBatchPayError,
        )
        from datetime import date as _date

        bank_account_code = (request.data.get('bank_account_code') or '').strip()
        if not bank_account_code:
            return Response(
                {'error': 'bank_account_code is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_ids = request.data.get('claim_ids')
        claim_ids = None
        if raw_ids is not None:
            try:
                claim_ids = [int(x) for x in raw_ids]
            except (TypeError, ValueError):
                return Response(
                    {'error': 'claim_ids must be a list of integers.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        posting_date = None
        raw_date = request.data.get('posting_date')
        if raw_date:
            try:
                posting_date = _date.fromisoformat(str(raw_date))
            except ValueError:
                return Response(
                    {'error': 'posting_date must be YYYY-MM-DD.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        payment_reference = (request.data.get('payment_reference') or '').strip()
        dry_run = bool(request.data.get('dry_run', False))

        try:
            result = SocialBenefitBatchPayService.run_batch(
                bank_account_code=bank_account_code,
                posting_date=posting_date,
                claim_ids=claim_ids,
                payment_reference=payment_reference,
                user=request.user if request.user.is_authenticated else None,
                dry_run=dry_run,
            )
        except SocialBenefitBatchPayError as exc:
            return Response(
                {'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'posting_date':       result.posting_date.isoformat(),
            'bank_account_code':  result.bank_account_code,
            'dry_run':            dry_run,
            'journal_id':         result.journal_id,
            'journal_reference':  result.journal_reference,
            'claims_paid':        result.claims_paid,
            'claims_skipped':     result.claims_skipped,
            'total_paid':         str(result.total_paid),
            'paid_claim_ids':     result.paid_claim_ids,
            'skipped_details':    result.skipped_details,
        })
