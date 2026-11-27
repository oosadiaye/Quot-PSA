"""revenue_admin reacts to accounting's revenue_collected event, but only while its module is switched on."""
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from accounting.signals.events import revenue_collected
from revenue_admin import receivers


def _collection():
    return SimpleNamespace(receipt_number="R-9", payer_tin="T-9", revenue_head=object(), amount=Decimal("55"))


def _send():
    revenue_collected.send(sender=object, collection=_collection(), journal=object())


def test_module_off_applies_nothing():
    with mock.patch.object(receivers, "_revenue_admin_enabled", return_value=False), \
         mock.patch.object(receivers, "apply_collection") as apply:
        _send()
    apply.assert_not_called()


def test_module_on_applies_the_collection():
    collection = _collection()
    with mock.patch.object(receivers, "_revenue_admin_enabled", return_value=True), \
         mock.patch.object(receivers, "apply_collection") as apply:
        revenue_collected.send(sender=object, collection=collection, journal=object())
    apply.assert_called_once_with(
        receipt_number="R-9", payer_tin="T-9", revenue_head=collection.revenue_head, amount=Decimal("55"))


def test_switch_reads_the_tenants_module_state_and_never_gates_public():
    tenant = mock.Mock(pk=7, schema_name="some_state")
    with mock.patch.object(receivers, "connection", mock.Mock(tenant=tenant)), \
         mock.patch.object(receivers, "_is_module_enabled", return_value=True) as enabled:
        assert receivers._revenue_admin_enabled() is True
    enabled.assert_called_once_with("revenue_admin", tenant)
    public = mock.Mock(pk=1, schema_name="public")
    with mock.patch.object(receivers, "connection", mock.Mock(tenant=public)):
        assert receivers._revenue_admin_enabled() is False
