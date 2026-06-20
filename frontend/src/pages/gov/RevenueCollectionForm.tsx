/**
 * Revenue Collection (IGR) — Journal-Style Entry — Quot PSE
 * Route: /accounting/revenue-collections/new
 *
 * Lean Journal-style layout:
 *   - Header: Collection Date, MDA (Admin), Narration
 *   - NCoA panel: Function, Programme, Fund, Geographic (4 segments)
 *   - GL Journal lines (TSA picker + Account FK pickers, Dr/Cr balance)
 *   - Collapsible Payer / Period card
 *   - Single Post button
 *
 * What is DERIVED (not user-entered):
 *   - economic_code: comes from the credit line's GL account code
 *     (NCoA economic segment == GL account code in this CoA).
 *   - tsa_account (header): comes from the first TSA-tagged line.
 *   - collection_channel: defaults to 'BANK' in initial state.
 *
 * What is REMOVED from the UI (vs older versions):
 *   - Channel / Payment Ref / RRR / TSA Account header cards
 *   - Economic (Revenue Head) dropdown in NCoA panel (now derived)
 *   - MDA in NCoA panel (promoted to header — mandatory cannot live
 *     inside an "all 6 required" group when 1 of them is special).
 */
import { useEffect, useMemo, useState } from 'react';
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

const MONTHS = Array.from({ length: 12 }, (_, i): [string, string] => [
    String(i + 1), new Date(2000, i).toLocaleString('en', { month: 'long' }),
]);

const fmtNGN = (v: number): string =>
    v ? '\u20A6' + v.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '\u20A60.00';

/**
 * A row in the revenue journal-entry table.
 *
 * ``tsa_account`` is the per-line shortcut for "this line is the cash
 * inflow against this TSA". When set, ``account`` is auto-resolved to
 * the TSA's underlying ``gl_cash_account`` (driven by
 * ``TreasuryAccount.gl_cash_account`` — see backend model). This way
 * the user picks a meaningful TSA (e.g. "Main Treasury — UBA
 * 1024531234") instead of hunting through the full COA for the cash
 * GL code, and gets it right by construction. Leaving ``tsa_account``
 * blank falls back to the manual ``account`` picker — useful for the
 * credit (revenue) leg or any non-cash adjustment.
 */
interface JournalLine {
    id: string;
    tsa_account: string; // TreasuryAccount FK id (optional)
    account: string;     // Account FK id (auto-filled when tsa_account is set)
    debit: string;
    credit: string;
    memo: string;
}

interface TSAOption {
    id: number;
    account_number: string;
    account_name: string;
    gl_cash_account: number | null;
    gl_cash_account_code?: string;
    gl_cash_account_name?: string;
}

interface AccountOption {
    id: number;
    code: string;
    name: string;
}

/**
 * A minimal "new line" shape. The form opens with exactly two rows:
 * Dr cash/TSA and Cr revenue, both blank — the user picks the accounts
 * (or a TSA shortcut) and amounts directly.
 */
