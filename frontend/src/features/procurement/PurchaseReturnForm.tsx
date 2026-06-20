import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    RotateCcw, AlertTriangle, CheckCircle2, Undo2, Save, X,
} from 'lucide-react';
import {
    useCreatePurchaseReturn,
    usePurchaseOrders,
    usePurchaseOrder,
    useGRNsForPO,
    useGRN,
} from './hooks/useProcurement';
import { useCurrency } from '../../context/CurrencyContext';
import { safeAdd, safeMultiply } from '../accounting/utils/currency';
import AccountingLayout from '../accounting/AccountingLayout';
import PageHeader from '../../components/PageHeader';
import '../accounting/styles/glassmorphism.css';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────
interface ReturnLine {
    po_line_id: number;
    item_id: number | null;
    item_description: string;
    received_qty: number;
    unit_price: number;
    qty_to_return: string;
    line_reason: string;
    /** True when the user has entered more than received — row turns red */
    over_qty: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────
const PurchaseReturnForm: React.FC = () => {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const createReturn = useCreatePurchaseReturn();

    // ── PO selection ──────────────────────────────────────────────────────────
    // Returns can be raised against Posted or Closed POs only (goods already
    // received and invoiced). Fetch a wide page and client-filter.
    const { data: posData } = usePurchaseOrders({ page_size: 200 });
    const allPos = posData?.results || posData || [];
    const posList = Array.isArray(allPos)
        ? allPos.filter((po: any) => ['Posted', 'Closed'].includes(po.status))
        : [];

    const [selectedPOId, setSelectedPOId] = useState<number | null>(null);
    const { data: selectedPO } = usePurchaseOrder(selectedPOId);

    // ── GRN selection (cascade from PO) ───────────────────────────────────────
    const { data: grnsForPO, isLoading: grnsLoading } = useGRNsForPO(selectedPOId);
    const postedGRNs = Array.isArray(grnsForPO)
        ? grnsForPO.filter((g: any) => g.status === 'Posted')
        : [];

    const [selectedGRNId, setSelectedGRNId] = useState<number | null>(null);
    const { data: selectedGRN, isLoading: grnLoading } = useGRN(selectedGRNId);

    // ── Header fields ─────────────────────────────────────────────────────────
    const [header, setHeader] = useState({
        return_date: new Date().toISOString().split('T')[0],
        reason: '',
        notes: '',
    });

    // ── Return lines (populated from GRN) ─────────────────────────────────────
    const [lines, setLines] = useState<ReturnLine[]>([]);
    const [formError, setFormError] = useState('');

    // When GRN is selected, build lines from its lines array
    useEffect(() => {
        if (selectedGRN?.lines) {
            setLines(
                selectedGRN.lines.map((gl: any) => ({
                    po_line_id: gl.po_line,
                    item_id: gl.item ?? null,
                    // item_description and po_line_item both come from po_line.item_description
                    // (GoodsReceivedNoteLine has no own item_description column since migration 0005).
                    item_description: gl.item_description || gl.po_line_item || '',
                    received_qty: parseFloat(gl.quantity_received || '0'),
                    unit_price: parseFloat(gl.unit_price || '0'),
                    qty_to_return: '',
                    line_reason: '',
                    over_qty: false,
                })),
            );
        } else {
            setLines([]);
        }
    }, [selectedGRN]);

    // Reset GRN when PO changes
    useEffect(() => {
        setSelectedGRNId(null);
        setLines([]);
    }, [selectedPOId]);

    // ── Line handlers ─────────────────────────────────────────────────────────
    const updateLine = (index: number, field: keyof ReturnLine, value: string) => {
        setLines(prev =>
            prev.map((l, i) => {
                if (i !== index) return l;
                const updated = { ...l, [field]: value };
                if (field === 'qty_to_return') {
                    const qty = parseFloat(value) || 0;
                    updated.over_qty = qty > l.received_qty;
                }
                return updated;
            }),
        );
    };

    // ── Derived state ─────────────────────────────────────────────────────────
    const totalReturnValue = useMemo(() => {
        return lines.reduce(
            (sum, l) => safeAdd(sum, safeMultiply(l.qty_to_return || '0', l.unit_price)),
            0,
        );
    }, [lines]);

    const linesWithQty = lines.filter(l => parseFloat(l.qty_to_return) > 0);
    const anyLineOverQty = lines.some(l => l.over_qty);
    const hasValidLines = linesWithQty.length > 0 && !anyLineOverQty;

    // ── Submit ────────────────────────────────────────────────────────────────
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        if (!selectedPOId) { setFormError('Please select a Purchase Order.'); return; }
        if (!selectedGRNId) { setFormError('Please select a Goods Received Note.'); return; }
        if (!hasValidLines) {
            setFormError('Enter at least one return quantity and ensure no quantities exceed what was received.');
            return;
        }

        const payload = {
            purchase_order: selectedPOId,
            goods_received_note: selectedGRNId,
            return_date: header.return_date,
            reason: header.reason,
            notes: header.notes,
            lines: linesWithQty.map(l => ({
                po_line: l.po_line_id,
                item: l.item_id || undefined,
                item_description: l.item_description,
                quantity: parseFloat(l.qty_to_return),
                unit_price: l.unit_price,
                reason: l.line_reason || undefined,
            })),
        };

        try {
            await createReturn.mutateAsync(payload);
            navigate('/procurement/returns');
        } catch (err: any) {
            const msg =
                err?.response?.data?.detail ||
                err?.response?.data?.lines?.[0] ||
                'Failed to create purchase return. Please check the form and try again.';
            setFormError(typeof msg === 'string' ? msg : JSON.stringify(msg));
        }
    };

