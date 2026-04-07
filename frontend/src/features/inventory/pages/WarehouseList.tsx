import { useState } from 'react';
import { useWarehouses, useCreateWarehouse, useUpdateWarehouse, useDeleteWarehouse } from '../hooks/useInventory';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Building2, MapPin, Plus, Edit2, Trash2, Star, ChevronDown, ChevronUp } from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

interface Warehouse {
    id: number;
    name: string;
    location?: string;
    is_active: boolean;
    is_central: boolean;
}

interface FormData {
    name: string;
    location: string;
    is_active: boolean;
    is_central: boolean;
}

const DEFAULT_FORM: FormData = { name: '', location: '', is_active: true, is_central: false };

// ─── Toggle Switch ────────────────────────────────────────────────────────────

const ToggleSwitch = ({
    checked,
    onChange,
    label,
}: {
    checked: boolean;
    onChange: (v: boolean) => void;
    label: string;
}) => (
    <label style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', cursor: 'pointer', userSelect: 'none' }}>
        <div
            onClick={() => onChange(!checked)}
            style={{
                width: '40px',
                height: '22px',
                borderRadius: '11px',
                background: checked ? 'var(--color-success)' : 'var(--color-border)',
                position: 'relative',
                transition: 'background 0.2s',
                flexShrink: 0,
                cursor: 'pointer',
            }}
        >
            <div style={{
                width: '16px',
                height: '16px',
                borderRadius: '50%',
                background: '#fff',
                position: 'absolute',
                top: '3px',
                left: checked ? '21px' : '3px',
                transition: 'left 0.2s',
                boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
            }} />
        </div>
        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>{label}</span>
    </label>
);

// ─── Warehouse Card ────────────────────────────────────────────────────────────

const WarehouseCard = ({
    warehouse,
    onEdit,
    onDelete,
    confirmDelete,
    setConfirmDelete,
}: {
    warehouse: Warehouse;
    onEdit: (wh: Warehouse) => void;
    onDelete: (id: number) => void;
    confirmDelete: number | null;
    setConfirmDelete: (id: number | null) => void;
}) => {
    const borderColor = warehouse.is_active ? 'var(--color-success)' : 'var(--color-border)';

    return (
        <div
            className="card"
            style={{
                padding: 0,
                overflow: 'hidden',
                borderLeft: `4px solid ${borderColor}`,
                transition: 'box-shadow 0.2s',
            }}
        >
            {/* Card top */}
            <div style={{ padding: '1.25rem 1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
                        <span style={{ fontSize: 'var(--text-lg)', fontWeight: 800, color: 'var(--color-text)' }}>{warehouse.name}</span>

                        {warehouse.is_central && (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.15rem 0.55rem', borderRadius: '99px', fontSize: 'var(--text-xs)', fontWeight: 700, background: 'rgba(245,158,11,0.18)', color: '#d97706' }}>
                                <Star size={11} strokeWidth={2.5} /> Central
                            </span>
                        )}

                        <span style={{
                            padding: '0.15rem 0.55rem',
                            borderRadius: '99px',
                            fontSize: 'var(--text-xs)',
                            fontWeight: 600,
                            background: warehouse.is_active ? 'rgba(16,185,129,0.15)' : 'rgba(156,163,175,0.2)',
                            color: warehouse.is_active ? 'var(--color-success)' : '#9ca3af',
                        }}>
                            {warehouse.is_active ? 'Active' : 'Inactive'}
                        </span>
                    </div>

                    {warehouse.location ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                            <MapPin size={14} strokeWidth={2} />
                            <span>{warehouse.location}</span>
                        </div>
                    ) : (
                        <div style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>No location specified</div>
                    )}
                </div>

                {/* Actions */}
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexShrink: 0 }}>
                    {confirmDelete === warehouse.id ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-error)', fontWeight: 600 }}>Delete?</span>
                            <button
                                onClick={() => onDelete(warehouse.id)}
                                style={{ background: 'var(--color-error)', color: '#fff', border: 'none', borderRadius: '6px', padding: '0.3rem 0.75rem', fontSize: 'var(--text-xs)', fontWeight: 600, cursor: 'pointer' }}
                            >Yes</button>
                            <button
                                onClick={() => setConfirmDelete(null)}
                                style={{ background: 'var(--color-surface)', color: 'var(--color-text-muted)', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '0.3rem 0.75rem', fontSize: 'var(--text-xs)', cursor: 'pointer' }}
                            >No</button>
                        </div>
                    ) : (
                        <>
                            <button
                                className="btn btn-outline"
                                onClick={() => onEdit(warehouse)}
                                style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '0.4rem 0.85rem', fontSize: 'var(--text-xs)' }}
                            >
                                <Edit2 size={14} /> Edit
                            </button>
                            <button
                                className="btn btn-outline"
                                onClick={() => setConfirmDelete(warehouse.id)}
                                style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '0.4rem 0.85rem', fontSize: 'var(--text-xs)', color: 'var(--color-error)', borderColor: 'var(--color-error)' }}
                            >
                                <Trash2 size={14} /> Delete
                            </button>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};

