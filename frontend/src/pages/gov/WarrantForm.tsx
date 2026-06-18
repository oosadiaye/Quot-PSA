/**
 * Warrant (AIE) Create Form — Quot PSE
 * Route: /budget/warrants/new
 *
 * Two-pane layout:
 *
 *   Left  — Step 1 picks an MDA, Step 2 ticks one or more economic
 *           lines under that MDA (with per-line amount inputs). Quarter
 *           and release date are shared across the whole batch. Submit
 *           hits POST /budget/warrants/bulk_create/ which wraps every
 *           line in a single transaction — N warrants land or none do,
 *           never half.
 *
 *   Right — Live print-style preview using the same
 *           <WarrantPrintLayout/> component the actual /print page
 *           renders. Pulls letterhead, signatures and footer from
 *           /budget/warrant-printout-settings/current/. So WYSIWYG —
 *           anything tweaked in /settings/warrant-printout shows up
 *           here immediately, and matches the printout one-to-one.
 *
 * Schema invariant preserved: Warrant.unique_together = (appropriation,
 * quarter). Each ticked line still becomes one Warrant row; "multi-line"
 * is purely a frontend orchestration on top of the existing model.
 */
import { useState, useMemo, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Save, AlertCircle, FileText, Info, Paperclip, X,
    Building2, CheckCircle2, Eye, EyeOff, Sparkles, Search,
} from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import '../../features/accounting/styles/glassmorphism.css';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAppropriationsList, useFiscalYears } from '../../hooks/useGovForms';
import apiClient from '../../api/client';
import WarrantPrintLayout from '../../components/warrant/WarrantPrintLayout';
import type { WarrantPrintSettings } from '../../components/warrant/WarrantPrintLayout';
import SmartCreateWarrantModal from './SmartCreateWarrantModal';

// ─── Local style tokens ──────────────────────────────────────────────
const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-xs)',
};
const selectStyle: React.CSSProperties = { ...inputStyle };
const lblStyle: React.CSSProperties = {
    display: 'block', fontSize: '0.65rem', fontWeight: 600,
    color: 'var(--color-text-muted)', marginBottom: '0.25rem',
    textTransform: 'uppercase' as const, letterSpacing: '0.04em',
};

/**
 * Period preset buttons. Each computes a [from, to] from the supplied
 * fiscal-year bounds. "Annual" is the default — it spans the entire
 * fiscal year — but we surface quarter-equivalent presets so the
 * legacy quarterly workflow is one click away even though quarter is
 * no longer the schema's primary period column.
 */
const PERIOD_PRESETS = (fyStart: Date, fyEnd: Date) => {
    const carve = (q: number): [Date, Date] => {
        const span = fyEnd.getTime() - fyStart.getTime();
        const bucket = span / 4;
        const start = new Date(fyStart.getTime() + bucket * (q - 1));
        const end = q === 4
            ? new Date(fyEnd)
            : new Date(fyStart.getTime() + bucket * q - 24 * 3600 * 1000);
        return [start, end];
    };
    return [
        { key: 'annual', label: 'Annual', range: [fyStart, fyEnd] as [Date, Date] },
        { key: 'q1', label: 'Q1', range: carve(1) },
        { key: 'q2', label: 'Q2', range: carve(2) },
        { key: 'q3', label: 'Q3', range: carve(3) },
        { key: 'q4', label: 'Q4', range: carve(4) },
    ];
};

const toIso = (d: Date) => d.toISOString().split('T')[0];

