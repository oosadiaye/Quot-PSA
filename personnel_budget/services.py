"""
personnel_budget — payroll-to-appropriation binding services (G3).

Closes the review finding that the most valuable control in the FUTURE_MODULES
set was modelled but not wired: ``PayrollPostingService.post_payroll_run`` posted
salary expense straight to the GL with no appropriation lookup and no
budget-check.

This module provides the two operations the ``PayrollBudgetBinding`` model
documented but nothing implemented:

* ``bind_payroll_run``     — create/refresh the PayrollRun → Appropriation
  binding, snapshotting ``remaining_at_binding`` and the governing
  ``check_level``.
* ``assert_payroll_budget_ok`` — the enforcement gate. Runs the same central
  ``accounting.services.budget_check_rules.check_policy`` engine every other
  posting path uses, so a PayrollRun is held to the same electrified
  commitment-control standards as a journal, PO, or payment voucher. Raises
  ``budget.services.BudgetExceededError`` when a STRICT rule is crossed (no
  binding, or bound appropriation exhausted).

The module is deliberately thin and stays decoupled from ``accounting`` /
``hrm``: it imports accounting's check engine lazily and is invoked from
``payroll_posting`` via a safe lazy import, so enabling/disabling the
personnel_budget module never breaks the core payroll flow at import time.
"""
from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def _resolve_salary_account(run):
    """Resolve the GL account salary expense is booked against for a run.

    Mirrors payroll_posting's override → DEFAULT_GL_ACCOUNTS fallback so the
    enforcement gate examines the SAME account that will actually receive the
    salary debit.
    """
    from accounting.services.base_posting import get_gl_account

    if getattr(run, 'payroll_expense_account_id', None) and run.payroll_expense_account:
        return run.payroll_expense_account
    return get_gl_account('SALARY_EXPENSE', 'Expense', 'Salary')


def _run_total(run, requested_amount=None):
    if requested_amount is not None:
        return Decimal(str(requested_amount))
    return Decimal(str(getattr(run, 'total_gross', 0) or 0))


def _available(binding):
    """Remaining balance of a bound appropriation."""
    from accounting.services.budget_check_rules import _appropriation_available
    return _appropriation_available(binding.appropriation_line)


def _governing_level(run):
    from accounting.services.budget_check_rules import resolve_rule_for_account
    account = _resolve_salary_account(run)
    rule = resolve_rule_for_account(account.code) if account else None
    if rule:
        return rule.check_level, rule.description
    from django.conf import settings
    return getattr(settings, 'BUDGET_DEFAULT_CONTROL_LEVEL', 'NONE'), ''


def bind_payroll_run(run, appropriation, *, bound_by=None, requested_amount=None):
    """Create or refresh a PayrollRun → Appropriation binding.

    Snapshots ``remaining_at_binding`` and ``check_level`` so the binding row
    is an immutable record of the control state at approval time (the model's
    intent — ``check_level`` is "copied from the governing BudgetCheckRule at
    binding time").

    Returns the created/updated ``PayrollBudgetBinding``.
    """
    from .models import PayrollBudgetBinding

    amount = _run_total(run, requested_amount)
    level, _desc = _governing_level(run)

    binding, _created = PayrollBudgetBinding.objects.update_or_create(
        payroll_run=run,
        defaults={
            'appropriation_line': appropriation,
            'bound_amount': amount,
            'remaining_at_binding': _appropriation_available_safe(appropriation),
            'check_level': level,
            'bound_by': bound_by,
        },
    )
    logger.info(
        'PayrollBudgetBinding %s for run %s (amount=%s level=%s)',
        'created' if _created else 'updated',
        run.pk, amount, level,
    )
    return binding


def _appropriation_available_safe(appropriation):
    from accounting.services.budget_check_rules import _appropriation_available
    return _appropriation_available(appropriation)


def assert_payroll_budget_ok(run, requested_amount=None):
    """Enforce the G3 payroll budget gate before a run posts to the GL.

    Uses the same central ``check_policy`` engine as journals/POs/vouchers:

    * If a ``PayrollBudgetBinding`` exists, evaluate the bound appropriation's
      remaining balance against the payroll amount under the governing policy.
    * If no binding exists, evaluate with ``appropriation=None`` — a STRICT
      rule blocks (the run cannot silently post unbudgeted), WARNING/NONE allow
      but flag.

    Returns ``accounting.services.budget_check_rules.CheckResult``. Raises
    ``budget.services.BudgetExceededError`` when ``result.blocked`` is True.
    """
    from accounting.services.budget_check_rules import check_policy

    account = _resolve_salary_account(run)
    amount = _run_total(run, requested_amount)
    account_code = account.code if account else ''

    binding = getattr(run, 'budget_binding', None)
    appropriation = binding.appropriation_line if binding else None

    result = check_policy(
        account_code=account_code,
        appropriation=appropriation,
        requested_amount=amount,
        transaction_label=f'payroll run {getattr(run, "run_number", run.pk)}',
        account_name=getattr(account, 'name', ''),
    )

    if result.blocked:
        from budget.services import BudgetExceededError
        raise BudgetExceededError(result.reason)

    return result


def assert_payroll_bound(run, requested_amount=None):
    """Strict gate: a PayrollRun must carry a binding covering the amount.

    This is the personnel_budget module's own Definition-of-Done check — a run
    may not post unless it has an approved binding whose remaining balance
    covers the payroll amount. Used when the module is active so operators
    cannot bypass the control by simply refusing to create a binding.
    """
    from budget.services import BudgetExceededError

    binding = getattr(run, 'budget_binding', None)
    if binding is None:
        raise BudgetExceededError(
            f'Payroll run {getattr(run, "run_number", run.pk)} has no '
            'PayrollBudgetBinding. Bind it to an approved appropriation '
            'before posting (personnel_budget module).'
        )
    amount = _run_total(run, requested_amount)
    level = binding.check_level or 'STRICT'
    if level == 'STRICT' and amount > _available(binding):
        raise BudgetExceededError(
            f'Payroll run {getattr(run, "run_number", run.pk)} exceeds the '
            f'bound appropriation remaining balance '
            f'{_available(binding)} (requested {amount}).'
        )
    return binding
