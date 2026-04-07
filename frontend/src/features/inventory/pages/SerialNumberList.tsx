import { useState, useMemo } from 'react';
import {
    useSerialNumbers,
    useItems,
    useWarehouses,
    useCreateSerialNumber,
    useDeleteSerialNumber,
} from '../hooks/useInventory';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import { Hash, MapPin, Plus, Trash2, ChevronDown, ChevronUp, Barcode } from 'lucide-react';

interface SerialNumber {
    id: number;
    serial_number: string;
    item: number;
    item_name: string;
    sku?: string;
    warehouse: number;
    warehouse_name: string;
    status: string;
    purchase_date?: string;
    purchase_price?: string | number;
    warranty_start?: string;
    warranty_end?: string;
    current_location?: string;
    notes?: string;
    sale_date?: string;
}

interface Item {
    id: number;
    sku: string;
    name: string;
}

interface Warehouse {
    id: number;
    name: string;
    location?: string;
}

const STATUS_OPTIONS = ['All', 'Available', 'Allocated', 'Sold', 'Returned', 'Defective', 'Scrapped'];

const STATUS_STYLE: Record<string, { background: string; color: string; label: string }> = {
    available: { background: '#d1fae5', color: '#065f46', label: 'Available' },
    allocated: { background: '#dbeafe', color: '#1e40af', label: 'Allocated' },
    sold:      { background: '#ede9fe', color: '#5b21b6', label: 'Sold' },
    returned:  { background: '#ffedd5', color: '#9a3412', label: 'Returned' },
    defective: { background: '#fee2e2', color: '#991b1b', label: 'Defective' },
    scrapped:  { background: '#f1f5f9', color: '#475569', label: 'Scrapped' },
};

const EMPTY_FORM = {
    serial_number: '',
    item: '',
    warehouse: '',
    purchase_date: '',
    purchase_price: '',
    warranty_start: '',
    warranty_end: '',
    notes: '',
};

function warrantyStatus(end?: string): 'active' | 'expired' | 'none' {
    if (!end) return 'none';
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return new Date(end) >= today ? 'active' : 'expired';
}

const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '9px 14px',
    borderRadius: '8px',
    border: '2px solid var(--color-border, #e2e8f0)',
    fontSize: '13px',
    fontFamily: 'inherit',
    background: '#f8fafc',
    boxSizing: 'border-box',
};

const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '12px',
    fontWeight: 600,
    marginBottom: '6px',
    color: 'var(--color-text)',
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

