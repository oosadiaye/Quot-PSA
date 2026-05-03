"""Unit tests for BudgetCheckRule resolver + check_policy() engine.

Every enforcement path (journal post, PO approve, AP invoice post, payment
voucher, asset acquisition) routes through check_policy(). Verifying the
three check-level branches (NONE / WARNING / STRICT) here is enough to
guarantee uniform behaviour across every caller.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from accounting.services.budget_check_rules import (
    CheckResult,
    check_policy,
    resolve_rule_for_account,
)


pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_appropriation():
    """Appropriation-ish object with just enough shape for check_policy."""
    def _make(approved=Decimal('1000000'), expended=Decimal('0'), committed=Decimal('0')):
        return SimpleNamespace(
            amount_approved=approved,
            cached_total_expended=expended,
            cached_total_committed=committed,
        )
    return _make


@pytest.fixture
def rules(db):
    """Seed a clean set of rules so tests don't collide with defaults."""
    from accounting.models import BudgetCheckRule
    BudgetCheckRule.objects.all().delete()

    BudgetCheckRule.objects.create(
        gl_from='10000000', gl_to='19999999',
        check_level='NONE', priority=10, is_active=True,
        description='Assets — no check',
    )
    BudgetCheckRule.objects.create(
        gl_from='21000000', gl_to='21999999',
        check_level='STRICT', priority=20, is_active=True,
        description='Personnel — strict',
    )
    BudgetCheckRule.objects.create(
        gl_from='30000000', gl_to='39999999',
        check_level='WARNING', warning_threshold_pct=80,
        priority=10, is_active=True,
        description='Capital — warn at 80%',
    )
    return None


# ---------------------------------------------------------------------------
# resolve_rule_for_account()
# ---------------------------------------------------------------------------

def test_resolver_returns_none_when_no_rule_matches(rules):
    assert resolve_rule_for_account('99999999') is None


def test_resolver_picks_narrowest_rule_on_overlap(rules):
    """A narrow override should beat a broad default."""
    from accounting.models import BudgetCheckRule

    BudgetCheckRule.objects.create(
        gl_from='21100000', gl_to='21100099',
        check_level='NONE', priority=5, is_active=True,
        description='Tiny override',
    )
    rule = resolve_rule_for_account('21100050')
    assert rule.description == 'Tiny override'


def test_resolver_ignores_inactive_rules(rules):
    from accounting.models import BudgetCheckRule
    BudgetCheckRule.objects.filter(gl_from='21000000').update(is_active=False)
    # Falls through to default — no broader rule covers 21xxx in our seed
    assert resolve_rule_for_account('21000100') is None


# ---------------------------------------------------------------------------
# check_policy() branches
# ---------------------------------------------------------------------------

def test_policy_none_passes_even_without_appropriation(rules):
    result = check_policy(
        account_code='10000500', appropriation=None,
        requested_amount=Decimal('500'), transaction_label='journal',
    )
    assert result.level == 'NONE'
    assert not result.blocked
    assert result.warnings == []


def test_policy_strict_blocks_when_no_appropriation(rules):
    result = check_policy(
        account_code='21000100', appropriation=None,
        requested_amount=Decimal('500'), transaction_label='journal',
    )
    assert result.level == 'STRICT'
    assert result.blocked is True
    assert 'Strict budget control' in result.reason
    assert '21000100' in result.reason


def test_policy_strict_blocks_when_amount_exceeds_balance(rules, fake_appropriation):
    appro = fake_appropriation(approved=Decimal('100'))
    result = check_policy(
        account_code='21000100', appropriation=appro,
        requested_amount=Decimal('500'), transaction_label='journal',
    )
    assert result.blocked is True
    assert 'exceeds appropriation available balance' in result.reason


def test_policy_strict_passes_within_balance(rules, fake_appropriation):
    appro = fake_appropriation(approved=Decimal('10000'))
    result = check_policy(
        account_code='21000100', appropriation=appro,
        requested_amount=Decimal('500'),
    )
    assert result.level == 'STRICT'
    assert not result.blocked


def test_policy_warning_allows_without_appropriation(rules):
    result = check_policy(
        account_code='30000100', appropriation=None,
        requested_amount=Decimal('500'), transaction_label='PO',
    )
    assert result.level == 'WARNING'
    assert not result.blocked
    assert len(result.warnings) == 1
    assert 'No active Appropriation' in result.warnings[0]


def test_policy_warning_fires_at_threshold(rules, fake_appropriation):
    # 85% utilisation → above the 80% threshold
    appro = fake_appropriation(
        approved=Decimal('1000'),
        expended=Decimal('500'),
        committed=Decimal('350'),
    )
    result = check_policy(
        account_code='30000100', appropriation=appro,
        requested_amount=Decimal('50'),
    )
    assert result.level == 'WARNING'
    assert not result.blocked
    assert any('utilisation' in w for w in result.warnings)


def test_policy_warning_silent_under_threshold(rules, fake_appropriation):
    appro = fake_appropriation(
        approved=Decimal('1000'),
        expended=Decimal('100'),
        committed=Decimal('100'),
    )
    result = check_policy(
        account_code='30000100', appropriation=appro,
        requested_amount=Decimal('50'),
    )
    assert result.level == 'WARNING'
    assert not result.blocked
    assert result.warnings == []


def test_policy_with_no_rule_falls_back_to_default(rules, settings):
    """No BudgetCheckRule matches → settings.BUDGET_DEFAULT_CONTROL_LEVEL wins."""
    settings.BUDGET_DEFAULT_CONTROL_LEVEL = 'NONE'
    result = check_policy(
        account_code='99999999', appropriation=None,
        requested_amount=Decimal('500'),
    )
    assert result.level == 'NONE'
    assert not result.blocked
