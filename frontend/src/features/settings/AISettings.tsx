/**
 * AISettings — what AI is switched on for this organisation.
 * Route: /settings/ai
 *
 * The superadmin page is the control surface: keys, providers, which
 * capability uses which model. This is its counterpart for the
 * organisation on the receiving end, and it answers a different question
 * — not "what may I configure" but **"what is switched on for us, where
 * does our data go, and what has it done".**
 *
 * So the page leads with disclosure rather than controls. A ministry
 * evaluating this arrangement needs to know which third party sees its
 * documents and amounts, whether that party retains them, and whether it
 * brokers them onward — before it needs any button.
 *
 * The controls are **on and off**, per capability. The platform still
 * provisions each capability — it picks the provider and model and commits
 * spend when it sets one up. After that the organisation decides whether an
 * already-provisioned capability is running: it can switch one back on here
 * (with a confirmation, since running it sends content to that provider) or
 * switch everything off. A capability the platform has not provisioned
 * cannot be turned on from this page.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    ShieldCheck, ShieldAlert, AlertCircle, ArrowLeft, Ban, ExternalLink,
    Activity, FileText, Coins, Info, Power,
} from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import apiClient from '../../api/client';
import { formatApiError } from '../../utils/apiError';

interface Capability {
    id: number;
    capability: string;
    capability_display: string;
    provider_name: string;
    provider_retains_data: boolean;
    provider_is_broker: boolean;
    provider_data_policy_url: string;
    sends_document_images: boolean;
    sends_ledger_amounts: boolean;
    model_id: string;
    is_active: boolean;
    is_usable: boolean;
    require_redaction: boolean;
    monthly_cost_cap: string;
    calls_this_month: number;
    spend_this_month: number | string;
}

interface AIStatus {
    tenant_name: string;
    period_start: string;
    capabilities: Capability[];
    totals: { calls: number; spend: number | string; active: number; usable: number };
}

interface AICall {
    id: number;
    capability_display: string;
    provider_name: string;
    model_id: string;
    request_hash: string;
    redacted_field_count: number;
    status: string;
    status_display: string;
    error_message: string;
    total_tokens: number;
    cost_usd: string;
    latency_ms: number;
    created_at: string;
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
    padding: '2px 8px', borderRadius: 999, fontSize: 11,
    fontWeight: 600, background: bg, color: fg, whiteSpace: 'nowrap',
});

const enableBtn: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: '6px 12px', borderRadius: 8, fontSize: 12.5, fontWeight: 700,
    cursor: 'pointer', background: 'var(--color-surface-hover)',
    color: 'var(--color-primary)', border: '1px solid var(--color-border)',
};
const enableConfirmBtn: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: '6px 12px', borderRadius: 8, fontSize: 12.5, fontWeight: 700,
    cursor: 'pointer', background: '#16a34a', color: '#fff',
    border: '1px solid #15803d',
};
const enableCancelBtn: React.CSSProperties = {
    padding: '6px 10px', borderRadius: 8, fontSize: 12.5, fontWeight: 600,
    cursor: 'pointer', background: 'transparent',
    color: 'var(--color-text-muted)', border: '1px solid var(--color-border)',
};

/** Spend arrives as a float that can be ~1e-06. Two decimals reads $0.00. */
const money = (v: number | string) => {
    const n = Number(v ?? 0);
    if (n === 0) return '$0.00';
    return n < 0.01 ? `$${n.toFixed(6)}` : `$${n.toFixed(2)}`;
};

const dt = (iso: string) =>
    new Date(iso).toLocaleString('en-GB', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });

