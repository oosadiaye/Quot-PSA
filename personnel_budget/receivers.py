"""personnel_budget's reaction to accounting's events (accounting never imports this module)."""
from django.db import connection
from django.dispatch import receiver

from accounting.signals.events import payroll_pre_post
from core.permissions import _is_module_enabled

from .services import assert_payroll_budget_ok


def _personnel_budget_enabled() -> bool:
    """Is the module switched on for this tenant? Off (or no row) means payroll posts exactly as it did before the
    module existed. The public schema is never gated."""
    tenant = getattr(connection, 'tenant', None)
    if tenant is None or getattr(tenant, 'schema_name', 'public') == 'public':
        return False
    return _is_module_enabled('personnel_budget', tenant)


@receiver(payroll_pre_post, dispatch_uid='personnel_budget.payroll_budget_gate')
def enforce_payroll_budget(sender, payroll_run, total_gross, **kwargs):
    """The G3 payroll budget gate: salary posting must not bypass the appropriation/commitment control the rest of the
    ledger honours. Raises ``budget.services.BudgetExceededError`` when the run is blocked."""
    if not _personnel_budget_enabled():
        return
    assert_payroll_budget_ok(payroll_run, requested_amount=total_gross)
