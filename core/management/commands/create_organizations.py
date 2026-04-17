"""
Bootstrap Organization records from existing AdministrativeSegments.

Creates:
1. One Organization per AdministrativeSegment where is_mda=True
2. Three oversight organizations (Budget Authority, Finance Authority,
   Audit Authority) linked to their matching AdminSegments if they exist.

Usage:
    python manage.py create_organizations
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Create Organization records from existing AdministrativeSegments'

    def handle(self, *args, **options):
        from core.models import Organization
        from accounting.models.ncoa import AdministrativeSegment

        self.stdout.write(self.style.NOTICE(
            f'\nBootstrapping organizations in schema: {connection.schema_name}\n'
        ))

        created = 0
        skipped = 0

        # ── 1. Create orgs from MDA-level AdminSegments ─────────
        mda_segments = AdministrativeSegment.objects.filter(
            is_mda=True, is_active=True,
        ).order_by('code')

        for seg in mda_segments:
            # Determine org_role: check name for oversight offices
            org_role = 'MDA'
            name_lower = seg.name.lower()
            if any(k in name_lower for k in ['budget', 'economic planning']):
                org_role = 'BUDGET_AUTHORITY'
            elif any(k in name_lower for k in ['accountant general']):
                org_role = 'FINANCE_AUTHORITY'
            elif any(k in name_lower for k in ['auditor general']):
                org_role = 'AUDIT_AUTHORITY'

            org, was_created = Organization.objects.get_or_create(
                code=seg.code,
                defaults={
                    'name': seg.name,
                    'short_name': seg.short_name or '',
                    'org_role': org_role,
                    'administrative_segment': seg,
                    'legacy_mda': seg.legacy_mda,
                    'is_active': True,
                    'description': seg.description or '',
                },
            )
            if was_created:
                created += 1
                label = f' [{org.get_org_role_display()}]' if org_role != 'MDA' else ''
                self.stdout.write(f'  + {seg.code}: {seg.name}{label}')
            else:
                skipped += 1

        # ── 2. Ensure oversight orgs exist even if no segment match ─
        OVERSIGHT_DEFAULTS = [
            {
                'code': 'BUDGET-AUTH',
                'name': 'Ministry of Budget & Economic Planning',
                'org_role': 'BUDGET_AUTHORITY',
            },
            {
                'code': 'FINANCE-AUTH',
                'name': "Accountant General's Office",
                'org_role': 'FINANCE_AUTHORITY',
            },
            {
                'code': 'AUDIT-AUTH',
                'name': "Auditor General's Office",
                'org_role': 'AUDIT_AUTHORITY',
            },
        ]

        for defaults in OVERSIGHT_DEFAULTS:
            # Only create if no org with this role already exists
            existing = Organization.objects.filter(
                org_role=defaults['org_role'],
            ).first()
            if not existing:
                org, was_created = Organization.objects.get_or_create(
                    code=defaults['code'],
                    defaults={
                        'name': defaults['name'],
                        'org_role': defaults['org_role'],
                        'is_active': True,
                    },
                )
                if was_created:
                    created += 1
                    self.stdout.write(
                        f'  + {org.code}: {org.name} [{org.get_org_role_display()}]'
                    )

        self.stdout.write(self.style.SUCCESS(
            f'\nDone: {created} created, {skipped} skipped '
            f'(total: {Organization.objects.count()} organizations)\n'
        ))