// ─── Component ────────────────────────────────────────────────────────────────

const WarehouseList = () => {
    const { data: warehousesRaw, isLoading } = useWarehouses();
    const createWarehouse = useCreateWarehouse();
    const updateWarehouse = useUpdateWarehouse();
    const deleteWarehouse = useDeleteWarehouse();

    const [formOpen, setFormOpen]   = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [formData, setFormData]   = useState<FormData>(DEFAULT_FORM);
    const [formError, setFormError] = useState<string | null>(null);
    const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

    if (isLoading) return <LoadingScreen message="Loading warehouses..." />;

    const warehousesList: Warehouse[] = Array.isArray((warehousesRaw as any)?.results)
        ? (warehousesRaw as any).results
        : Array.isArray(warehousesRaw) ? warehousesRaw as any : [];

    const totalCount    = warehousesList.length;
    const activeCount   = warehousesList.filter(w => w.is_active).length;
    const centralCount  = warehousesList.filter(w => w.is_central).length;

    const openNewForm = () => {
        setEditingId(null);
        setFormData(DEFAULT_FORM);
        setFormError(null);
        setFormOpen(true);
    };

    const openEditForm = (wh: Warehouse) => {
        setEditingId(wh.id);
        setFormData({ name: wh.name, location: wh.location || '', is_active: wh.is_active, is_central: wh.is_central });
        setFormError(null);
        setFormOpen(true);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError(null);
        try {
            if (editingId !== null) {
                await updateWarehouse.mutateAsync({ id: editingId, data: formData });
            } else {
                await createWarehouse.mutateAsync(formData);
            }
            setFormOpen(false);
            setEditingId(null);
            setFormData(DEFAULT_FORM);
        } catch (err: any) {
            const raw = err?.response?.data;
            const msg =
                raw?.detail ||
                raw?.error ||
                (typeof raw === 'object' && raw !== null ? JSON.stringify(raw) : null) ||
                err?.message ||
                'An unexpected error occurred';
            setFormError(msg);
        }
    };

    const handleDelete = async (id: number) => {
        try {
            await deleteWarehouse.mutateAsync(id);
            setConfirmDelete(null);
        } catch (err: any) {
            const msg = err?.response?.data?.detail || err?.message || 'Cannot delete — may have associated stock.';
            setFormError(msg);
            setConfirmDelete(null);
        }
    };

    const isPending = createWarehouse.isPending || updateWarehouse.isPending;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }} className="animate-fade">
                <PageHeader
                    title="Warehouses"
                    subtitle="Manage warehouse locations and settings."
                    icon={<Building2 size={22} />}
                    actions={
                        <button className="btn btn-primary" onClick={openNewForm}>
                            <Plus size={16} /> New Warehouse
                        </button>
                    }
                />

                {/* ── Summary Cards ────────────────────────────────────────── */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1.25rem', marginBottom: '2rem' }}>
                    {[
                        { label: 'Total Warehouses',   value: totalCount,  color: 'var(--color-primary)', bg: 'rgba(59,130,246,0.12)' },
                        { label: 'Active',             value: activeCount,  color: 'var(--color-success)', bg: 'rgba(16,185,129,0.12)' },
                        { label: 'Central Warehouses', value: centralCount, color: '#f59e0b',               bg: 'rgba(245,158,11,0.12)' },
                    ].map(({ label, value, color, bg }) => (
                        <div key={label} className="card" style={{ borderLeft: `4px solid ${color}` }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                <div style={{ padding: '0.75rem', borderRadius: '0.625rem', background: bg, flexShrink: 0 }}>
                                    <Building2 size={20} style={{ color }} />
                                </div>
                                <div>
                                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
                                    <div style={{ fontSize: 'var(--text-xl)', fontWeight: 800 }}>{value}</div>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>

                {/* ── Error Banner ─────────────────────────────────────────── */}
                {formError && (
                    <div style={{ padding: '0.75rem 1rem', background: 'rgba(239,68,68,0.1)', color: 'var(--color-error)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '8px', marginBottom: '1.25rem', fontSize: 'var(--text-sm)' }}>
                        {formError}
                    </div>
                )}

                {/* ── Collapsible Form ─────────────────────────────────────── */}
                {formOpen && (
                    <div className="card" style={{ marginBottom: '2rem', borderTop: '3px solid var(--color-primary)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                            <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0 }}>
                                {editingId !== null ? 'Edit Warehouse' : 'New Warehouse'}
                            </h3>
                            <button
                                onClick={() => { setFormOpen(false); setFormError(null); }}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', padding: '0.25rem' }}
                            >
                                <ChevronUp size={18} />
                            </button>
                        </div>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.25rem' }}>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.4rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                                        Name <span style={{ color: 'var(--color-error)' }}>*</span>
                                    </label>
                                    <input
                                        type="text"
                                        className="input"
                                        value={formData.name}
                                        onChange={e => setFormData({ ...formData, name: e.target.value })}
                                        placeholder="e.g. Main Warehouse"
                                        required
                                    />
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.4rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                                        Location <span style={{ color: 'var(--color-error)' }}>*</span>
                                    </label>
                                    <input
                                        type="text"
                                        className="input"
                                        value={formData.location}
                                        onChange={e => setFormData({ ...formData, location: e.target.value })}
                                        placeholder="e.g. 123 Industrial Ave"
                                        required
                                    />
                                </div>
                            </div>

                            <div style={{ display: 'flex', gap: '2rem', marginBottom: '1.5rem' }}>
                                <ToggleSwitch
                                    checked={formData.is_active}
                                    onChange={v => setFormData({ ...formData, is_active: v })}
                                    label="Active"
                                />
                                <ToggleSwitch
                                    checked={formData.is_central}
                                    onChange={v => setFormData({ ...formData, is_central: v })}
                                    label="Central Warehouse"
                                />
                            </div>

                            <div style={{ display: 'flex', gap: '0.75rem' }}>
                                <button type="submit" className="btn btn-primary" disabled={isPending}>
                                    {isPending ? 'Saving...' : editingId !== null ? 'Update Warehouse' : 'Create Warehouse'}
                                </button>
                                <button
                                    type="button"
                                    className="btn btn-outline"
                                    onClick={() => { setFormOpen(false); setFormError(null); }}
                                >
                                    Cancel
                                </button>
                            </div>
                        </form>
                    </div>
                )}

                {/* ── Collapse trigger when form is closed ─────────────────── */}
                {!formOpen && (
                    <button
                        onClick={openNewForm}
                        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', background: 'none', border: '1px dashed var(--color-border)', borderRadius: '8px', padding: '0.5rem 1rem', cursor: 'pointer', marginBottom: '1.5rem', width: '100%', justifyContent: 'center' }}
                    >
                        <ChevronDown size={16} /> Add a warehouse
                    </button>
                )}

                {/* ── Warehouse Grid ───────────────────────────────────────── */}
                {warehousesList.length === 0 ? (
                    <div className="card" style={{ textAlign: 'center', padding: '4rem 2rem' }}>
                        <Building2 size={48} style={{ opacity: 0.15, display: 'block', margin: '0 auto 1rem' }} />
                        <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>No warehouses configured</div>
                        <div style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>Create your first warehouse to get started.</div>
                    </div>
                ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem' }}>
                        {warehousesList.map(wh => (
                            <WarehouseCard
                                key={wh.id}
                                warehouse={wh}
                                onEdit={openEditForm}
                                onDelete={handleDelete}
                                confirmDelete={confirmDelete}
                                setConfirmDelete={setConfirmDelete}
                            />
                        ))}
                    </div>
                )}
            </main>
        </div>
    );
};

export default WarehouseList;
