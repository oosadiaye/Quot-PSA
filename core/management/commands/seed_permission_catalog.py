"""
seed_permission_catalog
=======================
Idempotently seed the granular permission catalogue, the seven default
public-sector roles, and the canonical SoD rule set across one or all
tenant schemas.

Why these seven roles:
    Accountant General, Accounting Officer — accounting line of duty
    Procurement Administrator (Permanent Secretary) — procurement authoriser
    Budget Director, Budget Officer — budget line of duty
    Treasury Manager, Treasury Officer — treasury line of duty

Each role carries a curated default permission set. Tenants edit the
permissions through the role editor; **nothing here is hardcoded into
the runtime checks** — the runtime reads the saved DB rows. Re-running
this command refreshes the seed templates without overwriting tenant
edits (system rows are upserted by ``code``; non-system rows are
untouched).

Usage:

    # All tenants
    python manage.py seed_permission_catalog

    # One tenant
    python manage.py seed_permission_catalog --schema delta_state

    # Reset system rows back to canonical defaults (keep tenant edits
    # to non-system rows). Mostly used after a permission catalogue
    # extension lands in code.
    python manage.py seed_permission_catalog --refresh-system
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django_tenants.utils import get_tenant_model, schema_context


# ─── PERMISSION CATALOGUE ─────────────────────────────────────────────
#
# Each row: (code, module, resource, action, label, risk_level, sort).
# ``code`` is the stable string id used by signals, evaluators, and the
# UI — never rename without a data migration. Risk levels feed the UI
# badge colour: critical (red), high (orange), medium (amber), low (slate).

CATALOGUE: list[tuple[str, str, str, str, str, str, int]] = [
    # ─────── BUDGET ─────────────────────────────────────────────────
    ('budget.appropriation.view',     'budget', 'appropriation', 'view',     'View appropriations',                       'low',      10),
    ('budget.appropriation.create',   'budget', 'appropriation', 'create',   'Draft new appropriation lines',             'medium',   20),
    ('budget.appropriation.submit',   'budget', 'appropriation', 'submit',   'Submit appropriation for approval',         'medium',   30),
    ('budget.appropriation.approve',  'budget', 'appropriation', 'approve',  'Approve / enact appropriation',             'critical', 40),
    ('budget.appropriation.close',    'budget', 'appropriation', 'close',    'Close appropriation at FY end',             'high',     50),
    ('budget.virement.create',        'budget', 'virement',      'create',   'Initiate appropriation virement',           'medium',   60),
    ('budget.virement.approve',       'budget', 'virement',      'approve',  'Approve appropriation virement',            'high',     70),
    ('budget.warrant.view',           'budget', 'warrant',       'view',     'View warrants / AIE',                       'low',      80),
    ('budget.warrant.create',         'budget', 'warrant',       'create',   'Create warrant draft',                      'medium',   90),
    ('budget.warrant.release',        'budget', 'warrant',       'release',  'Release warrant (sign AIE)',                'critical', 100),
    ('budget.warrant.suspend',        'budget', 'warrant',       'suspend',  'Suspend a released warrant',                'high',     110),
    ('budget.revenue.view',           'budget', 'revenue',       'view',     'View revenue budget',                       'low',      120),
    ('budget.revenue.create',         'budget', 'revenue',       'create',   'Draft revenue targets',                     'medium',   130),
    ('budget.revenue.approve',        'budget', 'revenue',       'approve',  'Approve revenue targets',                   'high',     140),
    ('budget.report.execution',       'budget', 'report',        'execution','View budget-execution reports',             'low',      150),
    ('budget.report.variance',        'budget', 'report',        'variance', 'View variance / performance reports',       'low',      160),
    ('budget.warrant.configure',      'budget', 'warrant',       'configure','Configure warrant printout settings',       'medium',   170),

    # ─────── ACCOUNTING / GL ────────────────────────────────────────
    ('accounting.journal.view',       'accounting', 'journal', 'view',     'View journal entries',                       'low',      10),
    ('accounting.journal.create',     'accounting', 'journal', 'create',   'Create draft journal entry',                 'medium',   20),
    ('accounting.journal.submit',     'accounting', 'journal', 'submit',   'Submit journal for approval',                'medium',   30),
    ('accounting.journal.approve',    'accounting', 'journal', 'approve',  'Approve journal entry',                      'high',     40),
    ('accounting.journal.post',       'accounting', 'journal', 'post',     'Post journal to GL (immutable)',             'critical', 50),
    ('accounting.journal.reverse',    'accounting', 'journal', 'reverse',  'Reverse a posted journal',                   'critical', 60),
    ('accounting.coa.view',           'accounting', 'coa',     'view',     'View Chart of Accounts',                     'low',      70),
    ('accounting.coa.manage',         'accounting', 'coa',     'manage',   'Create / edit accounts & NCoA segments',     'high',     80),
    ('accounting.fiscalperiod.view',  'accounting', 'fiscalperiod', 'view',    'View fiscal periods',                    'low',      90),
    ('accounting.fiscalperiod.close', 'accounting', 'fiscalperiod', 'close',   'Close fiscal period',                    'critical', 100),
    ('accounting.payable.view',       'accounting', 'payable', 'view',     'View AP invoices',                           'low',      110),
    ('accounting.payable.create',     'accounting', 'payable', 'create',   'Enter vendor invoice',                       'medium',   120),
    ('accounting.payable.approve',    'accounting', 'payable', 'approve',  'Approve vendor invoice for payment',         'high',     130),
    ('accounting.payable.post',       'accounting', 'payable', 'post',     'Post AP invoice to GL',                      'critical', 140),
    ('accounting.receivable.view',    'accounting', 'receivable', 'view',  'View AR / customer invoices',                'low',      150),
    ('accounting.receivable.create',  'accounting', 'receivable', 'create','Raise customer invoice',                     'medium',   160),
    ('accounting.receivable.approve', 'accounting', 'receivable', 'approve','Approve customer invoice / write-off',      'high',     170),
    ('accounting.bankrec.create',     'accounting', 'bankrec', 'create',   'Prepare bank reconciliation',                'medium',   180),
    ('accounting.bankrec.approve',    'accounting', 'bankrec', 'approve',  'Approve bank reconciliation',                'high',     190),
    ('accounting.fixedasset.view',    'accounting', 'fixedasset', 'view',  'View fixed asset register',                  'low',      200),
    ('accounting.fixedasset.create',  'accounting', 'fixedasset', 'create','Capitalise / register fixed asset',          'medium',   210),
    ('accounting.fixedasset.dispose', 'accounting', 'fixedasset', 'dispose','Dispose / write-off fixed asset',           'high',     220),
    ('accounting.report.financials',  'accounting', 'report', 'financials','View IPSAS financial statements',            'low',      230),
    ('accounting.report.trialbal',    'accounting', 'report', 'trialbal',  'View trial balance',                         'low',      240),

    # ─────── TREASURY / TSA ─────────────────────────────────────────
    ('treasury.tsa.view',             'treasury', 'tsa',      'view',      'View TSA bank accounts',                     'low',      10),
    ('treasury.tsa.manage',           'treasury', 'tsa',      'manage',    'Add / edit TSA accounts',                    'critical', 20),
    ('treasury.voucher.view',         'treasury', 'voucher',  'view',      'View payment vouchers',                      'low',      30),
    ('treasury.voucher.create',       'treasury', 'voucher',  'create',    'Create draft payment voucher',               'medium',   40),
    ('treasury.voucher.check',        'treasury', 'voucher',  'check',     'Check payment voucher (4-eyes)',             'high',     50),
    ('treasury.voucher.audit',        'treasury', 'voucher',  'audit',     'Internal audit of payment voucher',          'high',     60),
    ('treasury.voucher.approve',      'treasury', 'voucher',  'approve',   'Approve / authorise payment voucher',        'critical', 70),
    ('treasury.voucher.schedule',     'treasury', 'voucher',  'schedule',  'Schedule voucher into bank file',            'high',     80),
    ('treasury.voucher.pay',          'treasury', 'voucher',  'pay',       'Mark voucher as paid (process cash-out)',    'critical', 90),
    ('treasury.voucher.cancel',       'treasury', 'voucher',  'cancel',    'Cancel a payment voucher',                   'high',     100),
    ('treasury.voucher.reverse',      'treasury', 'voucher',  'reverse',   'Reverse a paid voucher',                     'critical', 110),
    ('treasury.transfer.create',      'treasury', 'transfer', 'create',    'Initiate TSA-to-TSA bank transfer',          'high',     120),
    ('treasury.transfer.approve',     'treasury', 'transfer', 'approve',   'Approve TSA-to-TSA bank transfer',           'critical', 130),
    ('treasury.cashflow.view',        'treasury', 'cashflow', 'view',      'View cash-flow / TSA balance reports',       'low',      140),

    # ─────── PROCUREMENT ────────────────────────────────────────────
    ('procurement.vendor.view',       'procurement', 'vendor', 'view',     'View vendor master',                         'low',      10),
    ('procurement.vendor.create',     'procurement', 'vendor', 'create',   'Register new vendor',                        'medium',   20),
    ('procurement.vendor.approve',    'procurement', 'vendor', 'approve',  'Approve vendor registration',                'high',     30),
    ('procurement.vendor.suspend',    'procurement', 'vendor', 'suspend',  'Suspend / blacklist vendor',                 'high',     40),
    ('procurement.pr.view',           'procurement', 'pr',     'view',     'View purchase requisitions',                 'low',      50),
    ('procurement.pr.create',         'procurement', 'pr',     'create',   'Raise purchase requisition',                 'low',      60),
    ('procurement.pr.submit',         'procurement', 'pr',     'submit',   'Submit PR for approval',                     'medium',   70),
    ('procurement.pr.approve',        'procurement', 'pr',     'approve',  'Approve purchase requisition',               'high',     80),
    ('procurement.po.view',           'procurement', 'po',     'view',     'View purchase orders',                       'low',      90),
    ('procurement.po.create',         'procurement', 'po',     'create',   'Create purchase order from PR',              'medium',   100),
    ('procurement.po.approve',        'procurement', 'po',     'approve',  'Approve purchase order',                     'critical', 110),
    ('procurement.po.cancel',         'procurement', 'po',     'cancel',   'Cancel purchase order',                      'high',     120),
    ('procurement.grn.view',          'procurement', 'grn',    'view',     'View goods received notes',                  'low',      130),
    ('procurement.grn.post',          'procurement', 'grn',    'post',     'Post goods received note',                   'medium',   140),
    ('procurement.invoice.match',     'procurement', 'invoice','match',    '3-way invoice match',                        'medium',   150),
    ('procurement.invoice.approve',   'procurement', 'invoice','approve',  'Approve matched invoice for payment',        'high',     160),
    ('procurement.tender.view',       'procurement', 'tender', 'view',     'View tenders / RFQ',                         'low',      170),
    ('procurement.tender.create',     'procurement', 'tender', 'create',   'Open tender / issue RFQ',                    'medium',   180),
    ('procurement.tender.evaluate',   'procurement', 'tender', 'evaluate', 'Evaluate tender bids',                       'high',     190),
    ('procurement.tender.award',      'procurement', 'tender', 'award',    'Award tender to vendor',                     'critical', 200),

    # ─────── CONTRACTS / IPC ────────────────────────────────────────
    ('contracts.contract.view',       'contracts', 'contract', 'view',     'View contracts',                             'low',      10),
    ('contracts.contract.create',     'contracts', 'contract', 'create',   'Draft contract',                             'medium',   20),
    ('contracts.contract.activate',   'contracts', 'contract', 'activate', 'Activate (sign) contract',                   'critical', 30),
    ('contracts.contract.close',      'contracts', 'contract', 'close',    'Close contract',                             'high',     40),
    ('contracts.contract.variation',  'contracts', 'contract', 'variation','Raise contract variation / write-up',        'high',     50),
    ('contracts.contract.varapprove', 'contracts', 'contract', 'varapprove','Approve contract variation',                'critical', 60),
    ('contracts.mb.create',           'contracts', 'mb',       'create',   'Record measurement-book entry',              'medium',   70),
    ('contracts.mb.approve',          'contracts', 'mb',       'approve',  'Approve measurement book',                   'high',     80),
    ('contracts.ipc.view',            'contracts', 'ipc',      'view',     'View IPCs',                                  'low',      90),
    ('contracts.ipc.create',          'contracts', 'ipc',      'create',   'Draft IPC',                                  'medium',   100),
    ('contracts.ipc.submit',          'contracts', 'ipc',      'submit',   'Submit IPC',                                 'medium',   110),
    ('contracts.ipc.certify',         'contracts', 'ipc',      'certify',  'Certify IPC (technical)',                    'high',     120),
    ('contracts.ipc.approve',         'contracts', 'ipc',      'approve',  'Approve IPC for payment',                    'critical', 130),
    ('contracts.ipc.raise',           'contracts', 'ipc',      'raise',    'Raise payment voucher from IPC',             'high',     140),
    ('contracts.ipc.pay',             'contracts', 'ipc',      'pay',      'Mark IPC paid (cash-out)',                   'critical', 150),
    ('contracts.retention.release',   'contracts', 'retention','release',  'Release retention',                          'high',     160),

    # ─────── INVENTORY ──────────────────────────────────────────────
    ('inventory.item.view',           'inventory', 'item',     'view',     'View item master',                           'low',      10),
    ('inventory.item.manage',         'inventory', 'item',     'manage',   'Create / edit items',                        'medium',   20),
    ('inventory.stock.view',          'inventory', 'stock',    'view',     'View stock levels',                          'low',      30),
    ('inventory.stock.adjust',        'inventory', 'stock',    'adjust',   'Stock adjustment / write-off',               'high',     40),
    ('inventory.stock.transfer',      'inventory', 'stock',    'transfer', 'Inter-warehouse transfer',                   'medium',   50),
    ('inventory.warehouse.manage',    'inventory', 'warehouse','manage',   'Configure warehouses',                       'medium',   60),

    # ─────── HRM / PAYROLL ──────────────────────────────────────────
    ('hrm.employee.view',             'hrm', 'employee', 'view',           'View employee records',                      'low',      10),
    ('hrm.employee.manage',           'hrm', 'employee', 'manage',         'Create / edit employees',                    'medium',   20),
    ('hrm.payroll.view',              'hrm', 'payroll',  'view',           'View payroll runs',                          'low',      30),
    ('hrm.payroll.create',            'hrm', 'payroll',  'create',         'Create payroll run',                         'medium',   40),
    ('hrm.payroll.approve',           'hrm', 'payroll',  'approve',        'Approve payroll run',                        'critical', 50),
    ('hrm.payroll.post',              'hrm', 'payroll',  'post',           'Post payroll to GL',                         'critical', 60),
    ('hrm.leave.approve',             'hrm', 'leave',    'approve',        'Approve leave request',                      'medium',   70),

    # ─────── REVENUE (IGR) ──────────────────────────────────────────
    ('revenue.collection.view',       'revenue', 'collection', 'view',     'View revenue collections',                   'low',      10),
    ('revenue.collection.record',     'revenue', 'collection', 'record',   'Record revenue collection',                  'medium',   20),
    ('revenue.collection.refund',     'revenue', 'collection', 'refund',   'Process revenue refund',                     'high',     30),

    # ─────── REPORTING / AUDIT ──────────────────────────────────────
    ('reporting.ipsas.view',          'reporting', 'ipsas', 'view',        'View IPSAS reports',                         'low',      10),
    ('reporting.executive.view',      'reporting', 'executive', 'view',    'View executive dashboards',                  'low',      20),
    ('audit.trail.view',              'audit',     'trail',     'view',    'View audit trail',                           'medium',   10),
    ('audit.trail.export',            'audit',     'trail',     'export',  'Export audit trail (immutable signed)',      'high',     20),

    # ─────── ADMIN / RBAC ───────────────────────────────────────────
    ('admin.tenant.configure',        'admin', 'tenant', 'configure',      'Configure tenant settings',                  'critical', 10),
    ('admin.branding.configure',      'admin', 'branding', 'configure',    'Configure branding & company info',          'medium',   20),
    ('admin.fiscalyear.configure',    'admin', 'fiscalyear', 'configure',  'Configure fiscal years',                     'high',     30),
    ('rbac.role.view',                'rbac',  'role',  'view',            'View roles & permissions',                   'low',      10),
    ('rbac.role.manage',              'rbac',  'role',  'manage',          'Create / edit / delete roles',               'critical', 20),
    ('rbac.assignment.manage',        'rbac',  'assignment', 'manage',     'Assign / revoke roles for users',            'critical', 30),
    ('rbac.sod.manage',               'rbac',  'sod',   'manage',          'Create / edit SoD rules',                    'critical', 40),
    ('rbac.bypass_sod',               'rbac',  'sod',   'bypass',          'Bypass SoD checks (break-glass — audited)',  'critical', 50),
]


# ─── DEFAULT ROLES ────────────────────────────────────────────────────
#
# Each role is a curated default — admins can edit any of these
# permission sets through the UI without breaking anything; this seed
# upserts only the row, never rewrites the M2M unless ``--refresh-system``
# is passed (so admin edits to system roles persist).

ROLES: dict[str, dict] = {
    'accountant_general': {
        'name': 'Accountant General',
        'module': 'accounting',
        'role_type': 'manager',
        'description': (
            'Top-level accounting authority. Approves and posts journals, '
            'authorises payment vouchers, oversees fiscal-period close. '
            'Cannot create the artefacts they approve — SoD enforced via '
            'rule-driven evaluator.'
        ),
        'permissions': [
            'accounting.journal.view', 'accounting.journal.approve', 'accounting.journal.post', 'accounting.journal.reverse',
            'accounting.coa.view', 'accounting.coa.manage',
            'accounting.fiscalperiod.view', 'accounting.fiscalperiod.close',
            'accounting.payable.view', 'accounting.payable.approve', 'accounting.payable.post',
            'accounting.receivable.view', 'accounting.receivable.approve',
            'accounting.bankrec.approve',
            'accounting.fixedasset.view', 'accounting.fixedasset.dispose',
            'accounting.report.financials', 'accounting.report.trialbal',
            'treasury.voucher.view', 'treasury.voucher.approve',
            'treasury.tsa.view',
            'reporting.ipsas.view', 'reporting.executive.view',
            'audit.trail.view',
            'budget.report.execution', 'budget.report.variance',
        ],
    },
    'accounting_officer': {
        'name': 'Accounting Officer',
        'module': 'accounting',
        'role_type': 'officer',
        'description': (
            'Day-to-day GL data entry and reconciliation. Drafts journals, '
            'enters AP/AR invoices, prepares bank reconciliations.'
        ),
        'permissions': [
            'accounting.journal.view', 'accounting.journal.create', 'accounting.journal.submit',
            'accounting.coa.view',
            'accounting.fiscalperiod.view',
            'accounting.payable.view', 'accounting.payable.create',
            'accounting.receivable.view', 'accounting.receivable.create',
            'accounting.bankrec.create',
            'accounting.fixedasset.view', 'accounting.fixedasset.create',
            'accounting.report.trialbal',
            'budget.report.execution',
        ],
    },
    'procurement_admin': {
        'name': 'Procurement Administrator (Permanent Secretary)',
        'module': 'procurement',
        'role_type': 'manager',
        'description': (
            'Permanent Secretary level — approves POs and tenders, '
            'authorises vendor onboarding, awards contracts. Does not '
            'raise PRs (SoD).'
        ),
        'permissions': [
            'procurement.vendor.view', 'procurement.vendor.approve', 'procurement.vendor.suspend',
            'procurement.pr.view', 'procurement.pr.approve',
            'procurement.po.view', 'procurement.po.approve', 'procurement.po.cancel',
            'procurement.grn.view',
            'procurement.invoice.approve',
            'procurement.tender.view', 'procurement.tender.evaluate', 'procurement.tender.award',
            'contracts.contract.view', 'contracts.contract.activate', 'contracts.contract.varapprove',
            'audit.trail.view',
            'reporting.executive.view',
            'budget.report.execution',
        ],
    },
    'budget_director': {
        'name': 'Budget Director',
        'module': 'budget',
        'role_type': 'manager',
        'description': (
            'Heads the budget office. Approves appropriations and virements, '
            'releases warrants, owns the annual budget cycle.'
        ),
        'permissions': [
            'budget.appropriation.view', 'budget.appropriation.approve', 'budget.appropriation.close',
            'budget.virement.approve',
            'budget.warrant.view', 'budget.warrant.release', 'budget.warrant.suspend',
            'budget.revenue.view', 'budget.revenue.approve',
            'budget.report.execution', 'budget.report.variance',
            'budget.warrant.configure',
            'reporting.ipsas.view', 'reporting.executive.view',
            'audit.trail.view',
        ],
    },
    'budget_officer': {
        'name': 'Budget Officer',
        'module': 'budget',
        'role_type': 'officer',
        'description': (
            'Drafts appropriations, processes virement requests, monitors '
            'execution. Cannot approve their own work (SoD).'
        ),
        'permissions': [
            'budget.appropriation.view', 'budget.appropriation.create', 'budget.appropriation.submit',
            'budget.virement.create',
            'budget.warrant.view', 'budget.warrant.create',
            'budget.revenue.view', 'budget.revenue.create',
            'budget.report.execution', 'budget.report.variance',
        ],
    },
    'treasury_manager': {
        'name': 'Treasury Manager',
        'module': 'treasury',
        'role_type': 'manager',
        'description': (
            'Oversees TSA cash management. Approves payment vouchers, '
            'authorises bank transfers between TSA accounts.'
        ),
        'permissions': [
            'treasury.tsa.view', 'treasury.tsa.manage',
            'treasury.voucher.view', 'treasury.voucher.approve', 'treasury.voucher.cancel',
            'treasury.transfer.approve',
            'treasury.cashflow.view',
            'accounting.bankrec.approve',
            'reporting.ipsas.view', 'reporting.executive.view',
            'audit.trail.view',
        ],
    },
    'treasury_officer': {
        'name': 'Treasury Officer',
        'module': 'treasury',
        'role_type': 'officer',
        'description': (
            'Day-to-day cash operations. Creates and checks payment '
            'vouchers, schedules bank files, initiates TSA transfers.'
        ),
        'permissions': [
            'treasury.tsa.view',
            'treasury.voucher.view', 'treasury.voucher.create', 'treasury.voucher.check',
            'treasury.voucher.audit', 'treasury.voucher.schedule', 'treasury.voucher.pay',
            'treasury.transfer.create',
            'treasury.cashflow.view',
        ],
    },
}


# ─── DEFAULT SoD RULES ────────────────────────────────────────────────
#
# Each rule names two permissions that must not be exercised together
# on the same document (``same_document``) or held by the same user
# at all (``hold``). Tenants edit, deactivate, or extend these; the
# evaluator reads from the database every call so changes take effect
# immediately.

SOD_RULES: list[dict] = [
    # ── Procurement maker / checker chain ────────────────────────────
    {
        'code': 'sod.pr.maker_checker',
        'name': 'PR — raiser cannot approve own requisition',
        'permission_a': 'procurement.pr.create',
        'permission_b': 'procurement.pr.approve',
        'scope': 'same_document', 'severity': 'block',
        'description': 'PPA s.32 — purchase requisition approval must be performed by a different officer from the raiser.',
    },
    {
        'code': 'sod.po.maker_checker',
        'name': 'PO — creator cannot approve own purchase order',
        'permission_a': 'procurement.po.create',
        'permission_b': 'procurement.po.approve',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Authoriser of a PO must not be the same officer who created it.',
    },
    {
        'code': 'sod.invoice.match_approve',
        'name': 'Invoice — matcher cannot also approve match',
        'permission_a': 'procurement.invoice.match',
        'permission_b': 'procurement.invoice.approve',
        'scope': 'same_document', 'severity': 'block',
        'description': '3-way match is a control; approval of the match must be performed independently.',
    },
    {
        'code': 'sod.tender.evaluate_award',
        'name': 'Tender — evaluator cannot also award',
        'permission_a': 'procurement.tender.evaluate',
        'permission_b': 'procurement.tender.award',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Tender evaluation and award decision must be in different hands (PPA s.34).',
    },
    {
        'code': 'sod.vendor.create_approve',
        'name': 'Vendor — creator cannot approve own vendor record',
        'permission_a': 'procurement.vendor.create',
        'permission_b': 'procurement.vendor.approve',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Phantom-vendor risk — creator and approver must be different.',
    },

    # ── Accounting maker / checker chain ─────────────────────────────
    {
        'code': 'sod.journal.create_approve',
        'name': 'Journal — creator cannot approve own JV',
        'permission_a': 'accounting.journal.create',
        'permission_b': 'accounting.journal.approve',
        'scope': 'same_document', 'severity': 'block',
        'description': 'JV approval is the 2-eyes control on accounting entries.',
    },
    {
        'code': 'sod.journal.approve_post',
        'name': 'Journal — approver cannot also post',
        'permission_a': 'accounting.journal.approve',
        'permission_b': 'accounting.journal.post',
        'scope': 'same_document', 'severity': 'warn',
        'description': '4-eyes between approve and post is preferred; warn-only because the AG often legitimately holds both for adjusting entries.',
    },
    {
        'code': 'sod.payable.create_approve',
        'name': 'AP invoice — creator cannot approve own invoice',
        'permission_a': 'accounting.payable.create',
        'permission_b': 'accounting.payable.approve',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Approval of a vendor invoice must be performed by a different officer from the data-entry clerk.',
    },
    {
        'code': 'sod.bankrec.prepare_approve',
        'name': 'Bank reconciliation — preparer cannot approve',
        'permission_a': 'accounting.bankrec.create',
        'permission_b': 'accounting.bankrec.approve',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Bank-rec is a key control; preparer and approver must be different.',
    },

    # ── Budget maker / checker chain ─────────────────────────────────
    {
        'code': 'sod.appropriation.draft_approve',
        'name': 'Appropriation — drafter cannot approve own line',
        'permission_a': 'budget.appropriation.create',
        'permission_b': 'budget.appropriation.approve',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Drafter and approver of an appropriation line must be different.',
    },
    {
        'code': 'sod.virement.create_approve',
        'name': 'Virement — initiator cannot approve own virement',
        'permission_a': 'budget.virement.create',
        'permission_b': 'budget.virement.approve',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Virement approval must be by a different officer to prevent retroactive overrun hiding.',
    },
    {
        'code': 'sod.warrant.create_release',
        'name': 'Warrant — drafter cannot release the warrant',
        'permission_a': 'budget.warrant.create',
        'permission_b': 'budget.warrant.release',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Cash-release warrant must be signed (released) by the AG / budget director, not the drafter.',
    },

    # ── Treasury / payment chain ─────────────────────────────────────
    {
        'code': 'sod.voucher.create_check',
        'name': 'PV — creator cannot also check',
        'permission_a': 'treasury.voucher.create',
        'permission_b': 'treasury.voucher.check',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Voucher checker is the first 2-eyes step; cannot be performed by the creator.',
    },
    {
        'code': 'sod.voucher.check_approve',
        'name': 'PV — checker cannot approve same voucher',
        'permission_a': 'treasury.voucher.check',
        'permission_b': 'treasury.voucher.approve',
        'scope': 'same_document', 'severity': 'block',
        'description': '4-eyes — approval cannot be by the checker.',
    },
    {
        'code': 'sod.voucher.approve_pay',
        'name': 'PV — approver cannot also process payment',
        'permission_a': 'treasury.voucher.approve',
        'permission_b': 'treasury.voucher.pay',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Authorisation and cash-out must be in different hands.',
    },
    {
        'code': 'sod.transfer.create_approve',
        'name': 'TSA transfer — initiator cannot approve own transfer',
        'permission_a': 'treasury.transfer.create',
        'permission_b': 'treasury.transfer.approve',
        'scope': 'same_document', 'severity': 'block',
        'description': 'TSA-to-TSA transfer is high-risk; initiator and approver must differ.',
    },

    # ── Contract / IPC chain (the existing 5-stage signoff) ──────────
    {
        'code': 'sod.contract.create_activate',
        'name': 'Contract — creator cannot activate own contract',
        'permission_a': 'contracts.contract.create',
        'permission_b': 'contracts.contract.activate',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Contract activation must be by a different officer (mirrors existing contract_activation SoD).',
    },
    {
        'code': 'sod.ipc.submit_certify',
        'name': 'IPC — submitter cannot certify',
        'permission_a': 'contracts.ipc.submit',
        'permission_b': 'contracts.ipc.certify',
        'scope': 'same_document', 'severity': 'block',
        'description': 'IPC technical certification independent of submitter.',
    },
    {
        'code': 'sod.ipc.certify_approve',
        'name': 'IPC — certifier cannot approve',
        'permission_a': 'contracts.ipc.certify',
        'permission_b': 'contracts.ipc.approve',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Approval is the financial gate; certification is technical. Must be different actors.',
    },
    {
        'code': 'sod.ipc.approve_pay',
        'name': 'IPC — approver cannot mark paid',
        'permission_a': 'contracts.ipc.approve',
        'permission_b': 'contracts.ipc.pay',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Cash-out must be by treasury, not by the contract approver.',
    },
    {
        'code': 'sod.variation.create_approve',
        'name': 'Variation — raiser cannot approve own write-up',
        'permission_a': 'contracts.contract.variation',
        'permission_b': 'contracts.contract.varapprove',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Contract variation approval is a high-risk decision; cannot be by the raiser.',
    },

    # ── HRM / Payroll ────────────────────────────────────────────────
    {
        'code': 'sod.payroll.create_approve',
        'name': 'Payroll — creator cannot approve own run',
        'permission_a': 'hrm.payroll.create',
        'permission_b': 'hrm.payroll.approve',
        'scope': 'same_document', 'severity': 'block',
        'description': 'Payroll approval (large cash-out) must be 2-eyes from creation.',
    },
    {
        'code': 'sod.payroll.approve_post',
        'name': 'Payroll — approver cannot also post to GL',
        'permission_a': 'hrm.payroll.approve',
        'permission_b': 'hrm.payroll.post',
        'scope': 'same_document', 'severity': 'warn',
        'description': '4-eyes between payroll approve and GL post is preferred but optional for small entities.',
    },
]


class Command(BaseCommand):
    help = 'Seed permission catalogue, default roles, and SoD rules across tenants.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema', default=None,
            help='Schema name to seed. Default: every non-public tenant.',
        )
        parser.add_argument(
            '--refresh-system', action='store_true',
            help=(
                'Re-write system role permission M2Ms back to the canonical '
                'set defined in this seed. Without this flag, existing system '
                'roles keep whatever the admin edited via the UI.'
            ),
        )

    def handle(self, *args, **opts):
        schema = opts['schema']
        refresh = opts['refresh_system']

        Tenant = get_tenant_model()
        if schema:
            tenants = list(Tenant.objects.filter(schema_name=schema))
            if not tenants:
                self.stderr.write(self.style.ERROR(f'No tenant with schema={schema}'))
                return
        else:
            tenants = list(Tenant.objects.exclude(schema_name='public'))

        for tenant in tenants:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'\n=== {tenant.schema_name} ({tenant.name}) ==='
            ))
            try:
                with schema_context(tenant.schema_name):
                    self._seed_one(refresh)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f'  FAIL: {exc}'))

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Tenants processed: {len(tenants)}'
        ))

    @transaction.atomic
    def _seed_one(self, refresh: bool):
        from core.models import PermissionDefinition, Role, SoDRule

        # 1. Permission catalogue — upsert by code.
        catalogue_count = 0
        catalogue_index: dict[str, PermissionDefinition] = {}
        for code, module, resource, action, label, risk, sort in CATALOGUE:
            obj, _created = PermissionDefinition.objects.update_or_create(
                code=code,
                defaults={
                    'module':     module,
                    'resource':   resource,
                    'action':     action,
                    'label':      label,
                    'risk_level': risk,
                    'sort_order': sort,
                    'is_system':  True,
                },
            )
            catalogue_index[code] = obj
            catalogue_count += 1
        self.stdout.write(f'  permissions: {catalogue_count} upserted')

        # 2. Default roles — upsert by code.
        for code, spec in ROLES.items():
            role, created = Role.objects.update_or_create(
                code=code,
                defaults={
                    'name':        spec['name'],
                    'module':      spec['module'],
                    'role_type':   spec['role_type'],
                    'description': spec['description'],
                    'is_system':   True,
                    'is_active':   True,
                    # Boolean flags kept for backward compat with
                    # legacy permission-string consumers.
                    'can_view':    True,
                    'can_add':     spec['role_type'] == 'officer',
                    'can_change':  spec['role_type'] == 'officer',
                    'can_approve': spec['role_type'] == 'manager',
                    'can_post':    spec['role_type'] == 'manager',
                },
            )
            # Only refresh M2Ms when the role is brand-new OR the
            # operator explicitly asked. This preserves admin edits.
            if created or refresh:
                wanted = [
                    catalogue_index[c]
                    for c in spec['permissions']
                    if c in catalogue_index
                ]
                role.permissions.set(wanted)
                self.stdout.write(
                    f'  role: {code} ({"created" if created else "refreshed"}, '
                    f'{len(wanted)} perms)'
                )
            else:
                self.stdout.write(f'  role: {code} (kept existing edits)')

        # 3. SoD rules — upsert by code, refresh permission FKs.
        sod_count = 0
        for spec in SOD_RULES:
            try:
                pa = catalogue_index[spec['permission_a']]
                pb = catalogue_index[spec['permission_b']]
            except KeyError as missing:
                self.stderr.write(
                    f'  SoD rule {spec["code"]}: missing permission '
                    f'{missing} — skipped'
                )
                continue
            SoDRule.objects.update_or_create(
                code=spec['code'],
                defaults={
                    'name':         spec['name'],
                    'description':  spec['description'],
                    'permission_a': pa,
                    'permission_b': pb,
                    'scope':        spec['scope'],
                    'severity':     spec['severity'],
                    'is_active':    True,
                    'is_system':    True,
                },
            )
            sod_count += 1
        self.stdout.write(f'  sod rules: {sod_count} upserted')
