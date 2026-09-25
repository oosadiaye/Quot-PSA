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

    ``bank_account`` (id) simulates the operator's current, possibly-unsaved
    bank-account selection.
    """
    from rest_framework.test import APIRequestFactory, force_authenticate
    from accounting.views.payables import PaymentViewSet
    factory = APIRequestFactory()
    params = {'bank_account': bank_account} if bank_account else {}
    request = factory.get(
        f'/accounting/payments/{payment.pk}/proposed_entries/', params,
    )
    force_authenticate(request, user=user)
    view = PaymentViewSet.as_view({'get': 'proposed_entries'})
    return view(request, pk=payment.pk)


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

    def test_override_bank_account_resolves_cash_gl(
        self, superuser, bank_account_for_batch,
    ):
        """A ``?bank_account=`` override resolves the cash GL from THAT account —
        so the operator can simulate the bank account they're about to pick,
        before the draft is saved."""
        vendor = _vendor()
        pv = _make_pv(payment_type='ADVANCE', special_gl='A', vendor=vendor,
                      gross=Decimal('50000.00'))
        payment = _provision(pv)
        payment.bank_account = None          # nothing saved yet
        payment.save()

        resp = _proposed(payment, superuser, bank_account=bank_account_for_batch.id)
        assert resp.status_code == 200, getattr(resp, 'data', resp)
        data = resp.data
        assert data['needs_bank_account'] is False
        by_code = {e['account_code']: e for e in data['entries']}
        assert bank_account_for_batch.gl_account.code in by_code
        assert Decimal(by_code[bank_account_for_batch.gl_account.code]['credit']) == Decimal('50000.00')

    def test_no_bank_account_shows_placeholder(self, superuser):
        """No saved bank account and no override → placeholder cash line (no
        made-up GL), and ``needs_bank_account`` is true."""
        vendor = _vendor()
        pv = _make_pv(payment_type='ADVANCE', special_gl='A', vendor=vendor,
                      gross=Decimal('50000.00'))
        payment = _provision(pv)
        payment.bank_account = None
        payment.save()

        data = _proposed(payment, superuser).data
        assert data['needs_bank_account'] is True
        # The cash line is a placeholder — blank code, net credit, no 31010101.
        cash = [e for e in data['entries'] if Decimal(e['credit']) == Decimal('50000.00')]
        assert cash and cash[0]['account_code'] == ''
        assert all(e['account_code'] != '31010101' for e in data['entries'])


@pytest.mark.django_db(transaction=True)
class TestProposedEntriesMatchesPosted:

    def test_post_without_bank_account_is_rejected(
        self, superuser, open_fiscal_period,
    ):
        """Posting an invoice-PV payment requires a bank account (with a GL) —
        the main branch no longer falls back to a default cash GL."""
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
        payment.bank_account = None
        payment.save()

        resp = _post_payment(payment, superuser)
        assert resp.status_code == 400, getattr(resp, 'data', resp)
        assert 'bank account' in str(resp.data).lower()

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
