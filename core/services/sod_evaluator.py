"""
Rule-driven Segregation-of-Duties evaluator.

Reads ``core.SoDRule`` rows at evaluation time. No hardcoded role pairs,
no hardcoded permission pairs — everything is data the tenant can edit
through the SoD-rules admin page. Changes take effect on the next call
because the evaluator queries the database, and the row-level cache is
invalidated by the post_save signal on ``SoDRule``.

Two evaluation modes match the two ``SoDRule.scope`` values:

1. ``check_assignment(user, *, additional_role=None,
                       additional_permission=None)``
   For ``hold`` scope rules — "this user must not hold both
   permissions". Used by the role-editor and assignment screens to
   show violations BEFORE save (and reject on save when severity is
   ``block``).

2. ``check_action(user, action_permission, document)``
   For ``same_document`` scope rules — "this user must not exercise
   both permissions on the same document". Used by service-layer
   action handlers (PR.approve, IPC.certify, JV.post, etc.) to
   reject the action when the same user already holds the prior
   permission on the same document.

Both modes return a ``list[Violation]`` (possibly empty). Callers
decide whether to surface as a hard block (severity=block) or a
non-fatal warning (severity=warn).

Bypass: holders of ``rbac.bypass_sod`` (a Django auth.Permission
codename) skip evaluation entirely. ``actor.is_superuser`` /
``actor.is_staff`` also bypass — same escape hatch the existing
``contracts.services.sod.actor_can_bypass_sod`` provides for contracts.
Bypasses are logged at WARNING level so audit reports can flag them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Optional

from django.contrib.auth.models import AbstractUser
from django.db.models import Q

logger = logging.getLogger(__name__)


# ─── Violation record returned to callers ────────────────────────────

@dataclass(frozen=True)
class Violation:
    """One SoD rule that the proposed action / assignment would breach.

    Equality is by (rule_id, scope) so duplicates from multiple
    role-paths collapse to one record per rule.
    """
    rule_id: int
    rule_code: str
    rule_name: str
    scope: str          # 'hold' | 'same_document'
    severity: str       # 'block' | 'warn'
    permission_a_code: str
    permission_a_label: str
    permission_b_code: str
    permission_b_label: str
    reason: str

    @property
    def is_blocking(self) -> bool:
        return self.severity == 'block'


# ─── Bypass logic (mirrors contracts.services.sod.actor_can_bypass_sod) ─

_BYPASS_PERM = 'rbac.bypass_sod'


def actor_can_bypass(actor: Optional[AbstractUser]) -> bool:
    """True when ``actor`` is allowed to skip SoD checks.

    Mirrors the contract-side bypass so the entire ERP applies the same
    escape hatch. Logs at WARNING when bypass is exercised so audit
    reports surface it.
    """
    if actor is None or not actor.is_authenticated:
        return False
    if actor.is_superuser or actor.is_staff:
        logger.warning(
            'sod_evaluator: bypass via staff/superuser by user_id=%s',
            actor.pk,
        )
        return True
    if actor.has_perm(_BYPASS_PERM):
        logger.warning(
            'sod_evaluator: bypass via rbac.bypass_sod permission by user_id=%s',
            actor.pk,
        )
        return True
    return False


# ─── Permission resolution helpers ───────────────────────────────────

def _user_permission_codes(user: AbstractUser) -> set[str]:
    """Return every ``PermissionDefinition.code`` held by the user
    through any active ``RoleAssignment`` → ``Role.permissions``.

    Inactive role assignments and inactive roles are skipped so a
    user who has been temporarily revoked stops causing violations
    immediately.

    The query is intentionally a single round-trip — this runs on
    every action-time check.
    """
    from core.models import RoleAssignment

    codes_qs = (
        RoleAssignment.objects
        .filter(user=user, is_active=True, role__is_active=True)
        .values_list('role__permissions__code', flat=True)
    )
    return {code for code in codes_qs if code}


def _role_permission_codes(role) -> set[str]:
    """Permission codes attached to a single Role row."""
    return set(role.permissions.values_list('code', flat=True))


# ─── Mode 1: assignment-time check ───────────────────────────────────

def check_assignment(
    user: AbstractUser,
    *,
    additional_role=None,
    additional_permission_codes: Optional[Iterable[str]] = None,
) -> list[Violation]:
    """Evaluate ``hold`` scope rules against the permissions a user
    would hold AFTER a proposed change.

    Pass ``additional_role`` (a ``Role`` instance not yet assigned)
    or ``additional_permission_codes`` (a set of new perms being
    added to a role the user already has) to preview violations
    BEFORE save — the role editor uses this to show a warning panel
    on the form.

    Returns the deduplicated list of violations. Empty when clean.
    """
    if actor_can_bypass(user):
        return []

    from core.models import SoDRule

    held = _user_permission_codes(user)
    if additional_role is not None:
        held |= _role_permission_codes(additional_role)
    if additional_permission_codes:
        held |= set(additional_permission_codes)

    if not held:
        return []

    # Pull all active hold-scope rules whose BOTH legs intersect
    # the user's effective permission set. The query reduces ~150
    # rules to the handful that could match before we iterate in
    # Python.
    candidate_rules = SoDRule.objects.filter(
        is_active=True, scope='hold',
        permission_a__code__in=held,
        permission_b__code__in=held,
    ).select_related('permission_a', 'permission_b')

    return _materialise(candidate_rules)


# ─── Mode 2: action-time check ────────────────────────────────────────

def check_action(
    user: AbstractUser,
    action_permission_code: str,
    document,
    *,
    document_actor_attr_map: Optional[dict[str, str]] = None,
) -> list[Violation]:
    """Evaluate ``same_document`` scope rules against ``user`` acting
    on ``document`` with ``action_permission_code``.

    A violation occurs when:

      • a same_document rule names ``action_permission_code`` as one
        of its two permissions, AND
      • the document records that ``user`` previously exercised the
        OTHER permission on this same document.

    "Previously exercised" is detected by looking at conventional
    actor attributes on the document. By default we check
    ``created_by_id``, ``submitted_by_id``, ``approved_by_id``,
    ``certified_by_id``, ``posted_by_id``, ``raised_by_id``,
    ``paid_by_id`` against ``user.pk`` — these are the standard
    fields the existing audit-base models carry. Callers needing
    custom mappings (e.g. Contract uses ``activator``) pass
    ``document_actor_attr_map={'permission_code': 'attr_name'}``.

    Returns the deduplicated list of violations. Empty when clean.
    """
    if actor_can_bypass(user):
        return []

    from core.models import SoDRule

    candidate_rules = SoDRule.objects.filter(
        Q(permission_a__code=action_permission_code) |
        Q(permission_b__code=action_permission_code),
        is_active=True, scope='same_document',
    ).select_related('permission_a', 'permission_b')

    out: list[Violation] = []
    for rule in candidate_rules:
        # The "other side" of the rule — the permission code the
        # actor must NOT have already exercised on this document.
        other_code = (
            rule.permission_b.code
            if rule.permission_a.code == action_permission_code
            else rule.permission_a.code
        )
        if _user_already_exercised_on_document(
            user, other_code, document, document_actor_attr_map,
        ):
            out.extend(_materialise([rule]))

    return out


# ─── Helpers ─────────────────────────────────────────────────────────

# Conventional document fields that record which user performed which
# action. Maps permission action names → likely document attribute.
# Callers can override per-document via document_actor_attr_map.
_DEFAULT_ACTOR_ATTRS_BY_ACTION = {
    'create':   ('created_by_id',),
    'submit':   ('submitted_by_id', 'submitter_id'),
    'certify':  ('certified_by_id', 'certifier_id'),
    'review':   ('reviewed_by_id', 'reviewer_id'),
    'approve':  ('approved_by_id', 'approver_id'),
    'post':     ('posted_by_id',),
    'release':  ('released_by_id',),
    'pay':      ('paid_by_id',),
    'raise':    ('raised_by_id',),
    'check':    ('checked_by_id',),
    'audit':    ('audited_by_id',),
    'reverse':  ('reversed_by_id',),
}


def _user_already_exercised_on_document(
    user, permission_code: str, document,
    override_map: Optional[dict[str, str]],
) -> bool:
    """Did ``user`` already perform the action implied by
    ``permission_code`` on ``document``?

    Resolution order:
      1. Caller-supplied override (``override_map[permission_code]``)
      2. Conventional attribute by action verb (last segment of code)
      3. Fallback: ``created_by_id`` (covers the most common SoD case
         "you cannot approve what you created")
    """
    # Override wins.
    attr_name = (override_map or {}).get(permission_code)
    if attr_name and hasattr(document, attr_name):
        return getattr(document, attr_name) == user.pk

    # Convention: split ``module.resource.action`` and look up by action.
    action = permission_code.rsplit('.', 1)[-1] if '.' in permission_code else permission_code
    candidates = _DEFAULT_ACTOR_ATTRS_BY_ACTION.get(action, ())
    for attr in candidates:
        if hasattr(document, attr):
            return getattr(document, attr) == user.pk

    # Final fallback — the most universal SoD invariant.
    if hasattr(document, 'created_by_id'):
        return document.created_by_id == user.pk

    return False


def _materialise(rules: Iterable) -> list[Violation]:
    """Convert SoDRule rows into Violation dataclass instances.

    Deduplicates by rule_id so a user matching the same rule via
    multiple role assignments only produces one Violation entry.
    """
    seen: set[int] = set()
    out: list[Violation] = []
    for rule in rules:
        if rule.id in seen:
            continue
        seen.add(rule.id)
        out.append(Violation(
            rule_id=rule.id,
            rule_code=rule.code,
            rule_name=rule.name,
            scope=rule.scope,
            severity=rule.severity,
            permission_a_code=rule.permission_a.code,
            permission_a_label=rule.permission_a.label,
            permission_b_code=rule.permission_b.code,
            permission_b_label=rule.permission_b.label,
            reason=rule.description or rule.name,
        ))
    return out


# ─── Convenience: raise a structured error ───────────────────────────

class SoDViolation(Exception):
    """Raised by ``enforce_*`` helpers when a blocking violation exists.

    Callers in the service layer can ``except SoDViolation`` to roll
    back the surrounding ``transaction.atomic()``. The DRF view layer
    converts this to a 403 with the ``violations`` payload so the
    React UI can render each rule's reason in a banner.
    """
    def __init__(self, violations: list[Violation]):
        self.violations = violations
        msg = '; '.join(f'{v.rule_code}: {v.reason}' for v in violations)
        super().__init__(f'SoD violation(s): {msg}')


def enforce_action(
    user, action_permission_code: str, document, **kwargs,
) -> None:
    """Raise ``SoDViolation`` if any blocking violations apply to this action.

    Non-blocking (``warn``) violations are returned via logger only —
    the action proceeds. Callers wanting to surface warnings should
    call ``check_action`` directly.
    """
    violations = check_action(user, action_permission_code, document, **kwargs)
    blocking = [v for v in violations if v.is_blocking]
    if blocking:
        raise SoDViolation(blocking)
    for v in violations:
        logger.warning(
            'SoD warn (allowed): user_id=%s rule=%s on doc=%s',
            user.pk, v.rule_code, getattr(document, 'pk', '?'),
        )
