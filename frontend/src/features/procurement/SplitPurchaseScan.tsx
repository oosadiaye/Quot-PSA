/**
 * SplitPurchaseScan — advisory scan for threshold evasion and duplicates.
 * Route: /procurement/split-scan
 *
 * `ProcurementThreshold` already enforces the BPP ceilings correctly. The
 * evasion this page is about is not exceeding one — it is three orders
 * just beneath it, to the same vendor, in the same fortnight. Every order
 * passes every check; only the pattern is wrong.
 *
 * The page reports and nothing more. It cannot block, cancel or amend an
 * order, and most of what it lists has already been paid. Its entire job
 * is to decide where a reviewer looks first, which is why the ordering is
 * by how far over the ceiling a cluster went rather than by date.
 *
 * The arithmetic that finds clusters runs server-side whether or not AI
 * is configured; a model only judges whether descriptions read as one
 * divided requirement. When it is off or unreachable every cluster still
 * appears, marked "not assessed" — the finding stands on the arithmetic.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    AlertTriangle, Search, Copy, ShieldAlert, Info, ArrowLeft, CheckCircle2,
    HelpCircle,
} from 'lucide-react';
import { useMutation } from '@tanstack/react-query';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import apiClient from '../../api/client';
import { formatApiError } from '../../utils/apiError';

interface Cluster {
    vendor_id: number;
    vendor_name: string;
    purchase_ids: number[];
    total: string;
    ceiling: string;
    excess: string;
    escalates_to: string;
    first_date: string;
    last_date: string;
    span_days: number;
    verdict: 'DIVIDED' | 'SEPARATE' | 'UNCLEAR';
    confidence: number;
    reason: string;
}

interface Duplicate {
    vendor_id: number;
    vendor_name: string;
    purchase_ids: number[];
    amount: string;
    difference: string;
    days_apart: number;
}

interface ScanResult {
    window: { since: string; until: string };
    orders_examined: number;
    ai_judging: boolean;
    split_clusters: Cluster[];
    duplicate_candidates: Duplicate[];
}

const card: React.CSSProperties = {
    background: 'var(--color-surface)', borderRadius: 12, border: '1px solid var(--color-border)',
    padding: 20, marginBottom: 16,
};
const lbl: React.CSSProperties = {
    fontSize: 11, fontWeight: 700, color: 'var(--color-text-muted)',
    textTransform: 'uppercase', letterSpacing: '0.4px',
};
const pill = (bg: string, fg: string): React.CSSProperties => ({
    display: 'inline-flex', alignItems: 'center', gap: 4,
    padding: '2px 9px', borderRadius: 999, fontSize: 11,
    fontWeight: 700, background: bg, color: fg, whiteSpace: 'nowrap',
});

/** Nigerian convention: ₦ with thousands separators, no decimals on large sums. */
const naira = (v: string | number) => {
    const n = Number(v ?? 0);
    return `₦${n.toLocaleString('en-NG', { maximumFractionDigits: 2 })}`;
};

const ddmmyyyy = (iso: string) =>
    new Date(iso).toLocaleDateString('en-GB', {
        day: '2-digit', month: '2-digit', year: 'numeric',
    });

const today = () => new Date().toISOString().slice(0, 10);
const aYearAgo = () => {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 1);
    return d.toISOString().slice(0, 10);
};

const VERDICT_STYLE: Record<Cluster['verdict'], { style: React.CSSProperties; label: string; icon: React.ReactNode }> = {
    DIVIDED: {
        style: pill('#fee2e2', '#991b1b'),
        label: 'Looks divided',
        icon: <ShieldAlert size={12} />,
    },
    SEPARATE: {
        style: pill('#dcfce7', '#166534'),
        label: 'Looks separate',
        icon: <CheckCircle2 size={12} />,
    },
    UNCLEAR: {
        style: pill('#f1f5f9', '#475569'),
        label: 'Not assessed',
        icon: <HelpCircle size={12} />,
    },
};

