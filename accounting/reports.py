from django.db.models import Sum, Q, Count
from datetime import date
from decimal import Decimal
from typing import Dict, List, Any
from dataclasses import dataclass, field


class ReportError(Exception):
    pass


@dataclass
class ReportRow:
    code: str
    name: str
    amount: Decimal = Decimal('0')
    children: List['ReportRow'] = field(default_factory=list)
    level: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class FinancialReportService:
    BALANCE_SHEET_ASSETS = ['1000', '1100', '1200', '1300', '1400', '1500']
    BALANCE_SHEET_LIABILITIES = ['2000', '2100', '2200', '2300', '2400']
    BALANCE_SHEET_EQUITY = ['3000', '3100', '3200', '3300']
    INCOME_REVENUE = ['4000', '4100', '4200']
    INCOME_EXPENSE = ['5000', '5100', '5200', '5300', '5400', '5500']

    @staticmethod
    def get_account_balances(start_date: date, end_date: date, account_codes: List[str] = None) -> Dict:
        from accounting.models import JournalLine

        queryset = JournalLine.objects.filter(
            header__posting_date__gte=start_date,
            header__posting_date__lte=end_date,
            header__status='Posted'
        ).select_related('account', 'header')

        if account_codes:
            q = Q()
            for code in account_codes:
                q |= Q(account__code__startswith=code)
            queryset = queryset.filter(q)

        balances = queryset.values('account__code', 'account__name', 'account__account_type').annotate(
            total_debit=Sum('debit'),
            total_credit=Sum('credit')
        )

        result = {}
        for b in balances:
            code = b['account__code']
            debit = b['total_debit'] or Decimal('0')
            credit = b['total_credit'] or Decimal('0')
            account_type = b['account__account_type']

            if account_type in ['Asset', 'Expense']:
                balance = debit - credit
            else:
                balance = credit - debit

            result[code] = {
                'code': code,
                'name': b['account__name'],
                'amount': balance,
                'type': account_type
            }

        return result

    @staticmethod
    def generate_balance_sheet(start_date: date, end_date: date) -> Dict:
        balances = FinancialReportService.get_account_balances(
            start_date, end_date
        )

        assets = Decimal('0')
        liabilities = Decimal('0')
        equity = Decimal('0')

        asset_details = []
        liability_details = []
        equity_details = []

        for code, data in balances.items():
            amount = data['amount']
            acct_type = data.get('type', '')

            if acct_type == 'Asset':
                assets += amount
                asset_details.append(data)
            elif acct_type == 'Liability':
                liabilities += amount
                liability_details.append(data)
            elif acct_type == 'Equity':
                equity += amount
                equity_details.append(data)

        net_income = FinancialReportService._get_net_income(start_date, end_date)
        equity += net_income

        return {
            'report_type': 'Balance Sheet',
            'as_of_date': end_date,
            'assets': {
                'total': assets,
                'details': asset_details
            },
            'liabilities': {
                'total': liabilities,
                'details': liability_details
            },
            'equity': {
                'total': equity,
                'details': equity_details,
                'net_income': net_income
            },
            'check': assets - (liabilities + equity)
        }

    @staticmethod
    def _get_net_income(start_date: date, end_date: date) -> Decimal:
        from accounting.models import JournalLine

        revenue = JournalLine.objects.filter(
            header__posting_date__gte=start_date,
            header__posting_date__lte=end_date,
            header__status='Posted',
            account__account_type='Income',
        ).aggregate(total=Sum('credit') - Sum('debit'))['total'] or Decimal('0')

        expense = JournalLine.objects.filter(
            header__posting_date__gte=start_date,
            header__posting_date__lte=end_date,
            header__status='Posted',
            account__account_type='Expense',
        ).aggregate(total=Sum('debit') - Sum('credit'))['total'] or Decimal('0')

        return revenue - expense

    @staticmethod
    def generate_income_statement(start_date: date, end_date: date) -> Dict:
        from accounting.models import JournalLine

        revenue_qs = JournalLine.objects.filter(
            header__posting_date__gte=start_date,
            header__posting_date__lte=end_date,
            header__status='Posted',
            account__account_type='Income',
        ).values('account__code', 'account__name').annotate(
            total=Sum('credit') - Sum('debit')
        ).order_by('account__code')

        expense_qs = JournalLine.objects.filter(
            header__posting_date__gte=start_date,
            header__posting_date__lte=end_date,
            header__status='Posted',
            account__account_type='Expense',
        ).values('account__code', 'account__name').annotate(
            total=Sum('debit') - Sum('credit')
        ).order_by('account__code')

        revenue_details = [{'code': r['account__code'], 'name': r['account__name'], 'amount': r['total'] or Decimal('0')} for r in revenue_qs]
        expense_details = [{'code': e['account__code'], 'name': e['account__name'], 'amount': e['total'] or Decimal('0')} for e in expense_qs]

        total_revenue = sum(r['amount'] for r in revenue_details)
        total_expenses = sum(e['amount'] for e in expense_details)
        net_income = total_revenue - total_expenses

        return {
            'report_type': 'Income Statement',
            'period': {'start': start_date, 'end': end_date},
            'revenue': {
                'total': total_revenue,
                'details': revenue_details
            },
            'expenses': {
                'total': total_expenses,
                'details': expense_details
            },
            'net_income': net_income
        }

    @staticmethod
    def generate_cash_flow_direct(start_date: date, end_date: date) -> Dict:
        """Cash Flow Statement — direct method.

        Classifies cash movements by looking at the *counterpart* account
        type on each journal that touches cash/bank accounts:
        - Operating: counterpart is Income, Expense, or current Asset/Liability
        - Investing: counterpart is non-current Asset
        - Financing: counterpart is Equity or long-term Liability
        """
        from accounting.models import JournalLine, Account

        cash_accounts = Account.objects.filter(
            Q(name__icontains='cash') | Q(name__icontains='bank'),
            account_type='Asset',
            is_active=True,
        ).values_list('id', flat=True)

        cash_lines = JournalLine.objects.filter(
            header__posting_date__gte=start_date,
            header__posting_date__lte=end_date,
            header__status='Posted',
            account_id__in=list(cash_accounts),
        ).select_related('header')

        operating = Decimal('0')
        investing = Decimal('0')
        financing = Decimal('0')
        details = []

        for line in cash_lines:
            net = line.debit - line.credit
            # Find counterpart lines to classify
            counterparts = JournalLine.objects.filter(
                header=line.header,
            ).exclude(account_id__in=list(cash_accounts)).select_related('account')

            category = 'operating'
            for cp in counterparts[:1]:  # classify by first counterpart
                if cp.account:
                    if cp.account.account_type == 'Equity':
                        category = 'financing'
                    elif cp.account.account_type == 'Asset' and 'depreciation' not in (cp.account.name or '').lower():
                        category = 'investing'

            if category == 'operating':
                operating += net
            elif category == 'investing':
                investing += net
            else:
                financing += net

            details.append({
                'date': str(line.header.posting_date),
                'reference': line.header.reference_number,
                'category': category,
                'amount': net,
            })

        return {
            'report_type': 'Cash Flow Statement (Direct Method)',
            'period': {'start': start_date, 'end': end_date},
            'operating_activities': {'net': operating},
            'investing_activities': {'net': investing},
            'financing_activities': {'net': financing},
            'net_change': operating + investing + financing,
            'details': details,
        }

    @staticmethod
    def generate_cash_flow_indirect(start_date: date, end_date: date) -> Dict:
        net_income = FinancialReportService._get_net_income(start_date, end_date)

        from accounting.models import JournalLine

        adjustments = []

        depreciation = JournalLine.objects.filter(
            header__posting_date__gte=start_date,
            header__posting_date__lte=end_date,
            header__status='Posted',
            account__account_type='Expense',
            account__name__icontains='depreciation',
        ).aggregate(total=Sum('debit'))['total'] or Decimal('0')

        if depreciation > 0:
            adjustments.append({'description': 'Add: Depreciation', 'amount': depreciation})

        wc_changes = FinancialReportService._get_working_capital_changes(start_date, end_date)

        return {
            'report_type': 'Cash Flow Statement (Indirect Method)',
            'period': {'start': start_date, 'end': end_date},
            'net_income': net_income,
            'adjustments': adjustments,
            'working_capital_changes': wc_changes,
            'operating_cash_flow': net_income + depreciation + wc_changes,
            'investing_activities': {'net': Decimal('0')},
            'financing_activities': {'net': Decimal('0')},
        }

    @staticmethod
    def _get_working_capital_changes(start_date: date, end_date: date) -> Decimal:
        """Approximate change in working capital (current assets excl. cash - current liabilities)."""
        from accounting.models import GLBalance
        from datetime import timedelta

        prior_start = start_date - timedelta(days=365)
        prior_end = start_date - timedelta(days=1)

        def _wc(fy, period):
            """Get net working-capital for a period from GL balances."""
            current_assets = GLBalance.objects.filter(
                fiscal_year=fy,
                period=period,
                account__account_type='Asset',
            ).exclude(
                account__name__icontains='cash',
            ).exclude(
                account__name__icontains='bank',
            ).aggregate(
                net=Sum('debit_balance') - Sum('credit_balance')
            )['net'] or Decimal('0')

            current_liabilities = GLBalance.objects.filter(
                fiscal_year=fy,
                period=period,
                account__account_type='Liability',
            ).aggregate(
                net=Sum('credit_balance') - Sum('debit_balance')
            )['net'] or Decimal('0')

            return current_assets - current_liabilities

        current_wc = _wc(end_date.year, end_date.month)
        prior_wc = _wc(start_date.year, start_date.month)

        # Increase in WC reduces operating cash flow (negative adjustment)
        return -(current_wc - prior_wc)

    @staticmethod
    def generate_from_template(template_id: int, start_date: date, end_date: date, user=None) -> Dict:
        """Generate a financial report using a FinancialReportTemplate and persist the result."""
        from accounting.models import FinancialReportTemplate, FinancialReport

        template = FinancialReportTemplate.objects.get(pk=template_id, is_active=True)
        report_type = template.report_type.lower()

        generators = {
            'balance sheet': FinancialReportService.generate_balance_sheet,
            'income statement': FinancialReportService.generate_income_statement,
            'cash flow direct': FinancialReportService.generate_cash_flow_direct,
            'cash flow indirect': FinancialReportService.generate_cash_flow_indirect,
        }

        generator = generators.get(report_type)
        if not generator:
            raise ReportError(f"Unknown report type: '{template.report_type}'")

        data = generator(start_date, end_date)
        data['template_name'] = template.name

        # Persist the generated report
        report = FinancialReport.objects.create(
            template=template,
            report_date=end_date,
            generated_by=user,
            data=data,
        )
        data['report_id'] = report.id
        return data


