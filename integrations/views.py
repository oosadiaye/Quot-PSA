"""
Integration API Views
======================
Exposes:
  /api/v1/integrations/configs/                     CRUD integration configs
  /api/v1/integrations/configs/{id}/test/           Test connection
  /api/v1/integrations/configs/{id}/sync/           Trigger manual sync
  /api/v1/integrations/configs/{id}/field-mappings/ CRUD field mappings
  /api/v1/integrations/configs/{id}/webhooks/       List webhook deliveries
  /api/v1/integrations/webhook-endpoints/           CRUD outbound webhook subs
  /api/v1/integrations/webhook-endpoints/{id}/rotate-secret/
  /api/v1/integrations/sync-logs/                   Read-only sync history
  /api/v1/integrations/inbound/sap/                 SAP inbound webhook
  /api/v1/integrations/inbound/dynamics/            Dynamics inbound webhook
  /api/v1/integrations/inbound/sage/                Sage inbound webhook
  /api/v1/integrations/inbound/shopify/             Shopify inbound webhook
  /api/v1/integrations/inbound/stripe/              Stripe inbound webhook
  /api/v1/integrations/inbound/paystack/            Paystack inbound webhook
  /api/v1/integrations/inbound/flutterwave/         Flutterwave inbound webhook
  /api/v1/integrations/inbound/generic/{config_id}/ Generic inbound webhook
"""
import json
import logging
import threading
from typing import Any

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    EventType, IntegrationConfig, ModuleCode,
    SyncDirection, SyncLog, SyncStatus, SystemType,
    WebhookDelivery, WebhookEndpoint, WebhookInboundLog,
)
from .serializers import (
    FieldMappingSerializer, IntegrationConfigListSerializer,
    IntegrationConfigSerializer, SyncLogSerializer,
    WebhookDeliverySerializer, WebhookEndpointSerializer,
    WebhookInboundLogSerializer,
)

logger = logging.getLogger('integrations.views')


# ---------------------------------------------------------------------------
# Integration Config ViewSet
# ---------------------------------------------------------------------------

