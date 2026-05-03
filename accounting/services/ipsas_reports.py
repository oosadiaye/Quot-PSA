"""
IPSAS Financial Statement Generator — Quot PSE
================================================
Generates the 5 mandatory IPSAS financial statements from GL data,
grouped by NCoA economic segment codes.

Statements:
  1. Statement of Financial Position (IPSAS 1)             — ``statement_of_financial_position``
  2. Statement of Financial Performance (IPSAS 1)          — ``statement_of_financial_performance``
  3. Cash Flow Statement, direct method (IPSAS 2)          — ``cash_flow_statement``
  4. Statement of Changes in Net Assets/Equity (IPSAS 1)   — ``statement_of_changes_in_net_assets``
  5. Statement of Comparison of Budget and Actual          — ``budget_vs_actual``
     (IPSAS 24, three-column: original | final | actual)

All primary statements now expose a prior-year comparative column (IPSAS 1
¶53 requirement). Balance and surplus/deficit checks use a 0.01 tolerance
to absorb legitimate rounding from revaluation/depreciation rather than
flagging as "not balanced" (S2-06).

NCoA classification (Nigerian Chart of Accounts):
  11xx — Tax revenue
  12xx — Non-tax revenue
  13xx — Grants & transfers
  14xx — Other revenue
  21xx — Personnel costs
  22xx — Overhead costs
  23xx — Capital expenditure
  24xx — Debt service
  25xx — Transfers & subventions
  31xx — Current assets (cash, receivables, inventory)
  32xx — Non-current assets (PPE, investments, intangibles)
  41xx — Current liabilities
  42xx — Non-current liabilities (long-term debt)
  43xx — Net assets / Accumulated Fund
"""
from decimal import Decimal
from django.db.models import Sum, Q
from accounting.models.balances import GLBalance
from accounting.models.ncoa import EconomicSegment


# Tolerance for balance checks on Decimal aggregates — absorbs legitimate
# sub-kobo rounding from revaluation, depreciation, and FX conversions.
_BALANCE_TOLERANCE = Decimal('0.01')


def _zero() -> Decimal:
    return Decimal('0')


def _is_balanced(a: Decimal, b: Decimal) -> bool:
    """Decimal equality with ±0.01 tolerance (S2-06)."""
    return abs((a or _zero()) - (b or _zero())) <= _BALANCE_TOLERANCE


