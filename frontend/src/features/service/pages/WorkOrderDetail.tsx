import { useParams, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useDialog } from '../../../hooks/useDialog';
import { ArrowLeft, CheckCircle, Plus, Trash2, DollarSign, BookOpen, Wrench, Clock, Package } from 'lucide-react';
import {
    useWorkOrder, useCompleteWorkOrder, useAddWorkOrderMaterial,
    useDeleteWorkOrderMaterial, usePostWorkOrderToGL, useTechnicians, useUpdateWorkOrder,
} from '../hooks/useService';
import ServiceLayout from '../ServiceLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import type { WorkOrder, WorkOrderMaterial, Technician } from '../types';

const statusColor = (status: string) => {
    switch (status) {
        case 'Completed': return '#22c55e';
        case 'In Progress': return '#2471a3';
        case 'Assigned': return '#fbbf24';
        case 'Pending': return '#9ca3af';
        case 'Cancelled': return '#ef4444';
        default: return '#9ca3af';
    }
};

const priorityColor = (p: string) => {
    switch (p) {
        case 'Urgent': return '#ef4444';
        case 'High': return '#f97316';
        case 'Medium': return '#2471a3';
        default: return '#9ca3af';
    }
};

export default function WorkOrderDetail() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const { showConfirm } = useDialog();
    const { data: workOrder, isLoading } = useWorkOrder(id || '');
    const { data: technicians } = useTechnicians();
    const completeWorkOrder = useCompleteWorkOrder();
    const addMaterial = useAddWorkOrderMaterial();
    const deleteMaterial = useDeleteWorkOrderMaterial();
    const postToGL = usePostWorkOrderToGL();
    const updateWorkOrder = useUpdateWorkOrder();

    const techsList = (technicians?.results || technicians || []) as Technician[];

    const [showAddMaterial, setShowAddMaterial] = useState(false);
    const [materialForm, setMaterialForm] = useState({ item_description: '', quantity: '', unit_price: '' });

    const handleAddMaterial = (e: React.FormEvent) => {
        e.preventDefault();
        if (!workOrder) return;
        addMaterial.mutate({
            workOrderId: workOrder.id,
            item_description: materialForm.item_description,
            quantity: parseFloat(materialForm.quantity),
            unit_price: parseFloat(materialForm.unit_price),
        }, {
            onSuccess: () => {
                setShowAddMaterial(false);
                setMaterialForm({ item_description: '', quantity: '', unit_price: '' });
            },
        });
    };

    const handleDeleteMaterial = async (materialId: number) => {
        if (await showConfirm('Remove this material?')) {
            deleteMaterial.mutate(materialId);
        }
    };

    const handleComplete = async () => {
        if (workOrder && await showConfirm('Mark this work order as completed?')) {
            completeWorkOrder.mutate(workOrder.id);
        }
    };

    const handlePostToGL = async () => {
        if (workOrder && await showConfirm('Post this work order to the General Ledger?')) {
            postToGL.mutate(workOrder.id);
        }
    };

    const handleAssignTechnician = (techId: string) => {
        if (workOrder && techId) {
            updateWorkOrder.mutate({ id: workOrder.id, technician: parseInt(techId) as unknown as null });
        }
    };

    if (isLoading) return <LoadingScreen message="Loading work order..." />;
    if (!workOrder) return (
        <ServiceLayout>
            <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                Work order not found.
            </div>
        </ServiceLayout>
    );

    const wo = workOrder as WorkOrder;
    const materials = wo.materials || [];
    const isEditable = wo.status !== 'Completed' && wo.status !== 'Cancelled';

    const inputStyle: React.CSSProperties = {
        width: '100%', padding: '0.5rem', fontSize: 'var(--text-xs)',
        border: '2.5px solid var(--color-border)', borderRadius: '6px',
        background: 'var(--color-surface)', color: 'var(--color-text)',
    };

    return (
        <ServiceLayout>
            <div style={{ padding: '1.5rem', maxWidth: '960px' }}>
                {/* Back */}
                <button
                    onClick={() => navigate('/service/work-orders')}
                    style={{
                        display: 'flex', alignItems: 'center', gap: '0.4rem',
                        background: 'none', border: 'none', color: 'var(--color-primary)',
                        cursor: 'pointer', padding: 0, fontSize: 'var(--text-sm)', marginBottom: '1.25rem',
                    }}
                >
                    <ArrowLeft size={16} /> Back to Work Orders
                </button>

                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
                    <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                            <span style={{ fontFamily: 'monospace', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>{wo.work_order_number}</span>
                            <span style={{
                                padding: '0.2rem 0.6rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 600,
                                background: `${statusColor(wo.status)}20`, color: statusColor(wo.status),
                            }}>{wo.status}</span>
                            <span style={{
                                padding: '0.2rem 0.6rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 600,
                                background: `${priorityColor(wo.priority)}20`, color: priorityColor(wo.priority),
                            }}>{wo.priority}</span>
                        </div>
                        <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>{wo.title}</h1>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        {isEditable && (
                            <button onClick={handleComplete} style={{
                                display: 'flex', alignItems: 'center', gap: '0.4rem',
                                padding: '0.5rem 1rem', background: 'rgba(34,197,94,0.1)',
                                color: '#22c55e', border: 'none', borderRadius: '8px',
                                fontWeight: 600, cursor: 'pointer', fontSize: 'var(--text-sm)',
                            }}>
                                <CheckCircle size={16} /> Complete
                            </button>
                        )}
                        {wo.status === 'Completed' && (
                            <button onClick={handlePostToGL} disabled={postToGL.isPending} style={{
                                display: 'flex', alignItems: 'center', gap: '0.4rem',
                                padding: '0.5rem 1rem', background: 'rgba(59,130,246,0.1)',
                                color: '#2471a3', border: 'none', borderRadius: '8px',
                                fontWeight: 600, cursor: 'pointer', fontSize: 'var(--text-sm)',
                            }}>
                                <BookOpen size={16} /> {postToGL.isPending ? 'Posting...' : 'Post to GL'}
                            </button>
                        )}
                    </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '1.5rem' }}>
                    {/* Left column */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                        {/* Description */}
                        <div style={{
                            background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                            borderRadius: '12px', padding: '1.25rem',
                        }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '0.75rem', color: 'var(--color-text)' }}>Description</h3>
                            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', margin: 0, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                                {wo.description}
                            </p>
                            {wo.notes && (
                                <>
                                    <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginTop: '1rem', marginBottom: '0.5rem', color: 'var(--color-text)' }}>Notes</h3>
                                    <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', margin: 0, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                                        {wo.notes}
                                    </p>
                                </>
                            )}
                        </div>

                        {/* Materials */}
                        <div style={{
                            background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                            borderRadius: '12px', padding: '1.25rem',
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                                <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', display: 'flex', alignItems: 'center', gap: '0.4rem', margin: 0 }}>
                                    <Package size={16} /> Materials ({materials.length})
                                </h3>
                                {isEditable && (
                                    <button
                                        onClick={() => setShowAddMaterial(true)}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: '0.3rem',
                                            padding: '0.4rem 0.75rem', background: 'var(--color-primary)',
                                            color: 'white', border: 'none', borderRadius: '6px',
                                            fontWeight: 600, cursor: 'pointer', fontSize: 'var(--text-xs)',
                                        }}
                                    >
                                        <Plus size={14} /> Add
                                    </button>
                                )}
                            </div>

                            {materials.length === 0 ? (
                                <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>
                                    No materials added yet.
                                </div>
                            ) : (
                                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                    <thead>
                                        <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                            <th style={{ padding: '0.5rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Item</th>
                                            <th style={{ padding: '0.5rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Qty</th>
                                            <th style={{ padding: '0.5rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Unit Price</th>
                                            <th style={{ padding: '0.5rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Total</th>
                                            {isEditable && <th style={{ padding: '0.5rem', width: '40px' }}></th>}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {materials.map((m: WorkOrderMaterial) => (
                                            <tr key={m.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                                <td style={{ padding: '0.5rem', fontSize: 'var(--text-xs)' }}>{m.item_description}</td>
                                                <td style={{ padding: '0.5rem', textAlign: 'right', fontSize: 'var(--text-xs)' }}>{m.quantity}</td>
                                                <td style={{ padding: '0.5rem', textAlign: 'right', fontSize: 'var(--text-xs)' }}>${Number(m.unit_price).toFixed(2)}</td>
                                                <td style={{ padding: '0.5rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600 }}>${Number(m.total_price).toFixed(2)}</td>
                                                {isEditable && (
                                                    <td style={{ padding: '0.5rem', textAlign: 'center' }}>
                                                        <button onClick={() => handleDeleteMaterial(m.id)} style={{
                                                            background: 'none', border: 'none', color: '#ef4444',
                                                            cursor: 'pointer', padding: '0.2rem',
                                                        }}>
                                                            <Trash2 size={14} />
                                                        </button>
                                                    </td>
                                                )}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}

                            {/* Add material form */}
                            {showAddMaterial && (
                                <form onSubmit={handleAddMaterial} style={{
                                    marginTop: '1rem', padding: '1rem', borderRadius: '8px',
                                    background: 'rgba(59,130,246,0.03)', border: '1px solid var(--color-border)',
                                }}>
                                    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: '0.5rem', marginBottom: '0.75rem' }}>
                                        <input
                                            type="text" placeholder="Item description" required
                                            value={materialForm.item_description}
                                            onChange={e => setMaterialForm({ ...materialForm, item_description: e.target.value })}
                                            style={inputStyle}
                                        />
                                        <input
                                            type="number" placeholder="Qty" required min="0.01" step="0.01"
                                            value={materialForm.quantity}
                                            onChange={e => setMaterialForm({ ...materialForm, quantity: e.target.value })}
                                            style={inputStyle}
                                        />
                                        <input
                                            type="number" placeholder="Unit price" required min="0" step="0.01"
                                            value={materialForm.unit_price}
                                            onChange={e => setMaterialForm({ ...materialForm, unit_price: e.target.value })}
                                            style={inputStyle}
                                        />
                                    </div>
                                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                        <button type="button" onClick={() => setShowAddMaterial(false)} style={{
                                            padding: '0.4rem 0.75rem', fontSize: 'var(--text-xs)',
                                            background: 'transparent', border: '1px solid var(--color-border)',
                                            borderRadius: '6px', color: 'var(--color-text)', cursor: 'pointer',
                                        }}>Cancel</button>
                                        <button type="submit" disabled={addMaterial.isPending} style={{
                                            padding: '0.4rem 0.75rem', fontSize: 'var(--text-xs)',
                                            background: 'var(--color-primary)', border: 'none',
                                            borderRadius: '6px', color: 'white', fontWeight: 600, cursor: 'pointer',
                                        }}>{addMaterial.isPending ? 'Adding...' : 'Add Material'}</button>
                                    </div>
                                </form>
                            )}
                        </div>
                    </div>

                    {/* Right column */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                        {/* Cost breakdown */}
                        <div style={{
                            background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                            borderRadius: '12px', padding: '1.25rem',
                        }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                <DollarSign size={16} /> Cost Breakdown
                            </h3>
                            {[
                                { label: 'Labor Hours', value: `${wo.labor_hours}h` },
                                { label: 'Labor Cost', value: `$${Number(wo.labor_cost).toFixed(2)}` },
                                { label: 'Parts Cost', value: `$${Number(wo.parts_cost).toFixed(2)}` },
                            ].map((item, i) => (
                                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--color-border)', fontSize: 'var(--text-xs)' }}>
                                    <span style={{ color: 'var(--color-text-muted)' }}>{item.label}</span>
                                    <span style={{ color: 'var(--color-text)', fontWeight: 500 }}>{item.value}</span>
                                </div>
                            ))}
                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem 0 0', fontSize: 'var(--text-sm)' }}>
                                <span style={{ fontWeight: 700, color: 'var(--color-text)' }}>Total</span>
                                <span style={{ fontWeight: 700, color: 'var(--color-primary)' }}>${Number(wo.total_cost).toFixed(2)}</span>
                            </div>
                        </div>

                        {/* Details */}
                        <div style={{
                            background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                            borderRadius: '12px', padding: '1.25rem',
                        }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text)' }}>Details</h3>
                            {[
                                { label: 'Asset', value: wo.asset_name || '-' },
                                { label: 'Scheduled', value: wo.scheduled_date || '-' },
                                { label: 'Completed', value: wo.completed_date || '-' },
                                { label: 'Created', value: new Date(wo.created_at).toLocaleDateString() },
                            ].map((item, i) => (
                                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--color-border)', fontSize: 'var(--text-xs)' }}>
                                    <span style={{ color: 'var(--color-text-muted)' }}>{item.label}</span>
                                    <span style={{ color: 'var(--color-text)', fontWeight: 500 }}>{item.value}</span>
                                </div>
                            ))}
                        </div>

                        {/* Technician */}
                        <div style={{
                            background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                            borderRadius: '12px', padding: '1.25rem',
                        }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '0.75rem', color: 'var(--color-text)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                <Wrench size={16} /> Technician
                            </h3>
                            {wo.technician_name ? (
                                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text)', fontWeight: 500 }}>
                                    {wo.technician_name}
                                </div>
                            ) : (
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>Unassigned</div>
                            )}
                            {isEditable && (
                                <select
                                    onChange={(e) => handleAssignTechnician(e.target.value)}
                                    defaultValue=""
                                    style={{
                                        marginTop: '0.75rem', width: '100%', padding: '0.5rem',
                                        fontSize: 'var(--text-xs)', border: '2.5px solid var(--color-border)',
                                        borderRadius: '6px', background: 'var(--color-surface)', color: 'var(--color-text)',
                                    }}
                                >
                                    <option value="">{wo.technician_name ? 'Reassign...' : 'Assign...'}</option>
                                    {techsList.filter((tech) => tech.is_available).map((tech) => (
                                        <option key={tech.id} value={tech.id}>{tech.name}</option>
                                    ))}
                                </select>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </ServiceLayout>
    );
}
