import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useProductionOrder } from '../hooks/useProduction';
import Sidebar from '../../../components/Sidebar';
import BackButton from '../../../components/BackButton';
import LoadingScreen from '../../../components/common/LoadingScreen';
import MaterialConsumptionTab from './tabs/MaterialConsumptionTab';
import FinishedGoodsTab from './tabs/FinishedGoodsTab';
import JobCardsTab from './tabs/JobCardsTab';
import BatchesTab from './tabs/BatchesTab';
import QualityTab from './tabs/QualityTab';
import {
    useStartProduction, useCompleteProduction, usePostProductionToGL,
    useMaterialRequirements, useMaterialIssues, useMaterialReceipts, useJobCards,
    useUpdateProductionOrder, useScheduleProduction,
} from '../hooks/useProduction';
import { Package, CheckCircle, Layers, ClipboardList, Shield, Play, FileCheck, XCircle, Edit2 } from 'lucide-react';

type TabKey = 'materials' | 'finished' | 'jobcards' | 'batches' | 'quality';

const STATUS_COLORS: Record<string, string> = {
    Draft: '#64748b',
    Scheduled: '#191e6a',
    'In Progress': '#3b82f6',
    'On Hold': '#f59e0b',
    Done: '#10b981',
    Cancelled: '#ef4444',
};

