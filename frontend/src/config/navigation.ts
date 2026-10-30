/**
 * The application's navigation tree: the single source for the sidebar and for anything that needs to know
 * "which screens exist and how do I get to them" (the Ask AI finder).
 *
 * Whether the signed-in user may SEE an entry is decided by ``isNavItemVisible`` below, so both consumers
 * agree. Only top-level entries carry a permission and a module; sub-items inherit their parent's.
 */
import {
    BarChart3,
    Wallet,
    ShoppingCart,
    Package,
    TrendingUp,
    CheckCircle,
    DollarSign,
    FileText,
    Receipt,
    Building,
    Building2,
    List,
    CreditCard,
    ArrowRightLeft,
    UserPlus,
    Users,
    History,
    Shield,
    Briefcase,
    Calendar,
    AlertTriangle,
    Clock,
    Settings,
    Warehouse,
    Boxes,
    UserCog,
    ShieldCheck,
    ShieldAlert,
    GraduationCap,
    Award,
    Banknote,
    Landmark,
    Target,
    CalendarCheck,
    ClipboardCheck,
    Star,
    GitBranch,
    MapPin,
    Truck,
    BookOpen,
    UserMinus,
    Layers,
    HandCoins,
    FolderTree,
    FilePlus,
    User,
    ArrowUpRight,
    Activity,
    Scale,
    Search,
    Handshake,
    FileSignature,
    Archive,
    Sparkles,
} from 'lucide-react';
import { hasPermission, type UserPermissions } from '../hooks/usePermissions';

export interface SubItem {
    name: string;
    path: string;
    icon: any;
}

export interface MenuItem {
    name: string;
    icon: any;
    path: string;
    requiredPerm: string | null;
    module: string | null;
    subItems?: SubItem[];
}

