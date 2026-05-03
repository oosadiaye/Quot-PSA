/**
 * Revenue Collection (IGR) — Journal-Style Entry — Quot PSE
 * Route: /accounting/revenue-collections/new
 *
 * Redesigned to match the Journal Entry layout:
 *   - Header row (Collection Date, Reference, Narration)
 *   - Mandatory NCoA dimensions (MDA, Fund, Function, Program, Geo)
 *   - GL Journal lines (real Account FK pickers) with Dr/Cr balance check
 *   - Collapsible optional Payer / Period card
 *   - Single Post button
 *
 * The old "Revenue Head *" field is intentionally removed — the
 * second (credit) line of the journal IS the revenue GL account, so
 * keeping a separate Revenue Head dropdown caused the user to enter
 * the same information twice. The GL account on the credit line is
 * the single source of truth for which revenue is being collected.
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Save, AlertCircle, Plus, Trash2, CheckCircle2, BookOpen, ChevronDown, ChevronUp, User,
} from 'lucide-react';
import apiClient from '../../api/client';
import AccountingLayout from '../../features/accounting/AccountingLayout';
import PageHeader from '../../components/PageHeader';
import {
    useCreateRevenueCollection, useNCoASegments, useTSAAccounts,
} from '../../hooks/useGovForms';
import { useAccounts, useMDAs } from '../../features/accounting/hooks/useBudgetDimensions';
import { useFunds, useFunctions, usePrograms, useGeos } from '../../features/accounting/hooks/useDimensions';

const COLLECTION_CHANNELS: Array<[string, string]> = [
    ['BANK', 'Bank Deposit'],
    ['ONLINE', 'Online Payment'],
    ['USSD', 'USSD'],
    ['AGENT', 'Collection Agent'],
    ['COUNTER', 'Counter'],
    ['POS', 'POS Terminal'],
];

const MONTHS = Array.from({ length: 12 }, (_, i): [string, string] => [
    String(i + 1), new Date(2000, i).toLocaleString('en', { month: 'long' }),
]);

const fmtNGN = (v: number): string =>
    v ? '\u20A6' + v.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '\u20A60.00';

interface JournalLine {
    id: string;
    account: string;    // Account FK id
    debit: string;
    credit: string;
    memo: string;
}

/**
 * A minimal "new line" shape. The form opens with exactly two rows:
 * Dr cash/TSA and Cr revenue, both blank — the user picks the accounts
 * and amounts directly (same as the Journal Entry form).
 */
