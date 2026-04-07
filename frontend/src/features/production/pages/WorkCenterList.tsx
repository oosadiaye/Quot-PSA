import { useState } from 'react';
import { useDialog } from '../../../hooks/useDialog';
import { useWorkCenters, useCreateWorkCenter, useUpdateWorkCenter, useDeleteWorkCenter } from '../hooks/useProduction';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import { Plus, Factory, Edit2, Trash2, X } from 'lucide-react';
import LoadingScreen from '../../../components/common/LoadingScreen';

const WorkCenterList = () => {
    const { showConfirm } = useDialog();
    const { data: workCentersData, isLoading } = useWorkCenters();
    const createWC = useCreateWorkCenter();
    const updateWC = useUpdateWorkCenter();
    const deleteWC = useDeleteWorkCenter();

    const [showModal, setShowModal] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [formData, setFormData] = useState({
        name: '',
        code: '',
        description: '',
        capacity_hours: '8',
        efficiency: '100',
        labor_rate: '0',
        overhead_rate: '0',
        is_active: true,
    });

    const workCenters = Array.isArray(workCentersData?.results) ? workCentersData.results : Array.isArray(workCentersData) ? workCentersData : [];

    if (isLoading) {
        return <LoadingScreen message="Loading work centers..." />;
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const payload = {
            ...formData,
            capacity_hours: parseFloat(formData.capacity_hours),
            efficiency: parseFloat(formData.efficiency),
            labor_rate: parseFloat(formData.labor_rate),
            overhead_rate: parseFloat(formData.overhead_rate),
        };

        if (editingId) {
            await updateWC.mutateAsync({ id: editingId, data: payload });
        } else {
            await createWC.mutateAsync(payload);
        }
        resetForm();
    };

    const handleEdit = (wc: any) => {
        setEditingId(wc.id);
        setFormData({
            name: wc.name || '',
            code: wc.code || '',
            description: wc.description || '',
            capacity_hours: String(wc.capacity_hours || 8),
            efficiency: String(wc.efficiency || 100),
            labor_rate: String(wc.labor_rate || 0),
            overhead_rate: String(wc.overhead_rate || 0),
            is_active: wc.is_active ?? true,
        });
        setShowModal(true);
    };

    const handleDelete = async (id: number) => {
        if (await showConfirm('Are you sure you want to delete this work center?')) {
            await deleteWC.mutateAsync(id);
        }
    };

    const resetForm = () => {
        setShowModal(false);
        setEditingId(null);
        setFormData({
            name: '',
            code: '',
            description: '',
            capacity_hours: '8',
            efficiency: '100',
            labor_rate: '0',
            overhead_rate: '0',
            is_active: true,
        });
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Work Centers"
                    subtitle="Manage production work centers and their capacity."
                    icon={<Factory size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
                            <Plus size={18} /> New Work Center
                        </button>
                    }
                />

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Code</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Name</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Capacity (hrs)</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Efficiency %</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Labor Rate</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {workCenters.length === 0 ? (
                                <tr><td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No work centers found</td></tr>
                            ) : (
                                workCenters.map((wc: any) => (
                                    <tr key={wc.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem', fontWeight: 600 }}>{wc.code}</td>
                                        <td style={{ padding: '1rem' }}>{wc.name}</td>
                                        <td style={{ padding: '1rem' }}>{wc.capacity_hours}</td>
                                        <td style={{ padding: '1rem' }}>{wc.efficiency}%</td>
                                        <td style={{ padding: '1rem' }}>${wc.labor_rate}</td>
                                        <td style={{ padding: '1rem' }}>
                                            <span style={{
                                                padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 700,
                                                background: wc.is_active ? 'rgba(34, 197, 94, 0.15)' : 'rgba(107, 114, 128, 0.15)',
                                                color: wc.is_active ? 'var(--color-success)' : 'var(--color-text-muted)'
                                            }}>
                                                {wc.is_active ? 'Active' : 'Inactive'}
                                            </span>
                                        </td>
                                        <td style={{ padding: '1rem' }}>
                                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                                                <button className="btn btn-outline" style={{ padding: '0.4rem' }} onClick={() => handleEdit(wc)}>
                                                    <Edit2 size={14} />
                                                </button>
                                                <button className="btn btn-outline" style={{ padding: '0.4rem', color: 'var(--color-error)' }} onClick={() => handleDelete(wc.id)}>
                                                    <Trash2 size={14} />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {showModal && (
                    <div style={{
                        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                        background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
                    }}>
                        <div className="card" style={{ width: '500px', padding: '2rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                                <h2>{editingId ? 'Edit Work Center' : 'New Work Center'}</h2>
                                <button onClick={resetForm} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
                                    <X size={20} />
                                </button>
                            </div>
                            <form onSubmit={handleSubmit}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Code<span className="required-mark"> *</span></label>
                                        <input
                                            type="text"
                                            className="input"
                                            value={formData.code}
                                            onChange={e => setFormData({ ...formData, code: e.target.value })}
                                            required
                                        />
                                    </div>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Name<span className="required-mark"> *</span></label>
                                        <input
                                            type="text"
                                            className="input"
                                            value={formData.name}
                                            onChange={e => setFormData({ ...formData, name: e.target.value })}
                                            required
                                        />
                                    </div>
                                </div>
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Description</label>
                                    <textarea
                                        className="input"
                                        value={formData.description}
                                        onChange={e => setFormData({ ...formData, description: e.target.value })}
                                        rows={2}
                                        style={{ width: '100%' }}
                                    />
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Capacity (hours/day)</label>
                                        <input
                                            type="number"
                                            step="0.01"
                                            className="input"
                                            value={formData.capacity_hours}
                                            onChange={e => setFormData({ ...formData, capacity_hours: e.target.value })}
                                        />
                                    </div>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Efficiency %</label>
                                        <input
                                            type="number"
                                            step="0.01"
                                            className="input"
                                            value={formData.efficiency}
                                            onChange={e => setFormData({ ...formData, efficiency: e.target.value })}
                                        />
                                    </div>
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Labor Rate</label>
                                        <input
                                            type="number"
                                            step="0.01"
                                            className="input"
                                            value={formData.labor_rate}
                                            onChange={e => setFormData({ ...formData, labor_rate: e.target.value })}
                                        />
                                    </div>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Overhead Rate</label>
                                        <input
                                            type="number"
                                            step="0.01"
                                            className="input"
                                            value={formData.overhead_rate}
                                            onChange={e => setFormData({ ...formData, overhead_rate: e.target.value })}
                                        />
                                    </div>
                                </div>
                                <div style={{ marginBottom: '1.5rem' }}>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <input
                                            type="checkbox"
                                            checked={formData.is_active}
                                            onChange={e => setFormData({ ...formData, is_active: e.target.checked })}
                                        />
                                        <span>Active</span>
                                    </label>
                                </div>
                                <div style={{ display: 'flex', gap: '1rem' }}>
                                    <button type="button" className="btn btn-outline" onClick={resetForm} style={{ flex: 1 }}>Cancel</button>
                                    <button type="submit" className="btn btn-primary" style={{ flex: 1 }}>{editingId ? 'Update' : 'Create'}</button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
};

export default WorkCenterList;
