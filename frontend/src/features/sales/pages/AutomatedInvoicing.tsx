import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSalesOrders, useSalesAnalytics } from '../hooks/useSales';
import SalesLayout from '../layout/SalesLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Receipt, FileCheck, Clock, CheckCircle, AlertTriangle, ArrowRight, TrendingUp } from 'lucide-react';
import { useCurrency } from '../../../context/CurrencyContext';

// ─── Status helpers ───────────────────────────────────────────────────────────

const invoiceStatusBadge = (status: string) => {
    const map: Record<string, { bg: string; color: string; label: string }> = {
        Posted:  { bg: 'rgba(16,185,129,0.12)', color: '#10b981', label: 'Invoiced' },
        Closed:  { bg: 'rgba(100,116,139,0.12)', color: '#64748b', label: 'Closed' },
        Approved:{ bg: 'rgba(59,130,246,0.12)', color: '#3b82f6', label: 'Approved' },
        Pending: { bg: 'rgba(245,158,11,0.12)', color: '#f59e0b', label: 'Pending' },
        Draft:   { bg: 'rgba(107,114,128,0.1)', color: '#6b7280', label: 'Draft' },
        Rejected:{ bg: 'rgba(239,68,68,0.1)', color: '#ef4444', label: 'Rejected' },
    };
    const s = map[status] ?? { bg: 'rgba(107,114,128,0.1)', color: '#6b7280', label: status };
    return (
        <span style={{ padding: '0.2rem 0.6rem', borderRadius: '20px', fontSize: 'var(--text-xs)', fontWeight: 700, background: s.bg, color: s.color, display: 'inline-flex', alignItems: 'center', gap: '0.25rem', whiteSpace: 'nowrap' }}>
            {status === 'Posted' || status === 'Closed' ? <CheckCircle size={11} /> : <AlertTriangle size={11} />}
            {s.label}
        </span>
    );
};

// ─── Component ────────────────────────────────────────────────────────────────

