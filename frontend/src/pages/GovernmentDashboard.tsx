/**
 * Government IFMIS Dashboard — Quot PSE
 *
 * Executive dashboard for state government financial management.
 * Shows: TSA cash position, revenue performance, budget execution,
 * and pending payment vouchers.
 *
 * Data sources:
 *   /accounting/ipsas/tsa-cash-position/
 *   /accounting/ipsas/financial-performance/
 *   /accounting/revenue-collections/summary/
 *   /budget/execution-report/
 *   /core/dashboard-stats/
 */
import { useMemo } from 'react';
import Sidebar from '../components/Sidebar';
import {
    Landmark, TrendingUp, TrendingDown, Banknote, Receipt, FileText,
    ArrowRight, BarChart3, ShoppingCart, CheckCircle, Users,
    ArrowUpRight, ArrowDownRight, PieChart as PieChartIcon,
    Wallet, CreditCard, Activity,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';
import {
    useTSACashPosition,
    useRevenueCollectionSummary,
    useBudgetExecution,
    useFinancialPerformance,
} from '../hooks/useGovDashboard';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts';

/* ── Colors: Nigerian government palette ────────────────── */
const GOV = {
    green:     '#008751',
    greenDk:   '#005a35',
    greenLt:   '#00b368',
    gold:      '#C89B3C',
    blue:      '#1e4d8c',
    red:       '#c0392b',
    grayDk:    '#1a2332',
    grayLt:    '#f0f4f8',
    white:     '#ffffff',
};

const CHART_COLORS = [GOV.green, GOV.gold, GOV.blue, GOV.red, '#8b5cf6', '#0d9488'];

/* ── Formatters ─────────────────────────────────────────── */
const fmtNGN = (val: number): string => {
    const abs = Math.abs(val);
    const sign = val < 0 ? '-' : '';
    if (abs >= 1_000_000_000) return `${sign}₦${(abs / 1_000_000_000).toFixed(2)}B`;
    if (abs >= 1_000_000) return `${sign}₦${(abs / 1_000_000).toFixed(1)}M`;
    if (abs >= 1_000) return `${sign}₦${(abs / 1_000).toFixed(0)}K`;
    return `${sign}₦${abs.toLocaleString('en-NG')}`;
};

const fmtFull = (val: number) =>
    '₦' + val.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/* ── Styles ─────────────────────────────────────────────── */
const cardStyle: React.CSSProperties = {
    background: '#fff',
    borderRadius: '16px',
    border: '1px solid #e8ecf1',
    padding: '24px',
    transition: 'box-shadow 0.2s',
};

const kpiCard = (color: string): React.CSSProperties => ({
    ...cardStyle,
    borderLeft: `4px solid ${color}`,
    cursor: 'pointer',
});

/* ── Tooltip ────────────────────────────────────────────── */
const ChartTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    return (
        <div style={{
            background: GOV.grayDk, borderRadius: '10px', padding: '12px 16px',
            boxShadow: '0 8px 24px rgba(0,0,0,0.2)', border: 'none',
        }}>
            <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>{label}</div>
            {payload.map((p: any) => (
                <div key={p.dataKey} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: p.color }} />
                    <span style={{ fontSize: '13px', color: '#e2e8f0', fontWeight: 500 }}>
                        {p.name}: {fmtNGN(p.value)}
                    </span>
                </div>
            ))}
        </div>
    );
};

/* ── Main Component ─────────────────────────────────────── */