class BudgetReportService:
    @staticmethod
    def generate_budget_vs_actual(
        budget_period_id: int,
        fund_id: int = None,
        mda_id: int = None
    ) -> Dict:
        from accounting.models import Budget, BudgetPeriod, JournalLine

        try:
            period = BudgetPeriod.objects.get(pk=budget_period_id)
        except BudgetPeriod.DoesNotExist:
            raise ReportError("Budget period not found")

        budgets = Budget.objects.filter(period=period)
        if fund_id:
            budgets = budgets.filter(fund_id=fund_id)
        if mda_id:
            budgets = budgets.filter(mda_id=mda_id)

        budget_details = []
        for budget in budgets.select_related('account', 'fund', 'mda'):
            actual = JournalLine.objects.filter(
                header__posting_date__gte=period.start_date,
                header__posting_date__lte=period.end_date,
                header__status='Posted',
                account=budget.account
            ).aggregate(
                actual=Sum('debit') - Sum('credit')
            )['actual'] or Decimal('0')

            budget_amount = budget.revised_amount or budget.allocated_amount
            variance = budget_amount - actual
            variance_percent = (variance / budget_amount * 100) if budget_amount else Decimal('0')

            budget_details.append({
                'account_code': budget.account.code,
                'account_name': budget.account.name,
                'fund': budget.fund.name if budget.fund else None,
                'mda': budget.mda.name if budget.mda else None,
                'budget_amount': budget_amount,
                'actual': actual,
                'variance': variance,
                'variance_percent': variance_percent,
                'utilization': (actual / budget_amount * 100) if budget_amount else Decimal('0')
            })

        total_budget = sum(b['budget_amount'] for b in budget_details)
        total_actual = sum(b['actual'] for b in budget_details)

        return {
            'report_type': 'Budget vs Actual',
            'period': {'start': period.start_date, 'end': period.end_date},
            'total_budget': total_budget,
            'total_actual': total_actual,
            'total_variance': total_budget - total_actual,
            'details': budget_details
        }

    @staticmethod
    def generate_budget_performance(
        fiscal_year: int,
        fund_id: int = None
    ) -> Dict:
        from accounting.models import Budget, BudgetPeriod

        periods = BudgetPeriod.objects.filter(fiscal_year=fiscal_year)

        performance_data = []
        for period in periods:
            budgets = Budget.objects.filter(period=period)
            if fund_id:
                budgets = budgets.filter(fund_id=fund_id)

            total_allocated = budgets.aggregate(total=Sum('allocated_amount'))['total'] or Decimal('0')
            total_revised = budgets.aggregate(total=Sum('revised_amount'))['total'] or Decimal('0')

            performance_data.append({
                'period': f"P{period.period_number} {period.period_type}",
                'period_start': period.start_date,
                'period_end': period.end_date,
                'allocated_amount': total_allocated,
                'revised_amount': total_revised,
                'available_budget': total_allocated - total_revised,
                'utilization_rate': (total_revised / total_allocated * 100) if total_allocated else Decimal('0')
            })

        return {
            'report_type': 'Budget Performance Report',
            'fiscal_year': fiscal_year,
            'periods': performance_data,
            'summary': {
                'total_allocated': sum(p['allocated_amount'] for p in performance_data),
                'total_revised': sum(p['revised_amount'] for p in performance_data),
                'avg_utilization': sum(p['utilization_rate'] for p in performance_data) / len(performance_data) if performance_data else Decimal('0')
            }
        }


