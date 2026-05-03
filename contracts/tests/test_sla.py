"""
Pure-Python tests for contracts/sla.py — no DB, no Celery.

Verifies:
  * default SLA values are sensible (48-96 h range)
  * ``CONTRACTS_SLA`` settings overrides merge correctly
  * ``sla_delta`` returns ``timedelta`` of the right size
  * unknown keys fall back to 48 h rather than raising
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings

from contracts.sla import reminder_lead, sla_delta, sla_hours


class TestSLAHours:

    def test_known_keys_match_defaults(self):
        assert sla_hours("variation_submitted")     == 48
        assert sla_hours("variation_reviewed")      == 72
        assert sla_hours("ipc_submitted")           == 48
        assert sla_hours("ipc_certifier_reviewed")  == 48
        assert sla_hours("ipc_approved")            == 72
        assert sla_hours("ipc_voucher_raised")      == 96
        assert sla_hours("reminder_lead_hours")     == 24

    def test_unknown_key_returns_fallback(self):
        assert sla_hours("this_key_does_not_exist") == 48

    @override_settings(CONTRACTS_SLA={"ipc_submitted": 12})
    def test_settings_override(self):
        assert sla_hours("ipc_submitted") == 12
        # Unrelated keys still default
        assert sla_hours("ipc_approved") == 72

    @override_settings(CONTRACTS_SLA={"variation_submitted": 4})
    def test_sla_delta_shape(self):
        assert sla_delta("variation_submitted") == timedelta(hours=4)

    def test_reminder_lead(self):
        assert reminder_lead() == timedelta(hours=24)
