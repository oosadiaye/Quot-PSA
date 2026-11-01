"""The Medium Term Expenditure Framework: assess it against the fiscal rules, project it, stress it, and approve it.

Best practice this follows (World Bank / IMF PFM guidance, PEFA, and the shape of Nigeria's MTEF / Fiscal Strategy Paper):

* a rolling three-year horizon (the budget year and two outer years), each year a resource envelope built from sources,
  spent by economic category and financed explicitly;
* the macro assumptions that sit behind the numbers (inflation, exchange rate, oil price);
* fiscal rules checked automatically and explained in words: a fully financed budget, the golden rule (borrow only for
  capital), limits on debt service, personnel cost and borrowing, and a floor on capital spending;
* realism checks: out-year revenue growth against inflation, and the budget year against last year's actual spending;
* sector (MDA) ceilings that must fit inside the envelope, and are not issued from an unapproved framework;
* sensitivity analysis, so the effect of an oil-price or revenue shock is known before it happens;
* an approval gate: a framework that breaks a rule can only be approved with a reason, which is kept on the record.

Nothing here writes to the general ledger or to Budget. It reads appropriations (for last year's outturn) and writes only
the MTEF tables. The rule limits live in ``MTEFPolicy`` and are the government's to set; the defaults are a starting point.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from budget_prep.models import MDACeiling, MTEFPolicy, MTEFProjection

PASS, WARN, FAIL = 'pass', 'warn', 'fail'
HORIZON = 3
_CENT = Decimal('0.01')
_ZERO = Decimal('0')
_REAL_STATUSES = ('APPROVED', 'ENACTED', 'ACTIVE', 'CLOSED')
_FAMILY = {'21': 'personnel', '22': 'overhead', '23': 'capital'}


class MTEFError(Exception):
    """An MTEF operation was refused; ``findings`` carries the rule results when a rule is the reason."""

    def __init__(self, message: str, *, findings: list | None = None):
        super().__init__(message)
        self.findings = findings or []


@dataclass(frozen=True)
class Finding:
    rule: str
    status: str
    message: str
    value: str | None = None
    limit: str | None = None

    def as_dict(self) -> dict:
        return {'rule': self.rule, 'status': self.status, 'message': self.message, 'value': self.value, 'limit': self.limit}


def _q(v) -> Decimal:
    return Decimal(v).quantize(_CENT, rounding=ROUND_HALF_UP)


def _pct(part, whole) -> Decimal | None:
    whole = Decimal(whole or 0)
    return None if whole <= 0 else _q(Decimal(part or 0) / whole * 100)


def _m(v) -> str:
    return f'{Decimal(v):,.2f}'


def get_policy() -> MTEFPolicy:
    """The government's fiscal rules, created with the default limits on first use. Always read back from the database, so
    a limit prints the same ("30.00") on the first use as on every later one."""
    policy = MTEFPolicy.objects.order_by('pk').first()
    if policy is None:
        policy = MTEFPolicy.objects.create()
        policy.refresh_from_db()
    return policy


# ───────────────────────────── figures and rules ─────────────────────────────

def figures(p: MTEFProjection) -> dict:
    """Everything worth showing for one year, worked out from its parts."""
    revenue, spend = p.total_revenue, p.total_expenditure
    return {
        'year': p.fiscal_year,
        'status': p.status,
        'assumptions': {
            'inflation': str(p.inflation_assumption), 'exchange_rate': str(p.exchange_rate_assumption),
            'oil_price': None if p.oil_price_assumption is None else str(p.oil_price_assumption),
            'oil_sensitivity': str(p.oil_sensitivity),
            'gdp': str(p.gdp_assumption), 'opening_debt_stock': str(p.opening_debt_stock),
        },
        'revenue': {n: str(getattr(p, n)) for n in MTEFProjection.REVENUE_FIELDS},
        'expenditure': {n: str(getattr(p, n)) for n in MTEFProjection.EXPENDITURE_FIELDS},
        'financing': {n: str(getattr(p, n)) for n in MTEFProjection.FINANCING_FIELDS},
        'totals': {
            'revenue': str(revenue), 'recurrent_revenue': str(p.recurrent_revenue), 'expenditure': str(spend),
            'recurrent_expenditure': str(p.recurrent_expenditure), 'balance': str(p.fiscal_balance),
            'financing': str(p.total_financing), 'unfinanced_gap': str(p.unfinanced_gap),
        },
        'ratios': {
            'debt_service_pct_revenue': _opt(_pct(p.exp_debt_service, revenue)),
            'personnel_pct_recurrent_revenue': _opt(_pct(p.exp_personnel, p.recurrent_revenue)),
            'capital_pct_expenditure': _opt(_pct(p.exp_capital, spend)),
            'borrowing_pct_revenue': _opt(_pct(p.fin_domestic + p.fin_external, revenue)),
            'deficit_pct_gdp': _opt(_pct(_deficit(p), p.gdp_assumption)),
            'debt_stock_pct_gdp': _opt(_pct(closing_debt(p), p.gdp_assumption)),
        },
        'approved_by': p.approved_by, 'approved_at': p.approved_at.isoformat() if p.approved_at else None,
        'override_reason': p.override_reason,
    }


def _deficit(p: MTEFProjection) -> Decimal:
    return max(_ZERO, -Decimal(p.fiscal_balance))


def closing_debt(p: MTEFProjection) -> Decimal:
    """The debt owed at the end of the year: what was owed at the start plus the year's new borrowing."""
    return Decimal(p.opening_debt_stock) + Decimal(p.fin_domestic) + Decimal(p.fin_external)


