/**
 * Shared journal-display components.
 *
 * Two pure-render Lego bricks — they take *already-fetched* journal
 * data and produce the canonical visual treatment used everywhere a
 * journal is displayed in the app:
 *
 *   - ``<JournalHeaderStrip />`` — doc number / posting date / status
 *     / total DR / total CR strip. The compact at-a-glance summary
 *     consumers show above the lines table.
 *
 *   - ``<JournalLinesTable />`` — DR/CR lines table with account
 *     code + name, debit, credit, memo. The audit-grade renderer.
 *
 * Both components are stateless and side-effect-free. Consumers do
 * their own data fetching (typically via React Query), apply their
 * own loading/error/empty states, and slot these components into
 * whatever surrounding chrome they need (modal, inline card,
 * embedded tab, etc.).
 *
 * Why "pure-render" rather than self-fetching: lets each consumer
 * coordinate the journal data with the rest of their page state
 * (cache invalidation, refetch on focus, optimistic updates) without
 * the shared component dictating a fetch strategy.
 *
 * Why two components rather than one: composability. Some consumers
 * want only the lines table (e.g., a future print preview). Some
 * want only the header strip (e.g., a journal-list row hover card).
 * Two bricks compose into more shapes than one monolith.
 *
 * Design intent for IPSAS audit consistency:
 *   Auditors will physically point at this rendering and ask "show
 *   me how this is computed." It MUST look identical across every
 *   surface that displays a journal — receipt detail, contract
 *   mobilization tab, outgoing payment journal modal, etc. Drift
 *   across surfaces costs auditor trust. Sharing the rendering makes
 *   drift structurally impossible.
 */
import type { CSSProperties } from 'react';

// ── Shared types ─────────────────────────────────────────────────────
// Mirror the backend's JournalDetailSerializer output. Kept here as
// the single source of truth — consumers import these instead of
// redeclaring their own (which previously drifted: some had
// ``document_number?`` while others had it required, etc.).

export interface JournalLine {
    id: number;
    account_code: string;
    account_name: string;
    debit: string | number;
    credit: string | number;
    memo: string;
    document_number?: string;
}

export interface JournalDetail {
    id: number;
    posting_date: string;
    description: string;
    reference_number: string;
    status: string;
    document_number: string;
    total_debit: string | number;
    total_credit: string | number;
    lines: JournalLine[];
}


// ── JournalHeaderStrip ──────────────────────────────────────────────

interface JournalHeaderStripProps {
    journal: JournalDetail;
    formatCurrency: (n: number | string) => string;
}

export function JournalHeaderStrip({
    journal,
    formatCurrency,
}: JournalHeaderStripProps) {
    return (
        <div style={headerStripStyle}>
            <div>
                <div style={labelStyle}>Doc Number</div>
                <div style={{ ...valueStyle, fontFamily: 'monospace' }}>
                    {journal.document_number || journal.reference_number || '—'}
                </div>
            </div>
            <div>
                <div style={labelStyle}>Posting Date</div>
                <div style={valueStyle}>
                    {journal.posting_date
                        ? new Date(journal.posting_date).toLocaleDateString('en-GB')
                        : '—'}
                </div>
            </div>
            <div>
                <div style={labelStyle}>Status</div>
                <div style={{ ...valueStyle, color: journal.status === 'Posted' ? '#15803d' : '#92400e' }}>
                    {journal.status}
                </div>
            </div>
            <div>
                <div style={labelStyle}>Total Debit</div>
                <div style={{ ...valueStyle, fontFamily: 'monospace', color: '#15803d' }}>
                    {formatCurrency(Number(journal.total_debit) || 0)}
                </div>
            </div>
            <div>
                <div style={labelStyle}>Total Credit</div>
                <div style={{ ...valueStyle, fontFamily: 'monospace', color: '#dc2626' }}>
                    {formatCurrency(Number(journal.total_credit) || 0)}
                </div>
            </div>
        </div>
    );
}


