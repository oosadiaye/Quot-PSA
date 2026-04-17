/**
 * Appropriation Detail + Actions — Quot PSE
 * Route: /budget/appropriations/:id
 *
 * Shows appropriation details and provides status transition buttons:
 * DRAFT → Submit → SUBMITTED → Approve → APPROVED → Enact → ACTIVE → Close → CLOSED
 */
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, CheckCircle2, Send, Shield, Zap, Lock, Calendar, Building2 } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import '../../features/accounting/styles/glassmorphism.css';
import apiClient from '../../api/client';

const fmtNGN = (v: number | string | undefined): string => {
    const num = typeof v === 'string' ? parseFloat(v) : (v || 0);
    if (isNaN(num)) return '\u20A60.00';
    return '\u20A6' + num.toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

const STATUS_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
    DRAFT:     { color: '#64748b', bg: '#f1f5f9', label: 'Draft' },
    SUBMITTED: { color: '#1e40af', bg: '#dbeafe', label: 'Submitted' },
    APPROVED:  { color: '#6b21a8', bg: '#f3e8ff', label: 'Approved' },
    ENACTED:   { color: '#166534', bg: '#dcfce7', label: 'Enacted' },
    ACTIVE:    { color: '#166534', bg: '#dcfce7', label: 'Active' },
    CLOSED:    { color: '#dc2626', bg: '#fef2f2', label: 'Closed' },
};

const thStyle: React.CSSProperties = {
    padding: '0.5rem 0.625rem', textAlign: 'left', fontSize: '0.6rem',
    fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
    color: 'var(--color-text-muted)', whiteSpace: 'nowrap',
    borderBottom: '2px solid var(--color-border, #e2e8f0)',
    background: 'var(--color-surface, #f8fafc)',
};
const tdStyle: React.CSSProperties = {
    padding: '0.5rem 0.625rem', fontSize: 'var(--text-xs)',
    borderBottom: '1px solid var(--color-border, #f1f5f9)',
    whiteSpace: 'nowrap',
};

