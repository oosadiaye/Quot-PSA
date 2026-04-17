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
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, ArrowDownCircle, ArrowUpCircle, FileDown } from 'lucide-react';
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
    source: 'PAYMENT' | 'REVENUE';
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

// --- main component ----------------------------------------------------------

export default function TSALedger() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();

    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');

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