def _opt(v):
    return None if v is None else str(v)


def prior_outturn(year: int) -> dict | None:
    """What was actually spent in the year before, by family, from the enacted appropriations; None when there is none."""
    from accounting.models.advanced import FiscalYear
    from budget.models import Appropriation

    fy = FiscalYear.objects.filter(year=year - 1).first()
    if fy is None:
        return None
    totals = {'personnel': _ZERO, 'overhead': _ZERO, 'capital': _ZERO, 'other': _ZERO}
    seen = False
    for a in Appropriation.objects.filter(fiscal_year=fy, status__in=_REAL_STATUSES, economic__code__startswith='2').select_related('economic'):
        seen = True
        totals[_FAMILY.get(a.economic.code[:2], 'other')] += Decimal(a.total_expended)
    if not seen:
        return None
    total = sum(totals.values(), _ZERO)
    return {'year': year - 1, **{k: str(_q(v)) for k, v in totals.items()}, 'total': str(_q(total))} if total > 0 else None


def assess_year(p: MTEFProjection, policy: MTEFPolicy, *, previous: MTEFProjection | None = None,
                outturn: dict | None = None) -> list[Finding]:
    """Hold one year to the fiscal rules. Every finding says in words what is wrong and by how much."""
    out: list[Finding] = []
    revenue, spend = p.total_revenue, p.total_expenditure
    recurrent_rev, recurrent_exp = p.recurrent_revenue, p.recurrent_expenditure

    if revenue <= 0:
        return [Finding('Resource envelope', FAIL, 'No revenue has been entered, so there is no resource envelope to spend within.')]
    out.append(Finding('Resource envelope', PASS, f'Total revenue is {_m(revenue)}.', _m(revenue)))

    gap = p.unfinanced_gap
    if gap > 0:
        out.append(Finding('Fully financed', FAIL,
                           f'The deficit of {_m(-p.fiscal_balance)} is not fully financed: {_m(gap)} is unfunded. '
                           'Reduce spending or identify financing.', _m(gap), '0.00'))
    else:
        out.append(Finding('Fully financed', PASS, 'The budget is in balance or its deficit is fully financed.', _m(gap), '0.00'))

    if policy.enforce_golden_rule:
        over = recurrent_exp - recurrent_rev
        out.append(Finding('Golden rule', FAIL,
                           f'Recurrent spending ({_m(recurrent_exp)}) exceeds recurrent revenue ({_m(recurrent_rev)}) by {_m(over)}: '
                           'borrowing would be paying running costs, not building assets.', _m(recurrent_exp), _m(recurrent_rev))
                   if over > 0 else
                   Finding('Golden rule', PASS, f'Recurrent spending is within recurrent revenue, with {_m(-over)} to spare.',
                           _m(recurrent_exp), _m(recurrent_rev)))

    def limit(rule, value, bound, *, cap=True, severity=WARN, what='', unit='%'):
        if value is None:
            return
        breached = value > bound if cap else value < bound
        word = 'above the limit of' if cap else 'below the floor of'
        out.append(Finding(rule, severity if breached else PASS,
                           f'{what} is {value}{unit}, {word} {bound}{unit}.' if breached else f'{what} is {value}{unit}, within the {"limit" if cap else "floor"} of {bound}{unit}.',
                           f'{value}', f'{bound}'))

    limit('Debt service', _pct(p.exp_debt_service, revenue), Decimal(policy.max_debt_service_pct), severity=FAIL,
          what='Debt service as a share of total revenue')
    limit('Personnel cost', _pct(p.exp_personnel, recurrent_rev), Decimal(policy.max_personnel_pct),
          what='Personnel cost as a share of recurrent revenue')
    limit('Capital share', _pct(p.exp_capital, spend), Decimal(policy.min_capital_pct), cap=False,
          what='Capital expenditure as a share of total expenditure')
    limit('Borrowing', _pct(p.fin_domestic + p.fin_external, revenue), Decimal(policy.max_borrowing_pct),
          what='New borrowing as a share of total revenue')

    limit('Deficit to GDP', _pct(_deficit(p), p.gdp_assumption), Decimal(policy.max_deficit_pct_gdp), severity=FAIL,
          what='The fiscal deficit as a share of GDP')
    limit('Debt stock', _pct(closing_debt(p), p.gdp_assumption), Decimal(policy.max_debt_stock_pct_gdp), severity=FAIL,
          what='Closing public debt as a share of GDP')

    if p.inflation_assumption <= 0 or p.exchange_rate_assumption <= 0:
        out.append(Finding('Assumptions', WARN, 'The inflation or exchange-rate assumption is blank, so the projection has no stated basis.'))
    else:
        out.append(Finding('Assumptions', PASS, 'Inflation and exchange-rate assumptions are stated.'))

    if previous is not None and previous.total_revenue > 0:
        growth = _q((revenue - previous.total_revenue) / previous.total_revenue * 100)
        allowed = _q(Decimal(p.inflation_assumption) + Decimal(policy.max_revenue_growth_pct))
        out.append(Finding('Revenue growth', WARN if growth > allowed else PASS,
                           f'Revenue grows {growth}% on {previous.fiscal_year}, '
                           + (f'more than the {allowed}% that inflation plus {policy.max_revenue_growth_pct} points allows: check it is realistic.'
                              if growth > allowed else f'within the {allowed}% that inflation plus {policy.max_revenue_growth_pct} points allows.'),
                           str(growth), str(allowed)))

    if outturn:
        actual = Decimal(outturn['total'])
        allowed_spend = _q(actual * (1 + (Decimal(p.inflation_assumption) + Decimal(policy.max_outturn_jump_pct)) / 100))
        jump = _q((spend - actual) / actual * 100)
        out.append(Finding('Against last year\'s actual spending', WARN if spend > allowed_spend else PASS,
                           f'Planned spending of {_m(spend)} is {jump}% on what was actually spent in {outturn["year"]} ({_m(actual)})'
                           + (f', beyond the {policy.max_outturn_jump_pct} points above inflation that is normally credible.' if spend > allowed_spend else '.'),
                           str(jump), str(policy.max_outturn_jump_pct)))
    return out


