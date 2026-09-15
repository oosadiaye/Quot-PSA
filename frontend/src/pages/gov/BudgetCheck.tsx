/**
 * Budget Check — Quot PSE
 * Route: /budget/check
 *
 * Look a budget line up and read its current position. Nothing else.
 *
 * There is no create, no edit, no status action and no drill-through that
 * changes anything — deliberately. An officer asked "is there budget for
 * this?" needs an answer they can trust, and a screen that can also alter
 * the thing it reports invites the answer to be altered. Appropriations
 * remain the place where a line is maintained; this is the place where it
 * is consulted.
 *
 * Everything is filtered client-side from one fetch of the selected
 * fiscal year. Two reasons beyond it being fast enough at this size:
 * every dropdown option is derived from the rows actually present, so no
 * option can return an empty result; and the figures on the detail panel
 * come from the same response as the row that was clicked, so the summary
 * and the detail can never disagree.
 */
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search, X, Info, ShieldCheck } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import apiClient from '../../api/client';

const fmtNGN = (v: number | string | undefined | null): string => {
    const num = typeof v === 'string' ? parseFloat(v) : (v || 0);
    if (isNaN(num)) return '₦0.00';
    return '₦' + num.toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

const STATUS_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
    DRAFT: { color: '#64748b', bg: '#f1f5f9', label: 'Draft' },
    SUBMITTED: { color: '#1e40af', bg: '#dbeafe', label: 'Submitted' },
    APPROVED: { color: '#6b21a8', bg: '#f3e8ff', label: 'Approved' },
    ENACTED: { color: '#166534', bg: '#dcfce7', label: 'Enacted' },
    ACTIVE: { color: '#166534', bg: '#dcfce7', label: 'Active' },
    CLOSED: { color: '#dc2626', bg: '#fef2f2', label: 'Closed' },
};

const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '0.65rem',
    fontWeight: 700,
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
    color: '#64748b',
    marginBottom: '0.3rem',
};

const controlStyle: React.CSSProperties = {
    width: '100%',
    padding: '0.45rem 0.6rem',
    fontSize: '0.8rem',
    border: '1px solid #e2e8f0',
    borderRadius: '6px',
    background: '#fff',
    color: '#1e293b',
};

const card: React.CSSProperties = {
    background: '#fff',
    border: '1px solid #e2e8f0',
    borderRadius: '10px',
    padding: '1rem 1.1rem',
    marginBottom: '1rem',
};

type Line = Record<string, any>;

/** Distinct {value,label} options taken from the rows themselves. */
const optionsFrom = (rows: Line[], codeKey: string, nameKey: string) => {
    const seen = new Map<string, string>();
    rows.forEach((r) => {
        const code = r[codeKey];
        if (code === null || code === undefined || code === '') return;
        if (!seen.has(String(code))) {
            seen.set(String(code), `${code}${r[nameKey] ? ` — ${r[nameKey]}` : ''}`);
        }
    });
    return [...seen.entries()]
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([value, label]) => ({ value, label }));
};

