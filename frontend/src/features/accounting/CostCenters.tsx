import { useState, useMemo, useRef } from 'react';
import { Plus, Edit, Trash2, Search, X, Check, ChevronUp, ChevronDown, Target, Filter, Download, Upload, FileDown, ChevronDown as ChevronDownIcon } from 'lucide-react';
import {
    useCostCenters,
    useCreateCostCenter,
    useUpdateCostCenter,
    useDeleteCostCenter,
    exportCostCenters,
    downloadCostCenterTemplate,
    importCostCenters,
} from './hooks/useCostCenters';
import type { CostCenter, CostCenterFormData } from './hooks/useCostCenters';
import AccountingLayout from './AccountingLayout';
import PageHeader from '../../components/PageHeader';
import LoadingScreen from '../../components/common/LoadingScreen';
import { useDialog } from '../../hooks/useDialog';
import logger from '../../utils/logger';
import './styles/glassmorphism.css';

type SortKey = 'code' | 'name' | 'center_type' | 'is_active';

const CENTER_TYPES = [
    { value: 'Department', label: 'Department' },
    { value: 'Project', label: 'Project' },
    { value: 'Activity', label: 'Activity' },
    { value: 'Location', label: 'Location' },
];

const initialFormData: CostCenterFormData = {
    code: '',
    name: '',
    center_type: 'Department',
    parent: null,
    is_active: true,
    gl_account: null,
};

