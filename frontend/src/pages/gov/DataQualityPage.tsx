/**
 * GL Data Quality Diagnostics — Quot PSE
 * Route: /accounting/data-quality
 *
 * Runs five audit checks against the live GL and renders:
 *   - Overall health banner (OK / WARN / FAIL)
 *   - Per-check status cards
 *   - Expandable drill-down sample of offending records
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    CheckCircle, AlertTriangle, XCircle, RefreshCw,
    ChevronDown, ChevronRight, ShieldCheck,
} from 'lucide-react';
import apiClient from '../../api/client';
import { ListPageShell } from '../../components/layout';

type CheckStatus = 'ok' | 'warn' | 'fail';

interface DataQualityCheck {
    key: string;
    label: string;
    description: string;
    status: CheckStatus;
    count: number;
    samples: Array<Record<string, unknown>>;
}

interface DataQualitySummary {
    ok: number;
    warn: number;
    fail: number;
    total: number;
}

interface DataQualityResponse {
    generated_at: string;
    overall: CheckStatus;
    summary: DataQualitySummary;
    checks: DataQualityCheck[];
}

const STATUS_META: Record<CheckStatus, {
    label: string; color: string; bg: string; border: string;
    icon: typeof CheckCircle;
}> = {
    ok:   { label: 'OK',       color: '#16a34a', bg: '#f0fdf4', border: '#86efac', icon: CheckCircle    },
    warn: { label: 'WARNING',  color: '#d97706', bg: '#fffbeb', border: '#fcd34d', icon: AlertTriangle  },
    fail: { label: 'FAIL',     color: '#dc2626', bg: '#fef2f2', border: '#fca5a5', icon: XCircle        },
};

/** Format cell values for the drill-down table. */
function formatCell(key: string, value: unknown): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (typeof value === 'number') return value.toLocaleString('en-NG');
    const str = String(value);
    // Money-shaped keys → prepend NGN + parse + format
    const moneyKey = /amount|debit|credit|balance|committed|expended|approved|breach|delta/i;
    if (moneyKey.test(key)) {
        const n = parseFloat(str);
        if (Number.isFinite(n)) {
            return 'NGN ' + n.toLocaleString('en-NG', {
                minimumFractionDigits: 2, maximumFractionDigits: 2,
            });
        }
    }
    return str;
}

