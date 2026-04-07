from .common import AccountingPagination, DimensionImportExportMixin, viewsets
from ..models import Fund, Function, Program, Geo
from ..serializers import FundSerializer, FunctionSerializer, ProgramSerializer, GeoSerializer


class FundViewSet(DimensionImportExportMixin, viewsets.ModelViewSet):
    """Full CRUD operations for Fund dimension."""
    queryset = Fund.objects.all()
    serializer_class = FundSerializer
    filterset_fields = ['is_active']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination
    dimension_label = 'fund'
    dimension_example_rows = [
        ['FUND001', 'General Fund', 'Main operating fund', 'true'],
        ['FUND002', 'Capital Fund', 'Capital projects fund', 'true'],
    ]

class FunctionViewSet(DimensionImportExportMixin, viewsets.ModelViewSet):
    """Full CRUD operations for Function dimension."""
    queryset = Function.objects.all()
    serializer_class = FunctionSerializer
    filterset_fields = ['is_active']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination
    dimension_label = 'function'
    dimension_example_rows = [
        ['FUNC001', 'Administration', 'General administration function', 'true'],
        ['FUNC002', 'Education', 'Education and training function', 'true'],
    ]

class ProgramViewSet(DimensionImportExportMixin, viewsets.ModelViewSet):
    """Full CRUD operations for Program dimension."""
    queryset = Program.objects.all()
    serializer_class = ProgramSerializer
    filterset_fields = ['is_active']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination
    dimension_label = 'program'
    dimension_example_rows = [
        ['PROG001', 'Health Services', 'Public health services program', 'true'],
        ['PROG002', 'Infrastructure', 'Infrastructure development program', 'true'],
    ]

class GeoViewSet(DimensionImportExportMixin, viewsets.ModelViewSet):
    """Full CRUD operations for Geo dimension."""
    queryset = Geo.objects.all()
    serializer_class = GeoSerializer
    filterset_fields = ['is_active']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination
    dimension_label = 'geo'
    dimension_example_rows = [
        ['GEO001', 'Headquarters', 'Main office location', 'true'],
        ['GEO002', 'Regional Office', 'Regional satellite office', 'true'],
    ]
