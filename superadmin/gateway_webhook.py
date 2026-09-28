"""
Inbound PSP callback — the settlement signal.

Unauthenticated by design: a PSP cannot hold our session, so the ONLY
auth is the HMAC signature over the raw request body, verified with a
constant-time compare (the same pattern as ``hrm.views_biometric``).

``GatewayTransaction`` lives in the public schema, so this view — which
the middleware pins to public and lets through without tenant resolution
— looks the transaction up by its reference, then settles inside the
owning tenant's schema via ``schema_context``. It is idempotent: a
re-delivered callback for an already-settled transaction is a no-op.
"""
from __future__ import annotations

import json
import logging

from django.http import (
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_tenants.utils import schema_context

from superadmin.gateway_connectors import get_connector
from superadmin.gateway_connectors.base import WebhookEvent
from superadmin.gateway_models import (
    GatewayService,
    GatewayTransaction,
    PaymentGatewayProvider,
)

logger = logging.getLogger(__name__)

# PSPs name the signature header differently; accept the common ones.
_SIGNATURE_HEADERS = (
    "HTTP_X_GATEWAY_SIGNATURE",
    "HTTP_X_REMITA_SIGNATURE",
    "HTTP_X_XPRESSPAY_SIGNATURE",
    "HTTP_X_PAYMENT_SIGNATURE",
    "HTTP_X_SIGNATURE",
)


def _signature(request) -> str | None:
    for header in _SIGNATURE_HEADERS:
        value = request.META.get(header)
        if value:
            return value
    return None


@csrf_exempt
@require_POST
def gateway_webhook(request, gateway):
    """Settle a gateway transaction from a PSP callback.

    URL: ``/api/v1/gateway/webhook/<gateway>/`` (public, HMAC-authenticated).
    """
    provider = PaymentGatewayProvider.objects.filter(key=gateway).first()
    if provider is None:
        return HttpResponseBadRequest("Unknown gateway.")

    raw = request.body  # read raw bytes BEFORE any parsing, for the HMAC
    connector = get_connector(provider)

    # Authentication is the signature and nothing else.
    if not connector.verify_webhook(provider, raw, _signature(request)):
        logger.warning("Gateway webhook rejected: bad signature for %s", gateway)
        return HttpResponseForbidden("Invalid signature.")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest("Invalid JSON body.")

    event = connector.parse_webhook(provider, payload)
    if not event.gateway_reference:
        return HttpResponseBadRequest("Callback carries no transaction reference.")

    txn = (
        GatewayTransaction.objects
        .select_related("tenant")
        .filter(provider=provider, gateway_reference=event.gateway_reference)
        .first()
    )
    if txn is None:
        # 200 (not 4xx) so the PSP stops retrying a reference we do not hold —
        # a retry storm on an unknown reference helps no one.
        logger.warning(
            "Gateway webhook: no transaction for %s ref %s",
            gateway, event.gateway_reference,
        )
        return JsonResponse({"status": "ignored", "detail": "unknown reference"}, status=200)

    if txn.status in (
        GatewayTransaction.Status.SUCCESS,
        GatewayTransaction.Status.REVERSED,
    ):
        return JsonResponse({"status": "already settled"}, status=200)

    success = event.outcome == WebhookEvent.SUCCESS
    try:
        with schema_context(txn.tenant.schema_name):
            if txn.direction == GatewayService.COLLECTION:
                from accounting.services.gateway_collection import settle_collection
                settle_collection(txn, success=success)
            else:
                from accounting.services.gateway_disbursement import (
                    settle_gateway_disbursement,
                )
                settle_gateway_disbursement(txn, success=success)
    except Exception:  # noqa: BLE001 - log server-side, don't echo internals to a PSP
        logger.exception(
            "Gateway webhook settlement failed for %s ref %s",
            gateway, event.gateway_reference,
        )
        return JsonResponse({"status": "error"}, status=500)

    return JsonResponse({"status": "settled", "outcome": event.outcome}, status=200)
