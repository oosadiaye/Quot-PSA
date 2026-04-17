"""
Seeds Nigeria NCoA Economic Segment codes (~90 core posting-level accounts).
Based on OAGF NCoA v2.0 and NGF GIFMIS Chart of Accounts.
Run: python manage.py seed_ncoa_economic
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from accounting.models.ncoa import EconomicSegment

# fmt: off
ECONOMIC_CODES = [
    # ── REVENUE (1xxxxxxx) ────────────────────────────────────────────
    {'code': '10000000', 'name': 'Revenue',                        'type': '1', 'sub': '0', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '11000000', 'name': 'Tax Revenue',                    'type': '1', 'sub': '1', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '11100100', 'name': 'Pay As You Earn (PAYE)',         'type': '1', 'sub': '1', 'cls': '10', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '11100200', 'name': 'Direct Assessment Tax',          'type': '1', 'sub': '1', 'cls': '10', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '11100300', 'name': 'Road Tax',                       'type': '1', 'sub': '1', 'cls': '10', 'sub_cls': '03', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '11100400', 'name': 'Stamp Duty',                     'type': '1', 'sub': '1', 'cls': '10', 'sub_cls': '04', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '11100500', 'name': 'Capital Gains Tax (CGT)',        'type': '1', 'sub': '1', 'cls': '10', 'sub_cls': '05', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '11100600', 'name': 'Withholding Tax (WHT)',          'type': '1', 'sub': '1', 'cls': '10', 'sub_cls': '06', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '11100700', 'name': 'Business Premises Levy',         'type': '1', 'sub': '1', 'cls': '10', 'sub_cls': '07', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '12000000', 'name': 'Non-Tax Revenue',                'type': '1', 'sub': '2', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '12100100', 'name': 'Fees and Fines',                 'type': '1', 'sub': '2', 'cls': '10', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '12100200', 'name': 'Licenses and Permits',           'type': '1', 'sub': '2', 'cls': '10', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '12100300', 'name': 'Rent on Government Property',    'type': '1', 'sub': '2', 'cls': '10', 'sub_cls': '03', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '12100400', 'name': 'Interest Income',                'type': '1', 'sub': '2', 'cls': '10', 'sub_cls': '04', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '12100500', 'name': 'Dividends from Gov Companies',   'type': '1', 'sub': '2', 'cls': '10', 'sub_cls': '05', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '12100700', 'name': 'Miscellaneous Revenue',          'type': '1', 'sub': '2', 'cls': '10', 'sub_cls': '07', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '13000000', 'name': 'Grants and Transfers',           'type': '1', 'sub': '3', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '13100100', 'name': 'FAAC — Statutory Allocation',    'type': '1', 'sub': '3', 'cls': '10', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '13100200', 'name': 'FAAC — VAT Distribution',        'type': '1', 'sub': '3', 'cls': '10', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '13100300', 'name': 'FAAC — Excess Crude Account',    'type': '1', 'sub': '3', 'cls': '10', 'sub_cls': '03', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    {'code': '13200100', 'name': 'Grants — Development Partners',  'type': '1', 'sub': '3', 'cls': '20', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Income'},
    # ── EXPENDITURE (2xxxxxxx) ────────────────────────────────────────
    {'code': '20000000', 'name': 'Expenditure',                    'type': '2', 'sub': '0', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '21000000', 'name': 'Personnel Costs',                'type': '2', 'sub': '1', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '21100100', 'name': 'Basic Salaries',                 'type': '2', 'sub': '1', 'cls': '10', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '21100200', 'name': 'Housing Allowance',              'type': '2', 'sub': '1', 'cls': '10', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '21100300', 'name': 'Transport Allowance',            'type': '2', 'sub': '1', 'cls': '10', 'sub_cls': '03', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '21100400', 'name': 'Leave Allowance',                'type': '2', 'sub': '1', 'cls': '10', 'sub_cls': '04', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '21100500', 'name': 'Overtime Payments',              'type': '2', 'sub': '1', 'cls': '10', 'sub_cls': '05', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '21200100', 'name': 'Employer Pension (10% CPS)',     'type': '2', 'sub': '1', 'cls': '20', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '21200200', 'name': 'NHF Contribution (Employer)',    'type': '2', 'sub': '1', 'cls': '20', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '21300100', 'name': 'Pensions Paid (Retirees)',       'type': '2', 'sub': '1', 'cls': '30', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '21300200', 'name': 'Gratuities',                     'type': '2', 'sub': '1', 'cls': '30', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '22000000', 'name': 'Operations & Maintenance',       'type': '2', 'sub': '2', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '22100100', 'name': 'Travel and Transport',           'type': '2', 'sub': '2', 'cls': '10', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '22100200', 'name': 'Utilities (Electricity/Water)',  'type': '2', 'sub': '2', 'cls': '10', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '22100300', 'name': 'Materials and Supplies',         'type': '2', 'sub': '2', 'cls': '10', 'sub_cls': '03', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '22100400', 'name': 'Maintenance of Buildings',       'type': '2', 'sub': '2', 'cls': '10', 'sub_cls': '04', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '22100500', 'name': 'Maintenance of Vehicles',        'type': '2', 'sub': '2', 'cls': '10', 'sub_cls': '05', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '22100700', 'name': 'Consultancy Services',           'type': '2', 'sub': '2', 'cls': '10', 'sub_cls': '07', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '22100800', 'name': 'Training and Capacity Building', 'type': '2', 'sub': '2', 'cls': '10', 'sub_cls': '08', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '23000000', 'name': 'Capital Expenditure',            'type': '2', 'sub': '3', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '23100100', 'name': 'Acquisition of Land',            'type': '2', 'sub': '3', 'cls': '10', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '23100200', 'name': 'Construction of Buildings',      'type': '2', 'sub': '3', 'cls': '10', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '23100300', 'name': 'Purchase of Vehicles',           'type': '2', 'sub': '3', 'cls': '10', 'sub_cls': '03', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '23100400', 'name': 'Purchase of Plant and Equipment','type': '2', 'sub': '3', 'cls': '10', 'sub_cls': '04', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '23100500', 'name': 'Purchase of ICT Equipment',      'type': '2', 'sub': '3', 'cls': '10', 'sub_cls': '05', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '23100600', 'name': 'Construction of Infrastructure', 'type': '2', 'sub': '3', 'cls': '10', 'sub_cls': '06', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '24000000', 'name': 'Debt Service',                   'type': '2', 'sub': '4', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '24100100', 'name': 'Domestic Loan Interest',         'type': '2', 'sub': '4', 'cls': '10', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '24200100', 'name': 'Domestic Loan Repayment',        'type': '2', 'sub': '4', 'cls': '20', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '25000000', 'name': 'Transfers and Subventions',      'type': '2', 'sub': '5', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '25100100', 'name': 'Subvention to Parastatals',      'type': '2', 'sub': '5', 'cls': '10', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    {'code': '25100200', 'name': 'Social Benefits',                'type': '2', 'sub': '5', 'cls': '10', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Expense'},
    # ── ASSETS (3xxxxxxx) ────────────────────────────────────────────
    {'code': '30000000', 'name': 'Assets',                         'type': '3', 'sub': '0', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Asset'},
    {'code': '31000000', 'name': 'Current Assets',                 'type': '3', 'sub': '1', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Asset'},
    {'code': '31100100', 'name': 'Cash in TSA — Main Account',     'type': '3', 'sub': '1', 'cls': '10', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Asset'},
    {'code': '31100200', 'name': 'Cash in TSA — Sub-Accounts',     'type': '3', 'sub': '1', 'cls': '10', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Asset'},
    {'code': '31100300', 'name': 'Petty Cash',                     'type': '3', 'sub': '1', 'cls': '10', 'sub_cls': '03', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Asset'},
    {'code': '31200100', 'name': 'Tax Revenue Receivables',        'type': '3', 'sub': '1', 'cls': '20', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': True,  'balance': 'DEBIT',  'legacy': 'Asset'},
    {'code': '31300100', 'name': 'Advances — Personal',            'type': '3', 'sub': '1', 'cls': '30', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Asset'},
    {'code': '31300200', 'name': 'Advances — Project',             'type': '3', 'sub': '1', 'cls': '30', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Asset'},
    {'code': '31400100', 'name': 'Stores and Inventory',           'type': '3', 'sub': '1', 'cls': '40', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': True,  'balance': 'DEBIT',  'legacy': 'Asset'},
    {'code': '32000000', 'name': 'Non-Current Assets',             'type': '3', 'sub': '2', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Asset'},
    {'code': '32100100', 'name': 'Land (at cost)',                  'type': '3', 'sub': '2', 'cls': '10', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Asset'},
    {'code': '32100200', 'name': 'Buildings (at cost)',             'type': '3', 'sub': '2', 'cls': '10', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Asset'},
    {'code': '32100300', 'name': 'Accum. Depreciation — Buildings','type': '3', 'sub': '2', 'cls': '10', 'sub_cls': '03', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Asset'},
    {'code': '32200100', 'name': 'Plant and Equipment (at cost)',   'type': '3', 'sub': '2', 'cls': '20', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Asset'},
    {'code': '32300100', 'name': 'Vehicles (at cost)',              'type': '3', 'sub': '2', 'cls': '30', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Asset'},
    {'code': '32400100', 'name': 'Capital Work-in-Progress (CWIP)','type': '3', 'sub': '2', 'cls': '40', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'DEBIT',  'legacy': 'Asset'},
    # ── LIABILITIES AND NET ASSETS (4xxxxxxx) ────────────────────────
    {'code': '40000000', 'name': 'Liabilities and Net Assets',     'type': '4', 'sub': '0', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Liability'},
    {'code': '41000000', 'name': 'Current Liabilities',            'type': '4', 'sub': '1', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Liability'},
    {'code': '41100100', 'name': 'Accounts Payable — Vendors',     'type': '4', 'sub': '1', 'cls': '10', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': True,  'balance': 'CREDIT', 'legacy': 'Liability'},
    {'code': '41200100', 'name': 'PAYE Payable (to SIRS/FIRS)',    'type': '4', 'sub': '1', 'cls': '20', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Liability'},
    {'code': '41200200', 'name': 'Pension Payable — Employee (8%)','type': '4', 'sub': '1', 'cls': '20', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Liability'},
    {'code': '41200300', 'name': 'Pension Payable — Employer(10%)','type': '4', 'sub': '1', 'cls': '20', 'sub_cls': '03', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Liability'},
    {'code': '41200400', 'name': 'NHF Payable (2.5%)',             'type': '4', 'sub': '1', 'cls': '20', 'sub_cls': '04', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Liability'},
    {'code': '41200500', 'name': 'NHIS Payable',                   'type': '4', 'sub': '1', 'cls': '20', 'sub_cls': '05', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Liability'},
    {'code': '41200600', 'name': 'Salary Payable — Net',           'type': '4', 'sub': '1', 'cls': '20', 'sub_cls': '06', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Liability'},
    {'code': '41300100', 'name': 'Deposits Received',              'type': '4', 'sub': '1', 'cls': '30', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Liability'},
    {'code': '42000000', 'name': 'Non-Current Liabilities',        'type': '4', 'sub': '2', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Liability'},
    {'code': '42100100', 'name': 'Domestic Borrowings — Bonds',    'type': '4', 'sub': '2', 'cls': '10', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Liability'},
    {'code': '42100200', 'name': 'Domestic Borrowings — Loans',    'type': '4', 'sub': '2', 'cls': '10', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Liability'},
    {'code': '42200100', 'name': 'Foreign Loans',                  'type': '4', 'sub': '2', 'cls': '20', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Liability'},
    {'code': '43000000', 'name': 'Net Assets / Equity',            'type': '4', 'sub': '3', 'cls': '00', 'sub_cls': '00', 'item': '00', 'posting': False, 'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Equity'},
    {'code': '43100100', 'name': 'Accumulated Fund / Fund Balance','type': '4', 'sub': '3', 'cls': '10', 'sub_cls': '01', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Equity'},
    {'code': '43100200', 'name': 'Statutory Reserve',              'type': '4', 'sub': '3', 'cls': '10', 'sub_cls': '02', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Equity'},
    {'code': '43100300', 'name': 'Surplus/(Deficit) Current Year', 'type': '4', 'sub': '3', 'cls': '10', 'sub_cls': '03', 'item': '00', 'posting': True,  'ctrl': False, 'balance': 'CREDIT', 'legacy': 'Equity'},
]
# fmt: on


class Command(BaseCommand):
    help = 'Seed Nigeria NCoA Economic Segment codes (OAGF v2.0 standard)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Clear existing economic segments before seeding',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['clear']:
            EconomicSegment.objects.all().delete()
            self.stdout.write(self.style.WARNING('Cleared existing economic segments.'))

        created = updated = 0
        for entry in ECONOMIC_CODES:
            obj, was_created = EconomicSegment.objects.update_or_create(
                code=entry['code'],
                defaults={
                    'name':               entry['name'],
                    'account_type_code':  entry['type'],
                    'sub_type_code':      entry['sub'],
                    'account_class_code': entry['cls'],
                    'sub_class_code':     entry['sub_cls'],
                    'line_item_code':     entry['item'],
                    'is_posting_level':   entry['posting'],
                    'is_control_account': entry['ctrl'],
                    'normal_balance':     entry['balance'],
                    'legacy_account_type': entry['legacy'],
                    'is_active':          True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        # Set parent FKs
        self._set_parents()

        self.stdout.write(self.style.SUCCESS(
            f'NCoA Economic Segments: {created} created, {updated} updated. '
            f'Total: {EconomicSegment.objects.count()}'
        ))

    def _set_parents(self):
        """Link each account to its nearest parent header."""
        for seg in EconomicSegment.objects.filter(is_posting_level=True):
            parent_code = seg.code[:2] + '000000'
            if parent_code != seg.code:
                try:
                    seg.parent = EconomicSegment.objects.get(code=parent_code)
                    seg.save(update_fields=['parent'])
                except EconomicSegment.DoesNotExist:
                    pass
