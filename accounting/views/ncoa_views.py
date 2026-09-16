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
    AdministrativeSegment, FunctionalSegment,
    ProgrammeSegment, FundSegment, GeographicSegment, NCoACode,
)
from accounting.serializers_ncoa import (
    AdministrativeSegmentSerializer,
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
    # economic is the GL Account now — it carries account_type, not the
    # NCoA account_type_code digit the retired segment model used.
    filterset_fields = ['is_active', 'economic__account_type', 'fund']
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
