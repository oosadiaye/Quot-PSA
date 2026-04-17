"""
Seed realistic demo GL transactions so every financial report shows
non-zero values out of the box.

Usage
-----
Run in a specific tenant schema:

    python manage.py tenant_command seed_demo_gl --schema=delta_state
    python manage.py tenant_command seed_demo_gl --schema=delta_state --year=2026
    python manage.py tenant_command seed_demo_gl --schema=delta_state --clear  # removes existing demo data first

Design
------
- **Idempotent by ``reference_number`` prefix**: every seeded journal is
  stamped ``DEMO-SEED-YYYY-MM-NN``. Re-running skips months already
  seeded; the ``--clear`` flag wipes prior seed data before inserting.
- **Every journal is balanced**: Σ debit = Σ credit.
- **All status='Posted'**: so Trial Balance, IPSAS statements, and
  Data-Quality dashboard see them.
- **GLBalance rows written**: the IPSAS reports read from GLBalance, so
  we update it alongside the raw JournalHeader/Line inserts.
- **Covers all NCoA groups**: revenue (11/12/13/14), expenses (21/22/
  23/24/25), assets (31/32), liabilities (41/42), net assets (43). If
  fewer accounts exist the seeder still works — it uses whatever active
  accounts it can find per account_type.
"""
from __future__ import annotations

import random
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone


_REF_PREFIX = 'DEMO-SEED-'


