"""
Seed baseline Role rows for an Accountant-General's office deployment.

Creates six SOD-aware roles covering the three core financial-control
modules (Budget, Accounting, Procurement). Each module has a senior
Manager (can approve, post, change) and an Officer (can add, view,
cannot approve own work). This matches the public-sector two-signature
"maker / checker" convention.

Roles created
-------------
* ``budget_manager``        — Budget & Appropriation Manager
* ``budget_officer``        — Budget Officer
* ``accountant_general``    — Accountant General (senior manager)
* ``account_officer``       — Account Officer
* ``procurement_manager``   — Procurement Manager
* ``procurement_officer``   — Procurement Officer

Usage
-----
    python manage.py tenant_command seed_baseline_roles --schema=<name>
    python manage.py tenant_command seed_baseline_roles --schema=<name> --clear

Re-running without ``--clear`` is idempotent: matches by ``code``,
updates flags to the latest spec, never duplicates.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


# ---------------------------------------------------------------------------
# Baseline SOD-compliant role matrix.
# ---------------------------------------------------------------------------
# For each role we encode (can_view, can_add, can_change, can_delete,
# can_approve, can_post). The split is:
#   Officer → can add + change + view (NOT approve, NOT post)
#   Manager → can view + approve + post (NOT add — maker/checker split)
# Delete is reserved for admin on all roles (destructive; should require
# a separate authority).
# ---------------------------------------------------------------------------
BASELINE_ROLES: list[dict] = [
    # ───── Budget ────────────────────────────────────────────────
    {
        'code':      'budget_officer',
        'name':      'Budget Officer',
        'module':    'budget',
        'role_type': 'officer',
        'perms':     dict(can_view=True, can_add=True, can_change=True,
                          can_delete=False, can_approve=False, can_post=False),
        'is_default': True,
    },
    {
        'code':      'budget_manager',
        'name':      'Budget & Appropriation Manager',
        'module':    'budget',
        'role_type': 'manager',
        'perms':     dict(can_view=True, can_add=False, can_change=True,
                          can_delete=False, can_approve=True, can_post=True),
        'is_default': False,
    },

    # ───── Accounting ────────────────────────────────────────────
    {
        'code':      'account_officer',
        'name':      'Account Officer',
        'module':    'accounting',
        'role_type': 'officer',
        'perms':     dict(can_view=True, can_add=True, can_change=True,
                          can_delete=False, can_approve=False, can_post=False),
        'is_default': True,
    },
    {
        'code':      'accountant_general',
        'name':      'Accountant General',
        'module':    'accounting',
        'role_type': 'manager',
        'perms':     dict(can_view=True, can_add=False, can_change=True,
                          can_delete=False, can_approve=True, can_post=True),
        'is_default': False,
    },

    # ───── Procurement ───────────────────────────────────────────
    {
        'code':      'procurement_officer',
        'name':      'Procurement Officer',
        'module':    'procurement',
        'role_type': 'officer',
        'perms':     dict(can_view=True, can_add=True, can_change=True,
                          can_delete=False, can_approve=False, can_post=False),
        'is_default': True,
    },
    {
        'code':      'procurement_manager',
        'name':      'Procurement Manager',
        'module':    'procurement',
        'role_type': 'manager',
        'perms':     dict(can_view=True, can_add=False, can_change=True,
                          can_delete=False, can_approve=True, can_post=True),
        'is_default': False,
    },
]


class Command(BaseCommand):
    help = 'Seed baseline Budget / Accounting / Procurement roles.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Delete any existing baseline role rows before inserting.',
        )

    def handle(self, *args, **options):
        from core.models import Role

        clear: bool = options['clear']
        baseline_codes = [spec['code'] for spec in BASELINE_ROLES]

        if clear:
            deleted, _ = Role.objects.filter(code__in=baseline_codes).delete()
            self.stdout.write(self.style.WARNING(
                f'Cleared {deleted} existing baseline role rows.'
            ))

        created = updated = 0
        for spec in BASELINE_ROLES:
            perms = spec['perms']
            obj, was_created = Role.objects.update_or_create(
                code=spec['code'],
                defaults={
                    'name':       spec['name'],
                    'module':     spec['module'],
                    'role_type':  spec['role_type'],
                    'is_default': spec['is_default'],
                    'is_active':  True,
                    **perms,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
            flags = ' '.join(
                k.replace('can_', '+') for k, v in perms.items() if v
            )
            self.stdout.write(
                f'  {"[+]" if was_created else "[~]"} {obj.code:<24} '
                f'{obj.name:<40} {flags}'
            )

        self.stdout.write(self.style.SUCCESS(
            f'Baseline roles — {created} created, {updated} updated.'
        ))
