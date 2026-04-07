import { useState, useMemo } from 'react';
import {
    useStockMovements,
    useItems,
    useWarehouses,
    useStockTransfer,
    useReceiveTransfer,
    useStockByWarehouse,
} from '../hooks/useInventory';
import { useDialog } from '../../../hooks/useDialog';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import {
    ArrowRightLeft,
    Plus,
    Search,
    CheckCircle,
    X,
    Package,
    PackageCheck,
    Clock,
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

interface StockMovement {
    id: number;
    movement_type: string;
    item: number;
    item_name: string;
    warehouse: number;
    warehouse_name: string;
    to_warehouse?: number;
    to_warehouse_name?: string;
    quantity: number;
    unit_price: number;
    reference_number: string;
    remarks: string;
    gl_posted: boolean;
    transfer_status?: string;
    journal_entry_number?: string;
    receive_journal_number?: string;
    created_at: string;
    batch?: number;
}

type DateRange = 'today' | '7days' | '30days' | 'all';

// ─── Helpers ──────────────────────────────────────────────────────────────────

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
    const date        = new Date(dateStr);
    const now         = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    if (range === 'today')  return date >= startOfToday;
    if (range === '7days')  { const d = new Date(startOfToday); d.setDate(d.getDate() - 6);  return date >= d; }
    if (range === '30days') { const d = new Date(startOfToday); d.setDate(d.getDate() - 29); return date >= d; }
    return true;
}

// ─── Component ────────────────────────────────────────────────────────────────

