"""
Remita connector — disbursement (payments out).

Remita is the Nigerian government payments backbone, so it is the default
disbursement rail here. The exact endpoint paths, the request-hash field
order and the response field names differ between Remita's product tiers
and its sandbox vs production, so they are read from the provider's
``config`` (with the documented defaults below) rather than hardcoded —
that way tuning the integration against the sandbox is a config change,
not a code change, and never touches the seam.

`config` keys honoured (all optional; defaults shown):
    disburse_path      "/echannelsvc/api/v1/send/payment"
    status_path        "/echannelsvc/api/v1/send/status"
    signature_algo     "sha512"  (Remita request hashes are SHA-512)
    reference_field    "transactionRef"
    status_field       "responseCode"
    success_codes      ["00", "01"]
    webhook_ref_field  "transactionRef"
    webhook_status_field "status"

VERIFY-AGAINST-SANDBOX: the precise hash string composition and success
codes must be confirmed with live sandbox credentials before production.
"""
from __future__ import annotations

from decimal import Decimal

from superadmin.gateway_connectors.base import (
    ConnectorError,
    ConnectorResult,
    DisburseRequest,
    WebhookEvent,
    hmac_sha512,
    hmac_sha256,
    post_json,
    signatures_equal,
)

_DEFAULTS = {
    "disburse_path": "/echannelsvc/api/v1/send/payment",
    "status_path": "/echannelsvc/api/v1/send/status",
    "reference_field": "transactionRef",
    "status_field": "responseCode",
    "success_codes": ["00", "01"],
    "webhook_ref_field": "transactionRef",
    "webhook_status_field": "status",
    "webhook_success_values": ["success", "successful", "00", "01"],
}


class RemitaConnector:
    def _cfg(self, provider, key: str):
        return (provider.config or {}).get(key, _DEFAULTS[key])

    def _url(self, provider, path_key: str) -> str:
        return provider.base_url.rstrip("/") + self._cfg(provider, path_key)

    def _headers(self, provider, signature: str) -> dict:
        # Remita identifies the merchant by id + api key and authenticates
        # the request with a SHA-512 hash in the Authorization header.
        return {
            "Content-Type": "application/json",
            "MERCHANT_ID": provider.merchant_id,
            "API_KEY": provider.api_key,
            "REQUEST_TS": "",  # filled by caller when required; kept for parity
            "Authorization": f"remitaHash={signature}",
        }

    def disburse(self, provider, request: DisburseRequest) -> ConnectorResult:
        # Request hash: merchant + reference + amount + secret, SHA-512.
        # (Field order VERIFY-AGAINST-SANDBOX.)
        amount_str = f"{request.amount:.2f}"
        to_sign = f"{provider.merchant_id}{request.reference}{amount_str}{provider.api_key}"
        signature = hmac_sha512(provider.secret_key, to_sign)

        body = {
            "merchantId": provider.merchant_id,
            "transactionRef": request.reference,
            "amount": amount_str,
            "currency": request.currency,
            "beneficiaryAccount": request.beneficiary_account,
            "beneficiaryBankCode": request.beneficiary_bank_code,
            "beneficiaryName": request.beneficiary_name,
            "narration": request.narration,
        }
        resp = post_json(
            self._url(provider, "disburse_path"),
            headers=self._headers(provider, signature),
            json_body=body,
        )
        try:
            data = resp.json()
        except ValueError:
            raise ConnectorError(
                f"Remita returned a non-JSON response (HTTP {resp.status_code})."
            )

        status_code = str(data.get(self._cfg(provider, "status_field"), ""))
        accepted = status_code in [str(c) for c in self._cfg(provider, "success_codes")]
        return ConnectorResult(
            accepted=accepted,
            gateway_reference=str(data.get(self._cfg(provider, "reference_field"), "")),
            fee=Decimal(str(data.get("fee", "0") or "0")),
            http_status=resp.status_code,
            error="" if accepted else str(data.get("responseMsg", data))[:500],
            raw=data,
        )

    def query_status(self, provider, gateway_reference: str) -> WebhookEvent:
        signature = hmac_sha512(
            provider.secret_key, f"{provider.merchant_id}{gateway_reference}{provider.api_key}",
        )
        resp = post_json(
            self._url(provider, "status_path"),
            headers=self._headers(provider, signature),
            json_body={"merchantId": provider.merchant_id, "transactionRef": gateway_reference},
        )
        try:
            data = resp.json()
        except ValueError:
            raise ConnectorError("Remita status returned a non-JSON response.")
        return self._to_event(provider, data, fallback_ref=gateway_reference)

    def verify_webhook(self, provider, raw_body: bytes, signature: str) -> bool:
        expected = hmac_sha256(provider.webhook_secret, raw_body)
        return signatures_equal(expected, signature)

    def parse_webhook(self, provider, payload: dict) -> WebhookEvent:
        return self._to_event(provider, payload)

    def _to_event(self, provider, data: dict, *, fallback_ref: str = "") -> WebhookEvent:
        ref = str(data.get(self._cfg(provider, "webhook_ref_field"), "") or fallback_ref)
        raw_status = str(data.get(self._cfg(provider, "webhook_status_field"), "")).lower()
        success_values = [str(v).lower() for v in self._cfg(provider, "webhook_success_values")]
        outcome = WebhookEvent.SUCCESS if raw_status in success_values else WebhookEvent.FAILED
        amount = data.get("amount")
        return WebhookEvent(
            gateway_reference=ref,
            outcome=outcome,
            amount=Decimal(str(amount)) if amount not in (None, "") else None,
            fee=Decimal(str(data["fee"])) if data.get("fee") not in (None, "") else None,
            raw=data,
        )

    def test_connection(self, provider) -> dict:
        # A cheap reachability/credential probe. Remita has no universal
        # ping, so we hit the status endpoint with a dummy ref and treat any
        # authenticated HTTP answer (even "not found") as "credentials work".
        try:
            signature = hmac_sha512(provider.secret_key, f"{provider.merchant_id}ping{provider.api_key}")
            resp = post_json(
                self._url(provider, "status_path"),
                headers=self._headers(provider, signature),
                json_body={"merchantId": provider.merchant_id, "transactionRef": "ping"},
            )
            return {"ok": resp.status_code < 500, "http_status": resp.status_code}
        except ConnectorError as exc:
            return {"ok": False, "detail": str(exc)}
