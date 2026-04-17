/**
 * Bank Reconciliation — Quot PSE
 * Route: /accounting/bank-reconciliation
 *
 * Complete bank-reconciliation workflow:
 *   1. Pick TSA account, upload CSV statement  → header + lines parsed
 *   2. Run Auto-Match                          → tier-matched by backend
 *   3. Review unmatched lines; link manually,  → matched lines stamped
 *      ignore bank charges, unlink mistakes      with user + timestamp
 *   4. Start Reconciliation Session            → book vs statement balance
 *      for period end
 *   5. Complete session                        → matched payment / revenue
 *                                                rows flagged reconciled
 */
import { useMemo, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Upload, RefreshCw, CheckCircle2, AlertCircle, Landmark, Play,
    Link as LinkIcon, X, FileText, Download, Eye, EyeOff,
    CalendarCheck, Lock,
} from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import apiClient from '../../api/client';
import '../../features/accounting/styles/glassmorphism.css';

// ─── helpers ────────────────────────────────────────────────────────────────

const fmtNGN = (v: number | string | undefined | null): string => {
    const num = typeof v === 'string' ? parseFloat(v) : (v ?? 0);
    if (isNaN(num as number)) return '\u20A60.00';
    return '\u20A6' + (num as number).toLocaleString('en-NG', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
};

const extractBackendError = (err: any): string => {
    const data = err?.response?.data;
    if (!data) return err?.message || 'Request failed';
    if (typeof data === 'string') return data;
    if (data.detail) return String(data.detail);
    const firstKey = Object.keys(data)[0];
    if (firstKey) {
        const v = data[firstKey];
        return Array.isArray(v) ? String(v[0]) : String(v);
    }
    return 'Request failed';
};

// ─── types ──────────────────────────────────────────────────────────────────

interface TSAAccount {
    id: number;
    account_number: string;
    account_name: string;
    bank: string;
    current_balance: string | number;
    mda_name?: string;
}

interface StatementLine {
    id: number;
    line_number: number;
    transaction_date: string;
    value_date: string | null;
    description: string;
    reference: string;
    debit: string | number;
    credit: string | number;
    balance_after: string | number | null;
    match_status: 'UNMATCHED' | 'AUTO' | 'MANUAL' | 'IGNORED';
    match_confidence: string | number;
    matched_payment: number | null;
    matched_payment_number: string | null;
    matched_revenue: number | null;
    matched_revenue_number: string | null;
    matched_by: number | null;
    matched_by_name: string | null;
    matched_at: string | null;
    updated_at: string;
}

interface ParseError {
    file_row?: number;
    data_row?: number;
    error: string;
}

interface StatementImport {
    id: number;
    tsa_account: number;
    tsa_account_number: string;
    tsa_account_name: string;
    original_filename: string;
    file_url: string | null;
    statement_from: string;
    statement_to: string;
    opening_balance: string | number;
    closing_balance: string | number;
    total_debits: string | number;
    total_credits: string | number;
    line_count: number;
    status: 'PARSED' | 'MATCHED' | 'COMPLETED' | 'FAILED';
    matched_count: number;
    unmatched_count: number;
    ignored_count: number;
    parse_errors: ParseError[];
    created_at: string;
    uploaded_by_name: string | null;
    lines?: StatementLine[];
}

interface Candidate {
    id: number;
    reference: string;
    date: string | null;
    amount: string | number;
    beneficiary?: string;
    payer?: string;
    narration?: string;
}

interface CandidatesResponse {
    payments: Candidate[];
    revenues: Candidate[];
}

interface Reconciliation {
    id: number;
    tsa_account: number;
    tsa_account_number: string;
    tsa_account_name: string;
    period_start: string;
    period_end: string;
    book_balance: string | number;
    statement_balance: string | number;
    adjusted_balance: string | number;
    unmatched_debits: string | number;
    unmatched_credits: string | number;
    difference: string | number;
    statement_import: number | null;
    status: 'DRAFT' | 'REVIEWED' | 'COMPLETED';
    completed_at: string | null;
    completed_by_name: string | null;
    notes: string;
    created_at: string;
}

// ─── common styles ──────────────────────────────────────────────────────────

const thStyle: React.CSSProperties = {
    padding: '0.5rem 0.625rem', textAlign: 'left', fontSize: '0.65rem',
    fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.03em',
    color: 'var(--color-text-muted, #64748b)',
    borderBottom: '2px solid var(--color-border, #e2e8f0)',
};
const tdStyle: React.CSSProperties = {
    padding: '0.5rem 0.625rem', fontSize: '0.8rem',
    color: 'var(--color-text, #1e293b)',
};

// ─── upload card ────────────────────────────────────────────────────────────

function UploadCard({
    tsaAccounts, onUploaded,
}: {
    tsaAccounts: TSAAccount[];
    onUploaded: (stmt: StatementImport) => void;
}) {
    const [tsaId, setTsaId] = useState<string>('');
    const [opening, setOpening] = useState<string>('0');
    const [file, setFile] = useState<File | null>(null);
    const [error, setError] = useState<string>('');
    const fileInputRef = useRef<HTMLInputElement>(null);

    const uploadMut = useMutation({
        mutationFn: async () => {
            if (!tsaId) throw new Error('Select a TSA account');
            if (!file) throw new Error('Choose a CSV file to upload');
            const fd = new FormData();
            fd.append('tsa_account', tsaId);
            fd.append('statement_file', file);
            fd.append('opening_balance', opening || '0');
            const res = await apiClient.post(
                '/accounting/tsa-bank-statements/', fd,
                { headers: { 'Content-Type': 'multipart/form-data' } },
            );
            return res.data as StatementImport;
        },
        onSuccess: (data) => {
            setError('');
            setFile(null);
            if (fileInputRef.current) fileInputRef.current.value = '';
            onUploaded(data);
        },
        onError: (err: any) => setError(extractBackendError(err)),
    });

    return (
        <div className="glass-card" style={{ padding: '1.25rem 1.5rem', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Upload size={18} color="#0f766e" />
                    <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>
                        Upload Bank Statement
                    </h3>
                </div>
                <a
                    href="/api/v1/accounting/tsa-bank-statements/sample-csv/"
                    download="tsa-statement-sample.csv"
                    style={{
                        display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                        fontSize: '0.75rem', color: '#0f766e', textDecoration: 'none',
                        padding: '0.25rem 0.625rem',
                        border: '1px solid #0f766e', borderRadius: '6px',
                    }}
                >
                    <Download size={12} /> Sample CSV
                </a>
            </div>
            <p style={{
                margin: '0 0 1rem', fontSize: '0.8rem',
                color: 'var(--color-text-muted, #64748b)',
            }}>
                CSV file with columns <strong>date, description, reference, debit, credit, balance</strong>.
                Any subset of these headers is accepted; other columns are ignored.
                Max file size 10 MB.
            </p>
            <div style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(240px, 1.5fr) 140px 1fr auto',
                gap: '0.75rem', alignItems: 'end',
            }}>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                    TSA Account
                    <select
                        value={tsaId}
                        onChange={e => setTsaId(e.target.value)}
                        style={{
                            display: 'block', width: '100%', marginTop: '0.25rem',
                            padding: '0.5rem', borderRadius: '6px',
                            border: '1px solid var(--color-border, #e2e8f0)',
                            fontSize: '0.85rem',
                        }}
                    >
                        <option value="">Select TSA account...</option>
                        {tsaAccounts.map(a => (
                            <option key={a.id} value={a.id}>
                                {a.account_number} — {a.account_name}
                            </option>
                        ))}
                    </select>
                </label>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                    Opening Balance
                    <input
                        type="number"
                        step="0.01"
                        value={opening}
                        onChange={e => setOpening(e.target.value)}
                        style={{
                            display: 'block', width: '100%', marginTop: '0.25rem',
                            padding: '0.5rem', borderRadius: '6px',
                            border: '1px solid var(--color-border, #e2e8f0)',
                            fontSize: '0.85rem',
                        }}
                    />
                </label>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                    Statement File (CSV)
                    <input
                        type="file"
                        ref={fileInputRef}
                        accept=".csv,.tsv,.txt"
                        onChange={e => setFile(e.target.files?.[0] ?? null)}
                        style={{
                            display: 'block', width: '100%', marginTop: '0.25rem',
                            fontSize: '0.8rem',
                        }}
                    />
                </label>
                <button
                    onClick={() => uploadMut.mutate()}
                    disabled={uploadMut.isPending || !tsaId || !file}
                    style={{
                        padding: '0.5rem 1rem',
                        background: uploadMut.isPending || !tsaId || !file
                            ? '#94a3b8'
                            : 'linear-gradient(135deg, #0f766e 0%, #065f46 100%)',
                        color: '#fff', border: 'none', borderRadius: '6px',
                        fontSize: '0.85rem', fontWeight: 600,
                        cursor: uploadMut.isPending || !tsaId || !file ? 'not-allowed' : 'pointer',
                        whiteSpace: 'nowrap',
                    }}
                >
                    {uploadMut.isPending ? 'Uploading...' : 'Upload & Parse'}
                </button>
            </div>
            {error && (
                <div style={{
                    marginTop: '0.75rem', padding: '0.5rem 0.75rem',
                    background: '#fef2f2', border: '1px solid #fecaca',
                    borderRadius: '6px', fontSize: '0.8rem', color: '#991b1b',
                    display: 'flex', gap: '0.5rem', alignItems: 'flex-start',
                }}>
                    <AlertCircle size={14} style={{ flexShrink: 0, marginTop: '2px' }} /> {error}
                </div>
            )}
        </div>
    );
}

// ─── reconciliation session card ────────────────────────────────────────────

function ReconciliationSessionCard({
    statement, reconciliation, onCreated, onCompleted,
}: {
    statement: StatementImport;
    reconciliation: Reconciliation | null;
    onCreated: (r: Reconciliation) => void;
    onCompleted: () => void;
}) {
    const [periodStart, setPeriodStart] = useState(statement.statement_from);
    const [periodEnd, setPeriodEnd] = useState(statement.statement_to);
    const [notes, setNotes] = useState('');
    const [error, setError] = useState('');

    const startMut = useMutation({
        mutationFn: async () => {
            const res = await apiClient.post('/accounting/tsa-bank-reconciliations/', {
                tsa_account: statement.tsa_account,
                period_start: periodStart,
                period_end: periodEnd,
                statement_import: statement.id,
                notes,
            });
            return res.data as Reconciliation;
        },
        onSuccess: (data) => { setError(''); onCreated(data); },
        onError: (err: any) => setError(extractBackendError(err)),
    });

    const refreshMut = useMutation({
        mutationFn: async () => {
            if (!reconciliation) return null;
            const res = await apiClient.post(
                `/accounting/tsa-bank-reconciliations/${reconciliation.id}/refresh/`,
            );
            return res.data as Reconciliation;
        },
        onSuccess: (data) => { if (data) onCreated(data); },
    });

    const completeMut = useMutation({
        mutationFn: async (force: boolean) => {
            if (!reconciliation) return null;
            const res = await apiClient.post(
                `/accounting/tsa-bank-reconciliations/${reconciliation.id}/complete/`,
                { force },
            );
            return res.data as Reconciliation;
        },
        onSuccess: () => { setError(''); onCompleted(); },
        onError: (err: any) => setError(extractBackendError(err)),
    });

    if (!reconciliation) {
        return (
            <div className="glass-card" style={{
                padding: '1.25rem 1.5rem', marginBottom: '1rem',
                borderLeft: '3px solid #0f766e',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                    <CalendarCheck size={18} color="#0f766e" />
                    <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>
                        Start Reconciliation Session
                    </h3>
                </div>
                <p style={{ margin: '0 0 0.75rem', fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                    A session locks in the book vs statement balances for this
                    period and, when completed, flags matched payments and revenue
                    collections as reconciled.
                </p>
                <div style={{
                    display: 'grid', gridTemplateColumns: '1fr 1fr 2fr auto',
                    gap: '0.75rem', alignItems: 'end',
                }}>
                    <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                        Period Start
                        <input
                            type="date"
                            value={periodStart}
                            onChange={e => setPeriodStart(e.target.value)}
                            style={inputStyle}
                        />
                    </label>
                    <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                        Period End
                        <input
                            type="date"
                            value={periodEnd}
                            onChange={e => setPeriodEnd(e.target.value)}
                            style={inputStyle}
                        />
                    </label>
                    <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                        Notes (optional)
                        <input
                            type="text"
                            value={notes}
                            onChange={e => setNotes(e.target.value)}
                            placeholder="e.g. End-of-April reconciliation"
                            style={inputStyle}
                        />
                    </label>
                    <button
                        onClick={() => startMut.mutate()}
                        disabled={startMut.isPending}
                        style={primaryBtnStyle}
                    >
                        {startMut.isPending ? 'Starting...' : 'Start Session'}
                    </button>
                </div>
                {error && <ErrorBanner msg={error} />}
            </div>
        );
    }

    const diff = Number(reconciliation.difference);
    const isBalanced = Math.abs(diff) < 0.01;
    const isCompleted = reconciliation.status === 'COMPLETED';

    return (
        <div className="glass-card" style={{
            padding: '1.25rem 1.5rem', marginBottom: '1rem',
            borderLeft: `3px solid ${isCompleted ? '#16a34a' : isBalanced ? '#0f766e' : '#d97706'}`,
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {isCompleted ? <Lock size={18} color="#16a34a" /> : <CalendarCheck size={18} color="#0f766e" />}
                    <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>
                        Reconciliation Session
                    </h3>
                    <span style={{
                        padding: '2px 10px', borderRadius: '12px',
                        fontSize: '0.7rem', fontWeight: 600,
                        background: isCompleted ? '#d1fae5' : '#dbeafe',
                        color: isCompleted ? '#065f46' : '#1e40af',
                    }}>
                        {reconciliation.status}
                    </span>
                </div>
                <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                    {reconciliation.period_start} → {reconciliation.period_end}
                    {reconciliation.completed_by_name && (
                        <> · Completed by <strong>{reconciliation.completed_by_name}</strong></>
                    )}
                </span>
            </div>

            <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                gap: '0.5rem', marginBottom: '0.75rem',
            }}>
                <Stat label="Book Balance" value={fmtNGN(reconciliation.book_balance)} color="#64748b" />
                <Stat label="Statement Balance" value={fmtNGN(reconciliation.statement_balance)} color="#2563eb" />
                <Stat label="Unmatched Debits" value={fmtNGN(reconciliation.unmatched_debits)} color="#dc2626" />
                <Stat label="Unmatched Credits" value={fmtNGN(reconciliation.unmatched_credits)} color="#16a34a" />
                <Stat
                    label="Difference"
                    value={fmtNGN(reconciliation.difference)}
                    color={isBalanced ? '#16a34a' : '#d97706'}
                />
            </div>

            {!isCompleted && (
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <button
                        onClick={() => refreshMut.mutate()}
                        disabled={refreshMut.isPending}
                        style={secondaryBtnStyle}
                    >
                        <RefreshCw size={14} />
                        {refreshMut.isPending ? 'Refreshing...' : 'Refresh Balances'}
                    </button>
                    <button
                        onClick={() => {
                            if (!isBalanced) {
                                const ok = window.confirm(
                                    `Book and statement differ by ${fmtNGN(diff)}. Complete anyway?`
                                );
                                if (!ok) return;
                                completeMut.mutate(true);
                            } else {
                                completeMut.mutate(false);
                            }
                        }}
                        disabled={completeMut.isPending}
                        style={{
                            ...primaryBtnStyle,
                            background: 'linear-gradient(135deg, #16a34a 0%, #15803d 100%)',
                        }}
                    >
                        <CheckCircle2 size={14} />
                        {completeMut.isPending ? 'Completing...' : 'Complete Reconciliation'}
                    </button>
                </div>
            )}
            {error && <ErrorBanner msg={error} />}
        </div>
    );
}

const inputStyle: React.CSSProperties = {
    display: 'block', width: '100%', marginTop: '0.25rem',
    padding: '0.5rem', borderRadius: '6px',
    border: '1px solid var(--color-border, #e2e8f0)',
    fontSize: '0.85rem',
};

const primaryBtnStyle: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
    padding: '0.5rem 1rem',
    background: 'linear-gradient(135deg, #0f766e 0%, #065f46 100%)',
    color: '#fff', border: 'none', borderRadius: '6px',
    fontSize: '0.85rem', fontWeight: 600,
    cursor: 'pointer', whiteSpace: 'nowrap',
};

const secondaryBtnStyle: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
    padding: '0.5rem 0.875rem',
    background: '#fff', color: 'var(--color-text, #1e293b)',
    border: '1px solid var(--color-border, #e2e8f0)',
    borderRadius: '6px',
    fontSize: '0.85rem', fontWeight: 500, cursor: 'pointer',
};

function ErrorBanner({ msg }: { msg: string }) {
    return (
        <div style={{
            marginTop: '0.75rem', padding: '0.5rem 0.75rem',
            background: '#fef2f2', border: '1px solid #fecaca',
            borderRadius: '6px', fontSize: '0.8rem', color: '#991b1b',
            display: 'flex', gap: '0.5rem', alignItems: 'flex-start',
        }}>
            <AlertCircle size={14} style={{ flexShrink: 0, marginTop: '2px' }} /> {msg}
        </div>
    );
}

// ─── manual match modal ─────────────────────────────────────────────────────

function ManualMatchModal({
    line, statementId, onClose, onMatched,
}: {
    line: StatementLine;
    statementId: number;
    onClose: () => void;
    onMatched: () => void;
}) {
    const [error, setError] = useState('');

    const { data: candidates, isLoading, isError } = useQuery<CandidatesResponse>({
        queryKey: ['tsa-stmt-candidates', statementId],
        queryFn: async () => {
            const res = await apiClient.get(
                `/accounting/tsa-bank-statements/${statementId}/candidates/`,
            );
            return res.data;
        },
    });

    const matchMut = useMutation({
        mutationFn: async (payload: { payment_id?: number; revenue_id?: number }) => {
            const res = await apiClient.post(
                `/accounting/tsa-bank-statement-lines/${line.id}/match/`,
                payload,
            );
            return res.data;
        },
        onSuccess: () => { onMatched(); onClose(); },
        onError: (err: any) => setError(extractBackendError(err)),
    });

    const isDebit = Number(line.debit) > 0;
    const pool = isDebit ? (candidates?.payments || []) : (candidates?.revenues || []);
    const lineAmount = Number(isDebit ? line.debit : line.credit);

    return (
        <div
            style={{
                position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                zIndex: 1000,
            }}
            onClick={onClose}
        >
            <div
                className="glass-card"
                style={{
                    background: '#fff', padding: '1.5rem',
                    width: '90%', maxWidth: '800px', maxHeight: '85vh',
                    overflow: 'auto',
                }}
                onClick={e => e.stopPropagation()}
            >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                    <h3 style={{ margin: 0 }}>
                        Match to {isDebit ? 'Payment' : 'Revenue Collection'}
                    </h3>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
                        <X size={20} />
                    </button>
                </div>

                <div style={{
                    padding: '0.75rem', background: '#f8fafc', borderRadius: '6px',
                    marginBottom: '1rem', fontSize: '0.85rem',
                }}>
                    <div><strong>Date:</strong> {line.transaction_date}</div>
                    <div><strong>Reference:</strong> {line.reference || '—'}</div>
                    <div><strong>Description:</strong> {line.description}</div>
                    <div><strong>Amount:</strong>{' '}
                        <span style={{ color: isDebit ? '#dc2626' : '#16a34a', fontWeight: 600 }}>
                            {fmtNGN(lineAmount)} {isDebit ? '(Debit)' : '(Credit)'}
                        </span>
                    </div>
                </div>

                {error && <ErrorBanner msg={error} />}

                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)', marginTop: '0.5rem', marginBottom: '0.5rem' }}>
                    Unmatched {isDebit ? 'Payment Instructions' : 'Revenue Collections'} in date window:
                </div>

                {isLoading ? (
                    <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                        Loading candidates...
                    </div>
                ) : isError ? (
                    <div style={{ padding: '1.5rem', textAlign: 'center', color: '#dc2626' }}>
                        Could not load candidates. Please try again.
                    </div>
                ) : pool.length === 0 ? (
                    <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                        No unmatched candidates found.
                    </div>
                ) : (
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                        <thead>
                            <tr style={{ background: '#f1f5f9' }}>
                                <th style={{ padding: '0.5rem', textAlign: 'left' }}>Reference</th>
                                <th style={{ padding: '0.5rem', textAlign: 'left' }}>Date</th>
                                <th style={{ padding: '0.5rem', textAlign: 'left' }}>
                                    {isDebit ? 'Beneficiary' : 'Payer'}
                                </th>
                                <th style={{ padding: '0.5rem', textAlign: 'right' }}>Amount</th>
                                <th />
                            </tr>
                        </thead>
                        <tbody>
                            {pool.map(c => {
                                const amtMatch = Math.abs(Number(c.amount) - lineAmount) < 0.01;
                                return (
                                    <tr key={c.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                        <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>
                                            {c.reference || '—'}
                                        </td>
                                        <td style={{ padding: '0.5rem' }}>{c.date || '—'}</td>
                                        <td style={{ padding: '0.5rem' }}>
                                            {c.beneficiary || c.payer || '—'}
                                        </td>
                                        <td style={{
                                            padding: '0.5rem', textAlign: 'right',
                                            fontWeight: 600,
                                            color: amtMatch ? '#16a34a' : 'inherit',
                                        }}>
                                            {fmtNGN(c.amount)}
                                            {amtMatch && ' ✓'}
                                        </td>
                                        <td style={{ padding: '0.5rem', textAlign: 'right' }}>
                                            <button
                                                onClick={() => matchMut.mutate(
                                                    isDebit ? { payment_id: c.id } : { revenue_id: c.id }
                                                )}
                                                disabled={matchMut.isPending}
                                                style={{
                                                    padding: '0.25rem 0.625rem',
                                                    background: '#0f766e', color: '#fff',
                                                    border: 'none', borderRadius: '4px',
                                                    fontSize: '0.75rem', fontWeight: 600,
                                                    cursor: matchMut.isPending ? 'not-allowed' : 'pointer',
                                                }}
                                            >
                                                {matchMut.isPending ? '...' : 'Link'}
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}

// ─── statement detail panel ─────────────────────────────────────────────────

function StatementDetail({
    statementId, onClose,
}: {
    statementId: number;
    onClose: () => void;
}) {
    const qc = useQueryClient();
    const [matchLine, setMatchLine] = useState<StatementLine | null>(null);
    const [filter, setFilter] = useState<'all' | 'matched' | 'unmatched' | 'ignored'>('all');
    const [actionError, setActionError] = useState('');
    const [showErrors, setShowErrors] = useState(false);

    const { data: stmt, refetch } = useQuery<StatementImport>({
        queryKey: ['tsa-statement', statementId],
        queryFn: async () => {
            const res = await apiClient.get(`/accounting/tsa-bank-statements/${statementId}/`);
            return res.data;
        },
    });

    // Session for this statement (if any exists).
    const { data: sessionsRaw } = useQuery<{ results?: Reconciliation[] } | Reconciliation[]>({
        queryKey: ['tsa-reconciliations', statementId],
        queryFn: async () => {
            const res = await apiClient.get('/accounting/tsa-bank-reconciliations/', {
                params: { statement_import: statementId, page_size: 5 },
            });
            return res.data;
        },
    });
    const sessions: Reconciliation[] = Array.isArray(sessionsRaw)
        ? sessionsRaw
        : (sessionsRaw?.results ?? []);
    const activeSession = sessions[0] || null;

    const autoMatch = useMutation({
        mutationFn: async () => {
            const res = await apiClient.post(
                `/accounting/tsa-bank-statements/${statementId}/auto_match/`,
            );
            return res.data;
        },
        onSuccess: () => {
            setActionError('');
            refetch();
            qc.invalidateQueries({ queryKey: ['tsa-statements'] });
        },
        onError: (err: any) => setActionError(extractBackendError(err)),
    });

    const unmatch = useMutation({
        mutationFn: async (lineId: number) => {
            await apiClient.post(
                `/accounting/tsa-bank-statement-lines/${lineId}/unmatch/`,
            );
        },
        onSuccess: () => { setActionError(''); refetch(); },
        onError: (err: any) => setActionError(extractBackendError(err)),
    });

    const ignoreMut = useMutation({
        mutationFn: async (lineId: number) => {
            await apiClient.post(
                `/accounting/tsa-bank-statement-lines/${lineId}/ignore/`,
            );
        },
        onSuccess: () => { setActionError(''); refetch(); },
        onError: (err: any) => setActionError(extractBackendError(err)),
    });

    if (!stmt) return null;

    const filteredLines = (stmt.lines || []).filter(l => {
        if (filter === 'matched') return l.match_status === 'AUTO' || l.match_status === 'MANUAL';
        if (filter === 'unmatched') return l.match_status === 'UNMATCHED';
        if (filter === 'ignored') return l.match_status === 'IGNORED';
        return true;
    });

    const isLocked = stmt.status === 'COMPLETED';

    return (
        <>
            {/* Session card */}
            <ReconciliationSessionCard
                statement={stmt}
                reconciliation={activeSession}
                onCreated={() => {
                    qc.invalidateQueries({ queryKey: ['tsa-reconciliations', statementId] });
                    refetch();
                }}
                onCompleted={() => {
                    qc.invalidateQueries({ queryKey: ['tsa-reconciliations', statementId] });
                    qc.invalidateQueries({ queryKey: ['tsa-statements'] });
                    refetch();
                }}
            />

            <div className="glass-card" style={{ padding: '1.25rem 1.5rem' }}>
                <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    marginBottom: '0.75rem',
                }}>
                    <div>
                        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>
                            <FileText size={16} style={{ verticalAlign: 'middle', marginRight: '0.375rem' }} />
                            {stmt.original_filename}
                            {isLocked && (
                                <Lock size={14} style={{ marginLeft: '0.375rem', verticalAlign: 'middle' }} color="#16a34a" />
                            )}
                        </h3>
                        <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
                            {stmt.tsa_account_number} · {stmt.statement_from} → {stmt.statement_to} · {stmt.line_count} lines
                            {stmt.uploaded_by_name && <> · uploaded by <strong>{stmt.uploaded_by_name}</strong></>}
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.375rem' }}>
                        {stmt.file_url && (
                            <a
                                href={stmt.file_url}
                                target="_blank"
                                rel="noreferrer"
                                style={{
                                    padding: '0.375rem 0.625rem',
                                    background: '#fff', border: '1px solid #e2e8f0',
                                    borderRadius: '6px', cursor: 'pointer',
                                    display: 'flex', alignItems: 'center', gap: '0.25rem',
                                    fontSize: '0.75rem', color: '#0f766e', textDecoration: 'none',
                                }}
                            >
                                <Download size={12} /> Original
                            </a>
                        )}
                        <button onClick={onClose} style={{
                            padding: '0.375rem', background: 'none', border: '1px solid #e2e8f0',
                            borderRadius: '6px', cursor: 'pointer',
                        }}>
                            <X size={16} />
                        </button>
                    </div>
                </div>

                {/* Parse errors (M10) */}
                {stmt.parse_errors && stmt.parse_errors.length > 0 && (
                    <div style={{
                        padding: '0.5rem 0.75rem', marginBottom: '0.75rem',
                        background: '#fef3c7', border: '1px solid #fcd34d',
                        borderRadius: '6px', fontSize: '0.8rem',
                    }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ color: '#92400e', fontWeight: 600 }}>
                                <AlertCircle size={12} style={{ verticalAlign: 'middle' }} />{' '}
                                {stmt.parse_errors.length} row(s) skipped during parsing
                            </span>
                            <button
                                onClick={() => setShowErrors(v => !v)}
                                style={{
                                    background: 'none', border: 'none', cursor: 'pointer',
                                    fontSize: '0.75rem', color: '#92400e', textDecoration: 'underline',
                                    display: 'flex', alignItems: 'center', gap: '0.25rem',
                                }}
                            >
                                {showErrors ? <EyeOff size={12} /> : <Eye size={12} />}
                                {showErrors ? 'Hide' : 'Show'}
                            </button>
                        </div>
                        {showErrors && (
                            <ul style={{ margin: '0.5rem 0 0 0', paddingLeft: '1.25rem', color: '#78350f' }}>
                                {stmt.parse_errors.map((e, i) => (
                                    <li key={i}>
                                        File row {e.file_row ?? '?'}: {e.error}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                )}

                {/* Summary strip */}
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                    gap: '0.5rem', marginBottom: '1rem',
                }}>
                    <Stat label="Opening" value={fmtNGN(stmt.opening_balance)} color="#64748b" />
                    <Stat label="Credits" value={fmtNGN(stmt.total_credits)} color="#16a34a" />
                    <Stat label="Debits" value={fmtNGN(stmt.total_debits)} color="#dc2626" />
                    <Stat label="Closing" value={fmtNGN(stmt.closing_balance)} color="#0f766e" />
                    <Stat
                        label="Matched"
                        value={`${stmt.matched_count} / ${stmt.line_count}`}
                        color="#2563eb"
                    />
                    {stmt.ignored_count > 0 && (
                        <Stat label="Ignored" value={String(stmt.ignored_count)} color="#6b7280" />
                    )}
                </div>

                {/* Actions */}
                <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
                    <button
                        onClick={() => autoMatch.mutate()}
                        disabled={autoMatch.isPending || isLocked}
                        style={{
                            ...primaryBtnStyle,
                            opacity: isLocked ? 0.5 : 1,
                            cursor: isLocked ? 'not-allowed' : 'pointer',
                        }}
                    >
                        <Play size={14} />
                        {autoMatch.isPending ? 'Matching...' : 'Run Auto-Match'}
                    </button>
                    {autoMatch.data && (
                        <div style={{
                            padding: '0.5rem 0.75rem', background: '#ecfdf5',
                            border: '1px solid #a7f3d0', borderRadius: '6px',
                            fontSize: '0.8rem', color: '#065f46',
                        }}>
                            ✓ Matched {autoMatch.data.result?.matched ?? 0} of {autoMatch.data.result?.total_lines ?? 0}
                            {autoMatch.data.result?.ambiguous > 0 && (
                                <> · {autoMatch.data.result.ambiguous} ambiguous</>
                            )}
                        </div>
                    )}
                    <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                        <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>Filter:</span>
                        {(['all', 'matched', 'unmatched', 'ignored'] as const).map(f => (
                            <button
                                key={f}
                                onClick={() => setFilter(f)}
                                style={{
                                    padding: '0.25rem 0.625rem',
                                    background: filter === f ? '#0f766e' : '#fff',
                                    color: filter === f ? '#fff' : '#64748b',
                                    border: '1px solid var(--color-border, #e2e8f0)',
                                    borderRadius: '4px',
                                    fontSize: '0.75rem', fontWeight: 600,
                                    cursor: 'pointer', textTransform: 'capitalize',
                                }}
                            >
                                {f}
                            </button>
                        ))}
                    </div>
                </div>

                {actionError && <ErrorBanner msg={actionError} />}

                {/* Lines table */}
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                        <thead>
                            <tr style={{ background: '#f8fafc' }}>
                                <th style={thStyle}>Date</th>
                                <th style={thStyle}>Reference</th>
                                <th style={thStyle}>Description</th>
                                <th style={{ ...thStyle, textAlign: 'right' }}>Debit</th>
                                <th style={{ ...thStyle, textAlign: 'right' }}>Credit</th>
                                <th style={thStyle}>Match</th>
                                <th style={{ ...thStyle, textAlign: 'right' }}>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredLines.map(l => (
                                <tr key={l.id} style={{
                                    borderBottom: '1px solid #f1f5f9',
                                    background: l.match_status === 'UNMATCHED' ? '#fffbeb'
                                        : l.match_status === 'IGNORED' ? '#f3f4f6'
                                        : 'transparent',
                                }}>
                                    <td style={tdStyle}>{l.transaction_date}</td>
                                    <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: '0.75rem' }}>
                                        {l.reference || '—'}
                                    </td>
                                    <td style={tdStyle}>{l.description || '—'}</td>
                                    <td style={{ ...tdStyle, textAlign: 'right', color: '#dc2626', fontWeight: Number(l.debit) > 0 ? 600 : 400 }}>
                                        {Number(l.debit) > 0 ? fmtNGN(l.debit) : ''}
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'right', color: '#16a34a', fontWeight: Number(l.credit) > 0 ? 600 : 400 }}>
                                        {Number(l.credit) > 0 ? fmtNGN(l.credit) : ''}
                                    </td>
                                    <td style={tdStyle}>
                                        <MatchBadge line={l} />
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'right' }}>
                                        {isLocked ? (
                                            <span style={{ fontSize: '0.7rem', color: '#94a3b8' }}>Locked</span>
                                        ) : l.match_status === 'UNMATCHED' ? (
                                            <div style={{ display: 'flex', gap: '0.25rem', justifyContent: 'flex-end' }}>
                                                <button
                                                    onClick={() => setMatchLine(l)}
                                                    style={linkBtnStyle}
                                                >
                                                    <LinkIcon size={10} /> Link
                                                </button>
                                                <button
                                                    onClick={() => {
                                                        if (window.confirm('Mark this line as ignored? Use for bank charges or items with no book entry.')) {
                                                            ignoreMut.mutate(l.id);
                                                        }
                                                    }}
                                                    style={ignoreBtnStyle}
                                                >
                                                    Ignore
                                                </button>
                                            </div>
                                        ) : (
                                            <button
                                                onClick={() => unmatch.mutate(l.id)}
                                                style={unlinkBtnStyle}
                                            >
                                                {l.match_status === 'IGNORED' ? 'Restore' : 'Unlink'}
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {matchLine && (
                    <ManualMatchModal
                        line={matchLine}
                        statementId={statementId}
                        onClose={() => setMatchLine(null)}
                        onMatched={() => { refetch(); setMatchLine(null); }}
                    />
                )}
            </div>
        </>
    );
}

const linkBtnStyle: React.CSSProperties = {
    padding: '0.25rem 0.5rem', background: '#0f766e',
    color: '#fff', border: 'none', borderRadius: '4px',
    fontSize: '0.7rem', fontWeight: 600, cursor: 'pointer',
    display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
};

const ignoreBtnStyle: React.CSSProperties = {
    padding: '0.25rem 0.5rem', background: '#fff',
    color: '#6b7280', border: '1px solid #d1d5db',
    borderRadius: '4px', fontSize: '0.7rem',
    fontWeight: 600, cursor: 'pointer',
};

const unlinkBtnStyle: React.CSSProperties = {
    padding: '0.25rem 0.5rem', background: '#fff',
    color: '#dc2626', border: '1px solid #fecaca',
    borderRadius: '4px', fontSize: '0.7rem',
    fontWeight: 600, cursor: 'pointer',
};

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
    return (
        <div style={{
            padding: '0.625rem 0.75rem',
            background: `${color}10`, border: `1px solid ${color}30`,
            borderRadius: '6px',
        }}>
            <div style={{ fontSize: '0.65rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>
                {label}
            </div>
            <div style={{ fontSize: '0.95rem', fontWeight: 700, color }}>
                {value}
            </div>
        </div>
    );
}

function MatchBadge({ line }: { line: StatementLine }) {
    const map: Record<StatementLine['match_status'], { bg: string; color: string; label: string }> = {
        UNMATCHED: { bg: '#fef3c7', color: '#92400e', label: 'Unmatched' },
        AUTO:      { bg: '#dbeafe', color: '#1e40af', label: `Auto (${Math.round(Number(line.match_confidence))}%)` },
        MANUAL:    { bg: '#d1fae5', color: '#065f46', label: 'Manual' },
        IGNORED:   { bg: '#e5e7eb', color: '#374151', label: 'Ignored' },
    };
    const style = map[line.match_status];
    const ref = line.matched_payment_number || line.matched_revenue_number;
    return (
        <div>
            <span style={{
                padding: '2px 8px', borderRadius: '12px',
                fontSize: '0.65rem', fontWeight: 600,
                background: style.bg, color: style.color,
            }}>
                {style.label}
            </span>
            {ref && (
                <div style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)', marginTop: '2px' }}>
                    → {ref}
                </div>
            )}
            {line.matched_by_name && (
                <div style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)' }}>
                    by {line.matched_by_name}
                </div>
            )}
        </div>
    );
}

// ─── main page ──────────────────────────────────────────────────────────────

const PAGE_SIZE = 25;

export default function BankReconciliation() {
    const qc = useQueryClient();
    const [selectedStatementId, setSelectedStatementId] = useState<number | null>(null);
    const [page, setPage] = useState(1);

    const { data: tsaAccountsRaw } = useQuery<{ results?: TSAAccount[] } | TSAAccount[]>({
        queryKey: ['tsa-accounts-for-recon'],
        queryFn: async () => {
            const res = await apiClient.get('/accounting/tsa-accounts/', {
                params: { is_active: true, page_size: 200 },
            });
            return res.data;
        },
    });
    const tsaAccounts: TSAAccount[] = Array.isArray(tsaAccountsRaw)
        ? tsaAccountsRaw
        : (tsaAccountsRaw?.results ?? []);

    const { data: statementsData, refetch: refetchStatements } = useQuery<
        { results?: StatementImport[]; count?: number } | StatementImport[]
    >({
        queryKey: ['tsa-statements', page],
        queryFn: async () => {
            const res = await apiClient.get('/accounting/tsa-bank-statements/', {
                params: { page, page_size: PAGE_SIZE },
            });
            return res.data;
        },
    });
    const statements: StatementImport[] = useMemo(() => {
        if (!statementsData) return [];
        if (Array.isArray(statementsData)) return statementsData;
        return statementsData.results ?? [];
    }, [statementsData]);
    const totalCount = useMemo(() => {
        if (!statementsData) return 0;
        if (Array.isArray(statementsData)) return statementsData.length;
        return statementsData.count ?? 0;
    }, [statementsData]);
    const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

    const statusBadge = (s: StatementImport['status']) => {
        const map = {
            PARSED:    { bg: '#fef3c7', color: '#92400e' },
            MATCHED:   { bg: '#dbeafe', color: '#1e40af' },
            COMPLETED: { bg: '#d1fae5', color: '#065f46' },
            FAILED:    { bg: '#fee2e2', color: '#991b1b' },
        };
        return map[s];
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Bank Reconciliation"
                    subtitle="Upload bank statements, auto-match against system transactions, and close the period"
                />

                <UploadCard
                    tsaAccounts={tsaAccounts}
                    onUploaded={(stmt) => {
                        qc.invalidateQueries({ queryKey: ['tsa-statements'] });
                        // Only auto-open the new upload — don't re-select on
                        // every subsequent list refresh (L5).
                        setSelectedStatementId(stmt.id);
                    }}
                />

                {/* Statements list */}
                <div className="glass-card" style={{ padding: '1rem 1.25rem', marginBottom: '1rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                        <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700 }}>
                            <Landmark size={16} style={{ verticalAlign: 'middle', marginRight: '0.375rem' }} />
                            Uploaded Statements {totalCount > 0 && <span style={{ color: 'var(--color-text-muted)', fontWeight: 400, fontSize: '0.8rem' }}>· {totalCount} total</span>}
                        </h3>
                        <button
                            onClick={() => refetchStatements()}
                            style={{
                                padding: '0.375rem 0.625rem', background: 'none',
                                border: '1px solid #e2e8f0', borderRadius: '6px',
                                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.25rem',
                                fontSize: '0.75rem', color: 'var(--color-text-muted)',
                            }}
                        >
                            <RefreshCw size={12} /> Refresh
                        </button>
                    </div>
                    {statements.length === 0 ? (
                        <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
                            No statements uploaded yet. Use the upload card above to start.
                        </div>
                    ) : (
                        <>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                                <thead>
                                    <tr style={{ background: '#f8fafc' }}>
                                        <th style={thStyle}>TSA</th>
                                        <th style={thStyle}>File</th>
                                        <th style={thStyle}>Period</th>
                                        <th style={{ ...thStyle, textAlign: 'right' }}>Lines</th>
                                        <th style={{ ...thStyle, textAlign: 'right' }}>Matched</th>
                                        <th style={{ ...thStyle, textAlign: 'right' }}>Closing</th>
                                        <th style={thStyle}>Status</th>
                                        <th />
                                    </tr>
                                </thead>
                                <tbody>
                                    {statements.map(s => (
                                        <tr
                                            key={s.id}
                                            style={{
                                                borderBottom: '1px solid #f1f5f9',
                                                background: s.id === selectedStatementId ? '#f0fdfa' : 'transparent',
                                                cursor: 'pointer',
                                            }}
                                            onClick={() => setSelectedStatementId(
                                                s.id === selectedStatementId ? null : s.id
                                            )}
                                        >
                                            <td style={tdStyle}>
                                                {s.tsa_account_number}
                                                <div style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                                                    {s.tsa_account_name}
                                                </div>
                                            </td>
                                            <td style={tdStyle}>{s.original_filename}</td>
                                            <td style={tdStyle}>{s.statement_from} → {s.statement_to}</td>
                                            <td style={{ ...tdStyle, textAlign: 'right' }}>{s.line_count}</td>
                                            <td style={{ ...tdStyle, textAlign: 'right' }}>
                                                {s.matched_count}{' / '}{s.line_count}
                                                {s.unmatched_count > 0 && (
                                                    <span style={{ color: '#dc2626', fontSize: '0.7rem', marginLeft: '0.25rem' }}>
                                                        ({s.unmatched_count} left)
                                                    </span>
                                                )}
                                            </td>
                                            <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600 }}>
                                                {fmtNGN(s.closing_balance)}
                                            </td>
                                            <td style={tdStyle}>
                                                <span style={{
                                                    padding: '2px 8px', borderRadius: '12px',
                                                    fontSize: '0.65rem', fontWeight: 600,
                                                    ...statusBadge(s.status),
                                                }}>
                                                    {s.status}
                                                </span>
                                            </td>
                                            <td style={{ ...tdStyle, textAlign: 'right' }}>
                                                {s.id === selectedStatementId ? '▼' : '▶'}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>

                            {/* Pagination (L8) */}
                            {totalPages > 1 && (
                                <div style={{
                                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                    marginTop: '0.75rem', paddingTop: '0.75rem',
                                    borderTop: '1px solid var(--color-border, #e8ecf1)',
                                    fontSize: '0.75rem', color: 'var(--color-text-muted)',
                                }}>
                                    <span>
                                        Page {page} of {totalPages} · Showing {(page - 1) * PAGE_SIZE + 1}
                                        –{Math.min(page * PAGE_SIZE, totalCount)} of {totalCount}
                                    </span>
                                    <div style={{ display: 'flex', gap: '0.375rem' }}>
                                        <button
                                            onClick={() => setPage(p => Math.max(1, p - 1))}
                                            disabled={page === 1}
                                            style={{
                                                ...secondaryBtnStyle,
                                                padding: '0.25rem 0.625rem',
                                                fontSize: '0.75rem',
                                                opacity: page === 1 ? 0.5 : 1,
                                                cursor: page === 1 ? 'not-allowed' : 'pointer',
                                            }}
                                        >
                                            Previous
                                        </button>
                                        <button
                                            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                                            disabled={page >= totalPages}
                                            style={{
                                                ...secondaryBtnStyle,
                                                padding: '0.25rem 0.625rem',
                                                fontSize: '0.75rem',
                                                opacity: page >= totalPages ? 0.5 : 1,
                                                cursor: page >= totalPages ? 'not-allowed' : 'pointer',
                                            }}
                                        >
                                            Next
                                        </button>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </div>

                {selectedStatementId && (
                    <StatementDetail
                        statementId={selectedStatementId}
                        onClose={() => setSelectedStatementId(null)}
                    />
                )}
            </main>
        </div>
    );
}
