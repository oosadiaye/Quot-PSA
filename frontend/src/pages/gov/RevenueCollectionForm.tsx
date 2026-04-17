/**
 * Revenue Collection (IGR) — Journal-Style Entry — Quot PSE
 * Route: /accounting/revenue-collections/new
 *
 * Structured like a journal entry with mandatory double-entry:
 * - Header: Revenue details, payer, collection info
 * - Lines: Debit (TSA/Cash) and Credit (Revenue account) with auto-balance
 * - NCoA classification with full 52-digit code resolution
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Save, AlertCircle, Plus, Trash2, CheckCircle2, BookOpen } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import '../../features/accounting/styles/glassmorphism.css';
import {
    useCreateRevenueCollection, useRevenueHeadsList, useNCoASegments, useTSAAccounts,
} from '../../hooks/useGovForms';
import apiClient from '../../api/client';

const selectStyle: React.CSSProperties = {
    width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-xs)',
};
const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-xs)',
};
const lblStyle: React.CSSProperties = {
    display: 'block', fontSize: '0.65rem', fontWeight: 600,
    color: 'var(--color-text-muted)', marginBottom: '0.25rem',
    textTransform: 'uppercase' as const, letterSpacing: '0.04em',
};

const COLLECTION_CHANNELS = [
    ['BANK', 'Bank Deposit'], ['ONLINE', 'Online Payment'], ['USSD', 'USSD'],
    ['AGENT', 'Collection Agent'], ['COUNTER', 'Counter'], ['POS', 'POS Terminal'],
];
const MONTHS = Array.from({ length: 12 }, (_, i) => [
    String(i + 1), new Date(2000, i).toLocaleString('en', { month: 'long' }),
]);

const fmtNGN = (v: number): string =>
    v ? '\u20A6' + v.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '\u20A60.00';

interface JournalLine {
    id: string;
    account_label: string;
    account_code: string;
    debit: string;
    credit: string;
    narration: string;
}

export default function RevenueCollectionForm() {
    const navigate = useNavigate();
    const createRevenue = useCreateRevenueCollection();
    const { data: segments, isLoading: segsLoading } = useNCoASegments();
    const { data: tsaAccounts } = useTSAAccounts();
    const { data: revenueHeads } = useRevenueHeadsList();

    const [formError, setFormError] = useState('');

    // Header state
    const [form, setForm] = useState({
        revenue_head: '', collection_channel: 'BANK', collection_date: '',
        amount: '', payment_reference: '', rrr: '',
        payer_name: '', payer_tin: '', payer_phone: '', payer_address: '',
        tsa_account: '', period_month: '', period_year: '', description: '',
        admin_code: '', economic_code: '', functional_code: '',
        programme_code: '', fund_code: '', geo_code: '',
    });

    // Journal lines state (auto-generated from header, but editable)
    const [lines, setLines] = useState<JournalLine[]>([
        { id: '1', account_label: 'TSA Cash Account', account_code: '31100100', debit: '', credit: '', narration: 'Revenue received into TSA' },
        { id: '2', account_label: 'Revenue Account', account_code: '', debit: '', credit: '', narration: 'IGR revenue recognized' },
    ]);

    const set = (field: string, value: string) => setForm(prev => ({ ...prev, [field]: value }));

    // Auto-update journal lines when amount or revenue head changes
    const selectedHead = revenueHeads?.find((r: any) => String(r.id) === form.revenue_head);
    const selectedTSA = (tsaAccounts || []).find((a: any) => String(a.id) === form.tsa_account);

    // Compute totals
    const totalDebit = useMemo(() => lines.reduce((s, l) => s + (parseFloat(l.debit) || 0), 0), [lines]);
    const totalCredit = useMemo(() => lines.reduce((s, l) => s + (parseFloat(l.credit) || 0), 0), [lines]);
    const isBalanced = Math.abs(totalDebit - totalCredit) < 0.01 && totalDebit > 0;

    // Auto-populate lines from amount
    const autoPopulateLines = (amount: string) => {
        const amt = amount || '';
        setLines(prev => [
            { ...prev[0], debit: amt, credit: '', account_label: selectedTSA ? `TSA: ${selectedTSA.account_name}` : 'TSA Cash Account', account_code: '31100100' },
            { ...prev[1], debit: '', credit: amt, account_label: selectedHead ? `Revenue: ${selectedHead.name}` : 'Revenue Account', account_code: selectedHead?.ncoa_economic_code || '' },
            ...prev.slice(2),
        ]);
    };

    const updateLine = (index: number, field: keyof JournalLine, value: string) => {
        setLines(prev => prev.map((l, i) => i === index ? { ...l, [field]: value } : l));
    };

    const addLine = () => {
        setLines(prev => [...prev, {
            id: String(Date.now()), account_label: '', account_code: '', debit: '', credit: '', narration: '',
        }]);
    };

    const removeLine = (index: number) => {
        if (lines.length <= 2) return; // Minimum 2 lines for double-entry
        setLines(prev => prev.filter((_, i) => i !== index));
    };

    const handleAmountChange = (value: string) => {
        set('amount', value);
        autoPopulateLines(value);
    };

    const handleRevenueHeadChange = (value: string) => {
        set('revenue_head', value);
        const head = revenueHeads?.find((r: any) => String(r.id) === value);
        setLines(prev => prev.map((l, i) =>
            i === 1 ? { ...l, account_label: head ? `Revenue: ${head.name}` : 'Revenue Account', account_code: head?.ncoa_economic_code || '' } : l
        ));
    };

    const handleTSAChange = (value: string) => {
        set('tsa_account', value);
        const tsa = (tsaAccounts || []).find((a: any) => String(a.id) === value);
        setLines(prev => prev.map((l, i) =>
            i === 0 ? { ...l, account_label: tsa ? `TSA: ${tsa.account_name}` : 'TSA Cash Account' } : l
        ));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        if (!isBalanced) {
            setFormError(`Journal entry is not balanced. Debit: ${fmtNGN(totalDebit)}, Credit: ${fmtNGN(totalCredit)}`);
            return;
        }

        // Resolve NCoA code
        let ncoaCodeId: number | null = null;
        if (form.admin_code && form.economic_code && form.functional_code &&
            form.programme_code && form.fund_code && form.geo_code) {
            try {
                const { data } = await apiClient.post('/accounting/ncoa/codes/resolve/', {
                    admin_code: form.admin_code, economic_code: form.economic_code,
                    functional_code: form.functional_code, programme_code: form.programme_code,
                    fund_code: form.fund_code, geo_code: form.geo_code,
                });
                ncoaCodeId = data.id;
            } catch (err: any) {
                setFormError(err.response?.data?.error || 'Failed to resolve NCoA code');
                return;
            }
        } else {
            setFormError('Please select all 6 NCoA segments');
            return;
        }

        const payload: Record<string, unknown> = {
            revenue_head: parseInt(form.revenue_head) || null,
            collection_channel: form.collection_channel,
            collection_date: form.collection_date || null,
            amount: form.amount,
            payment_reference: form.payment_reference,
            rrr: form.rrr,
            payer_name: form.payer_name, payer_tin: form.payer_tin,
            payer_phone: form.payer_phone, payer_address: form.payer_address,
            ncoa_code: ncoaCodeId,
            tsa_account: parseInt(form.tsa_account) || null,
            period_month: parseInt(form.period_month) || null,
            period_year: parseInt(form.period_year) || null,
            description: form.description,
        };

        try {
            await createRevenue.mutateAsync(payload);
            navigate('/accounting/revenue-collections');
        } catch (err: any) {
            const d = err.response?.data;
            if (d?.detail) setFormError(d.detail);
            else if (d && typeof d === 'object') {
                const msgs = Object.entries(d).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`);
                setFormError(msgs.join(' | '));
            } else setFormError(err.message || 'Failed to create');
        }
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader title="Revenue Collection Entry" subtitle="Record IGR revenue with mandatory double-entry journal posting" icon={<BookOpen size={22} />} />

                {formError && (
                    <div style={{ padding: '10px 14px', borderRadius: '8px', marginBottom: '14px', background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}>
                        <AlertCircle size={14} /> {formError}
                    </div>
                )}

                <form onSubmit={handleSubmit}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                        {/* Left Column: Revenue + Payer */}
                        <div>
                            <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                                <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>Revenue Details</h3>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                                    <div style={{ gridColumn: '1 / -1' }}>
                                        <label style={lblStyle}>Revenue Head * <span style={{ fontWeight: 400, textTransform: 'none', color: '#94a3b8' }}>(what you're collecting)</span></label>
                                        <select style={selectStyle} required value={form.revenue_head} onChange={e => handleRevenueHeadChange(e.target.value)}>
                                            <option value="">Select revenue head...</option>
                                            {(revenueHeads || []).map((r: any) => <option key={r.id} value={r.id}>{r.code} - {r.name}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={lblStyle}>Amount (NGN) *</label>
                                        <input style={{ ...inputStyle, fontSize: '16px', fontWeight: 700 }} type="number" step="0.01" min="0.01" required value={form.amount} onChange={e => handleAmountChange(e.target.value)} placeholder="0.00" />
                                    </div>
                                    <div>
                                        <label style={lblStyle}>Collection Date *</label>
                                        <input style={inputStyle} type="date" required value={form.collection_date} onChange={e => set('collection_date', e.target.value)} />
                                    </div>
                                    <div>
                                        <label style={lblStyle}>Channel</label>
                                        <select style={selectStyle} value={form.collection_channel} onChange={e => set('collection_channel', e.target.value)}>
                                            {COLLECTION_CHANNELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={lblStyle}>Payment Ref / Teller No.</label>
                                        <input style={inputStyle} value={form.payment_reference} onChange={e => set('payment_reference', e.target.value)} placeholder="Bank teller number" />
                                    </div>
                                    <div>
                                        <label style={lblStyle}>RRR (Remita)</label>
                                        <input style={inputStyle} value={form.rrr} onChange={e => set('rrr', e.target.value)} placeholder="Remita reference" />
                                    </div>
                                    <div>
                                        <label style={lblStyle}>TSA Account *</label>
                                        <select style={selectStyle} required value={form.tsa_account} onChange={e => handleTSAChange(e.target.value)}>
                                            <option value="">Select TSA...</option>
                                            {(tsaAccounts || []).map((a: any) => <option key={a.id} value={a.id}>{a.account_number} - {a.account_name}</option>)}
                                        </select>
                                    </div>
                                </div>
                            </div>

                            <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                                <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>Payer Information</h3>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                                    <div><label style={lblStyle}>Payer Name *</label><input style={inputStyle} required value={form.payer_name} onChange={e => set('payer_name', e.target.value)} placeholder="Full name" /></div>
                                    <div><label style={lblStyle}>Payer TIN</label><input style={inputStyle} value={form.payer_tin} onChange={e => set('payer_tin', e.target.value)} placeholder="Tax ID" /></div>
                                    <div><label style={lblStyle}>Phone</label><input style={inputStyle} value={form.payer_phone} onChange={e => set('payer_phone', e.target.value)} /></div>
                                    <div><label style={lblStyle}>Period</label>
                                        <div style={{ display: 'flex', gap: 6 }}>
                                            <select style={{ ...selectStyle, flex: 1 }} value={form.period_month} onChange={e => set('period_month', e.target.value)}>
                                                <option value="">Month</option>
                                                {MONTHS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                            </select>
                                            <input style={{ ...inputStyle, width: 80 }} type="number" min="2020" max="2099" value={form.period_year} onChange={e => set('period_year', e.target.value)} placeholder="Year" />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Right Column: NCoA + Journal Lines */}
                        <div>
                            <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                                <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>NCoA Classification</h3>
                                {segsLoading ? <div style={{ color: '#94a3b8', fontSize: 13 }}>Loading...</div> : (
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                                        <div><label style={lblStyle}>MDA *</label>
                                            <select style={selectStyle} required value={form.admin_code} onChange={e => set('admin_code', e.target.value)}>
                                                <option value="">Select...</option>
                                                {segments?.administrative?.map((s: any) => <option key={s.code} value={s.code}>{s.code} - {s.name}</option>)}
                                            </select>
                                        </div>
                                        <div><label style={lblStyle}>Economic *</label>
                                            <select style={selectStyle} required value={form.economic_code} onChange={e => set('economic_code', e.target.value)}>
                                                <option value="">Select...</option>
                                                {segments?.economic?.map((s: any) => <option key={s.code} value={s.code}>{s.code} - {s.name}</option>)}
                                            </select>
                                        </div>
                                        <div><label style={lblStyle}>Function *</label>
                                            <select style={selectStyle} required value={form.functional_code} onChange={e => set('functional_code', e.target.value)}>
                                                <option value="">Select...</option>
                                                {segments?.functional?.map((s: any) => <option key={s.code} value={s.code}>{s.code} - {s.name}</option>)}
                                            </select>
                                        </div>
                                        <div><label style={lblStyle}>Programme *</label>
                                            <select style={selectStyle} required value={form.programme_code} onChange={e => set('programme_code', e.target.value)}>
                                                <option value="">Select...</option>
                                                {segments?.programme?.map((s: any) => <option key={s.code} value={s.code}>{s.code} - {s.name}</option>)}
                                            </select>
                                        </div>
                                        <div><label style={lblStyle}>Fund *</label>
                                            <select style={selectStyle} required value={form.fund_code} onChange={e => set('fund_code', e.target.value)}>
                                                <option value="">Select...</option>
                                                {segments?.fund?.map((s: any) => <option key={s.code} value={s.code}>{s.code} - {s.name}</option>)}
                                            </select>
                                        </div>
                                        <div><label style={lblStyle}>Geographic *</label>
                                            <select style={selectStyle} required value={form.geo_code} onChange={e => set('geo_code', e.target.value)}>
                                                <option value="">Select...</option>
                                                {segments?.geographic?.map((s: any) => <option key={s.code} value={s.code}>{s.code} - {s.name}</option>)}
                                            </select>
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Journal Entry Lines — the core double-entry */}
                            <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem', border: '2px solid #c7d2fe' }}>
                                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: '#4338ca', margin: '0 0 1rem 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    <BookOpen size={16} /> Journal Entry Lines
                                    <span style={{ fontWeight: 400, fontSize: 11, color: '#94a3b8', marginLeft: 'auto' }}>
                                        Mandatory double-entry
                                    </span>
                                </div>

                                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                                    <thead>
                                        <tr style={{ background: '#eef2ff' }}>
                                            <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, color: '#4338ca', fontSize: 10, textTransform: 'uppercase' }}>Account</th>
                                            <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 600, color: '#4338ca', fontSize: 10, textTransform: 'uppercase', width: 110 }}>Debit (NGN)</th>
                                            <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 600, color: '#4338ca', fontSize: 10, textTransform: 'uppercase', width: 110 }}>Credit (NGN)</th>
                                            <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, color: '#4338ca', fontSize: 10, textTransform: 'uppercase' }}>Narration</th>
                                            <th style={{ width: 32 }}></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {lines.map((line, idx) => (
                                            <tr key={line.id} style={{ borderBottom: '1px solid #e8ecf1' }}>
                                                <td style={{ padding: '6px 8px' }}>
                                                    <div style={{ fontSize: 12, fontWeight: 600, color: '#1e293b' }}>{line.account_label || '(Select account)'}</div>
                                                    {line.account_code && <div style={{ fontSize: 10, color: '#94a3b8', fontFamily: 'monospace' }}>{line.account_code}</div>}
                                                </td>
                                                <td style={{ padding: '6px 4px' }}>
                                                    <input style={{ ...inputStyle, textAlign: 'right', padding: '6px 8px', fontSize: 13, fontWeight: 600, background: line.debit ? '#f0fdf4' : '#fff' }}
                                                        type="number" step="0.01" min="0" placeholder="0.00"
                                                        value={line.debit} onChange={e => updateLine(idx, 'debit', e.target.value)} />
                                                </td>
                                                <td style={{ padding: '6px 4px' }}>
                                                    <input style={{ ...inputStyle, textAlign: 'right', padding: '6px 8px', fontSize: 13, fontWeight: 600, background: line.credit ? '#fef2f2' : '#fff' }}
                                                        type="number" step="0.01" min="0" placeholder="0.00"
                                                        value={line.credit} onChange={e => updateLine(idx, 'credit', e.target.value)} />
                                                </td>
                                                <td style={{ padding: '6px 4px' }}>
                                                    <input style={{ ...inputStyle, padding: '6px 8px', fontSize: 12 }}
                                                        value={line.narration} onChange={e => updateLine(idx, 'narration', e.target.value)} placeholder="Line memo" />
                                                </td>
                                                <td style={{ padding: '6px 2px' }}>
                                                    {lines.length > 2 && (
                                                        <button type="button" onClick={() => removeLine(idx)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: 2 }}>
                                                            <Trash2 size={13} />
                                                        </button>
                                                    )}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                    <tfoot>
                                        <tr style={{ borderTop: '2px solid #c7d2fe' }}>
                                            <td style={{ padding: '8px 10px', fontWeight: 700, fontSize: 12, color: '#1e293b' }}>
                                                Total
                                                <button type="button" onClick={addLine} style={{
                                                    marginLeft: 10, background: 'none', border: '1px dashed #94a3b8',
                                                    borderRadius: 4, padding: '2px 8px', fontSize: 10, color: '#64748b',
                                                    cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 3,
                                                }}>
                                                    <Plus size={10} /> Add Line
                                                </button>
                                            </td>
                                            <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 700, fontSize: 13, color: '#166534' }}>
                                                {fmtNGN(totalDebit)}
                                            </td>
                                            <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 700, fontSize: 13, color: '#dc2626' }}>
                                                {fmtNGN(totalCredit)}
                                            </td>
                                            <td style={{ padding: '8px 10px' }}>
                                                {isBalanced ? (
                                                    <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#166534', fontSize: 11, fontWeight: 600 }}>
                                                        <CheckCircle2 size={13} /> Balanced
                                                    </span>
                                                ) : totalDebit > 0 || totalCredit > 0 ? (
                                                    <span style={{ color: '#dc2626', fontSize: 11, fontWeight: 600 }}>
                                                        Difference: {fmtNGN(Math.abs(totalDebit - totalCredit))}
                                                    </span>
                                                ) : (
                                                    <span style={{ color: '#94a3b8', fontSize: 11 }}>Enter amounts above</span>
                                                )}
                                            </td>
                                            <td></td>
                                        </tr>
                                    </tfoot>
                                </table>
                            </div>

                            {/* Description */}
                            <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                                <label style={lblStyle}>Narration / Description</label>
                                <textarea style={{ ...inputStyle, minHeight: '50px' }} value={form.description} onChange={e => set('description', e.target.value)} placeholder="Revenue collection description..." />
                            </div>
                        </div>
                    </div>

                    {/* Submit Row */}
                    <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '8px' }}>
                        <button type="button" onClick={() => navigate(-1)} className="glass-button" style={{
                            padding: '10px 20px', borderRadius: '8px', border: '1px solid var(--color-border)',
                            background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                        }}>
                            Cancel
                        </button>
                        <button type="submit" disabled={createRevenue.isPending || !isBalanced} style={{
                            padding: '10px 24px', borderRadius: '8px', border: 'none',
                            background: isBalanced ? 'linear-gradient(135deg, var(--primary, #191e6a) 0%, var(--primary-dark, #0f1240) 100%)' : '#94a3b8', color: '#fff',
                            fontSize: '13px', fontWeight: 600, cursor: isBalanced ? 'pointer' : 'not-allowed',
                            display: 'flex', alignItems: 'center', gap: '6px',
                            opacity: createRevenue.isPending ? 0.7 : 1,
                            boxShadow: isBalanced ? '0 4px 12px rgba(15, 18, 64, 0.3)' : 'none',
                        }}>
                            <Save size={14} />
                            {createRevenue.isPending ? 'Posting...' : 'Post Revenue Entry'}
                        </button>
                    </div>
                </form>
            </main>
        </div>
    );
}
