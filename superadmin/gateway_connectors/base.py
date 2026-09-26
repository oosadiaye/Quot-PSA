"""
The uniform connector contract and shared helpers.

The seam speaks these shapes to every PSP:

  * :class:`DisburseRequest`  — what we ask a gateway to pay out.
  * :class:`ConnectorResult`  — the gateway's immediate answer to a dispatch.
  * :class:`WebhookEvent`     — a settlement outcome, from a callback or a
    status poll, normalised so both paths converge on one handler.

A connector is stateless: every method takes the
:class:`~superadmin.gateway_models.PaymentGatewayProvider` so credentials,
base URL and per-provider ``config`` are read fresh and nothing sensitive
lives on the instance.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, runtime_checkable

import requests

DEFAULT_TIMEOUT = 30


class ConnectorError(Exception):
    """A gateway transport/API failure (distinct from a refusal)."""


@dataclass
class DisburseRequest:
    """A payout instruction, in the platform's own terms."""

    #: Our idempotency key AND the reference we quote to the PSP. A retry
    #: with the same value must never move money twice.
    reference: str
    amount: Decimal
    beneficiary_account: str
    beneficiary_bank_code: str
    beneficiary_name: str
    narration: str = ""
    currency: str = "NGN"


@dataclass
class ConnectorResult:
    """A gateway's immediate answer to a dispatch.

    ``accepted`` means the instruction was taken for processing — final
    settlement arrives later via a :class:`WebhookEvent`. It does NOT mean
    the money has moved.
    """

    accepted: bool
    gateway_reference: str = ""
    fee: Decimal = Decimal("0.00")
    http_status: int | None = None
    error: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class WebhookEvent:
    """A normalised settlement outcome (from callback or status poll)."""

    gateway_reference: str
    #: 'success' or 'failed' — the two terminal outcomes the ledger acts on.
    outcome: str
    amount: Decimal | None = None
    fee: Decimal | None = None
    raw: dict = field(default_factory=dict)

    SUCCESS = "success"
    FAILED = "failed"


@runtime_checkable
class GatewayConnector(Protocol):
    """What every PSP connector must provide."""

    def disburse(self, provider, request: DisburseRequest) -> ConnectorResult:
        """Send a payout instruction. Never raises on a declined payment —
        it returns ``accepted=False``; it raises :class:`ConnectorError`
        only on transport/protocol failure."""
        ...

    def query_status(self, provider, gateway_reference: str) -> WebhookEvent:
        """Poll the gateway for a transaction's settlement outcome."""
        ...

    def verify_webhook(self, provider, raw_body: bytes, signature: str) -> bool:
        """Constant-time verification of an inbound callback's signature."""
        ...

    def parse_webhook(self, provider, payload: dict) -> WebhookEvent:
        """Normalise a verified callback body into a :class:`WebhookEvent`."""
        ...

    def test_connection(self, provider) -> dict:
        """Cheap credential/reachability check for the admin Test button."""
        ...


# ── Shared helpers ───────────────────────────────────────────────────────


def hmac_sha512(secret: str, message: str) -> str:
    """Hex HMAC-SHA512 — the common Nigerian-PSP request-signature scheme."""
    return hmac.new(
        secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha512,
    ).hexdigest()


def hmac_sha256(secret: str, message: bytes) -> str:
    """Hex HMAC-SHA256 over raw bytes — used to verify webhook bodies."""
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def signatures_equal(expected: str, provided: str | None) -> bool:
    """Constant-time compare; False on anything malformed rather than raising."""
    if not provided:
        return False
    try:
        return hmac.compare_digest(expected, provided.strip())
    except (TypeError, ValueError):
        return False


def post_json(url: str, *, headers: dict, json_body: dict, timeout: int = DEFAULT_TIMEOUT):
    """POST helper that turns transport failure into :class:`ConnectorError`.

    Kept here so every connector reports network problems the same way and
    the seam can distinguish "the PSP said no" (a result) from "we could
    not reach the PSP" (an error).
    """
    try:
        return requests.post(url, headers=headers, json=json_body, timeout=timeout)
    except requests.RequestException as exc:
        raise ConnectorError(f"Gateway request failed: {exc}") from exc
