"""
Outbound Webhook Dispatcher
============================
Sends DTSG ERP events to all subscribed WebhookEndpoint URLs.

Usage (call from Django signals or views):
    from integrations.webhook_dispatcher import dispatch_event
    dispatch_event('sales_order.created', module='sales', payload={...})

The dispatcher:
  1. Finds all active WebhookEndpoints matching the event + module
  2. Serialises the payload as JSON
  3. Signs with HMAC-SHA256 (X-DTSG-Signature header)
  4. POSTs to each target_url in a background thread
  5. Logs success/failure in WebhookDelivery
  6. Schedules retries on transient failures
"""
import json
import logging
import threading
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.utils import timezone

logger = logging.getLogger('integrations.webhook')


def dispatch_event(
    event_type: str,
    payload: Dict[str, Any],
    module: str = '',
    tenant_schema: str = None,
):
    """
    Dispatch a DTSG event to all matching webhook subscribers.
    Runs delivery in background threads so callers are never blocked.

    :param event_type: EventType value, e.g. 'sales_order.created'
    :param payload:    JSON-serialisable dict
    :param module:     ModuleCode, used to filter subscriptions
    :param tenant_schema: Schema name for multi-tenant context
    """
    try:
        from integrations.models import WebhookEndpoint

        # Filter active endpoints that subscribe to this event/module
        endpoints = WebhookEndpoint.objects.filter(is_active=True)
        matching = []
        for ep in endpoints:
            # Empty events list = subscribe to all
            if ep.events and event_type not in ep.events:
                continue
            # Empty modules list = all modules
            if module and ep.modules and module not in ep.modules:
                continue
            matching.append(ep)

        if not matching:
            return

        # Enrich payload with DTSG metadata
        enriched = {
            'event': event_type,
            'module': module,
            'timestamp': timezone.now().isoformat(),
            'source': 'dtsg_erp',
            'data': payload,
        }
        if tenant_schema:
            enriched['tenant'] = tenant_schema

        for ep in matching:
            t = threading.Thread(
                target=_deliver_to_endpoint,
                args=(ep, event_type, enriched),
                daemon=True,
            )
            t.start()

    except Exception as exc:
        logger.error('webhook dispatch error: %s', exc, exc_info=True)


def _deliver_to_endpoint(endpoint, event_type: str, payload: dict, attempt: int = 1):
    """Deliver a single webhook event to a target URL."""
    import requests as req_lib
    from integrations.models import WebhookDelivery, SyncStatus

    raw_body = json.dumps(payload, default=str).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'X-DTSG-Event': event_type,
        'X-DTSG-Attempt': str(attempt),
    }
    # Sign the payload
    sig = endpoint.sign_payload(raw_body)
    if sig:
        headers['X-DTSG-Signature'] = sig

    # Merge custom headers
    if endpoint.headers:
        headers.update(endpoint.headers)

    delivery = WebhookDelivery.objects.create(
        endpoint=endpoint,
        event_type=event_type,
        payload=payload,
        attempt_count=attempt,
        status=SyncStatus.PENDING,
    )

    try:
        resp = req_lib.post(
            endpoint.target_url,
            data=raw_body,
            headers=headers,
            timeout=endpoint.timeout_seconds,
        )
        delivery.response_status = resp.status_code
        delivery.response_body = resp.text[:2000]

        if resp.ok:
            delivery.status = SyncStatus.SUCCESS
            delivery.delivered_at = timezone.now()
            logger.info('Webhook delivered: %s -> %s (%d)', event_type, endpoint.target_url, resp.status_code)
        else:
            _handle_delivery_failure(delivery, endpoint, event_type, payload, attempt,
                                     f'HTTP {resp.status_code}: {resp.text[:200]}')
    except req_lib.exceptions.Timeout:
        _handle_delivery_failure(delivery, endpoint, event_type, payload, attempt, 'Timeout')
    except req_lib.exceptions.ConnectionError as exc:
        _handle_delivery_failure(delivery, endpoint, event_type, payload, attempt, f'Connection error: {exc}')
    except Exception as exc:
        _handle_delivery_failure(delivery, endpoint, event_type, payload, attempt, str(exc))
    finally:
        delivery.save()


def _handle_delivery_failure(delivery, endpoint, event_type, payload, attempt, error_msg):
    from integrations.models import SyncStatus
    delivery.error_message = error_msg
    logger.warning('Webhook delivery failed: %s -> %s (attempt %d): %s',
                   event_type, endpoint.target_url, attempt, error_msg)
    if attempt < endpoint.max_retries:
        # Exponential backoff: 60s, 120s, 240s
        backoff = 60 * (2 ** (attempt - 1))
        delivery.status = SyncStatus.RETRY
        delivery.next_retry_at = timezone.now() + timedelta(seconds=backoff)
        # Schedule retry in background
        t = threading.Timer(
            backoff,
            _deliver_to_endpoint,
            args=(endpoint, event_type, payload, attempt + 1),
        )
        t.daemon = True
        t.start()
    else:
        delivery.status = SyncStatus.FAILED
        logger.error('Webhook exhausted retries: %s -> %s', event_type, endpoint.target_url)
