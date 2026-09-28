"""
The disbursement seam.

Every payout runs through :func:`disburse`, the money-out sibling of
:func:`superadmin.ai_client.call_model`. Its value is in what it
**refuses**, what it makes **idempotent**, and what it **records** — not
in any provider's API surface, which lives in the connectors.

    1. Idempotent: a reference already sent is returned, never sent twice.
    2. Fail closed: refuses unless the tenant toggle, the platform switch,
       the credentials, the direction and the cap all allow it — and
       records the refusal.
    3. Records a GatewayTransaction (a hash of the request, never the
       account details) whether it succeeds or fails.

Settlement is asynchronous: an accepted dispatch leaves the transaction
``SENT``; the webhook (or a status poll) later moves it to ``SUCCESS`` or
``FAILED`` and posts the ledger entries. This seam never claims money has
moved.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from decimal import Decimal

from superadmin.gateway_connectors import (
    ConnectorError,
    DisburseRequest,
    get_connector,
)
from superadmin.gateway_models import GatewayService, GatewayTransaction


class GatewayRefused(Exception):
    """Raised when a payout is refused before anything is transmitted.

    Distinct from :class:`ConnectorError` on purpose: this is the guardrail
    working, not the gateway failing, and must not be counted as an outage.
    """


@dataclass
class GatewayResult:
    transaction_id: int
    status: str
    accepted: bool
    gateway_reference: str = ""


def _hash_request(request: DisburseRequest) -> str:
    """SHA-256 of the payout instruction — proves what was sent without
    the log becoming a copy of the beneficiary's account details."""
    canonical = json.dumps(
        {
            "reference": request.reference,
            "amount": str(request.amount),
            "currency": request.currency,
            "account": request.beneficiary_account,
            "bank": request.beneficiary_bank_code,
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_refused(tenant, provider, request, subject, reason: str) -> None:
    """Log a refusal without consuming the real idempotency key, so a
    later retry (e.g. after the gateway is enabled) can still go out."""
    GatewayTransaction.objects.create(
        tenant=tenant,
        provider=provider,
        direction=GatewayService.DISBURSEMENT,
        idempotency_key=f"{request.reference}:refused:{uuid.uuid4().hex[:8]}",
        amount=request.amount,
        currency=request.currency,
        status=GatewayTransaction.Status.REFUSED,
        error_message=f"Refused before sending: {reason}"[:500],
        subject=subject,
    )


def disburse(*, tenant, setting, request: DisburseRequest, subject: dict | None = None) -> GatewayResult:
    """Dispatch one payout through a tenant's configured gateway.

    ``setting`` is a :class:`~superadmin.gateway_models.TenantGatewaySetting`;
    ``setting.is_usable`` folds the tenant toggle, the platform switch and
    credential presence into one gate.
    """
    provider = setting.provider
    subject = subject or {}

    # 1. Idempotency — a reference already dispatched is never sent twice.
    existing = GatewayTransaction.objects.filter(idempotency_key=request.reference).first()
    if existing and existing.status in (
        GatewayTransaction.Status.SENT,
        GatewayTransaction.Status.SUCCESS,
    ):
        return GatewayResult(
            existing.pk, existing.status, accepted=True,
            gateway_reference=existing.gateway_reference,
        )

    # 2. Fail closed.
    if not setting.is_usable:
        _record_refused(
            tenant, provider, request, subject,
            "the gateway is inactive for this tenant, or disabled/unconfigured platform-wide.",
        )
        raise GatewayRefused(f"Gateway {provider} is not enabled for this tenant.")
    if not provider.supports_disbursement:
        _record_refused(tenant, provider, request, subject, "this gateway does not disburse.")
        raise GatewayRefused(f"Gateway {provider} is not a disbursement gateway.")
    cap = setting.per_transaction_cap or Decimal("0")
    if cap > 0 and request.amount > cap:
        _record_refused(
            tenant, provider, request, subject,
            f"amount {request.amount} exceeds the per-transaction cap {cap}.",
        )
        raise GatewayRefused("Payout exceeds this gateway's per-transaction cap.")

    # 3. Create (or reuse) the keyed transaction and dispatch.
    txn = existing or GatewayTransaction.objects.create(
        tenant=tenant,
        provider=provider,
        direction=GatewayService.DISBURSEMENT,
        idempotency_key=request.reference,
        amount=request.amount,
        currency=request.currency,
        status=GatewayTransaction.Status.PENDING,
        request_hash=_hash_request(request),
        subject=subject,
    )

    connector = get_connector(provider)
    try:
        result = connector.disburse(provider, request)
    except ConnectorError as exc:
        # Could not reach / parse the gateway. The instruction did not land;
        # the transaction is FAILED and may be retried with the same key.
        txn.status = GatewayTransaction.Status.FAILED
        txn.error_message = str(exc)[:500]
        txn.save(update_fields=["status", "error_message", "updated_at"])
        raise

    txn.gateway_reference = result.gateway_reference or txn.gateway_reference
    txn.fee = result.fee
    txn.http_status = result.http_status
    txn.status = (
        GatewayTransaction.Status.SENT if result.accepted
        else GatewayTransaction.Status.FAILED
    )
    if not result.accepted:
        txn.error_message = result.error[:500]
    txn.save(update_fields=[
        "gateway_reference", "fee", "http_status", "status",
        "error_message", "updated_at",
    ])

    return GatewayResult(
        txn.pk, txn.status, accepted=result.accepted,
        gateway_reference=txn.gateway_reference,
    )