export const menuItems: MenuItem[] = [
    { name: 'Dashboard', icon: BarChart3, path: '/dashboard', requiredPerm: null, module: null },
    {
        name: 'Accounting', icon: Wallet, path: '/accounting',
        requiredPerm: 'view_journalheader', module: 'accounting',
        subItems: [
            { name: 'Journal Entries', path: '/accounting', icon: FileText },
            { name: 'Revenue Entries (IGR)', path: '/accounting/revenue-collections', icon: Banknote },
            { name: 'Chart of Accounts', path: '/accounting/coa', icon: List },
            // Same vendor master as Procurement → Suppliers/Vendor; surfaced here
            // so suppliers can be created from Accounting as well as Procurement.
            { name: 'Suppliers/Vendor', path: '/procurement/vendors', icon: Building2 },
            { name: 'AP Invoice', path: '/accounting/ap', icon: Receipt },
            { name: 'Vendor Down Payment', path: '/accounting/advance-requests/new', icon: HandCoins },
            { name: 'AP Invoices Register', path: '/accounting/ap-invoices', icon: Layers },
            { name: 'Trial Balance', path: '/accounting/reports/trial-balance', icon: ClipboardCheck },
            { name: 'GL Reports', path: '/accounting/reports', icon: BarChart3 },
            { name: 'Fixed Assets', path: '/accounting/fixed-assets', icon: Building },
            { name: 'Period Close', path: '/accounting/reports/period-close', icon: CalendarCheck },
        ],
    },
    {
        name: 'Budget & Appropriation', icon: DollarSign, path: '/budget/appropriations',
        requiredPerm: 'view_budget', module: 'budget',
        subItems: [
            { name: 'Appropriations', path: '/budget/appropriations', icon: FileText },
            { name: 'Supplementary Budget', path: '/budget/supplementary', icon: Layers },
            { name: 'Virement (Transfer)', path: '/budget/virements', icon: ArrowRightLeft },
            { name: 'Revenue Budget', path: '/budget/revenue-budget', icon: Banknote },
            { name: 'Warrants / AIE', path: '/budget/warrants', icon: CreditCard },
            { name: 'Warrant Utilization', path: '/budget/warrant-utilization', icon: Scale },
            { name: 'Budget Check', path: '/budget/check', icon: ShieldCheck },
            { name: 'Execution Report', path: '/budget/execution-report', icon: TrendingUp },
            { name: 'Variance Analysis', path: '/accounting/budget/variance', icon: TrendingUp },
        ],
    },
    {
        name: 'Treasury & Banking', icon: Landmark, path: '/accounting/tsa-accounts',
        requiredPerm: 'view_journalheader', module: 'treasury',
        subItems: [
            { name: 'Bank Accounts', path: '/accounting/tsa-accounts', icon: Landmark },
            // Atomic inter-TSA transfer — posts a balanced JV (DR target /
            // CR source) and updates both ``current_balance`` rows in real
            // time. Sits next to ``Bank Accounts`` so operators reach it
            // from the same mental cluster as account management.
            { name: 'Bank Transfer', path: '/accounting/tsa-accounts/transfer', icon: ArrowRightLeft },
            { name: 'Cash Posting', path: '/accounting/cash-posting', icon: Banknote },
            // Unified approval-staging register for BOTH Payment Vouchers and
            // Payment Documents. The standalone "Payment Documents" list is
            // folded in here (its create/detail routes remain).
            { name: 'Payment Proposal', path: '/accounting/payment-proposals', icon: Receipt },
            // Mobilization advances are now merged into Outgoing Payments →
            // Advances tab (Contract Mobilization Advances), so the standalone
            // link is retired.
            { name: 'Outgoing Payments', path: '/accounting/outgoing-payments', icon: ArrowUpRight },
            // Posted payments + the cheques issued against them; select posted
            // payment lines and create a cheque (number + date) covering them.
            { name: 'Cheque Register', path: '/accounting/cheque-register', icon: BookOpen },
            // H2 follow-up (WS6) — operator surface for cascade failures.
            // Sits next to Outgoing Payments because the failures come
            // from posted-payment cascades; this is the same operator
            // mental cluster.
            { name: 'Payment Reconciliation Queue', path: '/accounting/payment-reconciliation-queue', icon: AlertTriangle },
            { name: 'Payment Instructions', path: '/accounting/payment-instructions', icon: CreditCard },
            { name: 'Bank Reconciliation', path: '/accounting/bank-reconciliation', icon: Scale },
            { name: 'Cash Position', path: '/accounting/ipsas/tsa-cash-position', icon: Activity },
        ],
    },
    {
        // Five segments, not six. The economic segment was a copy of the
        // chart of accounts — same codes, same names, same hierarchy —
        // and now lives under General Ledger > Chart of Accounts. The
        // rest classify things the GL does not.
        name: 'NCoA Classification', icon: Layers, path: '/accounting/ncoa/administrative',
        requiredPerm: 'view_journalheader', module: 'accounting',
        subItems: [
            { name: 'Administrative (MDA)', path: '/accounting/ncoa/administrative', icon: Building },
            { name: 'Functional (COFOG)', path: '/accounting/ncoa/functional', icon: Target },
            { name: 'Programme', path: '/accounting/ncoa/programme', icon: FileText },
            { name: 'Fund Sources', path: '/accounting/ncoa/fund', icon: Wallet },
            { name: 'Geographic', path: '/accounting/ncoa/geographic', icon: MapPin },
            // The composite code is assembled from the five segments at
            // submit time (via /accounting/ncoa/codes/resolve/), not
            // maintained by hand — so it is not a navigation destination.
        ],
    },
    {
        name: 'Procurement', icon: ShoppingCart, path: '/procurement/requisitions',
        requiredPerm: 'view_purchaseorder', module: 'procurement',
        subItems: [
            { name: 'Purchase Requisitions', path: '/procurement/requisitions', icon: FileText },
            { name: 'Purchase Orders', path: '/procurement/orders', icon: ShoppingCart },
            { name: 'Goods Received Notes', path: '/procurement/grn', icon: Package },
            { name: 'Invoice Verification', path: '/procurement/matching', icon: CheckCircle },
            { name: 'Suppliers/Vendor', path: '/procurement/vendors', icon: Building },
            { name: 'Expired Suppliers', path: '/procurement/vendors-expired', icon: Clock },
            { name: 'Vendor Categories', path: '/procurement/vendor-categories', icon: FolderTree },
            // Advisory: orders that clear a ceiling individually but not
            // together. Reports only — see features/procurement/SplitPurchaseScan.
            { name: 'Split & Duplicate Scan', path: '/procurement/split-scan', icon: AlertTriangle },
        ],
    },
    {
        name: 'Contracts & Milestones', icon: Handshake, path: '/contracts/dashboard',
        requiredPerm: 'view_contract', module: 'contracts',
        subItems: [
            { name: 'Contracts Dashboard', path: '/contracts/dashboard', icon: BarChart3 },
            { name: 'All Contracts', path: '/contracts', icon: FileText },
            { name: 'New Contract', path: '/contracts/new', icon: FilePlus },
            // "Write-up" is the product label for upward contract-amount revaluations.
            // Route path stays /contracts/variations so existing bookmarks and the
            // ContractVariation API contract continue to work — only the user-facing
            // label changes.
            { name: 'Write-ups', path: '/contracts/variations', icon: TrendingUp },
        ],
    },
    {
        name: 'Government Stores', icon: Package, path: '/inventory',
        requiredPerm: 'view_item', module: 'inventory',
        subItems: [
            { name: 'Store Items', path: '/inventory', icon: Package },
            { name: 'Item Categories', path: '/inventory/categories', icon: List },
            { name: 'Warehouses / Stores', path: '/inventory/warehouses', icon: Warehouse },
            { name: 'Goods Received', path: '/inventory/stocks', icon: Boxes },
            { name: 'Store Issuance', path: '/inventory/movements', icon: Truck },
        ],
    },
    {
        name: 'Human Resources', icon: Users, path: '/hrm/dashboard',
        requiredPerm: 'view_employee', module: 'hrm',
        subItems: [
            { name: 'HR Dashboard', path: '/hrm/dashboard', icon: BarChart3 },
            { name: 'Employee Directory', path: '/hrm/employees', icon: Users },
            { name: 'Departments', path: '/hrm/departments', icon: Building },
            { name: 'Positions', path: '/hrm/positions', icon: Briefcase },
            { name: 'Leave Management', path: '/hrm/leave', icon: Calendar },
            { name: 'Attendance', path: '/hrm/attendance', icon: Clock },
            { name: 'Holidays', path: '/hrm/holidays', icon: CalendarCheck },
            { name: 'Job Posts', path: '/hrm/job-posts', icon: FileText },
            { name: 'Candidates', path: '/hrm/candidates', icon: UserPlus },
            { name: 'Payroll', path: '/hrm/payroll', icon: Banknote },
            { name: 'Payslips', path: '/hrm/payslips', icon: Receipt },
            { name: 'Performance', path: '/hrm/performance', icon: Award },
            { name: 'Training Programs', path: '/hrm/training', icon: GraduationCap },
            { name: 'Skills', path: '/hrm/skills', icon: Star },
            { name: 'Policies', path: '/hrm/policies', icon: BookOpen },
            { name: 'Compliance', path: '/hrm/compliance', icon: Shield },
            { name: 'Exit Management', path: '/hrm/exit', icon: UserMinus },
        ],
    },
    {
        name: 'IPSAS Reporting', icon: BarChart3, path: '/accounting/ipsas/financial-position',
        requiredPerm: 'view_journalheader', module: 'accounting',
        subItems: [
            { name: 'Financial Position', path: '/accounting/ipsas/financial-position', icon: Landmark },
            { name: 'Financial Performance', path: '/accounting/ipsas/financial-performance', icon: TrendingUp },
            { name: 'Cash Flow Statement', path: '/accounting/ipsas/cash-flow', icon: Activity },
            { name: 'Changes in Net Assets', path: '/accounting/ipsas/changes-in-net-assets', icon: TrendingUp },
            { name: 'Notes to Financial Statements', path: '/accounting/ipsas/notes', icon: FileText },
            { name: 'Budget vs Actual', path: '/accounting/ipsas/budget-vs-actual', icon: BarChart3 },
            { name: 'Budget Performance', path: '/accounting/ipsas/budget-performance', icon: Scale },
            { name: 'Revenue Performance', path: '/accounting/ipsas/revenue-performance', icon: Banknote },
            { name: 'Cash Position', path: '/accounting/ipsas/tsa-cash-position', icon: Landmark },
            { name: 'Functional Performance', path: '/accounting/ipsas/functional-classification', icon: BarChart3 },
            { name: 'Programme Performance', path: '/accounting/ipsas/programme-performance', icon: TrendingUp },
            { name: 'Geographic Performance', path: '/accounting/ipsas/geographic-distribution', icon: MapPin },
            { name: 'Fund Performance', path: '/accounting/ipsas/fund-performance', icon: DollarSign },
        ],
    },
    {
        name: 'Data Quality', icon: Shield, path: '/accounting/data-quality',
        requiredPerm: 'view_journalheader', module: 'audit',
    },
    {
        // ── Administration group ──────────────────────────────────────
        // Bundles all tenant-administrator surfaces under one entry so
        // role/permission/user-management is discoverable as a unit
        // rather than scattered across five top-level items. The order
        // inside ``subItems`` mirrors the workflow an admin follows
        // when onboarding a new tenant: define perms → assemble roles
        // → assign users → write SoD rules → tune approval gates →
        // review audit/override trail.
        // ``module: null`` (not ``'admin'``) is intentional: 'admin'
        // isn't a billable TenantModule entry — every tenant gets RBAC
        // by definition. ``isModuleEnabled`` does a strict ``=== true``
        // check, so when a tenant has any explicit ``enabled_modules``
        // dict entries but ``admin`` isn't one of them, this group
        // would silently disappear. Mirroring the pattern used by the
        // existing "Settings" entry below: gate visibility purely by
        // ``requiredPerm`` (tenant admins bypass via ``tenant_role``).
        name: 'Administration', icon: ShieldCheck, path: '/admin/roles',
        requiredPerm: 'view_user', module: null,
        subItems: [
            { name: 'Roles & Permissions', path: '/admin/roles',          icon: Shield },
            { name: 'User Management',     path: '/user-management',      icon: UserCog },
            { name: 'SoD Rules',           path: '/admin/sod-rules',      icon: ShieldAlert },
            { name: 'Approval Rules',      path: '/admin/approval-rules', icon: CheckCircle },
            { name: 'Override Audit',      path: '/admin/audit/overrides', icon: AlertTriangle },
            { name: 'Fiscal Years',        path: '/admin/fiscal-years',   icon: Calendar },
        ],
    },
    {
        name: 'Audit Trail', icon: Shield, path: '/audit/trail',
        requiredPerm: 'view_journalheader', module: 'audit',
    },
    {
        name: 'Approvals', icon: CheckCircle, path: '/approvals/dashboard',
        requiredPerm: 'view_approval', module: 'workflow',
        subItems: [
            { name: 'Approval Inbox', path: '/approvals', icon: CheckCircle },
            { name: 'Approval Groups', path: '/approvals/groups', icon: Users },
            { name: 'Approval Templates', path: '/approvals/templates', icon: FileText },
            { name: 'Approval History', path: '/approvals/history', icon: History },
        ],
    },
    {
        name: 'Workflow', icon: GitBranch, path: '/workflow/dashboard',
        requiredPerm: 'view_workflowdefinition', module: 'workflow',
        subItems: [
            { name: 'Workflow Dashboard', path: '/workflow/dashboard', icon: BarChart3 },
            { name: 'Workflow Inbox', path: '/workflow/inbox', icon: FileText },
            { name: 'Definitions', path: '/workflow/definitions', icon: FileText },
            { name: 'Groups', path: '/workflow/groups', icon: Users },
            { name: 'Instances', path: '/workflow/instances', icon: List },
        ],
    },
    // ``User Management`` was previously a separate top-level entry
    // here — it now lives inside the Administration group above so all
    // tenant-admin surfaces (roles, users, SoD, audit, approvals) are
    // discoverable as one cohesive unit instead of being scattered.
    {
        name: 'Settings', icon: Settings, path: '/settings/organizations',
        requiredPerm: 'view_accountingsettings', module: null,
        subItems: [
            { name: 'Organizations (MDAs)', path: '/settings/organizations', icon: Users },
            { name: 'Government Config', path: '/settings/government', icon: Building },
            { name: 'Fiscal Year', path: '/settings/fiscal-year', icon: CalendarCheck },
            { name: 'Bank Accounts', path: '/settings/bank-accounts', icon: Landmark },
            { name: 'Payment Deduction', path: '/settings/tax', icon: Receipt },
            { name: 'Branding & Company', path: '/settings/branding', icon: Building },
            { name: 'Accounting Settings', path: '/settings/accounting', icon: Settings },
            // Tenant-wide warrant printout config — letterhead + 3
            // signatures (Governor, Finance Commissioner, AG) used to
            // compose every AIE printout. Configure once at onboarding;
            // future signatory changes only need a new image upload.
            { name: 'Warrant Printout', path: '/settings/warrant-printout', icon: FileSignature },
            { name: 'Bank Letter', path: '/settings/bank-letter', icon: Landmark },
            { name: 'Backups', path: '/settings/backups', icon: Archive },
            // What AI is switched on for this organisation, what it sends
            // and where. Read-only apart from an off switch — enabling is
            // a platform decision, see features/settings/AISettings.tsx.
            { name: 'AI', path: '/settings/ai', icon: Sparkles },
            // E-payment: which disbursement gateways are switched on for this
            // organisation, and the clearing account their money flows through.
            { name: 'Payment Gateways', path: '/settings/payment-gateways', icon: CreditCard },
        ],
    },
    // Future modules: each is a per-tenant switch (see isModuleEnabled); off ⇒ the entry disappears, data is kept.
    { name: 'Budget Preparation', icon: Landmark, path: '/budget-prep', requiredPerm: null, module: 'budget_prep' },
    { name: 'e-Procurement', icon: ShoppingCart, path: '/egp', requiredPerm: null, module: 'egp' },
    { name: 'Establishment & Payroll', icon: Users, path: '/personnel-budget', requiredPerm: null, module: 'personnel_budget' },
    { name: 'Public Debt', icon: Wallet, path: '/debt', requiredPerm: null, module: 'debt' },
    { name: 'Fiscal Transparency', icon: Search, path: '/transparency', requiredPerm: null, module: 'transparency' },
    { name: 'Results & M&E', icon: Target, path: '/results', requiredPerm: null, module: 'results' },
    { name: 'Integration Gateway', icon: GitBranch, path: '/integrations', requiredPerm: null, module: 'integrations' },
    { name: 'Revenue Administration', icon: Receipt, path: '/revenue-admin', requiredPerm: null, module: 'revenue_admin' },
    { name: 'Cash Planning', icon: Banknote, path: '/cash-planning', requiredPerm: null, module: 'cash_planning' },
    { name: 'Advances & Travel', icon: Briefcase, path: '/staff-advances', requiredPerm: null, module: 'staff_advances' },
    { name: 'Internal Audit', icon: Shield, path: '/internal-audit', requiredPerm: null, module: 'internal_audit' },
    { name: 'Fleet Management', icon: Truck, path: '/fleet', requiredPerm: null, module: 'fleet' },
    { name: 'Supplier Catalogue', icon: BookOpen, path: '/catalogue', requiredPerm: null, module: 'catalogue' },
    { name: 'Asset Declaration', icon: ClipboardCheck, path: '/disclosure', requiredPerm: null, module: 'disclosure' },
    { name: 'Legal & Risk', icon: Scale, path: '/legal', requiredPerm: null, module: 'legal' },
    {
        name: 'System Admin', icon: UserCog, path: '/superadmin',
        requiredPerm: 'is_superuser', module: null,
        subItems: [
            { name: 'Admin Dashboard', path: '/superadmin', icon: Settings },
            { name: 'Snapshots', path: '/admin/snapshots', icon: Archive },
        ],
    },
];

