import { useState, useMemo } from 'react';
import {
    useStockMovements,
    useItems,
    useWarehouses,
    useCreateStockMovement,
} from '../hooks/useInventory';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import {
    SlidersHorizontal,
    Plus,
    Search,
    TrendingUp,
    TrendingDown,
    Settings,
    CheckCircle,
    X,
    Package,
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

interface StockMovement {
    id: number;
    movement_type: string;
    item: number;
    item_name: string;
    warehouse: number;
    warehouse_name: string;
    quantity: number;
    unit_price: number;
    reference_number: string;
    remarks: string;
    gl_posted: boolean;
    journal_entry_number?: string;
    created_at: string;
    batch?: number;
}

type DateRange = 'today' | '7days' | '30days' | 'all';
type AdjType  = 'IN' | 'OUT' | 'ADJ';

// ─── Helpers ──────────────────────────────────────────────────────────────────

const MOVEMENT_META: Record<string, { label: string; bg: string; color: string; Icon: React.FC<{ size?: number }> }> = {
    IN:  { label: 'Stock In',     bg: 'rgba(16,185,129,0.12)', color: '#10b981', Icon: TrendingUp  },
    OUT: { label: 'Stock Out',    bg: 'rgba(239,68,68,0.12)',  color: '#ef4444', Icon: TrendingDown },
    ADJ: { label: 'Adjustment',  bg: 'rgba(59,130,246,0.12)', color: '#3b82f6', Icon: Settings     },
};

const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: 'var(--text-xs)',
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color: 'var(--color-text-muted)',
    marginBottom: '0.375rem',
};

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

const tdStyle: React.CSSProperties = {
    padding: '0.75rem 1rem',
    fontSize: 'var(--text-sm)',
    color: 'var(--color-text)',
    borderBottom: '1px solid var(--color-border)',
};

