"""DRF serializers for the snapshots feature.

The serializer is intentionally write-restrictive: clients can only set
``schema_name`` and ``label`` on create. Every other field is set by the
service layer or by Celery and exposed as read-only.

Fields deliberately NOT exposed:
- ``artifact_path``: internal storage path; would leak server filesystem layout
- ``kek_fingerprint``: which key encrypted this artifact; security-sensitive
- ``manifest``: raw manifest leaks encryption envelope (wrapped_dek_b64/iv_b64/
  tag_b64), PII key fingerprint, and code version; use ``manifest_summary``
  instead which exposes only operationally-useful fields.
- ``triggered_by``: internal user PK; use ``triggered_by_username`` instead.
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
    manifest_summary = serializers.SerializerMethodField()

    class Meta:
        model = SnapshotJob
        fields = [
            'id',
            'schema_name',
            'label',
            'status',
            'status_display',
            'triggered_by_username',
            'triggered_at',
            'started_at',
            'completed_at',
            'size_bytes',
            'sha256',
            'manifest_summary',
            'error_class',
            'error_message',
            'has_artifact',
        ]
        read_only_fields = [
            'id', 'status', 'status_display',
            'triggered_by_username',
            'triggered_at', 'started_at', 'completed_at',
            'size_bytes', 'sha256', 'manifest_summary',
            'error_class', 'error_message',
            'has_artifact',
        ]

    def get_has_artifact(self, obj: SnapshotJob) -> bool:
        return bool(obj.artifact_path) and obj.status == SnapshotJob.Status.SUCCEEDED

    def get_manifest_summary(self, obj: SnapshotJob) -> dict:
        """Operational subset of the manifest. Strips cryptographic material
        (encryption envelope), PII key fingerprint, and code version — these
        are useful internally but should not be exposed via the API."""
        m = obj.manifest or {}
        snapshot = m.get('snapshot') or {}
        contents = m.get('contents') or {}
        return {
            'schema_version': m.get('schema_version'),
            'created_at_utc': snapshot.get('created_at_utc'),
            'database_sql_sha256': contents.get('database_sql_sha256'),
            'media_file_count': contents.get('media_file_count'),
            'media_total_bytes': contents.get('media_total_bytes'),
        }

    def validate_schema_name(self, value: str) -> str:
        from django_tenants.utils import get_public_schema_name
        if value == get_public_schema_name():
            raise serializers.ValidationError(
                'Cannot snapshot the public schema via the API.')
        if not SCHEMA_NAME_RE.fullmatch(value):
            raise serializers.ValidationError(
                'schema_name must be lowercase, start with a letter, '
                'contain only letters, digits, and underscores, '
                'and be at most 63 characters.')
        return value

    def validate_label(self, value: str) -> str:
        if value and len(value) > 120:
            raise serializers.ValidationError('label exceeds 120 characters.')
        return value
