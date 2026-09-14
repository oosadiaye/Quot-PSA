"""
Superadmin API for AI provider configuration.

Three concerns, deliberately separated:

  * the **catalogue** — which providers exist and whether the platform
    allows them at all;
  * the **per-tenant, per-capability** toggles;
  * the **call log**, read-only, because an audit trail you can edit is
    not an audit trail.

Credentials are write-only throughout. A key can be set and replaced but
never read back through the API — the UI shows a masked tail so an
operator can tell which key is loaded without the API becoming a way to
exfiltrate it.
"""
from __future__ import annotations

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from superadmin.ai_models import AICall, AICapability, AIProvider, TenantAISetting
from superadmin.views import IsSuperAdminUser


class AIProviderSerializer(serializers.ModelSerializer):
    """Catalogue row. ``api_key`` is write-only; ``api_key_masked`` reads."""

    api_key = serializers.CharField(
        write_only=True, required=False, allow_blank=True,
        style={"input_type": "password"},
        help_text="Set or replace the credential. Never returned.",
    )
    api_key_masked = serializers.CharField(read_only=True)
    is_configured = serializers.BooleanField(read_only=True)
    is_usable = serializers.BooleanField(read_only=True)
    key_display = serializers.CharField(source="get_key_display", read_only=True)

    class Meta:
        model = AIProvider
        fields = [
            "id", "key", "key_display", "display_name", "base_url",
            "available_models", "is_enabled", "sort_order",
            "api_key", "api_key_masked", "is_configured", "is_usable",
            "sends_document_images", "sends_ledger_amounts", "retains_data",
            "is_broker", "data_policy_url",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def create(self, validated_data):
        secret = validated_data.pop("api_key", "")
        provider = AIProvider(**validated_data)
        if secret:
            provider.set_api_key(secret)
        provider.save()
        return provider

    def update(self, instance, validated_data):
        secret = validated_data.pop("api_key", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        # An absent key leaves the stored one alone; an explicitly empty
        # one clears it. "Not sent" and "sent as blank" are different
        # statements, and collapsing them would mean every unrelated edit
        # wiped the credential.
        if secret is not None:
            instance.set_api_key(secret)
        instance.save()
        return instance


class TenantAISettingSerializer(serializers.ModelSerializer):
    capability_display = serializers.CharField(
        source="get_capability_display", read_only=True,
    )
    provider_name = serializers.CharField(
        source="provider.display_name", read_only=True,
    )
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    is_usable = serializers.BooleanField(read_only=True)

    class Meta:
        model = TenantAISetting
        fields = [
            "id", "tenant", "tenant_name", "capability", "capability_display",
            "provider", "provider_name", "model_id", "is_active",
            "monthly_cost_cap", "require_redaction", "is_usable",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AICallSerializer(serializers.ModelSerializer):
    capability_display = serializers.CharField(
        source="get_capability_display", read_only=True,
    )
    provider_name = serializers.CharField(
        source="provider.display_name", read_only=True,
    )
    total_tokens = serializers.IntegerField(read_only=True)

    class Meta:
        model = AICall
        fields = [
            "id", "tenant", "capability", "capability_display",
            "provider", "provider_name", "model_id",
            "request_hash", "redacted_field_count",
            "status", "http_status", "error_message",
            "prompt_tokens", "completion_tokens", "total_tokens",
            "cost_usd", "latency_ms", "subject", "created_at",
        ]


class AIProviderViewSet(viewsets.ModelViewSet):
    """The provider catalogue. Superadmin only."""

    serializer_class = AIProviderSerializer
    permission_classes = [IsAuthenticated, IsSuperAdminUser]
    queryset = AIProvider.objects.all()

    @action(detail=True, methods=["post"], url_path="toggle")
    def toggle(self, request, pk=None):
        """Flip the platform-wide switch for one provider.

        Refuses to enable a provider with no credential: the toggle would
        read as on while every call failed at the provider with a 401,
        which is a worse state than an honest refusal.
        """
        provider = self.get_object()
        if not provider.is_enabled and not provider.is_configured:
            return Response(
                {
                    "detail": (
                        f"{provider.display_name} has no API key. Add one "
                        f"before enabling it."
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
        """Call the provider's model catalogue to prove the key works.

        Chosen deliberately over a completion: it is free, fast, and
        answers the only question an operator has at this point — is this
        key accepted.
        """
        import requests

        provider = self.get_object()
        if not provider.is_configured:
            return Response(
                {"detail": "No API key set.", "code": "no_credential"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            url = provider.base_url.rstrip("/") + "/models"
            headers = (
                {"x-api-key": provider.api_key, "anthropic-version": "2023-06-01"}
                if provider.key == AIProvider.Key.ANTHROPIC
                else {"Authorization": f"Bearer {provider.api_key}"}
            )
            response = requests.get(url, headers=headers, timeout=20)
            models = []
            if response.ok:
                payload = response.json()
                models = payload.get("data") or payload.get("models") or []
            return Response({
                "ok": response.ok,
                "http_status": response.status_code,
                "model_count": len(models),
                "detail": "Key accepted." if response.ok else response.text[:200],
            })
        except Exception as exc:                      # noqa: BLE001
            return Response(
                {"ok": False, "detail": str(exc)[:200]},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    @action(detail=True, methods=["post"], url_path="sync-models")
    def sync_models(self, request, pk=None):
        """Refresh ``available_models`` from the provider, pricing included.

        Pricing is what makes the monthly ceiling enforceable, so this is
        not cosmetic: a stale catalogue means calls costed at zero.
        """
        import requests

        provider = self.get_object()
        if not provider.is_configured:
            return Response(
                {"detail": "No API key set.", "code": "no_credential"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            url = provider.base_url.rstrip("/") + "/models"
            headers = (
                {"x-api-key": provider.api_key, "anthropic-version": "2023-06-01"}
                if provider.key == AIProvider.Key.ANTHROPIC
                else {"Authorization": f"Bearer {provider.api_key}"}
            )
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            raw = response.json().get("data") or []
            provider.available_models = [
                {
                    "id": m.get("id"),
                    "label": m.get("name") or m.get("id"),
                    "pricing": m.get("pricing") or {},
                }
                for m in raw if m.get("id")
            ]
            provider.save(update_fields=["available_models", "updated_at"])
            return Response({
                "ok": True,
                "model_count": len(provider.available_models),
            })
        except Exception as exc:                      # noqa: BLE001
            return Response(
                {"ok": False, "detail": str(exc)[:200]},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class TenantAISettingViewSet(viewsets.ModelViewSet):
    """Per-tenant, per-capability toggles."""

    serializer_class = TenantAISettingSerializer
    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    def get_queryset(self):
        qs = TenantAISetting.objects.select_related("tenant", "provider")
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
        """Tenant kill switch.

        The first question in an incident is "can you stop it now", and
        the answer has to be one action rather than a walk through every
        capability.
        """
        tenant_id = request.data.get("tenant")
        if not tenant_id:
            return Response(
                {"detail": "tenant is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        count = TenantAISetting.objects.filter(
            tenant_id=tenant_id, is_active=True,
        ).update(is_active=False, updated_at=timezone.now())
        return Response({"disabled": count})

    @action(detail=False, methods=["get"], url_path="capabilities")
    def capabilities(self, request):
        """The capability list, so the UI need not hardcode it."""
        return Response([
            {"value": c.value, "label": c.label} for c in AICapability
        ])


class AICallViewSet(viewsets.ReadOnlyModelViewSet):
    """The call log. Read-only: an editable audit trail is not one."""

    serializer_class = AICallSerializer
    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    def get_queryset(self):
        qs = AICall.objects.select_related("provider", "tenant")
        params = self.request.query_params
        if params.get("tenant"):
            qs = qs.filter(tenant_id=params["tenant"])
        if params.get("capability"):
            qs = qs.filter(capability=params["capability"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        return qs

    @action(detail=False, methods=["get"], url_path="usage")
    def usage(self, request):
        """Spend and volume for the current month, per tenant.

        This is what a cost ceiling is enforced against, so it reads from
        the same rows the ceiling counts rather than a separate tally
        that could drift from them.
        """
        now = timezone.now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        rows = (
            AICall.objects
            .filter(created_at__gte=start)
            .values("tenant", "tenant__name", "capability")
            .annotate(
                calls=Count("id"),
                cost=Sum("cost_usd"),
                prompt_tokens=Sum("prompt_tokens"),
                completion_tokens=Sum("completion_tokens"),
            )
            .order_by("-cost")
        )
        return Response({"period_start": start, "rows": list(rows)})
