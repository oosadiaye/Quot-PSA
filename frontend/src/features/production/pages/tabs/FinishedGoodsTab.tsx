import { useState } from 'react';
import {
    useMaterialReceipts, useCreateMaterialReceipt, usePostMaterialReceiptToGL,
} from '../../hooks/useProduction';
import { useWarehouses } from '../../../inventory/hooks/useInventory';
import logger from '../../../../utils/logger';

interface Props {
    orderId: number;
    order: any;
}

const FinishedGoodsTab = ({ orderId, order }: Props) => {
    const { data: receiptsData } = useMaterialReceipts({ production_order: orderId });
    const { data: warehousesData } = useWarehouses();
    const createReceipt = useCreateMaterialReceipt();
    const postReceiptToGL = usePostMaterialReceiptToGL();

    const [form, setForm] = useState({ quantity_received: '', warehouse: '', receipt_date: new Date().toISOString().split('T')[0], scrap_quantity: '0', notes: '' });
    const [error, setError] = useState('');
    const [glWarning, setGlWarning] = useState('');

    const receipts = receiptsData?.results || receiptsData || [];
    const warehouses = warehousesData?.results || warehousesData || [];

    const totalReceived = receipts.reduce((s: number, r: any) => s + parseFloat(r.quantity_received || 0), 0);
    const totalScrap = receipts.reduce((s: number, r: any) => s + parseFloat(r.scrap_quantity || 0), 0);
    const remaining = parseFloat(order.quantity_planned) - totalReceived;

    const canReceive = ['In Progress', 'Done'].includes(order.status);

    const handleReceive = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setGlWarning('');
        try {
            const scrap = parseFloat(form.scrap_quantity) || 0;
            const result = await createReceipt.mutateAsync({
                production_order: orderId,
                quantity_received: parseFloat(form.quantity_received),
                receipt_date: form.receipt_date,
                is_scrap: scrap > 0,
                scrap_quantity: scrap,
                notes: form.notes,
            });
            try {
                await postReceiptToGL.mutateAsync(result.id);
            } catch (glErr: any) {
                logger.error('GL posting failed for finished goods receipt', glErr);
                setGlWarning('Goods received successfully, but GL posting failed. Please post manually or contact finance.');
            }
            setForm({ quantity_received: '', warehouse: '', receipt_date: new Date().toISOString().split('T')[0], scrap_quantity: '0', notes: '' });
        } catch (err: any) {
            setError(err?.response?.data?.error || err?.message || 'Failed to receive goods');
        }
    };

    const cardStyle: React.CSSProperties = {
        background: 'var(--color-surface, #fff)', border: '1px solid var(--color-border, #e2e8f0)',
        borderRadius: '12px', padding: '20px', marginBottom: '16px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
    };
    const thStyle: React.CSSProperties = {
        padding: '10px 14px', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.5px', color: 'var(--color-text-muted, #64748b)', textAlign: 'left',
        background: 'rgba(15,18,64,0.04)', borderBottom: '1.5px solid var(--color-border, #e2e8f0)',
    };
    const tdStyle: React.CSSProperties = {
        padding: '12px 14px', fontSize: '13px', borderBottom: '1px solid var(--color-border, #e2e8f0)',
    };

    const summaryCards = [
        { label: 'Planned', value: order.quantity_planned, color: '#0f172a' },
        { label: 'Received', value: totalReceived.toFixed(2), color: '#10b981' },
        { label: 'Remaining', value: remaining > 0 ? remaining.toFixed(2) : '0.00', color: '#f59e0b' },
        { label: 'Scrap', value: totalScrap.toFixed(2), color: '#ef4444' },
    ];

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
            {glWarning && (
                <div style={{
                    padding: '10px 16px', borderRadius: '8px', marginBottom: '12px',
                    background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)',
                    color: '#d97706', fontSize: '13px', fontWeight: 500,
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                    <span>{glWarning}</span>
                    <button aria-label="Dismiss warning" onClick={() => setGlWarning('')} style={{ background: 'none', border: 'none', color: '#d97706', cursor: 'pointer', fontWeight: 700, fontSize: '14px' }}><span aria-hidden="true">&times;</span></button>
                </div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '14px', marginBottom: '16px' }}>
                {summaryCards.map(c => (
                    <div key={c.label} style={{ ...cardStyle, textAlign: 'center', marginBottom: 0 }}>
                        <div style={{ fontSize: '24px', fontWeight: 800, color: c.color, letterSpacing: '-0.5px' }}>{c.value}</div>
                        <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginTop: '4px' }}>{c.label}</div>
                    </div>
                ))}
            </div>

            {canReceive && (
                <div style={cardStyle}>
                    <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '14px' }}>+ Receive Finished Goods</h3>
                    <form onSubmit={handleReceive} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto auto auto', gap: '12px', alignItems: 'end' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Quantity Received</label>
                            <input type="number" step="0.01" value={form.quantity_received} onChange={e => setForm({ ...form, quantity_received: e.target.value })} required style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }} />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Warehouse</label>
                            <select value={form.warehouse} onChange={e => setForm({ ...form, warehouse: e.target.value })} style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }}>
                                <option value="">Select warehouse...</option>
                                {warehouses.map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
                            </select>
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Receipt Date</label>
                            <input type="date" value={form.receipt_date} onChange={e => setForm({ ...form, receipt_date: e.target.value })} style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }} />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Scrap Qty</label>
                            <input type="number" step="0.01" value={form.scrap_quantity} onChange={e => setForm({ ...form, scrap_quantity: e.target.value })} style={{ width: '80px', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }} />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Notes</label>
                            <input value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} placeholder="Optional" style={{ width: '120px', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }} />
                        </div>
                        <button type="submit" disabled={createReceipt.isPending} style={{ padding: '9px 18px', borderRadius: '8px', fontSize: '12px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #059669, #10b981)', color: 'white', fontFamily: 'inherit', height: '38px' }}>
                            {createReceipt.isPending ? 'Receiving...' : 'Receive'}
                        </button>
                    </form>
                </div>
            )}

            <div style={cardStyle}>
                <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '14px' }}>Receipt History</h3>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            <th style={thStyle}>Date</th>
                            <th style={thStyle}>Qty Received</th>
                            <th style={thStyle}>Scrap</th>
                            <th style={thStyle}>Notes</th>
                        </tr>
                    </thead>
                    <tbody>
                        {receipts.map((r: any) => (
                            <tr key={r.id}>
                                <td style={tdStyle}>{r.receipt_date}</td>
                                <td style={{ ...tdStyle, fontWeight: 600 }}>{Number(r.quantity_received).toFixed(2)}</td>
                                <td style={tdStyle}>{Number(r.scrap_quantity || 0).toFixed(2)}</td>
                                <td style={{ ...tdStyle, color: 'var(--color-text-muted)', fontSize: '12px' }}>{r.notes || '\u2014'}</td>
                            </tr>
                        ))}
                        {receipts.length === 0 && (
                            <tr><td colSpan={4} style={{ ...tdStyle, textAlign: 'center', color: 'var(--color-text-muted)' }}>No finished goods received yet</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default FinishedGoodsTab;
