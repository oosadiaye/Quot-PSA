"""
IPSAS 31 + IPSAS 33 register endpoints.

Two viewsets:

  * ``IntangibleAssetViewSet`` — IPSAS 31 register. CRUD + impair +
    dispose lifecycle actions.

  * ``OpeningBalanceSheetViewSet`` + ``OpeningBalanceItemViewSet`` —
    IPSAS 33 first-time-adoption register. The sheet supports a
    ``finalise`` action that posts a single JournalHeader with every
    item as a line and flips the sheet to FINALISED (immutable).
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounting.models import (
    IntangibleAsset, OpeningBalanceSheet, OpeningBalanceItem,
)


# =============================================================================
# IPSAS 31 — Intangible Assets
# =============================================================================

class IntangibleAssetSerializer(serializers.ModelSerializer):
    carrying_amount      = serializers.DecimalField(
        max_digits=22, decimal_places=2, read_only=True,
    )
    monthly_amortisation = serializers.DecimalField(
        max_digits=22, decimal_places=2, read_only=True,
    )
    is_fully_amortised   = serializers.BooleanField(read_only=True)
    category_display     = serializers.CharField(
        source='get_category_display', read_only=True,
    )
    status_display       = serializers.CharField(
        source='get_status_display', read_only=True,
    )
    amortisation_method_display = serializers.CharField(
        source='get_amortisation_method_display', read_only=True,
    )
    mda_code = serializers.CharField(source='mda.code', read_only=True, default=None)
    mda_name = serializers.CharField(source='mda.name', read_only=True, default=None)

    class Meta:
        model = IntangibleAsset
        fields = [
            'id', 'asset_number', 'name', 'description',
            'category', 'category_display',
            'acquisition_cost', 'acquisition_date',
            'useful_life_months', 'amortisation_method',
            'amortisation_method_display',
            'accumulated_amortisation', 'residual_value',
            'impairment_loss', 'last_impairment_review',
            'mda', 'mda_code', 'mda_name',
            'journal_entry',
            'status', 'status_display',
            'disposed_at', 'disposed_by',
            'notes',
            'carrying_amount', 'monthly_amortisation', 'is_fully_amortised',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id',
            'category_display', 'status_display', 'amortisation_method_display',
            'mda_code', 'mda_name',
            'carrying_amount', 'monthly_amortisation', 'is_fully_amortised',
            'disposed_at', 'disposed_by',
            'created_at', 'updated_at',
        ]


class IntangibleAssetViewSet(viewsets.ModelViewSet):
    """IPSAS 31 register + lifecycle."""
    queryset = IntangibleAsset.objects.all().select_related('mda', 'journal_entry')
    serializer_class = IntangibleAssetSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'category', 'amortisation_method', 'mda']
    ordering_fields = ['acquisition_date', 'acquisition_cost', 'asset_number']
    ordering = ['-acquisition_date']

    @action(detail=True, methods=['post'])
    def impair(self, request, pk=None):
        """Record an impairment loss (IPSAS 26 + IPSAS 31 ¶73).

        Body: ``{"amount": "<NGN>", "reason": "<non-empty>"}``. The
        amount is added to ``impairment_loss``; ``carrying_amount``
        drops by the same amount.
        """
        from django.utils import timezone

        asset: IntangibleAsset = self.get_object()
        try:
            amount = Decimal(str(request.data.get('amount', 0)))
        except Exception:
            return Response(
                {'error': 'amount must be a decimal number.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount <= 0:
            return Response(
                {'error': 'Impairment amount must be positive.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reason = (request.data.get('reason') or '').strip()
        if len(reason) < 10:
            return Response(
                {'error': 'A reason of at least 10 characters is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount > asset.carrying_amount:
            return Response(
                {
                    'error': (
                        f'Impairment of NGN {amount:,.2f} exceeds carrying '
                        f'amount NGN {asset.carrying_amount:,.2f}. IPSAS 26 '
                        f'caps the loss at carrying amount.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        asset.impairment_loss = (asset.impairment_loss or Decimal('0')) + amount
        asset.last_impairment_review = timezone.now().date()
        asset.status = 'IMPAIRED'
        asset.notes = (asset.notes + '\n' if asset.notes else '') + (
            f'Impairment NGN {amount:,.2f} recorded '
            f'on {asset.last_impairment_review}: {reason}'
        )
        asset.save(update_fields=[
            'impairment_loss', 'last_impairment_review',
            'status', 'notes', 'updated_at',
        ])
        return Response(self.get_serializer(asset).data)

    @action(detail=True, methods=['post'])
    def dispose(self, request, pk=None):
        """Dispose of an intangible asset (IPSAS 31 ¶106).

        Body: ``{"reason": "<non-empty>"}``. Flips status to DISPOSED
        and stamps disposed_at / disposed_by.
        """
        from django.utils import timezone

        asset: IntangibleAsset = self.get_object()
        if asset.status == 'DISPOSED':
            return Response(
                {'error': 'Asset is already disposed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reason = (request.data.get('reason') or '').strip()
        if len(reason) < 10:
            return Response(
                {'error': 'A reason of at least 10 characters is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        asset.status = 'DISPOSED'
        asset.disposed_at = timezone.now()
        asset.disposed_by = request.user if request.user.is_authenticated else None
        asset.notes = (asset.notes + '\n' if asset.notes else '') + (
            f'Disposed on {asset.disposed_at.date()} '
            f'by {getattr(asset.disposed_by, "username", "system")}: {reason}'
        )
        asset.save()
        return Response(self.get_serializer(asset).data)

    @action(detail=False, methods=['post'], url_path='run-amortisation')
    def run_amortisation(self, request):
        """Post monthly amortisation for every eligible intangible asset.

        Body: ``{"year": 2026, "month": 4, "dry_run": false}``.

        Idempotent: re-running for the same (year, month) skips
        already-stamped assets via the ``AMORT:YYYY-MM`` marker on
        each asset's ``notes`` field.

        Requires ``amortise_intangible_asset`` permission OR
        staff/superuser.
        """
        from accounting.services.intangible_amortisation import (
            IntangibleAmortisationService, AmortisationRunError,
        )

        user = request.user
        if not (
            user.is_authenticated and (
                user.is_superuser or user.is_staff
                or user.has_perm('accounting.amortise_intangible_asset')
            )
        ):
            return Response(
                {'error': 'You do not have permission to run amortisation.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            year = int(request.data.get('year'))
            month = int(request.data.get('month'))
        except (TypeError, ValueError):
            return Response(
                {'error': 'year and month are required integers.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        dry_run = bool(request.data.get('dry_run') or False)

        try:
            result = IntangibleAmortisationService.run_monthly(
                year=year, month=month, user=user, dry_run=dry_run,
            )
        except AmortisationRunError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'year':               result.year,
            'month':              result.month,
            'dry_run':            dry_run,
            'journal_id':         result.journal_id,
            'journal_reference':  result.journal_reference,
            'assets_posted':      result.assets_posted,
            'assets_skipped':     result.assets_skipped,
            'total_amortisation': str(result.total_amortisation),
            'skipped_details':    result.skipped_details,
        })


# =============================================================================
# IPSAS 33 — Opening Balance Sheet
# =============================================================================

class OpeningBalanceItemSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_type = serializers.CharField(source='account.account_type', read_only=True)
    deemed_cost_basis_display = serializers.CharField(
        source='get_deemed_cost_basis_display', read_only=True,
    )
    amount = serializers.DecimalField(
        max_digits=22, decimal_places=2, read_only=True,
    )

    class Meta:
        model = OpeningBalanceItem
        fields = [
            'id', 'sheet', 'account',
            'account_code', 'account_name', 'account_type',
            'debit', 'credit', 'amount',
            'deemed_cost_basis', 'deemed_cost_basis_display',
            'deemed_cost_rationale', 'supporting_document_ref',
            'memo',
        ]
        read_only_fields = [
            'id', 'account_code', 'account_name', 'account_type',
            'deemed_cost_basis_display', 'amount',
        ]


class OpeningBalanceSheetSerializer(serializers.ModelSerializer):
    items = OpeningBalanceItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_balanced = serializers.BooleanField(read_only=True)
    item_count = serializers.SerializerMethodField()
    finalised_by_username = serializers.SerializerMethodField()

    class Meta:
        model = OpeningBalanceSheet
        fields = [
            'id', 'transition_date', 'description',
            'status', 'status_display',
            'total_assets', 'total_liabilities', 'total_net_assets',
            'is_balanced',
            'finalised_at', 'finalised_by', 'finalised_by_username',
            'finalisation_journal',
            'transition_notes',
            'items', 'item_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id',
            'status_display', 'is_balanced', 'item_count',
            'total_assets', 'total_liabilities', 'total_net_assets',
            'finalised_at', 'finalised_by', 'finalised_by_username',
            'finalisation_journal',
            'items',
            'created_at', 'updated_at',
        ]

    def get_item_count(self, obj):
        return obj.items.count()

    def get_finalised_by_username(self, obj):
        return getattr(obj.finalised_by, 'username', None)


class OpeningBalanceSheetViewSet(viewsets.ModelViewSet):
    """IPSAS 33 opening balance sheet lifecycle."""
    queryset = OpeningBalanceSheet.objects.all().prefetch_related(
        'items__account',
    )
    serializer_class = OpeningBalanceSheetSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'transition_date']
    ordering = ['-transition_date']

    def perform_destroy(self, instance: OpeningBalanceSheet):
        if instance.status != 'DRAFT':
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                'Only DRAFT opening balance sheets can be deleted. '
                'Finalised sheets are immutable by IPSAS 33 design.'
            )
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        """Move DRAFT → REVIEWED. No structural change; freezes the sheet
        for finalisation-approval review."""
        sheet: OpeningBalanceSheet = self.get_object()
        if sheet.status != 'DRAFT':
            return Response(
                {'error': f'Sheet status is {sheet.status!r}, expected DRAFT.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sheet.status = 'REVIEWED'
        sheet.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(sheet).data)

    @action(detail=True, methods=['post'])
    def unreview(self, request, pk=None):
        """Move REVIEWED → DRAFT. Used if a reviewer sends the sheet back
        for amendment before finalisation."""
        sheet: OpeningBalanceSheet = self.get_object()
        if sheet.status != 'REVIEWED':
            return Response(
                {'error': f'Sheet status is {sheet.status!r}, expected REVIEWED.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sheet.status = 'DRAFT'
        sheet.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(sheet).data)

    @action(detail=True, methods=['post'])
    def finalise(self, request, pk=None):
        """Post the opening journal and lock the sheet.

        Creates one ``JournalHeader`` (posting_date = transition_date)
        with one ``JournalLine`` per ``OpeningBalanceItem``. Journal
        is immediately status='Posted' with ``source_module='ipsas_33_transition'``.
        Sheet flips to FINALISED.

        Pre-flight: the sum of debits must equal the sum of credits
        (±0.01). Refuses otherwise.

        Requires the ``finalise_opening_balance_sheet`` permission OR
        staff/superuser.
        """
        from django.db.models import Sum
        from django.utils import timezone
        from accounting.models import JournalHeader, JournalLine

        user = request.user
        if not (
            user.is_authenticated and (
                user.is_superuser or user.is_staff
                or user.has_perm('accounting.finalise_opening_balance_sheet')
            )
        ):
            return Response(
                {'error': 'You do not have permission to finalise opening balance sheets.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        sheet: OpeningBalanceSheet = self.get_object()
        if sheet.status == 'FINALISED':
            return Response(
                {'error': 'Sheet is already finalised.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        items = list(sheet.items.select_related('account').all())
        if not items:
            return Response(
                {'error': 'Cannot finalise: no items on the sheet.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Balance check — opening balances must be internally consistent.
        totals = sheet.items.aggregate(
            total_debit=Sum('debit'), total_credit=Sum('credit'),
        )
        total_debit = totals['total_debit'] or Decimal('0')
        total_credit = totals['total_credit'] or Decimal('0')
        if abs(total_debit - total_credit) > Decimal('0.01'):
            return Response(
                {
                    'error': (
                        f'Sheet is unbalanced: DR {total_debit:,.2f} vs '
                        f'CR {total_credit:,.2f}. Fix the items and retry.'
                    ),
                    'total_debit':  str(total_debit),
                    'total_credit': str(total_credit),
                    'difference':   str(total_debit - total_credit),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Aggregate totals by account-type for the sheet header.
        total_assets = Decimal('0')
        total_liabilities = Decimal('0')
        total_net_assets = Decimal('0')
        for item in items:
            at = (item.account.account_type or '').lower()
            if at == 'asset':
                total_assets += item.amount
            elif at in ('liability', 'liabilities'):
                total_liabilities += (-item.amount)  # credit positive
            elif at in ('equity', 'net_assets'):
                total_net_assets += (-item.amount)

        with transaction.atomic():
            header = JournalHeader.objects.create(
                posting_date=sheet.transition_date,
                description=(
                    f'IPSAS 33 Opening Balance Sheet — transition to '
                    f'accrual basis effective {sheet.transition_date}.'
                ),
                reference_number=f'OBS-{sheet.transition_date.isoformat()}',
                status='Draft',
                source_module='ipsas_33_transition',
                source_document_id=sheet.pk,
                posted_by=user,
            )
            JournalLine.objects.bulk_create([
                JournalLine(
                    header=header,
                    account=item.account,
                    debit=item.debit,
                    credit=item.credit,
                    memo=item.memo or (
                        f'IPSAS 33 OBS — {item.get_deemed_cost_basis_display()}'
                    ),
                )
                for item in items
            ])

            # Flip to Posted — triggers Sprint 1 invariants including
            # DB-level DR=CR check (already validated above).
            header.status = 'Posted'
            header.posted_at = timezone.now()
            header.save(update_fields=['status', 'posted_at'])

            sheet.status = 'FINALISED'
            sheet.finalised_at = timezone.now()
            sheet.finalised_by = user
            sheet.finalisation_journal = header
            sheet.total_assets = total_assets
            sheet.total_liabilities = total_liabilities
            sheet.total_net_assets = total_net_assets
            sheet.save()

        return Response({
            'message': (
                f'Opening balance sheet finalised. Journal '
                f'{header.reference_number} posted with '
                f'{len(items)} line(s).'
            ),
            'journal_id':         header.pk,
            'journal_reference':  header.reference_number,
            'sheet':              self.get_serializer(sheet).data,
        })


class OpeningBalanceItemViewSet(viewsets.ModelViewSet):
    """CRUD on individual items within a sheet."""
    queryset = OpeningBalanceItem.objects.all().select_related('sheet', 'account')
    serializer_class = OpeningBalanceItemSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['sheet', 'deemed_cost_basis', 'account']

    def _check_sheet_mutable(self, sheet: OpeningBalanceSheet):
        if sheet.status == 'FINALISED':
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                'Cannot modify items on a FINALISED opening balance sheet.'
            )

    def perform_create(self, serializer):
        self._check_sheet_mutable(serializer.validated_data['sheet'])
        serializer.save()

    def perform_update(self, serializer):
        self._check_sheet_mutable(serializer.instance.sheet)
        serializer.save()

    def perform_destroy(self, instance: OpeningBalanceItem):
        self._check_sheet_mutable(instance.sheet)
        super().perform_destroy(instance)