const newLine = (): JournalLine => ({
    id: `l-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    account: '',
    debit: '',
    credit: '',
    memo: '',
});

export default function RevenueCollectionForm() {
    const navigate = useNavigate();
    const createRevenue = useCreateRevenueCollection();

    // Dimension data
    const { data: segments, isLoading: segsLoading } = useNCoASegments();
    const { data: tsaAccounts = [] } = useTSAAccounts();
    const { data: mdas = [] } = useMDAs({ is_active: true });
    const { data: funds = [] } = useFunds();
    const { data: functionsList = [] } = useFunctions();
    const { data: programs = [] } = usePrograms();
    const { data: geos = [] } = useGeos();
    const { data: accounts = [] } = useAccounts({ is_active: true });

    const [formError, setFormError] = useState('');
    const [showPayer, setShowPayer] = useState(false);

    // Header
    const [header, setHeader] = useState({
        collection_date: new Date().toISOString().split('T')[0],
        payment_reference: '',
        rrr: '',
        description: '',
        collection_channel: 'BANK',
        tsa_account: '',
        // NCoA 6-segment control (the mandatory dimensions)
        admin_code: '',
        economic_code: '',
        functional_code: '',
        programme_code: '',
        fund_code: '',
        geo_code: '',
        // Optional payer + period
        payer_name: '',
        payer_tin: '',
        payer_phone: '',
        payer_address: '',
        period_month: '',
        period_year: '',
    });

    const setH = (field: string, value: string) =>
        setHeader((prev) => ({ ...prev, [field]: value }));

    // Journal lines — double-entry. Seeded as 2 empty rows: Dr Cash/TSA | Cr Revenue.
    const [lines, setLines] = useState<JournalLine[]>([newLine(), newLine()]);
    const updateLine = (idx: number, field: keyof JournalLine, value: string) =>
        setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, [field]: value } : l)));
    const addLine = () => setLines((prev) => [...prev, newLine()]);
    const removeLine = (idx: number) => {
        if (lines.length <= 2) return;
        setLines((prev) => prev.filter((_, i) => i !== idx));
    };

    // Totals
    const totalDebit = useMemo(
        () => lines.reduce((s, l) => s + (parseFloat(l.debit) || 0), 0),
        [lines],
    );
    const totalCredit = useMemo(
        () => lines.reduce((s, l) => s + (parseFloat(l.credit) || 0), 0),
        [lines],
    );
    const isBalanced = Math.abs(totalDebit - totalCredit) < 0.01 && totalDebit > 0;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        if (!isBalanced) {
            setFormError(
                `Journal is not balanced. Debit: ${fmtNGN(totalDebit)}, Credit: ${fmtNGN(totalCredit)}.`,
            );
            return;
        }
        if (lines.some((l) => !l.account)) {
            setFormError('Every journal line must have a GL account selected.');
            return;
        }

        // Resolve the 6-segment NCoA composite id (required by the
        // backend so revenue gets the full classification).
        const required = [
            header.admin_code, header.economic_code, header.functional_code,
            header.programme_code, header.fund_code, header.geo_code,
        ];
        if (required.some((v) => !v)) {
            setFormError('Please select all 6 NCoA segments (MDA, Economic, Function, Program, Fund, Geo).');
            return;
        }
        let ncoaCodeId: number | null = null;
        try {
            const { data } = await apiClient.post('/accounting/ncoa/codes/resolve/', {
                admin_code: header.admin_code,
                economic_code: header.economic_code,
                functional_code: header.functional_code,
                programme_code: header.programme_code,
                fund_code: header.fund_code,
                geo_code: header.geo_code,
            });
            ncoaCodeId = data.id;
        } catch (err: any) {
            setFormError(err?.response?.data?.error || 'Failed to resolve NCoA code');
            return;
        }

        // Primary credit line = the revenue account being recognised.
        // Backend expects a revenue_head or an economic_code; we send
        // the economic_code from the NCoA dimensions (already captured).
        const totalAmount = totalCredit.toFixed(2);

        const payload: Record<string, unknown> = {
            collection_channel: header.collection_channel,
            collection_date: header.collection_date || null,
            amount: totalAmount,
            payment_reference: header.payment_reference,
            rrr: header.rrr,
            payer_name: header.payer_name,
            payer_tin: header.payer_tin,
            payer_phone: header.payer_phone,
            payer_address: header.payer_address,
            ncoa_code: ncoaCodeId,
            tsa_account: parseInt(header.tsa_account) || null,
            period_month: parseInt(header.period_month) || null,
            period_year: parseInt(header.period_year) || null,
            description: header.description,
            // Journal lines forwarded raw so the backend can mirror
            // the posting onto its own JournalHeader / JournalLine.
            journal_lines: lines.map((l) => ({
                account: parseInt(l.account),
                debit: parseFloat(l.debit) || 0,
                credit: parseFloat(l.credit) || 0,
                memo: l.memo,
            })),
        };

        try {
            await createRevenue.mutateAsync(payload);
            navigate('/accounting/revenue-collections');
        } catch (err: any) {
            const d = err?.response?.data;
            if (d?.detail) setFormError(d.detail);
            else if (d && typeof d === 'object') {
                setFormError(
                    Object.entries(d)
                        .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
                        .join(' | '),
                );
            } else setFormError(err?.message || 'Failed to create');
        }
    };

    return (
        <AccountingLayout>
            <PageHeader
                title="Revenue Collection Entry"
                subtitle="Record IGR revenue as a balanced GL journal (Dr Cash/TSA / Cr Revenue)"
                icon={<BookOpen size={22} />}
            />

            {formError && (
                <div style={{
                    padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626',
                    borderRadius: 8, marginBottom: '1.5rem', fontSize: 'var(--text-sm)',
                    display: 'flex', alignItems: 'center', gap: 8,
                }}>
                    <AlertCircle size={16} /> {formError}
                </div>
            )}

            <form onSubmit={handleSubmit}>
                {/* ── Header fields ───────────────────────────────── */}
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: '1.5rem', marginBottom: '2rem',
                }}>
                    <div className="card">
                        <label className="label">Collection Date<span className="required-mark"> *</span></label>
                        <input type="date" required
                            value={header.collection_date}
                            onChange={(e) => setH('collection_date', e.target.value)}
                        />
                    </div>
                    <div className="card">
                        <label className="label">Channel</label>
                        <select value={header.collection_channel}
                            onChange={(e) => setH('collection_channel', e.target.value)}>
                            {COLLECTION_CHANNELS.map(([v, l]) => (
                                <option key={v} value={v}>{l}</option>
                            ))}
                        </select>
                    </div>
                    <div className="card">
                        <label className="label">Payment Ref / Teller</label>
                        <input type="text"
                            placeholder="Bank teller / confirmation"
                            value={header.payment_reference}
                            onChange={(e) => setH('payment_reference', e.target.value)}
                        />
                    </div>
                    <div className="card">
                        <label className="label">RRR (Remita)</label>
                        <input type="text"
                            placeholder="Remita reference"
                            value={header.rrr}
                            onChange={(e) => setH('rrr', e.target.value)}
                        />
                    </div>
                    <div className="card">
                        <label className="label">TSA Account<span className="required-mark"> *</span></label>
                        <select required value={header.tsa_account}
                            onChange={(e) => setH('tsa_account', e.target.value)}>
                            <option value="">Select TSA...</option>
                            {(tsaAccounts as any[]).map((a: any) => (
                                <option key={a.id} value={a.id}>
                                    {a.account_number} - {a.account_name}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div className="card" style={{ gridColumn: 'span 2' }}>
                        <label className="label">Narration / Description<span className="required-mark"> *</span></label>
                        <input type="text" required
                            placeholder="Purpose of this collection"
                            value={header.description}
                            onChange={(e) => setH('description', e.target.value)}
                        />
                    </div>
                </div>

                {/* ── Mandatory NCoA Dimensions ───────────────────── */}
                <div className="card" style={{ marginBottom: '2rem' }}>
                    <h3 style={{ marginBottom: '1rem', fontSize: 'var(--text-base)' }}>
                        NCoA Classification <span style={{ fontSize: 12, fontWeight: 400, color: '#94a3b8' }}>(all 6 segments required)</span>
                    </h3>
                    {segsLoading ? (
                        <div style={{ color: '#94a3b8', fontSize: 13 }}>Loading NCoA segments...</div>
                    ) : (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
                            <div>
                                <label className="label">MDA (Admin)<span className="required-mark"> *</span></label>
                                <select required value={header.admin_code}
                                    onChange={(e) => setH('admin_code', e.target.value)}>
                                    <option value="">Select...</option>
                                    {segments?.administrative?.map((s: any) => (
                                        <option key={s.code} value={s.code}>{s.code} - {s.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="label">Economic (Revenue Head)<span className="required-mark"> *</span></label>
                                <select required value={header.economic_code}
                                    onChange={(e) => setH('economic_code', e.target.value)}>
                                    <option value="">Select...</option>
                                    {segments?.economic?.map((s: any) => (
                                        <option key={s.code} value={s.code}>{s.code} - {s.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="label">Function (COFOG)<span className="required-mark"> *</span></label>
                                <select required value={header.functional_code}
                                    onChange={(e) => setH('functional_code', e.target.value)}>
                                    <option value="">Select...</option>
                                    {segments?.functional?.map((s: any) => (
                                        <option key={s.code} value={s.code}>{s.code} - {s.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="label">Programme<span className="required-mark"> *</span></label>
                                <select required value={header.programme_code}
                                    onChange={(e) => setH('programme_code', e.target.value)}>
                                    <option value="">Select...</option>
                                    {segments?.programme?.map((s: any) => (
                                        <option key={s.code} value={s.code}>{s.code} - {s.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="label">Fund<span className="required-mark"> *</span></label>
                                <select required value={header.fund_code}
                                    onChange={(e) => setH('fund_code', e.target.value)}>
                                    <option value="">Select...</option>
                                    {segments?.fund?.map((s: any) => (
                                        <option key={s.code} value={s.code}>{s.code} - {s.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="label">Geographic<span className="required-mark"> *</span></label>
                                <select required value={header.geo_code}
                                    onChange={(e) => setH('geo_code', e.target.value)}>
                                    <option value="">Select...</option>
                                    {segments?.geographic?.map((s: any) => (
                                        <option key={s.code} value={s.code}>{s.code} - {s.name}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    )}
                </div>

                {/* ── GL Journal Lines (double-entry, Journal-style) ── */}
                <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: '2rem' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--background)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>GL Account</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: 150, textAlign: 'right' }}>Debit (NGN)</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: 150, textAlign: 'right' }}>Credit (NGN)</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Memo</th>
                                <th style={{ padding: '1rem', width: 50 }}></th>
                            </tr>
                        </thead>
                        <tbody>
                            {lines.map((line, idx) => (
                                <tr key={line.id} style={{ borderBottom: '1px solid var(--border)' }}>
                                    <td style={{ padding: '0.5rem 0.75rem' }}>
                                        <select required
                                            value={line.account}
                                            onChange={(e) => updateLine(idx, 'account', e.target.value)}
                                            style={{ width: '100%' }}
                                        >
                                            <option value="">Select Account...</option>
                                            {(accounts as any[]).map((a: any) => (
                                                <option key={a.id} value={a.id}>
                                                    {a.code} — {a.name}
                                                </option>
                                            ))}
                                        </select>
                                    </td>
                                    <td style={{ padding: '0.5rem 0.5rem' }}>
                                        <input type="number" step="0.01" min="0"
                                            value={line.debit}
                                            onChange={(e) => updateLine(idx, 'debit', e.target.value)}
                                            placeholder="0.00"
                                            style={{
                                                width: '100%', textAlign: 'right',
                                                background: line.debit ? '#f0fdf4' : '#fff',
                                                fontWeight: 600,
                                            }}
                                        />
                                    </td>
                                    <td style={{ padding: '0.5rem 0.5rem' }}>
                                        <input type="number" step="0.01" min="0"
                                            value={line.credit}
                                            onChange={(e) => updateLine(idx, 'credit', e.target.value)}
                                            placeholder="0.00"
                                            style={{
                                                width: '100%', textAlign: 'right',
                                                background: line.credit ? '#fef2f2' : '#fff',
                                                fontWeight: 600,
                                            }}
                                        />
                                    </td>
                                    <td style={{ padding: '0.5rem 0.5rem' }}>
                                        <input type="text"
                                            placeholder="Line memo"
                                            value={line.memo}
                                            onChange={(e) => updateLine(idx, 'memo', e.target.value)}
                                            style={{ width: '100%' }}
                                        />
                                    </td>
                                    <td style={{ padding: '0.5rem', textAlign: 'center' }}>
                                        {lines.length > 2 && (
                                            <button type="button" onClick={() => removeLine(idx)}
                                                style={{
                                                    background: 'none', border: 'none', cursor: 'pointer',
                                                    color: '#ef4444', padding: 4,
                                                }}
                                            >
                                                <Trash2 size={16} />
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                        <tfoot>
                            <tr style={{ borderTop: '2px solid var(--border)', background: '#f8fafc' }}>
                                <td style={{ padding: '0.75rem 1rem' }}>
                                    <button type="button" onClick={addLine}
                                        style={{
                                            background: 'none', border: '1px dashed #94a3b8',
                                            borderRadius: 6, padding: '4px 10px', fontSize: 12,
                                            color: '#64748b', cursor: 'pointer',
                                            display: 'inline-flex', alignItems: 'center', gap: 4,
                                        }}
                                    >
                                        <Plus size={12} /> Add Line
                                    </button>
                                </td>
                                <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 700, color: '#166534' }}>
                                    {fmtNGN(totalDebit)}
                                </td>
                                <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 700, color: '#dc2626' }}>
                                    {fmtNGN(totalCredit)}
                                </td>
                                <td colSpan={2} style={{ padding: '0.75rem 1rem' }}>
                                    {isBalanced ? (
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: '#166534', fontSize: 12, fontWeight: 600 }}>
                                            <CheckCircle2 size={14} /> Balanced
                                        </span>
                                    ) : totalDebit > 0 || totalCredit > 0 ? (
                                        <span style={{ color: '#dc2626', fontSize: 12, fontWeight: 600 }}>
                                            Out of balance by {fmtNGN(Math.abs(totalDebit - totalCredit))}
                                        </span>
                                    ) : (
                                        <span style={{ color: '#94a3b8', fontSize: 12 }}>
                                            Enter amounts above
                                        </span>
                                    )}
                                </td>
                            </tr>
                        </tfoot>
                    </table>
                </div>

                {/* ── Optional Payer / Period card (collapsible) ─── */}
                <div className="card" style={{ marginBottom: '2rem' }}>
                    <button type="button"
                        onClick={() => setShowPayer((v) => !v)}
                        style={{
                            width: '100%', background: 'none', border: 'none', cursor: 'pointer',
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            padding: 0, color: 'var(--color-text)', fontSize: 'var(--text-base)',
                            fontWeight: 600,
                        }}
                    >
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                            <User size={16} /> Payer Details
                            <span style={{ fontSize: 12, fontWeight: 400, color: '#94a3b8' }}>(optional)</span>
                        </span>
                        {showPayer ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                    </button>
                    {showPayer && (
                        <div style={{
                            marginTop: '1rem',
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                            gap: '1rem',
                        }}>
                            <div>
                                <label className="label">Payer Name</label>
                                <input type="text"
                                    placeholder="Full name"
                                    value={header.payer_name}
                                    onChange={(e) => setH('payer_name', e.target.value)}
                                />
                            </div>
                            <div>
                                <label className="label">Payer TIN</label>
                                <input type="text"
                                    placeholder="Tax identification"
                                    value={header.payer_tin}
                                    onChange={(e) => setH('payer_tin', e.target.value)}
                                />
                            </div>
                            <div>
                                <label className="label">Phone</label>
                                <input type="text"
                                    value={header.payer_phone}
                                    onChange={(e) => setH('payer_phone', e.target.value)}
                                />
                            </div>
                            <div>
                                <label className="label">Address</label>
                                <input type="text"
                                    value={header.payer_address}
                                    onChange={(e) => setH('payer_address', e.target.value)}
                                />
                            </div>
                            <div>
                                <label className="label">Period Month</label>
                                <select value={header.period_month}
                                    onChange={(e) => setH('period_month', e.target.value)}>
                                    <option value="">—</option>
                                    {MONTHS.map(([v, l]) => (
                                        <option key={v} value={v}>{l}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="label">Period Year</label>
                                <input type="number" min="2020" max="2099"
                                    placeholder="e.g. 2026"
                                    value={header.period_year}
                                    onChange={(e) => setH('period_year', e.target.value)}
                                />
                            </div>
                        </div>
                    )}
                </div>

                {/* ── Actions ──────────────────────────────────── */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                    <button type="button" onClick={() => navigate(-1)}
                        className="btn btn-outline"
                        style={{ padding: '10px 20px' }}
                    >
                        Cancel
                    </button>
                    <button type="submit"
                        disabled={createRevenue.isPending || !isBalanced}
                        className="btn btn-primary"
                        style={{
                            padding: '10px 24px', opacity: (!isBalanced || createRevenue.isPending) ? 0.5 : 1,
                            display: 'inline-flex', alignItems: 'center', gap: 6,
                        }}
                    >
                        <Save size={14} />
                        {createRevenue.isPending ? 'Posting...' : 'Post Revenue Entry'}
                    </button>
                </div>
            </form>
        </AccountingLayout>
    );
}