def worst(findings: list[Finding]) -> str:
    states = {f.status for f in findings}
    return FAIL if FAIL in states else WARN if WARN in states else PASS


# ───────────────────────────── ceilings ─────────────────────────────

def ceilings_against(p: MTEFProjection) -> list[dict]:
    """The MDA ceilings issued for this year against the envelope for each type, with the headroom left."""
    allocated = {'personnel': _ZERO, 'overhead': _ZERO, 'capital': _ZERO}
    for c in MDACeiling.objects.filter(fiscal_year=p.fiscal_year):
        allocated['personnel'] += c.personnel_ceiling
        allocated['overhead'] += c.overhead_ceiling
        allocated['capital'] += c.capital_ceiling
    envelope = {'personnel': p.exp_personnel, 'overhead': p.exp_overhead, 'capital': p.exp_capital}
    return [{'type': t, 'envelope': str(envelope[t]), 'allocated': str(allocated[t]), 'headroom': str(envelope[t] - allocated[t]),
             'over': allocated[t] > envelope[t]} for t in ('personnel', 'overhead', 'capital')]


def check_ceiling_fits(fiscal_year: int, *, personnel, overhead, capital, exclude_pk=None) -> None:
    """Refuse a ceiling that the MTEF cannot support: an unapproved framework, or one that would overspend a type."""
    p = MTEFProjection.objects.filter(fiscal_year=fiscal_year).first()
    if p is None:
        return                                        # no framework for the year: nothing to hold the ceiling to
    if p.status != 'approved':
        raise MTEFError(f'The {fiscal_year} MTEF is not approved yet. Approve it before issuing MDA ceilings.')
    others = MDACeiling.objects.filter(fiscal_year=fiscal_year)
    if exclude_pk:
        others = others.exclude(pk=exclude_pk)
    wanted = {'personnel': Decimal(personnel or 0), 'overhead': Decimal(overhead or 0), 'capital': Decimal(capital or 0)}
    envelope = {'personnel': p.exp_personnel, 'overhead': p.exp_overhead, 'capital': p.exp_capital}
    for kind, value in wanted.items():
        used = sum((getattr(c, f'{kind}_ceiling') for c in others), _ZERO)
        if used + value > envelope[kind]:
            raise MTEFError(f'This {kind} ceiling of {_m(value)} would take the {kind} ceilings to {_m(used + value)}, '
                            f'above the {fiscal_year} MTEF envelope of {_m(envelope[kind])} (already allocated: {_m(used)}).')


