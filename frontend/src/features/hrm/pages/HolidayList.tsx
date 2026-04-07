import { useState } from 'react';
import { useHolidays, useCreateHoliday, useUpdateHoliday, useDeleteHoliday } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, Edit, Trash2, Calendar } from 'lucide-react';
import { useDialog } from '../../../hooks/useDialog';

const HolidayList = () => {
    const { showAlert, showConfirm } = useDialog();
    const { data: holidaysData, isLoading } = useHolidays();
    const createHoliday = useCreateHoliday();
    const updateHoliday = useUpdateHoliday();
    const deleteHoliday = useDeleteHoliday();
    
    const [showForm, setShowForm] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [formData, setFormData] = useState({ name: '', date: '', is_recurring: false, description: '' });

    const holidays = holidaysData?.results || holidaysData || [];

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            if (editingId) {
                await updateHoliday.mutateAsync({ id: editingId, data: formData });
            } else {
                await createHoliday.mutateAsync(formData);
            }
            setShowForm(false);
            setEditingId(null);
            setFormData({ name: '', date: '', is_recurring: false, description: '' });
        } catch (err) {
            showAlert('Error saving holiday');
        }
    };

    const handleEdit = (holiday: any) => {
        setFormData({ name: holiday.name, date: holiday.date, is_recurring: holiday.is_recurring || false, description: holiday.description || '' });
        setEditingId(holiday.id);
        setShowForm(true);
    };

    const handleDelete = async (id: number) => {
        if (await showConfirm('Delete this holiday?')) {
            try { await deleteHoliday.mutateAsync(id); } catch (err) { showAlert('Error deleting holiday'); }
        }
    };

    if (isLoading) return <LoadingScreen message="Loading holidays..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Holidays"
                    subtitle="Manage company holidays and observances"
                    icon={<Calendar size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => { setShowForm(true); setEditingId(null); setFormData({ name: '', date: '', is_recurring: false, description: '' }); }}>
                            <Plus size={18} /> Add Holiday
                        </button>
                    }
                />

                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3>{editingId ? 'Edit Holiday' : 'New Holiday'}</h3>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Name<span className="required-mark"> *</span></label><input type="text" className="input" value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} required /></div>
                                <div><label style={{ display: 'block', marginBottom: '0.5rem' }}>Date<span className="required-mark"> *</span></label><input type="date" className="input" value={formData.date} onChange={e => setFormData({ ...formData, date: e.target.value })} required /></div>
                                <div style={{ display: 'flex', alignItems: 'center', marginTop: '1.5rem' }}><label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><input type="checkbox" checked={formData.is_recurring} onChange={e => setFormData({ ...formData, is_recurring: e.target.checked })} /> Recurring Yearly</label></div>
                            </div>
                            <div style={{ marginBottom: '1rem' }}><label style={{ display: 'block', marginBottom: '0.5rem' }}>Description</label><textarea className="input" value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} rows={2} style={{ width: '100%' }} /></div>
                            <div style={{ display: 'flex', gap: '1rem' }}><button type="submit" className="btn btn-primary">{editingId ? 'Update' : 'Create'}</button><button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button></div>
                        </form>
                    </div>
                )}

                <div style={{ display: 'grid', gap: '1rem' }}>
                    {holidays.length === 0 ? (
                        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}><Calendar size={48} style={{ color: 'var(--color-text-muted)', marginBottom: '1rem' }} /><p>No holidays found</p></div>
                    ) : (
                        holidays.map((holiday: any) => (
                            <div key={holiday.id} className="card" style={{ padding: '1.5rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                        <div style={{ width: '48px', height: '48px', borderRadius: '10px', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Calendar size={24} /></div>
                                        <div>
                                            <div style={{ fontWeight: 600 }}>{holiday.name}</div>
                                            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{holiday.date} {holiday.is_recurring && '(Recurring)'}</div>
                                        </div>
                                    </div>
                                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                                        <button className="btn btn-outline" onClick={() => handleEdit(holiday)}><Edit size={16} /></button>
                                        <button className="btn btn-outline" onClick={() => handleDelete(holiday.id)} style={{ color: 'var(--color-error)' }}><Trash2 size={16} /></button>
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

export default HolidayList;
