"""
Superadmin control surface for payment gateways.

The platform provisions gateways here — credentials, the master switch,
and per-tenant enablement — exactly as ``ai_views`` does for AI providers.
Secrets are write-only in and masked out; the log is read-only.
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from superadmin.gateway_connectors import ConnectorError, get_connector
from superadmin.gateway_models import (
    GatewayTransaction,
    PaymentGatewayProvider,
    TenantGatewaySetting,
)
from superadmin.views import IsSuperAdminUser


class PaymentGatewayProviderSerializer(serializers.ModelSerializer):
    """Catalogue row. Secrets are write-only; only masked tails read back."""

    api_key = serializers.CharField(
        write_only=True, required=False, allow_blank=True,
        style={"input_type": "password"},
        help_text="Set or replace the API/public key. Never returned.",
    )
    secret_key = serializers.CharField(
        write_only=True, required=False, allow_blank=True,
        style={"input_type": "password"},
        help_text="Set or replace the signing secret. Never returned.",
    )
    webhook_secret = serializers.CharField(
        write_only=True, required=False, allow_blank=True,
        style={"input_type": "password"},
        help_text="Set or replace the webhook-verification secret. Never returned.",
    )
    api_key_masked = serializers.CharField(read_only=True)
    secret_key_masked = serializers.CharField(read_only=True)
    is_configured = serializers.BooleanField(read_only=True)
    is_usable = serializers.BooleanField(read_only=True)
    key_display = serializers.CharField(source="get_key_display", read_only=True)

    class Meta:
        model = PaymentGatewayProvider
        fields = [
            "id", "key", "key_display", "display_name", "base_url", "environment",
            "merchant_id", "config",
            "supports_disbursement", "supports_collection",
            "is_enabled", "sort_order",
            "api_key", "secret_key", "webhook_secret",
            "api_key_masked", "secret_key_masked", "is_configured", "is_usable",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def _apply_secrets(self, instance, validated_data):
        # Absent = leave alone; explicit blank = clear. Collapsing them would
        # wipe a credential on every unrelated edit.
        for field, setter in (
            ("api_key", instance.set_api_key),
            ("secret_key", instance.set_secret_key),
            ("webhook_secret", instance.set_webhook_secret),
        ):
            value = validated_data.pop(field, None)
            if value is not None:
                setter(value)

    def create(self, validated_data):
        provider = PaymentGatewayProvider()
        self._apply_secrets(provider, validated_data)
        for field, value in validated_data.items():
            setattr(provider, field, value)
        provider.save()
        return provider

    def update(self, instance, validated_data):
        self._apply_secrets(instance, validated_data)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


class TenantGatewaySettingSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source="provider.display_name", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    is_usable = serializers.BooleanField(read_only=True)

    class Meta:
        model = TenantGatewaySetting
        fields = [
            "id", "tenant", "tenant_name", "provider", "provider_name",
            "is_active", "is_default", "per_transaction_cap", "is_usable",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class GatewayTransactionSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source="provider.display_name", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = GatewayTransaction
        fields = [
            "id", "tenant", "tenant_name", "provider", "provider_name",
            "direction", "idempotency_key", "gateway_reference",
            "amount", "fee", "currency", "status", "request_hash",
            "http_status", "error_message", "subject",
            "settled_at", "created_at", "updated_at",
        ]


class PaymentGatewayProviderViewSet(viewsets.ModelViewSet):
    """The gateway catalogue. Superadmin only."""

    serializer_class = PaymentGatewayProviderSerializer
    permission_classes = [IsAuthenticated, IsSuperAdminUser]
    queryset = PaymentGatewayProvider.objects.all()

    @action(detail=True, methods=["post"], url_path="toggle")
    def toggle(self, request, pk=None):
        """Flip the platform-wide switch. Refuses to enable a keyless gateway
        (it would read as on while every call 401s)."""
        provider = self.get_object()
        if not provider.is_enabled and not provider.is_configured:
            return Response(
                {
                    "detail": (
                        f"{provider.display_name} has no credentials. Add an "
                        f"API key and signing secret before enabling it."
                    ),
                    "code": "no_credential",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        provider.is_enabled = not provider.is_enabled
        provider.save(update_fields=["is_enabled", "updated_at"])
        return Response(self.get_serializer(provider).data)

    @action(detail=True, methods=["post"], url_path="test")
    def test_connection(self, request, pk=None):
        """Cheap reachability/credential probe via the connector."""
        provider = self.get_object()
        if not provider.is_configured:
            return Response(
                {"detail": "No credentials set.", "code": "no_credential"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = get_connector(provider).test_connection(provider)
            return Response(result)
        except ConnectorError as exc:
            return Response(
                {"ok": False, "detail": str(exc)[:200]},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class TenantGatewaySettingViewSet(viewsets.ModelViewSet):
    """Per-tenant gateway provisioning."""

    serializer_class = TenantGatewaySettingSerializer
    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    def get_queryset(self):
        qs = TenantGatewaySetting.objects.select_related("tenant", "provider")
        tenant_id = self.request.query_params.get("tenant")
        return qs.filter(tenant_id=tenant_id) if tenant_id else qs

    @action(detail=True, methods=["post"], url_path="toggle")
    def toggle(self, request, pk=None):
        setting = self.get_object()
        setting.is_active = not setting.is_active
        setting.save(update_fields=["is_active", "updated_at"])
        return Response(self.get_serializer(setting).data)

    @action(detail=False, methods=["post"], url_path="disable-all")
    def disable_all(self, request):
        """Tenant kill switch — stop every gateway for one tenant in one action."""
        tenant_id = request.data.get("tenant")
        if not tenant_id:
            return Response(
                {"detail": "tenant is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        count = TenantGatewaySetting.objects.filter(
            tenant_id=tenant_id, is_active=True,
        ).update(is_active=False, updated_at=timezone.now())
        return Response({"disabled": count})


class GatewayTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """The payout/collection log. Read-only — an editable audit trail is not one."""

    serializer_class = GatewayTransactionSerializer
    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    def get_queryset(self):
        qs = GatewayTransaction.objects.select_related("tenant", "provider")
        params = self.request.query_params
        if params.get("tenant"):
            qs = qs.filter(tenant_id=params["tenant"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        return qs
