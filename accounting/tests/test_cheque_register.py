"""Cheque Register — create ONE cheque covering several posted payments.

``CheckViewSet.create_from_payments`` links the selected POSTED payments to a
new ``Check`` (Payment.cheque). No GL posting — the payments already posted;
this records the physical cheque against them. Guards: payments must be Posted
and not already on a cheque, and the cheque number must be unique.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


def _posted_payment(amount, vendor=None):
    from accounting.models.receivables import Payment
    return Payment.objects.create(
        payment_number=f'PAY-{uuid.uuid4().hex[:8]}',
        payment_method='Wire', total_amount=Decimal(str(amount)),
        status='Posted', vendor=vendor,
    )


def _create_from_payments(user, **body):
    from rest_framework.test import APIRequestFactory, force_authenticate
    from accounting.views.banking import CheckViewSet
    factory = APIRequestFactory()
    req = factory.post('/accounting/checks/create-from-payments/', body, format='json')
    force_authenticate(req, user=user)
    return CheckViewSet.as_view({'post': 'create_from_payments'})(req)


@pytest.mark.django_db
class TestChequeRegister:

    def test_one_cheque_covers_multiple_payments(self, superuser):
        from accounting.models.receivables import Check
        p1 = _posted_payment('1000.00')
        p2 = _posted_payment('2500.00')
        resp = _create_from_payments(
            superuser, check_number='CHQ-001', date_issued='2026-03-01',
            payment_ids=[p1.id, p2.id],
        )
        assert resp.status_code == 201, getattr(resp, 'data', resp)
        chk = Check.objects.get(check_number='CHQ-001')
        assert chk.amount == Decimal('3500.00')      # summed across the lines
        assert chk.payments.count() == 2
        p1.refresh_from_db(); p2.refresh_from_db()
        assert p1.cheque_id == chk.id and p2.cheque_id == chk.id

    def test_rejects_non_posted_payment(self, superuser):
        from accounting.models.receivables import Payment
        p = Payment.objects.create(
            payment_number=f'PAY-{uuid.uuid4().hex[:8]}', payment_method='Wire',
            total_amount=Decimal('500'), status='Draft',
        )
        resp = _create_from_payments(
            superuser, check_number='CHQ-002', date_issued='2026-03-01', payment_ids=[p.id],
        )
        assert resp.status_code == 400
        assert 'not posted' in str(resp.data).lower()

    def test_rejects_payment_already_on_cheque(self, superuser):
        p = _posted_payment('1000.00')
        r1 = _create_from_payments(
            superuser, check_number='CHQ-003', date_issued='2026-03-01', payment_ids=[p.id],
        )
        assert r1.status_code == 201
        r2 = _create_from_payments(
            superuser, check_number='CHQ-004', date_issued='2026-03-01', payment_ids=[p.id],
        )
        assert r2.status_code == 400
        assert 'already on a cheque' in str(r2.data).lower()

    def test_rejects_duplicate_cheque_number(self, superuser):
        p1 = _posted_payment('1000.00')
        p2 = _posted_payment('1000.00')
        r1 = _create_from_payments(
            superuser, check_number='CHQ-DUP', date_issued='2026-03-01', payment_ids=[p1.id],
        )
        assert r1.status_code == 201
        r2 = _create_from_payments(
            superuser, check_number='CHQ-DUP', date_issued='2026-03-01', payment_ids=[p2.id],
        )
        assert r2.status_code == 400
        assert 'already exists' in str(r2.data).lower()