const GovernmentDashboard = () => {
    const navigate = useNavigate();

    // Data hooks
    const { data: tsa, isLoading: tsaLoading } = useTSACashPosition();
    const { data: revenue } = useRevenueCollectionSummary();
    const { data: budgetItems } = useBudgetExecution();
    const { data: performance } = useFinancialPerformance();

    // Legacy dashboard data (for counts)
    const { data: stats } = useQuery<any>({
        queryKey: ['dashboard-stats'],
        queryFn: async () => (await apiClient.get('/core/dashboard-stats/')).data,
        staleTime: 60_000,
    });

    // Compute budget execution totals
    const budgetTotals = useMemo(() => {
        if (!budgetItems?.length) return { approved: 0, expended: 0, available: 0, pct: 0 };
        const approved = budgetItems.reduce((s, i) => s + parseFloat(i.approved || '0'), 0);
        const expended = budgetItems.reduce((s, i) => s + parseFloat(i.expended || '0'), 0);
        const available = budgetItems.reduce((s, i) => s + parseFloat(i.available || '0'), 0);
        return {
            approved,
            expended,
            available,
            pct: approved > 0 ? (expended / approved * 100) : 0,
        };
    }, [budgetItems]);

    // Revenue by head for pie chart
    const revenuePie = useMemo(() => {
        if (!revenue?.by_revenue_head?.length) return [];
        return revenue.by_revenue_head.slice(0, 6).map((rh, i) => ({
            name: rh.revenue_head__name || 'Unknown',
            value: rh.total || 0,
            fill: CHART_COLORS[i % CHART_COLORS.length],
        }));
    }, [revenue]);

    // Budget execution bar chart (top 10 MDAs)
    const budgetBar = useMemo(() => {
        if (!budgetItems?.length) return [];
        return budgetItems.slice(0, 10).map(item => ({
            name: item.mda?.substring(0, 20) || 'MDA',
            Approved: parseFloat(item.approved || '0'),
            Expended: parseFloat(item.expended || '0'),
        }));
    }, [budgetItems]);

    // Quick actions — government-specific
    const quickActions = [
        { label: 'New Journal Entry', icon: FileText, path: '/accounting/new', color: GOV.blue },
        { label: 'Payment Vouchers', icon: Receipt, path: '/accounting/payment-vouchers', color: GOV.green },
        { label: 'Approval Inbox', icon: CheckCircle, path: '/approvals', color: GOV.gold },
        { label: 'Budget Execution', icon: BarChart3, path: '/budget/execution-report', color: GOV.red },
    ];

    const orgName =
        localStorage.getItem('activeTenant') ||
        (() => { try { const i = localStorage.getItem('tenantInfo'); return i ? JSON.parse(i).name : null; } catch { return null; } })() ||
        'State Government';

    return (
        <div style={{ background: GOV.grayLt, minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '32px', overflow: 'auto' }}>
                {/* ── Header ──────────────────────────────────── */}
                <div style={{ marginBottom: '32px' }}>
                    <div style={{ fontSize: '28px', fontWeight: 800, color: GOV.grayDk }}>
                        Government Financial Dashboard
                    </div>
                    <div style={{ fontSize: '14px', color: '#64748b', marginTop: '4px' }}>
                        {orgName} — IFMIS Executive Overview
                    </div>
                </div>

                {/* ── Row 1: KPI Cards ────────────────────────── */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px', marginBottom: '28px' }}>
                    {/* TSA Cash Position */}
                    <div style={kpiCard(GOV.green)} onClick={() => navigate('/accounting/tsa-accounts')}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                            <div style={{
                                width: 44, height: 44, borderRadius: '12px',
                                background: `${GOV.green}14`,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}>
                                <Landmark size={22} style={{ color: GOV.green }} />
                            </div>
                            <div style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase' }}>
                                TSA Cash Position
                            </div>
                        </div>
                        <div style={{ fontSize: '28px', fontWeight: 800, color: GOV.grayDk }}>
                            {tsaLoading ? '...' : fmtNGN(tsa?.total_balance ?? 0)}
                        </div>
                        <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                            {tsa?.account_count ?? 0} active accounts
                        </div>
                    </div>

                    {/* Revenue Collected */}
                    <div style={kpiCard(GOV.gold)} onClick={() => navigate('/accounting/revenue-collections')}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                            <div style={{
                                width: 44, height: 44, borderRadius: '12px',
                                background: `${GOV.gold}14`,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}>
                                <Banknote size={22} style={{ color: GOV.gold }} />
                            </div>
                            <div style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase' }}>
                                Revenue Collected (YTD)
                            </div>
                        </div>
                        <div style={{ fontSize: '28px', fontWeight: 800, color: GOV.grayDk }}>
                            {fmtNGN(revenue?.total_collected ?? 0)}
                        </div>
                        <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                            {revenue?.by_revenue_head?.length ?? 0} revenue heads
                        </div>
                    </div>

                    {/* Budget Execution */}
                    <div style={kpiCard(GOV.blue)} onClick={() => navigate('/budget/appropriations')}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                            <div style={{
                                width: 44, height: 44, borderRadius: '12px',
                                background: `${GOV.blue}14`,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}>
                                <BarChart3 size={22} style={{ color: GOV.blue }} />
                            </div>
                            <div style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase' }}>
                                Budget Execution
                            </div>
                        </div>
                        <div style={{ fontSize: '28px', fontWeight: 800, color: GOV.grayDk }}>
                            {budgetTotals.pct.toFixed(1)}%
                        </div>
                        <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                            {fmtNGN(budgetTotals.expended)} of {fmtNGN(budgetTotals.approved)}
                        </div>
                    </div>

                    {/* Pending Approvals */}
                    <div style={kpiCard(GOV.red)} onClick={() => navigate('/approvals')}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                            <div style={{
                                width: 44, height: 44, borderRadius: '12px',
                                background: `${GOV.red}14`,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}>
                                <CheckCircle size={22} style={{ color: GOV.red }} />
                            </div>
                            <div style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase' }}>
                                Pending Approvals
                            </div>
                        </div>
                        <div style={{ fontSize: '28px', fontWeight: 800, color: GOV.grayDk }}>
                            {stats?.pending_approvals ?? 0}
                        </div>
                        <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                            PVs, POs, Journals awaiting action
                        </div>
                    </div>
                </div>

                {/* ── Row 2: Charts ────────────────────────────── */}
                <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: '20px', marginBottom: '28px' }}>
                    {/* Budget Execution by MDA (Bar Chart) */}
                    <div style={cardStyle}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                            <div>
                                <div style={{ fontSize: '16px', fontWeight: 700, color: GOV.grayDk }}>
                                    Budget Execution by MDA
                                </div>
                                <div style={{ fontSize: '13px', color: '#94a3b8' }}>
                                    Appropriation vs Actual Expenditure
                                </div>
                            </div>
                        </div>
                        <div style={{ width: '100%', height: 280 }}>
                            {budgetBar.length > 0 ? (
                                <ResponsiveContainer>
                                    <BarChart data={budgetBar} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                                        <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#94a3b8' }}
                                            angle={-30} textAnchor="end" height={60} />
                                        <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false}
                                            tickFormatter={fmtNGN} width={70} />
                                        <Tooltip content={<ChartTooltip />} />
                                        <Bar dataKey="Approved" name="Approved" fill={GOV.blue} radius={[4, 4, 0, 0]} />
                                        <Bar dataKey="Expended" name="Expended" fill={GOV.green} radius={[4, 4, 0, 0]} />
                                    </BarChart>
                                </ResponsiveContainer>
                            ) : (
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#94a3b8' }}>
                                    No active appropriations. Enact budget to see execution data.
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Revenue by Source (Donut) */}
                    <div style={cardStyle}>
                        <div style={{ marginBottom: '20px' }}>
                            <div style={{ fontSize: '16px', fontWeight: 700, color: GOV.grayDk }}>
                                Revenue by Source
                            </div>
                            <div style={{ fontSize: '13px', color: '#94a3b8' }}>IGR Collection Breakdown</div>
                        </div>
                        <div style={{ width: '100%', height: 280 }}>
                            {revenuePie.length > 0 ? (
                                <ResponsiveContainer>
                                    <PieChart>
                                        <Pie data={revenuePie} cx="50%" cy="45%" innerRadius={55} outerRadius={85}
                                            paddingAngle={3} dataKey="value">
                                            {revenuePie.map((entry, i) => (
                                                <Cell key={i} fill={entry.fill} />
                                            ))}
                                        </Pie>
                                        <Tooltip formatter={(val: number) => fmtNGN(val)} />
                                        <Legend wrapperStyle={{ fontSize: '11px' }} />
                                    </PieChart>
                                </ResponsiveContainer>
                            ) : (
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#94a3b8' }}>
                                    No revenue collections posted yet.
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* ── Row 3: Financial Summary + Quick Actions ── */}
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px', marginBottom: '28px' }}>
                    {/* Financial Performance Summary */}
                    <div style={cardStyle}>
                        <div style={{ fontSize: '16px', fontWeight: 700, color: GOV.grayDk, marginBottom: '20px' }}>
                            Financial Performance (IPSAS)
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
                            <div style={{
                                background: '#f0fdf4', borderRadius: '12px', padding: '20px',
                                border: '1px solid #dcfce7',
                            }}>
                                <div style={{ fontSize: '12px', fontWeight: 600, color: GOV.green, marginBottom: '8px' }}>
                                    <TrendingUp size={13} style={{ marginRight: '4px', verticalAlign: '-2px' }} />
                                    TOTAL REVENUE
                                </div>
                                <div style={{ fontSize: '24px', fontWeight: 800, color: GOV.grayDk }}>
                                    {fmtNGN(performance?.revenue?.total ?? 0)}
                                </div>
                            </div>
                            <div style={{
                                background: '#fef2f2', borderRadius: '12px', padding: '20px',
                                border: '1px solid #fecaca',
                            }}>
                                <div style={{ fontSize: '12px', fontWeight: 600, color: GOV.red, marginBottom: '8px' }}>
                                    <TrendingDown size={13} style={{ marginRight: '4px', verticalAlign: '-2px' }} />
                                    TOTAL EXPENDITURE
                                </div>
                                <div style={{ fontSize: '24px', fontWeight: 800, color: GOV.grayDk }}>
                                    {fmtNGN(performance?.expenditure?.total ?? 0)}
                                </div>
                            </div>
                            <div style={{
                                background: performance?.surplus_deficit && performance.surplus_deficit >= 0
                                    ? '#f0fdf4' : '#fef2f2',
                                borderRadius: '12px', padding: '20px',
                                border: `1px solid ${performance?.surplus_deficit && performance.surplus_deficit >= 0 ? '#dcfce7' : '#fecaca'}`,
                            }}>
                                <div style={{
                                    fontSize: '12px', fontWeight: 600, marginBottom: '8px',
                                    color: performance?.surplus_deficit && performance.surplus_deficit >= 0 ? GOV.green : GOV.red,
                                }}>
                                    <Activity size={13} style={{ marginRight: '4px', verticalAlign: '-2px' }} />
                                    SURPLUS / (DEFICIT)
                                </div>
                                <div style={{ fontSize: '24px', fontWeight: 800, color: GOV.grayDk }}>
                                    {fmtNGN(performance?.surplus_deficit ?? 0)}
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Quick Actions */}
                    <div style={cardStyle}>
                        <div style={{ fontSize: '16px', fontWeight: 700, color: GOV.grayDk, marginBottom: '16px' }}>
                            Quick Actions
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                            {quickActions.map(action => (
                                <div
                                    key={action.path}
                                    onClick={() => navigate(action.path)}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: '12px',
                                        padding: '12px 16px', borderRadius: '10px',
                                        border: '1px solid #e8ecf1', cursor: 'pointer',
                                        transition: 'all 0.15s',
                                    }}
                                    onMouseEnter={e => {
                                        (e.currentTarget as HTMLDivElement).style.background = '#f8fafc';
                                        (e.currentTarget as HTMLDivElement).style.borderColor = action.color;
                                    }}
                                    onMouseLeave={e => {
                                        (e.currentTarget as HTMLDivElement).style.background = '';
                                        (e.currentTarget as HTMLDivElement).style.borderColor = '#e8ecf1';
                                    }}
                                >
                                    <action.icon size={18} style={{ color: action.color }} />
                                    <span style={{ flex: 1, fontSize: '14px', fontWeight: 500, color: GOV.grayDk }}>
                                        {action.label}
                                    </span>
                                    <ArrowRight size={14} style={{ color: '#cbd5e1' }} />
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* ── Row 4: TSA Account Breakdown ──────────── */}
                {tsa && tsa.by_account_type.length > 0 && (
                    <div style={cardStyle}>
                        <div style={{ fontSize: '16px', fontWeight: 700, color: GOV.grayDk, marginBottom: '16px' }}>
                            TSA Account Breakdown
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(tsa.by_account_type.length, 4)}, 1fr)`, gap: '16px' }}>
                            {tsa.by_account_type.map((acct, i) => (
                                <div key={acct.account_type} style={{
                                    padding: '16px', borderRadius: '10px',
                                    background: i === 0 ? `${GOV.green}08` : '#f8fafc',
                                    border: `1px solid ${i === 0 ? `${GOV.green}20` : '#e8ecf1'}`,
                                }}>
                                    <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', marginBottom: '6px' }}>
                                        {acct.account_type.replace(/_/g, ' ')}
                                    </div>
                                    <div style={{ fontSize: '20px', fontWeight: 700, color: GOV.grayDk }}>
                                        {fmtNGN(acct.balance)}
                                    </div>
                                    <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px' }}>
                                        {acct.count} account{acct.count !== 1 ? 's' : ''}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* ── Footer ──────────────────────────────────── */}
                <div style={{ textAlign: 'center', padding: '24px 0', color: '#94a3b8', fontSize: '12px' }}>
                    Quot PSE — Nigeria Government IFMIS | NCoA Compliant | IPSAS Accrual
                </div>
            </main>
        </div>
    );
};

export default GovernmentDashboard;