# ───────────────────────────── the framework ─────────────────────────────

def framework(base_year: int) -> dict:
    """The three-year framework: each year's figures, rule findings, and (for the first) last year's outturn and ceilings."""
    policy = get_policy()
    rows = {p.fiscal_year: p for p in MTEFProjection.objects.filter(fiscal_year__gte=base_year, fiscal_year__lt=base_year + HORIZON)}
    years = []
    for i in range(HORIZON):
        y = base_year + i
        p = rows.get(y)
        if p is None:
            years.append({'year': y, 'missing': True})
            continue
        outturn = prior_outturn(y)
        findings = assess_year(p, policy, previous=rows.get(y - 1), outturn=outturn)
        years.append({**figures(p), 'id': p.pk, 'missing': False, 'overall': worst(findings),
                      'findings': [f.as_dict() for f in findings], 'prior_outturn': outturn,
                      'ceilings': ceilings_against(p) if p.exp_personnel or p.exp_overhead or p.exp_capital else []})
    present = [y for y in years if not y['missing']]
    return {
        'base_year': base_year, 'years': years,
        'overall': worst([Finding('', y['overall'], '') for y in present]) if present else 'empty',
        'complete': len(present) == HORIZON,
        'policy': {f.name: str(getattr(policy, f.name)) if not isinstance(getattr(policy, f.name), bool) else getattr(policy, f.name)
                   for f in MTEFPolicy._meta.fields if f.name.startswith(('max_', 'min_', 'enforce_'))},
    }


def scenario(base_year: int, *, oil_price_change_pct=0, igr_change_pct=0, cost_change_pct=0) -> dict:
    """What the framework looks like if the oil price, IGR or costs move. Computed in memory; nothing is saved."""
    policy = get_policy()
    oil, igr, cost = Decimal(str(oil_price_change_pct or 0)), Decimal(str(igr_change_pct or 0)), Decimal(str(cost_change_pct or 0))
    rows = {p.fiscal_year: p for p in MTEFProjection.objects.filter(fiscal_year__gte=base_year, fiscal_year__lt=base_year + HORIZON)}
    out, shocked = [], {}
    for y in sorted(rows):
        p = rows[y]
        before = assess_year(p, policy, previous=rows.get(y - 1), outturn=prior_outturn(y))
        c = MTEFProjection(**{f.attname: getattr(p, f.attname) for f in MTEFProjection._meta.concrete_fields if f.attname != 'id'})
        pull = 1 + oil / 100 * Decimal(p.oil_sensitivity)
        c.rev_statutory, c.rev_vat = _q(p.rev_statutory * pull), _q(p.rev_vat * pull)
        c.rev_igr = _q(p.rev_igr * (1 + igr / 100))
        for name in ('exp_personnel', 'exp_overhead', 'exp_other_recurrent'):
            setattr(c, name, _q(getattr(p, name) * (1 + cost / 100)))
        c.aggregate_revenue, c.aggregate_expenditure = c.total_revenue, c.total_expenditure
        c.fiscal_balance = c.aggregate_revenue - c.aggregate_expenditure           # in memory only; never saved
        shocked[y] = c
        after = assess_year(c, policy, previous=shocked.get(y - 1), outturn=prior_outturn(y))
        newly = [a.as_dict() for a in after if a.status == FAIL and not any(b.rule == a.rule and b.status == FAIL for b in before)]
        out.append({'year': y, 'before': figures(p)['totals'], 'after': figures(c)['totals'],
                    'balance_change': str(c.fiscal_balance - p.fiscal_balance), 'findings': [f.as_dict() for f in after],
                    'newly_failing': newly, 'overall': worst(after)})
    return {'base_year': base_year, 'shock': {'oil_price_change_pct': str(oil), 'igr_change_pct': str(igr), 'cost_change_pct': str(cost)},
            'years': out}


