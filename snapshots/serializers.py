"""DRF serializers for the snapshots feature.

The serializer is intentionally write-restrictive: clients can only set
``schema_name`` and ``label`` on create. Every other field is set by the
service layer or by Celery and exposed as read-only.

Fields deliberately NOT exposed:
- ``artifact_path``: internal storage path; would leak server filesystem layout
- ``kek_fingerprint``: which key encrypted this artifact; security-sensitive
"""
from __future__ import annotations

from rest_framework import serializers

from snapshots.constants import SCHEMA_NAME_RE
from snapshots.models import SnapshotJob


class SnapshotJobSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source='get_status_display', read_only=True)
    triggered_by_username = serializers.CharField(
        source='triggered_by.username', read_only=True)
    has_artifact = serializers.SerializerMethodField()

    class Meta:
        model = SnapshotJob
        fields = [
            'id',
            'schema_name',
            'label',
            'status',
            'status_display',
            'triggered_by',
            'triggered_by_username',
            'triggered_at',
            'started_at',
            'completed_at',
            'size_bytes',
            'sha256',
            'manifest',
            'error_class',
            'error_message',
            'has_artifact',
        ]
        read_only_fields = [
            'id', 'status', 'status_display',
            'triggered_by', 'triggered_by_username',
            'triggered_at', 'started_at', 'completed_at',
            'size_bytes', 'sha256', 'manifest',
            'error_class', 'error_message',
            'has_artifact',
        ]

    def get_has_artifact(self, obj: SnapshotJob) -> bool:
        return bool(obj.artifact_path) and obj.status == SnapshotJob.Status.SUCCEEDED

    def validate_schema_name(self, value: str) -> str:
        if not SCHEMA_NAME_RE.fullmatch(value):
            raise serializers.ValidationError(
                'schema_name must match ^[a-z][a-z0-9_]{0,62}$ '
                '(lowercase, digit-not-first, max 63 chars).')
        return value

    def validate_label(self, value: str) -> str:
        if value and len(value) > 120:
            raise serializers.ValidationError('label exceeds 120 characters.')
        return value
