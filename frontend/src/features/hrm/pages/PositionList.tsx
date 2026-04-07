import { useState } from 'react';
import { usePositions, useDepartments, useCreatePosition, useUpdatePosition, useDeletePosition } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, Edit, Trash2, Briefcase, Search, X } from 'lucide-react';
import '../../accounting/styles/glassmorphism.css';
import { useDialog } from '../../../hooks/useDialog';

const GRADE_OPTIONS = [
    { value: 'Entry', label: 'Entry Level' },
    { value: 'Mid', label: 'Mid Level' },
    { value: 'Senior', label: 'Senior Level' },
    { value: 'Manager', label: 'Manager' },
    { value: 'Director', label: 'Director' },
    { value: 'Executive', label: 'Executive' },
];

const gradeColors: Record<string, { bg: string; color: string }> = {
    Entry: { bg: 'rgba(156, 163, 175, 0.1)', color: '#9ca3af' },
    Mid: { bg: 'rgba(36, 113, 163, 0.1)', color: '#2471a3' },
    Senior: { bg: 'rgba(139, 92, 246, 0.1)', color: '#8b5cf6' },
    Manager: { bg: 'rgba(245, 158, 11, 0.1)', color: '#f59e0b' },
    Director: { bg: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' },
    Executive: { bg: 'rgba(16, 185, 129, 0.1)', color: '#10b981' },
};

const selectStyle: React.CSSProperties = {
    width: '100%', padding: '0.625rem', borderRadius: '8px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-sm)',
};
const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.625rem', borderRadius: '8px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-sm)',
};
const labelStyle: React.CSSProperties = {
    display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600,
    color: 'var(--color-text)', marginBottom: '0.375rem',
};

