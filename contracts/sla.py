"""
Service-level-agreement (SLA) configuration for the contracts workflow.

All values are in **hours**. They can be overridden in Django settings
under the ``CONTRACTS_SLA`` dict::

    CONTRACTS_SLA = {
        "variation_submitted":    48,   # hours to review
        "variation_reviewed":     72,   # hours to final approval
        "ipc_submitted":          48,   # hours until certifier acts
        "ipc_certifier_reviewed": 48,   # hours until approver acts
        "ipc_approved":           72,   # hours until treasury raises PV
        "ipc_voucher_raised":     96,   # hours until cash is disbursed
        "reminder_lead_hours":    24,   # send reminder N hours before SLA
    }

Rationale for the defaults: Nigerian BPP procurement guidelines allow
approving officers up to 72 hours for tier-LOCAL variation approval and
up to 96 hours for treasury-side disbursement. IPC workflow uses a
shorter 48-hour clock at each tier so contractors aren't held up.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Mapping

from django.conf import settings


# ── Default SLA table (hours) ──────────────────────────────────────────

_DEFAULT_SLA: Mapping[str, int] = {
    # Variation workflow
    "variation_submitted":     48,
    "variation_reviewed":      72,
    # IPC workflow
    "ipc_submitted":           48,
    "ipc_certifier_reviewed":  48,
    "ipc_approved":            72,
    "ipc_voucher_raised":      96,
    # Reminder cadence
    "reminder_lead_hours":     24,
}


def _sla_table() -> Mapping[str, int]:
    """Merge settings overrides on top of the defaults."""
    overrides: Mapping[str, int] = getattr(settings, "CONTRACTS_SLA", {}) or {}
    merged = dict(_DEFAULT_SLA)
    merged.update(overrides)
    return merged


def sla_hours(key: str) -> int:
    """Hours allowed at a given workflow step.

    Unknown keys fall back to 48 h rather than raising — operational
    safety: we never want a scheduler to crash because a new status was
    added and the SLA table wasn't updated in lockstep.
    """
    return int(_sla_table().get(key, 48))


def sla_delta(key: str) -> timedelta:
    return timedelta(hours=sla_hours(key))


def reminder_lead() -> timedelta:
    return timedelta(hours=sla_hours("reminder_lead_hours"))
