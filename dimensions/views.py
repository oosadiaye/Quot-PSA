"""
Dimensions API. Core, not an optional module: no ModuleEnabled gate. With no dimensions defined every list is empty
and the forms show nothing extra.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import RBACPermission
from . import services
from .models import RECORD_TYPES, DimensionTag, DimensionType, DimensionValue
from .serializers import DimensionTypeSerializer, DimensionValueSerializer


def _refused(exc: Exception) -> Response:
    return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)


class DimensionTypeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, RBACPermission]
    queryset = DimensionType.objects.select_related('parent_type').all()
    serializer_class = DimensionTypeSerializer
    filterset_fields = ['is_active', 'parent_type']

    @action(detail=False, methods=['get'], url_path='for-record')
    def for_record(self, request):
        """What a form needs: the active dimensions switched on for a record type, whether each is mandatory, and the
        active values (with their parent) to pick from. Empty when the tenant has defined none."""
        record_type = request.query_params.get('record_type', '')
        if record_type not in RECORD_TYPES:
            return Response({'error': f"Unknown record type '{record_type}'."}, status=status.HTTP_400_BAD_REQUEST)
        out = []
        for dimension in DimensionType.objects.filter(is_active=True).select_related('parent_type'):
            if record_type not in (dimension.applies_to or []):
                continue
            values = dimension.values.filter(is_active=True).select_related('parent')
            out.append({
                'code': dimension.code, 'name': dimension.name,
                'parent_type': dimension.parent_type.code if dimension.parent_type else None,
                'required': record_type in (dimension.required_on or []),
                'values': [{'code': v.code, 'name': v.name, 'parent': v.parent.code if v.parent else None}
                           for v in values],
            })
        return Response(out)


class DimensionValueViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, RBACPermission]
    queryset = DimensionValue.objects.select_related('dimension_type', 'parent').all()
    serializer_class = DimensionValueSerializer
    filterset_fields = ['dimension_type', 'parent', 'is_active']
    search_fields = ['code', 'name']


class DimensionTagViewSet(viewsets.GenericViewSet):
    """Read and set the dimension tags of one record, and the per-dimension report."""
    permission_classes = [IsAuthenticated, RBACPermission]
    queryset = DimensionTag.objects.all()

    def list(self, request):
        record_type, record_id = request.query_params.get('record_type'), request.query_params.get('record_id')
        if not record_type or not str(record_id or '').isdigit():
            return Response({'error': 'record_type and a numeric record_id are required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(services.get_tags(record_type, int(record_id)))

    @action(detail=False, methods=['post'], url_path='set')
    def set_tags(self, request):
        data = request.data
        record_type, record_id, tags = data.get('record_type'), data.get('record_id'), data.get('tags')
        if not record_type or not str(record_id or '').isdigit() or not isinstance(tags, dict):
            return Response({'error': 'record_type, record_id and tags (an object) are required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            return Response(services.set_tags(record_type, int(record_id), tags))
        except services.DimensionError as exc:
            return _refused(exc)

    @action(detail=False, methods=['get'], url_path=r'report/(?P<type_code>[-\w]+)')
    def report(self, request, type_code=None):
        params = request.query_params
        try:
            return Response(services.dimension_report(
                type_code, parent_value=params.get('parent_value'), date_from=params.get('date_from') or None,
                date_to=params.get('date_to') or None, account_type=params.get('account_type') or 'Expense'))
        except services.DimensionError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_404_NOT_FOUND)