function formatDate(dateStr: string) {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function isInDateRange(dateStr: string, range: DateRange): boolean {
    if (range === 'all') return true;
    const date     = new Date(dateStr);
    const now      = new Date();
    const today    = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    if (range === 'today')  return date >= today;
    if (range === '7days')  { const d = new Date(today); d.setDate(d.getDate() - 6);  return date >= d; }
    if (range === '30days') { const d = new Date(today); d.setDate(d.getDate() - 29); return date >= d; }
    return true;
}

// ─── Component ────────────────────────────────────────────────────────────────

const InventoryAdjustment = () => {
    const { formatCurrency } = useCurrency();

    // ── Filter state
    const [search,         setSearch]         = useState('');
    const [typeFilter,     setTypeFilter]     = useState('');
    const [warehouseFilter,setWarehouseFilter] = useState('');
    const [dateRange,      setDateRange]      = useState<DateRange>('all');
    const [currentPage,    setCurrentPage]    = useState(1);
    const pageSize = 20;

    // ── Form panel
    const [showPanel,  setShowPanel]  = useState(false);
    const [formError,  setFormError]  = useState<string | null>(null);
    const [adjType,    setAdjType]    = useState<AdjType>('IN');

    // ── Adjustment form state
    const [form, setForm] = useState({
        item:             '',
        warehouse:        '',
        quantity:         '',
        unit_price:       '',
        reference_number: '',
        remarks:          '',
        batch:            '',
    });

    const queryFilters = useMemo(() => ({
        page:          currentPage,
        page_size:     pageSize,
        search:        search || undefined,
        // Only fetch IN/OUT/ADJ — never TRF (that lives on the Transfers page).
        // When a specific type filter is active use it; otherwise tell the backend to
        // exclude TRF entirely so pagination counts are accurate.
        movement_type: typeFilter || undefined,
        exclude_type:  typeFilter ? undefined : 'TRF',
        warehouse:     warehouseFilter || undefined,
    }), [currentPage, search, typeFilter, warehouseFilter]);

    const { data: movements, isLoading } = useStockMovements(queryFilters);
    const { data: items }                = useItems();
    const { data: warehouses }           = useWarehouses();
    const createMovement                 = useCreateStockMovement();

    const rawList: StockMovement[] = useMemo(() => {
        const all: StockMovement[] = movements?.results || movements || [];
        // Exclude any TRF movements that may slip through if no type filter active
        return all.filter(m => m.movement_type !== 'TRF');
    }, [movements]);

    const totalCount  = movements?.count || (Array.isArray(movements) ? movements.length : 0);
    const totalPages  = Math.ceil(totalCount / pageSize);
    const itemsList   = items?.results      || items      || [];
    const warehousesList = warehouses?.results || warehouses || [];

    const movementsList = useMemo(
        () => rawList.filter(m => isInDateRange(m.created_at, dateRange)),
        [rawList, dateRange]
    );

    // ── Summary stats
    const totalIn   = useMemo(() => rawList.filter(m => m.movement_type === 'IN') .reduce((s, m) => s + Number(m.quantity), 0), [rawList]);
    const totalOut  = useMemo(() => rawList.filter(m => m.movement_type === 'OUT').reduce((s, m) => s + Number(m.quantity), 0), [rawList]);
    const totalAdj  = useMemo(() => rawList.filter(m => m.movement_type === 'ADJ').length, [rawList]);
    const totalVal  = useMemo(() => rawList.reduce((s, m) => s + Number(m.quantity) * Number(m.unit_price), 0), [rawList]);

    const resetForm = () => setForm({ item: '', warehouse: '', quantity: '', unit_price: '', reference_number: '', remarks: '', batch: '' });

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError(null);
        try {
            await createMovement.mutateAsync({
                movement_type:    adjType,
                item:             Number(form.item),
                warehouse:        Number(form.warehouse),
                quantity:         parseFloat(form.quantity),
                unit_price:       parseFloat(form.unit_price || '0'),
                reference_number: form.reference_number || undefined,
                remarks:          form.remarks          || undefined,
                batch:            form.batch ? Number(form.batch) : undefined,
            });
            setShowPanel(false);
            resetForm();
        } catch (err: any) {
            const msg =
                err?.response?.data?.detail ||
                err?.response?.data?.error  ||
                (typeof err?.response?.data === 'object' ? JSON.stringify(err.response.data) : null) ||
                err?.message ||
                'Failed to save adjustment';
            setFormError(msg);
        }
    };

    if (isLoading) return <LoadingScreen message="Loading adjustments..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>

                <PageHeader
                    title="Inventory Adjustments"
                    subtitle="Record stock receipts, stock issues, and quantity adjustments"
                    icon={<SlidersHorizontal size={22} />}
                    actions={
                        <button
                            className="btn btn-primary"
                            onClick={() => { setShowPanel(v => !v); setFormError(null); }}
                            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}
                        >
                            <Plus size={16} />
                            New Adjustment
                        </button>
                    }
                />

                {/* ── Summary Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
                    {[
                        { label: 'Stock In (units)',  value: totalIn.toLocaleString(undefined, { maximumFractionDigits: 2 }),  color: '#10b981' },
                        { label: 'Stock Out (units)', value: totalOut.toLocaleString(undefined, { maximumFractionDigits: 2 }), color: '#ef4444' },
                        { label: 'Adjustments',       value: totalAdj.toLocaleString(),                                        color: '#3b82f6' },
                        { label: 'Page Value',        value: formatCurrency(totalVal),                                         color: 'var(--color-primary)' },
                    ].map(({ label, value, color }) => (
                        <div key={label} className="card" style={{ padding: '1.25rem 1.5rem' }}>
                            <span style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>
                                {label}
                            </span>
                            <span style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color }}>{value}</span>
                        </div>
                    ))}
                </div>

                {/* ── Error Banner */}
                {formError && (
                    <div style={{ padding: '0.75rem 1rem', background: 'rgba(239,68,68,0.08)', color: 'var(--color-error)', borderRadius: '8px', marginBottom: '1rem', border: '1px solid rgba(239,68,68,0.2)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span>{formError}</span>
                        <button onClick={() => setFormError(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-error)' }}><X size={16} /></button>
                    </div>
                )}

                {/* ── New Adjustment Panel */}
                {showPanel && (
                    <div className="card animate-fade" style={{ marginBottom: '2rem', padding: '1.5rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                            <div>
                                <div style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)', marginBottom: '0.25rem' }}>
                                    New Inventory Adjustment
                                </div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                    Select the adjustment type, then fill in the details below.
                                </div>
                            </div>
                            <button onClick={() => { setShowPanel(false); setFormError(null); }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                                <X size={18} />
                            </button>
                        </div>

                        <form onSubmit={handleSubmit}>
                            {/* Type selector */}
                            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
                                {(['IN', 'OUT', 'ADJ'] as AdjType[]).map(type => {
                                    const meta   = MOVEMENT_META[type];
                                    const active = adjType === type;
                                    return (
                                        <button
                                            key={type}
                                            type="button"
                                            onClick={() => setAdjType(type)}
                                            style={{
                                                padding: '0.5rem 1.25rem',
                                                borderRadius: '8px',
                                                border:      active ? 'none' : '1px solid var(--color-border)',
                                                background:  active ? meta.color : 'transparent',
                                                color:       active ? '#fff' : 'var(--color-text-muted)',
                                                cursor:      'pointer',
                                                fontWeight:  600,
                                                fontSize:    'var(--text-sm)',
                                                fontFamily:  'inherit',
                                                display:     'inline-flex',
                                                alignItems:  'center',
                                                gap:         '0.4rem',
                                            }}
                                        >
                                            <meta.Icon size={14} /> {meta.label}
                                        </button>
                                    );
                                })}
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div>
                                    <label style={labelStyle}>Item <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <select className="input" value={form.item} onChange={e => {
                                        const newItemId = e.target.value;
                                        // FIX #27: auto-populate unit_price from the selected item's
                                        // average cost so GL journals post at a non-zero value.
                                        const selectedItem = itemsList.find((i: any) => String(i.id) === newItemId);
                                        const autoCost = selectedItem
                                            ? String(selectedItem.average_cost || selectedItem.cost_price || '')
                                            : form.unit_price;
                                        setForm({ ...form, item: newItemId, unit_price: autoCost });
                                    }} required>
                                        <option value="">Select item...</option>
                                        {itemsList.map((i: any) => (
                                            <option key={i.id} value={i.id}>{i.sku} — {i.name}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label style={labelStyle}>Warehouse <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <select className="input" value={form.warehouse} onChange={e => setForm({ ...form, warehouse: e.target.value })} required>
                                        <option value="">Select warehouse...</option>
                                        {warehousesList.map((w: any) => (
                                            <option key={w.id} value={w.id}>{w.name}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label style={labelStyle}>Quantity <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <input type="number" step="0.01" min="0.01" className="input" placeholder="0" value={form.quantity} onChange={e => setForm({ ...form, quantity: e.target.value })} required />
                                </div>
                                <div>
                                    <label style={labelStyle}>Unit Price</label>
                                    <input type="number" step="0.01" min="0" className="input" placeholder="0.00" value={form.unit_price} onChange={e => setForm({ ...form, unit_price: e.target.value })} />
                                </div>
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
                                <div>
                                    <label style={labelStyle}>Reference Number</label>
                                    <input type="text" className="input" placeholder="ADJ-0001" value={form.reference_number} onChange={e => setForm({ ...form, reference_number: e.target.value })} />
                                </div>
                                <div>
                                    <label style={labelStyle}>Remarks</label>
                                    <input type="text" className="input" placeholder="Reason for adjustment..." value={form.remarks} onChange={e => setForm({ ...form, remarks: e.target.value })} />
                                </div>
                                <div>
                                    <label style={labelStyle}>Batch (optional)</label>
                                    <input type="number" className="input" placeholder="Batch ID" value={form.batch} onChange={e => setForm({ ...form, batch: e.target.value })} />
                                </div>
                            </div>

                            {/* Contextual tip */}
                            <div style={{ padding: '0.75rem 1rem', borderRadius: '8px', background: 'var(--color-surface)', border: '1px solid var(--color-border)', marginBottom: '1.25rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                {adjType === 'IN'  && '📦 Stock In — Increases on-hand quantity. Use for opening stock, supplier deliveries not via a PO, or found stock.'}
                                {adjType === 'OUT' && '📤 Stock Out — Decreases on-hand quantity. Use for consumption, samples, damaged goods written off.'}
                                {adjType === 'ADJ' && '⚖️ Adjustment — Use for quantity corrections after a physical count or cycle count. Does not affect cost layer history.'}
                            </div>

                            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                                <button type="button" className="btn btn-outline" onClick={() => { setShowPanel(false); resetForm(); }}>Cancel</button>
                                <button
                                    type="submit"
                                    className="btn btn-primary"
                                    disabled={createMovement.isPending}
                                    style={{ minWidth: '140px' }}
                                >
                                    {createMovement.isPending ? 'Saving...' : `Save ${MOVEMENT_META[adjType].label}`}
                                </button>
                            </div>
                        </form>
                    </div>
                )}

                {/* ── Filter Bar */}
                <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                    {/* Search */}
                    <div style={{ flex: 1, minWidth: '200px', position: 'relative' }}>
                        <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)', pointerEvents: 'none' }} />
                        <input
                            type="text"
                            placeholder="Search by item name or reference..."
                            value={search}
                            onChange={e => { setSearch(e.target.value); setCurrentPage(1); }}
                            style={{ width: '100%', padding: '0.625rem 0.75rem 0.625rem 2.5rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}
                        />
                    </div>

                    {/* Type filter */}
                    <div style={{ display: 'flex', gap: '0.375rem' }}>
                        {[['', 'All'], ['IN', 'IN'], ['OUT', 'OUT'], ['ADJ', 'ADJ']].map(([val, label]) => (
                            <button
                                key={val}
                                onClick={() => { setTypeFilter(val); setCurrentPage(1); }}
                                style={{
                                    padding: '0.5rem 0.875rem', borderRadius: '8px',
                                    border:     typeFilter === val ? 'none' : '1px solid var(--color-border)',
                                    background: typeFilter === val ? 'var(--color-primary)' : 'transparent',
                                    color:      typeFilter === val ? '#fff' : 'var(--color-text-muted)',
                                    cursor: 'pointer', fontWeight: 600, fontSize: 'var(--text-xs)', fontFamily: 'inherit',
                                }}
                            >
                                {label}
                            </button>
                        ))}
                    </div>

                    {/* Warehouse filter */}
                    <select
                        value={warehouseFilter}
                        onChange={e => { setWarehouseFilter(e.target.value); setCurrentPage(1); }}
                        style={{ padding: '0.625rem 1rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)', minWidth: '160px' }}
                    >
                        <option value="">All Warehouses</option>
                        {warehousesList.map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
                    </select>

                    {/* Date range */}
                    <div style={{ display: 'flex', gap: '0.375rem' }}>
                        {([['today', 'Today'], ['7days', 'Last 7d'], ['30days', 'Last 30d'], ['all', 'All']] as [DateRange, string][]).map(([val, label]) => (
                            <button
                                key={val}
                                onClick={() => setDateRange(val)}
                                style={{
                                    padding: '0.5rem 0.875rem', borderRadius: '8px',
                                    border:     dateRange === val ? 'none' : '1px solid var(--color-border)',
                                    background: dateRange === val ? 'var(--color-primary)' : 'transparent',
                                    color:      dateRange === val ? '#fff' : 'var(--color-text-muted)',
                                    cursor: 'pointer', fontWeight: 600, fontSize: 'var(--text-xs)', fontFamily: 'inherit',
                                }}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* ── Table */}
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ textAlign: 'left' }}>
                                    <th style={thStyle}>Type</th>
                                    <th style={thStyle}>Item</th>
                                    <th style={thStyle}>Warehouse</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Quantity</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Unit Price</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Value</th>
                                    <th style={thStyle}>Reference</th>
                                    <th style={{ ...thStyle, textAlign: 'center' }}>GL Posted</th>
                                    <th style={thStyle}>Remarks</th>
                                    <th style={thStyle}>Date</th>
                                </tr>
                            </thead>
                            <tbody>
                                {movementsList.length === 0 ? (
                                    <tr>
                                        <td colSpan={10} style={{ padding: '4rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                            <Package size={48} style={{ margin: '0 auto 1rem', opacity: 0.2, display: 'block' }} />
                                            <p style={{ fontWeight: 500 }}>No adjustments found</p>
                                            <p style={{ fontSize: 'var(--text-sm)', marginTop: '0.25rem' }}>
                                                Click <strong>New Adjustment</strong> to record a stock in, out, or quantity adjustment.
                                            </p>
                                        </td>
                                    </tr>
                                ) : (
                                    movementsList.map(m => {
                                        const meta     = MOVEMENT_META[m.movement_type] ?? MOVEMENT_META.ADJ;
                                        const qtyColor = m.movement_type === 'IN' ? '#10b981' : m.movement_type === 'OUT' ? '#ef4444' : '#3b82f6';
                                        const value    = Number(m.quantity) * Number(m.unit_price);

                                        return (
                                            <tr key={m.id} style={{ transition: 'background 0.15s' }}>
                                                <td style={tdStyle}>
                                                    <span style={{
                                                        display: 'inline-flex', alignItems: 'center', gap: '0.35rem',
                                                        padding: '0.25rem 0.65rem', borderRadius: '9999px',
                                                        background: meta.bg, color: meta.color,
                                                        fontSize: 'var(--text-xs)', fontWeight: 700, whiteSpace: 'nowrap',
                                                    }}>
                                                        <meta.Icon size={12} /> {meta.label}
                                                    </span>
                                                </td>
                                                <td style={{ ...tdStyle, fontWeight: 600 }}>{m.item_name}</td>
                                                <td style={{ ...tdStyle, color: 'var(--color-text-muted)' }}>{m.warehouse_name}</td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: qtyColor }}>
                                                    {m.movement_type === 'OUT' ? '−' : '+'}{Math.abs(Number(m.quantity))}
                                                </td>
                                                <td style={{ ...tdStyle, textAlign: 'right', color: 'var(--color-text-muted)' }}>
                                                    {Number(m.unit_price) > 0 ? formatCurrency(Number(m.unit_price)) : '—'}
                                                </td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600, color: 'var(--color-text)' }}>
                                                    {value > 0 ? formatCurrency(value) : '—'}
                                                </td>
                                                <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 'var(--text-xs)', color: m.reference_number ? 'var(--color-text)' : 'var(--color-text-muted)' }}>
                                                    {m.reference_number || '—'}
                                                </td>
                                                <td style={{ ...tdStyle, textAlign: 'center' }}>
                                                    {m.gl_posted
                                                        ? <CheckCircle size={16} style={{ color: '#10b981' }} />
                                                        : <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>—</span>
                                                    }
                                                </td>
                                                <td style={{ ...tdStyle, color: 'var(--color-text-muted)', maxWidth: '200px' }}>
                                                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }} title={m.remarks}>
                                                        {m.remarks ? (m.remarks.length > 45 ? m.remarks.slice(0, 45) + '…' : m.remarks) : '—'}
                                                    </span>
                                                </td>
                                                <td style={{ ...tdStyle, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                                                    {formatDate(m.created_at)}
                                                </td>
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>

                {/* ── Pagination */}
                {totalPages > 1 && (
                    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.75rem', marginTop: '1.5rem' }}>
                        <button className="btn btn-outline" disabled={currentPage <= 1} onClick={() => setCurrentPage(p => p - 1)}>Previous</button>
                        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                            Page {currentPage} of {totalPages} · {totalCount} total
                        </span>
                        <button className="btn btn-outline" disabled={currentPage >= totalPages} onClick={() => setCurrentPage(p => p + 1)}>Next</button>
                    </div>
                )}

            </main>
        </div>
    );
};

export default InventoryAdjustment;
