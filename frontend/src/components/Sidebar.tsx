import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
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
} from 'lucide-react';
import { usePermissions, hasPermission } from '../hooks/usePermissions';
import { useTenantModules } from '../hooks/useTenantModules';
import { useBranding } from '../context/BrandingContext';
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
        name: 'Accounting', icon: Wallet, path: '/accounting/dashboard',
        requiredPerm: 'view_journalheader', module: 'accounting',
        subItems: [
            { name: 'Chart of Accounts', path: '/accounting/coa', icon: List },
            { name: 'Journal Entries', path: '/accounting', icon: FileText },
            { name: 'GL Reports', path: '/accounting/reports', icon: BarChart3 },
            { name: 'Accounts Payable', path: '/accounting/ap', icon: Receipt },
            { name: 'Accounts Receivable', path: '/accounting/ar', icon: DollarSign },
            { name: 'Incoming Payments', path: '/accounting/incoming-payments', icon: Banknote },
            { name: 'Outgoing Payments', path: '/accounting/outgoing-payments', icon: ArrowUpRight },
            { name: 'Fixed Assets', path: '/accounting/fixed-assets', icon: Building },
            { name: 'Asset Categories', path: '/accounting/asset-categories', icon: FolderTree },
            { name: 'Bank & Cash', path: '/accounting/bank-cash', icon: Landmark },
            { name: 'Cash Accounts', path: '/accounting/cash-accounts', icon: Coins },
            { name: 'Cost Centers', path: '/accounting/cost-centers', icon: Target },
            { name: 'Recurring Journals', path: '/accounting/recurring-journals', icon: Repeat },
            { name: 'Accruals & Deferrals', path: '/accounting/accruals-deferrals', icon: CalendarClock },
            { name: 'Intercompany', path: '/accounting/intercompany', icon: Building },
            { name: 'Multi-Company', path: '/accounting/multi-company', icon: Landmark },
            { name: 'Consolidation', path: '/accounting/consolidation', icon: Layers },
        ],
    },
    {
        name: 'Dimensions', icon: Layers, path: '/accounting/dimensions',
        requiredPerm: 'view_journalheader', module: 'dimensions',
        subItems: [
            { name: 'Dimensions Dashboard', path: '/accounting/dimensions', icon: BarChart3 },
            { name: 'Funds', path: '/accounting/dimensions/funds', icon: Wallet },
            { name: 'Functions', path: '/accounting/dimensions/functions', icon: BarChart3 },
            { name: 'Programs', path: '/accounting/dimensions/programs', icon: FileText },
            { name: 'Geo Locations', path: '/accounting/dimensions/geos', icon: MapPin },
        ],
    },
    {
        name: 'Budget Management', icon: DollarSign, path: '/accounting/budget/dashboard',
        requiredPerm: 'view_budget', module: 'budget',
        subItems: [
            { name: 'Budget Dashboard', path: '/accounting/budget/dashboard', icon: BarChart3 },
            { name: 'Budget Entry', path: '/accounting/budget/entry', icon: FileText },
            { name: 'Create / Upload', path: '/accounting/budget/create', icon: FilePlus },
            { name: 'Variance Analysis', path: '/accounting/budget/variance', icon: TrendingUp },
        ],
    },
    {
        name: 'Procurement', icon: ShoppingCart, path: '/procurement/dashboard',
        requiredPerm: 'view_purchaseorder', module: 'procurement',
        subItems: [
            { name: 'Vendors', path: '/procurement/vendors', icon: Building },
            { name: 'Vendor Categories', path: '/procurement/vendor-categories', icon: FolderTree },
            { name: 'Purchase Requisitions', path: '/procurement/requisitions', icon: FileText },
            { name: 'Purchase Orders', path: '/procurement/orders', icon: ShoppingCart },
            { name: 'Goods Received Notes', path: '/procurement/grn', icon: Package },
            { name: 'Invoice Verification', path: '/procurement/matching', icon: CheckCircle },
            { name: 'Vendor Performance', path: '/procurement/vendor-performance', icon: TrendingUp },
            { name: 'Purchase Returns', path: '/procurement/returns', icon: RotateCcw },
        ],
    },
    {
        name: 'Inventory', icon: Package, path: '/inventory/dashboard',
        requiredPerm: 'view_item', module: 'inventory',
        subItems: [
            { name: 'Inventory Dashboard', path: '/inventory/dashboard', icon: BarChart3 },
            { name: 'Products', path: '/inventory', icon: Package },
            { name: 'Product Types', path: '/inventory/product-types', icon: Layers },
            { name: 'Product Categories', path: '/inventory/categories', icon: List },
            { name: 'Warehouses', path: '/inventory/warehouses', icon: Warehouse },
            { name: 'Inventory Ledger', path: '/inventory/stocks', icon: Boxes },
            { name: 'Batch Management', path: '/inventory/batches', icon: Package },
            { name: 'Serial Numbers', path: '/inventory/serial-numbers', icon: Hash },
            { name: 'Inventory Adjustments', path: '/inventory/adjustments', icon: SlidersHorizontal },
            { name: 'Stock Transfers', path: '/inventory/movements', icon: Truck },
            { name: 'Stock Valuation', path: '/inventory/valuation', icon: DollarSign },
            { name: 'Reconciliation', path: '/inventory/reconciliations', icon: RotateCcw },
            { name: 'Reorder Alerts', path: '/inventory/reorder-alerts', icon: Bell },
            { name: 'Expiry Alerts', path: '/inventory/expiry-alerts', icon: Calendar },
        ],
    },
    {
        name: 'Sales', icon: TrendingUp, path: '/sales/dashboard',
        requiredPerm: 'view_salesorder', module: 'sales',
        subItems: [
            { name: 'Customers', path: '/sales/customers', icon: Users },
            { name: 'Customer Categories', path: '/sales/customer-categories', icon: BookOpen },
            { name: 'CRM Lite', path: '/sales/crm', icon: UserPlus },
            { name: 'Quotations', path: '/sales/quotations', icon: FileText },
            { name: 'Sales Orders', path: '/sales/orders', icon: ShoppingCart },
            { name: 'Delivery Notes', path: '/sales/delivery-notes', icon: Truck },
            { name: 'Automated Invoicing', path: '/sales/invoicing', icon: Receipt },
            { name: 'Credit Limits', path: '/sales/credit-limits', icon: CreditCard },
        ],
    },
    {
        name: 'Service', icon: Wrench, path: '/service/dashboard',
        requiredPerm: 'view_serviceticket', module: 'service',
        subItems: [
            { name: 'Service Dashboard', path: '/service/dashboard', icon: BarChart3 },
            { name: 'Service Assets', path: '/service/assets', icon: HardDrive },
            { name: 'Technicians', path: '/service/technicians', icon: UserCog },
            { name: 'Service Tickets', path: '/service/tickets', icon: Ticket },
            { name: 'Maintenance Schedules', path: '/service/schedules', icon: CalendarClock },
            { name: 'Work Orders', path: '/service/work-orders', icon: FileText },
            { name: 'Citizen Requests', path: '/service/citizen-requests', icon: UserPlus },
            { name: 'Service Metrics', path: '/service/metrics', icon: BarChart3 },
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
        name: 'Production', icon: Factory, path: '/production/dashboard',
        requiredPerm: 'view_productionorder', module: 'production',
        subItems: [
            { name: 'Production Dashboard', path: '/production/dashboard', icon: BarChart3 },
            { name: 'Bill of Materials', path: '/production/bom', icon: FileText },
            { name: 'Work Centers', path: '/production/work-centers', icon: Factory },
            { name: 'Production Orders', path: '/production/orders', icon: Package },
        ],
    },
    {
        name: 'Quality', icon: Shield, path: '/quality/dashboard',
        requiredPerm: 'view_qualityinspection', module: 'quality',
        subItems: [
            { name: 'Quality Dashboard', path: '/quality/dashboard', icon: BarChart3 },
            { name: 'Inspections', path: '/quality/inspections', icon: Search },
            { name: 'Non-Conformance', path: '/quality/ncr', icon: AlertTriangle },
            { name: 'Customer Complaints', path: '/quality/complaints', icon: UserPlus },
            { name: 'Checklists', path: '/quality/checklists', icon: ClipboardCheck },
            { name: 'Calibrations', path: '/quality/calibrations', icon: Gauge },
            { name: 'Supplier Quality', path: '/quality/supplier-quality', icon: BadgeCheck },
        ],
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
        name: 'Settings', icon: Settings, path: '/settings/accounting',
        requiredPerm: 'view_accountingsettings', module: null,
        subItems: [
            { name: 'Accounting Settings', path: '/settings/accounting', icon: Wallet },
            { name: 'Currencies', path: '/settings/accounting/currencies', icon: Coins },
            { name: 'Tax Management', path: '/settings/tax', icon: Receipt },
            { name: 'Fiscal Year', path: '/settings/fiscal-year', icon: CalendarCheck },
            { name: 'Bank Accounts', path: '/settings/bank-accounts', icon: Landmark },
            { name: 'Inventory Settings', path: '/settings/inventory', icon: Package },
            { name: 'Branding & Company', path: '/settings/branding', icon: Building },
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
    const tenantInfo = (() => {
        try {
            const raw = localStorage.getItem('tenantInfo');
            return raw ? JSON.parse(raw) : null;
        } catch { return null; }
    })();
    const activeTenant = tenantInfo?.name || 'No Organization';
    const { data: user, isLoading: permLoading } = usePermissions();
    const { data: tenantModules, isLoading: modulesLoading } = useTenantModules();
    const [expandedMenus, setExpandedMenus] = useState<string[]>([]);
    const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

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
        if (permLoading) return !item.requiredPerm;
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
        <div style={{
            width: '260px', height: '100vh',
            background: 'linear-gradient(180deg, #1a1f66 0%, #242a88 100%)',
            color: 'rgba(255,255,255,0.75)',
            display: 'flex', flexDirection: 'column',
            position: 'fixed', left: 0, top: 0,
            overflowY: 'auto',
            borderRight: '1px solid rgba(255,255,255,0.07)',
            zIndex: 20
        }}>
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

                {/* Tenant switcher */}
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '8px',
                    padding: '8px 10px', borderRadius: '8px',
                    background: 'rgba(255,255,255,0.08)',
                    border: '1px solid rgba(255,255,255,0.12)'
                }}>
                    <div style={{
                        width: '28px', height: '28px', borderRadius: '6px',
                        background: 'rgba(255,255,255,0.12)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0
                    }}>
                        <Building size={14} style={{ color: 'rgba(255,255,255,0.7)' }} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{
                            fontSize: '12px', fontWeight: 600, color: '#ffffff',
                            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'
                        }}>
                            {activeTenant}
                        </div>
                    </div>
                    <button
                        onClick={handleSwitchTenant}
                        title="Switch Organization"
                        style={{
                            background: 'none', border: 'none', cursor: 'pointer',
                            color: 'rgba(255,255,255,0.55)', padding: '2px',
                            fontSize: '11px', fontWeight: 600,
                        }}
                    >
                        Switch
                    </button>
                </div>
            </div>

            {/* Back button */}
            <div style={{ padding: '8px 12px 4px' }}>
                <BackButton variant="compact" />
            </div>

            {/* Navigation */}
            <nav style={{ flex: 1, padding: '4px 12px', display: 'flex', flexDirection: 'column', gap: '1px' }}>
                {filteredItems.map((item) => (
                    <div key={item.name}>
                        <div
                            onClick={() => {
                                if (item.subItems) {
                                    toggleMenu(item.name);
                                } else {
                                    navigate(item.path);
                                }
                            }}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '10px',
                                padding: '8px 12px', borderRadius: '8px',
                                cursor: 'pointer', transition: 'all 0.15s',
                                background: isParentActive(item) ? 'rgba(255,255,255,0.14)' : 'transparent',
                                color: isParentActive(item) ? '#ffffff' : 'rgba(255,255,255,0.75)',
                            }}
                            onMouseOver={(e) => {
                                if (!isParentActive(item)) {
                                    e.currentTarget.style.background = 'rgba(255,255,255,0.07)';
                                }
                            }}
                            onMouseOut={(e) => {
                                if (!isParentActive(item)) {
                                    e.currentTarget.style.background = 'transparent';
                                }
                            }}
                        >
                            <item.icon size={18} style={{
                                color: isParentActive(item) ? '#ffffff' : 'rgba(255,255,255,0.5)',
                                flexShrink: 0
                            }} />
                            <span style={{
                                flex: 1, fontSize: '13.5px',
                                fontWeight: isParentActive(item) ? 600 : 500,
                                color: isParentActive(item) ? '#ffffff' : 'rgba(255,255,255,0.8)',
                            }}>
                                {item.name}
                            </span>
                            {item.subItems ? (
                                expandedMenus.includes(item.name) ?
                                    <ChevronDown size={14} style={{ color: 'rgba(255,255,255,0.35)' }} /> :
                                    <ChevronRight size={14} style={{ color: 'rgba(255,255,255,0.35)' }} />
                            ) : null}
                        </div>

                        {item.subItems && expandedMenus.includes(item.name) && (
                            <div style={{ marginLeft: '12px', borderLeft: '1.5px solid rgba(255,255,255,0.15)', marginTop: '2px', marginBottom: '4px' }}>
                                {item.subItems.map((subItem) => (
                                    <div
                                        key={subItem.name}
                                        onClick={() => navigate(subItem.path)}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: '8px',
                                            padding: '6px 12px 6px 16px', borderRadius: '0 6px 6px 0',
                                            cursor: 'pointer', transition: 'all 0.15s',
                                            background: isActive(subItem.path) ? 'rgba(255,255,255,0.14)' : 'transparent',
                                            marginLeft: '4px'
                                        }}
                                        onMouseOver={(e) => {
                                            if (!isActive(subItem.path)) {
                                                e.currentTarget.style.background = 'rgba(255,255,255,0.07)';
                                            }
                                        }}
                                        onMouseOut={(e) => {
                                            if (!isActive(subItem.path)) {
                                                e.currentTarget.style.background = 'transparent';
                                            }
                                        }}
                                    >
                                        <subItem.icon size={14} style={{
                                            color: isActive(subItem.path) ? '#ffffff' : 'rgba(255,255,255,0.45)',
                                            flexShrink: 0
                                        }} />
                                        <span style={{
                                            fontSize: '12.5px',
                                            fontWeight: isActive(subItem.path) ? 600 : 400,
                                            color: isActive(subItem.path) ? '#ffffff' : 'rgba(255,255,255,0.7)',
                                        }}>
                                            {subItem.name}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                ))}
            </nav>

            {/* Footer */}
            <div style={{ padding: '12px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                {/* Account / Profile link */}
                <div
                    onClick={() => navigate('/account')}
                    style={{
                        display: 'flex', alignItems: 'center', gap: '10px',
                        padding: '8px 12px', borderRadius: '8px',
                        cursor: 'pointer', transition: 'all 0.15s',
                        color: isActive('/account') ? '#ffffff' : 'rgba(255,255,255,0.75)',
                        background: isActive('/account') ? 'rgba(255,255,255,0.14)' : 'transparent',
                        marginBottom: '2px',
                    }}
                    onMouseOver={(e) => { if (!isActive('/account')) e.currentTarget.style.background = 'rgba(255,255,255,0.07)'; }}
                    onMouseOut={(e) => { if (!isActive('/account')) e.currentTarget.style.background = 'transparent'; }}
                >
                    <User size={18} style={{ color: isActive('/account') ? '#ffffff' : 'rgba(255,255,255,0.5)' }} />
                    <span style={{ fontSize: '13.5px', fontWeight: 500 }}>My Account</span>
                </div>

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
    );
};

export default Sidebar;
