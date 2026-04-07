import { useState, useMemo } from 'react';
import { useStockByWarehouseList, useWarehouses } from '../hooks/useInventory';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Package, MapPin, Search, Layers, Grid3X3 } from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

interface StockEntry {
    id: number;
    item: number;
    item_name: string;
    item_sku: string;
    warehouse: number;
    warehouse_name: string;
    quantity: number;
    reserved_quantity: number;
    available_quantity: number;
}

interface Warehouse {
    id: number;
    name: string;
    location?: string;
}

type GroupMode = 'item' | 'warehouse';
type StockStatusFilter = 'All' | 'In Stock' | 'Low' | 'Empty';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getEntryStatus(entry: StockEntry): 'Available' | 'Partially Reserved' | 'Fully Reserved' | 'Empty' {
    const qty       = Number(entry.quantity || 0);
    const reserved  = Number(entry.reserved_quantity || 0);
    const available = Number(entry.available_quantity ?? qty - reserved);
    if (qty <= 0) return 'Empty';
    if (reserved <= 0) return 'Available';
    if (available <= 0) return 'Fully Reserved';
    return 'Partially Reserved';
}

function resolveAvailable(entry: StockEntry): number {
    const qty      = Number(entry.quantity || 0);
    const reserved = Number(entry.reserved_quantity || 0);
    if (entry.available_quantity !== undefined && entry.available_quantity !== null) {
        return Number(entry.available_quantity);
    }
    return Math.max(0, qty - reserved);
}

function healthPct(entry: StockEntry): number {
    const qty  = Number(entry.quantity || 0);
    const avail = resolveAvailable(entry);
    if (qty <= 0) return 0;
    return Math.min(100, Math.max(0, (avail / qty) * 100));
}

function healthColor(pct: number): string {
    if (pct <= 0)    return '#ef4444';
    if (pct < 50)   return '#f97316';
    if (pct < 100)  return '#f59e0b';
    return '#10b981';
}

// ─── Sub-components ───────────────────────────────────────────────────────────

const StatusBadge = ({ status }: { status: ReturnType<typeof getEntryStatus> }) => {
    const styles: Record<string, React.CSSProperties> = {
        Available:           { background: 'rgba(16,185,129,0.15)',  color: '#10b981' },
        'Partially Reserved': { background: 'rgba(245,158,11,0.15)',  color: '#f59e0b' },
        'Fully Reserved':    { background: 'rgba(239,68,68,0.15)',   color: '#ef4444' },
        Empty:               { background: 'rgba(156,163,175,0.2)',  color: '#9ca3af' },
    };
    return (
        <span style={{ padding: '0.2rem 0.6rem', borderRadius: '99px', fontSize: 'var(--text-xs)', fontWeight: 600, ...styles[status] }}>
            {status}
        </span>
    );
};

const HealthBar = ({ entry }: { entry: StockEntry }) => {
    const pct   = healthPct(entry);
    const color = healthColor(pct);
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: '80px' }}>
            <div style={{ flex: 1, height: '6px', borderRadius: '3px', background: 'var(--color-border)', overflow: 'hidden' }}>
                <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: '3px', transition: 'width 0.3s' }} />
            </div>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', minWidth: '32px', textAlign: 'right' }}>{pct.toFixed(0)}%</span>
        </div>
    );
};

// ─── Row ──────────────────────────────────────────────────────────────────────

