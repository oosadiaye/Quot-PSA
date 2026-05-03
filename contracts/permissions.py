"""
Role-based permission classes for the contracts API.

These permissions compose on top of the standard DRF IsAuthenticated
so the authentication layer stays uniform across the project. They
express the *authorization* dimension only — i.e. "what role does this
user have on this contract?".

The class hierarchy mirrors the segregation-of-duties matrix encoded
by the service layer:

                         create  activate  draft IPC  certify  approve  pay  close
    Contract Officer       ✓        ·         ·         ·        ·      ·     ·
    Procurement Head       ·        ✓         ·         ·        ·      ·     ·
    Contractor Rep         ·        ·         ✓         ·        ·      ·     ·
    Engineer / QS          ·        ·         ·         ✓        ·      ·     ·
    Approving Officer      ·        ·         ·         ·        ✓      ·     ·
    Treasury Officer       ·        ·         ·         ·        ·      ✓     ·
    Accountant-General     ·        ·         ·         ·        ·      ·     ✓

SoD enforcement (actor ≠ creator/certifier/approver/etc.) happens
inside the service layer — the role matrix here only decides WHICH
endpoint a user may hit, not whether the specific state-transition is
allowed for them on this particular contract.

Superusers always pass; staff users get the same treatment as a
Procurement Head for day-to-day operations.
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated, SAFE_METHODS


# ── Django permission codenames (created via migration data seeds) ─────

PERM_VIEW_CONTRACT      = "contracts.view_contract"
PERM_ADD_CONTRACT       = "contracts.add_contract"
PERM_CHANGE_CONTRACT    = "contracts.change_contract"
PERM_ACTIVATE_CONTRACT  = "contracts.activate_contract"
PERM_CLOSE_CONTRACT     = "contracts.close_contract"

# ── SoD bypass ─────────────────────────────────────────────────────────
# SAP-style: if a user is granted this permission (or is a Django
# superuser), the "actor ≠ creator/certifier/approver" segregation-of-
# duties checks are *skipped* in the service layer. Default tenants do
# NOT grant this — it exists so trusted power users / test accounts /
# automated reconciliation jobs can transition contracts end-to-end.
#
# Auditors see every SoD override in the ContractApprovalStep audit
# trail (the service records `sod_bypassed=True` on the step row).
PERM_BYPASS_SOD         = "contracts.bypass_sod"

PERM_DRAFT_IPC          = "contracts.add_interimpaymentcertificate"
PERM_CERTIFY_IPC        = "contracts.certify_ipc"
PERM_APPROVE_IPC        = "contracts.approve_ipc"

# Milestone certification — the engineer/QS marks physical work
# complete on a milestone. Functionally the "approve milestone"
# action: it transitions the milestone from PENDING/IN_PROGRESS to
# COMPLETED and unlocks IPC submission against that milestone.
# Reuses the same SoD bucket as IPC certification because the same
# professional certifies both.
PERM_CERTIFY_MILESTONE  = "contracts.certify_milestone"
PERM_RAISE_VOUCHER      = "contracts.raise_voucher"
PERM_MARK_IPC_PAID      = "contracts.mark_ipc_paid"

PERM_DRAFT_VARIATION    = "contracts.add_contractvariation"
PERM_REVIEW_VARIATION   = "contracts.review_variation"
PERM_APPROVE_VARIATION  = "contracts.approve_variation"

PERM_APPROVE_RETENTION  = "contracts.approve_retention"
PERM_PAY_RETENTION      = "contracts.pay_retention"

PERM_ISSUE_COMPLETION   = "contracts.add_completioncertificate"


def _user_is_tenant_admin(user) -> bool:
    """Return True when ``user`` has ``UserTenantRole.role='admin'`` on
    any active tenant assignment.

    Tenant admins are this codebase's notion of "the boss for one
    organisation" — distinct from Django ``is_superuser``/``is_staff``
    which are platform-wide. The contract permission classes treat
    them as universally trusted for *any* contract action within
    their tenant; the underlying schema isolation already prevents
    cross-tenant leakage so granting all-permissions inside one
    schema is safe.
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    try:
        # Local import — avoids circular dependency at module load.
        from tenants.models import UserTenantRole
        return UserTenantRole.objects.filter(
            user=user, role='admin', is_active=True,
        ).exists()
    except Exception:
        # If the tenant table is unreachable for any reason (legacy
        # tests, schema not migrated), fall back to denying — safer
        # than granting blanket admin rights on a misconfigured row.
        return False