const AutomatedInvoicing = () => {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();

    const { data: ordersData, isLoading } = useSalesOrders();
    const { data: analytics } = useSalesAnalytics();

    const orders: any[] = useMemo(() =>
        Array.isArray(ordersData) ? ordersData : (ordersData?.results ?? []),
        [ordersData]
    );

    const postedOrders = useMemo(() => orders.filter(o => o.status === 'Posted' || o.status === 'Closed'), [orders]);
    const pendingInvoice = useMemo(() => orders.filter(o => o.status === 'Approved'), [orders]);
    const draftOrders = useMemo(() => orders.filter(o => o.status === 'Draft' || o.status === 'Pending'), [orders]);

    const totalInvoiced = useMemo(() => postedOrders.reduce((s, o) => s + parseFloat(o.total_amount || 0), 0), [postedOrders]);
    const totalPending = useMemo(() => pendingInvoice.reduce((s, o) => s + parseFloat(o.total_amount || 0), 0), [pendingInvoice]);
    const totalDraft = useMemo(() => draftOrders.reduce((s, o) => s + parseFloat(o.total_amount || 0), 0), [draftOrders]);

    if (isLoading) return <LoadingScreen message="Loading invoicing data..." />;

    return (
        <SalesLayout title="Automated Invoicing" description="Invoices are generated automatically when sales orders are posted">

            {/* ── KPI strip */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
                {[
                    { label: 'Invoiced Orders', value: postedOrders.length, sub: formatCurrency(totalInvoiced), icon: <FileCheck size={22} />, color: '#10b981', bg: 'rgba(16,185,129,0.12)' },
                    { label: 'Pending Approval', value: pendingInvoice.length, sub: formatCurrency(totalPending), icon: <Clock size={22} />, color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
                    { label: 'In Draft', value: draftOrders.length, sub: formatCurrency(totalDraft), icon: <Receipt size={22} />, color: '#6b7280', bg: 'rgba(107,114,128,0.1)' },
                    { label: 'Total Revenue', value: analytics?.total_revenue ? formatCurrency(analytics.total_revenue) : formatCurrency(totalInvoiced), sub: `${analytics?.total_orders ?? orders.length} orders`, icon: <TrendingUp size={22} />, color: 'var(--color-primary)', bg: 'rgba(59,130,246,0.1)' },
                ].map(({ label, value, sub, icon, color, bg }) => (
                    <div key={label} className="card" style={{ padding: '1.25rem 1.5rem' }}>
                        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                            <div style={{ width: 42, height: 42, borderRadius: '10px', background: bg, display: 'flex', alignItems: 'center', justifyContent: 'center', color }}>{icon}</div>
                        </div>
                        <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>{label}</div>
                        <div style={{ fontSize: '1.5rem', fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>{sub}</div>
                    </div>
                ))}
            </div>

            {/* ── How it works */}
            <div style={{ marginBottom: '2rem' }}>
                <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, marginBottom: '1rem', color: 'var(--color-text)' }}>O2C Workflow — How Automated Invoicing Works</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem' }}>
                    {[
                        { step: 1, color: '#6b7280', bg: 'rgba(107,114,128,0.1)', title: 'Create Sales Order', desc: 'Enter customer, line items, and dimensions. Order starts as Draft.' },
                        { step: 2, color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', title: 'Approve Order', desc: 'Credit check runs. Stock reserved. Order moves to Approved.' },
                        { step: 3, color: '#3b82f6', bg: 'rgba(59,130,246,0.12)', title: 'Post Order', desc: 'Invoice draft created automatically. Customer balance updated.' },
                        { step: 4, color: '#10b981', bg: 'rgba(16,185,129,0.12)', title: 'Deliver & Invoice', desc: 'Deliver goods. AR and revenue journals posted. Invoice finalised.' },
                    ].map(({ step, color, bg, title, desc }) => (
                        <div key={step} className="card" style={{ padding: '1.25rem', position: 'relative' }}>
                            {step < 4 && (
                                <ArrowRight size={14} style={{ position: 'absolute', right: '-11px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)', zIndex: 1 }} />
                            )}
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', marginBottom: '0.625rem' }}>
                                <span style={{ width: 26, height: 26, borderRadius: '50%', background: bg, color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 'var(--text-xs)', fontWeight: 800 }}>{step}</span>
                                <span style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>{title}</span>
                            </div>
                            <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', margin: 0, lineHeight: 1.5 }}>{desc}</p>
                        </div>
                    ))}
                </div>
            </div>

            {/* ── Pending approval — action needed */}
            {pendingInvoice.length > 0 && (
                <div style={{ marginBottom: '2rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.875rem' }}>
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0, color: 'var(--color-text)' }}>
                            Approved — Ready to Post ({pendingInvoice.length})
                        </h3>
                        <button className="btn btn-primary" onClick={() => navigate('/sales/orders')} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: 'var(--text-sm)' }}>
                            Go to Sales Orders <ArrowRight size={14} />
                        </button>
                    </div>
                    <div className="card" style={{ padding: 0, overflow: 'hidden', borderLeft: '3px solid #f59e0b' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: 'var(--color-surface)' }}>
                                    {['Order #', 'Customer', 'Order Date', 'Amount', 'Status'].map(h => (
                                        <th key={h} style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--color-text-muted)', textAlign: 'left', borderBottom: '1px solid var(--color-border)' }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {pendingInvoice.map((order: any) => (
                                    <tr key={order.id} style={{ borderBottom: '1px solid var(--color-border)', cursor: 'pointer' }}
                                        onClick={() => navigate('/sales/orders')}
                                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-surface)')}
                                        onMouseLeave={e => (e.currentTarget.style.background = '')}>
                                        <td style={{ padding: '0.875rem 1rem', fontWeight: 600 }}>{order.order_number}</td>
                                        <td style={{ padding: '0.875rem 1rem' }}>{order.customer_name}</td>
                                        <td style={{ padding: '0.875rem 1rem', color: 'var(--color-text-muted)' }}>{order.order_date}</td>
                                        <td style={{ padding: '0.875rem 1rem', fontWeight: 600, color: 'var(--color-primary)' }}>{formatCurrency(parseFloat(order.total_amount || 0))}</td>
                                        <td style={{ padding: '0.875rem 1rem' }}>{invoiceStatusBadge(order.status)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* ── Posted / Invoiced orders */}
            <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.875rem' }}>
                    <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0 }}>
                        Invoiced Orders ({postedOrders.length})
                    </h3>
                    <button className="btn btn-outline" onClick={() => navigate('/sales/orders')} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: 'var(--text-sm)' }}>
                        View All Orders <ArrowRight size={14} />
                    </button>
                </div>
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)' }}>
                                {['Order #', 'Customer', 'Order Date', 'Subtotal', 'Tax', 'Total', 'Status'].map(h => (
                                    <th key={h} style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--color-text-muted)', textAlign: 'left', borderBottom: '2px solid var(--color-border)' }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {postedOrders.length === 0 ? (
                                <tr>
                                    <td colSpan={7} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <Receipt size={40} style={{ display: 'block', margin: '0 auto 0.75rem', opacity: 0.2 }} />
                                        <p style={{ margin: 0 }}>No invoiced orders yet. Post a sales order to generate an invoice.</p>
                                    </td>
                                </tr>
                            ) : (
                                postedOrders.map((order: any) => (
                                    <tr key={order.id}
                                        style={{ borderBottom: '1px solid var(--color-border)', cursor: 'pointer', transition: 'background 0.12s' }}
                                        onClick={() => navigate('/sales/orders')}
                                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-surface)')}
                                        onMouseLeave={e => (e.currentTarget.style.background = '')}>
                                        <td style={{ padding: '0.875rem 1rem', fontWeight: 600 }}>{order.order_number}</td>
                                        <td style={{ padding: '0.875rem 1rem' }}>{order.customer_name}</td>
                                        <td style={{ padding: '0.875rem 1rem', color: 'var(--color-text-muted)' }}>{order.order_date}</td>
                                        <td style={{ padding: '0.875rem 1rem' }}>{formatCurrency(parseFloat(order.subtotal || 0))}</td>
                                        <td style={{ padding: '0.875rem 1rem', color: 'var(--color-text-muted)' }}>{formatCurrency(parseFloat(order.tax_amount || 0))}</td>
                                        <td style={{ padding: '0.875rem 1rem', fontWeight: 700, color: 'var(--color-primary)' }}>{formatCurrency(parseFloat(order.total_amount || 0))}</td>
                                        <td style={{ padding: '0.875rem 1rem' }}>{invoiceStatusBadge(order.status)}</td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </SalesLayout>
    );
};

export default AutomatedInvoicing;
