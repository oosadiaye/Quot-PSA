"""Budget check rule resolver — one call-site for every enforcement path.

Every module that gates postings against appropriation (journal post,
PO approval, 3-way match invoice verification, vendor invoice post,
payment voucher) resolves the applicable rule through ``check_policy()``
here. That keeps the policy single-sourced and the enforcement points
uniform.

Returned ``CheckResult`` is a discriminated dataclass with three cases:

    * ``level='NONE'``    — nothing to enforce. Caller posts freely.
    * ``level='WARNING'`` — caller posts, but should attach ``warnings``
      to the response so the UI can surface a yellow banner.
    * ``level='STRICT'``  — caller MUST raise / return 400 with ``blocked``
      set to the explanation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class CheckResult:
    level: str  # 'NONE' | 'WARNING' | 'STRICT'
    blocked: bool = False
    reason: str = ''
    warnings: list = field(default_factory=list)
    rule_description: str = ''
    threshold_pct: Optional[Decimal] = None
    utilisation_pct: Optional[Decimal] = None


def resolve_rule_for_account(account_code: str):
    """Return the narrowest active BudgetCheckRule containing ``account_code``.

    Rule choice algorithm:
      1. Filter to ``is_active=True`` AND ``gl_from <= code <= gl_to``.
      2. Pick the rule with the smallest ``(gl_to - gl_from)`` width.
      3. Tiebreaker: highest ``priority`` wins.

    Returns ``None`` when no active rule covers the code — callers fall
    back to Django ``BUDGET_DEFAULT_CONTROL_LEVEL`` (default 'NONE').
    """
    if not account_code:
        return None

    from accounting.models import BudgetCheckRule

    candidates = BudgetCheckRule.objects.filter(
        is_active=True,
        gl_from__lte=account_code,
        gl_to__gte=account_code,
    )

    best = None
    best_width = None
    for rule in candidates:
        w = rule.width
        if best is None or w < best_width or (w == best_width and rule.priority > best.priority):
            best = rule
            best_width = w
    return best


def _effective_level(rule) -> str:
    from django.conf import settings
    if rule:
        return rule.check_level
    return getattr(settings, 'BUDGET_DEFAULT_CONTROL_LEVEL', 'NONE')


def check_policy(
    *,
    account_code: str,
    appropriation=None,
    requested_amount: Optional[Decimal] = None,
    transaction_label: str = 'transaction',
    account_name: str = '',
) -> CheckResult:
    """Evaluate whether a posting against ``account_code`` is permitted.

    Parameters
    ----------
    account_code
        GL account code the line is being posted to. Used to look up the
        matching rule.
    appropriation
        The ``budget.Appropriation`` row the posting would encumber, if
        any. ``None`` when no matching appropriation exists (the most
        interesting STRICT case).
    requested_amount
        Decimal amount of the line. Used to compute utilisation % when
        an appropriation exists. Optional — omit for pre-post checks
        that don't know the amount yet.
    transaction_label
        Free-text label ('journal', 'PO', 'payment voucher') used in
        the reason message so the user sees context.
    account_name
        Optional human-readable account name (e.g. "Uniforms and Other
        Clothing"). Surfaced in the STRICT error message instead of
        the rule's description, because rule descriptions can be
        miscalibrated (e.g. a tenant admin widens a "Personnel Costs"
        rule's range without updating the label). Showing the actual
        account name makes the error trustworthy.

    Returns
    -------
    CheckResult
        Always — the caller inspects ``.blocked`` for strict stops and
        ``.warnings`` for advisory flags.
    """
    rule = resolve_rule_for_account(account_code)
    level = _effective_level(rule)
    desc = rule.description if rule else ''

    # ── NONE → everything passes, no logging ────────────────────
    if level == 'NONE':
        return CheckResult(level='NONE', rule_description=desc)

    # ── STRICT → must have an appropriation, must have funds ────
    if level == 'STRICT':
        if appropriation is None:
            # Build a message that names the ACCOUNT (truth) and the
            # rule range (so the operator can spot a mis-scoped rule).
            # Format: "GL <code> (<account name>). This is gated by
            # rule covering <from>–<to> (<rule desc>). Either create
            # the appropriation, or fix the rule range in Settings →
            # Budget Check Rules if this account doesn't belong in
            # that range."
            acc_label = account_name or desc
            rule_range = (
                f'{rule.gl_from}–{rule.gl_to}'
                if rule and rule.gl_from and rule.gl_to else ''
            )
            rule_clause = (
                f' Matched by strict rule covering {rule_range}'
                + (f' ({desc})' if desc else '')
                + '.'
            ) if rule_range else ''
            reason = (
                f'Strict budget control is active for GL {account_code}'
                + (f' ({acc_label})' if acc_label else '')
                + f'. This {transaction_label} cannot be posted without an '
                  f'active Appropriation on that economic code.'
                + rule_clause
                + ' Either (1) create / activate the appropriation for '
                  f'GL {account_code}, or (2) edit the budget check rule '
                  'in Settings → Budget Check Rules if this account does '
                  'not belong under strict control.'
            )
            return CheckResult(
                level='STRICT', blocked=True, reason=reason, rule_description=desc,
            )
        if requested_amount is not None:
            available = _appropriation_available(appropriation)
            if Decimal(str(requested_amount)) > available:
                # Same display-priority as the no-appropriation branch
                # above: prefer the human GL account name over the
                # rule description. Showing "(Office Stationery)"
                # tells the operator WHICH account is over budget;
                # showing "(Expenditure - STRICT. Posting requires...)"
                # is the rule's text, not the account's, and was a
                # readability regression introduced when this branch
                # was first written.
                acc_label = account_name or desc
                reason = (
                    f'Strict budget control — requested {requested_amount} '
                    f'exceeds appropriation available balance {available} '
                    f'for GL {account_code}'
                    + (f' ({acc_label})' if acc_label else '') + '.'
                )
                return CheckResult(
                    level='STRICT', blocked=True, reason=reason, rule_description=desc,
                )
        return CheckResult(level='STRICT', rule_description=desc)

    # ── WARNING → always posts; raise flag when utilisation ≥ threshold
    threshold = Decimal('80.00')
    if rule and rule.warning_threshold_pct is not None:
        threshold = Decimal(str(rule.warning_threshold_pct))

    warnings: list = []
    util = None
    if appropriation is not None:
        approved = Decimal(str(appropriation.amount_approved or 0))
        if approved > 0:
            expended = Decimal(str(getattr(appropriation, 'cached_total_expended', 0) or 0))
            committed = Decimal(str(getattr(appropriation, 'cached_total_committed', 0) or 0))
            util = ((expended + committed) / approved) * Decimal('100')
            if util >= threshold:
                warnings.append(
                    f'Appropriation utilisation {util:.1f}% for GL {account_code}'
                    + (f' ({desc})' if desc else '')
                    + f' is at or above the {threshold}% warning threshold.'
                )
    else:
        warnings.append(
            f'No active Appropriation for GL {account_code}'
            + (f' ({desc})' if desc else '')
            + f'. This {transaction_label} will post unbudgeted.'
        )

    return CheckResult(
        level='WARNING',
        warnings=warnings,
        rule_description=desc,
        threshold_pct=threshold,
        utilisation_pct=util,
    )


def _appropriation_available(appropriation) -> Decimal:
    """Helper to compute the appropriation's available balance safely."""
    approved = Decimal(str(appropriation.amount_approved or 0))
    expended = Decimal(str(getattr(appropriation, 'cached_total_expended', 0) or 0))
    committed = Decimal(str(getattr(appropriation, 'cached_total_committed', 0) or 0))
    return approved - expended - committed


def find_matching_appropriation(*, mda, fund, account, fiscal_year=None):
    """Look up the Appropriation row that would cover this posting.

    ``account`` here is the legacy ``accounting.Account`` (which points
    at an NCoA EconomicSegment via its code). We walk the NCoA parent
    chain so a child-coded GL line (e.g. 21100100 Basic Salaries)
    matches a parent-coded appropriation (e.g. 21000000 Personnel
    Costs).

    Multi-strategy lookup — tries each in order, returns the first
    match. This guards against the most common silent-mismatch
    failures we see in real tenants:

      Strategy 1 — FK-bridge match. Joins via NCoA segments'
        ``legacy_mda`` / ``legacy_fund`` FKs to the legacy
        accounting.MDA / accounting.Fund used on the invoice. Works
        when the bridge tables are fully backfilled.

      Strategy 2 — code match. Joins by the NCoA segment's ``code``
        equalling the legacy entity's ``code``. Fires when an
        Appropriation has been created against an NCoA segment that
        wasn't bridged (legacy_mda / legacy_fund FK is null) — common
        on freshly-imported budget lines where the bridge job hasn't
        run yet.

      Strategy 3 — case-insensitive status. Some seed migrations
        write 'Active' (Title Case) while the model expects 'ACTIVE'.
        Re-runs strategies 1 & 2 with ``status__iexact='ACTIVE'``.

    Returns the best match or None.
    """
    if not (mda and fund and account):
        return None

    from budget.models import Appropriation
    from accounting.models.ncoa import EconomicSegment

    econ_segs = EconomicSegment.objects.filter(code=account.code)
    if not econ_segs.exists():
        return None

    # BFS up the parent chain so child codes match ancestor appropriations.
    ancestors = list(econ_segs)
    frontier = list(econ_segs)
    while frontier:
        parents = [s for s in (f.parent for f in frontier) if s is not None]
        ancestors.extend(parents)
        frontier = parents

    mda_code = getattr(mda, 'code', None)
    fund_code = getattr(fund, 'code', None)

    def _apply_year(qs):
        if fiscal_year:
            return qs.filter(fiscal_year__year=fiscal_year)
        return qs

    # Strategy 1 — exact FK bridge match, status='ACTIVE'.
    qs = _apply_year(Appropriation.objects.filter(
        administrative__legacy_mda=mda,
        fund__legacy_fund=fund,
        economic__in=ancestors,
        status='ACTIVE',
    ))
    hit = qs.first()
    if hit:
        return hit

    # Strategy 2 — code match (works when legacy_mda / legacy_fund
    # FK is null on the NCoA segment).
    if mda_code and fund_code:
        qs = _apply_year(Appropriation.objects.filter(
            administrative__code=mda_code,
            fund__code=fund_code,
            economic__in=ancestors,
            status='ACTIVE',
        ))
        hit = qs.first()
        if hit:
            return hit

    # Strategy 3 — re-run both with case-insensitive status.
    qs = _apply_year(Appropriation.objects.filter(
        administrative__legacy_mda=mda,
        fund__legacy_fund=fund,
        economic__in=ancestors,
        status__iexact='ACTIVE',
    ))
    hit = qs.first()
    if hit:
        return hit

    if mda_code and fund_code:
        qs = _apply_year(Appropriation.objects.filter(
            administrative__code=mda_code,
            fund__code=fund_code,
            economic__in=ancestors,
            status__iexact='ACTIVE',
        ))
        hit = qs.first()
        if hit:
            return hit

    return None
