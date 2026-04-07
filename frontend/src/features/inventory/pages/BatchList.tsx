import { useState, useMemo } from 'react';
import {
    useBatches,
    useItems,
    useWarehouses,
    useDeleteBatch,
    useCreateBatch,
    useSplitBatch,
    useTransferBatch,
} from '../hooks/useInventory';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import {
    Package,
    Plus,
    Scissors,
    ArrowRightLeft,
    Trash2,
    Search,
    X,
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

interface Batch {
    id: number;
    batch_number: string;
    item: number;
    item_name: string;
    warehouse: number;
    warehouse_name: string;
    quantity: number;
    remaining_quantity: number;
    unit_cost: number;
    receipt_date: string;
    expiry_date: string | null;
    reference_number: string;
}

type StatusFilter = 'all' | 'active' | 'expiring' | 'expired' | 'depleted';
type RowPanel = 'split' | 'transfer' | null;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function daysUntilExpiry(expiryDate: string | null): number | null {
    if (!expiryDate) return null;
    const expiry = new Date(expiryDate);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return Math.ceil((expiry.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

function getExpiryStatus(expiryDate: string | null): 'none' | 'expired' | 'expiring' | 'ok' {
    if (!expiryDate) return 'none';
    const days = daysUntilExpiry(expiryDate);
    if (days === null) return 'none';
    if (days <= 0) return 'expired';
    if (days <= 30) return 'expiring';
    return 'ok';
}

function getBatchStatus(batch: Batch): StatusFilter {
    if (batch.remaining_quantity <= 0) return 'depleted';
    const expStatus = getExpiryStatus(batch.expiry_date);
    if (expStatus === 'expired') return 'expired';
    if (expStatus === 'expiring') return 'expiring';
    return 'active';
}

function addDays(dateStr: string, days: number): string {
    const d = new Date(dateStr);
    d.setDate(d.getDate() + days);
    return d.toISOString().split('T')[0];
}

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
};

// ─── Expiry Badge ─────────────────────────────────────────────────────────────

const ExpiryBadge = ({ expiryDate }: { expiryDate: string | null }) => {
    const status = getExpiryStatus(expiryDate);
    const days = expiryDate ? daysUntilExpiry(expiryDate) : null;

    if (status === 'none') return <span style={{ color: 'var(--color-text-muted)' }}>—</span>;

    if (status === 'expired') return (
        <span style={{ padding: '0.2rem 0.55rem', borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 700, background: 'rgba(239,68,68,0.12)', color: '#ef4444' }}>
            EXPIRED
        </span>
    );

    if (status === 'expiring') return (
        <span style={{ padding: '0.2rem 0.55rem', borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 700, background: 'rgba(245,158,11,0.12)', color: '#f59e0b' }}>
            {days}d left
        </span>
    );

    return (
        <span style={{ padding: '0.2rem 0.55rem', borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 700, background: 'rgba(16,185,129,0.1)', color: '#10b981' }}>
            OK
        </span>
    );
};

// ─── Qty Bar ──────────────────────────────────────────────────────────────────

const QtyBar = ({ quantity, remaining }: { quantity: number; remaining: number }) => {
    const pct = quantity > 0 ? Math.min(100, Math.max(0, (remaining / quantity) * 100)) : 0;
    const barColor = pct > 50 ? '#10b981' : pct > 20 ? '#f59e0b' : '#ef4444';
    return (
        <div style={{ minWidth: '100px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                <span style={{ fontWeight: 700, color: 'var(--color-text)' }}>{Number(remaining).toLocaleString()}</span>
                <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>/ {Number(quantity).toLocaleString()}</span>
            </div>
            <div style={{ height: '4px', borderRadius: '9999px', background: 'var(--color-border)', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${pct}%`, background: barColor, borderRadius: '9999px', transition: 'width 0.3s' }} />
            </div>
        </div>
    );
};

// ─── Component ────────────────────────────────────────────────────────────────

const BatchList = () => {
    const { formatCurrency } = useCurrency();

    const { data: batches, isLoading } = useBatches();
    const { data: items } = useItems();
    const { data: warehouses } = useWarehouses();
    const deleteBatch = useDeleteBatch();
    const createBatch = useCreateBatch();
    const splitBatch = useSplitBatch();
    const transferBatch = useTransferBatch();

    // ── Filter state
    const [search, setSearch] = useState('');
    const [itemFilter, setItemFilter] = useState('');
    const [warehouseFilter, setWarehouseFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

    // ── UI state
    const [showCreateForm, setShowCreateForm] = useState(false);
    const [formError, setFormError] = useState<string | null>(null);
    const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
    // Per-row panel state: {rowId -> 'split' | 'transfer'}
    const [rowPanels, setRowPanels] = useState<Record<number, RowPanel>>({});
    const [splitForms, setSplitForms] = useState<Record<number, { batch_number: string; quantity: string }>>({});
    const [transferForms, setTransferForms] = useState<Record<number, { to_warehouse: string; quantity: string }>>({});
    const [rowErrors, setRowErrors] = useState<Record<number, string>>({});
    const [rowLoading, setRowLoading] = useState<Record<number, boolean>>({});

    const today = new Date().toISOString().split('T')[0];
    const [createForm, setCreateForm] = useState({
        batch_number: '',
        item: '',
        warehouse: '',
        quantity: '',
        unit_cost: '',
        receipt_date: today,
        expiry_date: '',
        reference_number: '',
    });
    // Tracks whether expiry was auto-suggested (so receipt date change can recalculate it)
    const [expiryAutoSet, setExpiryAutoSet] = useState(false);

    const batchesList: Batch[] = batches?.results || batches || [];
    const itemsList = items?.results || items || [];
    const warehousesList = warehouses?.results || warehouses || [];

    // ── Summary stats
    const totalBatches = batchesList.length;
    const activeBatches = batchesList.filter((b) => b.remaining_quantity > 0 && getExpiryStatus(b.expiry_date) !== 'expired').length;
    const expiringSoon = batchesList.filter((b) => getExpiryStatus(b.expiry_date) === 'expiring').length;
    const expired = batchesList.filter((b) => getExpiryStatus(b.expiry_date) === 'expired').length;

    // ── Filtered list
    const filteredBatches = useMemo(() => {
        return batchesList.filter((b) => {
            if (search) {
                const s = search.toLowerCase();
                if (!b.batch_number.toLowerCase().includes(s) && !b.item_name.toLowerCase().includes(s)) return false;
            }
            if (itemFilter && String(b.item) !== String(itemFilter)) return false;
            if (warehouseFilter && String(b.warehouse) !== String(warehouseFilter)) return false;
            if (statusFilter !== 'all' && getBatchStatus(b) !== statusFilter) return false;
            return true;
        });
    }, [batchesList, search, itemFilter, warehouseFilter, statusFilter]);

    // ── Panel helpers
    const togglePanel = (id: number, panel: RowPanel) => {
        setRowPanels((prev) => {
            const current = prev[id];
            return { ...prev, [id]: current === panel ? null : panel };
        });
        setRowErrors((prev) => ({ ...prev, [id]: '' }));
    };

    const resetRowPanel = (id: number) => {
        setRowPanels((prev) => ({ ...prev, [id]: null }));
        setSplitForms((prev) => ({ ...prev, [id]: { batch_number: '', quantity: '' } }));
        setTransferForms((prev) => ({ ...prev, [id]: { to_warehouse: '', quantity: '' } }));
        setRowErrors((prev) => ({ ...prev, [id]: '' }));
    };

    // ── Create batch
    const handleCreateSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError(null);
        try {
            await createBatch.mutateAsync({
                batch_number: createForm.batch_number,
                item: Number(createForm.item),
                warehouse: Number(createForm.warehouse),
                quantity: parseFloat(createForm.quantity),
                remaining_quantity: parseFloat(createForm.quantity),
                unit_cost: parseFloat(createForm.unit_cost),
                receipt_date: createForm.receipt_date,
                expiry_date: createForm.expiry_date || null,
                reference_number: createForm.reference_number || undefined,
            });
            setShowCreateForm(false);
            setCreateForm({ batch_number: '', item: '', warehouse: '', quantity: '', unit_cost: '', receipt_date: today, expiry_date: '', reference_number: '' });
            setExpiryAutoSet(false);
        } catch (err: any) {
            const msg =
                err?.response?.data?.detail ||
                err?.response?.data?.error ||
                (typeof err?.response?.data === 'object' ? JSON.stringify(err.response.data) : null) ||
                err?.message || 'Failed to create batch';
            setFormError(msg);
        }
    };

    // ── Split
    const handleSplit = async (batch: Batch) => {
        const form = splitForms[batch.id] || { batch_number: '', quantity: '' };
        if (!form.quantity) return;
        setRowLoading((prev) => ({ ...prev, [batch.id]: true }));
        setRowErrors((prev) => ({ ...prev, [batch.id]: '' }));
        try {
            await splitBatch.mutateAsync({
                id: batch.id,
                split_quantity: parseFloat(form.quantity),
                new_batch_number: form.batch_number || undefined,
            });
            resetRowPanel(batch.id);
        } catch (err: any) {
            const msg =
                err?.response?.data?.detail ||
                err?.response?.data?.error ||
                (typeof err?.response?.data === 'object' ? JSON.stringify(err.response.data) : null) ||
                err?.message || 'Failed to split batch';
            setRowErrors((prev) => ({ ...prev, [batch.id]: msg }));
        } finally {
            setRowLoading((prev) => ({ ...prev, [batch.id]: false }));
        }
    };

    // ── Transfer
    const handleTransfer = async (batch: Batch) => {
        const form = transferForms[batch.id] || { to_warehouse: '', quantity: '' };
        if (!form.to_warehouse || !form.quantity) return;
        setRowLoading((prev) => ({ ...prev, [batch.id]: true }));
        setRowErrors((prev) => ({ ...prev, [batch.id]: '' }));
        try {
            await transferBatch.mutateAsync({
                id: batch.id,
                to_warehouse: Number(form.to_warehouse),
                transfer_quantity: parseFloat(form.quantity),
            });
            resetRowPanel(batch.id);
        } catch (err: any) {
            const msg =
                err?.response?.data?.detail ||
                err?.response?.data?.error ||
                (typeof err?.response?.data === 'object' ? JSON.stringify(err.response.data) : null) ||
                err?.message || 'Failed to transfer batch';
            setRowErrors((prev) => ({ ...prev, [batch.id]: msg }));
        } finally {
            setRowLoading((prev) => ({ ...prev, [batch.id]: false }));
        }
    };

    // ── Delete
    const handleDelete = async (id: number) => {
        try {
            await deleteBatch.mutateAsync(id);
            setConfirmDeleteId(null);
        } catch {
            setConfirmDeleteId(null);
        }
    };

    if (isLoading) return <LoadingScreen message="Loading batches..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Batches & Lots"
                    subtitle="Manage batch numbers, lot tracking, and expiry"
                    icon={<Package size={22} />}
                    actions={
                        <button
                            className="btn btn-primary"
                            onClick={() => setShowCreateForm((v) => !v)}
                            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}
                        >
                            <Plus size={16} />
                            New Batch
                        </button>
                    }
                />

                {/* ── Summary Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
                    {[
                        { label: 'Total Batches', value: totalBatches, color: 'var(--color-primary)' },
                        { label: 'Active Batches', value: activeBatches, color: '#10b981' },
                        { label: 'Expiring Soon', value: expiringSoon, color: '#f59e0b' },
                        { label: 'Expired', value: expired, color: '#ef4444' },
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

                {/* ── Create Batch Form */}
                {showCreateForm && (
                    <div className="card animate-fade" style={{ marginBottom: '2rem', padding: '1.5rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                            <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>New Batch</h3>
                            <button onClick={() => setShowCreateForm(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}><X size={18} /></button>
                        </div>
                        <form onSubmit={handleCreateSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div>
                                    <label style={labelStyle}>Batch Number <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <input type="text" className="input" placeholder="BATCH-001" value={createForm.batch_number} onChange={(e) => setCreateForm({ ...createForm, batch_number: e.target.value })} required />
                                </div>
                                <div>
                                    <label style={labelStyle}>Item <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <select className="input" value={createForm.item} onChange={(e) => {
                                        const selectedItem = itemsList.find((i: any) => String(i.id) === e.target.value);
                                        const shelfLife = selectedItem?.shelf_life_days;
                                        const autoExpiry = shelfLife ? addDays(createForm.receipt_date, shelfLife) : '';
                                        setCreateForm({ ...createForm, item: e.target.value, expiry_date: autoExpiry });
                                        setExpiryAutoSet(!!shelfLife);
                                    }} required>
                                        <option value="">Select item...</option>
                                        {itemsList.map((i: any) => <option key={i.id} value={i.id}>{i.sku} — {i.name}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={labelStyle}>Warehouse <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <select className="input" value={createForm.warehouse} onChange={(e) => setCreateForm({ ...createForm, warehouse: e.target.value })} required>
                                        <option value="">Select warehouse...</option>
                                        {warehousesList.map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={labelStyle}>Quantity <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <input type="number" step="0.01" className="input" placeholder="0" value={createForm.quantity} onChange={(e) => setCreateForm({ ...createForm, quantity: e.target.value })} required />
                                </div>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1.25rem' }}>
                                <div>
                                    <label style={labelStyle}>Unit Cost <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <input type="number" step="0.01" className="input" placeholder="0.00" value={createForm.unit_cost} onChange={(e) => setCreateForm({ ...createForm, unit_cost: e.target.value })} required />
                                </div>
                                <div>
                                    <label style={labelStyle}>Receipt Date <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <input type="date" className="input" value={createForm.receipt_date} onChange={(e) => {
                                        const newDate = e.target.value;
                                        const selectedItem = itemsList.find((i: any) => String(i.id) === createForm.item);
                                        const shelfLife = selectedItem?.shelf_life_days;
                                        const newExpiry = expiryAutoSet && shelfLife ? addDays(newDate, shelfLife) : createForm.expiry_date;
                                        setCreateForm({ ...createForm, receipt_date: newDate, expiry_date: newExpiry });
                                    }} required />
                                </div>
                                <div>
                                    <label style={labelStyle}>
                                        Expiry Date
                                        {expiryAutoSet && createForm.expiry_date && (
                                            <span style={{ marginLeft: '6px', fontSize: '10px', fontWeight: 500, color: '#10b981', textTransform: 'none', letterSpacing: 0 }}>
                                                ✦ auto-suggested
                                            </span>
                                        )}
                                    </label>
                                    <input type="date" className="input" value={createForm.expiry_date} onChange={(e) => {
                                        setCreateForm({ ...createForm, expiry_date: e.target.value });
                                        setExpiryAutoSet(false); // manual override
                                    }} />
                                </div>
                                <div>
                                    <label style={labelStyle}>Reference Number</label>
                                    <input type="text" className="input" placeholder="REF-001" value={createForm.reference_number} onChange={(e) => setCreateForm({ ...createForm, reference_number: e.target.value })} />
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                                <button type="button" className="btn btn-outline" onClick={() => setShowCreateForm(false)}>Cancel</button>
                                <button type="submit" className="btn btn-primary" disabled={createBatch.isPending}>
                                    {createBatch.isPending ? 'Creating...' : 'Create Batch'}
                                </button>
                            </div>
                        </form>
                    </div>
                )}

                {/* ── Filter Bar */}
                <div style={{ marginBottom: '1.25rem' }}>
                    {/* Row 1: Search + dropdowns */}
                    <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '0.75rem', alignItems: 'center' }}>
                        <div style={{ flex: '2 1 220px', position: 'relative' }}>
                            <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)', pointerEvents: 'none' }} />
                            <input
                                type="text"
                                placeholder="Search batch number or item..."
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                style={{ width: '100%', padding: '0.625rem 0.75rem 0.625rem 2.5rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}
                            />
                        </div>
                        <select
                            value={itemFilter}
                            onChange={(e) => setItemFilter(e.target.value)}
                            style={{ flex: '1 1 160px', padding: '0.625rem 1rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}
                        >
                            <option value="">All Items</option>
                            {itemsList.map((i: any) => <option key={i.id} value={i.id}>{i.name}</option>)}
                        </select>
                        <select
                            value={warehouseFilter}
                            onChange={(e) => setWarehouseFilter(e.target.value)}
                            style={{ flex: '1 1 160px', padding: '0.625rem 1rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}
                        >
                            <option value="">All Warehouses</option>
                            {warehousesList.map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
                        </select>
                    </div>
                    {/* Row 2: Status tabs */}
                    <div style={{ display: 'flex', gap: '0.375rem' }}>
                        {(['all', 'active', 'expiring', 'expired', 'depleted'] as StatusFilter[]).map((s) => (
                            <button
                                key={s}
                                onClick={() => setStatusFilter(s)}
                                style={{
                                    padding: '0.5rem 0.875rem',
                                    borderRadius: '8px',
                                    border: statusFilter === s ? 'none' : '1px solid var(--color-border)',
                                    background: statusFilter === s ? 'var(--color-primary)' : 'transparent',
                                    color: statusFilter === s ? '#fff' : 'var(--color-text-muted)',
                                    cursor: 'pointer',
                                    fontWeight: 600,
                                    fontSize: 'var(--text-xs)',
                                    fontFamily: 'inherit',
                                    textTransform: 'capitalize',
                                }}
                            >
                                {s === 'expiring' ? 'Expiring Soon' : s.charAt(0).toUpperCase() + s.slice(1)}
                            </button>
                        ))}
                    </div>
                </div>

                {/* ── Table */}
                {filteredBatches.length === 0 ? (
                    <div className="card" style={{ padding: '4rem 2rem', textAlign: 'center' }}>
                        <Package size={48} style={{ margin: '0 auto 1rem', opacity: 0.2, display: 'block' }} />
                        <p style={{ color: 'var(--color-text-muted)', fontWeight: 500 }}>No batches found</p>
                    </div>
                ) : (
                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ textAlign: 'left' }}>
                                        <th style={thStyle}>Batch Number</th>
                                        <th style={thStyle}>Product</th>
                                        <th style={thStyle}>Warehouse</th>
                                        <th style={thStyle}>Quantity</th>
                                        <th style={{ ...thStyle, textAlign: 'right' }}>Unit Cost</th>
                                        <th style={thStyle}>Receipt Date</th>
                                        <th style={thStyle}>Expiry</th>
                                        <th style={{ ...thStyle, width: '160px' }}>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredBatches.map((batch) => {
                                        const panel = rowPanels[batch.id] || null;
                                        const splitForm = splitForms[batch.id] || { batch_number: '', quantity: '' };
                                        const transferForm = transferForms[batch.id] || { to_warehouse: '', quantity: '' };
                                        const rowError = rowErrors[batch.id] || '';
                                        const isLoading = rowLoading[batch.id] || false;
                                        const otherWarehouses = warehousesList.filter((w: any) => String(w.id) !== String(batch.warehouse));

                                        return (
                                            <>
                                                <tr key={batch.id} style={{ borderBottom: panel ? 'none' : '1px solid var(--color-border)' }}>
                                                    <td style={tdStyle}>
                                                        <span style={{ fontWeight: 700, fontFamily: 'monospace', fontSize: 'var(--text-sm)' }}>
                                                            {batch.batch_number}
                                                        </span>
                                                    </td>
                                                    <td style={tdStyle}>
                                                        <div style={{ fontWeight: 600 }}>{batch.item_name}</div>
                                                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontFamily: 'monospace' }}>
                                                            {itemsList.find((i: any) => i.id === batch.item)?.sku || ''}
                                                        </div>
                                                    </td>
                                                    <td style={{ ...tdStyle, color: 'var(--color-text-muted)' }}>{batch.warehouse_name}</td>
                                                    <td style={tdStyle}>
                                                        <QtyBar quantity={Number(batch.quantity)} remaining={Number(batch.remaining_quantity)} />
                                                    </td>
                                                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 500 }}>
                                                        {formatCurrency(Number(batch.unit_cost || 0))}
                                                    </td>
                                                    <td style={{ ...tdStyle, color: 'var(--color-text-muted)' }}>
                                                        {batch.receipt_date?.split('T')[0] || '—'}
                                                    </td>
                                                    <td style={tdStyle}>
                                                        <ExpiryBadge expiryDate={batch.expiry_date} />
                                                        {batch.expiry_date && (
                                                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '0.2rem' }}>
                                                                {batch.expiry_date.split('T')[0]}
                                                            </div>
                                                        )}
                                                    </td>
                                                    <td style={tdStyle}>
                                                        {confirmDeleteId === batch.id ? (
                                                            <div style={{ display: 'flex', gap: '0.375rem', alignItems: 'center' }}>
                                                                <button
                                                                    onClick={() => handleDelete(batch.id)}
                                                                    style={{ background: '#ef4444', color: '#fff', border: 'none', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer', fontSize: 'var(--text-xs)', fontFamily: 'inherit', fontWeight: 600 }}
                                                                >Yes</button>
                                                                <button
                                                                    onClick={() => setConfirmDeleteId(null)}
                                                                    style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer', fontSize: 'var(--text-xs)', fontFamily: 'inherit' }}
                                                                >No</button>
                                                            </div>
                                                        ) : (
                                                            <div style={{ display: 'flex', gap: '0.375rem', alignItems: 'center' }}>
                                                                <button
                                                                    onClick={() => togglePanel(batch.id, 'split')}
                                                                    title="Split batch"
                                                                    style={{
                                                                        display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                                                        padding: '0.3rem 0.6rem', borderRadius: '6px', cursor: 'pointer',
                                                                        background: panel === 'split' ? 'rgba(59,130,246,0.12)' : 'var(--color-surface)',
                                                                        color: panel === 'split' ? '#3b82f6' : 'var(--color-text-muted)',
                                                                        border: '1px solid var(--color-border)', fontSize: 'var(--text-xs)', fontWeight: 600, fontFamily: 'inherit',
                                                                    }}
                                                                >
                                                                    <Scissors size={12} /> Split
                                                                </button>
                                                                <button
                                                                    onClick={() => togglePanel(batch.id, 'transfer')}
                                                                    title="Transfer batch"
                                                                    style={{
                                                                        display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                                                        padding: '0.3rem 0.6rem', borderRadius: '6px', cursor: 'pointer',
                                                                        background: panel === 'transfer' ? 'rgba(245,158,11,0.12)' : 'var(--color-surface)',
                                                                        color: panel === 'transfer' ? '#f59e0b' : 'var(--color-text-muted)',
                                                                        border: '1px solid var(--color-border)', fontSize: 'var(--text-xs)', fontWeight: 600, fontFamily: 'inherit',
                                                                    }}
                                                                >
                                                                    <ArrowRightLeft size={12} /> Transfer
                                                                </button>
                                                                <button
                                                                    onClick={() => setConfirmDeleteId(batch.id)}
                                                                    title="Delete batch"
                                                                    style={{ display: 'inline-flex', alignItems: 'center', padding: '0.3rem', borderRadius: '6px', cursor: 'pointer', background: 'rgba(239,68,68,0.08)', color: '#ef4444', border: 'none' }}
                                                                >
                                                                    <Trash2 size={13} />
                                                                </button>
                                                            </div>
                                                        )}
                                                    </td>
                                                </tr>

                                                {/* ── Split Panel */}
                                                {panel === 'split' && (
                                                    <tr key={`${batch.id}-split`}>
                                                        <td colSpan={8} style={{ padding: '0 1rem 0.875rem', borderBottom: '1px solid var(--color-border)' }}>
                                                            <div style={{ background: 'rgba(59,130,246,0.05)', border: '1px solid rgba(59,130,246,0.15)', borderRadius: '8px', padding: '1rem' }}>
                                                                <div style={{ fontWeight: 700, fontSize: 'var(--text-sm)', color: '#3b82f6', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                                                                    <Scissors size={14} /> Split Batch — {batch.batch_number}
                                                                    <span style={{ fontSize: 'var(--text-xs)', fontWeight: 400, color: 'var(--color-text-muted)', marginLeft: '0.5rem' }}>
                                                                        (remaining: {Number(batch.remaining_quantity).toLocaleString()})
                                                                    </span>
                                                                </div>
                                                                {rowError && (
                                                                    <div style={{ padding: '0.5rem 0.75rem', background: 'rgba(239,68,68,0.08)', color: '#ef4444', borderRadius: '6px', fontSize: 'var(--text-xs)', marginBottom: '0.75rem' }}>{rowError}</div>
                                                                )}
                                                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
                                                                    <div>
                                                                        <label style={labelStyle}>New Batch Number <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                                                        <input
                                                                            type="text"
                                                                            className="input"
                                                                            placeholder="BATCH-001-A"
                                                                            value={splitForm.batch_number}
                                                                            onChange={(e) => setSplitForms((prev) => ({ ...prev, [batch.id]: { ...splitForm, batch_number: e.target.value } }))}
                                                                        />
                                                                    </div>
                                                                    <div>
                                                                        <label style={labelStyle}>
                                                                            Split Quantity <span style={{ color: 'var(--color-error)' }}>*</span>
                                                                            <span style={{ fontWeight: 400, textTransform: 'none', color: 'var(--color-text-muted)', marginLeft: '0.25rem' }}>
                                                                                (max {Number(batch.remaining_quantity).toLocaleString()})
                                                                            </span>
                                                                        </label>
                                                                        <input
                                                                            type="number"
                                                                            step="0.01"
                                                                            min="0.01"
                                                                            max={Number(batch.remaining_quantity)}
                                                                            className="input"
                                                                            placeholder="0"
                                                                            value={splitForm.quantity}
                                                                            onChange={(e) => setSplitForms((prev) => ({ ...prev, [batch.id]: { ...splitForm, quantity: e.target.value } }))}
                                                                        />
                                                                    </div>
                                                                </div>
                                                                <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                                                    <button className="btn btn-outline" style={{ fontSize: 'var(--text-xs)', padding: '0.375rem 0.75rem' }} onClick={() => resetRowPanel(batch.id)}>Cancel</button>
                                                                    <button
                                                                        className="btn btn-primary"
                                                                        style={{ fontSize: 'var(--text-xs)', padding: '0.375rem 0.875rem', background: '#3b82f6', display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}
                                                                        onClick={() => handleSplit(batch)}
                                                                        disabled={isLoading || !splitForm.quantity || !splitForm.batch_number}
                                                                    >
                                                                        {isLoading ? 'Splitting...' : <><Scissors size={12} /> Split</>}
                                                                    </button>
                                                                </div>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                )}

                                                {/* ── Transfer Panel */}
                                                {panel === 'transfer' && (
                                                    <tr key={`${batch.id}-transfer`}>
                                                        <td colSpan={8} style={{ padding: '0 1rem 0.875rem', borderBottom: '1px solid var(--color-border)' }}>
                                                            <div style={{ background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: '8px', padding: '1rem' }}>
                                                                <div style={{ fontWeight: 700, fontSize: 'var(--text-sm)', color: '#f59e0b', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                                                                    <ArrowRightLeft size={14} /> Transfer Batch — {batch.batch_number}
                                                                    <span style={{ fontSize: 'var(--text-xs)', fontWeight: 400, color: 'var(--color-text-muted)', marginLeft: '0.5rem' }}>
                                                                        from {batch.warehouse_name}
                                                                    </span>
                                                                </div>
                                                                {rowError && (
                                                                    <div style={{ padding: '0.5rem 0.75rem', background: 'rgba(239,68,68,0.08)', color: '#ef4444', borderRadius: '6px', fontSize: 'var(--text-xs)', marginBottom: '0.75rem' }}>{rowError}</div>
                                                                )}
                                                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
                                                                    <div>
                                                                        <label style={labelStyle}>To Warehouse <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                                                        <select
                                                                            className="input"
                                                                            value={transferForm.to_warehouse}
                                                                            onChange={(e) => setTransferForms((prev) => ({ ...prev, [batch.id]: { ...transferForm, to_warehouse: e.target.value } }))}
                                                                        >
                                                                            <option value="">Select warehouse...</option>
                                                                            {otherWarehouses.map((w: any) => (
                                                                                <option key={w.id} value={w.id}>{w.name}</option>
                                                                            ))}
                                                                        </select>
                                                                    </div>
                                                                    <div>
                                                                        <label style={labelStyle}>
                                                                            Transfer Quantity <span style={{ color: 'var(--color-error)' }}>*</span>
                                                                            <span style={{ fontWeight: 400, textTransform: 'none', color: 'var(--color-text-muted)', marginLeft: '0.25rem' }}>
                                                                                (max {Number(batch.remaining_quantity).toLocaleString()})
                                                                            </span>
                                                                        </label>
                                                                        <input
                                                                            type="number"
                                                                            step="0.01"
                                                                            min="0.01"
                                                                            max={Number(batch.remaining_quantity)}
                                                                            className="input"
                                                                            placeholder="0"
                                                                            value={transferForm.quantity}
                                                                            onChange={(e) => setTransferForms((prev) => ({ ...prev, [batch.id]: { ...transferForm, quantity: e.target.value } }))}
                                                                        />
                                                                    </div>
                                                                </div>
                                                                <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                                                    <button className="btn btn-outline" style={{ fontSize: 'var(--text-xs)', padding: '0.375rem 0.75rem' }} onClick={() => resetRowPanel(batch.id)}>Cancel</button>
                                                                    <button
                                                                        className="btn btn-primary"
                                                                        style={{ fontSize: 'var(--text-xs)', padding: '0.375rem 0.875rem', background: '#f59e0b', display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}
                                                                        onClick={() => handleTransfer(batch)}
                                                                        disabled={isLoading || !transferForm.quantity || !transferForm.to_warehouse}
                                                                    >
                                                                        {isLoading ? 'Transferring...' : <><ArrowRightLeft size={12} /> Transfer</>}
                                                                    </button>
                                                                </div>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                )}
                                            </>
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

export default BatchList;