class Command(BaseCommand):
    help = 'Seed realistic balanced GL transactions for demo / testing.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year', type=int, default=None,
            help='Fiscal year to seed (defaults to current year).',
        )
        parser.add_argument(
            '--clear', action='store_true',
            help='Delete all DEMO-SEED-* journals (and their GLBalance '
                 'contributions) before re-seeding.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be seeded without writing anything.',
        )

    def handle(self, *args, **options):
        from accounting.models import (
            Account, JournalHeader, JournalLine, GLBalance,
        )

        year: int = options['year'] or date.today().year
        clear: bool = options['clear']
        dry_run: bool = options['dry_run']

        self.stdout.write(self.style.NOTICE(
            f'Seeding demo GL transactions for FY {year} '
            f'(clear={clear}, dry_run={dry_run})'
        ))

        # ── Resolve account buckets by NCoA role ────────────────────
        buckets = _resolve_account_buckets(Account)
        resolved = {k: v for k, v in buckets.items() if v is not None}
        missing = [k for k, v in buckets.items() if v is None]
        if not resolved:
            raise CommandError(
                'No active posting-level accounts found in any NCoA group. '
                'Run `seed_ncoa` or `seed_ncoa_as_coa` first.'
            )
        if missing:
            self.stdout.write(self.style.WARNING(
                f'Skipping recipes for unresolved NCoA groups: '
                f'{", ".join(missing)}'
            ))

        self.stdout.write('Resolved buckets:')
        for role, acc in resolved.items():
            self.stdout.write(f'  {role:<20} -> {acc.code} ({acc.name})')

        # ── Clear prior seed data if asked ──────────────────────────
        if clear:
            prior_qs = JournalHeader.objects.filter(
                reference_number__startswith=_REF_PREFIX,
                posting_date__year=year,
            )
            count = prior_qs.count()
            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f'[dry-run] would delete {count} prior DEMO-SEED headers '
                    f'for FY {year}.'
                ))
            else:
                with transaction.atomic():
                    # Also rewind the GLBalance contributions from these.
                    for h in prior_qs.prefetch_related('lines'):
                        for line in h.lines.all():
                            _adjust_balance(
                                GLBalance, line.account, h,
                                year, h.posting_date.month,
                                -(line.debit or Decimal('0')),
                                -(line.credit or Decimal('0')),
                            )
                    deleted, _ = prior_qs.delete()
                self.stdout.write(self.style.WARNING(
                    f'Cleared {deleted} prior seed headers.'
                ))

        # ── Seed month-by-month ─────────────────────────────────────
        total_headers = 0
        total_lines = 0
        rng = random.Random(f'{year}-demo-seed')

        existing_refs = set(
            JournalHeader.objects
            .filter(
                reference_number__startswith=_REF_PREFIX,
                posting_date__year=year,
            )
            .values_list('reference_number', flat=True)
        )

        recipes = _recipes(buckets)

        for month in range(1, 13):
            posting_date = _month_end(year, month)
            for idx, recipe in enumerate(recipes, start=1):
                ref = f'{_REF_PREFIX}{year}-{month:02d}-{idx:02d}'
                if ref in existing_refs:
                    continue

                amount = _scaled_amount(rng, recipe['base'])
                if dry_run:
                    total_headers += 1
                    total_lines += 2
                    continue

                with transaction.atomic():
                    header = JournalHeader.objects.create(
                        posting_date=posting_date,
                        description=recipe['description'],
                        reference_number=ref,
                        status='Posted',
                        posted_at=timezone.now(),
                        source_module='demo_seed',
                    )
                    debit_account = recipe['debit_account']
                    credit_account = recipe['credit_account']
                    JournalLine.objects.create(
                        header=header, account=debit_account,
                        debit=amount, credit=Decimal('0'),
                        memo=recipe['debit_memo'],
                    )
                    JournalLine.objects.create(
                        header=header, account=credit_account,
                        debit=Decimal('0'), credit=amount,
                        memo=recipe['credit_memo'],
                    )
                    _adjust_balance(
                        GLBalance, debit_account, header,
                        year, month, amount, Decimal('0'),
                    )
                    _adjust_balance(
                        GLBalance, credit_account, header,
                        year, month, Decimal('0'), amount,
                    )
                    total_headers += 1
                    total_lines += 2

        self.stdout.write(self.style.SUCCESS(
            f'Seed complete — {total_headers} headers, {total_lines} lines '
            f'for FY {year}.{" (dry-run, nothing written)" if dry_run else ""}'
        ))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_account_buckets(Account) -> dict[str, object | None]:
    """Resolve one representative Account per NCoA posting group.

    The IPSAS statement reports read balances via
    ``EconomicSegment.legacy_account_id`` — so we prefer Accounts that
    are the legacy_account for an active, posting-level
    EconomicSegment in the expected NCoA prefix. Falls back to a
    first-active-by-prefix search if NCoA isn't seeded.

    Returns a dict keyed by semantic role (not by account_type) so the
    recipes can pick distinct accounts for each transaction class.
    """
    from accounting.models.ncoa import EconomicSegment

    roles: dict[str, list[str]] = {
        # Revenue-side NCoA groups.
        'tax_revenue':     ['11'],
        'non_tax_revenue': ['12'],
        'grant_revenue':   ['13'],
        # Expense-side groups.
        'personnel':       ['21'],
        'goods_services':  ['22'],
        'capital_exp':     ['23'],
        'debt_service':    ['24'],
        'transfers':       ['25'],
        # Asset-side.
        'cash':            ['31'],
        'non_current_asset': ['32'],
        # Liability-side.
        'current_liab':    ['41'],
        'non_current_liab': ['42'],
    }

    out: dict[str, object | None] = {}
    for role, prefixes in roles.items():
        account = None
        # Prefer NCoA-bridged posting segments (so IPSAS reports see the
        # balance via the segment lookup).
        seg = (
            EconomicSegment.objects
            .filter(
                code__startswith=prefixes[0],
                is_posting_level=True,
                is_active=True,
                legacy_account__isnull=False,
                legacy_account__is_active=True,
            )
            .select_related('legacy_account')
            .order_by('code')
            .first()
        )
        if seg:
            account = seg.legacy_account
        else:
            # Fallback: any active account with the prefix.
            account = (
                Account.objects
                .filter(code__startswith=prefixes[0], is_active=True)
                .order_by('code')
                .first()
            )
        out[role] = account
    return out


