"""
Government Tenant Setup — Quot PSE
====================================
One-command setup for a new State Government or LGA tenant.
Creates the tenant, seeds NCoA data per-tier, populates LGA geographic
data, creates MDAs, and initializes TSA accounts.

Usage:
    # State Government tenant
    python manage.py setup_state_tenant \\
        --schema kwara_state \\
        --name "Kwara State Government" \\
        --domain kwara.quotpse.ng \\
        --state-code 18 \\
        --tier STATE

    # LGA tenant
    python manage.py setup_state_tenant \\
        --schema ilorin_west_lga \\
        --name "Ilorin West LGA" \\
        --domain ilorinwest.quotpse.ng \\
        --state-code 18 \\
        --tier LGA \\
        --lga-code 08
"""
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import connection

# NBS state code -> state name lookup
NBS_STATE_NAMES = {
    '01': 'Abia', '02': 'Adamawa', '03': 'Akwa Ibom', '04': 'Anambra',
    '05': 'Bauchi', '06': 'Bayelsa', '07': 'Benue', '08': 'Borno',
    '09': 'Cross River', '10': 'Delta', '11': 'Ebonyi', '12': 'Edo',
    '13': 'Enugu', '14': 'Jigawa', '15': 'Kogi', '16': 'Kaduna',
    '17': 'Kano', '18': 'Kwara', '19': 'Katsina', '20': 'Kebbi',
    '21': 'Ekiti', '22': 'Nasarawa', '23': 'Lagos', '24': 'Kogi',
    '25': 'Niger', '26': 'Ogun', '27': 'Imo', '28': 'Ondo',
    '29': 'Osun', '30': 'Oyo', '31': 'Sokoto', '32': 'Rivers',
    '33': 'Taraba', '34': 'Adamawa', '35': 'Yobe', '36': 'Zamfara',
    '37': 'FCT Abuja',
}


