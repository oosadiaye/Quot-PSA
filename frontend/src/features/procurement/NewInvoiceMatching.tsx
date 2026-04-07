import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, CheckCircle, AlertTriangle, XCircle, Package, FileText, ClipboardList, CreditCard, ChevronDown, ChevronUp, Minus } from 'lucide-react';
import { useCreateMatching, usePurchaseOrders, useGRNs, usePurchaseOrder, useGRN, useDownPaymentForPO, useApplyDownPayment } from './hooks/useProcurement';
import { useCurrency } from '../../context/CurrencyContext';
import AccountingLayout from '../accounting/AccountingLayout';
import '../accounting/styles/glassmorphism.css';

const inp: React.CSSProperties = {
    width: '100%', padding: '0.45rem 0.6rem', borderRadius: '6px',
    border: '1px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-sm)',
};
const lbl: React.CSSProperties = {
    display: 'block', fontSize: '0.65rem', fontWeight: 600,
    color: 'var(--color-text-muted)', marginBottom: '0.28rem',
    textTransform: 'uppercase' as const, letterSpacing: '0.04em',
};
const card: React.CSSProperties = {
    background: 'var(--color-surface)', border: '1px solid var(--color-border)',
    borderRadius: '10px', padding: '1.1rem', marginBottom: '1rem',
};
const sectionTitle: React.CSSProperties = {
    fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-text)',
    margin: '0 0 0.875rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem',
};
const th: React.CSSProperties = {
    padding: '0.5rem 0.75rem', fontSize: '0.65rem', fontWeight: 700,
    color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em',
    textAlign: 'left' as const, background: 'rgba(0,0,0,0.03)', whiteSpace: 'nowrap' as const,
};
const td: React.CSSProperties = {
    padding: '0.5rem 0.75rem', fontSize: 'var(--text-sm)',
    borderTop: '1px solid var(--color-border)',
};

function VariancePill({ po, actual }: { po: number; actual: number }) {
    if (!po || !actual) return <span style={{ color: 'var(--color-text-muted)' }}>—</span>;
    const diff = actual - po;
    const pct = ((diff / po) * 100).toFixed(1);
    const ok = Math.abs(diff) < 0.01;
    const over = diff > 0;
    const color = ok ? '#22c55e' : over ? '#ef4444' : '#f59e0b';
    const bg = ok ? 'rgba(34,197,94,0.1)' : over ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)';
    return (
        <span style={{ padding: '0.15rem 0.5rem', borderRadius: '9999px', background: bg, color, fontWeight: 600, fontSize: '0.7rem', whiteSpace: 'nowrap' }}>
            {ok ? '✓ Match' : `${over ? '+' : ''}${pct}%`}
        </span>
    );
}

