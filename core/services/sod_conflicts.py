"""
Segregation-of-Duties (SOD) conflict detector.

In public-sector finance, certain combinations of authority in one
person's hands create a material risk of fraud or undetected error.
This service encodes the canonical SOD matrix for the baseline role
set and exposes two operations:

  * ``conflicts_for_roles(codes)`` — given a set of role codes, return
    the list of conflict pairs present.
  * ``matrix()`` — return the full SOD matrix for display.

The rules below are derived from the ICAN public-sector accounting
manual, IPSAS conceptual framework ¶3.32, and the Treasury Single
Account operational directive. They are conservative by design:
`allow=false` means "do not combine in the same user" — an override
requires dual-control documentation.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SODRule:
    role_a: str
    role_b: str
    severity: str   # 'high' | 'medium' | 'low'
    reason: str


# Canonical conflicts. Ordered alphabetically for stability.
_SOD_RULES: tuple[SODRule, ...] = (
    # ─── Same-module maker/checker conflicts (highest severity) ─────
    SODRule(
        role_a='account_officer', role_b='accountant_general',
        severity='high',
        reason='Same user cannot both create journals and post/approve '
               'them — violates IPSAS accrual control and ICAN PS3.1.',
    ),
    SODRule(
        role_a='budget_officer', role_b='budget_manager',
        severity='high',
        reason='Same user cannot prepare appropriations and enact '
               'them — violates legislative vs. administrative '
               'separation under the Fiscal Responsibility Act.',
    ),
    SODRule(
        role_a='procurement_officer', role_b='procurement_manager',
        severity='high',
        reason='Same user cannot raise purchase requests and approve '
               'purchase orders — violates Public Procurement Act s.32.',
    ),

    # ─── Cross-module authority concentration (high severity) ───────
    SODRule(
        role_a='accountant_general', role_b='procurement_manager',
        severity='high',
        reason='Posting authority + procurement approval in one person '
               'enables phantom-vendor fraud (invoice-to-payment cycle '
               'fully controlled).',
    ),
    SODRule(
        role_a='accountant_general', role_b='budget_manager',
        severity='high',
        reason='Posting authority + budget amendment authority enables '
               'retroactive appropriation virement to hide overruns.',
    ),

    # ─── Officer-level cross-module conflicts (medium severity) ─────
    SODRule(
        role_a='account_officer', role_b='procurement_officer',
        severity='medium',
        reason='Entering vendor invoices + raising purchase requests '
               'enables fictitious purchase workflow (mitigated by '
               'manager-level approvals, but still flagged).',
    ),
    SODRule(
        role_a='account_officer', role_b='budget_officer',
        severity='medium',
        reason='Journal entry + appropriation entry concentrates data '
               'capture across both sides of commitment accounting.',
    ),
)


def matrix() -> list[dict]:
    """Return the full SOD matrix for display in the UI."""
    return [
        {
            'role_a':   r.role_a,
            'role_b':   r.role_b,
            'severity': r.severity,
            'reason':   r.reason,
        }
        for r in _SOD_RULES
    ]


def conflicts_for_roles(role_codes: list[str] | set[str]) -> list[dict]:
    """Given a set of role codes held by one user, return each SOD
    rule violated by that combination.

    Returns
    -------
    list of {role_a, role_b, severity, reason}

    Empty list when no conflicts — the combination is SOD-clean.
    """
    held = set(role_codes)
    out: list[dict] = []
    for rule in _SOD_RULES:
        if rule.role_a in held and rule.role_b in held:
            out.append({
                'role_a':   rule.role_a,
                'role_b':   rule.role_b,
                'severity': rule.severity,
                'reason':   rule.reason,
            })
    return out


def conflicts_for_user(user) -> list[dict]:
    """Convenience wrapper — resolve a user's role codes via the
    RoleAssignment helper in core.models (if it exists) or fall back
    to Django Group name matching. Returns the list of SOD rules
    this user currently violates.

    Gracefully returns an empty list when no role-assignment model
    is available so the service stays non-fatal on fresh tenants.
    """
    codes: set[str] = set()
    try:
        from core.models import Role  # noqa: F401
        # If a direct user→role linkage model is added later, plumb
        # it here. For now we inspect Django Group names.
        for group in user.groups.all():
            codes.add(group.name)
    except Exception:
        pass
    if not codes:
        return []
    return conflicts_for_roles(codes)
