"""
Chart of Accounts seeder — covers ALL modules:
  Core Banking/Accounting | Sales | Procurement | Inventory |
  Production | HRM/Payroll | Service | Quality

Usage:
  python manage.py seed_coa              # idempotent: get_or_create only
  python manage.py seed_coa --force      # update_or_create (name/type sync)
  python manage.py seed_coa --reset      # DELETE all accounts then recreate
  python manage.py seed_coa --validate   # check every DEFAULT_GL_ACCOUNTS key resolves
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from accounting.models import Account


# =============================================================================
# Complete Chart of Accounts — 8-digit hierarchical codes
#   10xxxxxx  Assets
#   20xxxxxx  Liabilities
#   30xxxxxx  Equity
#   40xxxxxx  Income / Revenue
#   50xxxxxx  Cost of Goods Sold / Direct Costs
#   60-67xx   Operating Expenses
#   70xxxxxx  Procurement-specific
#   80xxxxxx  Inventory-specific
#   90-91xx   Service Module
#   92xxxxxx  Quality / Non-Conformance
#   95xxxxxx  Capital Assets / Fixed Assets
# =============================================================================
DEFAULT_CHART_OF_ACCOUNTS = [

    # =========================================================================
    # ASSETS (10000000 – 19999999)
    # =========================================================================

    # --- 101x Cash & Bank ---
    {'code': '10100000', 'name': 'Cash and Cash Equivalents',        'type': 'Asset'},
    # Bank reconciliation control accounts — is_reconciliation=True required for
    # BankAccount.gl_account FK filtering (limit_choices_to={'reconciliation_type': 'bank_accounting'})
    {'code': '10101000', 'name': 'Cash in Bank - Operating',         'type': 'Asset',
     'is_reconciliation': True, 'reconciliation_type': 'bank_accounting'},
    {'code': '10102000', 'name': 'Cash in Bank - Payroll',           'type': 'Asset',
     'is_reconciliation': True, 'reconciliation_type': 'bank_accounting'},
    {'code': '10103000', 'name': 'Cash in Bank - Project',           'type': 'Asset',
     'is_reconciliation': True, 'reconciliation_type': 'bank_accounting'},
    {'code': '10104000', 'name': 'Petty Cash',                       'type': 'Asset',
     'is_reconciliation': True, 'reconciliation_type': 'bank_accounting'},

    # --- 102x Accounts Receivable ---
    # AR control account — reconciliation_type drives aging report and customer ledger matching
    {'code': '10200000', 'name': 'Accounts Receivable',              'type': 'Asset',
     'is_reconciliation': True, 'reconciliation_type': 'accounts_receivable'},
    {'code': '10201000', 'name': 'Accounts Receivable - Trade',      'type': 'Asset'},
    {'code': '10202000', 'name': 'Accounts Receivable - Other',      'type': 'Asset'},
    {'code': '10203000', 'name': 'Accounts Receivable - Intercompany','type': 'Asset'},
    {'code': '10204000', 'name': 'Allowance for Doubtful Accounts',  'type': 'Asset'},

    # --- 103x Inventory ---
    # Inventory control account — reconciliation_type drives stock valuation reconciliation
    {'code': '10300000', 'name': 'Inventory',                        'type': 'Asset',
     'is_reconciliation': True, 'reconciliation_type': 'inventory'},
    {'code': '10301000', 'name': 'Inventory - Raw Materials',        'type': 'Asset'},
    {'code': '10302000', 'name': 'Inventory - Work in Progress',     'type': 'Asset'},
    {'code': '10303000', 'name': 'Inventory - Finished Goods',       'type': 'Asset'},
    {'code': '10304000', 'name': 'Inventory - Supplies',             'type': 'Asset'},
    {'code': '10305000', 'name': 'Inventory - Spare Parts',          'type': 'Asset'},

    # --- 104x Prepaid / Other Current Assets ---
    {'code': '10400000', 'name': 'Prepaid Expenses',                 'type': 'Asset'},
    {'code': '10401000', 'name': 'Prepaid Insurance',                'type': 'Asset'},
    {'code': '10402000', 'name': 'Prepaid Rent',                     'type': 'Asset'},
    {'code': '10403000', 'name': 'Prepaid Subscriptions',            'type': 'Asset'},

    # --- 105x Clearing / Transit Accounts (Inventory Module) ---
    #   Goods in Transit: debit at transfer-dispatch, credit at transfer-receive.
    #   Net = 0 once the receiving warehouse confirms; value never permanently sits here.
    {'code': '10500000', 'name': 'Goods in Transit',                 'type': 'Asset'},
    {'code': '10501000', 'name': 'Goods in Transit - Inter-Warehouse','type': 'Asset'},
    {'code': '10502000', 'name': 'Goods in Transit - Inbound',       'type': 'Asset'},

    # --- 111x Notes Receivable ---
    {'code': '11100000', 'name': 'Notes Receivable',                 'type': 'Asset'},
    {'code': '11101000', 'name': 'Notes Receivable - Current',       'type': 'Asset'},
    {'code': '11102000', 'name': 'Notes Receivable - Long-term',     'type': 'Asset'},
    {'code': '11200000', 'name': 'Interest Receivable',              'type': 'Asset'},
    {'code': '11300000', 'name': 'Due from Other Funds',             'type': 'Asset'},

    # --- 121x–125x Fixed Assets ─────────────────────────────────────────────
    #   Five major asset categories, each a reconciliation account so the
    #   asset subledger (FixedAsset records) can be reconciled to the GL.
    #   reconciliation_type='fixed_assets' lets the recon engine group them.

    # ── 1. Land ──────────────────────────────────────────────────────────
    #   Non-depreciable — no accumulated depreciation account needed.
    {'code': '12100000', 'name': 'Land',                             'type': 'Asset',
     'is_reconciliation': True, 'reconciliation_type': 'asset_accounting'},

    # ── 2. Buildings ─────────────────────────────────────────────────────
    {'code': '12200000', 'name': 'Buildings',                        'type': 'Asset',
     'is_reconciliation': True, 'reconciliation_type': 'asset_accounting'},
    {'code': '12201000', 'name': 'Building Improvements',            'type': 'Asset'},
    {'code': '12202000', 'name': 'Accumulated Depreciation - Buildings','type': 'Asset'},

    # ── 3. Equipment & Machinery ─────────────────────────────────────────
    {'code': '12300000', 'name': 'Equipment',                        'type': 'Asset',
     'is_reconciliation': True, 'reconciliation_type': 'asset_accounting'},
    {'code': '12301000', 'name': 'Office Equipment',                 'type': 'Asset'},
    {'code': '12302000', 'name': 'Computer Equipment',               'type': 'Asset'},
    {'code': '12304000', 'name': 'Machinery',                        'type': 'Asset'},
    {'code': '12306000', 'name': 'Accumulated Depreciation - Equipment','type': 'Asset'},

    # ── 4. Motor Vehicles ────────────────────────────────────────────────
    {'code': '12303000', 'name': 'Vehicles',                         'type': 'Asset',
     'is_reconciliation': True, 'reconciliation_type': 'asset_accounting'},
    {'code': '12307000', 'name': 'Accumulated Depreciation - Vehicles','type': 'Asset'},

    # ── 5. Furniture & Fixtures ──────────────────────────────────────────
    {'code': '12305000', 'name': 'Furniture and Fixtures',           'type': 'Asset',
     'is_reconciliation': True, 'reconciliation_type': 'asset_accounting'},
    {'code': '12308000', 'name': 'Accumulated Depreciation - Furniture','type': 'Asset'},

    # --- Intangible Assets ---
    {'code': '12400000', 'name': 'Intangible Assets',                'type': 'Asset'},
    {'code': '12401000', 'name': 'Software',                         'type': 'Asset'},
    {'code': '12402000', 'name': 'Patents and Trademarks',           'type': 'Asset'},
    {'code': '12403000', 'name': 'Accumulated Amortization',         'type': 'Asset'},
    {'code': '12500000', 'name': 'Construction in Progress',         'type': 'Asset'},

    # --- 131x Other Assets ---
    {'code': '13100000', 'name': 'Investments',                      'type': 'Asset'},
    {'code': '13101000', 'name': 'Long-term Investments',            'type': 'Asset'},
    {'code': '13200000', 'name': 'Deferred Charges',                 'type': 'Asset'},
    {'code': '13300000', 'name': 'Deposit on Purchases',             'type': 'Asset'},

    # =========================================================================
    # LIABILITIES (20000000 – 29999999)
    # =========================================================================

    # --- 201x Accounts Payable ---
    # AP control account — reconciliation_type drives aging report and vendor ledger matching
    {'code': '20100000', 'name': 'Accounts Payable',                 'type': 'Liability',
     'is_reconciliation': True, 'reconciliation_type': 'accounts_payable'},
    {'code': '20101000', 'name': 'Accounts Payable - Trade',         'type': 'Liability'},
    {'code': '20102000', 'name': 'Accounts Payable - Other',         'type': 'Liability'},
    {'code': '20103000', 'name': 'Accounts Payable - Intercompany',  'type': 'Liability'},

    # --- 202x Accrued Expenses (Payroll / HRM) ---
    {'code': '20200000', 'name': 'Accrued Expenses',                 'type': 'Liability'},
    {'code': '20201000', 'name': 'Accrued Salaries and Wages',       'type': 'Liability'},
    {'code': '20202000', 'name': 'Accrued Payroll Taxes',            'type': 'Liability'},
    {'code': '20203000', 'name': 'Accrued Employee Benefits',        'type': 'Liability'},
    {'code': '20204000', 'name': 'Accrued Rent',                     'type': 'Liability'},
    {'code': '20205000', 'name': 'Accrued Utilities',                'type': 'Liability'},

    # --- 203x Notes Payable ---
    {'code': '20300000', 'name': 'Notes Payable',                    'type': 'Liability'},
    {'code': '20301000', 'name': 'Notes Payable - Current',          'type': 'Liability'},
    {'code': '20302000', 'name': 'Notes Payable - Long-term',        'type': 'Liability'},

    # --- 204x Deferred Revenue ---
    {'code': '20400000', 'name': 'Deferred Revenue',                 'type': 'Liability'},
    {'code': '20401000', 'name': 'Deferred Income - Services',       'type': 'Liability'},
    {'code': '20402000', 'name': 'Unearned Revenue',                 'type': 'Liability'},

    # --- 205x Tax Payable (Sales / HRM) ---
    #   20500000 is the primary TAX_PAYABLE anchor — pointed to by DEFAULT_GL_ACCOUNTS.
    {'code': '20500000', 'name': 'Sales Tax Payable',                'type': 'Liability'},
    {'code': '20501000', 'name': 'VAT Payable',                      'type': 'Liability'},
    {'code': '20502000', 'name': 'Withholding Tax Payable',          'type': 'Liability'},
    # HRM: pension contributions withheld and owed to pension fund
    {'code': '20503000', 'name': 'Pension Payable',                  'type': 'Liability'},
    {'code': '20504000', 'name': 'PAYE Tax Payable',                 'type': 'Liability'},

    # --- 206x Other Current Liabilities & Clearing Accounts ---
    {'code': '20600000', 'name': 'Due to Other Funds',               'type': 'Liability'},
    # GR/IR Clearing: 3-way match P2P workflow. DR at GRN (goods received, invoice pending);
    # cleared when vendor invoice is matched. Net balance = unmatched GRN value.
    {'code': '20601000', 'name': 'GR/IR Clearing Account',           'type': 'Liability'},
    {'code': '20700000', 'name': 'Customer Deposits',                'type': 'Liability'},
    {'code': '20800000', 'name': 'Credit Notes Payable',             'type': 'Liability'},

    # --- 211x Long-term Liabilities ---
    {'code': '21100000', 'name': 'Bonds Payable',                    'type': 'Liability'},
    {'code': '21200000', 'name': 'Mortgages Payable',                'type': 'Liability'},
    {'code': '21300000', 'name': 'Capital Leases',                   'type': 'Liability'},
    {'code': '21400000', 'name': 'Pension Liability',                'type': 'Liability'},
    {'code': '21500000', 'name': 'Other Post-employment Benefits',   'type': 'Liability'},

    # =========================================================================
    # EQUITY (30000000 – 39999999)
    # =========================================================================
    {'code': '30100000', 'name': 'Fund Balance',                     'type': 'Equity'},
    {'code': '30101000', 'name': 'Fund Balance - Reserved',          'type': 'Equity'},
    {'code': '30102000', 'name': 'Fund Balance - Unreserved',        'type': 'Equity'},
    {'code': '30200000', 'name': 'Invested in Capital Assets',       'type': 'Equity'},
    {'code': '30300000', 'name': 'Contributed Capital',              'type': 'Equity'},
    {'code': '30400000', 'name': 'Retained Earnings',                'type': 'Equity'},
    {'code': '30401000', 'name': 'Retained Earnings - Appropriated', 'type': 'Equity'},
    {'code': '30402000', 'name': 'Retained Earnings - Unappropriated','type': 'Equity'},
    {'code': '30500000', 'name': 'Capital Surplus',                  'type': 'Equity'},
    {'code': '30600000', 'name': 'Accumulated Surplus/Deficit',      'type': 'Equity'},

    # =========================================================================
    # REVENUE (40000000 – 49999999)
    # =========================================================================

    # --- 401x Sales Module Revenue ---
    {'code': '40100000', 'name': 'Sales Revenue',                    'type': 'Income'},
    {'code': '40101000', 'name': 'Sales Revenue - Products',         'type': 'Income'},
    {'code': '40102000', 'name': 'Sales Revenue - Services',         'type': 'Income'},
    {'code': '40103000', 'name': 'Sales Returns and Allowances',     'type': 'Income'},
    {'code': '40104000', 'name': 'Sales Discounts',                  'type': 'Income'},

    # --- 402x Service Module Revenue ---
    {'code': '40200000', 'name': 'Service Revenue',                  'type': 'Income'},
    {'code': '40201000', 'name': 'Service Revenue - Consulting',     'type': 'Income'},
    {'code': '40202000', 'name': 'Service Revenue - Maintenance',    'type': 'Income'},
    {'code': '40203000', 'name': 'Service Revenue - Installation',   'type': 'Income'},
    {'code': '40204000', 'name': 'Service Revenue - Repair',         'type': 'Income'},

    # --- 403x Other Operating Revenue ---
    {'code': '40300000', 'name': 'Contract Revenue',                 'type': 'Income'},
    {'code': '40400000', 'name': 'Rental Revenue',                   'type': 'Income'},
    {'code': '40500000', 'name': 'Commission Revenue',               'type': 'Income'},

    # --- 411x Other Income ---
    {'code': '41100000', 'name': 'Interest Income',                  'type': 'Income'},
    {'code': '41200000', 'name': 'Dividend Income',                  'type': 'Income'},
    {'code': '41300000', 'name': 'Gain on Asset Disposal',           'type': 'Income'},
    {'code': '41400000', 'name': 'Other Income',                     'type': 'Income'},
    {'code': '41500000', 'name': 'Grants and Subsidies',             'type': 'Income'},

    # --- 416x Inventory Adjustment Income (Inventory Module) ---
    #   Credited when a positive stock adjustment (gain) is posted.
    {'code': '41600000', 'name': 'Inventory Adjustment Income',      'type': 'Income'},
    {'code': '41601000', 'name': 'Inventory Gain - Physical Count',  'type': 'Income'},

    # =========================================================================
    # COST OF GOODS SOLD / DIRECT COSTS (50000000 – 59999999)
    # =========================================================================

    # --- 501x COGS (Sales + Delivery) ---
    {'code': '50100000', 'name': 'Cost of Goods Sold',               'type': 'Expense'},
    {'code': '50101000', 'name': 'Cost of Products Sold',            'type': 'Expense'},
    {'code': '50102000', 'name': 'Cost of Services Rendered',        'type': 'Expense'},

    # --- 502x Direct Labor (Production + HRM) ---
    {'code': '50200000', 'name': 'Direct Labor',                     'type': 'Expense'},
    {'code': '50201000', 'name': 'Direct Labor - Wages',             'type': 'Expense'},
    {'code': '50202000', 'name': 'Direct Labor - Benefits',          'type': 'Expense'},

    # --- 503x Direct Materials (Production BOM backflush) ---
    {'code': '50300000', 'name': 'Direct Materials',                 'type': 'Expense'},
    {'code': '50301000', 'name': 'Raw Materials Consumed',           'type': 'Expense'},
    {'code': '50302000', 'name': 'Direct Supplies',                  'type': 'Expense'},

    # --- 504x Manufacturing Overhead (Production) ---
    {'code': '50400000', 'name': 'Manufacturing Overhead',           'type': 'Expense'},
    {'code': '50401000', 'name': 'Depreciation - Manufacturing',     'type': 'Expense'},
    {'code': '50402000', 'name': 'Indirect Labor',                   'type': 'Expense'},
    {'code': '50403000', 'name': 'Indirect Materials',               'type': 'Expense'},

    # --- 505x Inventory Variance ---
    {'code': '50500000', 'name': 'Inventory Variance',               'type': 'Expense'},
    {'code': '50501000', 'name': 'Purchase Price Variance',          'type': 'Expense'},
    {'code': '50502000', 'name': 'Usage Variance',                   'type': 'Expense'},

    # =========================================================================
    # OPERATING EXPENSES (60000000 – 69999999)
    # =========================================================================

    # --- 601x Personnel Costs (HRM) ---
    {'code': '60100000', 'name': 'Salaries and Wages',               'type': 'Expense'},
    {'code': '60101000', 'name': 'Salaries - Administrative',        'type': 'Expense'},
    {'code': '60102000', 'name': 'Salaries - Sales',                 'type': 'Expense'},
    {'code': '60103000', 'name': 'Salaries - Operations',            'type': 'Expense'},
    {'code': '60200000', 'name': 'Employee Benefits',                'type': 'Expense'},
    {'code': '60201000', 'name': 'Health Insurance',                 'type': 'Expense'},
    {'code': '60202000', 'name': 'Pension Contributions',            'type': 'Expense'},
    {'code': '60203000', 'name': 'Payroll Taxes',                    'type': 'Expense'},
    {'code': '60204000', 'name': 'Workers Compensation',             'type': 'Expense'},
    {'code': '60300000', 'name': 'Training and Development',         'type': 'Expense'},
    {'code': '60301000', 'name': 'Employee Training',                'type': 'Expense'},
    {'code': '60302000', 'name': 'Recruitment Expenses',             'type': 'Expense'},

    # --- 611x Facilities ---
    {'code': '61100000', 'name': 'Rent Expense',                     'type': 'Expense'},
    {'code': '61101000', 'name': 'Office Rent',                      'type': 'Expense'},
    {'code': '61102000', 'name': 'Warehouse Rent',                   'type': 'Expense'},
    {'code': '61200000', 'name': 'Utilities',                        'type': 'Expense'},
    {'code': '61201000', 'name': 'Electricity',                      'type': 'Expense'},
    {'code': '61202000', 'name': 'Water and Sewer',                  'type': 'Expense'},
    {'code': '61203000', 'name': 'Telephone and Internet',           'type': 'Expense'},
    {'code': '61300000', 'name': 'Maintenance and Repairs',          'type': 'Expense'},
    {'code': '61301000', 'name': 'Building Maintenance',             'type': 'Expense'},
    {'code': '61302000', 'name': 'Equipment Maintenance',            'type': 'Expense'},
    {'code': '61303000', 'name': 'Vehicle Maintenance',              'type': 'Expense'},
    {'code': '61400000', 'name': 'Insurance Expense',                'type': 'Expense'},
    {'code': '61401000', 'name': 'Property Insurance',               'type': 'Expense'},
    {'code': '61402000', 'name': 'Liability Insurance',              'type': 'Expense'},

    # --- 621x Professional Services ---
    {'code': '62100000', 'name': 'Professional Fees',                'type': 'Expense'},
    {'code': '62101000', 'name': 'Legal Fees',                       'type': 'Expense'},
    {'code': '62102000', 'name': 'Accounting and Audit Fees',        'type': 'Expense'},
    {'code': '62103000', 'name': 'Consulting Fees',                  'type': 'Expense'},
    {'code': '62200000', 'name': 'Bank Charges',                     'type': 'Expense'},
    {'code': '62300000', 'name': 'Contract Labor',                   'type': 'Expense'},

    # --- 631x Marketing & Sales ---
    {'code': '63100000', 'name': 'Advertising and Promotion',        'type': 'Expense'},
    {'code': '63101000', 'name': 'Marketing Campaigns',              'type': 'Expense'},
    {'code': '63102000', 'name': 'Trade Shows',                      'type': 'Expense'},
    {'code': '63200000', 'name': 'Travel and Entertainment',         'type': 'Expense'},
    {'code': '63201000', 'name': 'Travel - Employees',               'type': 'Expense'},
    {'code': '63202000', 'name': 'Meals and Entertainment',          'type': 'Expense'},
    {'code': '63300000', 'name': 'Sales Commissions',                'type': 'Expense'},
    {'code': '63400000', 'name': 'Customer Discounts',               'type': 'Expense'},
    {'code': '63401000', 'name': 'Trade Discounts',                  'type': 'Expense'},
    {'code': '63402000', 'name': 'Cash Discounts',                   'type': 'Expense'},

    # --- 641x Office & Administrative ---
    {'code': '64100000', 'name': 'Office Supplies',                  'type': 'Expense'},
    {'code': '64200000', 'name': 'Postage and Shipping',             'type': 'Expense'},
    {'code': '64300000', 'name': 'Printing and Reproduction',        'type': 'Expense'},
    {'code': '64400000', 'name': 'Equipment Rental',                 'type': 'Expense'},
    {'code': '64500000', 'name': 'Software Subscriptions',           'type': 'Expense'},
    {'code': '64600000', 'name': 'Security Services',                'type': 'Expense'},
    {'code': '64700000', 'name': 'Cleaning Services',                'type': 'Expense'},

    # --- 651x Technology ---
    {'code': '65100000', 'name': 'IT Expenses',                      'type': 'Expense'},
    {'code': '65101000', 'name': 'Hardware Purchases',               'type': 'Expense'},
    {'code': '65102000', 'name': 'Software Licenses',                'type': 'Expense'},
    {'code': '65103000', 'name': 'Cloud Services',                   'type': 'Expense'},
    {'code': '65104000', 'name': 'IT Support Services',              'type': 'Expense'},

    # --- 661x Depreciation ---
    {'code': '66100000', 'name': 'Depreciation Expense',             'type': 'Expense'},
    {'code': '66101000', 'name': 'Depreciation - Buildings',         'type': 'Expense'},
    {'code': '66102000', 'name': 'Depreciation - Equipment',         'type': 'Expense'},
    {'code': '66103000', 'name': 'Depreciation - Vehicles',          'type': 'Expense'},
    {'code': '66104000', 'name': 'Depreciation - Furniture',         'type': 'Expense'},
    {'code': '66200000', 'name': 'Amortization Expense',             'type': 'Expense'},

    # --- 671x Other Expenses ---
    {'code': '67100000', 'name': 'Bad Debt Expense',                 'type': 'Expense'},
    {'code': '67200000', 'name': 'Interest Expense',                 'type': 'Expense'},
    {'code': '67201000', 'name': 'Interest on Loans',                'type': 'Expense'},
    {'code': '67202000', 'name': 'Interest on Bonds',                'type': 'Expense'},
    {'code': '67300000', 'name': 'Taxes and Licenses',               'type': 'Expense'},
    {'code': '67301000', 'name': 'Property Taxes',                   'type': 'Expense'},
    {'code': '67302000', 'name': 'Business Licenses',                'type': 'Expense'},
    {'code': '67400000', 'name': 'Loss on Asset Disposal',           'type': 'Expense'},
    {'code': '67500000', 'name': 'Miscellaneous Expenses',           'type': 'Expense'},
    {'code': '67600000', 'name': 'Contributions and Donations',      'type': 'Expense'},

    # =========================================================================
    # PROCUREMENT MODULE (70000000 – 79999999)
    # =========================================================================
    {'code': '70100000', 'name': 'Purchase Orders Expense',          'type': 'Expense'},
    {'code': '70200000', 'name': 'Procurement Admin Costs',          'type': 'Expense'},
    {'code': '70300000', 'name': 'Shipping and Freight In',          'type': 'Expense'},
    {'code': '70301000', 'name': 'Inbound Freight',                  'type': 'Expense'},
    {'code': '70302000', 'name': 'Customs and Duties',               'type': 'Expense'},
    {'code': '70400000', 'name': 'Inspection Costs',                 'type': 'Expense'},
    {'code': '70500000', 'name': 'Receiving Costs',                  'type': 'Expense'},
    {'code': '70600000', 'name': 'Storage Costs',                    'type': 'Expense'},
    {'code': '70700000', 'name': 'Inventory Write-offs',             'type': 'Expense'},
    # Contra-expense accounts: credit balances reduce procurement cost.
    # Typed as Expense (not Income) to match the 7x = Expense number series.
    {'code': '70800000', 'name': 'Vendor Rebates',                   'type': 'Expense'},
    {'code': '70900000', 'name': 'Vendor Discounts Taken',           'type': 'Expense'},
    {'code': '70110000', 'name': 'Purchase Returns',                 'type': 'Expense'},
    {'code': '70120000', 'name': 'Vendor Credit Notes Applied',      'type': 'Expense'},

    # =========================================================================
    # INVENTORY MODULE (80000000 – 89999999)
    # =========================================================================
    {'code': '80100000', 'name': 'Inventory Valuation Adjustment',   'type': 'Expense'},
    {'code': '80200000', 'name': 'Obsolete Inventory Reserve',       'type': 'Expense'},
    {'code': '80300000', 'name': 'Inventory Counting Loss',          'type': 'Expense'},
    {'code': '80400000', 'name': 'Stock-out Costs',                  'type': 'Expense'},
    {'code': '80500000', 'name': 'Warehouse Labor',                  'type': 'Expense'},
    {'code': '80600000', 'name': 'Warehouse Equipment Depreciation', 'type': 'Expense'},
    {'code': '80700000', 'name': 'Packing Materials',                'type': 'Expense'},
    # Inventory Shrinkage: DR this / CR Inventory on negative ADJ movements
    {'code': '80800000', 'name': 'Inventory Shrinkage',              'type': 'Expense'},
    {'code': '80900000', 'name': 'Inventory Write-down Expense',     'type': 'Expense'},

    # =========================================================================
    # SERVICE MODULE (90000000 – 91999999)
    # =========================================================================

    # --- 90x Service Revenue ---
    {'code': '90100000', 'name': 'Service Revenue - Labor',          'type': 'Income'},
    {'code': '90200000', 'name': 'Service Revenue - Parts',          'type': 'Income'},
    {'code': '90300000', 'name': 'Service Revenue - Contracts',      'type': 'Income'},
    {'code': '90400000', 'name': 'Warranty Revenue',                 'type': 'Income'},

    # --- 90x Service Expenses ---
    {'code': '90500000', 'name': 'Technician Wages',                 'type': 'Expense'},
    {'code': '90600000', 'name': 'Technician Benefits',              'type': 'Expense'},
    {'code': '90700000', 'name': 'Service Vehicle Expenses',         'type': 'Expense'},
    {'code': '90800000', 'name': 'Service Tools and Equipment',      'type': 'Expense'},
    {'code': '90900000', 'name': 'Warranty Claims Expense',          'type': 'Expense'},

    # --- 91x Parts & Contract Costs ---
    {'code': '91000000', 'name': 'Parts Consumed',                   'type': 'Expense'},
    {'code': '91100000', 'name': 'Service Contract Expense',         'type': 'Expense'},
    {'code': '91200000', 'name': 'Customer Satisfaction Expense',    'type': 'Expense'},
    # SERVICE_EXPENSE: general service cost bucket (maps to DEFAULT_GL_ACCOUNTS key)
    {'code': '91500000', 'name': 'Service Expense',                  'type': 'Expense'},
    {'code': '91501000', 'name': 'Service Expense - Labour',         'type': 'Expense'},
    {'code': '91502000', 'name': 'Service Expense - Materials',      'type': 'Expense'},

    # =========================================================================
    # QUALITY MODULE (92000000 – 92999999)
    # =========================================================================
    # QC_EXPENSE: cost of quality inspections (maps to DEFAULT_GL_ACCOUNTS key)
    {'code': '92100000', 'name': 'Quality Control Expense',          'type': 'Expense'},
    {'code': '92101000', 'name': 'Quality Inspection Costs',         'type': 'Expense'},
    {'code': '92102000', 'name': 'Testing and Calibration',          'type': 'Expense'},
    # SCRAP_EXPENSE: scrapped material write-off (maps to DEFAULT_GL_ACCOUNTS key)
    {'code': '92200000', 'name': 'Scrap Expense',                    'type': 'Expense'},
    {'code': '92201000', 'name': 'Scrap Material Write-off',         'type': 'Expense'},
    {'code': '92300000', 'name': 'Non-Conformance Costs',            'type': 'Expense'},
    {'code': '92301000', 'name': 'Rework Costs',                     'type': 'Expense'},
    {'code': '92302000', 'name': 'Reject and Disposal Costs',        'type': 'Expense'},
    {'code': '92400000', 'name': 'Warranty Provision',               'type': 'Expense'},

    # =========================================================================
    # CAPITAL ASSETS / FIXED ASSETS MODULE (95000000 – 95999999)
    # All accounts in this range are Asset type to match '95' → 'Asset' series.
    # Impairment Loss (Expense) and Asset Retirement Obligation (Liability) are
    # relocated to their proper ranges below to avoid series type conflicts.
    # =========================================================================
    {'code': '95000000', 'name': 'Capital Expenditures',             'type': 'Asset'},
    {'code': '95100000', 'name': 'Assets Under Construction',        'type': 'Asset'},
    {'code': '95200000', 'name': 'Accumulated Impairment',           'type': 'Asset'},

    # Impairment Loss → 66x Depreciation/Amortization expense range
    {'code': '66300000', 'name': 'Impairment Loss',                  'type': 'Expense'},

    # Asset Retirement Obligation → 21x Long-term Liabilities range
    {'code': '21600000', 'name': 'Asset Retirement Obligation',      'type': 'Liability'},
]


class Command(BaseCommand):
    help = (
        'Seed default Chart of Accounts for all modules.\n'
        '  --reset     Delete ALL existing accounts then recreate (clean slate)\n'
        '  --force     update_or_create (sync names/types without deleting)\n'
        '  --validate  Verify every DEFAULT_GL_ACCOUNTS key resolves after seeding'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete ALL existing Account records before seeding (clean slate)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update existing accounts (name/type sync, no deletion)',
        )
        parser.add_argument(
            '--validate',
            action='store_true',
            help='After seeding, verify every DEFAULT_GL_ACCOUNTS key resolves to an Account',
        )

    def handle(self, *args, **options):
        reset    = options.get('reset', False)
        force    = options.get('force', False)
        validate = options.get('validate', False)

        # ── 1. Optional clean-slate wipe ──────────────────────────────────────
        if reset:
            deleted_count, _ = Account.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f'🗑  Deleted {deleted_count} existing accounts (--reset)')
            )
            # After reset, force=True so we create every record fresh
            force = True

        # ── 2. Seed ───────────────────────────────────────────────────────────
        created_count = 0
        updated_count = 0
        skipped_count = 0

        for acc_data in DEFAULT_CHART_OF_ACCOUNTS:
            code     = acc_data['code']
            name     = acc_data['name']
            acc_type = acc_data['type']   # already matches model choices exactly

            # Build the defaults dict; reconciliation fields are optional per-account
            account_defaults = {
                'name': name,
                'account_type': acc_type,
                'is_active': True,
            }
            if acc_data.get('is_reconciliation'):
                account_defaults['is_reconciliation']   = True
                account_defaults['reconciliation_type'] = acc_data.get('reconciliation_type', '')

            if force:
                _, created = Account.objects.update_or_create(
                    code=code,
                    defaults=account_defaults,
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1
            else:
                _, created = Account.objects.get_or_create(
                    code=code,
                    defaults=account_defaults,
                )
                if created:
                    created_count += 1
                else:
                    skipped_count += 1

        # ── 3. Summary ────────────────────────────────────────────────────────
        total = Account.objects.count()
        self.stdout.write(self.style.SUCCESS('\n✅ Chart of Accounts seeded successfully!'))
        self.stdout.write(self.style.SUCCESS(f'   Created  : {created_count} accounts'))
        if force:
            self.stdout.write(self.style.SUCCESS(f'   Updated  : {updated_count} accounts'))
        else:
            self.stdout.write(self.style.SUCCESS(f'   Skipped  : {skipped_count} accounts (already exist)'))
        self.stdout.write(self.style.SUCCESS(f'   Total DB : {total} accounts'))

        self.stdout.write(self.style.WARNING('\n📊 Account Summary by Type:'))
        for acc_type, label in [
            ('Asset',     'Assets'),
            ('Liability', 'Liabilities'),
            ('Equity',    'Equity'),
            ('Income',    'Income / Revenue'),
            ('Expense',   'Expenses'),
        ]:
            count = Account.objects.filter(account_type=acc_type).count()
            self.stdout.write(f'   {label:<20}: {count}')

        # ── 4. Validate DEFAULT_GL_ACCOUNTS mapping ───────────────────────────
        if validate or reset:
            self._validate_gl_settings()

    def _validate_gl_settings(self):
        """
        Check that every code in DEFAULT_GL_ACCOUNTS resolves to an active Account.
        Reports missing accounts so operators can act before going live.
        """
        default_gl = getattr(settings, 'DEFAULT_GL_ACCOUNTS', {})
        if not default_gl:
            self.stdout.write(self.style.WARNING(
                '\n⚠  DEFAULT_GL_ACCOUNTS not found in settings — skipping validation.'
            ))
            return

        self.stdout.write(self.style.WARNING('\n🔍 Validating DEFAULT_GL_ACCOUNTS mapping…'))
        missing = []
        ok_count = 0

        for key, code in sorted(default_gl.items()):
            account = Account.objects.filter(code=code).first()
            if account:
                ok_count += 1
                self.stdout.write(f'   ✓  {key:<35} → {code}  ({account.name})')
            else:
                missing.append((key, code))
                self.stdout.write(
                    self.style.ERROR(f'   ✗  {key:<35} → {code}  *** NOT FOUND ***')
                )

        if missing:
            self.stdout.write(self.style.ERROR(
                f'\n❌ {len(missing)} GL account code(s) in DEFAULT_GL_ACCOUNTS '
                f'do not resolve to any Account record.\n'
                '   Add the missing codes to the seeder and re-run with --reset.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\n✅ All {ok_count} DEFAULT_GL_ACCOUNTS keys resolve correctly.'
            ))