class CostCenterReportService:
    @staticmethod
    def generate_cost_center_report(
        start_date: date,
        end_date: date,
        cost_center_id: int = None
    ) -> Dict:
        from accounting.models import JournalLineCostCenter, CostCenter

        cost_centers = CostCenter.objects.all()
        if cost_center_id:
            cost_centers = cost_centers.filter(pk=cost_center_id)

        cc_details = []
        for cc in cost_centers:
            lines = JournalLineCostCenter.objects.filter(
                journal_line__header__posting_date__gte=start_date,
                journal_line__header__posting_date__lte=end_date,
                journal_line__header__status='Posted',
                cost_center=cc
            ).select_related('journal_line__account')

            total_amount = lines.aggregate(total=Sum('amount'))['total'] or Decimal('0')
            transaction_count = lines.count()

            by_account = lines.values(
                'journal_line__account__code',
                'journal_line__account__name'
            ).annotate(total=Sum('amount'))

            account_breakdown = [
                {'code': a['journal_line__account__code'], 'name': a['journal_line__account__name'], 'amount': a['total']}
                for a in by_account
            ]

            cc_details.append({
                'cost_center_code': cc.code,
                'cost_center_name': cc.name,
                'total_amount': total_amount,
                'transaction_count': transaction_count,
                'by_account': account_breakdown
            })

        return {
            'report_type': 'Cost Center Report',
            'period': {'start': start_date, 'end': end_date},
            'cost_centers': cc_details,
            'grand_total': sum(cc['total_amount'] for cc in cc_details)
        }


