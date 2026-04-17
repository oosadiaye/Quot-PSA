import React, { useState, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    Plus, Trash2, FileText, Layers, Paperclip,
    ReceiptText, ArrowLeftRight, CheckCircle, AlertCircle,
} from 'lucide-react';
import { useCreateVendorInvoice, useTaxCodes, useWithholdingTaxes } from '../hooks/useAccountingEnhancements';
import { useVendors } from '../../procurement/hooks/useProcurement';
import { useDimensions } from '../hooks/useJournal';
import { useIsDimensionsEnabled } from '../../../hooks/useTenantModules';
import { useNCoASegments } from '../../../hooks/useGovForms';
import { useAuth } from '../../../context/AuthContext';
import { useCurrency } from '../../../context/CurrencyContext';
import AccountingLayout from '../AccountingLayout';
import BackButton from '../../../components/BackButton';
import SearchableSelect from '../../../components/SearchableSelect';
import apiClient from '../../../api/client';
import '../styles/glassmorphism.css';

type TabType = 'invoice' | 'credit_memo';

let _lineUid = 0;
const nextLineUid = () => String(++_lineUid);

type LineType = 'expense' | 'asset' | 'gl';

interface InvoiceLine {
    _uid: string;
    line_type: LineType;
    account: string;
    description: string;
    amount: string;
    tax_code: string;
    withholding_tax: string;
}

interface Props {
    onCancel: () => void;
    onSuccess: () => void;
}

