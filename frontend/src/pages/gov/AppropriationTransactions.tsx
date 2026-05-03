/**
 * Appropriation Transactions — drill-down page.
 *
 * Lists every transaction that contributes to an appropriation's
 * committed / expended balance: PO commitments, direct AP invoices,
 * direct payment vouchers, and manual journal entries. Each row is
 * deep-linked back to the source document so the auditor can pivot
 * from "this appropriation has ₦7.08M expended — what consumed it?"
 * into the originating record in two clicks.
 */
import { useMemo, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
    ArrowLeft, FileText, ListChecks, ExternalLink, Search, Download,
} from 'lucide-react';
import apiClient from '../../api/client';
import AccountingLayout from '../../features/accounting/AccountingLayout';
import LoadingScreen from '../../components/common/LoadingScreen';
import PageHeader from '../../components/PageHeader';
import { useCurrency } from '../../context/CurrencyContext';

interface TxnRow {
    type: 'PO_COMMITMENT' | 'AP_INVOICE' | 'PV' | 'JE';
    status: string;
    kind: 'committed' | 'expended' | 'reversal';
    date: string;
    reference: string;
    description: string;
    party: string;
    amount: string;
    source_id: number | null;
    source_url: string;
}

interface TxnResponse {
    appropriation: any;
    transactions: TxnRow[];
    summary: {
        committed_count: number;
        committed_total: string;
        expended_count: number;
        expended_total: string;
    };
}

const TYPE_LABEL: Record<TxnRow['type'], string> = {
    PO_COMMITMENT: 'Purchase Order',
    AP_INVOICE:    'Vendor Invoice',
    PV:            'Payment Voucher',
    JE:            'Journal Entry',
};

const KIND_BADGE: Record<TxnRow['kind'], { bg: string; color: string; label: string }> = {
    committed: { bg: '#fef3c7', color: '#a16207', label: 'Committed' },
    expended:  { bg: '#fee2e2', color: '#b91c1c', label: 'Expended' },
    reversal:  { bg: '#dcfce7', color: '#15803d', label: 'Reversal' },
};

