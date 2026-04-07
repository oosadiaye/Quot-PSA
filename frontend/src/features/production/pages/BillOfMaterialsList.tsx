import { useState } from 'react';
import { useDialog } from '../../../hooks/useDialog';
import { useBillOfMaterials, useCreateBOM, useUpdateBOM, useDeleteBOM } from '../hooks/useProduction';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import { Plus, FileText, Edit2, Trash2, X } from 'lucide-react';
import LoadingScreen from '../../../components/common/LoadingScreen';

const BillOfMaterialsList = () => {
    const { showConfirm } = useDialog();
    const { data: bomsData, isLoading } = useBillOfMaterials();
    const createBOM = useCreateBOM();
    const updateBOM = useUpdateBOM();
    const deleteBOM = useDeleteBOM();

    const [showModal, setShowModal] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [formData, setFormData] = useState({
        item_code: '',
        item_name: '',
        item_type: 'Finished',
        unit: 'PCS',
        standard_cost: '0',
        is_active: true,
        requires_quality_inspection: false,
    });

    const boms = Array.isArray(bomsData?.results) ? bomsData.results : Array.isArray(bomsData) ? bomsData : [];

    if (isLoading) {
        return <LoadingScreen message="Loading bills of materials..." />;
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const payload = {
            ...formData,
            standard_cost: parseFloat(formData.standard_cost),
        };

        if (editingId) {
            await updateBOM.mutateAsync({ id: editingId, data: payload });
        } else {
            await createBOM.mutateAsync(payload);
        }
        resetForm();
    };

    const handleEdit = (bom: any) => {
        setEditingId(bom.id);
        setFormData({
            item_code: bom.item_code || '',
            item_name: bom.item_name || '',
            item_type: bom.item_type || 'Finished',
            unit: bom.unit || 'PCS',
            standard_cost: String(bom.standard_cost || 0),
            is_active: bom.is_active ?? true,
            requires_quality_inspection: bom.requires_quality_inspection ?? false,
        });
        setShowModal(true);
    };

    const handleDelete = async (id: number) => {
        if (await showConfirm('Are you sure you want to delete this BOM?')) {
            await deleteBOM.mutateAsync(id);
        }
    };

    const resetForm = () => {
        setShowModal(false);
        setEditingId(null);
        setFormData({
            item_code: '',
            item_name: '',
            item_type: 'Finished',
            unit: 'PCS',
            standard_cost: '0',
            is_active: true,
            requires_quality_inspection: false,
        });
    };

    const getTypeColor = (type: string) => {
        const colors: Record<string, string> = {
            'Finished': 'var(--color-success)',
            'Semi-Finished': '#f59e0b',
            'Raw Material': 'var(--color-primary)',
        };
        return colors[type] || 'var(--color-text-muted)';
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Bill of Materials"
                    subtitle="Manage BOMs for finished, semi-finished, and raw materials."
                    icon={<FileText size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
                            <Plus size={18} /> New BOM
                        </button>
                    }
                />

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Code</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Item Name</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Type</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Unit</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Standard Cost</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {boms.length === 0 ? (
                                <tr><td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No bills of materials found</td></tr>
                            ) : (
                                boms.map((bom: any) => (
                                    <tr key={bom.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem', fontWeight: 600 }}>{bom.item_code}</td>
                                        <td style={{ padding: '1rem' }}>{bom.item_name}</td>
                                        <td style={{ padding: '1rem' }}>
                                            <span style={{
                                                padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 700,
                                                background: `${getTypeColor(bom.item_type)}20`, color: getTypeColor(bom.item_type)
                                            }}>
                                                {bom.item_type}
                                            </span>
                                        </td>
                                        <td style={{ padding: '1rem' }}>{bom.unit}</td>
                                        <td style={{ padding: '1rem', fontWeight: 600, color: 'var(--color-primary)' }}>${bom.standard_cost}</td>
                                        <td style={{ padding: '1rem' }}>
                                            <span style={{
                                                padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 700,
                                                background: bom.is_active ? 'rgba(34, 197, 94, 0.15)' : 'rgba(107, 114, 128, 0.15)',
                                                color: bom.is_active ? 'var(--color-success)' : 'var(--color-text-muted)'
                                            }}>
                                                {bom.is_active ? 'Active' : 'Inactive'}
                                            </span>
                                        </td>
                                        <td style={{ padding: '1rem' }}>
                                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                                                <button className="btn btn-outline" style={{ padding: '0.4rem' }} onClick={() => handleEdit(bom)}>
                                                    <Edit2 size={14} />
                                                </button>
                                                <button className="btn btn-outline" style={{ padding: '0.4rem', color: 'var(--color-error)' }} onClick={() => handleDelete(bom.id)}>
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
                                <h2>{editingId ? 'Edit BOM' : 'New BOM'}</h2>
                                <button onClick={resetForm} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
                                    <X size={20} />
                                </button>
                            </div>
                            <form onSubmit={handleSubmit}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Item Code<span className="required-mark"> *</span></label>
                                        <input
                                            type="text"
                                            className="input"
                                            value={formData.item_code}
                                            onChange={e => setFormData({ ...formData, item_code: e.target.value })}
                                            required
                                        />
                                    </div>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Item Name<span className="required-mark"> *</span></label>
                                        <input
                                            type="text"
                                            className="input"
                                            value={formData.item_name}
                                            onChange={e => setFormData({ ...formData, item_name: e.target.value })}
                                            required
                                        />
                                    </div>
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Type</label>
                                        <select
                                            className="input"
                                            value={formData.item_type}
                                            onChange={e => setFormData({ ...formData, item_type: e.target.value })}
                                        >
                                            <option value="Finished">Finished Product</option>
                                            <option value="Semi-Finished">Semi-Finished Product</option>
                                            <option value="Raw Material">Raw Material</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Unit</label>
                                        <select
                                            className="input"
                                            value={formData.unit}
                                            onChange={e => setFormData({ ...formData, unit: e.target.value })}
                                        >
                                            <option value="PCS">Pieces</option>
                                            <option value="KG">Kilograms</option>
                                            <option value="L">Liters</option>
                                            <option value="M">Meters</option>
                                        </select>
                                    </div>
                                </div>
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Standard Cost</label>
                                    <input
                                        type="number"
                                        step="0.01"
                                        className="input"
                                        value={formData.standard_cost}
                                        onChange={e => setFormData({ ...formData, standard_cost: e.target.value })}
                                    />
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
                                <div style={{ marginBottom: '1.5rem' }}>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <input
                                            type="checkbox"
                                            checked={formData.requires_quality_inspection}
                                            onChange={e => setFormData({ ...formData, requires_quality_inspection: e.target.checked })}
                                        />
                                        <span>Requires Quality Inspection</span>
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

export default BillOfMaterialsList;