class IFRSReportService:
    @staticmethod
    def generate_ifrs_comparison_report(
        start_date: date,
        end_date: date,
        fiscal_year: int
    ) -> Dict:
        from accounting.models import Budget, JournalLine

        budgets = Budget.objects.filter(
            period__fiscal_year=fiscal_year
        ).select_related('account', 'period')

        budget_summary = budgets.values('account__code', 'account__name').annotate(
            total_budget=Sum('approved_budget')
        )

        actuals = JournalLine.objects.filter(
            header__posting_date__gte=start_date,
            header__posting_date__lte=end_date,
            header__status='Posted'
        ).values('account__code', 'account__name').annotate(
            total_actual=Sum('debit') - Sum('credit')
        )

        actual_dict = {a['account__code']: a for a in actuals}

        comparison = []
        for b in budget_summary:
            code = b['account__code']
            actual_data = actual_dict.get(code, {})

            actual = actual_data.get('total_actual') or Decimal('0')
            budget = b['total_budget'] or Decimal('0')
            variance = budget - actual
            variance_pct = (variance / budget * 100) if budget else Decimal('0')

            comparison.append({
                'account_code': code,
                'account_name': b['account__name'],
                'budget': budget,
                'actual': actual,
                'variance': variance,
                'variance_percentage': variance_pct,
                'status': 'Favorable' if variance >= 0 else 'Unfavorable'
            })

        total_budget = sum(c['budget'] for c in comparison)
        total_actual = sum(c['actual'] for c in comparison)

        return {
            'report_type': 'IFRS Comparison Report',
            'ifrs_standard': 'IPSAS / IFRS for Public Sector',
            'period': {'start': start_date, 'end': end_date},
            'fiscal_year': fiscal_year,
            'comparison': comparison,
            'summary': {
                'total_budget': total_budget,
                'total_actual': total_actual,
                'total_variance': total_budget - total_actual,
                'budget_accuracy': (total_actual / total_budget * 100) if total_budget else Decimal('0')
            }
        }


