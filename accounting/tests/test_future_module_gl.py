"""GL-integration regression tests for the staff_advances and debt services
(review finding 3).

Historically ``staff_advances.StaffAdvance.journal`` / ``ImprestRetirement.journal``
and the debt coupon paid-warrant path were FKs nothing ever populated — advances
and debt-service payments left the system unrecorded in the GL. These tests pin
the guard behaviour of the new services so the gap cannot silently reopen.

Verification strategy note (same as test_payroll_budget_gate.py): the tenant
schema-migrate harness is slow, and the services touch the DB (JournalHeader /
select_for_update / post_journal), so these are DB-backed and run in CI where
the harness is not a 15-minute bottleneck.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from accounting.services.base_posting import TransactionPostingError

pytestmark = pytest.mark.django_db


def _fake_account(code='10100000', name='Cash'):
    return SimpleNamespace(code=code, name=name)


def _fake_advance(amount='1000', recovered='0', journal=None, reference=None, pk=1):
    return SimpleNamespace(
        pk=pk,
        amount=Decimal(amount),
        recovered_amount=Decimal(recovered),
        journal=journal,
        journal_id=journal.pk if journal else None,
        reference=reference or f'SA-{pk:04d}',
        advance_date=None,
    )


# ---------------------------------------------------------------------------
# StaffAdvanceGLService — disbursement / recovery guards
# ---------------------------------------------------------------------------

def test_disburse_rejects_second_posting(rules, monkeypatch):
    """An advance already carrying a journal pin must refuse to double-post."""
    from staff_advances.services import StaffAdvanceGLService

    already = SimpleNamespace(pk=99)
    advance = _fake_advance(journal=already)
    monkeypatch.setattr(StaffAdvanceGLService, 'resolve_recon_account',
                        lambda: _fake_account())
    with pytest.raises(TransactionPostingError):
        StaffAdvanceGLService.disburse(
            staff_advance=advance, actor=SimpleNamespace(pk=1),
        )


def test_disburse_rejects_nonpositive_amount(rules, monkeypatch):
    from staff_advances.services import StaffAdvanceGLService

    advance = _fake_advance(amount='0')
    monkeypatch.setattr(StaffAdvanceGLService, 'resolve_recon_account',
                        lambda: _fake_account())
    with pytest.raises(TransactionPostingError):
        StaffAdvanceGLService.disburse(
            staff_advance=advance, actor=SimpleNamespace(pk=1),
        )


def test_disburse_rejects_missing_recon(rules, monkeypatch):
    """No staff-advance recon GL configured → clear operator error."""
    from staff_advances.services import StaffAdvanceGLService

    advance = _fake_advance()
    monkeypatch.setattr(StaffAdvanceGLService, 'resolve_recon_account', lambda: None)
    with pytest.raises(TransactionPostingError) as exc:
        StaffAdvanceGLService.disburse(
            staff_advance=advance, actor=SimpleNamespace(pk=1),
        )
    assert 'recon account' in str(exc.value)


def test_recovery_requires_disbursement_pin(rules, monkeypatch):
    """Recovering an advance never disbursed to the GL must fail."""
    from staff_advances.services import StaffAdvanceGLService

    advance = _fake_advance()  # journal_id None
    with pytest.raises(TransactionPostingError):
        StaffAdvanceGLService.record_recovery(
            staff_advance=advance, amount=Decimal('100'),
            actor=SimpleNamespace(pk=1),
        )


def test_recovery_rejects_over_recovery(rules, monkeypatch):
    from staff_advances.services import StaffAdvanceGLService

    advance = _fake_advance(amount='1000', recovered='900', journal=SimpleNamespace(pk=1))
    monkeypatch.setattr(StaffAdvanceGLService, 'resolve_recon_account',
                        lambda: _fake_account())
    with pytest.raises(TransactionPostingError):
        StaffAdvanceGLService.record_recovery(
            staff_advance=advance, amount=Decimal('200'),
            actor=SimpleNamespace(pk=1),
        )


def test_retire_imprest_rejects_second_pin(rules, monkeypatch):
    from staff_advances.services import StaffAdvanceGLService

    retirement = SimpleNamespace(
        pk=5, amount=Decimal('100'), journal_id=7, journal=SimpleNamespace(pk=7),
        imprest=SimpleNamespace(pk=1, reference='IMP-1', retirements=type('q', (), {'count': lambda s: 0})()),
    )
    monkeypatch.setattr(StaffAdvanceGLService, 'resolve_recon_account',
                        lambda: _fake_account())
    with pytest.raises(TransactionPostingError):
        StaffAdvanceGLService.retire_imprest(
            retirement=retirement, actor=SimpleNamespace(pk=1),
        )


# ---------------------------------------------------------------------------
# DebtServiceGLService — pay_coupon guards
# ---------------------------------------------------------------------------

def test_pay_coupon_rejects_already_paid(rules):
    from debt.services import DebtServiceGLService

    coupon = SimpleNamespace(
        pk=1, status='paid', principal_amount=Decimal('100'),
        interest_amount=Decimal('0'), commitment_fee=Decimal('0'),
        schedule=None,
    )
    with pytest.raises(TransactionPostingError):
        DebtServiceGLService.pay_coupon(
            coupon=coupon, actor=SimpleNamespace(pk=1),
        )


def test_pay_coupon_rejects_nonpositive_amount(rules):
    from debt.services import DebtServiceGLService

    coupon = SimpleNamespace(
        pk=1, status='scheduled', principal_amount=Decimal('0'),
        interest_amount=Decimal('0'), commitment_fee=Decimal('0'),
        schedule=None,
    )
    with pytest.raises(TransactionPostingError):
        DebtServiceGLService.pay_coupon(
            coupon=coupon, actor=SimpleNamespace(pk=1),
        )


def test_pay_coupon_rejects_missing_expense_gl(rules, monkeypatch):
    from debt.services import DebtServiceGLService

    coupon = SimpleNamespace(
        pk=1, status='scheduled', principal_amount=Decimal('100'),
        interest_amount=Decimal('0'), commitment_fee=Decimal('0'),
        schedule=SimpleNamespace(instrument=SimpleNamespace(instrument_number='LN-1')),
    )
    monkeypatch.setattr(DebtServiceGLService, 'resolve_expense_account', lambda: None)
    with pytest.raises(TransactionPostingError) as exc:
        DebtServiceGLService.pay_coupon(
            coupon=coupon, actor=SimpleNamespace(pk=1), paid_date='2026-01-01',
        )
    assert 'Debt Service Expense' in str(exc.value)
