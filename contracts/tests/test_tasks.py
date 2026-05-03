"""
Light-weight tests for contracts/tasks.py.

The task bodies iterate tenants + touch the ORM, so a true end-to-end
test belongs in D7's tenant-schema integration suite. Here we verify
the task *imports* cleanly, exposes the right Celery name, and that
internal helpers (_age_hours, status-map wiring) behave sanely.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from contracts import tasks


class TestTaskRegistration:
    """Celery names must be stable — beat-schedule entries reference
    them as strings, so a rename is a breaking change."""

    def test_escalate_stale_variations_registered(self):
        assert tasks.escalate_stale_variations.name == (
            "contracts.tasks.escalate_stale_variations"
        )

    def test_escalate_stale_ipcs_registered(self):
        assert tasks.escalate_stale_ipcs.name == (
            "contracts.tasks.escalate_stale_ipcs"
        )

    def test_reminders_registered(self):
        assert tasks.send_pending_approval_reminders.name == (
            "contracts.tasks.send_pending_approval_reminders"
        )

    def test_notify_registered(self):
        assert tasks.notify_approval_assigned.name == (
            "contracts.tasks.notify_approval_assigned"
        )

    def test_reconcile_registered(self):
        assert tasks.reconcile_contract_balances.name == (
            "contracts.tasks.reconcile_contract_balances"
        )


class TestStatusMaps:
    """Regression guard: the escalation maps must cover every status that
    can sit waiting for action without moving.  A new status added to
    VariationStatus / IPCStatus that represents pending work MUST be
    reflected here or it will never escalate."""

    def test_variation_map_is_exhaustive_for_pending(self):
        from contracts.models import VariationStatus
        covered = set(tasks._ESCALATABLE_VARIATION_STATUSES.keys())
        # Pending (awaiting-action) variation statuses.
        pending = {VariationStatus.SUBMITTED, VariationStatus.REVIEWED}
        assert pending.issubset(covered)

    def test_ipc_map_is_exhaustive_for_pending(self):
        from contracts.models import IPCStatus
        covered = set(tasks._ESCALATABLE_IPC_STATUSES.keys())
        pending = {
            IPCStatus.SUBMITTED,
            IPCStatus.CERTIFIER_REVIEWED,
            IPCStatus.APPROVED,
            IPCStatus.VOUCHER_RAISED,
        }
        assert pending.issubset(covered)


class TestAgeHelper:

    def test_age_hours_positive(self):
        now = timezone.now()
        ts = now - timedelta(hours=5, minutes=6)
        assert tasks._age_hours(ts, now) == 5.1

    def test_age_hours_zero_when_equal(self):
        now = timezone.now()
        assert tasks._age_hours(now, now) == 0.0
