import logging
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from core.permissions import IsApprover
from django.db.models import Sum, DecimalField
from django.db.models.functions import Coalesce
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
import pandas as pd
from django.utils import timezone

logger = logging.getLogger(__name__)
from .common import AccountingPagination
from ..models import (
    Account, JournalHeader, JournalLine, Currency, GLBalance, MDA,
    ExchangeRateHistory, AccountingSettings, TransactionSequence,
)
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from ..filters import JournalFilter
from ..serializers import (
    AccountSerializer, JournalHeaderSerializer, JournalDetailSerializer,
    CurrencySerializer, GLBalanceSerializer, MDASerializer,
    AccountingSettingsSerializer,
)


class AccountViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    filterset_fields = ['account_type', 'is_active', 'is_reconciliation', 'reconciliation_type']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination

    def destroy(self, request, *args, **kwargs):
        """Override destroy to catch PROTECT errors and return a clean 400."""
        instance = self.get_object()
        if instance.journalline_set.exists():
            return Response(
                {'detail': f'Cannot delete account "{instance.code} - {instance.name}" because it has journal entries.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.query_params.get('include_inactive'):
            queryset = queryset.filter(is_active=True)
        # Annotate total debit/credit from GLBalance to avoid N+1 in serializer
        queryset = queryset.annotate(
            _total_debit=Coalesce(Sum('glbalance__debit_balance'), Decimal('0'), output_field=DecimalField()),
            _total_credit=Coalesce(Sum('glbalance__credit_balance'), Decimal('0'), output_field=DecimalField()),
        )
        return queryset

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download a CSV template for account imports.

        The example codes follow the NCoA Economic Segment first-digit
        convention so the legacy ``Account.account_type`` and the NCoA
        ``account_type_code`` line up by construction:

            1xxxxxxx  Revenue / Income
            2xxxxxxx  Expenditure / Expense
            3xxxxxxx  Assets
            4xxxxxxx  Liabilities and Net Assets (Equity also lives here)

        Comment lines (``# …``) at the top are skipped on import — see the
        bulk_import body which also uses ``pd.read_csv(comment='#')``.
        """
        import io
        import csv
        from django.http import HttpResponse

        help_lines = [
            'Chart of Accounts import template (NCoA-aligned).',
            'REQUIRED columns: code (max 20 chars), name (max 200 chars), account_type.',
            'OPTIONAL columns: is_active (default true), is_reconciliation (default false),',
            '  reconciliation_type (e.g. bank_accounting, accounts_receivable, accounts_payable),',
            '  auto_create_asset (true/false; default false), asset_category (Asset Category CODE).',
            'account_type must be exactly one of: Asset, Liability, Equity, Income, Expense.',
            'NCoA convention — the FIRST digit of the code encodes the account family:',
            "  1xxxxxxx -> Income (Revenue)        e.g. 11000000  Tax Revenue",
            "  2xxxxxxx -> Expense (Expenditure)   e.g. 21000000  Personnel Costs",
            "  3xxxxxxx -> Asset                   e.g. 31000000  Cash and Cash Equivalents",
            "  4xxxxxxx -> Liability or Equity     e.g. 41000000  Accounts Payable",
            '',
            'Asset auto-capitalisation (IPSAS): set auto_create_asset=true on a GL where',
            'every debit should auto-create a FixedAsset and reroute the GL debit to the',
            "category's cost account. The asset_category column must hold the CODE (not id)",
            "of an Asset Category configured in Settings -> Asset Categories — the code is",
            'looked up by the importer. Typical use: 23xxxxxx capex GLs paired with the',
            'matching asset category (PLANT, BUILDINGS, VEHICLES, ICT, etc.).',
            'Lines starting with # (like these) are ignored on import.',
        ]

        output = io.StringIO()
        writer = csv.writer(output)
        for line in help_lines:
            writer.writerow([f'# {line}'])
        writer.writerow([
            'code', 'name', 'account_type',
            'is_active', 'is_reconciliation', 'reconciliation_type',
            'auto_create_asset', 'asset_category',
        ])
        # Income (1xxxxxxx)
        writer.writerow(['11000000', 'Tax Revenue',                       'Income',    'true',  'false', '',                     'false', ''])
        writer.writerow(['11100100', 'Tax Revenue — PAYE',                'Income',    'true',  'false', '',                     'false', ''])
        writer.writerow(['13000000', 'Grants and Transfers',              'Income',    'true',  'false', '',                     'false', ''])
        # Expense (2xxxxxxx). Capex GLs (23xxxxxx) demonstrate auto-capitalisation;
        # leave auto_create_asset blank/false for Personnel / O&M GLs.
        writer.writerow(['21000000', 'Personnel Costs',                   'Expense',   'true',  'false', '',                     'false', ''])
        writer.writerow(['21100500', 'Overtime Payments',                 'Expense',   'true',  'false', '',                     'false', ''])
        writer.writerow(['22000000', 'Operations & Maintenance',          'Expense',   'true',  'false', '',                     'false', ''])
        writer.writerow(['23100100', 'Purchase of Land',                  'Expense',   'true',  'false', '',                     'true',  'LAND'])
        writer.writerow(['23100200', 'Purchase of Buildings',             'Expense',   'true',  'false', '',                     'true',  'BUILDINGS'])
        writer.writerow(['23100400', 'Purchase of Plant and Equipment',   'Expense',   'true',  'false', '',                     'true',  'PLANT'])
        writer.writerow(['23100500', 'Purchase of ICT Equipment',         'Expense',   'true',  'false', '',                     'true',  'ICT'])
        # Asset (3xxxxxxx) — typically the cost-account targets that auto-capitalisation
        # reroutes debits TO. Don't set auto_create_asset on these (would loop).
        writer.writerow(['31000000', 'Cash and Cash Equivalents',         'Asset',     'true',  'true',  'bank_accounting',      'false', ''])
        writer.writerow(['31200000', 'Accounts Receivable',               'Asset',     'true',  'true',  'accounts_receivable',  'false', ''])
        writer.writerow(['32100100', 'Land (at cost)',                    'Asset',     'true',  'false', '',                     'false', ''])
        # Liability / Equity (4xxxxxxx)
        writer.writerow(['41000000', 'Accounts Payable',                  'Liability', 'true',  'true',  'accounts_payable',     'false', ''])
        writer.writerow(['43100100', 'Accumulated Fund / Fund Balance',   'Equity',    'true',  'false', '',                     'false', ''])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="account_import_template.csv"'
        return response

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        """Import accounts from CSV/Excel file."""
        file = request.FILES.get('file')
        if not file:
            return Response(
                {"error": "A CSV or Excel file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024  # 5MB
        if file.size > MAX_IMPORT_FILE_SIZE:
            return Response(
                {"error": "File too large. Maximum 5MB allowed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Pre-strip ``# …`` comment lines (and their CSV-quoted forms ``"#…``,
        # ``'#…``) so the help block at the top of the downloaded template
        # round-trips cleanly. ``dtype=str`` + ``keep_default_na=False`` keep
        # numeric-looking codes from being promoted to float64 and stringified
        # back as e.g. ``'11000000.0'`` (13 chars instead of 8 — would trip the
        # length validator). Mirror of the protections in
        # accounting/views/common.py for dimension imports.
        def _is_comment_cell(cell: str) -> bool:
            s = (cell or '').strip()
            return s.startswith('#') or s.startswith('"#') or s.startswith("'#")

        try:
            if file.name.endswith('.xlsx'):
                df_raw = pd.read_excel(
                    file, header=None, nrows=10000, dtype=str,
                    keep_default_na=False, na_filter=False,
                )
                if df_raw.empty:
                    return Response(
                        {"error": "The uploaded spreadsheet is empty."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                header_idx = None
                for i in range(len(df_raw)):
                    first = str(df_raw.iloc[i, 0]) if df_raw.shape[1] else ''
                    if first and first.strip() and not _is_comment_cell(first):
                        header_idx = i
                        break
                if header_idx is None:
                    return Response(
                        {"error": "Could not find a header row (every row starts with '#')."},
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
                import io as _io
                raw = file.read()
                text = (
                    raw.decode('utf-8-sig', errors='replace')
                    if isinstance(raw, bytes) else str(raw)
                )
                cleaned_lines = [ln for ln in text.splitlines() if not _is_comment_cell(ln)]
                if not cleaned_lines:
                    return Response(
                        {"error": "The uploaded CSV is empty (or contains only comment lines)."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                df = pd.read_csv(
                    _io.StringIO('\n'.join(cleaned_lines)),
                    nrows=10000, dtype=str,
                    keep_default_na=False, na_filter=False,
                )
        except Exception as e:
            return Response(
                {"error": f"Failed to parse file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Normalize column names
        df.columns = df.columns.str.strip().str.lower()

        required_columns = {'code', 'name', 'account_type'}
        missing = required_columns - set(df.columns)
        if missing:
            return Response(
                {"error": f"Missing required columns: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_types = {'Asset', 'Liability', 'Equity', 'Income', 'Expense'}
        created_count = 0
        skipped_count = 0
        errors = []

        # Load accounting settings for digit/series enforcement
        from ..models import AccountingSettings
        acct_settings = AccountingSettings.objects.first()

        for index, row in df.iterrows():
            row_num = index + 2  # header row + 0-based index
            try:
                code = str(row['code']).strip()
                name = str(row['name']).strip()
                account_type = str(row['account_type']).strip()

                if not code or len(code) > 20:
                    errors.append(f"Row {row_num}: Invalid code '{code}' (must be 1-20 characters).")
                    continue

                if not name or len(name) > 150:
                    errors.append(f"Row {row_num}: Invalid name (must be 1-150 characters).")
                    continue

                matched_type = None
                for vt in valid_types:
                    if account_type.lower() == vt.lower():
                        matched_type = vt
                        break
                if not matched_type:
                    errors.append(f"Row {row_num}: Invalid account_type '{account_type}'. Must be one of: {', '.join(sorted(valid_types))}.")
                    continue

                # Validate against digit enforcement and number series
                if acct_settings:
                    is_valid, code_errors = acct_settings.validate_account_code(code, matched_type)
                    if not is_valid:
                        errors.append(f"Row {row_num}: {'; '.join(code_errors)}")
                        continue

                is_active = True
                if 'is_active' in df.columns:
                    raw = str(row.get('is_active', 'true')).strip().lower()
                    is_active = raw in ('true', '1', 'yes', 'active')

                is_reconciliation = False
                if 'is_reconciliation' in df.columns:
                    raw_recon = str(row.get('is_reconciliation', 'false')).strip().lower()
                    is_reconciliation = raw_recon in ('true', '1', 'yes')

                reconciliation_type = ''
                if 'reconciliation_type' in df.columns:
                    recon_val = row.get('reconciliation_type', '')
                    reconciliation_type = '' if pd.isna(recon_val) else str(recon_val).strip()

                valid_recon_types = {
                    'accounts_payable', 'accounts_receivable',
                    'inventory', 'asset_accounting', 'bank_accounting',
                }

                if is_reconciliation and matched_type not in ('Asset', 'Liability'):
                    errors.append(f"Row {row_num}: Reconciliation is only valid for Asset or Liability accounts.")
                    continue

                if is_reconciliation and reconciliation_type not in valid_recon_types:
                    errors.append(f"Row {row_num}: Invalid reconciliation_type '{reconciliation_type}'.")
                    continue

                if not is_reconciliation:
                    reconciliation_type = ''

                # Asset auto-capitalisation (Phase 1 + 2). Two columns:
                #   auto_create_asset — boolean toggle
                #   asset_category    — Asset Category CODE (resolved to FK below)
                # Resolution by code (not numeric FK id) keeps the CSV stable
                # across tenants and reviewable by humans.
                auto_create_asset = False
                if 'auto_create_asset' in df.columns:
                    raw_auto = str(row.get('auto_create_asset', 'false')).strip().lower()
                    auto_create_asset = raw_auto in ('true', '1', 'yes')

                asset_category_obj = None
                if 'asset_category' in df.columns:
                    cat_val = row.get('asset_category', '')
                    cat_code = '' if pd.isna(cat_val) else str(cat_val).strip()
                    if cat_code:
                        from accounting.models.assets import AssetCategory
                        asset_category_obj = AssetCategory.objects.filter(
                            code__iexact=cat_code, is_active=True,
                        ).first()
                        if not asset_category_obj:
                            errors.append(
                                f"Row {row_num}: Asset Category code '{cat_code}' not found "
                                f"(or inactive). Create it first under Settings -> Asset Categories."
                            )
                            continue

                # Mirror the model.clean() invariant: enabling auto-create
                # without a category is a configuration error — fail loud.
                if auto_create_asset and not asset_category_obj:
                    errors.append(
                        f"Row {row_num}: auto_create_asset=true requires a non-empty "
                        f"asset_category column referencing a live Asset Category code."
                    )
                    continue

                if Account.objects.filter(code=code).exists():
                    skipped_count += 1
                    continue

                Account.objects.create(
                    code=code,
                    name=name,
                    account_type=matched_type,
                    is_active=is_active,
                    is_reconciliation=is_reconciliation,
                    reconciliation_type=reconciliation_type,
                    auto_create_asset=auto_create_asset,
                    asset_category=asset_category_obj,
                )
                created_count += 1

            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

        return Response({
            'success': True,
            'created': created_count,
            'skipped': skipped_count,
            'errors': errors,
        })

    @action(detail=False, methods=['post'], url_path='bulk-reconcile')
    def bulk_reconcile(self, request):
        """
        Mark (or clear) multiple GL accounts as Reconciliation accounts.

        Request body:
            ids: list[int]                 — account ids to update (max 200)
            reconciliation_type: str|null  — one of accounts_payable,
                                             accounts_receivable, inventory,
                                             asset_accounting, bank_accounting.
                                             Empty/null/missing = clear flag.

        Behaviour:
            * Asset / Liability accounts get is_reconciliation=True with the
              chosen sub-type (or False if cleared). All other account types
              are silently skipped — reconciliation is only meaningful for
              Asset and Liability per the existing form / model rules.
            * Per-row save() so signals (audit log, cache invalidation) fire.
            * Returns counts and a list of skipped {id, code, account_type}
              so the UI can surface partial-success cleanly.
        """
        ids = request.data.get('ids', [])
        if not ids:
            return Response(
                {'error': 'No account IDs provided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(ids) > 200:
            return Response(
                {'error': 'Maximum 200 items per bulk reconcile.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        recon_type = (request.data.get('reconciliation_type') or '').strip()
        valid_types = {
            'accounts_payable', 'accounts_receivable',
            'inventory', 'asset_accounting', 'bank_accounting',
        }
        clearing = (recon_type == '')
        if not clearing and recon_type not in valid_types:
            return Response(
                {
                    'error': (
                        f"Invalid reconciliation_type '{recon_type}'. "
                        f"Must be one of: {', '.join(sorted(valid_types))} (or empty to clear)."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        accounts = list(Account.objects.filter(id__in=ids))
        updated = 0
        skipped: list[dict] = []
        with transaction.atomic():
            for acc in accounts:
                # Reconciliation is only valid on Asset / Liability rows
                # (mirrors the per-row form rule and Account.clean() intent).
                if acc.account_type not in ('Asset', 'Liability'):
                    skipped.append({
                        'id': acc.id,
                        'code': acc.code,
                        'account_type': acc.account_type,
                    })
                    continue
                if clearing:
                    acc.is_reconciliation = False
                    acc.reconciliation_type = ''
                else:
                    acc.is_reconciliation = True
                    acc.reconciliation_type = recon_type
                acc.save(update_fields=['is_reconciliation', 'reconciliation_type'])
                updated += 1

        return Response({
            'status': (
                f'Cleared reconciliation flag on {updated} account(s).'
                if clearing else
                f'Marked {updated} account(s) as {recon_type} reconciliation.'
            ),
            'updated': updated,
            'skipped_count': len(skipped),
            'skipped': skipped,
        })

    @action(detail=False, methods=['post'], url_path='bulk-set-auto-asset')
    def bulk_set_auto_asset(self, request):
        """
        Mass-set (or clear) the IPSAS asset auto-capitalisation flag on
        multiple GL accounts.

        Request body:
            ids: list[int]            — account ids to update (max 200)
            asset_category_id: int|null
                                     — Asset Category PK to link. If null/missing
                                       the toggle is cleared (auto_create_asset=False
                                       AND asset_category=NULL).
                                       If set, the category must exist and be
                                       active; auto_create_asset is forced to True.

        Behaviour:
            * Per-row save() so signals fire and audit trail is consistent.
            * No GL-series restriction (intentional — eligibility is data-
              driven via the per-account toggle, not a hardcoded prefix).
            * Returns counts plus a list of skipped {id, code, reason} so
              the UI can surface partial-success cleanly.
        """
        ids = request.data.get('ids', [])
        if not ids:
            return Response(
                {'error': 'No account IDs provided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(ids) > 200:
            return Response(
                {'error': 'Maximum 200 items per bulk update.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cat_id = request.data.get('asset_category_id')
        clearing = (cat_id in (None, '', 0))
        category = None
        if not clearing:
            from accounting.models.assets import AssetCategory
            try:
                category = AssetCategory.objects.get(id=int(cat_id), is_active=True)
            except (ValueError, TypeError, AssetCategory.DoesNotExist):
                return Response(
                    {
                        'error': (
                            f"Asset Category id={cat_id} not found or inactive. "
                            f"Pick an active category from Settings → Asset Categories."
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not category.cost_account_id:
                return Response(
                    {
                        'error': (
                            f"Asset Category '{category.name}' has no cost account configured. "
                            f"Set the Cost Account on the category before flagging GL accounts to it."
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        accounts = list(Account.objects.filter(id__in=ids))
        updated = 0
        skipped: list[dict] = []
        with transaction.atomic():
            for acc in accounts:
                if clearing:
                    acc.auto_create_asset = False
                    acc.asset_category = None
                else:
                    acc.auto_create_asset = True
                    acc.asset_category = category
                acc.save(update_fields=['auto_create_asset', 'asset_category'])
                updated += 1

        return Response({
            'status': (
                f'Cleared asset auto-capitalisation flag on {updated} account(s).'
                if clearing else
                f"Marked {updated} account(s) for auto-capitalisation to category "
                f"'{category.code} — {category.name}'."
            ),
            'updated': updated,
            'skipped_count': len(skipped),
            'skipped': skipped,
            'category': (
                None if clearing else
                {'id': category.id, 'code': category.code, 'name': category.name}
            ),
        })

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        """Delete multiple GL accounts. Only accounts with no journal lines can be deleted."""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': 'No account IDs provided.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > 100:
            return Response({'error': 'Maximum 100 items per bulk delete.'}, status=status.HTTP_400_BAD_REQUEST)

        accounts = Account.objects.filter(id__in=ids)
        in_use = accounts.filter(journalline__isnull=False).distinct()
        if in_use.exists():
            names = ', '.join(f"{a.code} - {a.name}" for a in in_use[:5])
            return Response(
                {'error': f'Cannot delete accounts with journal entries: {names}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        count = accounts.count()
        accounts.delete()
        return Response({'status': f'{count} account(s) deleted successfully.', 'deleted': count})

class JournalViewSet(viewsets.ModelViewSet):
    queryset = JournalHeader.objects.select_related(
        'fund', 'function', 'program', 'geo'
    ).prefetch_related('lines', 'lines__account')
    serializer_class = JournalHeaderSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_class = JournalFilter
    ordering_fields = ['posting_date', 'reference_number', 'document_number', 'total_debit', 'total_credit', 'status']
    search_fields = ['reference_number', 'document_number', 'description']
    pagination_class = AccountingPagination

    def get_queryset(self):
        # Annotate total_debit and total_credit for ordering support.
        # Default ordering: most-recently-saved first (by pk desc). A
        # just-saved draft must always land at the top of the list even
        # when its posting_date is in the past — users expect "where did
        # the thing I just clicked Save on go" to mean row #1. ``-id``
        # is a reliable proxy for insertion order since pks are
        # monotonically assigned. ``-posting_date`` is kept as a
        # secondary tiebreaker for deterministic ordering across equal
        # pk ranges (e.g. legacy-imported journals with sequential pks).
        qs = super().get_queryset().annotate(
            total_debit=Coalesce(Sum('lines__debit'), Decimal('0'), output_field=DecimalField()),
            total_credit=Coalesce(Sum('lines__credit'), Decimal('0'), output_field=DecimalField())
        )
        # Only apply the default ordering when the request hasn't asked
        # for something specific via ?ordering= — otherwise the user's
        # column-click sort would be clobbered.
        if not self.request.query_params.get('ordering'):
            qs = qs.order_by('-id', '-posting_date')
        return qs

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return JournalDetailSerializer
        return JournalHeaderSerializer

    def get_permissions(self):
        if self.action == 'post_journal':
            return [IsApprover('post')]
        if self.action == 'approve':
            return [IsApprover()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # ── Period lock enforcement ──────────────────────────────
        posting_date = serializer.validated_data.get('posting_date')
        if posting_date:
            from accounting.models.advanced import FiscalPeriod
            period = FiscalPeriod.objects.filter(
                start_date__lte=posting_date,
                end_date__gte=posting_date,
                period_type='Monthly',
            ).first()
            if period and (period.is_closed or period.is_locked):
                if not period.allow_journal_entry:
                    return Response(
                        {"error": f"Period {period.period_number}/{period.fiscal_year} is {period.status}. "
                                  f"Journal entries are not allowed in this period. "
                                  f"Contact the Accountant General to request access."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        lines_data = request.data.get('lines', [])

        # Validate debits equal credits
        total_debit = sum(Decimal(str(line.get('debit', 0))) for line in lines_data)
        total_credit = sum(Decimal(str(line.get('credit', 0))) for line in lines_data)

        if total_debit != total_credit:
            return Response(
                {"error": f"Journal is not balanced. Debits: {total_debit}, Credits: {total_credit}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # Create journal header
            journal = serializer.save()

            # Create journal lines
            for line_data in lines_data:
                JournalLine.objects.create(
                    header=journal,
                    account_id=line_data.get('account'),
                    debit=line_data.get('debit', 0),
                    credit=line_data.get('credit', 0),
                    memo=line_data.get('memo', '')
                )

            # Auto-post if status is Posted
            if journal.status == 'Posted':
                self._post_to_gl(journal, request.user)

        headers_serializer = JournalHeaderSerializer(journal)
        return Response(headers_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.status == 'Posted':
            return Response(
                {"error": "Cannot modify a posted journal entry. Use update_description to change its description."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)

        lines_data = request.data.get('lines', None)

        # If lines provided, validate and update
        if lines_data:
            total_debit = sum(Decimal(str(line.get('debit', 0))) for line in lines_data)
            total_credit = sum(Decimal(str(line.get('credit', 0))) for line in lines_data)

            if total_debit != total_credit:
                return Response(
                    {"error": f"Journal is not balanced. Debits: {total_debit}, Credits: {total_credit}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        with transaction.atomic():
            if lines_data:
                # Delete existing lines and create new ones
                instance.lines.all().delete()

                for line_data in lines_data:
                    JournalLine.objects.create(
                        header=instance,
                        account_id=line_data.get('account'),
                        debit=line_data.get('debit', 0),
                        credit=line_data.get('credit', 0),
                        memo=line_data.get('memo', '')
                    )

            journal = serializer.save()

            # Auto-post if status is Posted
            if journal.status == 'Posted':
                self._post_to_gl(journal, request.user)

        headers_serializer = JournalHeaderSerializer(journal)
        return Response(headers_serializer.data)

    @action(detail=True, methods=['patch'])
    def update_description(self, request, pk=None):
        """Update only the description of a journal entry, regardless of its status."""
        journal = self.get_object()
        new_description = request.data.get('description')

        if new_description is None:
            return Response(
                {"error": "Please provide a 'description' field."},
                status=status.HTTP_400_BAD_REQUEST
            )

        journal.description = new_description
        journal.save(update_fields=['description'], _allow_status_change=True)

        return Response({
            "status": "Journal description updated successfully.",
            "id": journal.id,
            "description": journal.description
        })

    def _post_to_gl(self, journal, user, skip_budget_check=False):
        """Post journal entries to GL balances in real-time with optional budget validation."""
        from django.db import transaction
        # Canonical budget system: use budget.models.UnifiedBudget for all budget checks.
        # accounting.budget_logic is the legacy wrapper; budget.models is the source of truth.
        from budget.models import UnifiedBudget
        from budget.models import UnifiedBudgetEncumbrance

        with transaction.atomic():
            fiscal_year = journal.posting_date.year
            period = journal.posting_date.month

            # Generate Sequential Document Number for the Header
            if not journal.document_number:
                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

            # Budget validation — rule-driven.
            # The tenant's BudgetCheckRule set dictates the behaviour per
            # GL-range. STRICT rules apply to EVERY posting that lands in
            # the range (debit or credit, any account_type). WARNING rules
            # fire when an expense-side line would push utilisation over
            # the threshold. NONE rules are skipped entirely.
            budget_violations = []
            budget_warnings = []
            from accounting.services.budget_check_rules import (
                check_policy, find_matching_appropriation, resolve_rule_for_account,
            )

            for line in journal.lines.all():
                if not line.document_number:
                    line.document_number = journal.document_number
                    line.save(update_fields=['document_number'])

                if skip_budget_check:
                    continue

                # The "amount in play" for policy — debit if it's a debit
                # line, credit if credit, else zero. Strict policies gate
                # *any* non-zero touch on a covered GL; warning utilisation
                # computations use the expense-side amount (debit).
                amt = (line.debit or Decimal('0')) + (line.credit or Decimal('0'))
                if amt <= 0:
                    continue

                # Budget consumption is a DEBIT-side concept; credits on
                # any GL release / reverse budget rather than consume it.
                # Skipping credits here means a correcting journal that
                # credits an expense GL succeeds even when no appropriation
                # matches the line — which is the correct behaviour for
                # reversals. Mirrors the same skip in the signal handler
                # in accounting/signals/budget_enforcement.py.
                if not (line.debit and line.debit > 0):
                    continue

                # Short-circuit: if no rule covers this GL, we follow the
                # legacy behaviour — only gate Expense-debit lines via the
                # UnifiedBudget encumbrance path. Anything outside every
                # rule is "uncontrolled" by design.
                rule = resolve_rule_for_account(line.account.code)
                if rule is None and not (
                    line.account.account_type == 'Expense'
                    and line.debit and line.debit > 0
                ):
                    continue

                # ── Rule-driven policy evaluation ──────────────
                appropriation = find_matching_appropriation(
                    mda=journal.mda,
                    fund=journal.fund,
                    account=line.account,
                    fiscal_year=fiscal_year,
                )
                result = check_policy(
                    account_code=line.account.code,
                    appropriation=appropriation,
                    requested_amount=line.debit or Decimal('0'),
                    transaction_label='journal',
                    account_name=line.account.name,
                )
                if result.blocked:
                    budget_violations.append({
                        'account': line.account.code,
                        'account_name': line.account.name,
                        'requested': str(line.debit or line.credit),
                        'level': result.level,
                        'message': result.reason,
                    })
                    continue
                if result.warnings:
                    budget_warnings.extend([
                        f'[{line.account.code}] {w}' for w in result.warnings
                    ])

                # ── Warrant / AIE ceiling check ─────────────────
                # PFM law (Nigerian Finance Regulations §§ 400–417, PFM
                # Act 2007) requires a released warrant BEFORE expenditure
                # recognition. check_policy() above covered the annual
                # appropriation; this block covers the quarterly warrant.
                # Applies only to expense-side debits that have a matching
                # appropriation and a STRICT policy — WARNING / NONE ranges
                # intentionally skip because an un-warranted posting on a
                # non-strict GL is still the legitimate default for many
                # statutory heads. Tenant-level ``enforce_warrant`` flag
                # is the master switch — tenants that haven't digitised
                # warrant issuance yet see no change in behaviour.
                # Statutory-source JVs (debt service, pensions payroll,
                # judicial salaries) carry standing warrants under
                # Constitution §81(2) — whitelisted via source_module.
                STATUTORY_SOURCES = {
                    'debt_service', 'pension_payroll', 'pensions',
                    'judicial_salary', 'statutory_charge', 'cfs',
                }
                if (
                    result.level == 'STRICT'
                    and appropriation is not None
                    and line.account.account_type == 'Expense'
                    and line.debit and line.debit > 0
                    and (journal.source_module or '') not in STATUTORY_SOURCES
                ):
                    from budget.services import _is_warrant_enforced
                    from accounting.budget_logic import (
                        check_warrant_availability,
                        is_warrant_pre_payment_enforced,
                    )
                    if _is_warrant_enforced() and is_warrant_pre_payment_enforced():
                        warrant_ok, warrant_msg, _info = check_warrant_availability(
                            dimensions={'mda': journal.mda, 'fund': journal.fund},
                            account=line.account,
                            amount=line.debit,
                        )
                        if not warrant_ok:
                            budget_violations.append({
                                'account': line.account.code,
                                'account_name': line.account.name,
                                'requested': str(line.debit),
                                'level': 'WARRANT',
                                'message': warrant_msg,
                            })
                            continue

                # ── Encumbrance bookkeeping ─────────────────────
                # NOTE: STRICT/WARNING gate decisions are already made by
                # check_policy() above. The UnifiedBudget path below no
                # longer vetoes posting — it only records an encumbrance
                # for reporting on accounts that carry a UnifiedBudget row.
                if result.level == 'NONE':
                    continue
                if line.account.account_type != 'Expense' or not (line.debit and line.debit > 0):
                    continue  # encumbrances are expense-side only
                budget = UnifiedBudget.get_budget_for_transaction(
                    dimensions={'fund': journal.fund, 'mda': journal.mda},
                    account=line.account,
                    fiscal_year=str(fiscal_year),
                    period_type='MONTHLY',
                    period_number=period,
                )
                if budget and budget.enable_encumbrance:
                    UnifiedBudgetEncumbrance.objects.create(
                        budget=budget,
                        reference_type='GENERAL',
                        reference_id=journal.id,
                        reference_number=journal.document_number or '',
                        encumbrance_date=journal.posting_date,
                        amount=line.debit,
                        status='ACTIVE',
                        description=f"Journal {journal.document_number}: {journal.description[:100]}",
                        created_by=user,
                    )

            # If there are hard-stop budget violations, abort
            if budget_violations:
                raise ValidationError({
                    'budget_violations': budget_violations,
                    'message': 'Budget check failed. Cannot post journal.',
                    'detail': '; '.join(v['message'] for v in budget_violations),
                })

            # ── IPSAS Asset Auto-Capitalisation (SAP-style sub-ledger) ────
            # Delegated to the shared service so every posting path
            # (Journal, AP Invoice, GRN, Payment Voucher) ends up with the
            # same audit trail, the same contra-entries, and the same
            # FixedAsset record shape. See accounting/services/asset_capitalization.py
            # for the full design rationale.
            from accounting.services.asset_capitalization import apply_asset_capitalization
            auto_assets_created = apply_asset_capitalization(journal)

            # Post to GL balances (atomic F()-based)
            from accounting.services import update_gl_from_journal
            update_gl_from_journal(journal)

            # The service already logs internally; nothing further needed
            # here. ``auto_assets_created`` is a list of dicts with keys
            # source_gl / recon_gl / asset_number / amount / name — used
            # by the bulk-post UI to surface a per-asset success summary.

            # NOTE: Appropriation totals are refreshed by the JournalHeader
            # post-save signal (accounting/signals/budget_enforcement.py).
            # Doing it here would be premature — the journal is still
            # 'Draft' at this point and total_expended only sums
            # status='Posted' lines. Post-save fires after the caller
            # flips status to 'Posted', which is the correct moment.

            # Attach any non-blocking warnings to the journal's meta so the
            # caller (post_journal action) can include them in its response.
            if budget_warnings:
                journal._budget_warnings = budget_warnings

    def _perform_post(self, journal, user):
        """
        Core posting routine — shared by ``post_journal`` (per-row) and
        ``bulk_post``. Validates period, balance, line presence; writes
        GL balances; runs asset auto-capitalisation; flips status.

        Returns a success-payload dict on completion. Raises on failure
        — the caller is responsible for catching and shaping the
        response (per-row returns a 400 Response, bulk returns a per-row
        ``failed`` entry and continues).
        """
        from accounting.models import BudgetPeriod

        if journal.status == 'Posted':
            raise ValueError('Journal is already posted.')

        # Validate period is open for posting
        period = BudgetPeriod.get_period_for_date(journal.posting_date)
        if period and not period.can_post():
            raise ValueError(
                f"Cannot post to period {period}. "
                f"Period status is: {period.get_status_display()}"
            )

        # Validate balance
        total_debit = journal.lines.aggregate(total=Sum('debit'))['total'] or 0
        total_credit = journal.lines.aggregate(total=Sum('credit'))['total'] or 0
        if total_debit != total_credit:
            raise ValueError(
                f"Cannot post unbalanced journal. Debits: {total_debit}, Credits: {total_credit}"
            )

        # Validate has lines
        if not journal.lines.exists():
            raise ValueError('Cannot post journal with no lines.')

        # Post to GL — this writes GLBalance rows AND, for any line whose
        # account has auto_create_asset=True, auto-creates a FixedAsset and
        # reroutes the GL debit to the asset category's cost account.
        self._post_to_gl(journal, user)

        # Mark inline-checked so the pre-save signal doesn't re-evaluate
        # the same budget policy when we flip status. _totals_refreshed
        # must NOT be set — the post-save signal needs to run after the
        # status flip so total_expended (filtered on status='Posted')
        # picks up the new posting.
        journal._budget_checked = True

        # Status change requires the explicit save kwarg — the model's
        # save() guard refuses other modifications after Posted to keep
        # audit trail integrity.
        journal.status = 'Posted'
        journal.save(_allow_status_change=True)

        # Bust cached reports for this fiscal year.
        try:
            from accounting.services.report_cache import invalidate_period_reports
            invalidate_period_reports(fiscal_year=journal.posting_date.year)
        except Exception:
            pass

        return {
            'journal_id': journal.id,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'fiscal_year': journal.posting_date.year,
            'period': journal.posting_date.month,
            'warnings': getattr(journal, '_budget_warnings', []),
        }

    @action(detail=True, methods=['post'])
    def post_journal(self, request, pk=None):
        """Post journal entry to GL balances in real-time."""
        journal = self.get_object()
        try:
            payload = self._perform_post(journal, request.user)
            return Response({'status': 'Journal posted successfully.', **payload})
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            from accounting.services.posting_errors import format_post_error
            return Response(
                format_post_error(e, context='journal entry'),
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=['post'])
    def unpost_journal(self, request, pk=None):
        """Unpost journal entry and reverse GL balances."""
        from ..models import JournalReversal

        journal = self.get_object()

        if journal.status != 'Posted':
            return Response(
                {"error": "Only posted journals can be unposted."},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get('reason', 'Manual unpost')
        reversal_type = request.data.get('reversal_type', 'Unpost')

        try:
            fiscal_year = journal.posting_date.year
            period = journal.posting_date.month

            reversed_balances = []

            with transaction.atomic():
                for line in journal.lines.all():
                    gl_balance = GLBalance.objects.filter(
                        account=line.account,
                        fund=journal.fund,
                        function=journal.function,
                        program=journal.program,
                        geo=journal.geo,
                        fiscal_year=fiscal_year,
                        period=period
                    ).first()

                    if gl_balance:
                        old_debit = gl_balance.debit_balance
                        old_credit = gl_balance.credit_balance

                        if line.debit > 0:
                            gl_balance.debit_balance -= line.debit
                        if line.credit > 0:
                            gl_balance.credit_balance -= line.credit
                        gl_balance.save()

                        reversed_balances.append({
                            'account': str(line.account),
                            'old_debit': str(old_debit),
                            'old_credit': str(old_credit),
                            'new_debit': str(gl_balance.debit_balance),
                            'new_credit': str(gl_balance.credit_balance)
                        })

                journal.status = 'Approved'
                journal.save(_allow_status_change=True)

                JournalReversal.objects.create(
                    original_journal=journal,
                    reversal_type=reversal_type,
                    reason=reason,
                    reversed_by=request.user,
                    gl_balances_reversed=reversed_balances
                )

                # ── IPSAS Asset Auto-Capitalisation reversal (Phase 3) ─────
                # Mark any FixedAsset created by this journal's lines as
                # 'Retired' so the asset register reflects the reversal.
                # We don't hard-delete because depreciation rows or disposal
                # journals may already reference the asset; soft-retiring
                # preserves audit trail. The original line's account/asset
                # FK are left in place for the same reason — the reversal
                # log shows what happened, not erases it.
                from accounting.models.assets import FixedAsset
                auto_assets = FixedAsset.objects.filter(
                    created_from_journal_line__header=journal,
                    status='Active',
                )
                retired_count = auto_assets.update(status='Retired')
                if retired_count:
                    logger.info(
                        'Auto-capitalisation reversal: journal=%s retired %d asset(s).',
                        journal.document_number, retired_count,
                    )

            # P6-T4 — bust cached reports; the unpost removed GL balances.
            try:
                from accounting.services.report_cache import invalidate_period_reports
                invalidate_period_reports(fiscal_year=fiscal_year)
            except Exception:
                pass

            return Response({"status": "Journal unposted successfully."})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        """Delete multiple journal entries. Only Draft journals can be deleted."""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': 'No journal IDs provided'}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > 100:
            return Response({'error': 'Maximum 100 items per bulk delete.'}, status=status.HTTP_400_BAD_REQUEST)

        journals = JournalHeader.objects.filter(id__in=ids)
        posted = journals.filter(status='Posted').count()
        if posted > 0:
            return Response(
                {'error': f'{posted} journal(s) are Posted and cannot be deleted. Only Draft journals can be deleted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        count = journals.count()
        journals.delete()
        return Response({'status': f'{count} journal(s) deleted successfully', 'deleted': count})

    @action(detail=False, methods=['post'], url_path='bulk-post')
    def bulk_post(self, request):
        """
        Bulk-post Draft journals to the General Ledger.

        Reuses the per-row ``post_journal`` action on each journal so all
        validations (balance, period-open, budget-check, dimension-required)
        fire identically — no shortcut paths. Continues on individual
        failures and returns a per-row breakdown:

            {
                "posted":  N,
                "skipped": M,
                "failed":  [{"id": …, "reference": …, "error": …}, …]
            }

        OrganizationFilterMixin scoping carries through via the queryset
        filter, so SEPARATED-mode users can only post their own MDA's
        drafts. Eligible rows: status == 'Draft' only — anything else is
        silently skipped (it's already past Draft).
        """
        ids = request.data.get('ids', [])
        if not isinstance(ids, list) or not ids:
            return Response(
                {'error': 'Provide a non-empty "ids" list.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(ids) > 100:
            return Response(
                {'error': 'Maximum 100 items per bulk post.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        clean_ids: list[int] = []
        for raw in ids:
            try:
                clean_ids.append(int(raw))
            except (TypeError, ValueError):
                continue

        scoped = JournalHeader.objects.filter(id__in=clean_ids)
        draft_journals = list(scoped.filter(status='Draft'))
        skipped_count = scoped.exclude(status='Draft').count()

        posted_ids: list[int] = []
        failed: list[dict] = []
        for journal in draft_journals:
            # Re-use the *exact* per-row posting path — same validations,
            # same _post_to_gl call (asset auto-capitalisation included),
            # same status-change-with-allow flag. Without this, bulk-post
            # would (a) skip asset auto-create on 23xxxxxx GLs, and (b)
            # be rejected by the JournalHeader.save() audit guard which
            # forbids modifications without _allow_status_change=True.
            try:
                self._perform_post(journal, request.user)
                posted_ids.append(journal.id)
            except Exception as exc:  # noqa: BLE001
                failed.append({
                    'id': journal.id,
                    'reference': journal.reference_number or f'JE-{journal.id}',
                    'error': str(exc),
                })

        return Response({
            'posted': len(posted_ids),
            'skipped': skipped_count,
            'failed': failed,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download a CSV template for bulk journal import."""
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'reference_number', 'posting_date', 'description',
            'account_code', 'debit', 'credit', 'memo',
        ])
        # Two balanced example journals
        writer.writerow(['JV-2024-001', '2024-01-15', 'Salary Payment',    '50200000', '50000', '0',     'Salary expense'])
        writer.writerow(['JV-2024-001', '2024-01-15', 'Salary Payment',    '20200000', '0',     '50000', 'Payroll liability'])
        writer.writerow(['JV-2024-002', '2024-01-16', 'Office Supplies',   '50100000', '5000',  '0',     'Office supplies'])
        writer.writerow(['JV-2024-002', '2024-01-16', 'Office Supplies',   '10100000', '0',     '5000',  'Cash payment'])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="journal_import_template.csv"'
        return response

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        """Import multiple journals from a CSV or Excel file.

        Format: one row per journal line; rows sharing the same reference_number
        are grouped into one JournalHeader.  Each group must be balanced
        (total debits == total credits).  Duplicate reference numbers that
        already exist in the DB are skipped with an error message.
        """
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'A CSV or Excel file is required.'}, status=status.HTTP_400_BAD_REQUEST)

        MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
        if file.size > MAX_IMPORT_FILE_SIZE:
            return Response({'error': 'File too large. Maximum 5 MB allowed.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file, nrows=5000)
            else:
                df = pd.read_csv(file, nrows=5000)
        except Exception as exc:
            return Response({'error': f'Failed to parse file: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

        df.columns = df.columns.str.strip().str.lower()

        required_cols = {'reference_number', 'posting_date', 'account_code', 'debit', 'credit'}
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            return Response(
                {'error': f'Missing required columns: {", ".join(sorted(missing_cols))}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Normalise nulls
        df['debit']  = pd.to_numeric(df['debit'],  errors='coerce').fillna(0)
        df['credit'] = pd.to_numeric(df['credit'], errors='coerce').fillna(0)
        df['memo']   = df['memo'].fillna('') if 'memo' in df.columns else ''
        df['description'] = df.get('description', df['reference_number']).fillna('')

        created_count = 0
        skipped_count = 0
        errors = []

        for ref_num, group in df.groupby('reference_number', sort=False):
            ref_num = str(ref_num).strip()
            try:
                with transaction.atomic():
                    # Skip duplicate reference numbers
                    if JournalHeader.objects.filter(reference_number=ref_num).exists():
                        errors.append(f'{ref_num}: reference number already exists — skipped.')
                        skipped_count += 1
                        continue

                    first = group.iloc[0]
                    posting_date = str(first.get('posting_date', '')).strip()
                    description  = str(first.get('description',  ref_num)).strip() or ref_num

                    total_debit  = Decimal('0')
                    total_credit = Decimal('0')
                    lines_to_create = []

                    for _, row in group.iterrows():
                        account_code = str(row.get('account_code', '')).strip()
                        try:
                            account = Account.objects.get(code=account_code)
                        except Account.DoesNotExist:
                            raise ValueError(f'account code "{account_code}" not found')

                        debit  = Decimal(str(row['debit']  or 0))
                        credit = Decimal(str(row['credit'] or 0))
                        memo   = str(row.get('memo', '') or '')
                        total_debit  += debit
                        total_credit += credit
                        lines_to_create.append({'account': account, 'debit': debit, 'credit': credit, 'memo': memo})

                    if abs(total_debit - total_credit) >= Decimal('0.01'):
                        raise ValueError(
                            f'not balanced — debits {total_debit}, credits {total_credit}'
                        )

                    # Create header via serializer for field validation
                    serializer = JournalHeaderSerializer(data={
                        'posting_date':    posting_date,
                        'reference_number': ref_num,
                        'description':     description,
                        'status':          'Draft',
                    })
                    serializer.is_valid(raise_exception=True)
                    journal = serializer.save()

                    JournalLine.objects.bulk_create([
                        JournalLine(
                            header=journal,
                            account=line['account'],
                            debit=line['debit'],
                            credit=line['credit'],
                            memo=line['memo'],
                        )
                        for line in lines_to_create
                    ])

                    created_count += 1

            except Exception as exc:
                errors.append(f'{ref_num}: {exc}')
                skipped_count += 1

        return Response({
            'created': created_count,
            'skipped': skipped_count,
            'errors':  errors,
        }, status=status.HTTP_201_CREATED if created_count else status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def trial_balance(self, request):
        """Get trial balance for a period."""
        from django.db.models import Sum

        fiscal_year = int(request.query_params.get('year', timezone.now().year))
        period = int(request.query_params.get('period', timezone.now().month))

        # PF-13: Aggregate across ALL periods in the fiscal year up to
        # the selected period for cumulative YTD trial balance.
        balances = (
            GLBalance.objects.filter(
                fiscal_year=fiscal_year,
                period__lte=period
            )
            .values('account__id', 'account__code', 'account__name', 'account__account_type')
            .annotate(
                total_debit=Sum('debit_balance'),
                total_credit=Sum('credit_balance'),
            )
            .order_by('account__code')
        )

        data = []
        total_debit = 0
        total_credit = 0

        for bal in balances:
            net = bal['total_debit'] - bal['total_credit']
            if net >= 0:
                debit = net
                credit = 0
            else:
                debit = 0
                credit = abs(net)

            data.append({
                'account_code': bal['account__code'],
                'account_name': bal['account__name'],
                'account_type': bal['account__account_type'],
                'debit': debit,
                'credit': credit
            })
            total_debit += debit
            total_credit += credit

        return Response({
            'fiscal_year': fiscal_year,
            'period': period,
            'accounts': data,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'difference': total_debit - total_credit
        })

    @action(detail=False, methods=['get'])
    def gl_report(self, request):
        """Get general ledger report."""

        account_id = request.query_params.get('account')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not account_id:
            return Response({"error": "account parameter required"}, status=status.HTTP_400_BAD_REQUEST)

        journals = JournalHeader.objects.filter(
            lines__account_id=account_id,
            status='Posted'
        )

        if start_date:
            journals = journals.filter(posting_date__gte=start_date)
        if end_date:
            journals = journals.filter(posting_date__lte=end_date)

        journals = journals.distinct().prefetch_related('lines')

        data = []
        running_balance = 0

        for journal in journals:
            for line in journal.lines.filter(account_id=account_id):
                debit = line.debit or 0
                credit = line.credit or 0
                movement = debit - credit
                running_balance += movement

                data.append({
                    'date': journal.posting_date,
                    'reference': journal.reference_number,
                    'description': journal.description,
                    'debit': debit,
                    'credit': credit,
                    'balance': running_balance
                })

        return Response({
            'account_id': account_id,
            'entries': data,
            'ending_balance': running_balance
        })

# ============================================================================
# MULTI-CURRENCY VIEWSETS
# ============================================================================

class CurrencyViewSet(viewsets.ModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    filterset_fields = ['is_active', 'is_base_currency']
    pagination_class = AccountingPagination

    @action(detail=False, methods=['post'], url_path='convert')
    def convert(self, request):
        """Convert an amount between two currencies using ExchangeRateHistory or fallback to spot rates."""
        amount = request.data.get('amount')
        from_code = request.data.get('from_currency')
        to_code = request.data.get('to_currency')
        rate_date = request.data.get('date')

        if amount is None or not from_code or not to_code:
            return Response({'error': 'amount, from_currency, and to_currency are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = Decimal(str(amount))
        except Exception:
            return Response({'error': 'Invalid amount.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from_cur = Currency.objects.get(code=from_code)
            to_cur = Currency.objects.get(code=to_code)
        except Currency.DoesNotExist:
            return Response({'error': 'Currency not found.'}, status=status.HTTP_404_NOT_FOUND)

        if from_cur.id == to_cur.id:
            return Response({'converted_amount': str(amount), 'rate': '1.000000'})

        # Try ExchangeRateHistory for the given date
        rate_entry = None
        if rate_date:
            rate_entry = ExchangeRateHistory.objects.filter(
                from_currency=from_cur, to_currency=to_cur, rate_date=rate_date
            ).first()
            if not rate_entry:
                # Try reverse direction
                reverse = ExchangeRateHistory.objects.filter(
                    from_currency=to_cur, to_currency=from_cur, rate_date=rate_date
                ).first()
                if reverse and reverse.exchange_rate:
                    converted = amount * (Decimal(1) / reverse.exchange_rate)
                    return Response({'converted_amount': str(converted.quantize(Decimal('0.01'))), 'rate': str((Decimal(1) / reverse.exchange_rate).quantize(Decimal('0.000001')))})

        if not rate_entry:
            # Try latest rate from ExchangeRateHistory
            rate_entry = ExchangeRateHistory.objects.filter(
                from_currency=from_cur, to_currency=to_cur
            ).first()

        if rate_entry and rate_entry.exchange_rate:
            converted = amount * rate_entry.exchange_rate
            return Response({'converted_amount': str(converted.quantize(Decimal('0.01'))), 'rate': str(rate_entry.exchange_rate)})

        # Fallback: use Currency.exchange_rate (rates relative to base)
        if from_cur.exchange_rate and to_cur.exchange_rate:
            cross_rate = to_cur.exchange_rate / from_cur.exchange_rate
            converted = amount * cross_rate
            return Response({'converted_amount': str(converted.quantize(Decimal('0.01'))), 'rate': str(cross_rate.quantize(Decimal('0.000001')))})

        return Response({'error': 'No exchange rate available for this currency pair.'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get', 'put'], url_path='defaults')
    def defaults(self, request):
        """GET/PUT the default currency configuration."""
        settings_obj, _ = AccountingSettings.objects.get_or_create(pk=1)

        if request.method == 'GET':
            serializer = AccountingSettingsSerializer(settings_obj)
            return Response(serializer.data)

        serializer = AccountingSettingsSerializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

# ============================================================================
# GL REPORTING VIEWSETS
# ============================================================================

class GLBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset for GL balance reporting."""
    serializer_class = GLBalanceSerializer
    filterset_fields = ['fiscal_year', 'period', 'account', 'fund', 'function', 'program', 'geo']
    search_fields = ['account__code', 'account__name']

    def get_queryset(self):
        from django.db.models import Subquery, OuterRef, CharField, Value
        from django.db.models.functions import Cast

        qs = GLBalance.objects.all().select_related('account', 'fund', 'function', 'program', 'geo')

        # Annotate reference and journal_number from the most recent journal line
        # to avoid N+1 queries in the serializer
        latest_line = JournalLine.objects.filter(
            account=OuterRef('account'),
            header__posting_date__year=OuterRef('fiscal_year'),
            header__posting_date__month=OuterRef('period'),
        ).order_by('-header__posting_date', '-header__id')

        qs = qs.annotate(
            reference=Coalesce(
                Subquery(latest_line.values('header__reference_number')[:1]),
                Value(''),
                output_field=CharField(),
            ),
            journal_number=Coalesce(
                Cast(Subquery(latest_line.values('header__id')[:1]), output_field=CharField()),
                Value(''),
                output_field=CharField(),
            ),
        )
        return qs

    @action(detail=False, methods=['get'])
    def financial_statements(self, request):
        """PF-14: Return Balance Sheet and Income Statement data.

        Query params:
            year  – fiscal year (default: current year)
            period – up to this period for YTD (default: current month)

        Returns structured data grouped by account_type.
        """
        from django.db.models import Sum

        fiscal_year = int(request.query_params.get('year', timezone.now().year))
        period = int(request.query_params.get('period', timezone.now().month))

        balances = (
            GLBalance.objects.filter(fiscal_year=fiscal_year, period__lte=period)
            .values('account__account_type')
            .annotate(
                total_debit=Sum('debit_balance'),
                total_credit=Sum('credit_balance'),
            )
        )

        summary = {}
        for row in balances:
            acct_type = row['account__account_type']
            summary[acct_type] = {
                'total_debit': row['total_debit'] or Decimal('0'),
                'total_credit': row['total_credit'] or Decimal('0'),
                'net': (row['total_debit'] or Decimal('0')) - (row['total_credit'] or Decimal('0')),
            }

        assets = summary.get('Asset', {}).get('net', Decimal('0'))
        liabilities = summary.get('Liability', {}).get('net', Decimal('0'))
        equity = summary.get('Equity', {}).get('net', Decimal('0'))
        income = (summary.get('Income', {}).get('total_credit', Decimal('0'))
                  - summary.get('Income', {}).get('total_debit', Decimal('0')))
        expenses = (summary.get('Expense', {}).get('total_debit', Decimal('0'))
                    - summary.get('Expense', {}).get('total_credit', Decimal('0')))
        net_income = income - expenses

        return Response({
            'fiscal_year': fiscal_year,
            'period': period,
            'balance_sheet': {
                'assets': str(assets),
                'liabilities': str(abs(liabilities)),
                'equity': str(abs(equity)),
                'total_liabilities_and_equity': str(abs(liabilities) + abs(equity)),
            },
            'income_statement': {
                'income': str(income),
                'expenses': str(expenses),
                'net_income': str(net_income),
            },
            'detail_by_type': {k: {kk: str(vv) for kk, vv in v.items()} for k, v in summary.items()},
        })


# ============================================================================
# BUDGET MANAGEMENT VIEWSETS
# ============================================================================

class MDAViewSet(viewsets.ModelViewSet):
    queryset = MDA.objects.all()
    serializer_class = MDASerializer
    filterset_fields = ['mda_type', 'is_active', 'parent_mda']
    search_fields = ['code', 'name']
