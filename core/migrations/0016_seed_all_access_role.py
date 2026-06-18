"""Seed the canonical 'All Access' Role.

Idempotent ``update_or_create`` of a single curated ``core.Role`` row
per tenant schema. Marked ``is_system=True`` so admins cannot delete it
(matches the same protection applied to other system-seeded roles like
accountant_general / budget_officer).

Why this exists:
  Tenant admins need a way to grant a specific user "do anything"
  authority — for break-glass scenarios, system-administrator users,
  or business-driven SoD overrides where the client has explicitly
  decided the audit trail is sufficient governance. The "All Access"
  role is the canonical signal: assign it to a user, and every
  tenant-scoped permission check sees ``{'__all__'}`` short-circuit
  (see ``core.permissions._get_tenant_permissions``) plus every SoD
  bypass helper returns True (see ``contracts.services.sod``).

Replayed across every tenant schema by ``migrate_schemas --tenant``.
"""
from django.db import migrations


ALL_ACCESS_DEFAULTS = {
    'name': 'All Access',
    'module': 'admin',
    'role_type': 'manager',
    'can_view': True,
    'can_add': True,
    'can_change': True,
    'can_delete': True,
    'can_approve': True,
    'can_post': True,
    'is_active': True,
    'is_default': False,
    # System-seeded — admins can edit assignments but the role itself
    # cannot be deleted (enforced at the model / admin layer).
    'is_system': True,
}


def seed_all_access_role(apps, _schema_editor):
    Role = apps.get_model('core', 'Role')
    Role.objects.update_or_create(
        code='all_access',
        defaults=ALL_ACCESS_DEFAULTS,
    )


def remove_all_access_role(apps, _schema_editor):
    """Reverse migration — best-effort delete.

    Refuses to delete if the role has live assignments (avoids
    orphaning users mid-flight if a tenant rolls back). Operators
    must reassign affected users first.
    """
    Role = apps.get_model('core', 'Role')
    role = Role.objects.filter(code='all_access').first()
    if role is None:
        return
    try:
        if hasattr(role, 'assignments') and role.assignments.filter(is_active=True).exists():
            # Don't risk it — bail out and let the operator handle.
            return
    except Exception:
        pass
    role.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_re_encrypt_mfa_secrets_v2'),
    ]

    operations = [
        migrations.RunPython(seed_all_access_role, remove_all_access_role),
    ]
