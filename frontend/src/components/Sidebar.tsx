import { useState, useEffect, useLayoutEffect, useRef } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import {
    BarChart3,
    Wallet,
    ShoppingCart,
    Package,
    Wrench,
    TrendingUp,
    LogOut,
    ChevronRight,
    ChevronDown,
    CheckCircle,
    DollarSign,
    FileText,
    Receipt,
    Building,
    List,
    CreditCard,
    ArrowRightLeft,
    UserPlus,
    Users,
    History,
    Factory,
    Shield,
    Briefcase,
    Calendar,
    AlertTriangle,
    Clock,
    Settings,
    Warehouse,
    Boxes,
    RotateCcw,
    Bell,
    HardDrive,
    UserCog,
    Ticket,
    CalendarClock,
    GraduationCap,
    Award,
    Banknote,
    Landmark,
    Target,
    CalendarCheck,
    Repeat,
    ClipboardCheck,
    Gauge,
    Star,
    GitBranch,
    MapPin,
    Truck,
    Search,
    BookOpen,
    UserMinus,
    BadgeCheck,
    Layers,
    FolderTree,
    Coins,
    Hash,
    FilePlus,
    User,
    ArrowUpRight,
    SlidersHorizontal,
    Monitor,
    Activity,
    Scale,
    Handshake,
} from 'lucide-react';
import { Menu, X } from 'lucide-react';
import { usePermissions, hasPermission } from '../hooks/usePermissions';
import { useTenantModules } from '../hooks/useTenantModules';
import { useBranding } from '../context/BrandingContext';
import { useAuth } from '../context/AuthContext';
import { useIsMobile } from '../design';
import OrganizationSwitcher from './OrganizationSwitcher';
import NotificationBell from './NotificationBell';
import BackButton from './BackButton';

interface SubItem {
    name: string;
    path: string;
    icon: any;
}

interface MenuItem {
    name: string;
    icon: any;
    path: string;
    requiredPerm: string | null;
    module: string | null;
    subItems?: SubItem[];
}

