"""
Management command to seed default roles for tenants.

Creates default roles with module-based permissions:
- Account Manager / Account Officer
- Sales Manager / Sales Officer
- Procurement Manager / Procurement Officer
- Inventory Manager / Inventory Officer
- HR Manager / HR Officer
- Service Engineer Manager / Service Officer (mapped from technical module)
- Budget Manager / Budget Officer
- Production Manager / Production Officer
- Quality Manager / Quality Officer
- Technical Manager / Technical Officer
- Admin Manager (for tenant admin)

Usage:
    python manage.py seed_default_roles --tenant=schema_name
    python manage.py seed_default_roles --all (seeds all tenants)
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django_tenants.utils import schema_context

from tenants.models import Client, UserTenantRole
# Role now lives in each tenant's own schema
from core.models import Role


DEFAULT_ROLES = [
    # ── Quot PSE: Government IFMIS Roles ────────────────────────────────
    # Accounting (GL)
    {'name': 'Accountant', 'code': 'accountant', 'module': 'accounting',
     'role_type': 'manager', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': True, 'can_approve': True, 'can_post': True, 'is_default': False},
    {'name': 'Accounts Officer', 'code': 'accounts_officer', 'module': 'accounting',
     'role_type': 'officer', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': False, 'can_approve': False, 'can_post': False, 'is_default': False},
    # Budget & Appropriation
    {'name': 'Budget Controller', 'code': 'budget_controller', 'module': 'budget',
     'role_type': 'manager', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': True, 'can_approve': True, 'can_post': False, 'is_default': False},
    {'name': 'Budget Officer', 'code': 'budget_officer', 'module': 'budget',
     'role_type': 'officer', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': False, 'can_approve': False, 'can_post': False, 'is_default': False},
    # Treasury & TSA
    {'name': 'Treasury Manager', 'code': 'treasury_manager', 'module': 'treasury',
     'role_type': 'manager', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': True, 'can_approve': True, 'can_post': True, 'is_default': False},
    {'name': 'Treasury Officer', 'code': 'treasury_officer', 'module': 'treasury',
     'role_type': 'officer', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': False, 'can_approve': False, 'can_post': False, 'is_default': False},
    # Revenue (IGR)
    {'name': 'Revenue Controller', 'code': 'revenue_controller', 'module': 'revenue',
     'role_type': 'manager', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': True, 'can_approve': True, 'can_post': True, 'is_default': False},
    {'name': 'Revenue Officer', 'code': 'revenue_officer', 'module': 'revenue',
     'role_type': 'officer', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': False, 'can_approve': False, 'can_post': False, 'is_default': False},
    # Procurement
    {'name': 'Procurement Manager', 'code': 'procurement_manager', 'module': 'procurement',
     'role_type': 'manager', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': True, 'can_approve': True, 'can_post': False, 'is_default': False},
    {'name': 'Procurement Officer', 'code': 'procurement_officer', 'module': 'procurement',
     'role_type': 'officer', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': False, 'can_approve': False, 'can_post': False, 'is_default': False},
    # Stores & Inventory
    {'name': 'Stores Manager', 'code': 'stores_manager', 'module': 'inventory',
     'role_type': 'manager', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': True, 'can_approve': True, 'can_post': False, 'is_default': False},
    {'name': 'Stores Officer', 'code': 'stores_officer', 'module': 'inventory',
     'role_type': 'officer', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': False, 'can_approve': False, 'can_post': False, 'is_default': False},
    # Human Resources
    {'name': 'HR Manager', 'code': 'hr_manager', 'module': 'hrm',
     'role_type': 'manager', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': True, 'can_approve': True, 'can_post': False, 'is_default': False},
    {'name': 'HR Officer', 'code': 'hr_officer', 'module': 'hrm',
     'role_type': 'officer', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': False, 'can_approve': False, 'can_post': False, 'is_default': False},
    # Workflow
    {'name': 'Workflow Admin', 'code': 'workflow_admin', 'module': 'workflow',
     'role_type': 'manager', 'can_view': True, 'can_add': True, 'can_change': True,
     'can_delete': True, 'can_approve': True, 'can_post': False, 'is_default': False},
    # Reporting
    {'name': 'Report Viewer', 'code': 'report_viewer', 'module': 'reporting',
     'role_type': 'officer', 'can_view': True, 'can_add': False, 'can_change': False,
     'can_delete': False, 'can_approve': False, 'can_post': False, 'is_default': False},
    # Audit
    {'name': 'Internal Auditor', 'code': 'internal_auditor', 'module': 'audit',
     'role_type': 'manager', 'can_view': True, 'can_add': True, 'can_change': False,
     'can_delete': False, 'can_approve': True, 'can_post': False, 'is_default': False},
    # Admin
    {
        'name': 'System Admin',
        'code': 'admin_manager',
        'module': 'admin',
        'role_type': 'manager',
        'can_view': True,
        'can_add': True,
        'can_change': True,
        'can_delete': True,
        'can_approve': True,
        'can_post': False,
        'is_default': True,
    },
]


class Command(BaseCommand):
    help = 'Seed default roles with module-based permissions for tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant',
            type=str,
            help='Schema name of specific tenant to seed roles for',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Seed roles for all tenants',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )

    def handle(self, *args, **options):
        tenant_schema = options.get('tenant')
        seed_all = options.get('all')
        dry_run = options.get('dry_run')

        if not tenant_schema and not seed_all:
            self.stdout.write(
                self.style.ERROR('Please specify --tenant=schema_name or --all')
            )
            return

        if seed_all:
            tenants = Client.objects.exclude(schema_name='public')
            self.stdout.write(f'Found {tenants.count()} tenants to process')
        else:
            tenant = Client.objects.filter(schema_name=tenant_schema).first()
            if not tenant:
                self.stdout.write(
                    self.style.ERROR(f'Tenant with schema "{tenant_schema}" not found')
                )
                return
            tenants = [tenant]

        total_roles = 0
        total_groups = 0

        for tenant in tenants:
            self.stdout.write(f'\nProcessing tenant: {tenant.name} ({tenant.schema_name})')
            
            roles_created, groups_created = self.seed_tenant_roles(
                tenant, dry_run
            )
            total_roles += roles_created
            total_groups += groups_created

        self.stdout.write(
            self.style.SUCCESS(
                f'\nCompleted: {total_roles} roles, {total_groups} permission groups created'
            )
        )

    def seed_tenant_roles(self, tenant, dry_run=False):
        """Seed roles into the tenant's own schema, then create auth Groups in public."""
        roles_created = 0
        groups_created = 0

        # Phase 1 — roles live in the tenant's own PostgreSQL schema
        seeded_roles = []
        with schema_context(tenant.schema_name):
            for role_data in DEFAULT_ROLES:
                role_code = role_data['code']
                existing_role = Role.objects.filter(code=role_code).first()

                if existing_role:
                    self.stdout.write(f'  - Role "{role_data["name"]}" already exists, skipping')
                    seeded_roles.append((role_code, existing_role.get_permissions()))
                else:
                    if dry_run:
                        self.stdout.write(f'  + Would create role: {role_data["name"]}')
                    else:
                        role = Role.objects.create(**role_data)
                        roles_created += 1
                        self.stdout.write(f'  + Created role: {role.name}')
                        seeded_roles.append((role_code, role.get_permissions()))

        if dry_run:
            return roles_created, groups_created

        # Phase 2 — Groups/Permissions are in the PUBLIC schema; no schema_context switch
        for role_code, perms in seeded_roles:
            group_name = f"{tenant.schema_name}_{role_code}"
            group, created = Group.objects.get_or_create(name=group_name)
            if not created:
                group.permissions.clear()
                self.stdout.write(f'    Updated group: {group_name}')
            else:
                self.stdout.write(f'    Created group: {group_name}')
                groups_created += 1

            assigned = 0
            for codename in perms:
                # A codename may exist for multiple content_types — add all
                matching = Permission.objects.filter(codename=codename)
                for perm in matching:
                    group.permissions.add(perm)
                    assigned += 1
            self.stdout.write(f'      Assigned {assigned} permissions to group')

        return roles_created, groups_created