const StockRow = ({ entry, showItem, showWarehouse }: {
    entry: StockEntry;
    showItem: boolean;
    showWarehouse: boolean;
}) => {
    const qty      = Number(entry.quantity || 0);
    const reserved = Number(entry.reserved_quantity || 0);
    const available = resolveAvailable(entry);
    const status   = getEntryStatus(entry);

    return (
        <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
            {showItem && (
                <td style={{ padding: '0.75rem 1rem' }}>
                    <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>{entry.item_name}</div>
                    <div style={{ fontFamily: 'monospace', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '2px' }}>{entry.item_sku}</div>
                </td>
            )}
            {showWarehouse && (
                <td style={{ padding: '0.75rem 1rem' }}>
                    <div style={{ fontWeight: 500, fontSize: 'var(--text-sm)' }}>{entry.warehouse_name}</div>
                </td>
            )}
            <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)' }}>
                {qty.toFixed(2)}
            </td>
            <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                {reserved > 0 ? (
                    <span style={{ padding: '0.2rem 0.6rem', borderRadius: '99px', fontSize: 'var(--text-xs)', fontWeight: 600, background: 'rgba(245,158,11,0.15)', color: '#f59e0b' }}>
                        {reserved.toFixed(2)}
                    </span>
                ) : (
                    <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>—</span>
                )}
            </td>
            <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)', color: available > 0 ? 'var(--color-success)' : 'var(--color-error)' }}>
                {available.toFixed(2)}
            </td>
            <td style={{ padding: '0.75rem 1rem', minWidth: '120px' }}>
                <HealthBar entry={entry} />
            </td>
            <td style={{ padding: '0.75rem 1rem' }}>
                <StatusBadge status={status} />
            </td>
        </tr>
    );
};

// ─── Component ────────────────────────────────────────────────────────────────

