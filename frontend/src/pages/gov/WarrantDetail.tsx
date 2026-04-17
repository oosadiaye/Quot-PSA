/**
 * Warrant / AIE Detail + Release — Quot PSE
 * Route: /budget/warrants/:id
 *
 * Shows warrant details and provides Release / Suspend actions.
 * Releasing a warrant triggers notifications to MDA accountant + AG.
 */
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, CheckCircle2, Zap, PauseCircle, FileText, Download } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import '../../features/accounting/styles/glassmorphism.css';
import apiClient from '../../api/client';

const fmtNGN = (v: number | string | undefined): string => {
    const num = typeof v === 'string' ? parseFloat(v) : (v || 0);
    if (isNaN(num)) return '\u20A60.00';
    return '\u20A6' + num.toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

const STATUS_CONFIG: Record<string, { color: string; bg: string }> = {
    PENDING:   { color: '#f59e0b', bg: '#fffbeb' },
    RELEASED:  { color: '#166534', bg: '#dcfce7' },
    SUSPENDED: { color: '#dc2626', bg: '#fef2f2' },
    EXHAUSTED: { color: '#64748b', bg: '#f1f5f9' },
};

export default function WarrantDetail() {
    const { id } = useParams<{ id: string }>();
    const qc = useQueryClient();
    const [msg, setMsg] = useState('');
    const [err, setErr] = useState('');

    const { data: warrant, isLoading } = useQuery({
        queryKey: ['warrant-detail', id],
        queryFn: async () => {
            const res = await apiClient.get(`/budget/warrants/${id}/`);
            return res.data;
        },
        enabled: !!id,
    });

    const doAction = useMutation({
        mutationFn: async (action: string) => {
            const res = await apiClient.post(`/budget/warrants/${id}/${action}/`);
            return res.data;
        },
        onSuccess: (data, action) => {
            setMsg(`Warrant ${action}d successfully — status: ${data.status}`);
            setErr('');
            qc.invalidateQueries({ queryKey: ['warrant-detail', id] });
            qc.invalidateQueries({ queryKey: ['generic-list'] });
            setTimeout(() => setMsg(''), 4000);
        },
        onError: (error: any) => {
            setErr(error?.response?.data?.error || 'Action failed');
            setTimeout(() => setErr(''), 5000);
        },
    });

    if (isLoading || !warrant) {
        return (
            <div style={{ display: 'flex' }}>
                <Sidebar />
                <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                    <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--color-text-muted)' }}>Loading...</div>
                </main>
            </div>
        );
    }

    const sc = STATUS_CONFIG[warrant.status] || STATUS_CONFIG.PENDING;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title={`Warrant: ${warrant.appropriation_mda}`}
                    subtitle={`Q${warrant.quarter} — ${warrant.appropriation_account}`}
                    icon={<FileText size={22} />}
                />

                {msg && (
                    <div style={{ padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem', background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)', color: '#22c55e', fontSize: 'var(--text-sm)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <CheckCircle2 size={15} /> {msg}
                    </div>
                )}
                {err && (
                    <div style={{ padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#ef4444', fontSize: 'var(--text-sm)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <AlertCircle size={15} /> {err}
                    </div>
                )}

                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.25rem' }}>
                    {/* Left: Details */}
                    <div>
                        <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>Warrant Details</h3>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                <div>
                                    <div style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.25rem' }}>MDA</div>
                                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{warrant.appropriation_mda}</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.25rem' }}>Economic Code</div>
                                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{warrant.appropriation_account}</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.25rem' }}>Quarter</div>
                                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>Q{warrant.quarter}</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.25rem' }}>Release Date</div>
                                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{warrant.release_date}</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.25rem' }}>AIE Reference</div>
                                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{warrant.authority_reference}</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.25rem' }}>Amount</div>
                                    <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--primary, #191e6a)' }}>{fmtNGN(warrant.amount_released)}</div>
                                </div>
                            </div>
                            {warrant.notes && (
                                <div style={{ marginTop: '1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{warrant.notes}</div>
                            )}
                        </div>

                        {/* Attachment */}
                        {warrant.attachment_url && (
                            <div className="glass-card" style={{ padding: '1.25rem' }}>
                                <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 0.75rem 0' }}>AIE Letter Attachment</h3>
                                <a href={warrant.attachment_url} target="_blank" rel="noopener noreferrer"
                                    style={{
                                        display: 'inline-flex', alignItems: 'center', gap: '0.5rem',
                                        padding: '0.5rem 1rem', borderRadius: '6px',
                                        background: 'rgba(25,30,106,0.05)', border: '1px solid rgba(25,30,106,0.15)',
                                        color: 'var(--primary, #191e6a)', fontSize: 'var(--text-sm)',
                                        fontWeight: 500, textDecoration: 'none',
                                    }}>
                                    <Download size={14} /> View / Download AIE Letter
                                </a>
                            </div>
                        )}
                    </div>

                    {/* Right: Status + Actions */}
                    <div>
                        <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem', textAlign: 'center' }}>
                            <div style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Warrant Status</div>
                            <div style={{
                                display: 'inline-block', padding: '0.5rem 1.5rem', borderRadius: '2rem',
                                fontSize: 'var(--text-base)', fontWeight: 700,
                                background: sc.bg, color: sc.color,
                                border: `2px solid ${sc.color}30`,
                            }}>
                                {warrant.status}
                            </div>
                        </div>

                        {/* Actions based on status */}
                        {warrant.status === 'PENDING' && (
                            <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                                <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 0.75rem 0' }}>Release Warrant</h3>
                                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: '0 0 1rem 0' }}>
                                    Releasing this warrant authorizes the MDA to spend up to {fmtNGN(warrant.amount_released)} this quarter.
                                    MDA accountant and AG will be notified automatically.
                                </p>
                                <button
                                    onClick={() => doAction.mutate('release')}
                                    disabled={doAction.isPending}
                                    style={{
                                        width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
                                        padding: '0.75rem 1.5rem', borderRadius: '8px', border: 'none',
                                        background: 'linear-gradient(135deg, #166534 0%, #14532d 100%)',
                                        color: 'white', fontWeight: 600, fontSize: 'var(--text-sm)',
                                        cursor: 'pointer', boxShadow: '0 4px 12px rgba(22,101,52,0.3)',
                                        opacity: doAction.isPending ? 0.7 : 1,
                                    }}
                                >
                                    <Zap size={16} /> {doAction.isPending ? 'Releasing...' : 'Release Warrant (AIE)'}
                                </button>
                            </div>
                        )}

                        {warrant.status === 'RELEASED' && (
                            <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                                <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 0.75rem 0' }}>Warrant Active</h3>
                                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: '0 0 1rem 0' }}>
                                    This warrant is released. The MDA can now raise payment vouchers against it.
                                </p>
                                <button
                                    onClick={() => doAction.mutate('suspend')}
                                    disabled={doAction.isPending}
                                    style={{
                                        width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
                                        padding: '0.625rem 1.5rem', borderRadius: '8px',
                                        border: '1px solid var(--color-border)',
                                        background: 'var(--color-surface)', color: '#dc2626',
                                        fontWeight: 500, fontSize: 'var(--text-sm)', cursor: 'pointer',
                                    }}
                                >
                                    <PauseCircle size={16} /> Suspend Warrant
                                </button>
                            </div>
                        )}

                        {(warrant.status === 'SUSPENDED' || warrant.status === 'EXHAUSTED') && (
                            <div className="glass-card" style={{ padding: '1.25rem', textAlign: 'center' }}>
                                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                    This warrant is {warrant.status.toLowerCase()}. No further actions available.
                                </div>
                            </div>
                        )}

                        {/* Info */}
                        <div className="glass-card" style={{ padding: '1.25rem' }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 0.75rem 0' }}>How AIE Works</h3>
                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', lineHeight: 1.6 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
                                    <span style={{ width: 18, height: 18, borderRadius: '50%', background: '#f59e0b', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, flexShrink: 0 }}>1</span>
                                    Budget Office creates warrant (PENDING)
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
                                    <span style={{ width: 18, height: 18, borderRadius: '50%', background: '#166534', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, flexShrink: 0 }}>2</span>
                                    Commissioner releases warrant (RELEASED)
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
                                    <span style={{ width: 18, height: 18, borderRadius: '50%', background: 'var(--primary, #191e6a)', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, flexShrink: 0 }}>3</span>
                                    MDA + AG notified automatically
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <span style={{ width: 18, height: 18, borderRadius: '50%', background: '#3b82f6', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, flexShrink: 0 }}>4</span>
                                    MDA raises PVs up to released amount
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
}
