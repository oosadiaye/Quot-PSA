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
  2. ``actor.is_staff``               — Django staff (mirrors the DRF
                                        permission gate so the two
                                        layers don't disagree)
  3. ``has_perm('contracts.bypass_sod')`` — explicit per-user/group grant
  4. ``UserTenantRole(role='admin')`` for the active tenant — the
     project's native "Tenant Admin" signal

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
    if getattr(actor, "is_staff", False):
        return True
    has_perm = getattr(actor, "has_perm", None)
    if callable(has_perm) and has_perm("contracts.bypass_sod"):
        return True
    if _actor_is_tenant_admin(actor):
        return True
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
