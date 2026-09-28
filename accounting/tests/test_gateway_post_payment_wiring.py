"""Auto-fire wiring: PaymentViewSet.post_payment → gateway disbursement.

The dispatch mechanics (clearing journal, settle, reversal) are pinned in
test_gateway_disbursement.py; the webhook in superadmin/tests/test_gateway_webhook.py.
Here we pin the *routing decision* in post_payment:

  * Toggle ON  + an eligible invoice-backed vendor payable → the gateway fires
    (DR AP / CR deductions / CR Gateway Clearing; NO bank credit — cash parked).
  * Toggle OFF (no active setting)                         → the normal
    DR AP / CR Bank post runs and the gateway is never called (fail-closed).

Requests go through the REAL middleware stack (APIClient + HTTP_X_TENANT_DOMAIN)
so TenantMainMiddleware sets ``connection.tenant`` to the pytest_schema Client —
the gateway branch resolves the TenantGatewaySetting off that. An APIRequestFactory
call would leave a FakeTenant (no pk) and always fail closed to the bank path.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest

from superadmin.gateway_client import GatewayResult

POST_URL = "/api/v1/accounting/payments/{pk}/post_payment/"


# ── Shared-graph builders (public schema) ──────────────────────────────

def _public_client_and_admin():
    """Re-assert the pytest_schema Client + Domain + a superuser, pinned to
    public (a preceding transaction=True test flushes these — see project
    memory ci_tenant_flush_wipes_domain). Returns (tenant, user); leaves the
    connection on public (caller restores)."""
    from django.contrib.auth import get_user_model
    from tenants.models import Client, Domain
    tenant, _ = Client.objects.get_or_create(
        schema_name="pytest_schema", defaults={"name": "PyTest Tenant"},
    )
    Domain.objects.get_or_create(
        domain="pytest.localhost", tenant=tenant, defaults={"is_primary": True},
    )
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="gw_wire_admin", defaults={"is_staff": True, "is_superuser": True},
    )
    return tenant, user


def _activate_gateway_for(tenant):
    """Create a usable Remita provider + an ACTIVE TenantGatewaySetting for
    ``tenant`` (both public/shared). Caller must already be on public."""
    from superadmin.gateway_models import PaymentGatewayProvider, TenantGatewaySetting
    provider = PaymentGatewayProvider(
        key=PaymentGatewayProvider.Key.REMITA, display_name="Remita",
        base_url="https://sandbox.remita.test", is_enabled=True,
        supports_disbursement=True, merchant_id="M1",
        api_key_encrypted="gwv1:x", secret_key_encrypted="gwv1:x",
    )
    provider.save()
    return TenantGatewaySetting.objects.create(
        tenant=tenant, provider=provider, is_active=True,
    )


@pytest.fixture
def gw_wiring(db):
    """(APIClient pinned to the pytest tenant, tenant, activate_gateway callable).

    Calling ``activate_gateway()`` creates the active setting; omitting it
    leaves the tenant with no gateway (the fail-closed / toggle-OFF case)."""
    from django.db import connection
    from rest_framework.test import APIClient
    previous = getattr(connection, "schema_name", "public")
    connection.set_schema_to_public()
    try:
        tenant, user = _public_client_and_admin()
    finally:
        try:
            connection.set_schema(previous)
        except Exception:
            connection.set_schema_to_public()

    def activate_gateway():
        prev = getattr(connection, "schema_name", "public")
        connection.set_schema_to_public()
        try:
            return _activate_gateway_for(tenant)
        finally:
            try:
                connection.set_schema(prev)
            except Exception:
                connection.set_schema_to_public()

    client = APIClient(HTTP_X_TENANT_DOMAIN="pytest.localhost")
    client.force_authenticate(user=user)
    return client, tenant, activate_gateway


def _invoice_backed_vendor_payment(bank_account):
    """Build an invoice-backed vendor PV payment whose vendor HAS bank details
    (gateway-eligible). Reuses the proven central-payment builders."""
    from accounting.models.receivables import VendorInvoice
    from accounting.tests.test_central_payment_processing import (
        _vendor, _accounts, _make_pv, _add_wht, _provision,
    )
    vendor = _vendor()
    vendor.bank_account_number = "0123456789"
    vendor.bank_sort_code = "057"
    vendor.bank_name = "Zenith Bank"
    vendor.save()
    ap, wht_gl, _ = _accounts()
    inv_no = f"VINV-{uuid.uuid4().hex[:8]}"
    VendorInvoice.objects.create(
        invoice_number=inv_no, vendor=vendor,
        total_amount=Decimal("100000.00"), status="Posted",
    )
    pv = _make_pv(invoice_number=inv_no, gross=Decimal("100000.00"), vendor=vendor)
    _add_wht(pv, wht_gl, "10000.00")  # net 90,000
    payment = _provision(pv)
    payment.bank_account = bank_account
    payment.save()
    return payment, ap, wht_gl


def _mock_disburse_ok():
    calls = []

    def _fake(**kw):
        calls.append(kw)
        return GatewayResult(
            transaction_id=1, status="sent", accepted=True, gateway_reference="RMT-1",
        )

    return _fake, calls


@pytest.mark.django_db(transaction=True)
def test_post_payment_fires_gateway_when_active(
    gw_wiring, bank_account_for_batch, open_fiscal_period,
):
    """Toggle ON + eligible vendor payable → the payout is dispatched through
    the gateway and books to the clearing GL, not Bank."""
    from accounting.models import JournalHeader
    from accounting.services import gateway_disbursement
    client, _tenant, activate_gateway = gw_wiring
    activate_gateway()
    payment, ap, wht_gl = _invoice_backed_vendor_payment(bank_account_for_batch)

    fake, calls = _mock_disburse_ok()
    with patch.object(gateway_disbursement, "disburse", fake):
        resp = client.post(POST_URL.format(pk=payment.pk), {}, format="json")

    assert resp.status_code == 200, getattr(resp, "data", resp)
    payment.refresh_from_db()
    assert payment.status == "Posted"
    j = payment.journal_entry
    assert j.source_module == "gateway_disbursement"
    lines = {l.account_id: (l.debit or 0, l.credit or 0) for l in j.lines.all()}
    assert lines[ap.id][0] == Decimal("100000.00")            # DR AP gross
    assert lines[wht_gl.id][1] == Decimal("10000.00")         # CR WHT
    # CR clearing (net) — and the bank GL is NOT credited (cash not moved yet).
    assert bank_account_for_batch.gl_account_id not in lines
    assert len(calls) == 1                                    # dispatched once
    assert calls[0]["request"].amount == Decimal("90000.00")  # net to the PSP


@pytest.mark.django_db(transaction=True)
def test_post_payment_uses_bank_when_gateway_inactive(
    gw_wiring, bank_account_for_batch, open_fiscal_period,
):
    """Toggle OFF (no active setting) → the normal DR AP / CR Bank post runs
    and the gateway is never called (fail-closed)."""
    from accounting.services import gateway_disbursement
    client, _tenant, _activate = gw_wiring   # activate_gateway NOT called
    payment, ap, _wht = _invoice_backed_vendor_payment(bank_account_for_batch)

    fake, calls = _mock_disburse_ok()
    with patch.object(gateway_disbursement, "disburse", fake):
        resp = client.post(POST_URL.format(pk=payment.pk), {}, format="json")

    assert resp.status_code == 200, getattr(resp, "data", resp)
    payment.refresh_from_db()
    assert payment.status == "Posted"
    j = payment.journal_entry
    assert j.source_module != "gateway_disbursement"          # normal AP post
    lines = {l.account_id: (l.debit or 0, l.credit or 0) for l in j.lines.all()}
    assert lines[ap.id][0] == Decimal("100000.00")            # DR AP gross
    assert lines[bank_account_for_batch.gl_account_id][1] == Decimal("90000.00")  # CR bank net
    assert calls == []                                        # gateway NOT called
