from datetime import datetime
from decimal import InvalidOperation

import pandas as pd

from .common import (
    viewsets, status, Response, action, transaction, Decimal, AccountingPagination,
)
from ..models import (
    FixedAsset, JournalHeader, JournalLine, DepreciationSchedule,
    AssetClass, AssetConfiguration, AssetCategory, AssetLocation,
    AssetInsurance, AssetMaintenance, AssetTransfer,
    AssetDepreciationSchedule, AssetRevaluationRun, AssetDisposal, AssetImpairment, Account, TransactionSequence,
    DepreciationRunSchedule,
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

    def create(self, request, *args, **kwargs):
        """Override create to surface BudgetCheckRule warnings.

        The serializer's ``validate()`` runs ``check_policy`` against
        the (MDA, Economic, Fund) dimension tuple. STRICT violations
        already bubble up as a structured 400. WARNING-level hits
        (e.g. account has a WARNING rule AND no appropriation exists
        yet) are stored on the serializer as ``_bcr_warnings`` — we
        echo them back on the 201 response so the UI can show a soft
        banner without blocking the save.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        payload = dict(serializer.data)
        warnings = getattr(serializer, '_bcr_warnings', []) or []
        if warnings:
            payload['budget_warnings'] = warnings
        return Response(payload, status=status.HTTP_201_CREATED, headers=headers)

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

        # L4 fix: refuse to acquire (post a separate ACQ JV) when the
        # asset was already auto-capitalised from an AP invoice line.
        # ``apply_asset_capitalization`` stamps the source journal-line
        # FK on the asset; calling ``acquire`` on top would double-book
        # DR Asset / CR Cash for the same acquisition.
        if getattr(asset, 'created_from_journal_line_id', None):
            return Response(
                {"error": (
                    "Asset was already capitalised from a vendor invoice "
                    f"(JournalLine #{asset.created_from_journal_line_id}). "
                    "The acquisition GL entry has already been booked — "
                    "calling ``acquire`` again would double-book."
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
            "asset_ids": [1, 2, 3],   // optional — defaults to all eligible active assets
            "simulate": true           // true = preview only, false = post to GL
        }

        Eligibility: ``status='Active'`` AND ``acquisition_cost > 0``
        (only posted values can be depreciated). Single source of
        truth in ``accounting.services.depreciation.run_monthly_depreciation``
        — shared with the scheduled auto-run command.
        """
        from accounting.services.depreciation import run_monthly_depreciation as _run

        period_date = request.data.get('period_date')
        asset_ids = request.data.get('asset_ids', [])
        simulate = request.data.get('simulate', True)

        if not period_date:
            return Response({"error": "period_date is required."}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(period_date, str):
            period_date = datetime.strptime(period_date, '%Y-%m-%d').date()
        # Delegate to the shared service and return directly.
        return Response(_run(
            period_date=period_date,
            asset_ids=asset_ids or None,
            simulate=bool(simulate),
            user=request.user,
        ))

    # Legacy inline implementation retained below — unreachable after
    # the delegation above but kept as a commented-out reference for
    # anyone auditing the refactor.
    def _legacy_bulk_depreciation(self, request, period_date, asset_ids, simulate):

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

    # ─── Import / Export plumbing ─────────────────────────────────────────
    # Mirrors the comment-stripping + dtype=str defenses of
    # accounting/views/common.py:DimensionImportExportMixin so the asset-
    # category template carries a help block at the top, numeric-looking
    # codes survive Excel round-tripping intact, and blank cells become
    # empty strings instead of pandas NaN sentinel values.

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download a CSV template for bulk asset-category import."""
        import io
        import csv as _csv
        from django.http import HttpResponse

        help_lines = [
            'Asset Category import template.',
            'REQUIRED columns: code (max 20 chars), name (max 100 chars).',
            'OPTIONAL columns and defaults if blank:',
            '  cost_account_code                       — GL account that receives capitalised',
            '                                            cost when auto-create-asset fires.',
            '  accumulated_depreciation_account_code   — GL account credited by depreciation',
            '                                            posting (contra-asset).',
            '  depreciation_expense_account_code       — GL account debited by depreciation',
            '                                            posting (P&L).',
            '  depreciation_method (default Straight-Line) — one of: Straight-Line,',
            '                                                 Declining Balance, Double Declining Balance,',
            '                                                 Sum of Years Digits, Units of Production.',
            '  default_life_years (default 5)          — useful life in years.',
            '  residual_value_type (default percentage) — one of: percentage, amount.',
            '  residual_value (default 0)              — % of cost OR fixed amount.',
            '  is_active (default true)                — boolean.',
            '',
            'GL account columns are looked up by CODE (not numeric id) so the template is',
            'portable across tenants. Codes must already exist in the Chart of Accounts —',
            'the importer rejects rows pointing to missing accounts with a clear error.',
            'Re-uploading is idempotent: rows with an existing ``code`` are UPDATED in place.',
            'Lines starting with # (like these) are ignored on import.',
        ]

        cols = [
            'code', 'name',
            'cost_account_code',
            'accumulated_depreciation_account_code',
            'depreciation_expense_account_code',
            'depreciation_method', 'default_life_years',
            'residual_value_type', 'residual_value',
            'is_active',
        ]
        examples = [
            ['LAND',      'Land',                   '32100100', '',         '',         'Straight-Line', '0',   'percentage', '0',  'true'],
            ['BUILDINGS', 'Buildings',              '32200100', '32299100', '22250100', 'Straight-Line', '40',  'percentage', '5',  'true'],
            ['VEHICLES',  'Motor Vehicles',         '32300100', '32399100', '22250200', 'Straight-Line', '5',   'percentage', '10', 'true'],
            ['PLANT',     'Plant and Equipment',    '32400100', '32499100', '22250300', 'Straight-Line', '8',   'percentage', '5',  'true'],
            ['ICT',       'ICT Equipment',          '32500100', '32599100', '22250400', 'Straight-Line', '4',   'percentage', '10', 'true'],
            ['FURNITURE', 'Furniture and Fixtures', '32600100', '32699100', '22250500', 'Straight-Line', '7',   'percentage', '5',  'true'],
            ['LIBRARY',   'Library Books',          '32700100', '32799100', '22250600', 'Straight-Line', '5',   'percentage', '0',  'true'],
        ]

        output = io.StringIO()
        writer = _csv.writer(output)
        for line in help_lines:
            writer.writerow([f'# {line}'])
        writer.writerow(cols)
        for row in examples:
            writer.writerow(row)
        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="asset_category_import_template.csv"'
        return response

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        """Import or update asset categories from CSV / Excel."""
        from accounting.models.gl import Account
        import io as _io

        file = request.FILES.get('file')
        if not file:
            return Response(
                {'error': 'A CSV or Excel file is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if file.size > 5 * 1024 * 1024:
            return Response(
                {'error': 'File too large. Maximum 5MB allowed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        def _is_comment_cell(cell: str) -> bool:
            s = (cell or '').strip()
            return s.startswith('#') or s.startswith('"#') or s.startswith("'#")

        # Same protections as the dimension importer: dtype=str so codes don't
        # get float-promoted to '11000000.0', keep_default_na=False so blanks
        # come through as empty strings instead of NaN.
        try:
            if file.name.endswith('.xlsx'):
                df_raw = pd.read_excel(
                    file, header=None, nrows=10000, dtype=str,
                    keep_default_na=False, na_filter=False,
                )
                if df_raw.empty:
                    return Response({'error': 'The uploaded spreadsheet is empty.'},
                                    status=status.HTTP_400_BAD_REQUEST)
                header_idx = None
                for i in range(len(df_raw)):
                    first = str(df_raw.iloc[i, 0]) if df_raw.shape[1] else ''
                    if first and first.strip() and not _is_comment_cell(first):
                        header_idx = i
                        break
                if header_idx is None:
                    return Response(
                        {'error': "Could not find a header row (every row starts with '#')."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                cols = df_raw.iloc[header_idx].astype(str).tolist()
                df = df_raw.iloc[header_idx + 1:].reset_index(drop=True)
                df.columns = cols
                if not df.empty:
                    first_col = df.columns[0]
                    mask = df[first_col].astype(str).map(_is_comment_cell)
                    df = df[~mask].reset_index(drop=True)
            else:
                raw = file.read()
                text = raw.decode('utf-8-sig', errors='replace') if isinstance(raw, bytes) else str(raw)
                cleaned_lines = [ln for ln in text.splitlines() if not _is_comment_cell(ln)]
                if not cleaned_lines:
                    return Response(
                        {'error': 'The uploaded CSV is empty (or only contains comment lines).'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                df = pd.read_csv(
                    _io.StringIO('\n'.join(cleaned_lines)),
                    nrows=10000, dtype=str,
                    keep_default_na=False, na_filter=False,
                )
        except Exception as e:
            return Response(
                {'error': f'Failed to parse file: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        df.columns = df.columns.str.strip().str.lower()
        required = {'code', 'name'}
        missing = required - set(df.columns)
        if missing:
            return Response(
                {'error': f"Missing required columns: {', '.join(sorted(missing))}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_methods = {
            'Straight-Line', 'Declining Balance', 'Double Declining Balance',
            'Sum of Years Digits', 'Units of Production',
        }
        valid_residual = {'percentage', 'amount'}

        # Simple cache so we don't query the same Account by code repeatedly
        # across rows that share a cost / accumulated / expense GL.
        account_cache: dict[str, 'Account | None'] = {}
        def _resolve_account(code_str: str) -> 'Account | None':
            code_str = (code_str or '').strip()
            if not code_str:
                return None
            if code_str in account_cache:
                return account_cache[code_str]
            obj = Account.objects.filter(code=code_str).first()
            account_cache[code_str] = obj
            return obj

        def _str_cell(row, col, default=''):
            if col not in df.columns:
                return default
            v = row.get(col, '')
            return default if v in ('', None) else str(v).strip()

        def _bool_cell(row, col, default=True):
            if col not in df.columns:
                return default
            raw = str(row.get(col, '') or '').strip().lower()
            if raw == '':
                return default
            return raw in ('true', '1', 'yes', 'y', 'active')

        created = 0
        updated = 0
        errors: list[str] = []

        for idx, row in df.iterrows():
            row_num = idx + 2
            try:
                code = _str_cell(row, 'code')
                name = _str_cell(row, 'name')
                if not code or len(code) > 20:
                    errors.append(f"Row {row_num}: Invalid code '{code}' (1-20 chars).")
                    continue
                if not name or len(name) > 100:
                    errors.append(f"Row {row_num}: Invalid name (1-100 chars).")
                    continue

                method = _str_cell(row, 'depreciation_method', 'Straight-Line') or 'Straight-Line'
                if method not in valid_methods:
                    errors.append(
                        f"Row {row_num}: Invalid depreciation_method '{method}'. "
                        f"Must be one of: {', '.join(sorted(valid_methods))}."
                    )
                    continue

                residual_type = _str_cell(row, 'residual_value_type', 'percentage') or 'percentage'
                if residual_type not in valid_residual:
                    errors.append(
                        f"Row {row_num}: Invalid residual_value_type '{residual_type}'. "
                        f"Must be 'percentage' or 'amount'."
                    )
                    continue

                try:
                    life_years = int(_str_cell(row, 'default_life_years', '5') or '5')
                except (TypeError, ValueError):
                    errors.append(f"Row {row_num}: default_life_years must be a whole number.")
                    continue

                try:
                    residual_value = Decimal(_str_cell(row, 'residual_value', '0') or '0')
                except (TypeError, InvalidOperation):
                    errors.append(f"Row {row_num}: residual_value must be a decimal number.")
                    continue

                # GL account FKs — by code lookup. Empty cells are allowed
                # (the model has null=True on all three FKs).
                cost_acc = _resolve_account(_str_cell(row, 'cost_account_code'))
                if _str_cell(row, 'cost_account_code') and not cost_acc:
                    errors.append(
                        f"Row {row_num}: cost_account_code "
                        f"'{_str_cell(row, 'cost_account_code')}' not found in Chart of Accounts."
                    )
                    continue
                accum_acc = _resolve_account(_str_cell(row, 'accumulated_depreciation_account_code'))
                if _str_cell(row, 'accumulated_depreciation_account_code') and not accum_acc:
                    errors.append(
                        f"Row {row_num}: accumulated_depreciation_account_code "
                        f"'{_str_cell(row, 'accumulated_depreciation_account_code')}' not found."
                    )
                    continue
                expense_acc = _resolve_account(_str_cell(row, 'depreciation_expense_account_code'))
                if _str_cell(row, 'depreciation_expense_account_code') and not expense_acc:
                    errors.append(
                        f"Row {row_num}: depreciation_expense_account_code "
                        f"'{_str_cell(row, 'depreciation_expense_account_code')}' not found."
                    )
                    continue

                defaults = {
                    'name': name,
                    'depreciation_method': method,
                    'default_life_years': life_years,
                    'residual_value_type': residual_type,
                    'residual_value': residual_value,
                    'is_active': _bool_cell(row, 'is_active', True),
                    'cost_account': cost_acc,
                    'accumulated_depreciation_account': accum_acc,
                    'depreciation_expense_account': expense_acc,
                }
                obj, was_created = AssetCategory.objects.update_or_create(
                    code=code, defaults=defaults,
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

        return Response({
            'success': True,
            'created': created,
            'updated': updated,
            'skipped': 0,
            'errors': errors,
        })

    @action(detail=False, methods=['get'], url_path='export')
    def export_data(self, request):
        """Export every asset category as a CSV (re-importable round-trip)."""
        import io
        import csv as _csv
        from django.http import HttpResponse

        cols = [
            'code', 'name',
            'cost_account_code',
            'accumulated_depreciation_account_code',
            'depreciation_expense_account_code',
            'depreciation_method', 'default_life_years',
            'residual_value_type', 'residual_value',
            'is_active',
        ]
        output = io.StringIO()
        writer = _csv.writer(output)
        writer.writerow(cols)
        for cat in self.get_queryset():
            writer.writerow([
                cat.code,
                cat.name,
                cat.cost_account.code if cat.cost_account else '',
                cat.accumulated_depreciation_account.code if cat.accumulated_depreciation_account else '',
                cat.depreciation_expense_account.code if cat.depreciation_expense_account else '',
                cat.depreciation_method,
                cat.default_life_years,
                cat.residual_value_type,
                cat.residual_value,
                'true' if cat.is_active else 'false',
            ])
        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="asset_categories_export.csv"'
        return response


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


class DepreciationRunScheduleViewSet(viewsets.ModelViewSet):
    """CRUD + manual-trigger endpoint for the monthly auto-depreciation schedule.

    Typical flow:
      1. ``GET`` list → UI shows current schedule (usually one row)
      2. ``POST {'day_of_month': 1, 'is_active': true}`` → create
      3. ``POST .../{id}/run_now/`` → fire the run immediately
         without waiting for the cron / beat trigger (useful for
         catch-up or manual month-end close).
    """
    queryset = DepreciationRunSchedule.objects.all()
    # Auto-generate the serializer so we don't have to hand-write one
    # — simple models with no computed fields can use ModelSerializer
    # with ``fields = '__all__'`` directly.
    serializer_class = None  # set below via Meta hack

    def get_serializer_class(self):
        from rest_framework import serializers as _s

        class _Schedule(_s.ModelSerializer):
            class Meta:
                model = DepreciationRunSchedule
                fields = '__all__'
                read_only_fields = [
                    'last_run_at', 'last_run_period_date',
                    'last_run_assets_posted', 'last_run_total_amount',
                    'last_run_skipped', 'last_run_error',
                    'next_run_date', 'created_at', 'updated_at',
                ]
        return _Schedule

    @action(detail=True, methods=['post'], url_path='run-now')
    def run_now(self, request, pk=None):
        """Fire the schedule immediately (bypasses next_run_date).

        Body (all optional):
          * ``simulate`` (bool, default false) — dry-run preview
          * ``period_date`` (ISO date) — override the computed
            period-end (defaults to month-end of today)
        """
        from accounting.services.depreciation import (
            run_monthly_depreciation as _run,
        )
        from datetime import date as _d
        import calendar as _cal

        schedule = self.get_object()
        simulate = bool(request.data.get('simulate', False))
        period_raw = request.data.get('period_date')
        if period_raw:
            period = datetime.strptime(str(period_raw), '%Y-%m-%d').date()
        else:
            today = _d.today()
            last = _cal.monthrange(today.year, today.month)[1]
            period = _d(today.year, today.month, last)

        result = _run(
            period_date=period,
            asset_ids=None,
            simulate=simulate,
            user=request.user,
        )

        # Persist bookkeeping on live runs
        if not simulate:
            from django.utils import timezone as _tz
            summary = result.get('summary', {})
            schedule.last_run_at = _tz.now()
            schedule.last_run_period_date = period
            schedule.last_run_assets_posted = int(summary.get('posted', 0))
            schedule.last_run_total_amount = summary.get('total_amount', 0)
            schedule.last_run_skipped = int(summary.get('skipped', 0))
            schedule.last_run_error = ''
            # advance next_run_date by one month so scheduled cron
            # doesn't immediately re-fire the same period.
            day = min(schedule.day_of_month or 1, 28)
            if period.month == 12:
                schedule.next_run_date = _d(period.year + 1, 1, day)
            else:
                schedule.next_run_date = _d(period.year, period.month + 1, day)
            schedule.save()

        return Response({
            'schedule_id': schedule.pk,
            **result,
        })
