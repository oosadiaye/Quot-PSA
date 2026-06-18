"""Tenant default seeder — loads ``tenants/seed_data/*.json`` into a tenant.

Why this service exists
-----------------------
Before this seeder, a freshly provisioned tenant could not post any
journal: ``_validate_fiscal_period`` rejected every posting with "No
period defined for date X" because ``FiscalYear`` / ``FiscalPeriod`` /
``BudgetPeriod`` were empty, ``get_vendor_ap_account`` failed because
no AP recon account existed, and PV mark-paid failed because no TSA
was configured. Admins had to seed all of this by hand on day 1 — a
class-A onboarding tax.

This service reads JSON files from ``tenants/seed_data/`` and upserts
them with stable keys, so:

* **Provisioning** can call ``TenantDefaultsSeeder.seed_all()`` after
  the schema migrate completes, and the tenant is immediately usable.
* **Backfill** runs the same logic via ``manage.py seed_tenant_defaults``
  for already-provisioned tenants that pre-date this feature.
* **Re-runs are no-ops** thanks to per-model ``get_or_create`` /
  ``update_or_create`` keyed on the model's natural identifier.

Why JSON, not Python literals
-----------------------------
The "nothing hardcoded" project rule: integrators who deploy this ERP
for a different state government can ship a tailored ``accounts.json``
or ``budget_check_rules.json`` without editing Python. The loader
reads the file fresh on every invocation; no rebuild or migration is
required to change the defaults.

Placeholder substitution
------------------------
Strings in the JSON support these tokens, resolved at load time so a
tenant provisioned in 2030 gets ``FY 2030`` automatically:

  ``{{current_fy_year}}``      → ``date.today().year``
  ``{{current_fy_start}}``     → ``YYYY-01-01``
  ``{{current_fy_end}}``       → ``YYYY-12-31``
  ``{{month_start:N}}``        → first day of month N (1-12)
  ``{{month_end:N}}``          → last day of month N (1-12)
  ``{{quarter_start:N}}``      → first day of quarter N (1-4)
  ``{{quarter_end:N}}``        → last day of quarter N (1-4)

Substitution only fires on string values; integers / booleans pass
through unchanged.
"""
from __future__ import annotations

import calendar
import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

from django.db import transaction
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)

# Single source of truth for where seed data lives. Keeping the path
# computed relative to this module's location means moving the package
# (e.g. into a subdirectory) doesn't break the loader.
SEED_DATA_DIR = Path(__file__).resolve().parent.parent / 'seed_data'


# ─────────────────────────────────────────────────────────────────────
# Placeholder substitution
# ─────────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r'\{\{\s*([a-z_]+)(?::(\d+))?\s*\}\}')


def _resolve_tokens(value: Any, year: int) -> Any:
    """Recursively resolve ``{{...}}`` placeholders inside JSON values.

    Strings get rewritten. Lists / dicts are walked. Other primitives
    pass through unchanged. A token that doesn't match a known name
    is left in place and logged at WARNING so a typo surfaces — the
    loader treats unresolved placeholders as a config bug, not silent
    fallback to literal text.
    """
    if isinstance(value, str):
        return _TOKEN_RE.sub(lambda m: _expand_token(m.group(1), m.group(2), year), value)
    if isinstance(value, list):
        return [_resolve_tokens(v, year) for v in value]
    if isinstance(value, dict):
        return {k: _resolve_tokens(v, year) for k, v in value.items()}
    return value


def _expand_token(name: str, arg: Optional[str], year: int) -> str:
    """Expand a single ``{{name:arg}}`` token to its string form."""
    if name == 'current_fy_year':
        return str(year)
    if name == 'current_fy_start':
        return f'{year}-01-01'
    if name == 'current_fy_end':
        return f'{year}-12-31'
    if name == 'month_start' and arg:
        return f'{year}-{int(arg):02d}-01'
    if name == 'month_end' and arg:
        m = int(arg)
        last = calendar.monthrange(year, m)[1]
        return f'{year}-{m:02d}-{last:02d}'
    if name == 'quarter_start' and arg:
        q = int(arg)
        start_month = (q - 1) * 3 + 1
        return f'{year}-{start_month:02d}-01'
    if name == 'quarter_end' and arg:
        q = int(arg)
        end_month = q * 3
        last = calendar.monthrange(year, end_month)[1]
        return f'{year}-{end_month:02d}-{last:02d}'
    logger.warning('Unknown seed-data placeholder: {{%s%s}}', name, f':{arg}' if arg else '')
    return f'{{{{{name}{":" + arg if arg else ""}}}}}'  # leave untouched


