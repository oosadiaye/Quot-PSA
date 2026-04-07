import { useState, useMemo } from 'react';
import { useExpiryAlerts, useGenerateExpiryAlerts } from '../hooks/useInventory';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Calendar, RefreshCw } from 'lucide-react';

interface ExpiryAlert {
    id: number;
    batch_number: string;
    item_name: string;
    expiry_date: string;
    remaining_quantity: number | string;
    warehouse_name: string;
    alert_date?: string;
    is_sent: boolean;
    is_dismissed?: boolean;
}

type UrgencyFilter = 'All' | 'Expired' | 'Critical' | 'Warning' | 'Healthy';

function daysUntilExpiry(expiryDate: string): number {
    const expiry = new Date(expiryDate);
    const today  = new Date();
    today.setHours(0, 0, 0, 0);
    expiry.setHours(0, 0, 0, 0);
    return Math.round((expiry.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

function getUrgency(days: number): 'expired' | 'critical' | 'warning' | 'healthy' {
    if (days < 0)   return 'expired';
    if (days <= 7)  return 'critical';
    if (days <= 30) return 'warning';
    return 'healthy';
}

const URGENCY_BADGE: Record<string, { label: string; bg: string; color: string }> = {
    expired:  { label: 'EXPIRED',  bg: '#fee2e2', color: '#991b1b' },
    critical: { label: 'CRITICAL', bg: '#ffedd5', color: '#7c2d12' },
    warning:  { label: 'WARNING',  bg: '#fef3c7', color: '#92400e' },
    healthy:  { label: 'HEALTHY',  bg: '#d1fae5', color: '#065f46' },
};

const DAYS_PILL: Record<string, { bg: string; color: string }> = {
    expired:  { bg: '#fee2e2', color: '#991b1b' },
    critical: { bg: '#ffedd5', color: '#7c2d12' },
    warning:  { bg: '#fef3c7', color: '#92400e' },
    healthy:  { bg: '#d1fae5', color: '#065f46' },
};

const ROW_TINT: Record<string, string> = {
    expired:  'rgba(239,68,68,0.05)',
    critical: 'rgba(234,88,12,0.04)',
    warning:  'transparent',
    healthy:  'transparent',
};

const thStyle: React.CSSProperties = {
    padding: '0.9rem 1rem',
    fontSize: 'var(--text-xs)',
    fontWeight: 700,
    textTransform: 'uppercase',
    color: 'var(--color-text-muted)',
    whiteSpace: 'nowrap',
    textAlign: 'left',
};

const tdStyle: React.CSSProperties = {
    padding: '0.9rem 1rem',
    fontSize: 'var(--text-sm)',
    color: 'var(--color-text)',
    verticalAlign: 'middle',
};

const filterInputStyle: React.CSSProperties = {
    padding: '9px 14px',
    borderRadius: '8px',
    border: '2px solid var(--color-border, #e2e8f0)',
    fontSize: '13px',
    fontFamily: 'inherit',
    background: '#f8fafc',
    boxSizing: 'border-box',
};

const ExpiryAlertList = () => {
    const { data: alertsData, isLoading } = useExpiryAlerts();
    const generateAlerts                  = useGenerateExpiryAlerts();

    const [urgencyFilter, setUrgencyFilter] = useState<UrgencyFilter>('All');
    const [search, setSearch]               = useState('');

    const allAlerts: ExpiryAlert[] = useMemo(() => alertsData?.results ?? alertsData ?? [], [alertsData]);

    const filtered = useMemo(() => {
        let list = [...allAlerts];

        if (search) {
            const q = search.toLowerCase();
            list = list.filter(a =>
                a.item_name?.toLowerCase().includes(q) ||
                a.batch_number?.toLowerCase().includes(q)
            );
        }

        if (urgencyFilter !== 'All') {
            list = list.filter(a => {
                const days    = daysUntilExpiry(a.expiry_date);
                const urgency = getUrgency(days);
                switch (urgencyFilter) {
                    case 'Expired':  return urgency === 'expired';
                    case 'Critical': return urgency === 'critical';
                    case 'Warning':  return urgency === 'warning';
                    case 'Healthy':  return urgency === 'healthy';
                    default:         return true;
                }
            });
        }

        list.sort((a, b) => new Date(a.expiry_date).getTime() - new Date(b.expiry_date).getTime());
        return list;
    }, [allAlerts, search, urgencyFilter]);

    const kpiExpired  = allAlerts.filter(a => daysUntilExpiry(a.expiry_date) < 0).length;
    const kpiCritical = allAlerts.filter(a => { const d = daysUntilExpiry(a.expiry_date); return d >= 0 && d <= 7; }).length;
    const kpiWarning  = allAlerts.filter(a => { const d = daysUntilExpiry(a.expiry_date); return d >= 8 && d <= 30; }).length;
    const kpiHealthy  = allAlerts.filter(a => daysUntilExpiry(a.expiry_date) > 30).length;

    if (isLoading) return <LoadingScreen message="Loading expiry alerts..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }} className="animate-fade">

                <PageHeader
                    title="Batch Expiry Alerts"
                    subtitle="Monitor batch expiry dates and take action before stock goes to waste"
                    icon={<Calendar size={22} />}
                    actions={
                        <button
                            onClick={() => generateAlerts.mutate()}
                            disabled={generateAlerts.isPending}
                            style={{
                                display: 'inline-flex', alignItems: 'center', gap: '7px',
                                padding: '0.5rem 1.1rem', borderRadius: '8px',
                                fontSize: '13px', fontWeight: 600,
                                border: 'none', cursor: 'pointer',
                                background: 'rgba(255,255,255,0.18)', color: 'white',
                                fontFamily: 'inherit',
                                opacity: generateAlerts.isPending ? 0.7 : 1,
                            }}
                        >
                            <RefreshCw size={14} className={generateAlerts.isPending ? 'animate-spin' : ''} />
                            {generateAlerts.isPending ? 'Generating...' : 'Generate Alerts'}
                        </button>
                    }
                />

                {/* KPI Mini Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
                    {[
                        { label: 'Expired',             value: kpiExpired,  accent: '#dc2626', bg: '#fef2f2', filter: 'Expired'  as UrgencyFilter },
                        { label: 'Critical (0–7 days)', value: kpiCritical, accent: '#ea580c', bg: '#fff7ed', filter: 'Critical' as UrgencyFilter },
                        { label: 'Warning (8–30 days)', value: kpiWarning,  accent: '#d97706', bg: '#fffbeb', filter: 'Warning'  as UrgencyFilter },
                        { label: 'Healthy (> 30 days)', value: kpiHealthy,  accent: '#059669', bg: '#f0fdf4', filter: 'Healthy'  as UrgencyFilter },
                    ].map(k => (
                        <button
                            key={k.label}
                            onClick={() => setUrgencyFilter(urgencyFilter === k.filter ? 'All' : k.filter)}
                            style={{
                                padding: '1.1rem 1.25rem', display: 'flex', flexDirection: 'column', gap: '4px',
                                borderRadius: '12px', border: `2px solid ${urgencyFilter === k.filter ? k.accent : 'transparent'}`,
                                borderTop: `3px solid ${k.accent}`, background: k.bg, cursor: 'pointer',
                                textAlign: 'left', boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                                transition: 'border-color 0.15s',
                            }}
                        >
                            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{k.label}</span>
                            <span style={{ fontSize: '2rem', fontWeight: 700, color: k.accent, lineHeight: 1.1 }}>{k.value}</span>
                        </button>
                    ))}
                </div>

                {/* Filter Bar */}
                <div className="card" style={{ padding: '1rem 1.25rem', marginBottom: '1.25rem', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center' }}>
                    <input
                        style={{ ...filterInputStyle, width: '260px', flex: 'none' } as React.CSSProperties}
                        placeholder="Search by item name or batch number..."
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                    />
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                        {(['All', 'Expired', 'Critical', 'Warning', 'Healthy'] as UrgencyFilter[]).map(f => (
                            <button
                                key={f}
                                onClick={() => setUrgencyFilter(f)}
                                style={{
                                    padding: '6px 14px', borderRadius: '20px',
                                    fontSize: '12px', fontWeight: 600,
                                    border: '1.5px solid',
                                    borderColor: urgencyFilter === f ? 'var(--color-primary, #191e6a)' : 'var(--color-border, #e2e8f0)',
                                    background: urgencyFilter === f ? 'var(--color-primary, #191e6a)' : 'transparent',
                                    color: urgencyFilter === f ? 'white' : 'var(--color-text-muted)',
                                    cursor: 'pointer', fontFamily: 'inherit',
                                    transition: 'all 0.15s',
                                }}
                            >
                                {f}
                            </button>
                        ))}
                    </div>
                    <span style={{ marginLeft: 'auto', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', fontWeight: 500 }}>
                        {filtered.length} alert{filtered.length !== 1 ? 's' : ''}
                    </span>
                </div>

                {/* Table */}
                {filtered.length === 0 ? (
                    <div className="card" style={{ textAlign: 'center', padding: '4rem 2rem' }}>
                        <Calendar size={48} style={{ color: 'var(--color-success, #10b981)', marginBottom: '1rem', display: 'block', margin: '0 auto 1rem' }} />
                        <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-base)', margin: 0 }}>
                            {search || urgencyFilter !== 'All' ? 'No alerts match your filters.' : 'No expiry alerts. All batches are healthy!'}
                        </p>
                    </div>
                ) : (
                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '860px' }}>
                                <thead>
                                    <tr style={{ background: 'var(--color-surface)', borderBottom: '2px solid var(--color-border)' }}>
                                        <th style={thStyle}>Batch Number</th>
                                        <th style={thStyle}>Product</th>
                                        <th style={thStyle}>Warehouse</th>
                                        <th style={{ ...thStyle, textAlign: 'right' }}>Remaining Qty</th>
                                        <th style={thStyle}>Expiry Date</th>
                                        <th style={{ ...thStyle, textAlign: 'center' }}>Days Until Expiry</th>
                                        <th style={thStyle}>Urgency</th>
                                        <th style={thStyle}>Alert Sent</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filtered.map((alert) => {
                                        const days    = daysUntilExpiry(alert.expiry_date);
                                        const urgency = getUrgency(days);
                                        const badge   = URGENCY_BADGE[urgency];
                                        const pill    = DAYS_PILL[urgency];
                                        const rowBg   = ROW_TINT[urgency];

                                        let pillText = '';
                                        if (days < 0) {
                                            pillText = `${Math.abs(days)} day${Math.abs(days) !== 1 ? 's' : ''} ago`;
                                        } else {
                                            pillText = `${days} day${days !== 1 ? 's' : ''}`;
                                        }

                                        return (
                                            <tr key={alert.id} style={{ borderBottom: '1px solid var(--color-border)', background: rowBg }}>
                                                <td style={tdStyle}>
                                                    <span style={{ fontWeight: 700, fontSize: 'var(--text-sm)' }}>{alert.batch_number}</span>
                                                </td>
                                                <td style={tdStyle}>{alert.item_name}</td>
                                                <td style={{ ...tdStyle, color: 'var(--color-text-muted)' }}>{alert.warehouse_name}</td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600 }}>
                                                    {Number(alert.remaining_quantity).toLocaleString()}
                                                </td>
                                                <td style={{ ...tdStyle, color: 'var(--color-text-muted)' }}>
                                                    {alert.expiry_date?.split('T')[0]}
                                                </td>
                                                <td style={{ ...tdStyle, textAlign: 'center' }}>
                                                    <span style={{
                                                        display: 'inline-block',
                                                        padding: '4px 12px',
                                                        borderRadius: '20px',
                                                        fontSize: '13px',
                                                        fontWeight: 700,
                                                        background: pill.bg,
                                                        color: pill.color,
                                                        whiteSpace: 'nowrap',
                                                    }}>
                                                        {pillText}
                                                    </span>
                                                </td>
                                                <td style={tdStyle}>
                                                    <span style={{
                                                        display: 'inline-block',
                                                        padding: '3px 10px',
                                                        borderRadius: '20px',
                                                        fontSize: 'var(--text-xs)',
                                                        fontWeight: 700,
                                                        letterSpacing: '0.04em',
                                                        background: badge.bg,
                                                        color: badge.color,
                                                    }}>
                                                        {badge.label}
                                                    </span>
                                                </td>
                                                <td style={tdStyle}>
                                                    {alert.is_sent ? (
                                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 10px', borderRadius: '20px', fontSize: 'var(--text-xs)', fontWeight: 700, background: '#d1fae5', color: '#065f46' }}>
                                                            Sent
                                                        </span>
                                                    ) : (
                                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 10px', borderRadius: '20px', fontSize: 'var(--text-xs)', fontWeight: 700, background: '#f1f5f9', color: '#64748b' }}>
                                                            Pending
                                                        </span>
                                                    )}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
};

export default ExpiryAlertList;
