"""XBRL Export Service

Provides XBRL/iXBRL export for financial reports:
- Balance Sheet
- Income Statement
- Cash Flow Statement
- Trial Balance
- Custom reports
"""
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field, asdict
from django.contrib.auth.models import User
from accounting.models import XBRLReport


@dataclass
class XBRLConcept:
    """Represents an XBRL concept/taxonomy element."""
    id: str
    name: str
    label: str
    type: str
    period_type: str
    balance_type: str
    parent_id: str = ''


@dataclass
class XBRLFact:
    """Represents a single fact in an XBRL report."""
    concept_id: str
    value: Any
    unit: str
    period: str
    decimals: int = 2
    context_ref: str = ''


@dataclass
class XBRLContext:
    """Represents an XBRL context."""
    id: str
    entity: str
    period_start: str
    period_end: str
    period_type: str


class XBRLExportService:
    """Service for XBRL export operations."""

    GAAP_TAXONOMY = {
        'Assets': XBRLConcept('Assets', 'Assets', 'Total Assets', 'numeric', 'duration', 'credit'),
        'CurrentAssets': XBRLConcept('CurrentAssets', 'CurrentAssets', 'Current Assets', 'numeric', 'duration', 'debit'),
        'CashAndCashEquivalents': XBRLConcept('CashAndCashEquivalents', 'CashAndCashEquivalents', 'Cash and Cash Equivalents', 'numeric', 'instant', 'debit'),
        'AccountsReceivable': XBRLConcept('AccountsReceivable', 'AccountsReceivable', 'Accounts Receivable', 'numeric', 'instant', 'debit'),
        'Inventory': XBRLConcept('Inventory', 'Inventory', 'Inventory', 'numeric', 'instant', 'debit'),
        'PrepaidExpenses': XBRLConcept('PrepaidExpenses', 'PrepaidExpenses', 'Prepaid Expenses', 'numeric', 'instant', 'debit'),
        'NonCurrentAssets': XBRLConcept('NonCurrentAssets', 'NonCurrentAssets', 'Non-Current Assets', 'numeric', 'duration', 'debit'),
        'PropertyPlantEquipment': XBRLConcept('PropertyPlantEquipment', 'PropertyPlantEquipment', 'Property, Plant & Equipment', 'numeric', 'instant', 'debit'),
        'AccumulatedDepreciation': XBRLConcept('AccumulatedDepreciation', 'AccumulatedDepreciation', 'Accumulated Depreciation', 'numeric', 'instant', 'credit'),
        'IntangibleAssets': XBRLConcept('IntangibleAssets', 'IntangibleAssets', 'Intangible Assets', 'numeric', 'instant', 'debit'),
        'Liabilities': XBRLConcept('Liabilities', 'Liabilities', 'Total Liabilities', 'numeric', 'duration', 'credit'),
        'CurrentLiabilities': XBRLConcept('CurrentLiabilities', 'CurrentLiabilities', 'Current Liabilities', 'numeric', 'duration', 'credit'),
        'AccountsPayable': XBRLConcept('AccountsPayable', 'AccountsPayable', 'Accounts Payable', 'numeric', 'instant', 'credit'),
        'AccruedExpenses': XBRLConcept('AccruedExpenses', 'AccruedExpenses', 'Accrued Expenses', 'numeric', 'instant', 'credit'),
        'ShortTermDebt': XBRLConcept('ShortTermDebt', 'ShortTermDebt', 'Short-Term Debt', 'numeric', 'instant', 'credit'),
        'NonCurrentLiabilities': XBRLConcept('NonCurrentLiabilities', 'NonCurrentLiabilities', 'Non-Current Liabilities', 'numeric', 'duration', 'credit'),
        'LongTermDebt': XBRLConcept('LongTermDebt', 'LongTermDebt', 'Long-Term Debt', 'numeric', 'instant', 'credit'),
        'Equity': XBRLConcept('Equity', 'Equity', 'Total Equity', 'numeric', 'duration', 'credit'),
        'RetainedEarnings': XBRLConcept('RetainedEarnings', 'RetainedEarnings', 'Retained Earnings', 'numeric', 'duration', 'credit'),
        'Revenue': XBRLConcept('Revenue', 'Revenue', 'Total Revenue', 'numeric', 'duration', 'credit'),
        'SalesRevenue': XBRLConcept('SalesRevenue', 'SalesRevenue', 'Sales Revenue', 'numeric', 'duration', 'credit'),
        'ServiceRevenue': XBRLConcept('ServiceRevenue', 'ServiceRevenue', 'Service Revenue', 'numeric', 'duration', 'credit'),
        'CostOfRevenue': XBRLConcept('CostOfRevenue', 'CostOfRevenue', 'Cost of Revenue', 'numeric', 'duration', 'debit'),
        'GrossProfit': XBRLConcept('GrossProfit', 'GrossProfit', 'Gross Profit', 'numeric', 'duration', 'credit'),
        'OperatingExpenses': XBRLConcept('OperatingExpenses', 'OperatingExpenses', 'Operating Expenses', 'numeric', 'duration', 'debit'),
        'SalariesAndWages': XBRLConcept('SalariesAndWages', 'SalariesAndWages', 'Salaries and Wages', 'numeric', 'duration', 'debit'),
        'RentExpense': XBRLConcept('RentExpense', 'RentExpense', 'Rent Expense', 'numeric', 'duration', 'debit'),
        'DepreciationExpense': XBRLConcept('DepreciationExpense', 'DepreciationExpense', 'Depreciation Expense', 'numeric', 'duration', 'debit'),
        'OperatingIncome': XBRLConcept('OperatingIncome', 'OperatingIncome', 'Operating Income', 'numeric', 'duration', 'credit'),
        'InterestExpense': XBRLConcept('InterestExpense', 'InterestExpense', 'Interest Expense', 'numeric', 'duration', 'debit'),
        'IncomeBeforeTax': XBRLConcept('IncomeBeforeTax', 'IncomeBeforeTax', 'Income Before Tax', 'numeric', 'duration', 'credit'),
        'IncomeTaxExpense': XBRLConcept('IncomeTaxExpense', 'IncomeTaxExpense', 'Income Tax Expense', 'numeric', 'duration', 'debit'),
        'NetIncome': XBRLConcept('NetIncome', 'NetIncome', 'Net Income', 'numeric', 'duration', 'credit'),
        'CashFlowFromOperations': XBRLConcept('CashFlowFromOperations', 'CashFlowFromOperations', 'Cash Flow from Operations', 'numeric', 'duration', 'direct'),
        'CashFlowFromInvesting': XBRLConcept('CashFlowFromInvesting', 'CashFlowFromInvesting', 'Cash Flow from Investing', 'numeric', 'duration', 'direct'),
        'CashFlowFromFinancing': XBRLConcept('CashFlowFromFinancing', 'CashFlowFromFinancing', 'Cash Flow from Financing', 'numeric', 'duration', 'direct'),
        'NetCashFlow': XBRLConcept('NetCashFlow', 'NetCashFlow', 'Net Cash Flow', 'numeric', 'duration', 'direct'),
    }

    @classmethod
    def get_financial_data(
        cls,
        fiscal_year: int,
        period_start: date,
        period_end: date,
        report_type: str
    ) -> Dict[str, Any]:
        """
        Get financial data for report generation.
        
        Args:
            fiscal_year: Fiscal year
            period_start: Period start date
            period_end: Period end date
            report_type: Type of report
            
        Returns:
            Dictionary with financial data
        """
        from accounting.models import GLBalance, Account
        
        accounts = Account.objects.filter(is_active=True)
        
        data = {}
        for concept_id, concept in cls.GAAP_TAXONOMY.items():
            if concept.period_type == 'instant':
                balances = GLBalance.objects.filter(
                    account__in=accounts,
                    fiscal_year=fiscal_year,
                    period=period_end.month
                )
            else:
                balances = GLBalance.objects.filter(
                    account__in=accounts,
                    fiscal_year=fiscal_year,
                    period__lte=period_end.month
                )
            
            if concept.balance_type == 'debit':
                total = sum(b.debit_balance for b in balances)
            else:
                total = sum(b.credit_balance for b in balances)
            
            data[concept_id] = float(total)
        
        return data

    @classmethod
    def generate_balance_sheet(
        cls,
        fiscal_year: int,
        period_end: date,
        user: User = None
    ) -> Tuple[str, int]:
        """
        Generate XBRL Balance Sheet.
        
        Args:
            fiscal_year: Fiscal year
            period_end: End date of period
            user: User generating report
            
        Returns:
            Tuple of (xbrl_content, file_size)
        """
        from accounting.models import Company
        
        context_id = f"CY{fiscal_year}"
        
        data = cls.get_financial_data(
            fiscal_year,
            date(fiscal_year, 1, 1),
            period_end,
            'balance_sheet'
        )
        
        xbrl = cls._generate_xbrl_header(
            report_type='BalanceSheet',
            fiscal_year=fiscal_year,
            period_end=period_end,
        )
        
        xbrl += cls._generate_xbrl_context(context_id, period_end, 'instant')
        xbrl += cls._generate_xbrl_units()
        
        for concept_id, concept in cls.GAAP_TAXONOMY.items():
            if concept_id in data and data[concept_id] != 0:
                xbrl += cls._generate_xbrl_fact(
                    concept_id, data[concept_id], context_id
                )
        
        xbrl += '</xbrli:xbrl>\n</html>'
        
        report = XBRLReport.objects.create(
            report_type='BalanceSheet',
            report_name=f'Balance Sheet FY{fiscal_year}',
            fiscal_year=fiscal_year,
            period_start=date(fiscal_year, 1, 1),
            period_end=period_end,
            content=xbrl,
            generated_by=user,
            file_size=len(xbrl.encode('utf-8')),
        )
        
        return xbrl, len(xbrl.encode('utf-8'))

    @classmethod
    def generate_income_statement(
        cls,
        fiscal_year: int,
        period_end: date,
        user: User = None
    ) -> Tuple[str, int]:
        """Generate XBRL Income Statement."""
        context_id = f"FY{fiscal_year}"
        
        data = cls.get_financial_data(
            fiscal_year,
            date(fiscal_year, 1, 1),
            period_end,
            'income_statement'
        )
        
        xbrl = cls._generate_xbrl_header(
            report_type='IncomeStatement',
            fiscal_year=fiscal_year,
            period_end=period_end,
        )
        
        xbrl += cls._generate_xbrl_context(context_id, period_end, 'duration')
        xbrl += cls._generate_xbrl_units()
        
        for concept_id, concept in cls.GAAP_TAXONOMY.items():
            if concept_id in data and data[concept_id] != 0:
                xbrl += cls._generate_xbrl_fact(
                    concept_id, data[concept_id], context_id
                )
        
        xbrl += '</xbrli:xbrl>\n</html>'
        
        report = XBRLReport.objects.create(
            report_type='IncomeStatement',
            report_name=f'Income Statement FY{fiscal_year}',
            fiscal_year=fiscal_year,
            period_start=date(fiscal_year, 1, 1),
            period_end=period_end,
            content=xbrl,
            generated_by=user,
            file_size=len(xbrl.encode('utf-8')),
        )
        
        return xbrl, len(xbrl.encode('utf-8'))

    @classmethod
    def generate_trial_balance(
        cls,
        fiscal_year: int,
        period: int,
        user: User = None
    ) -> Tuple[str, int]:
        """Generate XBRL Trial Balance."""
        from accounting.models import GLBalance, Account
        
        context_id = f"P{period}FY{fiscal_year}"
        
        xbrl = cls._generate_xbrl_header(
            report_type='TrialBalance',
            fiscal_year=fiscal_year,
            period_end=date(fiscal_year, period, 1),
        )
        
        xbrl += cls._generate_xbrl_context(
            context_id, 
            date(fiscal_year, period, 1), 
            'duration'
        )
        xbrl += cls._generate_xbrl_units()
        
        balances = GLBalance.objects.filter(
            fiscal_year=fiscal_year,
            period=period
        ).select_related('account')
        
        for balance in balances:
            xbrl += cls._generate_xbrl_fact(
                f"Account_{balance.account.code}",
                float(balance.debit_balance - balance.credit_balance),
                context_id
            )
        
        xbrl += '</xbrli:xbrl>\n</html>'
        
        report = XBRLReport.objects.create(
            report_type='TrialBalance',
            report_name=f'Trial Balance FY{fiscal_year} P{period}',
            fiscal_year=fiscal_year,
            period_start=date(fiscal_year, period, 1),
            period_end=date(fiscal_year, period, 28),
            content=xbrl,
            generated_by=user,
            file_size=len(xbrl.encode('utf-8')),
        )
        
        return xbrl, len(xbrl.encode('utf-8'))

    @classmethod
    def _generate_xbrl_header(
        cls,
        report_type: str,
        fiscal_year: int,
        period_end: date
    ) -> str:
        """Generate XBRL document header."""
        return f'''<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">
<head>
    <title>DTSG ERP - {report_type}</title>
    <meta charset="UTF-8"/>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .xbrl-table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        .xbrl-table th, .xbrl-table td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        .xbrl-table th {{ background-color: #f2f2f2; }}
        .xbrl-table .total-row {{ font-weight: bold; background-color: #f9f9f9; }}
        .header {{ text-align: center; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>DTSG ERP Financial Report</h1>
        <h2>{report_type}</h2>
        <p>Fiscal Year: {fiscal_year} | As of: {period_end}</p>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
<xbrli:xbrl>
'''

    @classmethod
    def _generate_xbrl_context(
        cls,
        context_id: str,
        period_date: date,
        period_type: str
    ) -> str:
        """Generate XBRL context element."""
        if period_type == 'instant':
            return f'''
    <xbrli:context id="{context_id}">
        <xbrli:entity>
            <xbrli:identifier scheme="http://dtsg-erp.com">DTSG</xbrli:identifier>
        </xbrli:entity>
        <xbrli:period>
            <xbrli:instant>{period_date.isoformat()}</xbrli:instant>
        </xbrli:period>
    </xbrli:context>
'''
        else:
            start_date = date(period_date.year, 1, 1)
            return f'''
    <xbrli:context id="{context_id}">
        <xbrli:entity>
            <xbrli:identifier scheme="http://dtsg-erp.com">DTSG</xbrli:identifier>
        </xbrli:entity>
        <xbrli:period>
            <xbrli:startDate>{start_date.isoformat()}</xbrli:startDate>
            <xbrli:endDate>{period_date.isoformat()}</xbrli:endDate>
        </xbrli:period>
    </xbrli:context>
'''

    @classmethod
    def _generate_xbrl_units(cls) -> str:
        """Generate XBRL unit elements."""
        return '''
    <xbrli:unit id="EUR">
        <xbrli:measure>iso4217:EUR</xbrli:measure>
    </xbrli:unit>
    <xbrli:unit id="USD">
        <xbrli:measure>iso4217:USD</xbrli:measure>
    </xbrli:unit>
    <xbrli:unit id="shares">
        <xbrli:measure>xbrli:shares</xbrli:measure>
    </xbrli:unit>
'''

    @classmethod
    def _generate_xbrl_fact(
        cls,
        concept_id: str,
        value: float,
        context_id: str
    ) -> str:
        """Generate XBRL fact element."""
        if value < 0:
            sign = '-'
            value = abs(value)
        else:
            sign = ''
        
        return f'''
    <dtsg:{concept_id} contextRef="{context_id}" decimals="2" unitRef="USD">{sign}{value:.2f}</dtsg:{concept_id}>
'''

    @classmethod
    def export_to_json(
        cls,
        fiscal_year: int,
        period_start: date,
        period_end: date,
        user: User = None
    ) -> Dict[str, Any]:
        """
        Export financial data to JSON format.
        
        Args:
            fiscal_year: Fiscal year
            period_start: Period start
            period_end: Period end
            user: User exporting
            
        Returns:
            Dictionary with financial data
        """
        data = cls.get_financial_data(
            fiscal_year, period_start, period_end, 'full_report'
        )
        
        return {
            'report_metadata': {
                'fiscal_year': fiscal_year,
                'period_start': period_start.isoformat(),
                'period_end': period_end.isoformat(),
                'generated_at': datetime.now().isoformat(),
                'generated_by': user.username if user else 'System',
                'taxonomy': 'DTSG-GAAP',
                'version': '1.0',
            },
            'financial_data': data,
            'concepts': {
                concept_id: asdict(concept) 
                for concept_id, concept in cls.GAAP_TAXONOMY.items()
            },
        }

    @classmethod
    def get_report_list(
        cls,
        report_type: str = None,
        fiscal_year: int = None
    ) -> List[Dict[str, Any]]:
        """Get list of generated reports."""
        reports = XBRLReport.objects.all()
        
        if report_type:
            reports = reports.filter(report_type=report_type)
        if fiscal_year:
            reports = reports.filter(fiscal_year=fiscal_year)
        
        return [
            {
                'id': r.id,
                'report_type': r.report_type,
                'report_name': r.report_name,
                'fiscal_year': r.fiscal_year,
                'period_start': str(r.period_start),
                'period_end': str(r.period_end),
                'generated_by': r.generated_by.username if r.generated_by else 'System',
                'generated_at': r.generated_at.isoformat(),
                'file_size': r.file_size,
            }
            for r in reports
        ]

    @classmethod
    def download_report(cls, report_id: int) -> Tuple[str, str]:
        """
        Get report content for download.
        
        Args:
            report_id: XBRLReport ID
            
        Returns:
            Tuple of (content, filename)
        """
        report = XBRLReport.objects.get(id=report_id)
        filename = f"{report.report_type}_{report.fiscal_year}.html"
        return report.content, filename