const StockMovementList = () => {
    const { showAlert, showConfirm } = useDialog();
    const { formatCurrency } = useCurrency();

    // ── Filter state
    const [search,          setSearch]          = useState('');
    const [warehouseFilter, setWarehouseFilter] = useState('');
    const [dateRange,       setDateRange]       = useState<DateRange>('all');
    const [currentPage,     setCurrentPage]     = useState(1);
    const pageSize = 20;

    // ── Panel state
    const [showPanel, setShowPanel] = useState(false);
    const [formError, setFormError] = useState<string | null>(null);

    // ── Transfer form state
    const [trfForm, setTrfForm] = useState({
        item:             '',
        from_warehouse:   '',
        to_warehouse:     '',
        quantity:         '',
        reference_number: '',
        remarks:          '',
    });

    const queryFilters = useMemo(() => ({
        page:          currentPage,
        page_size:     pageSize,
        search:        search || undefined,
        movement_type: 'TRF',                    // Transfers page — TRF only
        warehouse:     warehouseFilter || undefined,
    }), [currentPage, search, warehouseFilter]);

    const { data: movements, isLoading } = useStockMovements(queryFilters);
    const { data: items }      = useItems();
    const { data: warehouses } = useWarehouses();
    const stockTransfer   = useStockTransfer();
    const receiveTransfer = useReceiveTransfer();

    // ── Stock availability (fetched the moment an item is selected)
    const selectedItemId = trfForm.item ? Number(trfForm.item) : 0;
    const { data: warehouseStocks, isFetching: stockFetching } = useStockByWarehouse(selectedItemId);
    const stockList: { warehouse: number; warehouse_name: string; quantity: number; reserved_quantity: number; available_quantity: number }[] =
        Array.isArray(warehouseStocks) ? warehouseStocks : [];

    // Available qty in the selected source warehouse
    const sourceStock = trfForm.from_warehouse
        ? stockList.find(s => String(s.warehouse) === String(trfForm.from_warehouse))
        : null;
    const availableQty = sourceStock ? Number(sourceStock.available_quantity ?? sourceStock.quantity) : null;

    // Whether the entered quantity exceeds what's available
    const requestedQty = trfForm.quantity ? parseFloat(trfForm.quantity) : 0;
    const qtyExceeds   = availableQty !== null && requestedQty > 0 && requestedQty > availableQty;

    const rawList: StockMovement[]  = movements?.results || movements || [];
    const totalCount                = movements?.count   || (Array.isArray(movements) ? movements.length : 0);
    const totalPages                = Math.ceil(totalCount / pageSize);
    const itemsList                 = items?.results      || items      || [];
    const warehousesList            = warehouses?.results || warehouses || [];

    // Client-side date filter
    const movementsList = useMemo(
        () => rawList.filter(m => isInDateRange(m.created_at, dateRange)),
        [rawList, dateRange]
    );

    // ── Summary stats
    const statsInTransit = useMemo(() => rawList.filter(m => m.transfer_status === 'In Transit').length, [rawList]);
    const statsReceived  = useMemo(() => rawList.filter(m => m.transfer_status === 'Received').length,   [rawList]);
    const statsQty       = useMemo(() => rawList.reduce((s, m) => s + Number(m.quantity), 0),            [rawList]);

    const resetTrfForm = () => setTrfForm({ item: '', from_warehouse: '', to_warehouse: '', quantity: '', reference_number: '', remarks: '' });

    const handleTransferSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError(null);
        try {
            // Use the item's current average cost for GL valuation.
            // Falls back to cost_price, then 0 if no cost data exists yet.
            const selectedItem = itemsList.find((i: any) => String(i.id) === String(trfForm.item));
            const unitPrice = Number(selectedItem?.average_cost ?? selectedItem?.cost_price ?? 0);
            await stockTransfer.mutateAsync({
                item:             Number(trfForm.item),
                from_warehouse:   Number(trfForm.from_warehouse),
                to_warehouse:     Number(trfForm.to_warehouse),
                quantity:         parseFloat(trfForm.quantity),
                unit_price:       unitPrice,
                reference_number: trfForm.reference_number || undefined,
                remarks:          trfForm.remarks          || undefined,
            });
            setShowPanel(false);
            resetTrfForm();
        } catch (err: any) {
            const msg =
                err?.response?.data?.detail ||
                err?.response?.data?.error  ||
                (typeof err?.response?.data === 'object' ? JSON.stringify(err.response.data) : null) ||
                err?.message ||
                'Failed to create transfer';
            setFormError(msg);
        }
    };

    if (isLoading) return <LoadingScreen message="Loading stock transfers..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>

                <PageHeader
                    title="Stock Transfers"
                    subtitle="Track inter-warehouse transfers — dispatch from source, receive GRN at destination"
                    icon={<ArrowRightLeft size={22} />}
                    actions={
                        <button
                            className="btn btn-primary"
                            onClick={() => { setShowPanel(v => !v); setFormError(null); }}
                            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}
                        >
                            <Plus size={16} />
                            New Transfer
                        </button>
                    }
                />

                {/* ── Summary Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
                    {[
                        { label: 'Total Transfers',   value: totalCount,                                                        color: 'var(--color-primary)' },
                        { label: 'In Transit',         value: statsInTransit,                                                    color: '#f59e0b' },
                        { label: 'Received',           value: statsReceived,                                                     color: '#10b981' },
                        { label: 'Units Transferred',  value: statsQty.toLocaleString(undefined, { maximumFractionDigits: 2 }), color: '#3b82f6' },
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

                {/* ── New Transfer Panel */}
                {showPanel && (
                    <div className="card animate-fade" style={{ marginBottom: '2rem', padding: '1.5rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                            <div>
                                <div style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)', marginBottom: '0.2rem' }}>
                                    New Stock Transfer
                                </div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                    Stock leaves the source warehouse immediately. Destination must post a Receive GRN to update their inventory.
                                </div>
                            </div>
                            <button onClick={() => { setShowPanel(false); setFormError(null); }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                                <X size={18} />
                            </button>
                        </div>

                        <form onSubmit={handleTransferSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div>
                                    <label style={labelStyle}>Item <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <select className="input" value={trfForm.item} onChange={e => setTrfForm({ ...trfForm, item: e.target.value })} required>
                                        <option value="">Select item...</option>
                                        {itemsList.map((i: any) => <option key={i.id} value={i.id}>{i.sku} — {i.name}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={labelStyle}>From Warehouse <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <select
                                        className="input"
                                        value={trfForm.from_warehouse}
                                        onChange={e => setTrfForm({ ...trfForm, from_warehouse: e.target.value })}
                                        required
                                        style={{
                                            borderColor: trfForm.from_warehouse && availableQty === 0
                                                ? '#ef4444'
                                                : trfForm.from_warehouse && availableQty !== null && qtyExceeds
                                                    ? '#f59e0b'
                                                    : undefined,
                                        }}
                                    >
                                        <option value="">Select warehouse...</option>
                                        {warehousesList.map((w: any) => {
                                            const ws = stockList.find(s => s.warehouse === w.id);
                                            const qty = ws ? Number(ws.available_quantity ?? ws.quantity) : null;
                                            const suffix = selectedItemId > 0 && !stockFetching
                                                ? (qty === null ? ' — no stock record' : ` — ${qty.toLocaleString(undefined, { maximumFractionDigits: 4 })} avail.`)
                                                : '';
                                            return <option key={w.id} value={w.id}>{w.name}{suffix}</option>;
                                        })}
                                    </select>

                                    {/* Stock availability badge — shows as soon as item + warehouse are both selected */}
                                    {trfForm.from_warehouse && selectedItemId > 0 && (
                                        <div style={{ marginTop: '0.4rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                            {stockFetching ? (
                                                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>Loading stock…</span>
                                            ) : availableQty === null ? (
                                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', padding: '0.2rem 0.6rem', borderRadius: '9999px', background: 'rgba(107,114,128,0.1)', color: '#6b7280', fontSize: 'var(--text-xs)', fontWeight: 700 }}>
                                                    ⚠ No stock record for this warehouse
                                                </span>
                                            ) : availableQty === 0 ? (
                                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', padding: '0.2rem 0.6rem', borderRadius: '9999px', background: 'rgba(239,68,68,0.1)', color: '#ef4444', fontSize: 'var(--text-xs)', fontWeight: 700 }}>
                                                    ✕ Out of stock in this warehouse
                                                </span>
                                            ) : (
                                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', padding: '0.2rem 0.6rem', borderRadius: '9999px', background: 'rgba(16,185,129,0.1)', color: '#10b981', fontSize: 'var(--text-xs)', fontWeight: 700 }}>
                                                    ✓ Available: {availableQty.toLocaleString(undefined, { maximumFractionDigits: 4 })} units
                                                    {sourceStock && Number(sourceStock.reserved_quantity) > 0 && (
                                                        <span style={{ fontWeight: 400, opacity: 0.85 }}>
                                                            &nbsp;({Number(sourceStock.reserved_quantity).toLocaleString()} reserved)
                                                        </span>
                                                    )}
                                                </span>
                                            )}
                                        </div>
                                    )}
                                </div>
                                <div>
                                    <label style={labelStyle}>To Warehouse <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <select className="input" value={trfForm.to_warehouse} onChange={e => setTrfForm({ ...trfForm, to_warehouse: e.target.value })} required>
                                        <option value="">Select warehouse...</option>
                                        {warehousesList
                                            .filter((w: any) => String(w.id) !== String(trfForm.from_warehouse))
                                            .map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
                                    </select>
                                </div>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1.25rem' }}>
                                <div>
                                    <label style={labelStyle}>Quantity <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <input
                                        type="number" step="0.01" min="0.01"
                                        className="input"
                                        placeholder="0"
                                        value={trfForm.quantity}
                                        onChange={e => setTrfForm({ ...trfForm, quantity: e.target.value })}
                                        required
                                        style={{ borderColor: qtyExceeds ? '#ef4444' : undefined }}
                                    />
                                    {qtyExceeds && (
                                        <div style={{ marginTop: '0.4rem', display: 'flex', alignItems: 'center', gap: '0.3rem', color: '#ef4444', fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                                            ⚠ Exceeds available stock by {(requestedQty - availableQty!).toLocaleString(undefined, { maximumFractionDigits: 4 })} units
                                        </div>
                                    )}
                                </div>
                                <div>
                                    <label style={labelStyle}>Reference Number</label>
                                    <input type="text" className="input" placeholder="TRF-0001" value={trfForm.reference_number} onChange={e => setTrfForm({ ...trfForm, reference_number: e.target.value })} />
                                </div>
                                <div>
                                    <label style={labelStyle}>Remarks</label>
                                    <input type="text" className="input" placeholder="Optional remarks..." value={trfForm.remarks} onChange={e => setTrfForm({ ...trfForm, remarks: e.target.value })} />
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                                <button type="button" className="btn btn-outline" onClick={() => { setShowPanel(false); resetTrfForm(); }}>Cancel</button>
                                <button type="submit" className="btn btn-primary" disabled={stockTransfer.isPending} style={{ minWidth: '140px' }}>
                                    {stockTransfer.isPending ? 'Dispatching...' : 'Dispatch Transfer'}
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
                                    <th style={thStyle}>Item</th>
                                    <th style={thStyle}>Route</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Quantity</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Unit Price</th>
                                    <th style={thStyle}>Reference</th>
                                    <th style={{ ...thStyle, textAlign: 'center' }}>GL Posted</th>
                                    <th style={{ ...thStyle, textAlign: 'center' }}>Transfer Status</th>
                                    <th style={thStyle}>Remarks</th>
                                    <th style={thStyle}>Date</th>
                                    <th style={thStyle}></th>
                                </tr>
                            </thead>
                            <tbody>
                                {movementsList.length === 0 ? (
                                    <tr>
                                        <td colSpan={10} style={{ padding: '4rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                            <Package size={48} style={{ margin: '0 auto 1rem', opacity: 0.2, display: 'block' }} />
                                            <p style={{ fontWeight: 500 }}>No transfers found</p>
                                            <p style={{ fontSize: 'var(--text-sm)', marginTop: '0.25rem' }}>
                                                Click <strong>New Transfer</strong> to dispatch stock between warehouses.
                                            </p>
                                        </td>
                                    </tr>
                                ) : (
                                    movementsList.map(m => {
                                        const isInTransit = m.transfer_status === 'In Transit';
                                        const isReceived  = m.transfer_status === 'Received';

                                        return (
                                            <tr key={m.id} style={{
                                                transition: 'background 0.15s',
                                                background: isInTransit ? 'rgba(245,158,11,0.04)' : undefined,
                                            }}>
                                                {/* Item */}
                                                <td style={{ ...tdStyle, fontWeight: 600 }}>{m.item_name}</td>

                                                {/* Route WH A → WH B */}
                                                <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>
                                                    <span style={{ color: 'var(--color-text)' }}>{m.warehouse_name}</span>
                                                    {m.to_warehouse_name && (
                                                        <>
                                                            <ArrowRightLeft size={12} style={{ margin: '0 0.4rem', color: 'var(--color-text-muted)', verticalAlign: 'middle' }} />
                                                            <span style={{ color: 'var(--color-text)' }}>{m.to_warehouse_name}</span>
                                                        </>
                                                    )}
                                                </td>

                                                {/* Quantity */}
                                                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#f59e0b' }}>
                                                    {Number(m.quantity).toLocaleString(undefined, { maximumFractionDigits: 4 })}
                                                </td>

                                                {/* Unit Price */}
                                                <td style={{ ...tdStyle, textAlign: 'right', color: 'var(--color-text-muted)' }}>
                                                    {Number(m.unit_price) > 0 ? formatCurrency(Number(m.unit_price)) : '—'}
                                                </td>

                                                {/* Reference */}
                                                <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 'var(--text-xs)', color: m.reference_number ? 'var(--color-text)' : 'var(--color-text-muted)' }}>
                                                    {m.reference_number || '—'}
                                                </td>

                                                {/* GL Posted */}
                                                <td style={{ ...tdStyle, textAlign: 'center' }}>
                                                    {m.gl_posted
                                                        ? <CheckCircle size={16} style={{ color: '#10b981' }} />
                                                        : <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>—</span>
                                                    }
                                                </td>

                                                {/* Transfer Status */}
                                                <td style={{ ...tdStyle, textAlign: 'center' }}>
                                                    {isInTransit && (
                                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', padding: '0.2rem 0.6rem', borderRadius: '9999px', background: 'rgba(245,158,11,0.12)', color: '#f59e0b', fontSize: 'var(--text-xs)', fontWeight: 700 }}>
                                                            <Clock size={11} /> In Transit
                                                        </span>
                                                    )}
                                                    {isReceived && (
                                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', padding: '0.2rem 0.6rem', borderRadius: '9999px', background: 'rgba(16,185,129,0.12)', color: '#10b981', fontSize: 'var(--text-xs)', fontWeight: 700 }}>
                                                            <PackageCheck size={11} /> Received
                                                        </span>
                                                    )}
                                                    {!isInTransit && !isReceived && (
                                                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>—</span>
                                                    )}
                                                </td>

                                                {/* Remarks */}
                                                <td style={{ ...tdStyle, color: 'var(--color-text-muted)', maxWidth: '180px' }}>
                                                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }} title={m.remarks}>
                                                        {m.remarks ? (m.remarks.length > 40 ? m.remarks.slice(0, 40) + '…' : m.remarks) : '—'}
                                                    </span>
                                                </td>

                                                {/* Date */}
                                                <td style={{ ...tdStyle, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                                                    {formatDate(m.created_at)}
                                                </td>

                                                {/* Receive GRN action */}
                                                <td style={{ ...tdStyle, textAlign: 'right', whiteSpace: 'nowrap' }}>
                                                    {isInTransit && (
                                                        <button
                                                            onClick={async () => {
                                                                if (!await showConfirm(`Confirm receipt of ${m.quantity} × ${m.item_name} at ${m.to_warehouse_name}?`)) return;
                                                                try {
                                                                    await receiveTransfer.mutateAsync(m.id);
                                                                } catch (err: any) {
                                                                    showAlert(err?.response?.data?.error || 'Failed to receive transfer.');
                                                                }
                                                            }}
                                                            disabled={receiveTransfer.isPending}
                                                            style={{
                                                                display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                                                padding: '0.3rem 0.75rem', borderRadius: '6px',
                                                                background: '#10b981', color: '#fff', border: 'none',
                                                                cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 700,
                                                                opacity: receiveTransfer.isPending ? 0.6 : 1,
                                                            }}
                                                        >
                                                            <PackageCheck size={13} />
                                                            Receive GRN
                                                        </button>
                                                    )}
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

export default StockMovementList;