const StockLevelList = () => {
    const { data: stocks, isLoading } = useStockByWarehouseList();
    const { data: warehousesRaw } = useWarehouses();

    const [search, setSearch] = useState('');
    const [warehouseFilter, setWarehouseFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState<StockStatusFilter>('All');
    const [groupMode, setGroupMode] = useState<GroupMode>('warehouse');

    const stocksList: StockEntry[] = Array.isArray((stocks as any)?.results)
        ? (stocks as any).results
        : Array.isArray(stocks) ? stocks as any : [];

    const warehouses: Warehouse[] = Array.isArray((warehousesRaw as any)?.results)
        ? (warehousesRaw as any).results
        : Array.isArray(warehousesRaw) ? warehousesRaw as any : [];

    // ── Summary stats ─────────────────────────────────────────────────────────

    const totalEntries   = stocksList.length;
    const totalAvailable = stocksList.reduce((s, e) => s + resolveAvailable(e), 0);
    const totalReserved  = stocksList.reduce((s, e) => s + Number(e.reserved_quantity || 0), 0);
    const warehouseCount = new Set(stocksList.map(e => e.warehouse)).size;

    // ── Filter ────────────────────────────────────────────────────────────────

    const filtered = useMemo(() => {
        return stocksList.filter(entry => {
            const q = search.toLowerCase();
            if (q && !entry.item_name?.toLowerCase().includes(q) && !entry.item_sku?.toLowerCase().includes(q)) return false;
            if (warehouseFilter && String(entry.warehouse) !== warehouseFilter) return false;
            if (statusFilter !== 'All') {
                const s = getEntryStatus(entry);
                if (statusFilter === 'In Stock' && s === 'Empty') return false;
                if (statusFilter === 'Low' && s !== 'Partially Reserved') return false;
                if (statusFilter === 'Empty' && s !== 'Empty') return false;
            }
            return true;
        });
    }, [stocksList, search, warehouseFilter, statusFilter]);

    // ── Group ─────────────────────────────────────────────────────────────────

    type GroupData = {
        key: string;
        label: string;
        sublabel?: string;
        totalQty: number;
        entries: StockEntry[];
    };

    const groups: GroupData[] = useMemo(() => {
        if (groupMode === 'warehouse') {
            const map = new Map<number, GroupData>();
            for (const e of filtered) {
                if (!map.has(e.warehouse)) {
                    const wh = warehouses.find(w => w.id === e.warehouse);
                    map.set(e.warehouse, {
                        key: String(e.warehouse),
                        label: e.warehouse_name || `Warehouse ${e.warehouse}`,
                        sublabel: wh?.location,
                        totalQty: 0,
                        entries: [],
                    });
                }
                const g = map.get(e.warehouse)!;
                g.entries.push(e);
                g.totalQty += Number(e.quantity || 0);
            }
            return Array.from(map.values());
        } else {
            const map = new Map<number, GroupData>();
            for (const e of filtered) {
                if (!map.has(e.item)) {
                    map.set(e.item, {
                        key: String(e.item),
                        label: e.item_name,
                        sublabel: e.item_sku,
                        totalQty: 0,
                        entries: [],
                    });
                }
                const g = map.get(e.item)!;
                g.entries.push(e);
                g.totalQty += Number(e.quantity || 0);
            }
            return Array.from(map.values());
        }
    }, [filtered, groupMode, warehouses]);

    if (isLoading) return <LoadingScreen message="Loading stock levels..." />;

    const thStyle: React.CSSProperties = {
        padding: '0.75rem 1rem',
        fontSize: 'var(--text-xs)',
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        color: 'var(--color-text-muted)',
        whiteSpace: 'nowrap',
        background: 'var(--color-surface)',
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }} className="animate-fade">
                <PageHeader
                    title="Stock Levels"
                    subtitle="Multi-warehouse stock level overview with availability and reservations."
                    icon={<Package size={22} />}
                />

                {/* ── Summary Cards ────────────────────────────────────────── */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.25rem', marginBottom: '2rem' }}>
                    {[
                        { label: 'Total Stock Entries', value: totalEntries,                color: 'var(--color-primary)',  bg: 'rgba(59,130,246,0.12)'  },
                        { label: 'Total Available',     value: totalAvailable.toFixed(2),   color: 'var(--color-success)',  bg: 'rgba(16,185,129,0.12)'  },
                        { label: 'Total Reserved',      value: totalReserved.toFixed(2),    color: '#f59e0b',               bg: 'rgba(245,158,11,0.12)'  },
                        { label: 'Warehouses',          value: warehouseCount,              color: '#8b5cf6',               bg: 'rgba(139,92,246,0.12)'  },
                    ].map(({ label, value, color, bg }) => (
                        <div key={label} className="card" style={{ borderLeft: `4px solid ${color}` }}>
                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>{label}</div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                <div style={{ padding: '0.5rem', borderRadius: '0.5rem', background: bg, flexShrink: 0 }}>
                                    <Package size={18} style={{ color }} />
                                </div>
                                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 800, lineHeight: 1 }}>{value}</div>
                            </div>
                        </div>
                    ))}
                </div>

                {/* ── Filter bar ───────────────────────────────────────────── */}
                <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                    <div style={{ position: 'relative', flex: 1, minWidth: '220px' }}>
                        <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)', pointerEvents: 'none' }} />
                        <input
                            type="text"
                            className="input"
                            placeholder="Search item name or SKU..."
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                            style={{ paddingLeft: '2.25rem', width: '100%' }}
                        />
                    </div>

                    <select className="input" value={warehouseFilter} onChange={e => setWarehouseFilter(e.target.value)} style={{ minWidth: '170px' }}>
                        <option value="">All Warehouses</option>
                        {warehouses.map(w => (
                            <option key={w.id} value={String(w.id)}>{w.name}</option>
                        ))}
                    </select>

                    <div style={{ display: 'flex', gap: '0.4rem' }}>
                        {(['All', 'In Stock', 'Low', 'Empty'] as StockStatusFilter[]).map(s => (
                            <button
                                key={s}
                                onClick={() => setStatusFilter(s)}
                                style={{
                                    padding: '0.4rem 0.85rem',
                                    borderRadius: '99px',
                                    border: statusFilter === s ? 'none' : '1px solid var(--color-border)',
                                    cursor: 'pointer',
                                    fontSize: 'var(--text-xs)',
                                    fontWeight: 600,
                                    background: statusFilter === s ? 'var(--color-primary)' : 'transparent',
                                    color: statusFilter === s ? '#fff' : 'var(--color-text-muted)',
                                    transition: 'all 0.15s',
                                }}
                            >{s}</button>
                        ))}
                    </div>

                    {/* Group toggle */}
                    <div style={{ marginLeft: 'auto', display: 'flex', border: '1px solid var(--color-border)', borderRadius: '8px', overflow: 'hidden' }}>
                        <button
                            onClick={() => setGroupMode('item')}
                            style={{ padding: '0.4rem 0.85rem', border: 'none', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.35rem', background: groupMode === 'item' ? 'var(--color-primary)' : 'transparent', color: groupMode === 'item' ? '#fff' : 'var(--color-text-muted)', transition: 'all 0.15s' }}
                        >
                            <Layers size={14} /> Group by Item
                        </button>
                        <button
                            onClick={() => setGroupMode('warehouse')}
                            style={{ padding: '0.4rem 0.85rem', border: 'none', borderLeft: '1px solid var(--color-border)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.35rem', background: groupMode === 'warehouse' ? 'var(--color-primary)' : 'transparent', color: groupMode === 'warehouse' ? '#fff' : 'var(--color-text-muted)', transition: 'all 0.15s' }}
                        >
                            <Grid3X3 size={14} /> Group by Warehouse
                        </button>
                    </div>
                </div>

                {/* ── Grouped content ──────────────────────────────────────── */}
                {groups.length === 0 ? (
                    <div className="card" style={{ textAlign: 'center', padding: '3.5rem' }}>
                        <Package size={40} style={{ opacity: 0.2, display: 'block', margin: '0 auto 0.75rem' }} />
                        <p style={{ color: 'var(--color-text-muted)' }}>No stock entries found.</p>
                    </div>
                ) : (
                    groups.map(group => (
                        <div key={group.key} style={{ marginBottom: '2rem' }}>
                            {/* Group header */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    {groupMode === 'warehouse'
                                        ? <MapPin size={16} style={{ color: 'var(--color-primary)' }} />
                                        : <Package size={16} style={{ color: 'var(--color-primary)' }} />
                                    }
                                    <span style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}>{group.label}</span>
                                    {group.sublabel && (
                                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontFamily: groupMode === 'item' ? 'monospace' : 'inherit' }}>
                                            {group.sublabel}
                                        </span>
                                    )}
                                </div>
                                <span style={{ fontSize: 'var(--text-xs)', background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: '99px', padding: '0.15rem 0.6rem', color: 'var(--color-text-muted)', fontWeight: 600 }}>
                                    {group.entries.length} {groupMode === 'warehouse' ? 'item' : 'warehouse'}{group.entries.length !== 1 ? 's' : ''}
                                </span>
                                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                    Total qty: <strong style={{ color: 'var(--color-text)' }}>{group.totalQty.toFixed(2)}</strong>
                                </span>
                            </div>

                            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                                <div style={{ overflowX: 'auto' }}>
                                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                                        <thead>
                                            <tr style={{ borderBottom: '2px solid var(--color-border)' }}>
                                                {groupMode === 'warehouse' && (
                                                    <th style={{ ...thStyle, textAlign: 'left' }}>Item</th>
                                                )}
                                                {groupMode === 'item' && (
                                                    <th style={{ ...thStyle, textAlign: 'left' }}>Warehouse</th>
                                                )}
                                                <th style={{ ...thStyle, textAlign: 'right' }}>On Hand</th>
                                                <th style={{ ...thStyle, textAlign: 'right' }}>Reserved</th>
                                                <th style={{ ...thStyle, textAlign: 'right' }}>Available</th>
                                                <th style={{ ...thStyle }}>Stock Health</th>
                                                <th style={{ ...thStyle }}>Status</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {group.entries.map(entry => (
                                                <StockRow
                                                    key={entry.id}
                                                    entry={entry}
                                                    showItem={groupMode === 'warehouse'}
                                                    showWarehouse={groupMode === 'item'}
                                                />
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    ))
                )}
            </main>
        </div>
    );
};

export default StockLevelList;