function prettify(k: string): string {
    return k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

interface CheckCardProps {
    check: DataQualityCheck;
    expanded: boolean;
    onToggle: () => void;
}

function CheckCard({ check, expanded, onToggle }: CheckCardProps) {
    const meta = STATUS_META[check.status];
    const Icon = meta.icon;
    const hasSamples = check.samples.length > 0;
    const columns = hasSamples ? Object.keys(check.samples[0]) : [];

    return (
        <div
            style={{
                background: '#fff', borderRadius: '12px',
                border: `1px solid ${meta.border}`,
                marginBottom: 14, overflow: 'hidden',
            }}
        >
            <button
                onClick={onToggle}
                style={{
                    display: 'flex', alignItems: 'center', gap: 14,
                    width: '100%', padding: '16px 20px',
                    background: 'transparent', border: 'none', cursor: 'pointer',
                    textAlign: 'left',
                }}
            >
                <Icon size={22} style={{ color: meta.color, flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ fontSize: 15, fontWeight: 700, color: '#1e293b' }}>
                            {check.label}
                        </span>
                        <span style={{
                            fontSize: 10, fontWeight: 700,
                            padding: '2px 8px', borderRadius: 999,
                            background: meta.bg, color: meta.color,
                            border: `1px solid ${meta.border}`,
                            letterSpacing: '0.5px',
                        }}>
                            {meta.label}
                        </span>
                        <span style={{
                            fontSize: 12, color: '#64748b', fontFamily: 'monospace',
                        }}>
                            {check.count} finding{check.count === 1 ? '' : 's'}
                        </span>
                    </div>
                    <div style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
                        {check.description}
                    </div>
                </div>
                {hasSamples && (
                    expanded
                        ? <ChevronDown size={18} style={{ color: '#94a3b8' }} />
                        : <ChevronRight size={18} style={{ color: '#94a3b8' }} />
                )}
            </button>

            {expanded && hasSamples && (
                <div style={{
                    borderTop: '1px solid #f1f5f9',
                    background: '#fafbfc',
                    overflowX: 'auto',
                }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 700 }}>
                        <thead>
                            <tr style={{ background: '#f1f5f9' }}>
                                {columns.map(c => (
                                    <th key={c} style={{
                                        padding: '8px 12px', textAlign: 'left',
                                        fontSize: 11, fontWeight: 700, color: '#64748b',
                                        textTransform: 'uppercase', letterSpacing: '0.5px',
                                        whiteSpace: 'nowrap',
                                    }}>
                                        {prettify(c)}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {check.samples.map((row, i) => (
                                <tr key={i} style={{ borderTop: '1px solid #eef2f7' }}>
                                    {columns.map(c => (
                                        <td key={c} style={{
                                            padding: '8px 12px', fontSize: 13,
                                            color: '#1e293b',
                                            fontFamily: /amount|debit|credit|balance|delta|breach|committed|expended|approved|date|id|reference/i.test(c)
                                                ? 'monospace' : undefined,
                                        }}>
                                            {formatCell(c, row[c])}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {check.count > check.samples.length && (
                        <div style={{
                            padding: '10px 16px', fontSize: 12, color: '#64748b',
                            borderTop: '1px solid #eef2f7', background: '#fff',
                        }}>
                            Showing first {check.samples.length} of {check.count} findings.
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default function DataQualityPage() {
    const [expanded, setExpanded] = useState<Set<string>>(new Set());

    const { data, isLoading, error, refetch, isFetching } = useQuery<DataQualityResponse>({
        queryKey: ['data-quality'],
        queryFn: async () => (await apiClient.get('/accounting/data-quality/')).data,
        staleTime: 60_000,
    });

    const toggle = (key: string) => {
        setExpanded(prev => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key); else next.add(key);
            return next;
        });
    };

    const overallMeta = data ? STATUS_META[data.overall] : STATUS_META.ok;

    return (
        <ListPageShell>
                <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    marginBottom: '24px',
                }}>
                    <div>
                        <h1 style={{
                            fontSize: '24px', fontWeight: 800, color: '#1e293b', margin: 0,
                            display: 'flex', alignItems: 'center', gap: 10,
                        }}>
                            <ShieldCheck size={22} /> GL Data Quality
                        </h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>
                            Five audit checks against the live GL and budget state
                        </p>
                    </div>
                    <button
                        onClick={() => refetch()}
                        disabled={isFetching}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '6px',
                            padding: '8px 16px', borderRadius: '8px',
                            border: '1px solid #e2e8f0', background: '#fff',
                            cursor: isFetching ? 'wait' : 'pointer', fontSize: '14px',
                            opacity: isFetching ? 0.7 : 1,
                        }}
                    >
                        <RefreshCw
                            size={16}
                            style={{
                                animation: isFetching ? 'spin 1s linear infinite' : undefined,
                            }}
                        />
                        {isFetching ? 'Running…' : 'Re-run checks'}
                    </button>
                </div>

                {isLoading ? (
                    <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>
                        Running data-quality checks...
                    </div>
                ) : error ? (
                    <div style={{ textAlign: 'center', padding: 40, color: '#dc2626' }}>
                        Failed to load diagnostics.
                    </div>
                ) : data ? (
                    <div style={{ maxWidth: '1100px' }}>
                        {/* Overall banner */}
                        <div style={{
                            background: overallMeta.bg,
                            border: `2px solid ${overallMeta.border}`,
                            borderRadius: 12, padding: 20, marginBottom: 24,
                            display: 'flex', alignItems: 'center', gap: 18,
                        }}>
                            <overallMeta.icon size={40} style={{ color: overallMeta.color }} />
                            <div style={{ flex: 1 }}>
                                <div style={{
                                    fontSize: 13, fontWeight: 700,
                                    color: overallMeta.color,
                                    textTransform: 'uppercase', letterSpacing: '0.5px',
                                }}>
                                    Overall Status
                                </div>
                                <div style={{
                                    fontSize: 24, fontWeight: 800, color: '#1e293b',
                                    marginTop: 2,
                                }}>
                                    {overallMeta.label}
                                </div>
                                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                                    Generated {new Date(data.generated_at).toLocaleString('en-NG')}
                                </div>
                            </div>
                            <div style={{
                                display: 'flex', gap: 14, fontSize: 13,
                            }}>
                                <SummaryPill count={data.summary.ok}   status="ok"   />
                                <SummaryPill count={data.summary.warn} status="warn" />
                                <SummaryPill count={data.summary.fail} status="fail" />
                            </div>
                        </div>

                        {/* Check cards */}
                        {data.checks.map(check => (
                            <CheckCard
                                key={check.key}
                                check={check}
                                expanded={expanded.has(check.key)}
                                onToggle={() => toggle(check.key)}
                            />
                        ))}
                    </div>
                ) : null}
            </main>
            <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
        </div>
    );
}

interface SummaryPillProps {
    count: number;
    status: CheckStatus;
}

function SummaryPill({ count, status }: SummaryPillProps) {
    const meta = STATUS_META[status];
    return (
        <div style={{
            background: '#fff', padding: '8px 14px', borderRadius: 10,
            border: `1px solid ${meta.border}`,
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            minWidth: 70,
        }}>
            <div style={{
                fontSize: 22, fontWeight: 800, color: meta.color, lineHeight: 1,
            }}>
                {count}
            </div>
            <div style={{
                fontSize: 10, fontWeight: 700, color: '#64748b',
                textTransform: 'uppercase', letterSpacing: '0.5px', marginTop: 4,
            }}>
                {meta.label}
        </ListPageShell>
    );
}