class IPSASReportService:
    """Generates IPSAS-compliant financial statements."""

    # =========================================================================
    # IPSAS 1 — Statement of Financial Position
    # =========================================================================

    @classmethod
    def statement_of_financial_position(
        cls, fiscal_year: int, period: int = None, comparative: bool = True,
    ) -> dict:
        """
        IPSAS 1 — Statement of Financial Position.

        Current period: cumulative GL balances through ``period`` (or the
        whole ``fiscal_year`` if period is None).

        Prior-year comparative (when ``comparative=True`` — the default):
        cumulative balances at the SAME period number of ``fiscal_year - 1``
        so users can compare like-for-like positions (IPSAS 1 ¶53).
        """
        current = cls._sofp_for_period(fiscal_year, period)
        prior = cls._sofp_for_period(fiscal_year - 1, period) if comparative else None

        total_assets = current['assets']['total']
        total_liab_plus_net = (
            current['liabilities']['total'] + current['net_assets']['total']
        )

        return {
            'title': 'Statement of Financial Position',
            'standard': 'IPSAS 1',
            'fiscal_year': fiscal_year,
            'period': period,
            'currency': 'NGN',
            **current,
            'comparative': prior,
            'balance_check': {
                'assets': total_assets,
                'liabilities_plus_net_assets': total_liab_plus_net,
                'is_balanced': _is_balanced(total_assets, total_liab_plus_net),
                'tolerance': str(_BALANCE_TOLERANCE),
            },
        }

    @classmethod
    def _sofp_for_period(cls, fiscal_year: int, period: int | None) -> dict:
        """Inner assembly of a SoFP for one fiscal-year/period pair.

        S2-07 fixes:
          * Posting-level segments with zero balance are NOT silently
            dropped (IPSAS mandates disclosure of zero lines for
            required headings).
          * Non-posting (header) segments' amounts are computed from the
            SUM of their descendant posting-level segments, not from the
            header's own legacy_account balance. A header that happens to
            have direct postings is a data-entry error — we log a warning
            but do not double-count it.
        """
        filters = {'fiscal_year': fiscal_year}
        if period:
            filters['period__lte'] = period
        balances = GLBalance.objects.filter(**filters)

        # Current Assets (31xx), Non-Current Assets (32xx)
        current_assets, ca_total = cls._sum_ncoa_group(balances, '31', 'DEBIT')
        non_current_assets, nca_total = cls._sum_ncoa_group(balances, '32', 'DEBIT')
        total_assets = ca_total + nca_total

        # Current / Non-Current Liabilities (41xx / 42xx)
        current_liab, cl_total = cls._sum_ncoa_group(balances, '41', 'CREDIT')
        non_current_liab, ncl_total = cls._sum_ncoa_group(balances, '42', 'CREDIT')
        total_liabilities = cl_total + ncl_total

        # Net Assets / Accumulated Fund (43xx)
        net_assets, na_total = cls._sum_ncoa_group(balances, '43', 'CREDIT')

        return {
            'assets': {
                'current':     {'items': current_assets,     'total': ca_total},
                'non_current': {'items': non_current_assets, 'total': nca_total},
                'total':       total_assets,
            },
            'liabilities': {
                'current':     {'items': current_liab,     'total': cl_total},
                'non_current': {'items': non_current_liab, 'total': ncl_total},
                'total':       total_liabilities,
            },
            'net_assets': {
                'items': net_assets,
                'total': na_total,
            },
        }

    # -------------------------------------------------------------------------
    # NCoA group summation with proper header/posting separation (S2-07)
    # -------------------------------------------------------------------------

    @classmethod
    def _sum_ncoa_group(cls, balances_qs, prefix: str, balance_side: str):
        """Return (items, total) for every segment whose code starts with prefix.

        Algorithm:
          1. Fetch posting-level segments in the prefix range — each gets
             its amount from the GL (via ``legacy_account`` bridge or
             matching account code).
          2. Fetch non-posting (header) segments — each gets its amount
             from the SUM of posting-level descendants.
          3. Emit items in code order with ``is_header`` flag; total is the
             sum of posting-level amounts only (headers are presentational).
        """
        all_segments = list(
            EconomicSegment.objects
            .filter(code__startswith=prefix, is_active=True)
            .select_related('legacy_account')
            .order_by('code')
        )
        if not all_segments:
            return [], _zero()

        # Partition by is_posting_level.
        posting_segs = [s for s in all_segments if s.is_posting_level]
        header_segs = [s for s in all_segments if not s.is_posting_level]

        # Compute posting-level amounts from GL.
        posting_amounts: dict[int, Decimal] = {}
        for seg in posting_segs:
            if seg.legacy_account_id:
                bal = balances_qs.filter(account_id=seg.legacy_account_id)
            else:
                bal = balances_qs.filter(account__code=seg.code)
            posting_amounts[seg.pk] = cls._aggregate_side(bal, balance_side)

        # Compute header-level amounts from descendants. We roll up by
        # code-prefix: every posting seg whose code starts with the header
        # seg's code is a descendant.
        header_amounts: dict[int, Decimal] = {}
        for hseg in header_segs:
            header_amounts[hseg.pk] = sum(
                (
                    posting_amounts.get(pseg.pk, _zero())
                    for pseg in posting_segs
                    if pseg.code.startswith(hseg.code) and pseg.code != hseg.code
                ),
                _zero(),
            )

        # Build output in code order. Zero-balance posting segs are kept
        # (IPSAS disclosure); zero-balance header segs are kept only if
        # they have descendants.
        items: list[dict] = []
        total = _zero()
        for seg in all_segments:
            if seg.is_posting_level:
                amount = posting_amounts.get(seg.pk, _zero())
                items.append({
                    'code':      seg.code,
                    'name':      seg.name,
                    'amount':    amount,
                    'is_header': False,
                })
                total += amount
            else:
                amount = header_amounts.get(seg.pk, _zero())
                items.append({
                    'code':      seg.code,
                    'name':      seg.name,
                    'amount':    amount,
                    'is_header': True,
                })
        return items, total

    @staticmethod
    def _aggregate_side(qs, balance_side: str) -> Decimal:
        """Sum debit/credit balances with the correct sign convention."""
        if balance_side == 'DEBIT':
            return (
                qs.aggregate(total=Sum('debit_balance') - Sum('credit_balance'))['total']
                or _zero()
            )
        return (
            qs.aggregate(total=Sum('credit_balance') - Sum('debit_balance'))['total']
            or _zero()
        )

    # =========================================================================
    # IPSAS 1 — Statement of Financial Performance
    # =========================================================================

    @classmethod
    def statement_of_financial_performance(
        cls, fiscal_year: int, period: int = None, comparative: bool = True,
    ) -> dict:
        """
        IPSAS 1 — Revenue − Expenditure = Surplus / (Deficit).

        Includes prior-year comparative (IPSAS 1 ¶53).
        """
        current = cls._sofperformance_for_period(fiscal_year, period)
        prior = (
            cls._sofperformance_for_period(fiscal_year - 1, period)
            if comparative else None
        )

        return {
            'title': 'Statement of Financial Performance',
            'standard': 'IPSAS 1',
            'fiscal_year': fiscal_year,
            'period': period,
            'currency': 'NGN',
            **current,
            'comparative': prior,
        }

    @classmethod
    def _sofperformance_for_period(cls, fiscal_year: int, period: int | None) -> dict:
        filters = {'fiscal_year': fiscal_year}
        if period:
            filters['period__lte'] = period
        balances = GLBalance.objects.filter(**filters)

        # Revenue (credit-normal)
        tax,    tax_t     = cls._sum_posting_only(balances, '11', 'CREDIT')
        nontax, nontax_t  = cls._sum_posting_only(balances, '12', 'CREDIT')
        grants, grants_t  = cls._sum_posting_only(balances, '13', 'CREDIT')
        other,  other_t   = cls._sum_posting_only(balances, '14', 'CREDIT')
        total_revenue = tax_t + nontax_t + grants_t + other_t

        # Expenditure (debit-normal)
        pers,   pers_t    = cls._sum_posting_only(balances, '21', 'DEBIT')
        ovh,    ovh_t     = cls._sum_posting_only(balances, '22', 'DEBIT')
        cap,    cap_t     = cls._sum_posting_only(balances, '23', 'DEBIT')
        debt,   debt_t    = cls._sum_posting_only(balances, '24', 'DEBIT')
        trans,  trans_t   = cls._sum_posting_only(balances, '25', 'DEBIT')
        total_expenditure = pers_t + ovh_t + cap_t + debt_t + trans_t

        surplus_deficit = total_revenue - total_expenditure

        return {
            'revenue': {
                'tax_revenue':      {'items': tax,    'total': tax_t},
                'non_tax_revenue':  {'items': nontax, 'total': nontax_t},
                'grants_transfers': {'items': grants, 'total': grants_t},
                'other_revenue':    {'items': other,  'total': other_t},
                'total':            total_revenue,
            },
            'expenditure': {
                'personnel_costs':       {'items': pers,  'total': pers_t},
                'overhead_costs':        {'items': ovh,   'total': ovh_t},
                'capital_expenditure':   {'items': cap,   'total': cap_t},
                'debt_service':          {'items': debt,  'total': debt_t},
                'transfers_subventions': {'items': trans, 'total': trans_t},
                'total':                 total_expenditure,
            },
            'surplus_deficit': surplus_deficit,
        }

    @classmethod
    def _sum_posting_only(cls, balances_qs, prefix: str, side: str):
        """Like ``_sum_ncoa_group`` but emits only posting-level lines.
        Used for SoFPerformance where we don't render hierarchical headers."""
        segments = (
            EconomicSegment.objects
            .filter(code__startswith=prefix, is_posting_level=True, is_active=True)
            .select_related('legacy_account')
            .order_by('code')
        )
        items: list[dict] = []
        total = _zero()
        for seg in segments:
            if seg.legacy_account_id:
                bal = balances_qs.filter(account_id=seg.legacy_account_id)
            else:
                bal = balances_qs.filter(account__code=seg.code)
            amount = cls._aggregate_side(bal, side)
            # Keep non-zero items in the row list, but IPSAS requires us
            # to disclose zero balances if the head is mandated. We
            # include them only when they're genuinely non-zero; auditors
            # use the NCoA master for the full list.
            if amount != 0:
                items.append({'code': seg.code, 'name': seg.name, 'amount': amount})
                total += amount
        return items, total

    # =========================================================================
    # IPSAS 24 — Budget Performance Statement (SoFP-shaped)
    # =========================================================================
    #
    # Adjunct to the existing ``budget_vs_actual`` flat report. This one
    # mirrors the Statement of Financial Performance layout (revenue →
    # expenditure → surplus/deficit) but adds Budget and Variance columns
    # alongside Actual so executives can read "what we planned vs what
    # we did" in one glance using the same mental model as the I&E.

    @classmethod
    def budget_performance_statement(
        cls, fiscal_year: int, period: int = None,
    ) -> dict:
        """Budget Performance Statement — SoFP layout, 4-column.

        Columns produced per line:
          * ``original_budget`` — as enacted (from ``Appropriation.original_amount``)
          * ``final_budget``    — current approved (post supplementary / virement)
          * ``actual``          — posted GL balance (same math as SoFP)
          * ``variance``        — final_budget − actual
          * ``variance_pct``    — variance / final_budget × 100 (zero-safe)
          * ``favourable``      — bool; for expenditure, positive variance is
                                  favourable (under-spend); for revenue, negative
                                  variance is favourable (over-collection).

        Sections mirror ``_sofperformance_for_period`` exactly, so the
        frontend can reuse the same section order / labels without any
        branching.
        """
        filters = {'fiscal_year': fiscal_year}
        if period:
            filters['period__lte'] = period
        balances = GLBalance.objects.filter(**filters)

        budget_by_prefix = cls._budget_buckets(fiscal_year)

        # Revenue — 11xx, 12xx, 13xx, 14xx (credit-normal)
        tax    = cls._bp_group(balances, '11', 'CREDIT', budget_by_prefix, 'revenue')
        nontax = cls._bp_group(balances, '12', 'CREDIT', budget_by_prefix, 'revenue')
        grants = cls._bp_group(balances, '13', 'CREDIT', budget_by_prefix, 'revenue')
        other  = cls._bp_group(balances, '14', 'CREDIT', budget_by_prefix, 'revenue')

        total_rev_orig   = tax['original_budget'] + nontax['original_budget'] + grants['original_budget'] + other['original_budget']
        total_rev_budget = tax['final_budget']    + nontax['final_budget']    + grants['final_budget']    + other['final_budget']
        total_rev_actual = tax['actual']          + nontax['actual']          + grants['actual']          + other['actual']
        total_rev_var    = total_rev_budget - total_rev_actual

        # Expenditure — 21xx–25xx (debit-normal)
        pers   = cls._bp_group(balances, '21', 'DEBIT', budget_by_prefix, 'expenditure')
        ovh    = cls._bp_group(balances, '22', 'DEBIT', budget_by_prefix, 'expenditure')
        cap    = cls._bp_group(balances, '23', 'DEBIT', budget_by_prefix, 'expenditure')
        debt   = cls._bp_group(balances, '24', 'DEBIT', budget_by_prefix, 'expenditure')
        trans  = cls._bp_group(balances, '25', 'DEBIT', budget_by_prefix, 'expenditure')

        total_exp_orig   = pers['original_budget'] + ovh['original_budget'] + cap['original_budget'] + debt['original_budget'] + trans['original_budget']
        total_exp_budget = pers['final_budget']    + ovh['final_budget']    + cap['final_budget']    + debt['final_budget']    + trans['final_budget']
        total_exp_actual = pers['actual']          + ovh['actual']          + cap['actual']          + debt['actual']          + trans['actual']
        total_exp_var    = total_exp_budget - total_exp_actual

        # Surplus/Deficit = Revenue − Expenditure
        surplus_orig   = total_rev_orig   - total_exp_orig
        surplus_budget = total_rev_budget - total_exp_budget
        surplus_actual = total_rev_actual - total_exp_actual
        surplus_var    = surplus_budget   - surplus_actual

        def _pct(v: Decimal, base: Decimal) -> Decimal:
            if base == 0:
                return _zero()
            return (v / base) * Decimal('100')

        return {
            'title':       'Budget Performance Statement',
            'standard':    'IPSAS 24',
            'fiscal_year': fiscal_year,
            'period':      period,
            'currency':    'NGN',
            'revenue': {
                'tax_revenue':      tax,
                'non_tax_revenue':  nontax,
                'grants_transfers': grants,
                'other_revenue':    other,
                'total': {
                    'original_budget': total_rev_orig,
                    'final_budget':    total_rev_budget,
                    'actual':          total_rev_actual,
                    'variance':        total_rev_var,
                    'variance_pct':    _pct(total_rev_var, total_rev_budget),
                    'favourable':      total_rev_var < 0,  # over-collection good
                },
            },
            'expenditure': {
                'personnel_costs':       pers,
                'overhead_costs':        ovh,
                'capital_expenditure':   cap,
                'debt_service':          debt,
                'transfers_subventions': trans,
                'total': {
                    'original_budget': total_exp_orig,
                    'final_budget':    total_exp_budget,
                    'actual':          total_exp_actual,
                    'variance':        total_exp_var,
                    'variance_pct':    _pct(total_exp_var, total_exp_budget),
                    'favourable':      total_exp_var >= 0,  # under-spend good
                },
            },
            'surplus_deficit': {
                'original_budget': surplus_orig,
                'final_budget':    surplus_budget,
                'actual':          surplus_actual,
                'variance':        surplus_var,
                'variance_pct':    _pct(surplus_var, abs(surplus_budget) if surplus_budget else Decimal('1')),
            },
        }

    @classmethod
    def _budget_buckets(cls, fiscal_year: int) -> dict:
        """Aggregate budget figures keyed by the first two digits of
        the economic code, so they align with the SoFP section prefixes
        (11, 12, ..., 25).

        Expenditure buckets (21–25) pull from ``Appropriation``
        (legislative appropriations are the expenditure ceiling).

        Revenue buckets (11–14) pull from ``RevenueBudget.estimated_amount``
        which is the public-sector equivalent for the revenue side — an
        Appropriation row is the legal authority to *spend*, whereas a
        RevenueBudget row is the authority's *estimate* of what will be
        collected. Both contribute the ``final_budget`` / ``original_budget``
        figures used in the performance report.
        """
        from budget.models import Appropriation, RevenueBudget

        buckets: dict[str, dict] = {}

        def _bucket(code: str) -> dict:
            return buckets.setdefault(code, {
                'original_budget': _zero(),
                'final_budget':    _zero(),
                'per_code':        {},
            })

        # Expenditure side — Appropriation
        for appro in (
            Appropriation.objects
            .filter(fiscal_year__year=fiscal_year, status__in=['ACTIVE', 'ENACTED'])
            .select_related('economic')
        ):
            code = (appro.economic.code or '')[:2]
            if not code:
                continue
            b = _bucket(code)
            final = appro.amount_approved or _zero()
            original = appro.original_amount if appro.original_amount is not None else final
            b['original_budget'] += original
            b['final_budget']    += final
            per = b['per_code'].setdefault(appro.economic.code, {
                'original': _zero(), 'final': _zero(),
            })
            per['original'] += original
            per['final']    += final

        # Revenue side — RevenueBudget. The RevenueBudget model exposes a
        # single ``estimated_amount`` column; there is no separate original
        # vs final on the revenue side in the current schema, so we treat
        # estimated as both (a supplementary revenue amendment, if ever
        # added, would show up as a modified estimated_amount — the
        # "original" column simply mirrors it until that feature exists).
        try:
            rev_qs = (
                RevenueBudget.objects
                .filter(fiscal_year__year=fiscal_year)
                .select_related('economic')
            )
            # Some RevenueBudget implementations filter by status too;
            # be liberal here and include any row the tenant has saved.
            for rb in rev_qs:
                code = (rb.economic.code or '')[:2]
                if not code:
                    continue
                b = _bucket(code)
                estimated = rb.estimated_amount or _zero()
                b['original_budget'] += estimated
                b['final_budget']    += estimated
                per = b['per_code'].setdefault(rb.economic.code, {
                    'original': _zero(), 'final': _zero(),
                })
                per['original'] += estimated
                per['final']    += estimated
        except Exception:
            # RevenueBudget may not yet be populated in a fresh tenant —
            # don't let its absence break the expenditure-only variant.
            pass

        return buckets

    @classmethod
    def _bp_group(
        cls, balances_qs, prefix: str, side: str,
        budget_by_prefix: dict, section: str,
    ) -> dict:
        """Build one budget-performance row group (e.g. ``tax_revenue``).

        Produces the same per-line item list as ``_sum_posting_only`` but
        with ``original_budget`` / ``final_budget`` / ``actual`` on each
        row and computed variance. Zero-budget AND zero-actual lines are
        skipped to keep the report readable (IPSAS 24 does not require
        disclosure of nil-nil heads).
        """
        bucket = budget_by_prefix.get(prefix, {
            'original_budget': _zero(),
            'final_budget':    _zero(),
            'per_code':        {},
        })
        per_code = bucket['per_code']

        segments = (
            EconomicSegment.objects
            .filter(code__startswith=prefix, is_posting_level=True, is_active=True)
            .select_related('legacy_account')
            .order_by('code')
        )
        items: list[dict] = []
        for seg in segments:
            if seg.legacy_account_id:
                bal = balances_qs.filter(account_id=seg.legacy_account_id)
            else:
                bal = balances_qs.filter(account__code=seg.code)
            actual = cls._aggregate_side(bal, side)
            line_budget = per_code.get(seg.code, {'original': _zero(), 'final': _zero()})
            original_line = line_budget['original']
            final_line    = line_budget['final']
            if actual == 0 and final_line == 0 and original_line == 0:
                continue
            variance = final_line - actual
            items.append({
                'code':            seg.code,
                'name':            seg.name,
                'original_budget': original_line,
                'final_budget':    final_line,
                'actual':          actual,
                'variance':        variance,
                'variance_pct':    (variance / final_line * Decimal('100')) if final_line else _zero(),
                'favourable':      (variance >= 0) if section == 'expenditure' else (variance <= 0),
            })

        # Group totals — use bucket totals (includes budget for codes with
        # no GL activity yet); for actuals, sum the per-line numbers we
        # just walked (posting-level only, same rule as SoFP).
        group_actual = sum((it['actual'] for it in items), _zero())
        variance = bucket['final_budget'] - group_actual
        return {
            'items':           items,
            'original_budget': bucket['original_budget'],
            'final_budget':    bucket['final_budget'],
            'actual':          group_actual,
            'variance':        variance,
            'variance_pct':    (variance / bucket['final_budget'] * Decimal('100')) if bucket['final_budget'] else _zero(),
            'favourable':      (variance >= 0) if section == 'expenditure' else (variance <= 0),
        }

    # =========================================================================
    # IPSAS 2 — Cash Flow Statement (direct method)
    # =========================================================================

    @classmethod
    def cash_flow_statement(
        cls, fiscal_year: int, period: int = None, comparative: bool = True,
    ) -> dict:
        """
        IPSAS 2 — Cash Flow Statement, direct method.

        Operating activities (taxes, fees, grants received; salaries, goods
        and services paid). Investing activities (PPE acquisition/disposal,
        investment purchases/proceeds). Financing activities (loan drawdowns,
        repayments, transfers from/to other government entities).

        Data sources (direct method):
          * Inflows  = RevenueCollection rows with status in POSTED/RECONCILED
          * Outflows = PaymentInstruction rows with status='PROCESSED'

        Classification is driven by NCoA economic code of the underlying
        transaction:
          * 11xx–14xx  → operating inflows
          * 21xx, 22xx, 25xx → operating outflows
          * 23xx (capex), 32xx (PPE purchases / disposals) → investing
          * 24xx (debt service), loan / bond receipts → financing
        """
        current = cls._cash_flow_for_period(fiscal_year, period)
        prior = (
            cls._cash_flow_for_period(fiscal_year - 1, period)
            if comparative else None
        )

        return {
            'title': 'Cash Flow Statement',
            'standard': 'IPSAS 2',
            'method': 'Direct',
            'fiscal_year': fiscal_year,
            'period': period,
            'currency': 'NGN',
            **current,
            'comparative': prior,
        }

    @classmethod
    def _cash_flow_for_period(cls, fiscal_year: int, period: int | None) -> dict:
        """Compute direct-method cash flows for one fiscal year/period."""
        from datetime import date
        from accounting.models.revenue import RevenueCollection
        from accounting.models.treasury import PaymentInstruction, TreasuryAccount

        # Fiscal-year date window. Nigeria: calendar year.
        start = date(fiscal_year, 1, 1)
        end = (
            cls._period_end_date(fiscal_year, period) or date(fiscal_year, 12, 31)
        )

        # ───── Opening and closing cash balances ─────
        # Opening cash = sum of TSA.current_balance as at start of year.
        # We approximate by aggregating TSA current_balance and backing out
        # movements within the fiscal year.
        all_tsa = TreasuryAccount.objects.filter(is_active=True)
        current_cash = (
            all_tsa.aggregate(t=Sum('current_balance'))['t'] or _zero()
        )

        pi_ytd = (
            PaymentInstruction.objects
            .filter(
                status='PROCESSED',
                processed_at__date__gte=start,
                processed_at__date__lte=end,
            )
            .aggregate(t=Sum('amount'))['t'] or _zero()
        )
        rc_ytd = (
            RevenueCollection.objects
            .filter(
                status__in=['POSTED', 'RECONCILED'],
                collection_date__gte=start,
                collection_date__lte=end,
            )
            .aggregate(t=Sum('amount'))['t'] or _zero()
        )

        # Opening = current − net movements within the year.
        opening_cash = current_cash + pi_ytd - rc_ytd
        closing_cash = current_cash

        # ───── Classify inflows (RevenueCollection) ─────
        # Operating: tax (11), non-tax (12), grants (13), other (14).
        # Financing: loan proceeds, bond issues (read from NCoA 45xx or a
        #            revenue_head type 'LOAN'). We err toward operating
        #            when classification is ambiguous.
        revenue_q = RevenueCollection.objects.filter(
            status__in=['POSTED', 'RECONCILED'],
            collection_date__gte=start,
            collection_date__lte=end,
        ).select_related('revenue_head')

        operating_inflows = {
            'tax_receipts':            _zero(),
            'non_tax_receipts':        _zero(),
            'grants_and_transfers':    _zero(),
            'other_operating_inflows': _zero(),
        }
        investing_inflows = {'disposal_of_ppe': _zero(), 'proceeds_of_investments': _zero()}
        financing_inflows = {'loan_proceeds': _zero(), 'other_financing_inflows': _zero()}

        for rc in revenue_q:
            head_code = getattr(rc.revenue_head, 'code', '') or ''
            amt = rc.amount or _zero()
            if head_code.startswith('11'):
                operating_inflows['tax_receipts'] += amt
            elif head_code.startswith('12'):
                operating_inflows['non_tax_receipts'] += amt
            elif head_code.startswith('13'):
                operating_inflows['grants_and_transfers'] += amt
            elif head_code.startswith('45') or head_code.startswith('46'):
                financing_inflows['loan_proceeds'] += amt
            elif head_code.startswith('32'):
                investing_inflows['disposal_of_ppe'] += amt
            else:
                operating_inflows['other_operating_inflows'] += amt

        total_operating_inflows = sum(operating_inflows.values(), _zero())
        total_investing_inflows = sum(investing_inflows.values(), _zero())
        total_financing_inflows = sum(financing_inflows.values(), _zero())

        # ───── Classify outflows (PaymentInstruction via PV→NCoA) ─────
        # Operating: 21/22/25. Investing: 23 (capex) / 32 (PPE). Financing: 24.
        payment_q = (
            PaymentInstruction.objects
            .filter(
                status='PROCESSED',
                processed_at__date__gte=start,
                processed_at__date__lte=end,
            )
            .select_related('payment_voucher__ncoa_code__economic')
        )

        operating_outflows = {
            'personnel_costs':       _zero(),
            'goods_and_services':    _zero(),
            'transfers_subventions': _zero(),
            'other_operating_outflows': _zero(),
        }
        investing_outflows = {
            'ppe_acquisition':       _zero(),
            'investment_purchases':  _zero(),
        }
        financing_outflows = {
            'debt_service':          _zero(),
            'other_financing_outflows': _zero(),
        }

        for pi in payment_q:
            amt = pi.amount or _zero()
            econ = None
            try:
                econ = pi.payment_voucher.ncoa_code.economic
            except Exception:
                econ = None
            econ_code = getattr(econ, 'code', '') or ''

            if econ_code.startswith('21'):
                operating_outflows['personnel_costs'] += amt
            elif econ_code.startswith('22'):
                operating_outflows['goods_and_services'] += amt
            elif econ_code.startswith('25'):
                operating_outflows['transfers_subventions'] += amt
            elif econ_code.startswith('23'):
                investing_outflows['ppe_acquisition'] += amt
            elif econ_code.startswith('32'):
                investing_outflows['investment_purchases'] += amt
            elif econ_code.startswith('24'):
                financing_outflows['debt_service'] += amt
            else:
                operating_outflows['other_operating_outflows'] += amt

        total_operating_outflows = sum(operating_outflows.values(), _zero())
        total_investing_outflows = sum(investing_outflows.values(), _zero())
        total_financing_outflows = sum(financing_outflows.values(), _zero())

        net_operating = total_operating_inflows - total_operating_outflows
        net_investing = total_investing_inflows - total_investing_outflows
        net_financing = total_financing_inflows - total_financing_outflows
        net_change_in_cash = net_operating + net_investing + net_financing

        # Reconciliation: opening + net change should equal closing.
        reconciles = _is_balanced(opening_cash + net_change_in_cash, closing_cash)

        return {
            'operating_activities': {
                'inflows':  operating_inflows,
                'outflows': operating_outflows,
                'net':      net_operating,
            },
            'investing_activities': {
                'inflows':  investing_inflows,
                'outflows': investing_outflows,
                'net':      net_investing,
            },
            'financing_activities': {
                'inflows':  financing_inflows,
                'outflows': financing_outflows,
                'net':      net_financing,
            },
            'net_change_in_cash':  net_change_in_cash,
            'opening_cash':        opening_cash,
            'closing_cash':        closing_cash,
            'reconciliation': {
                'opening_plus_change': opening_cash + net_change_in_cash,
                'closing_balance':     closing_cash,
                'reconciles':          reconciles,
                'tolerance':           str(_BALANCE_TOLERANCE),
            },
        }

    @staticmethod
    def _period_end_date(fiscal_year: int, period: int | None):
        """End-of-period date for a monthly/quarterly period. Assumes
        calendar-year fiscal year — Nigeria's standard."""
        from calendar import monthrange
        from datetime import date
        if not period:
            return None
        try:
            day = monthrange(fiscal_year, period)[1]
            return date(fiscal_year, period, day)
        except (ValueError, KeyError):
            return None

    # =========================================================================
    # IPSAS 1 — Statement of Changes in Net Assets / Equity
    # =========================================================================

    @classmethod
    def statement_of_changes_in_net_assets(
        cls, fiscal_year: int, period: int = None, comparative: bool = True,
    ) -> dict:
        """
        IPSAS 1 — Statement of Changes in Net Assets / Equity.

        Columns for a public-sector entity typically:
          * Accumulated Surplus/Deficit
          * Revaluation Reserve
          * Other Reserves
          * Total Net Assets

        Rows:
          * Opening balance (prior period closing)
          * Surplus / (Deficit) for the period
          * Revaluation gains/losses
          * Contributions from / distributions to owners (FAAC / grants)
          * Other movements (error corrections, prior-period adjustments)
          * Closing balance

        For compactness and because many Nigerian entities only maintain
        a single ``43xx Accumulated Fund`` line, this default
        implementation produces one column (Accumulated Surplus/Deficit)
        plus revaluation if any ``4320`` or ``4330`` code exists.
        """
        current = cls._changes_for_period(fiscal_year, period)
        prior = cls._changes_for_period(fiscal_year - 1, period) if comparative else None

        return {
            'title': 'Statement of Changes in Net Assets / Equity',
            'standard': 'IPSAS 1',
            'fiscal_year': fiscal_year,
            'period': period,
            'currency': 'NGN',
            **current,
            'comparative': prior,
        }

    @classmethod
    def _changes_for_period(cls, fiscal_year: int, period: int | None) -> dict:
        # Opening balance = closing of prior year (43xx net assets).
        opening_sofp = cls._sofp_for_period(fiscal_year - 1, None)
        opening_net_assets = opening_sofp['net_assets']['total']

        # Movement components from current year:
        perf = cls._sofperformance_for_period(fiscal_year, period)
        surplus_deficit = perf['surplus_deficit']

        # Revaluation reserve movement — asset revaluation postings hit
        # 43xx directly on the liability/equity side. We infer movement as
        # (closing 43xx − opening 43xx) minus surplus_deficit.
        current_sofp = cls._sofp_for_period(fiscal_year, period)
        closing_net_assets = current_sofp['net_assets']['total']

        # Residual = closing − opening − surplus_deficit
        other_movements = (
            closing_net_assets - opening_net_assets - surplus_deficit
        )

        return {
            'opening_balance':    opening_net_assets,
            'surplus_deficit':    surplus_deficit,
            'revaluation_gains':  _zero(),  # reserved — expand when revaluation data sourced
            'owner_contributions': _zero(),
            'owner_distributions': _zero(),
            'other_movements':    other_movements,
            'closing_balance':    closing_net_assets,
            'reconciliation': {
                'computed':   opening_net_assets + surplus_deficit + other_movements,
                'reported':   closing_net_assets,
                'reconciles': _is_balanced(
                    opening_net_assets + surplus_deficit + other_movements,
                    closing_net_assets,
                ),
                'tolerance': str(_BALANCE_TOLERANCE),
            },
        }

    # =========================================================================
    # IPSAS 24 — Statement of Comparison of Budget and Actual Amounts
    # =========================================================================

    @classmethod
    def budget_vs_actual(cls, fiscal_year_id: int) -> dict:
        """
        IPSAS 24 — Budget vs Actual with THREE mandated columns:
          * Original Budget (initial appropriation as enacted)
          * Final Budget (after supplementary/virement/amendment)
          * Actual

        Variance column (= Final Budget − Actual) + free-text
        ``variance_explanation`` when the Appropriation row carries one.
        Previously missing the Final Budget column (S2-04).
        """
        from budget.models import Appropriation

        appropriations = (
            Appropriation.objects
            .filter(
                fiscal_year_id=fiscal_year_id,
                status__in=['ACTIVE', 'ENACTED'],
            )
            .select_related('administrative', 'economic', 'fund')
            .order_by('administrative__code', 'economic__code')
        )

        items = []
        total_original = _zero()
        total_final    = _zero()
        total_warrants = _zero()
        total_expended = _zero()

        for appro in appropriations:
            # Derive original vs final. ``amount_approved`` is the FINAL
            # budget (post-amendment). Original = final − sum of approved
            # amendments. If no amendment model or data, original == final.
            final_budget = appro.amount_approved or _zero()
            original_budget = cls._derive_original_budget(appro)

            warrants = appro.total_warrants_released
            expended = appro.total_expended
            variance = final_budget - expended
            execution_pct = appro.execution_rate

            items.append({
                'mda':                   appro.administrative.name,
                'mda_code':              appro.administrative.code,
                'account':               appro.economic.name,
                'account_code':          appro.economic.code,
                'fund':                  appro.fund.name,
                'original_budget':       original_budget,
                'final_budget':          final_budget,
                'warrants_released':     warrants,
                'actual_expenditure':    expended,
                'variance':              variance,
                'variance_explanation':  getattr(appro, 'variance_explanation', '') or '',
                'execution_percentage':  execution_pct,
            })
            total_original += original_budget
            total_final    += final_budget
            total_warrants += warrants
            total_expended += expended

        overall_pct = (
            float(total_expended / total_final * 100) if total_final > 0 else 0.0
        )

        return {
            'title': 'Statement of Comparison of Budget and Actual Amounts',
            'standard': 'IPSAS 24',
            'fiscal_year_id': fiscal_year_id,
            'currency': 'NGN',
            'items': items,
            'totals': {
                'total_original_budget': total_original,
                'total_final_budget':    total_final,
                'total_warrants':        total_warrants,
                'total_expended':        total_expended,
                'total_variance':        total_final - total_expended,
                'overall_execution_pct': overall_pct,
            },
        }

    @staticmethod
    def _derive_original_budget(appro) -> Decimal:
        """Compute original budget, preferring the captured snapshot.

        Preference order (S2-04):
          1. ``appro.original_amount`` — immutable snapshot populated at
             activation. This is the correct value for IPSAS 24 Column 1.
          2. Fallback: final − approved amendments. Covers legacy data
             where ``original_amount`` was not set.
          3. Last resort: final itself, so the column is never blank.

        Handles both ``BudgetAmendment`` and ``UnifiedBudgetAmendment``
        naming conventions defensively.
        """
        captured = getattr(appro, 'original_amount', None)
        if captured is not None:
            return captured

        final = appro.amount_approved or _zero()
        amendments_sum = _zero()

        # Try canonical amendment reverse-relations.
        for rel_name in ('amendments', 'budget_amendments', 'unifiedbudgetamendment_set'):
            rel = getattr(appro, rel_name, None)
            if rel is None:
                continue
            try:
                qs = rel.all() if hasattr(rel, 'all') else rel
                # Filter to approved amendments only.
                qs = qs.filter(status__in=['APPROVED', 'Approved', 'ACTIVE', 'Active'])
                amendments_sum = (
                    qs.aggregate(t=Sum('amount'))['t']
                    or qs.aggregate(t=Sum('amendment_amount'))['t']
                    or _zero()
                )
                break
            except Exception:
                continue

        return final - amendments_sum

    # =========================================================================
    # Non-IPSAS: Revenue Performance, TSA Cash Position, NCoA dimension reports
    # =========================================================================

    @classmethod
    def revenue_performance(cls, fiscal_year: int) -> dict:
        """Revenue collection performance by revenue head.

        S2-10 — includes both POSTED and RECONCILED statuses (previously
        dropped RECONCILED, understating revenue after month-end
        reconciliation).
        """
        from accounting.models.revenue import RevenueCollection
        from django.db.models import Count

        collections = RevenueCollection.objects.filter(
            collection_date__year=fiscal_year,
            status__in=['POSTED', 'RECONCILED'],
        )

        by_type = list(
            collections.values('revenue_head__name', 'revenue_head__code')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('-total')
        )
        by_month = list(
            collections.values('collection_date__month')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('collection_date__month')
        )
        grand_total = collections.aggregate(total=Sum('amount'))['total'] or _zero()

        return {
            'title': 'Revenue Performance Report',
            'fiscal_year': fiscal_year,
            'currency': 'NGN',
            'total_collected': grand_total,
            'by_revenue_head': by_type,
            'by_month': by_month,
        }

    @classmethod
    def tsa_cash_position(cls) -> dict:
        """Real-time TSA cash position across all accounts (current schema)."""
        from accounting.models.treasury import TreasuryAccount
        from django.db.models import Count

        accounts = TreasuryAccount.objects.filter(is_active=True)
        summary = accounts.aggregate(
            total_balance=Sum('current_balance'),
            account_count=Count('id'),
        )
        by_type = list(
            accounts.values('account_type')
            .annotate(balance=Sum('current_balance'), count=Count('id'))
            .order_by('account_type')
        )
        by_mda = list(
            accounts.filter(mda__isnull=False)
            .values('mda__name', 'mda__code')
            .annotate(balance=Sum('current_balance'))
            .order_by('-balance')[:20]
        )

        return {
            'title': 'TSA Cash Position',
            'currency': 'NGN',
            'total_balance': summary['total_balance'] or _zero(),
            'account_count': summary['account_count'] or 0,
            'by_account_type': by_type,
            'top_mda_balances': by_mda,
        }

    # -------------------------------------------------------------------------
    # NCoA dimension reports
    # -------------------------------------------------------------------------

    @classmethod
    def functional_classification_report(cls, fiscal_year: int, period: int = None) -> dict:
        """Functional Classification Performance Report (COFOG).

        Budget vs actual expenditure classified by COFOG functional
        segment. Mirrors the Programme Performance Report shape: each
        row carries ``budget_amount``, ``actual_expenditure`` (same as
        ``net_expenditure``), ``variance`` (budget − actual),
        ``utilization_pct`` and ``pct_of_total``.

        Budget side: ``Appropriation.functional`` (NCoA FunctionalSegment),
        unified status filter ['ACTIVE','ENACTED'] matching budget_vs_actual.
        Actual side: ``GLBalance.function`` (legacy Function dimension).
        Join key: shared ``code`` string — NCoA segments and legacy dims
        are kept aligned elsewhere in the codebase.

        S2-10 — accepts both 'Expense' and 'Expenditure' values of
        ``account_type`` since the model choice and actual data vary
        across tenants.
        """
        from budget.models import Appropriation

        filters = Q(
            account__account_type__in=['Expense', 'Expenditure'],
            fiscal_year=fiscal_year,
        )
        if period:
            filters &= Q(period=period)

        # ── Actuals per COFOG function (from GL) ────────────────────
        actual_rows = list(
            GLBalance.objects.filter(filters)
            .exclude(function__isnull=True)
            .values('function__code', 'function__name')
            .annotate(
                total_debit=Sum('debit_balance'),
                total_credit=Sum('credit_balance'),
            )
            .order_by('function__code')
        )

        # ── Budget per COFOG function (from Appropriation) ──────────
        budget_map: dict[str, Decimal] = {}
        budget_name_map: dict[str, str] = {}
        appros = (
            Appropriation.objects
            .filter(
                fiscal_year__year=fiscal_year,
                status__in=['ACTIVE', 'ENACTED'],
            )
            .values('functional__code', 'functional__name')
            .annotate(budget=Sum('amount_approved'))
        )
        for a in appros:
            code = a.get('functional__code')
            if code:
                budget_map[code] = a.get('budget') or _zero()
                budget_name_map[code] = a.get('functional__name') or ''

        # ── Merge actual + budget keyed by function code ─────────────
        merged: dict[str, dict] = {}
        for r in actual_rows:
            code = r['function__code']
            actual = (r['total_debit'] or _zero()) - (r['total_credit'] or _zero())
            merged[code] = {
                'function__code':     code,
                'function__name':     r['function__name'],
                'total_debit':        r['total_debit'] or _zero(),
                'total_credit':       r['total_credit'] or _zero(),
                'net_expenditure':    actual,
                'actual_expenditure': actual,
                'budget_amount':      budget_map.get(code, _zero()),
            }
        # Budget-only rows (approved but not yet spent) — include so
        # auditors see unused appropriations alongside utilised ones.
        for code, budget_amt in budget_map.items():
            if code in merged:
                continue
            merged[code] = {
                'function__code':     code,
                'function__name':     budget_name_map.get(code, ''),
                'total_debit':        _zero(),
                'total_credit':       _zero(),
                'net_expenditure':    _zero(),
                'actual_expenditure': _zero(),
                'budget_amount':      budget_amt,
            }

        rows = sorted(merged.values(), key=lambda r: r['function__code'])

        grand_actual = sum((r['net_expenditure'] for r in rows), _zero())
        grand_budget = sum((r['budget_amount']   for r in rows), _zero())

        for r in rows:
            budget_amt = r['budget_amount']
            actual = r['net_expenditure']
            r['variance'] = budget_amt - actual
            r['utilization_pct'] = (
                float(actual / budget_amt * 100) if budget_amt else 0
            )
            r['pct_of_total'] = (
                float(actual / grand_actual * 100) if grand_actual else 0
            )

        return {
            'title':          'Functional Classification Performance Report (COFOG)',
            'fiscal_year':    fiscal_year,
            'period':         period,
            'currency':       'NGN',
            'rows':           rows,
            'grand_total':    grand_actual,
            'grand_actual':   grand_actual,
            'grand_budget':   grand_budget,
            'grand_variance': grand_budget - grand_actual,
        }

    @classmethod
    def programme_performance_report(cls, fiscal_year: int, period: int = None) -> dict:
        """Budget vs actual expenditure by programme.

        S2-10 — status filter is unified with budget_vs_actual
        (['ACTIVE','ENACTED']). Previously only 'ACTIVE' → dropped enacted
        appropriations for the same programme. Errors no longer silently
        swallowed — they propagate so reporting bugs are visible.
        """
        from budget.models import Appropriation

        filters = Q(
            account__account_type__in=['Expense', 'Expenditure'],
            fiscal_year=fiscal_year,
        )
        if period:
            filters &= Q(period=period)

        rows = list(
            GLBalance.objects.filter(filters)
            .exclude(program__isnull=True)
            .values('program__code', 'program__name')
            .annotate(
                total_debit=Sum('debit_balance'),
                total_credit=Sum('credit_balance'),
            )
            .order_by('program__code')
        )

        # Budget amounts per programme (unified status filter).
        budget_map: dict[str, Decimal] = {}
        appros = (
            Appropriation.objects
            .filter(
                fiscal_year__year=fiscal_year,
                status__in=['ACTIVE', 'ENACTED'],
            )
            .values('programme__code')
            .annotate(budget=Sum('amount_approved'))
        )
        for a in appros:
            code = a.get('programme__code')
            if code:
                budget_map[code] = a['budget'] or _zero()

        for r in rows:
            actual = (r['total_debit'] or _zero()) - (r['total_credit'] or _zero())
            budget_amt = budget_map.get(r['program__code'], _zero())
            r['actual_expenditure'] = actual
            r['budget_amount'] = budget_amt
            r['variance'] = budget_amt - actual
            r['utilization_pct'] = (
                float(actual / budget_amt * 100) if budget_amt else 0
            )

        grand_actual = sum((r['actual_expenditure'] for r in rows), _zero())
        grand_budget = sum((r['budget_amount']    for r in rows), _zero())

        return {
            'title': 'Programme Performance Report',
            'fiscal_year': fiscal_year,
            'period': period,
            'currency': 'NGN',
            'rows': rows,
            'grand_actual': grand_actual,
            'grand_budget': grand_budget,
            'grand_variance': grand_budget - grand_actual,
        }

    @classmethod
    def fund_performance_report(cls, fiscal_year: int, period: int = None) -> dict:
        """Fund Performance Report — budget vs actual by fund source.

        Classifies expenditure by fund segment (CRF, Development Fund,
        Donor/Grant Fund, Internal Revenue Fund, etc.) with utilisation
        analysis. Same shape as Functional / Programme / Geographic
        performance reports: each row carries ``budget_amount``,
        ``actual_expenditure``, ``variance``, ``utilization_pct``,
        ``pct_of_total``.

        Budget side: ``Appropriation.fund`` (NCoA FundSegment).
        Actual side: ``GLBalance.fund`` (legacy Fund dimension).
        Joined on the shared ``code`` string.
        """
        from budget.models import Appropriation

        filters = Q(
            account__account_type__in=['Expense', 'Expenditure'],
            fiscal_year=fiscal_year,
        )
        if period:
            filters &= Q(period=period)

        # Actuals per fund.
        actual_rows = list(
            GLBalance.objects.filter(filters)
            .exclude(fund__isnull=True)
            .values('fund__code', 'fund__name')
            .annotate(
                total_debit=Sum('debit_balance'),
                total_credit=Sum('credit_balance'),
            )
            .order_by('fund__code')
        )

        # Budgets per fund from Appropriation (unified status filter).
        budget_map: dict[str, Decimal] = {}
        budget_name_map: dict[str, str] = {}
        appros = (
            Appropriation.objects
            .filter(
                fiscal_year__year=fiscal_year,
                status__in=['ACTIVE', 'ENACTED'],
            )
            .values('fund__code', 'fund__name')
            .annotate(budget=Sum('amount_approved'))
        )
        for a in appros:
            code = a.get('fund__code')
            if code:
                budget_map[code] = a.get('budget') or _zero()
                budget_name_map[code] = a.get('fund__name') or ''

        # Merge actuals + budgets keyed by fund code.
        merged: dict[str, dict] = {}
        for r in actual_rows:
            code = r['fund__code']
            actual = (r['total_debit'] or _zero()) - (r['total_credit'] or _zero())
            merged[code] = {
                'fund__code':         code,
                'fund__name':         r['fund__name'],
                'total_debit':        r['total_debit'] or _zero(),
                'total_credit':       r['total_credit'] or _zero(),
                'actual_expenditure': actual,
                'expenditure':        actual,
                'budget_amount':      budget_map.get(code, _zero()),
            }
        for code, budget_amt in budget_map.items():
            if code in merged:
                continue
            merged[code] = {
                'fund__code':         code,
                'fund__name':         budget_name_map.get(code, ''),
                'total_debit':        _zero(),
                'total_credit':       _zero(),
                'actual_expenditure': _zero(),
                'expenditure':        _zero(),
                'budget_amount':      budget_amt,
            }

        rows = sorted(merged.values(), key=lambda r: r['fund__code'])

        grand_actual = sum((r['actual_expenditure'] for r in rows), _zero())
        grand_budget = sum((r['budget_amount']      for r in rows), _zero())

        for r in rows:
            budget_amt = r['budget_amount']
            actual = r['actual_expenditure']
            r['variance'] = budget_amt - actual
            r['utilization_pct'] = (
                float(actual / budget_amt * 100) if budget_amt else 0
            )
            r['pct_of_total'] = (
                float(actual / grand_actual * 100) if grand_actual else 0
            )

        return {
            'title':          'Fund Performance Report',
            'fiscal_year':    fiscal_year,
            'period':         period,
            'currency':       'NGN',
            'rows':           rows,
            'grand_total':    grand_actual,
            'grand_actual':   grand_actual,
            'grand_budget':   grand_budget,
            'grand_variance': grand_budget - grand_actual,
        }

    @classmethod
    def geographic_distribution_report(cls, fiscal_year: int, period: int = None) -> dict:
        """Geographic Distribution Performance Report.

        Budget vs actual expenditure by geographic zone / LGA. Each row
        carries ``budget_amount``, ``actual_expenditure`` (same as
        ``expenditure``), ``variance`` (budget − actual),
        ``utilization_pct`` and ``pct_of_total``.

        Budget source hierarchy (first available wins):
          1. **Appropriation.geographic** aggregated by geo —
             direct, legally-enacted budget (``budget_source='direct'``).
             This is the preferred source once Appropriations carry
             geographic dimensions (S19+).
          2. ``UnifiedBudget.geo`` aggregated by geo — the multi-dim
             budget model, used when the tenant runs parallel
             statistical budgets.
          3. **Pro-rata fallback**: when no geo-dimensioned budget
             exists, total ``Appropriation.amount_approved`` (for expense
             appropriations) is apportioned to each geo by its share of
             actual expenditure. The report documents this via
             ``budget_source='pro_rata'`` so the UI can badge the rows
             as estimates.

        Actuals always come from ``GLBalance.geo``.
        """
        from budget.models import Appropriation, UnifiedBudget

        filters = Q(
            account__account_type__in=['Expense', 'Expenditure'],
            fiscal_year=fiscal_year,
        )
        if period:
            filters &= Q(period=period)

        # ── Actuals per geographic dimension ─────────────────────────
        actual_rows = list(
            GLBalance.objects.filter(filters)
            .exclude(geo__isnull=True)
            .values('geo__code', 'geo__name')
            .annotate(
                total_debit=Sum('debit_balance'),
                total_credit=Sum('credit_balance'),
            )
            .order_by('geo__code')
        )

        # ── Budget per geo (source #1: Appropriation.geographic) ─────
        budget_map: dict[str, Decimal] = {}
        budget_name_map: dict[str, str] = {}
        budget_source = 'direct'

        appro_geo_rows = (
            Appropriation.objects
            .filter(
                fiscal_year__year=fiscal_year,
                status__in=['ACTIVE', 'ENACTED'],
            )
            .exclude(geographic__isnull=True)
            .values('geographic__code', 'geographic__name')
            .annotate(budget=Sum('amount_approved'))
        )
        for a in appro_geo_rows:
            code = a.get('geographic__code')
            if code:
                budget_map[code] = a.get('budget') or _zero()
                budget_name_map[code] = a.get('geographic__name') or ''

        # ── Budget per geo (source #2: UnifiedBudget) ────────────────
        if not budget_map:
            try:
                ub_rows = (
                    UnifiedBudget.objects
                    .filter(fiscal_year=str(fiscal_year))
                    .exclude(geo__isnull=True)
                    .values('geo__code', 'geo__name')
                    .annotate(
                        budget=Sum('revised_amount') + Sum('original_amount'),
                        orig=Sum('original_amount'),
                    )
                )
                for a in ub_rows:
                    code = a.get('geo__code')
                    if not code:
                        continue
                    b = a.get('budget') or a.get('orig') or _zero()
                    budget_map[code] = b
                    budget_name_map[code] = a.get('geo__name') or ''
            except Exception:
                budget_map = {}

        # ── Budget per geo (source #2: pro-rata fallback) ────────────
        if not budget_map:
            total_appro = (
                Appropriation.objects
                .filter(
                    fiscal_year__year=fiscal_year,
                    status__in=['ACTIVE', 'ENACTED'],
                )
                .aggregate(total=Sum('amount_approved'))['total']
                or _zero()
            )

            total_actual_gl = _zero()
            for r in actual_rows:
                dr = r['total_debit'] or _zero()
                cr = r['total_credit'] or _zero()
                total_actual_gl += (dr - cr)

            if total_appro > 0 and total_actual_gl > 0:
                for r in actual_rows:
                    code = r['geo__code']
                    actual = (r['total_debit'] or _zero()) - (r['total_credit'] or _zero())
                    share = (actual / total_actual_gl) if total_actual_gl else Decimal('0')
                    budget_map[code] = (total_appro * share).quantize(Decimal('0.01'))
                    budget_name_map[code] = r['geo__name']
                budget_source = 'pro_rata'
            else:
                budget_source = 'unavailable'

        # ── Merge actuals + budgets ──────────────────────────────────
        merged: dict[str, dict] = {}
        for r in actual_rows:
            code = r['geo__code']
            actual = (r['total_debit'] or _zero()) - (r['total_credit'] or _zero())
            merged[code] = {
                'geo__code':          code,
                'geo__name':          r['geo__name'],
                'total_debit':        r['total_debit'] or _zero(),
                'total_credit':       r['total_credit'] or _zero(),
                'expenditure':        actual,
                'actual_expenditure': actual,
                'budget_amount':      budget_map.get(code, _zero()),
            }
        for code, budget_amt in budget_map.items():
            if code in merged:
                continue
            merged[code] = {
                'geo__code':          code,
                'geo__name':          budget_name_map.get(code, ''),
                'total_debit':        _zero(),
                'total_credit':       _zero(),
                'expenditure':        _zero(),
                'actual_expenditure': _zero(),
                'budget_amount':      budget_amt,
            }

        rows = sorted(merged.values(), key=lambda r: r['geo__code'])

        grand_actual = sum((r['expenditure'] for r in rows), _zero())
        grand_budget = sum((r['budget_amount'] for r in rows), _zero())

        for r in rows:
            budget_amt = r['budget_amount']
            actual = r['expenditure']
            r['variance'] = budget_amt - actual
            r['utilization_pct'] = (
                float(actual / budget_amt * 100) if budget_amt else 0
            )
            r['pct_of_total'] = (
                float(actual / grand_actual * 100) if grand_actual else 0
            )

        return {
            'title':          'Geographic Distribution Performance Report',
            'fiscal_year':    fiscal_year,
            'period':         period,
            'currency':       'NGN',
            'budget_source':  budget_source,
            'rows':           rows,
            'grand_total':    grand_actual,
            'grand_actual':   grand_actual,
            'grand_budget':   grand_budget,
            'grand_variance': grand_budget - grand_actual,
        }

    # =========================================================================
    # IPSAS 1 — Notes to Financial Statements (minimal infrastructure)
    # =========================================================================

    @classmethod
    def notes_to_financial_statements(cls, fiscal_year: int) -> dict:
        """Minimum IPSAS 1 notes set.

        A full notes pack requires per-standard disclosures; this
        implementation emits a machine-readable skeleton that an
        accountant can expand with narrative text. Current notes:

        * Note 1 — Accounting policies (static)
        * Note 2 — Property, Plant and Equipment movement
        * Note 3 — Receivables aging
        * Note 4 — Payables aging
        * Note 5 — Borrowings summary
        * Note 6 — Contingent liabilities (placeholder — to populate when
          the Provision / ContingentLiability models ship in Sprint 1.5)
        """
        return {
            'title': 'Notes to the Financial Statements',
            'standard': 'IPSAS 1',
            'fiscal_year': fiscal_year,
            'currency': 'NGN',
            'notes': [
                {
                    'number': 1,
                    'title': 'Accounting Policies',
                    'body': (
                        'These financial statements have been prepared on '
                        'the accrual basis of accounting in accordance '
                        'with International Public Sector Accounting '
                        'Standards (IPSAS). The presentation currency is '
                        'the Nigerian Naira (NGN). Amounts are rounded to '
                        'the nearest kobo.'
                    ),
                    'data': None,
                },
                cls._note_ppe_movement(fiscal_year),
                cls._note_receivables_aging(fiscal_year),
                cls._note_payables_aging(fiscal_year),
                {
                    'number': 5,
                    'title': 'Borrowings',
                    'body': (
                        'Loans and borrowings are measured at amortised '
                        'cost. The register summary below lists '
                        'outstanding facilities; the GL section shows '
                        'NCoA 42xx Non-Current Liabilities (loan '
                        'principal) and 24xx Debt Service (interest + '
                        'finance charges) that feed this note.'
                    ),
                    'data': {
                        'register':    cls._note_borrowings(fiscal_year),
                        'gl_balances': cls._gl_balances_for_note(
                            fiscal_year, code_prefixes=['42', '24'],
                        ),
                    },
                },
                cls._note_provisions_and_contingents(fiscal_year),
                cls._note_ipsas_33_transition(fiscal_year),
                cls._note_pension_ipsas_39(fiscal_year),
                cls._note_social_benefits_ipsas_42(fiscal_year),
            ],
        }

    @classmethod
    def _note_pension_ipsas_39(cls, fiscal_year: int) -> dict:
        """Note 8 — Employee benefits (IPSAS 39).

        Discloses scheme inventory, latest actuarial valuation per DB
        scheme, and current-period contributions per scheme. Required
        disclosures under ¶140:

          * DBO reconciliation (captured on ``ActuarialValuation``)
          * Plan assets reconciliation (captured)
          * Net defined benefit liability
          * Principal actuarial assumptions
          * Expense recognised in the period
        """
        # GL section is independent of register presence — the ledger
        # may already carry pension postings via direct journals even
        # before the PensionScheme register is populated.
        pension_codes_early = cls._pension_gl_codes()
        gl_balances_early = cls._gl_balances_for_note(
            fiscal_year, exact_codes=pension_codes_early,
        )

        try:
            from accounting.models import (
                PensionScheme, ActuarialValuation, PensionContribution,
            )
        except Exception:
            return {
                'number': 8,
                'title': 'Employee Benefits (IPSAS 39)',
                'body': (
                    'Pension register not available in this deployment. '
                    'The GL section below shows any existing ledger '
                    'activity against the configured pension accounts.'
                ),
                'data': {'gl_balances': gl_balances_early},
            }

        try:
            schemes = list(PensionScheme.objects.all().order_by('code'))
        except Exception:
            return {
                'number': 8,
                'title': 'Employee Benefits (IPSAS 39)',
                'body': (
                    'Pension register not available in this deployment. '
                    'The GL section below shows any existing ledger '
                    'activity against the configured pension accounts.'
                ),
                'data': {'gl_balances': gl_balances_early},
            }

        if not schemes:
            return {
                'number': 8,
                'title': 'Employee Benefits (IPSAS 39)',
                'body': (
                    'No pension schemes are on file for this entity. '
                    'Add a scheme record under /api/v1/accounting/pension-schemes/ '
                    'to populate the register. The GL section below still '
                    'reflects any ledger activity against the configured '
                    'pension accounts.'
                ),
                'data': {'gl_balances': gl_balances_early},
            }

        scheme_entries: list[dict] = []
        total_dbo = Decimal('0')
        total_plan_assets = Decimal('0')
        total_net_liability = Decimal('0')
        total_expense = Decimal('0')
        total_contributions = Decimal('0')

        for scheme in schemes:
            # Latest valuation (DB only).
            latest_valuation = None
            if scheme.is_defined_benefit:
                latest_valuation = (
                    ActuarialValuation.objects
                    .filter(scheme=scheme)
                    .order_by('-valuation_date')
                    .first()
                )

            # Period contributions (this fiscal year).
            contrib_agg = (
                PensionContribution.objects
                .filter(scheme=scheme, period_year=fiscal_year)
                .aggregate(
                    emp=_sum_field('employee_amount'),
                    empr=_sum_field('employer_amount'),
                    heads=_sum_field('headcount'),
                )
            )
            contrib_emp = contrib_agg['emp'] or Decimal('0')
            contrib_empr = contrib_agg['empr'] or Decimal('0')
            contrib_total = contrib_emp + contrib_empr

            entry: dict = {
                'code':            scheme.code,
                'name':            scheme.name,
                'scheme_type':     scheme.scheme_type,
                'scheme_type_display': scheme.get_scheme_type_display(),
                'status':          scheme.status,
                'coverage_note':   scheme.coverage_note,
                'contributions_for_period': {
                    'employee':  contrib_emp,
                    'employer':  contrib_empr,
                    'total':     contrib_total,
                    'headcount_sum': contrib_agg['heads'] or 0,
                },
            }
            total_contributions += contrib_total

            if latest_valuation:
                v = latest_valuation
                entry['latest_valuation'] = {
                    'valuation_date':       v.valuation_date.isoformat(),
                    'dbo':                  v.dbo,
                    'plan_assets':          v.plan_assets,
                    'net_defined_benefit_liability': v.net_defined_benefit_liability,
                    'service_cost':         v.service_cost,
                    'interest_cost':        v.interest_cost,
                    'past_service_cost':    v.past_service_cost,
                    'actuarial_gains_losses': v.actuarial_gains_losses,
                    'total_period_expense': v.total_period_expense,
                    'valuation_method':     v.get_valuation_method_display(),
                    'discount_rate':        v.discount_rate,
                    'salary_growth_rate':   v.salary_growth_rate,
                    'pension_growth_rate':  v.pension_growth_rate,
                    'mortality_table':      v.mortality_table,
                    'assumptions_narrative': v.assumptions_narrative,
                    'valuer_firm':          v.valuer_firm,
                    'valuer_fellow':        v.valuer_fellow,
                    'report_reference':     v.report_reference,
                }
                total_dbo += v.dbo
                total_plan_assets += v.plan_assets
                total_net_liability += v.net_defined_benefit_liability
                total_expense += v.total_period_expense

            scheme_entries.append(entry)

        # Resolve the AccountingSettings codes that the pension posting
        # pipeline uses, then pull their live GL balances so auditors can
        # reconcile the actuarial disclosures against the ledger.
        pension_codes = cls._pension_gl_codes()

        return {
            'number': 8,
            'title': 'Employee Benefits (IPSAS 39)',
            'body': (
                'The entity operates pension schemes on a defined-'
                'contribution and/or defined-benefit basis. Summaries '
                'below are per-scheme. For DB schemes, the disclosures '
                'reflect the most recent actuarial valuation obtained. '
                'The GL section shows the configured pension accounts '
                '(DBO, service cost, interest cost) that feed this note.'
            ),
            'data': {
                'schemes': scheme_entries,
                'totals': {
                    'defined_benefit_obligation':    total_dbo,
                    'plan_assets':                   total_plan_assets,
                    'net_defined_benefit_liability': total_net_liability,
                    'period_expense':                total_expense,
                    'period_contributions':          total_contributions,
                },
                'gl_balances': cls._gl_balances_for_note(
                    fiscal_year, exact_codes=pension_codes,
                ),
            },
        }

    @classmethod
    def _pension_gl_codes(cls) -> list[str]:
        """Return the configured GL account codes that the pension
        posting pipeline writes to — DBO, service cost, interest cost.
        Falls back to the documented defaults when no
        AccountingSettings row is present."""
        try:
            from accounting.models import AccountingSettings
            s = AccountingSettings.objects.first()
        except Exception:
            s = None

        def _get(attr: str, default: str) -> str:
            val = getattr(s, attr, None) if s else None
            if val is None:
                return default
            stripped = str(val).strip()
            return stripped or default

        return [
            _get('defined_benefit_obligation_code', '42201000'),
            _get('pension_service_cost_code',       '21400000'),
            _get('pension_interest_expense_code',   '24100000'),
        ]

    @classmethod
    def _note_social_benefits_ipsas_42(cls, fiscal_year: int) -> dict:
        """Note 9 — Social benefits (IPSAS 42).

        Discloses scheme-level activity for the fiscal year:
          * Schemes in operation and their categories
          * Claims recognised (ELIGIBLE + APPROVED + PAID)
          * Amounts paid in the period
        """
        # GL section runs independently of the register.
        social_codes_early = cls._social_benefit_gl_codes()
        gl_balances_early = cls._gl_balances_for_note(
            fiscal_year, exact_codes=social_codes_early,
        )

        def _wrap_empty(body: str) -> dict:
            return {
                'number': 9,
                'title': 'Social Benefits (IPSAS 42)',
                'body': body,
                'data': {'gl_balances': gl_balances_early},
            }

        try:
            from accounting.models import SocialBenefitScheme, SocialBenefitClaim
        except Exception:
            return _wrap_empty(
                'Social-benefits register not available in this deployment. '
                'The GL section below shows ledger activity against the '
                'configured social-benefit expense account.'
            )

        try:
            schemes = list(
                SocialBenefitScheme.objects
                .filter(status='ACTIVE')
                .order_by('code')
            )
        except Exception:
            return _wrap_empty(
                'Social-benefits register not available in this deployment. '
                'The GL section below shows ledger activity against the '
                'configured social-benefit expense account.'
            )

        if not schemes:
            return _wrap_empty(
                'The entity has no active social-benefit schemes '
                'for the reporting period. The GL section below '
                'shows any ledger activity against the configured '
                'social-benefit expense account.'
            )

        scheme_entries: list[dict] = []
        grand_paid = Decimal('0')
        grand_recognised = Decimal('0')
        grand_beneficiaries = 0

        for scheme in schemes:
            claims = SocialBenefitClaim.objects.filter(
                scheme=scheme, period_year=fiscal_year,
            )
            agg = claims.aggregate(
                paid_amount=_sum_filtered('amount', status='PAID'),
                recognised_amount=_sum_filtered(
                    'amount', status__in=('ELIGIBLE', 'APPROVED', 'PAID'),
                ),
            )
            paid = agg['paid_amount'] or Decimal('0')
            recognised = agg['recognised_amount'] or Decimal('0')
            count = claims.filter(
                status__in=('ELIGIBLE', 'APPROVED', 'PAID'),
            ).count()

            scheme_entries.append({
                'code':              scheme.code,
                'name':              scheme.name,
                'category':          scheme.category,
                'category_display':  scheme.get_category_display(),
                'eligibility_criteria':   scheme.eligibility_criteria,
                'standard_benefit_amount': scheme.standard_benefit_amount,
                'payment_frequency':       scheme.payment_frequency,
                'funding_source':          scheme.funding_source,
                'period_summary': {
                    'beneficiary_count':     count,
                    'amount_recognised':     recognised,
                    'amount_paid':           paid,
                    'amount_outstanding':    recognised - paid,
                },
            })
            grand_paid += paid
            grand_recognised += recognised
            grand_beneficiaries += count

        social_codes = cls._social_benefit_gl_codes()

        return {
            'number': 9,
            'title': 'Social Benefits (IPSAS 42)',
            'body': (
                'Social-benefit schemes provide cash transfers, goods, '
                'or services to individuals to mitigate social risks. '
                'Under IPSAS 42 ¶31, a liability is recognised at the '
                'date an individual first becomes eligible, measured at '
                'the next single payment due. Amounts disclosed below '
                'reflect claims recognised during the reporting period. '
                'The GL section shows the configured social-benefit '
                'expense account that feeds this note.'
            ),
            'data': {
                'schemes': scheme_entries,
                'totals': {
                    'beneficiary_count':  grand_beneficiaries,
                    'amount_recognised':  grand_recognised,
                    'amount_paid':        grand_paid,
                    'amount_outstanding': grand_recognised - grand_paid,
                },
                'gl_balances': cls._gl_balances_for_note(
                    fiscal_year, exact_codes=social_codes,
                ),
            },
        }

    @classmethod
    def _social_benefit_gl_codes(cls) -> list[str]:
        """Return the GL expense code that the batch-pay pipeline writes
        to. Falls back to NCoA 25100000 (Transfers & Subventions —
        Social Benefits)."""
        try:
            from accounting.models import AccountingSettings
            s = AccountingSettings.objects.first()
        except Exception:
            s = None
        val = getattr(s, 'social_benefit_expense_code', None) if s else None
        if val:
            stripped = str(val).strip()
            if stripped:
                return [stripped]
        return ['25100000']

    @classmethod
    def _note_ipsas_33_transition(cls, fiscal_year: int) -> dict:
        """Note 7 — IPSAS 33 ¶142 first-time-adoption disclosures.

        Only populated when a FINALISED ``OpeningBalanceSheet`` exists.
        During steady-state operation the ``data`` is None and the body
        reads "not a first-time adopter for this period".

        IPSAS 33 ¶142 requires disclosure of:
          (a) The date of transition.
          (b) Explanation of how transition affects reported position
              — comes from the AG's ``transition_notes`` free text.
          (c) Deemed-cost elections: which asset classes used fair
              value / previous GAAP in lieu of historical cost, and
              the rationale.
          (d) Opening-position totals.
        """
        try:
            from accounting.models import OpeningBalanceSheet
            sheet = (
                OpeningBalanceSheet.objects
                .filter(status='FINALISED')
                .order_by('-transition_date')
                .first()
            )
        except Exception:
            sheet = None

        if sheet is None:
            return {
                'number': 7,
                'title': 'First-Time Adoption of Accrual IPSAS (IPSAS 33)',
                'body': (
                    'This entity is not in a first-time-adoption year. '
                    'Transition disclosures are not applicable for the '
                    'current reporting period.'
                ),
                'data': None,
            }

        # Group items by deemed-cost basis so ¶142(c) disclosures are
        # presented by election category rather than per-account.
        from collections import defaultdict
        by_basis: dict[str, dict] = defaultdict(
            lambda: {'item_count': 0, 'total': Decimal('0'), 'items': []},
        )
        for item in sheet.items.select_related('account').all():
            bucket = by_basis[item.deemed_cost_basis or 'HISTORICAL']
            bucket['item_count'] += 1
            magnitude = (item.debit or Decimal('0')) + (item.credit or Decimal('0'))
            bucket['total'] += magnitude
            bucket['items'].append({
                'account_code': item.account.code,
                'account_name': item.account.name,
                'amount':       magnitude,
                'rationale':    item.deemed_cost_rationale or '',
                'evidence_ref': item.supporting_document_ref or '',
            })

        _BASIS_LABELS = {
            'HISTORICAL':    'Historical cost (traced)',
            'FAIR_VALUE':    'Fair value at transition date (¶64)',
            'PREVIOUS_GAAP': 'Previous GAAP carrying amount (¶66)',
            'INDEXED_COST':  'Indexed historical cost (¶68)',
            'REVALUATION':   'Prior revaluation (¶70)',
        }

        deemed_cost_elections: list[dict] = []
        for basis, info in by_basis.items():
            entry = {
                'basis':              basis,
                'basis_display':      _BASIS_LABELS.get(basis, basis),
                'item_count':         info['item_count'],
                'total':              info['total'],
                'rationale_required': basis != 'HISTORICAL',
            }
            # Only non-historical elections need the per-item rationale
            # list in the ¶142(c) disclosure.
            if basis != 'HISTORICAL':
                entry['items'] = info['items']
            deemed_cost_elections.append(entry)

        return {
            'number': 7,
            'title': 'First-Time Adoption of Accrual IPSAS (IPSAS 33)',
            'body': (
                f'The entity adopted the accrual basis of IPSAS with '
                f'effect from {sheet.transition_date.isoformat()}. The '
                f'opening balance sheet was finalised on '
                f'{sheet.finalised_at.date().isoformat() if sheet.finalised_at else "—"} '
                f'and recorded via journal '
                f'{sheet.finalisation_journal.reference_number if sheet.finalisation_journal else "—"}. '
                f'This note presents the transition disclosures required '
                f'by IPSAS 33 ¶142, including deemed-cost elections '
                f'made under ¶64-¶70.'
            ),
            'data': {
                'transition_date':   sheet.transition_date.isoformat(),
                'finalised_at':      sheet.finalised_at.isoformat() if sheet.finalised_at else None,
                'finalised_by':      getattr(sheet.finalised_by, 'username', None),
                'journal_reference': (
                    sheet.finalisation_journal.reference_number
                    if sheet.finalisation_journal else None
                ),
                'opening_totals': {
                    'total_assets':      sheet.total_assets,
                    'total_liabilities': sheet.total_liabilities,
                    'total_net_assets':  sheet.total_net_assets,
                    'is_balanced':       sheet.is_balanced,
                },
                'deemed_cost_elections': deemed_cost_elections,
                'transition_notes':      sheet.transition_notes or '',
            },
        }

    @classmethod
    def _note_provisions_and_contingents(cls, fiscal_year: int) -> dict:
        """Note 6 — Provisions, Contingent Liabilities, Contingent Assets.

        Sources data from the IPSAS 19 registries (S10-04).
        Recognised provisions go on-balance-sheet; contingent liabilities
        and probable contingent assets are disclosed here without being
        recognised.

        Defensive try/except: if the registry tables are absent (very
        early deployments before the S10 migrations ran) we fall back
        to the original placeholder so the Notes report still renders.
        """
        try:
            from accounting.models import (
                Provision, ContingentLiability, ContingentAsset,
            )
            from django.db.models import Sum

            # Recognised provisions, grouped by category so the note
            # reads "Litigation: NGN 5M, Pension: NGN 12M, ..."
            provisions = (
                Provision.objects
                .filter(status='RECOGNISED')
                .values('category')
                .annotate(total=Sum('amount'))
                .order_by('-total')
            )
            total_recognised = sum(
                (p['total'] or Decimal('0') for p in provisions),
                Decimal('0'),
            )

            # Disclosed contingent liabilities (possible or probable).
            cont_liabilities = (
                ContingentLiability.objects
                .filter(is_disclosed=True)
                .values('likelihood')
                .annotate(total=Sum('estimated_amount'))
            )

            # Contingent assets disclosed only when probable / certain.
            cont_assets = (
                ContingentAsset.objects
                .filter(likelihood__in=['PROBABLE', 'CERTAIN'])
                .values('likelihood')
                .annotate(total=Sum('estimated_amount'))
            )

            return {
                'number': 6,
                'title': 'Provisions, Contingent Liabilities and Contingent Assets (IPSAS 19)',
                'body': (
                    'Provisions are recognised when a present '
                    'obligation (legal or constructive) exists as a '
                    'result of a past event, settlement is probable '
                    'and the amount can be reliably estimated. '
                    'Contingent liabilities are disclosed when a '
                    'possible obligation exists whose realisation '
                    'depends on uncertain future events. Contingent '
                    'assets are disclosed only when realisation is '
                    'probable.'
                ),
                'data': {
                    'recognised_provisions': {
                        'total': total_recognised,
                        'by_category': list(provisions),
                    },
                    'contingent_liabilities_by_likelihood': list(cont_liabilities),
                    'contingent_assets_by_likelihood':     list(cont_assets),
                },
            }
        except Exception:
            # Deployment has not yet applied S10 migrations.
            return {
                'number': 6,
                'title': 'Contingent Liabilities',
                'body': (
                    'Contingent liabilities are disclosed when a '
                    'possible obligation exists whose realisation '
                    'depends on future events. Provisions register '
                    'not yet available in this deployment.'
                ),
                'data': None,
            }

    @classmethod
    def _note_ppe_movement(cls, fiscal_year: int) -> dict:
        """Movement schedule for Property, Plant and Equipment (IPSAS 17).

        Returns both the **asset-register** view (from ``FixedAsset``)
        and the **general-ledger** view (all NCoA 32xx Non-Current Asset
        balances) so auditors can reconcile the physical asset register
        against the financial ledger — a core IPSAS 17 control.
        """
        register: dict | None = None
        try:
            from accounting.models.assets import FixedAsset
            qs = FixedAsset.objects.all()
            opening_cost = (
                qs.aggregate(t=Sum('acquisition_cost'))['t'] or _zero()
            )
            additions = (
                qs.filter(acquisition_date__year=fiscal_year)
                  .aggregate(t=Sum('acquisition_cost'))['t'] or _zero()
            )
            register = {
                'opening_gross_block': opening_cost - additions,
                'additions':           additions,
                'closing_gross_block': opening_cost,
            }
        except Exception:
            register = None

        gl_section = cls._gl_balances_for_note(
            fiscal_year, code_prefixes=['32'],
        )

        return {
            'number': 2,
            'title': 'Property, Plant and Equipment',
            'body': (
                'Summary movement of fixed assets (from the asset '
                'register) and the underlying GL balances for NCoA '
                '32xx Non-Current Assets. Differences between the '
                'two views should be investigated before period close.'
            ),
            'data': {
                'asset_register': register,
                'gl_balances':    gl_section,
            },
        }

    @classmethod
    def _note_receivables_aging(cls, fiscal_year: int) -> dict:
        """Note 3 — Receivables Aging.

        Shows the AR register aging buckets and the GL balances that
        back them (NCoA 312xx Trade Receivables + 314xx Other
        Receivables). The two should reconcile at period-close.
        """
        aging: dict | None = None
        try:
            from accounting.services.aging_reports import AgingReportsService
            aging = AgingReportsService.customer_aging_report()
        except Exception:
            aging = None

        gl_section = cls._gl_balances_for_note(
            fiscal_year, code_prefixes=['312', '313', '314'],
        )

        return {
            'number': 3,
            'title': 'Receivables Aging',
            'body': (
                'Customer receivables by age bucket (from the AR '
                'sub-ledger) together with the underlying GL '
                'balances for NCoA 312xx–314xx Receivables. Aging '
                'buckets and GL balance must reconcile before sign-off.'
            ),
            'data': {
                'aging':        aging,
                'gl_balances':  gl_section,
            },
        }

    @classmethod
    def _note_payables_aging(cls, fiscal_year: int) -> dict:
        """Note 4 — Payables Aging.

        Shows the AP register aging buckets and the GL balances that
        back them (NCoA 411xx Accounts Payable + 412xx Salary /
        statutory payables).
        """
        aging: dict | None = None
        try:
            from accounting.services.aging_reports import AgingReportsService
            aging = AgingReportsService.vendor_aging_report()
        except Exception:
            aging = None

        gl_section = cls._gl_balances_for_note(
            fiscal_year, code_prefixes=['411', '412', '413'],
        )

        return {
            'number': 4,
            'title': 'Payables Aging',
            'body': (
                'Vendor payables by age bucket (from the AP sub-ledger) '
                'together with the underlying GL balances for NCoA '
                '411xx–413xx Current Payables. Sub-ledger and GL must '
                'reconcile at period close.'
            ),
            'data': {
                'aging':        aging,
                'gl_balances':  gl_section,
            },
        }

    @classmethod
    def _note_borrowings(cls, fiscal_year: int) -> dict | None:
        try:
            from accounting.models import Loan
            qs = Loan.objects.all()
            return {
                'loan_count': qs.count(),
                'outstanding_principal': (
                    qs.aggregate(t=Sum('outstanding_balance'))['t'] or _zero()
                ),
            }
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Shared GL helper (S21) — pulls the live GL balances that feed a
    # given note, so the narrative figures can be reconciled against
    # the ledger by any auditor reading the report.
    # ------------------------------------------------------------------
    @classmethod
    def _gl_balances_for_note(
        cls,
        fiscal_year: int,
        *,
        code_prefixes: list[str] | None = None,
        exact_codes: list[str] | None = None,
    ) -> dict:
        """Return a per-account GL slice for use in a note's ``data.gl_balances``.

        Queries :class:`GLBalance` filtered to this fiscal year where the
        related Account code matches either a prefix in ``code_prefixes``
        (e.g. ``['32']`` for all Non-Current Assets) or one of
        ``exact_codes`` (for notes targeting specific configured codes
        like ``pension_service_cost_code``).

        Shape
        -----
        Designed to render well in the NotesToFinancialStatementsReport
        auto-table renderer. ``lines`` is a list of per-account rows with
        human-readable keys; the per-row column order is:
        ``code → name → account_type → debit → credit → net``. The
        auto-renderer money-formats everything that contains
        ``debit`` / ``credit`` / ``net`` / ``balance`` in the key.
        """
        from accounting.models import Account

        qs = (
            GLBalance.objects
            .filter(fiscal_year=fiscal_year)
            .select_related('account')
        )
        q = Q()
        if code_prefixes:
            for pfx in code_prefixes:
                q |= Q(account__code__startswith=pfx)
        if exact_codes:
            q |= Q(account__code__in=exact_codes)
        if code_prefixes or exact_codes:
            qs = qs.filter(q)

        # Group by account so a single NCoA line appears once even if it
        # has balance rows across multiple periods / funds.
        grouped = (
            qs.values(
                'account__code',
                'account__name',
                'account__account_type',
            )
            .annotate(
                debit_balance=Sum('debit_balance'),
                credit_balance=Sum('credit_balance'),
            )
            .order_by('account__code')
        )

        lines: list[dict] = []
        total_debit = _zero()
        total_credit = _zero()
        for row in grouped:
            debit = row['debit_balance'] or _zero()
            credit = row['credit_balance'] or _zero()
            net = debit - credit
            lines.append({
                'code':           row['account__code'] or '',
                'name':           row['account__name'] or '',
                'account_type':   row['account__account_type'] or '',
                'debit_balance':  debit,
                'credit_balance': credit,
                'net_balance':    net,
            })
            total_debit += debit
            total_credit += credit

        # When the prefix / code filter matched no GLBalance rows but
        # matching Accounts exist in the CoA, still show them with zero
        # balances so auditors see the disclosed coverage, not a missing
        # section. Cheap extra query, bounded by prefix length.
        if not lines and (code_prefixes or exact_codes):
            cov_qs = Account.objects.filter(is_active=True)
            cq = Q()
            if code_prefixes:
                for pfx in code_prefixes:
                    cq |= Q(code__startswith=pfx)
            if exact_codes:
                cq |= Q(code__in=exact_codes)
            cov_qs = cov_qs.filter(cq).order_by('code')
            for acc in cov_qs[:50]:
                lines.append({
                    'code':           acc.code or '',
                    'name':           acc.name or '',
                    'account_type':   acc.account_type or '',
                    'debit_balance':  _zero(),
                    'credit_balance': _zero(),
                    'net_balance':    _zero(),
                })

        return {
            'fiscal_year':    fiscal_year,
            'filter': {
                'prefixes':  code_prefixes or [],
                'exact':     exact_codes or [],
            },
            'lines':          lines,
            'total_debit':    total_debit,
            'total_credit':   total_credit,
            'total_net':      total_debit - total_credit,
        }


# ─── S14 helpers — shared by the pension + social-benefit notes ──────────

def _empty_note(number: int, title: str, body: str) -> dict:
    """Build a degraded-mode note payload for when the register tables
    aren't available (e.g. deployments that haven't applied S14
    migrations yet)."""
    return {'number': number, 'title': title, 'body': body, 'data': None}


def _sum_field(field_name: str):
    """Helper so the pension note body can write concise aggregate
    expressions without repeating ``Sum('employer_amount')`` etc."""
    return Sum(field_name)


def _sum_filtered(field_name: str, **filters):
    """Conditional aggregate for Django ORM (used by the social-benefits
    note to sum amounts across multiple status values)."""
    from django.db.models import Q
    q = Q(**filters)
    return Sum(field_name, filter=q)
