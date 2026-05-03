import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
    Package, FileText, Layers, Info, Truck, AlertTriangle,
    CheckCircle2, Split, CalendarClock, Building2, Lock,
} from 'lucide-react';
import { useCreateGRN, usePurchaseOrders, usePurchaseOrder } from './hooks/useProcurement';
// NOTE: warehouse selection has been removed from the GRN form. The MDA is now
// the user-facing receiving dimension; the backend resolves MDA → default
// Warehouse via inventory.services.get_default_warehouse_for_mda().
import { useCurrency } from '../../context/CurrencyContext';
import { safeAdd, safeMultiply } from '../accounting/utils/currency';
import AccountingLayout from '../accounting/AccountingLayout';
import PageHeader from '../../components/PageHeader';
import SearchableSelect from '../../components/SearchableSelect';
import '../accounting/styles/glassmorphism.css';

// ─── Types ────────────────────────────────────────────────────────────────────

interface GRNLine {
    po_line_id: number;
    item_description: string;
    ordered_qty: number;
    already_received: number;
    pending_qty: number;
    unit_price: number;
    // Receipt fields
    quantity_received: string;
    batch_number: string;
    expiry_date: string;
    // For auto-suggest
    item_shelf_life_days: number | null;
    expiry_auto_set: boolean;
}

// ─── Helper ───────────────────────────────────────────────────────────────────

function addDays(dateStr: string, days: number): string {
    const d = new Date(dateStr);
    d.setDate(d.getDate() + days);
    return d.toISOString().split('T')[0];
}

// ─── Component ────────────────────────────────────────────────────────────────

