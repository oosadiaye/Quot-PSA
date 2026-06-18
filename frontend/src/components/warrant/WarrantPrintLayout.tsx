/**
 * WarrantPrintLayout — single source of truth for the warrant
 * (AIE) document body. Used by both:
 *
 *   1. ``WarrantPrintPreview.tsx`` — the actual printout, full A4 page.
 *   2. ``WarrantForm.tsx``         — the live preview panel beside
 *                                    the create form so operators see
 *                                    exactly what will be printed
 *                                    before they submit.
 *
 * The two consumers differ only in chrome (toolbar, page background)
 * and in scale. The body — letterhead, title, lines table, signatures,
 * footer — is identical because they share this component. Any future
 * tweak to the printed layout therefore only needs to land here.
 *
 * The component intentionally accepts a *list* of lines, not a single
 * appropriation, so it can render either:
 *   • a one-line warrant (legacy / single appropriation), or
 *   • a multi-line composite warrant — N appropriations under one MDA
 *     released together for a single quarter.
 */
import React from 'react';
import BrandedPrintHeader from '../print/BrandedPrintHeader';

export interface WarrantPrintSettings {
    state_name?: string;
    ministry_of_finance_name?: string;
    office_address?: string;
    letterhead_logo_url: string | null;
    governor_name?: string;
    governor_title?: string;
    governor_signature_url: string | null;
    finance_commissioner_name?: string;
    finance_commissioner_title?: string;
    finance_commissioner_signature_url: string | null;
    accountant_general_name?: string;
    accountant_general_title?: string;
    accountant_general_signature_url: string | null;
    footer_notes?: string;
}

export interface WarrantPrintLine {
    /** Economic code (e.g. "21010101"). */
    economic_code?: string;
    /** Economic name (e.g. "Salaries — Permanent Staff"). */
    economic_name?: string;
    /** Amount released for this line, in NGN. Plain number or string. */
    amount_released: number | string;
    /** Approved amount on the underlying appropriation (annual). */
    appropriation_amount_approved?: number | string;
    /** Per-line note (optional). */
    notes?: string;
}

export interface WarrantPrintLayoutProps {
    settings: WarrantPrintSettings;
    /** "DTSG/AGW/2026/0084" or auto-generated reference. */
    warrant_number: string;
    /** Start of the warrant's effective window (ISO date string). */
    effective_from?: string;
    /** End of the effective window (ISO date string). */
    effective_to?: string;
    /**
     * Legacy quarter (1..4). Optional; only used when no date range
     * is provided so the layout still reads naturally for old data.
     */
    quarter?: number | string;
    /** Real-time status overlay (EXPIRED rendered as a watermark). */
    effective_status?: string;
    /** ISO date (YYYY-MM-DD) or display string. */
    release_date: string;
    /** Always required — the recipient ministry/agency. */
    mda_name: string;
    /** All appropriation lines being released (>= 1). */
    lines: WarrantPrintLine[];
    /** Free text under the lines table (optional). */
    body_notes?: string;
    /**
     * Render scale. ``preview`` shrinks fonts and signatures so the
     * panel fits next to the form; ``print`` is the full A4 layout.
     * Defaults to ``print``.
     */
    mode?: 'preview' | 'print';
}