const BudgetCheck = () => {
    const [fiscalYearId, setFiscalYearId] = useState<string>('');
    const [codeQuery, setCodeQuery] = useState('');
    const [descQuery, setDescQuery] = useState('');
    const [mda, setMda] = useState('');
    const [fund, setFund] = useState('');
    const [econ, setEcon] = useState('');
    const [status, setStatus] = useState('');
    const [selectedId, setSelectedId] = useState<string | null>(null);

    const { data: fiscalYears = [] } = useQuery<any[]>({
        queryKey: ['budget-check-fiscal-years'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/fiscal-years/', {
                params: { page_size: 100 },
            });
            return Array.isArray(data) ? data : data?.results ?? [];
        },
        staleTime: 5 * 60 * 1000,
    });

    // Default to the active year the moment the list arrives.
    const effectiveFy = useMemo(() => {
        if (fiscalYearId) return fiscalYearId;
        const active = fiscalYears.find((f: any) => f.is_active)
            || [...fiscalYears].sort((a: any, b: any) => b.year - a.year)[0];
        return active ? String(active.id) : '';
    }, [fiscalYearId, fiscalYears]);

    const { data: lines = [], isLoading, isError, error } = useQuery<Line[]>({
        queryKey: ['budget-check-lines', effectiveFy],
        enabled: Boolean(effectiveFy),
        queryFn: async () => {
            const { data } = await apiClient.get('/budget/appropriations/', {
                params: { fiscal_year: effectiveFy, page_size: 2000, ordering: 'budget_code' },
            });
            return Array.isArray(data) ? data : data?.results ?? [];
        },
        staleTime: 60 * 1000,
    });

    const mdaOptions = useMemo(() => optionsFrom(lines, 'administrative_code', 'administrative_name'), [lines]);
    const fundOptions = useMemo(() => optionsFrom(lines, 'fund_code', 'fund_name'), [lines]);
    const econOptions = useMemo(() => optionsFrom(lines, 'economic_code', 'economic_name'), [lines]);
    const statusOptions = useMemo(
        () => [...new Set(lines.map((l) => l.status).filter(Boolean))].sort(),
        [lines],
    );

    const filtered = useMemo(() => {
        const code = codeQuery.trim().toLowerCase();
        const desc = descQuery.trim().toLowerCase();
        return lines.filter((l) => {
            if (code && !String(l.budget_code || '').toLowerCase().includes(code)) return false;
            if (desc) {
                const haystack = [
                    l.economic_code, l.economic_name, l.description,
                ].map((x) => String(x || '').toLowerCase()).join(' ');
                if (!haystack.includes(desc)) return false;
            }
            if (mda && String(l.administrative_code) !== mda) return false;
            if (fund && String(l.fund_code) !== fund) return false;
            if (econ && String(l.economic_code) !== econ) return false;
            if (status && String(l.status) !== status) return false;
            return true;
        });
    }, [lines, codeQuery, descQuery, mda, fund, econ, status]);

    const selected = useMemo(
        () => filtered.find((l) => String(l.id) === String(selectedId)) || null,
        [filtered, selectedId],
    );

    const hasFilter = Boolean(codeQuery || descQuery || mda || fund || econ || status);
    const clear = () => {
        setCodeQuery(''); setDescQuery(''); setMda(''); setFund(''); setEcon(''); setStatus('');
        setSelectedId(null);
    };

    const sc = selected ? (STATUS_CONFIG[selected.status] || STATUS_CONFIG.DRAFT) : null;

    return (
        <div style={{ display: 'flex', minHeight: '100vh', background: '#f1f5f9' }}>
            <Sidebar />
            {/* The sidebar is position:fixed at 260px, so content must be
                offset by the same amount — matching every other page here.
                Without it the first columns sit underneath the nav. */}
            <main style={{ flex: 1, minWidth: 0, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Budget Check"
                    subtitle="Look up a budget line and read its current position. Enquiry only — nothing here changes a budget."
                    icon={<ShieldCheck size={20} />}
                />

                <div style={{ paddingTop: '1.25rem', maxWidth: '1400px' }}>
                    {/* ── Search & filter ─────────────────────────────── */}
                    <div style={card}>
                        <div style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
                            gap: '0.75rem',
                            alignItems: 'end',
                        }}>
                            <div>
                                <label style={labelStyle} htmlFor="bc-code">Budget Code</label>
                                <div style={{ position: 'relative' }}>
                                    <Search size={13} style={{ position: 'absolute', left: '0.55rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                                    <input
                                        id="bc-code"
                                        type="text"
                                        value={codeQuery}
                                        onChange={(e) => { setCodeQuery(e.target.value); setSelectedId(null); }}
                                        placeholder="e.g. BL-2026-0142"
                                        style={{ ...controlStyle, paddingLeft: '1.8rem' }}
                                    />
                                </div>
                            </div>

                            <div>
                                <label style={labelStyle} htmlFor="bc-desc">GL Code / Description</label>
                                <div style={{ position: 'relative' }}>
                                    <Search size={13} style={{ position: 'absolute', left: '0.55rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                                    <input
                                        id="bc-desc"
                                        type="text"
                                        value={descQuery}
                                        onChange={(e) => { setDescQuery(e.target.value); setSelectedId(null); }}
                                        placeholder="e.g. 22020 or 'travel'"
                                        style={{ ...controlStyle, paddingLeft: '1.8rem' }}
                                    />
                                </div>
                            </div>

                            <div>
                                <label style={labelStyle} htmlFor="bc-fy">Fiscal Year</label>
                                <select
                                    id="bc-fy"
                                    value={effectiveFy}
                                    onChange={(e) => { setFiscalYearId(e.target.value); setSelectedId(null); }}
                                    style={controlStyle}
                                >
                                    {fiscalYears.map((f: any) => (
                                        <option key={f.id} value={String(f.id)}>{f.name || `FY ${f.year}`}</option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label style={labelStyle} htmlFor="bc-mda">MDA</label>
                                <select id="bc-mda" value={mda} onChange={(e) => { setMda(e.target.value); setSelectedId(null); }} style={controlStyle}>
                                    <option value="">All</option>
                                    {mdaOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                                </select>
                            </div>

                            <div>
                                <label style={labelStyle} htmlFor="bc-econ">GL Account</label>
                                <select id="bc-econ" value={econ} onChange={(e) => { setEcon(e.target.value); setSelectedId(null); }} style={controlStyle}>
                                    <option value="">All</option>
                                    {econOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                                </select>
                            </div>

                            <div>
                                <label style={labelStyle} htmlFor="bc-fund">Fund</label>
                                <select id="bc-fund" value={fund} onChange={(e) => { setFund(e.target.value); setSelectedId(null); }} style={controlStyle}>
                                    <option value="">All</option>
                                    {fundOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                                </select>
                            </div>

                            <div>
                                <label style={labelStyle} htmlFor="bc-status">Status</label>
                                <select id="bc-status" value={status} onChange={(e) => { setStatus(e.target.value); setSelectedId(null); }} style={controlStyle}>
                                    <option value="">All</option>
                                    {statusOptions.map((s) => (
                                        <option key={s} value={s}>{(STATUS_CONFIG[s] || { label: s }).label}</option>
                                    ))}
                                </select>
                            </div>

                            {hasFilter && (
                                <div>
                                    <button
                                        onClick={clear}
                                        style={{
                                            ...controlStyle, cursor: 'pointer', fontWeight: 600,
                                            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.35rem',
                                            color: '#475569',
                                        }}
                                    >
                                        <X size={13} /> Clear
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* ── Matches ─────────────────────────────────────── */}
                    <div style={card}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.6rem' }}>
                            <h2 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e293b', margin: 0 }}>
                                Matching budget lines
                            </h2>
                            <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                                {isLoading ? 'Loading…' : `${filtered.length} of ${lines.length}`}
                            </span>
                        </div>

                        {isError ? (
                            <div style={{ color: '#b91c1c', fontSize: '0.8rem', padding: '0.8rem' }}>
                                Could not load budget lines: {String((error as any)?.message || 'unknown error')}
                            </div>
                        ) : isLoading ? (
                            <div style={{ color: '#94a3b8', fontSize: '0.8rem', padding: '1rem', textAlign: 'center' }}>Loading…</div>
                        ) : filtered.length === 0 ? (
                            <div style={{ color: '#94a3b8', fontSize: '0.8rem', padding: '1.2rem', textAlign: 'center' }}>
                                {lines.length === 0
                                    ? 'No budget lines in this fiscal year.'
                                    : 'No budget line matches these filters.'}
                            </div>
                        ) : (
                            <div style={{ maxHeight: '340px', overflowY: 'auto', border: '1px solid #f1f5f9', borderRadius: '6px' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                                    <thead style={{ position: 'sticky', top: 0, background: '#f8fafc', zIndex: 1 }}>
                                        <tr>
                                            {['Budget Code', 'GL Account', 'Description', 'Fund', 'Status', 'Approved', 'Expended', 'Available'].map((h, i) => (
                                                <th key={h} style={{
                                                    padding: '0.5rem 0.6rem', textAlign: i >= 5 ? 'right' : 'left',  // Approved / Expended / Available
                                                    fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase',
                                                    letterSpacing: '0.03em', color: '#64748b',
                                                    borderBottom: '1px solid #e2e8f0', whiteSpace: 'nowrap',
                                                }}>{h}</th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {filtered.map((l) => {
                                            const isSel = String(l.id) === String(selectedId);
                                            const lsc = STATUS_CONFIG[l.status] || STATUS_CONFIG.DRAFT;
                                            return (
                                                <tr
                                                    key={l.id}
                                                    onClick={() => setSelectedId(String(l.id))}
                                                    style={{
                                                        cursor: 'pointer',
                                                        background: isSel ? 'rgba(79,70,229,0.08)' : 'transparent',
                                                        borderLeft: isSel ? '3px solid #4f46e5' : '3px solid transparent',
                                                    }}
                                                >
                                                    <td style={{ padding: '0.45rem 0.6rem', fontFamily: 'monospace', fontWeight: 600, borderBottom: '1px solid #f8fafc' }}>
                                                        {l.budget_code || <span style={{ color: '#94a3b8', fontStyle: 'italic', fontFamily: 'inherit' }}>not set</span>}
                                                    </td>
                                                    <td style={{ padding: '0.45rem 0.6rem', fontFamily: 'monospace', color: '#4f46e5', fontWeight: 600, borderBottom: '1px solid #f8fafc' }}>{l.economic_code}</td>
                                                    <td style={{ padding: '0.45rem 0.6rem', borderBottom: '1px solid #f8fafc', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.economic_name}</td>
                                                    <td style={{ padding: '0.45rem 0.6rem', fontFamily: 'monospace', borderBottom: '1px solid #f8fafc' }}>{l.fund_code}</td>
                                                    <td style={{ padding: '0.45rem 0.6rem', borderBottom: '1px solid #f8fafc' }}>
                                                        <span style={{ background: lsc.bg, color: lsc.color, padding: '0.1rem 0.4rem', borderRadius: '4px', fontSize: '0.68rem', fontWeight: 700 }}>{lsc.label}</span>
                                                    </td>
                                                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', fontWeight: 600, borderBottom: '1px solid #f8fafc', whiteSpace: 'nowrap' }}>{fmtNGN(l.amount_approved)}</td>
                                                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', fontWeight: 600, color: '#dc2626', borderBottom: '1px solid #f8fafc', whiteSpace: 'nowrap' }}>{fmtNGN(l.total_expended)}</td>
                                                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', fontWeight: 700, color: '#047857', borderBottom: '1px solid #f8fafc', whiteSpace: 'nowrap' }}>{fmtNGN(l.available_balance)}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>

                    {/* ── Detail of the selected line ─────────────────── */}
                    {selected ? (
                        <div style={card}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.6rem', marginBottom: '0.9rem' }}>
                                <div>
                                    <div style={{ fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: '#64748b' }}>
                                        Budget Code
                                    </div>
                                    <div style={{ fontSize: '1.15rem', fontWeight: 800, fontFamily: 'monospace', color: '#1e293b' }}>
                                        {selected.budget_code || <span style={{ color: '#94a3b8', fontStyle: 'italic', fontFamily: 'inherit', fontWeight: 600 }}>not set</span>}
                                    </div>
                                    <div style={{ fontSize: '0.8rem', color: '#475569', marginTop: '0.15rem' }}>
                                        {selected.economic_code} — {selected.economic_name}
                                    </div>
                                </div>
                                {sc && (
                                    <span style={{ background: sc.bg, color: sc.color, padding: '0.25rem 0.7rem', borderRadius: '999px', fontSize: '0.72rem', fontWeight: 700 }}>
                                        {sc.label}
                                    </span>
                                )}
                            </div>

                            {/* Money */}
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.7rem', marginBottom: '1rem' }}>
                                {[
                                    { label: 'Approved', value: selected.amount_approved, color: '#1e293b' },
                                    { label: 'Warrants Released', value: selected.total_warrants_released, color: '#b45309' },
                                    { label: 'Committed', value: selected.total_all_committed ?? selected.total_committed, color: '#d97706' },
                                    { label: 'Expended', value: selected.total_expended, color: '#dc2626' },
                                    { label: 'Available', value: selected.available_balance, color: '#047857' },
                                ].map((m) => (
                                    <div key={m.label} style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '0.6rem 0.7rem' }}>
                                        <div style={{ fontSize: '0.64rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.03em', color: '#64748b' }}>{m.label}</div>
                                        <div style={{ fontSize: '0.95rem', fontWeight: 800, color: m.color, marginTop: '0.2rem' }}>{fmtNGN(m.value)}</div>
                                    </div>
                                ))}
                            </div>

                            <div style={{ marginBottom: '1rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#64748b', marginBottom: '0.25rem' }}>
                                    <span>Execution rate</span>
                                    <span style={{ fontWeight: 700 }}>{Number(selected.execution_rate || 0).toFixed(1)}%</span>
                                </div>
                                <div style={{ height: '6px', background: '#f1f5f9', borderRadius: '999px', overflow: 'hidden' }}>
                                    <div style={{
                                        width: `${Math.min(100, Math.max(0, Number(selected.execution_rate || 0)))}%`,
                                        height: '100%', background: '#4f46e5',
                                    }} />
                                </div>
                            </div>

                            {/* The six NCoA segments — what identifies the line structurally */}
                            <div style={{ fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: '#64748b', marginBottom: '0.45rem' }}>
                                NCoA Classification
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '0.55rem', marginBottom: '0.9rem' }}>
                                {[
                                    ['Administrative (MDA)', selected.administrative_code, selected.administrative_name],
                                    ['Economic (GL Account)', selected.economic_code, selected.economic_name],
                                    ['Functional (COFOG)', selected.functional_code, selected.functional_name],
                                    ['Programme', selected.programme_code, selected.programme_name],
                                    ['Fund', selected.fund_code, selected.fund_name],
                                    ['Geographic', selected.geographic_code, selected.geographic_name],
                                ].map(([label, code, name]) => (
                                    <div key={String(label)} style={{ borderLeft: '2px solid #e2e8f0', paddingLeft: '0.55rem' }}>
                                        <div style={{ fontSize: '0.62rem', color: '#94a3b8', fontWeight: 700, textTransform: 'uppercase' }}>{label}</div>
                                        <div style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.8rem', color: '#1e293b' }}>
                                            {code || <span style={{ color: '#cbd5e1', fontFamily: 'inherit' }}>—</span>}
                                        </div>
                                        <div style={{ fontSize: '0.7rem', color: '#64748b' }}>{name || ''}</div>
                                    </div>
                                ))}
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '0.55rem' }}>
                                {[
                                    ['Fiscal Year', selected.fiscal_year_label],
                                    ['Appropriation Type', selected.appropriation_type],
                                    ['Law Reference', selected.law_reference],
                                    ['Description', selected.description],
                                ].map(([label, value]) => (
                                    <div key={String(label)}>
                                        <div style={{ fontSize: '0.62rem', color: '#94a3b8', fontWeight: 700, textTransform: 'uppercase' }}>{label}</div>
                                        <div style={{ fontSize: '0.8rem', color: '#1e293b' }}>{value || <span style={{ color: '#cbd5e1' }}>—</span>}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ) : (
                        <div style={{ ...card, display: 'flex', alignItems: 'center', gap: '0.55rem', color: '#64748b', fontSize: '0.82rem' }}>
                            <Info size={15} />
                            Select a budget line above to see its current position.
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
};

export default BudgetCheck;