const GRNForm = () => {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const { formatCurrency } = useCurrency();
    const createGRN = useCreateGRN();

    const poParam = Number(searchParams.get('po'));
    const preselectedPoId = Number.isFinite(poParam) && poParam > 0 ? poParam : null;

    const { data: posData } = usePurchaseOrders({ page_size: 200 });
    const allPos = posData?.results || posData || [];
    // Eligible: Approved or Posted
    const posList = Array.isArray(allPos)
        ? allPos.filter((po: any) => ['Approved', 'Posted'].includes(po.status))
        : [];

    const [selectedPOId, setSelectedPOId] = useState<number | null>(preselectedPoId);
    const { data: selectedPO, isLoading: poLoading } = usePurchaseOrder(selectedPOId);

    const [header, setHeader] = useState({
        received_date: new Date().toISOString().split('T')[0],
        received_by: '',
        notes: '',
    });

    // MDA is derived from the selected PO and is locked — the user cannot
    // change it. Public-sector accountability requires that the receiving
    // MDA always equals the MDA on the originating Purchase Order.
    const poMdaId: number | null = (selectedPO?.mda as number | null) ?? null;
    const poMdaName: string =
        (selectedPO?.mda_name as string | undefined) ?? '';
    const poMdaCode: string =
        (selectedPO?.mda_code as string | undefined) ?? '';

    const [lines, setLines] = useState<GRNLine[]>([]);
    const [formError, setFormError] = useState('');

    // ── Populate lines from selected PO ──────────────────────────────────────
    useEffect(() => {
        if (selectedPO?.lines) {
            const newLines: GRNLine[] = selectedPO.lines
                .filter((l: any) => l.pending_quantity > 0)
                .map((l: any) => {
                    const shelfLife = l.item_shelf_life_days ?? null;
                    const autoExpiry = shelfLife ? addDays(header.received_date, shelfLife) : '';
                    return {
                        po_line_id: l.id,
                        item_description: l.item_description,
                        ordered_qty: parseFloat(l.quantity),
                        already_received: parseFloat(l.quantity_received || '0'),
                        pending_qty: parseFloat(l.pending_quantity || '0'),
                        unit_price: parseFloat(l.unit_price),
                        quantity_received: '',
                        batch_number: '',
                        expiry_date: autoExpiry,
                        item_shelf_life_days: shelfLife,
                        expiry_auto_set: !!shelfLife,
                    };
                });
            setLines(newLines);
        } else {
            setLines([]);
        }
    }, [selectedPO]);

    // ── Recalculate auto-set expiry dates when received_date changes ──────────
    useEffect(() => {
        setLines(prev => prev.map(l => {
            if (l.expiry_auto_set && l.item_shelf_life_days) {
                return { ...l, expiry_date: addDays(header.received_date, l.item_shelf_life_days) };
            }
            return l;
        }));
    }, [header.received_date]);

    // ── Line updaters ─────────────────────────────────────────────────────────
    const updateLine = (index: number, field: keyof GRNLine, value: string) => {
        setLines(prev => {
            const next = [...prev];
            if (field === 'expiry_date') {
                next[index] = { ...next[index], expiry_date: value, expiry_auto_set: false };
            } else {
                next[index] = { ...next[index], [field]: value };
            }
            return next;
        });
    };

    // ── Derived ───────────────────────────────────────────────────────────────
    const linesWithQty = useMemo(
        () => lines.filter(l => parseFloat(l.quantity_received || '0') > 0),
        [lines]
    );

    const totalValue = useMemo(
        () => lines.reduce((sum, l) => safeAdd(sum, safeMultiply(l.quantity_received || '0', l.unit_price)), 0),
        [lines]
    );

    const totalQtyReceiving = useMemo(
        () => lines.reduce((sum, l) => safeAdd(sum, l.quantity_received || '0'), 0),
        [lines]
    );

    const isPartialGRN = useMemo(() => {
        if (linesWithQty.length === 0) return false;
        return !lines.every(l => parseFloat(l.quantity_received || '0') >= l.pending_qty);
    }, [lines, linesWithQty]);

    const lineHasOverQty = (line: GRNLine) => parseFloat(line.quantity_received || '0') > line.pending_qty;
    const anyLineOverQty = useMemo(() => lines.some(lineHasOverQty), [lines]);

    // Batch number is optional in PSA — many ministries receive non-batchable
    // items (stationery, office furniture, services). Kept here as a no-op
    // for backwards compat with downstream code that still reads it.
    const linesMissingBatch: GRNLine[] = [];

    // ── Submit ────────────────────────────────────────────────────────────────
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        if (!selectedPOId)          { setFormError('Purchase Order is required.'); return; }
        if (!header.received_by.trim()) { setFormError('Received By is required.'); return; }
        if (!poMdaId) {
            setFormError(
                'Selected Purchase Order has no MDA assigned — cannot create a GRN. ' +
                'Re-open the PO and assign an MDA before receiving.'
            );
            return;
        }
        if (linesWithQty.length === 0) { setFormError('At least one line must have a quantity received.'); return; }
        if (anyLineOverQty)         { setFormError('One or more lines exceed the pending quantity. Please correct before saving.'); return; }
        // Batch number is optional in PSA — no missing-batch check.

        const payload = {
            purchase_order: selectedPOId,
            received_date: header.received_date,
            received_by: header.received_by,
            mda: poMdaId,  // sent for defense-in-depth; backend also auto-populates from PO
            notes: header.notes || undefined,
            lines: linesWithQty.map(l => ({
                po_line: l.po_line_id,
                quantity_received: parseFloat(l.quantity_received),
                batch_number: l.batch_number.trim(),
                expiry_date: l.expiry_date || null,
            })),
        };

        try {
            await createGRN.mutateAsync(payload);
            navigate('/procurement/grn');
        } catch (err: any) {
            const data = err?.response?.data;
            if (data?.error)       setFormError(data.error);
            else if (data?.detail) setFormError(data.detail);
            else if (data && typeof data === 'object') {
                const msgs = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`);
                setFormError(msgs.join(' | ') || 'Failed to create GRN.');
            } else {
                setFormError(err?.message || 'Failed to create GRN.');
            }
        }
    };

    // ── Styles ────────────────────────────────────────────────────────────────
    const labelStyle: React.CSSProperties = {
        display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)',
        fontWeight: 600, color: 'var(--color-text-secondary, #64748b)',
    };
    const inputStyle: React.CSSProperties = {
        width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
        border: '2px solid var(--color-border, #e2e8f0)',
        background: 'var(--color-background, #fff)', color: 'var(--color-text, #1e293b)',
        fontSize: 'var(--text-sm)', outline: 'none', transition: 'border-color 0.15s',
    };
    const selectStyle: React.CSSProperties = { ...inputStyle, appearance: 'auto' as any };
    const sectionHeaderStyle: React.CSSProperties = {
        display: 'flex', alignItems: 'center', gap: '0.5rem',
        fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text, #1e293b)',
        marginBottom: '1.5rem',
    };
    const iconBoxStyle: React.CSSProperties = {
        width: '28px', height: '28px', borderRadius: '6px',
        background: 'rgba(79, 70, 229, 0.1)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', flexShrink: 0,
    };
    const thStyle: React.CSSProperties = {
        padding: '0.5rem 0.5rem 0.75rem', textAlign: 'left', fontSize: 'var(--text-xs)',
        fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
        color: 'var(--color-text-muted)', whiteSpace: 'nowrap',
    };
    const requiredMark = <span className="required-mark"> *</span>;

    return (
        <AccountingLayout>
            <form onSubmit={handleSubmit}>
                <PageHeader
                    title="New Goods Received Note"
                    subtitle="Record goods received against a purchase order."
                    icon={<Package size={22} />}
                    onBack={() => navigate('/procurement/grn')}
                    actions={
                        <>
                            <button type="button" className="btn btn-outline" onClick={() => navigate('/procurement/grn')}
                                style={{ padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px', color: 'white', borderColor: 'rgba(255,255,255,0.3)', background: 'transparent' }}>
                                Cancel
                            </button>
                            <button type="submit" className="btn btn-primary"
                                disabled={createGRN.isPending || !selectedPOId || lines.length === 0 || anyLineOverQty}
                                style={{ padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px', background: 'rgba(255,255,255,0.18)', color: 'white', border: '1px solid rgba(255,255,255,0.25)' }}>
                                {createGRN.isPending ? 'Saving...' : 'Save GRN'}
                            </button>
                        </>
                    }
                />

                {/* ── Error banner ─────────────────────────────────────────── */}
                {formError && (
                    <div style={{ padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626', borderRadius: '8px', marginBottom: '1.5rem', fontSize: 'var(--text-sm)', display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                        <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: '1px' }} />
                        {formError}
                    </div>
                )}

                {/* ── Active-GRN warning ───────────────────────────────────── */}
                {selectedPO?.has_active_grns && (
                    <div style={{ padding: '0.875rem 1rem', marginBottom: '1.25rem', borderRadius: '8px', background: 'rgba(245,158,11,0.1)', border: '1.5px solid rgba(245,158,11,0.35)', display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
                        <AlertTriangle size={18} color="#d97706" style={{ flexShrink: 0, marginTop: '1px' }} />
                        <div>
                            <p style={{ fontWeight: 700, color: '#92400e', fontSize: 'var(--text-sm)', marginBottom: '0.15rem' }}>Active GRN exists for this PO</p>
                            <p style={{ color: '#92400e', fontSize: 'var(--text-xs)', opacity: 0.85 }}>
                                A GRN has already been created against this PO. This will create an additional partial receipt for remaining quantities only.
                            </p>
                        </div>
                    </div>
                )}

                {/* ── Layout ───────────────────────────────────────────────── */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: '1.5rem', alignItems: 'start' }}>

                    {/* LEFT COLUMN */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                        {/* GRN Header Card */}
                        <div className="card" style={{ padding: '1.75rem' }}>
                            <div style={sectionHeaderStyle}>
                                <span style={iconBoxStyle}><FileText size={16} color="#4f46e5" /></span>
                                GRN Details
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>

                                {/* PO Selection — type-to-search via SearchableSelect.
                                    The native <select> required scrolling through every
                                    PO in the tenant; SearchableSelect lets the operator
                                    type the PO number (e.g. "PO-2026-00003") or vendor
                                    name and pick from a filtered list. ``label``
                                    carries the headline match-text; ``sublabel`` shows
                                    vendor + status so two POs from the same vendor
                                    can be told apart at a glance. */}
                                <div>
                                    <label style={labelStyle}>Purchase Order{requiredMark}</label>
                                    <SearchableSelect
                                        options={posList.map((po: any) => ({
                                            value: String(po.id),
                                            label: `${po.po_number} — ${po.vendor_name}`,
                                            sublabel: po.status ? `Status: ${po.status}` : undefined,
                                        }))}
                                        value={selectedPOId ? String(selectedPOId) : ''}
                                        onChange={(v: string) => setSelectedPOId(v ? Number(v) : null)}
                                        placeholder="Type PO number or vendor name..."
                                        required
                                    />
                                </div>

                                {/* Received Date */}
                                <div>
                                    <label style={labelStyle}>Received Date{requiredMark}</label>
                                    <input style={inputStyle} type="date"
                                        value={header.received_date}
                                        onChange={e => setHeader({ ...header, received_date: e.target.value })} required />
                                </div>

                                {/* Received By + MDA (locked, from PO) */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                    <div>
                                        <label style={labelStyle}>Received By{requiredMark}</label>
                                        <input style={inputStyle} type="text" placeholder="Name of receiving officer"
                                            value={header.received_by}
                                            onChange={e => setHeader({ ...header, received_by: e.target.value })} required />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>
                                            MDA (from PO){requiredMark}
                                            <span style={{
                                                marginLeft: '0.4rem', display: 'inline-flex',
                                                alignItems: 'center', gap: '0.2rem',
                                                fontSize: '10px', color: '#64748b', fontWeight: 500,
                                            }}>
                                                <Lock size={10} /> locked
                                            </span>
                                        </label>
                                        <div style={{
                                            ...inputStyle,
                                            display: 'flex', alignItems: 'center', gap: '0.5rem',
                                            background: 'rgba(79, 70, 229, 0.04)',
                                            borderColor: poMdaId ? 'rgba(79, 70, 229, 0.25)' : '#e2e8f0',
                                            cursor: 'not-allowed',
                                            color: poMdaId ? 'var(--color-text, #1e293b)' : '#94a3b8',
                                            minHeight: '36px',
                                        }}>
                                            <Building2 size={14} color={poMdaId ? '#4f46e5' : '#94a3b8'} />
                                            {poMdaId ? (
                                                <span>
                                                    <strong>{poMdaCode || `#${poMdaId}`}</strong>
                                                    {poMdaName ? ` — ${poMdaName}` : ''}
                                                </span>
                                            ) : selectedPOId ? (
                                                <span style={{ fontStyle: 'italic' }}>
                                                    PO has no MDA assigned
                                                </span>
                                            ) : (
                                                <span style={{ fontStyle: 'italic' }}>
                                                    Select a Purchase Order first
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                {/* Notes */}
                                <div>
                                    <label style={labelStyle}>Notes</label>
                                    <textarea
                                        style={{ ...inputStyle, minHeight: '70px', resize: 'vertical', fontFamily: 'inherit' }}
                                        placeholder="Additional notes about this receipt..."
                                        value={header.notes}
                                        onChange={e => setHeader({ ...header, notes: e.target.value })}
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Receive Lines Card */}
                        <div className="card" style={{ padding: '1.75rem' }}>
                            <div style={{ ...sectionHeaderStyle, justifyContent: 'space-between' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <span style={iconBoxStyle}><Package size={16} color="#4f46e5" /></span>
                                    Receive Lines
                                </div>
                                {isPartialGRN && (
                                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '0.25rem 0.65rem', borderRadius: '20px', background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.4)', color: '#b45309', fontSize: 'var(--text-xs)', fontWeight: 700 }}>
                                        <Split size={12} /> Partial Receipt
                                    </span>
                                )}
                            </div>

                            {!selectedPOId ? (
                                <div style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--color-text-muted)' }}>
                                    <Truck size={48} style={{ opacity: 0.3, marginBottom: '0.75rem', display: 'block', margin: '0 auto 0.75rem' }} />
                                    <p style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>Select a Purchase Order to load lines</p>
                                </div>
                            ) : poLoading ? (
                                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-muted)' }}>Loading PO lines...</div>
                            ) : lines.length === 0 ? (
                                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-muted)' }}>
                                    <CheckCircle2 size={32} color="#10b981" style={{ display: 'block', margin: '0 auto 0.75rem' }} />
                                    <p style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>All items on this PO have been fully received.</p>
                                </div>
                            ) : (
                                <>
                                    {/* Batch hint banner */}
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.625rem 0.875rem', background: 'rgba(79,70,229,0.06)', border: '1px solid rgba(79,70,229,0.18)', borderRadius: '8px', marginBottom: '1.25rem', fontSize: 'var(--text-xs)', color: '#4f46e5' }}>
                                        <CalendarClock size={14} style={{ flexShrink: 0 }} />
                                        <span><strong>Batch &amp; expiry are optional</strong> — fill them in only for batchable inventory (drugs, consumables). Expiry date is auto-suggested from the product's shelf life when applicable.</span>
                                    </div>

                                    <div style={{ overflowX: 'auto' }}>
                                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                            <thead>
                                                <tr style={{ borderBottom: '2px solid var(--color-border)' }}>
                                                    <th style={thStyle}>Item</th>
                                                    <th style={{ ...thStyle, width: '72px', textAlign: 'right' }}>Ordered</th>
                                                    <th style={{ ...thStyle, width: '72px', textAlign: 'right' }}>Rcvd</th>
                                                    <th style={{ ...thStyle, width: '72px', textAlign: 'right' }}>Pending</th>
                                                    <th style={{ ...thStyle, width: '100px', textAlign: 'right' }}>Unit Price</th>
                                                    <th style={{ ...thStyle, width: '110px' }}>Qty to Receive{requiredMark}</th>
                                                    <th style={{ ...thStyle, width: '140px' }}>Batch / Lot No.</th>
                                                    <th style={{ ...thStyle, width: '140px' }}>Expiry Date</th>
                                                    <th style={{ ...thStyle, width: '90px', textAlign: 'right' }}>Line Total</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {lines.map((line, idx) => {
                                                    const qtyRcv = parseFloat(line.quantity_received || '0');
                                                    const overQty = qtyRcv > line.pending_qty;
                                                    // Batch number is optional in PSA — no per-row "missing batch" error.
                                                    const missingBatch = false;
                                                    const lineTotal = safeMultiply(line.quantity_received || '0', line.unit_price);
                                                    const rowError = overQty || missingBatch;

                                                    return (
                                                        <tr key={line.po_line_id} style={{ borderBottom: '1px solid var(--color-border)', background: rowError ? 'rgba(239,68,68,0.03)' : undefined }}>
                                                            {/* Item description */}
                                                            <td style={{ padding: '0.6rem 0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500, minWidth: '160px' }}>
                                                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                                                                    {overQty && <AlertTriangle size={13} color="#dc2626" style={{ flexShrink: 0 }} />}
                                                                    {line.item_description}
                                                                </div>
                                                                {overQty && (
                                                                    <div style={{ fontSize: '11px', color: '#dc2626', marginTop: '2px', fontWeight: 600 }}>
                                                                        Exceeds pending ({line.pending_qty})
                                                                    </div>
                                                                )}
                                                                {/* Batch is optional — no inline error. */}
                                                            </td>
                                                            {/* Ordered */}
                                                            <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', fontSize: 'var(--text-sm)' }}>{line.ordered_qty}</td>
                                                            {/* Already received */}
                                                            <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{line.already_received}</td>
                                                            {/* Pending */}
                                                            <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: '#4f46e5' }}>{line.pending_qty}</td>
                                                            {/* Unit price */}
                                                            <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', fontSize: 'var(--text-sm)' }}>{formatCurrency(line.unit_price)}</td>
                                                            {/* Qty to receive — clamped to the PO line's
                                                                ``pending_qty`` (= ordered − already received).
                                                                Three layers of defence: (1) ``max=pending_qty``
                                                                browser attribute, (2) ``Math.min`` clamp on
                                                                input so typing 88 against a pending of 4
                                                                snaps the field to 4 immediately, (3) the
                                                                pre-existing red banner + Save-button gate
                                                                catches any value that bypasses the above.
                                                                A user typing more than allowed will see the
                                                                value visibly snap, which is the clearest
                                                                signal that the cap exists. */}
                                                            <td style={{ padding: '0.35rem 0.5rem' }}>
                                                                <input
                                                                    style={{ ...inputStyle, textAlign: 'right', borderColor: overQty ? '#dc2626' : undefined, background: overQty ? 'rgba(239,68,68,0.05)' : undefined }}
                                                                    type="number" step="0.01" min="0" max={line.pending_qty}
                                                                    placeholder="0"
                                                                    value={line.quantity_received}
                                                                    onChange={e => {
                                                                        const raw = e.target.value;
                                                                        if (raw === '') {
                                                                            updateLine(idx, 'quantity_received', '');
                                                                            return;
                                                                        }
                                                                        const n = parseFloat(raw);
                                                                        if (isNaN(n)) {
                                                                            updateLine(idx, 'quantity_received', '');
                                                                            return;
                                                                        }
                                                                        // Clamp [0, pending_qty]; preserve user's
                                                                        // raw decimal precision unless the cap kicks in.
                                                                        const clamped = Math.max(0, Math.min(n, line.pending_qty));
                                                                        const out = clamped === n ? raw : String(clamped);
                                                                        updateLine(idx, 'quantity_received', out);
                                                                    }}
                                                                    title={`Maximum ${line.pending_qty} (pending receipt against PO line)`}
                                                                />
                                                            </td>
                                                            {/* Batch number */}
                                                            <td style={{ padding: '0.35rem 0.5rem' }}>
                                                                <input
                                                                    style={{ ...inputStyle, fontFamily: 'monospace', fontSize: '12px', borderColor: missingBatch ? '#dc2626' : undefined, background: missingBatch ? 'rgba(239,68,68,0.05)' : undefined }}
                                                                    type="text"
                                                                    placeholder="BATCH-001"
                                                                    value={line.batch_number}
                                                                    onChange={e => updateLine(idx, 'batch_number', e.target.value)}
                                                                />
                                                            </td>
                                                            {/* Expiry date */}
                                                            <td style={{ padding: '0.35rem 0.5rem' }}>
                                                                <input
                                                                    style={{ ...inputStyle, borderColor: line.expiry_auto_set && line.expiry_date ? 'rgba(16,185,129,0.5)' : undefined }}
                                                                    type="date"
                                                                    value={line.expiry_date}
                                                                    onChange={e => updateLine(idx, 'expiry_date', e.target.value)}
                                                                />
                                                                {line.expiry_auto_set && line.expiry_date && (
                                                                    <div style={{ fontSize: '10px', color: '#10b981', marginTop: '2px', fontWeight: 600 }}>
                                                                        ✦ auto-suggested — override if different
                                                                    </div>
                                                                )}
                                                            </td>
                                                            {/* Line total */}
                                                            <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: overQty ? '#dc2626' : 'var(--color-text)' }}>
                                                                {formatCurrency(lineTotal)}
                                                            </td>
                                                        </tr>
                                                    );
                                                })}
                                            </tbody>
                                            <tfoot>
                                                <tr>
                                                    <td colSpan={8} style={{ padding: '0.75rem 0.5rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)', borderTop: '2px solid var(--color-border)' }}>
                                                        Total Received Value:
                                                    </td>
                                                    <td style={{ padding: '0.75rem 0.5rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)', color: '#4f46e5', borderTop: '2px solid var(--color-border)' }}>
                                                        {formatCurrency(totalValue)}
                                                    </td>
                                                </tr>
                                            </tfoot>
                                        </table>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>

                    {/* RIGHT COLUMN */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                        {/* PO Info */}
                        {selectedPO && (
                            <div className="card" style={{ padding: '1.75rem' }}>
                                <div style={sectionHeaderStyle}>
                                    <span style={iconBoxStyle}><Layers size={16} color="#4f46e5" /></span>
                                    Purchase Order Info
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', fontSize: 'var(--text-sm)' }}>
                                    {[
                                        { label: 'PO Number',  value: selectedPO.po_number },
                                        { label: 'Vendor',     value: selectedPO.vendor_name },
                                        { label: 'Order Date', value: selectedPO.order_date ? new Date(selectedPO.order_date).toLocaleDateString('en-GB') : '—' },
                                        { label: 'PO Total',   value: formatCurrency(selectedPO.total_amount || 0) },
                                        { label: 'Total Lines',value: selectedPO.lines?.length || 0 },
                                    ].map(({ label, value }) => (
                                        <div key={label} style={{ display: 'flex', justifyContent: 'space-between' }}>
                                            <span style={{ color: 'var(--color-text-muted)' }}>{label}</span>
                                            <span style={{ fontWeight: 600 }}>{value}</span>
                                        </div>
                                    ))}
                                    <div style={{ marginTop: '0.25rem', padding: '0.5rem 0.75rem', borderRadius: '6px', background: selectedPO.has_active_grns ? 'rgba(245,158,11,0.1)' : 'rgba(16,185,129,0.08)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        {selectedPO.has_active_grns
                                            ? <AlertTriangle size={14} color="#d97706" />
                                            : <CheckCircle2 size={14} color="#059669" />}
                                        <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: selectedPO.has_active_grns ? '#92400e' : '#065f46' }}>
                                            {selectedPO.has_active_grns ? 'Active GRN exists' : 'No GRN yet — first receipt'}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Summary / validation card */}
                        <div style={{
                            borderRadius: '12px', padding: '1.75rem',
                            background: anyLineOverQty
                                ? 'linear-gradient(135deg, #dc2626 0%, #ef4444 100%)'
                                : isPartialGRN
                                    ? 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)'
                                    : 'linear-gradient(135deg, #059669 0%, #10b981 50%, #34d399 100%)',
                            color: '#fff',
                        }}>
                            <p style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '0.35rem', opacity: 0.85 }}>
                                {anyLineOverQty ? '⚠ Over-Quantity Error'
                                    : isPartialGRN ? 'Partial Receipt'
                                    : 'Receipt Summary'}
                            </p>
                            <p style={{ fontSize: 'var(--text-xs)', opacity: 0.8, marginBottom: '0.5rem' }}>Total Received Value</p>
                            <p style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: '-0.025em', marginBottom: '1.25rem' }}>
                                {formatCurrency(totalValue)}
                            </p>
                            <div style={{ borderTop: '1px solid rgba(255,255,255,0.2)', paddingTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                                {[
                                    { label: 'Items Receiving', value: linesWithQty.length },
                                    { label: 'Total Qty',       value: totalQtyReceiving },
                                    { label: 'Batches Entered', value: linesWithQty.filter(l => l.batch_number.trim()).length + ' / ' + linesWithQty.length + ' (optional)' },
                                    { label: 'Type',            value: isPartialGRN ? 'Partial' : linesWithQty.length > 0 ? 'Full Receipt' : 'Draft' },
                                ].map(({ label, value }) => (
                                    <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                        <span style={{ opacity: 0.85 }}>{label}</span>
                                        <span style={{ fontWeight: 600 }}>{value}</span>
                                    </div>
                                ))}
                            </div>

                            {/* Context messages */}
                            {(anyLineOverQty || isPartialGRN || totalValue > 0) && (
                                <div style={{ marginTop: '1.25rem', padding: '0.75rem', borderRadius: '8px', background: 'rgba(255,255,255,0.15)', display: 'flex', alignItems: 'flex-start', gap: '0.5rem', fontSize: 'var(--text-xs)' }}>
                                    {anyLineOverQty
                                        ? <><AlertTriangle size={14} style={{ flexShrink: 0, marginTop: '1px' }} /><span>One or more lines exceed their pending quantity. Correct quantities to save.</span></>
                                        : isPartialGRN
                                            ? <><Split size={14} style={{ flexShrink: 0, marginTop: '1px' }} /><span>Partial receipt — remaining qty can be received in a future GRN.</span></>
                                            : <><Info size={14} style={{ flexShrink: 0, marginTop: '1px' }} /><span>GRN saved as Draft. Post from the GRN list to update inventory &amp; book the GL journal.</span></>
                                    }
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </form>
        </AccountingLayout>
    );
};

export default GRNForm;