class Command(BaseCommand):
    help = 'Set up a new State Government or LGA tenant with full NCoA seed data'

    def add_arguments(self, parser):
        parser.add_argument('--schema', required=True,
                            help='PostgreSQL schema name (e.g. kwara_state)')
        parser.add_argument('--name', required=True,
                            help='Tenant display name (e.g. Kwara State Government)')
        parser.add_argument('--domain', required=True,
                            help='Tenant domain (e.g. kwara.quotpse.ng)')
        parser.add_argument('--state-code', required=True,
                            help='NBS 2-digit state code (e.g. 18 for Kwara)')
        parser.add_argument('--tier', required=True, choices=['STATE', 'LGA'],
                            help='Government tier: STATE or LGA')
        parser.add_argument('--lga-code', default='',
                            help='NBS LGA code within state (required for LGA tier)')
        parser.add_argument('--lga-name', default='',
                            help='LGA name (auto-detected if seed data exists)')
        parser.add_argument('--skip-seed', action='store_true',
                            help='Skip NCoA seed data')

    def handle(self, *args, **options):
        schema = options['schema']
        name = options['name']
        domain = options['domain']
        state_code = options['state_code']
        tier = options['tier']
        lga_code = options.get('lga_code', '')
        lga_name = options.get('lga_name', '')
        skip_seed = options['skip_seed']

        # Validate
        if tier == 'LGA' and not lga_code:
            raise CommandError('--lga-code is required for LGA tier tenants')

        state_name = NBS_STATE_NAMES.get(state_code, f'State {state_code}')
        tier_label = 'State Government' if tier == 'STATE' else 'Local Government Area'

        self.stdout.write(self.style.NOTICE(
            f'\n{"=" * 60}\n'
            f'  QUOT PSE - Government Tenant Setup\n'
            f'  Tenant: {name}\n'
            f'  Schema: {schema}\n'
            f'  Tier:   {tier_label}\n'
            f'  State:  {state_name} (NBS code: {state_code})\n'
            + (f'  LGA:    {lga_name or lga_code}\n' if tier == 'LGA' else '')
            + f'{"=" * 60}\n'
        ))

        # Step 1: Create tenant
        self.stdout.write('Step 1: Creating tenant...')
        tenant = self._create_tenant(schema, name, domain, tier, state_code,
                                     state_name, lga_code, lga_name)
        self.stdout.write(self.style.SUCCESS(f'  Tenant created: {tenant.schema_name}'))

        if skip_seed:
            self.stdout.write(self.style.WARNING('  Skipping seed data (--skip-seed)'))
            return

        # Step 2: Switch to tenant schema
        self.stdout.write('Step 2: Switching to tenant schema...')
        connection.set_tenant(tenant)
        self.stdout.write(self.style.SUCCESS(f'  Active schema: {connection.schema_name}'))

        # Step 3: Seed NCoA universal segments (same for all tiers)
        self.stdout.write('Step 3: Seeding NCoA Chart of Accounts...')
        call_command('seed_ncoa_economic')
        call_command('seed_ncoa', '--segment', 'functional')
        call_command('seed_ncoa', '--segment', 'fund')
        call_command('seed_ncoa', '--segment', 'programme')
        self.stdout.write(self.style.SUCCESS('  Universal NCoA segments seeded'))

        # Step 4: Seed geographic segments (tier-specific)
        self.stdout.write(f'Step 4: Seeding geographic segments for {state_name}...')
        call_command('seed_ncoa', '--segment', 'geo')
        # Seed LGA-level geographic data for this state
        try:
            call_command('seed_ncoa_lgas', '--state-code', state_code)
            self.stdout.write(self.style.SUCCESS(f'  LGAs seeded for {state_name}'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  LGA seeding skipped: {e}'))

        # If LGA tier, deactivate geographic codes outside this LGA
        if tier == 'LGA' and lga_code:
            self._filter_geo_for_lga(state_code, lga_code)

        # Step 5: Seed administrative segments (tier-specific MDAs)
        self.stdout.write(f'Step 5: Seeding {tier_label} MDA structure...')
        call_command('seed_ncoa', '--segment', 'administrative')
        call_command('seed_ncoa_state_mdas', '--tier', tier)
        self.stdout.write(self.style.SUCCESS(f'  {tier} MDAs seeded'))

        # Step 6: Seed procurement thresholds
        self.stdout.write('Step 6: Seeding BPP procurement thresholds...')
        call_command('seed_procurement_thresholds')

        # Step 7: Seed PAYE + pension
        self.stdout.write('Step 7: Seeding PAYE brackets + pension config...')
        call_command('seed_nigeria_payroll')

        # Step 8: Seed revenue heads
        self.stdout.write('Step 8: Seeding revenue heads...')
        call_command('seed_revenue_heads')

        # Step 9: Sync NCoA as Chart of Accounts (bridge EconomicSegment -> Account)
        self.stdout.write('Step 9: Syncing NCoA as Chart of Accounts...')
        call_command('seed_ncoa_as_coa')

        # Step 10: Sync NCoA as Dimensions (bridge Fund/Function/Program/Geo/MDA)
        self.stdout.write('Step 10: Syncing NCoA as Dimensions...')
        call_command('seed_ncoa_as_dimensions')

        # Step 11: Create initial TSA structure
        self.stdout.write('Step 11: Creating initial TSA account structure...')
        self._create_tsa_structure(name)

        # Step 12: Create initial fiscal year
        self.stdout.write('Step 12: Creating fiscal year...')
        self._create_fiscal_year()

        # Step 13: Enable government modules (sidebar visibility)
        self.stdout.write('Step 13: Enabling government modules...')
        self._enable_government_modules()

        # Step 14: Bootstrap organizations from MDAs
        self.stdout.write('Step 14: Creating organizations from MDAs...')
        call_command('create_organizations')

        # Summary
        self._print_summary(tier, state_name)

    def _create_tenant(self, schema, name, domain, tier, state_code,
                       state_name, lga_code, lga_name):
        from tenants.models import Client, Domain

        existing = Client.objects.filter(schema_name=schema).first()
        if existing:
            tenant = existing
            self.stdout.write(self.style.WARNING(f'  Tenant {schema} already exists, reusing'))
        else:
            tenant = Client(schema_name=schema, name=name)
            tenant.save()

        # Update government configuration
        tenant.government_tier = tier
        tenant.state_nbs_code = state_code
        tenant.state_name = state_name
        tenant.lga_code = lga_code
        tenant.lga_name = lga_name
        tenant.business_category = 'government'
        tenant.save(update_fields=[
            'government_tier', 'state_nbs_code', 'state_name',
            'lga_code', 'lga_name', 'business_category',
        ])

        Domain.objects.get_or_create(
            domain=domain,
            defaults={'tenant': tenant, 'is_primary': True},
        )
        return tenant

    def _filter_geo_for_lga(self, state_code, lga_code):
        """For LGA tier: deactivate geographic codes not belonging to this LGA."""
        from accounting.models.ncoa import GeographicSegment

        # Keep: zone-level, state-level, and this specific LGA
        # Deactivate: other LGAs in the same state
        other_lgas = GeographicSegment.objects.filter(
            state_code=state_code,
            lga_code__gt='00',  # Exclude state-level (lga_code='00')
        ).exclude(lga_code=lga_code)
        deactivated = other_lgas.update(is_active=False)
        if deactivated:
            self.stdout.write(f'  Deactivated {deactivated} geographic codes outside LGA {lga_code}')

    def _create_tsa_structure(self, tenant_name):
        from accounting.models.treasury import TreasuryAccount

        accounts = [
            {
                'account_number': 'TSA-MAIN-001',
                'account_name': f'{tenant_name} - Main TSA',
                'bank': 'Central Bank of Nigeria (CBN)',
                'account_type': 'MAIN_TSA',
            },
            {
                'account_number': 'TSA-CRF-001',
                'account_name': f'{tenant_name} - Consolidated Revenue Fund',
                'bank': 'CBN',
                'account_type': 'CONSOLIDATED',
            },
            {
                'account_number': 'TSA-REV-001',
                'account_name': f'{tenant_name} - Revenue Collection Account',
                'bank': 'Designated Collection Bank',
                'account_type': 'REVENUE',
            },
        ]

        main_tsa = None
        for acct_data in accounts:
            obj, created = TreasuryAccount.objects.get_or_create(
                account_number=acct_data['account_number'],
                defaults=acct_data,
            )
            if acct_data['account_type'] == 'MAIN_TSA':
                main_tsa = obj
            elif main_tsa and created:
                obj.parent_account = main_tsa
                obj.save(update_fields=['parent_account'])

            status = 'created' if created else 'exists'
            self.stdout.write(f'  TSA {acct_data["account_type"]}: {status}')

    def _create_fiscal_year(self):
        from accounting.models.advanced import FiscalYear, FiscalPeriod
        from accounting.models.balances import BudgetPeriod
        import datetime
        from calendar import monthrange

        year = datetime.date.today().year
        fy, created = FiscalYear.objects.get_or_create(
            year=year,
            defaults={
                'start_date': datetime.date(year, 1, 1),
                'end_date': datetime.date(year, 12, 31),
                'is_active': True,
                'name': f'FY{year}',
                'period_type': 'Monthly',
                'status': 'Open',
            },
        )
        status = 'created' if created else 'exists'
        self.stdout.write(f'  Fiscal Year {year}: {status}')

        # Auto-generate monthly FiscalPeriods + BudgetPeriods
        for month in range(1, 13):
            _, last_day = monthrange(year, month)
            start = datetime.date(year, month, 1)
            end = datetime.date(year, month, last_day)

            FiscalPeriod.objects.get_or_create(
                fiscal_year=year, period_number=month, period_type='Monthly',
                defaults={'start_date': start, 'end_date': end, 'status': 'Open'},
            )
            BudgetPeriod.objects.get_or_create(
                fiscal_year=year, period_number=month, period_type='MONTHLY',
                defaults={
                    'start_date': start, 'end_date': end,
                    'status': 'OPEN', 'allow_postings': True, 'allow_adjustments': True,
                },
            )

        self.stdout.write(f'  Fiscal/Budget periods: {FiscalPeriod.objects.filter(fiscal_year=year).count()} fiscal, {BudgetPeriod.objects.filter(fiscal_year=year).count()} budget')

    def _enable_government_modules(self):
        """Seed core.TenantModule records so the sidebar shows all government modules."""
        from core.models import TenantModule

        modules = [
            ('dimensions', 'NCoA Dimensions', 'NCoA 6-segment classification'),
            ('accounting', 'General Ledger', 'Chart of Accounts, Journals, AP/AR, Fixed Assets, IPSAS'),
            ('budget', 'Budget & Appropriation', 'Appropriations, Warrants, Budget Execution'),
            ('treasury', 'Treasury & TSA', 'Treasury Single Account, Payment Vouchers'),
            ('revenue', 'Revenue (IGR)', 'Revenue Heads, Revenue Collection, PAYE'),
            ('procurement', 'Procurement', 'Purchase Requisitions, POs, GRN, BPP Due Process'),
            ('inventory', 'Stores & Inventory', 'Government Stores, Stock Management'),
            ('hrm', 'Human Resources', 'Employees, Leave, Payroll, Pension'),
            ('workflow', 'Workflow & Approvals', 'Approval Templates, Multi-level Workflows'),
            ('reporting', 'Financial Reporting', 'IPSAS Statements, Budget vs Actual'),
            ('audit', 'Audit & Compliance', 'Audit Trail, Transaction Logs'),
        ]

        created_count = 0
        for module_name, title, desc in modules:
            _, was_created = TenantModule.objects.get_or_create(
                module_name=module_name,
                defaults={
                    'module_title': title,
                    'description': desc,
                    'is_active': True,
                },
            )
            if was_created:
                created_count += 1

        self.stdout.write(f'  {created_count} modules enabled ({TenantModule.objects.count()} total)')

    def _print_summary(self, tier, state_name):
        from accounting.models.ncoa import (
            EconomicSegment, FunctionalSegment, FundSegment,
            GeographicSegment, AdministrativeSegment, ProgrammeSegment,
        )
        from accounting.models.treasury import TreasuryAccount
        from accounting.models.revenue import RevenueHead
        from procurement.models import ProcurementThreshold
        from hrm.models import NigeriaTaxBracket, PensionFundAdministrator
        from accounting.models.gl import Account, Fund, Function, Program, Geo, MDA

        self.stdout.write(self.style.SUCCESS(
            f'\n{"=" * 60}\n'
            f'  {tier} TENANT SETUP COMPLETE - {state_name}\n'
            f'{"=" * 60}\n'
            f'  NCoA Economic Segments:     {EconomicSegment.objects.count():>5}\n'
            f'  NCoA Functional (COFOG):    {FunctionalSegment.objects.count():>5}\n'
            f'  NCoA Fund Sources:          {FundSegment.objects.count():>5}\n'
            f'  NCoA Geographic:            {GeographicSegment.objects.filter(is_active=True).count():>5}\n'
            f'  NCoA Administrative (MDA):  {AdministrativeSegment.objects.filter(is_mda=True).count():>5}\n'
            f'  NCoA Programme:             {ProgrammeSegment.objects.count():>5}\n'
            f'  Legacy GL Accounts:         {Account.objects.count():>5}\n'
            f'  Legacy Funds:               {Fund.objects.count():>5}\n'
            f'  Legacy Functions:           {Function.objects.count():>5}\n'
            f'  Legacy Programs:            {Program.objects.count():>5}\n'
            f'  Legacy Geos:                {Geo.objects.count():>5}\n'
            f'  Legacy MDAs:                {MDA.objects.count():>5}\n'
            f'  Revenue Heads:              {RevenueHead.objects.count():>5}\n'
            f'  BPP Thresholds:             {ProcurementThreshold.objects.count():>5}\n'
            f'  PAYE Tax Brackets:          {NigeriaTaxBracket.objects.filter(is_current=True).count():>5}\n'
            f'  Pension Fund Admins:        {PensionFundAdministrator.objects.count():>5}\n'
            f'  TSA Accounts:               {TreasuryAccount.objects.count():>5}\n'
            f'{"=" * 60}\n'
            f'  Ready to receive users and process transactions.\n'
        ))
