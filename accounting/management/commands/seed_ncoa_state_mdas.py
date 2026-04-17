"""
Seed State/LGA-Specific Administrative Segment (MDA) Structure
===============================================================
Seeds standard government organizational structure based on tier:
- STATE tier: Governor's Office, Ministries, Departments, Agencies (~25 MDAs)
- LGA tier: Chairman's Office, Departments (~10 MDAs)

Run:
    python manage.py seed_ncoa_state_mdas --tier STATE
    python manage.py seed_ncoa_state_mdas --tier LGA
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from accounting.models.ncoa import AdministrativeSegment


# ─── State Government MDA Template ──────────────────────────────────
# Format: (sector_code, org_code, name, mda_type)
STATE_MDAS = [
    # Sector 01: Administrative
    ('01', '01', 'Office of the Governor', 'MINISTRY'),
    ('01', '02', 'Office of the Deputy Governor', 'MINISTRY'),
    ('01', '03', 'Secretary to State Government', 'MINISTRY'),
    ('01', '04', 'Office of the Head of Service', 'DEPARTMENT'),
    ('01', '05', 'State House of Assembly', 'AGENCY'),
    ('01', '06', 'Ministry of Finance', 'MINISTRY'),
    ('01', '07', 'Ministry of Budget and Economic Planning', 'MINISTRY'),
    ('01', '08', 'Accountant General Office', 'DEPARTMENT'),
    ('01', '09', 'Auditor General Office', 'DEPARTMENT'),
    ('01', '10', 'Ministry of Local Government and Chieftaincy Affairs', 'MINISTRY'),
    ('01', '11', 'State Independent Electoral Commission (SIEC)', 'AGENCY'),
    ('01', '12', 'Bureau of Public Procurement', 'AGENCY'),
    ('01', '13', 'State Internal Revenue Service (SIRS)', 'AGENCY'),
    # Sector 02: Economic
    ('02', '01', 'Ministry of Agriculture and Rural Development', 'MINISTRY'),
    ('02', '02', 'Ministry of Commerce, Industry and Cooperatives', 'MINISTRY'),
    ('02', '03', 'Ministry of Works and Transport', 'MINISTRY'),
    ('02', '04', 'Ministry of Lands and Housing', 'MINISTRY'),
    ('02', '05', 'Ministry of Environment', 'MINISTRY'),
    ('02', '06', 'Ministry of Water Resources', 'MINISTRY'),
    ('02', '07', 'Ministry of Energy and Mineral Resources', 'MINISTRY'),
    # Sector 03: Law and Justice
    ('03', '01', 'Ministry of Justice', 'MINISTRY'),
    ('03', '02', 'Judiciary', 'AGENCY'),
    ('03', '03', 'Sharia Court of Appeal', 'AGENCY'),
    # Sector 04: Regional
    ('04', '01', 'Ministry of Information and Communications', 'MINISTRY'),
    # Sector 05: Social
    ('05', '01', 'Ministry of Education', 'MINISTRY'),
    ('05', '02', 'Ministry of Health', 'MINISTRY'),
    ('05', '03', 'Ministry of Women Affairs and Social Development', 'MINISTRY'),
    ('05', '04', 'Ministry of Youth and Sports Development', 'MINISTRY'),
    ('05', '05', 'Ministry of Culture and Tourism', 'MINISTRY'),
]

# ─── LGA MDA Template ───────────────────────────────────────────────
LGA_MDAS = [
    ('01', '01', 'Office of the LGA Chairman', 'UNIT'),
    ('01', '02', 'Office of the Vice Chairman', 'UNIT'),
    ('01', '03', 'LGA Legislative Council', 'UNIT'),
    ('01', '04', 'LGA Treasurer / Finance', 'DEPARTMENT'),
    ('01', '05', 'LGA Secretary', 'DEPARTMENT'),
    ('01', '06', 'Internal Audit', 'DEPARTMENT'),
    ('02', '01', 'Agriculture Department', 'DEPARTMENT'),
    ('02', '02', 'Works Department', 'DEPARTMENT'),
    ('05', '01', 'Education Department', 'DEPARTMENT'),
    ('05', '02', 'Primary Health Care', 'DEPARTMENT'),
    ('05', '03', 'Social Welfare', 'DEPARTMENT'),
    ('05', '04', 'Community Development', 'DEPARTMENT'),
]


class Command(BaseCommand):
    help = 'Seed standard government MDA structure for State or LGA tier'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tier', type=str, required=True, choices=['STATE', 'LGA'],
            help='Government tier: STATE or LGA',
        )
        parser.add_argument(
            '--clear', action='store_true',
            help='Clear existing MDA records before seeding (use with caution)',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        tier = options['tier']
        template = STATE_MDAS if tier == 'STATE' else LGA_MDAS
        tier_label = 'State Government' if tier == 'STATE' else 'Local Government Area'

        if options['clear']:
            # Only clear non-sector-level entries (keep the 5 sector headers)
            AdministrativeSegment.objects.filter(
                level__in=['ORGANIZATION', 'SUB_ORG', 'SUB_SUB_ORG', 'UNIT'],
            ).delete()
            self.stdout.write(self.style.WARNING('Cleared existing non-sector MDA records'))

        self.stdout.write(f'Seeding {tier_label} MDA structure ({len(template)} MDAs)...')

        created = updated = 0
        for sector_code, org_code, name, mda_type in template:
            code = f'{sector_code}{org_code}00000000'  # 12 digits: sector(2) + org(2) + zeros(8)

            # Find parent sector
            sector_code_full = f'{sector_code}0000000000'
            parent = AdministrativeSegment.objects.filter(
                code=sector_code_full, level='SECTOR',
            ).first()

            obj, was_created = AdministrativeSegment.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'level': 'ORGANIZATION',
                    'sector_code': sector_code,
                    'organization_code': org_code,
                    'parent': parent,
                    'is_active': True,
                    'is_mda': True,
                    'mda_type': mda_type,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'{tier_label} MDAs: {created} created, {updated} updated. '
            f'Total: {AdministrativeSegment.objects.filter(is_mda=True).count()} MDAs'
        ))
