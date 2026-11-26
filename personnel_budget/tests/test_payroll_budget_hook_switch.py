"""The payroll budget gate belongs to the optional personnel_budget module: with the module off, payroll posts as before."""
from unittest import mock

from accounting.signals.events import payroll_pre_post
from personnel_budget import receivers


def _tenant():
    return mock.Mock(pk=7, schema_name="some_state")


def _send():
    payroll_pre_post.send(sender=object, payroll_run=mock.Mock(), total_gross=1000)


def test_module_off_skips_the_gate_entirely():
    with mock.patch.object(receivers, "_personnel_budget_enabled", return_value=False),          mock.patch.object(receivers, "assert_payroll_budget_ok") as gate:
        _send()
    gate.assert_not_called()


def test_module_on_runs_the_gate():
    with mock.patch.object(receivers, "_personnel_budget_enabled", return_value=True),          mock.patch.object(receivers, "assert_payroll_budget_ok") as gate:
        _send()
    gate.assert_called_once()


def test_switch_reads_the_tenants_module_state():
    with mock.patch.object(receivers, "connection", mock.Mock(tenant=_tenant())),          mock.patch.object(receivers, "_is_module_enabled", return_value=False) as enabled:
        assert receivers._personnel_budget_enabled() is False
    enabled.assert_called_once_with("personnel_budget", mock.ANY)


def test_public_schema_is_never_gated():
    public = mock.Mock(pk=1, schema_name="public")
    with mock.patch.object(receivers, "connection", mock.Mock(tenant=public)):
        assert receivers._personnel_budget_enabled() is False