export default function AISettings() {
    const navigate = useNavigate();
    const qc = useQueryClient();
    const [showLog, setShowLog] = useState(false);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    // Capability awaiting a switch-on confirmation, keyed by its code.
    const [confirmEnable, setConfirmEnable] = useState<string | null>(null);

    const status = useQuery<AIStatus>({
        queryKey: ['tenant-ai-status'],
        queryFn: async () => (await apiClient.get('/core/ai/status/')).data,
    });

    const calls = useQuery<{ count: number; results: AICall[] }>({
        queryKey: ['tenant-ai-calls'],
        queryFn: async () => (await apiClient.get('/core/ai/calls/?limit=50')).data,
        enabled: showLog,
    });

    const disableAll = useMutation({
        mutationFn: async () => (await apiClient.post('/core/ai/disable-all/')).data,
        onSuccess: (d: { disabled: number }) => {
            setError('');
            setNotice(
                d.disabled
                    ? `Switched off ${d.disabled} ${d.disabled === 1 ? 'capability' : 'capabilities'}.`
                    : 'Nothing was active.',
            );
            qc.invalidateQueries({ queryKey: ['tenant-ai-status'] });
        },
        onError: (e) => setError(formatApiError(e, 'Could not switch AI off.')),
    });

    const enableCap = useMutation({
        mutationFn: async (capability: string) =>
            (await apiClient.post('/core/ai/enable/', { capability })).data,
        onSuccess: (d: { capability_display: string; is_active: boolean; is_usable: boolean }) => {
            setError('');
            setConfirmEnable(null);
            setNotice(
                d.is_usable
                    ? `${d.capability_display} switched on.`
                    : `${d.capability_display} switched on, but it is blocked upstream — ask your platform administrator.`,
            );
            qc.invalidateQueries({ queryKey: ['tenant-ai-status'] });
        },
        onError: (e) => {
            setConfirmEnable(null);
            setError(formatApiError(e, 'Could not switch the capability on.'));
        },
    });

    if (status.isLoading) {
        return (
            <div style={{ display: 'flex' }}>
                <Sidebar />
                <main style={{ flex: 1, marginLeft: 260, padding: 40, color: 'var(--color-text-subtle)' }}>Loading…</main>
            </div>
        );
    }

    if (status.isError) {
        return (
            <div style={{ display: 'flex', background: 'var(--color-background)', minHeight: '100vh' }}>
                <Sidebar />
                <main style={{ flex: 1, marginLeft: 260, padding: 32 }}>
                    <PageHeader title="AI" subtitle="Assistive features for this organisation" />
                    <div style={{ ...card, color: '#991b1b', background: '#fef2f2', borderColor: '#fca5a5' }}>
                        <AlertCircle size={16} style={{ verticalAlign: -3, marginRight: 6 }} />
                        {formatApiError(status.error, 'Could not load AI status.')}
                    </div>
                </main>
            </div>
        );
    }

    const data = status.data!;
    const rows = data.capabilities;
    const anyActive = data.totals.active > 0;

    return (
        <div style={{ display: 'flex', background: 'var(--color-background)', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: 260, padding: 32 }}>
                <PageHeader
                    title="AI"
                    subtitle={`Assistive features for ${data.tenant_name} — what is switched on, and what it has done`}
                    onBack={() => navigate('/settings')}
                    actions={
                        <button
                            type="button"
                            onClick={() => navigate('/settings')}
                            style={{
                                padding: '8px 16px', borderRadius: 8, cursor: 'pointer',
                                background: 'rgba(255,255,255,0.12)', color: '#fff',
                                border: '1px solid rgba(255,255,255,0.25)', fontSize: 13,
                                fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6,
                            }}
                        >
                            <ArrowLeft size={14} /> Back to Settings
                        </button>
                    }
                />

                {/* The promise the whole design rests on, stated first. */}
                <div style={{
                    padding: '12px 16px', borderRadius: 8, marginBottom: 16,
                    background: '#f0f9ff', border: '1px solid #bae6fd', color: '#075985',
                    display: 'flex', alignItems: 'flex-start', gap: 10, fontSize: 13, lineHeight: 1.6,
                }}>
                    <Info size={16} style={{ flexShrink: 0, marginTop: 2 }} />
                    <span>
                        <strong>AI proposes, the ledger disposes.</strong> Nothing here posts to
                        the general ledger, approves a payment or changes an appropriation.
                        Every result arrives as a draft for a named officer to accept, and the
                        acceptance — not the suggestion — is what the audit trail records.
                    </span>
                </div>

                {notice && (
                    <div style={{
                        padding: '10px 14px', borderRadius: 8, marginBottom: 16,
                        background: '#f0fdf4', border: '1px solid #86efac', color: '#166534', fontSize: 13,
                    }}>{notice}</div>
                )}
                {error && (
                    <div style={{
                        padding: '10px 14px', borderRadius: 8, marginBottom: 16,
                        background: '#fef2f2', border: '1px solid #fca5a5', color: '#991b1b', fontSize: 13,
                    }}>{error}</div>
                )}

                {rows.length === 0 ? (
                    <div style={{ ...card, textAlign: 'center', padding: 48, color: 'var(--color-text-muted)' }}>
                        <ShieldCheck size={32} style={{ color: 'var(--color-text-subtle)', marginBottom: 12 }} />
                        <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--color-text)', marginBottom: 6 }}>
                            No AI features are switched on
                        </div>
                        <div style={{ fontSize: 13, lineHeight: 1.6, maxWidth: 520, margin: '0 auto' }}>
                            Nothing from this organisation is being sent to an AI provider.
                            Ask your platform administrator if you want a capability enabled —
                            they choose the provider and model, and this page will then show
                            exactly what each one sends.
                        </div>
                    </div>
                ) : (
                    <>
                        {/* ── Month to date ───────────────────────────── */}
                        <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
                            {[
                                { icon: <Activity size={16} />, label: 'Calls this month', value: String(data.totals.calls) },
                                { icon: <Coins size={16} />, label: 'Spend this month', value: money(data.totals.spend) },
                                { icon: <ShieldCheck size={16} />, label: 'Active capabilities', value: `${data.totals.active} of ${rows.length}` },
                            ].map((s) => (
                                <div key={s.label} style={{ ...card, flex: '1 1 200px', marginBottom: 0 }}>
                                    <div style={{ ...lbl, display: 'flex', alignItems: 'center', gap: 6 }}>
                                        {s.icon}{s.label}
                                    </div>
                                    <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--color-text)', marginTop: 6 }}>
                                        {s.value}
                                    </div>
                                </div>
                            ))}
                        </div>

                        {/* ── One card per capability ─────────────────── */}
                        {rows.map((c) => (
                            <div key={c.id} style={card}>
                                <div style={{
                                    display: 'flex', justifyContent: 'space-between',
                                    alignItems: 'flex-start', gap: 16, flexWrap: 'wrap',
                                }}>
                                    <div style={{ minWidth: 240 }}>
                                        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--color-text)' }}>
                                            {c.capability_display}
                                        </div>
                                        <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 4 }}>
                                            {c.provider_name} · <code style={{ fontSize: 11 }}>{c.model_id}</code>
                                        </div>
                                    </div>
                                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                                        {c.is_active && c.is_usable
                                            ? <span style={pill('#dcfce7', '#166534')}><ShieldCheck size={12} />Active</span>
                                            : c.is_active
                                                ? <span style={pill('#ffedd5', '#9a3412')}><ShieldAlert size={12} />Blocked upstream</span>
                                                : <span style={pill('#f1f5f9', '#475569')}>Off</span>}
                                        {!c.is_active && (
                                            confirmEnable === c.capability ? (
                                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                                                    <button
                                                        type="button"
                                                        onClick={() => enableCap.mutate(c.capability)}
                                                        disabled={enableCap.isPending}
                                                        title={`Runs ${c.capability_display}: sends this organisation's data to ${c.provider_name} and commits spend against the monthly cap.`}
                                                        style={enableConfirmBtn}
                                                    >
                                                        <Power size={13} />
                                                        {enableCap.isPending ? 'Switching on…' : 'Confirm — commits spend'}
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => setConfirmEnable(null)}
                                                        disabled={enableCap.isPending}
                                                        style={enableCancelBtn}
                                                    >
                                                        Cancel
                                                    </button>
                                                </span>
                                            ) : (
                                                <button
                                                    type="button"
                                                    onClick={() => { setError(''); setNotice(''); setConfirmEnable(c.capability); }}
                                                    style={enableBtn}
                                                >
                                                    <Power size={13} /> Enable
                                                </button>
                                            )
                                        )}
                                    </div>
                                </div>

                                {/* What actually leaves the organisation. */}
                                <div style={{
                                    marginTop: 14, paddingTop: 14, borderTop: '1px dashed var(--color-border)',
                                    display: 'flex', gap: 24, flexWrap: 'wrap',
                                }}>
                                    <div style={{ minWidth: 210 }}>
                                        <div style={lbl}>What leaves this organisation</div>
                                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                                            {c.sends_document_images && <span style={pill('#eef2ff', '#3730a3')}><FileText size={12} />Documents</span>}
                                            {c.sends_ledger_amounts && <span style={pill('#eef2ff', '#3730a3')}>Amounts</span>}
                                            {c.require_redaction
                                                ? <span style={pill('#dcfce7', '#166534')}>Bank details, BVN &amp; TIN removed</span>
                                                : <span style={pill('#fee2e2', '#991b1b')}><ShieldAlert size={12} />Sent unredacted</span>}
                                        </div>
                                    </div>
                                    <div style={{ minWidth: 200 }}>
                                        <div style={lbl}>Who receives it</div>
                                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                                            {c.provider_is_broker && (
                                                <span style={pill('#ffedd5', '#9a3412')}
                                                    title="Routes to upstream providers, so its data policy is the union of theirs.">
                                                    Broker
                                                </span>
                                            )}
                                            {c.provider_retains_data
                                                ? <span style={pill('#fee2e2', '#991b1b')}><ShieldAlert size={12} />Retains data</span>
                                                : <span style={pill('#dcfce7', '#166534')}>No retention</span>}
                                            {c.provider_data_policy_url && (
                                                <a href={c.provider_data_policy_url} target="_blank" rel="noopener noreferrer"
                                                    style={{ ...pill('#f1f5f9', '#334155'), textDecoration: 'none' }}>
                                                    Policy <ExternalLink size={11} />
                                                </a>
                                            )}
                                        </div>
                                    </div>
                                    <div>
                                        <div style={lbl}>This month</div>
                                        <div style={{ fontSize: 13, color: 'var(--color-text)', marginTop: 8 }}>
                                            {c.calls_this_month} {c.calls_this_month === 1 ? 'call' : 'calls'} · {money(c.spend_this_month)}
                                            {Number(c.monthly_cost_cap) > 0 && (
                                                <span style={{ color: 'var(--color-text-muted)' }}>
                                                    {' '}of ${Number(c.monthly_cost_cap).toFixed(2)} cap
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))}

                        {/* ── The one control: off ────────────────────── */}
                        <div style={{
                            ...card,
                            display: 'flex', justifyContent: 'space-between',
                            alignItems: 'center', gap: 16, flexWrap: 'wrap',
                        }}>
                            <div style={{ maxWidth: 560 }}>
                                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text)' }}>
                                    Switch AI off for this organisation
                                </div>
                                <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', lineHeight: 1.6, marginTop: 4 }}>
                                    Stops every capability immediately. Nothing is deleted and past
                                    results are untouched. You can switch a provisioned capability
                                    back on above; adding a new one is done by your platform
                                    administrator, because it selects a model and commits spend.
                                </div>
                            </div>
                            <button
                                type="button"
                                disabled={!anyActive || disableAll.isPending}
                                onClick={() => disableAll.mutate()}
                                style={{
                                    padding: '10px 18px', borderRadius: 8, fontSize: 13, fontWeight: 700,
                                    display: 'flex', alignItems: 'center', gap: 8,
                                    cursor: anyActive && !disableAll.isPending ? 'pointer' : 'not-allowed',
                                    background: anyActive ? '#dc2626' : 'var(--color-surface-hover)',
                                    color: anyActive ? '#fff' : 'var(--color-text-subtle)',
                                    border: anyActive ? '1px solid #b91c1c' : '1px solid var(--color-border)',
                                }}
                            >
                                <Ban size={15} />
                                {disableAll.isPending ? 'Switching off…' : anyActive ? 'Switch all off' : 'Nothing active'}
                            </button>
                        </div>
                    </>
                )}

                {/* ── Audit trail ─────────────────────────────────────── */}
                <div style={card}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                        <div>
                            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text)' }}>
                                AI activity log
                            </div>
                            <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', marginTop: 4, lineHeight: 1.6 }}>
                                Every call this organisation has made. The log records a
                                fingerprint of what was sent, never the content itself.
                            </div>
                        </div>
                        <button
                            type="button"
                            onClick={() => setShowLog((v) => !v)}
                            style={{
                                padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600,
                                cursor: 'pointer', background: 'var(--color-surface)', color: 'var(--color-text-secondary)',
                                border: '1.5px solid var(--color-border)', whiteSpace: 'nowrap',
                            }}
                        >
                            {showLog ? 'Hide' : 'Show log'}
                        </button>
                    </div>

                    {showLog && (
                        <div style={{ marginTop: 16, overflowX: 'auto' }}>
                            {calls.isLoading && <div style={{ color: 'var(--color-text-subtle)', fontSize: 13 }}>Loading…</div>}
                            {calls.data && calls.data.results.length === 0 && (
                                <div style={{ color: 'var(--color-text-muted)', fontSize: 13 }}>No calls recorded.</div>
                            )}
                            {calls.data && calls.data.results.length > 0 && (
                                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, minWidth: 760 }}>
                                    <thead>
                                        <tr style={{ textAlign: 'left', color: 'var(--color-text-secondary)', background: 'var(--color-surface-hover)' }}>
                                            {['When', 'Capability', 'Model', 'Outcome', 'Tokens', 'Cost', 'Redacted', 'Fingerprint'].map((h) => (
                                                <th key={h} style={{ padding: '8px 10px', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.3px' }}>{h}</th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {calls.data.results.map((r) => (
                                            <tr key={r.id} style={{ borderTop: '1px solid var(--color-border-light)' }}>
                                                <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>{dt(r.created_at)}</td>
                                                <td style={{ padding: '8px 10px' }}>{r.capability_display}</td>
                                                <td style={{ padding: '8px 10px' }}><code style={{ fontSize: 11 }}>{r.model_id}</code></td>
                                                <td style={{ padding: '8px 10px' }}>
                                                    <span style={
                                                        r.status === 'success' ? pill('#dcfce7', '#166534')
                                                            : r.status === 'refused' ? pill('#f1f5f9', '#475569')
                                                                : pill('#fee2e2', '#991b1b')
                                                    }>{r.status_display}</span>
                                                </td>
                                                <td style={{ padding: '8px 10px' }}>{r.total_tokens}</td>
                                                <td style={{ padding: '8px 10px' }}>{money(r.cost_usd)}</td>
                                                <td style={{ padding: '8px 10px' }}>{r.redacted_field_count}</td>
                                                <td style={{ padding: '8px 10px' }}>
                                                    <code style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
                                                        {r.request_hash ? `${r.request_hash.slice(0, 12)}…` : '—'}
                                                    </code>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
