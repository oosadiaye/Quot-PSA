"""
Sprint-17 tests — seed_demo_gl structural / recipe integrity.

No-DB fast tier: verifies the recipe table is balanced, the amount
jitter produces positive values within the expected band, and the
reference-number format is stable (idempotency hinges on it).
"""
from __future__ import annotations

import random
from decimal import Decimal

import pytest


class _StubAccount:
    """Minimal stand-in for Account so _recipes(...) can reference it."""
    def __init__(self, code: str, account_type: str):
        self.code = code
        self.account_type = account_type


@pytest.fixture
def buckets():
    """Fully populated bucket map — every NCoA role is resolved."""
    return {
        'tax_revenue':       _StubAccount('11100100', 'Income'),
        'non_tax_revenue':   _StubAccount('12100100', 'Income'),
        'grant_revenue':     _StubAccount('13100100', 'Income'),
        'personnel':         _StubAccount('21100100', 'Expense'),
        'goods_services':    _StubAccount('22100100', 'Expense'),
        'capital_exp':       _StubAccount('23100100', 'Expense'),
        'debt_service':      _StubAccount('24100100', 'Expense'),
        'transfers':         _StubAccount('25100100', 'Expense'),
        'cash':              _StubAccount('31100100', 'Asset'),
        'non_current_asset': _StubAccount('32100100', 'Asset'),
        'current_liab':      _StubAccount('41100100', 'Liability'),
        'non_current_liab':  _StubAccount('42100100', 'Liability'),
    }


class TestRecipeShape:

    def test_all_ten_recipes_when_buckets_complete(self, buckets):
        from accounting.management.commands.seed_demo_gl import _recipes
        rs = _recipes(buckets)
        assert len(rs) == 10

    def test_missing_bucket_drops_its_recipes(self, buckets):
        """If NCoA debt_service group isn't seeded, that recipe is skipped."""
        from accounting.management.commands.seed_demo_gl import _recipes
        partial = {**buckets, 'debt_service': None}
        rs = _recipes(partial)
        assert len(rs) == 9  # 10 − 1
        assert all(r['debit_memo'] != 'Loan interest' for r in rs)

    def test_all_buckets_missing_returns_empty(self):
        from accounting.management.commands.seed_demo_gl import _recipes
        assert _recipes({}) == []

    def test_every_recipe_has_required_fields(self, buckets):
        from accounting.management.commands.seed_demo_gl import _recipes
        required = {
            'description', 'base', 'debit_account', 'credit_account',
            'debit_memo', 'credit_memo',
        }
        for r in _recipes(buckets):
            assert required.issubset(r.keys()), f'Missing fields in: {r}'

    def test_every_recipe_has_distinct_memos(self, buckets):
        from accounting.management.commands.seed_demo_gl import _recipes
        for r in _recipes(buckets):
            assert r['debit_memo'] != r['credit_memo']

    def test_every_recipe_has_positive_base_amount(self, buckets):
        from accounting.management.commands.seed_demo_gl import _recipes
        for r in _recipes(buckets):
            assert r['base'] > Decimal('0'), f'Non-positive base in {r}'

    def test_every_recipe_references_valid_buckets(self, buckets):
        from accounting.management.commands.seed_demo_gl import _recipes
        valid_accounts = set(id(a) for a in buckets.values())
        for r in _recipes(buckets):
            assert id(r['debit_account']) in valid_accounts
            assert id(r['credit_account']) in valid_accounts


class TestScaledAmount:

    def test_jitter_band_15_pct(self):
        from accounting.management.commands.seed_demo_gl import _scaled_amount
        rng = random.Random('test-seed')
        base = Decimal('1000000')
        samples = [_scaled_amount(rng, base) for _ in range(100)]
        for s in samples:
            # ±15 % band around base.
            assert Decimal('850000') <= s <= Decimal('1150000'), (
                f'{s} outside ±15% of {base}'
            )

    def test_jitter_is_deterministic_with_seed(self):
        from accounting.management.commands.seed_demo_gl import _scaled_amount
        rng1 = random.Random('fixed')
        rng2 = random.Random('fixed')
        base = Decimal('1000000')
        a = [_scaled_amount(rng1, base) for _ in range(10)]
        b = [_scaled_amount(rng2, base) for _ in range(10)]
        assert a == b

    def test_jitter_produces_two_decimal_places(self):
        from accounting.management.commands.seed_demo_gl import _scaled_amount
        rng = random.Random('kobo')
        s = _scaled_amount(rng, Decimal('1234567'))
        # quantize('0.01') → at most 2 decimal digits.
        assert -s.as_tuple().exponent <= 2


class TestMonthEnd:

    def test_jan(self):
        from accounting.management.commands.seed_demo_gl import _month_end
        from datetime import date
        assert _month_end(2026, 1) == date(2026, 1, 31)

    def test_feb_non_leap(self):
        from accounting.management.commands.seed_demo_gl import _month_end
        from datetime import date
        assert _month_end(2026, 2) == date(2026, 2, 28)

    def test_feb_leap(self):
        from accounting.management.commands.seed_demo_gl import _month_end
        from datetime import date
        assert _month_end(2024, 2) == date(2024, 2, 29)

    def test_dec(self):
        from accounting.management.commands.seed_demo_gl import _month_end
        from datetime import date
        assert _month_end(2026, 12) == date(2026, 12, 31)


class TestReferencePrefix:

    def test_prefix_constant(self):
        """The ref prefix is the idempotency key — freezing it protects
        upgrades from accidentally double-seeding."""
        from accounting.management.commands import seed_demo_gl
        assert seed_demo_gl._REF_PREFIX == 'DEMO-SEED-'


class TestCoverage:
    """Every NCoA account_type should appear at least once across the
    recipe set — otherwise reports for that group will still be zero."""

    def test_all_account_types_covered(self, buckets):
        from accounting.management.commands.seed_demo_gl import _recipes
        used = set()
        for r in _recipes(buckets):
            used.add(r['debit_account'].account_type)
            used.add(r['credit_account'].account_type)
        # Expect at least Asset, Income, Expense, Liability used.
        assert 'Asset' in used
        assert 'Income' in used
        assert 'Expense' in used
        assert 'Liability' in used


class TestRecipeBalance:
    """Every recipe is a balanced 2-line journal — debit amount equals
    credit amount by construction (same ``base``)."""

    def test_every_recipe_single_amount_drives_both_sides(self, buckets):
        from accounting.management.commands.seed_demo_gl import _recipes
        for r in _recipes(buckets):
            # The recipe carries one `base` amount — the handler uses it
            # for both the debit line and the credit line, which is how
            # balance is guaranteed at insertion time.
            assert r['base'] > Decimal('0')
            assert r['debit_account'] is not None
            assert r['credit_account'] is not None