const newLine = (): JournalLine => ({
    id: `l-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    tsa_account: '',
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

    /**
     * Update one cell of one line. Special-cased for ``tsa_account``:
     * when the user picks a TSA on a row, we ALSO auto-fill the
     * row's ``account`` field with that TSA's underlying
     * ``gl_cash_account`` (the GL Cash account flagged on the
     * TreasuryAccount). When the user clears the TSA, we leave
     * ``account`` alone so they can manually pick a different GL.
     */
    const updateLine = (idx: number, field: keyof JournalLine, value: string): void => {
        setLines((prev) => prev.map((l, i) => {
            if (i !== idx) return l;
            if (field === 'tsa_account') {
                const tsa = (tsaAccounts as TSAOption[]).find(
                    (t) => String(t.id) === value,
                );
                const autoAccount = tsa?.gl_cash_account
                    ? String(tsa.gl_cash_account)
                    : l.account;
                return { ...l, tsa_account: value, account: autoAccount };
            }
            return { ...l, [field]: value };
        }));
    };

    const addLine = (): void => setLines((prev) => [...prev, newLine()]);
    const removeLine = (idx: number): void => {
        if (lines.length <= 2) return;
        setLines((prev) => prev.filter((_, i) => i !== idx));
    };

    /**
     * Keep the header ``tsa_account`` in sync with the journal lines.
     * The backend model stores a single TSA per RevenueCollection;
     * the first line with a TSA picked wins. If the user clears every
     * line's TSA we leave the header alone (don't auto-clear), so a
     * user who explicitly set the header field then experiments with
     * line-level TSAs won't lose it.
     */
    const derivedHeaderTsa = useMemo<string>(() => {
        const firstWithTsa = lines.find((l) => l.tsa_account);
        return firstWithTsa?.tsa_account ?? '';
    }, [lines]);
    useEffect(() => {
        if (derivedHeaderTsa && header.tsa_account !== derivedHeaderTsa) {
            setH('tsa_account', derivedHeaderTsa);
        }
    }, [derivedHeaderTsa, header.tsa_account]);

    /**
     * NCoA economic code is the same identifier as the GL account
     * code on the revenue credit line. Rather than asking the user
     * to pick it twice, derive it from the first credit-side line
     * with a GL account selected. This keeps the backend wire
     * format unchanged (the resolver still needs ``economic_code``)
     * while removing the redundant header dropdown.
     */
    const derivedEconomicCode = useMemo<string>(() => {
        const firstCreditLine = lines.find(
            (l) => (parseFloat(l.credit) || 0) > 0 && l.account,
        );
        if (!firstCreditLine) return '';
        const acct = (accounts as AccountOption[]).find(
            (a) => String(a.id) === firstCreditLine.account,
        );
        return acct?.code ?? '';
    }, [lines, accounts]);
    useEffect(() => {
        if (derivedEconomicCode && header.economic_code !== derivedEconomicCode) {
            setH('economic_code', derivedEconomicCode);
        }
    }, [derivedEconomicCode, header.economic_code]);

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

        // Cash-leg sanity. RevenueCollection.tsa_account is required on
        // the model; the form auto-syncs it from the first line that
        // picks a TSA. If NO line picked a TSA AND the header is empty,
        // tell the user up-front rather than waiting for the backend to
        // 400 with a generic ``tsa_account: This field is required.``
        const anyLineHasTsa = lines.some((l) => l.tsa_account);
        if (!anyLineHasTsa && !header.tsa_account) {
            setFormError(
                'At least one line must pick a TSA Account (the cash inflow leg). '
                + 'Use the TSA Account column to designate which line is the cash receipt.',
            );
            return;
        }

        // Double-check every TSA-tagged line is on the DEBIT side. A
        // revenue collection is a cash inflow — a TSA on a credit line
        // would imply cash leaving the TSA against revenue, which is
        // backwards. Catch the mistake before the journal hits the GL.
        const reversedTsaLine = lines.findIndex(
            (l) => l.tsa_account && (parseFloat(l.credit) || 0) > 0
                && !(parseFloat(l.debit) || 0),
        );
        if (reversedTsaLine !== -1) {
            setFormError(
                `Line ${reversedTsaLine + 1}: a TSA Account is the cash inflow `
                + `leg of revenue collection — its amount must be in the DEBIT `
                + `column, not Credit.`,
            );
            return;
        }

        // Resolve the 6-segment NCoA composite id (required by the
        // backend so revenue gets the full classification). The UI
        // collects 4 segments directly + MDA in header + economic
        // derived from the credit line GL — verify all 6 made it
        // into state before asking the backend to resolve them.
        if (!header.admin_code) {
            setFormError('Please pick an MDA (Admin) at the top of the form.');
            return;
        }
        if (!header.economic_code) {
            setFormError(
                'Economic code could not be derived from the credit line. '
                + 'Make sure the credit (revenue) line has both a GL Account and a Credit amount.',
            );
            return;
        }
        const remaining = [
            header.functional_code, header.programme_code,
            header.fund_code, header.geo_code,
        ];
        if (remaining.some((v) => !v)) {
            setFormError('Please select all NCoA segments (Function, Programme, Fund, Geographic).');
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
            // ``tsa_account`` is preserved per-line so a future backend
            // can drive multi-TSA postings directly from the form
            // without another wire-format change. The current backend
            // ignores per-line tsa and uses the header field, which
            // we've auto-synced from the first TSA-tagged line above.
            journal_lines: lines.map((l) => ({
                tsa_account: l.tsa_account ? parseInt(l.tsa_account) : null,
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
                {/* ── Header fields ─────────────────────────────────
                    Channel, Payment Ref, RRR, and TSA Account were
                    moved off the header per UX feedback. TSA Account
                    now comes exclusively from the per-line picker on
                    the journal-lines table (header.tsa_account is
                    auto-synced from the first TSA-tagged line). MDA
                    is promoted here from the NCoA panel because it
                    is mandatory and identifies "who collected" — a
                    fact that cannot be derived from any GL code. */}
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
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
                        <label className="label">MDA (Admin)<span className="required-mark"> *</span></label>
                        <select required value={header.admin_code}
                            onChange={(e) => setH('admin_code', e.target.value)}>
                            <option value="">Select MDA...</option>
                            {segments?.administrative?.map((s: any) => (
                                <option key={s.code} value={s.code}>{s.code} - {s.name}</option>
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

                {/* ── Mandatory NCoA Dimensions ─────────────────────
                    MDA was promoted to the header (mandatory, set
                    by user). Economic is derived from the credit
                    line's GL account code (see derivedEconomicCode
                    useMemo). The remaining 4 dimensions stay here. */}
                <div className="card" style={{ marginBottom: '2rem' }}>
                    <h3 style={{ marginBottom: '1rem', fontSize: 'var(--text-base)' }}>
                        NCoA Classification <span style={{ fontSize: 12, fontWeight: 400, color: '#94a3b8' }}>(Function / Programme / Fund / Geographic — all required)</span>
                    </h3>
                    {segsLoading ? (
                        <div style={{ color: '#94a3b8', fontSize: 13 }}>Loading NCoA segments...</div>
                    ) : (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
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
                                <th
                                    style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: 240 }}
                                    title="Pick a Treasury Single Account to auto-resolve this row's GL Account to the TSA's underlying cash GL. Optional — leave blank for non-cash lines (e.g. the credit revenue leg)."
                                >
                                    TSA Account <span style={{ color: '#94a3b8', fontWeight: 400 }}>(cash leg)</span>
                                </th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>GL Account</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: 150, textAlign: 'right' }}>Debit (NGN)</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: 150, textAlign: 'right' }}>Credit (NGN)</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Memo</th>
                                <th style={{ padding: '1rem', width: 50 }}></th>
                            </tr>
                        </thead>
                        <tbody>
                            {lines.map((line, idx) => {
                                // When a TSA is picked, the GL Account picker is
                                // bound to that TSA's gl_cash_account and we
                                // disable it so the user can't accidentally pick a
                                // mismatched GL. Clearing the TSA re-enables the
                                // picker and the user goes back to manual mode.
                                const tsaLocked = !!line.tsa_account;
                                const tsaForRow = (tsaAccounts as TSAOption[]).find(
                                    (t) => String(t.id) === line.tsa_account,
                                );
                                return (
                                <tr key={line.id} style={{ borderBottom: '1px solid var(--border)' }}>
                                    <td style={{ padding: '0.5rem 0.75rem' }}>
                                        <select
                                            value={line.tsa_account}
                                            onChange={(e) => updateLine(idx, 'tsa_account', e.target.value)}
                                            aria-label="Treasury Single Account for this line"
                                            style={{ width: '100%' }}
                                        >
                                            <option value="">— (manual GL) —</option>
                                            {(tsaAccounts as TSAOption[]).map((t) => (
                                                <option key={t.id} value={t.id}>
                                                    {t.account_number} — {t.account_name}
                                                </option>
                                            ))}
                                        </select>
                                        {tsaLocked && tsaForRow?.gl_cash_account_code && (
                                            <div style={{
                                                marginTop: 4, fontSize: 11, color: '#16a34a',
                                                display: 'flex', alignItems: 'center', gap: 4,
                                            }}>
                                                <CheckCircle2 size={11} />
                                                Cash GL: {tsaForRow.gl_cash_account_code}
                                                {tsaForRow.gl_cash_account_name
                                                    ? ` — ${tsaForRow.gl_cash_account_name}`
                                                    : ''}
                                            </div>
                                        )}
                                    </td>
                                    <td style={{ padding: '0.5rem 0.75rem' }}>
                                        <select required
                                            value={line.account}
                                            onChange={(e) => updateLine(idx, 'account', e.target.value)}
                                            disabled={tsaLocked}
                                            title={tsaLocked
                                                ? 'Auto-resolved from the TSA above. Clear the TSA to override.'
                                                : 'Pick a GL account directly. Use the TSA column to the left to auto-fill the cash GL.'}
                                            style={{
                                                width: '100%',
                                                background: tsaLocked ? '#f1f5f9' : '#fff',
                                                cursor: tsaLocked ? 'not-allowed' : 'pointer',
                                            }}
                                        >
                                            <option value="">Select Account...</option>
                                            {(accounts as AccountOption[]).map((a) => (
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
                                );
                            })}
                        </tbody>
                        <tfoot>
                            <tr style={{ borderTop: '2px solid var(--border)', background: '#f8fafc' }}>
                                {/* colSpan=2 because the table now has a leading
                                    TSA Account column before GL Account — the
                                    Add Line affordance spans both since neither
                                    needs a footer total. */}
                                <td colSpan={2} style={{ padding: '0.75rem 1rem' }}>
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