const PositionList = () => {
    const { showAlert, showConfirm } = useDialog();
    const { data: positionsData, isLoading } = usePositions();
    const { data: departmentsData } = useDepartments();
    const createPosition = useCreatePosition();
    const updatePosition = useUpdatePosition();
    const deletePosition = useDeletePosition();

    const [showForm, setShowForm] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [formData, setFormData] = useState({
        title: '', code: '', department: '', grade: '', description: '', is_active: true,
    });
    const [searchTerm, setSearchTerm] = useState('');
    const [deptFilter, setDeptFilter] = useState('');
    const [error, setError] = useState('');

    const positions = positionsData?.results || positionsData || [];
    const departments = departmentsData?.results || departmentsData || [];

    const filteredPositions = Array.isArray(positions) ? positions.filter((pos: any) => {
        const matchesSearch = !searchTerm ||
            pos.title?.toLowerCase().includes(searchTerm.toLowerCase()) ||
            pos.code?.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesDept = !deptFilter || String(pos.department) === deptFilter;
        return matchesSearch && matchesDept;
    }) : [];

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        if (!formData.title || !formData.code || !formData.department || !formData.grade) {
            setError('Title, Code, Department, and Grade are required');
            return;
        }
        try {
            const payload = {
                title: formData.title,
                code: formData.code,
                department: Number(formData.department),
                grade: formData.grade,
                description: formData.description,
                is_active: formData.is_active,
            };
            if (editingId) {
                await updatePosition.mutateAsync({ id: editingId, data: payload });
            } else {
                await createPosition.mutateAsync(payload);
            }
            setShowForm(false);
            setEditingId(null);
            setFormData({ title: '', code: '', department: '', grade: '', description: '', is_active: true });
        } catch (err: any) {
            const detail = err?.response?.data;
            if (detail && typeof detail === 'object') {
                const msgs = Object.entries(detail)
                    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
                    .join('; ');
                setError(msgs);
            } else {
                setError('Error saving position');
            }
        }
    };

    const handleEdit = (pos: any) => {
        setFormData({
            title: pos.title,
            code: pos.code || '',
            department: String(pos.department),
            grade: pos.grade || '',
            description: pos.description || '',
            is_active: pos.is_active,
        });
        setEditingId(pos.id);
        setShowForm(true);
        setError('');
    };

    const handleDelete = async (id: number) => {
        if (await showConfirm('Delete this position?')) {
            try {
                await deletePosition.mutateAsync(id);
            } catch (err: any) {
                showAlert(err?.response?.data?.detail || 'Cannot delete — may have employees assigned');
            }
        }
    };

    const openNewForm = () => {
        setShowForm(true);
        setEditingId(null);
        setFormData({ title: '', code: '', department: '', grade: '', description: '', is_active: true });
        setError('');
    };

    if (isLoading) return <LoadingScreen message="Loading positions..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Positions"
                    subtitle="Manage job positions within departments"
                    icon={<Briefcase size={22} color="white" />}
                    actions={
                        <button
                            onClick={openNewForm}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '0.5rem',
                                padding: '0.75rem 1.5rem', background: 'var(--color-primary, #1e40af)',
                                color: 'white', border: 'none', borderRadius: '8px',
                                cursor: 'pointer', fontWeight: 500,
                            }}
                        >
                            <Plus size={20} /> Add Position
                        </button>
                    }
                />

                {/* Create/Edit Form */}
                {showForm && (
                    <div className="glass-card" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                            <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text)', margin: 0 }}>
                                {editingId ? 'Edit Position' : 'New Position'}
                            </h3>
                            <button
                                onClick={() => setShowForm(false)}
                                style={{ padding: '0.25rem', border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--color-text-muted)' }}
                            >
                                <X size={18} />
                            </button>
                        </div>

                        {error && (
                            <div style={{
                                padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem',
                                background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
                                color: '#ef4444', fontSize: 'var(--text-sm)',
                            }}>
                                {error}
                            </div>
                        )}

                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                <div>
                                    <label style={labelStyle}>Title *</label>
                                    <input
                                        type="text"
                                        value={formData.title}
                                        onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                                        placeholder="e.g. Software Engineer"
                                        required
                                        style={inputStyle}
                                    />
                                </div>
                                <div>
                                    <label style={labelStyle}>Code *</label>
                                    <input
                                        type="text"
                                        value={formData.code}
                                        onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                                        placeholder="e.g. SE-001"
                                        required
                                        style={inputStyle}
                                    />
                                </div>
                                <div>
                                    <label style={labelStyle}>Department *</label>
                                    <select
                                        value={formData.department}
                                        onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                                        required
                                        style={selectStyle}
                                    >
                                        <option value="">Select Department</option>
                                        {departments.map((d: any) => (
                                            <option key={d.id} value={d.id}>{d.name}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label style={labelStyle}>Grade *</label>
                                    <select
                                        value={formData.grade}
                                        onChange={(e) => setFormData({ ...formData, grade: e.target.value })}
                                        required
                                        style={selectStyle}
                                    >
                                        <option value="">Select Grade</option>
                                        {GRADE_OPTIONS.map((g) => (
                                            <option key={g.value} value={g.value}>{g.label}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>
                            <div style={{ marginBottom: '1rem' }}>
                                <label style={labelStyle}>Description</label>
                                <textarea
                                    value={formData.description}
                                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                                    rows={2}
                                    placeholder="Position description..."
                                    style={{ ...inputStyle, resize: 'vertical' }}
                                />
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
                                <div style={{ display: 'flex', gap: '0.5rem' }}>
                                    <button
                                        type="submit"
                                        disabled={createPosition.isPending || updatePosition.isPending}
                                        style={{
                                            padding: '0.625rem 1.25rem', borderRadius: '8px', border: 'none',
                                            background: 'var(--color-primary, #1e40af)', color: 'white',
                                            cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)',
                                            opacity: createPosition.isPending || updatePosition.isPending ? 0.6 : 1,
                                        }}
                                    >
                                        {editingId ? 'Update' : 'Create'}
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => setShowForm(false)}
                                        style={{
                                            padding: '0.625rem 1.25rem', borderRadius: '8px',
                                            border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                                            color: 'var(--color-text)', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)',
                                        }}
                                    >
                                        Cancel
                                    </button>
                                </div>
                                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>
                                    <input
                                        type="checkbox"
                                        checked={formData.is_active}
                                        onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                                    />
                                    Active
                                </label>
                            </div>
                        </form>
                    </div>
                )}

                {/* Search & Filter */}
                <div className="glass-card" style={{ marginBottom: '1.5rem', padding: '1rem' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '1rem' }}>
                        <div style={{ position: 'relative' }}>
                            <Search style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} size={20} />
                            <input
                                type="text"
                                placeholder="Search by title or code..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                style={{ ...inputStyle, paddingLeft: '2.75rem' }}
                            />
                        </div>
                        <select
                            value={deptFilter}
                            onChange={(e) => setDeptFilter(e.target.value)}
                            style={selectStyle}
                        >
                            <option value="">All Departments</option>
                            {departments.map((d: any) => (
                                <option key={d.id} value={d.id}>{d.name}</option>
                            ))}
                        </select>
                    </div>
                </div>

                {/* Table */}
                <div className="glass-card" style={{ overflow: 'hidden' }}>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                    <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Position</th>
                                    <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Code</th>
                                    <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Department</th>
                                    <th style={{ padding: '1rem 1.5rem', textAlign: 'center', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Grade</th>
                                    <th style={{ padding: '1rem 1.5rem', textAlign: 'center', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Employees</th>
                                    <th style={{ padding: '1rem 1.5rem', textAlign: 'center', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Status</th>
                                    <th style={{ padding: '1rem 1.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredPositions.length > 0 ? (
                                    filteredPositions.map((pos: any, index: number) => {
                                        const gc = gradeColors[pos.grade] || gradeColors.Entry;
                                        return (
                                            <tr
                                                key={pos.id}
                                                style={{
                                                    borderBottom: '1px solid var(--color-border)',
                                                    animation: `fadeInUp 0.3s ease-out ${index * 0.05}s both`,
                                                }}
                                            >
                                                <td style={{ padding: '1rem 1.5rem' }}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                                        <div style={{
                                                            width: '36px', height: '36px', borderRadius: '8px',
                                                            background: 'rgba(16, 185, 129, 0.1)', color: '#10b981',
                                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                        }}>
                                                            <Briefcase size={18} />
                                                        </div>
                                                        <span style={{ fontWeight: 500, color: 'var(--color-text)' }}>{pos.title}</span>
                                                    </div>
                                                </td>
                                                <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                                    {pos.code}
                                                </td>
                                                <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                    {pos.department_name || '—'}
                                                </td>
                                                <td style={{ padding: '1rem 1.5rem', textAlign: 'center' }}>
                                                    <span style={{
                                                        display: 'inline-block', padding: '0.25rem 0.75rem',
                                                        borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 500,
                                                        background: gc.bg, color: gc.color,
                                                    }}>
                                                        {GRADE_OPTIONS.find(g => g.value === pos.grade)?.label || pos.grade}
                                                    </span>
                                                </td>
                                                <td style={{ padding: '1rem 1.5rem', textAlign: 'center', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                    {pos.employee_count ?? 0}
                                                </td>
                                                <td style={{ padding: '1rem 1.5rem', textAlign: 'center' }}>
                                                    <span style={{
                                                        display: 'inline-block', padding: '0.25rem 0.75rem',
                                                        borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 500,
                                                        background: pos.is_active ? 'rgba(34, 197, 94, 0.1)' : 'rgba(156, 163, 175, 0.1)',
                                                        color: pos.is_active ? '#22c55e' : '#9ca3af',
                                                    }}>
                                                        {pos.is_active ? 'Active' : 'Inactive'}
                                                    </span>
                                                </td>
                                                <td style={{ padding: '1rem 1.5rem' }}>
                                                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                                        <button
                                                            onClick={() => handleEdit(pos)}
                                                            style={{
                                                                padding: '0.375rem 0.75rem', borderRadius: '6px',
                                                                border: 'none', background: 'rgba(36, 113, 163, 0.1)',
                                                                color: '#2471a3', cursor: 'pointer', fontSize: 'var(--text-xs)',
                                                                fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                                            }}
                                                        >
                                                            <Edit size={14} /> Edit
                                                        </button>
                                                        <button
                                                            onClick={() => handleDelete(pos.id)}
                                                            style={{
                                                                padding: '0.375rem 0.75rem', borderRadius: '6px',
                                                                border: 'none', background: 'rgba(239, 68, 68, 0.1)',
                                                                color: '#ef4444', cursor: 'pointer', fontSize: 'var(--text-xs)',
                                                                fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                                            }}
                                                        >
                                                            <Trash2 size={14} /> Delete
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })
                                ) : (
                                    <tr>
                                        <td colSpan={7} style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                            <Briefcase size={48} style={{ margin: '0 auto 1rem', opacity: 0.5, display: 'block' }} />
                                            <p>No positions found</p>
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </main>
        </div>
    );
};

export default PositionList;
