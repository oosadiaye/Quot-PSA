"""Serializers for the public, unauthenticated transparency portal.

These serialize ``superadmin.PublishedSnapshot`` rows — the public-schema,
materialized, read-only projection of approved fiscal publications.  The public
portal never touches tenant-schema ``ReportSnapshot`` / ``Publication`` tables
directly (FUTURE_MODULES §5.5).
"""
from rest_framework import serializers

from superadmin.models import PublishedSnapshot


class PublishedSnapshotSerializer(serializers.ModelSerializer):
    """Expose only what is safe for the public citizen portal."""

    class Meta:
        model = PublishedSnapshot
        fields = [
            'id', 'dataset_key', 'title', 'aggregation', 'fiscal_year',
            'period', 'payload', 'content_hash', 'published_at',
        ]
        read_only_fields = fields
