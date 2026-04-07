import { useNavigate } from 'react-router-dom';
import {
    Package,
    DollarSign,
    AlertTriangle,
    Calendar,
    Warehouse,
    CheckCircle,
    ArrowRightLeft,
    Tag,
    Layers,
    ClipboardList,
    RefreshCw,
    BarChart2,
    Hash,
    ScanLine,
    Scale,
    GitCompare,
    ArrowDown,
    ArrowUp,
    FileText,
} from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import {
    useStockValuation,
    useReorderAlerts,
    useExpiryAlerts,
    useStockMovements,
    useWarehouses,
} from '../hooks/useInventory';
import { useCurrency } from '../../../context/CurrencyContext';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ValuationItem {
    id: number;
    sku: string;
    name: string;
    total_quantity: number;
    total_value: number;
    average_cost: number;
    needs_reorder: boolean;
    unit_of_measure: string;
    valuation_method: string;
}

interface ReorderAlert {
    id: number;
    item_name: string;
    sku: string;
    current_stock: number;
    reorder_point: number;
    suggested_quantity: number;
    warehouse: string;
}

interface ExpiryAlert {
    id: number;
    batch_number: string;
    item_name: string;
    expiry_date: string;
    remaining_quantity: number;
    warehouse_name: string;
}

interface StockMovement {
    id: number;
    movement_type: string;
    item_name: string;
    quantity: number;
    unit_price: number;
    reference_number: string;
    warehouse_name: string;
    created_at: string;
}