const ProductionOrderDetail = () => {
    const { id } = useParams<{ id: string }>();
    const orderId = id ? parseInt(id) : undefined;
    const { data: order, isLoading } = useProductionOrder(orderId);
    const startProduction = useStartProduction();
    const completeProduction = useCompleteProduction();
    const postToGL = usePostProductionToGL();
    const [activeTab, setActiveTab] = useState<TabKey>('materials');
    const [completeQty, setCompleteQty] = useState('');
    const [showCompletePrompt, setShowCompletePrompt] = useState(false);
    const [showCancelConfirm, setShowCancelConfirm] = useState(false);
    const [showEditModal, setShowEditModal] = useState(false);
    const [editForm, setEditForm] = useState({ quantity_planned: '', start_date: '', end_date: '', notes: '' });
    const updateOrder = useUpdateProductionOrder();
    const scheduleProduction = useScheduleProduction();
    const { data: requirements } = useMaterialRequirements(orderId);
    const { data: issuesData } = useMaterialIssues(orderId ? { production_order: orderId } : {});
    const { data: receiptsData } = useMaterialReceipts(orderId ? { production_order: orderId } : {});
    const { data: jobCardsData } = useJobCards(orderId ? { production_order: orderId } : {});

    if (isLoading || !order) {
        return <LoadingScreen message="Loading production order..." />;
    }

    const progress = order.quantity_planned > 0
        ? Math.round((order.quantity_produced / order.quantity_planned) * 100)
        : 0;

    const statusColor = STATUS_COLORS[order.status] || '#64748b';

    const handleStart = async () => {
        await startProduction.mutateAsync(order.id);
    };

    const handleSchedule = async () => {
        await scheduleProduction.mutateAsync({
            id: order.id,
            start_date: order.start_date || new Date().toISOString().split('T')[0],
        });
    };

    const handleComplete = async () => {
        const qty = parseFloat(completeQty);
        if (!qty || qty <= 0) return;
        await completeProduction.mutateAsync({ id: order.id, quantity_produced: qty });
        setShowCompletePrompt(false);
        setCompleteQty('');
    };

    const handlePostToGL = async () => {
        await postToGL.mutateAsync(order.id);
    };

    const handleOpenEdit = () => {
        setEditForm({
            quantity_planned: String(order.quantity_planned),
            start_date: order.start_date || '',
            end_date: order.end_date || '',
            notes: order.notes || '',
        });
        setShowEditModal(true);
    };

    const handleSaveEdit = async () => {
        await updateOrder.mutateAsync({
            id: order.id,
            data: {
                quantity_planned: parseFloat(editForm.quantity_planned),
                start_date: editForm.start_date,
                end_date: editForm.end_date || null,
                notes: editForm.notes,
            },
        });
        setShowEditModal(false);
    };

    const reqCount = Array.isArray(requirements) ? requirements.length : 0;
    const issueCount = (issuesData?.results || issuesData || []).length;
    const receiptCount = (receiptsData?.results || receiptsData || []).length;
    const jobCardCount = (jobCardsData?.results || jobCardsData || []).length;

    const tabs: { key: TabKey; label: string; icon: any; count?: number }[] = [
        { key: 'materials', label: 'Materials', icon: Package, count: reqCount },
        { key: 'finished', label: 'Finished Goods', icon: CheckCircle, count: receiptCount },
        { key: 'jobcards', label: 'Job Cards', icon: ClipboardList, count: jobCardCount },
        { key: 'batches', label: 'Batches', icon: Layers },
        { key: 'quality', label: 'Quality', icon: Shield },
    ];

    return (
        <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--color-bg, #f1f5f9)' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2rem 2.5rem' }}>
                <BackButton />

                {/* Header Card */}
                <div style={{
                    background: 'var(--color-surface, #fff)', border: '1px solid var(--color-border, #e2e8f0)',
                    borderRadius: '14px', padding: '24px 28px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                    marginBottom: '20px',
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                            <h1 style={{ fontSize: '22px', fontWeight: 800, letterSpacing: '-0.5px' }}>{order.order_number}</h1>
                            <span style={{
                                padding: '5px 14px', borderRadius: '20px', fontSize: '11px',
                                fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px',
                                background: `${statusColor}1a`, color: statusColor,
                            }}>{order.status}</span>
                            {order.bom_requires_quality_inspection && (
                                <span style={{
                                    padding: '4px 10px', borderRadius: '20px', fontSize: '10px',
                                    fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px',
                                    background: 'rgba(139,92,246,0.1)', color: '#8b5cf6',
                                }}>QI Required</span>
                            )}
                            {!order.bom_requires_quality_inspection && (
                                <span style={{
                                    padding: '4px 10px', borderRadius: '20px', fontSize: '10px',
                                    fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px',
                                    background: 'rgba(100,116,139,0.1)', color: '#64748b',
                                }}>QI Not Required</span>
                            )}
                        </div>
                    </div>

                    <div style={{
                        display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '20px',
                        paddingTop: '16px', borderTop: '1px solid var(--color-border, #e2e8f0)',
                    }}>
                        {[
                            { label: 'Product (BOM)', value: order.bom_name },
                            { label: 'Work Center', value: order.work_center_name || '\u2014' },
                            { label: 'Start Date', value: order.start_date || '\u2014' },
                            { label: 'End Date', value: order.end_date || '\u2014' },
                            { label: 'Quantity', value: `${order.quantity_produced} / ${order.quantity_planned}` },
                        ].map(m => (
                            <div key={m.label}>
                                <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted, #64748b)', marginBottom: '4px' }}>{m.label}</div>
                                <div style={{ fontSize: '14px', fontWeight: 600 }}>{m.value}</div>
                            </div>
                        ))}
                    </div>

                    <div style={{ marginTop: '14px', paddingTop: '14px', borderTop: '1px solid var(--color-border, #e2e8f0)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', fontWeight: 600, color: 'var(--color-text-muted, #64748b)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px' }}>
                            <span>Production Progress</span>
                            <span style={{ color: '#191e6a', fontWeight: 700 }}>{progress}%</span>
                        </div>
                        <div style={{ height: '8px', borderRadius: '99px', background: '#e2e8f0', overflow: 'hidden' }}>
                            <div style={{ height: '100%', borderRadius: '99px', background: 'linear-gradient(90deg, #191e6a, #4a52c0)', width: `${progress}%`, transition: 'width 0.5s ease' }} />
                        </div>
                    </div>
                </div>

                {/* Action Bar */}
                <div style={{ display: 'flex', gap: '10px', marginBottom: '20px', flexWrap: 'wrap', alignItems: 'center' }}>
                    {order.status === 'Draft' && (
                        <button onClick={handleSchedule} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', boxShadow: '0 4px 12px rgba(15,18,64,0.3)', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <Play size={14} /> Schedule
                        </button>
                    )}
                    {order.status === 'Scheduled' && (
                        <button onClick={handleStart} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', boxShadow: '0 4px 12px rgba(15,18,64,0.3)', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <Play size={14} /> Start Production
                        </button>
                    )}
                    {order.status === 'In Progress' && !showCompletePrompt && (
                        <button onClick={() => setShowCompletePrompt(true)} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #059669, #10b981)', color: 'white', boxShadow: '0 4px 12px rgba(16,185,129,0.3)', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <CheckCircle size={14} /> Complete Production
                        </button>
                    )}
                    {showCompletePrompt && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 14px', borderRadius: '8px', background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)' }}>
                            <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text-muted)' }}>Qty Produced:</label>
                            <input type="number" value={completeQty} onChange={e => setCompleteQty(e.target.value)} placeholder={String(order.quantity_planned)} style={{ width: '100px', padding: '6px 10px', borderRadius: '6px', border: '2px solid var(--color-border, #e2e8f0)', fontSize: '13px', fontFamily: 'inherit' }} />
                            <button onClick={handleComplete} style={{ padding: '6px 14px', borderRadius: '6px', fontSize: '12px', fontWeight: 600, border: 'none', cursor: 'pointer', background: '#10b981', color: 'white', fontFamily: 'inherit' }}>Confirm</button>
                            <button onClick={() => setShowCompletePrompt(false)} style={{ padding: '6px 14px', borderRadius: '6px', fontSize: '12px', fontWeight: 600, border: '1px solid var(--color-border)', cursor: 'pointer', background: 'var(--color-surface)', color: 'var(--color-text-secondary)', fontFamily: 'inherit' }}>Cancel</button>
                        </div>
                    )}
                    {order.status === 'On Hold' && (
                        <button onClick={async () => { await updateOrder.mutateAsync({ id: order.id, data: { status: 'In Progress' } }); }} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', boxShadow: '0 4px 12px rgba(15,18,64,0.3)', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <Play size={14} /> Resume Production
                        </button>
                    )}
                    {order.status === 'Done' && (
                        <button onClick={handlePostToGL} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', boxShadow: '0 4px 12px rgba(15,18,64,0.3)', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <FileCheck size={14} /> Post to GL
                        </button>
                    )}
                    {['Draft', 'Scheduled'].includes(order.status) && (
                        <button onClick={handleOpenEdit} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: '1.5px solid var(--color-border, #e2e8f0)', cursor: 'pointer', background: 'var(--color-surface, #fff)', color: 'var(--color-text-secondary, #475569)', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <Edit2 size={14} /> Edit Order
                        </button>
                    )}
                    {['Draft', 'Scheduled', 'In Progress'].includes(order.status) && !showCancelConfirm && (
                        <button onClick={() => setShowCancelConfirm(true)} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: '1.5px solid rgba(239,68,68,0.3)', cursor: 'pointer', background: 'var(--color-surface, #fff)', color: '#ef4444', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <XCircle size={14} /> Cancel Order
                        </button>
                    )}
                    {showCancelConfirm && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 14px', borderRadius: '8px', background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)' }}>
                            <span style={{ fontSize: '12px', fontWeight: 600, color: '#ef4444' }}>Are you sure?</span>
                            <button onClick={() => setShowCancelConfirm(false)} style={{ padding: '6px 14px', borderRadius: '6px', fontSize: '12px', fontWeight: 600, border: '1px solid var(--color-border)', cursor: 'pointer', background: 'var(--color-surface)', color: 'var(--color-text-secondary)', fontFamily: 'inherit' }}>No</button>
                            <button onClick={async () => { await updateOrder.mutateAsync({ id: order.id, data: { status: 'Cancelled' } }); setShowCancelConfirm(false); }} style={{ padding: '6px 14px', borderRadius: '6px', fontSize: '12px', fontWeight: 600, border: 'none', cursor: 'pointer', background: '#ef4444', color: 'white', fontFamily: 'inherit' }}>Yes, Cancel</button>
                        </div>
                    )}
                </div>

                {/* Tabs */}
                <div style={{ display: 'flex', gap: 0, borderBottom: '2px solid var(--color-border, #e2e8f0)', marginBottom: '20px' }}>
                    {tabs.map(t => (
                        <button key={t.key} role="tab" aria-selected={activeTab === t.key} onClick={() => setActiveTab(t.key)} style={{
                            padding: '10px 20px', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                            color: activeTab === t.key ? '#191e6a' : 'var(--color-text-muted, #64748b)',
                            borderBottom: activeTab === t.key ? '2px solid #191e6a' : '2px solid transparent',
                            marginBottom: '-2px', transition: 'all 0.15s',
                            display: 'flex', alignItems: 'center', gap: '6px',
                            background: 'none', border: 'none', borderBottom: activeTab === t.key ? '2px solid #191e6a' : '2px solid transparent',
                        }}>
                            <t.icon size={14} aria-hidden="true" /> {t.label}
                            {t.count !== undefined && t.count > 0 && (
                                <span style={{
                                    background: 'rgba(25,30,106,0.1)', color: '#191e6a',
                                    fontSize: '10px', fontWeight: 700, padding: '2px 7px',
                                    borderRadius: '99px',
                                }}>{t.count}</span>
                            )}
                        </button>
                    ))}
                </div>

                {/* Tab Content */}
                {activeTab === 'materials' && <MaterialConsumptionTab orderId={order.id} order={order} />}
                {activeTab === 'finished' && <FinishedGoodsTab orderId={order.id} order={order} />}
                {activeTab === 'jobcards' && <JobCardsTab orderId={order.id} order={order} />}
                {activeTab === 'batches' && <BatchesTab orderId={order.id} order={order} />}
                {activeTab === 'quality' && <QualityTab orderId={order.id} order={order} />}

                {/* Edit Modal */}
                {showEditModal && (
                    <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999, backdropFilter: 'blur(2px)' }} onClick={() => setShowEditModal(false)}>
                        <div role="dialog" aria-modal="true" aria-labelledby="edit-order-dialog-title" style={{ background: 'white', borderRadius: '16px', padding: '28px', maxWidth: '450px', width: '90%', boxShadow: '0 24px 64px rgba(0,0,0,0.25)' }} onClick={e => e.stopPropagation()}>
                            <h3 id="edit-order-dialog-title" style={{ fontSize: '16px', fontWeight: 700, marginBottom: '16px' }}>Edit Production Order</h3>
                            <div style={{ display: 'grid', gap: '12px', marginBottom: '16px' }}>
                                <div>
                                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>Quantity Planned</label>
                                    <input type="number" step="0.01" value={editForm.quantity_planned} onChange={e => setEditForm({ ...editForm, quantity_planned: e.target.value })} style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid #e2e8f0', fontSize: '13px', fontFamily: 'inherit', background: '#f8fafc' }} />
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                                    <div>
                                        <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>Start Date</label>
                                        <input type="date" value={editForm.start_date} onChange={e => setEditForm({ ...editForm, start_date: e.target.value })} style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid #e2e8f0', fontSize: '13px', fontFamily: 'inherit', background: '#f8fafc' }} />
                                    </div>
                                    <div>
                                        <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>End Date</label>
                                        <input type="date" value={editForm.end_date} onChange={e => setEditForm({ ...editForm, end_date: e.target.value })} style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid #e2e8f0', fontSize: '13px', fontFamily: 'inherit', background: '#f8fafc' }} />
                                    </div>
                                </div>
                                <div>
                                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>Notes</label>
                                    <textarea value={editForm.notes} onChange={e => setEditForm({ ...editForm, notes: e.target.value })} rows={3} style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid #e2e8f0', fontSize: '13px', fontFamily: 'inherit', background: '#f8fafc', resize: 'vertical' }} />
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                                <button onClick={() => setShowEditModal(false)} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: '1px solid #e2e8f0', cursor: 'pointer', background: '#f8fafc', color: '#475569', fontFamily: 'inherit' }}>Cancel</button>
                                <button onClick={handleSaveEdit} disabled={updateOrder.isPending} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', fontFamily: 'inherit' }}>
                                    {updateOrder.isPending ? 'Saving...' : 'Save Changes'}
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
};

export default ProductionOrderDetail;
