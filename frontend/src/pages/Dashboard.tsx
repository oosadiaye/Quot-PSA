import { useState, useEffect, useMemo } from 'react';
import Sidebar from '../components/Sidebar';
import {
    TrendingUp,
    TrendingDown,
    CheckCircle,
    ArrowRight,
    FileText,
    Clock,
    LogOut,
    DollarSign,
    CreditCard,
    BarChart3,
    PieChart as PieChartIcon,
    ArrowUpRight,
    ArrowDownRight,
    Banknote,
    Receipt,
    ShoppingCart,
    Users,
    AlertTriangle,
    Activity,
    Wallet,
    Package,
    Landmark,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';
import { useTenantModules } from '../hooks/useTenantModules';
import logger from '../utils/logger';
import {
    AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, Legend,
} from 'recharts';

/* ── helpers ────────────────────────────────────────────── */

const hexRgba = (hex: string, alpha: number) => {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
};

/** Compact currency formatter — e.g. ₦1.2M, ₦450K */
const fmtCurrency = (val: number): string => {
    const abs = Math.abs(val);
    const sign = val < 0 ? '-' : '';
    if (abs >= 1_000_000) return `${sign}₦${(abs / 1_000_000).toFixed(1)}M`;
    if (abs >= 1_000) return `${sign}₦${(abs / 1_000).toFixed(0)}K`;
    return `${sign}₦${abs.toLocaleString('en-NG', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
};

const fmtFull = (val: number) =>
    '₦' + val.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Percentage change between two values */
const pctChange = (current: number, previous: number): { value: string; positive: boolean } | null => {
    if (!previous) return null;
    const pct = ((current - previous) / Math.abs(previous)) * 100;
    return { value: `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`, positive: pct >= 0 };
};

/** Format month key (2026-03) to short label (Mar) */
const fmtMonth = (key: string) => {
    const [y, m] = key.split('-');
    const date = new Date(Number(y), Number(m) - 1);
    return date.toLocaleString('en', { month: 'short' });
};

/* ── types ──────────────────────────────────────────────── */

interface DashboardData {
    pending_approvals: number;
    active_work_orders: number;
    open_requisitions: number;
    low_stock_alerts: number;
    revenue_mtd: number;
    revenue_prev: number;
    expenses_mtd: number;
    expenses_prev: number;
    net_income_mtd: number;
    monthly_trend: { month: string; revenue: number; expenses: number; net: number }[];
    ar_outstanding: number;
    ar_overdue_count: number;
    ar_overdue_amount: number;
    ap_outstanding: number;
    ap_count: number;
    cash_in_mtd: number;
    cash_out_mtd: number;
    net_cash_flow: number;
    procurement_mtd: number;
    budget_allocated: number;
    budget_consumed: number;
    budget_reserved: number;
    budget_available: number;
    budget_utilization: number;
    active_employees: number;
    total_employees: number;
    // Inventory
    total_items: number;
    total_stock_qty: number;
    inventory_value: number;
    stock_movements_in: number;
    stock_movements_out: number;
    // Fixed Assets
    fixed_assets_count: number;
    fixed_assets_value: number;
    fixed_assets_nbv: number;
    recent_transactions: {
        id: number;
        reference: string;
        date: string;
        description: string;
        source: string;
        amount: number;
    }[];
}

/* ── styles ─────────────────────────────────────────────── */

const card = {
    background: '#fff',
    borderRadius: '16px',
    border: '1px solid #e8ecf1',
    padding: '24px',
    transition: 'box-shadow 0.2s',
} as const;

const sectionTitle = {
    fontSize: '13px',
    fontWeight: 600 as const,
    color: '#94a3b8',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
    marginBottom: '6px',
};

/* ── chart palette ──────────────────────────────────────── */
const COLORS = {
    primary: '#191e6a',
    revenue: '#22c55e',
    expense: '#ef4444',
    net: '#3b82f6',
    accent: '#f59e0b',
    purple: '#8b5cf6',
    teal: '#0d9488',
    slate: '#64748b',
};

const PIE_COLORS = [COLORS.revenue, COLORS.expense, COLORS.accent, COLORS.purple];

/* ── custom tooltip ─────────────────────────────────────── */
const ChartTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    return (
        <div style={{
            background: '#1e293b', borderRadius: '10px', padding: '12px 16px',
            boxShadow: '0 8px 24px rgba(0,0,0,0.2)', border: 'none',
        }}>
            <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>{label}</div>
            {payload.map((p: any) => (
                <div key={p.dataKey} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: p.color }} />
                    <span style={{ fontSize: '13px', color: '#e2e8f0', fontWeight: 500 }}>
                        {p.name}: {fmtCurrency(p.value)}
                    </span>
                </div>
            ))}
        </div>
    );
};

/* ── reusable mini-KPI card ──────────────────────────────── */

const MiniKPI = ({ icon: Icon, label, value, color, onClick }: {
    icon: any; label: string; value?: number; color: string; onClick: () => void;
}) => (
    <div style={{ ...card, cursor: 'pointer' }} onClick={onClick}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div style={{
                width: '44px', height: '44px', borderRadius: '12px',
                background: hexRgba(color, 0.08),
                display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
                <Icon size={22} style={{ color }} />
            </div>
            <div style={{ flex: 1 }}>
                <div style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 500 }}>{label}</div>
                <div style={{ fontSize: '24px', fontWeight: 700, color: '#1e293b' }}>
                    {value ?? '—'}
                </div>
            </div>
            <ArrowRight size={16} style={{ color: '#cbd5e1' }} />
        </div>
    </div>
);

/* ── component ──────────────────────────────────────────── */

const Dashboard = () => {
    const navigate = useNavigate();
    const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);

    // ── Back-button interception ─────────────────────────────
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
        if (userRaw) user = JSON.parse(userRaw);
    } catch {
        logger.error('Failed to parse user data from localStorage');
    }

    const organizationName =
        localStorage.getItem('activeTenant') ||
        (() => { try { const i = localStorage.getItem('tenantInfo'); return i ? JSON.parse(i).name : null; } catch { return null; } })() ||
        'My Organization';

    const { data: d, isLoading } = useQuery<DashboardData>({
        queryKey: ['dashboard-stats'],
        queryFn: async () => (await apiClient.get('/core/dashboard-stats/')).data,
        staleTime: 60_000,
    });

    // Module visibility — only show analytics for enabled modules
    const { data: tenantModules } = useTenantModules();
    const enabledMap = tenantModules?.enabled_modules ?? {};
    const hasModuleData = Object.keys(enabledMap).length > 0;
    /** Returns true if module is enabled or no config exists (show all) */
    const mod = (key: string) => !hasModuleData || enabledMap[key] === true;

    // Memoize chart data to avoid re-creating on every render
    const trendData = useMemo(() =>
        (d?.monthly_trend ?? []).map(t => ({
            ...t,
            name: fmtMonth(t.month),
        })),
        [d?.monthly_trend],
    );

    const cashFlowPie = useMemo(() => {
        if (!d) return [];
        return [
            { name: 'Cash In', value: d.cash_in_mtd },
            { name: 'Cash Out', value: d.cash_out_mtd },
        ].filter(x => x.value > 0);
    }, [d]);

    const budgetPie = useMemo(() => {
        if (!d) return [];
        return [
            { name: 'Consumed', value: d.budget_consumed, color: COLORS.expense },
            { name: 'Reserved', value: d.budget_reserved, color: COLORS.accent },
            { name: 'Available', value: d.budget_available, color: COLORS.revenue },
        ].filter(x => x.value > 0);
    }, [d]);

    const revenueChange = d ? pctChange(d.revenue_mtd, d.revenue_prev) : null;
    const expenseChange = d ? pctChange(d.expenses_mtd, d.expenses_prev) : null;

    const quickActions = [
        { label: 'New Journal Entry', icon: FileText, path: '/accounting/new' },
        { label: 'Create Requisition', icon: ShoppingCart, path: '/procurement/requisitions/new' },
        { label: 'Approval Inbox', icon: CheckCircle, path: '/approvals' },
        { label: 'View Reports', icon: TrendingUp, path: '/accounting/reports' },
    ];

    return (
        <div style={{ display: 'flex', background: '#f1f5f9', minHeight: '100vh' }}>
            {/* ── Leave confirmation modal ──────────────────── */}
            {showLeaveConfirm && (
                <div style={{
                    position: 'fixed', inset: 0,
                    background: 'rgba(15,23,42,0.55)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    zIndex: 9999, backdropFilter: 'blur(2px)',
                }}>
                    <div style={{
                        background: 'white', borderRadius: '20px',
                        padding: '36px 32px', maxWidth: '400px', width: '90%',
                        boxShadow: '0 24px 64px rgba(0,0,0,0.25)', textAlign: 'center',
                    }}>
                        <div style={{
                            width: '64px', height: '64px', borderRadius: '50%',
                            background: '#fef2f2', display: 'flex',
                            alignItems: 'center', justifyContent: 'center',
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
                            <button onClick={() => setShowLeaveConfirm(false)} style={{
                                flex: 1, padding: '13px', background: '#f8fafc',
                                border: '1.5px solid #e2e8f0', borderRadius: '10px',
                                fontSize: '14px', fontWeight: 600, color: '#475569',
                                cursor: 'pointer', fontFamily: 'inherit',
                            }}>Stay Here</button>
                            <button onClick={handleConfirmLeave} style={{
                                flex: 1, padding: '13px',
                                background: 'linear-gradient(135deg, #ef4444, #dc2626)',
                                border: 'none', borderRadius: '10px',
                                fontSize: '14px', fontWeight: 600, color: 'white',
                                cursor: 'pointer', fontFamily: 'inherit',
                                boxShadow: '0 4px 12px rgba(239,68,68,0.35)',
                            }}>Sign Out</button>
                        </div>
                    </div>
                </div>
            )}

            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '0' }}>
                {/* ── Welcome Banner ─────────────────────────── */}
                <div style={{
                    background: 'linear-gradient(135deg, #191e6a 0%, #2e3898 60%, #4338ca 100%)',
                    padding: '28px 40px', color: 'white',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                    <div>
                        <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'white', marginBottom: '4px' }}>
                            Welcome back, {user.name}
                        </h1>
                        <p style={{ fontSize: '14px', color: 'rgba(255,255,255,0.65)', margin: 0 }}>
                            Here's your operations overview for today.
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                        {quickActions.map((a) => (
                            <button key={a.label} onClick={() => navigate(a.path)} style={{
                                display: 'flex', alignItems: 'center', gap: '6px',
                                padding: '8px 14px', borderRadius: '8px',
                                background: 'rgba(255,255,255,0.12)',
                                border: '1px solid rgba(255,255,255,0.2)',
                                color: 'white', cursor: 'pointer', fontSize: '12px',
                                fontWeight: 500, fontFamily: 'inherit', transition: 'all 0.2s',
                            }}
                            onMouseOver={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.22)'; }}
                            onMouseOut={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.12)'; }}
                            >
                                <a.icon size={13} /> {a.label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* ── Content Area ──────────────────────────── */}
                <div style={{ padding: '24px 32px', maxWidth: '1400px' }}>

                    {/* ── Row 1: Financial KPI Cards ───────── */}
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(4, 1fr)',
                        gap: '16px',
                        marginBottom: '24px',
                    }}>
                        {/* Revenue MTD */}
                        <div style={card}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                <div style={sectionTitle}>Revenue MTD</div>
                                <div style={{
                                    width: '36px', height: '36px', borderRadius: '10px',
                                    background: hexRgba(COLORS.revenue, 0.1),
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                }}>
                                    <TrendingUp size={18} style={{ color: COLORS.revenue }} />
                                </div>
                            </div>
                            <div style={{ fontSize: '26px', fontWeight: 700, color: '#1e293b', margin: '8px 0 4px' }}>
                                {isLoading ? '—' : fmtCurrency(d?.revenue_mtd ?? 0)}
                            </div>
                            {revenueChange && (
                                <div style={{
                                    fontSize: '12px', fontWeight: 600,
                                    color: revenueChange.positive ? COLORS.revenue : COLORS.expense,
                                    display: 'flex', alignItems: 'center', gap: '3px',
                                }}>
                                    {revenueChange.positive
                                        ? <ArrowUpRight size={13} />
                                        : <ArrowDownRight size={13} />}
                                    {revenueChange.value} vs last month
                                </div>
                            )}
                        </div>

                        {/* Expenses MTD */}
                        <div style={card}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                <div style={sectionTitle}>Expenses MTD</div>
                                <div style={{
                                    width: '36px', height: '36px', borderRadius: '10px',
                                    background: hexRgba(COLORS.expense, 0.1),
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                }}>
                                    <CreditCard size={18} style={{ color: COLORS.expense }} />
                                </div>
                            </div>
                            <div style={{ fontSize: '26px', fontWeight: 700, color: '#1e293b', margin: '8px 0 4px' }}>
                                {isLoading ? '—' : fmtCurrency(d?.expenses_mtd ?? 0)}
                            </div>
                            {expenseChange && (
                                <div style={{
                                    fontSize: '12px', fontWeight: 600,
                                    color: expenseChange.positive ? COLORS.expense : COLORS.revenue,
                                    display: 'flex', alignItems: 'center', gap: '3px',
                                }}>
                                    {expenseChange.positive
                                        ? <ArrowUpRight size={13} />
                                        : <ArrowDownRight size={13} />}
                                    {expenseChange.value} vs last month
                                </div>
                            )}
                        </div>

                        {/* Net Income MTD */}
                        <div style={card}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                <div style={sectionTitle}>Net Income MTD</div>
                                <div style={{
                                    width: '36px', height: '36px', borderRadius: '10px',
                                    background: hexRgba(COLORS.net, 0.1),
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                }}>
                                    <DollarSign size={18} style={{ color: COLORS.net }} />
                                </div>
                            </div>
                            <div style={{
                                fontSize: '26px', fontWeight: 700, margin: '8px 0 4px',
                                color: (d?.net_income_mtd ?? 0) >= 0 ? COLORS.revenue : COLORS.expense,
                            }}>
                                {isLoading ? '—' : fmtCurrency(d?.net_income_mtd ?? 0)}
                            </div>
                            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                                Revenue − Expenses
                            </div>
                        </div>

                        {/* Net Cash Flow */}
                        <div style={card}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                <div style={sectionTitle}>Cash Flow MTD</div>
                                <div style={{
                                    width: '36px', height: '36px', borderRadius: '10px',
                                    background: hexRgba(COLORS.teal, 0.1),
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                }}>
                                    <Banknote size={18} style={{ color: COLORS.teal }} />
                                </div>
                            </div>
                            <div style={{
                                fontSize: '26px', fontWeight: 700, margin: '8px 0 4px',
                                color: (d?.net_cash_flow ?? 0) >= 0 ? COLORS.revenue : COLORS.expense,
                            }}>
                                {isLoading ? '—' : fmtCurrency(d?.net_cash_flow ?? 0)}
                            </div>
                            <div style={{ fontSize: '12px', color: '#94a3b8', display: 'flex', gap: '8px' }}>
                                <span style={{ color: COLORS.revenue }}>↑ {fmtCurrency(d?.cash_in_mtd ?? 0)}</span>
                                <span style={{ color: COLORS.expense }}>↓ {fmtCurrency(d?.cash_out_mtd ?? 0)}</span>
                            </div>
                        </div>
                    </div>

                    {/* ── Row 2: Revenue/Expense Trend + Operations ── */}
                    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '16px', marginBottom: '24px' }}>
                        {/* Revenue & Expense Trend Chart */}
                        <div style={card}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                                <div>
                                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>Revenue vs Expenses</div>
                                    <div style={{ fontSize: '13px', color: '#94a3b8' }}>Last 6 months trend</div>
                                </div>
                                <div style={{ display: 'flex', gap: '16px' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#64748b' }}>
                                        <div style={{ width: 10, height: 10, borderRadius: '50%', background: COLORS.revenue }} />Revenue
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#64748b' }}>
                                        <div style={{ width: 10, height: 10, borderRadius: '50%', background: COLORS.expense }} />Expenses
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#64748b' }}>
                                        <div style={{ width: 10, height: 10, borderRadius: '50%', background: COLORS.net }} />Net
                                    </div>
                                </div>
                            </div>
                            <div style={{ width: '100%', height: 260 }}>
                                <ResponsiveContainer>
                                    <AreaChart data={trendData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                                        <defs>
                                            <linearGradient id="gRev" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor={COLORS.revenue} stopOpacity={0.15} />
                                                <stop offset="95%" stopColor={COLORS.revenue} stopOpacity={0} />
                                            </linearGradient>
                                            <linearGradient id="gExp" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor={COLORS.expense} stopOpacity={0.15} />
                                                <stop offset="95%" stopColor={COLORS.expense} stopOpacity={0} />
                                            </linearGradient>
                                        </defs>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                                        <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                                        <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false}
                                            tickFormatter={(v: number) => fmtCurrency(v)} width={70} />
                                        <Tooltip content={<ChartTooltip />} />
                                        <Area type="monotone" dataKey="revenue" name="Revenue"
                                            stroke={COLORS.revenue} strokeWidth={2.5} fill="url(#gRev)" />
                                        <Area type="monotone" dataKey="expenses" name="Expenses"
                                            stroke={COLORS.expense} strokeWidth={2.5} fill="url(#gExp)" />
                                        <Area type="monotone" dataKey="net" name="Net Income"
                                            stroke={COLORS.net} strokeWidth={2} fill="none" strokeDasharray="5 3" />
                                    </AreaChart>
                                </ResponsiveContainer>
                            </div>
                        </div>

                        {/* Operations Summary — module-aware */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                            {/* Pending Approvals (always visible) */}
                            <MiniKPI icon={CheckCircle} label="Pending Approvals" value={d?.pending_approvals}
                                color={COLORS.primary} onClick={() => navigate('/approvals')} />
                            {mod('procurement') && (
                                <MiniKPI icon={ShoppingCart} label="Open Requisitions" value={d?.open_requisitions}
                                    color={COLORS.teal} onClick={() => navigate('/procurement/requisitions')} />
                            )}
                            {mod('inventory') && (
                                <MiniKPI icon={AlertTriangle} label="Low Stock Alerts" value={d?.low_stock_alerts}
                                    color={COLORS.expense} onClick={() => navigate('/inventory/dashboard')} />
                            )}
                        </div>
                    </div>

                    {/* ── Row 3: Module-aware analytics grid ──── */}
                    {(() => {
                        // Build a dynamic list of analytics cards based on enabled modules
                        const cards: JSX.Element[] = [];

                        // Accounting: AR/AP (always shown — core module)
                        if (mod('accounting')) {
                            cards.push(
                                <div key="ar-ap" style={card}>
                                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b', marginBottom: '20px' }}>
                                        Receivables & Payables
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                                        <div style={{ background: '#f0fdf4', borderRadius: '12px', padding: '16px', border: '1px solid #dcfce7' }}>
                                            <div style={{ fontSize: '12px', fontWeight: 600, color: COLORS.revenue, marginBottom: '6px' }}>
                                                <Receipt size={13} style={{ marginRight: '4px', verticalAlign: '-2px' }} />
                                                ACCOUNTS RECEIVABLE
                                            </div>
                                            <div style={{ fontSize: '22px', fontWeight: 700, color: '#1e293b' }}>
                                                {fmtCurrency(d?.ar_outstanding ?? 0)}
                                            </div>
                                            {(d?.ar_overdue_count ?? 0) > 0 && (
                                                <div style={{ fontSize: '12px', color: COLORS.expense, marginTop: '4px', fontWeight: 500 }}>
                                                    ⚠ {d?.ar_overdue_count} overdue ({fmtCurrency(d?.ar_overdue_amount ?? 0)})
                                                </div>
                                            )}
                                        </div>
                                        <div style={{ background: '#fef2f2', borderRadius: '12px', padding: '16px', border: '1px solid #fecaca' }}>
                                            <div style={{ fontSize: '12px', fontWeight: 600, color: COLORS.expense, marginBottom: '6px' }}>
                                                <Wallet size={13} style={{ marginRight: '4px', verticalAlign: '-2px' }} />
                                                ACCOUNTS PAYABLE
                                            </div>
                                            <div style={{ fontSize: '22px', fontWeight: 700, color: '#1e293b' }}>
                                                {fmtCurrency(d?.ap_outstanding ?? 0)}
                                            </div>
                                            <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px' }}>
                                                {d?.ap_count ?? 0} outstanding invoices
                                            </div>
                                        </div>
                                        {/* Fixed Assets */}
                                        <div style={{ background: '#f8fafc', borderRadius: '12px', padding: '16px', border: '1px solid #e2e8f0' }}>
                                            <div style={{ fontSize: '12px', fontWeight: 600, color: COLORS.slate, marginBottom: '6px' }}>
                                                <Landmark size={13} style={{ marginRight: '4px', verticalAlign: '-2px' }} />
                                                FIXED ASSETS
                                            </div>
                                            <div style={{ fontSize: '22px', fontWeight: 700, color: '#1e293b' }}>
                                                {d?.fixed_assets_count ?? 0}
                                                <span style={{ fontSize: '13px', color: '#94a3b8', fontWeight: 400 }}> assets</span>
                                            </div>
                                            <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '2px' }}>
                                                NBV: {fmtCurrency(d?.fixed_assets_nbv ?? 0)}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            );
                        }

                        // Budget Utilization
                        cards.push(
                            <div key="budget" style={card}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>Budget Utilization</div>
                                    <div style={{
                                        fontSize: '20px', fontWeight: 700,
                                        color: (d?.budget_utilization ?? 0) > 90 ? COLORS.expense
                                             : (d?.budget_utilization ?? 0) > 70 ? COLORS.accent
                                             : COLORS.revenue,
                                    }}>
                                        {d?.budget_utilization ?? 0}%
                                    </div>
                                </div>
                                <div style={{ height: '10px', background: '#f1f5f9', borderRadius: '5px', overflow: 'hidden', marginBottom: '16px' }}>
                                    <div style={{
                                        height: '100%', borderRadius: '5px',
                                        width: `${Math.min(d?.budget_utilization ?? 0, 100)}%`,
                                        background: (d?.budget_utilization ?? 0) > 90
                                            ? `linear-gradient(90deg, ${COLORS.accent}, ${COLORS.expense})`
                                            : `linear-gradient(90deg, ${COLORS.primary}, ${COLORS.net})`,
                                        transition: 'width 0.6s ease',
                                    }} />
                                </div>
                                {budgetPie.length > 0 ? (
                                    <div style={{ width: '100%', height: 160 }}>
                                        <ResponsiveContainer>
                                            <PieChart>
                                                <Pie data={budgetPie} cx="50%" cy="50%"
                                                    innerRadius={40} outerRadius={65}
                                                    paddingAngle={3} dataKey="value">
                                                    {budgetPie.map((entry, i) => (
                                                        <Cell key={i} fill={entry.color} />
                                                    ))}
                                                </Pie>
                                                <Legend formatter={(value: string) => (
                                                    <span style={{ fontSize: '12px', color: '#64748b' }}>{value}</span>
                                                )} />
                                                <Tooltip formatter={(v: number) => fmtCurrency(v)} />
                                            </PieChart>
                                        </ResponsiveContainer>
                                    </div>
                                ) : (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                        {[
                                            { label: 'Allocated', val: d?.budget_allocated ?? 0, color: '#1e293b' },
                                            { label: 'Consumed', val: d?.budget_consumed ?? 0, color: COLORS.expense },
                                            { label: 'Available', val: d?.budget_available ?? 0, color: COLORS.revenue },
                                        ].map(r => (
                                            <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                                                <span style={{ color: '#64748b' }}>{r.label}</span>
                                                <span style={{ fontWeight: 600, color: r.color }}>{fmtCurrency(r.val)}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        );

                        // Procurement
                        if (mod('procurement')) {
                            cards.push(
                                <div key="procurement" style={card}>
                                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b', marginBottom: '20px' }}>Procurement</div>
                                    <div style={{ background: '#f0fdfa', borderRadius: '12px', padding: '16px', border: '1px solid #ccfbf1' }}>
                                        <div style={{ fontSize: '12px', fontWeight: 600, color: COLORS.teal, marginBottom: '6px' }}>
                                            <ShoppingCart size={13} style={{ marginRight: '4px', verticalAlign: '-2px' }} /> SPEND MTD
                                        </div>
                                        <div style={{ fontSize: '28px', fontWeight: 700, color: '#1e293b' }}>
                                            {fmtCurrency(d?.procurement_mtd ?? 0)}
                                        </div>
                                        <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px' }}>
                                            {d?.open_requisitions ?? 0} open requisitions
                                        </div>
                                    </div>
                                </div>
                            );
                        }

                        // Inventory
                        if (mod('inventory')) {
                            cards.push(
                                <div key="inventory" style={card}>
                                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b', marginBottom: '20px' }}>Inventory</div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                        <div style={{ background: '#faf5ff', borderRadius: '12px', padding: '16px', border: '1px solid #e9d5ff' }}>
                                            <div style={{ fontSize: '12px', fontWeight: 600, color: COLORS.purple, marginBottom: '6px' }}>
                                                <Package size={13} style={{ marginRight: '4px', verticalAlign: '-2px' }} /> STOCK VALUE
                                            </div>
                                            <div style={{ fontSize: '22px', fontWeight: 700, color: '#1e293b' }}>
                                                {fmtCurrency(d?.inventory_value ?? 0)}
                                            </div>
                                            <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '2px' }}>
                                                {d?.total_items ?? 0} active items
                                            </div>
                                        </div>
                                        <div style={{ display: 'flex', gap: '8px' }}>
                                            <div style={{
                                                flex: 1, background: '#f0fdf4', borderRadius: '10px', padding: '12px',
                                                border: '1px solid #dcfce7', textAlign: 'center',
                                            }}>
                                                <div style={{ fontSize: '20px', fontWeight: 700, color: COLORS.revenue }}>
                                                    {d?.stock_movements_in ?? 0}
                                                </div>
                                                <div style={{ fontSize: '11px', color: '#64748b' }}>Stock In</div>
                                            </div>
                                            <div style={{
                                                flex: 1, background: '#fef2f2', borderRadius: '10px', padding: '12px',
                                                border: '1px solid #fecaca', textAlign: 'center',
                                            }}>
                                                <div style={{ fontSize: '20px', fontWeight: 700, color: COLORS.expense }}>
                                                    {d?.stock_movements_out ?? 0}
                                                </div>
                                                <div style={{ fontSize: '11px', color: '#64748b' }}>Stock Out</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            );
                        }

                        // HRM
                        if (mod('hrm')) {
                            cards.push(
                                <div key="hrm" style={card}>
                                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b', marginBottom: '20px' }}>
                                        Human Resources
                                    </div>
                                    <div style={{ background: '#f5f3ff', borderRadius: '12px', padding: '16px', border: '1px solid #ede9fe' }}>
                                        <div style={{ fontSize: '12px', fontWeight: 600, color: COLORS.purple, marginBottom: '6px' }}>
                                            <Users size={13} style={{ marginRight: '4px', verticalAlign: '-2px' }} /> HEADCOUNT
                                        </div>
                                        <div style={{ fontSize: '28px', fontWeight: 700, color: '#1e293b' }}>
                                            {d?.active_employees ?? 0}
                                            <span style={{ fontSize: '14px', color: '#94a3b8', fontWeight: 400 }}>
                                                {' '}/ {d?.total_employees ?? 0}
                                            </span>
                                        </div>
                                        <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '2px' }}>
                                            Active employees
                                        </div>
                                    </div>
                                </div>
                            );
                        }

                        // Render the cards in a responsive grid
                        return (
                            <div style={{
                                display: 'grid',
                                gridTemplateColumns: `repeat(${Math.min(cards.length, 3)}, 1fr)`,
                                gap: '16px',
                                marginBottom: '24px',
                            }}>
                                {cards}
                            </div>
                        );
                    })()}

                    {/* ── Row 4: Recent Transactions (accounting) ── */}
                    {mod('accounting') && <div style={card}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                            <div>
                                <div style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>Recent Transactions</div>
                                <div style={{ fontSize: '13px', color: '#94a3b8' }}>Latest posted journal entries</div>
                            </div>
                            <button onClick={() => navigate('/accounting/journals')} style={{
                                background: 'none', border: '1px solid #e2e8f0',
                                borderRadius: '8px', padding: '6px 14px',
                                fontSize: '13px', fontWeight: 600, color: COLORS.primary,
                                cursor: 'pointer', fontFamily: 'inherit',
                            }}>View All</button>
                        </div>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                                <thead>
                                    <tr style={{ borderBottom: '2px solid #f1f5f9' }}>
                                        {['Reference', 'Date', 'Description', 'Source', 'Amount'].map((h) => (
                                            <th key={h} style={{
                                                padding: '10px 12px', textAlign: h === 'Amount' ? 'right' : 'left',
                                                fontSize: '11px', fontWeight: 600, color: '#94a3b8',
                                                textTransform: 'uppercase', letterSpacing: '0.5px',
                                            }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {(d?.recent_transactions ?? []).length === 0 ? (
                                        <tr>
                                            <td colSpan={5} style={{ padding: '32px', textAlign: 'center', color: '#94a3b8' }}>
                                                <Activity size={24} style={{ marginBottom: '8px', opacity: 0.4 }} /><br />
                                                No posted transactions yet
                                            </td>
                                        </tr>
                                    ) : (
                                        (d?.recent_transactions ?? []).map((tx) => (
                                            <tr key={tx.id} style={{
                                                borderBottom: '1px solid #f8fafc',
                                                transition: 'background 0.15s',
                                            }}
                                            onMouseOver={(e) => { e.currentTarget.style.background = '#fafbfc'; }}
                                            onMouseOut={(e) => { e.currentTarget.style.background = 'transparent'; }}
                                            >
                                                <td style={{ padding: '12px', fontWeight: 600, color: COLORS.primary }}>
                                                    {tx.reference}
                                                </td>
                                                <td style={{ padding: '12px', color: '#64748b' }}>
                                                    {tx.date ? new Date(tx.date).toLocaleDateString('en-GB', {
                                                        day: 'numeric', month: 'short', year: 'numeric',
                                                    }) : '—'}
                                                </td>
                                                <td style={{
                                                    padding: '12px', color: '#475569',
                                                    maxWidth: '280px', overflow: 'hidden',
                                                    textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                                }}>
                                                    {tx.description || '—'}
                                                </td>
                                                <td style={{ padding: '12px' }}>
                                                    {tx.source ? (
                                                        <span style={{
                                                            fontSize: '11px', fontWeight: 600,
                                                            color: COLORS.primary,
                                                            background: hexRgba(COLORS.primary, 0.07),
                                                            padding: '3px 10px', borderRadius: '6px',
                                                            textTransform: 'capitalize',
                                                        }}>{tx.source}</span>
                                                    ) : (
                                                        <span style={{ color: '#cbd5e1' }}>—</span>
                                                    )}
                                                </td>
                                                <td style={{
                                                    padding: '12px', textAlign: 'right',
                                                    fontWeight: 600, color: '#1e293b', fontVariantNumeric: 'tabular-nums',
                                                }}>
                                                    {fmtFull(tx.amount)}
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>}
                </div>
            </main>
        </div>
    );
};

export default Dashboard;
