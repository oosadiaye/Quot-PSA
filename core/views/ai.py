"""
Tenant-facing view of AI configuration.

The superadmin API in ``superadmin/ai_views.py`` is the control surface:
it holds credentials, enables providers platform-wide, and provisions
capabilities. This is its counterpart for the organisation on the
receiving end, and it answers a different question — not "what may I
configure" but **"what is switched on for us, where does our data go, and
what has it done"**.

Three rules shape it.

**The tenant comes from the connection, never from the request.** Every
queryset here is scoped by ``connection.tenant``, which django-tenants
resolves from the hostname before the view runs. A tenant id in a query
parameter would be a horizontal-access hole in a system where the rows
being filtered are in the *public* schema and therefore visible to every
tenant's database session.

**Credentials are not tenant-visible.** The provider's name and its data
policy are exactly what a ministry needs in order to judge the
arrangement; the API key and base URL are not theirs to see. This
serializer names its fields explicitly rather than excluding, so a field
added to the model later cannot leak by default.

**A tenant switches capabilities on and off; the platform provisions
them.** Choosing a provider and model, and committing spend, is the
platform's decision, made once when a capability is set up. After that the
organisation controls whether an already-provisioned capability is
running — switching one back on is theirs, and stopping one must never need
a support ticket. A capability the platform has not provisioned cannot be
turned on here, and turning a tenant toggle on never overrides a platform
switch that is off: usability still fails closed.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import connection
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsTenantAdmin
from superadmin.ai_models import AICall, TenantAISetting


def _tenant():
    """The tenant for this request, or None on the public schema."""
    tenant = getattr(connection, "tenant", None)
    if tenant is None or getattr(tenant, "schema_name", "public") == "public":
        return None
    return tenant


class TenantAIStatusSerializer(serializers.ModelSerializer):
    """One capability as its own organisation sees it.

    Fields are listed explicitly. ``exclude`` would mean that adding
    ``api_key_encrypted``-adjacent data to a related model later could
    start reaching tenants without anyone deciding it should.
    """

    capability_display = serializers.CharField(
        source="get_capability_display", read_only=True,
    )
    provider_name = serializers.CharField(
        source="provider.display_name", read_only=True,
    )
    # Data-policy flags travel with the row on purpose: the point of
    # showing a tenant which provider serves a capability is so they can
    # judge it, and the provider's name alone does not tell them whether
    # content is retained or brokered onward.
    provider_retains_data = serializers.BooleanField(
        source="provider.retains_data", read_only=True,
    )
    provider_is_broker = serializers.BooleanField(
        source="provider.is_broker", read_only=True,
    )
    provider_data_policy_url = serializers.CharField(
        source="provider.data_policy_url", read_only=True,
    )
    sends_document_images = serializers.BooleanField(
        source="provider.sends_document_images", read_only=True,
    )
    sends_ledger_amounts = serializers.BooleanField(
        source="provider.sends_ledger_amounts", read_only=True,
    )
    is_usable = serializers.BooleanField(read_only=True)

    class Meta:
        model = TenantAISetting
        fields = [
            "id", "capability", "capability_display",
            "provider_name", "provider_retains_data", "provider_is_broker",
            "provider_data_policy_url",
            "sends_document_images", "sends_ledger_amounts",
            "model_id", "is_active", "is_usable",
            "require_redaction", "monthly_cost_cap",
        ]
        read_only_fields = fields


class TenantAICallSerializer(serializers.ModelSerializer):
    """One call from the tenant's own audit trail.

    ``request_hash`` is included and the payload is not, which is the
    whole design: the row proves a call happened and lets two records be
    compared, without the log becoming a second copy of the ledger content
    that redaction removed on the way out.
    """

    capability_display = serializers.CharField(
        source="get_capability_display", read_only=True,
    )
    provider_name = serializers.CharField(
        source="provider.display_name", read_only=True,
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    total_tokens = serializers.IntegerField(read_only=True)

    class Meta:
        model = AICall
        fields = [
            "id", "capability", "capability_display", "provider_name",
            "model_id", "request_hash", "redacted_field_count",
            "status", "status_display", "error_message",
            "prompt_tokens", "completion_tokens", "total_tokens",
            "cost_usd", "latency_ms", "subject", "created_at",
        ]
        read_only_fields = fields


def _month_start():
    now = timezone.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def ai_status(request):
    """What AI is switched on for this organisation, and what it has cost."""
    tenant = _tenant()
    if tenant is None:
        return Response(
            {"detail": "No tenant on this request."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    settings_qs = (
        TenantAISetting.objects
        .select_related("provider")
        .filter(tenant=tenant)
        .order_by("capability")
    )

    start = _month_start()
    spend = {
        row["capability"]: row
        for row in (
            AICall.objects
            .filter(tenant=tenant, created_at__gte=start)
            .values("capability")
            .annotate(
                calls=Count("id"),
                cost=Sum("cost_usd"),
                prompt_tokens=Sum("prompt_tokens"),
                completion_tokens=Sum("completion_tokens"),
            )
        )
    }

    rows = []
    for row in TenantAIStatusSerializer(settings_qs, many=True).data:
        used = spend.get(row["capability"], {})
        rows.append({
            **row,
            "calls_this_month": used.get("calls", 0),
            # Sum() over an empty set is None, which would render as a
            # blank cell where 0 is the truthful answer.
            "spend_this_month": used.get("cost") or Decimal("0"),
        })

    totals = {
        "calls": sum(r["calls_this_month"] for r in rows),
        "spend": sum((r["spend_this_month"] for r in rows), Decimal("0")),
        "active": sum(1 for r in rows if r["is_active"]),
        "usable": sum(1 for r in rows if r["is_usable"]),
    }

    return Response({
        "tenant_name": tenant.name,
        "period_start": start,
        "capabilities": rows,
        "totals": totals,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def ai_calls(request):
    """This organisation's AI audit trail. Read-only, newest first."""
    tenant = _tenant()
    if tenant is None:
        return Response(
            {"detail": "No tenant on this request."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = AICall.objects.select_related("provider").filter(tenant=tenant)
    if request.query_params.get("capability"):
        qs = qs.filter(capability=request.query_params["capability"])
    if request.query_params.get("status"):
        qs = qs.filter(status=request.query_params["status"])

    try:
        limit = min(int(request.query_params.get("limit", 50)), 200)
    except (TypeError, ValueError):
        limit = 50

    total = qs.count()
    return Response({
        "count": total,
        "results": TenantAICallSerializer(qs[:limit], many=True).data,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def ai_disable_all(request):
    """Switch every AI capability off for this organisation.

    Deliberately one-directional. There is no tenant-side enable: turning
    a capability on selects a model, commits spend and sends content to a
    named third party, which is the platform's decision to make with the
    customer. Turning it off is the organisation's alone, and needing a
    support ticket to stop something is not a control.
    """
    tenant = _tenant()
    if tenant is None:
        return Response(
            {"detail": "No tenant on this request."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    disabled = TenantAISetting.objects.filter(
        tenant=tenant, is_active=True,
    ).update(is_active=False, updated_at=timezone.now())
    return Response({"disabled": disabled})


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantAdmin])
def ai_enable(request):
    """Switch one already-provisioned AI capability back on for this org.

    The counterpart to :func:`ai_disable_all`. A tenant may re-enable only a
    capability the platform has already provisioned for them — a
    :class:`TenantAISetting` row that already carries the provider and model
    the platform chose. This never creates a setting and never picks a
    provider, model or spend cap; those remain the platform's decision. It
    also cannot force a capability into use: ``is_usable`` still fails closed,
    so a tenant toggle on while the platform switch is off stays unusable, and
    the response says so. Enabling a capability with no provisioned row is
    refused, because choosing a model and committing spend is not the
    tenant's to do.
    """
    tenant = _tenant()
    if tenant is None:
        return Response(
            {"detail": "No tenant on this request."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    capability = (request.data or {}).get("capability")
    if not capability:
        return Response(
            {"detail": "A capability is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        setting = TenantAISetting.objects.select_related("provider").get(
            tenant=tenant, capability=capability,
        )
    except TenantAISetting.DoesNotExist:
        return Response(
            {"detail": (
                "That capability has not been provisioned for this "
                "organisation. Ask your platform administrator to set it up "
                "— choosing the provider and model is theirs to do."
            )},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not setting.is_active:
        setting.is_active = True
        setting.updated_at = timezone.now()
        setting.save(update_fields=["is_active", "updated_at"])

    return Response({
        "capability": setting.capability,
        "capability_display": setting.get_capability_display(),
        "is_active": setting.is_active,
        "is_usable": setting.is_usable,
    })
