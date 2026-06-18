/**
 * SmartCreateWarrantModal — quick path for raising N warrants for one
 * MDA in a single sweep, optionally merged into a single printout.
 *
 * Why this exists alongside WarrantForm:
 *   • WarrantForm is the canonical, full-context create flow (lists
 *     every appropriation under an MDA with available balances).
 *   • Smart Create skips that walk and asks: "How many lines do you
 *     want?" — then drops a horizontal grid where the operator types
 *     amounts and picks economic codes. Faster for the common case
 *     where the AG already knows the numbers from a quarterly release
 *     letter and just needs to enter them.
 *
 * The "Batch" toggle controls *print grouping*, not DB shape:
 *   • ON  — the modal sets one shared ``authority_reference`` across
 *           every created warrant and routes the user to
 *           ``/budget/warrants/print-batch?ids=…`` so they print one
 *           composite document covering every line.
 *   • OFF — every line gets its own per-line authority reference and
 *           the user lands on the warrant list to print each separately.
 *
 * In both cases the underlying table writes look identical: one
 * Warrant row per (appropriation, quarter) — the schema invariant
 * ``unique_together = (appropriation, quarter)`` is preserved by
 * client-side guards that prevent duplicate appropriation picks.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    X, Sparkles, ArrowRight, ArrowLeft,
    Building2, AlertCircle, Save, Layers, Files,
} from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';

// ─── Types ──────────────────────────────────────────────────────────
interface Appropriation {
    id: number;
    administrative_code: string;
    administrative_name: string;
    economic_code: string;
    economic_name: string;
    available_balance: string;
    amount_approved: string;
    fiscal_year_display?: string;
    fiscal_year?: number | string;
    fiscal_year_start_date?: string;
    fiscal_year_end_date?: string;
}

interface SmartLine {
    /** Selected appropriation id, or '' if not chosen yet. */
    appropriation_id: string;
    amount_released: string;
    notes: string;
}

interface Props {
    open: boolean;
    onClose: () => void;
    appropriations: Appropriation[];
    /** Optional pre-selected MDA code passed in from the parent form. */
    initialMdaCode?: string;
}

const toIso = (d: Date) => d.toISOString().split('T')[0];