class IntegrationConfigViewSet(viewsets.ModelViewSet):
    """CRUD for IntegrationConfig — one per connected external system."""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return IntegrationConfig.objects.all().order_by('name')

    def get_serializer_class(self):
        if self.action == 'list':
            return IntegrationConfigListSerializer
        return IntegrationConfigSerializer

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test connectivity to the remote system."""
        config = self.get_object()
        from .adapters.factory import get_adapter
        try:
            adapter = get_adapter(config)
            ok = adapter.test_connection()
            config.last_sync_at = timezone.now()
            config.save(update_fields=['last_sync_at'])
            if ok:
                return Response({'status': 'ok', 'message': f'Connected to {config.get_system_type_display()}'})
            return Response({'status': 'failed', 'message': 'Connection test returned False'},
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error('test_connection failed for %s: %s', config.name, exc)
            return Response({'status': 'error', 'message': str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        """
        Trigger a manual sync for this integration.
        Body: {"module": "accounting", "direction": "inbound"}
        """
        config = self.get_object()
        module = request.data.get('module', ModuleCode.ALL)
        direction = request.data.get('direction', SyncDirection.BIDIRECTIONAL)

        sync_log = SyncLog.objects.create(
            config=config,
            module=module,
            direction=direction,
            triggered_by='manual',
            status=SyncStatus.RUNNING,
        )

        def run_sync():
            from .sync_engine import run_module_sync
            try:
                run_module_sync(config, module, direction, sync_log)
            except Exception as exc:
                sync_log.status = SyncStatus.FAILED
                sync_log.error_summary = str(exc)
                sync_log.finished_at = timezone.now()
                sync_log.save()

        t = threading.Thread(target=run_sync, daemon=True)
        t.start()

        return Response({
            'status': 'started',
            'sync_log_id': str(sync_log.id),
            'message': f'Sync started for {module} ({direction})',
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['get', 'post'], url_path='field-mappings')
    def field_mappings(self, request, pk=None):
        config = self.get_object()
        if request.method == 'GET':
            mappings = config.field_mappings.all()
            return Response(FieldMappingSerializer(mappings, many=True).data)
        serializer = FieldMappingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(config=config)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='generate-webhook-secret')
    def generate_webhook_secret(self, request, pk=None):
        config = self.get_object()
        secret = config.generate_webhook_secret()
        return Response({'webhook_secret': secret})

    @action(detail=True, methods=['get'], url_path='sync-logs')
    def sync_logs(self, request, pk=None):
        config = self.get_object()
        logs = config.sync_logs.all()[:50]
        return Response(SyncLogSerializer(logs, many=True).data)

    @action(detail=True, methods=['get'], url_path='inbound-logs')
    def inbound_logs(self, request, pk=None):
        config = self.get_object()
        logs = config.inbound_logs.all()[:100]
        return Response(WebhookInboundLogSerializer(logs, many=True).data)

    # ---- Module-specific sync actions ----

    @action(detail=True, methods=['post'], url_path='sync/accounting')
    def sync_accounting(self, request, pk=None):
        return self._module_sync(pk, ModuleCode.ACCOUNTING, request.data.get('direction', 'inbound'))

    @action(detail=True, methods=['post'], url_path='sync/inventory')
    def sync_inventory(self, request, pk=None):
        return self._module_sync(pk, ModuleCode.INVENTORY, request.data.get('direction', 'inbound'))

    @action(detail=True, methods=['post'], url_path='sync/sales')
    def sync_sales(self, request, pk=None):
        return self._module_sync(pk, ModuleCode.SALES, request.data.get('direction', 'inbound'))

    @action(detail=True, methods=['post'], url_path='sync/procurement')
    def sync_procurement(self, request, pk=None):
        return self._module_sync(pk, ModuleCode.PROCUREMENT, request.data.get('direction', 'inbound'))

    @action(detail=True, methods=['post'], url_path='sync/hrm')
    def sync_hrm(self, request, pk=None):
        return self._module_sync(pk, ModuleCode.HRM, request.data.get('direction', 'inbound'))

    @action(detail=True, methods=['post'], url_path='sync/vendors')
    def sync_vendors(self, request, pk=None):
        return self._module_sync(pk, ModuleCode.VENDORS, request.data.get('direction', 'inbound'))

    @action(detail=True, methods=['post'], url_path='sync/customers')
    def sync_customers(self, request, pk=None):
        return self._module_sync(pk, ModuleCode.CUSTOMERS, request.data.get('direction', 'inbound'))

    @action(detail=True, methods=['post'], url_path='sync/items')
    def sync_items(self, request, pk=None):
        return self._module_sync(pk, ModuleCode.ITEMS, request.data.get('direction', 'inbound'))

    def _module_sync(self, pk, module, direction):
        try:
            config = IntegrationConfig.objects.get(pk=pk)
        except IntegrationConfig.DoesNotExist:
            return Response({'error': 'Integration config not found'}, status=status.HTTP_404_NOT_FOUND)
        sync_log = SyncLog.objects.create(
            config=config, module=module, direction=direction,
            triggered_by='manual', status=SyncStatus.RUNNING,
        )

        def run():
            from .sync_engine import run_module_sync
            try:
                run_module_sync(config, module, direction, sync_log)
            except Exception as exc:
                sync_log.status = SyncStatus.FAILED
                sync_log.error_summary = str(exc)
                sync_log.finished_at = timezone.now()
                sync_log.save()

        threading.Thread(target=run, daemon=True).start()
        return Response({'status': 'started', 'sync_log_id': str(sync_log.id)},
                        status=status.HTTP_202_ACCEPTED)


# ---------------------------------------------------------------------------
# Webhook Endpoint ViewSet
# ---------------------------------------------------------------------------

class WebhookEndpointViewSet(viewsets.ModelViewSet):
    queryset = WebhookEndpoint.objects.all()
    serializer_class = WebhookEndpointSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'], url_path='rotate-secret')
    def rotate_secret(self, request, pk=None):
        ep = self.get_object()
        secret = ep.generate_secret()
        return Response({'secret': secret})

    @action(detail=True, methods=['get'], url_path='deliveries')
    def deliveries(self, request, pk=None):
        ep = self.get_object()
        deliveries = ep.deliveries.all()[:100]
        return Response(WebhookDeliverySerializer(deliveries, many=True).data)

    @action(detail=True, methods=['post'], url_path='test')
    def test_delivery(self, request, pk=None):
        """Send a test ping to the target URL."""
        ep = self.get_object()
        from .webhook_dispatcher import _deliver_to_endpoint
        payload = {
            'event': 'test.ping',
            'module': 'all',
            'timestamp': timezone.now().isoformat(),
            'source': 'dtsg_erp',
            'data': {'message': 'DTSG ERP webhook test'},
        }
        t = threading.Thread(
            target=_deliver_to_endpoint, args=(ep, 'test.ping', payload), daemon=True
        )
        t.start()
        return Response({'status': 'test_sent', 'target': ep.target_url})


# ---------------------------------------------------------------------------
# Sync Log ViewSet (read-only)
# ---------------------------------------------------------------------------

class SyncLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SyncLog.objects.all().select_related('config').prefetch_related('items')
    serializer_class = SyncLogSerializer
    permission_classes = [IsAuthenticated]


# ---------------------------------------------------------------------------
# Inbound Webhook Receivers (no auth — verified by HMAC signature)
# ---------------------------------------------------------------------------

class BaseInboundWebhookView(APIView):
    """
    Base class for inbound webhook receivers.
    Subclasses set `source_system` and override `_verify_signature()`.
    """
    authentication_classes = []
    permission_classes = []
    source_system = SystemType.CUSTOM

    def _verify_signature(self, raw_body, request, config):
        """Override in subclasses for system-specific signature verification.
        Return True/False for valid/invalid, or None to use the default check."""
        return None

    def post(self, request, config_id=None):
        raw_body = request.body
        config = self._get_config(config_id)

        # Verify signature: prefer subclass-specific verification, fall back to generic DTSG header
        sig_valid = None
        if config and config.webhook_secret:
            sig_valid = self._verify_signature(raw_body, request, config)
            if sig_valid is None:
                # No subclass-specific verification; use default DTSG signature header
                sig_header = request.headers.get('X-DTSG-Signature', '')
                sig_valid = config.verify_hmac_signature(raw_body, sig_header)
            if not sig_valid:
                logger.warning('Inbound webhook signature mismatch from %s', self.source_system)
                return Response({'error': 'Invalid signature'}, status=status.HTTP_401_UNAUTHORIZED)

        # Parse payload
        try:
            parsed = json.loads(raw_body)
        except (ValueError, TypeError):
            parsed = None

        event_type = (
            request.headers.get('X-Event-Type')
            or request.headers.get('X-Shopify-Topic')
            or (parsed.get('eventType') if parsed else '')
            or 'unknown'
        )

        log = WebhookInboundLog.objects.create(
            config=config,
            source_system=self.source_system,
            event_type=event_type,
            headers=dict(request.headers),
            raw_payload=raw_body.decode('utf-8', errors='replace')[:50000],
            parsed_payload=parsed,
            signature_valid=sig_valid,
            processing_status=SyncStatus.PENDING,
        )

        # Process asynchronously
        t = threading.Thread(target=self._process_event, args=(log, event_type, parsed), daemon=True)
        t.start()

        return Response({'received': True, 'log_id': log.pk}, status=status.HTTP_200_OK)

    def _get_config(self, config_id):
        if config_id:
            return IntegrationConfig.objects.filter(pk=config_id).first()
        return IntegrationConfig.objects.filter(system_type=self.source_system, is_active=True).first()

    def _process_event(self, log, event_type: str, payload: Any):
        """Override in subclasses to act on incoming events."""
        log.processing_status = SyncStatus.SUCCESS
        log.processed_at = timezone.now()
        log.processing_notes = 'Received and logged'
        log.save()


class SAPInboundWebhookView(BaseInboundWebhookView):
    """Receive events pushed from SAP (e.g. via SAP Event Mesh)."""
    source_system = SystemType.SAP_S4HANA

    def _process_event(self, log, event_type, payload):
        from .sync_engine import process_sap_inbound_event
        try:
            process_sap_inbound_event(log.config, event_type, payload)
            log.processing_status = SyncStatus.SUCCESS
        except Exception as exc:
            log.processing_status = SyncStatus.FAILED
            log.processing_notes = str(exc)
        log.processed_at = timezone.now()
        log.save()


class DynamicsInboundWebhookView(BaseInboundWebhookView):
    """Receive Dynamics 365 change notifications (Power Automate / Azure Service Bus)."""
    source_system = SystemType.DYNAMICS_365_BC

    def _process_event(self, log, event_type, payload):
        from .sync_engine import process_dynamics_inbound_event
        try:
            process_dynamics_inbound_event(log.config, event_type, payload)
            log.processing_status = SyncStatus.SUCCESS
        except Exception as exc:
            log.processing_status = SyncStatus.FAILED
            log.processing_notes = str(exc)
        log.processed_at = timezone.now()
        log.save()


class SageInboundWebhookView(BaseInboundWebhookView):
    """Receive Sage Intacct webhook events."""
    source_system = SystemType.SAGE_INTACCT


class ShopifyInboundWebhookView(BaseInboundWebhookView):
    """Receive Shopify webhook events (orders, fulfilments, inventory)."""
    source_system = SystemType.SHOPIFY

    def _verify_signature(self, raw_body, request, config):
        hmac_header = request.headers.get('X-Shopify-Hmac-Sha256', '')
        if config:
            from .adapters.generic import ShopifyAdapter
            adapter = ShopifyAdapter(config)
            return adapter.verify_webhook(raw_body, hmac_header)
        return None

    def _process_event(self, log, event_type, payload):
        """Map Shopify order.created -> DTSG Sales Order."""
        from .sync_engine import process_shopify_order
        try:
            if event_type in ('orders/create', 'orders/updated'):
                process_shopify_order(log.config, payload)
            log.processing_status = SyncStatus.SUCCESS
        except Exception as exc:
            log.processing_status = SyncStatus.FAILED
            log.processing_notes = str(exc)
        log.processed_at = timezone.now()
        log.save()


class StripeInboundWebhookView(BaseInboundWebhookView):
    """Receive Stripe webhook events (payment_intent.succeeded, etc.)."""
    source_system = SystemType.STRIPE

    def post(self, request, config_id=None):
        raw_body = request.body
        sig_header = request.headers.get('Stripe-Signature', '')
        config = self._get_config(config_id)

        # Stripe uses its own signature format
        sig_valid = None
        if config:
            from .adapters.generic import StripeAdapter
            adapter = StripeAdapter(config)
            sig_valid = adapter.verify_webhook(raw_body, sig_header)
            if sig_valid is False:
                return Response({'error': 'Invalid Stripe signature'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            parsed = json.loads(raw_body)
        except (ValueError, TypeError):
            parsed = None

        event_type = parsed.get('type', 'unknown') if parsed else 'unknown'

        log = WebhookInboundLog.objects.create(
            config=config,
            source_system=self.source_system,
            event_type=event_type,
            headers=dict(request.headers),
            raw_payload=raw_body.decode('utf-8', errors='replace')[:50000],
            parsed_payload=parsed,
            signature_valid=sig_valid,
        )

        t = threading.Thread(target=self._process_event, args=(log, event_type, parsed), daemon=True)
        t.start()
        return Response({'received': True}, status=status.HTTP_200_OK)

    def _process_event(self, log, event_type, payload):
        """Map payment_intent.succeeded -> DTSG customer receipt."""
        from .sync_engine import process_stripe_payment
        try:
            if event_type == 'payment_intent.succeeded':
                process_stripe_payment(log.config, payload.get('data', {}).get('object', {}))
            log.processing_status = SyncStatus.SUCCESS
        except Exception as exc:
            log.processing_status = SyncStatus.FAILED
            log.processing_notes = str(exc)
        log.processed_at = timezone.now()
        log.save()


class PaystackInboundWebhookView(BaseInboundWebhookView):
    source_system = SystemType.PAYSTACK

    def post(self, request, config_id=None):
        raw_body = request.body
        sig_header = request.headers.get('X-Paystack-Signature', '')
        config = self._get_config(config_id)
        if config:
            from .adapters.generic import PaystackAdapter
            adapter = PaystackAdapter(config)
            if not adapter.verify_webhook(raw_body, sig_header):
                return Response({'error': 'Invalid signature'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            parsed = json.loads(raw_body)
        except (ValueError, TypeError):
            parsed = None
        event_type = parsed.get('event', 'unknown') if parsed else 'unknown'
        log = WebhookInboundLog.objects.create(
            config=config, source_system=self.source_system,
            event_type=event_type, headers=dict(request.headers),
            raw_payload=raw_body.decode('utf-8', errors='replace')[:50000],
            parsed_payload=parsed, signature_valid=True,
        )
        t = threading.Thread(target=self._process_event, args=(log, event_type, parsed), daemon=True)
        t.start()
        return Response({'received': True})


class FlutterwaveInboundWebhookView(BaseInboundWebhookView):
    source_system = SystemType.FLUTTERWAVE

    def post(self, request, config_id=None):
        raw_body = request.body
        sig_header = request.headers.get('verif-hash', '')
        config = self._get_config(config_id)
        if config:
            from .adapters.generic import FlutterwaveAdapter
            adapter = FlutterwaveAdapter(config)
            if not adapter.verify_webhook(raw_body, sig_header):
                return Response({'error': 'Invalid signature'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            parsed = json.loads(raw_body)
        except (ValueError, TypeError):
            parsed = None
        event_type = parsed.get('event', 'unknown') if parsed else 'unknown'
        log = WebhookInboundLog.objects.create(
            config=config, source_system=self.source_system,
            event_type=event_type, headers=dict(request.headers),
            raw_payload=raw_body.decode('utf-8', errors='replace')[:50000],
            parsed_payload=parsed, signature_valid=True,
        )
        t = threading.Thread(target=self._process_event, args=(log, event_type, parsed), daemon=True)
        t.start()
        return Response({'received': True})


class GenericInboundWebhookView(BaseInboundWebhookView):
    """
    Generic inbound endpoint.
    URL: /api/v1/integrations/inbound/generic/{config_id}/
    The config_id determines which IntegrationConfig's webhook_secret is used.
    """
    source_system = SystemType.CUSTOM
