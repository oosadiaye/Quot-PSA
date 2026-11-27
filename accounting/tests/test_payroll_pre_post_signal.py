"""Accounting announces a payroll run before posting it; whoever listens may refuse it. Accounting names no optional module."""
from decimal import Decimal
from unittest import mock

import pytest

from accounting.services import payroll_posting
from accounting.signals.events import payroll_pre_post


def test_announce_sends_the_run_and_the_gross_amount():
    run = mock.Mock()
    heard = mock.Mock()
    payroll_pre_post.connect(heard, weak=False, dispatch_uid="test.payroll.heard")
    try:
        payroll_posting._announce_payroll_posting(run, Decimal("1000"))
    finally:
        payroll_pre_post.disconnect(dispatch_uid="test.payroll.heard")
    assert heard.call_count == 1
    assert heard.call_args.kwargs["payroll_run"] is run
    assert heard.call_args.kwargs["total_gross"] == Decimal("1000")


def test_a_listener_that_raises_stops_the_posting():
    def refuse(sender, **kwargs):
        raise RuntimeError("over budget")

    payroll_pre_post.connect(refuse, weak=False, dispatch_uid="test.payroll.refuse")
    try:
        with pytest.raises(RuntimeError, match="over budget"):
            payroll_posting._announce_payroll_posting(mock.Mock(), Decimal("1"))
    finally:
        payroll_pre_post.disconnect(dispatch_uid="test.payroll.refuse")


def test_posting_module_does_not_import_any_optional_module():
    import inspect
    import re
    imports = re.findall(r"^\s*(?:from|import)\s+personnel_budget", inspect.getsource(payroll_posting), re.M)
    assert imports == []