interface WarehouseItem {
    id: number;
    name: string;
    location: string;
    is_active: boolean;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const getMovementColor = (type: string): string => {
    switch (type) {
        case 'IN':  return '#10b981';
        case 'OUT': return '#ef4444';
        case 'ADJ': return '#3b82f6';
        case 'TRF': return '#f59e0b';
        default:    return '#6b7280';
    }
};

const getMovementLabel = (type: string): string => {
    switch (type) {
        case 'IN':  return 'Stock In';
        case 'OUT': return 'Stock Out';
        case 'ADJ': return 'Adjustment';
        case 'TRF': return 'Transfer';
        default:    return type;
    }
};

const MovementTypeIcon = ({ type }: { type: string }) => {
    const color = getMovementColor(type);
    const s = 12;
    if (type === 'IN')  return <ArrowDown size={s} color={color} />;
    if (type === 'OUT') return <ArrowUp size={s} color={color} />;
    if (type === 'ADJ') return <RefreshCw size={s} color={color} />;
    if (type === 'TRF') return <ArrowRightLeft size={s} color={color} />;
    return <FileText size={s} color={color} />;
};

const LiveBadge = () => (
    <span style={{
        display: 'inline-flex', alignItems: 'center', gap: '0.35rem',
        padding: '0.2rem 0.65rem', borderRadius: '999px',
        background: 'rgba(16,185,129,0.12)', color: '#10b981',
        fontSize: 'var(--text-xs)', fontWeight: 700, letterSpacing: '0.04em',
        border: '1px solid rgba(16,185,129,0.3)',
    }}>
        <span style={{
            width: '7px', height: '7px', borderRadius: '50%',
            background: '#10b981', flexShrink: 0,
            animation: 'inv-pulse 1.6s ease-in-out infinite',
        }} />
        Live
    </span>
);

// ─── Component ────────────────────────────────────────────────────────────────

const InventoryDashboard = () => {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();

    const { data: valuationRaw,  isLoading: loadingVal } = useStockValuation();
    const { data: reorderRaw,    isLoading: loadingReo } = useReorderAlerts({ refetchInterval: 30_000 });
    const { data: expiryRaw,     isLoading: loadingExp } = useExpiryAlerts({ refetchInterval: 30_000 });
    const { data: movementsRaw,  isLoading: loadingMov } = useStockMovements({ page_size: 8 });
    const { data: warehousesRaw, isLoading: loadingWar } = useWarehouses();

    if (loadingVal || loadingReo || loadingExp || loadingMov || loadingWar) {
        return <LoadingScreen message="Loading inventory dashboard..." />;
    }

    const valuationList: ValuationItem[]  = Array.isArray(valuationRaw)  ? valuationRaw  : (valuationRaw?.items  ?? valuationRaw?.results  ?? []);
    const reorderList:   ReorderAlert[]   = Array.isArray(reorderRaw)    ? reorderRaw    : (reorderRaw?.results  ?? []);
    const expiryList:    ExpiryAlert[]    = Array.isArray(expiryRaw)     ? expiryRaw     : (expiryRaw?.results   ?? []);
    const movementsList: StockMovement[]  = Array.isArray(movementsRaw)  ? movementsRaw  : (movementsRaw?.results ?? []);
    const warehousesList: WarehouseItem[] = Array.isArray(warehousesRaw) ? warehousesRaw : (warehousesRaw?.results ?? []);

    // KPI values
    const totalProducts    = valuationList.length;
    const totalValue       = valuationList.reduce((s, i) => s + Number(i.total_value  || 0), 0);
    const inStockCount     = valuationList.filter(i => Number(i.total_quantity) > 0).length;
    const lowStockCount    = reorderList.length;
    const activeWarehouses = warehousesList.filter(w => w.is_active).length;

    const now = new Date();
    const in30Days = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
    const expiringSoon = expiryList.filter(e => {
        if (!e.expiry_date) return false;
        const d = new Date(e.expiry_date);
        return d >= now && d <= in30Days;
    }).length;

    // Valuation method grouping
    const methodGroups: Record<string, number> = {};
    valuationList.forEach(i => {
        const m = (i.valuation_method || 'Unknown').toUpperCase();
        methodGroups[m] = (methodGroups[m] || 0) + 1;
    });
    const methodTotal  = Object.values(methodGroups).reduce((s, v) => s + v, 0) || 1;
    const methodColors: Record<string, string> = { WA: '#3b82f6', FIFO: '#10b981', LIFO: '#f59e0b', UNKNOWN: '#6b7280' };

    // Top 10 by value
    const top10 = [...valuationList]
        .sort((a, b) => Number(b.total_value) - Number(a.total_value))
        .slice(0, 10);

    // Top 5 most urgent reorder (lowest stock/reorder ratio)
    const top5Reorder = [...reorderList]
        .sort((a, b) => {
            const rA = a.reorder_point > 0 ? a.current_stock / a.reorder_point : 0;
            const rB = b.reorder_point > 0 ? b.current_stock / b.reorder_point : 0;
            return rA - rB;
        })
        .slice(0, 5);

    // Quick-nav cards
    const navCards = [
        { label: 'Products',       desc: 'Browse & manage SKUs',         icon: Package,        path: '/inventory' },
        { label: 'Product Types',  desc: 'Define product type taxonomy',  icon: Layers,         path: '/inventory/product-types' },
        { label: 'Categories',     desc: 'Manage item categories',        icon: Tag,            path: '/inventory/categories' },
        { label: 'Warehouses',     desc: 'Locations & storage sites',     icon: Warehouse,      path: '/inventory/warehouses' },
        { label: 'Stock Levels',   desc: 'View stock by warehouse',       icon: BarChart2,      path: '/inventory/stocks' },
        { label: 'Movements',      desc: 'Receipts, issues & transfers',  icon: ArrowRightLeft, path: '/inventory/movements' },
        { label: 'Batches',        desc: 'Track lot & batch numbers',     icon: ClipboardList,  path: '/inventory/batches' },
        { label: 'Serial Numbers', desc: 'Serialised item tracking',      icon: ScanLine,       path: '/inventory/serial-numbers' },
        { label: 'Valuation',      desc: 'Cost & valuation reports',      icon: Scale,          path: '/inventory/valuation' },
        { label: 'Reconciliation', desc: 'Physical count vs system',      icon: GitCompare,     path: '/inventory/reconciliation' },
        { label: 'Reorder Alerts', desc: 'Below reorder-point items',     icon: AlertTriangle,  path: '/inventory/reorder-alerts' },
        { label: 'Expiry Alerts',  desc: 'Batches nearing expiry',        icon: Calendar,       path: '/inventory/expiry-alerts' },
    ];

    const kpis = [
        {
            label: 'Total Products', value: totalProducts.toLocaleString(),
            icon: Package, color: 'var(--color-primary)', bg: 'rgba(46,56,152,0.1)',
        },
        {
            label: 'Inventory Value', value: formatCurrency(totalValue),
            icon: DollarSign, color: '#10b981', bg: 'rgba(16,185,129,0.1)',
        },
        {
            label: 'In-Stock Items', value: inStockCount.toLocaleString(),
            icon: CheckCircle, color: '#10b981', bg: 'rgba(16,185,129,0.1)',
        },
        {
            label: 'Low Stock Alerts', value: lowStockCount.toLocaleString(),
            icon: AlertTriangle,
            color: lowStockCount > 0 ? '#ef4444' : '#6b7280',
            bg:    lowStockCount > 0 ? 'rgba(239,68,68,0.1)' : 'rgba(107,114,128,0.1)',
        },
        {
            label: 'Expiring Soon', value: expiringSoon.toLocaleString(),
            icon: Calendar,
            color: expiringSoon > 0 ? '#f59e0b' : '#6b7280',
            bg:    expiringSoon > 0 ? 'rgba(245,158,11,0.1)' : 'rgba(107,114,128,0.1)',
        },
        {
            label: 'Active Warehouses', value: activeWarehouses.toLocaleString(),
            icon: Warehouse, color: '#3b82f6', bg: 'rgba(59,130,246,0.1)',
        },
    ];

    return (
        <>
            <style>{`
                @keyframes inv-pulse {
                    0%, 100% { opacity: 1; transform: scale(1); }
                    50%       { opacity: 0.45; transform: scale(1.5); }
                }
            `}</style>

            <div style={{ display: 'flex' }}>
                <Sidebar />
                <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>

                    {/* Header */}
                    <PageHeader
                        title="Inventory Dashboard"
                        subtitle="Real-time overview of stock, valuation, and alerts."
                        icon={<Package size={22} />}
                        actions={
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                <LiveBadge />
                                <button
                                    className="btn btn-primary"
                                    onClick={() => navigate('/inventory/new')}
                                    style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: 'var(--text-xs)', padding: '0.5rem 1rem' }}
                                >
                                    <Hash size={14} />
                                    New Product
                                </button>
                            </div>
                        }
                    />

