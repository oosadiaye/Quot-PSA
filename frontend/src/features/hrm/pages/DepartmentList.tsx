import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDepartments, useCreateDepartment, useUpdateDepartment, useDeleteDepartment } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, Edit, Trash2, Building2 } from 'lucide-react';
import { useDialog } from '../../../hooks/useDialog';

const DepartmentList = () => {
    const { showAlert, showConfirm } = useDialog();
    const navigate = useNavigate();
    const { data: departmentsData, isLoading } = useDepartments();
    const createDept = useCreateDepartment();
    const updateDept = useUpdateDepartment();
    const deleteDept = useDeleteDepartment();
    
    const [showForm, setShowForm] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [formData, setFormData] = useState({ name: '', code: '', description: '', is_active: true });

    const departments = departmentsData?.results || departmentsData || [];

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            if (editingId) {
                await updateDept.mutateAsync({ id: editingId, data: formData });
            } else {
                await createDept.mutateAsync(formData);
            }
            setShowForm(false);
            setEditingId(null);
            setFormData({ name: '', code: '', description: '', is_active: true });
        } catch (err) {
            showAlert('Error saving department');
        }
    };

    const handleEdit = (dept: any) => {
        setFormData({ name: dept.name, code: dept.code, description: dept.description || '', is_active: dept.is_active });
        setEditingId(dept.id);
        setShowForm(true);
    };

    const handleDelete = async (id: number) => {
        if (await showConfirm('Delete this department?')) {
            try { await deleteDept.mutateAsync(id); } catch (err) { showAlert('Cannot delete - may have employees'); }
        }
    };

    if (isLoading) return <LoadingScreen message="Loading departments..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Departments"
                    subtitle="Manage organizational departments"
                    icon={<Building2 size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => { setShowForm(true); setEditingId(null); setFormData({ name: '', code: '', description: '', is_active: true }); }}>
                            <Plus size={18} /> Add Department
                        </button>
                    }
                />

                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3>{editingId ? 'Edit Department' : 'New Department'}</h3>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Name<span className="required-mark"> *</span></label><input type="text" className="input" value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} required /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Code<span className="required-mark"> *</span></label><input type="text" className="input" value={formData.code} onChange={e => setFormData({ ...formData, code: e.target.value })} required /></div>
                                <div style={{ display: 'flex', alignItems: 'center', marginTop: '1.5rem' }}><label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><input type="checkbox" checked={formData.is_active} onChange={e => setFormData({ ...formData, is_active: e.target.checked })} /> Active</label></div>
                            </div>
                            <div style={{ marginBottom: '1rem' }}><label style={{ display: 'block', marginBottom: '0.5rem' }}>Description</label><textarea className="input" value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} rows={2} style={{ width: '100%' }} /></div>
                            <div style={{ display: 'flex', gap: '1rem' }}><button type="submit" className="btn btn-primary">{editingId ? 'Update' : 'Create'}</button><button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button></div>
                        </form>
                    </div>
                )}

                <div style={{ display: 'grid', gap: '1rem' }}>
                    {departments.length === 0 ? (
                        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}><Building2 size={48} style={{ color: 'var(--color-text-muted)', marginBottom: '1rem' }} /><p>No departments found</p></div>
                    ) : (
                        departments.map((dept: any) => (
                            <div key={dept.id} className="card" style={{ padding: '1.5rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                        <div style={{ width: '48px', height: '48px', borderRadius: '10px', background: 'rgba(36, 113, 163, 0.1)', color: 'var(--color-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Building2 size={24} /></div>
                                        <div>
                                            <div style={{ fontWeight: 600 }}>{dept.name}</div>
                                            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{dept.code}</div>
                                        </div>
                                    </div>
                                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                                        <button className="btn btn-outline" onClick={() => handleEdit(dept)}><Edit size={16} /></button>
                                        <button className="btn btn-outline" onClick={() => handleDelete(dept.id)} style={{ color: 'var(--color-error)' }}><Trash2 size={16} /></button>
                                    </div>
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </main>
        </div>
    );
};

export default DepartmentList;