@dataclass
class RollResult:
    created: list = field(default_factory=list)
    kept: list = field(default_factory=list)


def roll_forward(base_year: int, *, growth: dict | None = None) -> RollResult:
    """Create the two outer years from the budget year by growing each line, leaving any year that already exists alone.

    Each category grows by its own rate when given, else by the budget year's inflation assumption; financing is held flat
    and the assumptions are carried over. The new years are drafts for the Budget Office to refine.
    """
    base = MTEFProjection.objects.filter(fiscal_year=base_year).first()
    if base is None:
        raise MTEFError(f'There is no MTEF for {base_year} to roll forward from. Enter the budget year first.')
    growth = {k: Decimal(str(v)) for k, v in (growth or {}).items() if v not in (None, '')}
    default = Decimal(base.inflation_assumption)
    rate = {
        **{n: growth.get('revenue_growth_pct', default) for n in MTEFProjection.REVENUE_FIELDS},
        'exp_debt_service': growth.get('debt_service_growth_pct', default),
        'exp_personnel': growth.get('personnel_growth_pct', default),
        'exp_overhead': growth.get('overhead_growth_pct', default),
        'exp_other_recurrent': growth.get('overhead_growth_pct', default),
        'exp_capital': growth.get('capital_growth_pct', default),
    }
    result, previous = RollResult(), base
    with transaction.atomic():
        for offset in range(1, HORIZON):
            year = base_year + offset
            existing = MTEFProjection.objects.filter(fiscal_year=year).first()
            if existing is not None:
                result.kept.append(year)
                previous = existing
                continue
            values = {n: _q(getattr(previous, n) * (1 + rate[n] / 100)) for n in rate}
            values.update({n: getattr(previous, n) for n in MTEFProjection.FINANCING_FIELDS})
            values['opening_debt_stock'] = closing_debt(previous)
            values['gdp_assumption'] = _q(previous.gdp_assumption * (1 + growth.get('gdp_growth_pct', default) / 100))
            previous = MTEFProjection.objects.create(
                fiscal_year=year, inflation_assumption=base.inflation_assumption, exchange_rate_assumption=base.exchange_rate_assumption,
                oil_price_assumption=base.oil_price_assumption, oil_sensitivity=base.oil_sensitivity,
                notes=f'Rolled forward from {base_year}.', **values)
            result.created.append(year)
    return result


def approve(p: MTEFProjection, *, override_reason: str = '', actor_name: str = '') -> list[Finding]:
    """Approve a year. A rule failure blocks it unless a reason is given, which is kept as the record of why it went ahead."""
    if p.status == 'approved':
        raise MTEFError(f'The {p.fiscal_year} MTEF is already approved.')
    policy = get_policy()
    previous = MTEFProjection.objects.filter(fiscal_year=p.fiscal_year - 1).first()
    findings = assess_year(p, policy, previous=previous, outturn=prior_outturn(p.fiscal_year))
    failing = [f for f in findings if f.status == FAIL]
    reason = (override_reason or '').strip()
    if failing and not reason:
        raise MTEFError(f'The {p.fiscal_year} MTEF breaks {len(failing)} fiscal rule(s): '
                        + '; '.join(f.rule for f in failing) + '. Fix them, or give a reason to approve anyway.', findings=findings)
    p.status, p.approved_by, p.approved_at = 'approved', actor_name[:200], timezone.now()
    p.override_reason = reason if failing else ''
    p.save()
    return findings


def reopen(p: MTEFProjection, *, reason: str) -> None:
    if p.status != 'approved':
        raise MTEFError('Only an approved MTEF needs reopening.')
    if not (reason or '').strip():
        raise MTEFError('Give a reason for reopening an approved MTEF; it is kept on the record.')
    p.notes = f'{p.notes}\nReopened {timezone.localdate():%d/%m/%Y}: {reason.strip()}'.strip()
    p.status, p.approved_by, p.approved_at, p.override_reason = 'draft', '', None, ''
    p.save()
