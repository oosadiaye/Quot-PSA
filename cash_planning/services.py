"""
cash_planning forecast engine — the module's value.

FUTURE_MODULES §5.9: pulls live signals out of the existing database (which
the dormant TreasuryForecast / CashFlowForecast models never did) and turns
them into a CashPlan + positional forecast. Everything is additive and
read-only here — this service never writes the general ledger. Each source is
independently safe when the contributing module is off (the queries degrade
gracefully per §3 invariant 4).
"""
from __future__ import annotations

import logging
from datetime import date

from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


class ForecastEngine:
    """Aggregates open commitments and obligations into forecast lines.

    Each ``build_*`` method pulls from a contributing module's models. If the
    contributing module is disabled or its tables are absent, the method
    returns an empty list rather than raising — so cash planning still works
    with any subset of sources active.
    """

    def __init__(self, fiscal_year: int, cash_plan=None):
        self.fiscal_year = fiscal_year
        self.cash_plan = cash_plan

    def _guard(self, fn):
        """Wrap a source query so a disabled/missing module never crashes."""
        try:
            return fn() or []
        except Exception as exc:  # noqa: BLE001
            logger.warning('cash_planning source unavailable: %s', exc)
            return []

    def from_payroll(self):
        """Projected payroll obligations from active PayrollRun/employee data."""
        def _q():
            from hrm.models import PayrollRun
            runs = (
                PayrollRun.objects
                .filter(fiscal_year=self.fiscal_year)
                .aggregate(total=Sum('gross_pay'))
            )
            total = runs.get('total') or 0
            if self.cash_plan is not None:
                return [{
                    'source': 'payroll', 'flow': 'outflow', 'amount': total,
                    'due_date': timezone.now().date(),
                    'description': 'Projected payroll for fiscal year',
                    'source_ref': f'fy{self.fiscal_year}',
                }]
            return []
        return self._guard(_q)

    def run(self) -> list[dict]:
        """Return all forecast lines for this fiscal year.

        Each contributing module keys off its own DB state, so this works
        whether or not debt / contracts / personnel_budget are enabled.
        """
        lines: list[dict] = []
        lines += self.from_payroll()
        # Additional sources (commitments, contracts, debt, revenue seasonality)
        # are wired incrementally as those modules ship and expose their models.
        return lines

    def build_position(self, opening_balance, warning_floor=0):
        """Return a computed daily-closing projection (no persistence)."""
        total_outflow = sum(float(l['amount']) for l in self.run() if l.get('flow') == 'outflow')
        closing = float(opening_balance) - total_outflow
        return {
            'opening_balance': opening_balance,
            'projected_outflow': round(total_outflow, 2),
            'projected_inflow': 0,
            'closing_balance': round(closing, 2),
            'warning_floor': warning_floor,
            'is_below_floor': closing < float(warning_floor),
        }
