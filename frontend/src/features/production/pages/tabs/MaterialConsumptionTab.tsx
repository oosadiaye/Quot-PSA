import { useState } from 'react';
import {
    useMaterialRequirements, useMaterialIssues,
    useCreateMaterialIssue, usePostMaterialIssueToGL,
    useBackflushMaterials,
} from '../../hooks/useProduction';
import { useWarehouses, useBatches } from '../../../inventory/hooks/useInventory';
import { Zap } from 'lucide-react';
import logger from '../../../../utils/logger';

interface Props {
    orderId: number;
    order: any;
}

const MaterialConsumptionTab = ({ orderId, order }: Props) => {
    const { data: requirements } = useMaterialRequirements(orderId);
    const { data: issuesData } = useMaterialIssues({ production_order: orderId });
    const { data: warehousesData } = useWarehouses();
    const { data: batchesData } = useBatches();
    const createIssue = useCreateMaterialIssue();
    const postIssueToGL = usePostMaterialIssueToGL();
    const backflush = useBackflushMaterials();

    const [issueForm, setIssueForm] = useState({ bom_line: '', quantity: '', warehouse: '', source_batch: '', notes: '' });
    const [backflushWarehouse, setBackflushWarehouse] = useState('');
    const [error, setError] = useState('');
    const [glWarning, setGlWarning] = useState('');

    const issues = issuesData?.results || issuesData || [];
    const warehouses = warehousesData?.results || warehousesData || [];
    const reqs = Array.isArray(requirements) ? requirements : [];
    const allBatches = batchesData?.results || batchesData || [];

    const issuedByLine: Record<number, number> = {};
    issues.forEach((iss: any) => {
        issuedByLine[iss.bom_line] = (issuedByLine[iss.bom_line] || 0) + parseFloat(iss.quantity_issued || 0);
    });

    const isInProgress = order.status === 'In Progress';
    const hasRemaining = reqs.some((r: any) => {
        const issued = issuedByLine[r.bom_line_id] || 0;
        return r.required_quantity - issued > 0;
    });

    const handleIssue = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setGlWarning('');
        try {
            const result = await createIssue.mutateAsync({
                production_order: orderId,
                bom_line: parseInt(issueForm.bom_line),
                quantity_issued: parseFloat(issueForm.quantity),
                issue_date: new Date().toISOString().split('T')[0],
                notes: issueForm.notes,
            });
            try {
                await postIssueToGL.mutateAsync(result.id);
            } catch (glErr: any) {
                logger.error('GL posting failed for material issue', glErr);
                setGlWarning('Material issued successfully, but GL posting failed. Please post manually or contact finance.');
            }
            setIssueForm({ bom_line: '', quantity: '', warehouse: '', source_batch: '', notes: '' });
        } catch (err: any) {
            setError(err?.response?.data?.error || err?.message || 'Failed to issue material');
        }
    };

    const handleBackflush = async () => {
        if (!backflushWarehouse) return;
        setError('');
        try {
            await backflush.mutateAsync({ orderId, warehouse: parseInt(backflushWarehouse) });
        } catch (err: any) {
            setError(err?.response?.data?.error || err?.message || 'Backflush failed');
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
    const badgeStyle = (color: string, bg: string): React.CSSProperties => ({
        display: 'inline-flex', padding: '3px 10px', borderRadius: '6px',
        fontSize: '11px', fontWeight: 600, background: bg, color,
    });

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
            {isInProgress && hasRemaining && (
                <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '14px 18px', borderRadius: '10px',
                    background: 'rgba(25,30,106,0.04)', border: '1px solid rgba(25,30,106,0.1)',
                    marginBottom: '16px',
                }}>
                    <span style={{ fontSize: '13px', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Zap size={14} /> <strong>Quick Action:</strong> Issue all remaining BOM materials
                    </span>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <select value={backflushWarehouse} onChange={e => setBackflushWarehouse(e.target.value)} style={{ padding: '7px 12px', borderRadius: '6px', border: '2px solid var(--color-border)', fontSize: '12px', fontFamily: 'inherit' }}>
                            <option value="">Select warehouse...</option>
                            {warehouses.map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
                        </select>
                        <button onClick={handleBackflush} disabled={!backflushWarehouse || backflush.isPending} style={{
                            padding: '7px 18px', borderRadius: '6px', fontSize: '12px', fontWeight: 600,
                            border: 'none', cursor: 'pointer', fontFamily: 'inherit',
                            background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white',
                            opacity: !backflushWarehouse ? 0.5 : 1,
                        }}>
                            {backflush.isPending ? 'Issuing...' : 'Issue All Materials (Backflush)'}
                        </button>
                    </div>
                </div>
            )}

            <div style={cardStyle}>
                <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '14px' }}>Material Requirements vs Issued</h3>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            <th style={thStyle}>Component</th>
                            <th style={thStyle}>Code</th>
                            <th style={thStyle}>Required</th>
                            <th style={thStyle}>Issued</th>
                            <th style={thStyle}>Remaining</th>
                            <th style={thStyle}>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {reqs.map((r: any) => {
                            const issued = issuedByLine[r.bom_line_id] || 0;
                            const remaining = r.required_quantity - issued;
                            const isFull = remaining <= 0;
                            const isPartial = issued > 0 && remaining > 0;
                            return (
                                <tr key={r.bom_line_id}>
                                    <td style={{ ...tdStyle, fontWeight: 600 }}>{r.component_name}</td>
                                    <td style={{ ...tdStyle, color: 'var(--color-text-muted)', fontSize: '12px' }}>{r.component_code}</td>
                                    <td style={tdStyle}>{Number(r.required_quantity).toFixed(2)}</td>
                                    <td style={tdStyle}>{issued.toFixed(2)}</td>
                                    <td style={tdStyle}>{remaining > 0 ? remaining.toFixed(2) : '0.00'}</td>
                                    <td style={tdStyle}>
                                        {isFull && <span style={badgeStyle('#10b981', 'rgba(16,185,129,0.1)')}>Fully Issued</span>}
                                        {isPartial && <span style={badgeStyle('#f59e0b', 'rgba(245,158,11,0.1)')}>Partial</span>}
                                        {!isFull && !isPartial && <span style={badgeStyle('#64748b', 'rgba(100,116,139,0.1)')}>Not Issued</span>}
                                    </td>
                                </tr>
                            );
                        })}
                        {reqs.length === 0 && (
                            <tr><td colSpan={6} style={{ ...tdStyle, textAlign: 'center', color: 'var(--color-text-muted)' }}>No BOM lines found</td></tr>
                        )}
                    </tbody>
                </table>
            </div>

            {isInProgress && (
                <div style={cardStyle}>
                    <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '14px' }}>+ Manual Material Issue</h3>
                    <form onSubmit={handleIssue} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr auto', gap: '12px', alignItems: 'end' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Component</label>
                            <select value={issueForm.bom_line} onChange={e => {
                                const selectedId = parseInt(e.target.value);
                                const req = reqs.find((r: any) => r.bom_line_id === selectedId);
                                const issued = issuedByLine[selectedId] || 0;
                                const remaining = req ? (req.required_quantity - issued) : 0;
                                setIssueForm({ ...issueForm, bom_line: e.target.value, quantity: remaining > 0 ? remaining.toFixed(2) : '' });
                            }} required style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }}>
                                <option value="">Select component...</option>
                                {reqs.filter((r: any) => (r.required_quantity - (issuedByLine[r.bom_line_id] || 0)) > 0).map((r: any) => (
                                    <option key={r.bom_line_id} value={r.bom_line_id}>{r.component_code} — {r.component_name}</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Quantity</label>
                            <input type="number" step="0.01" value={issueForm.quantity} onChange={e => setIssueForm({ ...issueForm, quantity: e.target.value })} required style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }} />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Warehouse</label>
                            <select value={issueForm.warehouse} onChange={e => setIssueForm({ ...issueForm, warehouse: e.target.value })} style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }}>
                                <option value="">Select warehouse...</option>
                                {warehouses.map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
                            </select>
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '6px' }}>Source Batch</label>
                            <select value={issueForm.source_batch} onChange={e => setIssueForm({ ...issueForm, source_batch: e.target.value })} style={{ width: '100%', padding: '9px 14px', borderRadius: '8px', border: '2px solid var(--color-border)', fontSize: '13px', fontFamily: 'inherit', background: 'var(--color-surface-hover, #f8fafc)' }}>
                                <option value="">Auto (FIFO)</option>
                                {allBatches.filter((b: any) => b.remaining_quantity > 0).map((b: any) => (
                                    <option key={b.id} value={b.id}>{b.batch_number} (qty: {Number(b.remaining_quantity).toFixed(0)})</option>
                                ))}
                            </select>
                        </div>
                        <button type="submit" disabled={createIssue.isPending} style={{ padding: '9px 18px', borderRadius: '8px', fontSize: '12px', fontWeight: 600, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white', fontFamily: 'inherit', height: '38px' }}>
                            {createIssue.isPending ? 'Issuing...' : 'Issue'}
                        </button>
                    </form>
                </div>
            )}

            <div style={cardStyle}>
                <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '14px' }}>Issue History</h3>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            <th style={thStyle}>Date</th>
                            <th style={thStyle}>Component</th>
                            <th style={thStyle}>Qty Issued</th>
                            <th style={thStyle}>Notes</th>
                        </tr>
                    </thead>
                    <tbody>
                        {issues.map((iss: any) => (
                            <tr key={iss.id}>
                                <td style={tdStyle}>{iss.issue_date}</td>
                                <td style={{ ...tdStyle, fontWeight: 600 }}>
                                    {reqs.find((r: any) => r.bom_line_id === iss.bom_line)?.component_name || `Line #${iss.bom_line}`}
                                </td>
                                <td style={tdStyle}>{Number(iss.quantity_issued).toFixed(2)}</td>
                                <td style={{ ...tdStyle, color: 'var(--color-text-muted)', fontSize: '12px' }}>{iss.notes || '\u2014'}</td>
                            </tr>
                        ))}
                        {issues.length === 0 && (
                            <tr><td colSpan={4} style={{ ...tdStyle, textAlign: 'center', color: 'var(--color-text-muted)' }}>No materials issued yet</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default MaterialConsumptionTab;
