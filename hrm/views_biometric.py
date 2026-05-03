"""Phase 8 — Biometric webhook endpoint.

Devices POST JSON event payloads signed with HMAC-SHA256 over the raw body,
using the ``BiometricDevice.webhook_secret`` as the key. The signature is
supplied in the ``X-Biometric-Signature`` header as lowercase hex.

Response codes:
    202 Accepted — event stored (may be duplicate; duplicates are no-ops).
    400 Bad Request — malformed JSON / missing required fields.
    401 Unauthorized — missing / invalid signature.
    404 Not Found — unknown device serial.
    503 Service Unavailable — device is disabled.
"""
from __future__ import annotations

import json
import logging

from django.http import HttpRequest, JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from hrm.services.biometric import (
    BiometricIngestError,
    ingest_event,
    project_to_attendance,
    verify_signature,
)

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = 'HTTP_X_BIOMETRIC_SIGNATURE'


@csrf_exempt
@require_POST
def biometric_webhook(request: HttpRequest, serial: str) -> HttpResponse:
    """Accept a single signed event from a registered biometric device."""
    from hrm.models import BiometricDevice

    try:
        device = BiometricDevice.objects.get(serial_number=serial)
    except BiometricDevice.DoesNotExist:
        return JsonResponse({'detail': 'unknown_device'}, status=404)

    if device.status != 'active':
        return JsonResponse({'detail': 'device_disabled'}, status=503)

    signature = request.META.get(SIGNATURE_HEADER, '')
    body_bytes = request.body  # raw bytes — read before parsing
    if not verify_signature(device.webhook_secret, body_bytes, signature):
        logger.warning('biometric webhook: bad signature device=%s', serial)
        return JsonResponse({'detail': 'invalid_signature'}, status=401)

    try:
        payload = json.loads(body_bytes.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'detail': 'malformed_json'}, status=400)

    try:
        event = ingest_event(device, payload)
    except BiometricIngestError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)
    except Exception:  # noqa: BLE001
        logger.exception('biometric webhook: ingest failed device=%s', serial)
        return JsonResponse({'detail': 'ingest_error'}, status=500)

    attendance = None
    try:
        attendance = project_to_attendance(event)
    except Exception:  # noqa: BLE001
        # Projection failures must NOT lose the raw event — it's already persisted.
        logger.exception('biometric webhook: projection failed event=%s', event.pk)

    return JsonResponse(
        {
            'event_id': event.pk,
            'status': event.process_status,
            'attendance_id': attendance.pk if attendance else None,
        },
        status=202,
    )