    // ─────────────────────────────────────────────────────────────────────────
    // Render helpers
    // ─────────────────────────────────────────────────────────────────────────
    const labelStyle: React.CSSProperties = {
        display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)',
        fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)',
    };
    const helpStyle: React.CSSProperties = {
        fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px',
    };

    // ─────────────────────────────────────────────────────────────────────────
    // Return summary state
    // ─────────────────────────────────────────────────────────────────────────
    const summaryColor = hasValidLines
        ? 'rgba(34, 197, 94, 0.1)'
        : anyLineOverQty
            ? 'rgba(239, 68, 68, 0.1)'
            : 'var(--color-surface-elevated, var(--color-surface))';

    const summaryBorder = hasValidLines
        ? '1px solid rgba(34, 197, 94, 0.3)'
        : anyLineOverQty
            ? '1px solid rgba(239, 68, 68, 0.3)'
            : '1px solid var(--color-border)';

    return (
        <AccountingLayout>
            <div style={{ padding: '1.5rem', maxWidth: '1200px', margin: '0 auto' }}>
                <form onSubmit={handleSubmit}>
                    {/* ── Page header ──────────────────────────────────────────────── */}
                    <PageHeader
                        title="New Purchase Return"
                        subtitle="Return goods to vendor against a posted GRN"
                        icon={<Undo2 size={22} />}
                        onBack={() => navigate('/procurement/returns')}
                        actions={
                            <>
                                <button type="button" className="btn btn-outline" onClick={() => navigate('/procurement/returns')}>
                                    <X size={18} /> Cancel
                                </button>
                                <button type="submit" className="btn btn-primary" disabled={createReturn.isPending || !hasValidLines}>
                                    <Save size={18} /> {createReturn.isPending ? 'Saving...' : 'Save as Draft'}
                                </button>
                            </>
                        }
                    />

                    {formError && (
                        <div style={{ padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626', borderRadius: '8px', marginBottom: '1rem' }}>
                            {formError}
                        </div>
                    )}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '1.25rem', alignItems: 'start' }}>

                        {/* ── LEFT COLUMN ──────────────────────────────────────── */}
                        <div>
                            {/* ── Section 1: PO + GRN Selection ──────────────── */}
                            <div className="card" style={{ marginBottom: '1.5rem' }}>
                                <h3 style={{ marginBottom: '1.5rem' }}>Source Document</h3>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                                    <div>
                                        <label style={labelStyle}>
                                            Purchase Order<span className="required-mark"> *</span>
                                        </label>
                                        <select
                                            className="input"
                                            required
                                            value={selectedPOId ?? ''}
                                            onChange={e => setSelectedPOId(e.target.value ? Number(e.target.value) : null)}
                                        >
                                            <option value="">— Select PO —</option>
                                            {posList.map((po: any) => (
                                                <option key={po.id} value={po.id}>
                                                    {po.po_number} — {po.vendor_name} [{po.status}]
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>
                                            Goods Received Note<span className="required-mark"> *</span>
                                        </label>
                                        <select
                                            className="input"
                                            required
                                            value={selectedGRNId ?? ''}
                                            onChange={e => setSelectedGRNId(e.target.value ? Number(e.target.value) : null)}
                                            disabled={!selectedPOId || grnsLoading}
                                            style={{
                                                opacity: !selectedPOId ? 0.5 : 1,
                                                cursor: !selectedPOId ? 'not-allowed' : 'pointer',
                                            }}
                                        >
                                            <option value="">
                                                {!selectedPOId
                                                    ? '— Select PO first —'
                                                    : grnsLoading
                                                        ? 'Loading GRNs…'
                                                        : postedGRNs.length === 0
                                                            ? 'No posted GRNs found'
                                                            : '— Select GRN —'}
                                            </option>
                                            {postedGRNs.map((g: any) => (
                                                <option key={g.id} value={g.id}>
                                                    {g.grn_number} — {new Date(g.received_date).toLocaleDateString()}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                </div>

                                {/* Vendor info chip */}
                                {selectedPO && (
                                    <div style={{
                                        marginTop: '1rem',
                                        padding: '0.625rem 1rem',
                                        background: 'rgba(36, 113, 163, 0.06)',
                                        borderRadius: '8px',
                                        border: '1px solid rgba(36, 113, 163, 0.15)',
                                        display: 'flex',
                                        gap: '2rem',
                                    }}>
                                        <div>
                                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Vendor</div>
                                            <div style={{ fontWeight: 600, color: 'var(--color-text)', marginTop: '0.125rem' }}>{selectedPO.vendor_name}</div>
                                        </div>
                                        <div>
                                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>PO Status</div>
                                            <div style={{ fontWeight: 600, color: 'var(--color-text)', marginTop: '0.125rem' }}>{selectedPO.status}</div>
                                        </div>
                                        <div>
                                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>PO Total</div>
                                            <div style={{ fontWeight: 600, color: 'var(--color-text)', marginTop: '0.125rem' }}>{formatCurrency(selectedPO.total_amount)}</div>
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* ── Section 2: Header Details ───────────────────── */}
                            <div className="card" style={{ marginBottom: '1.5rem' }}>
                                <h3 style={{ marginBottom: '1.5rem' }}>Return Details</h3>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '1.5rem' }}>
                                    <div>
                                        <label style={labelStyle}>
                                            Return Date<span className="required-mark"> *</span>
                                        </label>
                                        <input
                                            type="date"
                                            className="input"
                                            required
                                            value={header.return_date}
                                            onChange={e => setHeader({ ...header, return_date: e.target.value })}
                                        />
                                    </div>
                                </div>
                                <div style={{ marginBottom: '1.5rem' }}>
                                    <label style={labelStyle}>
                                        Return Reason<span className="required-mark"> *</span>
                                    </label>
                                    <textarea
                                        className="input"
                                        required
                                        rows={2}
                                        placeholder="Describe the reason for the return (e.g. damaged goods, wrong items, quality issue)"
                                        value={header.reason}
                                        onChange={e => setHeader({ ...header, reason: e.target.value })}
                                        style={{ resize: 'vertical' }}
                                    />
                                </div>
                                <div>
                                    <label style={labelStyle}>Internal Notes</label>
                                    <textarea
                                        className="input"
                                        rows={2}
                                        placeholder="Optional internal notes"
                                        value={header.notes}
                                        onChange={e => setHeader({ ...header, notes: e.target.value })}
                                        style={{ resize: 'vertical' }}
                                    />
                                    <p style={helpStyle}>Optional</p>
                                </div>
                            </div>

                            {/* ── Section 3: Return Lines ─────────────────────── */}
                            <div className="card" style={{ marginBottom: '1.5rem' }}>
                                <div style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    marginBottom: '1.5rem',
                                }}>
                                    <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        Return Lines
                                        {linesWithQty.length > 0 && (
                                            <span style={{
                                                padding: '0.125rem 0.5rem',
                                                background: 'rgba(36, 113, 163, 0.1)',
                                                color: '#2471a3',
                                                borderRadius: '9999px',
                                                fontSize: 'var(--text-xs)',
                                                fontWeight: 700,
                                            }}>
                                                {linesWithQty.length} line{linesWithQty.length !== 1 ? 's' : ''} selected
                                            </span>
                                        )}
                                    </h3>
                                    {selectedGRNId && grnLoading && (
                                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>Loading lines…</span>
                                    )}
                                </div>

                                {lines.length === 0 ? (
                                    <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <RotateCcw size={40} style={{ margin: '0 auto 1rem', opacity: 0.3, display: 'block' }} />
                                        <p style={{ margin: 0, fontSize: 'var(--text-sm)' }}>
                                            {!selectedGRNId ? 'Select a GRN to load return lines.' : 'No lines found on the selected GRN.'}
                                        </p>
                                    </div>
                                ) : (
                                    <div style={{ overflowX: 'auto' }}>
                                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                            <thead>
                                                <tr style={{ background: 'var(--color-surface-elevated, rgba(0,0,0,0.03))' }}>
                                                    {['Item / Description', 'Received Qty', 'Unit Price', 'Qty to Return', 'Line Reason'].map(h => (
                                                        <th key={h} style={{
                                                            padding: '0.625rem 1rem',
                                                            textAlign: h === 'Qty to Return' || h === 'Unit Price' ? 'right' : 'left',
                                                            fontSize: 'var(--text-xs)',
                                                            fontWeight: 700,
                                                            color: 'var(--color-text-muted)',
                                                            textTransform: 'uppercase',
                                                            whiteSpace: 'nowrap',
                                                        }}>{h}</th>
                                                    ))}
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {lines.map((line, idx) => (
                                                    <tr
                                                        key={line.po_line_id ?? idx}
                                                        style={{
                                                            borderTop: '1px solid var(--color-border)',
                                                            background: line.over_qty ? 'rgba(239, 68, 68, 0.06)' : 'transparent',
                                                            transition: 'background 0.15s',
                                                        }}
                                                    >
                                                        {/* Description */}
                                                        <td style={{ padding: '0.75rem 1rem' }}>
                                                            <div style={{ fontWeight: 500, color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                                {line.item_description || '—'}
                                                            </div>
                                                        </td>

                                                        {/* Received qty */}
                                                        <td style={{ padding: '0.75rem 1rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                                            {line.received_qty.toLocaleString()}
                                                        </td>

                                                        {/* Unit price */}
                                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                                            {formatCurrency(line.unit_price)}
                                                        </td>

                                                        {/* Qty to return input */}
                                                        <td style={{ padding: '0.5rem 1rem', textAlign: 'right' }}>
                                                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.25rem' }}>
                                                                <input
                                                                    type="number"
                                                                    min="0"
                                                                    max={line.received_qty}
                                                                    step="0.01"
                                                                    value={line.qty_to_return}
                                                                    onChange={e => updateLine(idx, 'qty_to_return', e.target.value)}
                                                                    placeholder="0"
                                                                    style={{
                                                                        width: '90px',
                                                                        padding: '0.375rem 0.5rem',
                                                                        border: `1px solid ${line.over_qty ? '#ef4444' : 'var(--color-border)'}`,
                                                                        borderRadius: '6px',
                                                                        background: 'var(--color-surface)',
                                                                        color: line.over_qty ? '#ef4444' : 'var(--color-text)',
                                                                        fontSize: 'var(--text-sm)',
                                                                        textAlign: 'right',
                                                                        fontWeight: 600,
                                                                    }}
                                                                />
                                                                {line.over_qty && (
                                                                    <span style={{ fontSize: '10px', color: '#ef4444', display: 'flex', alignItems: 'center', gap: '2px' }}>
                                                                        <AlertTriangle size={10} />
                                                                        Max {line.received_qty}
                                                                    </span>
                                                                )}
                                                            </div>
                                                        </td>

                                                        {/* Per-line reason */}
                                                        <td style={{ padding: '0.5rem 1rem' }}>
                                                            <input
                                                                type="text"
                                                                placeholder="Optional"
                                                                value={line.line_reason}
                                                                onChange={e => updateLine(idx, 'line_reason', e.target.value)}
                                                                style={{
                                                                    width: '100%',
                                                                    minWidth: '140px',
                                                                    padding: '0.375rem 0.5rem',
                                                                    border: '1px solid var(--color-border)',
                                                                    borderRadius: '6px',
                                                                    background: 'var(--color-surface)',
                                                                    color: 'var(--color-text)',
                                                                    fontSize: 'var(--text-sm)',
                                                                }}
                                                            />
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* ── RIGHT COLUMN: Summary ─────────────────────────────── */}
                        <div style={{ position: 'sticky', top: '1.5rem' }}>
                            <div className="card" style={{ background: summaryColor, border: summaryBorder, marginBottom: '1rem' }}>
                                <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '1rem' }}>
                                    Return Summary
                                </div>

                                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem', marginBottom: '1rem' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                        <span>Lines with qty</span>
                                        <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>{linesWithQty.length}</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                        <span>Total qty to return</span>
                                        <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>
                                            {linesWithQty.reduce((s, l) => s + (parseFloat(l.qty_to_return) || 0), 0).toLocaleString()}
                                        </span>
                                    </div>
                                    <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: '0.625rem', display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                        <span style={{ fontWeight: 700 }}>Return Value</span>
                                        <span style={{ fontWeight: 700, color: 'var(--color-text)', fontSize: 'var(--text-base)' }}>
                                            {formatCurrency(totalReturnValue)}
                                        </span>
                                    </div>
                                </div>

                                {/* State indicator */}
                                {anyLineOverQty && (
                                    <div style={{
                                        padding: '0.625rem 0.75rem',
                                        background: 'rgba(239, 68, 68, 0.08)',
                                        borderRadius: '8px',
                                        border: '1px solid rgba(239, 68, 68, 0.2)',
                                        display: 'flex',
                                        gap: '0.5rem',
                                        alignItems: 'flex-start',
                                        fontSize: 'var(--text-xs)',
                                        color: '#ef4444',
                                        marginBottom: '0.75rem',
                                    }}>
                                        <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: '1px' }} />
                                        <span>One or more quantities exceed what was received. Please correct before submitting.</span>
                                    </div>
                                )}
                                {hasValidLines && (
                                    <div style={{
                                        padding: '0.625rem 0.75rem',
                                        background: 'rgba(34, 197, 94, 0.08)',
                                        borderRadius: '8px',
                                        border: '1px solid rgba(34, 197, 94, 0.2)',
                                        display: 'flex',
                                        gap: '0.5rem',
                                        alignItems: 'center',
                                        fontSize: 'var(--text-xs)',
                                        color: '#22c55e',
                                        marginBottom: '0.75rem',
                                    }}>
                                        <CheckCircle2 size={14} />
                                        <span>Return lines look good.</span>
                                    </div>
                                )}
                            </div>

                            {/* Workflow note */}
                            <div style={{
                                padding: '0.75rem 1rem',
                                background: 'rgba(36, 113, 163, 0.05)',
                                borderRadius: '8px',
                                border: '1px solid rgba(36, 113, 163, 0.15)',
                                fontSize: 'var(--text-xs)',
                                color: 'var(--color-text-muted)',
                                marginBottom: '1rem',
                                lineHeight: 1.6,
                            }}>
                                <strong style={{ display: 'block', marginBottom: '0.25rem', color: 'var(--color-text)' }}>
                                    Return Workflow
                                </strong>
                                Saved as <strong>Draft</strong>. Submit for manager approval, then mark <strong>Completed</strong> to post the GL reversal and vendor credit note.
                            </div>

                        </div>
                    </div>
                </form>
            </div>
        </AccountingLayout>
    );
};

export default PurchaseReturnForm;