// ── JournalLinesTable ──────────────────────────────────────────────

interface JournalLinesTableProps {
    lines: JournalLine[];
    formatCurrency: (n: number | string) => string;
    /**
     * Optional empty-state message when ``lines.length === 0``. Defaults
     * to "This journal has no lines yet." Consumers can pass their own
     * (e.g., "This receipt has not been posted yet — no journal exists.").
     */
    emptyMessage?: string;
}

export function JournalLinesTable({
    lines,
    formatCurrency,
    emptyMessage = 'This journal has no lines yet.',
}: JournalLinesTableProps) {
    if (lines.length === 0) {
        return (
            <div style={emptyStateStyle}>
                {emptyMessage}
            </div>
        );
    }

    return (
        <div style={tableWrapperStyle}>
            <table style={tableStyle}>
                <thead>
                    <tr style={{ background: '#f1f5f9', textAlign: 'left' }}>
                        <th style={thStyle}>GL Account</th>
                        <th style={{ ...thStyle, textAlign: 'right', width: 140 }}>Debit (NGN)</th>
                        <th style={{ ...thStyle, textAlign: 'right', width: 140 }}>Credit (NGN)</th>
                        <th style={thStyle}>Memo</th>
                    </tr>
                </thead>
                <tbody>
                    {lines.map((line) => {
                        const dr = Number(line.debit) || 0;
                        const cr = Number(line.credit) || 0;
                        return (
                            <tr key={line.id} style={{ borderTop: '1px solid #e2e8f0' }}>
                                <td style={tdStyle}>
                                    <div style={accountCodeStyle}>
                                        {line.account_code}
                                    </div>
                                    <div style={accountNameStyle}>
                                        {line.account_name}
                                    </div>
                                </td>
                                <td style={{ ...amountCellStyle, fontWeight: dr ? 700 : 400, color: dr ? '#15803d' : '#cbd5e1' }}>
                                    {dr ? formatCurrency(dr) : '—'}
                                </td>
                                <td style={{ ...amountCellStyle, fontWeight: cr ? 700 : 400, color: cr ? '#dc2626' : '#cbd5e1' }}>
                                    {cr ? formatCurrency(cr) : '—'}
                                </td>
                                <td style={{ ...tdStyle, color: '#475569' }}>
                                    {line.memo || '—'}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}


// ── Styles (kept inline to match the project's existing pattern;
//    extracted as named consts only because they're shared between
//    the two components above) ─────────────────────────────────────

const headerStripStyle: CSSProperties = {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
    gap: 12,
    padding: 12,
    background: '#f8fafc',
    borderRadius: 8,
    border: '1px solid #e2e8f0',
};

const labelStyle: CSSProperties = {
    fontSize: 11,
    fontWeight: 700,
    color: '#94a3b8',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: 4,
};

const valueStyle: CSSProperties = {
    fontSize: 14,
    fontWeight: 500,
    color: '#1e293b',
};

const tableWrapperStyle: CSSProperties = {
    overflowX: 'auto',
    border: '1px solid #e2e8f0',
    borderRadius: 8,
};

const tableStyle: CSSProperties = {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 13,
};

const thStyle: CSSProperties = {
    padding: '10px 12px',
    fontSize: 11,
    fontWeight: 700,
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
};

const tdStyle: CSSProperties = {
    padding: '10px 12px',
};

const amountCellStyle: CSSProperties = {
    padding: '10px 12px',
    textAlign: 'right',
    fontFamily: 'monospace',
};

const accountCodeStyle: CSSProperties = {
    fontFamily: 'monospace',
    fontWeight: 600,
    color: '#1e4d8c',
};

const accountNameStyle: CSSProperties = {
    fontSize: 12,
    color: '#64748b',
    marginTop: 2,
};

const emptyStateStyle: CSSProperties = {
    padding: 24,
    textAlign: 'center',
    color: '#94a3b8',
    fontSize: 13,
};
