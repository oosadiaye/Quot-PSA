import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import { Users, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';

interface CreateApprovalGroupPayload {
    name: string;
    description: string;
    min_amount: string | null;
    max_amount: string | null;
}

const ApprovalGroups = () => {
    const queryClient = useQueryClient();
    const { data: groups, isLoading } = useQuery({
        queryKey: ['approval-groups'],
        queryFn: async () => {
            const { data } = await apiClient.get('/workflow/approval-groups/');
            return data;
        }
    });

    const createGroup = useMutation({
        mutationFn: async (payload: CreateApprovalGroupPayload) => {
            const { data } = await apiClient.post('/workflow/approval-groups/', payload);
            return data;
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['approval-groups'] })
    });

    const deleteGroup = useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/workflow/approval-groups/${id}/`);
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['approval-groups'] })
    });

    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState({ name: '', description: '', min_amount: '', max_amount: '' });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        createGroup.mutate({
            ...form,
            min_amount: form.min_amount || null,
            max_amount: form.max_amount || null
        }, { onSuccess: () => setShowForm(false) });
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Approval Groups"
                    subtitle="Manage approval groups and their members."
                    icon={<Users size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
                            <Plus size={18} /> New Group
                        </button>
                    }
                />

                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3>Create Approval Group</h3>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                                <input className="input" placeholder="Group Name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required />
                                <input className="input" placeholder="Description" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
                                <input className="input" type="number" placeholder="Min Amount" value={form.min_amount} onChange={e => setForm({ ...form, min_amount: e.target.value })} />
                                <input className="input" type="number" placeholder="Max Amount" value={form.max_amount} onChange={e => setForm({ ...form, max_amount: e.target.value })} />
                            </div>
                            <button type="submit" className="btn btn-primary" disabled={createGroup.isPending}>
                                {createGroup.isPending ? 'Creating...' : 'Create Group'}
                            </button>
                        </form>
                    </div>
                )}

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '1.5rem' }}>
                    {groups?.results?.map((group: any) => (
                        <div key={group.id} className="card">
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                                <div>
                                    <h3 style={{ marginBottom: '0.25rem' }}>{group.name}</h3>
                                    <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{group.description || 'No description'}</p>
                                </div>
                                <button className="btn btn-outline" style={{ color: 'var(--color-error)' }} onClick={() => deleteGroup.mutate(group.id)}>
                                    <Trash2 size={16} />
                                </button>
                            </div>
                            <div style={{ display: 'flex', gap: '1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                <span>Min: ${group.min_amount || '0'}</span>
                                <span>Max: ${group.max_amount || 'Unlimited'}</span>
                            </div>
                            <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)' }}>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>MEMBERS</div>
                                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                                    {group.member_names?.map((name: string, i: number) => (
                                        <span key={i} style={{ padding: '0.25rem 0.5rem', background: 'var(--color-surface)', borderRadius: '0.25rem', fontSize: 'var(--text-xs)' }}>{name}</span>
                                    ))}
                                    {(!group.member_names || group.member_names.length === 0) && <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>No members</span>}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </main>
        </div>
    );
};

export default ApprovalGroups;