export default function NewInvoiceMatching() {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const createMatching = useCreateMatching();

    const [form, setForm] = useState({
        purchase_order: '',
        goods_received_note: '',
        invoice_reference: '',
        invoice_date: '',
        invoice_amount: '',
        invoice_tax_amount: '',
        invoice_subtotal: '',
        notes: '',
    });
    const [error, setError] = useState('');

    const set = (field: string, val: string) =>
        setForm(prev => ({ ...prev, [field]: val }));

    // ── Data fetches ─────────────────────────────────────────────────
    const { data: posData } = usePurchaseOrders({ page_size: 200 });
    const pos = Array.isArray(posData) ? posData : (posData?.results ?? []);

    const { data: grnsData } = useGRNs({ page_size: 200 });
    const grns = Array.isArray(grnsData) ? grnsData : (grnsData?.results ?? []);

    const selectedPoId = form.purchase_order ? parseInt(form.purchase_order) : null;
    const selectedGrnId = form.goods_received_note ? parseInt(form.goods_received_note) : null;

    const { data: poDetail, isLoading: poLoading } = usePurchaseOrder(selectedPoId);
    const { data: grnDetail, isLoading: grnLoading } = useGRN(selectedGrnId);

    // ── Down Payment ─────────────────────────────────────────────────
    const { data: dpr } = useDownPaymentForPO(selectedPoId);
    const applyDownPayment = useApplyDownPayment();
    const [dpExpanded, setDpExpanded] = useState(false);
    const [dpEnabled, setDpEnabled] = useState(false);
    const [dpAmount, setDpAmount] = useState('');

    // Compute invoice amount early so it can be used in dp calculations
    const invoiceAmtEarly = form.invoice_amount ? parseFloat(form.invoice_amount) : null;

    // advance_remaining is now a serializer method field returned directly on the DPR response.
    // It reflects the unspent advance balance on the linked Payment record.
    const availableAdvance: number | null = dpr?.advance_remaining != null
        ? parseFloat(String(dpr.advance_remaining))
        : null;

    // Default dp amount = min(invoice, available)
    const defaultDpAmount = useMemo(() => {
        if (availableAdvance === null || !invoiceAmtEarly) return '';
        return String(Math.min(availableAdvance, invoiceAmtEarly));
    }, [availableAdvance, invoiceAmtEarly]);

    const effectiveDpAmount = dpEnabled ? (dpAmount || defaultDpAmount) : '0';
    const netPayable = invoiceAmtEarly !== null
        ? Math.max(0, invoiceAmtEarly - parseFloat(effectiveDpAmount || '0'))
        : null;

    // Filter GRNs to those linked to the selected PO
    const filteredGrns = selectedPoId
        ? grns.filter((g: any) => String(g.purchase_order) === String(selectedPoId))
        : grns;

    // Build per-line comparison table (PO lines as base)
    const comparisonLines = useMemo(() => {
        if (!poDetail?.lines) return [];
        const grnByPoLine: Record<number, number> = {};
        if (grnDetail?.lines) {
            for (const gl of grnDetail.lines) {
                grnByPoLine[gl.po_line] = (grnByPoLine[gl.po_line] || 0) + parseFloat(gl.quantity_received || 0);
            }
        }
        return poDetail.lines.map((line: any) => {
            const poQty = parseFloat(line.quantity || 0);
            const poPrice = parseFloat(line.unit_price || 0);
            const poAmt = poQty * poPrice;
            const grnQty = grnByPoLine[line.id] ?? null;
            const grnAmt = grnQty !== null ? grnQty * poPrice : null;
            return { ...line, poQty, poPrice, poAmt, grnQty, grnAmt };
        });
    }, [poDetail, grnDetail]);

    // When PO changes: reset GRN, then auto-select if exactly one GRN exists for that PO
    const handlePoChange = (val: string) => {
        const poGrns = val
            ? grns.filter((g: any) => String(g.purchase_order) === String(val))
            : [];
        setForm(prev => ({
            ...prev,
            purchase_order: val,
            // Auto-select the single GRN so the user doesn't have to click again
            goods_received_note: poGrns.length === 1 ? String(poGrns[0].id) : '',
        }));
    };

    // ── Totals summary ───────────────────────────────────────────────
    const poTotal = poDetail ? parseFloat(poDetail.total_amount || 0) : null;
    const grnTotal = grnDetail?.lines
        ? grnDetail.lines.reduce((s: number, l: any) => {
            const poLine = poDetail?.lines?.find((p: any) => p.id === l.po_line);
            const price = poLine ? parseFloat(poLine.unit_price || 0) : 0;
            return s + parseFloat(l.quantity_received || 0) * price;
        }, 0)
        : null;
    const invoiceAmt = form.invoice_amount ? parseFloat(form.invoice_amount) : null;

    // ── Submit ───────────────────────────────────────────────────────
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        if (!form.invoice_reference.trim()) { setError('Invoice reference is required.'); return; }
        if (!form.invoice_date) { setError('Invoice date is required.'); return; }
        if (!form.invoice_amount || parseFloat(form.invoice_amount) <= 0) {
            setError('Invoice amount must be greater than zero.'); return;
        }
        try {
            const newMatching = await createMatching.mutateAsync({
                purchase_order: selectedPoId ?? undefined,
                goods_received_note: selectedGrnId ?? undefined,
                invoice_reference: form.invoice_reference.trim(),
                invoice_date: form.invoice_date,
                invoice_amount: parseFloat(form.invoice_amount),
                invoice_tax_amount: form.invoice_tax_amount ? parseFloat(form.invoice_tax_amount) : undefined,
                invoice_subtotal: form.invoice_subtotal ? parseFloat(form.invoice_subtotal) : undefined,
                notes: form.notes.trim() || undefined,
            });

            // Apply down payment if toggle is on and an amount was resolved
            if (dpEnabled && newMatching?.id) {
                const dpAmt = parseFloat(dpAmount || defaultDpAmount);
                if (dpAmt > 0) {
                    await applyDownPayment.mutateAsync({ matchingId: newMatching.id, amount: dpAmt });
                }
            }

            navigate('/procurement/matching');
        } catch (err: any) {
            const d = err?.response?.data;
            setError(d?.error || d?.detail || JSON.stringify(d) || 'Failed to create verification.');
        }
    };

    return (
        <AccountingLayout>
            <div style={{ padding: '1.5rem', maxWidth: '1100px' }}>

                {/* ── Header ─────────────────────────────────────────── */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
                    <button onClick={() => navigate('/procurement/matching')} style={{
                        display: 'flex', alignItems: 'center', gap: '0.375rem', background: 'none',
                        border: '1px solid var(--color-border)', borderRadius: '6px',
                        padding: '0.4rem 0.75rem', color: 'var(--color-text-muted)',
                        cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 500,
                    }}>
                        <ArrowLeft size={14} /> Back
                    </button>
                    <div>
                        <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                            New Invoice Verification
                        </h1>
                        <p style={{ color: 'var(--color-text-muted)', margin: '0.15rem 0 0', fontSize: 'var(--text-sm)' }}>
                            Three-way verification: Purchase Order → GRN → Vendor Invoice
                        </p>
                    </div>
                </div>

                {error && (
                    <div style={{
                        padding: '0.625rem 0.875rem', marginBottom: '1rem',
                        background: 'rgba(239,68,68,0.08)', color: '#ef4444',
                        border: '1px solid rgba(239,68,68,0.2)', borderRadius: '6px',
                        fontSize: 'var(--text-sm)',
                    }}>{error}</div>
                )}

                <form onSubmit={handleSubmit}>
                    <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: '1rem', alignItems: 'start' }}>

                        {/* ── Left column: entry fields ─────────────── */}
                        <div>
                            {/* Source Documents */}
                            <div style={card}>
                                <p style={sectionTitle}><ClipboardList size={15} /> Source Documents</p>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                                    <div>
                                        <label style={lbl}>Purchase Order</label>
                                        <select style={inp} value={form.purchase_order}
                                            onChange={e => handlePoChange(e.target.value)}>
                                            <option value="">— Select PO (optional) —</option>
                                            {pos.map((po: any) => (
                                                <option key={po.id} value={po.id}>
                                                    {po.po_number} — {po.vendor_name || po.vendor}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={{ ...lbl, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                            <span>Goods Received Note (GRN)</span>
                                            {/* Badge: count of GRNs linked to this PO */}
                                            {selectedPoId && filteredGrns.length > 0 && (
                                                <span style={{
                                                    fontSize: '0.6rem', fontWeight: 700, padding: '0.1rem 0.45rem',
                                                    borderRadius: '9999px',
                                                    background: 'rgba(34,197,94,0.12)', color: '#15803d',
                                                    letterSpacing: '0.02em',
                                                }}>
                                                    {filteredGrns.length} GRN{filteredGrns.length > 1 ? 's' : ''} found
                                                </span>
                                            )}
                                        </label>

                                        {/* ── Case 1: No PO selected yet ── */}
                                        {!selectedPoId && (
                                            <select style={{ ...inp, color: 'var(--color-text-muted)' }} disabled>
                                                <option>— Select a PO first —</option>
                                            </select>
                                        )}

                                        {/* ── Case 2: PO selected, NO GRN exists ── */}
                                        {selectedPoId && filteredGrns.length === 0 && (
                                            <div style={{
                                                ...inp,
                                                display: 'flex', alignItems: 'center', gap: '0.5rem',
                                                color: '#b45309',
                                                background: 'rgba(245,158,11,0.07)',
                                                border: '1.5px solid rgba(245,158,11,0.35)',
                                                cursor: 'default',
                                                userSelect: 'none' as const,
                                            }}>
                                                <AlertTriangle size={14} color="#f59e0b" style={{ flexShrink: 0 }} />
                                                <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                                                    No GRN Created for this PO
                                                </span>
                                            </div>
                                        )}

                                        {/* ── Case 3: PO selected, GRNs available ── */}
                                        {selectedPoId && filteredGrns.length > 0 && (
                                            <>
                                                <select
                                                    style={{
                                                        ...inp,
                                                        borderColor: form.goods_received_note
                                                            ? 'rgba(34,197,94,0.5)'
                                                            : 'var(--color-border)',
                                                        background: form.goods_received_note
                                                            ? 'rgba(34,197,94,0.04)'
                                                            : 'var(--color-surface)',
                                                    }}
                                                    value={form.goods_received_note}
                                                    onChange={e => set('goods_received_note', e.target.value)}
                                                >
                                                    {filteredGrns.length > 1 && (
                                                        <option value="">— Select GRN —</option>
                                                    )}
                                                    {filteredGrns.map((g: any) => (
                                                        <option key={g.id} value={g.id}>
                                                            {g.grn_number}
                                                            {g.received_date ? ` — ${g.received_date}` : ''}
                                                            {g.status ? ` (${g.status})` : ''}
                                                        </option>
                                                    ))}
                                                </select>
                                                {/* Auto-selected hint */}
                                                {filteredGrns.length === 1 && form.goods_received_note && (
                                                    <p style={{ fontSize: '0.6rem', color: '#16a34a', margin: '0.2rem 0 0', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                                                        <CheckCircle size={10} /> Auto-linked — only GRN for this PO
                                                    </p>
                                                )}
                                            </>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Invoice Details */}
                            <div style={card}>
                                <p style={sectionTitle}><FileText size={15} /> Invoice Details</p>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                                    <div>
                                        <label style={lbl}>Invoice Reference <span style={{ color: '#ef4444' }}>*</span></label>
                                        <input type="text" style={inp} placeholder="e.g. INV-2026-001"
                                            value={form.invoice_reference}
                                            onChange={e => set('invoice_reference', e.target.value)} required />
                                    </div>
                                    <div>
                                        <label style={lbl}>Invoice Date <span style={{ color: '#ef4444' }}>*</span></label>
                                        <input type="date" style={inp} value={form.invoice_date}
                                            onChange={e => set('invoice_date', e.target.value)} required />
                                    </div>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                                        <div>
                                            <label style={lbl}>Subtotal</label>
                                            <input type="number" style={inp} placeholder="0.00"
                                                min="0" step="0.01" value={form.invoice_subtotal}
                                                onChange={e => set('invoice_subtotal', e.target.value)} />
                                        </div>
                                        <div>
                                            <label style={lbl}>Tax Amount</label>
                                            <input type="number" style={inp} placeholder="0.00"
                                                min="0" step="0.01" value={form.invoice_tax_amount}
                                                onChange={e => set('invoice_tax_amount', e.target.value)} />
                                        </div>
                                    </div>
                                    <div>
                                        <label style={lbl}>Invoice Total <span style={{ color: '#ef4444' }}>*</span></label>
                                        <input type="number" style={{ ...inp, fontWeight: 600, fontSize: 'var(--text-base)' }}
                                            placeholder="0.00" min="0.01" step="0.01"
                                            value={form.invoice_amount}
                                            onChange={e => set('invoice_amount', e.target.value)} required />
                                    </div>
                                    <div>
                                        <label style={lbl}>Notes</label>
                                        <textarea style={{ ...inp, resize: 'vertical' }} rows={2}
                                            value={form.notes}
                                            onChange={e => set('notes', e.target.value)} />
                                    </div>
                                </div>
                            </div>

                            {/* ── Down Payment Matching ──────────────────────── */}
                            {selectedPoId && dpr && (
                                <div style={{
                                    ...card,
                                    border: dpEnabled ? '1.5px solid rgba(99,102,241,0.4)' : '1px solid var(--color-border)',
                                    background: dpEnabled ? 'rgba(99,102,241,0.03)' : 'var(--color-surface)',
                                }}>
                                    {/* Collapsible header */}
                                    <button type="button"
                                        onClick={() => setDpExpanded(v => !v)}
                                        style={{
                                            width: '100%', background: 'none', border: 'none', cursor: 'pointer',
                                            display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 0,
                                        }}>
                                        <p style={{ ...sectionTitle, margin: 0, color: dpEnabled ? '#4f46e5' : 'var(--color-text)' }}>
                                            <CreditCard size={15} />
                                            Down Payment Matching
                                            {dpEnabled && (
                                                <span style={{
                                                    marginLeft: '0.4rem', fontSize: '0.6rem', fontWeight: 700,
                                                    padding: '0.1rem 0.45rem', borderRadius: '9999px',
                                                    background: 'rgba(99,102,241,0.12)', color: '#4f46e5',
                                                }}>
                                                    Applied
                                                </span>
                                            )}
                                        </p>
                                        {dpExpanded
                                            ? <ChevronUp size={15} color="var(--color-text-muted)" />
                                            : <ChevronDown size={15} color="var(--color-text-muted)" />
                                        }
                                    </button>

                                    {dpExpanded && (
                                        <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                                            {/* DPR summary */}
                                            <div style={{
                                                padding: '0.6rem 0.75rem', borderRadius: '6px',
                                                background: 'rgba(16,185,129,0.07)', border: '1px solid rgba(16,185,129,0.2)',
                                                fontSize: 'var(--text-xs)',
                                            }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                                                    <span style={{ color: 'var(--color-text-muted)' }}>Request #</span>
                                                    <span style={{ fontWeight: 600 }}>{dpr.request_number}</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                                                    <span style={{ color: 'var(--color-text-muted)' }}>Original Amount</span>
                                                    <span style={{ fontWeight: 600 }}>{formatCurrency(parseFloat(dpr.requested_amount || '0'))}</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                    <span style={{ color: 'var(--color-text-muted)' }}>Available Balance</span>
                                                    <span style={{ fontWeight: 700, color: '#059669' }}>
                                                        {availableAdvance !== null ? formatCurrency(availableAdvance) : '—'}
                                                    </span>
                                                </div>
                                            </div>

                                            {/* Toggle */}
                                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 500 }}>
                                                <input
                                                    type="checkbox"
                                                    checked={dpEnabled}
                                                    onChange={e => {
                                                        setDpEnabled(e.target.checked);
                                                        if (!e.target.checked) setDpAmount('');
                                                    }}
                                                    style={{ width: '16px', height: '16px', cursor: 'pointer', accentColor: '#4f46e5' }}
                                                />
                                                Apply down payment to this invoice
                                            </label>

                                            {dpEnabled && (
                                                <>
                                                    <div>
                                                        <label style={lbl}>Amount to Apply</label>
                                                        <input type="number" style={inp} placeholder={defaultDpAmount || '0.00'}
                                                            min="0.01" step="0.01"
                                                            max={availableAdvance !== null ? availableAdvance : undefined}
                                                            value={dpAmount}
                                                            onChange={e => setDpAmount(e.target.value)}
                                                        />
                                                        <p style={{ fontSize: '0.6rem', color: 'var(--color-text-muted)', margin: '0.2rem 0 0' }}>
                                                            Leave blank to apply full available balance ({availableAdvance !== null ? formatCurrency(availableAdvance) : '—'})
                                                        </p>
                                                    </div>
                                                    {netPayable !== null && (
                                                        <div style={{
                                                            padding: '0.6rem 0.75rem', borderRadius: '6px',
                                                            background: 'rgba(99,102,241,0.06)',
                                                            border: '1px solid rgba(99,102,241,0.2)',
                                                        }}>
                                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                                <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                                    <Minus size={12} />
                                                                    Net Payable to Vendor
                                                                </span>
                                                                <span style={{ fontWeight: 800, fontSize: 'var(--text-base)', color: '#4f46e5', fontFamily: 'monospace' }}>
                                                                    {formatCurrency(netPayable)}
                                                                </span>
                                                            </div>
                                                        </div>
                                                    )}
                                                </>
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Actions */}
                            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', paddingTop: '0.25rem' }}>
                                <button type="button" onClick={() => navigate('/procurement/matching')}
                                    style={{
                                        padding: '0.5rem 1.25rem', borderRadius: '6px',
                                        border: '1px solid var(--color-border)', background: 'none',
                                        color: 'var(--color-text)', cursor: 'pointer',
                                        fontSize: 'var(--text-sm)', fontWeight: 500,
                                    }}>
                                    Cancel
                                </button>
                                <button type="submit" disabled={createMatching.isPending}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: '0.375rem',
                                        padding: '0.5rem 1.25rem', borderRadius: '6px',
                                        background: 'var(--color-primary)', color: '#fff',
                                        border: 'none', cursor: createMatching.isPending ? 'not-allowed' : 'pointer',
                                        fontSize: 'var(--text-sm)', fontWeight: 600,
                                        opacity: createMatching.isPending ? 0.7 : 1,
                                    }}>
                                    <Save size={15} />
                                    {createMatching.isPending ? 'Saving…' : 'Create Verification'}
                                </button>
                            </div>
                        </div>

                        {/* ── Right column: Amount Summary + PO/GRN detail ── */}
                        <div>
                            {/* ── Amount Summary (sticky top-right) ─────────── */}
                            <div style={{
                                position: 'sticky', top: '1rem',
                                background: 'linear-gradient(135deg, rgba(25,30,106,0.05) 0%, rgba(79,70,229,0.06) 100%)',
                                border: '1.5px solid rgba(79,70,229,0.2)',
                                borderRadius: '12px', padding: '1rem 1.1rem',
                                marginBottom: '1rem',
                                boxShadow: '0 2px 12px rgba(79,70,229,0.08)',
                            }}>
                                <p style={{ ...sectionTitle, color: 'var(--color-primary)', marginBottom: '0.75rem' }}>
                                    Amount Summary
                                </p>

                                {(poTotal === null && grnTotal === null && invoiceAmt === null) ? (
                                    /* Placeholder when nothing selected yet */
                                    <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: 0, fontStyle: 'italic' }}>
                                        Select a PO and enter invoice details to see comparison.
                                    </p>
                                ) : (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
                                        {/* PO Total row */}
                                        {poTotal !== null && (
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 'var(--text-sm)' }}>
                                                <span style={{ color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                                                    <span style={{ width: '8px', height: '8px', borderRadius: '2px', background: '#6366f1', display: 'inline-block' }} />
                                                    PO Total
                                                </span>
                                                <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>{formatCurrency(poTotal)}</span>
                                            </div>
                                        )}

                                        {/* GRN Value row */}
                                        {grnTotal !== null && (
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 'var(--text-sm)' }}>
                                                <span style={{ color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                                                    <span style={{ width: '8px', height: '8px', borderRadius: '2px', background: '#22c55e', display: 'inline-block' }} />
                                                    GRN Value
                                                </span>
                                                <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>{formatCurrency(grnTotal)}</span>
                                            </div>
                                        )}

                                        {/* Invoice Total + variance rows */}
                                        {invoiceAmt !== null && (
                                            <>
                                                <div style={{
                                                    borderTop: '1px solid rgba(79,70,229,0.15)',
                                                    marginTop: '0.2rem', paddingTop: '0.45rem',
                                                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                                    fontSize: 'var(--text-sm)',
                                                }}>
                                                    <span style={{ color: 'var(--color-text)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                                                        <span style={{ width: '8px', height: '8px', borderRadius: '2px', background: '#f59e0b', display: 'inline-block' }} />
                                                        Invoice Total
                                                    </span>
                                                    <span style={{ fontWeight: 800, fontFamily: 'monospace', fontSize: 'var(--text-base)', color: 'var(--color-primary)' }}>
                                                        {formatCurrency(invoiceAmt)}
                                                    </span>
                                                </div>

                                                {/* Variance pills */}
                                                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', paddingTop: '0.15rem' }}>
                                                    {poTotal !== null && (
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                            <span>vs PO:</span>
                                                            <VariancePill po={poTotal} actual={invoiceAmt} />
                                                        </div>
                                                    )}
                                                    {grnTotal !== null && (
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                            <span>vs GRN:</span>
                                                            <VariancePill po={grnTotal} actual={invoiceAmt} />
                                                        </div>
                                                    )}
                                                </div>

                                                {/* Net payable row when down payment is applied */}
                                                {dpEnabled && netPayable !== null && (
                                                    <div style={{
                                                        marginTop: '0.4rem', paddingTop: '0.45rem',
                                                        borderTop: '1px dashed rgba(99,102,241,0.25)',
                                                    }}>
                                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 'var(--text-xs)', marginBottom: '0.2rem' }}>
                                                            <span style={{ color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                                                <CreditCard size={10} />
                                                                Down Payment Applied
                                                            </span>
                                                            <span style={{ fontWeight: 600, color: '#059669', fontFamily: 'monospace' }}>
                                                                − {formatCurrency(parseFloat(dpAmount || defaultDpAmount || '0'))}
                                                            </span>
                                                        </div>
                                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 'var(--text-sm)' }}>
                                                            <span style={{ fontWeight: 700, color: '#4f46e5', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                                                <Minus size={12} />
                                                                Net Payable
                                                            </span>
                                                            <span style={{ fontWeight: 800, fontFamily: 'monospace', fontSize: 'var(--text-base)', color: '#4f46e5' }}>
                                                                {formatCurrency(netPayable)}
                                                            </span>
                                                        </div>
                                                    </div>
                                                )}
                                            </>
                                        )}
                                    </div>
                                )}
                            </div>

                            {/* PO Header */}
                            {poLoading && (
                                <div style={{ ...card, color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                    Loading PO details…
                                </div>
                            )}
                            {poDetail && (
                                <div style={card}>
                                    <p style={sectionTitle}><Package size={15} /> Purchase Order — {poDetail.po_number}</p>

                                    {/* PO Header Info */}
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem 1rem', marginBottom: '1rem' }}>
                                        {[
                                            { label: 'Vendor', value: poDetail.vendor_name },
                                            { label: 'Order Date', value: poDetail.order_date },
                                            { label: 'Expected Delivery', value: poDetail.expected_delivery_date || '—' },
                                            { label: 'Status', value: poDetail.status },
                                            { label: 'Payment Terms', value: poDetail.payment_terms || '—' },
                                            { label: 'PO Total', value: formatCurrency(parseFloat(poDetail.total_amount || 0)) },
                                        ].map(({ label, value }) => (
                                            <div key={label}>
                                                <div style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '0.15rem' }}>{label}</div>
                                                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{value}</div>
                                            </div>
                                        ))}
                                    </div>

                                    {/* PO Line Items */}
                                    <div style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '0.5rem' }}>
                                        Line Items
                                    </div>
                                    <div style={{ overflowX: 'auto', borderRadius: '6px', border: '1px solid var(--color-border)' }}>
                                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)' }}>
                                            <thead>
                                                <tr>
                                                    <th style={th}>Description</th>
                                                    <th style={{ ...th, textAlign: 'right' }}>PO Qty</th>
                                                    <th style={{ ...th, textAlign: 'right' }}>Received</th>
                                                    <th style={{ ...th, textAlign: 'right' }}>Pending</th>
                                                    <th style={{ ...th, textAlign: 'right' }}>Unit Price</th>
                                                    <th style={{ ...th, textAlign: 'right' }}>PO Amount</th>
                                                    {selectedGrnId && <th style={{ ...th, textAlign: 'right' }}>GRN Qty</th>}
                                                    {selectedGrnId && <th style={{ ...th, textAlign: 'right' }}>GRN Amount</th>}
                                                    {selectedGrnId && <th style={{ ...th, textAlign: 'center' }}>Variance</th>}
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {comparisonLines.map((line: any) => (
                                                    <tr key={line.id}>
                                                        <td style={td}>
                                                            <div style={{ fontWeight: 500 }}>{line.item_description}</div>
                                                            {line.item_name && <div style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)' }}>{line.item_name}</div>}
                                                        </td>
                                                        <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace' }}>{line.poQty}</td>
                                                        <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace', color: line.is_fully_received ? '#22c55e' : 'var(--color-text)' }}>
                                                            {parseFloat(line.quantity_received || 0)}
                                                        </td>
                                                        <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace', color: parseFloat(line.pending_quantity) > 0 ? '#f59e0b' : '#22c55e' }}>
                                                            {parseFloat(line.pending_quantity || 0)}
                                                        </td>
                                                        <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace' }}>{formatCurrency(line.poPrice)}</td>
                                                        <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace', fontWeight: 600 }}>{formatCurrency(line.poAmt)}</td>
                                                        {selectedGrnId && (
                                                            <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace', color: line.grnQty !== null ? 'var(--color-text)' : 'var(--color-text-muted)' }}>
                                                                {grnLoading ? '…' : line.grnQty !== null ? line.grnQty : '—'}
                                                            </td>
                                                        )}
                                                        {selectedGrnId && (
                                                            <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace' }}>
                                                                {line.grnAmt !== null ? formatCurrency(line.grnAmt) : '—'}
                                                            </td>
                                                        )}
                                                        {selectedGrnId && (
                                                            <td style={{ ...td, textAlign: 'center' }}>
                                                                {line.grnAmt !== null
                                                                    ? <VariancePill po={line.poAmt} actual={line.grnAmt} />
                                                                    : <span style={{ color: 'var(--color-text-muted)', fontSize: '0.65rem' }}>No GRN</span>
                                                                }
                                                            </td>
                                                        )}
                                                    </tr>
                                                ))}
                                            </tbody>
                                            <tfoot>
                                                <tr style={{ borderTop: '2px solid var(--color-border)', background: 'rgba(0,0,0,0.02)' }}>
                                                    <td style={{ ...td, fontWeight: 700 }} colSpan={4}>Total</td>
                                                    <td style={{ ...td }} />
                                                    <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>
                                                        {formatCurrency(poTotal ?? 0)}
                                                    </td>
                                                    {selectedGrnId && (
                                                        <td style={{ ...td }} />
                                                    )}
                                                    {selectedGrnId && (
                                                        <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>
                                                            {grnTotal !== null ? formatCurrency(grnTotal) : '—'}
                                                        </td>
                                                    )}
                                                    {selectedGrnId && (
                                                        <td style={{ ...td, textAlign: 'center' }}>
                                                            {grnTotal !== null && poTotal !== null &&
                                                                <VariancePill po={poTotal} actual={grnTotal} />
                                                            }
                                                        </td>
                                                    )}
                                                </tr>
                                            </tfoot>
                                        </table>
                                    </div>

                                    {/* Receipt status indicators */}
                                    <div style={{ display: 'flex', gap: '1rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
                                        {comparisonLines.map((line: any) => (
                                            <div key={line.id} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.7rem' }}>
                                                {line.is_fully_received
                                                    ? <CheckCircle size={12} color="#22c55e" />
                                                    : parseFloat(line.quantity_received) > 0
                                                        ? <AlertTriangle size={12} color="#f59e0b" />
                                                        : <XCircle size={12} color="#ef4444" />
                                                }
                                                <span style={{ color: 'var(--color-text-muted)' }}>{line.item_description}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Prompt when nothing selected */}
                            {!selectedPoId && !selectedGrnId && (
                                <div style={{
                                    ...card, textAlign: 'center', padding: '3rem 2rem',
                                    color: 'var(--color-text-muted)',
                                    border: '2px dashed var(--color-border)',
                                    background: 'transparent',
                                }}>
                                    <Package size={40} style={{ margin: '0 auto 0.75rem', opacity: 0.3 }} />
                                    <p style={{ margin: 0, fontSize: 'var(--text-sm)' }}>
                                        Select a Purchase Order to view full line-item details
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>
                </form>
            </div>
        </AccountingLayout>
    );
}