def _load_json(filename: str, year: int) -> Any:
    """Read a seed file and run placeholder substitution.

    Missing files return ``None`` so callers can skip cleanly — an
    operator who deletes ``budget_check_rules.json`` (e.g. because
    their state uses a different fiscal rules set) shouldn't break
    provisioning.
    """
    path = SEED_DATA_DIR / filename
    if not path.exists():
        logger.info('Seed file missing, skipping: %s', filename)
        return None
    with path.open(encoding='utf-8') as f:
        raw = json.load(f)
    return _resolve_tokens(raw, year)


# ─────────────────────────────────────────────────────────────────────
# Seeder
# ─────────────────────────────────────────────────────────────────────

@dataclass
class SeedReport:
    """Per-tenant tally so the management command and the provision
    task can both surface what happened."""
    fiscal_year_created:    int = 0
    fiscal_periods_created: int = 0
    budget_periods_created: int = 0
    accounts_created:       int = 0
    rules_created:          int = 0
    tsa_created:            int = 0
    skipped:                list[str] = None

    def __post_init__(self):
        if self.skipped is None:
            self.skipped = []

    def total(self) -> int:
        return (
            self.fiscal_year_created
            + self.fiscal_periods_created
            + self.budget_periods_created
            + self.accounts_created
            + self.rules_created
            + self.tsa_created
        )