const SerialNumberList = () => {
    const { formatCurrency } = useCurrency();

    const [search, setSearch]               = useState('');
    const [statusFilter, setStatusFilter]   = useState('All');
    const [itemFilter, setItemFilter]       = useState('');
    const [warehouseFilter, setWarehouseFilter] = useState('');
    const [showForm, setShowForm]           = useState(false);
    const [form, setForm]                   = useState({ ...EMPTY_FORM });
    const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
    const [formError, setFormError]         = useState('');

    const apiFilters: Record<string, string> = {};
    if (statusFilter !== 'All') apiFilters.status    = statusFilter.toLowerCase();
    if (itemFilter)             apiFilters.item       = itemFilter;
    if (warehouseFilter)        apiFilters.warehouse  = warehouseFilter;
    if (search)                 apiFilters.search     = search;

    const { data: serialData, isLoading } = useSerialNumbers(apiFilters);
    const { data: itemsData }             = useItems();
    const { data: warehousesData }        = useWarehouses();
    const createSerial                    = useCreateSerialNumber();
    const deleteSerial                    = useDeleteSerialNumber();

    const serials: SerialNumber[] = useMemo(() => serialData?.results ?? serialData ?? [], [serialData]);
    const items: Item[]           = useMemo(() => itemsData?.results ?? itemsData ?? [], [itemsData]);
    const warehouses: Warehouse[] = useMemo(() => warehousesData?.results ?? warehousesData ?? [], [warehousesData]);

    const kpiTotal     = serials.length;
    const kpiAvailable = serials.filter(s => s.status === 'available').length;
    const kpiAllocSold = serials.filter(s => s.status === 'allocated' || s.status === 'sold').length;
    const kpiDefective = serials.filter(s => s.status === 'defective' || s.status === 'returned').length;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');
        if (!form.serial_number || !form.item || !form.warehouse) {
            setFormError('Serial Number, Item, and Warehouse are required.');
            return;
        }
        try {
            await createSerial.mutateAsync({
                serial_number:  form.serial_number,
                item:           parseInt(form.item),
                warehouse:      parseInt(form.warehouse),
                purchase_date:  form.purchase_date  || undefined,
                purchase_price: form.purchase_price ? parseFloat(form.purchase_price) : undefined,
                warranty_start: form.warranty_start || undefined,
                warranty_end:   form.warranty_end   || undefined,
                notes:          form.notes          || undefined,
            });
            setForm({ ...EMPTY_FORM });
            setShowForm(false);
        } catch (err: any) {
            setFormError(err?.response?.data?.detail ?? err?.message ?? 'Failed to create serial number.');
        }
    };

    const handleDelete = async (id: number) => {
        try {
            await deleteSerial.mutateAsync(id);
        } finally {
            setConfirmDelete(null);
        }
    };

    const clearFilters = () => {
        setSearch('');
        setStatusFilter('All');
        setItemFilter('');
        setWarehouseFilter('');
    };

    const hasFilters = search || statusFilter !== 'All' || itemFilter || warehouseFilter;

    if (isLoading) return <LoadingScreen message="Loading serial numbers..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }} className="animate-fade">

                <PageHeader
                    title="Serial Numbers"
                    subtitle="Track individual unit serial numbers and warranty status"
                    icon={<Barcode size={22} />}
                    actions={
                        <button
                            onClick={() => setShowForm(v => !v)}
                            style={{
                                display: 'inline-flex', alignItems: 'center', gap: '6px',
                                padding: '0.5rem 1.1rem', borderRadius: '8px',
                                fontSize: '13px', fontWeight: 600,
                                border: 'none', cursor: 'pointer',
                                background: 'rgba(255,255,255,0.18)', color: 'white',
                                fontFamily: 'inherit',
                            }}
                        >
                            <Plus size={14} />
                            Add Serial Number
                            {showForm ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </button>
                    }
                />

                {/* KPI Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
                    {[
                        { label: 'Total Serials',        value: kpiTotal,     accent: '#3b82f6', bg: '#eff6ff' },
                        { label: 'Available',            value: kpiAvailable, accent: '#059669', bg: '#f0fdf4' },
                        { label: 'Allocated / Sold',     value: kpiAllocSold, accent: '#7c3aed', bg: '#f5f3ff' },
                        { label: 'Defective / Returned', value: kpiDefective, accent: '#dc2626', bg: '#fef2f2' },
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

                {/* Collapsible Add Form */}
                {showForm && (
                    <div className="card" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--color-text)' }}>
                            <Plus size={16} /> Add New Serial Number
                        </h3>
                        {formError && (
                            <div style={{ padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626', borderRadius: '8px', marginBottom: '1rem', fontSize: 'var(--text-sm)' }}>
                                {formError}
                            </div>
                        )}
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                <div>
                                    <label style={labelStyle}>Serial Number <span style={{ color: '#ef4444' }}>*</span></label>
                                    <input
                                        style={{ ...inputStyle, fontFamily: 'monospace', letterSpacing: '0.03em' }}
                                        value={form.serial_number}
                                        onChange={e => setForm(f => ({ ...f, serial_number: e.target.value }))}
                                        placeholder="e.g. SN-20240001"
                                        required
                                    />
                                </div>
                                <div>
                                    <label style={labelStyle}>Item <span style={{ color: '#ef4444' }}>*</span></label>
                                    <select style={inputStyle} value={form.item} onChange={e => setForm(f => ({ ...f, item: e.target.value }))} required>
                                        <option value="">Select item...</option>
                                        {items.map(i => <option key={i.id} value={i.id}>{i.name} ({i.sku})</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={labelStyle}>Warehouse <span style={{ color: '#ef4444' }}>*</span></label>
                                    <select style={inputStyle} value={form.warehouse} onChange={e => setForm(f => ({ ...f, warehouse: e.target.value }))} required>
                                        <option value="">Select warehouse...</option>
                                        {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={labelStyle}>Purchase Date</label>
                                    <input type="date" style={inputStyle} value={form.purchase_date} onChange={e => setForm(f => ({ ...f, purchase_date: e.target.value }))} />
                                </div>
                                <div>
                                    <label style={labelStyle}>Purchase Price</label>
                                    <input type="number" step="0.01" min="0" style={inputStyle} value={form.purchase_price} onChange={e => setForm(f => ({ ...f, purchase_price: e.target.value }))} placeholder="0.00" />
                                </div>
                                <div>
                                    <label style={labelStyle}>Warranty Start</label>
                                    <input type="date" style={inputStyle} value={form.warranty_start} onChange={e => setForm(f => ({ ...f, warranty_start: e.target.value }))} />
                                </div>
                                <div>
                                    <label style={labelStyle}>Warranty End</label>
                                    <input type="date" style={inputStyle} value={form.warranty_end} onChange={e => setForm(f => ({ ...f, warranty_end: e.target.value }))} />
                                </div>
                                <div style={{ gridColumn: '1 / -1' }}>
                                    <label style={labelStyle}>Notes</label>
                                    <textarea
                                        rows={2}
                                        style={{ ...inputStyle, resize: 'vertical' }}
                                        value={form.notes}
                                        onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                                        placeholder="Optional notes..."
                                    />
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                                <button
                                    type="button"
                                    onClick={() => { setShowForm(false); setFormError(''); setForm({ ...EMPTY_FORM }); }}
                                    style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: '1px solid var(--color-border, #e2e8f0)', cursor: 'pointer', background: '#f8fafc', color: '#475569', fontFamily: 'inherit' }}
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={createSerial.isPending}
                                    style={{ padding: '9px 24px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', fontFamily: 'inherit', opacity: createSerial.isPending ? 0.7 : 1 }}
                                >
                                    {createSerial.isPending ? 'Adding...' : 'Add Serial Number'}
                                </button>
                            </div>
                        </form>
                    </div>
                )}

                {/* Filter Bar */}
                <div className="card" style={{ padding: '1rem 1.25rem', marginBottom: '1.25rem', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center' }}>
                    <input
                        style={{ ...inputStyle, width: '220px', flex: 'none' }}
                        placeholder="Search serial number..."
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                    />
                    <select style={{ ...inputStyle, width: '160px', flex: 'none' }} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
                        {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <select style={{ ...inputStyle, width: '200px', flex: 'none' }} value={itemFilter} onChange={e => setItemFilter(e.target.value)}>
                        <option value="">All Items</option>
                        {items.map(i => <option key={i.id} value={String(i.id)}>{i.name}</option>)}
                    </select>
                    <select style={{ ...inputStyle, width: '180px', flex: 'none' }} value={warehouseFilter} onChange={e => setWarehouseFilter(e.target.value)}>
                        <option value="">All Warehouses</option>
                        {warehouses.map(w => <option key={w.id} value={String(w.id)}>{w.name}</option>)}
                    </select>
                    {hasFilters && (
                        <button
                            onClick={clearFilters}
                            style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: '0 4px', textDecoration: 'underline' }}
                        >
                            Clear filters
                        </button>
                    )}
                    <span style={{ marginLeft: 'auto', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', fontWeight: 500 }}>
                        {serials.length} result{serials.length !== 1 ? 's' : ''}
                    </span>
                </div>

                {/* Table */}
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '960px' }}>
                            <thead>
                                <tr style={{ background: 'var(--color-surface)', borderBottom: '2px solid var(--color-border)' }}>
                                    <th style={thStyle}><span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}><Hash size={12} />Serial Number</span></th>
                                    <th style={thStyle}>Product</th>
                                    <th style={thStyle}><span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}><MapPin size={12} />Warehouse</span></th>
                                    <th style={thStyle}>Status</th>
                                    <th style={thStyle}>Purchase Date</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Purchase Price</th>
                                    <th style={thStyle}>Warranty</th>
                                    <th style={thStyle}>Location</th>
                                    <th style={{ ...thStyle, width: '72px' }}></th>
                                </tr>
                            </thead>
                            <tbody>
                                {serials.length === 0 ? (
                                    <tr>
                                        <td colSpan={9} style={{ padding: '3.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                            No serial numbers found. Adjust your filters or add a new entry.
                                        </td>
                                    </tr>
                                ) : (
                                    serials.map((sn) => {
                                        const statusKey  = (sn.status ?? '').toLowerCase();
                                        const statusMeta = STATUS_STYLE[statusKey] ?? { background: '#f1f5f9', color: '#475569', label: sn.status };
                                        const wStatus    = warrantyStatus(sn.warranty_end);

                                        return (
                                            <tr key={sn.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                                <td style={tdStyle}>
                                                    <span style={{ fontFamily: 'monospace', fontWeight: 700, letterSpacing: '0.04em', fontSize: '13px' }}>
                                                        {sn.serial_number}
                                                    </span>
                                                </td>
                                                <td style={tdStyle}>
                                                    <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>{sn.item_name}</div>
                                                    {sn.sku && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '2px' }}>{sn.sku}</div>}
                                                </td>
                                                <td style={tdStyle}>
                                                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                                        <MapPin size={13} />{sn.warehouse_name}
                                                    </span>
                                                </td>
                                                <td style={tdStyle}>
                                                    <span style={{
                                                        display: 'inline-block',
                                                        padding: '3px 10px',
                                                        borderRadius: '20px',
                                                        fontSize: 'var(--text-xs)',
                                                        fontWeight: 700,
                                                        background: statusMeta.background,
                                                        color: statusMeta.color,
                                                        textTransform: 'capitalize',
                                                        whiteSpace: 'nowrap',
                                                    }}>
                                                        {statusMeta.label}
                                                    </span>
                                                </td>
                                                <td style={{ ...tdStyle, color: 'var(--color-text-muted)' }}>
                                                    {sn.purchase_date ? sn.purchase_date.split('T')[0] : '—'}
                                                </td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600 }}>
                                                    {sn.purchase_price != null && sn.purchase_price !== ''
                                                        ? formatCurrency(Number(sn.purchase_price))
                                                        : '—'}
                                                </td>
                                                <td style={tdStyle}>
                                                    {wStatus === 'none' ? (
                                                        <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>—</span>
                                                    ) : (
                                                        <div>
                                                            <span style={{
                                                                display: 'inline-block',
                                                                padding: '2px 8px',
                                                                borderRadius: '12px',
                                                                fontSize: 'var(--text-xs)',
                                                                fontWeight: 700,
                                                                background: wStatus === 'active' ? '#d1fae5' : '#fee2e2',
                                                                color: wStatus === 'active' ? '#065f46' : '#991b1b',
                                                                marginBottom: '3px',
                                                            }}>
                                                                {wStatus === 'active' ? 'Active' : 'Expired'}
                                                            </span>
                                                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '2px' }}>
                                                                {sn.warranty_start?.split('T')[0]} → {sn.warranty_end?.split('T')[0]}
                                                            </div>
                                                        </div>
                                                    )}
                                                </td>
                                                <td style={{ ...tdStyle, fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                    {sn.current_location || '—'}
                                                </td>
                                                <td style={tdStyle}>
                                                    {confirmDelete === sn.id ? (
                                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-start' }}>
                                                            <span style={{ fontSize: '11px', color: '#dc2626', fontWeight: 600 }}>Confirm?</span>
                                                            <div style={{ display: 'flex', gap: '4px' }}>
                                                                <button
                                                                    onClick={() => handleDelete(sn.id)}
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
                                                            onClick={() => setConfirmDelete(sn.id)}
                                                            style={{ color: 'var(--color-error)', padding: '0.25rem 0.5rem', display: 'inline-flex', alignItems: 'center' }}
                                                            title="Delete serial number"
                                                        >
                                                            <Trash2 size={14} />
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
            </main>
        </div>
    );
};

export default SerialNumberList;