export default function AppropriationDetail() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const qc = useQueryClient();
    const [actionMsg, setActionMsg] = useState('');
    const [actionError, setActionError] = useState('');

    const { data: appro, isLoading } = useQuery({
        queryKey: ['appropriation-detail', id],
        queryFn: async () => {
            const res = await apiClient.get(`/budget/appropriations/${id}/`);
            return res.data;
        },
        enabled: !!id,
    });

    // Fetch all appropriation lines for the same MDA + fiscal year
    const { data: mdaLines = [] } = useQuery({
        queryKey: ['appropriation-mda-lines', appro?.administrative, appro?.fiscal_year],
        queryFn: async () => {
            const res = await apiClient.get('/budget/appropriations/', {
                params: { administrative: appro.administrative, fiscal_year: appro.fiscal_year, page_size: 200 },
            });
            const results = res.data?.results || res.data || [];
            return Array.isArray(results) ? results : [];
        },
        enabled: !!appro?.administrative && !!appro?.fiscal_year,
    });

    const doAction = useMutation({
        mutationFn: async (action: string) => {
            const res = await apiClient.post(`/budget/appropriations/${id}/${action}/`);
            return res.data;
        },
        onSuccess: (data, action) => {
            setActionMsg(`Appropriation ${action}ed successfully — now ${data.status}`);
            setActionError('');
            qc.invalidateQueries({ queryKey: ['appropriation-detail', id] });
            qc.invalidateQueries({ queryKey: ['generic-list'] });
            qc.invalidateQueries({ queryKey: ['appropriation-mda-lines'] });
            setTimeout(() => setActionMsg(''), 4000);
        },
        onError: (err: any) => {
            setActionError(err?.response?.data?.error || 'Action failed');
            setTimeout(() => setActionError(''), 5000);
        },
    });

    if (isLoading || !appro) {
        return (
            <div style={{ display: 'flex' }}>
                <Sidebar />
                <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                    <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--color-text-muted)' }}>Loading...</div>
                </main>
            </div>
        );
    }

    const sc = STATUS_CONFIG[appro.status] || STATUS_CONFIG.DRAFT;

    const NEXT_ACTIONS: Record<string, { action: string; label: string; icon: typeof Send; desc: string }> = {
        DRAFT:     { action: 'submit',  label: 'Submit for Review',    icon: Send,    desc: 'Send to Budget Office for review' },
        SUBMITTED: { action: 'approve', label: 'Approve',             icon: Shield,  desc: 'Budget Office approves this appropriation' },
        APPROVED:  { action: 'enact',   label: 'Enact (Make Active)',  icon: Zap,     desc: 'Activate after legislature passes Appropriation Act' },
        ACTIVE:    { action: 'close',   label: 'Close',               icon: Lock,    desc: 'Close at fiscal year end' },
    };

    const nextAction = NEXT_ACTIONS[appro.status];

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title={`Appropriation: ${appro.administrative_name}`}
                    subtitle={`${appro.economic_code || ''} ${appro.economic_name} — FY ${appro.fiscal_year_label}`}
                    icon={<Calendar size={22} />}
                />

                {/* Messages */}
                {actionMsg && (
                    <div style={{ padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem', background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)', color: '#22c55e', fontSize: 'var(--text-sm)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <CheckCircle2 size={15} /> {actionMsg}
                    </div>
                )}
                {actionError && (
                    <div style={{ padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#ef4444', fontSize: 'var(--text-sm)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <AlertCircle size={15} /> {actionError}
                    </div>
                )}

                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.25rem' }}>
                    {/* Left Column */}
                    <div>
                        {/* MDA Card */}
                        <div className="glass-card" style={{ padding: '1rem 1.25rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <div style={{ width: 40, height: 40, borderRadius: '10px', background: 'linear-gradient(135deg, #eff6ff, #dbeafe)', border: '1.5px solid #bfdbfe', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                <Building2 size={20} color="#2563eb" />
                            </div>
                            <div style={{ flex: 1 }}>
                                <div style={{ fontSize: '0.6rem', fontWeight: 700, color: '#2563eb', textTransform: 'uppercase', letterSpacing: '0.04em' }}>MDA (Administrative Segment)</div>
                                <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginTop: '0.15rem' }}>
                                    <span style={{ fontFamily: 'monospace', fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-text)' }}>{appro.administrative_code}</span>
                                    <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{appro.administrative_name}</span>
                                </div>
                            </div>
                            <div>
                                <span style={{ padding: '0.3rem 0.75rem', borderRadius: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, background: sc.bg, color: sc.color, border: `1.5px solid ${sc.color}30` }}>{sc.label}</span>
                            </div>
                        </div>

                        {/* Budget Execution */}
                        <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>Budget Execution</h3>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem' }}>
                                <div className="metric-card" style={{ borderLeft: '4px solid var(--primary, #191e6a)', padding: '1rem' }}>
                                    <div style={{ fontSize: '0.6rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Approved</div>
                                    <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)' }}>{fmtNGN(appro.amount_approved)}</div>
                                </div>
                                <div className="metric-card" style={{ borderLeft: '4px solid #f59e0b', padding: '1rem' }}>
                                    <div style={{ fontSize: '0.6rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Warrants</div>
                                    <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: '#f59e0b' }}>{fmtNGN(appro.total_warrants_released)}</div>
                                </div>
                                <div className="metric-card" style={{ borderLeft: '4px solid #ef4444', padding: '1rem' }}>
                                    <div style={{ fontSize: '0.6rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Expended</div>
                                    <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: '#ef4444' }}>{fmtNGN(appro.total_expended)}</div>
                                </div>
                                <div className="metric-card" style={{ borderLeft: '4px solid #22c55e', padding: '1rem' }}>
                                    <div style={{ fontSize: '0.6rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Available</div>
                                    <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: '#22c55e' }}>{fmtNGN(appro.available_balance)}</div>
                                </div>
                            </div>
                            {appro.execution_rate !== undefined && (
                                <div style={{ marginTop: '0.75rem' }}>
                                    <div style={{ fontSize: '0.6rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.25rem' }}>
                                        Execution Rate: {parseFloat(appro.execution_rate || '0').toFixed(1)}%
                                    </div>
                                    <div style={{ background: 'var(--color-border, #e2e8f0)', borderRadius: 6, height: 8, overflow: 'hidden' }}>
                                        <div style={{
                                            height: '100%', borderRadius: 6,
                                            width: `${Math.min(parseFloat(appro.execution_rate || '0'), 100)}%`,
                                            background: parseFloat(appro.execution_rate || '0') > 80 ? '#ef4444' : 'var(--primary, #191e6a)',
                                            transition: 'width 0.5s ease',
                                        }} />
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* NCoA Budget Classification — Excel-style table */}
                        <div className="glass-card" style={{ padding: '1.25rem', overflow: 'hidden' }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 0.75rem 0' }}>
                                NCoA Budget Classification — {appro.administrative_name}
                            </h3>
                            <div style={{ overflowX: 'auto' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)' }}>
                                    <thead>
                                        <tr>
                                            <th style={thStyle}>Economic Code</th>
                                            <th style={thStyle}>Economic Description</th>
                                            <th style={thStyle}>Functional</th>
                                            <th style={thStyle}>Programme</th>
                                            <th style={thStyle}>Fund</th>
                                            <th style={thStyle}>Type</th>
                                            <th style={{ ...thStyle, textAlign: 'right' }}>Approved</th>
                                            <th style={{ ...thStyle, textAlign: 'right' }}>Expended</th>
                                            <th style={{ ...thStyle, textAlign: 'right' }}>Available</th>
                                            <th style={{ ...thStyle, textAlign: 'center' }}>Status</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {mdaLines.map((line: any) => {
                                            const isCurrentLine = String(line.id) === String(id);
                                            const lineSc = STATUS_CONFIG[line.status] || STATUS_CONFIG.DRAFT;
                                            return (
                                                <tr key={line.id}
                                                    onClick={() => { if (!isCurrentLine) navigate(`/budget/appropriations/${line.id}`); }}
                                                    style={{
                                                        background: isCurrentLine ? 'rgba(79,70,229,0.06)' : 'transparent',
                                                        cursor: isCurrentLine ? 'default' : 'pointer',
                                                        borderLeft: isCurrentLine ? '3px solid #4f46e5' : '3px solid transparent',
                                                    }}>
                                                    <td style={{ ...tdStyle, fontFamily: 'monospace', fontWeight: 700, color: '#4f46e5' }}>
                                                        {line.economic_code}
                                                    </td>
                                                    <td style={{ ...tdStyle, fontWeight: isCurrentLine ? 600 : 400, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                                        {line.economic_name}
                                                    </td>
                                                    <td style={tdStyle}>
                                                        <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{line.functional_code}</span>
                                                        <div style={{ fontSize: '0.6rem', color: 'var(--color-text-muted)' }}>{line.functional_name}</div>
                                                    </td>
                                                    <td style={tdStyle}>
                                                        <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{line.programme_code}</span>
                                                        <div style={{ fontSize: '0.6rem', color: 'var(--color-text-muted)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }}>{line.programme_name}</div>
                                                    </td>
                                                    <td style={tdStyle}>
                                                        <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{line.fund_code}</span>
                                                        <div style={{ fontSize: '0.6rem', color: 'var(--color-text-muted)' }}>{line.fund_name}</div>
                                                    </td>
                                                    <td style={{ ...tdStyle, fontSize: '0.6rem', fontWeight: 600 }}>{line.appropriation_type}</td>
                                                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600 }}>{fmtNGN(line.amount_approved)}</td>
                                                    <td style={{ ...tdStyle, textAlign: 'right', color: '#ef4444' }}>{fmtNGN(line.total_expended)}</td>
                                                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600, color: '#059669' }}>{fmtNGN(line.available_balance)}</td>
                                                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                                                        <span style={{ padding: '0.15rem 0.4rem', borderRadius: '8px', fontSize: '0.6rem', fontWeight: 600, background: lineSc.bg, color: lineSc.color }}>{lineSc.label}</span>
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                    {mdaLines.length > 1 && (
                                        <tfoot>
                                            <tr style={{ borderTop: '2px solid var(--color-border)' }}>
                                                <td colSpan={6} style={{ ...tdStyle, fontWeight: 700, textAlign: 'right' }}>MDA Total:</td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700 }}>
                                                    {fmtNGN(mdaLines.reduce((s: number, l: any) => s + Number(l.amount_approved || 0), 0))}
                                                </td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#ef4444' }}>
                                                    {fmtNGN(mdaLines.reduce((s: number, l: any) => s + Number(l.total_expended || 0), 0))}
                                                </td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#059669' }}>
                                                    {fmtNGN(mdaLines.reduce((s: number, l: any) => s + Number(l.available_balance || 0), 0))}
                                                </td>
                                                <td style={tdStyle}></td>
                                            </tr>
                                        </tfoot>
                                    )}
                                </table>
                            </div>
                            {appro.description && (
                                <div style={{ marginTop: '0.75rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', borderTop: '1px solid var(--color-border)', paddingTop: '0.5rem' }}>
                                    {appro.description}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Right: Status + Actions */}
                    <div>
                        {/* Current Status */}
                        <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem', textAlign: 'center' }}>
                            <div style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Current Status</div>
                            <div style={{
                                display: 'inline-block', padding: '0.5rem 1.5rem', borderRadius: '2rem',
                                fontSize: 'var(--text-base)', fontWeight: 700,
                                background: sc.bg, color: sc.color,
                                border: `2px solid ${sc.color}30`,
                            }}>
                                {sc.label}
                            </div>
                        </div>

                        {/* Next Action */}
                        {nextAction && (
                            <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                                <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 0.75rem 0' }}>Next Step</h3>
                                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: '0 0 1rem 0' }}>
                                    {nextAction.desc}
                                </p>
                                <button
                                    onClick={() => doAction.mutate(nextAction.action)}
                                    disabled={doAction.isPending}
                                    style={{
                                        width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
                                        padding: '0.75rem 1.5rem', borderRadius: '8px', border: 'none',
                                        background: 'linear-gradient(135deg, var(--primary, #191e6a) 0%, var(--primary-dark, #0f1240) 100%)',
                                        color: 'white', fontWeight: 600, fontSize: 'var(--text-sm)',
                                        cursor: 'pointer', boxShadow: '0 4px 12px rgba(15, 18, 64, 0.3)',
                                        opacity: doAction.isPending ? 0.7 : 1,
                                    }}
                                >
                                    <nextAction.icon size={16} />
                                    {doAction.isPending ? 'Processing...' : nextAction.label}
                                </button>
                            </div>
                        )}

                        {appro.status === 'CLOSED' && (
                            <div className="glass-card" style={{ padding: '1.25rem', textAlign: 'center' }}>
                                <Lock size={24} color="var(--color-text-muted)" />
                                <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', margin: '0.5rem 0 0' }}>
                                    This appropriation is closed. No further actions available.
                                </p>
                            </div>
                        )}

                        {/* Workflow Guide */}
                        <div className="glass-card" style={{ padding: '1.25rem' }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 0.75rem 0' }}>Approval Workflow</h3>
                            {['DRAFT', 'SUBMITTED', 'APPROVED', 'ACTIVE', 'CLOSED'].map((s, i) => {
                                const isCurrent = appro.status === s;
                                const isPast = ['DRAFT', 'SUBMITTED', 'APPROVED', 'ACTIVE', 'CLOSED'].indexOf(appro.status) > i;
                                return (
                                    <div key={s} style={{
                                        display: 'flex', alignItems: 'center', gap: '0.5rem',
                                        padding: '0.4rem 0',
                                        opacity: isPast ? 0.5 : 1,
                                    }}>
                                        <div style={{
                                            width: 20, height: 20, borderRadius: '50%',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            fontSize: '10px', fontWeight: 700,
                                            background: isCurrent ? 'var(--primary, #191e6a)' : isPast ? '#22c55e' : 'var(--color-border, #e2e8f0)',
                                            color: isCurrent || isPast ? '#fff' : 'var(--color-text-muted)',
                                        }}>
                                            {isPast ? '\u2713' : i + 1}
                                        </div>
                                        <span style={{
                                            fontSize: 'var(--text-xs)',
                                            fontWeight: isCurrent ? 700 : 400,
                                            color: isCurrent ? 'var(--color-text)' : 'var(--color-text-muted)',
                                        }}>
                                            {STATUS_CONFIG[s]?.label || s}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
}