const VendorInvoiceForm: React.FC<Props> = ({ onCancel, onSuccess }) => {
    const { hasRole } = useAuth();
    // SoD: Credit Memo requires manager or admin role
    // Users who create invoices (officer/user) cannot create credit memos
    const canCreateCreditMemo = hasRole('manager');

    const { data: dims, isLoading: dimsLoading } = useDimensions();
    const { isEnabled: dimensionsEnabled } = useIsDimensionsEnabled();
    const { data: segments } = useNCoASegments();
    const { formatCurrency, currencySymbol } = useCurrency();
    const createInvoice = useCreateVendorInvoice();
    const { data: vendors } = useVendors({ is_active: true });
    const { data: taxCodes } = useTaxCodes({ is_active: true });
    const { data: whtList } = useWithholdingTaxes({ is_active: true });

    // Fetch fixed assets for the selected MDA (used in Asset line type)
    const [activeTab, setActiveTab] = useState<TabType>('invoice');
    const [header, setHeader] = useState({
        mda: '',
        vendor: '', reference: '', description: '',
        invoice_date: new Date().toISOString().split('T')[0],
        due_date: '', vendor_credit_amount: '',
        fund: '', function: '', program: '', geo: '',
    });
    const [lines, setLines] = useState<InvoiceLine[]>([
        { _uid: nextLineUid(), line_type: 'expense', account: '', description: '', amount: '0', tax_code: '', withholding_tax: '' },
    ]);
    const [attachment, setAttachment] = useState<File | null>(null);
    const [formError, setFormError] = useState('');

    // Fetch fixed assets for the selected MDA
    const { data: fixedAssets } = useQuery({
        queryKey: ['fixed-assets-mda', header.mda],
        queryFn: async () => {
            const params: Record<string, string> = { status: 'Active', page_size: '500' };
            if (header.mda) params.mda = header.mda;
            const res = await apiClient.get('/accounting/fixed-assets/', { params });
            const d = res.data;
            return Array.isArray(d) ? d : d?.results || [];
        },
        enabled: !!header.mda,
        staleTime: 60_000,
    });

    // Account lists filtered by type
    const allAccounts = dims?.accounts ?? [];
    const expenseAccounts = useMemo(() => allAccounts.filter((a: any) => a.account_type === 'Expense'), [allAccounts]);
    const assetAccounts = useMemo(() => allAccounts.filter((a: any) => a.account_type === 'Asset'), [allAccounts]);
    // GL = all accounts (for journal-style entries)
    const getAccountsForLineType = (lt: LineType) => {
        if (lt === 'expense') return expenseAccounts;
        if (lt === 'asset') return assetAccounts;
        return allAccounts; // 'gl' = any account
    };

    // Totals — safe integer-cent arithmetic
    const { subtotal, taxTotal, whtTotal, grandTotal } = useMemo(() => {
        let subCents = 0, taxCents = 0, whtCents = 0;
        for (const line of lines) {
            const amtCents = Math.round(Number(line.amount || 0) * 100);
            subCents += amtCents;
            if (line.tax_code) {
                const tc = taxCodes?.find((t: any) => String(t.id) === line.tax_code);
                if (tc) taxCents += Math.round(amtCents * Number(tc.rate) / 100);
            }
            if (line.withholding_tax) {
                const wc = whtList?.find((w: any) => String(w.id) === line.withholding_tax);
                if (wc) whtCents += Math.round(amtCents * Number(wc.rate) / 100);
            }
        }
        return {
            subtotal: subCents / 100,
            taxTotal: taxCents / 100,
            whtTotal: whtCents / 100,
            grandTotal: (subCents + taxCents - whtCents) / 100,
        };
    }, [lines, taxCodes, whtList]);

    const [addLineType, setAddLineType] = useState<LineType>('expense');
    const addLine = (lt?: LineType) =>
        setLines(prev => [...prev, { _uid: nextLineUid(), line_type: lt || addLineType, account: '', description: '', amount: '0', tax_code: '', withholding_tax: '' }]);
    const removeLine = (idx: number) => setLines(prev => prev.filter((_, i) => i !== idx));
    const updateLine = (idx: number, field: keyof InvoiceLine, value: string) =>
        setLines(prev => { const n = [...prev]; n[idx][field] = value; return n; });

    const switchTab = (tab: TabType) => {
        setActiveTab(tab);
        setLines([{ _uid: nextLineUid(), line_type: 'expense', account: '', description: '', amount: '0', tax_code: '', withholding_tax: '' }]);
        setFormError('');
        setHeader(h => ({ ...h, vendor_credit_amount: '' }));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        const jsonPayload: any = {
            mda: header.mda ? Number(header.mda) : null,
            vendor: Number(header.vendor),
            reference: header.reference,
            description: header.description,
            invoice_date: header.invoice_date,
            due_date: header.due_date || header.invoice_date,
            vendor_credit_amount: parseFloat(header.vendor_credit_amount || '0').toFixed(2),
            total_amount: grandTotal.toFixed(2),
            document_type: isCreditMemo ? 'Credit Memo' : 'Invoice',
            lines: lines.map(l => ({
                account: Number(l.account),
                description: l.description,
                amount: parseFloat(l.amount),
                tax_code: l.tax_code ? Number(l.tax_code) : null,
                withholding_tax: l.withholding_tax ? Number(l.withholding_tax) : null,
            })),
            ...(dimensionsEnabled ? {
                fund: header.fund ? Number(header.fund) : null,
                function: header.function ? Number(header.function) : null,
                program: header.program ? Number(header.program) : null,
                geo: header.geo ? Number(header.geo) : null,
            } : {}),
        };

        let payload: any = jsonPayload;
        if (attachment) {
            const fd = new FormData();
            Object.entries(jsonPayload).forEach(([k, v]) => {
                if (k === 'lines') fd.append(k, JSON.stringify(v));
                else if (v !== null && v !== undefined) fd.append(k, String(v));
            });
            fd.append('attachment', attachment);
            payload = fd;
        }

        try {
            await createInvoice.mutateAsync(payload);
            onSuccess();
        } catch (err: any) {
            const data = err.response?.data;
            // Priority: structured budget/warrant errors go first — they
            // carry the full human-readable message in a known field.
            // Fall back to the dump of all error fields for other cases.
            const msg =
                typeof data === 'string' ? data :
                data?.budget ? (Array.isArray(data.budget) ? data.budget.join(' ') : data.budget) :
                data?.error ? data.error :
                data?.detail ? data.detail :
                data && typeof data === 'object'
                    ? Object.entries(data)
                        .filter(([k]) => !['appropriation_exceeded', 'warrant_exceeded', 'no_appropriation',
                                           'missing_dimensions', 'dimensions', 'appropriation_id',
                                           'requested', 'available', 'deficit', 'warrant_info'].includes(k))
                        .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
                        .join(' | ')
                    : err.message || 'Failed to save document.';
            setFormError(msg || 'Failed to save document.');
        }
    };

    if (dimsLoading) return (
        <AccountingLayout>
            <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                Loading…
            </div>
        </AccountingLayout>
    );

    // ── Derived flags ────────────────────────────────────────────
    const isCreditMemo = activeTab === 'credit_memo';
    const creditAmount = parseFloat(header.vendor_credit_amount || '0');
    const isBalanced = isCreditMemo
        ? grandTotal > 0
        : Math.abs(grandTotal - creditAmount) < 0.01 && grandTotal > 0;
    const balanceDiff = isCreditMemo ? 0 : grandTotal - creditAmount;

    // ── Shared style tokens (compact) ────────────────────────────
    const inp: React.CSSProperties = {
        width: '100%', padding: '0.45rem 0.7rem', borderRadius: '7px',
        border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
        color: 'var(--color-text)', fontSize: 'var(--text-sm)',
        outline: 'none', fontFamily: 'inherit',
    };
    const lbl: React.CSSProperties = {
        display: 'block', marginBottom: '0.25rem',
        fontSize: '0.68rem', fontWeight: 700,
        textTransform: 'uppercase', letterSpacing: '0.05em',
        color: 'var(--color-text-muted)',
    };
    const fieldGap: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: '0.65rem' };
    const pill = (bg: string, color: string, text: string) => (
        <span style={{
            padding: '0.1rem 0.45rem', borderRadius: '4px',
            background: bg, color, fontWeight: 700, fontSize: '10px', letterSpacing: '0.03em',
        }}>{text}</span>
    );

    return (
        <form onSubmit={handleSubmit} style={{ height: '100%' }}>

            {/* ── TOP BAR: header + tabs on same row ──────────────── */}
            <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                marginBottom: '0.75rem', gap: '1rem',
            }}>
                {/* Left: back + title */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', minWidth: 0 }}>
                    <button type="button" onClick={onCancel} aria-label="Go back" style={{ cursor: 'pointer', background: 'none', border: 'none', padding: 0 }}><BackButton /></button>
                    <h1 style={{ fontSize: 'var(--text-lg)', fontWeight: 800, margin: 0, color: 'var(--color-text)', whiteSpace: 'nowrap' }}>
                        {isCreditMemo ? 'Vendor Credit Memo' : 'Vendor Invoice'}
                    </h1>
                    <p style={{ margin: 0, fontSize: '0.72rem', color: 'var(--color-text-muted)' }}>
                        {isCreditMemo ? 'Dr Accounts Payable · Cr Expense' : 'Dr Expense · Cr Accounts Payable'}
                    </p>
                </div>

                {/* Centre: tab switcher */}
                <div style={{
                    display: 'flex', borderRadius: '9px',
                    border: '1.5px solid var(--color-border)',
                    overflow: 'hidden', flexShrink: 0,
                }}>
                    {([
                        { key: 'invoice' as TabType, label: 'Vendor Invoice', Icon: FileText, restricted: false },
                        { key: 'credit_memo' as TabType, label: 'Credit Memo', Icon: ReceiptText, restricted: !canCreateCreditMemo },
                    ]).filter(t => !t.restricted).map(({ key, label, Icon }) => (
                        <button key={key} type="button" onClick={() => switchTab(key)} style={{
                            display: 'flex', alignItems: 'center', gap: '0.4rem',
                            padding: '0.45rem 1.1rem', border: 'none', cursor: 'pointer',
                            fontSize: 'var(--text-xs)', fontWeight: 600,
                            background: activeTab === key ? 'var(--color-primary)' : 'transparent',
                            color: activeTab === key ? '#fff' : 'var(--color-text-muted)',
                            transition: 'background 0.15s, color 0.15s',
                        }}>
                            <Icon size={13} />
                            {label}
                        </button>
                    ))}
                </div>

                {/* Right: action buttons */}
                <div style={{ display: 'flex', gap: '0.6rem', flexShrink: 0 }}>
                    <button type="button" className="btn btn-outline" onClick={onCancel}
                        style={{ padding: '0.45rem 1.1rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                        Cancel
                    </button>
                    <button type="submit" className="btn btn-primary"
                        disabled={createInvoice.isPending || !isBalanced}
                        title={!isBalanced ? 'Debit and credit must be equal before saving' : undefined}
                        style={{ padding: '0.45rem 1.25rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                        {createInvoice.isPending ? 'Saving…' : isCreditMemo ? 'Save Credit Memo' : 'Save Invoice'}
                    </button>
                </div>
            </div>

            {/* ── Info banner (compact 1-line) ─────────────────────── */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: '0.6rem',
                padding: '0.45rem 0.875rem', borderRadius: '7px', marginBottom: '0.75rem',
                background: isCreditMemo ? 'rgba(13,148,136,0.07)' : 'rgba(25,30,106,0.06)',
                border: `1px solid ${isCreditMemo ? 'rgba(13,148,136,0.25)' : 'rgba(25,30,106,0.18)'}`,
                fontSize: '0.72rem', color: 'var(--color-text-secondary)',
            }}>
                <ArrowLeftRight size={13} style={{ flexShrink: 0, color: isCreditMemo ? '#0d9488' : 'var(--color-primary)' }} />
                {isCreditMemo
                    ? <span><strong>Credit Memo</strong> — Dr AP (reduces vendor liability) · Cr Expense/Asset (reverses original charge).</span>
                    : <span><strong>Vendor Invoice</strong> — Dr Expense/Asset/GL Account · Cr AP (records vendor liability). Add lines by type: Expense, Asset, or GL Account.</span>}
            </div>

            {formError && (
                <div style={{
                    padding: '0.7rem 0.95rem', background: '#fef2f2', color: '#991b1b',
                    border: '1.5px solid #fecaca',
                    borderRadius: '8px', marginBottom: '0.75rem',
                    fontSize: 'var(--text-xs)', fontWeight: 500,
                    whiteSpace: 'pre-wrap' as const,  // preserves \n in budget messages
                    fontFamily: 'inherit',
                }}>
                    <div style={{ fontWeight: 700, marginBottom: '0.3rem', fontSize: 'var(--text-sm)' }}>
                        ⚠ Budget Validation Failed
                    </div>
                    {formError}
                </div>
            )}

            {/* ══════════════════════════════════════════════════════
                MAIN BODY — left panel (fields) + right panel (lines)
                ══════════════════════════════════════════════════════ */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: '320px 1fr',
                gap: '1rem',
                alignItems: 'start',
            }}>

                {/* ── LEFT PANEL: all header fields ─────────────── */}
                <div className="card" style={{ padding: '1.1rem 1.25rem' }}>
                    <p style={{
                        fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
                        letterSpacing: '0.06em', color: 'var(--color-text-muted)',
                        marginBottom: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.4rem',
                    }}>
                        {isCreditMemo ? <ReceiptText size={12} /> : <FileText size={12} />}
                        {isCreditMemo ? 'Credit Memo Details' : 'Invoice Details'}
                    </p>

                    <div style={fieldGap}>

                        {/* MDA — first field, mandatory */}
                        <div>
                            <label style={lbl}>Administrative (MDA) <span style={{ color: '#ef4444' }}>*</span></label>
                            <SearchableSelect
                                options={(segments?.administrative || []).map((s: any) => ({
                                    value: String(s.id), label: `${s.code} - ${s.name}`, sublabel: s.mda_type || s.level,
                                }))}
                                value={header.mda}
                                onChange={v => setHeader(h => ({ ...h, mda: v }))}
                                placeholder="Type MDA name or code..."
                                required
                            />
                        </div>

                        {/* Vendor */}
                        <div>
                            <label style={lbl}>Vendor <span style={{ color: '#ef4444' }}>*</span></label>
                            <select style={{ ...inp, appearance: 'auto' as any }}
                                value={header.vendor}
                                onChange={e => setHeader(h => ({ ...h, vendor: e.target.value }))} required>
                                <option value="">Select vendor…</option>
                                {vendors?.map((v: any) => <option key={v.id} value={v.id}>{v.name}</option>)}
                            </select>
                        </div>

                        {/* Reference */}
                        <div>
                            <label style={lbl}>{isCreditMemo ? 'Credit Memo No.' : 'Invoice No. / Reference'} <span style={{ color: '#ef4444' }}>*</span></label>
                            <input style={inp} type="text"
                                placeholder={isCreditMemo ? 'CM-001' : 'INV-001'}
                                value={header.reference}
                                onChange={e => setHeader(h => ({ ...h, reference: e.target.value }))} required />
                        </div>

                        {/* Dates */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                            <div>
                                <label style={lbl}>{isCreditMemo ? 'CM Date' : 'Invoice Date'} <span style={{ color: '#ef4444' }}>*</span></label>
                                <input style={inp} type="date" value={header.invoice_date}
                                    onChange={e => setHeader(h => ({ ...h, invoice_date: e.target.value }))} required />
                            </div>
                            {!isCreditMemo && (
                                <div>
                                    <label style={lbl}>Due Date <span style={{ color: '#ef4444' }}>*</span></label>
                                    <input style={inp} type="date" value={header.due_date}
                                        onChange={e => setHeader(h => ({ ...h, due_date: e.target.value }))} required />
                                </div>
                            )}
                        </div>

                        {/* Description */}
                        <div>
                            <label style={lbl}>Description</label>
                            <textarea
                                style={{ ...inp, minHeight: '60px', maxHeight: '80px', resize: 'vertical' }}
                                placeholder={isCreditMemo ? 'Reason for credit memo…' : 'Invoice details…'}
                                value={header.description}
                                onChange={e => setHeader(h => ({ ...h, description: e.target.value }))}
                            />
                        </div>

                        {/* Vendor AP credit amount — invoice only */}
                        {!isCreditMemo && (
                            <div>
                                <label style={lbl}>Vendor Amount (Cr AP) <span style={{ color: '#ef4444' }}>*</span></label>
                                <div style={{ position: 'relative' }}>
                                    <span style={{
                                        position: 'absolute', left: '9px', top: '50%', transform: 'translateY(-50%)',
                                        fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)',
                                        fontWeight: 700, pointerEvents: 'none',
                                    }}>{currencySymbol}</span>
                                    <input style={{ ...inp, paddingLeft: '1.75rem' }}
                                        type="number" step="0.01" min="0" placeholder="0.00"
                                        value={header.vendor_credit_amount}
                                        onChange={e => setHeader(h => ({ ...h, vendor_credit_amount: e.target.value }))}
                                        required />
                                </div>
                                <p style={{ margin: '0.2rem 0 0', fontSize: '0.65rem', color: 'var(--color-text-muted)' }}>
                                    Amount to credit to vendor's AP account.
                                </p>
                            </div>
                        )}

                        {/* Attachment */}
                        <div>
                            <label style={lbl}>Attachment (optional)</label>
                            {!attachment ? (
                                <label style={{
                                    display: 'flex', alignItems: 'center', gap: '0.4rem',
                                    padding: '0.45rem 0.75rem', borderRadius: '7px',
                                    border: '1.5px dashed var(--color-border)',
                                    cursor: 'pointer', color: 'var(--color-text-muted)',
                                    fontSize: 'var(--text-xs)',
                                }}>
                                    <Paperclip size={13} />
                                    <span>Attach image or PDF</span>
                                    <input type="file" accept="image/*,.pdf" style={{ display: 'none' }}
                                        onChange={e => setAttachment(e.target.files?.[0] || null)} />
                                </label>
                            ) : (
                                <div style={{
                                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                    padding: '0.4rem 0.75rem', borderRadius: '7px',
                                    background: 'rgba(25,30,106,0.05)',
                                    border: '1.5px solid rgba(25,30,106,0.18)',
                                    fontSize: 'var(--text-xs)',
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--color-text)', minWidth: 0 }}>
                                        <Paperclip size={12} color="var(--color-primary)" style={{ flexShrink: 0 }} />
                                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {attachment.name}
                                        </span>
                                        <span style={{ color: 'var(--color-text-muted)', flexShrink: 0 }}>
                                            ({(attachment.size / 1024).toFixed(0)} KB)
                                        </span>
                                    </div>
                                    <button type="button" onClick={() => setAttachment(null)}
                                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: '2px', flexShrink: 0 }}>
                                        <Trash2 size={13} />
                                    </button>
                                </div>
                            )}
                        </div>

                        {/* Dimensions (2×2 grid when enabled) */}
                        {dimensionsEnabled && (
                            <div>
                                <p style={{
                                    fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
                                    letterSpacing: '0.06em', color: 'var(--color-text-muted)',
                                    marginBottom: '0.5rem', marginTop: '0.25rem',
                                    display: 'flex', alignItems: 'center', gap: '0.35rem',
                                }}>
                                    <Layers size={11} /> Dimensions
                                </p>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                                    {[
                                        { key: 'fund', label: 'Fund', items: dims?.funds },
                                        { key: 'function', label: 'Function', items: dims?.functions },
                                        { key: 'program', label: 'Program', items: dims?.programs },
                                        { key: 'geo', label: 'Geo', items: dims?.geos },
                                    ].map(({ key, label, items }) => (
                                        <div key={key}>
                                            <label style={lbl}>{label} <span style={{ color: '#ef4444' }}>*</span></label>
                                            <select style={{ ...inp, appearance: 'auto' as any }}
                                                value={(header as any)[key]}
                                                onChange={e => setHeader(h => ({ ...h, [key]: e.target.value }))}
                                                required>
                                                <option value="">—</option>
                                                {items?.map((item: any) => (
                                                    <option key={item.id} value={item.id}>{item.code}</option>
                                                ))}
                                            </select>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                    </div>
                </div>

                {/* ── RIGHT PANEL: line items + balance/totals ──────── */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>

                    {/* Line Items Card */}
                    <div className="card" style={{ padding: '1.1rem 1.25rem' }}>
                        <div style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            marginBottom: '0.75rem',
                        }}>
                            <p style={{
                                fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
                                letterSpacing: '0.06em', color: 'var(--color-text-muted)', margin: 0,
                                display: 'flex', alignItems: 'center', gap: '0.4rem',
                            }}>
                                Line Items
                            </p>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                <button type="button" onClick={() => addLine('expense')}
                                    style={{ display: 'flex', alignItems: 'center', gap: '0.2rem', background: 'none', border: '1px solid var(--color-border)', borderRadius: '5px', cursor: 'pointer', color: 'var(--color-primary)', fontSize: '0.62rem', fontWeight: 600, padding: '0.25rem 0.5rem' }}>
                                    <Plus size={11} /> Expense
                                </button>
                                <button type="button" onClick={() => addLine('asset')}
                                    style={{ display: 'flex', alignItems: 'center', gap: '0.2rem', background: 'none', border: '1px solid var(--color-border)', borderRadius: '5px', cursor: 'pointer', color: '#0d9488', fontSize: '0.62rem', fontWeight: 600, padding: '0.25rem 0.5rem' }}>
                                    <Plus size={11} /> Asset
                                </button>
                                <button type="button" onClick={() => addLine('gl')}
                                    style={{ display: 'flex', alignItems: 'center', gap: '0.2rem', background: 'none', border: '1px solid var(--color-border)', borderRadius: '5px', cursor: 'pointer', color: '#7c3aed', fontSize: '0.62rem', fontWeight: 600, padding: '0.25rem 0.5rem' }}>
                                    <Plus size={11} /> GL Account
                                </button>
                            </div>
                        </div>

                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '560px' }}>
                                <thead>
                                    <tr style={{ borderBottom: '1.5px solid var(--color-border)' }}>
                                        {[
                                            { label: '#', w: '28px' },
                                            { label: 'Type', w: '70px' },
                                            { label: 'Account', w: '28%' },
                                            { label: 'Description', w: 'auto' },
                                            { label: 'Amount', w: '110px' },
                                            { label: 'Tax', w: '100px' },
                                            { label: 'WHT', w: '100px' },
                                            { label: '', w: '28px' },
                                        ].map(({ label, w }, i) => (
                                            <th key={i} style={{
                                                width: w, padding: '0 0.4rem 0.5rem',
                                                textAlign: 'left', fontSize: '0.62rem', fontWeight: 700,
                                                textTransform: 'uppercase', letterSpacing: '0.05em',
                                                color: 'var(--color-text-muted)',
                                            }}>
                                                {label}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {lines.map((line, idx) => {
                                        const lineTypeColors: Record<LineType, { bg: string; color: string; label: string }> = {
                                            expense: { bg: 'rgba(25,30,106,0.08)', color: 'var(--color-primary)', label: 'EXP' },
                                            asset: { bg: 'rgba(13,148,136,0.08)', color: '#0d9488', label: 'AST' },
                                            gl: { bg: 'rgba(124,58,237,0.08)', color: '#7c3aed', label: 'GL' },
                                        };
                                        const ltc = lineTypeColors[line.line_type] || lineTypeColors.expense;
                                        const accts = getAccountsForLineType(line.line_type);
                                        return (
                                        <tr key={line._uid} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                            {/* Row number */}
                                            <td style={{ padding: '0.3rem 0.4rem 0.3rem 0', color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', textAlign: 'center' }}>
                                                {idx + 1}
                                            </td>
                                            {/* Line Type badge */}
                                            <td style={{ padding: '0.3rem 0.3rem 0.3rem 0' }}>
                                                <span style={{
                                                    display: 'inline-block', padding: '0.15rem 0.4rem', borderRadius: '4px',
                                                    background: ltc.bg, color: ltc.color, fontWeight: 700,
                                                    fontSize: '0.58rem', letterSpacing: '0.03em',
                                                }}>{ltc.label}</span>
                                            </td>
                                            {/* Account — asset lines show fixed assets, others show GL accounts */}
                                            <td style={{ padding: '0.3rem 0.3rem 0.3rem 0' }}>
                                                {line.line_type === 'asset' ? (
                                                    <select style={{ ...inp, appearance: 'auto' as any, fontSize: 'var(--text-xs)', padding: '0.38rem 0.55rem', borderColor: !header.mda ? '#fbbf24' : '' }}
                                                        value={line.account}
                                                        onChange={e => {
                                                            updateLine(idx, 'account', e.target.value);
                                                            // Auto-fill description from asset name
                                                            const asset = (fixedAssets || []).find((a: any) => String(a.id) === e.target.value);
                                                            if (asset) updateLine(idx, 'description', `${asset.asset_number} — ${asset.name}`);
                                                        }} required>
                                                        <option value="">{header.mda ? 'Select asset…' : 'Select MDA first'}</option>
                                                        {(fixedAssets || []).map((a: any) => (
                                                            <option key={a.id} value={a.id}>
                                                                {a.asset_number} — {a.name} ({a.asset_category})
                                                            </option>
                                                        ))}
                                                    </select>
                                                ) : (
                                                    <select style={{ ...inp, appearance: 'auto' as any, fontSize: 'var(--text-xs)', padding: '0.38rem 0.55rem' }}
                                                        value={line.account}
                                                        onChange={e => updateLine(idx, 'account', e.target.value)} required>
                                                        <option value="">Select…</option>
                                                        {accts.map((a: any) => (
                                                            <option key={a.id} value={a.id}>{a.code} – {a.name}</option>
                                                        ))}
                                                    </select>
                                                )}
                                            </td>
                                            {/* Description */}
                                            <td style={{ padding: '0.3rem' }}>
                                                <input style={{ ...inp, fontSize: 'var(--text-xs)', padding: '0.38rem 0.55rem' }}
                                                    type="text" placeholder="Description"
                                                    value={line.description}
                                                    onChange={e => updateLine(idx, 'description', e.target.value)} />
                                            </td>
                                            {/* Amount */}
                                            <td style={{ padding: '0.3rem' }}>
                                                <div style={{ position: 'relative' }}>
                                                    <span style={{
                                                        position: 'absolute', left: '7px', top: '50%', transform: 'translateY(-50%)',
                                                        fontSize: '0.65rem', color: 'var(--color-text-muted)', fontWeight: 700, pointerEvents: 'none',
                                                    }}>{currencySymbol}</span>
                                                    <input style={{ ...inp, fontSize: 'var(--text-xs)', padding: '0.38rem 0.55rem 0.38rem 1.35rem' }}
                                                        type="number" step="0.01" min="0"
                                                        value={line.amount}
                                                        onChange={e => updateLine(idx, 'amount', e.target.value)} required />
                                                </div>
                                            </td>
                                            {/* Tax */}
                                            <td style={{ padding: '0.3rem' }}>
                                                <select style={{ ...inp, appearance: 'auto' as any, fontSize: 'var(--text-xs)', padding: '0.38rem 0.55rem' }}
                                                    value={line.tax_code}
                                                    onChange={e => updateLine(idx, 'tax_code', e.target.value)}>
                                                    <option value="">No Tax</option>
                                                    {taxCodes?.map((t: any) => (
                                                        <option key={t.id} value={t.id}>{t.code} ({t.rate}%)</option>
                                                    ))}
                                                </select>
                                            </td>
                                            {/* WHT */}
                                            <td style={{ padding: '0.3rem' }}>
                                                <select style={{ ...inp, appearance: 'auto' as any, fontSize: 'var(--text-xs)', padding: '0.38rem 0.55rem' }}
                                                    value={line.withholding_tax}
                                                    onChange={e => updateLine(idx, 'withholding_tax', e.target.value)}>
                                                    <option value="">No WHT</option>
                                                    {whtList?.map((w: any) => (
                                                        <option key={w.id} value={w.id}>{w.code} ({w.rate}%)</option>
                                                    ))}
                                                </select>
                                            </td>
                                            {/* Remove */}
                                            <td style={{ padding: '0.3rem', textAlign: 'center' }}>
                                                {lines.length > 1 && (
                                                    <button type="button" onClick={() => removeLine(idx)}
                                                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: '2px', lineHeight: 1 }}>
                                                        <Trash2 size={14} />
                                                    </button>
                                                )}
                                            </td>
                                        </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* ── Balance validator + totals (single card) ─────── */}
                    <div className="card" style={{
                        padding: '0.875rem 1.25rem',
                        border: grandTotal === 0
                            ? '1px solid var(--color-border)'
                            : isBalanced
                                ? '1px solid rgba(22,163,74,0.35)'
                                : '1px solid rgba(220,38,38,0.4)',
                        background: grandTotal === 0
                            ? 'var(--color-surface)'
                            : isBalanced
                                ? 'rgba(22,163,74,0.03)'
                                : 'rgba(220,38,38,0.03)',
                        transition: 'border-color 0.2s, background 0.2s',
                    }}>

                        {/* Balance row */}
                        <div style={{
                            display: 'grid',
                            gridTemplateColumns: '1fr 1px 1fr 1px auto',
                            alignItems: 'center',
                            gap: '1rem',
                            paddingBottom: '0.75rem',
                            marginBottom: '0.75rem',
                            borderBottom: '1px solid var(--color-border)',
                        }}>
                            {/* DR side */}
                            <div>
                                <p style={{ margin: '0 0 0.2rem', fontSize: '0.62rem', fontWeight: 600, color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                    {pill('rgba(25,30,106,0.1)', 'var(--color-primary)', 'DR')}
                                    {isCreditMemo ? 'Accounts Payable' : 'Expense (Lines)'}
                                </p>
                                <p style={{ margin: 0, fontSize: 'var(--text-base)', fontWeight: 800, color: 'var(--color-text)', letterSpacing: '-0.02em' }}>
                                    {formatCurrency(grandTotal)}
                                </p>
                            </div>

                            <div style={{ width: 1, height: 36, background: 'var(--color-border)', justifySelf: 'center' }} />

                            {/* CR side */}
                            <div>
                                <p style={{ margin: '0 0 0.2rem', fontSize: '0.62rem', fontWeight: 600, color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                    {pill('rgba(13,148,136,0.1)', '#0d9488', 'CR')}
                                    {isCreditMemo ? 'Expense (Lines)' : 'Accounts Payable'}
                                </p>
                                <p style={{ margin: 0, fontSize: 'var(--text-base)', fontWeight: 800, color: 'var(--color-text)', letterSpacing: '-0.02em' }}>
                                    {isCreditMemo ? formatCurrency(grandTotal) : formatCurrency(creditAmount)}
                                </p>
                            </div>

                            <div style={{ width: 1, height: 36, background: 'var(--color-border)', justifySelf: 'center' }} />

                            {/* Status */}
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.15rem', minWidth: '120px' }}>
                                {grandTotal === 0 ? (
                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontStyle: 'italic' }}>
                                        Enter amounts above
                                    </span>
                                ) : isBalanced ? (
                                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: '#16a34a', fontWeight: 700, fontSize: 'var(--text-sm)' }}>
                                        <CheckCircle size={15} /> Balanced
                                    </span>
                                ) : (
                                    <>
                                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: '#dc2626', fontWeight: 700, fontSize: 'var(--text-sm)' }}>
                                            <AlertCircle size={15} /> Out of Balance
                                        </span>
                                        <span style={{ fontSize: 'var(--text-xs)', color: '#dc2626', fontWeight: 600 }}>
                                            Diff: {formatCurrency(Math.abs(balanceDiff))}
                                        </span>
                                    </>
                                )}
                            </div>
                        </div>

                        {/* Totals strip */}
                        <div style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            flexWrap: 'wrap', gap: '0.5rem',
                        }}>
                            <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
                                {[
                                    { label: 'Subtotal', value: subtotal },
                                    { label: 'Tax', value: taxTotal },
                                    { label: 'WHT', value: whtTotal },
                                ].map(({ label, value }) => (
                                    <div key={label}>
                                        <p style={{ margin: 0, fontSize: '0.62rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', letterSpacing: '0.04em' }}>
                                            {label}
                                        </p>
                                        <p style={{ margin: 0, fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-text)' }}>
                                            {formatCurrency(value)}
                                        </p>
                                    </div>
                                ))}
                            </div>

                            {/* Grand total highlight */}
                            <div style={{
                                padding: '0.4rem 1rem', borderRadius: '8px',
                                background: isCreditMemo
                                    ? 'linear-gradient(135deg, #0f766e, #0d9488)'
                                    : 'linear-gradient(135deg, #0f1240, #191e6a)',
                                color: '#fff',
                                textAlign: 'right',
                            }}>
                                <p style={{ margin: 0, fontSize: '0.62rem', fontWeight: 600, opacity: 0.8, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                                    Total
                                </p>
                                <p style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 800, letterSpacing: '-0.02em' }}>
                                    {formatCurrency(grandTotal)}
                                </p>
                            </div>
                        </div>
                    </div>

                </div>{/* /right panel */}
            </div>{/* /main grid */}
        </form>
    );
};

export default VendorInvoiceForm;
