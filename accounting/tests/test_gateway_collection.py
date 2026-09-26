"""
IGR collection: the Xpresspay connector's request handling, and the
collection settlement's failure path. The success path (materialise a
RevenueCollection and post it) rides the separately-tested
post_revenue_collection_to_gl; here we pin what is specific to the gateway.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from superadmin.gateway_connectors.base import CollectRequest
from superadmin.gateway_connectors.xpresspay import XpresspayConnector
from superadmin.gateway_models import (
    GatewayService,
    GatewayTransaction,
    PaymentGatewayProvider,
)


class TestXpresspayCollection:
    """Pure request/response handling — no database."""

    def _provider(self):
        p = PaymentGatewayProvider(
            key="xpresspay", display_name="Xpresspay",
            base_url="https://sandbox.xpresspay.test", merchant_id="M1",
        )
        return p

    def test_initiate_signs_builds_and_parses(self):
        provider = self._provider()
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {
            "responseCode": "00", "transactionReference": "XP-1",
            "checkoutUrl": "https://pay.test/XP-1",
        }
        with patch.object(type(provider), "secret_key", "sec"), \
                patch.object(type(provider), "api_key", "pub"), \
                patch("superadmin.gateway_connectors.xpresspay.post_json", return_value=fake_resp) as pj:
            result = XpresspayConnector().initiate_collection(
                provider, CollectRequest(reference="IGR-1", amount=Decimal("5000.00"), payer_name="Ada"),
            )
        assert result.accepted is True
        assert result.gateway_reference == "XP-1"
        assert result.raw["checkoutUrl"] == "https://pay.test/XP-1"
        # A signed request went out.
        sent = pj.call_args.kwargs
        assert sent["headers"]["Authorization"] == "Bearer pub"
        assert sent["headers"]["X-Signature"]

    def test_declined_initiation_is_not_accepted(self):
        provider = self._provider()
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {"responseCode": "51", "responseMessage": "declined"}
        with patch.object(type(provider), "secret_key", "sec"), \
                patch.object(type(provider), "api_key", "pub"), \
                patch("superadmin.gateway_connectors.xpresspay.post_json", return_value=fake_resp):
            result = XpresspayConnector().initiate_collection(
                provider, CollectRequest(reference="IGR-2", amount=Decimal("100.00"), payer_name="Ada"),
            )
        assert result.accepted is False


@pytest.fixture
def collection_txn(db):
    from django.db import connection
    from tenants.models import Client
    previous = getattr(connection, "schema_name", "public")
    connection.set_schema_to_public()
    try:
        tenant, _ = Client.objects.get_or_create(
            schema_name="pytest_schema", defaults={"name": "PyTest Tenant"},
        )
        provider = PaymentGatewayProvider(
            key=PaymentGatewayProvider.Key.XPRESSPAY, display_name="Xpresspay",
            base_url="https://x.test", is_enabled=True, supports_collection=True,
            merchant_id="M1", api_key_encrypted="gwv1:x", secret_key_encrypted="gwv1:x",
        )
        provider.save()
        return GatewayTransaction.objects.create(
            tenant=tenant, provider=provider, direction=GatewayService.COLLECTION,
            idempotency_key="IGR-FAIL-1", gateway_reference="XP-FAIL",
            amount=Decimal("5000.00"), status=GatewayTransaction.Status.SENT,
            subject={"model": "RevenueCollection", "revenue_head_id": 1,
                     "ncoa_code_id": 1, "tsa_account_id": 1, "payer_name": "Ada"},
        )
    finally:
        try:
            connection.set_schema(previous)
        except Exception:
            connection.set_schema_to_public()


@pytest.mark.django_db
def test_settle_collection_failure_posts_nothing(collection_txn):
    from accounting.services.gateway_collection import settle_collection
    from accounting.models import RevenueCollection

    before = RevenueCollection.objects.count()
    result = settle_collection(collection_txn, success=False)
    assert result is None
    assert RevenueCollection.objects.count() == before  # no money in → no receipt
    collection_txn.refresh_from_db()
    assert collection_txn.status == GatewayTransaction.Status.FAILED
