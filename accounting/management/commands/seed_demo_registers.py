"""
Seed the remaining registers so every report has data.

Builds on ``seed_demo_gl`` (which seeded the GL) by populating the
transactional registers that IPSAS dimensional reports read from:

  * TreasuryAccount      — for TSA Cash Position.
  * RevenueCollection    — for Revenue Performance (by head + by month).
  * Appropriation        — for Budget-vs-Actual, Commitment, Execution.
  * GLBalance dimensions — for Functional / Programme / Geographic.

Usage
-----
    python manage.py tenant_command seed_demo_registers --schema=<name>
    python manage.py tenant_command seed_demo_registers --schema=<name> --year=2026
    python manage.py tenant_command seed_demo_registers --schema=<name> --clear

Each register is seeded *idempotently* — a stable natural key prevents
duplicates on re-run. Pass ``--clear`` to wipe demo rows first.
"""
from __future__ import annotations

import random
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F


_TAG = 'DEMO-REG-'


class Command(BaseCommand):
    help = 'Seed demo TSA balances, revenue collections, appropriations, and GL dimensions.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year', type=int, default=None,
            help='Fiscal year to seed (defaults to current year).',
        )
        parser.add_argument(
            '--clear', action='store_true',
            help='Delete all DEMO-REG-* rows before re-seeding.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would happen without writing.',
        )

    def handle(self, *args, **options):
        year: int = options['year'] or date.today().year
        clear: bool = options['clear']
        dry: bool = options['dry_run']

        self.stdout.write(self.style.NOTICE(
            f'Seeding demo registers for FY {year} '
            f'(clear={clear}, dry_run={dry})'
        ))

        if clear and not dry:
            self._clear(year)

        self._seed_tsa_balances(year, dry)
        self._seed_revenue_collections(year, dry)
        self._seed_appropriations(year, dry)
        self._attach_dimensions_to_journals(year, dry)

        self.stdout.write(self.style.SUCCESS(
            f'Register seed complete for FY {year}'
            f'{" (dry-run)" if dry else ""}.'
        ))

    # -----------------------------------------------------------------
    # Clear prior demo data
    # -----------------------------------------------------------------
    def _clear(self, year: int) -> None:
        from accounting.models import TreasuryAccount, RevenueCollection
        from budget.models import Appropriation

        ta = TreasuryAccount.objects.filter(
            account_number__startswith=_TAG,
        )
        rc = RevenueCollection.objects.filter(
            receipt_number__startswith=_TAG,
        )
        # Appropriations: filter by fiscal_year.year + presence of DEMO-REG
        # marker in description.
        ap = Appropriation.objects.filter(
            fiscal_year__year=year,
            variance_explanation__startswith=_TAG,
        )
        ta_n, rc_n, ap_n = ta.count(), rc.count(), ap.count()
        # Order matters — RevenueCollection PROTECT-references TSA, so
        # revenue collections must go first. Appropriations are
        # free-standing.
        rc.delete()
        ta.delete()
        ap.delete()
        self.stdout.write(self.style.WARNING(
            f'  Cleared: {ta_n} TSA, {rc_n} RevCollection, {ap_n} Appropriation.'
        ))

    # -----------------------------------------------------------------
    # 1. TSA balances
    # -----------------------------------------------------------------
    def _seed_tsa_balances(self, year: int, dry: bool) -> None:
        from accounting.models import TreasuryAccount

        specs = [
            ('MAIN_TSA',      'Main TSA Account — CBN',              Decimal('12500000000')),
            ('CONSOLIDATED',  'Consolidated Revenue Fund',           Decimal('3250000000')),
            ('REVENUE',       'IGR Collection Account',              Decimal('820000000')),
            ('SUB_ACCOUNT',   'Ministry of Education — Sub-Account', Decimal('250000000')),
            ('SUB_ACCOUNT',   'Ministry of Health — Sub-Account',    Decimal('385000000')),
            ('SUB_ACCOUNT',   'Ministry of Works — Sub-Account',     Decimal('540000000')),
            ('HOLDING',       'Pension Contributions Holding',       Decimal('95000000')),
        ]

        count = 0
        for idx, (acct_type, name, balance) in enumerate(specs, start=1):
            account_number = f'{_TAG}TSA-{idx:03d}'
            if dry:
                count += 1
                continue
            obj, created = TreasuryAccount.objects.update_or_create(
                account_number=account_number,
                defaults={
                    'account_name':    name,
                    'bank':            'CBN',
                    'account_type':    acct_type,
                    'is_active':       True,
                    'current_balance': balance,
                    'description':     f'Demo seed for FY {year}',
                },
            )
            if created:
                count += 1
        self.stdout.write(f'  TSA accounts: {count} created/updated.')

    # -----------------------------------------------------------------
    # 2. Revenue collections
    # -----------------------------------------------------------------
    def _seed_revenue_collections(self, year: int, dry: bool) -> None:
        from accounting.models import (
            RevenueHead, RevenueCollection, TreasuryAccount, NCoACode,
            AdministrativeSegment, FunctionalSegment,
            ProgrammeSegment, FundSegment, GeographicSegment,
        )

        heads = list(
            RevenueHead.objects
            .filter(is_active=True)
            .select_related('economic_segment')[:6]
        )
        if not heads:
            self.stdout.write(self.style.WARNING(
                '  No RevenueHead rows — skipping revenue collections. '
                'Run `seed_revenue_heads` first.'
            ))
            return

        tsa = (
            TreasuryAccount.objects
            .filter(account_type='REVENUE', is_active=True)
            .first()
            or TreasuryAccount.objects
            .filter(is_active=True)
            .first()
        )
        if tsa is None:
            self.stdout.write(self.style.WARNING(
                '  No TreasuryAccount — skipping revenue collections.'
            ))
            return

        # Default segments for the NCoACode lookup.
        admin_seg = AdministrativeSegment.objects.filter(is_active=True).first()
        func_seg = FunctionalSegment.objects.filter(is_active=True).first()
        prog_seg = ProgrammeSegment.objects.filter(is_active=True).first()
        fund_seg = FundSegment.objects.filter(is_active=True).first()
        geo_seg = GeographicSegment.objects.filter(is_active=True).first()
        if not all([admin_seg, func_seg, prog_seg, fund_seg, geo_seg]):
            self.stdout.write(self.style.WARNING(
                '  NCoA segments not fully seeded — skipping collections.'
            ))
            return

        rng = random.Random(f'{year}-rev')
        count = 0
        base_amounts = {
            'PAYE':         Decimal('8500000'),
            'ROAD_TAX':     Decimal('1200000'),
            'FEES_FINES':   Decimal('650000'),
            'STAMP_DUTY':   Decimal('980000'),
            'LICENSE':      Decimal('420000'),
            'OTHER':        Decimal('380000'),
            'FAAC':         Decimal('4800000'),
            'GRANT':        Decimal('2100000'),
        }

        for month in range(1, 13):
            for idx, head in enumerate(heads, start=1):
                receipt_number = f'{_TAG}REV-{year}-{month:02d}-{idx:02d}'
                if dry:
                    count += 1
                    continue

                # Build an NCoACode on demand for the (revenue_head.economic,
                # segments) tuple.
                ncoa_code, _ = NCoACode.objects.get_or_create(
                    administrative=admin_seg,
                    economic=head.economic_segment,
                    functional=func_seg,
                    programme=prog_seg,
                    fund=fund_seg,
                    geographic=geo_seg,
                    defaults={'is_active': True, 'description': 'Demo seed'},
                )

                base = base_amounts.get(head.revenue_type, Decimal('500000'))
                # ±20% jitter.
                factor = Decimal(str(1.0 + (rng.random() - 0.5) * 0.4))
                amount = (base * factor).quantize(Decimal('0.01'))

                _, created = RevenueCollection.objects.update_or_create(
                    receipt_number=receipt_number,
                    defaults={
                        'revenue_head':       head,
                        'ncoa_code':          ncoa_code,
                        'payer_name':         f'Demo Taxpayer {month:02d}-{idx:02d}',
                        'payer_tin':          f'T{year}{month:02d}{idx:04d}',
                        'amount':             amount,
                        'payment_reference':  f'{_TAG}PAY-{year}-{month:02d}-{idx:02d}',
                        'tsa_account':        tsa,
                        'collection_date':    _first_of_month(year, month),
                        'value_date':         _first_of_month(year, month),
                        'collection_channel': 'ONLINE',
                        'collecting_mda':     admin_seg,
                        'status':             'POSTED',
                        'period_month':       month,
                        'period_year':        year,
                        'description':        f'Demo revenue for {year}-{month:02d}',
                    },
                )
                if created:
                    count += 1
        self.stdout.write(f'  Revenue collections: {count} created.')

    # -----------------------------------------------------------------
    # 3. Appropriations (for Budget-vs-Actual / Execution / Commitment)
    # -----------------------------------------------------------------
    def _seed_appropriations(self, year: int, dry: bool) -> None:
        from accounting.models import (
            AdministrativeSegment, EconomicSegment, FunctionalSegment,
            ProgrammeSegment, FundSegment, GeographicSegment,
        )
        from accounting.models.advanced import FiscalYear
        from budget.models import Appropriation

        # Need a FiscalYear row.
        fy, _ = FiscalYear.objects.get_or_create(
            year=year,
            defaults={
                'name':       f'FY {year}',
                'start_date': date(year, 1, 1),
                'end_date':   date(year, 12, 31),
                'is_active':  True,
                'status':     'Open',
            },
        )

        admin_seg = AdministrativeSegment.objects.filter(is_active=True).first()
        func_seg  = FunctionalSegment.objects.filter(is_active=True).first()
        prog_seg  = ProgrammeSegment.objects.filter(is_active=True).first()
        if not all([admin_seg, func_seg, prog_seg]):
            self.stdout.write(self.style.WARNING(
                '  NCoA segments not seeded — skipping appropriations.'
            ))
            return

        # Pick up to 3 geographic segments so the Geographic Distribution
        # Performance Report shows multi-row dimensional budgets. Weights
        # are 50 / 30 / 20 — a realistic split for a state-capital + two
        # secondary LGAs. If fewer than 3 geo segments exist, remaining
        # budget collapses into the last one.
        geo_segs = list(
            GeographicSegment.objects
            .filter(is_active=True)
            .order_by('code')[:3]
        )
        if geo_segs:
            geo_weights = [Decimal('0.50'), Decimal('0.30'), Decimal('0.20')][:len(geo_segs)]
            total_w = sum(geo_weights, Decimal('0'))
            geo_weights = [w / total_w for w in geo_weights]
        else:
            geo_weights = []

        # Same split across up to 3 fund segments so Fund Performance
        # Report shows multi-fund dimensional budgets (Federation
        # Account, Capital Development Fund, IGR Fund typical mix).
        fund_segs = list(
            FundSegment.objects
            .filter(is_active=True)
            .order_by('code')[:3]
        )
        if not fund_segs:
            self.stdout.write(self.style.WARNING(
                '  NCoA fund segments not seeded — skipping appropriations.'
            ))
            return
        fund_weights = [Decimal('0.50'), Decimal('0.30'), Decimal('0.20')][:len(fund_segs)]
        total_fw = sum(fund_weights, Decimal('0'))
        fund_weights = [w / total_fw for w in fund_weights]

        # One appropriation per expense prefix (21/22/23/24/25) × geo.
        expense_prefixes = [
            ('21', Decimal('580000000')),   # Personnel
            ('22', Decimal('220000000')),   # Overhead
            ('23', Decimal('180000000')),   # CapEx
            ('24', Decimal('85000000')),    # Debt service
            ('25', Decimal('140000000')),   # Transfers
        ]
        count = 0
        for prefix, amount in expense_prefixes:
            econ_seg = (
                EconomicSegment.objects
                .filter(code__startswith=prefix, is_posting_level=True, is_active=True)
                .order_by('code')
                .first()
            )
            if econ_seg is None:
                continue

            # Cartesian split: every expense prefix × every fund × every
            # geo. With 3 funds and 3 geos this yields 9 appropriations
            # per prefix (5 prefixes × 9 = 45 per tenant).
            geo_iter = geo_segs if geo_segs else [None]
            geo_w_iter = geo_weights if geo_weights else [Decimal('1')]

            for fund_seg, fw in zip(fund_segs, fund_weights):
                for geo, gw in zip(geo_iter, geo_w_iter):
                    sliced = (amount * fw * gw).quantize(Decimal('0.01'))
                    if dry:
                        count += 1
                        continue
                    _, created = Appropriation.objects.update_or_create(
                        fiscal_year=fy,
                        administrative=admin_seg,
                        economic=econ_seg,
                        functional=func_seg,
                        programme=prog_seg,
                        fund=fund_seg,
                        geographic=geo,
                        defaults={
                            'amount_approved':      sliced,
                            'original_amount':      sliced,
                            'appropriation_type':   'ORIGINAL',
                            'status':               'ACTIVE',
                            'variance_explanation': f'{_TAG}demo seed',
                        },
                    )
                    if created:
                        count += 1
        self.stdout.write(f'  Appropriations: {count} created.')

    # -----------------------------------------------------------------
    # 4. Attach dimension FKs to DEMO-SEED journals + their GLBalance
    # -----------------------------------------------------------------
    def _attach_dimensions_to_journals(self, year: int, dry: bool) -> None:
        from accounting.models import (
            JournalHeader, GLBalance,
            Function, Program, Geo, Fund, MDA,
        )

        # Pick first active dimension rows. These are legacy FK models;
        # NCoA segments are separate.
        function = Function.objects.filter(is_active=True).first() if _has_is_active(Function) else Function.objects.first()
        program  = Program.objects.filter(is_active=True).first() if _has_is_active(Program) else Program.objects.first()
        geo      = Geo.objects.filter(is_active=True).first() if _has_is_active(Geo) else Geo.objects.first()
        fund     = Fund.objects.filter(is_active=True).first() if _has_is_active(Fund) else Fund.objects.first()
        mda      = MDA.objects.filter(is_active=True).first() if _has_is_active(MDA) else MDA.objects.first()

        dims = {
            'function': function, 'program': program, 'geo': geo,
            'fund': fund, 'mda': mda,
        }
        present = {k: v for k, v in dims.items() if v is not None}
        if not present:
            self.stdout.write(self.style.WARNING(
                '  No legacy dimension rows (Function/Program/Geo/Fund/MDA) '
                'present — skipping dimension attribution.'
            ))
            return

        qs = JournalHeader.objects.filter(
            reference_number__startswith='DEMO-SEED-',
            posting_date__year=year,
        )
        header_count = qs.count()
        if header_count == 0:
            self.stdout.write(
                '  No DEMO-SEED journals for this FY — run seed_demo_gl first.'
            )
            return

        if dry:
            self.stdout.write(
                f'  Would attach dimensions to {header_count} journals '
                f'({", ".join(present.keys())}).'
            )
            return

        with transaction.atomic():
            qs.update(**{k: v for k, v in present.items()})

            # Per-row dimension attribution on GLBalance, with merge-on-
            # conflict handling for unique_together (account, fund,
            # function, program, geo, mda, fiscal_year, period).
            gl_dims = {
                k: v for k, v in present.items()
                if k in ('function', 'program', 'geo', 'fund', 'mda')
            }
            merged = 0
            updated = 0
            for bal in GLBalance.objects.filter(
                fiscal_year=year,
                function__isnull=True,
                program__isnull=True,
                geo__isnull=True,
            ):
                # Find a row with the target dimensions already.
                existing = GLBalance.objects.filter(
                    account=bal.account,
                    fiscal_year=bal.fiscal_year,
                    period=bal.period,
                    **gl_dims,
                ).exclude(pk=bal.pk).first()

                if existing:
                    # Merge — add our balances into the existing dimensioned
                    # row and delete the null-dim one.
                    GLBalance.objects.filter(pk=existing.pk).update(
                        debit_balance=F('debit_balance') + bal.debit_balance,
                        credit_balance=F('credit_balance') + bal.credit_balance,
                    )
                    bal.delete()
                    merged += 1
                else:
                    # No conflict — safe to update in place.
                    for k, v in gl_dims.items():
                        setattr(bal, k, v)
                    bal.save(update_fields=list(gl_dims.keys()))
                    updated += 1

            self.stdout.write(
                f'  GLBalance: {updated} updated, {merged} merged with existing.'
            )

        dim_summary = ', '.join(
            f'{k}={getattr(v, "code", v.pk)}' for k, v in present.items()
        )
        self.stdout.write(
            f'  Attached dimensions to {header_count} journals ({dim_summary}).'
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_of_month(year: int, month: int) -> date:
    return date(year, month, 1)


def _has_is_active(model) -> bool:
    try:
        model._meta.get_field('is_active')
        return True
    except Exception:
        return False
