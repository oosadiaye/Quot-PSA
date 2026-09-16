/**
 * TSA Ledger — Quot PSE
 * Route: /accounting/tsa-accounts/:id/ledger
 *
 * Bank-statement-style ledger for a single Treasury Single Account.
 * Shows chronological debits (outflows from PaymentInstruction) and
 * credits (inflows from RevenueCollection) with opening/closing balance
 * and optional date-range filter.
 *
 * Why this is valuable:
 *  - Audit teams can trace every money movement on a given TSA without
 *    touching the underlying JournalLine table.
 *  - Finance staff get the same view the bank gives them, making the
 *    bank-reconciliation workflow a like-for-like comparison.
 */
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { ArrowLeft, ArrowDownCircle, ArrowUpCircle, FileDown, AlertTriangle, Plus, X } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import apiClient from '../../api/client';
import '../../features/accounting/styles/glassmorphism.css';

// --- utilities ---------------------------------------------------------------

const fmtNGN = (v: number | string | undefined | null): string => {
    const num = typeof v === 'string' ? parseFloat(v) : (v ?? 0);
    if (isNaN(num as number)) return '\u20A60.00';
    return '\u20A6' + (num as number).toLocaleString('en-NG', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
};

const thStyle: React.CSSProperties = {
    padding: '0.625rem 0.75rem', textAlign: 'left', fontSize: '0.6875rem',
    fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
    color: 'var(--color-text-muted, #64748b)', whiteSpace: 'nowrap',
    borderBottom: '2px solid var(--color-border, #e2e8f0)',
    background: 'var(--color-surface, #f8fafc)',
};
const tdStyle: React.CSSProperties = {
    padding: '0.625rem 0.75rem', fontSize: 'var(--text-sm, 13px)',
    borderBottom: '1px solid var(--color-border, #f1f5f9)',
};

// --- types -------------------------------------------------------------------

interface LedgerEntry {
    date: string | null;
    type: 'DEBIT' | 'CREDIT';
    reference: string;
    narration: string;
    counterparty: string;
    debit: string | number;
    credit: string | number;
    running_balance: string | number;
    // JOURNAL = a GL cash-account movement with no revenue/payment document
    // (vendor registration, advance disbursement, inter-TSA transfer, sweep).
    source: 'PAYMENT' | 'REVENUE' | 'JOURNAL';
    source_id: number;
}

interface LedgerResponse {
    account: {
        id: number;
        account_number: string;
        account_name: string;
        bank: string;
        account_type: string;
        current_balance: string | number;
        mda_name: string | null;
    };
    from: string | null;
    to: string | null;
    opening_balance: string | number;
    closing_balance: string | number;
    total_debits: string | number;
    total_credits: string | number;
    // Authoritative GL cash position and whether the stored current_balance
    // agrees with it. When balance_reconciled is false the field has drifted.
    gl_cash_balance?: string | number;
    balance_reconciled?: boolean;
    balance_discrepancy?: string | number;
    entries: LedgerEntry[];
}

// --- summary card ------------------------------------------------------------

function StatCard({
    label, value, accent, icon,
}: {
    label: string; value: string; accent: string; icon?: React.ReactNode;
}) {
    return (
        <div
            className="glass-card"
            style={{
                padding: '1rem 1.25rem', borderLeft: `3px solid ${accent}`,
                display: 'flex', flexDirection: 'column', gap: '0.25rem',
            }}
        >
            <div
                style={{
                    fontSize: '0.7rem', fontWeight: 600,
                    textTransform: 'uppercase', letterSpacing: '0.05em',
                    color: 'var(--color-text-muted, #64748b)',
                    display: 'flex', alignItems: 'center', gap: '0.375rem',
                }}
            >
                {icon}
                {label}
            </div>
            <div style={{ fontSize: '1.25rem', fontWeight: 700, color: accent }}>
                {value}
            </div>
        </div>
    );
}

// --- CSV export --------------------------------------------------------------

function downloadCsv(data: LedgerResponse): void {
    // Constructing CSV here (rather than a round-trip to the backend) keeps
    // the server contract minimal and the export zero-latency.
    const header = [
        'Date', 'Reference', 'Type', 'Counterparty',
        'Narration', 'Debit', 'Credit', 'Running Balance',
    ].join(',');
    const rows = data.entries.map(e => [
        e.date ?? '',
        JSON.stringify(e.reference ?? ''),
        e.type,
        JSON.stringify(e.counterparty ?? ''),
        JSON.stringify(e.narration ?? ''),
        e.debit ?? 0,
        e.credit ?? 0,
        e.running_balance ?? 0,
    ].join(','));
    const body = [header, ...rows].join('\n');
    const blob = new Blob([body], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `tsa-ledger-${data.account.account_number}.csv`;
    a.click();
    URL.revokeObjectURL(url);
}

// --- record-transaction modal ------------------------------------------------

interface ContraAccount {
    id: number;
    code: string;
    name: string;
    account_type?: string;
}

/**
 * Record a manual cash-book entry on this TSA.
 *
 * Every movement posts a balanced JV to the TSA's GL cash account plus a
 * contra account the officer chooses — so cash never moves on a TSA
 * without a matching GL posting, and the entry lands in the ledger. This
 * is the "all postings hit the GL" rule made usable.
 */
function RecordTransactionModal({
    accountId, accountName, onClose, onRecorded,
}: {
    accountId: string;
    accountName: string;
    onClose: () => void;
    onRecorded: () => void;
}) {
    const [direction, setDirection] = useState<'IN' | 'OUT'>('IN');
    const [amount, setAmount] = useState('');
    const [date, setDate] = useState('');
    const [narration, setNarration] = useState('');
    const [contra, setContra] = useState('');   // display text "code — name"
    const [err, setErr] = useState<string | null>(null);

    const { data: accounts = [] } = useQuery<ContraAccount[]>({
        queryKey: ['coa-accounts-for-contra'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/accounts/', {
                params: { page_size: 2000 },
            });
            return Array.isArray(data) ? data : data?.results ?? [];
        },
        staleTime: 5 * 60 * 1000,
    });

    // Datalist maps the typed/picked "code — name" back to an account id.
    const options = useMemo(
        () => accounts.map((a) => ({ id: a.id, label: `${a.code} — ${a.name}` })),
        [accounts],
    );
    const contraId = useMemo(() => {
        const q = contra.trim().toLowerCase();
        if (!q) return null;
        const hit = options.find((o) => o.label.toLowerCase() === q)
            || options.find((o) => o.label.toLowerCase().includes(q));
        return hit ? hit.id : null;
    }, [contra, options]);

    const mutation = useMutation({
        mutationFn: async () => {
            const body: Record<string, unknown> = {
                direction, amount, contra_account: contraId,
            };
            if (date) body.date = date;
            if (narration.trim()) body.narration = narration.trim();
            const { data } = await apiClient.post(
                `/accounting/tsa-accounts/${accountId}/record-transaction/`, body,
            );
            return data;
        },
        onSuccess: () => { onRecorded(); onClose(); },
        onError: (e: any) => setErr(e?.response?.data?.error || e?.message || 'Failed to record'),
    });

    const canSubmit = Boolean(
        amount && Number(amount) > 0 && contraId && !mutation.isPending,
    );

    const label: React.CSSProperties = {
        display: 'block', fontSize: '0.7rem', fontWeight: 700, color: '#64748b',
        textTransform: 'uppercase', letterSpacing: '0.03em', marginBottom: '0.3rem',
    };
    const field: React.CSSProperties = {
        width: '100%', padding: '0.5rem 0.65rem', fontSize: '0.85rem',
        border: '1px solid #e2e8f0', borderRadius: '8px', background: '#fff', color: '#1e293b',
    };

    return (
        <div
            role="dialog"
            aria-modal="true"
            style={{
                position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.5)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999,
                padding: '1rem',
            }}
            onClick={onClose}
        >
            <div
                onClick={(e) => e.stopPropagation()}
                style={{
                    width: 460, maxWidth: '100%', maxHeight: '90vh', overflow: 'auto',
                    background: '#fff', borderRadius: 12, padding: '1.4rem 1.5rem',
                    boxShadow: '0 20px 50px rgba(0,0,0,0.25)',
                }}
            >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                    <div>
                        <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 800, color: '#1e293b' }}>Record Transaction</h3>
                        <p style={{ margin: '0.2rem 0 0', fontSize: '0.78rem', color: '#64748b' }}>{accountName}</p>
                    </div>
                    <button onClick={onClose} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#64748b', padding: 4 }}>
                        <X size={18} />
                    </button>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
                    <div>
                        <span style={label}>Direction</span>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                            {(['IN', 'OUT'] as const).map((d) => (
                                <button
                                    key={d}
                                    type="button"
                                    onClick={() => setDirection(d)}
                                    style={{
                                        flex: 1, padding: '0.5rem', borderRadius: 8, fontSize: '0.82rem', fontWeight: 600,
                                        cursor: 'pointer',
                                        border: `1px solid ${direction === d ? (d === 'IN' ? '#16a34a' : '#dc2626') : '#e2e8f0'}`,
                                        background: direction === d ? (d === 'IN' ? '#f0fdf4' : '#fef2f2') : '#fff',
                                        color: direction === d ? (d === 'IN' ? '#166534' : '#991b1b') : '#64748b',
                                    }}
                                >
                                    {d === 'IN' ? 'Incoming (money in)' : 'Outgoing (money out)'}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <label style={label} htmlFor="rt-amount">Amount (NGN)</label>
                        <input id="rt-amount" type="number" min="0" step="0.01" value={amount}
                            onChange={(e) => setAmount(e.target.value)} placeholder="0.00" style={field} />
                    </div>

                    <div>
                        <label style={label} htmlFor="rt-contra">Contra account (the other leg)</label>
                        <input id="rt-contra" list="rt-contra-options" value={contra}
                            onChange={(e) => setContra(e.target.value)} placeholder="Type or pick an account" style={field} />
                        <datalist id="rt-contra-options">
                            {options.map((o) => <option key={o.id} value={o.label} />)}
                        </datalist>
                        <div style={{ fontSize: '0.68rem', color: '#94a3b8', marginTop: 3 }}>
                            {direction === 'IN'
                                ? 'DR the TSA cash account, CR this account.'
                                : 'CR the TSA cash account, DR this account.'}
                        </div>
                    </div>

                    <div style={{ display: 'flex', gap: '0.6rem' }}>
                        <div style={{ flex: 1 }}>
                            <label style={label} htmlFor="rt-date">Date</label>
                            <input id="rt-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} style={field} />
                        </div>
                    </div>

                    <div>
                        <label style={label} htmlFor="rt-narr">Narration</label>
                        <input id="rt-narr" value={narration} onChange={(e) => setNarration(e.target.value)}
                            placeholder="e.g. Bank charges, refund, direct lodgement" style={field} />
                    </div>

                    {err && (
                        <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', color: '#991b1b', padding: '0.6rem 0.8rem', borderRadius: 8, fontSize: '0.78rem' }}>
                            {err}
                        </div>
                    )}

                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.3rem' }}>
                        <button type="button" onClick={onClose}
                            style={{ padding: '0.5rem 1rem', border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', color: '#475569', fontSize: '0.82rem', fontWeight: 600, cursor: 'pointer' }}>
                            Cancel
                        </button>
                        <button type="button" onClick={() => { setErr(null); mutation.mutate(); }} disabled={!canSubmit}
                            style={{
                                padding: '0.5rem 1.1rem', border: 'none', borderRadius: 8,
                                background: canSubmit ? '#4f46e5' : '#c7d2fe', color: '#fff',
                                fontSize: '0.82rem', fontWeight: 600, cursor: canSubmit ? 'pointer' : 'not-allowed',
                            }}>
                            {mutation.isPending ? 'Recording…' : 'Record'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

// --- main component ----------------------------------------------------------

export default function TSALedger() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();

    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');
    const [showRecord, setShowRecord] = useState(false);

    const { data, isLoading, error, refetch, isFetching } = useQuery<LedgerResponse>({
        queryKey: ['tsa-ledger', id, dateFrom, dateTo],
        queryFn: async () => {
            const params: Record<string, string> = {};
            if (dateFrom) params.from = dateFrom;
            if (dateTo) params.to = dateTo;
            const res = await apiClient.get(
                `/accounting/tsa-accounts/${id}/ledger/`, { params },
            );
            return res.data;
        },
        enabled: Boolean(id),
    });

    // Group entries by date for cleaner presentation — a real bank statement
    // adds a tiny date divider whenever the day changes.
    const groupedEntries = useMemo(() => {
        if (!data?.entries) return [];
        const out: Array<LedgerEntry & { isNewDay: boolean }> = [];
        let lastDate: string | null | undefined = undefined;
        for (const e of data.entries) {
            out.push({ ...e, isNewDay: e.date !== lastDate });
            lastDate = e.date;
        }
        return out;
    }, [data?.entries]);

    if (isLoading) {
        return (
            <div style={{ display: 'flex' }}>
                <Sidebar />
                <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                    <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                        Loading ledger...
                    </div>
                </main>
            </div>
        );
    }

    if (error || !data) {
        return (
            <div style={{ display: 'flex' }}>
                <Sidebar />
                <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                    <div style={{ padding: '3rem', textAlign: 'center', color: '#ef4444' }}>
                        Unable to load ledger. Please try again.
                    </div>
                </main>
            </div>
        );
    }

    const { account } = data;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title={`${account.account_name}`}
                    subtitle={`${account.account_number} · ${account.bank}${account.mda_name ? ' · ' + account.mda_name : ''}`}
                />

                {/* Back + export toolbar */}
                <div
                    style={{
                        display: 'flex', justifyContent: 'space-between',
                        alignItems: 'center', marginBottom: '1rem',
                    }}
                >
                    <button
                        onClick={() => navigate('/accounting/tsa-accounts')}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '0.375rem',
                            padding: '0.5rem 0.875rem',
                            border: '1px solid var(--color-border, #e2e8f0)',
                            borderRadius: '8px',
                            background: 'var(--color-surface, #fff)',
                            color: 'var(--color-text, #1e293b)',
                            fontSize: '13px', fontWeight: 500, cursor: 'pointer',
                        }}
                    >
                        <ArrowLeft size={14} /> Back to TSA Accounts
                    </button>

                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button
                            onClick={() => setShowRecord(true)}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '0.375rem',
                                padding: '0.5rem 0.875rem', border: 'none', borderRadius: '8px',
                                background: '#4f46e5', color: '#fff',
                                fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                            }}
                        >
                            <Plus size={14} /> Record Transaction
                        </button>

                    <button
                        onClick={() => downloadCsv(data)}
                        disabled={data.entries.length === 0}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '0.375rem',
                            padding: '0.5rem 0.875rem',
                            border: '1px solid var(--color-border, #e2e8f0)',
                            borderRadius: '8px',
                            background: 'var(--color-surface, #fff)',
                            color: data.entries.length === 0 ? '#94a3b8' : '#0f766e',
                            fontSize: '13px', fontWeight: 500,
                            cursor: data.entries.length === 0 ? 'not-allowed' : 'pointer',
                        }}
                    >
                        <FileDown size={14} /> Export CSV
                    </button>
                    </div>
                </div>

                {showRecord && (
                    <RecordTransactionModal
                        accountId={String(id)}
                        accountName={account.account_name}
                        onClose={() => setShowRecord(false)}
                        onRecorded={() => refetch()}
                    />
                )}

                {/* Summary stats */}
                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                        gap: '0.75rem', marginBottom: '1.25rem',
                    }}
                >
                    <StatCard
                        label="Opening Balance"
                        value={fmtNGN(data.opening_balance)}
                        accent="#64748b"
                    />
                    <StatCard
                        label="Total Credits (Inflows)"
                        value={fmtNGN(data.total_credits)}
                        accent="#16a34a"
                        icon={<ArrowDownCircle size={12} />}
                    />
                    <StatCard
                        label="Total Debits (Outflows)"
                        value={fmtNGN(data.total_debits)}
                        accent="#dc2626"
                        icon={<ArrowUpCircle size={12} />}
                    />
                    <StatCard
                        label="Closing Balance"
                        value={fmtNGN(data.closing_balance)}
                        accent="#0f766e"
                    />
                </div>

                {/* Drift warning: the stored current_balance disagrees with the
                    GL cash account. The ledger's closing (from the movements)
                    is the figure to trust; the stored balance needs rebuilding. */}
                {data.balance_reconciled === false && (
                    <div
                        role="alert"
                        style={{
                            display: 'flex', alignItems: 'flex-start', gap: '0.6rem',
                            padding: '0.8rem 1rem', marginBottom: '1.25rem',
                            background: '#fffbeb', border: '1px solid #fcd34d',
                            borderRadius: '10px', color: '#92400e', fontSize: '0.82rem',
                            lineHeight: 1.5,
                        }}
                    >
                        <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: 1, color: '#d97706' }} />
                        <div>
                            <strong>Stored balance does not reconcile with the general ledger.</strong>
                            {' '}The account's stored balance is <strong>{fmtNGN(data.account.current_balance)}</strong>,
                            but the GL cash account nets to <strong>{fmtNGN(data.gl_cash_balance ?? 0)}</strong>
                            {' '}(a difference of <strong>{fmtNGN(data.balance_discrepancy ?? 0)}</strong>).
                            The movements below are the authoritative record — the stored balance
                            was not updated for every posting and needs rebuilding.
                        </div>
                    </div>
                )}

                {/* Date filter */}
                <div
                    className="glass-card"
                    style={{
                        padding: '0.75rem 1rem', marginBottom: '1rem',
                        display: 'flex', gap: '0.75rem', alignItems: 'center',
                        flexWrap: 'wrap',
                    }}
                >
                    <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                        From
                        <input
                            type="date"
                            value={dateFrom}
                            onChange={e => setDateFrom(e.target.value)}
                            style={{
                                marginLeft: '0.5rem',
                                padding: '0.375rem 0.5rem',
                                border: '1px solid var(--color-border, #e2e8f0)',
                                borderRadius: '6px',
                                fontSize: '13px',
                            }}
                        />
                    </label>
                    <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                        To
                        <input
                            type="date"
                            value={dateTo}
                            onChange={e => setDateTo(e.target.value)}
                            style={{
                                marginLeft: '0.5rem',
                                padding: '0.375rem 0.5rem',
                                border: '1px solid var(--color-border, #e2e8f0)',
                                borderRadius: '6px',
                                fontSize: '13px',
                            }}
                        />
                    </label>
                    <button
                        onClick={() => refetch()}
                        disabled={isFetching}
                        style={{
                            padding: '0.4rem 0.875rem',
                            background: 'linear-gradient(135deg, #191e6a 0%, #0f1240 100%)',
                            color: '#fff', border: 'none', borderRadius: '6px',
                            fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                        }}
                    >
                        {isFetching ? 'Loading...' : 'Apply'}
                    </button>
                    {(dateFrom || dateTo) && (
                        <button
                            onClick={() => { setDateFrom(''); setDateTo(''); }}
                            style={{
                                padding: '0.4rem 0.75rem',
                                background: 'transparent',
                                color: 'var(--color-text-muted)',
                                border: '1px solid var(--color-border, #e2e8f0)',
                                borderRadius: '6px', fontSize: '13px', cursor: 'pointer',
                            }}
                        >
                            Clear
                        </button>
                    )}
                </div>

                {/* Ledger table */}
                <div className="glass-card" style={{ overflow: 'hidden' }}>
                    {data.entries.length === 0 ? (
                        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                            No ledger entries for the selected period.
                        </div>
                    ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr>
                                    <th style={thStyle}>Date</th>
                                    <th style={thStyle}>Reference</th>
                                    <th style={thStyle}>Counterparty</th>
                                    <th style={thStyle}>Narration</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Debit</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Credit</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Balance</th>
                                </tr>
                            </thead>
                            <tbody>
                                {/* Opening balance row */}
                                <tr style={{ background: '#f8fafc' }}>
                                    <td style={{ ...tdStyle, fontWeight: 600, color: '#64748b' }}>
                                        {data.from || '—'}
                                    </td>
                                    <td colSpan={3} style={{ ...tdStyle, fontWeight: 600, fontStyle: 'italic', color: '#64748b' }}>
                                        Opening Balance
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'right' }}>—</td>
                                    <td style={{ ...tdStyle, textAlign: 'right' }}>—</td>
                                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#0f766e' }}>
                                        {fmtNGN(data.opening_balance)}
                                    </td>
                                </tr>

                                {groupedEntries.map((e, idx) => (
                                    <tr
                                        key={`${e.source}-${e.source_id}`}
                                        style={{
                                            borderTop: e.isNewDay && idx > 0
                                                ? '2px solid var(--color-border, #e8ecf1)' : undefined,
                                        }}
                                    >
                                        <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>
                                            {e.isNewDay ? (e.date ?? '—') : ''}
                                        </td>
                                        <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: '12px' }}>
                                            {e.reference}
                                        </td>
                                        <td style={tdStyle}>{e.counterparty || '—'}</td>
                                        <td style={{ ...tdStyle, color: 'var(--color-text-muted, #64748b)' }}>
                                            {e.narration || '—'}
                                        </td>
                                        <td style={{ ...tdStyle, textAlign: 'right', color: '#dc2626', fontWeight: 600 }}>
                                            {Number(e.debit) > 0 ? fmtNGN(e.debit) : ''}
                                        </td>
                                        <td style={{ ...tdStyle, textAlign: 'right', color: '#16a34a', fontWeight: 600 }}>
                                            {Number(e.credit) > 0 ? fmtNGN(e.credit) : ''}
                                        </td>
                                        <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600 }}>
                                            {fmtNGN(e.running_balance)}
                                        </td>
                                    </tr>
                                ))}

                                {/* Closing balance row */}
                                <tr style={{ background: '#f0fdf4', borderTop: '2px solid #16a34a' }}>
                                    <td style={{ ...tdStyle, fontWeight: 600, color: '#166534' }}>
                                        {data.to || '—'}
                                    </td>
                                    <td colSpan={3} style={{ ...tdStyle, fontWeight: 700, color: '#166534' }}>
                                        Closing Balance
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700 }}>
                                        {fmtNGN(data.total_debits)}
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700 }}>
                                        {fmtNGN(data.total_credits)}
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#166534' }}>
                                        {fmtNGN(data.closing_balance)}
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    )}
                </div>
            </main>
        </div>
    );
}
