"""
Seed Nigeria National Chart of Accounts (NCoA)
==============================================
Seeds all 6 NCoA segments with standard Nigerian government classification codes.

Usage:
    python manage.py seed_ncoa                    # Seeds all segments
    python manage.py seed_ncoa --segment economic # Seeds only economic segment
    python manage.py seed_ncoa --segment geo      # Seeds geographic segment
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from accounting.models.ncoa import (
    AdministrativeSegment, FunctionalSegment,
    ProgrammeSegment, FundSegment, GeographicSegment,
)


class Command(BaseCommand):
    help = 'Seeds the Nigeria National Chart of Accounts (NCoA) segments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--segment', type=str, default='all',
            choices=['all', 'economic', 'functional', 'fund', 'geo', 'administrative', 'programme'],
            help='Which segment to seed (default: all)',
        )

    def handle(self, *args, **options):
        segment = options['segment']

        if segment in ('all', 'economic'):
            # Delegate to the canonical seed_ncoa_economic command
            from django.core.management import call_command
            call_command('seed_ncoa_economic')
        if segment in ('all', 'functional'):
            self._seed_functional()
        if segment in ('all', 'fund'):
            self._seed_fund()
        if segment in ('all', 'geo'):
            self._seed_geographic()
        if segment in ('all', 'administrative'):
            self._seed_administrative()
        if segment in ('all', 'programme'):
            self._seed_programme()

        self.stdout.write(self.style.SUCCESS('NCoA seeding complete.'))

    # _seed_economic() is delegated to the ``seed_ncoa_economic``
    # command, which seeds the economic codes straight into the chart of
    # accounts — the economic segment and the CoA are one classifier.


    @transaction.atomic
    def _seed_functional(self):
        """Seeds the 10 COFOG divisions with key groups."""
        self.stdout.write('Seeding NCoA Functional Segment (COFOG)...')

        def fs(code, name, div, group='0', cls='0', parent_code=None):
            parent = None
            if parent_code:
                parent = FunctionalSegment.objects.filter(code=parent_code).first()
            obj, _ = FunctionalSegment.objects.update_or_create(
                code=code,
                defaults={
                    'name': name, 'division_code': div,
                    'group_code': group, 'class_code': cls,
                    'parent': parent, 'is_active': True,
                },
            )
            return obj

        # COFOG Divisions
        fs('70100', 'General Public Services', '701')
        fs('70110', 'Executive and Legislature', '701', '1', '0', '70100')
        fs('70120', 'Financial and Fiscal Affairs', '701', '2', '0', '70100')
        fs('70130', 'General Services', '701', '3', '0', '70100')
        fs('70140', 'Basic Research', '701', '4', '0', '70100')
        fs('70150', 'Public Debt Transactions', '701', '5', '0', '70100')
        fs('70160', 'Transfers of a General Character', '701', '6', '0', '70100')

        fs('70200', 'Defence', '702')
        fs('70210', 'Military Defence', '702', '1', '0', '70200')
        fs('70220', 'Civil Defence', '702', '2', '0', '70200')

        fs('70300', 'Public Order and Safety', '703')
        fs('70310', 'Police Services', '703', '1', '0', '70300')
        fs('70320', 'Fire Protection', '703', '2', '0', '70300')
        fs('70330', 'Law Courts', '703', '3', '0', '70300')
        fs('70340', 'Prisons', '703', '4', '0', '70300')

        fs('70400', 'Economic Affairs', '704')
        fs('70410', 'General Economic Affairs', '704', '1', '0', '70400')
        fs('70420', 'Agriculture, Forestry, Fishing', '704', '2', '0', '70400')
        fs('70430', 'Fuel and Energy', '704', '3', '0', '70400')
        fs('70440', 'Mining and Manufacturing', '704', '4', '0', '70400')
        fs('70450', 'Transport', '704', '5', '0', '70400')
        fs('70460', 'Communication', '704', '6', '0', '70400')
        fs('70470', 'Trade and Commerce', '704', '7', '0', '70400')

        fs('70500', 'Environmental Protection', '705')
        fs('70510', 'Waste Management', '705', '1', '0', '70500')
        fs('70520', 'Pollution Abatement', '705', '2', '0', '70500')

        fs('70600', 'Housing and Community Amenities', '706')
        fs('70610', 'Housing Development', '706', '1', '0', '70600')
        fs('70620', 'Community Development', '706', '2', '0', '70600')
        fs('70630', 'Water Supply', '706', '3', '0', '70600')

        fs('70700', 'Health', '707')
        fs('70710', 'Medical Services', '707', '1', '0', '70700')
        fs('70720', 'Public Health Services', '707', '2', '0', '70700')
        fs('70730', 'Hospital Services', '707', '3', '0', '70700')

        fs('70800', 'Recreation, Culture and Religion', '708')
        fs('70810', 'Recreation and Sports', '708', '1', '0', '70800')
        fs('70820', 'Cultural Services', '708', '2', '0', '70800')
        fs('70830', 'Religious Affairs', '708', '3', '0', '70800')

        fs('70900', 'Education', '709')
        fs('70910', 'Pre-Primary and Primary Education', '709', '1', '0', '70900')
        fs('70920', 'Secondary Education', '709', '2', '0', '70900')
        fs('70930', 'Tertiary Education', '709', '3', '0', '70900')
        fs('70940', 'Education Not Elsewhere Classified', '709', '4', '0', '70900')

        fs('71000', 'Social Protection', '710')
        fs('71010', 'Sickness and Disability', '710', '1', '0', '71000')
        fs('71020', 'Old Age', '710', '2', '0', '71000')
        fs('71030', 'Family and Children', '710', '3', '0', '71000')
        fs('71040', 'Social Exclusion', '710', '4', '0', '71000')

        self.stdout.write(self.style.SUCCESS(f'  Functional segment: {FunctionalSegment.objects.count()} codes'))

    @transaction.atomic
    def _seed_fund(self):
        """Seeds standard fund sources."""
        self.stdout.write('Seeding NCoA Fund Segment...')

        def fund(code, name, main, sub='0', source='00', restricted=False, parent_code=None):
            parent = None
            if parent_code:
                parent = FundSegment.objects.filter(code=parent_code).first()
            FundSegment.objects.update_or_create(
                code=code,
                defaults={
                    'name': name, 'main_fund_code': main,
                    'sub_fund_code': sub, 'fund_source_code': source,
                    'is_restricted': restricted, 'parent': parent, 'is_active': True,
                },
            )

        fund('01000', 'Federation Account', '01')
        fund('01100', 'FAAC - Statutory Allocation', '01', '1', '00', False, '01000')
        fund('01200', 'FAAC - VAT Allocation', '01', '2', '00', False, '01000')
        fund('01300', 'FAAC - Excess Crude / Augmentation', '01', '3', '00', False, '01000')

        fund('02000', 'Capital Development Fund', '02')
        fund('03000', 'Contingency Fund', '03')
        fund('04000', 'Education Tax / UBEC Fund', '04', parent_code=None)
        fund('05000', 'Donor / Grant Funds', '05')
        fund('05100', 'World Bank', '05', '1', '00', True, '05000')
        fund('05200', 'AfDB', '05', '2', '00', True, '05000')
        fund('05300', 'EU / Other Donors', '05', '3', '00', True, '05000')

        fund('06000', 'Domestic Loans', '06')
        fund('06100', 'Commercial Bank Loans', '06', '1', '00', True, '06000')
        fund('06200', 'Bond Proceeds', '06', '2', '00', True, '06000')

        fund('07000', 'Foreign Loans', '07')
        fund('08000', 'Internally Generated Revenue (IGR)', '08')
        fund('09000', 'Other Receipts', '09')

        self.stdout.write(self.style.SUCCESS(f'  Fund segment: {FundSegment.objects.count()} codes'))

    @transaction.atomic
    def _seed_geographic(self):
        """Seeds Nigeria 6 geo-political zones, 36 states + FCT."""
        self.stdout.write('Seeding NCoA Geographic Segment...')

        STATES = {
            # Zone 1: North-Central
            '1': [
                ('07', 'Benue'), ('15', 'Kogi'), ('18', 'Kwara'),
                ('22', 'Nasarawa'), ('25', 'Niger'), ('29', 'Plateau'),
                ('37', 'FCT Abuja'),
            ],
            # Zone 2: North-East
            '2': [
                ('02', 'Adamawa'), ('05', 'Bauchi'), ('08', 'Borno'),
                ('11', 'Gombe'), ('33', 'Taraba'), ('35', 'Yobe'),
            ],
            # Zone 3: North-West
            '3': [
                ('14', 'Jigawa'), ('16', 'Kaduna'), ('17', 'Kano'),
                ('19', 'Katsina'), ('20', 'Kebbi'), ('31', 'Sokoto'),
                ('36', 'Zamfara'),
            ],
            # Zone 4: South-East
            '4': [
                ('01', 'Abia'), ('04', 'Anambra'), ('11', 'Ebonyi'),
                ('13', 'Enugu'), ('27', 'Imo'),
            ],
            # Zone 5: South-South
            '5': [
                ('03', 'Akwa Ibom'), ('06', 'Bayelsa'), ('09', 'Cross River'),
                ('10', 'Delta'), ('12', 'Edo'),
                ('32', 'Rivers'),
            ],
            # Zone 6: South-West
            '6': [
                ('06', 'Ekiti'), ('23', 'Lagos'), ('26', 'Ogun'),
                ('28', 'Ondo'), ('29', 'Osun'), ('30', 'Oyo'),
            ],
        }

        zone_names = {
            '1': 'North-Central', '2': 'North-East', '3': 'North-West',
            '4': 'South-East', '5': 'South-South', '6': 'South-West',
        }

        for zone_code, zone_name in zone_names.items():
            zone, _ = GeographicSegment.objects.update_or_create(
                code=f'{zone_code}0000000',
                defaults={
                    'name': zone_name, 'zone_code': zone_code,
                    'state_code': '00', 'is_active': True,
                },
            )
            for state_code, state_name in STATES.get(zone_code, []):
                GeographicSegment.objects.update_or_create(
                    code=f'{zone_code}{state_code}00000',
                    defaults={
                        'name': state_name, 'zone_code': zone_code,
                        'state_code': state_code, 'parent': zone,
                        'is_active': True,
                    },
                )

        self.stdout.write(self.style.SUCCESS(f'  Geographic segment: {GeographicSegment.objects.count()} codes'))

    @transaction.atomic
    def _seed_administrative(self):
        """Seeds template administrative segment (5 sectors)."""
        self.stdout.write('Seeding NCoA Administrative Segment (template)...')

        sectors = [
            ('01', 'Administrative Sector'),
            ('02', 'Economic Sector'),
            ('03', 'Law and Justice Sector'),
            ('04', 'Regional Sector'),
            ('05', 'Social Sector'),
        ]

        for code, name in sectors:
            AdministrativeSegment.objects.update_or_create(
                code=f'{code}0000000000',
                defaults={
                    'name': name, 'level': 'SECTOR',
                    'sector_code': code, 'is_active': True,
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f'  Administrative segment: {AdministrativeSegment.objects.count()} codes'
            '\n  Note: Each state tenant should customize their MDA structure.'
        ))

    @transaction.atomic
    def _seed_programme(self):
        """Seeds template programme segment structure."""
        self.stdout.write('Seeding NCoA Programme Segment (template)...')

        programmes = [
            ('01010000000000', 'General Administration', '01', '01', False),
            ('02010000000000', 'Economic Development', '02', '01', False),
            ('03010000000000', 'Infrastructure', '03', '01', True),
            ('04010000000000', 'Social Services', '04', '01', False),
            ('05010000000000', 'Environmental Management', '05', '01', False),
        ]

        for code, name, policy, prog, is_cap in programmes:
            ProgrammeSegment.objects.update_or_create(
                code=code,
                defaults={
                    'name': name, 'policy_code': policy,
                    'programme_code': prog, 'is_capital': is_cap,
                    'is_active': True,
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f'  Programme segment: {ProgrammeSegment.objects.count()} codes'
            '\n  Note: Each MDA should define specific programmes/projects.'
        ))