const fmtNGN = (v: number | string | undefined): string => {
    const num = typeof v === 'string' ? parseFloat(v) : (v || 0);
    if (isNaN(num)) return '₦0.00';
    return '₦' + num.toLocaleString('en-NG', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
};

const fmtDate = (s: string | undefined): string => {
    if (!s) return '—';
    try {
        return new Date(s).toLocaleDateString('en-GB', {
            day: '2-digit', month: 'long', year: 'numeric',
        });
    } catch { return s; }
};

export default function WarrantPrintLayout({
    settings, warrant_number,
    effective_from, effective_to, quarter, effective_status,
    release_date, mda_name, lines, body_notes, mode = 'print',
}: WarrantPrintLayoutProps) {
    const isPreview = mode === 'preview';
    const totalAmount = lines.reduce((acc, l) => {
        const v = typeof l.amount_released === 'string'
            ? parseFloat(l.amount_released) : l.amount_released;
        return acc + (isNaN(v) ? 0 : v);
    }, 0);

    // Scale factors applied uniformly so a single source of truth
    // produces a tight preview and a comfortable print at the same time.
    const scale = isPreview ? 0.78 : 1;
    const f = (n: number) => Math.round(n * scale * 10) / 10;

    // ── Period label resolution. Prefers the explicit date range; if
    //    the caller only has a legacy quarter (e.g. when printing a
    //    historical warrant created before the date-range refactor)
    //    we render "Q1 — Q4" so the document still reads naturally.
    //    The annual case ("01 Jan 2026 → 31 Dec 2026") is the new
    //    default for every freshly-created warrant.
    const periodLabel = (() => {
        if (effective_from && effective_to) {
            return `${fmtDate(effective_from)} — ${fmtDate(effective_to)}`;
        }
        if (quarter) return `Q${quarter}`;
        return '';
    })();
    const isExpired = effective_status === 'EXPIRED';

    return (
        <div style={{
            background: 'white',
            padding: isPreview ? '18px 22px 22px' : '32px 40px 40px',
            fontFamily: "'Times New Roman', Georgia, serif",
            color: '#0f172a',
            position: 'relative',
        }}>
            {/* Real-time EXPIRED watermark — stamped diagonally across
                the page when the warrant's effective_to has elapsed.
                Renders behind the body so it doesn't break interactivity
                in the preview pane and prints to physical paper too. */}
            {isExpired && (
                <div aria-hidden="true" style={{
                    position: 'absolute', inset: 0,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    pointerEvents: 'none', zIndex: 1,
                }}>
                    <div style={{
                        transform: 'rotate(-22deg)',
                        fontSize: f(96), fontWeight: 800,
                        color: 'rgba(220, 38, 38, 0.18)',
                        letterSpacing: f(16),
                        textTransform: 'uppercase',
                        border: `${f(8)}px solid rgba(220, 38, 38, 0.18)`,
                        padding: `${f(8)}px ${f(28)}px`,
                        borderRadius: f(8),
                    }}>
                        EXPIRED
                    </div>
                </div>
            )}
            {/* ── Letterhead ─ same `BrandedPrintHeader` used by every
                printed document; ``letterhead_logo_url`` is the warrant-
                specific override. */}
            <BrandedPrintHeader
                logoOverrideUrl={settings.letterhead_logo_url}
                subtitle={settings.ministry_of_finance_name || 'Ministry of Finance'}
                compact={isPreview}
            />
            {settings.office_address && (
                <div style={{
                    textAlign: 'center', fontSize: f(11), color: '#475569',
                    marginTop: 4, fontStyle: 'italic',
                }}>
                    {settings.office_address}
                </div>
            )}

            {/* ── Title block ── */}
            <div style={{ margin: `${f(20)}px 0 ${f(14)}px`, textAlign: 'center', position: 'relative', zIndex: 2 }}>
                <div style={{
                    fontSize: f(18), fontWeight: 700,
                    textTransform: 'uppercase', letterSpacing: f(4),
                }}>
                    Authority to Incur Expenditure
                </div>
                <div style={{ fontSize: f(13), color: '#475569', marginTop: 4, letterSpacing: 1 }}>
                    Cash Release Warrant{periodLabel ? ` — ${periodLabel}` : ''}
                </div>
            </div>

            {/* ── Reference + date row ── */}
            <div style={{
                display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16,
                fontSize: f(12), marginBottom: f(16),
            }}>
                <div>
                    <div style={metaLabel(f)}>Warrant No.</div>
                    <div style={metaValue(f)}>{warrant_number}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                    <div style={metaLabel(f)}>Date of Release</div>
                    <div style={metaValue(f)}>{fmtDate(release_date)}</div>
                </div>
            </div>

            {/* ── Body — instruction paragraph ── */}
            <p style={{
                fontSize: f(13), lineHeight: 1.7,
                margin: `0 0 ${f(12)}px 0`, textAlign: 'justify',
                position: 'relative', zIndex: 2,
            }}>
                Pursuant to the appropriation enacted by the State House of
                Assembly for the financial year, authority is hereby granted
                to the {' '}<strong>{mda_name || 'designated MDA'}</strong>{' '}
                to incur expenditure against {lines.length === 1
                    ? 'the approved appropriation line'
                    : <><strong>{lines.length}</strong> approved appropriation lines</>}
                {' '}up to the amount{lines.length === 1 ? '' : 's'} specified
                below, effective {effective_from && effective_to
                    ? <>from <strong>{fmtDate(effective_from)}</strong> to <strong>{fmtDate(effective_to)}</strong></>
                    : quarter
                        ? <>for the quarter <strong>Q{quarter}</strong></>
                        : <>during the appropriation's fiscal year</>
                }.
            </p>

            {/* ── Lines table ── */}
            <table style={{
                width: '100%', borderCollapse: 'collapse',
                fontSize: f(12), marginBottom: f(14),
            }}>
                <thead>
                    <tr style={{ background: '#f1f5f9' }}>
                        <th style={th(f)}>Code</th>
                        <th style={{ ...th(f), textAlign: 'left' }}>Economic Line</th>
                        <th style={{ ...th(f), textAlign: 'right' }}>Approved (annual)</th>
                        <th style={{ ...th(f), textAlign: 'right' }}>Released (this warrant)</th>
                    </tr>
                </thead>
                <tbody>
                    {lines.map((l, idx) => (
                        <tr key={idx}>
                            <td style={td(f, true)}>{l.economic_code || '—'}</td>
                            <td style={td(f)}>{l.economic_name || '—'}</td>
                            <td style={tdAmount(f)}>
                                {fmtNGN(l.appropriation_amount_approved)}
                            </td>
                            <td style={{ ...tdAmount(f), fontWeight: 700 }}>
                                {fmtNGN(l.amount_released)}
                            </td>
                        </tr>
                    ))}
                    {lines.length > 1 && (
                        <tr style={{ background: '#0f172a', color: 'white' }}>
                            <td style={td(f)} colSpan={3}>
                                <strong>TOTAL CASH RELEASED — Q{quarter}</strong>
                            </td>
                            <td style={{ ...tdAmount(f), color: 'white', fontWeight: 700, fontSize: f(13) }}>
                                {fmtNGN(totalAmount)}
                            </td>
                        </tr>
                    )}
                </tbody>
            </table>

            {body_notes && (
                <div style={{
                    fontSize: f(11), color: '#475569',
                    background: '#f8fafc', padding: `${f(8)}px ${f(12)}px`,
                    border: '1px solid #e2e8f0', borderRadius: 6,
                    marginBottom: f(20), lineHeight: 1.5,
                }}>
                    <strong style={{ color: '#0f172a' }}>Notes: </strong>
                    {body_notes}
                </div>
            )}

            {/* ── Three signature blocks ── */}
            <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)',
                gap: f(20), marginTop: f(48), pageBreakInside: 'avoid',
            }}>
                <SignatureBlock f={f}
                    name={settings.governor_name}
                    title={settings.governor_title}
                    imageUrl={settings.governor_signature_url}
                />
                <SignatureBlock f={f}
                    name={settings.finance_commissioner_name}
                    title={settings.finance_commissioner_title}
                    imageUrl={settings.finance_commissioner_signature_url}
                />
                <SignatureBlock f={f}
                    name={settings.accountant_general_name}
                    title={settings.accountant_general_title}
                    imageUrl={settings.accountant_general_signature_url}
                />
            </div>

            {settings.footer_notes && (
                <div style={{
                    fontSize: f(9), color: '#94a3b8',
                    marginTop: f(28), paddingTop: 8,
                    borderTop: '1px solid #e2e8f0',
                    textAlign: 'center', letterSpacing: 0.5,
                }}>
                    {settings.footer_notes}
                </div>
            )}
        </div>
    );
}

