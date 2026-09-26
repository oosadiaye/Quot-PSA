"""
Xpresspay connector.

Per the integration split, Xpresspay is the **IGR collection** rail
(money in), not a disbursement rail. Its collection flow — generate a
payment reference / checkout, then confirm on callback — is wired in the
collection phase; what it needs now is a place in the registry, a
disbursement method that honestly declines (so the seam can never route a
payout to it), and the shared webhook verification it will use for
collection callbacks.

`config` keys honoured (defaults shown):
    signature_algo        "sha512"
    webhook_ref_field     "transactionReference"
    webhook_status_field  "status"
    webhook_success_values ["success", "successful", "00"]

VERIFY-AGAINST-SANDBOX before production.
"""
from __future__ import annotations

from decimal import Decimal

from superadmin.gateway_connectors.base import (
    ConnectorError,
    ConnectorResult,
    DisburseRequest,
    WebhookEvent,
    hmac_sha256,
    signatures_equal,
)

_DEFAULTS = {
    "webhook_ref_field": "transactionReference",
    "webhook_status_field": "status",
    "webhook_success_values": ["success", "successful", "00"],
}


class XpresspayConnector:
    def _cfg(self, provider, key: str):
        return (provider.config or {}).get(key, _DEFAULTS[key])

    def disburse(self, provider, request: DisburseRequest) -> ConnectorResult:
        # The seam guards with provider.supports_disbursement, so this should
        # never be reached; declining explicitly makes a misconfiguration a
        # clear error rather than a silent no-op.
        raise ConnectorError(
            "Xpresspay is configured as a collection (money-in) gateway and "
            "does not disburse. Route payouts through a disbursement gateway."
        )

    def query_status(self, provider, gateway_reference: str) -> WebhookEvent:
        raise ConnectorError("Xpresspay disbursement status is not applicable.")

    def verify_webhook(self, provider, raw_body: bytes, signature: str) -> bool:
        expected = hmac_sha256(provider.webhook_secret, raw_body)
        return signatures_equal(expected, signature)

    def parse_webhook(self, provider, payload: dict) -> WebhookEvent:
        ref = str(payload.get(self._cfg(provider, "webhook_ref_field"), ""))
        raw_status = str(payload.get(self._cfg(provider, "webhook_status_field"), "")).lower()
        success_values = [str(v).lower() for v in self._cfg(provider, "webhook_success_values")]
        outcome = WebhookEvent.SUCCESS if raw_status in success_values else WebhookEvent.FAILED
        amount = payload.get("amount")
        return WebhookEvent(
            gateway_reference=ref,
            outcome=outcome,
            amount=Decimal(str(amount)) if amount not in (None, "") else None,
            raw=payload,
        )

    def test_connection(self, provider) -> dict:
        return {
            "ok": provider.is_configured,
            "detail": "Credentials present" if provider.is_configured else "Not configured",
        }
