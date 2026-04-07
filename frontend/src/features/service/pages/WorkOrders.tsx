import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useWorkOrders, useCreateWorkOrder, useCompleteWorkOrder, useTechnicians, useServiceAssets } from '../hooks/useService';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import { Wrench, Plus, CheckCircle, Clock, Package } from 'lucide-react';
import LoadingScreen from '../../../components/common/LoadingScreen';
import type { WorkOrder, Technician, ServiceAsset } from '../types';

const WorkOrders = () => {
    const navigate = useNavigate();
    const { data: workOrders, isLoading } = useWorkOrders();
    const { data: technicians } = useTechnicians();
    const { data: assets } = useServiceAssets();
    const createWorkOrder = useCreateWorkOrder();
    const completeWorkOrder = useCompleteWorkOrder();
    const [showForm, setShowForm] = useState(false);
    const [formData, setFormData] = useState({
        title: '',
        description: '',
        priority: 'Medium',
        technician: '',
        asset: '',
        scheduled_date: '',
        labor_hours: 0,
        labor_cost: 0,
        parts_cost: 0,
    });

    const woList = (workOrders?.results || workOrders || []) as WorkOrder[];
    const techsList = (technicians?.results || technicians || []) as Technician[];
    const assetsList = (assets?.results || assets || []) as ServiceAsset[];

    const statusColor = (status: string) => {
        switch (status) {
            case 'Completed': return 'var(--color-success)';
            case 'In Progress': return 'var(--color-primary)';
            case 'Assigned': return 'var(--color-cta)';
            case 'Pending': return 'var(--color-text-muted)';
            default: return 'var(--color-text-muted)';
        }
    };

    const priorityColor = (p: string) => {
        switch (p) {
            case 'Urgent': return 'var(--color-error)';
            case 'High': return 'var(--color-cta)';
            case 'Medium': return 'var(--color-primary)';
            default: return 'var(--color-text-muted)';
        }
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        createWorkOrder.mutate(formData, {
            onSuccess: () => setShowForm(false)
        });
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Work Orders"
                    subtitle="Manage task assignments and track work completion."
                    icon={<Wrench size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
                            <Plus size={18} /> New Work Order
                        </button>
                    }
                />

                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>Create Work Order</h3>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem' }}>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)' }}>Title</label>
                                    <input
                                        type="text"
                                        className="input"
                                        value={formData.title}
                                        onChange={e => setFormData({ ...formData, title: e.target.value })}
                                        required
                                    />
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)' }}>Priority</label>
                                    <select
                                        className="input"
                                        value={formData.priority}
                                        onChange={e => setFormData({ ...formData, priority: e.target.value })}
                                    >
                                        <option value="Low">Low</option>
                                        <option value="Medium">Medium</option>
                                        <option value="High">High</option>
                                        <option value="Urgent">Urgent</option>
                                    </select>
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)' }}>Technician</label>
                                    <select
                                        className="input"
                                        value={formData.technician}
                                        onChange={e => setFormData({ ...formData, technician: e.target.value })}
                                    >
                                        <option value="">Select Technician</option>
                                        {techsList.map((t: Technician) => (
                                            <option key={t.id} value={t.id}>{t.name}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)' }}>Asset</label>
                                    <select
                                        className="input"
                                        value={formData.asset}
                                        onChange={e => setFormData({ ...formData, asset: e.target.value })}
                                    >
                                        <option value="">Select Asset</option>
                                        {assetsList.map((a: ServiceAsset) => (
                                            <option key={a.id} value={a.id}>{a.name}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)' }}>Scheduled Date</label>
                                    <input
                                        type="date"
                                        className="input"
                                        value={formData.scheduled_date}
                                        onChange={e => setFormData({ ...formData, scheduled_date: e.target.value })}
                                    />
                                </div>
                            </div>
                            <div style={{ marginTop: '1rem' }}>
                                <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)' }}>Description</label>
                                <textarea
                                    className="input"
                                    rows={3}
                                    value={formData.description}
                                    onChange={e => setFormData({ ...formData, description: e.target.value })}
                                />
                            </div>
                            <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
                                <button type="submit" className="btn btn-primary" disabled={createWorkOrder.isPending}>
                                    {createWorkOrder.isPending ? 'Creating...' : 'Create Work Order'}
                                </button>
                                <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
                            </div>
                        </form>
                    </div>
                )}

                {isLoading ? (
                    <LoadingScreen message="Loading work orders..." fullScreen={false} />
                ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))', gap: '1.5rem' }}>
                        {woList.map((wo: WorkOrder) => (
                            <div key={wo.id} className="card animate-fade" style={{
                                borderLeft: `6px solid ${priorityColor(wo.priority)}`,
                                cursor: 'pointer',
                            }} onClick={() => navigate(`/service/work-orders/${wo.id}`)}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
                                    <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-primary)' }}>{wo.work_order_number}</span>
                                    <span style={{
                                        padding: '0.2rem 0.6rem', borderRadius: '1rem', fontSize: 'var(--text-xs)', fontWeight: 700,
                                        background: `${statusColor(wo.status)}20`,
                                        color: statusColor(wo.status)
                                    }}>
                                        {wo.status.toUpperCase()}
                                    </span>
                                </div>
                                <h3 style={{ marginBottom: '0.75rem', color: 'var(--color-text)' }}>{wo.title}</h3>
                                <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', marginBottom: '1rem' }}>{wo.description}</p>

                                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                        <Wrench size={14} /> {wo.technician_name || 'Unassigned'}
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                        <Clock size={14} /> {wo.scheduled_date || 'Not scheduled'}
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                        <Package size={14} /> ${wo.total_cost || 0}
                                    </div>
                                </div>

                                {wo.status !== 'Completed' && wo.status !== 'Cancelled' && (
                                    <button
                                        className="btn btn-primary"
                                        style={{ width: '100%', padding: '0.6rem' }}
                                        onClick={(e) => { e.stopPropagation(); completeWorkOrder.mutate(wo.id); }}
                                    >
                                        <CheckCircle size={16} /> Complete Work Order
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </main>
        </div>
    );
};

export default WorkOrders;
