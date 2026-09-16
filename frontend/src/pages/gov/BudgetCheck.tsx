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
import { useEffect, useMemo, useRef, useState } from 'react';
import { formatDate } from '@/utils/date';
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

const txTd: React.CSSProperties = {
    padding: '0.45rem 0.6rem',
    borderBottom: '1px solid #f8fafc',
    color: '#1e293b',
};

type Line = Record<string, any>;

/**
 * Does a row's segment match what the officer typed or picked?
 *
 * Substring, over code AND name together, because these controls accept
 * both: picking a suggestion puts the bare code in the box, while typing
 * might be three digits of a code or a word from the name. An exact
 * comparison would serve the picked case and fail the typed one, which
 * is the half people actually use.
 */
const segmentMatches = (query: string, code: unknown, name: unknown): boolean => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return `${code ?? ''} ${name ?? ''}`.toLowerCase().includes(q);
};

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
    // The fiscal year is an input+datalist like every other control, but
    // its query value is the year's id, not its label — so the box holds
    // the display text and ``resolveFy`` maps what was typed or picked
    // back to an id.
    const [fyText, setFyText] = useState('');
    /**
     * ``?code=BL-2026`` pre-fills the code box.
     *
     * This is the one place a budget line is looked up by code, so every
     * other surface that wants that — the Appropriations rollup, a link
     * pasted into a memo — hands off here rather than growing its own
     * search. Read once at mount: thereafter the box is the source of
     * truth, and re-reading the URL would fight the typist.
     */
    const [codeQuery, setCodeQuery] = useState(
        () => new URLSearchParams(window.location.search).get('code') ?? '',
    );
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

    /**
     * Open on a real year, not on "all years" showing nothing.
     *
     * The register lands scoped to the active fiscal year (or the most
     * recent one if the calendar marks none), so an officer sees that
     * year's budget lines straight away rather than an empty page they
     * have to interpret. "All years" is still a choice in the dropdown.
     *
     * The exception is a ``?code=`` lookup: a pasted code may belong to
     * another year, so scoping it would hide the very line being sought.
     * There we stay on "all years" and let the code search span them.
     */
    const cameWithCode = useMemo(
        () => Boolean(new URLSearchParams(window.location.search).get('code')),
        [],
    );
    // Default once, when the years first load — not every time the field
    // goes empty, or clearing the box to "all years" would snap straight
    // back to the default year and that choice would be unreachable.
    const didDefaultFy = useRef(false);
    useEffect(() => {
        if (didDefaultFy.current || cameWithCode || fiscalYears.length === 0) return;
        didDefaultFy.current = true;
        if (fiscalYearId) return; // respect a year already chosen
        const active = fiscalYears.find((f: any) => f.is_active);
        const latest = [...fiscalYears].sort(
            (a: any, b: any) => (b.year ?? 0) - (a.year ?? 0),
        )[0];
        const pick = active ?? latest;
        if (pick) {
            setFiscalYearId(String(pick.id));
            setFyText(pick.name || `FY ${pick.year}`);
        }
    }, [fiscalYears, fiscalYearId, cameWithCode]);

    const { data: lines = [], isLoading, isError, error } = useQuery<Line[]>({
        queryKey: ['budget-check-lines', fiscalYearId || 'all'],
        queryFn: async () => {
            const params: Record<string, unknown> = {
                page_size: 2000, ordering: 'budget_code',
            };
            if (fiscalYearId) params.fiscal_year = fiscalYearId;
            const { data } = await apiClient.get('/budget/appropriations/', { params });
            return Array.isArray(data) ? data : data?.results ?? [];
        },
        staleTime: 60 * 1000,
    });

    const fyOptions = useMemo(
        () => fiscalYears
            .map((f: any) => ({ id: String(f.id), year: String(f.year ?? ''), label: f.name || `FY ${f.year}` }))
            .sort((a, b) => b.year.localeCompare(a.year)),
        [fiscalYears],
    );

    /** The fiscal year an input value points at — exact label, then year,
     *  then a unique substring; null when the box is empty or nothing
     *  fits, which the caller reads as "all years". */
    const resolveFy = (text: string) => {
        const q = text.trim().toLowerCase();
        if (!q) return null;
        return (
            fyOptions.find((o) => o.label.toLowerCase() === q) ||
            fyOptions.find((o) => o.year === q) ||
            fyOptions.find((o) => o.label.toLowerCase().includes(q) || o.year.includes(q)) ||
            null
        );
    };

    const onFyChange = (text: string) => {
        setFyText(text);
        setSelectedId(null);
        setFiscalYearId(resolveFy(text)?.id ?? '');
    };

    const mdaOptions = useMemo(() => optionsFrom(lines, 'administrative_code', 'administrative_name'), [lines]);
    const fundOptions = useMemo(() => optionsFrom(lines, 'fund_code', 'fund_name'), [lines]);
    const econOptions = useMemo(() => optionsFrom(lines, 'economic_code', 'economic_name'), [lines]);
    const statusOptions = useMemo(
        () => [...new Set(lines.map((l) => l.status).filter(Boolean))].sort(),
        [lines],
    );

    // Suggestions for the two search boxes. A ``datalist`` keeps them
    // genuinely both things: type any fragment, or open the list and pick
    // an exact value. A <select> would forbid the partial code an officer
    // half-remembers; a plain input would make them know the code already.
    //
    // The suggestion's *value* is what lands in the box, so it is the bare
    // code — the name rides along as the option's label, which browsers
    // show beside it. Putting "22100100 — Travel" in the value would set
    // the box to a string that then matches nothing.
    const codeSuggestions = useMemo(
        () => [...new Set(lines.map((l) => l.budget_code).filter(Boolean))].sort(),
        [lines],
    );

    const hasFilter = Boolean(
        codeQuery || descQuery || mda || fund || econ || status || fiscalYearId,
    );

    /**
     * Nothing is listed until the officer asks for something.
     *
     * This is an enquiry screen, not a register: opening it should not
     * answer a question nobody put. Listing every line by default also
     * trains the eye to skim a page that is usually irrelevant, and on a
     * real chart it is thousands of rows deep.
     *
     * The rows are still fetched on load, because the dropdowns below are
     * built from them — that is what guarantees no option can return an
     * empty result. Only the display waits.
     */
    const filtered = useMemo(() => {
        if (!hasFilter) return [];
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
            if (!segmentMatches(mda, l.administrative_code, l.administrative_name)) return false;
            if (!segmentMatches(fund, l.fund_code, l.fund_name)) return false;
            if (!segmentMatches(econ, l.economic_code, l.economic_name)) return false;
            // Status stays an exact select — it is a fixed, short list of
            // known values, so there is nothing to half-remember.
            if (status && String(l.status) !== status) return false;
            return true;
        });
    }, [lines, codeQuery, descQuery, mda, fund, econ, status]);

    /**
     * What actually consumed this line. The backend enumerates the very
     * sources its ``total_committed`` / ``total_expended`` are summed
     * from, so the rows below and the figures above cannot disagree —
     * and it reports any source it failed to read, which is surfaced
     * rather than quietly producing a short list that looks complete.
     */
    const { data: drill, isLoading: drillLoading, isError: drillError } = useQuery<any>({
        queryKey: ['budget-check-transactions', selectedId],
        enabled: Boolean(selectedId),
        queryFn: async () => {
            const { data } = await apiClient.get(
                `/budget/appropriations/${selectedId}/transactions/`,
            );
            return data;
        },
        staleTime: 30 * 1000,
    });

    const txns: any[] = drill?.transactions ?? [];
    const txnSummary = drill?.summary ?? null;
    const drillWarnings: string[] = drill?._warnings ?? [];
    const txnTotal = txns.reduce((sum, t) => sum + (parseFloat(t.amount) || 0), 0);

    const selected = useMemo(
        () => filtered.find((l) => String(l.id) === String(selectedId)) || null,
        [filtered, selectedId],
    );

    const clear = () => {
        setCodeQuery(''); setDescQuery(''); setMda(''); setFund(''); setEcon(''); setStatus('');
        setFiscalYearId('');
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
                                        list="bc-code-options"
                                        value={codeQuery}
                                        onChange={(e) => { setCodeQuery(e.target.value); setSelectedId(null); }}
                                        placeholder="Type or pick a code"
                                        data-testid="budget-check-code"
                                        style={{ ...controlStyle, paddingLeft: '1.8rem' }}
                                    />
                                    <datalist id="bc-code-options">
                                        {codeSuggestions.map((c) => <option key={c} value={c} />)}
                                    </datalist>
                                </div>
                            </div>

                            <div>
                                <label style={labelStyle} htmlFor="bc-desc">GL Code / Description</label>
                                <div style={{ position: 'relative' }}>
                                    <Search size={13} style={{ position: 'absolute', left: '0.55rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                                    <input
                                        id="bc-desc"
                                        type="text"
                                        list="bc-desc-options"
                                        value={descQuery}
                                        onChange={(e) => { setDescQuery(e.target.value); setSelectedId(null); }}
                                        placeholder="Type or pick an account"
                                        style={{ ...controlStyle, paddingLeft: '1.8rem' }}
                                    />
                                    <datalist id="bc-desc-options">
                                        {econOptions.map((o) => (
                                            <option key={o.value} value={o.value}>{o.label}</option>
                                        ))}
                                    </datalist>
                                </div>
                            </div>

                            <div>
                                <label style={labelStyle} htmlFor="bc-fy">Fiscal Year</label>
                                <div style={{ position: 'relative' }}>
                                    <Search size={13} style={{ position: 'absolute', left: '0.55rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                                    <input
                                        id="bc-fy"
                                        type="text"
                                        list="bc-fy-options"
                                        value={fyText}
                                        onChange={(e) => onFyChange(e.target.value)}
                                        placeholder="Type or pick a year"
                                        style={{ ...controlStyle, paddingLeft: '1.8rem' }}
                                    />
                                    {/* The option value is the display label, so picking one
                                        fills the box with "FY 2026" and resolveFy maps it to
                                        the year's id. Clear the box for all years. */}
                                    <datalist id="bc-fy-options">
                                        {fyOptions.map((o) => (
                                            <option key={o.id} value={o.label} />
                                        ))}
                                    </datalist>
                                </div>
                            </div>

                            <div>
                                <label style={labelStyle} htmlFor="bc-mda">MDA</label>
                                <div style={{ position: 'relative' }}>
                                    <Search size={13} style={{ position: 'absolute', left: '0.55rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                                    <input
                                        id="bc-mda"
                                        type="text"
                                        list="bc-mda-options"
                                        value={mda}
                                        onChange={(e) => { setMda(e.target.value); setSelectedId(null); }}
                                        placeholder="Type or pick an MDA"
                                        style={{ ...controlStyle, paddingLeft: '1.8rem' }}
                                    />
                                    <datalist id="bc-mda-options">
                                        {mdaOptions.map((o) => (
                                            <option key={o.value} value={o.value}>{o.label}</option>
                                        ))}
                                    </datalist>
                                </div>
                            </div>

                            <div>
                                <label style={labelStyle} htmlFor="bc-econ">GL Account</label>
                                <div style={{ position: 'relative' }}>
                                    <Search size={13} style={{ position: 'absolute', left: '0.55rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                                    <input
                                        id="bc-econ"
                                        type="text"
                                        list="bc-econ-options"
                                        value={econ}
                                        onChange={(e) => { setEcon(e.target.value); setSelectedId(null); }}
                                        placeholder="Type or pick an account"
                                        style={{ ...controlStyle, paddingLeft: '1.8rem' }}
                                    />
                                    <datalist id="bc-econ-options">
                                        {econOptions.map((o) => (
                                            <option key={o.value} value={o.value}>{o.label}</option>
                                        ))}
                                    </datalist>
                                </div>
                            </div>

                            <div>
                                <label style={labelStyle} htmlFor="bc-fund">Fund</label>
                                <div style={{ position: 'relative' }}>
                                    <Search size={13} style={{ position: 'absolute', left: '0.55rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                                    <input
                                        id="bc-fund"
                                        type="text"
                                        list="bc-fund-options"
                                        value={fund}
                                        onChange={(e) => { setFund(e.target.value); setSelectedId(null); }}
                                        placeholder="Type or pick a fund"
                                        style={{ ...controlStyle, paddingLeft: '1.8rem' }}
                                    />
                                    <datalist id="bc-fund-options">
                                        {fundOptions.map((o) => (
                                            <option key={o.value} value={o.value}>{o.label}</option>
                                        ))}
                                    </datalist>
                                </div>
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
                    <div style={card} data-testid="budget-check-results">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.6rem' }}>
                            <h2 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e293b', margin: 0 }}>
                                Matching budget lines
                            </h2>
                            <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                                {!hasFilter
                                    ? `${lines.length} budget line${lines.length === 1 ? '' : 's'} to search`
                                    : isLoading ? 'Loading…' : `${filtered.length} of ${lines.length}`}
                            </span>
                        </div>

                        {isError ? (
                            <div style={{ color: '#b91c1c', fontSize: '0.8rem', padding: '0.8rem' }}>
                                Could not load budget lines: {String((error as any)?.message || 'unknown error')}
                            </div>
                        ) : isLoading ? (
                            <div style={{ color: '#94a3b8', fontSize: '0.8rem', padding: '1rem', textAlign: 'center' }}>Loading…</div>
                        ) : !hasFilter ? (
                            <div style={{
                                color: '#64748b', fontSize: '0.82rem', padding: '1.6rem 1.2rem',
                                textAlign: 'center', lineHeight: 1.6,
                            }}>
                                <Search size={18} style={{ color: '#cbd5e1' }} />
                                <div style={{ marginTop: '0.4rem' }}>
                                    Enter a budget code, or use any filter above, to find a budget line.
                                </div>
                                <div style={{ fontSize: '0.74rem', color: '#94a3b8', marginTop: '0.2rem' }}>
                                    {/* Saying nothing has been searched for is not the same as
                                        saying nothing was found, and the difference matters on a
                                        screen whose whole job is answering "is there budget?" */}
                                    Nothing is listed until you search.
                                </div>
                            </div>
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
                                            {['Budget Code', 'FY', 'GL Account', 'Description', 'Fund', 'Status', 'Approved', 'Expended', 'Available'].map((h, i) => (
                                                <th key={h} style={{
                                                    padding: '0.5rem 0.6rem', textAlign: i >= 6 ? 'right' : 'left',  // Approved / Expended / Available
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
                                                    <td style={{ padding: '0.45rem 0.6rem', color: '#64748b', borderBottom: '1px solid #f8fafc', whiteSpace: 'nowrap' }}>{l.fiscal_year_label}</td>
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

                    {/* What consumed this line */}
                    {selected && (
                        <div style={card}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.6rem' }}>
                                <h2 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e293b', margin: 0 }}>
                                    Transactions recorded against this line
                                </h2>
                                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                                    {drillLoading ? 'Loading...' : `${txns.length} transaction${txns.length === 1 ? '' : 's'}`}
                                </span>
                            </div>

                            {drillWarnings.length > 0 && (
                                <div style={{
                                    background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e',
                                    borderRadius: '6px', padding: '0.5rem 0.7rem', fontSize: '0.75rem',
                                    marginBottom: '0.6rem',
                                }}>
                                    {/* A source the backend could not read. Saying so matters more
                                        than the list looking tidy: a short list that looks complete
                                        is how an officer concludes there is budget left when there
                                        is not. */}
                                    This drill-down is incomplete &mdash; {drillWarnings.join('; ')}
                                </div>
                            )}

                            {drillError ? (
                                <div style={{ color: '#b91c1c', fontSize: '0.8rem', padding: '0.8rem' }}>
                                    Could not load the transactions for this line.
                                </div>
                            ) : drillLoading ? (
                                <div style={{ color: '#94a3b8', fontSize: '0.8rem', padding: '1rem', textAlign: 'center' }}>Loading...</div>
                            ) : txns.length === 0 ? (
                                <div style={{ color: '#94a3b8', fontSize: '0.8rem', padding: '1.2rem', textAlign: 'center' }}>
                                    Nothing has been committed or spent against this line yet.
                                </div>
                            ) : (
                                <div style={{ overflowX: 'auto', border: '1px solid #f1f5f9', borderRadius: '6px' }}>
                                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                                        <thead style={{ background: '#f8fafc' }}>
                                            <tr>
                                                {['Date', 'Type', 'Reference', 'Party', 'Description', 'Status', 'Amount'].map((h, i) => (
                                                    <th key={h} style={{
                                                        padding: '0.5rem 0.6rem', textAlign: i === 6 ? 'right' : 'left',
                                                        fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase',
                                                        letterSpacing: '0.03em', color: '#64748b',
                                                        borderBottom: '1px solid #e2e8f0', whiteSpace: 'nowrap',
                                                    }}>{h}</th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {txns.map((t, idx) => {
                                                const isExpended = t.kind === 'expended';
                                                return (
                                                    <tr key={`${t.type}-${t.source_id}-${idx}`}>
                                                        <td style={txTd}>{formatDate(t.date)}</td>
                                                        <td style={{ ...txTd, whiteSpace: 'nowrap' }}>
                                                            <span style={{
                                                                background: isExpended ? '#fef2f2' : '#fffbeb',
                                                                color: isExpended ? '#dc2626' : '#b45309',
                                                                padding: '0.1rem 0.4rem', borderRadius: '4px',
                                                                fontSize: '0.66rem', fontWeight: 700,
                                                            }}>
                                                                {isExpended ? 'Expended' : 'Committed'}
                                                            </span>
                                                            <div style={{ fontSize: '0.62rem', color: '#94a3b8', marginTop: '0.1rem' }}>{t.type}</div>
                                                        </td>
                                                        <td style={{ ...txTd, fontFamily: 'monospace' }}>{t.reference || '\u2014'}</td>
                                                        <td style={txTd}>{t.party || '\u2014'}</td>
                                                        <td style={{ ...txTd, maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                            {t.description || '\u2014'}
                                                        </td>
                                                        <td style={txTd}>{t.status || '\u2014'}</td>
                                                        <td style={{ ...txTd, textAlign: 'right', fontWeight: 600, whiteSpace: 'nowrap', color: isExpended ? '#dc2626' : '#b45309' }}>
                                                            {fmtNGN(t.amount)}
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                        {/* Sum at the bottom. Committed and expended are shown apart
                                            before they are added: a transaction is one or the other,
                                            never both, so the total is what this line has consumed —
                                            and it is the same subtraction that produces the Available
                                            figure on the panel above. */}
                                        <tfoot>
                                            {txnSummary && (
                                                <>
                                                    <tr style={{ background: '#fafafa' }}>
                                                        <td colSpan={6} style={{ ...txTd, textAlign: 'right', color: '#b45309', fontWeight: 600 }}>
                                                            Committed ({txnSummary.committed_count})
                                                        </td>
                                                        <td style={{ ...txTd, textAlign: 'right', fontWeight: 700, color: '#b45309', whiteSpace: 'nowrap' }}>
                                                            {fmtNGN(txnSummary.committed_total)}
                                                        </td>
                                                    </tr>
                                                    <tr style={{ background: '#fafafa' }}>
                                                        <td colSpan={6} style={{ ...txTd, textAlign: 'right', color: '#dc2626', fontWeight: 600 }}>
                                                            Expended ({txnSummary.expended_count})
                                                        </td>
                                                        <td style={{ ...txTd, textAlign: 'right', fontWeight: 700, color: '#dc2626', whiteSpace: 'nowrap' }}>
                                                            {fmtNGN(txnSummary.expended_total)}
                                                        </td>
                                                    </tr>
                                                </>
                                            )}
                                            <tr style={{ background: '#f1f5f9' }}>
                                                <td colSpan={6} style={{ ...txTd, textAlign: 'right', fontWeight: 800, color: '#1e293b', borderTop: '2px solid #cbd5e1' }}>
                                                    Total of listed transactions
                                                </td>
                                                <td style={{ ...txTd, textAlign: 'right', fontWeight: 800, color: '#1e293b', borderTop: '2px solid #cbd5e1', whiteSpace: 'nowrap' }}>
                                                    {fmtNGN(txnTotal)}
                                                </td>
                                            </tr>
                                            {/* The appropriation keeps its own figure for what it
                                                has consumed, and it is not always this sum: the
                                                drill-down walks descendant GL accounts, so a
                                                parent-coded line lists spend that belongs to its
                                                children's own budget lines. Showing both numbers
                                                next to each other without a word would invite the
                                                reader to assume the smaller one is wrong. Stating
                                                the gap is the honest option — and it is a
                                                data-quality signal worth seeing. */}
                                            {(() => {
                                                const consumed = (parseFloat(selected.total_expended) || 0)
                                                    + (parseFloat(selected.total_all_committed ?? selected.total_committed) || 0);
                                                const gap = txnTotal - consumed;
                                                if (Math.abs(gap) < 0.01) {
                                                    return (
                                                        <tr>
                                                            <td colSpan={6} style={{ ...txTd, textAlign: 'right', color: '#047857', fontWeight: 700 }}>
                                                                Available after these
                                                            </td>
                                                            <td style={{ ...txTd, textAlign: 'right', fontWeight: 800, color: '#047857', whiteSpace: 'nowrap' }}>
                                                                {fmtNGN(selected.available_balance)}
                                                            </td>
                                                        </tr>
                                                    );
                                                }
                                                return (
                                                    <>
                                                        <tr>
                                                            <td colSpan={6} style={{ ...txTd, textAlign: 'right', color: '#64748b', fontWeight: 600 }}>
                                                                This line&rsquo;s own consumed figure
                                                            </td>
                                                            <td style={{ ...txTd, textAlign: 'right', fontWeight: 700, color: '#64748b', whiteSpace: 'nowrap' }}>
                                                                {fmtNGN(consumed)}
                                                            </td>
                                                        </tr>
                                                        <tr>
                                                            <td colSpan={7} style={{
                                                                ...txTd, background: '#fffbeb', color: '#92400e',
                                                                fontSize: '0.72rem', lineHeight: 1.45,
                                                            }}>
                                                                The listed transactions total {fmtNGN(txnTotal)}, which is{' '}
                                                                {fmtNGN(Math.abs(gap))} {gap > 0 ? 'more' : 'less'} than this
                                                                line&rsquo;s own consumed figure of {fmtNGN(consumed)}. The list walks
                                                                descendant GL accounts, so a parent-coded line shows spend that
                                                                belongs to its children&rsquo;s budget lines. The Available figure
                                                                above is calculated from this line&rsquo;s own figure, not from
                                                                this list.
                                                            </td>
                                                        </tr>
                                                    </>
                                                );
                                            })()}
                                        </tfoot>
                                    </table>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
};

export default BudgetCheck;