class GeneralLedgerReportService:
    @staticmethod
    def generate_general_ledger(
        start_date: date,
        end_date: date,
        account_code: str = None,
        cost_center_id: int = None
    ) -> Dict:
        from accounting.models import JournalLine

        lines = JournalLine.objects.filter(
            header__posting_date__gte=start_date,
            header__posting_date__lte=end_date,
            header__status='Posted'
        ).select_related('header', 'account').order_by('header__posting_date', 'header__id')

        if account_code:
            lines = lines.filter(account__code__startswith=account_code)

        entries = []
        running_balance = Decimal('0')

        for line in lines:
            if line.account.account_type in ['Asset', 'Expense']:
                running_balance += line.debit - line.credit
            else:
                running_balance += line.credit - line.debit

            entries.append({
                'date': line.header.posting_date,
                'reference': line.header.reference_number,
                'description': line.memo,
                'debit': line.debit,
                'credit': line.credit,
                'balance': running_balance,
            })

        return {
            'report_type': 'General Ledger',
            'period': {'start': start_date, 'end': end_date},
            'account_filter': account_code,
            'entries': entries,
            'total_debit': sum(e['debit'] for e in entries),
            'total_credit': sum(e['credit'] for e in entries),
        }


class TrialBalanceReportService:
    @staticmethod
    def generate_trial_balance(start_date: date, end_date: date) -> Dict:
        balances = FinancialReportService.get_account_balances(start_date, end_date)

        debit_total = Decimal('0')
        credit_total = Decimal('0')

        account_list = []
        for code, data in sorted(balances.items()):
            amount = abs(data['amount'])
            if data['type'] in ['Asset', 'Expense']:
                debit_total += amount
                debit = amount
                credit = Decimal('0')
            else:
                credit_total += amount
                debit = Decimal('0')
                credit = amount

            account_list.append({
                # Backward-compatible short keys.
                'code': code,
                'name': data['name'],
                'debit': debit,
                'credit': credit,
                # Frontend-friendly aliases — Trial Balance screen reads these.
                'account_code':    code,
                'account_name':    data['name'],
                'account_type':    data.get('type', ''),
                'debit_balance':   debit,
                'credit_balance':  credit,
            })

        return {
            'report_type': 'Trial Balance',
            'as_of_date': end_date,
            'accounts': account_list,
            'totals': {
                'debit':       debit_total,
                'credit':      credit_total,
                'difference':  debit_total - credit_total,
                # Frontend-friendly aliases.
                'total_debit':  debit_total,
                'total_credit': credit_total,
            }
        }


class InventoryReportService:
    @staticmethod
    def generate_stock_valuation(warehouse_id: int = None) -> Dict:
        from inventory.models import Item, ItemStock

        items = Item.objects.filter(is_active=True)

        item_valuations = []
        total_value = Decimal('0')

        for item in items.select_related('category'):
            if warehouse_id:
                stocks = ItemStock.objects.filter(item=item, warehouse_id=warehouse_id)
            else:
                stocks = ItemStock.objects.filter(item=item)

            total_qty = sum(s.quantity for s in stocks)
            avg_cost = item.average_cost or Decimal('0')
            item_value = total_qty * avg_cost

            item_valuations.append({
                'sku': item.sku,
                'name': item.name,
                'category': item.category.name if item.category else None,
                'quantity': total_qty,
                'unit_cost': avg_cost,
                'total_value': item_value
            })
            total_value += item_value

        return {
            'report_type': 'Inventory Stock Valuation',
            'warehouse_id': warehouse_id,
            'items': item_valuations,
            'total_value': total_value
        }

    @staticmethod
    def generate_low_stock_report() -> Dict:
        from inventory.models import Item

        items = Item.objects.filter(is_active=True, reorder_point__gt=0)

        low_stock_items = []
        for item in items:
            if item.needs_reorder:
                low_stock_items.append({
                    'sku': item.sku,
                    'name': item.name,
                    'current_quantity': item.stock_level,
                    'reorder_point': item.reorder_point,
                    'reorder_quantity': item.reorder_quantity,
                    'shortage': item.reorder_point - item.stock_level
                })

        return {
            'report_type': 'Low Stock Alert',
            'items': low_stock_items,
            'total_items': len(low_stock_items)
        }

    @staticmethod
    def generate_stock_movement(start_date: date, end_date: date) -> Dict:
        from inventory.models import StockMovement

        movements = StockMovement.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).select_related('item', 'from_warehouse', 'to_warehouse', 'created_by')

        by_type = movements.values('movement_type').annotate(
            count=Count('id'),
            total_quantity=Sum('quantity')
        )

        return {
            'report_type': 'Stock Movement Report',
            'period': {'start': start_date, 'end': end_date},
            'summary': list(by_type),
            'total_movements': movements.count()
        }