export default function SplitPurchaseScan() {
    const navigate = useNavigate();
    const [since, setSince] = useState(aYearAgo());
    const [until, setUntil] = useState(today());
    const [error, setError] = useState('');
    const [result, setResult] = useState<ScanResult | null>(null);

    const scan = useMutation({
        mutationFn: async () =>
            (await apiClient.post('/procurement/split-scan/', { since, until })).data as ScanResult,
        onSuccess: (data) => { setError(''); setResult(data); },
        onError: (e) => { setResult(null); setError(formatApiError(e, 'The scan could not run.')); },
    });

    const input: React.CSSProperties = {
        padding: '8px 10px', fontSize: 13, borderRadius: 6,
        border: '1.5px solid var(--color-border)', background: 'var(--color-surface)',
    };

    return (
        <div style={{ display: 'flex', background: 'var(--color-background)', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: 260, padding: 32 }}>
                <PageHeader
                    title="Split & Duplicate Scan"
                    subtitle="Purchase orders that individually clear an approval ceiling but together do not"
                    onBack={() => navigate('/procurement/orders')}
                    actions={
                        <button
                            type="button"
                            onClick={() => navigate('/procurement/orders')}
                            style={{
                                padding: '8px 16px', borderRadius: 8, cursor: 'pointer',
                                background: 'rgba(255,255,255,0.12)', color: '#fff',
                                border: '1px solid rgba(255,255,255,0.25)', fontSize: 13,
                                fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6,
                            }}
                        >
                            <ArrowLeft size={14} /> Back to Purchase Orders
                        </button>
                    }
                />

                <div style={{
                    padding: '12px 16px', borderRadius: 8, marginBottom: 16,
                    background: '#f0f9ff', border: '1px solid #bae6fd', color: '#075985',
                    display: 'flex', alignItems: 'flex-start', gap: 10, fontSize: 13, lineHeight: 1.6,
                }}>
                    <Info size={16} style={{ flexShrink: 0, marginTop: 2 }} />
                    <span>
                        <strong>Advisory only.</strong> Nothing here blocks, cancels or amends an
                        order, and most of what it lists has already been paid. Approval ceilings
                        are enforced elsewhere and continue to work; this looks for the pattern a
                        ceiling cannot see &mdash; several orders just beneath it, to one vendor,
                        close together.
                    </span>
                </div>

                {/* ── Controls ────────────────────────────────────────── */}
                <div style={{ ...card, display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap' }}>
                    <div>
                        <label style={{ ...lbl, display: 'block', marginBottom: 4 }} htmlFor="since">From</label>
                        <input id="since" type="date" value={since} style={input}
                            onChange={(e) => setSince(e.target.value)} />
                    </div>
                    <div>
                        <label style={{ ...lbl, display: 'block', marginBottom: 4 }} htmlFor="until">To</label>
                        <input id="until" type="date" value={until} style={input}
                            onChange={(e) => setUntil(e.target.value)} />
                    </div>
                    <button
                        type="button"
                        onClick={() => scan.mutate()}
                        disabled={scan.isPending}
                        style={{
                            padding: '9px 18px', borderRadius: 8, fontSize: 13, fontWeight: 700,
                            display: 'flex', alignItems: 'center', gap: 8,
                            cursor: scan.isPending ? 'wait' : 'pointer',
                            background: '#1d4ed8', color: '#fff', border: '1px solid #1e40af',
                        }}
                    >
                        <Search size={15} />{scan.isPending ? 'Scanning…' : 'Run scan'}
                    </button>
                    {result && (
                        <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>
                            {result.orders_examined} order{result.orders_examined === 1 ? '' : 's'} examined
                            {' · '}
                            {result.ai_judging
                                ? 'descriptions assessed'
                                : 'descriptions not assessed (AI detection is off)'}
                        </div>
                    )}
                </div>

                {error && (
                    <div style={{
                        ...card, background: '#fef2f2', borderColor: '#fca5a5', color: '#991b1b',
                        fontSize: 13,
                    }}>{error}</div>
                )}

                {result && (
                    <>
                        {/* ── Split clusters ──────────────────────────── */}
                        <div style={card}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                                <AlertTriangle size={17} style={{ color: '#b45309' }} />
                                <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--color-text)' }}>
                                    Possible split purchases
                                </span>
                            </div>
                            <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', lineHeight: 1.6, marginBottom: 14 }}>
                                Ordered by how far over the ceiling each group went, not by date —
                                the largest gap is where a reviewer should start.
                            </div>

                            {result.split_clusters.length === 0 ? (
                                <div style={{ color: 'var(--color-text-muted)', fontSize: 13 }} data-testid="no-clusters">
                                    No groups crossed an approval ceiling in this period.
                                </div>
                            ) : (
                                <div style={{ overflowX: 'auto' }}>
                                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, minWidth: 860 }}
                                        data-testid="cluster-table">
                                        <thead>
                                            <tr style={{ textAlign: 'left', color: 'var(--color-text-secondary)', background: 'var(--color-surface-hover)' }}>
                                                {['Vendor', 'Orders', 'Window', 'Combined', 'Ceiling', 'Over by',
                                                    'Would have needed', 'Assessment'].map((h) => (
                                                    <th key={h} style={{ padding: '8px 10px', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.3px' }}>{h}</th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {result.split_clusters.map((c) => {
                                                const v = VERDICT_STYLE[c.verdict] ?? VERDICT_STYLE.UNCLEAR;
                                                return (
                                                    <tr key={`${c.vendor_id}-${c.purchase_ids.join('-')}`}
                                                        style={{ borderTop: '1px solid var(--color-border-light)' }}>
                                                        <td style={{ padding: '8px 10px', fontWeight: 600 }}>{c.vendor_name}</td>
                                                        <td style={{ padding: '8px 10px' }}>
                                                            {c.purchase_ids.length}
                                                            <span style={{ color: 'var(--color-text-subtle)' }}> (#{c.purchase_ids.join(', #')})</span>
                                                        </td>
                                                        <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>
                                                            {ddmmyyyy(c.first_date)} – {ddmmyyyy(c.last_date)}
                                                            <span style={{ color: 'var(--color-text-subtle)' }}> ({c.span_days}d)</span>
                                                        </td>
                                                        <td style={{ padding: '8px 10px', fontWeight: 700 }}>{naira(c.total)}</td>
                                                        <td style={{ padding: '8px 10px', color: 'var(--color-text-muted)' }}>{naira(c.ceiling)}</td>
                                                        <td style={{ padding: '8px 10px', color: '#b91c1c', fontWeight: 600 }}>{naira(c.excess)}</td>
                                                        <td style={{ padding: '8px 10px' }}>{c.escalates_to}</td>
                                                        <td style={{ padding: '8px 10px' }}>
                                                            <span style={v.style} title={c.reason || undefined}>
                                                                {v.icon}{v.label}
                                                                {c.verdict !== 'UNCLEAR' && c.confidence > 0 && (
                                                                    <span style={{ opacity: 0.75 }}>
                                                                        {' '}{Math.round(c.confidence * 100)}%
                                                                    </span>
                                                                )}
                                                            </span>
                                                            {c.reason && (
                                                                <div style={{ color: 'var(--color-text-muted)', marginTop: 4, maxWidth: 320, lineHeight: 1.5 }}>
                                                                    {c.reason}
                                                                </div>
                                                            )}
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>

                        {/* ── Duplicates ──────────────────────────────── */}
                        <div style={card}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                                <Copy size={17} style={{ color: '#0369a1' }} />
                                <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--color-text)' }}>
                                    Possible duplicate payments
                                </span>
                            </div>
                            <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', lineHeight: 1.6, marginBottom: 14 }}>
                                Same vendor, near-identical amount, close together, different
                                references. Orders sharing a reference are one document seen
                                twice and are not listed.
                            </div>

                            {result.duplicate_candidates.length === 0 ? (
                                <div style={{ color: 'var(--color-text-muted)', fontSize: 13 }} data-testid="no-duplicates">
                                    No near-identical repeat orders in this period.
                                </div>
                            ) : (
                                <div style={{ overflowX: 'auto' }}>
                                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, minWidth: 620 }}
                                        data-testid="duplicate-table">
                                        <thead>
                                            <tr style={{ textAlign: 'left', color: 'var(--color-text-secondary)', background: 'var(--color-surface-hover)' }}>
                                                {['Vendor', 'Orders', 'Amount', 'Difference', 'Days apart'].map((h) => (
                                                    <th key={h} style={{ padding: '8px 10px', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.3px' }}>{h}</th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {result.duplicate_candidates.map((d) => (
                                                <tr key={d.purchase_ids.join('-')} style={{ borderTop: '1px solid var(--color-border-light)' }}>
                                                    <td style={{ padding: '8px 10px', fontWeight: 600 }}>{d.vendor_name}</td>
                                                    <td style={{ padding: '8px 10px' }}>#{d.purchase_ids.join(', #')}</td>
                                                    <td style={{ padding: '8px 10px', fontWeight: 700 }}>{naira(d.amount)}</td>
                                                    <td style={{ padding: '8px 10px' }}>{naira(d.difference)}</td>
                                                    <td style={{ padding: '8px 10px' }}>{d.days_apart}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    </>
                )}
            </main>
        </div>
    );
}
