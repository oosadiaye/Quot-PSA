import { useState } from 'react';
import {
    useJobCards, useCreateJobCard, useStartJobCard, useCompleteJobCard,
    useWorkCenters,
} from '../../hooks/useProduction';
import { useEmployees } from '../../../hrm/hooks/useHrm';
import { Play, CheckCircle, Plus } from 'lucide-react';

interface Props {
    orderId: number;
    order: any;
}

const STATUS_BORDER: Record<string, string> = {
    Pending: '#94a3b8',
    'In Progress': '#3b82f6',
    Done: '#10b981',
};

const STATUS_BADGE: Record<string, { bg: string; color: string }> = {
    Pending: { bg: 'rgba(100,116,139,0.12)', color: '#64748b' },
    'In Progress': { bg: 'rgba(59,130,246,0.12)', color: '#3b82f6' },
    Done: { bg: 'rgba(16,185,129,0.12)', color: '#10b981' },
};

const JobCardsTab = ({ orderId, order }: Props) => {
    const { data: cardsData } = useJobCards({ production_order: orderId });
    const { data: workCentersData } = useWorkCenters();
    const createCard = useCreateJobCard();
    const startCard = useStartJobCard();
    const completeCard = useCompleteJobCard();

    const { data: employeesData } = useEmployees();
    const employees = employeesData?.results || employeesData || [];

    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState({ sequence: '', operation_name: '', work_center: '', time_planned: '', operator: '', notes: '' });
    const [completeForm, setCompleteForm] = useState<{ id: number; time_actual: string; labor_cost: string } | null>(null);
    const [error, setError] = useState('');

    const cards = cardsData?.results || cardsData || [];
    const workCenters = workCentersData?.results || workCentersData || [];
    const canEdit = ['Draft', 'Scheduled', 'In Progress'].includes(order.status);

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        try {
            await createCard.mutateAsync({
                production_order: orderId,
                sequence: parseInt(form.sequence),
                operation_name: form.operation_name,
                work_center: parseInt(form.work_center),
                time_planned: parseFloat(form.time_planned),
                operator: form.operator ? parseInt(form.operator) : null,
                notes: form.notes,
            });
            setForm({ sequence: '', operation_name: '', work_center: '', time_planned: '', operator: '', notes: '' });
            setShowForm(false);
        } catch (err: any) {
            setError(err?.response?.data?.error || err?.message || 'Failed to create job card');
        }
    };

    const handleStart = async (id: number) => {
        setError('');
        try { await startCard.mutateAsync(id); } catch (err: any) {
            setError(err?.response?.data?.error || err?.message || 'Failed to start operation');
        }
    };

    const handleComplete = async () => {
        if (!completeForm) return;
        setError('');
        try {
            await completeCard.mutateAsync({
                id: completeForm.id,
                time_actual: parseFloat(completeForm.time_actual) || 0,
                labor_cost: parseFloat(completeForm.labor_cost) || 0,
            });
            setCompleteForm(null);
        } catch (err: any) {
            setError(err?.response?.data?.error || err?.message || 'Failed to complete operation');
        }
    };

    const inputStyle: React.CSSProperties = { width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2.5px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' };
    const labelStyle: React.CSSProperties = { display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' };

    return (
        <div>
            {error && (
                <div style={{
                    padding: '10px 16px', borderRadius: '8px', marginBottom: '12px',
                    background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
                    color: '#ef4444', fontSize: '13px', fontWeight: 500,
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                    <span>{error}</span>
                    <button aria-label="Dismiss error" onClick={() => setError('')} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontWeight: 700, fontSize: '14px' }}><span aria-hidden="true">&times;</span></button>
                </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ fontSize: '14px', fontWeight: 700 }}>Operations</h3>
                {canEdit && (
                    <button onClick={() => setShowForm(!showForm)} style={{ padding: '7px 16px', borderRadius: '8px', fontSize: '12px', fontWeight: 600, border: '1.5px solid var(--color-border)', cursor: 'pointer', background: 'var(--color-surface, #fff)', color: 'var(--color-text-secondary)', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                        <Plus size={14} /> Add Job Card
                    </button>
                )}
            </div>

            {showForm && (
                <div style={{ background: 'var(--color-surface, #fff)', border: '1px solid var(--color-border)', borderRadius: '12px', padding: '20px', marginBottom: '16px' }}>
                    <form onSubmit={handleCreate} style={{ display: 'grid', gridTemplateColumns: 'auto 1fr 1fr 1fr 1fr auto', gap: '12px', alignItems: 'end' }}>
                        <div>
                            <label style={labelStyle}>Seq #</label>
                            <input type="number" value={form.sequence} onChange={e => setForm({ ...form, sequence: e.target.value })} required style={{ ...inputStyle, width: '70px' }} />
                        </div>
                        <div>
                            <label style={labelStyle}>Operation Name</label>
                            <input value={form.operation_name} onChange={e => setForm({ ...form, operation_name: e.target.value })} required style={inputStyle} />
                        </div>
                        <div>
                            <label style={labelStyle}>Work Center</label>
                            <select value={form.work_center} onChange={e => setForm({ ...form, work_center: e.target.value })} required style={inputStyle}>
                                <option value="">Select...</option>
                                {workCenters.map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
                            </select>
                        </div>
                        <div>
                            <label style={labelStyle}>Planned Time (hrs)</label>
                            <input type="number" step="0.1" value={form.time_planned} onChange={e => setForm({ ...form, time_planned: e.target.value })} required style={inputStyle} />
                        </div>
                        <div>
                            <label style={labelStyle}>Operator</label>
                            <select value={form.operator} onChange={e => setForm({ ...form, operator: e.target.value })} style={inputStyle}>
                                <option value="">Unassigned</option>
                                {employees.map((emp: any) => <option key={emp.id} value={emp.id}>{emp.first_name} {emp.last_name}</option>)}
                            </select>
                        </div>
                        <button type="submit" disabled={createCard.isPending} style={{ padding: '9px 18px', borderRadius: '8px', fontSize: '12px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', fontFamily: 'inherit', height: '38px' }}>
                            Add
                        </button>
                    </form>
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '14px' }}>
                {cards.map((card: any) => {
                    const badge = STATUS_BADGE[card.status] || STATUS_BADGE.Pending;
                    return (
                        <div key={card.id} style={{ background: 'var(--color-surface, #fff)', border: '1px solid var(--color-border)', borderRadius: '12px', padding: '18px', borderLeft: `3px solid ${STATUS_BORDER[card.status] || '#94a3b8'}` }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                    <div style={{ width: '30px', height: '30px', borderRadius: '8px', background: 'rgba(25,30,106,0.08)', color: '#191e6a', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '13px', fontWeight: 800 }}>{card.sequence}</div>
                                    <span style={{ padding: '3px 10px', borderRadius: '20px', fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', background: badge.bg, color: badge.color }}>{card.status}</span>
                                </div>
                            </div>
                            <div style={{ fontSize: '14px', fontWeight: 700, marginBottom: '10px' }}>{card.operation_name}</div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', fontSize: '12px' }}>
                                <div><span style={{ fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)' }}>Work Center</span><div style={{ fontWeight: 600 }}>{card.work_center_name || '\u2014'}</div></div>
                                <div><span style={{ fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)' }}>Operator</span><div style={{ fontWeight: 600 }}>{card.operator_name || 'Unassigned'}</div></div>
                                <div><span style={{ fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)' }}>Planned</span><div style={{ fontWeight: 600 }}>{card.time_planned} hrs</div></div>
                                <div><span style={{ fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)' }}>Actual</span><div style={{ fontWeight: 600, color: card.time_actual ? '#10b981' : 'var(--color-text-subtle)' }}>{card.time_actual ? `${card.time_actual} hrs` : '\u2014'}</div></div>
                                {card.labor_cost > 0 && <div><span style={{ fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)' }}>Labor Cost</span><div style={{ fontWeight: 600 }}>${Number(card.labor_cost).toFixed(2)}</div></div>}
                            </div>

                            {card.status === 'Pending' && (
                                <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--color-border)' }}>
                                    <button onClick={() => handleStart(card.id)} style={{ padding: '6px 14px', borderRadius: '6px', fontSize: '11px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                        <Play size={12} /> Start
                                    </button>
                                </div>
                            )}
                            {card.status === 'In Progress' && completeForm?.id !== card.id && (
                                <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--color-border)' }}>
                                    <button onClick={() => setCompleteForm({ id: card.id, time_actual: '', labor_cost: '' })} style={{ padding: '6px 14px', borderRadius: '6px', fontSize: '11px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #059669, #10b981)', color: 'white', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                        <CheckCircle size={12} /> Complete
                                    </button>
                                </div>
                            )}
                            {completeForm?.id === card.id && (
                                <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--color-border)', display: 'flex', gap: '8px', alignItems: 'end' }}>
                                    <div>
                                        <label style={{ fontSize: '10px', fontWeight: 600, color: 'var(--color-text-muted)' }}>Actual Time (hrs)</label>
                                        <input type="number" step="0.1" value={completeForm.time_actual} onChange={e => setCompleteForm({ ...completeForm, time_actual: e.target.value })} style={{ width: '80px', padding: '5px 8px', borderRadius: '6px', border: '2.5px solid var(--color-border)', fontSize: '12px', fontFamily: 'inherit' }} />
                                    </div>
                                    <div>
                                        <label style={{ fontSize: '10px', fontWeight: 600, color: 'var(--color-text-muted)' }}>Labor Cost</label>
                                        <input type="number" step="0.01" value={completeForm.labor_cost} onChange={e => setCompleteForm({ ...completeForm, labor_cost: e.target.value })} style={{ width: '80px', padding: '5px 8px', borderRadius: '6px', border: '2.5px solid var(--color-border)', fontSize: '12px', fontFamily: 'inherit' }} />
                                    </div>
                                    <button onClick={handleComplete} style={{ padding: '5px 12px', borderRadius: '6px', fontSize: '11px', fontWeight: 600, border: 'none', cursor: 'pointer', background: '#10b981', color: 'white', fontFamily: 'inherit' }}>Done</button>
                                    <button onClick={() => setCompleteForm(null)} style={{ padding: '5px 12px', borderRadius: '6px', fontSize: '11px', fontWeight: 600, border: '1px solid var(--color-border)', cursor: 'pointer', background: 'var(--color-surface)', fontFamily: 'inherit' }}>Cancel</button>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
            {cards.length === 0 && (
                <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--color-text-muted)' }}>
                    <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '6px' }}>No job cards yet</div>
                    <div style={{ fontSize: '13px' }}>Add job cards to track manufacturing operations</div>
                </div>
            )}
        </div>
    );
};

export default JobCardsTab;
