import { useState } from 'react';
import { useBatches, useWarehouses, useSplitBatch, useTransferBatch } from '../../../inventory/hooks/useInventory';
import { useMaterialReceipts, useMaterialIssues } from '../../hooks/useProduction';

interface Props {
    orderId: number;
    order: any;
}

const BatchesTab = ({ orderId, order }: Props) => {
    const { data: batchesData } = useBatches();
    const { data: receiptsData } = useMaterialReceipts({ production_order: orderId });
    const { data: issuesData } = useMaterialIssues({ production_order: orderId });
    const { data: warehousesData } = useWarehouses();
    const splitBatch = useSplitBatch();
    const transferBatch = useTransferBatch();

    const [splitModal, setSplitModal] = useState<any>(null);
    const [transferModal, setTransferModal] = useState<any>(null);
    const [splitQty, setSplitQty] = useState('');
    const [transferQty, setTransferQty] = useState('');
    const [targetWarehouse, setTargetWarehouse] = useState('');
    const [error, setError] = useState('');

    const allBatches = batchesData?.results || batchesData || [];
    const warehouses = warehousesData?.results || warehousesData || [];
    const issues = issuesData?.results || issuesData || [];

    const orderBatches = allBatches.filter((b: any) =>
        b.reference_number?.includes(order.order_number) || b.batch_number?.includes(order.order_number)
    );

    const handleSplit = async () => {
        if (!splitModal || !splitQty) return;
        setError('');
        try {
            await splitBatch.mutateAsync({ id: splitModal.id, split_quantity: parseFloat(splitQty) });
            setSplitModal(null);
            setSplitQty('');
        } catch (err: any) {
            setError(err?.response?.data?.error || err?.message || 'Failed to split batch');
        }
    };

    const handleTransfer = async () => {
        if (!transferModal || !transferQty || !targetWarehouse) return;
        setError('');
        try {
            await transferBatch.mutateAsync({ id: transferModal.id, to_warehouse: parseInt(targetWarehouse), transfer_quantity: parseFloat(transferQty) });
            setTransferModal(null);
            setTransferQty('');
            setTargetWarehouse('');
        } catch (err: any) {
            setError(err?.response?.data?.error || err?.message || 'Failed to transfer batch');
        }
    };

    const cardStyle: React.CSSProperties = {
        background: 'var(--color-surface, #fff)', border: '1px solid var(--color-border, #e2e8f0)',
        borderRadius: '12px', overflow: 'hidden', marginBottom: '16px',
    };
    const headerStyle: React.CSSProperties = {
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '16px 20px', borderBottom: '1px solid var(--color-border)', background: 'rgba(15,18,64,0.02)',
    };
    const thStyle: React.CSSProperties = {
        padding: '10px 14px', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.5px', color: 'var(--color-text-muted)', textAlign: 'left',
        background: 'rgba(15,18,64,0.04)', borderBottom: '1.5px solid var(--color-border)',
    };
    const tdStyle: React.CSSProperties = {
        padding: '12px 14px', fontSize: '13px', borderBottom: '1px solid var(--color-border)',
    };
    const btnStyle: React.CSSProperties = {
        padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: 600,
        cursor: 'pointer', border: '1.5px solid var(--color-border)', background: 'var(--color-surface)',
        color: 'var(--color-text-secondary)', fontFamily: 'inherit',
    };
    const modalOverlay: React.CSSProperties = {
        position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.55)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', zIndex: 9999, backdropFilter: 'blur(2px)',
    };
    const modalBox: React.CSSProperties = {
        background: 'white', borderRadius: '16px', padding: '28px', maxWidth: '420px', width: '90%',
        boxShadow: '0 24px 64px rgba(0,0,0,0.25)',
    };
    const inputStyle: React.CSSProperties = {
        width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2.5px solid var(--color-border)',
        fontSize: '13px', fontFamily: 'inherit', background: '#f8fafc',
    };

    const expiryBadge = (date: string) => {
        if (!date) return null;
        const days = Math.ceil((new Date(date).getTime() - Date.now()) / 86400000);
        const color = days <= 0 ? '#ef4444' : days <= 30 ? '#f59e0b' : '#10b981';
        const bg = days <= 0 ? 'rgba(239,68,68,0.1)' : days <= 30 ? 'rgba(245,158,11,0.1)' : 'rgba(16,185,129,0.1)';
        return <span style={{ padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600, background: bg, color }}>{date}</span>;
    };

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
            <div style={cardStyle}>
                <div style={headerStyle}>
                    <h3 style={{ fontSize: '14px', fontWeight: 700 }}>Batches Created by This Order</h3>
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            <th style={thStyle}>Batch #</th>
                            <th style={thStyle}>Item</th>
                            <th style={thStyle}>Warehouse</th>
                            <th style={thStyle}>Original</th>
                            <th style={thStyle}>Remaining</th>
                            <th style={thStyle}>Unit Cost</th>
                            <th style={thStyle}>Received</th>
                            <th style={thStyle}>Expiry</th>
                            <th style={thStyle}>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {orderBatches.map((b: any) => (
                            <tr key={b.id}>
                                <td style={{ ...tdStyle, fontWeight: 700, color: '#191e6a' }}>{b.batch_number}</td>
                                <td style={tdStyle}>{b.item_name}</td>
                                <td style={tdStyle}>{b.warehouse_name}</td>
                                <td style={tdStyle}>{Number(b.quantity).toFixed(2)}</td>
                                <td style={tdStyle}>{Number(b.remaining_quantity).toFixed(2)}</td>
                                <td style={tdStyle}>${Number(b.unit_cost).toFixed(2)}</td>
                                <td style={tdStyle}>{b.receipt_date}</td>
                                <td style={tdStyle}>{expiryBadge(b.expiry_date)}</td>
                                <td style={tdStyle}>
                                    <div style={{ display: 'flex', gap: '4px' }}>
                                        <button style={btnStyle} onClick={() => setSplitModal(b)}>Split</button>
                                        <button style={btnStyle} onClick={() => setTransferModal(b)}>Transfer</button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                        {orderBatches.length === 0 && (
                            <tr><td colSpan={9} style={{ ...tdStyle, textAlign: 'center', color: 'var(--color-text-muted)' }}>No batches created yet — receive finished goods to create batches</td></tr>
                        )}
                    </tbody>
                </table>
            </div>

            {/* Source Batches Consumed */}
            <div style={cardStyle}>
                <div style={headerStyle}>
                    <h3 style={{ fontSize: '14px', fontWeight: 700 }}>Source Batches Consumed</h3>
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            <th style={thStyle}>Component</th>
                            <th style={thStyle}>Qty Used</th>
                            <th style={thStyle}>Issue Date</th>
                            <th style={thStyle}>Notes</th>
                        </tr>
                    </thead>
                    <tbody>
                        {issues.map((iss: any) => (
                            <tr key={iss.id}>
                                <td style={{ ...tdStyle, fontWeight: 600 }}>Line #{iss.bom_line}</td>
                                <td style={tdStyle}>{Number(iss.quantity_issued).toFixed(2)}</td>
                                <td style={tdStyle}>{iss.issue_date}</td>
                                <td style={{ ...tdStyle, color: 'var(--color-text-muted)', fontSize: '12px' }}>{iss.notes || '\u2014'}</td>
                            </tr>
                        ))}
                        {issues.length === 0 && (
                            <tr><td colSpan={4} style={{ ...tdStyle, textAlign: 'center', color: 'var(--color-text-muted)' }}>No materials consumed yet</td></tr>
                        )}
                    </tbody>
                </table>
            </div>

            {splitModal && (
                <div style={modalOverlay} onClick={() => setSplitModal(null)}>
                    <div role="dialog" aria-modal="true" aria-labelledby="split-batch-dialog-title" style={modalBox} onClick={e => e.stopPropagation()}>
                        <h3 id="split-batch-dialog-title" style={{ fontSize: '16px', fontWeight: 700, marginBottom: '16px' }}>Split Batch</h3>
                        <p style={{ fontSize: '13px', color: 'var(--color-text-secondary)', marginBottom: '16px' }}>
                            Splitting <strong>{splitModal.batch_number}</strong> (remaining: {Number(splitModal.remaining_quantity).toFixed(2)})
                        </p>
                        <div style={{ marginBottom: '16px' }}>
                            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>Split Quantity</label>
                            <input type="number" step="0.01" value={splitQty} onChange={e => setSplitQty(e.target.value)} placeholder="Enter quantity to split off" style={inputStyle} />
                        </div>
                        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                            <button onClick={() => setSplitModal(null)} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: '1px solid var(--color-border)', cursor: 'pointer', background: '#f8fafc', color: 'var(--color-text-secondary)', fontFamily: 'inherit' }}>Cancel</button>
                            <button onClick={handleSplit} disabled={splitBatch.isPending} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', fontFamily: 'inherit' }}>
                                {splitBatch.isPending ? 'Splitting...' : 'Split'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {transferModal && (
                <div style={modalOverlay} onClick={() => setTransferModal(null)}>
                    <div role="dialog" aria-modal="true" aria-labelledby="transfer-batch-dialog-title" style={modalBox} onClick={e => e.stopPropagation()}>
                        <h3 id="transfer-batch-dialog-title" style={{ fontSize: '16px', fontWeight: 700, marginBottom: '16px' }}>Transfer Batch</h3>
                        <p style={{ fontSize: '13px', color: 'var(--color-text-secondary)', marginBottom: '16px' }}>
                            Transferring from <strong>{transferModal.batch_number}</strong> (remaining: {Number(transferModal.remaining_quantity).toFixed(2)})
                        </p>
                        <div style={{ marginBottom: '12px' }}>
                            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>Target Warehouse</label>
                            <select value={targetWarehouse} onChange={e => setTargetWarehouse(e.target.value)} style={inputStyle}>
                                <option value="">Select warehouse...</option>
                                {warehouses.filter((w: any) => w.id !== transferModal.warehouse).map((w: any) => (
                                    <option key={w.id} value={w.id}>{w.name}</option>
                                ))}
                            </select>
                        </div>
                        <div style={{ marginBottom: '16px' }}>
                            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>Transfer Quantity</label>
                            <input type="number" step="0.01" value={transferQty} onChange={e => setTransferQty(e.target.value)} placeholder="Enter quantity" style={inputStyle} />
                        </div>
                        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                            <button onClick={() => setTransferModal(null)} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: '1px solid var(--color-border)', cursor: 'pointer', background: '#f8fafc', color: 'var(--color-text-secondary)', fontFamily: 'inherit' }}>Cancel</button>
                            <button onClick={handleTransfer} disabled={transferBatch.isPending} style={{ padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', fontFamily: 'inherit' }}>
                                {transferBatch.isPending ? 'Transferring...' : 'Transfer'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default BatchesTab;
