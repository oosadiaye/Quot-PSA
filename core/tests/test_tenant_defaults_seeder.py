"""
Tests for ``tenants.services.default_seeder`` — the placeholder
substitution layer plus the loader's contract.

We deliberately scope these tests to **no-DB** so they run on the
fast tier alongside the SoD wiring tests. The seeder's actual model
writes are exercised end-to-end by an integration test fixture that
runs against a real schema; here we cover the parts that don't need
the DB:

  * Token substitution for every supported placeholder.
  * Year-relative anchoring (a seed parsed in 2030 gets FY 2030).
  * The ``SeedReport`` total accounting.
  * The loader silently skips missing files (key for the "delete
    a JSON to opt out" use case).
  * The seed JSON files on disk parse cleanly and have the expected
    keys — catches a typo in the data files at test time rather than
    when an operator runs ``seed_tenant_defaults`` and sees a
    KeyError.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────────
# Placeholder substitution
# ─────────────────────────────────────────────────────────────────────

class TestResolveTokens:

    def _resolve(self, value, year=2026):
        from tenants.services.default_seeder import _resolve_tokens
        return _resolve_tokens(value, year)

    def test_current_fy_year(self):
        assert self._resolve('{{current_fy_year}}', year=2027) == '2027'

    def test_current_fy_start_end(self):
        assert self._resolve('{{current_fy_start}}', year=2026) == '2026-01-01'
        assert self._resolve('{{current_fy_end}}',   year=2026) == '2026-12-31'

    def test_month_start_end_padding(self):
        # Single-digit month must zero-pad so the resulting string is
        # an ISO date the ORM accepts without further parsing.
        assert self._resolve('{{month_start:1}}', year=2026) == '2026-01-01'
        assert self._resolve('{{month_end:1}}',   year=2026) == '2026-01-31'
        assert self._resolve('{{month_start:9}}', year=2026) == '2026-09-01'
        assert self._resolve('{{month_end:9}}',   year=2026) == '2026-09-30'

    def test_month_end_handles_february_leap(self):
        # 2024 is a leap year. The naïve "always 28" loop would miss
        # this — the seeder uses calendar.monthrange which gets it
        # right.
        assert self._resolve('{{month_end:2}}', year=2024) == '2024-02-29'
        assert self._resolve('{{month_end:2}}', year=2025) == '2025-02-28'

    def test_quarter_bounds(self):
        assert self._resolve('{{quarter_start:1}}', year=2026) == '2026-01-01'
        assert self._resolve('{{quarter_end:1}}',   year=2026) == '2026-03-31'
        assert self._resolve('{{quarter_start:4}}', year=2026) == '2026-10-01'
        assert self._resolve('{{quarter_end:4}}',   year=2026) == '2026-12-31'

    def test_unknown_token_is_left_in_place(self):
        # A typo in the JSON file shouldn't silently produce empty
        # strings — that would mask the bug. The loader passes through
        # the literal so the downstream ORM call fails loudly.
        out = self._resolve('{{not_a_real_token}}', year=2026)
        assert '{{not_a_real_token}}' in out

    def test_walks_nested_structures(self):
        # Confirms the recursive walk: dict-in-list-in-dict resolves
        # tokens at every depth.
        payload = {
            'a': '{{current_fy_year}}',
            'b': [
                {'start': '{{month_start:1}}'},
                {'end':   '{{month_end:12}}'},
            ],
            'c': 42,             # non-string passes through
            'd': True,
        }
        out = self._resolve(payload, year=2026)
        assert out['a'] == '2026'
        assert out['b'][0]['start'] == '2026-01-01'
        assert out['b'][1]['end']   == '2026-12-31'
        assert out['c'] == 42
        assert out['d'] is True


# ─────────────────────────────────────────────────────────────────────
# SeedReport
# ─────────────────────────────────────────────────────────────────────

class TestSeedReport:

    def test_total_sums_per_model_counts(self):
        from tenants.services.default_seeder import SeedReport
        r = SeedReport(
            fiscal_year_created=1,
            fiscal_periods_created=12,
            budget_periods_created=17,
            accounts_created=15,
            rules_created=4,
            tsa_created=1,
        )
        assert r.total() == 50

    def test_skipped_defaults_to_empty_list(self):
        from tenants.services.default_seeder import SeedReport
        # The dataclass uses ``__post_init__`` to convert None → [].
        # Without this, a default of ``[]`` at the dataclass level
        # would be shared across instances (mutable-default trap).
        a = SeedReport()
        b = SeedReport()
        a.skipped.append('x')
        assert a.skipped == ['x']
        assert b.skipped == []


# ─────────────────────────────────────────────────────────────────────
# Loader contract
# ─────────────────────────────────────────────────────────────────────

class TestLoadJson:

    def test_missing_file_returns_none_not_raise(self, tmp_path, monkeypatch):
        # Operators can opt out of a seed by deleting its JSON file.
        # The loader must skip cleanly, not crash. Point the loader
        # at an empty directory and confirm.
        from tenants.services import default_seeder
        monkeypatch.setattr(default_seeder, 'SEED_DATA_DIR', tmp_path)
        assert default_seeder._load_json('absent.json', year=2026) is None


# ─────────────────────────────────────────────────────────────────────
# On-disk JSON sanity
# ─────────────────────────────────────────────────────────────────────

class TestSeedDataFiles:
    """The JSON files must be parseable and carry the expected keys.

    These tests fail loudly when someone edits a seed file and
    breaks the schema the seeder expects — much better than a
    KeyError surfacing during a real tenant provision.
    """

    SEED_DIR = (
        Path(__file__).resolve().parent.parent.parent
        / 'tenants' / 'seed_data'
    )

    def _read(self, name):
        with (self.SEED_DIR / name).open(encoding='utf-8') as f:
            return json.load(f)

    def test_fiscal_year_has_required_keys(self):
        data = self._read('fiscal_year.json')
        for key in ('year', 'name', 'start_date', 'end_date'):
            assert key in data, f'fiscal_year.json missing {key}'

    def test_fiscal_periods_is_list_of_12(self):
        data = self._read('fiscal_periods.json')
        assert isinstance(data, list)
        assert len(data) == 12
        for row in data:
            for key in ('fiscal_year', 'period_number', 'period_type', 'start_date', 'end_date'):
                assert key in row, f'fiscal_periods.json row missing {key}'

    def test_budget_periods_covers_monthly_quarterly_annual(self):
        data = self._read('budget_periods.json')
        types = {row['period_type'] for row in data}
        assert types == {'MONTHLY', 'QUARTERLY', 'ANNUAL'}, (
            f'budget_periods.json must cover all three period types, got {types}'
        )

    def test_accounts_include_recon_tagged_essentials(self):
        data = self._read('accounts.json')
        recon_types = {
            row.get('reconciliation_type')
            for row in data
            if row.get('reconciliation_type')
        }
        # Without at least bank, AP, AR, inventory, asset reconciliation
        # accounts, get_vendor_ap_account and friends will hard-fail
        # on a freshly seeded tenant.
        required = {
            'bank_accounting', 'accounts_payable', 'accounts_receivable',
            'inventory', 'asset_accounting',
        }
        missing = required - recon_types
        assert not missing, f'accounts.json missing recon types: {missing}'

    def test_budget_check_rules_have_catchall(self):
        data = self._read('budget_check_rules.json')
        # The wildcard 00000000-99999999 catch-all must always be
        # present so the resolver never hits a "no rule found" case
        # (which historically returned STRICT and broke everything).
        catch_alls = [
            r for r in data
            if r['gl_from'] == '00000000' and r['gl_to'] == '99999999'
        ]
        assert catch_alls, 'budget_check_rules.json must include a 00000000-99999999 catch-all'

    def test_treasury_account_has_required_keys(self):
        data = self._read('treasury_account.json')
        for key in ('account_number', 'account_name', 'account_type'):
            assert key in data, f'treasury_account.json missing {key}'


# ─────────────────────────────────────────────────────────────────────
# Year-relative anchoring (regression guard)
# ─────────────────────────────────────────────────────────────────────

class TestYearAnchoring:
    """When a tenant is provisioned in 2030, the seed must produce
    FY 2030 — not the literal "2026" baked into the JSON file. This
    test catches the regression where someone replaces a placeholder
    with a hardcoded year.
    """

    def test_fiscal_year_json_uses_placeholder_not_literal(self):
        path = (
            Path(__file__).resolve().parent.parent.parent
            / 'tenants' / 'seed_data' / 'fiscal_year.json'
        )
        with path.open(encoding='utf-8') as f:
            raw = f.read()
        assert '{{current_fy_year}}' in raw, (
            'fiscal_year.json must use the {{current_fy_year}} placeholder so '
            'a tenant provisioned in any year gets the right FY automatically'
        )
        # And conversely: any literal year between 2020 and 2099 in the
        # FY row would be a regression.
        import re
        literal_years = re.findall(r'\b20[2-9][0-9]\b', raw)
        assert not literal_years, (
            f'fiscal_year.json contains hardcoded year(s): {literal_years} — '
            f'use the {{{{current_fy_year}}}} placeholder instead'
        )

    def test_seeder_resolves_to_target_year(self):
        """The integration boundary: instantiate the seeder with a
        specific year and verify the JSON parsing produces dates in
        that year. No DB write — just the substitution path."""
        from tenants.services.default_seeder import _load_json
        data = _load_json('fiscal_year.json', year=2031)
        assert data['year'] == '2031'
        assert data['start_date'] == '2031-01-01'
        assert data['end_date']   == '2031-12-31'
        assert 'FY 2031' in data['name']
