"""
In-App Notification API — Quot PSE

Endpoints:
- GET  /core/notifications/         — List user's notifications (unread first)
- GET  /core/notifications/unread_count/ — Count of unread notifications
- POST /core/notifications/<id>/read/    — Mark single notification as read
- POST /core/notifications/mark_all_read/ — Mark all as read
"""
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone

from core.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'category', 'priority', 'title', 'message',
            'action_url', 'is_read', 'read_at', 'created_at',
            'related_model', 'related_id',
        ]
        read_only_fields = fields


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """User's in-app notifications — read-only with mark-as-read actions."""
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    ordering = ['-created_at']

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by(
            'is_read', '-created_at',  # unread first, then by date
        )

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        count = Notification.objects.filter(
            user=request.user, is_read=False,
        ).count()
        return Response({'unread_count': count})

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=['is_read', 'read_at'])
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        updated = Notification.objects.filter(
            user=request.user, is_read=False,
        ).update(is_read=True, read_at=timezone.now())
        return Response({'marked_read': updated})