class TenantDefaultsSeeder:
    """Idempotent loader for the minimum data a new tenant needs.

    Usage::

        from tenants.services.default_seeder import TenantDefaultsSeeder
        report = TenantDefaultsSeeder(schema_name='my_tenant').seed_all()

    Each ``seed_*`` method is wrapped in its own ``transaction.atomic``
    block so a partial failure in (say) BudgetCheckRule loading
    doesn't roll back the FiscalYear/Period setup that's already
    landed. The trade-off: a tenant could end up with FY + Periods +
    Accounts but no Rules. That's a strictly better failure mode
    than rolling everything back — the missing piece can be added
    by re-running the seeder (idempotent), and the partial seed is
    still enough for journal posting to work.
    """

    def __init__(self, schema_name: str, *, year: Optional[int] = None):
        self.schema_name = schema_name
        # Use today's calendar year as the default FY anchor. Caller
        # can override for tests or for tenants on a non-calendar FY.
        self.year = year or date.today().year

    # ── public entry points ──────────────────────────────────────────

    def seed_all(self) -> SeedReport:
        """Run every ``seed_*`` step. Each step skips cleanly if its
        rows already exist, so this is safe to call repeatedly.
        """
        report = SeedReport()
        with schema_context(self.schema_name):
            self._seed_fiscal_year(report)
            self._seed_fiscal_periods(report)
            self._seed_budget_periods(report)
            self._seed_accounts(report)
            self._seed_budget_check_rules(report)
            self._seed_treasury_account(report)
        logger.info(
            'TenantDefaultsSeeder: schema=%s created=%d skipped=%s',
            self.schema_name, report.total(), report.skipped,
        )
        return report

    # ── individual seeders ───────────────────────────────────────────

    def _seed_fiscal_year(self, report: SeedReport) -> None:
        data = _load_json('fiscal_year.json', self.year)
        if data is None:
            report.skipped.append('fiscal_year')
            return
        from accounting.models.advanced import FiscalYear
        try:
            with transaction.atomic():
                year_value = int(data['year'])
                _, created = FiscalYear.objects.get_or_create(
                    year=year_value,
                    defaults={
                        'name':        data.get('name', f'FY {year_value}'),
                        'start_date':  data['start_date'],
                        'end_date':    data['end_date'],
                        'period_type': data.get('period_type', 'Monthly'),
                        'status':      data.get('status', 'Open'),
                        'is_active':   bool(data.get('is_active', True)),
                    },
                )
                if created:
                    report.fiscal_year_created = 1
        except Exception:
            logger.exception('FiscalYear seed failed for %s', self.schema_name)
            report.skipped.append('fiscal_year')

    def _seed_fiscal_periods(self, report: SeedReport) -> None:
        rows = _load_json('fiscal_periods.json', self.year)
        if rows is None:
            report.skipped.append('fiscal_periods')
            return
        from accounting.models.advanced import FiscalPeriod
        try:
            with transaction.atomic():
                for row in rows:
                    _, created = FiscalPeriod.objects.get_or_create(
                        fiscal_year=int(row['fiscal_year']),
                        period_number=int(row['period_number']),
                        period_type=row['period_type'],
                        defaults={
                            'start_date': row['start_date'],
                            'end_date':   row['end_date'],
                            'name':       row.get('name', ''),
                            'status':     row.get('status', 'Open'),
                        },
                    )
                    if created:
                        report.fiscal_periods_created += 1
        except Exception:
            logger.exception('FiscalPeriod seed failed for %s', self.schema_name)
            report.skipped.append('fiscal_periods')

    def _seed_budget_periods(self, report: SeedReport) -> None:
        rows = _load_json('budget_periods.json', self.year)
        if rows is None:
            report.skipped.append('budget_periods')
            return
        from accounting.models.balances import BudgetPeriod
        try:
            with transaction.atomic():
                for row in rows:
                    _, created = BudgetPeriod.objects.get_or_create(
                        fiscal_year=int(row['fiscal_year']),
                        period_type=row['period_type'],
                        period_number=int(row['period_number']),
                        defaults={
                            'start_date': row['start_date'],
                            'end_date':   row['end_date'],
                            'status':     row.get('status', 'OPEN'),
                        },
                    )
                    if created:
                        report.budget_periods_created += 1
        except Exception:
            logger.exception('BudgetPeriod seed failed for %s', self.schema_name)
            report.skipped.append('budget_periods')

    def _seed_accounts(self, report: SeedReport) -> None:
        rows = _load_json('accounts.json', self.year)
        if rows is None:
            report.skipped.append('accounts')
            return
        from accounting.models.gl import Account
        try:
            with transaction.atomic():
                for row in rows:
                    defaults = {
                        'name':         row['name'],
                        'account_type': row['account_type'],
                        'is_active':    bool(row.get('is_active', True)),
                    }
                    # Optional fields — only include when the JSON
                    # supplies them so the model's own defaults apply
                    # otherwise. Keeps the JSON shape minimal.
                    if 'reconciliation_type' in row:
                        defaults['reconciliation_type'] = row['reconciliation_type']
                    if 'is_postable' in row:
                        defaults['is_postable'] = bool(row['is_postable'])
                    _, created = Account.objects.get_or_create(
                        code=row['code'],
                        defaults=defaults,
                    )
                    if created:
                        report.accounts_created += 1
        except Exception:
            logger.exception('Account seed failed for %s', self.schema_name)
            report.skipped.append('accounts')

    def _seed_budget_check_rules(self, report: SeedReport) -> None:
        rows = _load_json('budget_check_rules.json', self.year)
        if rows is None:
            report.skipped.append('budget_check_rules')
            return
        from accounting.models.budget_check_rules import BudgetCheckRule
        try:
            with transaction.atomic():
                for row in rows:
                    _, created = BudgetCheckRule.objects.get_or_create(
                        gl_from=row['gl_from'],
                        gl_to=row['gl_to'],
                        defaults={
                            'check_level':           row.get('check_level', 'WARNING'),
                            'warning_threshold_pct': row.get('warning_threshold_pct', 80.00),
                            'description':           row.get('description', ''),
                            'priority':              int(row.get('priority', 0)),
                            'is_active':             bool(row.get('is_active', True)),
                        },
                    )
                    if created:
                        report.rules_created += 1
        except Exception:
            logger.exception('BudgetCheckRule seed failed for %s', self.schema_name)
            report.skipped.append('budget_check_rules')

    def _seed_treasury_account(self, report: SeedReport) -> None:
        data = _load_json('treasury_account.json', self.year)
        if data is None:
            report.skipped.append('treasury_account')
            return
        from accounting.models.treasury import TreasuryAccount
        try:
            with transaction.atomic():
                _, created = TreasuryAccount.objects.get_or_create(
                    account_number=data['account_number'],
                    defaults={
                        'account_name':    data['account_name'],
                        'bank':            data.get('bank', ''),
                        'sort_code':       data.get('sort_code', ''),
                        'account_type':    data.get('account_type', 'MAIN_TSA'),
                        'is_active':       bool(data.get('is_active', True)),
                        'current_balance': data.get('current_balance', '0.00'),
                        'description':     data.get('description', ''),
                    },
                )
                if created:
                    report.tsa_created = 1
        except Exception:
            logger.exception('TreasuryAccount seed failed for %s', self.schema_name)
            report.skipped.append('treasury_account')
