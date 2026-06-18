"""
core.checks — Django system checks for the audit-log redaction policy.

V18 — schema-growth enforcement
================================

The audit-log redaction registry ``AuditLog.SENSITIVE_FIELDS_BY_MODEL``
must list every model whose field names match a known PII / banking
shape. Without an automated check, future migrations that add a new
``national_id_number`` or ``bvn`` column to a model that is NOT in the
registry would silently log cleartext PII into ``AuditLog.changes``.

This check emits ``core.W001`` for any model in the curated app set
that exposes a PII-shaped field name without being registered in
``SENSITIVE_FIELDS_BY_MODEL``. The check runs on ``manage.py check``
and on every test session, so a developer who adds a new sensitive
column will see the warning the next time CI runs.
"""
from __future__ import annotations

from django.apps import apps
from django.core.checks import Warning, register


# Field-name shapes that ALWAYS warrant audit-log redaction. Matched
# as substrings (case-insensitive) against ``field.name`` so common
# variants like ``employee_bvn``, ``next_of_kin_bank_account_number``,
# ``primary_tax_identification_number`` are caught without having to
# enumerate every prefix.
PII_FIELD_PATTERNS = (
    'national_id_number',
    'tax_identification_number',
    'bvn',
    'social_security_number',
    'ssn',
    'passport_number',
    'bank_account',
    'bank_routing',
    'account_number',
    'routing_number',
    'credit_card',
    'cvv',
)

# Curated app labels. We intentionally do NOT scan ``auth``,
# ``contenttypes``, ``admin``, ``sessions`` etc. — Django's system
# apps don't carry domain PII and would just pollute the check output
# with false positives like ``Token.account_number`` (none exists, but
# the prefix-based names in third-party packages occasionally collide).
DOMAIN_APP_LABELS = (
    'accounting',
    'hrm',
    'contracts',
    'procurement',
    'budget',
    'core',
    'workflow',
)


@register()
def audit_log_pii_coverage_check(app_configs, **kwargs):
    """W001 — every domain model with a PII-shaped field name must be
    registered in ``AuditLog.SENSITIVE_FIELDS_BY_MODEL`` for redaction.

    Returns a list of ``checks.Warning`` instances, one per model that
    needs registry entry. The hint string gives the developer the exact
    redaction-set update needed.
    """
    # Late import — the AuditLog model is in the same app and importing
    # at module load time triggers AppRegistryNotReady in some test
    # bootstraps.
    try:
        from core.models import AuditLog
    except Exception:  # pragma: no cover — defensive against bootstrap
        return []

    registry = getattr(AuditLog, 'SENSITIVE_FIELDS_BY_MODEL', {}) or {}

    warnings: list[Warning] = []
    for model in apps.get_models():
        if model._meta.app_label not in DOMAIN_APP_LABELS:
            continue
        model_name = model.__name__
        registered = set(registry.get(model_name, set()) or set())

        # Identify PII-shaped fields on this model. Skip relations:
        # an FK named ``bank_account`` to ``accounting.BankAccount``
        # stores an FK id, not PII — the PII lives on the target
        # ``BankAccount`` model itself. Same for M2M / reverse rels.
        sensitive_fields_found: list[str] = []
        for field in model._meta.get_fields():
            field_name = getattr(field, 'name', None)
            if not field_name:
                continue
            # Skip relations and reverse accessors — only concrete
            # value-bearing columns can leak PII into AuditLog.changes.
            if getattr(field, 'is_relation', False):
                continue
            if not getattr(field, 'concrete', False):
                continue
            name_lower = field_name.lower()
            if any(pat in name_lower for pat in PII_FIELD_PATTERNS):
                sensitive_fields_found.append(field_name)

        if not sensitive_fields_found:
            continue

        # Already fully covered? Then nothing to warn about.
        unregistered = [
            f for f in sensitive_fields_found if f not in registered
        ]
        if not unregistered:
            continue

        warnings.append(
            Warning(
                (
                    f"Model '{model._meta.app_label}.{model_name}' has "
                    f"PII-shaped field(s) {sorted(unregistered)!r} that "
                    f"are NOT registered in "
                    f"AuditLog.SENSITIVE_FIELDS_BY_MODEL — audit log "
                    f"entries for this model will persist these values "
                    f"in cleartext, breaching NDPR/IFMIS redaction "
                    f"policy."
                ),
                hint=(
                    "Add this model to "
                    "`AuditLog.SENSITIVE_FIELDS_BY_MODEL` to ensure "
                    "audit log redaction. Example: "
                    f"SENSITIVE_FIELDS_BY_MODEL['{model_name}'] = "
                    f"{set(sorted(unregistered))!r}"
                ),
                obj=model,
                id='core.W001',
            )
        )
    return warnings
