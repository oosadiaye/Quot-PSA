import { useProductionOrders, useWorkCenters, useBillOfMaterials } from '../hooks/useProduction';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import { Factory, Package, FileText, Play, CheckCircle, Clock, AlertTriangle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import LoadingScreen from '../../../components/common/LoadingScreen';

const ProductionDashboard = () => {
    const navigate = useNavigate();
    const { data: ordersData, isLoading: ordersLoading } = useProductionOrders();
    const { data: workCentersData, isLoading: wcLoading } = useWorkCenters();
    const { data: bomsData, isLoading: bomsLoading } = useBillOfMaterials();

    const orders = Array.isArray(ordersData?.results) ? ordersData.results : Array.isArray(ordersData) ? ordersData : [];
    const workCenters = Array.isArray(workCentersData?.results) ? workCentersData.results : Array.isArray(workCentersData) ? workCentersData : [];
    const boms = Array.isArray(bomsData?.results) ? bomsData.results : Array.isArray(bomsData) ? bomsData : [];

    if (ordersLoading || wcLoading || bomsLoading) {
        return <LoadingScreen message="Loading production dashboard..." />;
    }

    const draftOrders = orders.filter((o: any) => o.status === 'Draft');
    const scheduledOrders = orders.filter((o: any) => o.status === 'Scheduled');
    const inProgressOrders = orders.filter((o: any) => o.status === 'In Progress');
    const doneOrders = orders.filter((o: any) => o.status === 'Done');

    const activeWorkCenters = workCenters.filter((w: any) => w.is_active);
    const finishedBOMs = boms.filter((b: any) => b.item_type === 'Finished');
    const rawMaterialBOMs = boms.filter((b: any) => b.item_type === 'Raw Material');

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Production & Manufacturing"
                    subtitle="Manage work centers, bills of materials, and production orders."
                    icon={<Factory size={22} color="white" />}
                />

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1.5rem', marginBottom: '2.5rem' }}>
                    <div className="card" role="button" tabIndex={0} style={{ cursor: 'pointer' }} onClick={() => navigate('/production/orders')} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') navigate('/production/orders'); }} aria-label="View Production Orders">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <div style={{ padding: '0.75rem', borderRadius: '0.5rem', background: 'rgba(36, 113, 163, 0.15)' }}>
                                <Package size={24} style={{ color: 'var(--color-primary)' }} aria-hidden="true" />
                            </div>
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>TOTAL ORDERS</div>
                                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{orders.length}</div>
                            </div>
                        </div>
                    </div>
                    <div className="card" role="button" tabIndex={0} style={{ cursor: 'pointer' }} onClick={() => navigate('/production/work-centers')} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') navigate('/production/work-centers'); }} aria-label="View Work Centers">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <div style={{ padding: '0.75rem', borderRadius: '0.5rem', background: 'rgba(34, 197, 94, 0.15)' }}>
                                <Factory size={24} style={{ color: 'var(--color-success)' }} aria-hidden="true" />
                            </div>
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>WORK CENTERS</div>
                                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{activeWorkCenters.length}</div>
                            </div>
                        </div>
                    </div>
                    <div className="card" role="button" tabIndex={0} style={{ cursor: 'pointer' }} onClick={() => navigate('/production/bom')} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') navigate('/production/bom'); }} aria-label="View Bill of Materials">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <div style={{ padding: '0.75rem', borderRadius: '0.5rem', background: 'rgba(139, 92, 246, 0.15)' }}>
                                <FileText size={24} style={{ color: '#8b5cf6' }} />
                            </div>
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>BILL OF MATERIALS</div>
                                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{boms.length}</div>
                            </div>
                        </div>
                    </div>
                    <div className="card">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <div style={{ padding: '0.75rem', borderRadius: '0.5rem', background: 'rgba(245, 158, 11, 0.15)' }}>
                                <AlertTriangle size={24} style={{ color: '#f59e0b' }} />
                            </div>
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>IN PROGRESS</div>
                                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{inProgressOrders.length}</div>
                            </div>
                        </div>
                    </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem', marginBottom: '2.5rem' }}>
                    <div>
                        <h2 style={{ fontSize: 'var(--text-lg)', marginBottom: '1rem' }}>Production Orders by Status</h2>
                        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                        <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                                        <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Count</th>
                                        <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Progress</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem' }}><span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><Clock size={14} /> Draft</span></td>
                                        <td style={{ padding: '1rem', fontWeight: 600 }}>{draftOrders.length}</td>
                                        <td style={{ padding: '1rem' }}><div style={{ width: '100%', height: '8px', background: 'var(--color-surface)', borderRadius: '4px' }}><div style={{ width: `${orders.length ? (draftOrders.length / orders.length) * 100 : 0}%`, height: '100%', background: 'var(--color-text-muted)', borderRadius: '4px' }} /></div></td>
                                    </tr>
                                    <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem' }}><span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#f59e0b' }}><Play size={14} /> Scheduled</span></td>
                                        <td style={{ padding: '1rem', fontWeight: 600 }}>{scheduledOrders.length}</td>
                                        <td style={{ padding: '1rem' }}><div style={{ width: '100%', height: '8px', background: 'var(--color-surface)', borderRadius: '4px' }}><div style={{ width: `${orders.length ? (scheduledOrders.length / orders.length) * 100 : 0}%`, height: '100%', background: '#f59e0b', borderRadius: '4px' }} /></div></td>
                                    </tr>
                                    <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem' }}><span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--color-primary)' }}><Clock size={14} /> In Progress</span></td>
                                        <td style={{ padding: '1rem', fontWeight: 600 }}>{inProgressOrders.length}</td>
                                        <td style={{ padding: '1rem' }}><div style={{ width: '100%', height: '8px', background: 'var(--color-surface)', borderRadius: '4px' }}><div style={{ width: `${orders.length ? (inProgressOrders.length / orders.length) * 100 : 0}%`, height: '100%', background: 'var(--color-primary)', borderRadius: '4px' }} /></div></td>
                                    </tr>
                                    <tr>
                                        <td style={{ padding: '1rem' }}><span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--color-success)' }}><CheckCircle size={14} /> Completed</span></td>
                                        <td style={{ padding: '1rem', fontWeight: 600 }}>{doneOrders.length}</td>
                                        <td style={{ padding: '1rem' }}><div style={{ width: '100%', height: '8px', background: 'var(--color-surface)', borderRadius: '4px' }}><div style={{ width: `${orders.length ? (doneOrders.length / orders.length) * 100 : 0}%`, height: '100%', background: 'var(--color-success)', borderRadius: '4px' }} /></div></td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <div>
                        <h2 style={{ fontSize: 'var(--text-lg)', marginBottom: '1rem' }}>Quick Stats</h2>
                        <div className="card" style={{ marginBottom: '1rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0' }}>
                                <span style={{ color: 'var(--color-text-muted)' }}>Finished Products (BOMs)</span>
                                <span style={{ fontWeight: 600 }}>{finishedBOMs.length}</span>
                            </div>
                        </div>
                        <div className="card" style={{ marginBottom: '1rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0' }}>
                                <span style={{ color: 'var(--color-text-muted)' }}>Raw Materials (BOMs)</span>
                                <span style={{ fontWeight: 600 }}>{rawMaterialBOMs.length}</span>
                            </div>
                        </div>
                        <div className="card">
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0' }}>
                                <span style={{ color: 'var(--color-text-muted)' }}>Inactive Work Centers</span>
                                <span style={{ fontWeight: 600, color: 'var(--color-error)' }}>{workCenters.length - activeWorkCenters.length}</span>
                            </div>
                        </div>
                    </div>
                </div>

                <h2 style={{ fontSize: 'var(--text-lg)', marginBottom: '1rem' }}>Recent Production Orders</h2>
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Order #</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Product</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Quantity</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Start Date</th>
                            </tr>
                        </thead>
                        <tbody>
                            {orders.length === 0 ? (
                                <tr><td colSpan={5} style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No production orders found</td></tr>
                            ) : (
                                orders.slice(0, 10).map((order: any) => (
                                    <tr key={order.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem', fontWeight: 600 }}>{order.order_number}</td>
                                        <td style={{ padding: '1rem' }}>{order.bom_name || '-'}</td>
                                        <td style={{ padding: '1rem' }}>{order.quantity_planned}</td>
                                        <td style={{ padding: '1rem' }}>
                                            <span style={{
                                                padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 700,
                                                background: order.status === 'Done' ? 'rgba(34, 197, 94, 0.15)' : order.status === 'In Progress' ? 'rgba(36, 113, 163, 0.15)' : order.status === 'Cancelled' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(107, 114, 128, 0.15)',
                                                color: order.status === 'Done' ? 'var(--color-success)' : order.status === 'In Progress' ? 'var(--color-primary)' : order.status === 'Cancelled' ? 'var(--color-error)' : 'var(--color-text-muted)'
                                            }}>
                                                {order.status}
                                            </span>
                                        </td>
                                        <td style={{ padding: '1rem' }}>{order.start_date || '-'}</td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </main>
        </div>
    );
};

export default ProductionDashboard;
