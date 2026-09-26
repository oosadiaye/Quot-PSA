"""
The inbound PSP callback: HMAC authentication, transaction resolution, and
success/failure routing. Settlement itself is mocked (its accounting is
pinned in accounting/tests/test_gateway_disbursement.py) so these focus on
the webhook's own job — who it trusts and what it dispatches.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

import pytest

from superadmin.gateway_connectors.remita import RemitaConnector
from superadmin.gateway_models import (
    GatewayService,
    GatewayTransaction,
    PaymentGatewayProvider,
)

_TEST_KEK = "0123456789abcdef" * 4
_SECRET = "whsecret-123"


def _sign(body: bytes) -> str:
    return hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def _gateway_kek(settings):
    """Gateway credentials need a KEK to encrypt/decrypt in these tests."""
    settings.GATEWAY_KEK_HEX = _TEST_KEK


# ── verify_webhook is pure crypto — test it without a database ─────────────
class TestWebhookSignature:
    def test_good_signature_accepts(self):
        provider = PaymentGatewayProvider(key="remita", display_name="Remita")
        with patch.object(type(provider), "webhook_secret", _SECRET):
            body = b'{"transactionRef":"R1","status":"success"}'
            assert RemitaConnector().verify_webhook(provider, body, _sign(body)) is True

    def test_tampered_body_rejected(self):
        provider = PaymentGatewayProvider(key="remita", display_name="Remita")
        with patch.object(type(provider), "webhook_secret", _SECRET):
            body = b'{"transactionRef":"R1","status":"success"}'
            sig = _sign(body)
            tampered = b'{"transactionRef":"R1","status":"success","amount":999}'
            assert RemitaConnector().verify_webhook(provider, tampered, sig) is False

    def test_missing_signature_rejected(self):
        provider = PaymentGatewayProvider(key="remita", display_name="Remita")
        with patch.object(type(provider), "webhook_secret", _SECRET):
            assert RemitaConnector().verify_webhook(provider, b"{}", None) is False


@pytest.fixture
def wh_provider(db):
    p = PaymentGatewayProvider(
        key=PaymentGatewayProvider.Key.REMITA, display_name="Remita",
        base_url="https://sandbox.remita.test", is_enabled=True,
        supports_disbursement=True, merchant_id="M1",
    )
    p.set_api_key("k")
    p.set_secret_key("s")
    p.set_webhook_secret(_SECRET)
    p.save()
    return p


@pytest.fixture
def wh_txn(db, wh_provider):
    from tenants.models import Client
    client = Client(schema_name="gw_wh_test", name="WH Test")
    client.auto_create_schema = False
    client.save()
    return GatewayTransaction.objects.create(
        tenant=client, provider=wh_provider,
        direction=GatewayService.DISBURSEMENT, idempotency_key="PAY-WH-1",
        gateway_reference="RMT-WH-1", amount=Decimal("500.00"),
        status=GatewayTransaction.Status.SENT,
        subject={"model": "Payment", "id": 1},
    )


def _post(client, body: dict, *, sign=True, gateway="remita"):
    raw = json.dumps(body).encode()
    headers = {}
    if sign:
        headers["HTTP_X_GATEWAY_SIGNATURE"] = _sign(raw)
    return client.post(
        f"/api/v1/gateway/webhook/{gateway}/",
        data=raw, content_type="application/json", **headers,
    )


@pytest.mark.django_db
class TestGatewayWebhook:
    def test_bad_signature_is_forbidden(self, client, wh_txn):
        raw = json.dumps({"transactionRef": "RMT-WH-1", "status": "success"}).encode()
        resp = client.post(
            "/api/v1/gateway/webhook/remita/", data=raw,
            content_type="application/json", HTTP_X_GATEWAY_SIGNATURE="deadbeef",
        )
        assert resp.status_code == 403

    def test_success_callback_settles_success(self, client, wh_txn):
        with patch("accounting.services.gateway_disbursement.settle_gateway_disbursement") as settle:
            resp = _post(client, {"transactionRef": "RMT-WH-1", "status": "success"})
        assert resp.status_code == 200
        settle.assert_called_once()
        assert settle.call_args.kwargs["success"] is True

    def test_failed_callback_settles_failure(self, client, wh_txn):
        with patch("accounting.services.gateway_disbursement.settle_gateway_disbursement") as settle:
            resp = _post(client, {"transactionRef": "RMT-WH-1", "status": "failed"})
        assert resp.status_code == 200
        settle.assert_called_once()
        assert settle.call_args.kwargs["success"] is False

    def test_unknown_reference_ignored_not_retried(self, client, wh_txn):
        with patch("accounting.services.gateway_disbursement.settle_gateway_disbursement") as settle:
            resp = _post(client, {"transactionRef": "NOPE", "status": "success"})
        assert resp.status_code == 200  # 200 so the PSP stops retrying
        settle.assert_not_called()

    def test_already_settled_is_idempotent(self, client, wh_txn):
        wh_txn.status = GatewayTransaction.Status.SUCCESS
        wh_txn.save(update_fields=["status"])
        with patch("accounting.services.gateway_disbursement.settle_gateway_disbursement") as settle:
            resp = _post(client, {"transactionRef": "RMT-WH-1", "status": "success"})
        assert resp.status_code == 200
        settle.assert_not_called()

    def test_unknown_gateway_is_bad_request(self, client):
        resp = _post(client, {"transactionRef": "x", "status": "success"}, gateway="paystack")
        assert resp.status_code == 400
