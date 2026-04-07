"""
Management command to set up RBAC groups and permissions for all modules.

Creates 4 permission groups matching the UserTenantRole tiers:
  - Senior Manager: ALL permissions (CRUD + approve + post) across all modules
  - Mid-Level Manager: View + Add + Change, most approvals, NO delete, NO payroll approval
  - User: View + Add + Change on operational models, NO delete, NO approvals
  - Viewer: View-only across all modules

Usage:
    python manage.py setup_rbac
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


# ---------------------------------------------------------------------------
# Permission matrix — defines which codenames each group gets per module.
#
# For each module the helper `_expand` builds the full set:
#   'view'   → view_<model>
#   'add'    → add_<model>
#   'change' → change_<model>
#   'delete' → delete_<model>
#   'custom' → the literal codename (e.g. approve_purchaseorder)
# ---------------------------------------------------------------------------

# Models per module (lowercase)
ACCOUNTING_MODELS = [
    'fund', 'function', 'program', 'geo', 'account', 'mda',
    'journalheader', 'journalline', 'journalreversal', 'currency', 'glbalance',
    'budgetperiod', 'budget', 'budgetencumbrance', 'budgettransfer',
    'budgetforecast', 'budgetamendment', 'budgetanomaly',
    'bankaccount', 'vendorinvoice', 'payment', 'paymentallocation',
    'customerinvoice', 'receipt', 'receiptallocation',
    'fixedasset', 'depreciationschedule', 'costcenter',
    'checkbook', 'check', 'bankreconciliation',
    'cashflowcategory', 'cashflowforecast',
    'taxregistration', 'taxexemption', 'taxreturn', 'withholdingtax', 'taxcode',
    'profitcenter', 'costallocationrule',
    'fiscalperiod', 'fiscalyear', 'periodaccess',
    'recurringjournal', 'recurringjournalline', 'recurringjournalrun',
    'accrual', 'deferral', 'deferralrecognition',
    'accountingsettings',
]

BUDGET_MODELS = [
    'budgetallocation', 'budgetline', 'budgetvariance',
]

PROCUREMENT_MODELS = [
    'purchasetype', 'vendor', 'purchaserequest', 'purchaserequestline',
    'purchaseorder', 'purchaseorderline',
    'goodsreceivednote', 'goodsreceivednoteline',
    'invoicematching', 'vendorcreditnote', 'vendordebitnote',
    'purchasereturn', 'purchasereturnline',
]

INVENTORY_MODELS = [
    'warehouse', 'producttype', 'productcategory', 'itemcategory',
    'item', 'itemstock', 'itembatch', 'stockmovement',
    'stockreconciliation', 'stockreconciliationline',
    'reorderalert', 'itemserialnumber', 'batchexpiryalert',
]

SALES_MODELS = [
    'customer', 'lead', 'opportunity',
    'quotation', 'quotationline',
    'salesorder', 'salesorderline',
    'deliverynote', 'deliverynoteline',
]

SERVICE_MODELS = [
    'serviceasset', 'technician', 'serviceticket', 'slatracking',
    'workorder', 'workordermaterial', 'citizenrequest',
    'servicemetric', 'maintenanceschedule',
]

HRM_MODELS = [
    'department', 'position', 'employee',
    'leavetype', 'leaverequest', 'leavebalance',
    'attendance', 'holiday',
    'jobpost', 'candidate', 'interview', 'onboardingtask', 'onboardingprogress',
    'salarystructure', 'salarycomponent', 'salarystructuretemplate',
    'payrollperiod', 'payrollrun', 'payrollline', 'payrollearning', 'payrolldeduction', 'payslip',
    'performancecycle', 'performancegoal', 'performancereview', 'competency', 'competencyrating', 'promotion',
    'trainingprogram', 'trainingenrollment', 'skill', 'employeeskill', 'trainingplan', 'trainingplanline',
    'policy', 'policyacknowledgement', 'compliancerecord', 'compliancetask', 'auditlog',
    'exitrequest', 'exitinterview', 'exitclearance', 'finalsettlement', 'experiencecertificate', 'assetreturn',
]

PRODUCTION_MODELS = [
    'workcenter', 'billofmaterials', 'bomline',
    'productionorder', 'materialissue', 'materialreceipt',
    'jobcard', 'routing',
]

QUALITY_MODELS = [
    'qualityinspection', 'inspectionline', 'nonconformance',
    'customercomplaint', 'qualitychecklist', 'qualitychecklistline',
    'calibrationrecord', 'supplierquality',
]

WORKFLOW_MODELS = [
    'approvalgroup', 'approvaltemplate', 'approvaltemplatestep',
    'approval', 'approvalstep', 'approvallog',
    'workflowdefinition', 'workflowstep', 'workflowinstance', 'workflowlog',
]

ALL_MODELS = (
    ACCOUNTING_MODELS + BUDGET_MODELS + PROCUREMENT_MODELS +
    INVENTORY_MODELS + SALES_MODELS + SERVICE_MODELS +
    HRM_MODELS + PRODUCTION_MODELS + QUALITY_MODELS + WORKFLOW_MODELS
)

# Custom permissions (not CRUD)
CUSTOM_PERMISSIONS = [
    'post_journalheader', 'approve_journalheader',
    'approve_budget', 'approve_budgettransfer',
    'approve_purchaserequest', 'approve_purchaseorder',
    'approve_salesorder', 'approve_quotation',
    'process_payrollrun', 'approve_payrollrun', 'approve_leaverequest',
    'approve_productionorder',
    'approve_qualityinspection',
    'approve_stockmovement',
]

# Models that users should NOT have add/change access to
# (sensitive/admin-only even for regular users)
ADMIN_ONLY_MODELS = [
    'fund', 'function', 'program', 'geo', 'mda', 'account', 'currency',
    'budgetperiod', 'fiscalperiod', 'fiscalyear', 'periodaccess',
    'costcenter', 'profitcenter', 'costallocationrule',
    'taxregistration', 'taxcode', 'accountingsettings',
    'leavetype', 'salarystructure', 'salarycomponent', 'salarystructuretemplate',
    'approvalgroup', 'approvaltemplate', 'approvaltemplatestep',
    'workflowdefinition', 'workflowstep',
]

# Models that mid-level managers shouldn't edit (payroll, budget admin)
SENIOR_ONLY_EDIT_MODELS = [
    'payrollrun', 'payrollperiod', 'payrollline',
    'budget', 'budgetallocation', 'budgetamendment', 'budgettransfer',
    'fiscalperiod', 'fiscalyear', 'periodaccess',
]


class Command(BaseCommand):
    help = 'Setup RBAC groups with permissions for all modules'

    def handle(self, *args, **kwargs):
        self.stdout.write("Setting up RBAC Groups and Permissions...\n")

        # Build permission sets for each group
        senior_perms = self._build_senior_manager()
        manager_perms = self._build_mid_level_manager()
        user_perms = self._build_user()
        viewer_perms = self._build_viewer()

        groups = {
            'Senior Manager': senior_perms,
            'Mid-Level Manager': manager_perms,
            'User': user_perms,
            'Viewer': viewer_perms,
        }

        for group_name, codenames in groups.items():
            group, created = Group.objects.get_or_create(name=group_name)
            if not created:
                group.permissions.clear()

            assigned = 0
            missing = []
            for codename in sorted(codenames):
                try:
                    perm = Permission.objects.get(codename=codename)
                    group.permissions.add(perm)
                    assigned += 1
                except Permission.DoesNotExist:
                    missing.append(codename)

            status = 'Created' if created else 'Updated'
            self.stdout.write(
                self.style.SUCCESS(f"  {status} '{group_name}': {assigned} permissions assigned")
            )
            if missing:
                self.stdout.write(
                    self.style.WARNING(f"    {len(missing)} permissions not found (models may not be migrated yet)")
                )

        self.stdout.write(self.style.SUCCESS("\nRBAC setup complete."))

    def _build_senior_manager(self):
        """ALL permissions: view + add + change + delete + all custom."""
        perms = set()
        for model in ALL_MODELS:
            perms.update([
                f'view_{model}', f'add_{model}',
                f'change_{model}', f'delete_{model}',
            ])
        perms.update(CUSTOM_PERMISSIONS)
        return perms

    def _build_mid_level_manager(self):
        """View + Add + Change on all models. Most approvals. NO delete. NO payroll approval."""
        perms = set()
        for model in ALL_MODELS:
            perms.add(f'view_{model}')
            if model not in SENIOR_ONLY_EDIT_MODELS:
                perms.update([f'add_{model}', f'change_{model}'])

        # Mid-level approvals (everything except payroll and budget)
        mid_approvals = [
            'approve_purchaserequest', 'approve_purchaseorder',
            'approve_salesorder', 'approve_quotation',
            'approve_leaverequest',
            'approve_productionorder', 'approve_qualityinspection',
            'approve_stockmovement',
        ]
        perms.update(mid_approvals)
        # GL posting for managers
        perms.add('post_journalheader')
        perms.add('approve_journalheader')
        return perms

    def _build_user(self):
        """View + Add + Change on operational models. NO delete. NO approvals."""
        perms = set()
        for model in ALL_MODELS:
            perms.add(f'view_{model}')
            if model not in ADMIN_ONLY_MODELS and model not in SENIOR_ONLY_EDIT_MODELS:
                perms.update([f'add_{model}', f'change_{model}'])
        # No custom permissions for regular users
        return perms

    def _build_viewer(self):
        """View-only on all models."""
        return {f'view_{model}' for model in ALL_MODELS}
