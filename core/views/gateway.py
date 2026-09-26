"""
Tenant-facing view of payment-gateway configuration.

The counterpart of :mod:`core.views.ai` for the disbursement/collection
rails. Same three rules:

* **The tenant comes from the connection, never the request** — every
  queryset is scoped by ``connection.tenant``.
* **Credentials are not tenant-visible** — the serializer names its fields
  explicitly and carries no key/secret, so a field added later cannot leak
  by default.
* **A tenant switches a provisioned gateway on or off** — it cannot create
  one or choose its credentials; that is the platform's decision.
"""
from __future__ import annotations

from django.db import connection
from django.db.models import Count
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsTenantAdmin
from superadmin.gateway_models import GatewayTransaction, TenantGatewaySetting


def _tenant():
    tenant = getattr(connection, "tenant", None)
    if tenant is None or getattr(tenant, "schema_name", "public") == "public":
        return None
    return tenant


class TenantGatewayStatusSerializer(serializers.ModelSerializer):
    """One provisioned gateway as its own organisation sees it — no secrets."""

    provider_name = serializers.CharField(source="provider.display_name", read_only=True)
    provider_key = serializers.CharField(source="provider.key", read_only=True)
    environment = serializers.CharField(source="provider.environment", read_only=True)
    supports_disbursement = serializers.BooleanField(source="provider.supports_disbursement", read_only=True)
    supports_collection = serializers.BooleanField(source="provider.supports_collection", read_only=True)
    is_usable = serializers.BooleanField(read_only=True)

    class Meta:
        model = TenantGatewaySetting
        fields = [
            "id", "provider_key", "provider_name", "environment",
            "supports_disbursement", "supports_collection",
            "is_active", "is_default", "is_usable", "per_transaction_cap",
        ]
        read_only_fields = fields


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def gateway_status(request):
    """What payment gateways are provisioned for this organisation, and which
    are switched on."""
    tenant = _tenant()
    if tenant is None:
        return Response({"detail": "No tenant on this request."}, status=status.HTTP_400_BAD_REQUEST)

    settings_qs = (
        TenantGatewaySetting.objects
        .select_related("provider")
        .filter(tenant=tenant)
        .order_by("provider__sort_order", "provider__display_name")
    )
    counts = {
        row["provider_id"]: row["n"]
        for row in (
            GatewayTransaction.objects
            .filter(tenant=tenant)
            .values("provider_id")
            .annotate(n=Count("id"))
        )
    }
    rows = []
    for setting in settings_qs:
        data = TenantGatewayStatusSerializer(setting).data
        data["transactions"] = counts.get(setting.provider_id, 0)
        rows.append(data)

    return Response({
        "tenant_name": tenant.name,
        "gateways": rows,
        "totals": {
            "provisioned": len(rows),
            "active": sum(1 for r in rows if r["is_active"]),
            "usable": sum(1 for r in rows if r["is_usable"]),
        },
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def gateway_enable(request):
    """Switch on one already-provisioned gateway for this organisation.

    Re-enables only a gateway the platform has provisioned (a
    :class:`TenantGatewaySetting` row already exists). Refuses an
    unprovisioned one — choosing the provider and credentials is the
    platform's decision. Never overrides the platform switch: usability
    still fails closed, and the response says so.
    """
    tenant = _tenant()
    if tenant is None:
        return Response({"detail": "No tenant on this request."}, status=status.HTTP_400_BAD_REQUEST)

    provider_key = (request.data or {}).get("gateway") or (request.data or {}).get("provider")
    if not provider_key:
        return Response({"detail": "A gateway is required."}, status=status.HTTP_400_BAD_REQUEST)

    setting = (
        TenantGatewaySetting.objects
        .select_related("provider")
        .filter(tenant=tenant, provider__key=provider_key)
        .first()
    )
    if setting is None:
        return Response(
            {"detail": (
                "That gateway has not been provisioned for this organisation. "
                "Ask your platform administrator to set it up."
            )},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not setting.is_active:
        setting.is_active = True
        setting.save(update_fields=["is_active", "updated_at"])

    return Response({
        "gateway": setting.provider.key,
        "provider_name": setting.provider.display_name,
        "is_active": setting.is_active,
        "is_usable": setting.is_usable,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def gateway_collect(request):
    """Raise an IGR collection through the tenant's collection gateway.

    Returns a payment reference and (when the gateway provides one) a
    checkout URL for the payer. The collection is confirmed and posted to
    the GL (DR Cash-in-TSA / CR Revenue) only when the gateway's webhook
    confirms payment — nothing is recognised on the strength of a request.
    """
    tenant = _tenant()
    if tenant is None:
        return Response({"detail": "No tenant on this request."}, status=status.HTTP_400_BAD_REQUEST)

    data = request.data or {}
    settings_qs = TenantGatewaySetting.objects.select_related("provider").filter(
        tenant=tenant, is_active=True,
        provider__is_enabled=True, provider__supports_collection=True,
    )
    if data.get("gateway"):
        settings_qs = settings_qs.filter(provider__key=data["gateway"])
    setting = settings_qs.order_by("-is_default", "provider__sort_order").first()
    if setting is None:
        return Response(
            {"detail": "No active collection gateway is available for this organisation."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    required = ["revenue_head", "ncoa_code", "tsa_account", "amount", "payer_name"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return Response(
            {"detail": f"Missing required fields: {', '.join(missing)}."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from accounting.services.gateway_collection import (
        GatewayCollectionError,
        initiate_collection,
    )
    from superadmin.gateway_client import GatewayRefused

    try:
        txn, checkout_url = initiate_collection(
            tenant=tenant, setting=setting,
            revenue_head_id=data["revenue_head"], ncoa_code_id=data["ncoa_code"],
            tsa_account_id=data["tsa_account"], amount=data["amount"],
            payer_name=data["payer_name"], payer_tin=data.get("payer_tin", ""),
            payer_phone=data.get("payer_phone", ""),
            collecting_mda_id=data.get("collecting_mda"),
            description=data.get("description", ""),
        )
    except GatewayRefused as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except GatewayCollectionError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        "status": txn.status,
        "reference": txn.idempotency_key,
        "gateway_reference": txn.gateway_reference,
        "checkout_url": checkout_url,
        "gateway": setting.provider.key,
        "gateway_transaction_id": txn.pk,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def gateway_disable_all(request):
    """Switch every gateway off for this organisation. One-directional and
    always available — the control an operator must never need a ticket for."""
    tenant = _tenant()
    if tenant is None:
        return Response({"detail": "No tenant on this request."}, status=status.HTTP_400_BAD_REQUEST)

    from django.utils import timezone
    disabled = TenantGatewaySetting.objects.filter(
        tenant=tenant, is_active=True,
    ).update(is_active=False, updated_at=timezone.now())
    return Response({"disabled": disabled})
