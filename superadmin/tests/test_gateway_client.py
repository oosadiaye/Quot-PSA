"""
The disbursement seam: what it refuses, what it makes idempotent, what it
records. The connector is mocked — this pins the seam's guarantees, not any
PSP's API.

All models are in the public/shared schema, so these run against the
default ``db`` fixture without a tenant schema; the Client is a plain
public-schema row (``auto_create_schema=False`` project-wide).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from superadmin.gateway_client import GatewayRefused, disburse
from superadmin.gateway_connectors.base import (
    ConnectorError,
    ConnectorResult,
    DisburseRequest,
)
from superadmin.gateway_models import (
    GatewayTransaction,
    PaymentGatewayProvider,
    TenantGatewaySetting,
)


class FakeConnector:
    def __init__(self, *, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def disburse(self, provider, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.result


def _request(reference="PAY-1", amount="1000.00"):
    return DisburseRequest(
        reference=reference, amount=Decimal(amount),
        beneficiary_account="0123456789", beneficiary_bank_code="058",
        beneficiary_name="ACME Ltd", narration="Milestone payment",
    )


@pytest.fixture
def tenant(db):
    from tenants.models import Client
    client = Client(schema_name="gw_test", name="GW Test")
    client.auto_create_schema = False
    client.save()
    return client


@pytest.fixture
def usable_provider(db):
    # is_configured only checks the encrypted fields are non-empty, and the
    # connector is mocked, so the seam tests need no real KEK/crypto — that
    # is covered in test_gateway_models.py. Set the envelopes directly.
    p = PaymentGatewayProvider(
        key=PaymentGatewayProvider.Key.REMITA, display_name="Remita",
        base_url="https://sandbox.remita.test", is_enabled=True,
        supports_disbursement=True, merchant_id="M1",
        api_key_encrypted="gwv1:dummy", secret_key_encrypted="gwv1:dummy",
    )
    p.save()
    return p


def _setting(tenant, provider, *, active=True, cap="0"):
    return TenantGatewaySetting.objects.create(
        tenant=tenant, provider=provider, is_active=active,
        per_transaction_cap=Decimal(cap),
    )


def _accepted_conn(monkeypatch, **kw):
    fake = FakeConnector(result=ConnectorResult(
        accepted=True, gateway_reference="RMT-9", http_status=200, **kw,
    ))
    monkeypatch.setattr("superadmin.gateway_client.get_connector", lambda p: fake)
    return fake


@pytest.mark.django_db
class TestDisburseSeam:
    def test_refuses_when_setting_inactive(self, tenant, usable_provider, monkeypatch):
        setting = _setting(tenant, usable_provider, active=False)
        fake = _accepted_conn(monkeypatch)
        with pytest.raises(GatewayRefused):
            disburse(tenant=tenant, setting=setting, request=_request())
        # Nothing was sent, and the refusal is on the record.
        assert fake.calls == []
        assert GatewayTransaction.objects.filter(
            status=GatewayTransaction.Status.REFUSED,
        ).count() == 1

    def test_refuses_when_provider_cannot_disburse(self, tenant, usable_provider, monkeypatch):
        usable_provider.supports_disbursement = False
        usable_provider.save(update_fields=["supports_disbursement"])
        setting = _setting(tenant, usable_provider)
        fake = _accepted_conn(monkeypatch)
        with pytest.raises(GatewayRefused):
            disburse(tenant=tenant, setting=setting, request=_request())
        assert fake.calls == []

    def test_dispatch_records_sent(self, tenant, usable_provider, monkeypatch):
        setting = _setting(tenant, usable_provider)
        fake = _accepted_conn(monkeypatch)
        result = disburse(
            tenant=tenant, setting=setting, request=_request(),
            subject={"model": "Payment", "id": 5},
        )
        assert result.accepted is True
        txn = GatewayTransaction.objects.get(idempotency_key="PAY-1")
        assert txn.status == GatewayTransaction.Status.SENT
        assert txn.gateway_reference == "RMT-9"
        assert txn.request_hash  # a hash, not the account details
        assert txn.subject == {"model": "Payment", "id": 5}
        assert len(fake.calls) == 1

    def test_idempotent_never_double_dispatches(self, tenant, usable_provider, monkeypatch):
        setting = _setting(tenant, usable_provider)
        fake = _accepted_conn(monkeypatch)
        r1 = disburse(tenant=tenant, setting=setting, request=_request("PAY-DUP"))
        r2 = disburse(tenant=tenant, setting=setting, request=_request("PAY-DUP"))
        assert r1.transaction_id == r2.transaction_id
        assert len(fake.calls) == 1  # the retry did not reach the gateway
        assert GatewayTransaction.objects.filter(idempotency_key="PAY-DUP").count() == 1

    def test_over_cap_is_refused(self, tenant, usable_provider, monkeypatch):
        setting = _setting(tenant, usable_provider, cap="500.00")
        fake = _accepted_conn(monkeypatch)
        with pytest.raises(GatewayRefused):
            disburse(tenant=tenant, setting=setting, request=_request(amount="1000.00"))
        assert fake.calls == []

    def test_connector_error_marks_failed_and_reraises(self, tenant, usable_provider, monkeypatch):
        setting = _setting(tenant, usable_provider)
        fake = FakeConnector(error=ConnectorError("unreachable"))
        monkeypatch.setattr("superadmin.gateway_client.get_connector", lambda p: fake)
        with pytest.raises(ConnectorError):
            disburse(tenant=tenant, setting=setting, request=_request("PAY-ERR"))
        txn = GatewayTransaction.objects.get(idempotency_key="PAY-ERR")
        assert txn.status == GatewayTransaction.Status.FAILED
        assert "unreachable" in txn.error_message

    def test_declined_payment_records_failed_not_refused(self, tenant, usable_provider, monkeypatch):
        # The gateway was reached but said no: FAILED (a real outcome), not
        # REFUSED (a guardrail) — the distinction the status field exists for.
        setting = _setting(tenant, usable_provider)
        fake = FakeConnector(result=ConnectorResult(
            accepted=False, http_status=400, error="insufficient float",
        ))
        monkeypatch.setattr("superadmin.gateway_client.get_connector", lambda p: fake)
        result = disburse(tenant=tenant, setting=setting, request=_request("PAY-NO"))
        assert result.accepted is False
        txn = GatewayTransaction.objects.get(idempotency_key="PAY-NO")
        assert txn.status == GatewayTransaction.Status.FAILED
        assert len(fake.calls) == 1
