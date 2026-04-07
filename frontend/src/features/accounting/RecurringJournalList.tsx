import { useState, useMemo, Fragment } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    useRecurringJournals, useGenerateRecurringJournalNow,
    useDeleteRecurringJournal, useAllRecurringJournalRuns,
} from './hooks/useRecurringJournal';
import AccountingLayout from './AccountingLayout';
import { useCurrency } from '../../context/CurrencyContext';
import {
    Plus, Play, Trash2, Edit2, Repeat, CheckCircle, CheckCircle2, X,
    AlertTriangle, BarChart2, ChevronDown, ChevronRight,
    Clock, Calendar, TrendingUp, AlertCircle, RefreshCw,
} from 'lucide-react';
import LoadingScreen from '../../components/common/LoadingScreen';

// ─── helpers ────────────────────────────────────────────────────────────────
const FREQ_LABELS: Record<string, string> = {
    daily: 'Daily', weekly: 'Weekly', biweekly: 'Bi-Weekly',
    monthly: 'Monthly', quarterly: 'Quarterly', annually: 'Annually',
};
const FREQ_COLOR: Record<string, { bg: string; color: string }> = {
    daily:     { bg: 'rgba(239,68,68,0.1)',   color: '#ef4444' },
    weekly:    { bg: 'rgba(245,158,11,0.1)',   color: '#d97706' },
    biweekly:  { bg: 'rgba(16,185,129,0.1)',   color: '#059669' },
    monthly:   { bg: 'rgba(79,70,229,0.1)',    color: '#4f46e5' },
    quarterly: { bg: 'rgba(168,85,247,0.1)',   color: '#a855f7' },
    annually:  { bg: 'rgba(59,130,246,0.1)',   color: '#3b82f6' },
};

const freqBadge = (freq: string) => {
    const c = FREQ_COLOR[freq] || { bg: '#f1f5f9', color: '#64748b' };
    return (
        <span style={{ background: c.bg, color: c.color, padding: '2px 8px', borderRadius: '99px', fontSize: '11px', fontWeight: 700 }}>
            {FREQ_LABELS[freq] || freq}
        </span>
    );
};

const statusBadge = (status: string) => {
    const map: Record<string, { bg: string; color: string; label: string }> = {
        Posted:    { bg: '#dcfce7', color: '#16a34a', label: 'Posted' },
        Generated: { bg: '#fef9c3', color: '#ca8a04', label: 'Pending' },
        Failed:    { bg: '#fee2e2', color: '#dc2626', label: 'Failed' },
    };
    const s = map[status] || { bg: '#f1f5f9', color: '#64748b', label: status };
    return (
        <span style={{ background: s.bg, color: s.color, padding: '2px 8px', borderRadius: '99px', fontSize: '11px', fontWeight: 700 }}>
            {s.label}
        </span>
    );
};