class _BaseContractsPermission(IsAuthenticated):
    """Authenticated by default; subclasses override ``required_perms``."""

    #: Tuple of permission codenames; ANY of them grants access.
    required_perms: tuple[str, ...] = ()

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        user = request.user
        # Three tiers of universal bypass:
        #   1. Django superuser  — platform owner
        #   2. Django staff      — back-office staff with admin-app access
        #   3. Tenant admin      — UserTenantRole.role='admin' on this
        #      tenant (the customer's own administrator)
        if user.is_superuser or user.is_staff:
            return True
        if _user_is_tenant_admin(user):
            return True
        if not self.required_perms:
            return True
        return any(user.has_perm(p) for p in self.required_perms)


class CanViewContracts(_BaseContractsPermission):
    """Read access to contract surfaces.

    Safe methods require ``view_contract``; write methods fall through
    to the endpoint-specific class.
    """

    required_perms = (PERM_VIEW_CONTRACT,)

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return super().has_permission(request, view)
        # Non-safe request — let the endpoint's own permission class
        # decide. We still require authentication.
        return IsAuthenticated().has_permission(request, view)


class CanManageContracts(_BaseContractsPermission):
    """Create / edit contract header fields (draft stage only)."""
    required_perms = (PERM_ADD_CONTRACT, PERM_CHANGE_CONTRACT)


class CanActivateContract(_BaseContractsPermission):
    required_perms = (PERM_ACTIVATE_CONTRACT,)


class CanCloseContract(_BaseContractsPermission):
    required_perms = (PERM_CLOSE_CONTRACT,)


class CanDraftIPC(_BaseContractsPermission):
    required_perms = (PERM_DRAFT_IPC,)


class CanCertifyIPC(_BaseContractsPermission):
    required_perms = (PERM_CERTIFY_IPC,)


class CanApproveMilestone(_BaseContractsPermission):
    """Approve / certify completion of a contract milestone.

    Granted to:
      • Django superusers / staff (universal)
      • Tenant admins (UserTenantRole.role='admin') — the customer's
        own organisation administrator
      • Anyone with ``contracts.certify_milestone`` OR
        ``contracts.certify_ipc`` (engineer / QS role) — the same
        person who certifies IPCs typically certifies milestones,
        so the IPC perm is accepted as a legacy alias.
    """
    required_perms = (PERM_CERTIFY_MILESTONE, PERM_CERTIFY_IPC)


class CanApproveIPC(_BaseContractsPermission):
    required_perms = (PERM_APPROVE_IPC,)


class CanRaiseVoucher(_BaseContractsPermission):
    required_perms = (PERM_RAISE_VOUCHER,)


class CanMarkIPCPaid(_BaseContractsPermission):
    required_perms = (PERM_MARK_IPC_PAID,)


class CanDraftVariation(_BaseContractsPermission):
    required_perms = (PERM_DRAFT_VARIATION,)


class CanReviewVariation(_BaseContractsPermission):
    required_perms = (PERM_REVIEW_VARIATION,)


class CanApproveVariation(_BaseContractsPermission):
    required_perms = (PERM_APPROVE_VARIATION,)


class CanApproveRetention(_BaseContractsPermission):
    required_perms = (PERM_APPROVE_RETENTION,)


class CanPayRetention(_BaseContractsPermission):
    required_perms = (PERM_PAY_RETENTION,)


class CanIssueCompletion(_BaseContractsPermission):
    required_perms = (PERM_ISSUE_COMPLETION,)
