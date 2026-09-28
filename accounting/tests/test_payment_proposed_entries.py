"""Proposed-entries preview for the Payment view.

``PaymentViewSet.proposed_entries`` must show the operator the DR/CR
line items BEFORE cash moves, computed from the linked PV, and those
lines must equal what ``post_payment`` actually books:

  * Invoice PV → DR Accounts Payable (gross) / CR each deduction /
    CR Bank (net) — NO expense line (the invoice already posted it).
  * Advance PV → DR Vendor-Advance recon (gross) / CR Bank (net).

Every preview balances (Σdebit == Σcredit), and once posted the action
returns the real booked journal lines.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

# Reuse the central-payment harness — same reference data + drivers.
from accounting.tests.test_central_payment_processing import (
    _accounts, _make_pv, _add_wht, _provision, _post_payment, _vendor,
)


def _proposed(payment, user, bank_account=None):
    """Drive PaymentViewSet.proposed_entries via a superuser DRF GET.

    ``bank_account`` (optional) is sent as the ?bank_account= override the
    modal uses to re-simulate against the bank the operator has selected.
    """
    from rest_framework.test import APIRequestFactory, force_authenticate
    from accounting.views.payables import PaymentViewSet
    factory = APIRequestFactory()
    params = {'bank_account': bank_account} if bank_account is not None else None
    request = factory.get(
        f'/accounting/payments/{payment.pk}/proposed_entries/', params,
    )
    force_authenticate(request, user=user)
    view = PaymentViewSet.as_view({'get': 'proposed_entries'})
    return view(request, pk=payment.pk)


def _simulate(user, **body):
    """Drive PaymentViewSet.simulate (stateless, form-driven preview)."""
    from rest_framework.test import APIRequestFactory, force_authenticate
    from accounting.views.payables import PaymentViewSet
    factory = APIRequestFactory()
    request = factory.post('/accounting/payments/simulate/', body, format='json')
    force_authenticate(request, user=user)
    return PaymentViewSet.as_view({'post': 'simulate'})(request)


@pytest.mark.django_db
def test_simulate_computes_from_form_without_saving(superuser, bank_account_for_batch):
    """The New Outgoing Payment 'Simulate' button posts raw form values to a
    stateless endpoint that returns the DR/CR the payment WOULD book —
    DR AP / CR deductions / CR the SELECTED bank — creating NO Payment row."""
    from accounting.models.receivables import VendorInvoice, Payment
    vendor = _vendor()
    ap, wht_gl, _ = _accounts()
    inv_no = f'VINV-{uuid.uuid4().hex[:8]}'
    inv = VendorInvoice.objects.create(
        invoice_number=inv_no, vendor=vendor,
        total_amount=Decimal('100000.00'), status='Posted',
    )
    pv = _make_pv(invoice_number=inv_no, gross=Decimal('100000.00'), vendor=vendor)
    _add_wht(pv, wht_gl, '10000.00')          # net = 90,000

    before = Payment.objects.count()
    resp = _simulate(
        superuser, payment_voucher=pv.id, vendor=vendor.id,
        bank_account=bank_account_for_batch.id, amount='90000.00', invoice=inv.id,
    )
    assert resp.status_code == 200, getattr(resp, 'data', resp)
    assert Payment.objects.count() == before          # nothing was saved
    data = resp.data
    assert data['posted'] is False and data['balanced'] is True
    by = {e['account_code']: e for e in data['entries']}
    assert Decimal(by[ap.code]['debit']) == Decimal('100000.00')                       # DR AP gross
    assert Decimal(by[wht_gl.code]['credit']) == Decimal('10000.00')                   # CR WHT
    assert Decimal(by[bank_account_for_batch.gl_account.code]['credit']) == Decimal('90000.00')  # CR selected bank net


@pytest.mark.django_db
class TestProposedEntriesDraft:

    def test_invoice_pv_preview_dr_ap_cr_deduction_cr_bank(
        self, superuser, bank_account_for_batch,
    ):
        from accounting.models.receivables import VendorInvoice
        vendor = _vendor()
        ap, wht_gl, _ = _accounts()
        inv_no = f'VINV-{uuid.uuid4().hex[:8]}'
        VendorInvoice.objects.create(
            invoice_number=inv_no, vendor=vendor,
            total_amount=Decimal('100000.00'), status='Posted',
        )
        pv = _make_pv(invoice_number=inv_no, gross=Decimal('100000.00'), vendor=vendor)
        _add_wht(pv, wht_gl, '10000.00')          # net = 90,000
        payment = _provision(pv)
        payment.bank_account = bank_account_for_batch
        payment.save()

        resp = _proposed(payment, superuser)
        assert resp.status_code == 200, getattr(resp, 'data', resp)
        data = resp.data
        assert data['posted'] is False
        assert data['balanced'] is True
        assert Decimal(data['total_debit']) == Decimal('100000.00')
        assert Decimal(data['total_credit']) == Decimal('100000.00')

        by_code = {e['account_code']: e for e in data['entries']}
        # DR Accounts Payable at GROSS — no expenditure line.
        assert Decimal(by_code[ap.code]['debit']) == Decimal('100000.00')
        assert Decimal(by_code[ap.code]['credit']) == Decimal('0.00')
        # CR WHT deduction.
        assert Decimal(by_code[wht_gl.code]['credit']) == Decimal('10000.00')
        # CR Bank at NET.
        bank_code = bank_account_for_batch.gl_account.code
        assert Decimal(by_code[bank_code]['credit']) == Decimal('90000.00')
        # No line names an Expense/Expenditure account.
        assert all('Expenditure' not in e['memo'] for e in data['entries'])

    def test_preview_bank_leg_follows_selected_bank_override(
        self, superuser, cash_account, bank_account_for_batch,
    ):
        """The net credit leg follows the SELECTED bank (?bank_account=), not
        the payment's stored bank — so the modal re-simulates when the operator
        changes the Bank Account dropdown, instead of defaulting to one GL."""
        from accounting.models import Account, BankAccount
        from accounting.models.receivables import VendorInvoice
        # A second bank account with a DISTINCT GL.
        alt_gl, _ = Account.objects.get_or_create(
            code='10105000',
            defaults={'name': 'Cash in Bank - Alt', 'account_type': 'Asset', 'is_active': True},
        )
        alt_bank = BankAccount.objects.create(
            name='Alt Treasury', account_number='0100070099', account_type='Bank',
            gl_account=alt_gl, bank_name='Alt Bank', is_active=True, currency=None,
        )
        vendor = _vendor()
        ap, wht_gl, _ = _accounts()
        inv_no = f'VINV-{uuid.uuid4().hex[:8]}'
        VendorInvoice.objects.create(
            invoice_number=inv_no, vendor=vendor,
            total_amount=Decimal('100000.00'), status='Posted',
        )
        pv = _make_pv(invoice_number=inv_no, gross=Decimal('100000.00'), vendor=vendor)
        _add_wht(pv, wht_gl, '10000.00')          # net = 90,000
        payment = _provision(pv)
        payment.bank_account = bank_account_for_batch   # SAVED bank = the default
        payment.save()

        # No override → credits the SAVED bank's GL.
        base = {e['account_code']: e for e in _proposed(payment, superuser).data['entries']}
        assert Decimal(base[bank_account_for_batch.gl_account.code]['credit']) == Decimal('90000.00')

        # Override → credits the SELECTED (alt) bank's GL, not the saved one.
        over = {e['account_code']: e for e in _proposed(payment, superuser, bank_account=alt_bank.id).data['entries']}
        assert Decimal(over[alt_gl.code]['credit']) == Decimal('90000.00')       # alt bank GL
        assert bank_account_for_batch.gl_account.code not in over                # NOT the saved bank

    def test_advance_pv_preview_dr_recon_cr_bank(
        self, superuser, bank_account_for_batch,
    ):
        vendor = _vendor()
        _, _, recon = _accounts()
        pv = _make_pv(payment_type='ADVANCE', special_gl='A', vendor=vendor,
                      gross=Decimal('50000.00'))
        payment = _provision(pv)
        payment.bank_account = bank_account_for_batch
        payment.save()

        resp = _proposed(payment, superuser)
        assert resp.status_code == 200, getattr(resp, 'data', resp)
        data = resp.data
        assert data['balanced'] is True
        by_code = {e['account_code']: e for e in data['entries']}
        # DR Vendor-Advance recon at gross (no deductions → net == gross).
        assert Decimal(by_code[recon.code]['debit']) == Decimal('50000.00')
        bank_code = bank_account_for_batch.gl_account.code
        assert Decimal(by_code[bank_code]['credit']) == Decimal('50000.00')


@pytest.mark.django_db(transaction=True)
def test_preview_credits_clearing_when_gateway_active(
    bank_account_for_batch, open_fiscal_period,
):
    """When the payment is gateway-eligible AND the tenant has an active usable
    e-payment gateway, the net credit leg is Gateway Settlement Clearing, not
    Bank — the preview shows exactly what post_payment will book (cash parked,
    not gone). Uses the SAME active_disbursement_setting gate as the post."""
    from django.db import connection
    from accounting.models import Account
    from accounting.models.receivables import VendorInvoice
    from accounting.services.payment_preview import compute_payment_entries
    from tenants.models import Client
    from superadmin.gateway_models import PaymentGatewayProvider, TenantGatewaySetting

    # An active, usable Remita gateway for the pytest tenant (public/shared).
    prev = getattr(connection, "schema_name", "public")
    connection.set_schema_to_public()
    try:
        tenant, _ = Client.objects.get_or_create(
            schema_name="pytest_schema", defaults={"name": "PyTest Tenant"},
        )
        prov = PaymentGatewayProvider(
            key=PaymentGatewayProvider.Key.REMITA, display_name="Remita",
            base_url="https://sandbox.remita.test", is_enabled=True,
            supports_disbursement=True, merchant_id="M1",
            api_key_encrypted="gwv1:x", secret_key_encrypted="gwv1:x",
        )
        prov.save()
        TenantGatewaySetting.objects.create(tenant=tenant, provider=prov, is_active=True)
    finally:
        connection.set_schema(prev)

    # A gateway-eligible invoice payment: vendor WITH bank details.
    vendor = _vendor()
    vendor.bank_account_number = "0123456789"
    vendor.save(update_fields=["bank_account_number"])
    ap, wht_gl, _ = _accounts()
    Account.objects.get_or_create(
        code="41090001",
        defaults={"name": "Gateway Settlement Clearing",
                  "account_type": "Liability", "is_active": True},
    )
    inv_no = f"VINV-{uuid.uuid4().hex[:8]}"
    VendorInvoice.objects.create(
        invoice_number=inv_no, vendor=vendor,
        total_amount=Decimal("100000.00"), status="Posted",
    )
    pv = _make_pv(invoice_number=inv_no, gross=Decimal("100000.00"), vendor=vendor)
    _add_wht(pv, wht_gl, "10000.00")          # net = 90,000
    payment = _provision(pv)
    payment.bank_account = bank_account_for_batch
    payment.save()

    # Pin the real Client (TenantMainMiddleware does this in production) so
    # active_disbursement_setting resolves the gateway.
    connection.tenant = tenant
    try:
        lines = compute_payment_entries(payment)
    finally:
        connection.tenant = None

    by_code = {l["account_code"]: l for l in lines}
    assert Decimal(by_code["41090001"]["credit"]) == Decimal("90000.00")   # CR clearing (net)
    assert Decimal(by_code[ap.code]["debit"]) == Decimal("100000.00")      # DR AP gross
    assert bank_account_for_batch.gl_account.code not in by_code           # Bank NOT credited


@pytest.mark.django_db(transaction=True)
class TestProposedEntriesMatchesPosted:

    def test_posted_preview_returns_real_journal_lines(
        self, superuser, bank_account_for_batch, open_fiscal_period,
    ):
        from accounting.models.receivables import VendorInvoice
        vendor = _vendor()
        ap, wht_gl, _ = _accounts()
        inv_no = f'VINV-{uuid.uuid4().hex[:8]}'
        VendorInvoice.objects.create(
            invoice_number=inv_no, vendor=vendor,
            total_amount=Decimal('100000.00'), status='Posted',
        )
        pv = _make_pv(invoice_number=inv_no, gross=Decimal('100000.00'), vendor=vendor)
        _add_wht(pv, wht_gl, '10000.00')
        payment = _provision(pv)
        payment.bank_account = bank_account_for_batch
        payment.save()

        # Preview BEFORE posting.
        pre = _proposed(payment, superuser).data
        assert pre['posted'] is False

        # Post it.
        posted = _post_payment(payment, superuser)
        assert posted.status_code == 200, getattr(posted, 'data', posted)

        # Preview AFTER posting → real journal lines, same balanced totals.
        post = _proposed(payment, superuser).data
        assert post['posted'] is True
        assert post['balanced'] is True
        assert Decimal(post['total_debit']) == Decimal(pre['total_debit'])
        assert Decimal(post['total_credit']) == Decimal(pre['total_credit'])
        assert Decimal(post['total_debit']) == Decimal('100000.00')