def _recipes(b: dict[str, object]) -> list[dict]:
    """Balanced monthly journal templates targeted at NCoA prefix groups
    so every IPSAS report and dimensional statement shows non-zero
    numbers.

    Coverage (NCoA prefix → transaction class):
      * 11 Tax Revenue          DR cash      CR tax_revenue
      * 12 Non-Tax Revenue      DR cash      CR non_tax_revenue
      * 13 Grant Revenue        DR cash      CR grant_revenue
      * 21 Personnel            DR personnel CR cash
      * 22 Goods & Services     DR g&s       CR cash
      * 23 Capital Expenditure  DR capex     CR cash
      * 24 Debt Service         DR debt_svc  CR cash
      * 25 Transfers            DR transfers CR cash
      * 32/42 Asset + Liability DR non_current_asset CR non_current_liab (finance lease / loan-funded PPE)
      * 41 Current Liability    DR personnel CR current_liab (accrued salary)

    Each recipe's ``base`` is an NGN amount jittered ±15 % per month.
    Skips a recipe silently if either side's bucket is unresolved (NCoA
    not seeded for that group).
    """
    all_recipes = [
        {
            'description':    'Monthly PAYE / tax revenue collection',
            'base':           Decimal('4500000'),
            'debit_key':      'cash',
            'credit_key':     'tax_revenue',
            'debit_memo':     'Cash — tax collection',
            'credit_memo':    'Tax revenue recognised',
        },
        {
            'description':    'Monthly fees & fines collection',
            'base':           Decimal('1100000'),
            'debit_key':      'cash',
            'credit_key':     'non_tax_revenue',
            'debit_memo':     'Cash — fees/fines',
            'credit_memo':    'Non-tax revenue recognised',
        },
        {
            'description':    'FAAC statutory allocation receipt',
            'base':           Decimal('3200000'),
            'debit_key':      'cash',
            'credit_key':     'grant_revenue',
            'debit_memo':     'Cash — FAAC',
            'credit_memo':    'Grant revenue recognised',
        },
        {
            'description':    'Monthly personnel payroll disbursement',
            'base':           Decimal('2800000'),
            'debit_key':      'personnel',
            'credit_key':     'cash',
            'debit_memo':     'Personnel costs',
            'credit_memo':    'Cash — salary disbursement',
        },
        {
            'description':    'Goods & services overhead',
            'base':           Decimal('1200000'),
            'debit_key':      'goods_services',
            'credit_key':     'cash',
            'debit_memo':     'O&M / overhead',
            'credit_memo':    'Cash — vendor payment',
        },
        {
            'description':    'Capital expenditure acquisition',
            'base':           Decimal('850000'),
            'debit_key':      'capital_exp',
            'credit_key':     'cash',
            'debit_memo':     'Capital project spend',
            'credit_memo':    'Cash — capital disbursement',
        },
        {
            'description':    'Debt-service interest payment',
            'base':           Decimal('420000'),
            'debit_key':      'debt_service',
            'credit_key':     'cash',
            'debit_memo':     'Loan interest',
            'credit_memo':    'Cash — debt service',
        },
        {
            'description':    'Transfer / subvention to parastatal',
            'base':           Decimal('680000'),
            'debit_key':      'transfers',
            'credit_key':     'cash',
            'debit_memo':     'Subvention expense',
            'credit_memo':    'Cash — transfer',
        },
        {
            'description':    'Loan-funded infrastructure acquisition',
            'base':           Decimal('500000'),
            'debit_key':      'non_current_asset',
            'credit_key':     'non_current_liab',
            'debit_memo':     'PPE recognised',
            'credit_memo':    'Loan payable',
        },
        {
            'description':    'Accrued salary liability',
            'base':           Decimal('320000'),
            'debit_key':      'personnel',
            'credit_key':     'current_liab',
            'debit_memo':     'Personnel accrual',
            'credit_memo':    'Salary payable',
        },
    ]

    # Skip recipes whose buckets are missing (NCoA partially seeded).
    out: list[dict] = []
    for r in all_recipes:
        dr = b.get(r['debit_key'])
        cr = b.get(r['credit_key'])
        if dr is None or cr is None:
            continue
        out.append({
            'description':    r['description'],
            'base':           r['base'],
            'debit_account':  dr,
            'credit_account': cr,
            'debit_memo':     r['debit_memo'],
            'credit_memo':    r['credit_memo'],
        })
    return out


def _scaled_amount(rng: random.Random, base: Decimal) -> Decimal:
    """Jitter the amount ±15 % so reports look organic."""
    factor = Decimal(str(1.0 + (rng.random() - 0.5) * 0.3))
    return (base * factor).quantize(Decimal('0.01'))


def _month_end(year: int, month: int) -> date:
    from calendar import monthrange
    return date(year, month, monthrange(year, month)[1])


def _adjust_balance(GLBalance, account, header, year, month,
                    debit_delta: Decimal, credit_delta: Decimal) -> None:
    """Apply a delta to the GLBalance row for (account + dimensions
    + period), creating it if missing. Deltas may be negative (used by
    --clear rewind). Negative results are allowed — this mirrors how
    reversals are booked in live use."""
    from django.db.models import F

    bal, _ = GLBalance.objects.get_or_create(
        account=account,
        fund=header.fund, function=header.function,
        program=header.program, geo=header.geo,
        mda=header.mda,
        fiscal_year=year, period=month,
        defaults={'debit_balance': Decimal('0'), 'credit_balance': Decimal('0')},
    )
    GLBalance.objects.filter(pk=bal.pk).update(
        debit_balance=F('debit_balance') + debit_delta,
        credit_balance=F('credit_balance') + credit_delta,
    )
