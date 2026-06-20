"""
Serializers for the async report-export API (additive).

Two serializers:

* ``AsyncExportJobCreateSerializer`` validates the POST body
  (``label``, ``fmt``, ``report_payload``). ``fmt`` is constrained to
  the formats ``ReportRenderer`` supports so a bad value is rejected at
  the boundary rather than failing later inside the Celery task.

* ``AsyncExportJobSerializer`` is the read/poll envelope returned by the
  status endpoint.
"""
from __future__ import annotations

from rest_framework import serializers

from accounting.models import AsyncExportJob


# Formats ReportRenderer.render() accepts (html, pdf, xlsx). 'excel' is
# an accepted alias of 'xlsx' in the renderer; we expose the canonical
# set here and let the renderer alias-map internally.
SUPPORTED_FORMATS = ('xlsx', 'pdf', 'html')


class AsyncExportJobCreateSerializer(serializers.Serializer):
    """Validates the create-job request body."""

    label = serializers.CharField(max_length=255)
    fmt = serializers.ChoiceField(choices=SUPPORTED_FORMATS)
    report_payload = serializers.JSONField()

    def validate_report_payload(self, value):
        # The renderer expects a dict-shaped report. Reject anything else
        # up front so the task never has to defend against a bad shape.
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                'report_payload must be a JSON object (report dict).'
            )
        return value


class AsyncExportJobSerializer(serializers.ModelSerializer):
    """Read-only status envelope for polling a job."""

    class Meta:
        model = AsyncExportJob
        fields = [
            'id', 'status', 'label', 'fmt',
            'filename', 'file_size', 'content_type', 'error',
            'created_at', 'completed_at',
        ]
        read_only_fields = fields
