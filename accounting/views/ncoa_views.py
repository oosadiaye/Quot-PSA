"""
NCoA Segment API ViewSets — Quot PSE
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
import pandas as pd


class NCoAPagination(PageNumberPagination):
    """Allow large page sizes for NCoA segment dropdowns."""
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 10000

from accounting.models.ncoa import (
    AdministrativeSegment, EconomicSegment, FunctionalSegment,
    ProgrammeSegment, FundSegment, GeographicSegment, NCoACode,
)
from accounting.serializers_ncoa import (
    AdministrativeSegmentSerializer, EconomicSegmentSerializer,
    FunctionalSegmentSerializer,
    ProgrammeSegmentSerializer, FundSegmentSerializer,
    GeographicSegmentSerializer, NCoACodeSerializer,
)
from accounting.views.common import DimensionImportExportMixin


# ── helpers ────────────────────────────────────────────────

def _str_col(row: 'pd.Series', col: str, default: str = '') -> str:
    """Safely read a string column from a pandas row."""
    val = row.get(col, default)
    if pd.isna(val):
        return default
    return str(val).strip()


def _bool_col(row: 'pd.Series', col: str, default: bool = True) -> bool:
    raw = str(row.get(col, str(default))).strip().lower()
    return raw in ('true', '1', 'yes', 'active')


# ── ViewSets ───────────────────────────────────────────────

class AdministrativeSegmentViewSet(DimensionImportExportMixin, viewsets.ModelViewSet):
    """NCoA Administrative Segment (MDA hierarchy)."""
    serializer_class = AdministrativeSegmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NCoAPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['level', 'sector_code', 'is_active', 'is_mda', 'mda_type']
    search_fields = ['code', 'name', 'short_name']
    ordering = ['code']

    dimension_label = 'administrative_segment'
    dimension_template_columns = [
        'code', 'name', 'level', 'sector_code', 'mda_type', 'is_active', 'description',
    ]
    dimension_example_rows = [
        ['010100000000', 'Office of the Governor', 'ORGANIZATION', '01', 'MINISTRY', 'true', ''],
        ['020100000000', 'Ministry of Agriculture', 'ORGANIZATION', '02', 'MINISTRY', 'true', 'Economic sector'],
    ]

    def get_queryset(self):
        return AdministrativeSegment.objects.select_related('parent')

    def get_import_field_mapping(self, row: 'pd.Series', columns: set[str]) -> dict:
        fields = super().get_import_field_mapping(row, columns)
        fields['level'] = _str_col(row, 'level', 'ORGANIZATION')
        fields['sector_code'] = _str_col(row, 'sector_code', '01')
        if 'mda_type' in columns:
            fields['mda_type'] = _str_col(row, 'mda_type', '')
        if fields.get('level') in ('ORGANIZATION', 'SUB_ORG', 'SUB_SUB_ORG', 'UNIT'):
            fields['is_mda'] = True
        return fields


class EconomicSegmentViewSet(DimensionImportExportMixin, viewsets.ModelViewSet):
    """NCoA Economic Segment (the account / hub segment)."""
    serializer_class = EconomicSegmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NCoAPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['account_type_code', 'is_posting_level', 'is_control_account', 'is_active']
    search_fields = ['code', 'name']
    ordering = ['code']

    dimension_label = 'economic_segment'
    # Template surfaces the full NCoA Economic Segment encoding:
    #   code (8 digits, X-X-XX-XX-XX positional)
    #   account_type_code (1 digit — must equal code[0]; one of 1/2/3/4)
    #   normal_balance (DEBIT or CREDIT — derived from account family)
    #   is_posting_level (true for leaf accounts that JournalLines hit)
    # is_control_account is omitted from the template since it's a niche flag;
    # the importer's get_import_field_mapping still picks it up if present.
    dimension_template_columns = [
        'code', 'name', 'account_type_code', 'normal_balance',
        'is_posting_level', 'is_active', 'description',
    ]
    dimension_template_help = [
        'NCoA Economic Segment import template.',
        'REQUIRED columns: code (8 digits, max 8 chars), name (max 200 chars),',
        '  account_type_code (one of: 1, 2, 3, 4 — see family table below).',
        'OPTIONAL columns: normal_balance (DEBIT or CREDIT, default DEBIT),',
        '  is_posting_level (default false), is_active (default true), description.',
        '',
        'NCoA GL code format — 8-digit positional encoding X-X-XX-XX-XX:',
        '  position 1   account_type_code  family digit (must match code[0])',
        '  position 2   sub_type_code      sub-family',
        '  positions 3-4 account_class_code class within sub-family',
        '  positions 5-6 sub_class_code     refinement of class',
        '  positions 7-8 line_item_code     posting-level leaf',
        '',
        'Account family table (account_type_code -> first digit of code):',
        '  1 = Revenue / Income           normal_balance = CREDIT  e.g. 11100100 PAYE',
        '  2 = Expenditure / Expense      normal_balance = DEBIT   e.g. 21100100 Salaries',
        '  3 = Assets                     normal_balance = DEBIT   e.g. 31000000 Cash & Equivalents',
        '  4 = Liabilities and Net Assets normal_balance = CREDIT  e.g. 41000000 Accounts Payable',
        '',
        'The first digit of `code` MUST equal account_type_code — the importer rejects mismatches.',
        'Lines starting with # (like these) are ignored on import.',
    ]
    dimension_example_rows = [
        # Revenue family (1xxxxxxx) — CREDIT-normal
        ['11000000', 'Tax Revenue',                   '1', 'CREDIT', 'false', 'true', 'Header — non-posting'],
        ['11100100', 'Pay As You Earn (PAYE)',        '1', 'CREDIT', 'true',  'true', 'Tax revenue — posting'],
        ['13000000', 'Grants and Transfers',          '1', 'CREDIT', 'true',  'true', 'Grants from FAAC / donors'],
        # Expenditure family (2xxxxxxx) — DEBIT-normal
        ['21000000', 'Personnel Costs',               '2', 'DEBIT',  'false', 'true', 'Header — non-posting'],
        ['21100100', 'Personnel Cost - Salaries',     '2', 'DEBIT',  'true',  'true', 'Recurrent expenditure'],
        ['22000000', 'Operations & Maintenance',      '2', 'DEBIT',  'true',  'true', 'Other charges'],
        ['23100400', 'Purchase of Plant & Equipment', '2', 'DEBIT',  'true',  'true', 'Capital expenditure'],
        # Asset family (3xxxxxxx) — DEBIT-normal
        ['31000000', 'Cash and Cash Equivalents',     '3', 'DEBIT',  'true',  'true', 'TSA, sub-accounts'],
        ['31200000', 'Accounts Receivable',           '3', 'DEBIT',  'true',  'true', 'Outstanding receivables'],
        ['32100100', 'Land (at cost)',                '3', 'DEBIT',  'true',  'true', 'PPE — land'],
        # Liability / Equity family (4xxxxxxx) — CREDIT-normal
        ['41000000', 'Accounts Payable',              '4', 'CREDIT', 'true',  'true', 'Vendor liabilities'],
        ['43100100', 'Accumulated Fund / Fund Balance', '4', 'CREDIT', 'true', 'true', 'Equity-equivalent'],
    ]

    def get_queryset(self):
        return EconomicSegment.objects.select_related('parent', 'legacy_account')

    def get_import_field_mapping(self, row: 'pd.Series', columns: set[str]) -> dict:
        # Defaults align with the NCoA documentation block above:
        #   - account_type_code: derive from code[0] when blank, else use the column.
        #     This means a CSV containing only `code` and `name` still imports
        #     correctly because the family digit IS the first digit of `code`.
        #   - normal_balance: derive from family (DEBIT for 2/3, CREDIT for 1/4).
        #   - is_posting_level: false unless explicitly set (header rows are non-posting).
        fields = super().get_import_field_mapping(row, columns)
        code_str = str(fields.get('code') or '').strip()
        first_digit = code_str[0] if code_str else '1'
        # account_type_code: explicit column wins, else derive from code[0].
        atc = _str_col(row, 'account_type_code', first_digit if first_digit in '1234' else '1')
        fields['account_type_code'] = atc
        # normal_balance: DEBIT for Expenditure (2) and Assets (3); CREDIT otherwise.
        default_balance = 'DEBIT' if atc in ('2', '3') else 'CREDIT'
        if 'normal_balance' in columns:
            nb = _str_col(row, 'normal_balance', default_balance).upper()
            fields['normal_balance'] = nb if nb in ('DEBIT', 'CREDIT') else default_balance
        else:
            fields['normal_balance'] = default_balance
        fields['is_posting_level'] = _bool_col(row, 'is_posting_level', False)
        if 'is_control_account' in columns:
            fields['is_control_account'] = _bool_col(row, 'is_control_account', False)
        return fields

    @action(detail=False, methods=['get'])
    def tree(self, request):
        """Hierarchical tree view of economic segments."""
        all_segments = list(
            EconomicSegment.objects.filter(is_active=True)
            .order_by('code')
            .values('id', 'code', 'name', 'account_type_code',
                    'is_posting_level', 'is_control_account',
                    'normal_balance', 'parent_id')
        )
        by_id = {s['id']: {**s, 'children': []} for s in all_segments}
        roots = []
        for s in all_segments:
            node = by_id[s['id']]
            if s['parent_id'] and s['parent_id'] in by_id:
                by_id[s['parent_id']]['children'].append(node)
            elif not s['parent_id']:
                roots.append(node)
        return Response(roots)

    @action(detail=False, methods=['get'])
    def posting_accounts(self, request):
        """List only posting-level accounts, optionally filtered by type."""
        account_type = request.query_params.get('type')
        qs = EconomicSegment.objects.filter(
            is_posting_level=True, is_active=True,
        )
        if account_type:
            qs = qs.filter(account_type_code=account_type)
        serializer = EconomicSegmentSerializer(qs.order_by('code'), many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='sync-from-coa')
    def sync_from_coa(self, request):
        """
        One-time backfill: walk every ``Account`` in the legacy Chart of
        Accounts and create / update the matching ``EconomicSegment``.

        Idempotent — re-running only adds rows that don't yet exist and
        refreshes name / type / active flags on those that do. The forward
        signal in ``accounting.signals.coa_to_ncoa`` keeps them in lockstep
        going forward, so this endpoint is normally called only once per
        tenant during initial setup.

        POST /api/v1/accounting/ncoa/economic/sync-from-coa/
        Returns:
            {
              "created": 47,
              "updated": 3,
              "skipped": 0,
              "skipped_details": [],
              "total": 50
            }
        """
        from accounting.services.coa_to_ncoa_sync import (
            sync_all_accounts_to_economic_segments,
        )
        result = sync_all_accounts_to_economic_segments()
        return Response(result)


class FunctionalSegmentViewSet(DimensionImportExportMixin, viewsets.ModelViewSet):
    """NCoA Functional Segment (COFOG)."""
    serializer_class = FunctionalSegmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NCoAPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['division_code', 'is_active']
    search_fields = ['code', 'name']
    ordering = ['code']

    dimension_label = 'functional_segment'
    dimension_template_columns = [
        'code', 'name', 'division_code', 'group_code', 'class_code', 'is_active', 'description',
    ]
    dimension_example_rows = [
        ['70100', 'General Public Services', '701', '0', '0', 'true', 'COFOG Division 701'],
        ['70710', 'Health - Hospital Services', '707', '1', '0', 'true', ''],
    ]

    def get_queryset(self):
        return FunctionalSegment.objects.select_related('parent')

    def get_import_field_mapping(self, row: 'pd.Series', columns: set[str]) -> dict:
        fields = super().get_import_field_mapping(row, columns)
        fields['division_code'] = _str_col(row, 'division_code', '701')
        fields['group_code'] = _str_col(row, 'group_code', '0')
        fields['class_code'] = _str_col(row, 'class_code', '0')
        return fields


class ProgrammeSegmentViewSet(DimensionImportExportMixin, viewsets.ModelViewSet):
    """NCoA Programme Segment."""
    serializer_class = ProgrammeSegmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NCoAPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['is_capital', 'is_active']
    search_fields = ['code', 'name']
    ordering = ['code']

    dimension_label = 'programme_segment'
    dimension_template_columns = [
        'code', 'name', 'policy_code', 'programme_code', 'project_code',
        'is_capital', 'is_active', 'description',
    ]
    dimension_example_rows = [
        ['01010000000000', 'Fiscal Policy Programme', '01', '01', '', 'false', 'true', ''],
        ['02030100010000', 'Road Construction', '02', '03', '010001', 'true', 'true', 'Capital'],
    ]

    def get_queryset(self):
        return ProgrammeSegment.objects.select_related('parent')

    def get_import_field_mapping(self, row: 'pd.Series', columns: set[str]) -> dict:
        fields = super().get_import_field_mapping(row, columns)
        fields['policy_code'] = _str_col(row, 'policy_code', '00')
        fields['programme_code'] = _str_col(row, 'programme_code', '00')
        fields['project_code'] = _str_col(row, 'project_code', '')
        fields['is_capital'] = _bool_col(row, 'is_capital', False)
        return fields


class FundSegmentViewSet(DimensionImportExportMixin, viewsets.ModelViewSet):
    """NCoA Fund Segment."""
    serializer_class = FundSegmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NCoAPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['main_fund_code', 'is_restricted', 'is_active']
    search_fields = ['code', 'name']
    ordering = ['code']

    dimension_label = 'fund_segment'
    dimension_template_columns = [
        'code', 'name', 'main_fund_code', 'sub_fund_code', 'fund_source_code',
        'is_active', 'description',
    ]
    dimension_example_rows = [
        ['01000', 'FAAC Statutory Allocation', '01', '0', '00', 'true', 'Federation Account'],
        ['08100', 'IGR - Taxes', '08', '1', '00', 'true', ''],
    ]

    def get_queryset(self):
        return FundSegment.objects.select_related('parent')

    def get_import_field_mapping(self, row: 'pd.Series', columns: set[str]) -> dict:
        fields = super().get_import_field_mapping(row, columns)
        fields['main_fund_code'] = _str_col(row, 'main_fund_code', '01')
        fields['sub_fund_code'] = _str_col(row, 'sub_fund_code', '0')
        fields['fund_source_code'] = _str_col(row, 'fund_source_code', '00')
        return fields


class GeographicSegmentViewSet(DimensionImportExportMixin, viewsets.ModelViewSet):
    """NCoA Geographic Segment."""
    serializer_class = GeographicSegmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NCoAPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['zone_code', 'state_code', 'is_active']
    search_fields = ['code', 'name']
    ordering = ['code']

    dimension_label = 'geographic_segment'
    # Template surfaces only the fields the Add/Edit form exposes. The legacy
    # NCoA hierarchy columns (zone_code, state_code, senatorial_code, lga_code,
    # ward_code) are no longer in the downloaded template — but the importer
    # still reads them when present (see ``get_import_field_mapping`` below),
    # so any pre-existing CSV that includes those columns continues to work.
    dimension_template_columns = [
        'code', 'name', 'is_active', 'description',
    ]
    dimension_template_help = [
        'NCoA Geographic Segment import template.',
        'REQUIRED columns: code (max 8 chars), name (max 200 chars).',
        "OPTIONAL columns and their defaults if blank: is_active=true, description=''.",
        'The code is the eight-digit composite — write 51000100, NOT 5-10-01-00 with separators.',
        'Lines starting with # (like these) are ignored on import.',
    ]
    dimension_example_rows = [
        # Minimal — only code + name, optional columns blank.
        ['51000100', 'Aniocha North', '', ''],
        # With optional fields populated.
        ['10000000', 'North-Central Zone', 'true', 'Zone 1'],
        ['52000000', 'Delta State', 'true', 'Delta State (header)'],
    ]

    def get_queryset(self):
        return GeographicSegment.objects.select_related('parent')

    def get_import_field_mapping(self, row: 'pd.Series', columns: set[str]) -> dict:
        # Only `code` and `name` are mandatory — every other column falls back
        # to the same default the serializer applies on a JSON POST. This keeps
        # the import contract consistent with /accounting/ncoa/geographic/ POST.
        fields = super().get_import_field_mapping(row, columns)
        fields['zone_code'] = _str_col(row, 'zone_code', '1')
        fields['state_code'] = _str_col(row, 'state_code', '00')
        fields['senatorial_code'] = _str_col(row, 'senatorial_code', '0')
        fields['lga_code'] = _str_col(row, 'lga_code', '00')
        fields['ward_code'] = _str_col(row, 'ward_code', '00')
        return fields


class NCoACodeViewSet(viewsets.ModelViewSet):
    """NCoA Composite Code — full 52-digit financial DNA."""
    serializer_class = NCoACodeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['is_active', 'economic__account_type_code', 'fund']
    search_fields = ['economic__code', 'economic__name', 'administrative__name']
    ordering = ['economic__code']

    def get_queryset(self):
        return NCoACode.objects.select_related(
            'administrative', 'economic', 'functional',
            'programme', 'fund', 'geographic',
        )

    @action(detail=False, methods=['post'])
    def resolve(self, request):
        """Resolve 6 segment codes into an NCoA composite code."""
        from accounting.services.ncoa_service import NCoAService, NCoAResolutionError
        required = ['admin_code', 'economic_code', 'functional_code',
                     'programme_code', 'fund_code', 'geo_code']
        missing = [f for f in required if not request.data.get(f)]
        if missing:
            return Response(
                {'error': f'Missing required fields: {", ".join(missing)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ncoa = NCoAService.resolve_code(
                admin_code=request.data['admin_code'],
                economic_code=request.data['economic_code'],
                functional_code=request.data['functional_code'],
                programme_code=request.data['programme_code'],
                fund_code=request.data['fund_code'],
                geo_code=request.data['geo_code'],
            )
            return Response(NCoACodeSerializer(ncoa).data, status=status.HTTP_200_OK)
        except NCoAResolutionError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
