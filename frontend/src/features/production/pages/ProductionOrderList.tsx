import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useProductionOrders, useBillOfMaterials, useWorkCenters, useCreateProductionOrder, useScheduleProduction, useStartProduction, useCompleteProduction, usePostProductionToGL } from '../hooks/useProduction';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import { Plus, Play, CheckCircle, FileCheck, Trash2, Clock, Package } from 'lucide-react';
import LoadingScreen from '../../../components/common/LoadingScreen';

const ProductionOrderList = () => {
    const { data: ordersData, isLoading } = useProductionOrders();
    const { data: bomsData } = useBillOfMaterials();
    const { data: workCentersData } = useWorkCenters();
    // bomsData and workCentersData are used only in the create form dropdowns
    const createOrder = useCreateProductionOrder();
    const scheduleProduction = useScheduleProduction();
    const startProduction = useStartProduction();
    const completeProduction = useCompleteProduction();
    const postToGL = usePostProductionToGL();
    const navigate = useNavigate();

    const [showModal, setShowModal] = useState(false);
    const [formData, setFormData] = useState({
        order_number: '',
        bom: '',
        quantity_planned: '',
        start_date: new Date().toISOString().split('T')[0],
        end_date: '',
        work_center: '',
        notes: '',
    });

    const orders = Array.isArray(ordersData?.results) ? ordersData.results : Array.isArray(ordersData) ? ordersData : [];
    const boms = Array.isArray(bomsData?.results) ? bomsData.results : Array.isArray(bomsData) ? bomsData : [];
    const workCenters = Array.isArray(workCentersData?.results) ? workCentersData.results : Array.isArray(workCentersData) ? workCentersData : [];

    if (isLoading) {
        return <LoadingScreen message="Loading production orders..." />;
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        await createOrder.mutateAsync({
            ...formData,
            bom: parseInt(formData.bom),
            quantity_planned: parseFloat(formData.quantity_planned),
            work_center: formData.work_center ? parseInt(formData.work_center) : null,
            status: 'Draft',
        });
        resetForm();
    };

    const resetForm = () => {
        setShowModal(false);
        setFormData({
            order_number: '',
            bom: '',
            quantity_planned: '',
            start_date: new Date().toISOString().split('T')[0],
            end_date: '',
            work_center: '',
            notes: '',
        });
    };

    const handleSchedule = async (order: any) => {
        await scheduleProduction.mutateAsync({
            id: order.id,
            start_date: order.start_date || new Date().toISOString().split('T')[0],
        });
    };

    const handleStart = async (id: number) => {
        await startProduction.mutateAsync(id);
    };

    const handleComplete = async (id: number, quantity: number) => {
        await completeProduction.mutateAsync({ id, quantity_produced: quantity });
    };

    const handlePostToGL = async (id: number) => {
        await postToGL.mutateAsync(id);
    };

    const getStatusColor = (status: string) => {
        const colors: Record<string, string> = {
            'Draft': 'var(--color-text-muted)',
            'Scheduled': '#f59e0b',
            'In Progress': 'var(--color-primary)',
            'On Hold': '#f59e0b',
            'Done': 'var(--color-success)',
            'Cancelled': 'var(--color-error)',
        };
        return colors[status] || 'var(--color-text-muted)';
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Production Orders"
                    subtitle="Create and manage manufacturing orders."
                    icon={<Package size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
                            <Plus size={18} /> New Production Order
                        </button>
                    }
                />

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Order #</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Product (BOM)</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Quantity</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Work Center</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Start Date</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {orders.length === 0 ? (
                                <tr><td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No production orders found</td></tr>
                            ) : (
                                orders.map((order: any) => (
                                    <tr key={order.id} onClick={() => navigate(`/production/orders/${order.id}`)} style={{ borderBottom: '1px solid var(--color-border)', cursor: 'pointer', transition: 'background 0.15s' }} onMouseOver={e => e.currentTarget.style.background = 'var(--color-surface-hover, #f8fafc)'} onMouseOut={e => e.currentTarget.style.background = ''}>
                                        <td style={{ padding: '1rem', fontWeight: 600 }}>{order.order_number}</td>
                                        <td style={{ padding: '1rem' }}>{order.bom_name || '-'}</td>
                                        <td style={{ padding: '1rem' }}>{order.quantity_planned}</td>
                                        <td style={{ padding: '1rem' }}>{order.work_center_name || '-'}</td>
                                        <td style={{ padding: '1rem' }}>{order.start_date}</td>
                                        <td style={{ padding: '1rem' }}>
                                            <span style={{
                                                padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 700,
                                                background: `${getStatusColor(order.status)}20`, color: getStatusColor(order.status)
                                            }}>
                                                {order.status}
                                            </span>
                                        </td>
                                        <td style={{ padding: '1rem' }}>
                                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                                                {order.status === 'Draft' && (
                                                    <button
                                                        className="btn btn-primary"
                                                        style={{ padding: '0.4rem 0.8rem', fontSize: 'var(--text-xs)' }}
                                                        onClick={(e) => { e.stopPropagation(); handleSchedule(order); }}
                                                    >
                                                        <Play size={12} /> Schedule
                                                    </button>
                                                )}
                                                {order.status === 'Scheduled' && (
                                                    <button
                                                        className="btn btn-primary"
                                                        style={{ padding: '0.4rem 0.8rem', fontSize: 'var(--text-xs)' }}
                                                        onClick={(e) => { e.stopPropagation(); handleStart(order.id); }}
                                                    >
                                                        <Play size={12} /> Start
                                                    </button>
                                                )}
                                                {order.status === 'In Progress' && (
                                                    <button
                                                        className="btn btn-primary"
                                                        style={{ padding: '0.4rem 0.8rem', fontSize: 'var(--text-xs)' }}
                                                        onClick={(e) => { e.stopPropagation(); handleComplete(order.id, parseFloat(order.quantity_planned)); }}
                                                    >
                                                        <CheckCircle size={12} /> Complete
                                                    </button>
                                                )}
                                                {order.status === 'Done' && (
                                                    <button
                                                        className="btn btn-outline"
                                                        style={{ padding: '0.4rem 0.8rem', fontSize: 'var(--text-xs)' }}
                                                        onClick={(e) => { e.stopPropagation(); handlePostToGL(order.id); }}
                                                    >
                                                        <FileCheck size={12} /> Post to GL
                                                    </button>
                                                )}
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
                            <h2 style={{ marginBottom: '1.5rem' }}>New Production Order</h2>
                            <form onSubmit={handleSubmit}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Order Number<span className="required-mark"> *</span></label>
                                        <input
                                            type="text"
                                            className="input"
                                            value={formData.order_number}
                                            onChange={e => setFormData({ ...formData, order_number: e.target.value })}
                                            required
                                        />
                                    </div>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>BOM<span className="required-mark"> *</span></label>
                                        <select
                                            className="input"
                                            value={formData.bom}
                                            onChange={e => setFormData({ ...formData, bom: e.target.value })}
                                            required
                                        >
                                            <option value="">Select BOM</option>
                                            {boms.map((b: any) => (
                                                <option key={b.id} value={b.id}>{b.item_code} - {b.item_name}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Quantity<span className="required-mark"> *</span></label>
                                        <input
                                            type="number"
                                            step="0.01"
                                            className="input"
                                            value={formData.quantity_planned}
                                            onChange={e => setFormData({ ...formData, quantity_planned: e.target.value })}
                                            required
                                        />
                                    </div>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Work Center</label>
                                        <select
                                            className="input"
                                            value={formData.work_center}
                                            onChange={e => setFormData({ ...formData, work_center: e.target.value })}
                                        >
                                            <option value="">Select Work Center</option>
                                            {workCenters.map((w: any) => (
                                                <option key={w.id} value={w.id}>{w.name}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Start Date</label>
                                        <input
                                            type="date"
                                            className="input"
                                            value={formData.start_date}
                                            onChange={e => setFormData({ ...formData, start_date: e.target.value })}
                                        />
                                    </div>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>End Date</label>
                                        <input
                                            type="date"
                                            className="input"
                                            value={formData.end_date}
                                            onChange={e => setFormData({ ...formData, end_date: e.target.value })}
                                        />
                                    </div>
                                </div>
                                <div style={{ marginBottom: '1.5rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Notes</label>
                                    <textarea
                                        className="input"
                                        value={formData.notes}
                                        onChange={e => setFormData({ ...formData, notes: e.target.value })}
                                        rows={2}
                                        style={{ width: '100%' }}
                                    />
                                </div>
                                <div style={{ display: 'flex', gap: '1rem' }}>
                                    <button type="button" className="btn btn-outline" onClick={resetForm} style={{ flex: 1 }}>Cancel</button>
                                    <button type="submit" className="btn btn-primary" style={{ flex: 1 }}>Create</button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
};

export default ProductionOrderList;
