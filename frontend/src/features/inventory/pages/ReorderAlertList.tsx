import { useState, useMemo } from 'react';
import {
    useReorderAlerts,
    useGenerateReorderAlerts,
    useDeleteReorderAlert,
    useWarehouses,
} from '../hooks/useInventory';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { AlertTriangle, RefreshCw, Trash2, Package, X } from 'lucide-react';

interface ReorderAlert {
    id: number;
    item_name: string;
    sku?: string;
    current_stock: number | string;
    reorder_point: number | string;
    suggested_quantity?: number | string;
    warehouse: number;
    warehouse_name: string;
    created_at?: string;
    is_sent: boolean;
}

interface Warehouse {
    id: number;
    name: string;
}

type SortMode = 'urgent' | 'alpha' | 'qty';

function stockRatio(alert: ReorderAlert): number {
    const cur = Number(alert.current_stock);
    const reo = Number(alert.reorder_point);
    if (reo <= 0) return cur === 0 ? 0 : 1;
    return cur / reo;
}

function stockBarColor(ratio: number): string {
    if (ratio === 0)      return '#ef4444';
    if (ratio < 0.5)      return '#f97316';
    if (ratio < 1)        return '#f59e0b';
    return '#10b981';
}

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

const ReorderAlertList = () => {
    const { data: alertsData, isLoading } = useReorderAlerts();
    const generateAlerts                  = useGenerateReorderAlerts();
    const deleteAlert                     = useDeleteReorderAlert();
    const { data: warehousesData }        = useWarehouses();

    const [search, setSearch]                 = useState('');
    const [warehouseFilter, setWarehouseFilter] = useState('');
    const [sortMode, setSortMode]             = useState<SortMode>('urgent');
    const [confirmDelete, setConfirmDelete]   = useState<number | null>(null);
    const [clearConfirm, setClearConfirm]     = useState(false);

    const allAlerts: ReorderAlert[]  = useMemo(() => alertsData?.results ?? alertsData ?? [], [alertsData]);
    const warehouses: Warehouse[]    = useMemo(() => warehousesData?.results ?? warehousesData ?? [], [warehousesData]);

    const filtered = useMemo(() => {
        let list = [...allAlerts];

        if (search) {
            const q = search.toLowerCase();
            list = list.filter(a =>
                a.item_name?.toLowerCase().includes(q) ||
                a.sku?.toLowerCase().includes(q)
            );
        }

        if (warehouseFilter) {
            list = list.filter(a => String(a.warehouse) === warehouseFilter);
        }

        switch (sortMode) {
            case 'urgent':
                list.sort((a, b) => stockRatio(a) - stockRatio(b));
                break;
            case 'alpha':
                list.sort((a, b) => (a.item_name ?? '').localeCompare(b.item_name ?? ''));
                break;
            case 'qty':
                list.sort((a, b) => Number(a.current_stock) - Number(b.current_stock));
                break;
        }

        return list;
    }, [allAlerts, search, warehouseFilter, sortMode]);

    const kpiTotal     = allAlerts.length;
    const kpiCritical  = allAlerts.filter(a => Number(a.current_stock) === 0).length;
    const kpiNeedsAct  = allAlerts.filter(a => {
        const cur = Number(a.current_stock);
        const reo = Number(a.reorder_point);
        return cur > 0 && reo > 0 && cur < reo / 2;
    }).length;

    const handleDelete = async (id: number) => {
        try {
            await deleteAlert.mutateAsync(id);
        } finally {
            setConfirmDelete(null);
        }
    };

    const handleClearAll = async () => {
        for (const alert of allAlerts) {
            await deleteAlert.mutateAsync(alert.id);
        }
        setClearConfirm(false);
    };

    if (isLoading) return <LoadingScreen message="Loading reorder alerts..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }} className="animate-fade">

                <PageHeader
                    title="Reorder Alerts"
                    subtitle="Products below their reorder point — take action to avoid stockouts"
                    icon={<AlertTriangle size={22} />}
                    actions={
                        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                            {allAlerts.length > 0 && (
                                clearConfirm ? (
                                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center', background: 'rgba(255,255,255,0.1)', borderRadius: '8px', padding: '4px 10px' }}>
                                        <span style={{ fontSize: '12px', color: 'white', fontWeight: 600 }}>Clear all?</span>
                                        <button
                                            onClick={handleClearAll}
                                            disabled={deleteAlert.isPending}
                                            style={{ padding: '4px 12px', borderRadius: '6px', fontSize: '12px', fontWeight: 700, border: 'none', cursor: 'pointer', background: '#ef4444', color: 'white', fontFamily: 'inherit' }}
                                        >
                                            Yes
                                        </button>
                                        <button
                                            onClick={() => setClearConfirm(false)}
                                            style={{ padding: '4px 10px', borderRadius: '6px', fontSize: '12px', fontWeight: 700, border: 'none', cursor: 'pointer', background: 'rgba(255,255,255,0.2)', color: 'white', fontFamily: 'inherit' }}
                                        >
                                            No
                                        </button>
                                    </div>
                                ) : (
                                    <button
                                        onClick={() => setClearConfirm(true)}
                                        style={{
                                            display: 'inline-flex', alignItems: 'center', gap: '6px',
                                            padding: '0.5rem 1rem', borderRadius: '8px',
                                            fontSize: '13px', fontWeight: 600,
                                            border: '1.5px solid rgba(255,255,255,0.4)', cursor: 'pointer',
                                            background: 'transparent', color: 'rgba(255,255,255,0.85)',
                                            fontFamily: 'inherit',
                                        }}
                                    >
                                        <X size={13} /> Clear All
                                    </button>
                                )
                            )}
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
                                <RefreshCw size={14} />
                                {generateAlerts.isPending ? 'Generating...' : 'Generate Alerts'}
                            </button>
                        </div>
                    }
                />

                {/* KPI Summary Row */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
                    {[
                        { label: 'Total Alerts',           value: kpiTotal,    accent: '#3b82f6', bg: '#eff6ff' },
                        { label: 'Out of Stock (Critical)', value: kpiCritical, accent: '#dc2626', bg: '#fef2f2' },
                        { label: 'Needs Action',            value: kpiNeedsAct, accent: '#ea580c', bg: '#fff7ed' },
                    ].map(k => (
                        <div
                            key={k.label}
                            className="card"
                            style={{ padding: '1.25rem 1.5rem', display: 'flex', flexDirection: 'column', gap: '4px', borderTop: `3px solid ${k.accent}`, background: k.bg }}
                        >
                            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{k.label}</span>
                            <span style={{ fontSize: '2rem', fontWeight: 700, color: k.accent, lineHeight: 1.1 }}>{k.value}</span>
                        </div>
                    ))}
                </div>

                {/* Filter Bar */}
                <div className="card" style={{ padding: '1rem 1.25rem', marginBottom: '1.25rem', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center' }}>
                    <input
                        style={{ ...filterInputStyle, width: '240px', flex: 'none' } as React.CSSProperties}
                        placeholder="Search by item name or SKU..."
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                    />
                    <select
                        style={{ ...filterInputStyle, width: '190px', flex: 'none' } as React.CSSProperties}
                        value={warehouseFilter}
                        onChange={e => setWarehouseFilter(e.target.value)}
                    >
                        <option value="">All Warehouses</option>
                        {warehouses.map(w => <option key={w.id} value={String(w.id)}>{w.name}</option>)}
                    </select>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        {([['urgent', 'Most Urgent'], ['alpha', 'Alphabetical'], ['qty', 'By Quantity']] as [SortMode, string][]).map(([mode, label]) => (
                            <button
                                key={mode}
                                onClick={() => setSortMode(mode)}
                                style={{
                                    padding: '6px 14px', borderRadius: '20px',
                                    fontSize: '12px', fontWeight: 600,
                                    border: '1.5px solid',
                                    borderColor: sortMode === mode ? 'var(--color-primary, #191e6a)' : 'var(--color-border, #e2e8f0)',
                                    background: sortMode === mode ? 'var(--color-primary, #191e6a)' : 'transparent',
                                    color: sortMode === mode ? 'white' : 'var(--color-text-muted)',
                                    cursor: 'pointer', fontFamily: 'inherit',
                                    transition: 'all 0.15s',
                                }}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                    <span style={{ marginLeft: 'auto', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', fontWeight: 500 }}>
                        {filtered.length} alert{filtered.length !== 1 ? 's' : ''}
                    </span>
                </div>

                {/* Empty State */}
                {filtered.length === 0 ? (
                    <div className="card" style={{ textAlign: 'center', padding: '4rem 2rem' }}>
                        <Package size={48} style={{ color: 'var(--color-success, #10b981)', display: 'block', margin: '0 auto 1rem' }} />
                        <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-base)', margin: 0 }}>
                            {search || warehouseFilter ? 'No alerts match your filters.' : 'All stock levels are healthy — no reorder alerts!'}
                        </p>
                    </div>
                ) : (
                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '820px' }}>
                                <thead>
                                    <tr style={{ background: 'var(--color-surface)', borderBottom: '2px solid var(--color-border)' }}>
                                        <th style={thStyle}>Product</th>
                                        <th style={thStyle}>Warehouse</th>
                                        <th style={{ ...thStyle, textAlign: 'right' }}>Current Stock</th>
                                        <th style={{ ...thStyle, textAlign: 'right' }}>Reorder Point</th>
                                        <th style={{ ...thStyle, minWidth: '160px' }}>Stock Level</th>
                                        <th style={{ ...thStyle, textAlign: 'right' }}>Suggested Reorder</th>
                                        <th style={thStyle}>Alert Sent</th>
                                        <th style={{ ...thStyle, width: '72px' }}></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filtered.map((alert) => {
                                        const cur      = Number(alert.current_stock);
                                        const reo      = Number(alert.reorder_point);
                                        const ratio    = stockRatio(alert);
                                        const pct      = Math.min(ratio * 100, 100);
                                        const barColor = stockBarColor(ratio);
                                        const isOos    = cur === 0;
                                        const rowBg    = isOos ? 'rgba(239,68,68,0.04)' : 'transparent';

                                        return (
                                            <tr key={alert.id} style={{ borderBottom: '1px solid var(--color-border)', background: rowBg }}>
                                                <td style={tdStyle}>
                                                    <div style={{ fontWeight: 600 }}>{alert.item_name}</div>
                                                    {alert.sku && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '2px' }}>{alert.sku}</div>}
                                                </td>
                                                <td style={{ ...tdStyle, color: 'var(--color-text-muted)' }}>{alert.warehouse_name}</td>
                                                <td style={{ ...tdStyle, textAlign: 'right' }}>
                                                    <span style={{
                                                        fontWeight: 700,
                                                        fontSize: 'var(--text-sm)',
                                                        color: cur === 0 ? '#ef4444' : cur < reo / 2 ? '#f97316' : 'var(--color-text)',
                                                    }}>
                                                        {cur.toLocaleString()}
                                                    </span>
                                                    {isOos && (
                                                        <span style={{ display: 'block', fontSize: '10px', fontWeight: 700, color: '#ef4444', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                                            Out of Stock
                                                        </span>
                                                    )}
                                                </td>
                                                <td style={{ ...tdStyle, textAlign: 'right', color: 'var(--color-text-muted)' }}>
                                                    {reo.toLocaleString()}
                                                </td>
                                                <td style={tdStyle}>
                                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                                        <div style={{ height: '8px', borderRadius: '999px', background: '#e2e8f0', overflow: 'hidden', position: 'relative' }}>
                                                            <div style={{
                                                                position: 'absolute', left: 0, top: 0, bottom: 0,
                                                                width: `${pct}%`,
                                                                background: barColor,
                                                                borderRadius: '999px',
                                                                transition: 'width 0.3s ease',
                                                            }} />
                                                        </div>
                                                        <span style={{ fontSize: '11px', fontWeight: 600, color: barColor }}>
                                                            {pct.toFixed(0)}%
                                                        </span>
                                                    </div>
                                                </td>
                                                <td style={{ ...tdStyle, textAlign: 'right' }}>
                                                    <span style={{
                                                        display: 'inline-block',
                                                        padding: '3px 10px',
                                                        borderRadius: '20px',
                                                        fontSize: 'var(--text-xs)',
                                                        fontWeight: 600,
                                                        background: '#f1f5f9',
                                                        color: '#475569',
                                                    }}>
                                                        {Number(alert.suggested_quantity ?? reo).toLocaleString()}
                                                    </span>
                                                </td>
                                                <td style={tdStyle}>
                                                    {alert.is_sent ? (
                                                        <span style={{ display: 'inline-block', padding: '3px 10px', borderRadius: '20px', fontSize: 'var(--text-xs)', fontWeight: 700, background: '#d1fae5', color: '#065f46' }}>
                                                            Sent
                                                        </span>
                                                    ) : (
                                                        <span style={{ display: 'inline-block', padding: '3px 10px', borderRadius: '20px', fontSize: 'var(--text-xs)', fontWeight: 700, background: '#f1f5f9', color: '#64748b' }}>
                                                            Pending
                                                        </span>
                                                    )}
                                                </td>
                                                <td style={tdStyle}>
                                                    {confirmDelete === alert.id ? (
                                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-start' }}>
                                                            <span style={{ fontSize: '11px', color: '#dc2626', fontWeight: 600 }}>Dismiss?</span>
                                                            <div style={{ display: 'flex', gap: '4px' }}>
                                                                <button
                                                                    onClick={() => handleDelete(alert.id)}
                                                                    style={{ background: '#dc2626', color: 'white', border: 'none', borderRadius: '4px', padding: '3px 8px', cursor: 'pointer', fontSize: '11px', fontWeight: 600 }}
                                                                >
                                                                    Yes
                                                                </button>
                                                                <button
                                                                    onClick={() => setConfirmDelete(null)}
                                                                    style={{ background: '#e2e8f0', border: 'none', borderRadius: '4px', padding: '3px 8px', cursor: 'pointer', fontSize: '11px' }}
                                                                >
                                                                    No
                                                                </button>
                                                            </div>
                                                        </div>
                                                    ) : (
                                                        <button
                                                            className="btn btn-outline"
                                                            onClick={() => setConfirmDelete(alert.id)}
                                                            style={{ color: 'var(--color-error)', padding: '0.25rem 0.5rem', display: 'inline-flex', alignItems: 'center' }}
                                                            title="Dismiss alert"
                                                        >
                                                            <Trash2 size={14} />
                                                        </button>
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

export default ReorderAlertList;