/** The signed-in user and whether their permissions are still loading. */
export interface ViewerState {
    user: UserPermissions | undefined | null;
    loading: boolean;
}

/** The tenant's enabled modules and whether they are still loading. */
export interface ModuleState {
    enabledModules: Record<string, boolean> | undefined | null;
    loading: boolean;
}

/** Is this module switched on for the tenant? Unknown or loading counts as on, so a slow response
 *  never blanks the menu. A tenant with an explicit module list gets only the modules set to true. */
export function isModuleEnabled(moduleKey: string | null, modules: ModuleState): boolean {
    if (!moduleKey) return true;
    if (modules.loading) return true;
    if (!modules.enabledModules) return true;
    if (Object.keys(modules.enabledModules).length > 0) {
        return modules.enabledModules[moduleKey] === true;
    }
    return true;
}

/** Would the sidebar show this top-level entry to this user? */
export function isNavItemVisible(item: MenuItem, viewer: ViewerState, modules: ModuleState): boolean {
    if (!isModuleEnabled(item.module, modules)) return false;
    if (!item.requiredPerm) return true;
    // Show everything while loading or if user data is unavailable (prevents a blank sidebar during auth issues).
    if (viewer.loading || !viewer.user) return true;
    return hasPermission(viewer.user, item.requiredPerm);
}
