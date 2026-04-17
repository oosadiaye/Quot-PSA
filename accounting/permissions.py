"""
Role-based permission classes for accounting API surfaces.

Used by IPSAS report views and any other endpoint that exposes
consolidated financial data. Stacked on top of ``IsAuthenticated`` so
the authentication layer stays standard — these add the authorization
dimension only.

S5-03 — IPSAS financial statements contain consolidated public-sector
financials (SoFP, SoFPerformance, Cash Flow, Changes in Net Assets,
Notes, Budget-vs-Actual). Previously these were gated by
``IsAuthenticated`` alone, which meant any authenticated user — including
a supplier or revenue collector — could pull the full state position.
IPSAS 1 disclosures are public *after* official publication; before
publication they must be restricted to Finance/Audit roles.

Grant policy (any of the following satisfies access):

* Superuser / staff users (administrative bypass)
* Django permission ``accounting.view_financial_statements`` (preferred
  granular grant)
* Legacy permission ``accounting.view_journalheader`` (anyone with
  general ledger read access implicitly has report access — matches
  the historical role model before this permission existed)
* ``is_oversight`` role on a ``core.Organization`` linked to the user
  (BUDGET_AUTHORITY, FINANCE_AUTHORITY, AUDIT_AUTHORITY) — this is
  the Nigerian public-sector equivalent of "Commissioner of Finance /
  Auditor-General" access.
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated


class CanViewFinancialStatements(IsAuthenticated):
    """Gate for IPSAS report endpoints."""

    _ACCEPTED_PERMS = (
        'accounting.view_financial_statements',
        'accounting.view_journalheader',
    )

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False

        user = request.user
        if not user or not user.is_authenticated:
            return False

        # Administrative bypass — superusers and staff always allowed.
        if user.is_superuser or user.is_staff:
            return True

        # Explicit Django permissions.
        if any(user.has_perm(p) for p in self._ACCEPTED_PERMS):
            return True

        # Nigerian public-sector oversight roles.
        # User must be linked via UserOrganization to an Organization whose
        # ``org_role`` grants cross-MDA read (BUDGET/FINANCE/AUDIT authority).
        if _user_has_oversight_org(user):
            return True

        return False


def _user_has_oversight_org(user) -> bool:
    """True if user is linked to any Organization with cross-MDA read rights.

    Defensive against older deployments that may not have the
    ``UserOrganization`` table yet — we swallow the lookup error and
    return False in that case so the caller falls through to a 403
    rather than a 500.
    """
    try:
        from core.models import UserOrganization
        return (
            UserOrganization.objects
            .filter(user=user, is_active=True)
            .filter(organization__org_role__in=(
                'BUDGET_AUTHORITY', 'FINANCE_AUTHORITY', 'AUDIT_AUTHORITY',
            ))
            .exists()
        )
    except Exception:
        return False


# =============================================================================
# S6-04 — RequiresMFA
# =============================================================================

class RequiresMFA(IsAuthenticated):
    """Permission that requires the session to carry a fresh MFA verification.

    Apply to viewsets that mutate sensitive state (journal posting,
    payment disbursement, warrant release, year-end close, period
    reopen). Users with MFA NOT enrolled are rejected with a 403
    pointing them at the enrollment endpoint — this is the whole point
    of MFA as a control, so there is no bypass for "just hasn't
    enrolled yet" beyond an explicit admin override on the user object.

    Freshness window is 30 minutes by default. A user who verified
    MFA more than 30 minutes ago must re-verify before posting. Tune
    via ``settings.MFA_VERIFICATION_TTL_MINUTES``.

    Exemptions:
      * Superuser — full administrative bypass. Strongly advise
        superusers to enroll MFA anyway; this exemption exists only
        to guarantee recoverability when MFA system itself breaks.
      * Users explicitly granted ``core.bypass_mfa`` (custom
        permission; intentionally not created automatically).
    """

    # Configurable freshness window.
    DEFAULT_TTL_MINUTES = 30

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False

        user = request.user

        # Superuser override — last-resort path when MFA system itself is
        # offline. Recommend disabling once the tenant is stable.
        if user.is_superuser:
            return True

        if user.has_perm('core.bypass_mfa'):
            return True

        # Must be enrolled.
        if not _user_is_mfa_enrolled(user):
            return False

        # Session must have been MFA-verified recently.
        return _session_mfa_is_fresh(
            request,
            max_age_minutes=self._ttl_minutes(),
        )

    @classmethod
    def _ttl_minutes(cls) -> int:
        from django.conf import settings
        return getattr(
            settings, 'MFA_VERIFICATION_TTL_MINUTES', cls.DEFAULT_TTL_MINUTES,
        )


def _user_is_mfa_enrolled(user) -> bool:
    """True if the user has completed MFA enrollment."""
    try:
        from core.models import UserMFA
        mfa = UserMFA.objects.filter(user=user).first()
        return bool(mfa and mfa.is_enrolled)
    except Exception:
        # If the UserMFA table isn't present (migration not yet applied),
        # fall back to allowing the user through rather than hard-locking
        # production on a deploy-order problem. This is a deliberate
        # trade-off: false-accept during rollout > global outage.
        return True


def _session_mfa_is_fresh(request, max_age_minutes: int) -> bool:
    """Whether the session's MFA verification is still fresh."""
    from datetime import datetime
    from django.utils import timezone

    session = getattr(request, 'session', None)
    if session is None:
        return False
    stamp = session.get('mfa_verified_at')
    if not stamp:
        return False
    try:
        verified_at = datetime.fromisoformat(stamp)
    except (ValueError, TypeError):
        return False
    age = timezone.now() - verified_at
    return age.total_seconds() <= max_age_minutes * 60