export default function CostCenters() {
    const [showForm, setShowForm] = useState(false);
    const [editingCenter, setEditingCenter] = useState<CostCenter | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [typeFilter, setTypeFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: 'asc' | 'desc' }>({ key: 'code', direction: 'asc' });
    const [formData, setFormData] = useState<CostCenterFormData>(initialFormData);

    const { showConfirm } = useDialog();
    const { data: costCenters, isLoading, isError, error } = useCostCenters();
    const createCenter = useCreateCostCenter();
    const updateCenter = useUpdateCostCenter();
    const deleteCenter = useDeleteCostCenter();

    // Filter and sort
    const filteredAndSorted = useMemo(() => {
        let list = costCenters || [];

        if (typeFilter) {
            list = list.filter((c) => c.center_type === typeFilter);
        }
        if (statusFilter) {
            list = list.filter((c) =>
                statusFilter === 'Active' ? c.is_active : !c.is_active
            );
        }
        if (searchTerm) {
            const term = searchTerm.toLowerCase();
            list = list.filter((c) =>
                c.code.toLowerCase().includes(term) ||
                c.name.toLowerCase().includes(term)
            );
        }

        list = [...list].sort((a, b) => {
            let aVal: any = a[sortConfig.key];
            let bVal: any = b[sortConfig.key];
            if (typeof aVal === 'string') aVal = aVal.toLowerCase();
            if (typeof bVal === 'string') bVal = bVal.toLowerCase();
            if (typeof aVal === 'boolean') { aVal = aVal ? 1 : 0; bVal = bVal ? 1 : 0; }
            if (aVal == null) aVal = '';
            if (bVal == null) bVal = '';
            if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
            if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
            return 0;
        });

        return list;
    }, [costCenters, typeFilter, statusFilter, searchTerm, sortConfig]);

    const requestSort = (key: SortKey) => {
        setSortConfig(prev =>
            prev.key === key && prev.direction === 'asc'
                ? { key, direction: 'desc' }
                : { key, direction: 'asc' }
        );
    };

    const getSortIcon = (key: SortKey) => {
        if (sortConfig.key !== key) return null;
        return sortConfig.direction === 'asc'
            ? <ChevronUp size={14} style={{ marginLeft: '4px', opacity: 0.7 }} />
            : <ChevronDown size={14} style={{ marginLeft: '4px', opacity: 0.7 }} />;
    };

    const handleOpenCreate = () => {
        setEditingCenter(null);
        setFormData(initialFormData);
        setShowForm(true);
    };

    const handleOpenEdit = (center: CostCenter) => {
        setEditingCenter(center);
        setFormData({
            code: center.code,
            name: center.name,
            center_type: center.center_type,
            parent: center.parent,
            is_active: center.is_active,
            gl_account: center.gl_account,
        });
        setShowForm(true);
    };

    const handleCloseForm = () => {
        setShowForm(false);
        setEditingCenter(null);
        setFormData(initialFormData);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            if (editingCenter) {
                await updateCenter.mutateAsync({ id: editingCenter.id, ...formData });
            } else {
                await createCenter.mutateAsync(formData);
            }
            handleCloseForm();
        } catch (err) {
            logger.error('Failed to save cost center:', err);
        }
    };

    const handleDelete = async (id: number) => {
        if (await showConfirm('Are you sure you want to delete this cost center?')) {
            try {
                await deleteCenter.mutateAsync(id);
            } catch (err) {
                logger.error('Failed to delete cost center:', err);
            }
        }
    };

    const totalCenters = costCenters?.length || 0;
    const activeCenters = costCenters?.filter(c => c.is_active).length || 0;
    const departments = costCenters?.filter(c => c.center_type === 'Department').length || 0;
    const projects = costCenters?.filter(c => c.center_type === 'Project').length || 0;

    if (isLoading) {
        return <LoadingScreen message="Loading cost centers..." />;
    }

    const thStyle: React.CSSProperties = {
        padding: '0.75rem 0.75rem', textAlign: 'left', fontWeight: 600,
        fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.05em',
        color: 'var(--color-text-muted)', cursor: 'pointer', userSelect: 'none',
        borderBottom: '2px solid var(--color-border)', whiteSpace: 'nowrap',
    };

    const tdStyle: React.CSSProperties = {
        padding: '0.7rem 0.75rem', fontSize: 'var(--text-sm)',
        borderBottom: '1px solid var(--color-border)',
    };

    const inputStyle: React.CSSProperties = {
        width: '100%', padding: '0.55rem 0.75rem', borderRadius: '8px',
        border: '2.5px solid var(--color-border)', background: 'var(--color-background)',
        color: 'var(--color-text)', fontSize: 'var(--text-sm)', outline: 'none',
    };

    const labelStyle: React.CSSProperties = {
        display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600,
        color: 'var(--color-text)', marginBottom: '0.35rem',
    };

    return (
        <AccountingLayout>
            <div>
                <PageHeader
                    title="Cost Centers"
                    subtitle="Manage cost center codes and descriptions for cost tracking"
                    icon={<Target size={22} />}
                    actions={
                        <button
                            className="btn btn-primary"
                            onClick={handleOpenCreate}
                            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
                        >
                            <Plus size={18} /> Add Cost Center
                        </button>
                    }
                />

                {/* Summary Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Total Centers</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>{totalCenters}</p>
                    </div>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Active</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-cta)' }}>{activeCenters}</p>
                    </div>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Departments</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: '#2471a3' }}>{departments}</p>
                    </div>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Projects</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: '#8b5cf6' }}>{projects}</p>
                    </div>
                </div>

                {/* Filters */}
                <div className="card" style={{ padding: '1rem', marginBottom: '1.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, minWidth: '200px', background: 'var(--color-background)', borderRadius: '8px', padding: '0 0.75rem', border: '1px solid var(--color-border)' }}>
                            <Search size={16} style={{ color: 'var(--color-text-muted)', flexShrink: 0 }} />
                            <input
                                type="text"
                                placeholder="Search by code or name..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                style={{ flex: 1, border: 'none', background: 'transparent', padding: '0.55rem 0', outline: 'none', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}
                            />
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <Filter size={16} style={{ color: 'var(--color-text-muted)' }} />
                            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} style={{ minWidth: '140px', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '2.5px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                <option value="">All Types</option>
                                {CENTER_TYPES.map(t => (
                                    <option key={t.value} value={t.value}>{t.label}</option>
                                ))}
                            </select>
                            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ minWidth: '120px', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '2.5px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                <option value="">All Status</option>
                                <option value="Active">Active</option>
                                <option value="Inactive">Inactive</option>
                            </select>
                        </div>
                    </div>
                </div>

                {/* Error State */}
                {isError && (
                    <div className="card" style={{ padding: '1.5rem', marginBottom: '1.5rem', borderLeft: '4px solid var(--color-error)' }}>
                        <p style={{ color: 'var(--color-error)', fontWeight: 600, margin: 0 }}>
                            Failed to load cost centers: {(error as any)?.message || 'Unknown error'}
                        </p>
                    </div>
                )}

                {/* Table */}
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr>
                                    <th style={thStyle} onClick={() => requestSort('code')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Code {getSortIcon('code')}</div>
                                    </th>
                                    <th style={thStyle} onClick={() => requestSort('name')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Name {getSortIcon('name')}</div>
                                    </th>
                                    <th style={thStyle} onClick={() => requestSort('center_type')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Type {getSortIcon('center_type')}</div>
                                    </th>
                                    <th style={thStyle} onClick={() => requestSort('is_active')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Status {getSortIcon('is_active')}</div>
                                    </th>
                                    <th style={{ ...thStyle, textAlign: 'center', cursor: 'default' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredAndSorted.length === 0 ? (
                                    <tr>
                                        <td colSpan={5} style={{ ...tdStyle, textAlign: 'center', padding: '2.5rem', color: 'var(--color-text-muted)' }}>
                                            {costCenters?.length === 0
                                                ? 'No cost centers yet. Click "Add Cost Center" to create one.'
                                                : 'No cost centers match your filters.'}
                                        </td>
                                    </tr>
                                ) : (
                                    filteredAndSorted.map((center) => (
                                        <tr
                                            key={center.id}
                                            style={{ transition: 'background 0.1s' }}
                                            onMouseOver={(e) => e.currentTarget.style.background = 'rgba(59,130,246,0.04)'}
                                            onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
                                        >
                                            <td style={{ ...tdStyle, fontWeight: 600, fontFamily: 'monospace', color: 'var(--color-primary)' }}>
                                                {center.code}
                                            </td>
                                            <td style={{ ...tdStyle, fontWeight: 500 }}>
                                                {center.name}
                                            </td>
                                            <td style={tdStyle}>
                                                <span style={{
                                                    padding: '0.15rem 0.5rem', borderRadius: '4px',
                                                    fontSize: 'var(--text-xs)', fontWeight: 500,
                                                    background: center.center_type === 'Department' ? 'rgba(59,130,246,0.08)' :
                                                        center.center_type === 'Project' ? 'rgba(139,92,246,0.08)' :
                                                        center.center_type === 'Activity' ? 'rgba(245,158,11,0.08)' :
                                                        'rgba(16,185,129,0.08)',
                                                    color: center.center_type === 'Department' ? '#2471a3' :
                                                        center.center_type === 'Project' ? '#8b5cf6' :
                                                        center.center_type === 'Activity' ? '#f59e0b' :
                                                        '#10b981',
                                                }}>
                                                    {center.center_type}
                                                </span>
                                            </td>
                                            <td style={tdStyle}>
                                                <span style={{
                                                    display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                                    padding: '0.15rem 0.5rem', borderRadius: '4px',
                                                    fontSize: 'var(--text-xs)', fontWeight: 500,
                                                    background: center.is_active ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
                                                    color: center.is_active ? '#10b981' : '#ef4444',
                                                }}>
                                                    {center.is_active ? <Check size={12} /> : <X size={12} />}
                                                    {center.is_active ? 'Active' : 'Inactive'}
                                                </span>
                                            </td>
                                            <td style={{ ...tdStyle, textAlign: 'center' }}>
                                                <div style={{ display: 'flex', justifyContent: 'center', gap: '0.4rem' }}>
                                                    <button
                                                        onClick={() => handleOpenEdit(center)}
                                                        title="Edit"
                                                        style={{
                                                            padding: '0.3rem 0.5rem', borderRadius: '6px',
                                                            border: '1px solid var(--color-border)',
                                                            background: 'var(--color-surface)',
                                                            color: 'var(--color-text-muted)', cursor: 'pointer',
                                                            fontSize: 'var(--text-xs)', display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                                        }}
                                                    >
                                                        <Edit size={13} />
                                                    </button>
                                                    <button
                                                        onClick={() => handleDelete(center.id)}
                                                        title="Delete"
                                                        style={{
                                                            padding: '0.3rem 0.5rem', borderRadius: '6px',
                                                            border: '1px solid rgba(239,68,68,0.3)',
                                                            background: 'rgba(239,68,68,0.05)',
                                                            color: '#ef4444', cursor: 'pointer',
                                                            fontSize: 'var(--text-xs)', display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                                        }}
                                                    >
                                                        <Trash2 size={13} />
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                    <div style={{ padding: '0.75rem 1rem', borderTop: '1px solid var(--color-border)', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                        Showing {filteredAndSorted.length} of {totalCenters} cost centers
                    </div>
                </div>

                {/* Create/Edit Modal */}
                {showForm && (
                    <div
                        style={{
                            position: 'fixed', inset: 0, zIndex: 1000,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)',
                        }}
                        onClick={(e) => { if (e.target === e.currentTarget) handleCloseForm(); }}
                    >
                        <div style={{
                            background: 'var(--color-surface)', borderRadius: '16px',
                            padding: '2rem', width: '100%', maxWidth: '500px',
                            border: '1px solid var(--color-border)',
                            boxShadow: '0 25px 50px rgba(0,0,0,0.25)',
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                                <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                                    {editingCenter ? 'Edit Cost Center' : 'New Cost Center'}
                                </h2>
                                <button
                                    onClick={handleCloseForm}
                                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', padding: '0.25rem' }}
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            <form onSubmit={handleSubmit}>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                        <div>
                                            <label style={labelStyle}>Code<span className="required-mark"> *</span></label>
                                            <input
                                                style={inputStyle}
                                                value={formData.code}
                                                onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                                                placeholder="e.g., CC-001"
                                                required
                                            />
                                        </div>
                                        <div>
                                            <label style={labelStyle}>Type<span className="required-mark"> *</span></label>
                                            <select
                                                style={inputStyle}
                                                value={formData.center_type}
                                                onChange={(e) => setFormData({ ...formData, center_type: e.target.value })}
                                                required
                                            >
                                                {CENTER_TYPES.map(t => (
                                                    <option key={t.value} value={t.value}>{t.label}</option>
                                                ))}
                                            </select>
                                        </div>
                                    </div>

                                    <div>
                                        <label style={labelStyle}>Name<span className="required-mark"> *</span></label>
                                        <input
                                            style={inputStyle}
                                            value={formData.name}
                                            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                            placeholder="e.g., Finance Department"
                                            required
                                        />
                                    </div>

                                    <div>
                                        <label style={labelStyle}>Parent Cost Center</label>
                                        <select
                                            style={inputStyle}
                                            value={formData.parent ?? ''}
                                            onChange={(e) => setFormData({ ...formData, parent: e.target.value ? Number(e.target.value) : null })}
                                        >
                                            <option value="">None (Top Level)</option>
                                            {(costCenters || [])
                                                .filter(c => c.id !== editingCenter?.id)
                                                .map(c => (
                                                    <option key={c.id} value={c.id}>{c.code} - {c.name}</option>
                                                ))}
                                        </select>
                                    </div>

                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <input
                                            type="checkbox"
                                            id="is_active"
                                            checked={formData.is_active}
                                            onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                                            style={{ width: '16px', height: '16px' }}
                                        />
                                        <label htmlFor="is_active" style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text)', cursor: 'pointer' }}>
                                            Active
                                        </label>
                                    </div>

                                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
                                        <button
                                            type="button"
                                            className="btn btn-outline"
                                            onClick={handleCloseForm}
                                        >
                                            Cancel
                                        </button>
                                        <button
                                            type="submit"
                                            className="btn btn-primary"
                                            disabled={createCenter.isPending || updateCenter.isPending}
                                            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
                                        >
                                            {(createCenter.isPending || updateCenter.isPending) ? 'Saving...' :
                                                editingCenter ? 'Update' : 'Create'}
                                        </button>
                                    </div>
                                </div>
                            </form>
                        </div>
                    </div>
                )}
            </div>
        </AccountingLayout>
    );
}