const fmtNGN = (v: number | string | undefined): string => {
    const num = typeof v === 'string' ? parseFloat(v) : (v || 0);
    if (isNaN(num)) return '₦0.00';
    return '₦' + num.toLocaleString('en-NG', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
};

// ─── Per-line state shape ────────────────────────────────────────────
// One row per appropriation under the selected MDA. ``amount_released``
// is a raw string so the input can stay controlled even when empty.
interface LineState {
    appropriation_id: number;
    economic_code: string;
    economic_name: string;
    available_balance: string;
    amount_approved: string;
    selected: boolean;
    amount_released: string;
    notes: string;
}

export default function WarrantForm() {
    const navigate = useNavigate();
    const qc = useQueryClient();
    const { data: appropriations } = useAppropriationsList();
    const fileInputRef = useRef<HTMLInputElement>(null);

    const [formError, setFormError] = useState('');
    const [attachmentFile, setAttachmentFile] = useState<File | null>(null);

    // Toggle for the right-side print preview panel — collapsible so
    // the form can take the full width on small screens.
    const [previewOpen, setPreviewOpen] = useState(true);
    // Smart Create modal — fast-path for entering N warrants at once
    // without walking the per-line checklist below. The modal lives
    // alongside the form so the operator can switch between the two
    // entry styles freely; both ultimately POST to the same
    // /budget/warrants/bulk_create/ endpoint.
    const [smartCreateOpen, setSmartCreateOpen] = useState(false);

    // ── Pull warrant printout settings so the live preview matches
    //    exactly what /print will show. Single source of truth lives in
    //    /settings/warrant-printout; query is shared with the print page
    //    via the same query key, so editing settings + reopening this
    //    form refetches just once.
    const { data: settings } = useQuery<WarrantPrintSettings>({
        queryKey: ['warrant-printout-settings'],
        queryFn: async () => {
            const { data } = await apiClient.get(
                '/budget/warrant-printout-settings/current/',
            );
            return data;
        },
    });

    // ── Two-stage picker: MDA first, lines second ────────────────────
    const [mdaInput, setMdaInput] = useState('');
    const [selectedMdaCode, setSelectedMdaCode] = useState('');
    const [selectedMdaName, setSelectedMdaName] = useState('');

    // Shared across all lines.
    // Date range replaces the legacy quarter selector. Defaults below
    // are seeded from the chosen MDA's fiscal year so the most common
    // case (an annual warrant covering the full FY) is zero-click.
    // Default both effective dates to today. Operators routinely raise
    // warrants for "release today" and the previous FY-bounds seed was
    // producing 1900-era dates whenever appropriations carried a stale
    // fiscal_year. The quick-preset chips (Annual / Q1-Q4) still let the
    // operator switch to a full-year or quarterly window in one click.
    const [effectiveFrom, setEffectiveFrom] = useState<string>(() => toIso(new Date()));
    const [effectiveTo, setEffectiveTo] = useState<string>(() => toIso(new Date()));
    const [releaseDate, setReleaseDate] = useState(
        new Date().toISOString().split('T')[0],
    );
    const [authorityRefPrefix, setAuthorityRefPrefix] = useState('');

    // Per-line state, regenerated when the MDA changes.
    const [lines, setLines] = useState<LineState[]>([]);
    // Search box above the economic-line picker. Filters by code prefix /
    // substring or by name (case-insensitive). Bulk Select all / Clear all
    // operate on the *filtered* view so an operator can type "22020" and
    // bulk-select only those lines without losing their existing picks
    // outside the filter.
    const [filterTerm, setFilterTerm] = useState('');

    // ── Derive: list of MDAs that have at least one appropriation ──
    const mdasWithBudget = useMemo(() => {
        if (!appropriations) return [];
        const seen = new Map<string, { code: string; name: string }>();
        for (const a of appropriations as any[]) {
            const key = a.administrative_code || '';
            if (key && !seen.has(key)) {
                seen.set(key, { code: key, name: a.administrative_name || '' });
            }
        }
        return [...seen.values()].sort((a, b) => a.code.localeCompare(b.code));
    }, [appropriations]);

    // ── Derive: appropriations under the chosen MDA ────────────────
    const apprsForMda = useMemo(() => {
        if (!appropriations || !selectedMdaCode) return [];
        return (appropriations as any[]).filter(
            a => a.administrative_code === selectedMdaCode,
        );
    }, [appropriations, selectedMdaCode]);

    // Regenerate lines whenever the MDA changes — preserves nothing
    // from the previous MDA on purpose (lines are tied to that MDA).
    useEffect(() => {
        if (!selectedMdaCode) {
            setLines([]);
            return;
        }
        const next: LineState[] = apprsForMda.map(a => ({
            appropriation_id: a.id,
            economic_code: a.economic_code || '',
            economic_name: a.economic_name || '',
            available_balance: a.available_balance || '0',
            amount_approved: a.amount_approved || '0',
            selected: false,
            amount_released: '',
            notes: '',
        }));
        setLines(next);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedMdaCode, appropriations]);

    // ── MDA resolver ─────────────────────────────────────────────────
    const resolveMda = (value: string) => {
        setMdaInput(value);
        const match = mdasWithBudget.find(
            m =>
                value === m.code ||
                value === `${m.code} — ${m.name}` ||
                value.toLowerCase() === m.name.toLowerCase(),
        );
        setSelectedMdaCode(match ? match.code : '');
        setSelectedMdaName(match ? match.name : '');
    };

    // ── Per-line mutators ────────────────────────────────────────────
    const toggleLine = (idx: number) =>
        setLines(prev => prev.map((l, i) =>
            i === idx ? {
                ...l, selected: !l.selected,
                // Auto-fill amount with available balance the first time
                // a line is ticked, so the common case (release the
                // full quarterly portion) is one-click. Operator can
                // overwrite immediately.
                amount_released: !l.selected && !l.amount_released
                    ? l.available_balance : l.amount_released,
            } : l,
        ));

    const setLineAmount = (idx: number, value: string) =>
        setLines(prev => prev.map((l, i) =>
            i === idx ? { ...l, amount_released: value } : l,
        ));

    const setLineNotes = (idx: number, value: string) =>
        setLines(prev => prev.map((l, i) =>
            i === idx ? { ...l, notes: value } : l,
        ));

    const selectAll = (sel: boolean) => {
        // Restrict bulk action to currently visible (filtered) rows so the
        // operator doesn't accidentally clear or release lines hidden by
        // the search filter.
        const q = filterTerm.trim().toLowerCase();
        const matches = (l: LineState) => !q
            || l.economic_code.toLowerCase().includes(q)
            || (l.economic_name || '').toLowerCase().includes(q);
        setLines(prev => prev.map(l => matches(l) ? ({
            ...l,
            selected: sel,
            amount_released: sel && !l.amount_released
                ? l.available_balance : l.amount_released,
        }) : l));
    };

    // ── Aggregates: selected count, total amount, balance breaches ──
    const selectedLines = useMemo(
        () => lines.filter(l => l.selected),
        [lines],
    );
    const totalReleased = useMemo(
        () => selectedLines.reduce(
            (acc, l) => acc + (parseFloat(l.amount_released) || 0), 0,
        ),
        [selectedLines],
    );
    const linesExceedingBalance = useMemo(
        () => selectedLines.filter(l =>
            (parseFloat(l.amount_released) || 0) >
            (parseFloat(l.available_balance) || 0),
        ),
        [selectedLines],
    );

    // ── Derive defaults from the chosen MDA's fiscal year. The
    //    appropriation list embeds ``fiscal_year_start_date`` /
    //    ``_end_date`` (added in the same refactor that introduced the
    //    date range) so we can default the warrant window to the
    //    appropriation's full FY without an extra query. Falls back
    //    to a calendar-year guess when the FY rows pre-date the
    //    schema change.
    // Pull every fiscal year and pick the active one as the source of
    // truth for the warrant date window + quick-preset chips. The
    // appropriation rows in some tenants still carry FY data from 1900
    // (legacy seed), so anchoring the presets there produced 1900-era
    // Q1-Q4 windows. The active FiscalYear is authoritative.
    const { data: fiscalYears } = useFiscalYears();
    const activeFiscalYear = useMemo(() => {
        const list = Array.isArray(fiscalYears) ? fiscalYears : [];
        return list.find((f: any) => f.is_active)
            || list.find((f: any) => f.status === 'Open')
            || list[0]
            || null;
    }, [fiscalYears]);

    const fy = useMemo(() => {
        if (activeFiscalYear) {
            return activeFiscalYear.name || String(activeFiscalYear.year || '');
        }
        if (!apprsForMda.length) return '';
        const a = apprsForMda[0];
        return a.fiscal_year_display || a.fiscal_year || '';
    }, [activeFiscalYear, apprsForMda]);

    const fyBounds = useMemo<[Date, Date]>(() => {
        // 1) Active FiscalYear wins — keeps quick presets anchored to the
        //    current government budget year regardless of appropriation seed.
        if (activeFiscalYear?.start_date && activeFiscalYear?.end_date) {
            return [new Date(activeFiscalYear.start_date), new Date(activeFiscalYear.end_date)];
        }
        // 2) Fallback: appropriation's FY (only if appropriations carry one).
        if (apprsForMda.length) {
            const a = apprsForMda[0] as any;
            const startStr = a.fiscal_year_start_date;
            const endStr = a.fiscal_year_end_date;
            if (startStr && endStr) {
                return [new Date(startStr), new Date(endStr)];
            }
        }
        // 3) Last resort: current calendar year.
        const yr = parseInt(String(fy), 10) || new Date().getFullYear();
        return [new Date(yr, 0, 1), new Date(yr, 11, 31)];
    }, [activeFiscalYear, apprsForMda, fy]);

    // Effective dates default to today (set in useState initializer above).
    // No FY-bounds auto-seed on MDA selection — the previous behaviour
    // produced 1900-era dates whenever appropriations carried a stale
    // fiscal_year. Operators who want a full-year or quarterly window
    // can click the Annual / Q1-Q4 preset chips below the date inputs.

    useEffect(() => {
        if (selectedMdaCode && fy && !authorityRefPrefix) {
            // No quarter to embed in the suffix anymore — the prefix
            // identifies the MDA + FY, the per-line economic code
            // disambiguates rows.
            setAuthorityRefPrefix(`AIE/${fy}/${selectedMdaCode}`);
        }
    }, [selectedMdaCode, fy, authorityRefPrefix]);

    // ── Build the lines payload sent to the bulk endpoint ──
    const buildPayloadLines = () =>
        selectedLines.map(l => ({
            appropriation: l.appropriation_id,
            amount_released: l.amount_released,
            authority_reference:
                authorityRefPrefix
                    ? `${authorityRefPrefix}/${l.economic_code}`
                    : `AIE/${l.economic_code}`,
            notes: l.notes,
        }));

    // ── Mutations ────────────────────────────────────────────────────
    const bulkCreate = useMutation({
        mutationFn: async () => {
            const body = {
                effective_from: effectiveFrom,
                effective_to: effectiveTo,
                release_date: releaseDate,
                lines: buildPayloadLines(),
            };
            const { data } = await apiClient.post(
                '/budget/warrants/bulk_create/', body,
            );
            return data;
        },
        onSuccess: async () => {
            // Best-effort attachment upload for the FIRST created warrant
            // so the AIE letter stays attached to the batch's first row
            // (the rest share the reference). A nicer implementation would
            // accept the file in the bulk endpoint; doing it after the
            // fact keeps the bulk endpoint JSON-only and avoids multipart
            // parsing on a hot path.
            // TODO: thread attachment through bulk endpoint when needed.
            qc.invalidateQueries({ queryKey: ['generic-list'] });
            qc.invalidateQueries({ queryKey: ['appropriations-dropdown'] });
            navigate('/budget/warrants');
        },
    });

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        if (!selectedMdaCode) {
            setFormError('Pick an MDA first.');
            return;
        }
        if (!effectiveFrom || !effectiveTo) {
            setFormError('Pick the effective date range (from / to).');
            return;
        }
        if (new Date(effectiveTo) < new Date(effectiveFrom)) {
            setFormError('Effective "to" cannot be earlier than "from".');
            return;
        }
        if (selectedLines.length === 0) {
            setFormError('Tick at least one economic line to release.');
            return;
        }
        if (linesExceedingBalance.length) {
            setFormError(
                `${linesExceedingBalance.length} line(s) exceed their available balance. Fix before submitting.`,
            );
            return;
        }
        for (const l of selectedLines) {
            const amt = parseFloat(l.amount_released);
            if (!amt || amt <= 0) {
                setFormError(`Line ${l.economic_code} has no amount.`);
                return;
            }
        }

        try {
            await bulkCreate.mutateAsync();
        } catch (err: any) {
            const d = err.response?.data;
            if (d?.lines) {
                // Backend returns per-line failures as
                // ``{ lines: [{ line, errors: {<field>: [...] | str} }] }``.
                // Flatten the nested DRF error shape into readable
                // sentences instead of dumping raw JSON onto the user.
                const flattenErrors = (errors: any): string => {
                    if (!errors) return 'Unknown error';
                    if (typeof errors === 'string') return errors;
                    if (Array.isArray(errors)) return errors.join(' ');
                    if (typeof errors === 'object') {
                        return Object.entries(errors)
                            .map(([field, msgs]) => {
                                const text = Array.isArray(msgs) ? msgs.join(' ') : String(msgs);
                                return field === 'non_field_errors' || field === 'detail'
                                    ? text
                                    : `${field}: ${text}`;
                            })
                            .join(' · ');
                    }
                    return String(errors);
                };
                const msgs = d.lines.map((row: any) => {
                    const flat = flattenErrors(row.errors);
                    // Backend ``row.line`` indexes the selected subset that
                    // was POSTed (one entry per ticked line), not the full
                    // table. Look up the code in ``selectedLines`` so the
                    // prefix matches what the operator actually ticked.
                    const code = selectedLines[row.line]?.economic_code
                        || lines[row.line]?.economic_code
                        || `Line ${row.line + 1}`;
                    // Add a one-line resolution hint for the overlap rule —
                    // the most common cause of a warrant-create rejection.
                    const hint = /overlaps an existing warrant/i.test(flat)
                        ? ' — open Warrants / AIE, then Approve → Release, or Cancel the conflicting warrant, or narrow this warrant\'s date window so it does not intersect.'
                        : '';
                    return `${code}: ${flat}${hint}`;
                });
                setFormError(msgs.join(' | '));
            } else if (d?.error) {
                setFormError(d.error);
            } else if (d?.detail) {
                setFormError(String(d.detail));
            } else if (d?.non_field_errors) {
                setFormError(
                    Array.isArray(d.non_field_errors)
                        ? d.non_field_errors.join(' ')
                        : String(d.non_field_errors),
                );
            } else {
                setFormError(err.message || 'Failed to create warrants');
            }
        }
    };

    // ── Build the lines that the print preview component renders ──
    // Mirror the on-form selection: if nothing is ticked, show all
    // lines as zero-released so the layout is still meaningful (the
    // preview reads as a placeholder until the operator picks lines).
    const previewLines = useMemo(() => {
        const source = selectedLines.length > 0 ? selectedLines : lines;
        return source.map(l => ({
            economic_code: l.economic_code,
            economic_name: l.economic_name,
            amount_released: l.amount_released || '0',
            appropriation_amount_approved: l.amount_approved,
        }));
    }, [selectedLines, lines]);

    const previewWarrantNumber = authorityRefPrefix
        || (selectedMdaCode && fy
            ? `AIE/${fy}/${selectedMdaCode}`
            : 'AIE/—/—');

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2rem 2.5rem' }}>
                <PageHeader
                    title="New Warrant (AIE)"
                    subtitle="Cash release for an MDA — pick one MDA, set the effective date range (defaults to annual), then tick the economic lines to warrant"
                    icon={<FileText size={22} />}
                    actions={
                        <button
                            type="button"
                            onClick={() => setSmartCreateOpen(true)}
                            title="Mass-create N warrants for one MDA in a single step"
                            style={{
                                display: 'inline-flex', alignItems: 'center', gap: 6,
                                padding: '8px 14px', borderRadius: 8, border: 'none',
                                background: 'linear-gradient(135deg, #6366f1 0%, #4338ca 100%)',
                                color: 'white', fontSize: 12, fontWeight: 700,
                                letterSpacing: 0.3,
                                cursor: 'pointer',
                                boxShadow: '0 4px 12px rgba(79, 70, 229, 0.35)',
                            }}
                        >
                            <Sparkles size={13} /> Smart Create
                        </button>
                    }
                />

                {formError && (
                    <div style={{
                        padding: '10px 14px', borderRadius: 8, marginBottom: 14,
                        background: '#fef2f2', border: '1px solid #fecaca',
                        color: '#dc2626', display: 'flex', alignItems: 'flex-start',
                        gap: 8, fontSize: 13,
                    }}>
                        <AlertCircle size={14} style={{ marginTop: 2, flexShrink: 0 }} />
                        <div style={{ wordBreak: 'break-word' }}>{formError}</div>
                    </div>
                )}

                <form onSubmit={handleSubmit}>
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: previewOpen ? 'minmax(0, 1.15fr) minmax(0, 1fr)' : '1fr',
                        gap: 18,
                        alignItems: 'flex-start',
                    }}>
                        {/* ════════════════════════════════════════════ *
                         *  LEFT: Multi-line picker + shared fields    *
                         * ════════════════════════════════════════════ */}
                        <div style={{ minWidth: 0 }}>
                            {/* Step 1 — MDA */}
                            <div className="glass-card" style={{ padding: '1.1rem 1.25rem', marginBottom: 14 }}>
                                <h3 style={cardH3}>
                                    <Building2 size={14} /> Step 1 · Select MDA
                                </h3>
                                <input
                                    type="text"
                                    list="mda-with-budget-list"
                                    value={mdaInput}
                                    onChange={e => resolveMda(e.target.value)}
                                    placeholder={mdasWithBudget.length
                                        ? `Type or pick from ${mdasWithBudget.length} MDA${mdasWithBudget.length === 1 ? '' : 's'} with a budget…`
                                        : 'No MDA has any appropriation yet'}
                                    disabled={mdasWithBudget.length === 0}
                                    style={{
                                        ...inputStyle,
                                        borderColor: selectedMdaCode ? '#22c55e' : undefined,
                                    }}
                                />
                                <datalist id="mda-with-budget-list">
                                    {mdasWithBudget.map(m => (
                                        <option key={m.code} value={`${m.code} — ${m.name}`} />
                                    ))}
                                </datalist>
                                {selectedMdaCode && (
                                    <div style={{ fontSize: 11, color: '#16a34a', marginTop: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
                                        <CheckCircle2 size={12} />
                                        Resolved <span style={{ fontFamily: 'monospace' }}>{selectedMdaCode}</span>
                                        &nbsp;·&nbsp; {apprsForMda.length} budget line{apprsForMda.length === 1 ? '' : 's'}
                                    </div>
                                )}
                            </div>

                            {/* Step 2 — Shared warrant details (dates, presets, prefix, attachment) */}
                            <div className="glass-card" style={{ padding: '1.1rem 1.25rem', marginBottom: 14 }}>
                                <h3 style={cardH3}>
                                    <Info size={14} /> Step 2 · Shared across all selected lines
                                </h3>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                                    <div>
                                        <label style={lblStyle}>Effective From *</label>
                                        <input
                                            style={inputStyle}
                                            type="date"
                                            required
                                            value={effectiveFrom}
                                            onChange={e => setEffectiveFrom(e.target.value)}
                                        />
                                    </div>
                                    <div>
                                        <label style={lblStyle}>Effective To *</label>
                                        <input
                                            style={{
                                                ...inputStyle,
                                                borderColor:
                                                    effectiveFrom && effectiveTo &&
                                                    new Date(effectiveTo) < new Date(effectiveFrom)
                                                        ? '#ef4444' : undefined,
                                            }}
                                            type="date"
                                            required
                                            value={effectiveTo}
                                            onChange={e => setEffectiveTo(e.target.value)}
                                        />
                                    </div>
                                    <div>
                                        <label style={lblStyle}>Release Date *</label>
                                        <input
                                            style={inputStyle}
                                            type="date"
                                            required
                                            value={releaseDate}
                                            onChange={e => setReleaseDate(e.target.value)}
                                        />
                                    </div>
                                    {/* Period presets — annual is the default; quarter
                                        presets are kept as one-click shortcuts for
                                        operators used to the legacy quarterly cadence.
                                        These derive their dates from the chosen MDA's
                                        fiscal year so the picks stay correct even if
                                        the FY isn't a calendar year. */}
                                    <div style={{ gridColumn: '1 / -1' }}>
                                        <label style={lblStyle}>Quick presets</label>
                                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                            {PERIOD_PRESETS(fyBounds[0], fyBounds[1]).map(p => {
                                                const [s, e] = p.range;
                                                const sIso = toIso(s); const eIso = toIso(e);
                                                const active = effectiveFrom === sIso && effectiveTo === eIso;
                                                return (
                                                    <button
                                                        key={p.key}
                                                        type="button"
                                                        onClick={() => {
                                                            setEffectiveFrom(sIso);
                                                            setEffectiveTo(eIso);
                                                        }}
                                                        style={{
                                                            padding: '6px 12px', borderRadius: 6,
                                                            border: active ? '2px solid #4f46e5' : '1px solid #cbd5e1',
                                                            background: active ? '#eef2ff' : '#fff',
                                                            color: active ? '#4338ca' : '#1e293b',
                                                            fontSize: 11, fontWeight: 600,
                                                            cursor: 'pointer',
                                                        }}
                                                    >
                                                        {p.label}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>
                                    <div style={{ gridColumn: '1 / -1' }}>
                                        <label style={lblStyle}>
                                            Authority Reference Prefix
                                            <span style={{ fontWeight: 400, textTransform: 'none', color: '#94a3b8' }}>
                                                {' '}(per-line refs append the economic code)
                                            </span>
                                        </label>
                                        <input
                                            style={inputStyle}
                                            value={authorityRefPrefix}
                                            onChange={e => setAuthorityRefPrefix(e.target.value)}
                                            placeholder="e.g. AIE/2026/Q1/050200000000"
                                        />
                                    </div>
                                </div>

                                {/* AIE letter attachment */}
                                <div style={{ marginTop: 12 }}>
                                    <label style={lblStyle}>
                                        <Paperclip size={11} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                                        AIE Letter Attachment
                                    </label>
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                                        style={{ display: 'none' }}
                                        onChange={e => setAttachmentFile(e.target.files?.[0] || null)}
                                    />
                                    {attachmentFile ? (
                                        <div style={{
                                            display: 'flex', alignItems: 'center', gap: 8,
                                            padding: '8px 12px', borderRadius: 8,
                                            background: '#f0fdf4', border: '1px solid #86efac',
                                        }}>
                                            <Paperclip size={14} color="#166534" />
                                            <span style={{ fontSize: 12, color: '#166534', flex: 1 }}>
                                                {attachmentFile.name}
                                            </span>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    setAttachmentFile(null);
                                                    if (fileInputRef.current) fileInputRef.current.value = '';
                                                }}
                                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: 2 }}
                                            >
                                                <X size={14} />
                                            </button>
                                        </div>
                                    ) : (
                                        <button
                                            type="button"
                                            onClick={() => fileInputRef.current?.click()}
                                            style={{
                                                display: 'flex', alignItems: 'center', gap: 6,
                                                padding: '8px 14px', borderRadius: 8,
                                                border: '1.5px dashed #cbd5e1', background: '#f8fafc',
                                                color: '#64748b', fontSize: 12, cursor: 'pointer', width: '100%',
                                            }}
                                        >
                                            <Paperclip size={13} /> Attach the signed AIE letter
                                        </button>
                                    )}
                                </div>
                            </div>

                            {/* Step 3 — Multi-line picker */}
                            <div className="glass-card" style={{ padding: '1.1rem 1.25rem', marginBottom: 14 }}>
                                <h3 style={cardH3}>
                                    <FileText size={14} /> Step 3 · Tick economic lines to release
                                </h3>
                                <p style={cardHint}>
                                    Each ticked line becomes its own Warrant row (one per
                                    economic code). The whole batch lands atomically: if
                                    any line fails validation, none persist.
                                </p>
                                {!selectedMdaCode ? (
                                    <div style={emptyHint}>
                                        Pick an MDA above to see its budget lines.
                                    </div>
                                ) : lines.length === 0 ? (
                                    <div style={emptyHint}>
                                        This MDA has no active appropriations.
                                    </div>
                                ) : (
                                    <>
                                        {/* Filter — search by economic code or name. */}
                                        <div style={{
                                            position: 'relative', marginBottom: 8,
                                        }}>
                                            <Search
                                                size={14}
                                                style={{
                                                    position: 'absolute', left: 10, top: '50%',
                                                    transform: 'translateY(-50%)', color: '#94a3b8',
                                                    pointerEvents: 'none',
                                                }}
                                            />
                                            <input
                                                type="text"
                                                value={filterTerm}
                                                onChange={e => setFilterTerm(e.target.value)}
                                                placeholder="Filter by economic code or name (e.g. 22020, security, oil)"
                                                aria-label="Filter economic lines"
                                                style={{
                                                    ...inputStyle,
                                                    paddingLeft: 32,
                                                    fontSize: 12,
                                                }}
                                            />
                                        </div>
                                        <div style={{
                                            display: 'flex', justifyContent: 'space-between',
                                            alignItems: 'center', marginBottom: 8,
                                        }}>
                                            <button
                                                type="button"
                                                onClick={() => selectAll(true)}
                                                style={miniBtn}
                                                title={filterTerm.trim() ? 'Selects only the filtered lines' : 'Selects every line'}
                                            >
                                                Select all{filterTerm.trim() ? ' (filtered)' : ''}
                                            </button>
                                            <div style={{ fontSize: 11, color: '#64748b' }}>
                                                {(() => {
                                                    const q = filterTerm.trim().toLowerCase();
                                                    if (!q) return `${lines.length} line${lines.length === 1 ? '' : 's'}`;
                                                    const shown = lines.filter(l =>
                                                        l.economic_code.toLowerCase().includes(q)
                                                        || (l.economic_name || '').toLowerCase().includes(q),
                                                    ).length;
                                                    return `${shown} of ${lines.length} match`;
                                                })()}
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => selectAll(false)}
                                                style={miniBtn}
                                                title={filterTerm.trim() ? 'Clears only the filtered lines' : 'Clears every line'}
                                            >
                                                Clear all{filterTerm.trim() ? ' (filtered)' : ''}
                                            </button>
                                        </div>
                                        <div style={{
                                            border: '1px solid #e2e8f0', borderRadius: 8,
                                            overflow: 'hidden', overflowX: 'auto',
                                        }}>
                                            <table style={{
                                                width: '100%', borderCollapse: 'collapse',
                                                fontSize: 12,
                                            }}>
                                                <thead style={{ background: '#f8fafc' }}>
                                                    <tr>
                                                        <th style={tblTh} />
                                                        <th style={{ ...tblTh, textAlign: 'left' }}>Code</th>
                                                        <th style={{ ...tblTh, textAlign: 'left' }}>Economic Line</th>
                                                        <th style={{ ...tblTh, textAlign: 'right' }}>Available</th>
                                                        <th style={{ ...tblTh, textAlign: 'right' }}>Amount to release</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {(() => {
                                                        const q = filterTerm.trim().toLowerCase();
                                                        // Preserve original indices for handlers.
                                                        const visible = lines
                                                            .map((line, idx) => ({ line, idx }))
                                                            .filter(({ line }) => !q
                                                                || line.economic_code.toLowerCase().includes(q)
                                                                || (line.economic_name || '').toLowerCase().includes(q));
                                                        if (visible.length === 0) {
                                                            return (
                                                                <tr>
                                                                    <td colSpan={5} style={{ ...tblTd, textAlign: 'center', color: '#94a3b8', padding: '14px' }}>
                                                                        No economic lines match "{filterTerm}".
                                                                    </td>
                                                                </tr>
                                                            );
                                                        }
                                                        return visible.map(({ line: l, idx }) => {
                                                        const amt = parseFloat(l.amount_released) || 0;
                                                        const avail = parseFloat(l.available_balance) || 0;
                                                        const exceeds = l.selected && amt > avail;
                                                        return (
                                                            <tr
                                                                key={l.appropriation_id}
                                                                style={{
                                                                    background: l.selected ? '#f0fdf4' : 'white',
                                                                    borderTop: '1px solid #e2e8f0',
                                                                }}
                                                            >
                                                                <td style={tblTd}>
                                                                    <input
                                                                        type="checkbox"
                                                                        checked={l.selected}
                                                                        onChange={() => toggleLine(idx)}
                                                                    />
                                                                </td>
                                                                <td style={{ ...tblTd, fontFamily: 'monospace' }}>
                                                                    {l.economic_code}
                                                                </td>
                                                                <td style={tblTd}>{l.economic_name}</td>
                                                                <td style={{ ...tblTd, textAlign: 'right', fontFamily: 'monospace' }}>
                                                                    {fmtNGN(l.available_balance)}
                                                                </td>
                                                                <td style={tblTd}>
                                                                    <input
                                                                        type="number" step="0.01" min="0"
                                                                        value={l.amount_released}
                                                                        onChange={e => setLineAmount(idx, e.target.value)}
                                                                        disabled={!l.selected}
                                                                        placeholder="0.00"
                                                                        style={{
                                                                            ...inputStyle,
                                                                            textAlign: 'right',
                                                                            fontFamily: 'monospace',
                                                                            borderColor: exceeds ? '#ef4444' : undefined,
                                                                            background: l.selected ? 'white' : '#f1f5f9',
                                                                            opacity: l.selected ? 1 : 0.6,
                                                                        }}
                                                                    />
                                                                    {exceeds && (
                                                                        <div style={{ fontSize: 10, color: '#ef4444', marginTop: 2, textAlign: 'right' }}>
                                                                            Exceeds available
                                                                        </div>
                                                                    )}
                                                                </td>
                                                            </tr>
                                                        );
                                                        });
                                                    })()}
                                                </tbody>
                                                <tfoot style={{ background: '#0f172a', color: 'white' }}>
                                                    <tr>
                                                        <td style={tblTd} colSpan={4}>
                                                            <strong>{selectedLines.length}</strong> line{selectedLines.length === 1 ? '' : 's'} selected · Total this batch
                                                        </td>
                                                        <td style={{
                                                            ...tblTd, textAlign: 'right', fontFamily: 'monospace',
                                                            fontWeight: 700, fontSize: 13,
                                                        }}>
                                                            {fmtNGN(totalReleased)}
                                                        </td>
                                                    </tr>
                                                </tfoot>
                                            </table>
                                        </div>
                                    </>
                                )}
                            </div>

                            {/* Submit row */}
                            <div style={{ display: 'flex', gap: 10, justifyContent: 'space-between', alignItems: 'center' }}>
                                <button
                                    type="button"
                                    onClick={() => setPreviewOpen(p => !p)}
                                    style={{
                                        display: 'inline-flex', alignItems: 'center', gap: 6,
                                        padding: '8px 14px', borderRadius: 8,
                                        background: '#f1f5f9', border: '1px solid #cbd5e1',
                                        color: '#0f172a', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                                    }}
                                >
                                    {previewOpen ? <EyeOff size={13} /> : <Eye size={13} />}
                                    {previewOpen ? 'Hide preview' : 'Show preview'}
                                </button>
                                <div style={{ display: 'flex', gap: 10 }}>
                                    <button
                                        type="button"
                                        onClick={() => navigate(-1)}
                                        className="glass-button"
                                        style={{
                                            padding: '10px 20px', borderRadius: 8,
                                            border: '1px solid var(--color-border)',
                                            background: 'var(--color-surface)',
                                            color: 'var(--color-text)',
                                            fontSize: 13, fontWeight: 600, cursor: 'pointer',
                                        }}
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={
                                            bulkCreate.isPending ||
                                            selectedLines.length === 0 ||
                                            linesExceedingBalance.length > 0
                                        }
                                        style={{
                                            padding: '10px 22px', borderRadius: 8, border: 'none',
                                            background: (selectedLines.length === 0 || linesExceedingBalance.length > 0)
                                                ? '#94a3b8'
                                                : 'linear-gradient(135deg, #191e6a 0%, #0f1240 100%)',
                                            color: '#fff', fontSize: 13, fontWeight: 700,
                                            cursor: (selectedLines.length === 0 || linesExceedingBalance.length > 0)
                                                ? 'not-allowed' : 'pointer',
                                            display: 'flex', alignItems: 'center', gap: 6,
                                            opacity: bulkCreate.isPending ? 0.7 : 1,
                                            boxShadow: '0 4px 12px rgba(15, 18, 64, 0.25)',
                                        }}
                                    >
                                        <Save size={14} />
                                        {bulkCreate.isPending
                                            ? 'Creating…'
                                            : selectedLines.length > 1
                                                ? `Create ${selectedLines.length} Warrants (PENDING)`
                                                : 'Create Warrant (PENDING)'}
                                    </button>
                                </div>
                            </div>
                        </div>

                        {/* ════════════════════════════════════════════ *
                         *  RIGHT: Live print-style preview            *
                         * ════════════════════════════════════════════ */}
                        {previewOpen && (
                            <div style={{ minWidth: 0 }}>
                                <div style={{
                                    background: '#0f172a', color: 'white',
                                    padding: '8px 14px', borderRadius: '8px 8px 0 0',
                                    fontSize: 11, fontWeight: 700, letterSpacing: 0.4,
                                    textTransform: 'uppercase',
                                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                }}>
                                    <span>Print Preview · matches /print exactly</span>
                                    {!settings && <span style={{ fontWeight: 400, color: '#94a3b8' }}>loading settings…</span>}
                                </div>
                                <div style={{
                                    background: 'white',
                                    borderRadius: '0 0 8px 8px',
                                    boxShadow: '0 8px 32px rgba(15, 23, 42, 0.10)',
                                    overflow: 'hidden',
                                    position: 'sticky', top: 16,
                                    maxHeight: 'calc(100vh - 60px)',
                                    overflowY: 'auto',
                                }}>
                                    {settings ? (
                                        <WarrantPrintLayout
                                            settings={settings}
                                            warrant_number={previewWarrantNumber}
                                            effective_from={effectiveFrom}
                                            effective_to={effectiveTo}
                                            release_date={releaseDate}
                                            mda_name={selectedMdaName || 'designated MDA'}
                                            lines={previewLines.length ? previewLines : [{
                                                economic_code: '—',
                                                economic_name: 'Tick lines on the left to populate this preview',
                                                amount_released: '0',
                                            }]}
                                            mode="preview"
                                        />
                                    ) : (
                                        <div style={{ padding: 30, textAlign: 'center', color: '#64748b', fontSize: 13 }}>
                                            Loading print settings…
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </form>

                {/* Smart Create modal — passes the appropriations list
                    in so the modal doesn't have to refetch, and pre-
                    selects the MDA the user has already picked on the
                    form (if any) so switching to fast-path doesn't
                    lose context. */}
                <SmartCreateWarrantModal
                    open={smartCreateOpen}
                    onClose={() => setSmartCreateOpen(false)}
                    appropriations={(appropriations as any[]) || []}
                    initialMdaCode={selectedMdaCode}
                />
            </main>
        </div>
    );
}

// ─── Local style tokens ──────────────────────────────────────────────
const cardH3: React.CSSProperties = {
    fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)',
    margin: '0 0 0.75rem 0', display: 'flex', alignItems: 'center', gap: 6,
};
const cardHint: React.CSSProperties = {
    fontSize: 11, color: '#94a3b8', margin: '0 0 12px', lineHeight: 1.5,
};
const emptyHint: React.CSSProperties = {
    padding: '20px 12px', textAlign: 'center',
    color: '#94a3b8', fontSize: 12,
    border: '1px dashed #e2e8f0', borderRadius: 8,
};
const miniBtn: React.CSSProperties = {
    padding: '4px 10px', borderRadius: 6,
    border: '1px solid #cbd5e1', background: '#fff',
    color: '#1e293b', fontSize: 11, fontWeight: 600,
    cursor: 'pointer',
};
const tblTh: React.CSSProperties = {
    padding: '7px 10px', fontSize: 10, fontWeight: 700,
    letterSpacing: 0.5, textTransform: 'uppercase',
    color: '#475569', borderBottom: '1px solid #e2e8f0',
};
const tblTd: React.CSSProperties = {
    padding: '7px 10px', fontSize: 12, color: '#0f172a',
    verticalAlign: 'middle',
};