export default function AppropriationTransactions() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const [typeFilter, setTypeFilter] = useState<string>('');
    const [searchTerm, setSearchTerm] = useState<string>('');

    // Fetch the appropriation header in parallel so we can render the
    // summary cards even when the transactions endpoint fails (e.g.
    // network error, server-side schema gap on a particular source).
    // The drill-down has value even when there are no transactions —
    // the operator still wants to see Approved / Available / etc.
    const { data: apprData } = useQuery<any>({
        queryKey: ['appropriation', id],
        queryFn: async () => {
            const { data } = await apiClient.get(`/budget/appropriations/${id}/`);
            return data;
        },
        enabled: !!id,
    });

    const { data, isLoading, error } = useQuery<TxnResponse>({
        queryKey: ['appropriation-transactions', id],
        queryFn: async () => {
            const { data } = await apiClient.get(
                `/budget/appropriations/${id}/transactions/`,
            );
            return data;
        },
        enabled: !!id,
        // Don't retry endlessly when the endpoint isn't available — fall
        // back to "no transactions" UI quickly so the page is usable.
        retry: 1,
    });

    // Resilient fallbacks: if the transactions endpoint failed but we
    // got the appropriation header, render the page anyway with an
    // empty transactions list. The operator sees the budget summary
    // and a friendly "no transactions yet" panel — never a hard error.
    const transactions = data?.transactions ?? [];
    const summary = data?.summary ?? {
        committed_count: 0, committed_total: '0',
        expended_count: 0, expended_total: '0',
    };
    const a = data?.appropriation ?? apprData;

    const filtered = useMemo(() => {
        const q = searchTerm.trim().toLowerCase();
        return transactions.filter((t) => {
            if (typeFilter && t.type !== typeFilter) return false;
            if (q) {
                const hay = `${t.reference} ${t.party} ${t.description}`.toLowerCase();
                if (!hay.includes(q)) return false;
            }
            return true;
        });
    }, [transactions, typeFilter, searchTerm]);

    if (isLoading && !apprData) return <AccountingLayout><LoadingScreen message="Loading transactions..." /></AccountingLayout>;

    // True dead end — neither endpoint returned anything we can render.
    // Only happens when the appropriation id itself is invalid.
    if (!a) {
        return (
            <AccountingLayout>
                <div style={{ padding: '3rem', textAlign: 'center' }}>
                    <p>Appropriation not found.</p>
                    <button className="btn btn-outline" onClick={() => navigate(-1)}>
                        <ArrowLeft size={14} /> Back
                    </button>
                </div>
            </AccountingLayout>
        );
    }

    const fmt = (v: any) => formatCurrency(parseFloat(String(v ?? 0)) || 0);

    // Excel-compatible CSV export. We emit one row per filtered
    // transaction plus a totals row. The leading UTF-8 BOM
    // (``﻿``) makes Excel auto-detect the file as UTF-8 so
    // ``₦`` and any non-ASCII vendor names render correctly without
    // the user picking the encoding manually. Filename carries the
    // economic code + DD/MM/YYYY date so multiple exports don't
    // collide in the Downloads folder.
    const handleExport = () => {
        if (!a) return;
        const csvEscape = (v: unknown): string => {
            const s = String(v ?? '');
            // Quote when comma, quote, or newline present; double-up
            // any embedded quotes per RFC 4180.
            if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
            return s;
        };
        const headers = [
            'Date', 'Type', 'Reference', 'Status', 'Kind',
            'Party / Account', 'Description', 'Amount (NGN)',
            'Source ID', 'Source URL',
        ];
        const rows = filtered.map((t) => [
            t.date,
            TYPE_LABEL[t.type] || t.type,
            t.reference,
            t.status,
            KIND_BADGE[t.kind]?.label || t.kind,
            t.party,
            t.description,
            (parseFloat(t.amount) || 0).toFixed(2),
            t.source_id ?? '',
            t.source_url,
        ]);
        const total = filtered.reduce((s, t) => s + (parseFloat(t.amount) || 0), 0);
        const totalRow = [
            '', '', '', '', '', '', `Total (${filtered.length} rows)`,
            total.toFixed(2), '', '',
        ];

        // Header preamble — gives the auditor full context on the
        // exported worksheet without needing to consult the parent
        // appropriation. Comment-style ``#`` rows are ignored on
        // re-import by the Appropriation CSV importer (same
        // convention used elsewhere in the codebase).
        const meta = [
            `# Appropriation: ${a.economic_code} — ${a.economic_name || ''}`,
            `# MDA: ${a.administrative_code || ''} — ${a.administrative_name || ''}`,
            `# Fiscal Year: ${a.fiscal_year_label || a.fiscal_year || ''}`,
            `# Approved: ${a.amount_approved}`,
            `# Committed (open): ${a.cached_total_committed}`,
            `# Expended: ${a.cached_total_expended}`,
            `# Available: ${a.available_balance}`,
            `# Generated: ${new Date().toISOString()}`,
        ];

        const csv = [
            ...meta,
            '',
            headers.map(csvEscape).join(','),
            ...rows.map((r) => r.map(csvEscape).join(',')),
            totalRow.map(csvEscape).join(','),
        ].join('\r\n');

        const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        // DD-MM-YYYY filename per Nigerian convention.
        const today = new Date();
        const dd = String(today.getDate()).padStart(2, '0');
        const mm = String(today.getMonth() + 1).padStart(2, '0');
        const yyyy = today.getFullYear();
        link.href = url;
        link.download = `appropriation_${a.economic_code}_transactions_${dd}-${mm}-${yyyy}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    return (
        <AccountingLayout>
            <PageHeader
                title={`Line Items — ${a.economic_name || 'Economic Code'}`}
                subtitle={
                    `${a.administrative_name || 'MDA'} · `
                    + `${a.economic_code} · FY ${a.fiscal_year_label || a.fiscal_year}`
                }
                icon={<ListChecks size={22} />}
                onBack={() => navigate(`/budget/appropriations/${id}`)}
            />

            {/* Top summary cards — same numbers the parent page shows,
                anchored here so the user has full context without
                navigating back. */}
            <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: '1rem', marginBottom: '1.25rem',
            }}>
                <SummaryCard label="Approved" value={fmt(a.amount_approved)} accent="#1e293b" />
                <SummaryCard label="Committed (open)" value={fmt(a.cached_total_committed)} accent="#a16207" />
                <SummaryCard label="Expended" value={fmt(a.cached_total_expended)} accent="#b91c1c" />
                <SummaryCard label="Available" value={fmt(a.available_balance)} accent="#059669" />
            </div>

            {/* Filters */}
            <div className="card" style={{
                padding: '0.875rem 1rem', marginBottom: '1rem',
                display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center',
            }}>
                <div style={{ position: 'relative', flex: '1 1 280px', minWidth: 240 }}>
                    <Search size={14} style={{
                        position: 'absolute', left: 8, top: '50%',
                        transform: 'translateY(-50%)', color: 'var(--color-text-muted)',
                    }} />
                    <input
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        placeholder="Search reference, vendor, description..."
                        style={{
                            width: '100%', padding: '0.5rem 0.75rem 0.5rem 1.875rem',
                            borderRadius: 6, border: '1px solid var(--color-border)',
                            fontSize: 'var(--text-sm)',
                        }}
                    />
                </div>
                <select
                    value={typeFilter}
                    onChange={(e) => setTypeFilter(e.target.value)}
                    style={{
                        padding: '0.5rem 0.75rem', borderRadius: 6,
                        border: '1px solid var(--color-border)', fontSize: 'var(--text-sm)',
                    }}
                >
                    <option value="">All transaction types</option>
                    <option value="PO_COMMITMENT">Purchase Orders (commitments)</option>
                    <option value="AP_INVOICE">Vendor Invoices (direct)</option>
                    <option value="PV">Payment Vouchers</option>
                    <option value="JE">Journal Entries</option>
                </select>
                <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                        {filtered.length} of {transactions.length} transaction{transactions.length === 1 ? '' : 's'}
                    </span>
                    <button
                        type="button"
                        onClick={handleExport}
                        disabled={filtered.length === 0}
                        title={
                            filtered.length === 0
                                ? 'No transactions to export'
                                : `Export ${filtered.length} row${filtered.length === 1 ? '' : 's'} to Excel-compatible CSV`
                        }
                        style={{
                            display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                            padding: '0.45rem 0.9rem',
                            background: filtered.length === 0 ? '#e2e8f0' : '#39cd9a',
                            color:      filtered.length === 0 ? '#94a3b8' : '#0b3a2c',
                            border: 'none', borderRadius: 8,
                            fontSize: 'var(--text-xs)', fontWeight: 700,
                            cursor: filtered.length === 0 ? 'not-allowed' : 'pointer',
                            whiteSpace: 'nowrap',
                        }}
                    >
                        <Download size={13} /> Export to Excel
                    </button>
                </div>
            </div>

            {/* Transactions table */}
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)', background: 'rgba(148,163,184,0.05)' }}>
                                <th style={th}>Date</th>
                                <th style={th}>Type</th>
                                <th style={th}>Reference</th>
                                <th style={th}>Party / Account</th>
                                <th style={th}>Description</th>
                                <th style={{ ...th, textAlign: 'center' }}>Kind</th>
                                <th style={{ ...th, textAlign: 'center' }}>Status</th>
                                <th style={{ ...th, textAlign: 'right' }}>Amount</th>
                                <th style={{ ...th, textAlign: 'center' }}>Open</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.length === 0 ? (
                                <tr>
                                    <td colSpan={9} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <FileText size={36} style={{ marginBottom: '0.75rem', opacity: 0.5 }} />
                                        {transactions.length === 0 ? (
                                            <>
                                                <div style={{ fontWeight: 600, marginBottom: '0.35rem' }}>
                                                    No transactions yet against this appropriation
                                                </div>
                                                <div style={{ fontSize: 'var(--text-xs)' }}>
                                                    Nothing has been committed or expended.
                                                    Available balance equals approved.
                                                </div>
                                                {error ? (
                                                    <div style={{ marginTop: '0.75rem', fontSize: 'var(--text-xs)', color: '#a16207' }}>
                                                        (One or more data sources couldn't be reached — what's shown is up to date.)
                                                    </div>
                                                ) : null}
                                            </>
                                        ) : (
                                            <div>No transactions match the current filters.</div>
                                        )}
                                    </td>
                                </tr>
                            ) : filtered.map((t, i) => {
                                const kb = KIND_BADGE[t.kind];
                                return (
                                    <tr key={`${t.type}-${t.source_id}-${i}`} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={td}>
                                            {t.date ? new Date(t.date).toLocaleDateString('en-GB') : '—'}
                                        </td>
                                        <td style={td}>
                                            <span style={{ fontSize: '0.7rem', fontWeight: 600, color: '#4f46e5' }}>
                                                {TYPE_LABEL[t.type]}
                                            </span>
                                        </td>
                                        <td style={{ ...td, fontFamily: 'monospace', fontWeight: 600 }}>
                                            {t.reference || '—'}
                                        </td>
                                        <td style={td}>{t.party || '—'}</td>
                                        <td style={{ ...td, color: 'var(--color-text-muted)', maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={t.description}>
                                            {t.description || '—'}
                                        </td>
                                        <td style={{ ...td, textAlign: 'center' }}>
                                            <span style={{
                                                padding: '0.15rem 0.55rem', borderRadius: 999,
                                                fontSize: '0.65rem', fontWeight: 700,
                                                background: kb.bg, color: kb.color,
                                            }}>{kb.label}</span>
                                        </td>
                                        <td style={{ ...td, textAlign: 'center', fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                                            {t.status}
                                        </td>
                                        <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace', fontWeight: 600 }}>
                                            {fmt(t.amount)}
                                        </td>
                                        <td style={{ ...td, textAlign: 'center' }}>
                                            {t.source_url ? (
                                                <Link to={t.source_url} title="Open source document"
                                                    style={{ color: '#4f46e5', display: 'inline-flex', alignItems: 'center' }}>
                                                    <ExternalLink size={14} />
                                                </Link>
                                            ) : '—'}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                        {filtered.length > 0 && (
                            <tfoot>
                                <tr style={{ borderTop: '2px solid var(--color-border)', background: 'rgba(148,163,184,0.05)' }}>
                                    <td colSpan={7} style={{ ...td, fontWeight: 700, textAlign: 'right' }}>
                                        Filtered total ({filtered.length}):
                                    </td>
                                    <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>
                                        {fmt(filtered.reduce((s, t) => s + (parseFloat(t.amount) || 0), 0))}
                                    </td>
                                    <td />
                                </tr>
                            </tfoot>
                        )}
                    </table>
                </div>
            </div>

            <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                <span><strong>{summary.committed_count}</strong> commitment(s) · {fmt(summary.committed_total)}</span>
                <span><strong>{summary.expended_count}</strong> expenditure(s) · {fmt(summary.expended_total)}</span>
            </div>
        </AccountingLayout>
    );
}

function SummaryCard({ label, value, accent }: { label: string; value: string; accent: string }) {
    return (
        <div className="card" style={{ padding: '1rem' }}>
            <div style={{ fontSize: '0.65rem', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.05em', color: 'var(--color-text-muted)' }}>
                {label}
            </div>
            <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: accent, marginTop: '0.35rem', fontFamily: 'monospace' }}>
                {value}
            </div>
        </div>
    );
}

const th: React.CSSProperties = {
    padding: '0.6rem 0.75rem', textAlign: 'left',
    fontSize: 'var(--text-xs)', textTransform: 'uppercase',
    letterSpacing: '0.05em', color: 'var(--color-text-muted)', fontWeight: 700,
};
const td: React.CSSProperties = {
    padding: '0.55rem 0.75rem', verticalAlign: 'middle',
};
