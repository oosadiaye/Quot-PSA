"""Accounting announces a posted revenue collection. A listener that fails must never undo the posted journal."""
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from accounting.services import revenue_collection_posting as posting
from accounting.signals.events import revenue_collected


def _collection():
    return SimpleNamespace(receipt_number="R-1", payer_tin="T-1", amount=Decimal("10"))


def test_announce_sends_the_collection_and_its_journal():
    heard = mock.Mock(return_value=None)
    revenue_collected.connect(heard, weak=False, dispatch_uid="test.revenue.heard")
    try:
        collection, journal = _collection(), object()
        posting.announce_revenue_collected(collection, journal)
    finally:
        revenue_collected.disconnect(dispatch_uid="test.revenue.heard")
    assert heard.call_args.kwargs["collection"] is collection
    assert heard.call_args.kwargs["journal"] is journal


def test_a_failing_listener_does_not_stop_the_others_or_raise():
    def broken(sender, **kwargs):
        raise RuntimeError("listener crashed")

    ok = mock.Mock(return_value=None)
    revenue_collected.connect(broken, weak=False, dispatch_uid="test.revenue.broken")
    revenue_collected.connect(ok, weak=False, dispatch_uid="test.revenue.ok")
    try:
        with mock.patch.object(posting, "logger") as log:
            posting.announce_revenue_collected(_collection(), object())     # must not raise
    finally:
        revenue_collected.disconnect(dispatch_uid="test.revenue.broken")
        revenue_collected.disconnect(dispatch_uid="test.revenue.ok")
    ok.assert_called_once()
    assert log.exception.called          # the failure is logged, not swallowed silently