// ─── Stat card ───────────────────────────────────────────────────────────────
const Stat = ({ label, value, color, icon }: { label: string; value: number | string; color?: string; icon?: React.ReactNode }) => (
    <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
        {icon && <div style={{ width: 38, height: 38, borderRadius: '10px', background: `${color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{icon}</div>}
        <div>
            <div style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px' }}>{label}</div>
            <div style={{ fontSize: '22px', fontWeight: 800, color: color || '#1e293b', lineHeight: 1 }}>{value}</div>
        </div>
    </div>
);

// ─── table styles ────────────────────────────────────────────────────────────
const th: React.CSSProperties = {
    padding: '10px 14px', textAlign: 'left', fontSize: '11px', fontWeight: 700,
    color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em',
    borderBottom: '1.5px solid #e2e8f0', whiteSpace: 'nowrap', background: '#f8fafc',
};
const td: React.CSSProperties = {
    padding: '11px 14px', fontSize: '13px', color: '#374151',
    borderBottom: '1px solid #f1f5f9', whiteSpace: 'nowrap', verticalAlign: 'middle',
};
const numCell = (val: number, color?: string): React.CSSProperties => ({
    ...td, textAlign: 'right', fontWeight: val > 0 ? 700 : 400,
    color: val > 0 ? (color || '#1e293b') : '#94a3b8',
});

type ConfirmModal =
    | { type: 'generate'; id: number; name: string }
    | { type: 'delete'; id: number; name: string }
    | null;

// ─── Main component ──────────────────────────────────────────────────────────
const RecurringJournalList = () => {
    const navigate = useNavigate();

    const { data: rawJournals = [], isLoading: jLoading } = useRecurringJournals();
    const { data: rawRuns = [], isLoading: rLoading } = useAllRecurringJournalRuns();

    const generateNow = useGenerateRecurringJournalNow();
    const deleteRecurring = useDeleteRecurringJournal();

    const [tab, setTab] = useState<'templates' | 'report'>('templates');
    const [filterActive, setFilterActive] = useState('all');
    const [freqFilter, setFreqFilter] = useState('all');
    const [expandedId, setExpandedId] = useState<number | null>(null);
    const [confirmModal, setConfirmModal] = useState<ConfirmModal>(null);
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

    const journals: any[] = Array.isArray(rawJournals) ? rawJournals : [];
    const runs: any[] = Array.isArray(rawRuns) ? rawRuns : [];

    const flash = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 3500);
    };

    // ─── Aggregate runs by template ID ────────────────────────────────────────
    const runsByTemplate = useMemo(() => {
        const map = new Map<number, any[]>();
        runs.forEach(r => {
            const id = r.recurring_journal;
            if (!map.has(id)) map.set(id, []);
            map.get(id)!.push(r);
        });
        return map;
    }, [runs]);

    const getStats = (id: number) => {
        const templateRuns = runsByTemplate.get(id) ?? [];
        const posted  = templateRuns.filter(r => r.status === 'Posted').length;
        const pending = templateRuns.filter(r => r.status === 'Generated').length;
        const failed  = templateRuns.filter(r => r.status === 'Failed').length;
        const lastRun = templateRuns.length
            ? templateRuns.slice().sort((a, b) => b.run_date.localeCompare(a.run_date))[0]
            : null;
        return { total: templateRuns.length, posted, pending, failed, lastRun };
    };

    // ─── Global stats ─────────────────────────────────────────────────────────
    const totalPosted  = runs.filter(r => r.status === 'Posted').length;
    const totalPending = runs.filter(r => r.status === 'Generated').length;
    const totalFailed  = runs.filter(r => r.status === 'Failed').length;
    const activeCount  = journals.filter(j => j.is_active).length;

    // ─── Filters ──────────────────────────────────────────────────────────────
    const filteredJournals = journals.filter(j => {
        if (filterActive === 'active' && !j.is_active) return false;
        if (filterActive === 'inactive' && j.is_active) return false;
        if (freqFilter !== 'all' && j.frequency !== freqFilter) return false;
        return true;
    });

    // ─── Confirm handler ──────────────────────────────────────────────────────
    const handleConfirm = async () => {
        if (!confirmModal) return;
        try {
            if (confirmModal.type === 'generate') {
                await generateNow.mutateAsync(confirmModal.id);
                flash(`Journal "${confirmModal.name}" generated successfully.`);
            } else {
                await deleteRecurring.mutateAsync(confirmModal.id);
                flash(`Template "${confirmModal.name}" deleted.`);
            }
        } catch (err: any) {
            const d = err?.response?.data;
            const msg = d?.error || d?.detail || `Failed to ${confirmModal.type === 'generate' ? 'generate' : 'delete'}.`;
            flash(String(msg), false);
        }
        setConfirmModal(null);
    };

    const isPending = generateNow.isPending || deleteRecurring.isPending;

    if (jLoading) return <LoadingScreen message="Loading recurring journals…" />;

    // ─── Shared tab button ────────────────────────────────────────────────────
    const tabBtn = (key: 'templates' | 'report', label: string, icon: React.ReactNode) => (
        <button key={key} onClick={() => setTab(key)} style={{
            padding: '8px 18px', borderRadius: '8px', border: 'none', cursor: 'pointer',
            fontSize: '13px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px',
            background: tab === key ? '#4f46e5' : '#f1f5f9',
            color: tab === key ? '#fff' : '#64748b',
            transition: 'all 0.15s',
        }}>
            {icon}{label}
        </button>
    );

    const selStyle: React.CSSProperties = {
        padding: '7px 10px', border: '1.5px solid #e2e8f0', borderRadius: '8px',
        fontSize: '12px', background: '#fff', color: '#374151', cursor: 'pointer',
    };

    return (
        <AccountingLayout>
            {/* ─── Toast ──────────────────────────────────────────────────── */}
            {toast && (
                <div style={{
                    position: 'fixed', top: '20px', right: '24px', zIndex: 1100,
                    background: toast.ok ? '#d1fae5' : '#fee2e2',
                    border: `1px solid ${toast.ok ? '#6ee7b7' : '#fca5a5'}`,
                    borderRadius: '10px', padding: '12px 18px',
                    display: 'flex', alignItems: 'center', gap: '10px',
                    color: toast.ok ? '#065f46' : '#991b1b',
                    boxShadow: '0 4px 24px rgba(0,0,0,0.12)', fontSize: '13px', fontWeight: 500,
                }}>
                    {toast.ok ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                    {toast.msg}
                    <button onClick={() => setToast(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}><X size={14} /></button>
                </div>
            )}

            {/* ─── Header ─────────────────────────────────────────────────── */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
                <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
                        <div style={{ width: 36, height: 36, borderRadius: '10px', background: 'rgba(79,70,229,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <Repeat size={18} color="#4f46e5" />
                        </div>
                        <h1 style={{ margin: 0, fontSize: '20px', fontWeight: 800, color: '#1e293b' }}>Recurring Journals</h1>
                    </div>
                    <p style={{ margin: 0, fontSize: '13px', color: '#94a3b8', paddingLeft: '46px' }}>
                        Manage templates and track automated posting activity
                    </p>
                </div>
                <button onClick={() => navigate('/accounting/recurring-journals/new')}
                    style={{ padding: '10px 18px', border: 'none', borderRadius: '10px', background: '#4f46e5', color: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px', boxShadow: '0 2px 8px rgba(79,70,229,0.25)' }}>
                    <Plus size={16} /> New Template
                </button>
            </div>

            {/* ─── Stats bar ──────────────────────────────────────────────── */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '12px', marginBottom: '24px' }}>
                <Stat label="Templates" value={journals.length} color="#4f46e5" icon={<Repeat size={16} color="#4f46e5" />} />
                <Stat label="Active" value={activeCount} color="#16a34a" icon={<CheckCircle size={16} color="#16a34a" />} />
                <Stat label="Inactive" value={journals.length - activeCount} color="#94a3b8" icon={<Clock size={16} color="#94a3b8" />} />
                <Stat label="Total Runs" value={runs.length} color="#1e293b" icon={<TrendingUp size={16} color="#1e293b" />} />
                <Stat label="Auto-Posted" value={totalPosted} color="#16a34a" icon={<CheckCircle2 size={16} color="#16a34a" />} />
                <Stat label="Pending / Failed" value={`${totalPending} / ${totalFailed}`} color={totalFailed > 0 ? '#dc2626' : '#d97706'} icon={<AlertCircle size={16} color={totalFailed > 0 ? '#dc2626' : '#d97706'} />} />
            </div>

            {/* ─── Tab bar ────────────────────────────────────────────────── */}
            <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '14px', overflow: 'hidden' }}>
                <div style={{ padding: '14px 20px', background: '#fafbfc', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', gap: '6px' }}>
                        {tabBtn('templates', `Templates (${journals.length})`, <Repeat size={13} />)}
                        {tabBtn('report', 'Run Report', <BarChart2 size={13} />)}
                    </div>
                    <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px', alignItems: 'center' }}>
                        {tab === 'templates' && (
                            <>
                                <select style={selStyle} value={filterActive} onChange={e => setFilterActive(e.target.value)}>
                                    <option value="all">All Status</option>
                                    <option value="active">Active</option>
                                    <option value="inactive">Inactive</option>
                                </select>
                                <select style={selStyle} value={freqFilter} onChange={e => setFreqFilter(e.target.value)}>
                                    <option value="all">All Frequencies</option>
                                    {Object.entries(FREQ_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                                </select>
                            </>
                        )}
                    </div>
                </div>

                {/* ══════════════════════════════════════════════════════════
                    TEMPLATES TAB
                ══════════════════════════════════════════════════════════ */}
                {tab === 'templates' && (
                    filteredJournals.length === 0 ? (
                        <div style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>
                            <Repeat size={40} color="#e2e8f0" style={{ display: 'block', margin: '0 auto 12px' }} />
                            <p style={{ margin: 0, fontSize: '13px' }}>No templates found.</p>
                            <button onClick={() => navigate('/accounting/recurring-journals/new')}
                                style={{ marginTop: '12px', padding: '8px 16px', border: 'none', borderRadius: '8px', background: '#4f46e5', color: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: 600 }}>
                                Create First Template
                            </button>
                        </div>
                    ) : (
                        <div style={{ display: 'grid', gap: 0 }}>
                            {filteredJournals.map((j: any) => {
                                const s = getStats(j.id);
                                return (
                                    <div key={j.id} style={{ padding: '16px 20px', borderBottom: '1px solid #f1f5f9', transition: 'background 0.1s' }}
                                        onMouseEnter={e => (e.currentTarget.style.background = '#fafbfc')}
                                        onMouseLeave={e => (e.currentTarget.style.background = '')}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px' }}>
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px', flexWrap: 'wrap' }}>
                                                    <span style={{ fontFamily: 'monospace', fontSize: '11px', background: j.is_active ? '#dcfce7' : '#f1f5f9', color: j.is_active ? '#16a34a' : '#94a3b8', padding: '2px 7px', borderRadius: '5px', fontWeight: 700 }}>{j.code}</span>
                                                    <span style={{ fontWeight: 700, fontSize: '14px', color: '#1e293b' }}>{j.name}</span>
                                                    {freqBadge(j.frequency)}
                                                    {j.auto_post && <span style={{ background: 'rgba(79,70,229,0.1)', color: '#4f46e5', padding: '2px 7px', borderRadius: '5px', fontSize: '11px', fontWeight: 700 }}>Auto-Post</span>}
                                                </div>
                                                <div style={{ display: 'flex', gap: '20px', fontSize: '12px', color: '#64748b', flexWrap: 'wrap' }}>
                                                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><Calendar size={12} /> Start: {j.start_date}</span>
                                                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><RefreshCw size={12} /> Next: <strong>{j.next_run_date || '—'}</strong></span>
                                                    {j.end_date && <span>End: {j.end_date}</span>}
                                                    <span style={{ color: '#94a3b8' }}>{j.description || 'No description'}</span>
                                                </div>
                                            </div>
                                            {/* Mini run summary */}
                                            <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexShrink: 0 }}>
                                                <div style={{ textAlign: 'center', minWidth: '36px' }}>
                                                    <div style={{ fontSize: '16px', fontWeight: 800, color: '#1e293b' }}>{s.total}</div>
                                                    <div style={{ fontSize: '10px', color: '#94a3b8', fontWeight: 600 }}>RUNS</div>
                                                </div>
                                                <div style={{ width: '1px', height: '28px', background: '#e2e8f0' }} />
                                                <div style={{ textAlign: 'center', minWidth: '36px' }}>
                                                    <div style={{ fontSize: '16px', fontWeight: 800, color: '#16a34a' }}>{s.posted}</div>
                                                    <div style={{ fontSize: '10px', color: '#94a3b8', fontWeight: 600 }}>POSTED</div>
                                                </div>
                                                <div style={{ textAlign: 'center', minWidth: '36px' }}>
                                                    <div style={{ fontSize: '16px', fontWeight: 800, color: s.pending > 0 ? '#d97706' : '#94a3b8' }}>{s.pending}</div>
                                                    <div style={{ fontSize: '10px', color: '#94a3b8', fontWeight: 600 }}>PENDING</div>
                                                </div>
                                                {s.failed > 0 && (
                                                    <div style={{ textAlign: 'center', minWidth: '36px' }}>
                                                        <div style={{ fontSize: '16px', fontWeight: 800, color: '#dc2626' }}>{s.failed}</div>
                                                        <div style={{ fontSize: '10px', color: '#94a3b8', fontWeight: 600 }}>FAILED</div>
                                                    </div>
                                                )}
                                                <div style={{ width: '1px', height: '28px', background: '#e2e8f0' }} />
                                                <div style={{ display: 'flex', gap: '4px' }}>
                                                    <button title="Generate Now" disabled={!j.is_active || isPending}
                                                        onClick={() => setConfirmModal({ type: 'generate', id: j.id, name: j.name })}
                                                        style={{ background: 'none', border: '1.5px solid #e2e8f0', borderRadius: '7px', padding: '5px 8px', cursor: j.is_active ? 'pointer' : 'not-allowed', color: j.is_active ? '#16a34a' : '#cbd5e1', display: 'flex', alignItems: 'center' }}>
                                                        <Play size={14} />
                                                    </button>
                                                    <button title="Edit" onClick={() => navigate(`/accounting/recurring-journals/${j.id}`)}
                                                        style={{ background: 'none', border: '1.5px solid #e2e8f0', borderRadius: '7px', padding: '5px 8px', cursor: 'pointer', color: '#64748b', display: 'flex', alignItems: 'center' }}>
                                                        <Edit2 size={14} />
                                                    </button>
                                                    <button title="Delete" onClick={() => setConfirmModal({ type: 'delete', id: j.id, name: j.name })}
                                                        style={{ background: 'none', border: '1.5px solid #e2e8f0', borderRadius: '7px', padding: '5px 8px', cursor: 'pointer', color: '#ef4444', display: 'flex', alignItems: 'center' }}>
                                                        <Trash2 size={14} />
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )
                )}

                {/* ══════════════════════════════════════════════════════════
                    REPORT TAB
                ══════════════════════════════════════════════════════════ */}
                {tab === 'report' && (
                    rLoading ? (
                        <div style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>Loading run data…</div>
                    ) : journals.length === 0 ? (
                        <div style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>No templates yet.</div>
                    ) : (
                        <>
                            <div style={{ overflowX: 'auto' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                    <thead>
                                        <tr>
                                            {['', 'Template', 'Frequency', 'Created', 'Start Date', 'End Date', 'Next Run', 'Auto-Post', 'Total Runs', 'Posted', 'Pending', 'Failed', 'Last Run'].map(h => (
                                                <th key={h} style={th}>{h}</th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {journals.map((j: any) => {
                                            const s = getStats(j.id);
                                            const isExpanded = expandedId === j.id;
                                            const templateRuns = runsByTemplate.get(j.id) ?? [];
                                            return (
                                                <Fragment key={j.id}>
                                                    <tr
                                                        onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                                                        onMouseLeave={e => (e.currentTarget.style.background = isExpanded ? '#fffbeb' : '')}>
                                                        {/* Expand toggle */}
                                                        <td style={{ ...td, width: '36px', paddingRight: 0 }}>
                                                            {s.total > 0 && (
                                                                <button onClick={() => setExpandedId(isExpanded ? null : j.id)}
                                                                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px', color: '#94a3b8', display: 'flex', alignItems: 'center' }}>
                                                                    {isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                                                                </button>
                                                            )}
                                                        </td>
                                                        {/* Template */}
                                                        <td style={td}>
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
                                                                <span style={{ fontFamily: 'monospace', fontSize: '10px', background: j.is_active ? '#dcfce7' : '#f1f5f9', color: j.is_active ? '#16a34a' : '#94a3b8', padding: '1px 6px', borderRadius: '4px', fontWeight: 700 }}>{j.code}</span>
                                                                <span style={{ fontWeight: 600, color: '#1e293b', maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis' }}>{j.name}</span>
                                                            </div>
                                                        </td>
                                                        <td style={td}>{freqBadge(j.frequency)}</td>
                                                        <td style={{ ...td, color: '#94a3b8', fontSize: '12px' }}>{j.created_at ? j.created_at.slice(0, 10) : '—'}</td>
                                                        <td style={td}>{j.start_date || '—'}</td>
                                                        <td style={{ ...td, color: j.end_date ? '#1e293b' : '#94a3b8' }}>{j.end_date || 'No end'}</td>
                                                        <td style={{ ...td, color: j.next_run_date ? '#4f46e5' : '#94a3b8', fontWeight: j.next_run_date ? 600 : 400 }}>{j.next_run_date || '—'}</td>
                                                        <td style={td}>
                                                            {j.auto_post
                                                                ? <span style={{ color: '#16a34a', fontWeight: 700, fontSize: '11px', display: 'flex', alignItems: 'center', gap: '3px' }}><CheckCircle size={13} /> Yes</span>
                                                                : <span style={{ color: '#94a3b8', fontSize: '11px' }}>Manual</span>}
                                                        </td>
                                                        <td style={{ ...td, textAlign: 'right', fontWeight: 700 }}>{s.total || <span style={{ color: '#cbd5e1' }}>0</span>}</td>
                                                        <td style={numCell(s.posted, '#16a34a')}>{s.posted || <span style={{ color: '#cbd5e1' }}>0</span>}</td>
                                                        <td style={numCell(s.pending, '#d97706')}>{s.pending || <span style={{ color: '#cbd5e1' }}>0</span>}</td>
                                                        <td style={numCell(s.failed, '#dc2626')}>{s.failed || <span style={{ color: '#cbd5e1' }}>0</span>}</td>
                                                        <td style={{ ...td, color: '#94a3b8', fontSize: '12px' }}>
                                                            {s.lastRun ? (
                                                                <div>
                                                                    <div style={{ color: '#374151' }}>{s.lastRun.run_date}</div>
                                                                    <div>{statusBadge(s.lastRun.status)}</div>
                                                                </div>
                                                            ) : '—'}
                                                        </td>
                                                    </tr>

                                                    {/* ── Expanded runs detail ── */}
                                                    {isExpanded && (
                                                        <tr>
                                                            <td colSpan={14} style={{ padding: 0, background: '#fffbeb', borderBottom: '2px solid #fcd34d' }}>
                                                                <div style={{ padding: '0 20px 16px 20px' }}>
                                                                    <div style={{ padding: '10px 0 8px', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                                                        Run History — {j.name}
                                                                    </div>
                                                                    <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: '8px', overflow: 'hidden', border: '1px solid #fde68a' }}>
                                                                        <thead>
                                                                            <tr style={{ background: '#fef9c3' }}>
                                                                                {['Run Date', 'Journal #', 'Status', 'Error'].map(h => (
                                                                                    <th key={h} style={{ ...th, background: 'transparent', borderBottom: '1px solid #fde68a', fontSize: '10px' }}>{h}</th>
                                                                                ))}
                                                                            </tr>
                                                                        </thead>
                                                                        <tbody>
                                                                            {templateRuns
                                                                                .slice()
                                                                                .sort((a, b) => b.run_date.localeCompare(a.run_date))
                                                                                .map((run: any) => (
                                                                                    <tr key={run.id}
                                                                                        onMouseEnter={e => (e.currentTarget.style.background = '#fffde7')}
                                                                                        onMouseLeave={e => (e.currentTarget.style.background = '')}>
                                                                                        <td style={{ ...td, fontSize: '12px' }}>{run.run_date}</td>
                                                                                        <td style={{ ...td, fontFamily: 'monospace', fontSize: '12px', color: '#4f46e5' }}>
                                                                                            {run.journal_number || <span style={{ color: '#94a3b8' }}>—</span>}
                                                                                        </td>
                                                                                        <td style={td}>{statusBadge(run.status)}</td>
                                                                                        <td style={{ ...td, fontSize: '11px', color: '#dc2626', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                                                                            {run.error_message || <span style={{ color: '#94a3b8' }}>—</span>}
                                                                                        </td>
                                                                                    </tr>
                                                                                ))}
                                                                        </tbody>
                                                                    </table>
                                                                </div>
                                                            </td>
                                                        </tr>
                                                    )}
                                                </Fragment>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>

                            {/* Report footer */}
                            <div style={{ padding: '12px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', display: 'flex', gap: '24px', fontSize: '12px', color: '#64748b', flexWrap: 'wrap', alignItems: 'center' }}>
                                <span>{journals.length} templates</span>
                                <span style={{ color: '#16a34a', fontWeight: 700 }}>✓ {totalPosted} posted</span>
                                <span style={{ color: '#d97706', fontWeight: totalPending > 0 ? 700 : 400 }}>⏳ {totalPending} pending</span>
                                {totalFailed > 0 && <span style={{ color: '#dc2626', fontWeight: 700 }}>✗ {totalFailed} failed</span>}
                                <span style={{ marginLeft: 'auto', color: '#94a3b8' }}>{runs.length} total runs across all templates</span>
                            </div>
                        </>
                    )
                )}
            </div>

            {/* ─── Confirm modal ──────────────────────────────────────────── */}
            {confirmModal && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div style={{ background: '#fff', borderRadius: '16px', padding: '28px', width: '420px', boxShadow: '0 25px 60px rgba(0,0,0,0.2)' }}>
                        <h3 style={{ margin: '0 0 10px', fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>
                            {confirmModal.type === 'generate' ? 'Generate Journal Now?' : 'Delete Template?'}
                        </h3>
                        <p style={{ margin: '0 0 24px', fontSize: '13px', color: '#64748b', lineHeight: 1.6 }}>
                            {confirmModal.type === 'generate'
                                ? `Immediately generate a journal entry from template "${confirmModal.name}".`
                                : `Permanently delete template "${confirmModal.name}" and all its run history. This cannot be undone.`}
                        </p>
                        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                            <button onClick={() => setConfirmModal(null)}
                                style={{ padding: '9px 18px', borderRadius: '8px', border: '1.5px solid #d1d5db', background: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: 600 }}>
                                Cancel
                            </button>
                            <button onClick={handleConfirm} disabled={isPending} style={{
                                padding: '9px 20px', borderRadius: '8px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: 700,
                                background: confirmModal.type === 'delete' ? '#dc2626' : '#4f46e5', color: '#fff',
                                opacity: isPending ? 0.7 : 1,
                            }}>
                                {isPending ? 'Processing…' : confirmModal.type === 'generate' ? 'Generate' : 'Delete'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </AccountingLayout>
    );
};

export default RecurringJournalList;
