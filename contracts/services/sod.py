"""
Shared Segregation-of-Duties bypass helper.

SoD across the contracts module is enforced inside service methods
(activation, IPC certify/approve/voucher/paid, variation review/approve,
retention release, etc.). Every one of those checks needs the same
"can this actor legitimately override?" answer, and all of them must
agree — otherwise an admin who can activate a contract could still be
blocked from certifying an IPC on it, which is confusing and wrong.

Bypass paths (any one is enough):

  1. ``actor.is_superuser``           — Django superuser
  2. ``has_perm('contracts.bypass_sod')`` — explicit per-user/group grant
  3. ``UserTenantRole(role='admin')`` for the active tenant — the
     project's native "Tenant Admin" signal
  4. Active assignment to the curated 'All Access' ``core.Role`` —
     the SAP PFCG-style "do anything" role granted by tenant admins
     for break-glass or business-driven SoD overrides. Seeded by
     migration ``core.0016_seed_all_access_role``.

DELIBERATELY OMITTED:
  - ``actor.is_staff`` is NOT a SoD bypass. ``is_staff`` only grants
    Django admin panel access and is commonly granted by seed scripts
    (tenants/tasks.py, seed_e2e_tenant.py) to ordinary tenant users.
    Treating it as a financial-control override would let any such user
    initiate and approve the same IPC, defeating the five-step payment
    chain. See production-readiness review B1.

Every bypass is still written to the ContractApprovalStep audit trail
by the calling service so auditors see exactly when and by whom SoD
was overridden.
"""
from __future__ import annotations


def actor_can_bypass_sod(actor) -> bool:
    """True if ``actor`` is entitled to skip SoD checks."""
    if actor is None:
        return False
    if getattr(actor, "is_superuser", False):
        return True
    # NOTE: ``is_staff`` is deliberately NOT a bypass — see module docstring.
    has_perm = getattr(actor, "has_perm", None)
    if callable(has_perm) and has_perm("contracts.bypass_sod"):
        return True
    if _actor_is_tenant_admin(actor):
        return True
    if _actor_has_all_access_role(actor):
        return True
    return False


def _actor_has_all_access_role(actor) -> bool:
    """True if ``actor`` holds an active assignment to the 'All Access'
    ``core.Role`` (code='all_access').

    Delegates to the canonical resolver in ``core.permissions`` so the
    SoD bypass and the permission-grant pathway agree by construction.
    Any DB / import failure falls through to False so the other bypass
    paths still get a shot.
    """
    if actor is None:
        return False
    try:
        from core.permissions import _user_has_all_access
        return _user_has_all_access(actor)
    except Exception:
        return False


def _actor_is_tenant_admin(actor) -> bool:
    """
    True if ``actor`` holds the Tenant Admin role for the active tenant.

    ``UserTenantRole`` lives in the public schema (tenants app is
    SHARED_APPS only), so this lookup works even while the request is
    running inside a tenant schema. Any import / DB error falls through
    to False so the caller's other bypass paths still get a shot.
    """
    try:
        from django.db import connection
        from tenants.models import UserTenantRole

        tenant = getattr(connection, "tenant", None)
        if tenant is None or getattr(tenant, "schema_name", "public") == "public":
            return False
        return UserTenantRole.objects.filter(
            user_id=actor.pk,
            tenant_id=tenant.pk,
            role="admin",
            is_active=True,
        ).exists()
    except Exception:
        return False
