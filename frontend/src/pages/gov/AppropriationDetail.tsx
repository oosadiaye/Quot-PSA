/**
 * Appropriation Detail + Actions — Quot PSE
 * Route: /budget/appropriations/:id
 *
 * Shows appropriation details and provides status transition buttons:
 * DRAFT → Submit → SUBMITTED → Approve → APPROVED → Enact → ACTIVE → Close → CLOSED
 */
import { useState, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, CheckCircle2, Send, Shield, Zap, Lock, Calendar, Building2, Download, Search, X } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import '../../features/accounting/styles/glassmorphism.css';
import apiClient from '../../api/client';
import { formatApiError } from '../../utils/apiError';

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

const filterLabelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '0.6rem', fontWeight: 700,
    textTransform: 'uppercase', letterSpacing: '0.05em',
    color: 'var(--color-text-muted)',
    marginBottom: '0.25rem',
};

const filterInputStyle: React.CSSProperties = {
    width: '100%', boxSizing: 'border-box',
    padding: '0.4rem 0.55rem',
    background: '#fff',
    border: '1px solid var(--color-border, #cbd5e1)',
    borderRadius: '6px',
    fontSize: '0.75rem', color: 'var(--color-text)',
    outline: 'none',
};

export default function AppropriationDetail() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const qc = useQueryClient();
    const [actionMsg, setActionMsg] = useState('');
    const [actionError, setActionError] = useState('');

    // Filter state for the line-items table.
    //   • econQuery     — substring match against economic code OR name
    //   • functional    — exact-match dropdown (functional_code)
    //   • programme     — exact-match dropdown (programme_code)
    //   • fund          — exact-match dropdown (fund_code)
    // Empty values disable that filter; combinations narrow further.
    const [econQuery, setEconQuery] = useState('');
    const [filterFunctional, setFilterFunctional] = useState('');
    const [filterProgramme, setFilterProgramme] = useState('');
    const [filterFund, setFilterFund] = useState('');

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

    /**
     * Distinct dropdown options for the segment filters, derived from the
     * loaded `mdaLines`. Each option carries `code — name` so the user
     * can search by either; the value sent back is the bare code.
     */
    const distinctOptions = useMemo(() => {
        const fnSet = new Map<string, string>();
        const prSet = new Map<string, string>();
        const fdSet = new Map<string, string>();
        for (const l of mdaLines as any[]) {
            if (l.functional_code) fnSet.set(l.functional_code, l.functional_name || '');
            if (l.programme_code)  prSet.set(l.programme_code,  l.programme_name  || '');
            if (l.fund_code)       fdSet.set(l.fund_code,       l.fund_name       || '');
        }
        const toOpts = (m: Map<string, string>) => Array.from(m.entries())
            .sort((a, b) => a[0].localeCompare(b[0]))
            .map(([code, name]) => ({ value: code, label: name ? `${code} — ${name}` : code }));
        return {
            functional: toOpts(fnSet),
            programme: toOpts(prSet),
            fund: toOpts(fdSet),
        };
    }, [mdaLines]);

    /**
     * Apply all four filters in turn. Substring match on the econ field
     * is case-insensitive and matches against either the code or the
     * description so users can search "travel" and find every travel
     * line regardless of code prefix.
     */
    const filteredLines = useMemo(() => {
        const q = econQuery.trim().toLowerCase();
        return (mdaLines as any[]).filter((l: any) => {
            if (q) {
                const code = String(l.economic_code || '').toLowerCase();
                const name = String(l.economic_name || '').toLowerCase();
                if (!code.includes(q) && !name.includes(q)) return false;
            }
            if (filterFunctional && String(l.functional_code) !== filterFunctional) return false;
            if (filterProgramme  && String(l.programme_code)  !== filterProgramme)  return false;
            if (filterFund       && String(l.fund_code)       !== filterFund)       return false;
            return true;
        });
    }, [mdaLines, econQuery, filterFunctional, filterProgramme, filterFund]);

    const hasActiveFilter = Boolean(econQuery || filterFunctional || filterProgramme || filterFund);
    const clearFilters = () => {
        setEconQuery('');
        setFilterFunctional('');
        setFilterProgramme('');
        setFilterFund('');
    };

    /**
     * Export the currently-filtered lines to an Excel-friendly CSV.
     *
     * We build a UTF-8 CSV with a BOM so Excel auto-detects encoding and
     * renders ₦ correctly. CSV is preferred over real .xlsx because:
     *  - zero JS dependencies (no SheetJS bundle bloat)
     *  - Excel opens .csv natively as a worksheet
     *  - users can edit + re-import via the existing /bulk-import/ flow
     *
     * Filename embeds the MDA code + FY so an auditor can sort a
     * folder of exports without renaming.
     */
    const handleExportExcel = () => {
        if (!appro) return;
        const headers = [
            'Fiscal Year', 'MDA Code', 'MDA Name',
            'Economic Code', 'Economic Description',
            'Functional Code', 'Functional Name',
            'Programme Code', 'Programme Name',
            'Fund Code', 'Fund Name',
            'Type', 'Approved', 'Warrants', 'Expended', 'Available',
            'Execution %', 'Status',
        ];
        const escape = (v: unknown) => {
            const s = String(v ?? '');
            // CSV escaping: wrap in quotes if contains comma/quote/newline,
            // and double internal quotes per RFC 4180.
            return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
        };
        const fyLabel = appro.fiscal_year_label || `FY ${appro.fiscal_year_year || ''}`.trim();
        const rows = filteredLines.map((l: any) => {
            const approved = Number(l.amount_approved ?? 0) || 0;
            const expended = Number(l.total_expended ?? 0) || 0;
            const available = approved - expended;
            const exec = approved > 0 ? (expended / approved) * 100 : 0;
            return [
                fyLabel,
                appro.administrative_code || '',
                appro.administrative_name || '',
                l.economic_code || '',
                l.economic_name || '',
                l.functional_code || '',
                l.functional_name || '',
                l.programme_code || '',
                l.programme_name || '',
                l.fund_code || '',
                l.fund_name || '',
                l.appropriation_type || '',
                approved.toFixed(2),
                Number(l.total_warrants_released ?? 0).toFixed(2),
                expended.toFixed(2),
                available.toFixed(2),
                exec.toFixed(2),
                l.status || '',
            ].map(escape).join(',');
        });
        const csv = '﻿' + [headers.map(escape).join(','), ...rows].join('\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `appropriations_${appro.administrative_code || 'mda'}_${fyLabel.replace(/\s+/g, '')}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    };

    /**
     * MDA-level Budget Execution aggregates.
     *
     * The Budget Execution strip at the top of this page used to show
     * stats for the *single* appropriation line the user clicked
     * (`appro.amount_approved`, etc.) — typically a single ₦6M line —
     * which read as misleading sitting above a 55-row table that totals
     * billions. Sum across `mdaLines` instead so the strip and the
     * table footer agree, matching the rollup card on the previous page.
     *
     * If `mdaLines` hasn't loaded yet we fall back to the per-line
     * values so the UI never renders blank during the second fetch.
     */
    const mdaTotals = useMemo(() => {
        const num = (v: unknown) => Number(v ?? 0) || 0;
        if (!mdaLines || mdaLines.length === 0) {
            return {
                approved: num(appro?.amount_approved),
                warrants: num(appro?.total_warrants_released),
                expended: num(appro?.total_expended),
                available: num(appro?.available_balance),
                executionRate: num(appro?.execution_rate),
                lineCount: 0,
            };
        }
        const approved = mdaLines.reduce((s: number, l: any) => s + num(l.amount_approved), 0);
        const warrants = mdaLines.reduce((s: number, l: any) => s + num(l.total_warrants_released), 0);
        const expended = mdaLines.reduce((s: number, l: any) => s + num(l.total_expended), 0);
        const available = approved - expended;
        const executionRate = approved > 0 ? (expended / approved) * 100 : 0;
        return { approved, warrants, expended, available, executionRate, lineCount: mdaLines.length };
    }, [mdaLines, appro]);

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
            setActionError(formatApiError(err));
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
                    subtitle={`${appro.economic_code || ''} — ${appro.economic_name || ''} • FY ${appro.fiscal_year_label}`}
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

                        {/* Budget Execution — MDA-level aggregates.
                            Sums across every appropriation line under the
                            same (MDA, FY) so the strip matches both the
                            table footer below and the rollup card on the
                            previous page. */}
                        <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '1rem' }}>
                                <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: 0 }}>
                                    Budget Execution
                                </h3>
                                <span style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                                    {mdaTotals.lineCount > 0
                                        ? `MDA total across ${mdaTotals.lineCount} line${mdaTotals.lineCount === 1 ? '' : 's'}`
                                        : 'Loading…'}
                                </span>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem' }}>
                                <div className="metric-card" style={{ borderLeft: '4px solid var(--primary, #191e6a)', padding: '1rem' }}>
                                    <div style={{ fontSize: '0.6rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Approved</div>
                                    <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)' }}>{fmtNGN(mdaTotals.approved)}</div>
                                </div>
                                <div className="metric-card" style={{ borderLeft: '4px solid #f59e0b', padding: '1rem' }}>
                                    <div style={{ fontSize: '0.6rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Warrants</div>
                                    <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: '#f59e0b' }}>{fmtNGN(mdaTotals.warrants)}</div>
                                </div>
                                <div className="metric-card" style={{ borderLeft: '4px solid #ef4444', padding: '1rem' }}>
                                    <div style={{ fontSize: '0.6rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Expended</div>
                                    <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: '#ef4444' }}>{fmtNGN(mdaTotals.expended)}</div>
                                </div>
                                <div className="metric-card" style={{ borderLeft: '4px solid #22c55e', padding: '1rem' }}>
                                    <div style={{ fontSize: '0.6rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Available</div>
                                    <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: '#22c55e' }}>{fmtNGN(mdaTotals.available)}</div>
                                </div>
                            </div>
                            <div style={{ marginTop: '0.75rem' }}>
                                <div style={{ fontSize: '0.6rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.25rem' }}>
                                    Execution Rate: {mdaTotals.executionRate.toFixed(1)}%
                                </div>
                                <div style={{ background: 'var(--color-border, #e2e8f0)', borderRadius: 6, height: 8, overflow: 'hidden' }}>
                                    <div style={{
                                        height: '100%', borderRadius: 6,
                                        width: `${Math.min(mdaTotals.executionRate, 100)}%`,
                                        background: mdaTotals.executionRate > 80 ? '#ef4444' : 'var(--primary, #191e6a)',
                                        transition: 'width 0.5s ease',
                                    }} />
                                </div>
                            </div>
                        </div>

                        {/* NCoA Budget Classification — Excel-style table */}
                        <div className="glass-card" style={{ padding: '1.25rem', overflow: 'hidden' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', marginBottom: '0.75rem' }}>
                                <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: 0 }}>
                                    NCoA Budget Classification — {appro.administrative_name}
                                    <span style={{ fontWeight: 400, color: 'var(--color-text-muted)', marginLeft: '0.5rem', fontSize: '0.7rem' }}>
                                        ({filteredLines.length} of {mdaLines.length} {mdaLines.length === 1 ? 'line' : 'lines'})
                                    </span>
                                </h3>
                                <div style={{ display: 'inline-flex', gap: '0.5rem', alignItems: 'center' }}>
                                    <button
                                        onClick={() => navigate(`/budget/appropriations/${id}/transactions`)}
                                        title="View every transaction (POs, invoices, PVs, journals) posted against this appropriation"
                                        style={{
                                            display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                                            padding: '0.4rem 0.85rem',
                                            background: '#39cd9a', color: '#0b3a2c',
                                            border: 'none', borderRadius: '8px',
                                            fontSize: '0.75rem', fontWeight: 700,
                                            cursor: 'pointer',
                                        }}
                                    >
                                        View Line Item Details
                                    </button>
                                    <button
                                        onClick={handleExportExcel}
                                        disabled={filteredLines.length === 0}
                                        title={filteredLines.length === 0 ? 'Nothing to export' : `Export ${filteredLines.length} line${filteredLines.length === 1 ? '' : 's'} to CSV (Excel)`}
                                        style={{
                                            display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                                            padding: '0.4rem 0.8rem',
                                            background: filteredLines.length === 0 ? '#e2e8f0' : '#fff',
                                            color: filteredLines.length === 0 ? '#94a3b8' : '#0f172a',
                                            border: '1px solid #cbd5e1', borderRadius: '8px',
                                            fontSize: '0.75rem', fontWeight: 600,
                                            cursor: filteredLines.length === 0 ? 'not-allowed' : 'pointer',
                                            boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
                                        }}
                                    >
                                        <Download size={13} /> Export to Excel
                                    </button>
                                </div>
                            </div>

                            {/* Filter strip — economic code search + segment dropdowns */}
                            <div style={{
                                display: 'grid',
                                gridTemplateColumns: 'minmax(200px, 1.4fr) repeat(3, minmax(140px, 1fr)) auto',
                                gap: '0.5rem',
                                alignItems: 'end',
                                background: 'var(--color-surface, #f8fafc)',
                                border: '1px solid var(--color-border, #e2e8f0)',
                                borderRadius: '8px',
                                padding: '0.65rem 0.8rem',
                                marginBottom: '0.75rem',
                            }}>
                                <div>
                                    <label style={filterLabelStyle}>Economic Code / Description</label>
                                    <div style={{ position: 'relative' }}>
                                        <Search size={12} style={{ position: 'absolute', left: '0.55rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                                        <input
                                            type="text"
                                            value={econQuery}
                                            onChange={(e) => setEconQuery(e.target.value)}
                                            placeholder="e.g. 22020 or 'travel'…"
                                            style={{
                                                ...filterInputStyle,
                                                paddingLeft: '1.7rem',
                                            }}
                                        />
                                    </div>
                                </div>
                                <div>
                                    <label style={filterLabelStyle}>Functional</label>
                                    <select value={filterFunctional} onChange={(e) => setFilterFunctional(e.target.value)} style={filterInputStyle}>
                                        <option value="">All</option>
                                        {distinctOptions.functional.map(opt => (
                                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label style={filterLabelStyle}>Programme</label>
                                    <select value={filterProgramme} onChange={(e) => setFilterProgramme(e.target.value)} style={filterInputStyle}>
                                        <option value="">All</option>
                                        {distinctOptions.programme.map(opt => (
                                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label style={filterLabelStyle}>Fund</label>
                                    <select value={filterFund} onChange={(e) => setFilterFund(e.target.value)} style={filterInputStyle}>
                                        <option value="">All</option>
                                        {distinctOptions.fund.map(opt => (
                                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                                        ))}
                                    </select>
                                </div>
                                {hasActiveFilter && (
                                    <button
                                        type="button"
                                        onClick={clearFilters}
                                        title="Clear all filters"
                                        style={{
                                            display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                            padding: '0.45rem 0.7rem',
                                            background: '#fff', color: '#475569',
                                            border: '1px solid #cbd5e1', borderRadius: '6px',
                                            fontSize: '0.7rem', fontWeight: 600, cursor: 'pointer',
                                            height: 'fit-content',
                                        }}
                                    >
                                        <X size={11} /> Clear
                                    </button>
                                )}
                            </div>

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
                                            <th style={{ ...thStyle, textAlign: 'center' }}>Details</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {filteredLines.length === 0 && (
                                            <tr><td colSpan={11} style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                                                {hasActiveFilter ? 'No lines match the current filters.' : 'No appropriation lines under this MDA.'}
                                            </td></tr>
                                        )}
                                        {filteredLines.map((line: any) => {
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
                                                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                                                        <button
                                                            type="button"
                                                            onClick={(e) => {
                                                                // Stop propagation so we don't ALSO trigger the
                                                                // row's onClick (which would navigate to the
                                                                // sibling appropriation detail instead of the
                                                                // line-item drill-down).
                                                                e.stopPropagation();
                                                                navigate(`/budget/appropriations/${line.id}/transactions`);
                                                            }}
                                                            title="View every transaction posted against this line"
                                                            style={{
                                                                padding: '0.25rem 0.55rem',
                                                                background: '#39cd9a',
                                                                color: '#0b3a2c',
                                                                border: 'none',
                                                                borderRadius: 6,
                                                                fontSize: '0.65rem',
                                                                fontWeight: 700,
                                                                cursor: 'pointer',
                                                                whiteSpace: 'nowrap',
                                                            }}
                                                        >
                                                            View Details
                                                        </button>
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                    {filteredLines.length > 0 && (
                                        <tfoot>
                                            <tr style={{ borderTop: '2px solid var(--color-border)' }}>
                                                <td colSpan={6} style={{ ...tdStyle, fontWeight: 700, textAlign: 'right' }}>
                                                    {hasActiveFilter ? 'Filtered Total:' : 'MDA Total:'}
                                                </td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700 }}>
                                                    {fmtNGN(filteredLines.reduce((s: number, l: any) => s + Number(l.amount_approved || 0), 0))}
                                                </td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#ef4444' }}>
                                                    {fmtNGN(filteredLines.reduce((s: number, l: any) => s + Number(l.total_expended || 0), 0))}
                                                </td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#059669' }}>
                                                    {fmtNGN(filteredLines.reduce((s: number, l: any) => {
                                                        const approved = Number(l.amount_approved || 0);
                                                        const expended = Number(l.total_expended || 0);
                                                        return s + (Number(l.available_balance ?? approved - expended) || 0);
                                                    }, 0))}
                                                </td>
                                                <td style={tdStyle}></td>
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
