from datetime import datetime

from .common import (
    viewsets, status, Response, action, transaction, Decimal, AccountingPagination,
)
from ..models import (
    FixedAsset, JournalHeader, JournalLine, DepreciationSchedule,
    AssetClass, AssetConfiguration, AssetCategory, AssetLocation,
    AssetInsurance, AssetMaintenance, AssetTransfer,
    AssetDepreciationSchedule, AssetRevaluationRun, AssetDisposal, AssetImpairment, Account, TransactionSequence,
)
from ..serializers import (
    FixedAssetSerializer,
    AssetClassSerializer, AssetConfigurationSerializer, AssetCategorySerializer,
    AssetLocationSerializer, AssetInsuranceSerializer, AssetMaintenanceSerializer,
    AssetTransferSerializer, AssetDepreciationScheduleSerializer,
    AssetRevaluationRunSerializer, AssetDisposalSerializer, AssetImpairmentSerializer,
)
from core.mixins import OrganizationFilterMixin


class FixedAssetViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    """Fixed Asset management — MDA mandatory, budget check on acquisition."""
    org_filter_field = 'mda'
    queryset = FixedAsset.objects.all().select_related(
        'mda', 'fund', 'function', 'program', 'geo',
        'asset_account', 'depreciation_expense_account', 'accumulated_depreciation_account'
    )
    serializer_class = FixedAssetSerializer
    filterset_fields = ['status', 'asset_category', 'mda']
    search_fields = ['asset_number', 'name', 'description']

    @action(detail=True, methods=['post'])
    def acquire(self, request, pk=None):
        """Post asset acquisition to GL — validates capital budget first.

        Budget check: asset acquisition consumes capital appropriation
        (Economic code 3xxxxxxx). MDA + Fund + Account must have active
        appropriation with sufficient balance.
        """
        asset = self.get_object()

        if not asset.asset_account:
            return Response({"error": "Asset account not configured on this asset."}, status=status.HTTP_400_BAD_REQUEST)

        if not asset.mda:
            return Response({"error": "MDA is required for asset acquisition. Assign this asset to an MDA first."}, status=status.HTTP_400_BAD_REQUEST)

        # ── Budget Validation (capital budget check) ──────────────
        if asset.mda and asset.asset_account and asset.fund:
            try:
                from budget.services import BudgetValidationService, BudgetExceededError
                from accounting.models.ncoa import AdministrativeSegment, EconomicSegment, FundSegment
                from accounting.models.advanced import FiscalYear

                admin_seg = AdministrativeSegment.objects.filter(legacy_mda=asset.mda).first()
                econ_seg = EconomicSegment.objects.filter(legacy_account=asset.asset_account).first()
                fund_seg = FundSegment.objects.filter(legacy_fund=asset.fund).first()
                active_fy = FiscalYear.objects.filter(is_active=True).first()

                if admin_seg and econ_seg and fund_seg and active_fy:
                    try:
                        BudgetValidationService.validate_expenditure(
                            administrative_id=admin_seg.pk,
                            economic_id=econ_seg.pk,
                            fund_id=fund_seg.pk,
                            fiscal_year_id=active_fy.pk,
                            amount=asset.acquisition_cost,
                            source='ASSET_ACQUISITION',
                        )
                    except BudgetExceededError as e:
                        return Response(
                            {"error": f"Capital budget validation failed: {str(e)}"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
            except ImportError:
                pass  # Budget module not available

        # Determine credit account: use Cash or AP from request or settings
        from django.conf import settings as django_settings
        default_gl = getattr(django_settings, 'DEFAULT_GL_ACCOUNTS', {})
        credit_account_type = request.data.get('payment_method', 'cash')  # 'cash' or 'ap'

        if credit_account_type == 'ap':
            cr_code = default_gl.get('ACCOUNTS_PAYABLE', '')
            cr_account = Account.objects.filter(code=cr_code).first() if cr_code else None
            if not cr_account:
                cr_account = Account.objects.filter(account_type='Liability', name__icontains='Payable').first()
        else:
            cr_code = default_gl.get('CASH_ACCOUNT', '')
            cr_account = Account.objects.filter(code=cr_code).first() if cr_code else None
            if not cr_account:
                cr_account = Account.objects.filter(account_type='Asset', name__icontains='Cash').first()

        if not cr_account:
            return Response({"error": "Credit account (Cash/AP) not found."}, status=status.HTTP_400_BAD_REQUEST)

        acq_cost = asset.acquisition_cost
        if not acq_cost or acq_cost <= 0:
            return Response({"error": "Asset has no acquisition cost."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                journal = JournalHeader.objects.create(
                    reference_number=f"ACQ-{asset.asset_number or asset.id}",
                    description=f"Asset Acquisition: {asset.name}",
                    posting_date=request.data.get('acquisition_date', asset.acquisition_date) or datetime.now().date(),
                    fund=asset.fund,
                    function=asset.function,
                    program=asset.program,
                    geo=asset.geo,
                    status='Posted'
                )
                JournalLine.objects.create(
                    header=journal,
                    account=asset.asset_account,
                    debit=acq_cost,
                    credit=Decimal('0.00'),
                    memo=f"Fixed Asset acquisition: {asset.name}"
                )
                JournalLine.objects.create(
                    header=journal,
                    account=cr_account,
                    debit=Decimal('0.00'),
                    credit=acq_cost,
                    memo=f"Payment for asset: {asset.name}"
                )
                from accounting.services import update_gl_from_journal
                update_gl_from_journal(journal, fund=asset.fund, function=asset.function,
                                       program=asset.program, geo=asset.geo)

            return Response({
                "status": "Asset acquisition posted to GL.",
                "journal_id": journal.id,
                "asset_id": asset.id,
                "amount": str(acq_cost)
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def calculate_depreciation(self, request, pk=None):
        """Calculate and create depreciation schedule for an asset."""
        asset = self.get_object()
        period_date = request.data.get('period_date')

        if not period_date:
            return Response({"error": "period_date is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from datetime import datetime
            if isinstance(period_date, str):
                period_date = datetime.strptime(period_date, '%Y-%m-%d').date()

            annual_depreciation = asset.calculate_annual_depreciation()
            monthly_depreciation = annual_depreciation / 12

            from ..models import DepreciationSchedule
            schedule, created = DepreciationSchedule.objects.get_or_create(
                asset=asset,
                period_date=period_date,
                defaults={'depreciation_amount': monthly_depreciation}
            )

            if created:
                return Response({
                    "status": "Depreciation schedule created.",
                    "amount": str(monthly_depreciation)
                })
            else:
                return Response({"error": "Schedule already exists for this period."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def post_depreciation(self, request, pk=None):
        """Post depreciation — creates journal entry + updates GL balances."""
        asset = self.get_object()
        period_date = request.data.get('period_date')

        if not period_date:
            return Response({"error": "period_date is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not asset.depreciation_expense_account or not asset.accumulated_depreciation_account:
            return Response(
                {"error": "Asset must have both depreciation expense and accumulated depreciation accounts configured."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from datetime import datetime
            if isinstance(period_date, str):
                period_date = datetime.strptime(period_date, '%Y-%m-%d').date()

            from ..models import DepreciationSchedule
            schedule, created = DepreciationSchedule.objects.get_or_create(
                asset=asset,
                period_date=period_date,
                defaults={'depreciation_amount': asset.calculate_annual_depreciation() / 12}
            )

            if schedule.is_posted:
                return Response({"error": "Depreciation already posted for this period."}, status=status.HTTP_400_BAD_REQUEST)

            depreciation_amount = schedule.depreciation_amount

            with transaction.atomic():
                # Create journal entry for audit trail
                journal = JournalHeader.objects.create(
                    reference_number=f"DEP-{asset.asset_code}-{period_date.strftime('%Y%m')}",
                    description=f"Depreciation: {asset.asset_name} ({period_date.strftime('%b %Y')})",
                    posting_date=period_date,
                    fund=asset.fund,
                    function=asset.function,
                    program=asset.program,
                    geo=asset.geo,
                    status='Posted'
                )

                # Debit: Depreciation Expense
                JournalLine.objects.create(
                    header=journal,
                    account=asset.depreciation_expense_account,
                    debit=depreciation_amount,
                    credit=Decimal('0.00'),
                    memo=f"Depreciation expense: {asset.asset_name}"
                )

                # Credit: Accumulated Depreciation
                JournalLine.objects.create(
                    header=journal,
                    account=asset.accumulated_depreciation_account,
                    debit=Decimal('0.00'),
                    credit=depreciation_amount,
                    memo=f"Accumulated depreciation: {asset.asset_name}"
                )

                # Update GL balances (atomic F()-based)
                from accounting.services import update_gl_from_journal
                update_gl_from_journal(journal, fund=asset.fund, function=asset.function,
                                       program=asset.program, geo=asset.geo)

                # Update asset accumulated depreciation
                asset.accumulated_depreciation += depreciation_amount
                asset.save()

                # Link journal to schedule and mark posted
                schedule.journal_entry = journal
                schedule.is_posted = True
                schedule.save()

            return Response({
                "status": "Depreciation posted to GL successfully.",
                "journal_id": journal.id,
                "asset_id": asset.id,
                "amount": str(depreciation_amount),
                "accumulated": str(asset.accumulated_depreciation),
                "fiscal_year": period_date.year,
                "period": period_date.month
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='bulk-depreciation')
    def bulk_depreciation(self, request):
        """Bulk depreciation run with simulation mode.

        POST /fixed-assets/bulk-depreciation/
        {
            "period_date": "2026-03-31",
            "asset_ids": [1, 2, 3],   // optional — defaults to all active
            "simulate": true           // true = preview only, false = post to GL
        }
        """
        period_date = request.data.get('period_date')
        asset_ids = request.data.get('asset_ids', [])
        simulate = request.data.get('simulate', True)

        if not period_date:
            return Response({"error": "period_date is required."}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(period_date, str):
            period_date = datetime.strptime(period_date, '%Y-%m-%d').date()

        # Build queryset of eligible assets
        assets_qs = FixedAsset.objects.filter(status='Active').select_related(
            'fund', 'function', 'program', 'geo',
            'depreciation_expense_account', 'accumulated_depreciation_account',
        )
        if asset_ids:
            assets_qs = assets_qs.filter(id__in=asset_ids)

        results = []
        total_amount = Decimal('0.00')
        skipped = 0

        if simulate:
            # --- SIMULATION: read-only preview ---
            for asset in assets_qs:
                if not asset.depreciation_expense_account or not asset.accumulated_depreciation_account:
                    results.append({
                        'asset_id': asset.id,
                        'asset_number': asset.asset_number,
                        'asset_name': asset.name,
                        'depreciation_amount': '0.00',
                        'accumulated_after': str(asset.accumulated_depreciation),
                        'nbv_after': str(asset.net_book_value),
                        'status': 'skipped',
                        'journal_id': None,
                        'message': 'Missing GL account configuration',
                    })
                    skipped += 1
                    continue

                existing = DepreciationSchedule.objects.filter(
                    asset=asset, period_date=period_date, is_posted=True
                ).exists()
                if existing:
                    results.append({
                        'asset_id': asset.id,
                        'asset_number': asset.asset_number,
                        'asset_name': asset.name,
                        'depreciation_amount': '0.00',
                        'accumulated_after': str(asset.accumulated_depreciation),
                        'nbv_after': str(asset.net_book_value),
                        'status': 'already_posted',
                        'journal_id': None,
                        'message': 'Already posted for this period',
                    })
                    skipped += 1
                    continue

                annual = asset.calculate_annual_depreciation()
                monthly = (annual / 12).quantize(Decimal('0.01'))
                accumulated_after = asset.accumulated_depreciation + monthly
                nbv_after = asset.acquisition_cost - accumulated_after

                results.append({
                    'asset_id': asset.id,
                    'asset_number': asset.asset_number,
                    'asset_name': asset.name,
                    'depreciation_amount': str(monthly),
                    'accumulated_after': str(accumulated_after),
                    'nbv_after': str(nbv_after),
                    'status': 'success',
                    'journal_id': None,
                    'message': '',
                })
                total_amount += monthly

        else:
            # --- LIVE RUN: post to GL inside a transaction ---
            with transaction.atomic():
                fiscal_year = period_date.year
                period = period_date.month

                for asset in assets_qs:
                    if not asset.depreciation_expense_account or not asset.accumulated_depreciation_account:
                        results.append({
                            'asset_id': asset.id,
                            'asset_number': asset.asset_number,
                            'asset_name': asset.name,
                            'depreciation_amount': '0.00',
                            'accumulated_after': str(asset.accumulated_depreciation),
                            'nbv_after': str(asset.net_book_value),
                            'status': 'skipped',
                            'journal_id': None,
                            'message': 'Missing GL account configuration',
                        })
                        skipped += 1
                        continue

                    schedule, _ = DepreciationSchedule.objects.get_or_create(
                        asset=asset,
                        period_date=period_date,
                        defaults={'depreciation_amount': asset.calculate_annual_depreciation() / 12}
                    )

                    if schedule.is_posted:
                        results.append({
                            'asset_id': asset.id,
                            'asset_number': asset.asset_number,
                            'asset_name': asset.name,
                            'depreciation_amount': '0.00',
                            'accumulated_after': str(asset.accumulated_depreciation),
                            'nbv_after': str(asset.net_book_value),
                            'status': 'already_posted',
                            'journal_id': schedule.journal_entry_id,
                            'message': 'Already posted for this period',
                        })
                        skipped += 1
                        continue

                    depreciation_amount = schedule.depreciation_amount

                    journal = JournalHeader.objects.create(
                        reference_number=f"DEP-{asset.asset_number}-{period_date.strftime('%Y%m')}",
                        description=f"Depreciation: {asset.name} ({period_date.strftime('%b %Y')})",
                        posting_date=period_date,
                        fund=asset.fund,
                        function=asset.function,
                        program=asset.program,
                        geo=asset.geo,
                        status='Posted',
                    )

                    JournalLine.objects.create(
                        header=journal,
                        account=asset.depreciation_expense_account,
                        debit=depreciation_amount,
                        credit=Decimal('0.00'),
                        memo=f"Depreciation expense: {asset.name}",
                    )
                    JournalLine.objects.create(
                        header=journal,
                        account=asset.accumulated_depreciation_account,
                        debit=Decimal('0.00'),
                        credit=depreciation_amount,
                        memo=f"Accumulated depreciation: {asset.name}",
                    )

                    # Update GL balances (atomic F()-based)
                    from accounting.services import update_gl_from_journal
                    update_gl_from_journal(journal, fund=asset.fund, function=asset.function,
                                           program=asset.program, geo=asset.geo)

                    asset.accumulated_depreciation += depreciation_amount
                    asset.save()

                    schedule.journal_entry = journal
                    schedule.is_posted = True
                    schedule.save()

                    accumulated_after = asset.accumulated_depreciation
                    nbv_after = asset.acquisition_cost - accumulated_after

                    results.append({
                        'asset_id': asset.id,
                        'asset_number': asset.asset_number,
                        'asset_name': asset.name,
                        'depreciation_amount': str(depreciation_amount),
                        'accumulated_after': str(accumulated_after),
                        'nbv_after': str(nbv_after),
                        'status': 'success',
                        'journal_id': journal.id,
                        'message': '',
                    })
                    total_amount += depreciation_amount

        return Response({
            'mode': 'simulation' if simulate else 'posted',
            'period_date': str(period_date),
            'summary': {
                'total_assets': len(results),
                'total_amount': str(total_amount),
                'skipped': skipped,
            },
            'results': results,
        })


# =============================================================================
# ASSET SUB-VIEWSETS
# =============================================================================

class AssetClassViewSet(viewsets.ModelViewSet):
    queryset = AssetClass.objects.all().select_related(
        'asset_account', 'accumulated_depreciation_account',
        'depreciation_expense_account', 'disposal_gain_account', 'disposal_loss_account'
    )
    serializer_class = AssetClassSerializer
    filterset_fields = ['depreciation_method']
    search_fields = ['name', 'code']


class AssetConfigurationViewSet(viewsets.ModelViewSet):
    queryset = AssetConfiguration.objects.all()
    serializer_class = AssetConfigurationSerializer


class AssetCategoryViewSet(viewsets.ModelViewSet):
    queryset = AssetCategory.objects.all().select_related(
        'cost_account',
        'accumulated_depreciation_account', 'depreciation_expense_account',
    )
    serializer_class = AssetCategorySerializer
    filterset_fields = ['is_active', 'depreciation_method']
    search_fields = ['name', 'code']
    pagination_class = AccountingPagination


class AssetLocationViewSet(viewsets.ModelViewSet):
    queryset = AssetLocation.objects.all().select_related('parent', 'manager')
    serializer_class = AssetLocationSerializer
    filterset_fields = ['is_active']
    search_fields = ['name', 'code']


class AssetInsuranceViewSet(viewsets.ModelViewSet):
    queryset = AssetInsurance.objects.all().select_related('asset')
    serializer_class = AssetInsuranceSerializer
    filterset_fields = ['asset', 'is_active']


class AssetMaintenanceViewSet(viewsets.ModelViewSet):
    queryset = AssetMaintenance.objects.all().select_related('asset', 'vendor')
    serializer_class = AssetMaintenanceSerializer
    filterset_fields = ['asset', 'maintenance_type', 'status']


class AssetTransferViewSet(viewsets.ModelViewSet):
    queryset = AssetTransfer.objects.all().select_related(
        'asset', 'from_location', 'to_location',
        'from_employee', 'to_employee', 'approved_by'
    )
    serializer_class = AssetTransferSerializer
    filterset_fields = ['asset', 'transfer_date']


class AssetDepreciationScheduleViewSet(viewsets.ModelViewSet):
    queryset = AssetDepreciationSchedule.objects.all().select_related('asset', 'period')
    serializer_class = AssetDepreciationScheduleSerializer
    filterset_fields = ['asset', 'period_date', 'is_posted']


class AssetRevaluationViewSet(viewsets.ModelViewSet):
    queryset = AssetRevaluationRun.objects.all().select_related('approved_by')
    serializer_class = AssetRevaluationRunSerializer
    filterset_fields = ['status', 'revaluation_method']


class AssetDisposalViewSet(viewsets.ModelViewSet):
    queryset = AssetDisposal.objects.all().select_related('asset', 'approved_by')
    serializer_class = AssetDisposalSerializer
    filterset_fields = ['asset', 'status', 'disposal_method']

    @action(detail=True, methods=['post'])
    def post_disposal(self, request, pk=None):
        """Post asset disposal to GL - removes asset, records gain/loss."""
        disposal = self.get_object()

        if disposal.status == 'POSTED':
            return Response({"error": "Disposal already posted."}, status=status.HTTP_400_BAD_REQUEST)

        asset = disposal.asset
        if not asset:
            return Response({"error": "No asset linked to disposal."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                acq_cost = asset.acquisition_cost
                accum_depr = asset.accumulated_depreciation
                nbv = acq_cost - accum_depr
                proceeds = disposal.sale_proceeds or Decimal('0.00')
                gain_loss = proceeds - nbv

                disposal.acquisition_cost = acq_cost
                disposal.accum_depreciation = accum_depr
                disposal.net_book_value = nbv
                if gain_loss >= 0:
                    disposal.gain_on_disposal = gain_loss
                    disposal.loss_on_disposal = Decimal('0.00')
                else:
                    disposal.gain_on_disposal = Decimal('0.00')
                    disposal.loss_on_disposal = abs(gain_loss)

                # Create journal entry
                journal = JournalHeader.objects.create(
                    reference_number=f"DISP-{disposal.disposal_number}",
                    description=f"Asset Disposal: {asset.name} ({disposal.disposal_number})",
                    posting_date=disposal.disposal_date,
                    status='Posted',
                )
                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

                doc_num = journal.document_number

                # Dr Accumulated Depreciation (remove)
                if asset.accumulated_depreciation_account and accum_depr > 0:
                    JournalLine.objects.create(
                        header=journal, account=asset.accumulated_depreciation_account,
                        debit=accum_depr, credit=Decimal('0.00'),
                        memo=f"Remove accum depr: {asset.asset_number}", document_number=doc_num,
                    )

                # Dr Cash/Proceeds (if sale)
                if proceeds > 0:
                    from accounting.transaction_posting import get_gl_account
                    cash_account = get_gl_account('CASH_ACCOUNT', 'Asset', 'Cash')
                    if cash_account:
                        JournalLine.objects.create(
                            header=journal, account=cash_account,
                            debit=proceeds, credit=Decimal('0.00'),
                            memo=f"Disposal proceeds: {asset.asset_number}", document_number=doc_num,
                        )

                # Dr Loss on Disposal (if loss)
                if gain_loss < 0:
                    loss_account = Account.objects.filter(
                        name__icontains='Loss on Disposal', account_type='Expense',
                    ).first()
                    if not loss_account:
                        loss_account = Account.objects.filter(
                            account_type='Expense', name__icontains='Loss',
                        ).first()
                    if loss_account:
                        JournalLine.objects.create(
                            header=journal, account=loss_account,
                            debit=abs(gain_loss), credit=Decimal('0.00'),
                            memo=f"Loss on disposal: {asset.asset_number}", document_number=doc_num,
                        )

                # Cr Asset Account (remove from books)
                if asset.asset_account:
                    JournalLine.objects.create(
                        header=journal, account=asset.asset_account,
                        debit=Decimal('0.00'), credit=acq_cost,
                        memo=f"Remove asset: {asset.asset_number}", document_number=doc_num,
                    )

                # Cr Gain on Disposal (if gain)
                if gain_loss > 0:
                    gain_account = Account.objects.filter(
                        name__icontains='Gain on Disposal', account_type='Income',
                    ).first()
                    if not gain_account:
                        gain_account = Account.objects.filter(
                            account_type='Income', name__icontains='Gain',
                        ).first()
                    if gain_account:
                        JournalLine.objects.create(
                            header=journal, account=gain_account,
                            debit=Decimal('0.00'), credit=gain_loss,
                            memo=f"Gain on disposal: {asset.asset_number}", document_number=doc_num,
                        )

                # Update GL balances (atomic F()-based)
                from accounting.services import update_gl_from_journal
                update_gl_from_journal(journal)

                # Update asset status
                asset.status = 'Disposed'
                asset.save(update_fields=['status'])

                disposal.journal_id = journal.id
                disposal.status = 'POSTED'
                disposal.save()

            return Response({
                "status": "Asset disposal posted to GL successfully.",
                "journal_id": journal.id,
                "gain_loss": str(gain_loss),
                "nbv": str(nbv),
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AssetImpairmentViewSet(viewsets.ModelViewSet):
    queryset = AssetImpairment.objects.all().select_related('asset')
    serializer_class = AssetImpairmentSerializer
    filterset_fields = ['asset']