const fmtNGN = (v: number | string): string => {
    const num = typeof v === 'string' ? parseFloat(v) : v;
    if (isNaN(num)) return '₦0.00';
    return '₦' + num.toLocaleString('en-NG', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
};

// Cap to keep the horizontal grid readable. 12 lines covers the
// realistic upper bound for an MDA's quarterly release in one sitting.
const MAX_LINES = 12;

export default function SmartCreateWarrantModal({
    open, onClose, appropriations, initialMdaCode,
}: Props) {
    const navigate = useNavigate();
    const qc = useQueryClient();

    // ── Wizard step (1 = MDA + N + shared, 2 = horizontal grid) ──
    const [step, setStep] = useState<1 | 2>(1);

    // ── Step-1 state ─────────────────────────────────────────────
    const [mdaCode, setMdaCode] = useState('');
    const [count, setCount] = useState(3);
    // Date range replaces the legacy quarter dropdown. Defaults to
    // the chosen MDA's fiscal year span (the "annual" preset),
    // overridable from the date inputs or one-click presets.
    const [effectiveFrom, setEffectiveFrom] = useState('');
    const [effectiveTo, setEffectiveTo] = useState('');
    const [releaseDate, setReleaseDate] = useState(
        new Date().toISOString().split('T')[0],
    );
    const [batchMode, setBatchMode] = useState(true);

    // ── Step-2 state — N rows of {appropriation, amount, notes} ──
    const [lines, setLines] = useState<SmartLine[]>([]);

    const [submitError, setSubmitError] = useState('');

    // Reset state on (re)open and apply incoming MDA pre-selection.
    useEffect(() => {
        if (!open) return;
        setStep(1);
        setMdaCode(initialMdaCode || '');
        setCount(3);
        setEffectiveFrom('');
        setEffectiveTo('');
        setReleaseDate(new Date().toISOString().split('T')[0]);
        setBatchMode(true);
        setLines([]);
        setSubmitError('');
    }, [open, initialMdaCode]);

    // ── Derived: MDA list (deduped, only those with appropriations) ──
    const mdas = useMemo(() => {
        const seen = new Map<string, { code: string; name: string }>();
        for (const a of appropriations) {
            const key = a.administrative_code || '';
            if (key && !seen.has(key)) {
                seen.set(key, { code: key, name: a.administrative_name || '' });
            }
        }
        return [...seen.values()].sort((a, b) => a.code.localeCompare(b.code));
    }, [appropriations]);

    // ── Derived: appropriations belonging to the chosen MDA ──
    const apprsForMda = useMemo(
        () => appropriations.filter(a => a.administrative_code === mdaCode),
        [appropriations, mdaCode],
    );

    // ── Fiscal-year bounds for the chosen MDA — used to seed the
    //    "annual" default and the quarter-equivalent presets.
    const fyBounds = useMemo<[Date, Date]>(() => {
        if (apprsForMda.length) {
            const a = apprsForMda[0];
            if (a.fiscal_year_start_date && a.fiscal_year_end_date) {
                return [new Date(a.fiscal_year_start_date), new Date(a.fiscal_year_end_date)];
            }
        }
        const yr = parseInt(String(apprsForMda[0]?.fiscal_year || ''), 10)
            || new Date().getFullYear();
        return [new Date(yr, 0, 1), new Date(yr, 11, 31)];
    }, [apprsForMda]);

    // Seed the date range with the FY span the first time an MDA is
    // picked. Manual edits persist; switching MDAs reseeds because
    // the FY can differ between MDAs.
    useEffect(() => {
        if (!mdaCode) return;
        const [s, e] = fyBounds;
        setEffectiveFrom(toIso(s));
        setEffectiveTo(toIso(e));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [mdaCode]);

    // ── Build the N rows when stepping into step 2 ──
    const goToStep2 = () => {
        if (!mdaCode) {
            setSubmitError('Pick an MDA.');
            return;
        }
        if (!effectiveFrom || !effectiveTo) {
            setSubmitError('Set the effective date range.');
            return;
        }
        if (new Date(effectiveTo) < new Date(effectiveFrom)) {
            setSubmitError('Effective "to" cannot be earlier than "from".');
            return;
        }
        if (count < 1) {
            setSubmitError('Number of warrants must be at least 1.');
            return;
        }
        if (count > apprsForMda.length) {
            setSubmitError(
                `This MDA only has ${apprsForMda.length} budget line${apprsForMda.length === 1 ? '' : 's'}; cannot create ${count} warrants (would force duplicate appropriations).`,
            );
            return;
        }
        setSubmitError('');
        setLines(Array.from({ length: count }, () => ({
            appropriation_id: '', amount_released: '', notes: '',
        })));
        setStep(2);
    };

    // ── Per-row mutators ─────────────────────────────────────────
    const setLine = (idx: number, patch: Partial<SmartLine>) =>
        setLines(prev => prev.map((l, i) => i === idx ? { ...l, ...patch } : l));

    // When the user picks an appropriation in a row, auto-fill amount
    // with the available balance (matches WarrantForm's one-click default).
    const pickAppropriation = (idx: number, value: string) => {
        const apr = apprsForMda.find(a => String(a.id) === value);
        setLine(idx, {
            appropriation_id: value,
            amount_released: apr && !lines[idx].amount_released
                ? apr.available_balance : lines[idx].amount_released,
        });
    };

    // ── Validation: detect duplicate appropriation picks. The schema
    //    rejects (appropriation, quarter) duplicates; surface this in
    //    the UI before the round-trip. Returns a Set of duplicate IDs.
    const duplicateIds = useMemo(() => {
        const counts = new Map<string, number>();
        for (const l of lines) {
            if (!l.appropriation_id) continue;
            counts.set(l.appropriation_id, (counts.get(l.appropriation_id) || 0) + 1);
        }
        return new Set(
            [...counts.entries()].filter(([, c]) => c > 1).map(([id]) => id),
        );
    }, [lines]);

    const totalAmount = useMemo(
        () => lines.reduce((acc, l) => acc + (parseFloat(l.amount_released) || 0), 0),
        [lines],
    );

    // ── Submit ────────────────────────────────────────────────────
    const fy = apprsForMda[0]?.fiscal_year_display
        || apprsForMda[0]?.fiscal_year || '';

    /**
     * Build the per-line ``authority_reference``. In batch mode we use
     * a single shared reference across every row so the print-batch
     * page can group them; in non-batch mode each row gets a distinct
     * reference appended with the economic code so the warrant list
     * keeps them separable.
     */
    const buildAuthorityReference = (line: SmartLine, sharedRef: string) => {
        if (batchMode) return sharedRef;
        const apr = apprsForMda.find(a => String(a.id) === line.appropriation_id);
        return `${sharedRef}/${apr?.economic_code || ''}`;
    };

    const bulkCreate = useMutation({
        mutationFn: async () => {
            // Shared reference now leans on the effective_from year
            // tag (no more quarter): "AIE/<FY>/<MDA>/<from>-<to>".
            // In batch mode this is the *whole* reference for every
            // row; in separate mode we append the economic code per
            // line so the warrant list keeps them distinct.
            const sharedRef = `AIE/${fy}/${mdaCode}/${effectiveFrom}-${effectiveTo}`;
            const payload = {
                effective_from: effectiveFrom,
                effective_to: effectiveTo,
                release_date: releaseDate,
                lines: lines
                    .filter(l => l.appropriation_id && parseFloat(l.amount_released) > 0)
                    .map(l => ({
                        appropriation: parseInt(l.appropriation_id, 10),
                        amount_released: l.amount_released,
                        authority_reference: buildAuthorityReference(l, sharedRef),
                        notes: l.notes,
                    })),
            };
            const { data } = await apiClient.post(
                '/budget/warrants/bulk_create/', payload,
            );
            return data as { created: { id: number }[]; count: number };
        },
        onSuccess: data => {
            qc.invalidateQueries({ queryKey: ['generic-list'] });
            qc.invalidateQueries({ queryKey: ['appropriations-dropdown'] });
            const ids = data.created.map(w => w.id).join(',');
            onClose();
            // Batch ON → composite print page; OFF → list (operator
            // prints each separately from the row actions).
            if (batchMode && ids) {
                navigate(`/budget/warrants/print-batch?ids=${ids}`);
            } else {
                navigate('/budget/warrants');
            }
        },
    });

    const handleSubmit = async () => {
        setSubmitError('');
        if (duplicateIds.size > 0) {
            setSubmitError('Two rows reference the same economic code. Each line must be a distinct appropriation.');
            return;
        }
        const filled = lines.filter(
            l => l.appropriation_id && parseFloat(l.amount_released) > 0,
        );
        if (filled.length === 0) {
            setSubmitError('Fill at least one row with an economic code and amount.');
            return;
        }
        // Per-row exceeds-balance guard.
        for (const l of filled) {
            const apr = apprsForMda.find(a => String(a.id) === l.appropriation_id);
            const avail = parseFloat(apr?.available_balance || '0');
            const amt = parseFloat(l.amount_released);
            if (amt > avail) {
                setSubmitError(
                    `Line on ${apr?.economic_code} exceeds available balance (${fmtNGN(avail)}).`,
                );
                return;
            }
        }
        try {
            await bulkCreate.mutateAsync();
        } catch (err: any) {
            const d = err.response?.data;
            if (d?.lines) {
                const msgs = d.lines.map((row: any) =>
                    `Row ${row.line + 1}: ${JSON.stringify(row.errors)}`,
                );
                setSubmitError(msgs.join(' · '));
            } else if (d?.error) {
                setSubmitError(d.error);
            } else {
                setSubmitError(err.message || 'Failed to create warrants');
            }
        }
    };

    if (!open) return null;

    return (
        <div
            role="dialog" aria-modal="true" aria-label="Smart Create Warrants"
            onClick={onClose}
            style={backdrop}
        >
            {/* Local keyframe definition. Previously the modal referenced
                ``pdf-modal-in`` from PdfPreviewModal — it worked only when
                that modal had been opened earlier in the session and its
                <style> block was still mounted. Inlining a matching
                keyframe here makes the fade-in effect deterministic. */}
            <style>{`
                @keyframes smart-modal-in {
                    from { opacity: 0; }
                    to   { opacity: 1; }
                }
            `}</style>
            <div onClick={e => e.stopPropagation()} style={shell}>
                {/* Header */}
                <div style={header}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={iconBadge}>
                            <Sparkles size={16} color="white" />
                        </div>
                        <div>
                            <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>
                                Smart Create Warrants
                            </div>
                            <div style={{ fontSize: 11, color: '#64748b', marginTop: 1 }}>
                                Step {step} of 2 · {step === 1 ? 'MDA + batch settings' : 'Per-line details'}
                            </div>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        aria-label="Close"
                        style={closeBtn}
                    >
                        <X size={16} />
                    </button>
                </div>

                {/* Body */}
                <div style={body}>
                    {submitError && (
                        <div style={errBanner}>
                            <AlertCircle size={14} style={{ marginTop: 1, flexShrink: 0 }} />
                            <div>{submitError}</div>
                        </div>
                    )}

                    {step === 1 && (
                        <Step1
                            mdaCode={mdaCode} setMdaCode={setMdaCode}
                            mdas={mdas}
                            count={count} setCount={c => setCount(Math.max(1, Math.min(MAX_LINES, c)))}
                            effectiveFrom={effectiveFrom} setEffectiveFrom={setEffectiveFrom}
                            effectiveTo={effectiveTo} setEffectiveTo={setEffectiveTo}
                            releaseDate={releaseDate} setReleaseDate={setReleaseDate}
                            batchMode={batchMode} setBatchMode={setBatchMode}
                            apprsForMda={apprsForMda}
                            fyBounds={fyBounds}
                        />
                    )}

                    {step === 2 && (
                        <Step2
                            lines={lines}
                            apprsForMda={apprsForMda}
                            duplicateIds={duplicateIds}
                            onPickAppropriation={pickAppropriation}
                            onSetLine={setLine}
                            totalAmount={totalAmount}
                            batchMode={batchMode}
                        />
                    )}
                </div>

                {/* Footer */}
                <div style={footer}>
                    {step === 2 ? (
                        <button
                            type="button"
                            onClick={() => setStep(1)}
                            style={btnGhost}
                        >
                            <ArrowLeft size={13} /> Back
                        </button>
                    ) : <span />}

                    {step === 1 ? (
                        <button
                            type="button"
                            onClick={goToStep2}
                            style={btnPrimary}
                        >
                            Next: enter line details <ArrowRight size={13} />
                        </button>
                    ) : (
                        <button
                            type="button"
                            onClick={handleSubmit}
                            disabled={bulkCreate.isPending}
                            style={{
                                ...btnPrimary,
                                opacity: bulkCreate.isPending ? 0.7 : 1,
                                cursor: bulkCreate.isPending ? 'progress' : 'pointer',
                            }}
                        >
                            <Save size={13} />
                            {bulkCreate.isPending
                                ? 'Creating…'
                                : batchMode
                                    ? `Create batch (${lines.filter(l => l.appropriation_id).length} lines → 1 printout)`
                                    : `Create ${lines.filter(l => l.appropriation_id).length} separate warrants`}
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}

// ════════════════════════════════════════════════════════════════════
// Step 1 — MDA, count, date range, batch toggle
// ════════════════════════════════════════════════════════════════════
interface Step1Props {
    mdaCode: string;
    setMdaCode: (v: string) => void;
    mdas: { code: string; name: string }[];
    count: number;
    setCount: (n: number) => void;
    effectiveFrom: string;
    setEffectiveFrom: (d: string) => void;
    effectiveTo: string;
    setEffectiveTo: (d: string) => void;
    releaseDate: string;
    setReleaseDate: (d: string) => void;
    batchMode: boolean;
    setBatchMode: (b: boolean) => void;
    apprsForMda: Appropriation[];
    fyBounds: [Date, Date];
}

/**
 * Period preset buttons mirror the WarrantForm presets — annual is
 * the default, quarterly shortcuts are surfaced for operators used
 * to the legacy cadence. Bounds are derived from the chosen MDA's
 * fiscal year so the picks stay correct even on non-calendar FYs.
 */
const buildPresets = (fyStart: Date, fyEnd: Date) => {
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

function Step1({
    mdaCode, setMdaCode, mdas, count, setCount,
    effectiveFrom, setEffectiveFrom,
    effectiveTo, setEffectiveTo,
    releaseDate, setReleaseDate,
    batchMode, setBatchMode, apprsForMda, fyBounds,
}: Step1Props) {
    return (
        <div style={{ display: 'grid', gap: 14 }}>
            {/* Batch toggle — front and centre because it changes the
                meaning of "create" later. */}
            <div style={{
                background: batchMode
                    ? 'linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%)'
                    : '#f8fafc',
                border: `2px solid ${batchMode ? '#6366f1' : '#e2e8f0'}`,
                borderRadius: 12, padding: 14,
                display: 'flex', alignItems: 'center', gap: 14,
                transition: 'background 200ms',
            }}>
                <div style={{
                    background: batchMode ? '#6366f1' : '#cbd5e1',
                    color: 'white', borderRadius: 8,
                    width: 38, height: 38,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                    {batchMode ? <Layers size={18} /> : <Files size={18} />}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>
                        {batchMode ? 'Batch mode — merged printout' : 'Separate mode — individual printouts'}
                    </div>
                    <div style={{ fontSize: 11, color: '#475569', marginTop: 2, lineHeight: 1.45 }}>
                        {batchMode
                            ? 'All lines share one Authority Reference and print as a single composite warrant document for this MDA.'
                            : 'Each line gets its own Authority Reference and prints as a separate warrant from the list.'}
                    </div>
                </div>
                {/* Switch */}
                <button
                    type="button"
                    role="switch"
                    aria-checked={batchMode}
                    onClick={() => setBatchMode(!batchMode)}
                    style={{
                        width: 50, height: 28, borderRadius: 14,
                        border: 'none', cursor: 'pointer',
                        background: batchMode ? '#6366f1' : '#cbd5e1',
                        position: 'relative',
                        transition: 'background 200ms',
                        flexShrink: 0,
                    }}
                >
                    <span style={{
                        position: 'absolute',
                        top: 3, left: batchMode ? 25 : 3,
                        width: 22, height: 22, borderRadius: '50%',
                        background: 'white',
                        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.25)',
                        transition: 'left 200ms',
                    }} />
                </button>
            </div>

            {/* MDA picker */}
            <div>
                <label style={lbl}>
                    <Building2 size={11} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                    MDA *
                </label>
                <select
                    style={input}
                    value={mdaCode}
                    onChange={e => setMdaCode(e.target.value)}
                >
                    <option value="">Pick the MDA being warranted…</option>
                    {mdas.map(m => (
                        <option key={m.code} value={m.code}>
                            {m.code} — {m.name}
                        </option>
                    ))}
                </select>
                {mdaCode && (
                    <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
                        {apprsForMda.length} budget line{apprsForMda.length === 1 ? '' : 's'} available on this MDA
                    </div>
                )}
            </div>

            {/* Count + date range + release date — replaces the legacy
                quarter dropdown. Date defaults seed from the chosen
                MDA's fiscal year (annual). Quick-preset chips let
                operators jump to a quarter span in one click. */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12 }}>
                <div>
                    <label style={lbl}>Number of warrants *</label>
                    <input
                        type="number"
                        min={1}
                        max={Math.max(1, Math.min(MAX_LINES, apprsForMda.length || MAX_LINES))}
                        value={count}
                        onChange={e => setCount(parseInt(e.target.value, 10) || 1)}
                        style={input}
                    />
                    <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 3 }}>
                        Max {Math.min(MAX_LINES, apprsForMda.length || MAX_LINES)}
                    </div>
                </div>
                <div>
                    <label style={lbl}>Effective from *</label>
                    <input
                        type="date"
                        style={input}
                        value={effectiveFrom}
                        onChange={e => setEffectiveFrom(e.target.value)}
                    />
                </div>
                <div>
                    <label style={lbl}>Effective to *</label>
                    <input
                        type="date"
                        style={{
                            ...input,
                            borderColor:
                                effectiveFrom && effectiveTo &&
                                new Date(effectiveTo) < new Date(effectiveFrom)
                                    ? '#ef4444' : undefined,
                        }}
                        value={effectiveTo}
                        onChange={e => setEffectiveTo(e.target.value)}
                    />
                </div>
                <div>
                    <label style={lbl}>Release date *</label>
                    <input
                        type="date"
                        style={input}
                        value={releaseDate}
                        onChange={e => setReleaseDate(e.target.value)}
                    />
                </div>
            </div>

            {/* Quick presets row */}
            <div>
                <label style={lbl}>Quick presets</label>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {buildPresets(fyBounds[0], fyBounds[1]).map(p => {
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
                                    fontSize: 11, fontWeight: 600, cursor: 'pointer',
                                }}
                            >
                                {p.label}
                            </button>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}

// ════════════════════════════════════════════════════════════════════
// Step 2 — Horizontal grid of N rows, one per warrant
// ════════════════════════════════════════════════════════════════════
interface Step2Props {
    lines: SmartLine[];
    apprsForMda: Appropriation[];
    duplicateIds: Set<string>;
    onPickAppropriation: (idx: number, value: string) => void;
    onSetLine: (idx: number, patch: Partial<SmartLine>) => void;
    totalAmount: number;
    batchMode: boolean;
}

function Step2({
    lines, apprsForMda, duplicateIds,
    onPickAppropriation, onSetLine, totalAmount, batchMode,
}: Step2Props) {
    return (
        <div>
            <div style={{
                fontSize: 11, color: '#64748b', marginBottom: 10, lineHeight: 1.5,
            }}>
                {batchMode
                    ? 'Each row becomes a Warrant row in the database; all of them share one Authority Reference and one printout document.'
                    : 'Each row becomes its own Warrant — own reference, own printout. Use the warrant list to print each one.'}
            </div>

            <div style={{
                border: '1px solid #e2e8f0', borderRadius: 8,
                overflow: 'hidden', overflowX: 'auto',
            }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                    <thead style={{ background: '#f8fafc' }}>
                        <tr>
                            <th style={th}>#</th>
                            <th style={{ ...th, textAlign: 'left', minWidth: 280 }}>Economic code</th>
                            <th style={{ ...th, textAlign: 'right', minWidth: 130 }}>Available</th>
                            <th style={{ ...th, textAlign: 'right', minWidth: 160 }}>Amount released</th>
                            <th style={{ ...th, textAlign: 'left', minWidth: 200 }}>Notes</th>
                        </tr>
                    </thead>
                    <tbody>
                        {lines.map((l, idx) => {
                            const apr = apprsForMda.find(a => String(a.id) === l.appropriation_id);
                            const avail = parseFloat(apr?.available_balance || '0');
                            const amt = parseFloat(l.amount_released) || 0;
                            const exceeds = !!apr && amt > avail;
                            const dup = duplicateIds.has(l.appropriation_id);
                            return (
                                <tr key={idx} style={{
                                    borderTop: '1px solid #e2e8f0',
                                    background: dup ? '#fef2f2' : 'white',
                                }}>
                                    <td style={{ ...td, fontWeight: 700, color: '#475569' }}>
                                        {idx + 1}
                                    </td>
                                    <td style={td}>
                                        <select
                                            value={l.appropriation_id}
                                            onChange={e => onPickAppropriation(idx, e.target.value)}
                                            style={{
                                                ...input,
                                                borderColor: dup ? '#ef4444' : undefined,
                                            }}
                                        >
                                            <option value="">Pick economic code…</option>
                                            {apprsForMda.map(a => (
                                                <option key={a.id} value={String(a.id)}>
                                                    {a.economic_code} — {a.economic_name}
                                                </option>
                                            ))}
                                        </select>
                                        {dup && (
                                            <div style={{ fontSize: 10, color: '#dc2626', marginTop: 3 }}>
                                                Duplicate — pick a different code
                                            </div>
                                        )}
                                    </td>
                                    <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace', color: '#475569' }}>
                                        {apr ? fmtNGN(apr.available_balance) : '—'}
                                    </td>
                                    <td style={td}>
                                        <input
                                            type="number" step="0.01" min="0"
                                            value={l.amount_released}
                                            onChange={e => onSetLine(idx, { amount_released: e.target.value })}
                                            placeholder="0.00"
                                            disabled={!l.appropriation_id}
                                            style={{
                                                ...input,
                                                textAlign: 'right',
                                                fontFamily: 'monospace',
                                                borderColor: exceeds ? '#ef4444' : undefined,
                                                background: l.appropriation_id ? 'white' : '#f1f5f9',
                                            }}
                                        />
                                        {exceeds && (
                                            <div style={{ fontSize: 10, color: '#ef4444', marginTop: 3, textAlign: 'right' }}>
                                                Exceeds available
                                            </div>
                                        )}
                                    </td>
                                    <td style={td}>
                                        <input
                                            type="text"
                                            value={l.notes}
                                            onChange={e => onSetLine(idx, { notes: e.target.value })}
                                            placeholder="optional"
                                            style={input}
                                        />
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                    <tfoot style={{ background: '#0f172a', color: 'white' }}>
                        <tr>
                            <td style={td} colSpan={3}>
                                <strong>{lines.filter(l => l.appropriation_id).length}</strong>
                                {' '}of {lines.length} rows filled
                            </td>
                            <td style={{
                                ...td, textAlign: 'right',
                                fontFamily: 'monospace', fontWeight: 700, fontSize: 13,
                            }}>
                                {fmtNGN(totalAmount)}
                            </td>
                            <td style={td} />
                        </tr>
                    </tfoot>
                </table>
            </div>
        </div>
    );
}

// ─── Inline styles ─────────────────────────────────────────────────
const backdrop: React.CSSProperties = {
    position: 'fixed', inset: 0, zIndex: 1200,
    background: 'rgba(15, 23, 42, 0.6)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: 24, animation: 'smart-modal-in 120ms ease-out',
};
const shell: React.CSSProperties = {
    background: 'white', borderRadius: 12,
    width: '100%', maxWidth: 1100,
    maxHeight: 'calc(100vh - 48px)',
    display: 'flex', flexDirection: 'column',
    boxShadow: '0 24px 64px rgba(15, 23, 42, 0.35)',
    overflow: 'hidden',
};
const header: React.CSSProperties = {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '14px 18px', borderBottom: '1px solid #e2e8f0',
    flexShrink: 0,
};
const iconBadge: React.CSSProperties = {
    width: 32, height: 32, borderRadius: 8,
    background: 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
};
const closeBtn: React.CSSProperties = {
    width: 32, height: 32, borderRadius: 8,
    background: '#f1f5f9', border: '1px solid #cbd5e1',
    cursor: 'pointer', color: '#1e293b',
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
};
const body: React.CSSProperties = {
    padding: 18, overflowY: 'auto', flex: 1,
};
const footer: React.CSSProperties = {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '12px 18px', borderTop: '1px solid #e2e8f0',
    background: '#f8fafc', flexShrink: 0, gap: 10,
};
const lbl: React.CSSProperties = {
    display: 'block', fontSize: 11, fontWeight: 700,
    color: '#475569', textTransform: 'uppercase',
    letterSpacing: 0.5, marginBottom: 5,
};
const input: React.CSSProperties = {
    width: '100%', padding: '7px 10px', borderRadius: 6,
    border: '1.5px solid #cbd5e1', background: 'white',
    color: '#0f172a', fontSize: 12, fontFamily: 'inherit',
    outline: 'none', boxSizing: 'border-box',
};
const th: React.CSSProperties = {
    padding: '8px 10px', fontSize: 10,
    fontWeight: 700, letterSpacing: 0.5,
    textTransform: 'uppercase', color: '#475569',
    borderBottom: '1px solid #e2e8f0', textAlign: 'center',
};
const td: React.CSSProperties = {
    padding: '8px 10px', fontSize: 12,
    color: '#0f172a', verticalAlign: 'middle',
};
const errBanner: React.CSSProperties = {
    padding: '10px 14px', borderRadius: 8, marginBottom: 14,
    background: '#fef2f2', border: '1px solid #fecaca',
    color: '#dc2626', display: 'flex', alignItems: 'flex-start',
    gap: 8, fontSize: 12,
};
const btnPrimary: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: '9px 16px', borderRadius: 8, border: 'none',
    background: 'linear-gradient(135deg, #4f46e5 0%, #4338ca 100%)',
    color: 'white', fontSize: 13, fontWeight: 700,
    cursor: 'pointer',
    boxShadow: '0 4px 12px rgba(79, 70, 229, 0.3)',
};
const btnGhost: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: '9px 14px', borderRadius: 8,
    background: 'white', border: '1px solid #cbd5e1',
    color: '#1e293b', fontSize: 13, fontWeight: 600,
    cursor: 'pointer',
};