def seed_tenant_default_roles(tenant):
    """
    Seed default roles into the tenant's own PostgreSQL schema.
    Called during tenant signup / manual seeding.

    Returns: tuple (roles_created, groups_created)

    Note: Role rows go into the tenant schema; Group/Permission rows stay in
    the public schema.  The two phases must NOT share the same schema_context.
    """
    roles_created = 0
    groups_created = 0
    seeded_roles = []  # [(role_code, [permission_codenames])]

    # Phase 1 — per-tenant schema: create Role rows
    with schema_context(tenant.schema_name):
        for role_data in DEFAULT_ROLES:
            role_code = role_data['code']
            existing_role = Role.objects.filter(code=role_code).first()
            if not existing_role:
                role = Role.objects.create(**role_data)
                roles_created += 1
                seeded_roles.append((role_code, role.get_permissions()))

    # Phase 2 — public schema: create Django Groups and assign Permissions
    for role_code, perms in seeded_roles:
        group_name = f"{tenant.schema_name}_{role_code}"
        group, group_created = Group.objects.get_or_create(name=group_name)
        if group_created:
            groups_created += 1
        for codename in perms:
            # A codename may exist for multiple content_types — add all
            for perm in Permission.objects.filter(codename=codename):
                group.permissions.add(perm)

    return roles_created, groups_created
