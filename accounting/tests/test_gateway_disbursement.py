"""
Gateway disbursement clearing journals + auto-reversing settlement.

A standalone payment (no PV/invoice) keeps the journal to DR AP / CR
Clearing so the clearing-account mechanics are unambiguous, and avoids the
vendor-invoice tables entirely. The ``disburse`` seam is mocked — its own
guarantees are pinned in superadmin/tests/test_gateway_client.py; here we
pin the *accounting*.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from superadmin.gateway_client import GatewayResult


@pytest.fixture
def gw_accounts(db):
    from accounting.models import Account
    ap, _ = Account.objects.get_or_create(
        code="20100000",
        defaults={"name": "Accounts Payable", "account_type": "Liability", "is_active": True},
    )
    clearing, _ = Account.objects.get_or_create(
        code="20900000",
        defaults={"name": "Gateway Clearing", "account_type": "Liability", "is_active": True},
    )
    bank, _ = Account.objects.get_or_create(
        code="10100000",
        defaults={"name": "Cash and Bank", "account_type": "Asset", "is_active": True},
    )
    return {"ap": ap, "clearing": clearing, "bank": bank}


@pytest.fixture
def gw_vendor(db):
    from procurement.models import Vendor
    return Vendor.objects.create(
        name="ACME Ltd", code="V-GW", is_active=True,
        bank_name="Zenith Bank", bank_account_number="0123456789",
        bank_sort_code="057",
    )


@pytest.fixture
def gw_setting(db):
    # The gateway models are SHARED (public). Under transaction=True the
    # public Client row can be flushed between tests, and a tenant can only
    # be (re)created in the public schema — so build the whole shared graph
    # with the connection pinned to public, then restore.
    from django.db import connection
    from tenants.models import Client
    from superadmin.gateway_models import PaymentGatewayProvider, TenantGatewaySetting
    previous = getattr(connection, "schema_name", "public")
    connection.set_schema_to_public()
    try:
        tenant, _ = Client.objects.get_or_create(
            schema_name="pytest_schema", defaults={"name": "PyTest Tenant"},
        )
        p = PaymentGatewayProvider(
            key=PaymentGatewayProvider.Key.REMITA, display_name="Remita",
            base_url="https://sandbox.remita.test", is_enabled=True,
            supports_disbursement=True, merchant_id="M1",
            api_key_encrypted="gwv1:x", secret_key_encrypted="gwv1:x",
        )
        p.save()
        return TenantGatewaySetting.objects.create(tenant=tenant, provider=p, is_active=True)
    finally:
        try:
            connection.set_schema(previous)
        except Exception:
            connection.set_schema_to_public()


@pytest.fixture
def draft_payment(db, gw_vendor, open_fiscal_period):
    from accounting.models import Payment
    return Payment.objects.create(
        payment_number="PAY-GW-1", payment_method="Wire",
        total_amount=Decimal("1000.00"), status="Draft",
        vendor=gw_vendor, reference_number="Contractor payout",
    )


def _mock_disburse():
    calls = []

    def _fake(**kw):
        calls.append(kw)
        return GatewayResult(
            transaction_id=1, status="sent", accepted=True, gateway_reference="RMT-1",
        )

    return _fake, calls


@pytest.mark.django_db(transaction=True)
def test_dispatch_posts_clearing_journal_not_bank(gw_accounts, gw_setting, draft_payment):
    from accounting.services import gateway_disbursement
    fake, calls = _mock_disburse()
    with patch.object(gateway_disbursement, "disburse", fake):
        result, journal = gateway_disbursement.dispatch_payment_via_gateway(
            draft_payment, gw_setting, actor=None,
        )

    lines = list(journal.lines.all())
    assert sum(l.debit for l in lines) == Decimal("1000.00")
    assert sum(l.credit for l in lines) == Decimal("1000.00")
    debit_line = next(l for l in lines if l.debit > 0)
    credit_line = next(l for l in lines if l.credit > 0)
    assert debit_line.account_id == gw_accounts["ap"].pk       # DR Accounts Payable
    assert credit_line.account_id == gw_accounts["clearing"].pk  # CR Gateway Clearing (NOT bank)

    draft_payment.refresh_from_db()
    assert draft_payment.status == "Posted"
    assert draft_payment.journal_entry_id == journal.pk
    # The net was dispatched, tagged back to the payment.
    assert calls[0]["request"].amount == Decimal("1000.00")
    assert calls[0]["subject"] == {"model": "Payment", "id": draft_payment.pk}
    assert result.accepted is True


@pytest.mark.django_db(transaction=True)
def test_settlement_success_moves_clearing_to_bank(gw_accounts, gw_setting, draft_payment):
    from accounting.services import gateway_disbursement
    from superadmin.gateway_models import GatewayService, GatewayTransaction
    fake, _ = _mock_disburse()
    with patch.object(gateway_disbursement, "disburse", fake):
        gateway_disbursement.dispatch_payment_via_gateway(draft_payment, gw_setting)

    tenant = gw_setting.tenant
    txn = GatewayTransaction.objects.create(
        tenant=tenant, provider=gw_setting.provider,
        direction=GatewayService.DISBURSEMENT, idempotency_key="PAY-GW-1",
        amount=Decimal("1000.00"), status=GatewayTransaction.Status.SENT,
        subject={"model": "Payment", "id": draft_payment.pk},
    )
    journal = gateway_disbursement.settle_gateway_disbursement(txn, success=True)

    lines = list(journal.lines.all())
    debit_line = next(l for l in lines if l.debit > 0)
    credit_line = next(l for l in lines if l.credit > 0)
    assert debit_line.account_id == gw_accounts["clearing"].pk  # DR Clearing
    assert credit_line.account_id == gw_accounts["bank"].pk      # CR Bank (cash out)
    txn.refresh_from_db()
    assert txn.status == GatewayTransaction.Status.SUCCESS
    assert txn.settled_at is not None


@pytest.mark.django_db(transaction=True)
def test_settlement_failure_auto_reverses_to_payable(gw_accounts, gw_setting, draft_payment):
    from accounting.services import gateway_disbursement
    from superadmin.gateway_models import GatewayService, GatewayTransaction
    fake, _ = _mock_disburse()
    with patch.object(gateway_disbursement, "disburse", fake):
        _, clearing_journal = gateway_disbursement.dispatch_payment_via_gateway(draft_payment, gw_setting)

    tenant = gw_setting.tenant
    txn = GatewayTransaction.objects.create(
        tenant=tenant, provider=gw_setting.provider,
        direction=GatewayService.DISBURSEMENT, idempotency_key="PAY-GW-1",
        amount=Decimal("1000.00"), status=GatewayTransaction.Status.SENT,
        subject={"model": "Payment", "id": draft_payment.pk},
    )
    reversal = gateway_disbursement.settle_gateway_disbursement(txn, success=False)

    # The reversal is the mirror of the clearing journal: CR AP / DR Clearing,
    # reinstating the payable and clearing the clearing balance.
    rev_lines = list(reversal.lines.all())
    assert sum(l.debit for l in rev_lines) == Decimal("1000.00")
    assert sum(l.credit for l in rev_lines) == Decimal("1000.00")
    ap_credit = next(l for l in rev_lines if l.credit > 0)
    clearing_debit = next(l for l in rev_lines if l.debit > 0)
    assert ap_credit.account_id == gw_accounts["ap"].pk        # CR AP (payable reinstated)
    assert clearing_debit.account_id == gw_accounts["clearing"].pk  # DR Clearing (undone)
    txn.refresh_from_db()
    assert txn.status == GatewayTransaction.Status.REVERSED


@pytest.mark.django_db
def test_refuses_when_gateway_unusable(gw_accounts, gw_setting, draft_payment):
    from accounting.services import gateway_disbursement
    from superadmin.gateway_client import GatewayRefused

    gw_setting.is_active = False
    gw_setting.save(update_fields=["is_active"])
    with pytest.raises(GatewayRefused):
        gateway_disbursement.dispatch_payment_via_gateway(draft_payment, gw_setting)
    draft_payment.refresh_from_db()
    assert draft_payment.status == "Draft"  # nothing posted
