from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    IntegrationConfigViewSet,
    WebhookEndpointViewSet,
    SyncLogViewSet,
    SAPInboundWebhookView,
    DynamicsInboundWebhookView,
    SageInboundWebhookView,
    ShopifyInboundWebhookView,
    StripeInboundWebhookView,
    PaystackInboundWebhookView,
    FlutterwaveInboundWebhookView,
    GenericInboundWebhookView,
)

router = DefaultRouter()
router.register('configs', IntegrationConfigViewSet, basename='integration-config')
router.register('webhook-endpoints', WebhookEndpointViewSet, basename='webhook-endpoint')
router.register('sync-logs', SyncLogViewSet, basename='sync-log')

# Inbound webhook receivers — no auth (HMAC verified inside view)
inbound_patterns = [
    path('sap/', SAPInboundWebhookView.as_view(), name='inbound-sap'),
    path('dynamics/', DynamicsInboundWebhookView.as_view(), name='inbound-dynamics'),
    path('sage/', SageInboundWebhookView.as_view(), name='inbound-sage'),
    path('shopify/', ShopifyInboundWebhookView.as_view(), name='inbound-shopify'),
    path('stripe/', StripeInboundWebhookView.as_view(), name='inbound-stripe'),
    path('paystack/', PaystackInboundWebhookView.as_view(), name='inbound-paystack'),
    path('flutterwave/', FlutterwaveInboundWebhookView.as_view(), name='inbound-flutterwave'),
    path('generic/<uuid:config_id>/', GenericInboundWebhookView.as_view(), name='inbound-generic'),
]

urlpatterns = [
    path('', include(router.urls)),
    path('inbound/', include(inbound_patterns)),
]