class HRReportService:
    @staticmethod
    def generate_headcount_report() -> Dict:
        from hrm.models import Employee, Department

        departments = Department.objects.filter(is_active=True)

        dept_stats = []
        total_employees = 0

        for dept in departments:
            active_count = Employee.objects.filter(department=dept, status='Active').count()
            dept_stats.append({
                'department': dept.name,
                'department_code': dept.code,
                'headcount': active_count
            })
            total_employees += active_count

        return {
            'report_type': 'Headcount Report',
            'departments': dept_stats,
            'total_headcount': total_employees
        }

    @staticmethod
    def generate_payroll_summary(month: int, year: int) -> Dict:
        from hrm.models import PayrollRun

        payroll_runs = PayrollRun.objects.filter(
            period__start_date__month=month,
            period__start_date__year=year,
            status='Approved'
        ).select_related('period')

        total_gross = Decimal('0')
        total_deductions = Decimal('0')
        total_net = Decimal('0')

        payroll_details = []

        for run in payroll_runs:
            total_gross += run.total_gross or Decimal('0')
            total_deductions += run.total_deductions or Decimal('0')
            total_net += run.total_net or Decimal('0')

            for line in run.lines.select_related('employee__user'):
                payroll_details.append({
                    'employee_number': line.employee.employee_number,
                    'employee_name': line.employee.user.get_full_name(),
                    'gross_amount': line.gross_salary,
                    'deductions': line.total_deductions,
                    'net_amount': line.net_salary,
                    'run_number': run.run_number,
                })

        return {
            'report_type': 'Payroll Summary',
            'period': {'month': month, 'year': year},
            'total_gross': total_gross,
            'total_deductions': total_deductions,
            'total_net': total_net,
            'employee_count': len(payroll_details),
            'details': payroll_details
        }

    @staticmethod
    def generate_attendance_report(start_date: date, end_date: date) -> Dict:
        from hrm.models import Attendance

        attendances = Attendance.objects.filter(
            date__gte=start_date,
            date__lte=end_date
        ).values('status').annotate(count=Count('id'))

        return {
            'report_type': 'Attendance Report',
            'period': {'start': start_date, 'end': end_date},
            'summary': list(attendances),
            'total_days': sum(a['count'] for a in attendances)
        }


class ProcurementReportService:
    @staticmethod
    def generate_purchase_summary(start_date: date, end_date: date) -> Dict:
        from procurement.models import PurchaseOrder

        orders = PurchaseOrder.objects.filter(
            order_date__gte=start_date,
            order_date__lte=end_date,
            status='Received'
        )

        total_purchases = orders.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

        return {
            'report_type': 'Purchase Summary',
            'period': {'start': start_date, 'end': end_date},
            'orders_count': orders.count(),
            'total_order_value': total_purchases,
        }

    @staticmethod
    def generate_vendors_report() -> Dict:
        from procurement.models import Vendor

        vendors = Vendor.objects.filter(is_active=True)

        vendor_list = []
        for vendor in vendors:
            total_orders = vendor.purchase_orders.count()
            total_purchases = vendor.purchase_orders.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

            vendor_list.append({
                'vendor_code': vendor.code,
                'vendor_name': vendor.name,
                'total_orders': total_orders,
                'total_purchases': total_purchases
            })

        return {
            'report_type': 'Vendors Report',
            'total_vendors': vendors.count(),
            'vendors': vendor_list
        }


