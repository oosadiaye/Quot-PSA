"""The payroll budget gate belongs to the optional personnel_budget module: with the module off, payroll posts as before."""
from unittest import mock

from accounting.services import payroll_posting


def _tenant():
    return mock.Mock(pk=7, schema_name="some_state")


def test_module_off_skips_the_gate_entirely():
    with mock.patch.object(payroll_posting, "_personnel_budget_enabled", return_value=False), \
         mock.patch("personnel_budget.services.assert_payroll_budget_ok") as gate:
        payroll_posting._enforce_payroll_budget(mock.Mock(), 1000)
    gate.assert_not_called()


def test_module_on_runs_the_gate():
    with mock.patch.object(payroll_posting, "_personnel_budget_enabled", return_value=True), \
         mock.patch("personnel_budget.services.assert_payroll_budget_ok") as gate:
        payroll_posting._enforce_payroll_budget(mock.Mock(), 1000)
    gate.assert_called_once()


def test_switch_reads_the_tenants_module_state():
    with mock.patch("django.db.connection", mock.Mock(tenant=_tenant())), \
         mock.patch("core.permissions._is_module_enabled", return_value=False) as enabled:
        assert payroll_posting._personnel_budget_enabled() is False
    enabled.assert_called_once_with("personnel_budget", mock.ANY)


def test_public_schema_is_never_gated():
    public = mock.Mock(pk=1, schema_name="public")
    with mock.patch("django.db.connection", mock.Mock(tenant=public)):
        assert payroll_posting._personnel_budget_enabled() is False
