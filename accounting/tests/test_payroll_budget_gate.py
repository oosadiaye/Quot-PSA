"""Payroll budget gate (G3) regression tests — review finding 2.

Closes the finding that ``PayrollPostingService.post_payroll_run`` posted
salary straight to the GL with no appropriation lookup and no budget check.
Verifies the enforcement wired into ``payroll_posting`` routes through the
central ``check_policy`` engine, so a PayrollRun is held to the same
commitment-control standards as a journal, PO, or payment voucher.

The three check-level branches (NONE / WARNING / STRICT) are already covered
centrally in ``test_budget_check_rules.py``; here we verify the *payroll*
integration point composes correctly against that engine.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from budget.services import BudgetExceededError
from personnel_budget.services import assert_payroll_budget_ok

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _fake_account(code='21000010', name='Salary Expense'):
    return SimpleNamespace(code=code, name=name)


def _fake_appropriation(approved=Decimal('1000000'), expended=Decimal('0'),
                        committed=Decimal('0')):
    return SimpleNamespace(
        amount_approved=approved,
        cached_total_expended=expended,
        cached_total_committed=committed,
    )


def _fake_run(total_gross='1000', account=None, binding=None):
    return SimpleNamespace(
        pk=1,
        run_number='PR-TEST-1',
        total_gross=Decimal(total_gross),
        payroll_expense_account_id=1 if account else None,
        payroll_expense_account=account,
        budget_binding=binding,
    )


def _fake_binding(appropriation, level='STRICT'):
    return SimpleNamespace(appropriation_line=appropriation, check_level=level)


# ---------------------------------------------------------------------------
# assert_payroll_budget_ok() — the gate post_payroll_run invokes
# ---------------------------------------------------------------------------

def test_gate_blocks_when_strict_and_no_binding(rules):
    """A STRICT salary rule without any binding/appropriation must block."""
    run = _fake_run(account=_fake_account())
    with pytest.raises(BudgetExceededError):
        assert_payroll_budget_ok(run, requested_amount=Decimal('1000'))


def test_gate_passes_when_bound_within_balance(rules):
    """Bound to an appropriation whose remaining balance covers payroll."""
    run = _fake_run(
        account=_fake_account(),
        binding=_fake_binding(_fake_appropriation(approved=Decimal('10000'))),
    )
    result = assert_payroll_budget_ok(run, requested_amount=Decimal('1000'))
    assert not result.blocked
    assert result.level == 'STRICT'


def test_gate_blocks_when_bound_balance_exhausted(rules):
    """Binding exists but the appropriation is exhausted."""
    appro = _fake_appropriation(
        approved=Decimal('500'),
        expended=Decimal('500'),
        committed=Decimal('0'),
    )
    run = _fake_run(account=_fake_account(), binding=_fake_binding(appro))
    with pytest.raises(BudgetExceededError):
        assert_payroll_budget_ok(run, requested_amount=Decimal('1000'))


def test_gate_passes_under_none_rule(rules):
    """A non-controlled account is never blocked, binding or not."""
    run = _fake_run(account=_fake_account(code='30000100'))
    result = assert_payroll_budget_ok(run, requested_amount=Decimal('1000'))
    assert not result.blocked
    assert result.level == 'NONE'


def test_gate_not_blocked_accounting_salary_falls_to_default(rules, settings):
    """No rule matches a non-personnel code → settings default governs."""
    settings.BUDGET_DEFAULT_CONTROL_LEVEL = 'NONE'
    run = _fake_run(account=_fake_account(code='89999999'))
    result = assert_payroll_budget_ok(run, requested_amount=Decimal('1000'))
    assert not result.blocked


# ---------------------------------------------------------------------------
# _enforce_payroll_budget() — the integration in post_payroll_run
# ---------------------------------------------------------------------------

def test_enforce_blocks_gate_from_posting_service(rules, monkeypatch):
    """post_payroll_run must refuse an unbound run on a STRICT salary account (once personnel_budget is switched on)."""
    import accounting.services.payroll_posting as pp_module
    monkeypatch.setattr(pp_module, '_personnel_budget_enabled', lambda: True)
    run = _fake_run(account=_fake_account())
    with pytest.raises(BudgetExceededError):
        pp_module._enforce_payroll_budget(run, Decimal('1000'))


def test_enforce_does_nothing_while_personnel_budget_is_switched_off(rules, monkeypatch):
    """The module is off by default: payroll posts exactly as it did before the module existed."""
    import accounting.services.payroll_posting as pp_module
    monkeypatch.setattr(pp_module, '_personnel_budget_enabled', lambda: False)
    pp_module._enforce_payroll_budget(_fake_run(account=_fake_account()), Decimal('1000'))     # must not raise


def test_enforce_fails_open_when_module_unavailable(rules, monkeypatch):
    """If personnel_budget cannot import, posting must NOT be blocked."""
    import accounting.services.payroll_posting as pp_module
    import builtins
    monkeypatch.setattr(pp_module, '_personnel_budget_enabled', lambda: True)   # switched on, but the import fails

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == 'personnel_budget.services':
            raise ImportError('personnel_budget not installed')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', _fake_import)
    pp_module._enforce_payroll_budget(_fake_run(), Decimal('1000'))