class TaxReportService:
    """Service for generating tax reports"""

    @staticmethod
    def generate_vat_return(period_start: date, period_end: date, tenant_id: int = None) -> Dict:
        """
        Generate VAT return for a given period
        Returns output VAT, input VAT, and net payable
        """
        from accounting.models import JournalLine

        output_tax_query = JournalLine.objects.filter(
            header__posting_date__range=[period_start, period_end],
            header__status='Posted'
        ).select_related('account')

        input_tax_query = JournalLine.objects.filter(
            header__posting_date__range=[period_start, period_end],
            header__status='Posted'
        ).select_related('account')

        output_vat = Decimal('0')
        input_vat = Decimal('0')

        for line in output_tax_query:
            tax_codes = line.account.tax_codes.filter(tax_type='vat', direction='sales') if hasattr(line.account, 'tax_codes') else []
            if tax_codes.exists():
                output_vat += line.debit

        for line in input_tax_query:
            tax_codes = line.account.tax_codes.filter(tax_type='vat', direction='purchase') if hasattr(line.account, 'tax_codes') else []
            if tax_codes.exists():
                input_vat += line.credit

        net_vat_payable = output_vat - input_vat

        return {
            'report_type': 'VAT Return',
            'period': {'start': period_start, 'end': period_end},
            'output_vat': float(output_vat),
            'input_vat': float(input_vat),
            'net_vat_payable': float(net_vat_payable),
            'status': 'Payable' if net_vat_payable > 0 else ('Receivable' if net_vat_payable < 0 else 'Nil'),
        }

    @staticmethod
    def generate_withholding_tax_report(period_start: date, period_end: date) -> Dict:
        """Generate withholding tax report for a given period"""
        from accounting.models import JournalLine

        withholding_entries = JournalLine.objects.filter(
            header__posting_date__range=[period_start, period_end],
            header__status='Posted',
            account__withholding_tax_codes__isnull=False
        ).select_related('account', 'header')

        tax_summary = {}
        for line in withholding_entries:
            for wht in line.account.withholding_tax_codes.all():
                if wht.code not in tax_summary:
                    tax_summary[wht.code] = {
                        'name': wht.name,
                        'rate': float(wht.rate),
                        'total_withheld': Decimal('0'),
                        'count': 0
                    }
                tax_summary[wht.code]['total_withheld'] += line.credit
                tax_summary[wht.code]['count'] += 1

        return {
            'report_type': 'Withholding Tax Report',
            'period': {'start': period_start, 'end': period_end},
            'tax_summary': {k: {**v, 'total_withheld': float(v['total_withheld'])} for k, v in tax_summary.items()},
            'total_withheld': float(sum(v['total_withheld'] for v in tax_summary.values()))
        }


class BudgetReportService:
    """Service for generating budget reports"""

    @staticmethod
    def encumbrance_aging_report(fiscal_year: str, mda_id: int = None) -> Dict:
        """Generate encumbrance aging by days outstanding"""
        from budget.models import UnifiedBudgetEncumbrance

        encumbrances = UnifiedBudgetEncumbrance.objects.filter(
            status__in=['ACTIVE', 'PARTIALLY_LIQUIDATED'],
            budget__fiscal_year=fiscal_year
        ).select_related('budget', 'budget__mda', 'budget__account')

        if mda_id:
            encumbrances = encumbrances.filter(budget__mda_id=mda_id)

        aging = {
            '0-30': {'amount': Decimal('0'), 'count': 0},
            '31-60': {'amount': Decimal('0'), 'count': 0},
            '61-90': {'amount': Decimal('0'), 'count': 0},
            '90+': {'amount': Decimal('0'), 'count': 0}
        }

        today = date.today()

        for enc in encumbrances:
            days = (today - enc.encumbrance_date).days
            if days <= 30:
                aging['0-30']['amount'] += enc.remaining_amount
                aging['0-30']['count'] += 1
            elif days <= 60:
                aging['31-60']['amount'] += enc.remaining_amount
                aging['31-60']['count'] += 1
            elif days <= 90:
                aging['61-90']['amount'] += enc.remaining_amount
                aging['61-90']['count'] += 1
            else:
                aging['90+']['amount'] += enc.remaining_amount
                aging['90+']['count'] += 1

        return {
            'report_type': 'Encumbrance Aging Report',
            'fiscal_year': fiscal_year,
            'as_of_date': today.isoformat(),
            'aging': {k: {**v, 'amount': float(v['amount'])} for k, v in aging.items()},
            'total_amount': float(sum(v['amount'] for v in aging.values())),
            'total_count': sum(v['count'] for v in aging.values())
        }
