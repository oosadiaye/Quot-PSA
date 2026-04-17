"""
Audit Trail Viewer API — Quot PSE

Read-only API for searching and filtering the system-wide audit log.
All changes across all modules are captured in core.AuditLog.
"""
from rest_framework import serializers, generics, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from core.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True, default='System')
    model_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            'id', 'timestamp', 'action', 'username', 'user',
            'model_name', 'object_repr', 'object_key', 'object_id',
            'changes', 'previous_values', 'new_values',
            'old_status', 'new_status',
            'amount', 'currency',
            'ip_address', 'description', 'reference',
        ]
        read_only_fields = fields

    def get_model_name(self, obj: AuditLog) -> str:
        if obj.content_type:
            return obj.content_type.model
        return ''


class AuditLogListView(generics.ListAPIView):
    """
    Searchable, filterable audit trail.

    Filters:
    - action: CREATE, UPDATE, DELETE, POST, APPROVE, REJECT, etc.
    - user: user ID
    - timestamp range via date_from / date_to query params

    Search:
    - object_repr, object_key, description, reference
    """
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['action', 'user']
    search_fields = ['object_repr', 'object_key', 'description', 'reference']
    ordering_fields = ['timestamp', 'action']
    ordering = ['-timestamp']

    def get_queryset(self):
        qs = AuditLog.objects.select_related('user', 'content_type').all()

        # Date range filtering
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)

        return qs