                    {/* ── KPI Row ─────────────────────────────────────────────── */}
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                        gap: '1.1rem',
                        marginBottom: '2rem',
                    }}>
                        {kpis.map(kpi => (
                            <div key={kpi.label} className="card animate-fade" style={{ padding: '1.25rem' }}>
                                <div style={{
                                    width: '34px', height: '34px', borderRadius: '8px',
                                    background: kpi.bg, display: 'flex', alignItems: 'center',
                                    justifyContent: 'center', marginBottom: '0.75rem',
                                }}>
                                    <kpi.icon size={17} color={kpi.color} />
                                </div>
                                <div style={{
                                    fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)',
                                    fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em',
                                    marginBottom: '0.25rem',
                                }}>
                                    {kpi.label}
                                </div>
                                <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)' }}>
                                    {kpi.value}
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* ── Two-column main ─────────────────────────────────────── */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>

                        {/* LEFT */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                            {/* Stock by Valuation Method — stacked bar */}
                            <div className="card" style={{ padding: '1.5rem' }}>
                                <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)', marginBottom: '1.25rem' }}>
                                    Stock by Valuation Method
                                </h3>
                                <div style={{ display: 'flex', height: '26px', borderRadius: '6px', overflow: 'hidden', marginBottom: '0.875rem' }}>
                                    {Object.keys(methodGroups).length === 0 ? (
                                        <div style={{ flex: 1, background: 'var(--color-border)' }} />
                                    ) : (
                                        Object.entries(methodGroups).map(([method, count]) => {
                                            const pct   = (count / methodTotal) * 100;
                                            const color = methodColors[method] ?? '#6b7280';
                                            return (
                                                <div
                                                    key={method}
                                                    title={`${method}: ${count} item${count !== 1 ? 's' : ''} (${pct.toFixed(1)}%)`}
                                                    style={{ width: `${pct}%`, background: color, transition: 'width 0.4s ease', minWidth: pct > 0 ? '4px' : '0' }}
                                                />
                                            );
                                        })
                                    )}
                                </div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.875rem' }}>
                                    {Object.entries(methodGroups).map(([method, count]) => (
                                        <div key={method} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                                            <span style={{ width: '9px', height: '9px', borderRadius: '2px', background: methodColors[method] ?? '#6b7280', flexShrink: 0 }} />
                                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                {method} <strong style={{ color: 'var(--color-text)' }}>{count}</strong>
                                                <span style={{ color: 'var(--color-text-muted)' }}> ({((count / methodTotal) * 100).toFixed(0)}%)</span>
                                            </span>
                                        </div>
                                    ))}
                                    {Object.keys(methodGroups).length === 0 && (
                                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>No valuation data available.</span>
                                    )}
                                </div>
                            </div>

                            {/* Top 10 Items by Value */}
                            <div className="card" style={{ padding: 0, overflow: 'hidden', flex: 1 }}>
                                <div style={{ padding: '1.1rem 1.5rem', borderBottom: '1px solid var(--color-border)' }}>
                                    <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                                        Top 10 Items by Value
                                    </h3>
                                </div>
                                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                    <thead>
                                        <tr style={{ background: 'var(--color-surface)' }}>
                                            {['SKU', 'Item', 'Qty', 'Avg Cost', 'Total Value'].map(h => (
                                                <th key={h} style={{
                                                    padding: '0.6rem 1rem',
                                                    fontSize: 'var(--text-xs)', fontWeight: 600,
                                                    textTransform: 'uppercase', color: 'var(--color-text-muted)',
                                                    textAlign: h === 'SKU' || h === 'Item' ? 'left' : 'right',
                                                    whiteSpace: 'nowrap',
                                                }}>
                                                    {h}
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {top10.length === 0 && (
                                            <tr>
                                                <td colSpan={5} style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                                    No valuation data.
                                                </td>
                                            </tr>
                                        )}
                                        {top10.map((item, idx) => (
                                            <tr
                                                key={item.id}
                                                style={{
                                                    borderBottom: '1px solid var(--color-border)',
                                                    background: idx % 2 === 1 ? 'var(--color-surface)' : 'transparent',
                                                }}
                                            >
                                                <td style={{ padding: '0.6rem 1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                                                    {item.sku}
                                                </td>
                                                <td style={{ padding: '0.6rem 1rem', fontSize: 'var(--text-sm)', fontWeight: 500, maxWidth: '140px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                    {item.name}
                                                </td>
                                                <td style={{ padding: '0.6rem 1rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                                                    {Number(item.total_quantity || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginLeft: '0.25rem' }}>
                                                        {item.unit_of_measure}
                                                    </span>
                                                </td>
                                                <td style={{ padding: '0.6rem 1rem', textAlign: 'right', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                                                    {formatCurrency(Number(item.average_cost || 0))}
                                                </td>
                                                <td style={{ padding: '0.6rem 1rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 700, color: '#10b981', whiteSpace: 'nowrap' }}>
                                                    {formatCurrency(Number(item.total_value || 0))}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        {/* RIGHT */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                            {/* Recent Stock Movements */}
                            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                                <div style={{
                                    padding: '1.1rem 1.5rem', borderBottom: '1px solid var(--color-border)',
                                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                }}>
                                    <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                                        Recent Stock Movements
                                    </h3>
                                    <button
                                        className="btn btn-outline"
                                        onClick={() => navigate('/inventory/movements')}
                                        style={{ fontSize: 'var(--text-xs)', padding: '0.3rem 0.75rem' }}
                                    >
                                        View All
                                    </button>
                                </div>
                                {movementsList.length === 0 ? (
                                    <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                        No recent movements.
                                    </div>
                                ) : (
                                    movementsList.slice(0, 8).map((mv, idx) => {
                                        const color = getMovementColor(mv.movement_type);
                                        const label = getMovementLabel(mv.movement_type);
                                        const date  = mv.created_at
                                            ? new Date(mv.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
                                            : '—';
                                        const isLast = idx === Math.min(movementsList.length, 8) - 1;
                                        return (
                                            <div
                                                key={mv.id}
                                                style={{
                                                    display: 'flex', alignItems: 'center', gap: '0.75rem',
                                                    padding: '0.75rem 1.5rem',
                                                    borderBottom: isLast ? 'none' : '1px solid var(--color-border)',
                                                }}
                                            >
                                                <span style={{
                                                    display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                                    padding: '0.2rem 0.55rem', borderRadius: '999px',
                                                    background: `${color}18`, color,
                                                    fontSize: 'var(--text-xs)', fontWeight: 700,
                                                    whiteSpace: 'nowrap', flexShrink: 0, minWidth: '84px',
                                                }}>
                                                    <MovementTypeIcon type={mv.movement_type} />
                                                    {label}
                                                </span>
                                                <div style={{ flex: 1, minWidth: 0 }}>
                                                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                        {mv.item_name || '—'}
                                                    </div>
                                                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                        {mv.warehouse_name || '—'}
                                                    </div>
                                                </div>
                                                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                                                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color }}>
                                                        {mv.movement_type === 'OUT' ? '−' : '+'}{Number(mv.quantity || 0).toLocaleString()}
                                                    </div>
                                                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                        {date}
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })
                                )}
                            </div>

                            {/* Reorder Alerts — top 5 */}
                            <div className="card" style={{ padding: 0, overflow: 'hidden', flex: 1 }}>
                                <div style={{
                                    padding: '1.1rem 1.5rem', borderBottom: '1px solid var(--color-border)',
                                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                }}>
                                    <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)', margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        Reorder Alerts
                                        {lowStockCount > 0 && (
                                            <span style={{
                                                padding: '0.1rem 0.5rem', borderRadius: '999px',
                                                background: 'rgba(239,68,68,0.12)', color: '#ef4444',
                                                fontSize: 'var(--text-xs)', fontWeight: 700,
                                            }}>
                                                {lowStockCount}
                                            </span>
                                        )}
                                    </h3>
                                    <button
                                        className="btn btn-outline"
                                        onClick={() => navigate('/inventory/reorder-alerts')}
                                        style={{ fontSize: 'var(--text-xs)', padding: '0.3rem 0.75rem' }}
                                    >
                                        View All
                                    </button>
                                </div>

                                {top5Reorder.length === 0 ? (
                                    <div style={{ padding: '2.5rem', textAlign: 'center' }}>
                                        <CheckCircle size={32} color="#10b981" style={{ marginBottom: '0.5rem' }} />
                                        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>All stock levels are healthy.</div>
                                    </div>
                                ) : (
                                    <div style={{ padding: '1rem 1.5rem' }}>
                                        {top5Reorder.map((alert, idx) => {
                                            const ratio    = alert.reorder_point > 0 ? alert.current_stock / alert.reorder_point : 0;
                                            const pct      = Math.min(ratio * 100, 100);
                                            const barColor = ratio < 0.5 ? '#ef4444' : ratio < 0.75 ? '#f59e0b' : '#10b981';
                                            return (
                                                <div key={alert.id} style={{ marginBottom: idx < top5Reorder.length - 1 ? '1.1rem' : 0 }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.3rem' }}>
                                                        <div style={{ minWidth: 0 }}>
                                                            <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                                {alert.item_name}
                                                            </span>
                                                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginLeft: '0.35rem' }}>
                                                                ({alert.sku})
                                                            </span>
                                                        </div>
                                                        <span style={{ fontSize: 'var(--text-xs)', color: '#ef4444', fontWeight: 700, flexShrink: 0, marginLeft: '0.5rem' }}>
                                                            {alert.current_stock} / {alert.reorder_point}
                                                        </span>
                                                    </div>
                                                    <div style={{ height: '6px', background: 'var(--color-border)', borderRadius: '3px', overflow: 'hidden' }}>
                                                        <div style={{
                                                            height: '100%', width: `${pct}%`,
                                                            background: barColor, borderRadius: '3px',
                                                            transition: 'width 0.4s ease',
                                                        }} />
                                                    </div>
                                                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '0.2rem' }}>
                                                        {alert.warehouse || '—'} · Suggest: {alert.suggested_quantity ?? '—'}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* ── Quick Navigation ─────────────────────────────────────── */}
                    <div>
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)', marginBottom: '1rem' }}>
                            Quick Access
                        </h3>
                        <div style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fill, minmax(175px, 1fr))',
                            gap: '1rem',
                        }}>
                            {navCards.map(card => (
                                <button
                                    key={card.label}
                                    onClick={() => navigate(card.path)}
                                    style={{
                                        display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
                                        gap: '0.5rem', padding: '1.1rem 1.2rem',
                                        background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                                        borderRadius: '10px', cursor: 'pointer', textAlign: 'left',
                                        transition: 'border-color 0.15s, box-shadow 0.15s',
                                    }}
                                    onMouseEnter={e => {
                                        (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--color-primary)';
                                        (e.currentTarget as HTMLButtonElement).style.boxShadow   = '0 0 0 3px rgba(46,56,152,0.08)';
                                    }}
                                    onMouseLeave={e => {
                                        (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--color-border)';
                                        (e.currentTarget as HTMLButtonElement).style.boxShadow   = 'none';
                                    }}
                                >
                                    <div style={{
                                        width: '32px', height: '32px', borderRadius: '7px',
                                        background: 'rgba(46,56,152,0.08)',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    }}>
                                        <card.icon size={16} color="var(--color-primary)" />
                                    </div>
                                    <div>
                                        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-text)', marginBottom: '0.15rem' }}>
                                            {card.label}
                                        </div>
                                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', lineHeight: 1.4 }}>
                                            {card.desc}
                                        </div>
                                    </div>
                                </button>
                            ))}
                        </div>
                    </div>

                </main>
            </div>
        </>
    );
};

export default InventoryDashboard;