function SignatureBlock({
    f, name, title, imageUrl,
}: {
    f: (n: number) => number;
    name?: string;
    title?: string;
    imageUrl: string | null;
}) {
    return (
        <div style={{
            textAlign: 'center', fontSize: f(11),
            display: 'flex', flexDirection: 'column', alignItems: 'center',
        }}>
            <div style={{
                height: f(50), marginBottom: 4,
                display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
                width: '100%',
            }}>
                {imageUrl && (
                    <img
                        src={imageUrl}
                        alt={`${name || 'signatory'} signature`}
                        style={{
                            maxHeight: f(50), maxWidth: '100%', objectFit: 'contain',
                        }}
                    />
                )}
            </div>
            <div style={{ width: '100%', borderTop: '1px solid #0f172a', paddingTop: 5 }}>
                <div style={{ fontSize: f(12), fontWeight: 700, lineHeight: 1.3 }}>
                    {name || '___________________'}
                </div>
                <div style={{ fontSize: f(10), color: '#475569', marginTop: 2, lineHeight: 1.4 }}>
                    {title || ''}
                </div>
            </div>
        </div>
    );
}

const metaLabel = (f: (n: number) => number): React.CSSProperties => ({
    fontSize: f(10), fontWeight: 700, letterSpacing: 1,
    textTransform: 'uppercase', color: '#64748b', marginBottom: 2,
});
const metaValue = (f: (n: number) => number): React.CSSProperties => ({
    fontSize: f(13), fontWeight: 700, color: '#0f172a',
    fontFamily: "'JetBrains Mono', monospace",
});
const th = (f: (n: number) => number): React.CSSProperties => ({
    padding: `${f(7)}px ${f(10)}px`, border: '1px solid #cbd5e1',
    fontSize: f(10), fontWeight: 700, letterSpacing: 0.6,
    textTransform: 'uppercase', color: '#475569', textAlign: 'center',
});
const td = (f: (n: number) => number, mono = false): React.CSSProperties => ({
    padding: `${f(7)}px ${f(10)}px`, border: '1px solid #cbd5e1',
    color: '#0f172a',
    fontFamily: mono ? "'JetBrains Mono', monospace" : 'inherit',
});
const tdAmount = (f: (n: number) => number): React.CSSProperties => ({
    padding: `${f(7)}px ${f(10)}px`, border: '1px solid #cbd5e1',
    textAlign: 'right',
    fontFamily: "'JetBrains Mono', monospace",
    fontVariantNumeric: 'tabular-nums',
});
