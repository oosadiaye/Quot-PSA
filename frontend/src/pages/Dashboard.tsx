import { useState, useEffect } from 'react';
import Sidebar from '../components/Sidebar';
import {
    Wallet,
    ShoppingCart,
    Package,
    Wrench,
    TrendingUp,
    CheckCircle,
    ArrowRight,
    Users,
    Factory,
    Shield,
    FileText,
    Clock,
    AlertTriangle,
    LogOut,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';
import { useTenantModules } from '../hooks/useTenantModules';
import logger from '../utils/logger';

/** Maps module display name → TenantModule key used by the backend */
const MODULE_KEY_MAP: Record<string, string> = {
    'Accounting':      'accounting',
    'Procurement':     'procurement',
    'Inventory':       'inventory',
    'Sales':           'sales',
    'Service':         'service',
    'Human Resources': 'hrm',
    'Production':      'production',
    'Quality':         'quality',
};

/** Convert a 6-digit hex colour to rgba() with a given alpha (0–1). */
const hexRgba = (hex: string, alpha: number) => {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
};

const Dashboard = () => {
    const navigate = useNavigate();
    const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);

    // ── Back-button interception ──────────────────────────────────────
    // We push a dummy history entry when the dashboard mounts so the first
    // back-press fires a `popstate` event instead of navigating away.
    // Inside the handler we re-push immediately to keep the URL locked
    // while the confirmation modal is open.
    useEffect(() => {
        window.history.pushState(null, '', window.location.pathname);
        const handlePopState = () => {
            window.history.pushState(null, '', window.location.pathname);
            setShowLeaveConfirm(true);
        };
        window.addEventListener('popstate', handlePopState);
        return () => window.removeEventListener('popstate', handlePopState);
    }, []);

    const handleConfirmLeave = () => {
        // Clear all session data then redirect to login
        localStorage.removeItem('authToken');
        localStorage.removeItem('user');
        localStorage.removeItem('tenantDomain');
        localStorage.removeItem('tenantInfo');
        localStorage.removeItem('tenantPermissions');
        localStorage.removeItem('activeTenant');
        localStorage.removeItem('impersonation');
        sessionStorage.removeItem('impersonation_session');
        setShowLeaveConfirm(false);
        navigate('/login', { replace: true });
    };

    let user = { name: 'Admin User' };
    try {
        const userRaw = localStorage.getItem('user');
        if (userRaw) {
            user = JSON.parse(userRaw);
        }
    } catch {
        logger.error('Failed to parse user data from localStorage');
    }

    // Reads the human-readable tenant name set during login / impersonation
    const organizationName =
        localStorage.getItem('activeTenant') ||
        (() => {
            try {
                const info = localStorage.getItem('tenantInfo');
                return info ? JSON.parse(info).name : null;
            } catch { return null; }
        })() ||
        'My Organization';

    const { data: tenantModules, isLoading: modulesLoading } = useTenantModules();

    const { data: dashboardData } = useQuery({
        queryKey: ['dashboard-stats'],
        queryFn: async () => {
            const { data } = await apiClient.get('/core/dashboard-stats/');
            return data;
        },
        staleTime: 60000,
    });

    const stats = [
        { label: 'Pending Approvals', value: dashboardData?.pending_approvals ?? '\u2014', change: dashboardData?.pending_approvals_change ?? '', icon: CheckCircle, color: '#191e6a' },
        { label: 'Active Work Orders', value: dashboardData?.active_work_orders ?? '\u2014', change: dashboardData?.active_work_orders_change ?? '', icon: Wrench, color: '#f59e0b' },
        { label: 'Open Requisitions', value: dashboardData?.open_requisitions ?? '\u2014', change: dashboardData?.open_requisitions_change ?? '', icon: FileText, color: '#22c55e' },
        { label: 'Low Stock Alerts', value: dashboardData?.low_stock_alerts ?? '\u2014', change: dashboardData?.low_stock_alerts_change ?? '', icon: AlertTriangle, color: '#ef4444' },
    ];

    /** All possible module cards — filtered below based on tenant module config */
    const allModules = [
        { name: 'Accounting',      icon: Wallet,    path: '/accounting/dashboard',  color: '#191e6a', description: 'General Ledger, AP/AR, and Financial Reporting.',            info: dashboardData?.accounting_journals    ? `${dashboardData.accounting_journals} Pending Journals`   : '12 Pending Journals' },
        { name: 'Procurement',     icon: ShoppingCart, path: '/procurement/dashboard', color: '#0d9488', description: 'Purchase requests, orders, and vendor management.',       info: dashboardData?.open_requisitions      ? `${dashboardData.open_requisitions} Open Requisitions`    : '5 Open Requisitions' },
        { name: 'Inventory',       icon: Package,   path: '/inventory/dashboard',   color: '#7c3aed', description: 'Stock levels, valuation, and asset tracking.',               info: dashboardData?.low_stock_alerts       ? `${dashboardData.low_stock_alerts} Low Stock Alerts`      : '2 Low Stock Alerts' },
        { name: 'Sales',           icon: TrendingUp, path: '/sales/dashboard',      color: '#f59e0b', description: 'CRM, quotations, and automated invoicing.',                   info: dashboardData?.sales_mtd              ? `₦${dashboardData.sales_mtd} Sales MTD`                 : '₦2.4M Sales MTD' },
        { name: 'Service',         icon: Wrench,    path: '/service/dashboard',     color: '#e05c1a', description: 'Work orders, citizen requests, and metrics.',                 info: dashboardData?.active_work_orders     ? `${dashboardData.active_work_orders} Active Work Orders`  : '8 Active Work Orders' },
        { name: 'Human Resources', icon: Users,     path: '/hrm/employees',         color: '#16a34a', description: 'Employee directory, leave management, and attendance.',       info: dashboardData?.active_employees       ? `${dashboardData.active_employees} Active Employees`      : '45 Active Employees' },
        { name: 'Production',      icon: Factory,   path: '/production/dashboard',  color: '#475569', description: 'Bill of Materials, work centers, and production orders.',    info: dashboardData?.production_orders      ? `${dashboardData.production_orders} Active Orders`        : '12 Active Orders' },
        { name: 'Quality',         icon: Shield,    path: '/quality/dashboard',     color: '#3b82f6', description: 'Inspections, non-conformance, and quality controls.',         info: dashboardData?.open_ncr               ? `${dashboardData.open_ncr} Open NCRs`                     : '2 Open NCRs' },
    ];

    /**
     * Filter module cards based on enabled_modules from the API:
     * - While loading (first fetch in progress): show nothing to avoid a
     *   misleading flash of all cards before real data arrives.
     * - If backend returned an empty map (fresh tenant / graceful degradation):
     *   show all cards so a new tenant still sees a useful dashboard.
     * - Otherwise: show only the cards whose module key is enabled.
     */
    const enabledModuleMap = tenantModules?.enabled_modules ?? {};
    const hasModuleConfig = Object.keys(enabledModuleMap).length > 0;
    const modules = modulesLoading
        ? []   // hide cards during initial load — prevents "all flash"
        : hasModuleConfig
            ? allModules.filter((mod) => enabledModuleMap[MODULE_KEY_MAP[mod.name]] === true)
            : allModules;

    const quickActions = [
        { label: 'New Journal Entry', icon: FileText, path: '/accounting/new' },
        { label: 'Create Requisition', icon: ShoppingCart, path: '/procurement/requisitions/new' },
        { label: 'Approval Inbox', icon: CheckCircle, path: '/approvals' },
        { label: 'View Reports', icon: TrendingUp, path: '/accounting/reports' },
    ];

    const pendingApprovals = [
        { title: 'Purchase Order #PO-2024-0847', type: 'Procurement', time: '2 hours ago', amount: '₦450,000' },
        { title: 'Journal Entry #JE-1204', type: 'Accounting', time: '4 hours ago', amount: '₦1,200,000' },
        { title: 'Leave Request — Sarah O.', type: 'HR', time: '1 day ago', amount: '5 days' },
    ];

    return (
        <div style={{ display: 'flex', background: '#eef2f7', minHeight: '100vh' }}>
            {/* ── Back-navigation / leave confirmation modal ────────── */}
            {showLeaveConfirm && (
                <div style={{
                    position: 'fixed', inset: 0,
                    background: 'rgba(15, 23, 42, 0.55)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    zIndex: 9999,
                    backdropFilter: 'blur(2px)',
                }}>
                    <div style={{
                        background: 'white', borderRadius: '20px',
                        padding: '36px 32px', maxWidth: '400px', width: '90%',
                        boxShadow: '0 24px 64px rgba(0,0,0,0.25)',
                        textAlign: 'center',
                    }}>
                        <div style={{
                            width: '64px', height: '64px', borderRadius: '50%',
                            background: '#fef2f2',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            margin: '0 auto 20px',
                        }}>
                            <LogOut size={30} style={{ color: '#ef4444' }} />
                        </div>

                        <h3 style={{ fontSize: '20px', fontWeight: 700, color: '#1e293b', marginBottom: '8px' }}>
                            Leave Dashboard?
                        </h3>
                        <p style={{ fontSize: '14px', color: '#64748b', lineHeight: 1.6, marginBottom: '28px' }}>
                            Navigating back will sign you out of <strong>{organizationName}</strong>.
                            Any unsaved work will be lost.
                        </p>

                        <div style={{ display: 'flex', gap: '12px' }}>
                            <button
                                onClick={() => setShowLeaveConfirm(false)}
                                style={{
                                    flex: 1, padding: '13px',
                                    background: '#f8fafc', border: '1.5px solid #e2e8f0',
                                    borderRadius: '10px', fontSize: '14px', fontWeight: 600,
                                    color: '#475569', cursor: 'pointer', fontFamily: 'inherit',
                                }}
                            >
                                Stay Here
                            </button>
                            <button
                                onClick={handleConfirmLeave}
                                style={{
                                    flex: 1, padding: '13px',
                                    background: 'linear-gradient(135deg, #ef4444, #dc2626)',
                                    border: 'none', borderRadius: '10px',
                                    fontSize: '14px', fontWeight: 600,
                                    color: 'white', cursor: 'pointer', fontFamily: 'inherit',
                                    boxShadow: '0 4px 12px rgba(239,68,68,0.35)',
                                }}
                            >
                                Sign Out
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '0' }}>
                {/* Welcome Banner */}
                <div style={{
                    background: 'linear-gradient(135deg, #191e6a 0%, #2e3898 100%)',
                    padding: '32px 40px', color: 'white',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center'
                }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'white', marginBottom: '6px' }}>
                            Welcome back, {user.name}
                        </h1>
                        <p style={{ fontSize: '15px', color: 'rgba(255,255,255,0.7)' }}>
                            Here's what's happening with your operations today.
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: '10px' }}>
                        {quickActions.map((action) => (
                            <button key={action.label} onClick={() => navigate(action.path)}
                                style={{
                                    display: 'flex', alignItems: 'center', gap: '6px',
                                    padding: '8px 14px', borderRadius: '8px',
                                    background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.25)',
                                    color: 'white', cursor: 'pointer', fontSize: '13px', fontWeight: 500,
                                    fontFamily: 'inherit', transition: 'all 0.2s',
                                }}
                                onMouseOver={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.25)'}
                                onMouseOut={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.15)'}
                            >
                                <action.icon size={14} />
                                {action.label}
                            </button>
                        ))}
                    </div>
                </div>

                <div style={{ padding: '24px 40px' }}>
                    {/* Stat Cards */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px', marginBottom: '28px' }}>
                        {stats.map((stat) => (
                            <div key={stat.label} style={{
                                background: '#fafbfc', borderRadius: '14px', padding: '20px 24px',
                                border: '1px solid #e2e8f0', transition: 'all 0.2s'
                            }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                                    <div style={{ fontSize: '13px', fontWeight: 500, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.3px' }}>
                                        {stat.label}
                                    </div>
                                    <div style={{
                                        width: '36px', height: '36px', borderRadius: '10px',
                                        background: hexRgba(stat.color, 0.1), display: 'flex', alignItems: 'center', justifyContent: 'center'
                                    }}>
                                        <stat.icon size={18} style={{ color: stat.color }} />
                                    </div>
                                </div>
                                <div style={{ fontSize: '28px', fontWeight: 700, color: '#1e293b', marginBottom: '4px' }}>
                                    {stat.value}
                                </div>
                                <div style={{ fontSize: '12px', color: '#94a3b8' }}>{stat.change}</div>
                            </div>
                        ))}
                    </div>

                    {/* Main content grid */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '24px' }}>
                        {/* Module Cards */}
                        <div>
                            <h2 style={{ fontSize: '18px', fontWeight: 700, color: '#1e293b', marginBottom: '16px' }}>
                                Modules
                            </h2>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px' }}>
                                {modules.map((mod) => (
                                    <div
                                        key={mod.name}
                                        onClick={() => navigate(mod.path)}
                                        style={{
                                            background: '#fafbfc', borderRadius: '14px',
                                            border: '1px solid #e2e8f0', cursor: 'pointer',
                                            overflow: 'hidden', transition: 'all 0.2s'
                                        }}
                                        onMouseOver={(e) => {
                                            e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.08)';
                                            e.currentTarget.style.transform = 'translateY(-2px)';
                                        }}
                                        onMouseOut={(e) => {
                                            e.currentTarget.style.boxShadow = 'none';
                                            e.currentTarget.style.transform = 'translateY(0)';
                                        }}
                                    >
                                        <div style={{ height: '3px', background: mod.color }} />
                                        <div style={{ padding: '20px' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '10px' }}>
                                                <div style={{
                                                    width: '40px', height: '40px', borderRadius: '10px',
                                                    background: hexRgba(mod.color, 0.1),
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center'
                                                }}>
                                                    <mod.icon size={20} style={{ color: mod.color }} />
                                                </div>
                                                <div>
                                                    <div style={{ fontSize: '15px', fontWeight: 700, color: '#1e293b' }}>{mod.name}</div>
                                                    <div style={{ fontSize: '11px', color: mod.color, fontWeight: 600 }}>{mod.info}</div>
                                                </div>
                                            </div>
                                            <p style={{ fontSize: '13px', color: '#64748b', lineHeight: 1.5, marginBottom: '12px' }}>
                                                {mod.description}
                                            </p>
                                            <div style={{
                                                display: 'flex', alignItems: 'center', gap: '4px',
                                                fontSize: '13px', fontWeight: 600, color: mod.color
                                            }}>
                                                Open <ArrowRight size={14} />
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Right sidebar */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                            {/* Pending Approvals */}
                            <div style={{
                                background: '#fafbfc', borderRadius: '14px',
                                border: '1px solid #e2e8f0', padding: '20px'
                            }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                                    <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#1e293b' }}>Pending Approvals</h3>
                                    <button onClick={() => navigate('/approvals')}
                                        style={{
                                            background: 'none', border: 'none', cursor: 'pointer',
                                            fontSize: '13px', color: '#191e6a', fontWeight: 600, fontFamily: 'inherit'
                                        }}>View All</button>
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                    {pendingApprovals.map((item) => (
                                        <div key={item.id ?? item.title} style={{
                                            padding: '12px', borderRadius: '10px', background: '#f8fafc',
                                            border: '1px solid #f1f5f9'
                                        }}>
                                            <div style={{ fontSize: '13px', fontWeight: 600, color: '#1e293b', marginBottom: '4px' }}>
                                                {item.title}
                                            </div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                    <span style={{
                                                        fontSize: '11px', fontWeight: 600, color: '#191e6a',
                                                        background: 'rgba(25,30,106,0.07)', padding: '2px 8px', borderRadius: '4px'
                                                    }}>{item.type}</span>
                                                    <span style={{ fontSize: '11px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '3px' }}>
                                                        <Clock size={11} /> {item.time}
                                                    </span>
                                                </div>
                                                <span style={{ fontSize: '13px', fontWeight: 600, color: '#1e293b' }}>{item.amount}</span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* System Status */}
                            <div style={{
                                background: '#fafbfc', borderRadius: '14px',
                                border: '1px solid #e2e8f0', padding: '20px'
                            }}>
                                <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#1e293b', marginBottom: '16px' }}>System Status</h3>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <span style={{ fontSize: '13px', color: '#64748b' }}>Server Status</span>
                                        <span style={{
                                            fontSize: '12px', fontWeight: 600, color: '#22c55e',
                                            display: 'flex', alignItems: 'center', gap: '5px'
                                        }}>
                                            <div style={{ width: '7px', height: '7px', background: '#22c55e', borderRadius: '50%' }} />
                                            Operational
                                        </span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <span style={{ fontSize: '13px', color: '#64748b' }}>Organization</span>
                                        <span style={{ fontSize: '13px', fontWeight: 600, color: '#1e293b' }}>
                                            {organizationName}
                                        </span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <span style={{ fontSize: '13px', color: '#64748b' }}>Last Refresh</span>
                                        <span style={{ fontSize: '13px', color: '#475569' }}>
                                            {new Date().toLocaleTimeString()}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
};

export default Dashboard;
