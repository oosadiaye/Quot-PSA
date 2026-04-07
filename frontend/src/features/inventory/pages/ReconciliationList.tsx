import { useState, useEffect, useRef } from 'react';
import {
    useReconciliations,
    useCreateReconciliation,
    useCompleteReconciliation,
    useAddReconciliationLine,
    usePopulateReconciliation,
    useStartReconciliation,
    useUpdateReconciliationLine,
    useWarehouses,
    useItems,
} from '../hooks/useInventory';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import {
    RefreshCw, Plus, CheckCircle, AlertTriangle, X,
    Download, ClipboardList, Layers, ChevronRight, Play,
    PackageSearch, Save,
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ReconciliationLine {
    id: number;
    item: number;
    item_name: string;
    system_quantity: number;
    physical_quantity: number;
    variance_quantity: number;
    variance_value: number;
    reason: string;
    is_adjusted: boolean;
}

interface Reconciliation {
    id: number;
    reconciliation_number: string;
    reconciliation_type: string;
    reconciliation_date: string;
    status: string;
    notes: string;
    warehouse: number;
    warehouse_name: string;
    lines: ReconciliationLine[];
}

// ─── Constants & helpers ──────────────────────────────────────────────────────

// Backend sends Title Case: 'Draft', 'In Progress', 'Completed', 'Cancelled'
const STATUS_META: Record<string, { bg: string; color: string; label: string }> = {
    'Draft':       { bg: 'rgba(100,116,139,0.12)', color: '#64748b', label: 'Draft' },
    'In Progress': { bg: 'rgba(59,130,246,0.12)',  color: '#3b82f6', label: 'In Progress' },
    'Completed':   { bg: 'rgba(16,185,129,0.12)',  color: '#10b981', label: 'Completed' },
    'Cancelled':   { bg: 'rgba(239,68,68,0.12)',   color: '#ef4444', label: 'Cancelled' },
};

// Backend sends Title Case: 'Full', 'Partial', 'Cycle', 'Spot'
const TYPE_LABELS: Record<string, string> = {
    'Full':    'Full Count',
    'Partial': 'Partial Count',
    'Cycle':   'Cycle Count',
    'Spot':    'Spot Check',
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

function statusPill(s: string) {
    const m = STATUS_META[s] ?? STATUS_META['Draft'];
    return (
        <span style={{
            padding: '0.2rem 0.6rem', borderRadius: '9999px',
            fontSize: 'var(--text-xs)', fontWeight: 700,
            background: m.bg, color: m.color,
        }}>{m.label}</span>
    );
}

function exportCSV(rec: Reconciliation, formatCurrency: (v: number) => string) {
    const headers = ['Item', 'System Qty', 'Physical Qty', 'Variance', 'Variance Value', 'Reason', 'Adjusted'];
    const rows = (rec.lines || []).map(l => [
        `"${l.item_name}"`,
        l.system_quantity,
        l.physical_quantity,
        l.variance_quantity > 0 ? `+${l.variance_quantity}` : l.variance_quantity,
        `"${formatCurrency(Math.abs(l.variance_value))}"`,
        `"${l.reason || ''}"`,
        l.is_adjusted ? 'Yes' : 'No',
    ]);
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const a = Object.assign(document.createElement('a'), {
        href: URL.createObjectURL(new Blob([csv], { type: 'text/csv' })),
        download: `${rec.reconciliation_number}.csv`,
    });
    a.click();
    URL.revokeObjectURL(a.href);
}

// ─── Component ────────────────────────────────────────────────────────────────

const ReconciliationList = () => {
    const { formatCurrency } = useCurrency();

    // ── Data
    const { data: reconciliations, isLoading } = useReconciliations();
    const { data: warehousesRaw } = useWarehouses();
    const { data: itemsRaw } = useItems();

    const createRec      = useCreateReconciliation();
    const completeRec    = useCompleteReconciliation();
    const addLine        = useAddReconciliationLine();
    const populateRec    = usePopulateReconciliation();
    const startRec       = useStartReconciliation();
    const updateLine     = useUpdateReconciliationLine();

    // ── UI state
    const [selectedId, setSelectedId]         = useState<number | null>(null);
    const [showNewForm, setShowNewForm]        = useState(false);
    const [statusFilter, setStatusFilter]     = useState('');
    const [warehouseFilter, setWarehouseFilter] = useState('');
    const [confirmCompleteId, setConfirmCompleteId] = useState<number | null>(null);
    const [showAddLine, setShowAddLine]        = useState(false);
    const [formError, setFormError]            = useState<string | null>(null);
    const [lineError, setLineError]            = useState<string | null>(null);

    // Per-line edits: lineId → { qty, reason }
    const [lineEdits, setLineEdits] = useState<Record<number, { qty: string; reason: string }>>({});
    const [savingLines, setSavingLines] = useState<Set<number>>(new Set());

    const today = new Date().toISOString().split('T')[0];

    const [formData, setFormData] = useState({
        warehouse: '', reconciliation_type: 'Full',
        reconciliation_date: today, notes: '',
    });
    const [lineForm, setLineForm] = useState({ item: '', physical_quantity: '', reason: '' });

    // ── Derived lists
    const recList: Reconciliation[] = (reconciliations as any)?.results ?? reconciliations ?? [];
    const warehousesList: any[] = (warehousesRaw as any)?.results ?? warehousesRaw ?? [];
    const itemsList: any[] = (itemsRaw as any)?.results ?? itemsRaw ?? [];

    const filteredList = recList.filter(r => {
        if (statusFilter && r.status !== statusFilter) return false;
        if (warehouseFilter && String(r.warehouse) !== warehouseFilter) return false;
        return true;
    });

    const selectedRec = recList.find(r => r.id === selectedId) ?? null;

    // Summary stats
    const totalCount    = recList.length;
    const inProgCount   = recList.filter(r => r.status === 'In Progress' || r.status === 'Draft').length;
    const completedCount = recList.filter(r => r.status === 'Completed').length;

    // ── Initialise line edits when selected reconciliation changes
    useEffect(() => {
        setLineEdits({});
        setShowAddLine(false);
        setLineError(null);
        setConfirmCompleteId(null);
    }, [selectedId]);

    useEffect(() => {
        if (!selectedRec) return;
        setLineEdits(prev => {
            const next = { ...prev };
            for (const line of selectedRec.lines ?? []) {
                if (!(line.id in next)) {
                    next[line.id] = {
                        qty: String(line.physical_quantity),
                        reason: line.reason ?? '',
                    };
                }
            }
            return next;
        });
    }, [selectedRec]);

    // ── Handlers

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError(null);
        try {
            const created = await createRec.mutateAsync({
                warehouse: Number(formData.warehouse),
                reconciliation_type: formData.reconciliation_type,
                reconciliation_date: formData.reconciliation_date,
                notes: formData.notes || undefined,
            });
            setShowNewForm(false);
            setFormData({ warehouse: '', reconciliation_type: 'Full', reconciliation_date: today, notes: '' });
            setSelectedId((created as any).id ?? null);
        } catch (err: any) {
            setFormError(
                err?.response?.data?.detail ??
                err?.response?.data?.error ??
                (typeof err?.response?.data === 'object' ? JSON.stringify(err.response.data) : null) ??
                err?.message ?? 'Failed to create reconciliation'
            );
        }
    };

    const handlePopulate = async (id: number) => {
        try { await populateRec.mutateAsync(id); } catch { /* ignore */ }
    };

    const handleStart = async (id: number) => {
        try { await startRec.mutateAsync(id); } catch { /* ignore */ }
    };

    const handleComplete = async (id: number) => {
        try {
            await completeRec.mutateAsync(id);
            setConfirmCompleteId(null);
        } catch { setConfirmCompleteId(null); }
    };

    const handleAddLine = async (recId: number) => {
        if (!lineForm.item || lineForm.physical_quantity === '') return;
        setLineError(null);
        try {
            await addLine.mutateAsync({
                recId,
                item: Number(lineForm.item),
                physical_quantity: parseFloat(lineForm.physical_quantity),
                reason: lineForm.reason,
            });
            setLineForm({ item: '', physical_quantity: '', reason: '' });
            setShowAddLine(false);
        } catch (err: any) {
            setLineError(
                err?.response?.data?.detail ??
                err?.response?.data?.error ??
                (typeof err?.response?.data === 'object' ? JSON.stringify(err.response.data) : null) ??
                err?.message ?? 'Failed to add item'
            );
        }
    };

    const handleLineSave = async (recId: number, lineId: number) => {
        const edit = lineEdits[lineId];
        if (!edit) return;
        const line = selectedRec?.lines?.find(l => l.id === lineId);
        if (!line) return;
        const qtyChanged  = parseFloat(edit.qty) !== Number(line.physical_quantity);
        const rsChanged   = edit.reason !== (line.reason ?? '');
        if (!qtyChanged && !rsChanged) return;

        setSavingLines(prev => new Set([...prev, lineId]));
        try {
            await updateLine.mutateAsync({
                recId,
                lineId,
                physical_quantity: parseFloat(edit.qty) || 0,
                reason: edit.reason,
            });
        } finally {
            setSavingLines(prev => { const n = new Set(prev); n.delete(lineId); return n; });
        }
    };

    // ── Count sheet variance helpers
    const linesOf = (rec: Reconciliation | null) => rec?.lines ?? [];
    const varianceLines = linesOf(selectedRec).filter(l => Number(l.variance_quantity) !== 0);
    const totalVarianceValue = linesOf(selectedRec).reduce((s, l) => s + Number(l.variance_value || 0), 0);

    const isActive = selectedRec && (selectedRec.status === 'Draft' || selectedRec.status === 'In Progress');
    const isDone   = selectedRec?.status === 'Completed';

    if (isLoading) return <LoadingScreen message="Loading reconciliations..." />;

    // ─── JSX ──────────────────────────────────────────────────────────────────
    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }} className="animate-fade">

                <PageHeader
                    title="Stock Reconciliation"
                    subtitle="Audit physical stock versus system records and post adjustments"
                    icon={<RefreshCw size={22} />}
                    actions={
                        <button
                            className="btn btn-primary"
                            onClick={() => { setShowNewForm(v => !v); setSelectedId(null); }}
                            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}
                        >
                            <Plus size={16} /> New Reconciliation
                        </button>
                    }
                />

                {/* ── Summary Cards ──────────────────────────────────────────── */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1.75rem' }}>
                    {[
                        { label: 'Total',       value: totalCount,    color: 'var(--color-primary)', icon: <ClipboardList size={20} /> },
                        { label: 'Active',      value: inProgCount,   color: '#3b82f6',               icon: <Layers size={20} /> },
                        { label: 'Completed',   value: completedCount, color: '#10b981',              icon: <CheckCircle size={20} /> },
                    ].map(({ label, value, color, icon }) => (
                        <div key={label} className="card" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <div style={{ padding: '0.6rem', borderRadius: '0.5rem', background: color + '1a', color, flexShrink: 0 }}>{icon}</div>
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-muted)' }}>{label}</div>
                                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 800, color }}>{value}</div>
                            </div>
                        </div>
                    ))}
                </div>

                {/* ── New Reconciliation Form ─────────────────────────────────── */}
                {showNewForm && (
                    <div className="card animate-fade" style={{ marginBottom: '1.5rem', padding: '1.5rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                            <h3 style={{ margin: 0, fontWeight: 700, fontSize: 'var(--text-lg)' }}>Start New Reconciliation</h3>
                            <button onClick={() => setShowNewForm(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}><X size={18} /></button>
                        </div>
                        {formError && (
                            <div style={{ padding: '0.6rem 0.875rem', background: 'rgba(239,68,68,0.08)', color: 'var(--color-error)', borderRadius: '6px', marginBottom: '1rem', fontSize: 'var(--text-sm)' }}>
                                {formError}
                            </div>
                        )}
                        <form onSubmit={handleCreate}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                <div>
                                    <label style={labelStyle}>Warehouse <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <select className="input" value={formData.warehouse} onChange={e => setFormData({ ...formData, warehouse: e.target.value })} required>
                                        <option value="">Select warehouse...</option>
                                        {warehousesList.map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={labelStyle}>Count Type <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <select className="input" value={formData.reconciliation_type} onChange={e => setFormData({ ...formData, reconciliation_type: e.target.value })} required>
                                        <option value="Full">Full Count</option>
                                        <option value="Partial">Partial Count</option>
                                        <option value="Cycle">Cycle Count</option>
                                        <option value="Spot">Spot Check</option>
                                    </select>
                                </div>
                                <div>
                                    <label style={labelStyle}>Count Date <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                    <input type="date" className="input" value={formData.reconciliation_date} onChange={e => setFormData({ ...formData, reconciliation_date: e.target.value })} required />
                                </div>
                            </div>
                            <div style={{ marginBottom: '1rem' }}>
                                <label style={labelStyle}>Notes</label>
                                <input type="text" className="input" placeholder="Optional notes about this count..." value={formData.notes} onChange={e => setFormData({ ...formData, notes: e.target.value })} />
                            </div>
                            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                                <button type="button" className="btn btn-outline" onClick={() => setShowNewForm(false)}>Cancel</button>
                                <button type="submit" className="btn btn-primary" disabled={createRec.isPending}>
                                    {createRec.isPending ? 'Creating...' : 'Create & Open'}
                                </button>
                            </div>
                        </form>
                    </div>
                )}

                {/* ── Two-panel layout ───────────────────────────────────────── */}
                <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-start' }}>

                    {/* ── LEFT: Reconciliation list ───────────────────────────── */}
                    <div style={{ width: selectedId ? '340px' : '100%', flexShrink: 0, transition: 'width 0.25s ease' }}>

                        {/* Filter bar */}
                        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
                            {(['', 'Draft', 'In Progress', 'Completed', 'Cancelled'] as const).map(s => {
                                const m = s ? STATUS_META[s] : null;
                                const active = statusFilter === s;
                                return (
                                    <button
                                        key={s || 'all'}
                                        onClick={() => setStatusFilter(s)}
                                        style={{
                                            padding: '0.3rem 0.75rem', borderRadius: '99px', fontSize: 'var(--text-xs)', fontWeight: 600, cursor: 'pointer',
                                            border: active ? 'none' : '1px solid var(--color-border)',
                                            background: active ? (m ? m.color : 'var(--color-primary)') : 'transparent',
                                            color: active ? '#fff' : 'var(--color-text-muted)',
                                        }}
                                    >{s || 'All'}</button>
                                );
                            })}
                            {!selectedId && (
                                <select className="input" value={warehouseFilter} onChange={e => setWarehouseFilter(e.target.value)} style={{ width: 'auto', marginLeft: 'auto' }}>
                                    <option value="">All Warehouses</option>
                                    {warehousesList.map((w: any) => <option key={w.id} value={String(w.id)}>{w.name}</option>)}
                                </select>
                            )}
                        </div>

                        {/* List */}
                        {filteredList.length === 0 ? (
                            <div className="card" style={{ textAlign: 'center', padding: '3rem 1.5rem', color: 'var(--color-text-muted)' }}>
                                <RefreshCw size={36} style={{ opacity: 0.2, display: 'block', margin: '0 auto 0.75rem' }} />
                                <p style={{ fontWeight: 500 }}>No reconciliations found</p>
                                <p style={{ fontSize: 'var(--text-sm)', marginTop: '0.25rem' }}>Create one to get started</p>
                            </div>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                {filteredList.map(rec => {
                                    const isSelected  = rec.id === selectedId;
                                    const meta        = STATUS_META[rec.status] ?? STATUS_META['Draft'];
                                    const lineCount   = rec.lines?.length ?? 0;
                                    const varLines    = (rec.lines ?? []).filter(l => Number(l.variance_quantity) !== 0).length;
                                    const varValue    = (rec.lines ?? []).reduce((s, l) => s + Number(l.variance_value || 0), 0);

                                    return (
                                        <div
                                            key={rec.id}
                                            onClick={() => setSelectedId(isSelected ? null : rec.id)}
                                            className="card"
                                            style={{
                                                padding: '0.875rem 1rem', cursor: 'pointer',
                                                borderLeft: `3px solid ${isSelected ? meta.color : 'transparent'}`,
                                                background: isSelected ? `${meta.color}08` : undefined,
                                                transition: 'all 0.15s',
                                            }}
                                        >
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem' }}>
                                                <div style={{ minWidth: 0 }}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.3rem', flexWrap: 'wrap' }}>
                                                        <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: 'var(--text-xs)', color: 'var(--color-primary)' }}>
                                                            {rec.reconciliation_number}
                                                        </span>
                                                        {statusPill(rec.status)}
                                                    </div>
                                                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginBottom: '0.2rem' }}>
                                                        {TYPE_LABELS[rec.reconciliation_type] ?? rec.reconciliation_type} · {rec.warehouse_name}
                                                    </div>
                                                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                        {rec.reconciliation_date?.split('T')[0]} · {lineCount} line{lineCount !== 1 ? 's' : ''}
                                                        {varLines > 0 && (
                                                            <span style={{ color: '#f59e0b', fontWeight: 600, marginLeft: '0.5rem' }}>
                                                                {varLines} variance{varLines !== 1 ? 's' : ''} · {formatCurrency(Math.abs(varValue))}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                                <ChevronRight size={14} style={{ color: 'var(--color-text-muted)', flexShrink: 0, opacity: isSelected ? 0 : 1 }} />
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    {/* ── RIGHT: Count sheet detail panel ─────────────────────── */}
                    {selectedRec && (
                        <div style={{ flex: 1, minWidth: 0 }} className="animate-fade">
                            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>

                                {/* ── Panel Header */}
                                <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                        <div>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.375rem', flexWrap: 'wrap' }}>
                                                <span style={{ fontFamily: 'monospace', fontWeight: 800, fontSize: 'var(--text-base)', color: 'var(--color-text)' }}>
                                                    {selectedRec.reconciliation_number}
                                                </span>
                                                {statusPill(selectedRec.status)}
                                                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', background: 'var(--color-border)', padding: '0.15rem 0.5rem', borderRadius: '4px' }}>
                                                    {TYPE_LABELS[selectedRec.reconciliation_type] ?? selectedRec.reconciliation_type}
                                                </span>
                                            </div>
                                            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                                {selectedRec.warehouse_name} · {selectedRec.reconciliation_date?.split('T')[0]}
                                                {selectedRec.notes && <span style={{ marginLeft: '0.75rem', fontStyle: 'italic' }}>— {selectedRec.notes}</span>}
                                            </div>
                                        </div>
                                        <button onClick={() => setSelectedId(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', flexShrink: 0 }}>
                                            <X size={18} />
                                        </button>
                                    </div>

                                    {/* ── Stats bar */}
                                    <div style={{ display: 'flex', gap: '1.5rem', marginTop: '0.875rem', paddingTop: '0.875rem', borderTop: '1px solid var(--color-border)' }}>
                                        <div>
                                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600 }}>Total Lines</div>
                                            <div style={{ fontWeight: 700 }}>{linesOf(selectedRec).length}</div>
                                        </div>
                                        <div>
                                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600 }}>With Variance</div>
                                            <div style={{ fontWeight: 700, color: varianceLines.length > 0 ? '#f59e0b' : 'var(--color-text-muted)' }}>{varianceLines.length}</div>
                                        </div>
                                        <div>
                                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600 }}>Variance Value</div>
                                            <div style={{ fontWeight: 700, color: totalVarianceValue < 0 ? '#ef4444' : totalVarianceValue > 0 ? '#10b981' : 'var(--color-text-muted)' }}>
                                                {totalVarianceValue !== 0 ? (totalVarianceValue > 0 ? '+' : '') + formatCurrency(totalVarianceValue) : '—'}
                                            </div>
                                        </div>

                                        {/* ── Action buttons (right-aligned) */}
                                        <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                                            {/* Draft actions */}
                                            {selectedRec.status === 'Draft' && (
                                                <>
                                                    <button
                                                        className="btn btn-outline"
                                                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', fontSize: 'var(--text-xs)', padding: '0.35rem 0.75rem' }}
                                                        onClick={() => handlePopulate(selectedRec.id)}
                                                        disabled={populateRec.isPending}
                                                    >
                                                        <PackageSearch size={14} />
                                                        {populateRec.isPending ? 'Loading...' : 'Populate All Items'}
                                                    </button>
                                                    <button
                                                        className="btn btn-outline"
                                                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', fontSize: 'var(--text-xs)', padding: '0.35rem 0.75rem', color: '#3b82f6', borderColor: '#3b82f6' }}
                                                        onClick={() => handleStart(selectedRec.id)}
                                                        disabled={startRec.isPending}
                                                    >
                                                        <Play size={13} /> Start Counting
                                                    </button>
                                                </>
                                            )}

                                            {/* Active: add item */}
                                            {isActive && (
                                                <button
                                                    className="btn btn-outline"
                                                    style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', fontSize: 'var(--text-xs)', padding: '0.35rem 0.75rem' }}
                                                    onClick={() => setShowAddLine(v => !v)}
                                                >
                                                    <Plus size={13} /> Add Item
                                                </button>
                                            )}

                                            {/* Active: complete (with confirm) */}
                                            {isActive && (
                                                confirmCompleteId === selectedRec.id ? (
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                        <AlertTriangle size={13} style={{ color: '#f59e0b' }} />
                                                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                            Post {varianceLines.length} adjustment{varianceLines.length !== 1 ? 's' : ''}?
                                                        </span>
                                                        <button className="btn btn-primary" style={{ fontSize: 'var(--text-xs)', padding: '0.3rem 0.7rem' }} onClick={() => handleComplete(selectedRec.id)} disabled={completeRec.isPending}>
                                                            {completeRec.isPending ? 'Posting…' : 'Confirm'}
                                                        </button>
                                                        <button className="btn btn-outline" style={{ fontSize: 'var(--text-xs)', padding: '0.3rem 0.7rem' }} onClick={() => setConfirmCompleteId(null)}>Cancel</button>
                                                    </div>
                                                ) : (
                                                    <button
                                                        className="btn btn-primary"
                                                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', fontSize: 'var(--text-xs)', padding: '0.35rem 0.875rem' }}
                                                        onClick={() => setConfirmCompleteId(selectedRec.id)}
                                                    >
                                                        <CheckCircle size={14} /> Complete
                                                    </button>
                                                )
                                            )}

                                            {/* Completed: export */}
                                            {isDone && (
                                                <button
                                                    className="btn btn-outline"
                                                    style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', fontSize: 'var(--text-xs)', padding: '0.35rem 0.75rem' }}
                                                    onClick={() => exportCSV(selectedRec, formatCurrency)}
                                                >
                                                    <Download size={13} /> Export CSV
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                {/* ── Add item form */}
                                {showAddLine && isActive && (
                                    <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--color-border)', background: 'rgba(59,130,246,0.03)' }}>
                                        {lineError && (
                                            <div style={{ marginBottom: '0.75rem', padding: '0.5rem 0.75rem', background: 'rgba(239,68,68,0.08)', color: 'var(--color-error)', borderRadius: '6px', fontSize: 'var(--text-sm)' }}>
                                                {lineError}
                                            </div>
                                        )}
                                        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 2fr auto', gap: '0.75rem', alignItems: 'flex-end' }}>
                                            <div>
                                                <label style={labelStyle}>Item *</label>
                                                <select className="input" value={lineForm.item} onChange={e => setLineForm({ ...lineForm, item: e.target.value })}>
                                                    <option value="">Select item...</option>
                                                    {itemsList.map((i: any) => <option key={i.id} value={i.id}>{i.sku} — {i.name}</option>)}
                                                </select>
                                            </div>
                                            <div>
                                                <label style={labelStyle}>Physical Qty *</label>
                                                <input type="number" step="0.01" className="input" placeholder="0" value={lineForm.physical_quantity} onChange={e => setLineForm({ ...lineForm, physical_quantity: e.target.value })} />
                                            </div>
                                            <div>
                                                <label style={labelStyle}>Reason</label>
                                                <input type="text" className="input" placeholder="Reason for variance..." value={lineForm.reason} onChange={e => setLineForm({ ...lineForm, reason: e.target.value })} />
                                            </div>
                                            <div style={{ display: 'flex', gap: '0.4rem', paddingBottom: '1px' }}>
                                                <button className="btn btn-primary" style={{ fontSize: 'var(--text-xs)', padding: '0.45rem 0.75rem' }} onClick={() => handleAddLine(selectedRec.id)} disabled={addLine.isPending || !lineForm.item || lineForm.physical_quantity === ''}>
                                                    {addLine.isPending ? '…' : 'Add'}
                                                </button>
                                                <button className="btn btn-outline" style={{ fontSize: 'var(--text-xs)', padding: '0.45rem 0.75rem' }} onClick={() => { setShowAddLine(false); setLineError(null); }}>
                                                    <X size={13} />
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {/* ── Count sheet table */}
                                {linesOf(selectedRec).length === 0 ? (
                                    <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <PackageSearch size={36} style={{ opacity: 0.2, display: 'block', margin: '0 auto 0.75rem' }} />
                                        <p style={{ fontWeight: 500, marginBottom: '0.375rem' }}>No items on this count sheet yet</p>
                                        {selectedRec.status === 'Draft' && (
                                            <p style={{ fontSize: 'var(--text-sm)' }}>
                                                Click <strong>Populate All Items</strong> to load every product in this warehouse, or <strong>Add Item</strong> to add individually.
                                            </p>
                                        )}
                                    </div>
                                ) : (
                                    <div style={{ overflowX: 'auto' }}>
                                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                                            <thead>
                                                <tr style={{ borderBottom: '2px solid var(--color-border)', background: 'var(--color-surface)' }}>
                                                    {['Item', 'System Qty', 'Physical Qty', 'Variance', 'Value', 'Reason'].map((h, i) => (
                                                        <th key={h} style={{
                                                            padding: '0.6rem 1rem', fontSize: 'var(--text-xs)', fontWeight: 700,
                                                            textTransform: 'uppercase', letterSpacing: '0.05em',
                                                            color: 'var(--color-text-muted)', whiteSpace: 'nowrap',
                                                            textAlign: i >= 1 && i <= 4 ? 'right' : 'left',
                                                        }}>{h}</th>
                                                    ))}
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {linesOf(selectedRec).map(line => {
                                                    // Use local edit state for live variance preview
                                                    const editQty       = lineEdits[line.id]?.qty ?? String(line.physical_quantity);
                                                    const editReason    = lineEdits[line.id]?.reason ?? (line.reason || '');
                                                    const physNum       = parseFloat(editQty) || 0;
                                                    const sysNum        = Number(line.system_quantity);
                                                    const liveVariance  = physNum - sysNum;
                                                    const liveValue     = liveVariance * Number(line.variance_value / (Number(line.variance_quantity) || 1) || 0);
                                                    const isSaving      = savingLines.has(line.id);

                                                    const varColor = liveVariance < 0 ? '#ef4444' : liveVariance > 0 ? '#10b981' : 'var(--color-text-muted)';

                                                    return (
                                                        <tr key={line.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                                            {/* Item name */}
                                                            <td style={{ padding: '0.55rem 1rem', fontWeight: 500, maxWidth: '200px' }}>
                                                                {line.item_name}
                                                            </td>

                                                            {/* System qty (readonly) */}
                                                            <td style={{ padding: '0.55rem 1rem', textAlign: 'right', color: 'var(--color-text-muted)' }}>
                                                                {Number(sysNum).toFixed(2)}
                                                            </td>

                                                            {/* Physical qty — editable or readonly */}
                                                            <td style={{ padding: '0.3rem 0.5rem', textAlign: 'right' }}>
                                                                {isActive ? (
                                                                    <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}>
                                                                        <input
                                                                            type="number"
                                                                            step="0.01"
                                                                            value={editQty}
                                                                            onChange={e => setLineEdits(prev => ({
                                                                                ...prev,
                                                                                [line.id]: { qty: e.target.value, reason: prev[line.id]?.reason ?? '' },
                                                                            }))}
                                                                            onBlur={() => handleLineSave(selectedRec.id, line.id)}
                                                                            style={{
                                                                                width: '90px', textAlign: 'right',
                                                                                padding: '0.3rem 0.5rem',
                                                                                border: `1px solid ${liveVariance !== 0 ? '#f59e0b' : 'var(--color-border)'}`,
                                                                                borderRadius: '6px',
                                                                                background: liveVariance !== 0 ? 'rgba(245,158,11,0.06)' : 'var(--color-bg)',
                                                                                fontSize: 'var(--text-sm)',
                                                                                fontWeight: 600,
                                                                            }}
                                                                        />
                                                                        {isSaving && <Save size={11} style={{ position: 'absolute', right: '-18px', color: '#3b82f6', animation: 'pulse 1s infinite' }} />}
                                                                    </div>
                                                                ) : (
                                                                    <span style={{ fontWeight: 600 }}>{Number(line.physical_quantity).toFixed(2)}</span>
                                                                )}
                                                            </td>

                                                            {/* Variance */}
                                                            <td style={{ padding: '0.55rem 1rem', textAlign: 'right', fontWeight: 700, color: varColor }}>
                                                                {liveVariance === 0 ? (
                                                                    <span style={{ color: 'var(--color-text-muted)' }}>—</span>
                                                                ) : (
                                                                    `${liveVariance > 0 ? '+' : ''}${liveVariance.toFixed(2)}`
                                                                )}
                                                            </td>

                                                            {/* Variance value */}
                                                            <td style={{ padding: '0.55rem 1rem', textAlign: 'right', color: varColor, fontWeight: 600 }}>
                                                                {Number(line.variance_value) === 0
                                                                    ? <span style={{ color: 'var(--color-text-muted)' }}>—</span>
                                                                    : formatCurrency(Math.abs(Number(line.variance_value)))}
                                                            </td>

                                                            {/* Reason — editable for active */}
                                                            <td style={{ padding: '0.3rem 0.5rem' }}>
                                                                {isActive ? (
                                                                    <input
                                                                        type="text"
                                                                        placeholder="Optional reason..."
                                                                        value={editReason}
                                                                        onChange={e => setLineEdits(prev => ({
                                                                            ...prev,
                                                                            [line.id]: { qty: prev[line.id]?.qty ?? String(line.physical_quantity), reason: e.target.value },
                                                                        }))}
                                                                        onBlur={() => handleLineSave(selectedRec.id, line.id)}
                                                                        style={{
                                                                            width: '100%', padding: '0.3rem 0.5rem',
                                                                            border: '1px solid var(--color-border)', borderRadius: '6px',
                                                                            background: 'var(--color-bg)', fontSize: 'var(--text-sm)',
                                                                        }}
                                                                    />
                                                                ) : (
                                                                    <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>{line.reason || '—'}</span>
                                                                )}
                                                            </td>
                                                        </tr>
                                                    );
                                                })}
                                            </tbody>

                                            {/* Footer totals */}
                                            {linesOf(selectedRec).length > 0 && (
                                                <tfoot>
                                                    <tr style={{ borderTop: '2px solid var(--color-border)', background: 'var(--color-surface)', fontWeight: 700 }}>
                                                        <td style={{ padding: '0.625rem 1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                            {linesOf(selectedRec).length} item{linesOf(selectedRec).length !== 1 ? 's' : ''}
                                                        </td>
                                                        <td style={{ padding: '0.625rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                            {linesOf(selectedRec).reduce((s, l) => s + Number(l.system_quantity), 0).toFixed(2)}
                                                        </td>
                                                        <td style={{ padding: '0.625rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                            {linesOf(selectedRec).reduce((s, l) => s + Number(l.physical_quantity), 0).toFixed(2)}
                                                        </td>
                                                        <td style={{ padding: '0.625rem 1rem', textAlign: 'right', color: totalVarianceValue < 0 ? '#ef4444' : totalVarianceValue > 0 ? '#10b981' : 'var(--color-text-muted)' }}>
                                                            {varianceLines.length > 0 ? `${varianceLines.length} variances` : '✓ All match'}
                                                        </td>
                                                        <td style={{ padding: '0.625rem 1rem', textAlign: 'right', color: totalVarianceValue < 0 ? '#ef4444' : totalVarianceValue > 0 ? '#10b981' : 'var(--color-text-muted)' }}>
                                                            {totalVarianceValue !== 0 ? formatCurrency(Math.abs(totalVarianceValue)) : '—'}
                                                        </td>
                                                        <td />
                                                    </tr>
                                                </tfoot>
                                            )}
                                        </table>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
};

export default ReconciliationList;