const menuItems: MenuItem[] = [
    { name: 'Dashboard', icon: BarChart3, path: '/dashboard', requiredPerm: null, module: null },
    {
        name: 'General Ledger', icon: Wallet, path: '/accounting',
        requiredPerm: 'view_journalheader', module: 'accounting',
        subItems: [
            { name: 'Journal Entries', path: '/accounting', icon: FileText },
            { name: 'Revenue Entries (IGR)', path: '/accounting/revenue-collections', icon: Banknote },
            { name: 'Chart of Accounts', path: '/accounting/coa', icon: List },
            { name: 'Accounts Payable', path: '/accounting/ap', icon: Receipt },
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
            { name: 'Virement (Transfer)', path: '/budget/virements/new', icon: ArrowRightLeft },
            { name: 'Revenue Budget', path: '/budget/revenue-budget', icon: Banknote },
            { name: 'Warrants / AIE', path: '/budget/warrants', icon: CreditCard },
            { name: 'Warrant Utilization', path: '/budget/warrant-utilization', icon: Scale },
            { name: 'Execution Report', path: '/budget/execution-report', icon: TrendingUp },
            { name: 'Variance Analysis', path: '/accounting/budget/variance', icon: TrendingUp },
        ],
    },
    {
        name: 'Treasury & Banking (TSA)', icon: Landmark, path: '/accounting/tsa-accounts',
        requiredPerm: 'view_journalheader', module: 'treasury',
        subItems: [
            { name: 'TSA Accounts', path: '/accounting/tsa-accounts', icon: Landmark },
            // Atomic inter-TSA transfer — posts a balanced JV (DR target /
            // CR source) and updates both ``current_balance`` rows in real
            // time. Sits next to ``TSA Accounts`` so operators reach it
            // from the same mental cluster as account management.
            { name: 'TSA Bank Transfer', path: '/accounting/tsa-accounts/transfer', icon: ArrowRightLeft },
            { name: 'Payment Vouchers', path: '/accounting/payment-vouchers', icon: Receipt },
            { name: 'Outgoing Payments', path: '/accounting/outgoing-payments', icon: ArrowUpRight },
            { name: 'Payment Instructions', path: '/accounting/payment-instructions', icon: CreditCard },
            { name: 'Bank Reconciliation', path: '/accounting/bank-reconciliation', icon: Scale },
            { name: 'Cash Position', path: '/accounting/ipsas/tsa-cash-position', icon: Activity },
        ],
    },
    {
        name: 'NCoA Classification', icon: Layers, path: '/accounting/ncoa/economic',
        requiredPerm: 'view_journalheader', module: 'accounting',
        subItems: [
            { name: 'Economic Segment', path: '/accounting/ncoa/economic', icon: DollarSign },
            { name: 'Administrative (MDA)', path: '/accounting/ncoa/administrative', icon: Building },
            { name: 'Functional (COFOG)', path: '/accounting/ncoa/functional', icon: Target },
            { name: 'Programme', path: '/accounting/ncoa/programme', icon: FileText },
            { name: 'Fund Sources', path: '/accounting/ncoa/fund', icon: Wallet },
            { name: 'Geographic', path: '/accounting/ncoa/geographic', icon: MapPin },
            { name: 'NCoA Codes', path: '/accounting/ncoa/codes', icon: Layers },
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
            { name: 'Add Suppliers', path: '/procurement/vendors', icon: Building },
            { name: 'Expired Suppliers', path: '/procurement/vendors-expired', icon: Clock },
            { name: 'Vendor Categories', path: '/procurement/vendor-categories', icon: FolderTree },
        ],
    },
    {
        name: 'Contracts & Milestones', icon: Handshake, path: '/contracts/dashboard',
        requiredPerm: 'view_contract', module: 'contracts',
        subItems: [
            { name: 'Contracts Dashboard', path: '/contracts/dashboard', icon: BarChart3 },
            { name: 'All Contracts', path: '/contracts', icon: FileText },
            { name: 'New Contract', path: '/contracts/new', icon: FilePlus },
            { name: 'Interim Payment Certificates', path: '/contracts/ipcs', icon: Scale },
            { name: 'Variations', path: '/contracts/variations', icon: TrendingUp },
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
            { name: 'TSA Cash Position', path: '/accounting/ipsas/tsa-cash-position', icon: Landmark },
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
        name: 'Roles & Permissions', icon: Shield, path: '/admin/roles',
        requiredPerm: 'view_user', module: 'admin',
    },
    {
        name: 'Approval Rules', icon: CheckCircle, path: '/admin/approval-rules',
        requiredPerm: 'view_approvalrule', module: 'admin',
    },
    {
        name: 'Override Audit', icon: AlertTriangle, path: '/admin/audit/overrides',
        requiredPerm: 'view_journalheader', module: 'audit',
    },
    {
        name: 'Fiscal Years', icon: Calendar, path: '/admin/fiscal-years',
        requiredPerm: 'view_fiscalyear', module: 'admin',
    },
    {
        name: 'Appropriations', icon: DollarSign, path: '/budget/appropriations',
        requiredPerm: 'view_appropriation', module: 'budget',
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
    { name: 'User Management', icon: UserCog, path: '/user-management', requiredPerm: 'view_employee', module: null },
    {
        name: 'Settings', icon: Settings, path: '/settings/organizations',
        requiredPerm: 'view_accountingsettings', module: null,
        subItems: [
            { name: 'Organizations (MDAs)', path: '/settings/organizations', icon: Users },
            { name: 'Government Config', path: '/settings/government', icon: Building },
            { name: 'Fiscal Year', path: '/settings/fiscal-year', icon: CalendarCheck },
            { name: 'Bank Accounts', path: '/settings/bank-accounts', icon: Landmark },
            { name: 'Tax Management', path: '/settings/tax', icon: Receipt },
            { name: 'Branding & Company', path: '/settings/branding', icon: Building },
            { name: 'Accounting Settings', path: '/settings/accounting', icon: Settings },
        ],
    },
    {
        name: 'System Admin', icon: UserCog, path: '/superadmin',
        requiredPerm: 'is_superuser', module: null,
        subItems: [
            { name: 'Admin Dashboard', path: '/superadmin', icon: Settings },
        ],
    },
];

const Sidebar = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const { branding } = useBranding();
    const { mdaIsolationMode } = useAuth();
    const showMdaSwitcher = mdaIsolationMode === 'SEPARATED';
    const tenantInfo = (() => {
        try {
            const raw = localStorage.getItem('tenantInfo');
            return raw ? JSON.parse(raw) : null;
        } catch { return null; }
    })();
    const activeTenant = tenantInfo?.name || 'No Organization';
    const { data: user, isLoading: permLoading } = usePermissions();
    const { data: tenantModules, isLoading: modulesLoading } = useTenantModules();
    // Persist expanded menus in localStorage. The Sidebar is rendered
    // by every page layout separately (~96 call-sites), which means it
    // unmounts/remounts on EVERY route change — a plain useState would
    // reset to [] each time and the user would lose their manually-
    // expanded menu groups after each click. localStorage survives
    // remount AND full page reload, so the sidebar stays open on the
    // group the user was working in until they explicitly collapse it.
    const EXPANDED_MENUS_STORAGE_KEY = 'quotpse.sidebar.expandedMenus.v1';
    const [expandedMenus, setExpandedMenus] = useState<string[]>(() => {
        try {
            const raw = window.localStorage.getItem(EXPANDED_MENUS_STORAGE_KEY);
            if (!raw) return [];
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string') : [];
        } catch {
            return [];
        }
    });
    // Write back on every change.
    useEffect(() => {
        try {
            window.localStorage.setItem(
                EXPANDED_MENUS_STORAGE_KEY,
                JSON.stringify(expandedMenus),
            );
        } catch { /* storage quota / private mode — ignore */ }
    }, [expandedMenus]);

    const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

    // ── Active-item scroll-into-view ───────────────────────────────────
    // Ref attached to the currently active sidebar row. On every path
    // change we scroll it into view so the user always sees where they
    // are in the nav tree without manually scrolling. ``block: 'nearest'``
    // means we don't scroll if it's already visible — avoids gratuitous
    // movement when the active item didn't change.
    const activeRowRef = useRef<HTMLElement | null>(null);
    useLayoutEffect(() => {
        if (activeRowRef.current) {
            activeRowRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
    }, [location.pathname, location.search]);

    // ── Responsive drawer state (Phase 1 of responsive rollout)
    const isMobile = useIsMobile();
    const [drawerOpen, setDrawerOpen] = useState(false);

    // Close drawer on route change
    useEffect(() => {
        if (isMobile) setDrawerOpen(false);
    }, [location.pathname, isMobile]);

    // Close drawer on Escape
    useEffect(() => {
        if (!drawerOpen) return;
        const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setDrawerOpen(false); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [drawerOpen]);

    // Lock body scroll when drawer is open on mobile
    useEffect(() => {
        if (isMobile && drawerOpen) {
            const prev = document.body.style.overflow;
            document.body.style.overflow = 'hidden';
            return () => { document.body.style.overflow = prev; };
        }
    }, [isMobile, drawerOpen]);

    useEffect(() => {
        const activeParent = menuItems.find(
            (item) =>
                item.subItems?.some((sub) => isActive(sub.path)) ||
                location.pathname === item.path ||
                location.pathname.startsWith(item.path)
        );
        if (activeParent?.subItems && !expandedMenus.includes(activeParent.name)) {
            setExpandedMenus((prev) =>
                prev.includes(activeParent.name) ? prev : [...prev, activeParent.name]
            );
        }
    }, [location.pathname, location.search]);

    const toggleMenu = (menuName: string) => {
        setExpandedMenus((prev) =>
            prev.includes(menuName) ? prev.filter((m) => m !== menuName) : [...prev, menuName]
        );
    };

    const isModuleEnabled = (moduleKey: string | null): boolean => {
        if (!moduleKey) return true;
        if (modulesLoading) return true;
        if (!tenantModules?.enabled_modules) return true;
        if (Object.keys(tenantModules.enabled_modules).length > 0) {
            return tenantModules.enabled_modules[moduleKey] === true;
        }
        return true;
    };

    const filteredItems = menuItems.filter((item) => {
        if (!isModuleEnabled(item.module)) return false;
        if (!item.requiredPerm) return true;
        // Show all items while loading or if user data unavailable
        // (prevents blank sidebar during auth issues)
        if (permLoading || !user) return true;
        return hasPermission(user, item.requiredPerm);
    });

    const handleLogout = () => {
        localStorage.removeItem('authToken');
        localStorage.removeItem('user');
        localStorage.removeItem('tenantDomain');
        localStorage.removeItem('tenantInfo');
        localStorage.removeItem('tenantPermissions');
        navigate('/login');
    };

    const handleSwitchTenant = () => {
        localStorage.removeItem('tenantDomain');
        localStorage.removeItem('tenantInfo');
        localStorage.removeItem('tenantPermissions');
        navigate('/login');
    };

    const isActive = (path: string) => {
        // For paths with a query string (e.g. /accounting/ar?tab=payments),
        // compare both pathname and search so the highlight works correctly.
        if (path.includes('?')) {
            const [p, q] = path.split('?');
            return location.pathname === p && location.search === `?${q}`;
        }
        return location.pathname === path;
    };
    const isParentActive = (item: MenuItem) => {
        if (item.subItems) {
            return item.subItems.some((sub) => isActive(sub.path)) || location.pathname.startsWith(item.path);
        }
        return isActive(item.path);
    };

    return (
        <>
        {/* Mobile hamburger + top bar — only on mobile */}
        {isMobile && (
            <div style={{
                position: 'fixed', top: 0, left: 0, right: 0, height: '56px',
                background: '#ffffff', borderBottom: '1px solid #e2e8f0',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '0 12px', gap: '12px', zIndex: 30,
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                paddingTop: 'env(safe-area-inset-top, 0)',
            }}>
                <button
                    onClick={() => setDrawerOpen(true)}
                    aria-label="Open navigation"
                    className="tap-target"
                    style={{ background: 'transparent', border: 'none', cursor: 'pointer', borderRadius: 8, color: '#1a237e' }}
                >
                    <Menu size={22} />
                </button>
                <div style={{ flex: 1, fontFamily: "'Manrope',sans-serif", fontWeight: 700, fontSize: 15, color: '#0b1320', textAlign: 'center', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {branding.name || 'Quot PSE'}
                </div>
                <NotificationBell />
            </div>
        )}

        {/* Top Header Bar — only visible when MDA separation is active, desktop only */}
        {showMdaSwitcher && !isMobile && (
            <div style={{
                position: 'fixed', top: 0, left: '260px', right: 0, height: '48px',
                background: '#ffffff', borderBottom: '1px solid #e2e8f0',
                display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
                padding: '0 24px', gap: '16px', zIndex: 15,
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            }}>
                <OrganizationSwitcher />
                <NotificationBell />
            </div>
        )}

        {/* Mobile drawer scrim */}
        {isMobile && drawerOpen && (
            <div
                onClick={() => setDrawerOpen(false)}
                style={{
                    position: 'fixed', inset: 0, background: 'rgba(15,23,89,0.45)',
                    zIndex: 25, animation: 'fade-in 180ms ease',
                }}
            />
        )}

        <div style={{
            width: '260px',
            height: '100vh',
            background: 'linear-gradient(180deg, #1a1f66 0%, #242a88 100%)',
            color: 'rgba(255,255,255,0.75)',
            display: 'flex', flexDirection: 'column',
            position: 'fixed', left: 0, top: 0,
            overflowY: 'auto',
            borderRight: '1px solid rgba(255,255,255,0.07)',
            zIndex: isMobile ? 28 : 20,
            transform: isMobile ? (drawerOpen ? 'translateX(0)' : 'translateX(-100%)') : 'none',
            transition: isMobile ? 'transform 240ms cubic-bezier(0.16, 1, 0.3, 1)' : 'none',
            boxShadow: isMobile && drawerOpen ? '0 0 40px rgba(0,0,0,0.35)' : 'none',
        }}>
            {/* Close button — mobile drawer only */}
            {isMobile && (
                <button
                    onClick={() => setDrawerOpen(false)}
                    aria-label="Close navigation"
                    className="tap-target"
                    style={{
                        position: 'absolute', top: 8, right: 8,
                        background: 'rgba(255,255,255,0.08)', border: 'none', cursor: 'pointer',
                        color: '#fff', borderRadius: 8, zIndex: 2,
                    }}
                >
                    <X size={20} />
                </button>
            )}
            {/* Header */}
            <div style={{
                padding: '20px 20px 16px',
                borderBottom: '1px solid rgba(255,255,255,0.1)'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                    <div style={{
                        width: '36px', height: '36px', borderRadius: '10px',
                        background: 'rgba(255,255,255,0.15)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0, overflow: 'hidden',
                    }}>
                        {branding.logo ? (
                            <img src={branding.logo} alt={branding.name} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                        ) : (
                            <svg viewBox="0 0 40 40" fill="none" width="20" height="20">
                                <rect x="4" y="8" width="14" height="14" rx="3" fill="white"/>
                                <rect x="22" y="8" width="14" height="14" rx="3" fill="rgba(255,255,255,0.7)"/>
                                <rect x="4" y="26" width="14" height="6" rx="3" fill="rgba(255,255,255,0.5)"/>
                                <rect x="22" y="26" width="14" height="6" rx="3" fill="rgba(255,255,255,0.3)"/>
                            </svg>
                        )}
                    </div>
                    <div>
                        <div style={{ fontSize: '16px', fontWeight: 700, color: '#ffffff', letterSpacing: '-0.3px' }}>
                            {branding.name}
                        </div>
                        <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.45)', fontWeight: 500 }}>
                            Enterprise Platform
                        </div>
                    </div>
                </div>
            </div>

            {/* Back button */}
            <div style={{ padding: '8px 12px 4px' }}>
                <BackButton variant="compact" />
            </div>

            {/* Navigation */}
            <nav style={{ flex: 1, padding: '4px 12px', display: 'flex', flexDirection: 'column', gap: '1px' }}>
                {filteredItems.map((item) => {
                    // Bright Quot accent green used for both hover and
                    // active states so the user can immediately see where
                    // they are in the nav. Translucent variants for
                    // subtle hover, solid + bold strip for active.
                    const ACCENT = '#39cd9a';
                    const HOVER_BG = 'rgba(57, 205, 154, 0.12)';
                    const ACTIVE_BG = 'rgba(57, 205, 154, 0.20)';

                    const parentActive = isParentActive(item);

                    // Shared row styling for both the parent <Link> (when the
                    // item has no subItems and is a real destination) and the
                    // parent <div> toggler (when the item groups subItems).
                    // Built as a function so the two code paths stay in sync.
                    const parentRowStyle: React.CSSProperties = {
                        position: 'relative',
                        display: 'flex', alignItems: 'center', gap: '10px',
                        padding: '8px 12px', borderRadius: '8px',
                        cursor: 'pointer', transition: 'background 0.15s, color 0.15s',
                        background: parentActive ? ACTIVE_BG : 'transparent',
                        color: parentActive ? ACCENT : 'rgba(255,255,255,0.75)',
                        // Link inherits <a> defaults; strip them out.
                        textDecoration: 'none',
                        // Solid 3px accent strip on the left edge of the
                        // active row — visible at a glance, even when
                        // multiple parent items share a similar shade.
                        boxShadow: parentActive ? `inset 3px 0 0 0 ${ACCENT}` : 'none',
                    };
                    const parentRowHoverIn = (e: React.MouseEvent<HTMLElement>) => {
                        if (!parentActive) {
                            (e.currentTarget as HTMLElement).style.background = HOVER_BG;
                            (e.currentTarget as HTMLElement).style.color = ACCENT;
                        }
                    };
                    const parentRowHoverOut = (e: React.MouseEvent<HTMLElement>) => {
                        if (!parentActive) {
                            (e.currentTarget as HTMLElement).style.background = 'transparent';
                            (e.currentTarget as HTMLElement).style.color = 'rgba(255,255,255,0.75)';
                        }
                    };
                    // Only the parent without subItems gets the
                    // active-ref (so scroll-into-view targets a leaf
                    // page). Parents with subItems delegate the ref to
                    // their active child below.
                    const parentRefProp = (parentActive && !item.subItems)
                        ? { ref: activeRowRef as React.RefObject<HTMLAnchorElement & HTMLDivElement> }
                        : {};
                    const parentInner = (
                        <>
                            <item.icon size={18} style={{
                                color: parentActive ? ACCENT : 'rgba(255,255,255,0.5)',
                                flexShrink: 0
                            }} />
                            <span style={{
                                flex: 1, fontSize: '13.5px',
                                fontWeight: parentActive ? 700 : 500,
                                color: parentActive ? ACCENT : 'rgba(255,255,255,0.85)',
                            }}>
                                {item.name}
                            </span>
                            {item.subItems ? (
                                expandedMenus.includes(item.name) ?
                                    <ChevronDown size={14} style={{ color: parentActive ? ACCENT : 'rgba(255,255,255,0.35)' }} /> :
                                    <ChevronRight size={14} style={{ color: parentActive ? ACCENT : 'rgba(255,255,255,0.35)' }} />
                            ) : null}
                        </>
                    );

                    return (
                        <div key={item.name}>
                            {item.subItems ? (
                                // Has a submenu — row is a toggler, not a link.
                                // (Most common case and there's no natural
                                // destination when subItems exist.)
                                <div
                                    role="button"
                                    tabIndex={0}
                                    onClick={() => toggleMenu(item.name)}
                                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') toggleMenu(item.name); }}
                                    style={parentRowStyle}
                                    onMouseOver={parentRowHoverIn}
                                    onMouseOut={parentRowHoverOut}
                                >
                                    {parentInner}
                                </div>
                            ) : (
                                // Leaf item — render as a real <Link> so
                                // right-click / middle-click / Ctrl+click
                                // open in a new tab and hover shows the URL
                                // in the status bar. Navigation via left-click
                                // still goes through React Router (no full
                                // page reload) because Link handles that.
                                <Link
                                    {...parentRefProp}
                                    to={item.path}
                                    style={parentRowStyle}
                                    onMouseOver={parentRowHoverIn}
                                    onMouseOut={parentRowHoverOut}
                                >
                                    {parentInner}
                                </Link>
                            )}

                            {item.subItems && expandedMenus.includes(item.name) && (
                                <div style={{ marginLeft: '12px', borderLeft: '1.5px solid rgba(255,255,255,0.15)', marginTop: '2px', marginBottom: '4px' }}>
                                    {item.subItems.map((subItem) => {
                                        const subActive = isActive(subItem.path);
                                        return (
                                            <Link
                                                ref={subActive ? (activeRowRef as React.RefObject<HTMLAnchorElement>) : undefined}
                                                key={subItem.name}
                                                to={subItem.path}
                                                style={{
                                                    position: 'relative',
                                                    display: 'flex', alignItems: 'center', gap: '8px',
                                                    padding: '6px 12px 6px 16px', borderRadius: '0 6px 6px 0',
                                                    cursor: 'pointer', transition: 'background 0.15s, color 0.15s',
                                                    background: subActive ? ACTIVE_BG : 'transparent',
                                                    marginLeft: '4px',
                                                    textDecoration: 'none',
                                                    boxShadow: subActive ? `inset 3px 0 0 0 ${ACCENT}` : 'none',
                                                }}
                                                onMouseOver={(e) => {
                                                    if (!subActive) {
                                                        e.currentTarget.style.background = HOVER_BG;
                                                    }
                                                }}
                                                onMouseOut={(e) => {
                                                    if (!subActive) {
                                                        e.currentTarget.style.background = 'transparent';
                                                    }
                                                }}
                                            >
                                                <subItem.icon size={14} style={{
                                                    color: subActive ? ACCENT : 'rgba(255,255,255,0.5)',
                                                    flexShrink: 0
                                                }} />
                                                <span style={{
                                                    fontSize: '12.5px',
                                                    fontWeight: subActive ? 700 : 400,
                                                    color: subActive ? ACCENT : 'rgba(255,255,255,0.75)',
                                                }}>
                                                    {subItem.name}
                                                </span>
                                            </Link>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    );
                })}
            </nav>

            {/* Footer */}
            <div style={{ padding: '12px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                {/* Account / Profile link — real <Link> so right-click /
                    middle-click / Ctrl+click open in a new tab natively. */}
                <Link
                    to="/account"
                    style={{
                        display: 'flex', alignItems: 'center', gap: '10px',
                        padding: '8px 12px', borderRadius: '8px',
                        cursor: 'pointer', transition: 'all 0.15s',
                        color: isActive('/account') ? '#ffffff' : 'rgba(255,255,255,0.75)',
                        background: isActive('/account') ? 'rgba(255,255,255,0.14)' : 'transparent',
                        marginBottom: '2px',
                        textDecoration: 'none',
                    }}
                    onMouseOver={(e) => { if (!isActive('/account')) e.currentTarget.style.background = 'rgba(255,255,255,0.07)'; }}
                    onMouseOut={(e) => { if (!isActive('/account')) e.currentTarget.style.background = 'transparent'; }}
                >
                    <User size={18} style={{ color: isActive('/account') ? '#ffffff' : 'rgba(255,255,255,0.5)' }} />
                    <span style={{ fontSize: '13.5px', fontWeight: 500 }}>My Account</span>
                </Link>

                <div
                    onClick={() => setShowLogoutConfirm(true)}
                    style={{
                        display: 'flex', alignItems: 'center', gap: '10px',
                        padding: '8px 12px', borderRadius: '8px',
                        cursor: 'pointer', transition: 'all 0.15s',
                        color: 'rgba(252,165,165,0.9)',
                    }}
                    onMouseOver={(e) => e.currentTarget.style.background = 'rgba(239,68,68,0.18)'}
                    onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
                >
                    <LogOut size={18} />
                    <span style={{ fontSize: '13.5px', fontWeight: 500 }}>Sign Out</span>
                </div>
            </div>

            {/* ── Logout confirmation overlay ─────────────────────── */}
            {showLogoutConfirm && (
                <div style={{
                    position: 'fixed', inset: 0,
                    background: 'rgba(15, 23, 42, 0.55)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    zIndex: 9999,
                    backdropFilter: 'blur(2px)',
                }}>
                    <div style={{
                        background: 'white', borderRadius: '20px',
                        padding: '36px 32px', maxWidth: '380px', width: '90%',
                        boxShadow: '0 24px 64px rgba(0,0,0,0.25)',
                        textAlign: 'center',
                    }}>
                        <div style={{
                            width: '60px', height: '60px', borderRadius: '50%',
                            background: '#fef2f2',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            margin: '0 auto 20px',
                        }}>
                            <LogOut size={28} style={{ color: '#ef4444' }} />
                        </div>

                        <h3 style={{ fontSize: '20px', fontWeight: 700, color: '#1e293b', marginBottom: '8px' }}>
                            Sign Out?
                        </h3>
                        <p style={{ fontSize: '14px', color: '#64748b', lineHeight: 1.6, marginBottom: '28px' }}>
                            You are about to sign out of <strong>{activeTenant}</strong>.
                            Any unsaved changes will be lost.
                        </p>

                        <div style={{ display: 'flex', gap: '12px' }}>
                            <button
                                onClick={() => setShowLogoutConfirm(false)}
                                style={{
                                    flex: 1, padding: '12px',
                                    background: '#f8fafc', border: '1.5px solid #e2e8f0',
                                    borderRadius: '10px', fontSize: '14px', fontWeight: 600,
                                    color: '#475569', cursor: 'pointer', fontFamily: 'inherit',
                                    transition: 'all 0.15s',
                                }}
                                onMouseOver={(e) => e.currentTarget.style.background = '#f1f5f9'}
                                onMouseOut={(e) => e.currentTarget.style.background = '#f8fafc'}
                            >
                                Stay
                            </button>
                            <button
                                onClick={handleLogout}
                                style={{
                                    flex: 1, padding: '12px',
                                    background: 'linear-gradient(135deg, #ef4444, #dc2626)',
                                    border: 'none', borderRadius: '10px',
                                    fontSize: '14px', fontWeight: 600,
                                    color: 'white', cursor: 'pointer', fontFamily: 'inherit',
                                    boxShadow: '0 4px 12px rgba(239,68,68,0.35)',
                                    transition: 'all 0.15s',
                                }}
                                onMouseOver={(e) => e.currentTarget.style.opacity = '0.9'}
                                onMouseOut={(e) => e.currentTarget.style.opacity = '1'}
                            >
                                Sign Out
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
        </>
    );
};

export default Sidebar;
