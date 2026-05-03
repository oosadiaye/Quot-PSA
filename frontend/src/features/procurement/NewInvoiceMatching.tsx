/**
 * Invoice Verification — SAP MIRO-style single-page workflow.
 *
 * Flow:
 *   1. Pick PO (and GRN) → page auto-loads PO/GRN data + prefills amounts
 *   2. Adjust the supplier-billed amounts (most of the time = no change)
 *   3. Live 3-way match badge updates as user types (no Save needed)
 *   4. Single "Post Invoice" button does everything atomically:
 *        create matching → calculate match → post GL journal → close commitment
 *   5. If partial receipt → modal asks user to confirm before posting
 *   6. If variance > 5% → backend returns 400, page prompts for reason, retries
 *
 * Replaces the previous stepped wizard which forced the user through three
 * navigation phases (entry → review → complete) and was getting stuck at
 * Pending_Review when the workflow gate kicked in. Single-button post is
 * the SAP MIRO approach: enter, validate, post — all in one keystroke chain.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    ArrowLeft, AlertTriangle, BookOpen, Building2, Calculator, CheckCircle,
    ChevronDown, ChevronUp, ClipboardList, CreditCard, FileText, Minus,
    Package, Sparkles, X, XCircle,
} from 'lucide-react';
import {
    usePurchaseOrders, useGRNs, usePurchaseOrder, useGRN,
    useDownPaymentForPO, useVerifyAndPost, useSimulateInvoice,
    useInvoiceMatchings,
    type SimulationResult,
} from './hooks/useProcurement';
import { useMDAs } from '../accounting/hooks/useBudgetDimensions';
import { useTaxCodes, useWithholdingTaxes } from '../accounting/hooks/useAccountingEnhancements';
import { useDialog } from '../../hooks/useDialog';
import { useCurrency } from '../../context/CurrencyContext';
import AccountingLayout from '../accounting/AccountingLayout';
import SearchableSelect from '../../components/SearchableSelect';
import '../accounting/styles/glassmorphism.css';

// ─── Style constants (kept inline to avoid a new file for one screen) ──────

const inp: React.CSSProperties = {
    width: '100%', padding: '0.45rem 0.6rem', borderRadius: '6px',
    border: '1px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-sm)',
};
const lbl: React.CSSProperties = {
    display: 'block', fontSize: '0.65rem', fontWeight: 600,
    color: 'var(--color-text-muted)', marginBottom: '0.28rem',
    textTransform: 'uppercase' as const, letterSpacing: '0.04em',
};
const card: React.CSSProperties = {
    background: 'var(--color-surface)', border: '1px solid var(--color-border)',
    borderRadius: '10px', padding: '1.1rem', marginBottom: '1rem',
};
const sectionTitle: React.CSSProperties = {
    fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-text)',
    margin: '0 0 0.875rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem',
};
const th: React.CSSProperties = {
    padding: '0.5rem 0.75rem', fontSize: '0.65rem', fontWeight: 700,
    color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em',
    textAlign: 'left' as const, background: 'rgba(0,0,0,0.03)', whiteSpace: 'nowrap' as const,
};
const td: React.CSSProperties = {
    padding: '0.5rem 0.75rem', fontSize: 'var(--text-sm)',
    borderTop: '1px solid var(--color-border)',
};

// Variance threshold mirrors the backend's PROCUREMENT_SETTINGS value.
const VARIANCE_THRESHOLD_PCT = 5.0;

// ─── Tiny inline components ────────────────────────────────────────────────

function VariancePill({ base, actual }: { base: number; actual: number }) {
    if (!base || !actual) return <span style={{ color: 'var(--color-text-muted)' }}>—</span>;
    const diff = actual - base;
    const pct = ((diff / base) * 100);
    const ok = Math.abs(diff) < 0.01;
    const over = diff > 0;
    const color = ok ? '#22c55e' : over ? '#ef4444' : '#f59e0b';
    const bg = ok ? 'rgba(34,197,94,0.1)' : over ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)';
    return (
        <span style={{ padding: '0.15rem 0.5rem', borderRadius: '9999px', background: bg, color, fontWeight: 600, fontSize: '0.7rem', whiteSpace: 'nowrap' }}>
            {ok ? '✓ Match' : `${over ? '+' : ''}${pct.toFixed(1)}%`}
        </span>
    );
}

interface MatchBadgeProps {
    poTotal: number | null;
    grnTotal: number | null;
    invoiceAmt: number | null;
}
/**
 * Live three-way-match badge. Computed client-side so the user sees the
 * verdict update as they type — same formula the backend uses, so the
 * calculated match status displayed here matches what `verify_and_post`
 * will record on the matching record.
 */
function LiveMatchBadge({ poTotal, grnTotal, invoiceAmt }: MatchBadgeProps) {
    if (!invoiceAmt || (!poTotal && !grnTotal)) return null;
    const base = grnTotal ?? poTotal ?? 0;
    const variance = invoiceAmt - base;
    const pct = base > 0 ? Math.abs(variance / base) * 100 : 0;
    const exact = Math.abs(variance) < 0.01;
    const within = pct <= VARIANCE_THRESHOLD_PCT;
    let label: string;
    let bg: string;
    let color: string;
    let icon: React.ReactNode;
    if (exact) {
        label = 'Full 3-way Match';
        bg = '#dcfce7'; color = '#15803d'; icon = <CheckCircle size={14} />;
    } else if (within) {
        label = `Within Tolerance (${pct.toFixed(2)}%)`;
        bg = '#ecfdf5'; color = '#059669'; icon = <CheckCircle size={14} />;
    } else {
        label = `Variance ${pct.toFixed(2)}% — Above 5% Threshold`;
        bg = '#fef2f2'; color = '#b91c1c'; icon = <AlertTriangle size={14} />;
    }
    return (
        <div style={{
            display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
            padding: '0.35rem 0.7rem', borderRadius: '999px',
            background: bg, color, fontSize: 'var(--text-xs)', fontWeight: 700,
            border: `1px solid ${color}40`,
        }}>
            {icon}
            {label}
        </div>
    );
}

interface ConfirmModalProps {
    title: string;
    body: React.ReactNode;
    confirmLabel: string;
    confirmColor: string;
    onConfirm: () => void;
    onCancel: () => void;
    extraInput?: { label: string; value: string; onChange: (v: string) => void; placeholder?: string };
}
/**
 * Lightweight blocking modal — used for both the partial-receipt
 * acknowledgement and the variance-reason override. Shares the same
 * shell so the visual language stays consistent regardless of which
 * gate the backend triggered.
 */
function ConfirmModal({ title, body, confirmLabel, confirmColor, onConfirm, onCancel, extraInput }: ConfirmModalProps) {
    return (
        <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(15,23,42,0.5)', display: 'flex',
            alignItems: 'center', justifyContent: 'center', zIndex: 9999,
            padding: '1rem',
        }} onClick={onCancel}>
            <div style={{
                background: 'var(--color-surface)', borderRadius: '12px',
                padding: '1.5rem', maxWidth: '480px', width: '100%',
                boxShadow: '0 20px 50px rgba(0,0,0,0.25)',
            }} onClick={e => e.stopPropagation()}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                    <h3 style={{ margin: 0, fontSize: 'var(--text-base)', fontWeight: 700 }}>{title}</h3>
                    <button onClick={onCancel} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                        <X size={18} />
                    </button>
                </div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text)', lineHeight: 1.55, marginBottom: '1.1rem' }}>
                    {body}
                </div>
                {extraInput && (
                    <div style={{ marginBottom: '1.1rem' }}>
                        <label style={lbl}>{extraInput.label}</label>
                        <input
                            type="text" style={inp}
                            value={extraInput.value}
                            placeholder={extraInput.placeholder}
                            onChange={e => extraInput.onChange(e.target.value)}
                            autoFocus
                        />
                    </div>
                )}
                <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                    <button onClick={onCancel} style={{
                        padding: '0.5rem 1rem', borderRadius: '6px',
                        border: '1px solid var(--color-border)', background: 'none',
                        color: 'var(--color-text)', cursor: 'pointer',
                        fontSize: 'var(--text-sm)', fontWeight: 500,
                    }}>Cancel</button>
                    <button onClick={onConfirm} style={{
                        padding: '0.5rem 1rem', borderRadius: '6px',
                        background: confirmColor, color: 'white',
                        border: 'none', cursor: 'pointer',
                        fontSize: 'var(--text-sm)', fontWeight: 600,
                    }}>{confirmLabel}</button>
                </div>
            </div>
        </div>
    );
}

interface WarrantExceededModalProps {
    info: {
        message: string;
        appropriation_label?: string;
        warrants_released?: string;
        already_consumed?: string;
        available_warrant?: string;
        requested?: string;
    };
    formatCurrency: (v: number) => string;
    onClose: () => void;
    onGoToWarrants: () => void;
}
/**
 * Hard-stop modal shown when a Vendor Invoice would push committed +
 * expended beyond the released warrants for its appropriation.
 *
 * In PSA terms this is a violation of the "Authority to Incur
 * Expenditure" — the Treasury hasn't released enough cash for this
 * spend, so the verifier cannot post regardless of how legitimate the
 * invoice itself is. There is intentionally no "Override" button;
 * resolving requires either (a) Treasury releasing an additional
 * warrant, or (b) reducing the invoice to fit the available ceiling.
 */
function WarrantExceededModal({ info, formatCurrency, onClose, onGoToWarrants }: WarrantExceededModalProps) {
    const fmt = (v?: string) => v != null ? formatCurrency(parseFloat(v)) : '—';
    return (
        <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(15,23,42,0.55)', display: 'flex',
            alignItems: 'center', justifyContent: 'center', zIndex: 9999,
            padding: '1rem',
        }} onClick={onClose}>
            <div style={{
                background: 'var(--color-surface)', borderRadius: '12px',
                padding: '1.5rem', maxWidth: '560px', width: '100%',
                boxShadow: '0 25px 60px rgba(0,0,0,0.3)',
                borderTop: '5px solid #dc2626',
            }} onClick={e => e.stopPropagation()}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.75rem' }}>
                    <div style={{
                        width: 40, height: 40, borderRadius: '50%',
                        background: '#fee2e2', display: 'flex',
                        alignItems: 'center', justifyContent: 'center',
                    }}>
                        <AlertTriangle size={22} color="#dc2626" />
                    </div>
                    <div>
                        <h3 style={{ margin: 0, fontSize: 'var(--text-base)', fontWeight: 700, color: '#991b1b' }}>
                            Warrant Ceiling Exceeded
                        </h3>
                        <p style={{ margin: '0.15rem 0 0', fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                            Authority to Incur Expenditure (AIE) limit reached
                        </p>
                    </div>
                </div>

                <p style={{ margin: '0 0 1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text)', lineHeight: 1.55 }}>
                    The treasury hasn't released enough cash against this appropriation
                    line to cover this invoice. Posting is blocked until Treasury
                    issues an additional warrant.
                </p>

                {/* Detail breakdown */}
                {info.appropriation_label && (
                    <div style={{
                        padding: '0.85rem 1rem', borderRadius: '8px',
                        background: '#fef2f2', border: '1px solid #fecaca',
                        marginBottom: '1rem', fontSize: 'var(--text-xs)',
                    }}>
                        <div style={{ fontWeight: 700, color: '#991b1b', marginBottom: '0.5rem', fontFamily: 'monospace' }}>
                            Appropriation: {info.appropriation_label}
                        </div>
                        <table style={{ width: '100%', fontFamily: 'monospace' }}>
                            <tbody>
                                <tr>
                                    <td style={{ padding: '0.2rem 0', color: '#7f1d1d' }}>Warrants Released</td>
                                    <td style={{ padding: '0.2rem 0', textAlign: 'right', fontWeight: 600 }}>{fmt(info.warrants_released)}</td>
                                </tr>
                                <tr>
                                    <td style={{ padding: '0.2rem 0', color: '#7f1d1d' }}>Less: Already Committed/Expended</td>
                                    <td style={{ padding: '0.2rem 0', textAlign: 'right', fontWeight: 600 }}>− {fmt(info.already_consumed)}</td>
                                </tr>
                                <tr style={{ borderTop: '1px solid #fecaca' }}>
                                    <td style={{ padding: '0.35rem 0', color: '#7f1d1d', fontWeight: 700 }}>Available Warrant</td>
                                    <td style={{ padding: '0.35rem 0', textAlign: 'right', fontWeight: 800, color: '#dc2626' }}>{fmt(info.available_warrant)}</td>
                                </tr>
                                <tr style={{ borderTop: '1px dashed #fca5a5' }}>
                                    <td style={{ padding: '0.35rem 0', color: '#7f1d1d', fontWeight: 700 }}>Requested (Invoice Total)</td>
                                    <td style={{ padding: '0.35rem 0', textAlign: 'right', fontWeight: 800, color: '#dc2626' }}>{fmt(info.requested)}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                )}

                {/* What to do next */}
                <div style={{
                    padding: '0.75rem 0.95rem', borderRadius: '8px',
                    background: 'rgba(245,158,11,0.08)',
                    border: '1px solid rgba(245,158,11,0.3)',
                    marginBottom: '1rem', fontSize: 'var(--text-xs)', color: '#92400e',
                }}>
                    <strong>To proceed:</strong>
                    <ul style={{ margin: '0.4rem 0 0', paddingLeft: '1.1rem', lineHeight: 1.6 }}>
                        <li>Ask Treasury to release an additional warrant for this appropriation, or</li>
                        <li>Reduce the invoice amount to fit the available ceiling, or</li>
                        <li>Reject this invoice if it shouldn't have been raised.</li>
                    </ul>
                </div>

                <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                    <button onClick={onClose} style={{
                        padding: '0.5rem 1rem', borderRadius: '6px',
                        border: '1px solid var(--color-border)', background: 'none',
                        color: 'var(--color-text)', cursor: 'pointer',
                        fontSize: 'var(--text-sm)', fontWeight: 500,
                    }}>
                        Close
                    </button>
                    <button onClick={onGoToWarrants} style={{
                        display: 'flex', alignItems: 'center', gap: '0.4rem',
                        padding: '0.5rem 1.1rem', borderRadius: '6px',
                        background: '#dc2626', color: 'white',
                        border: 'none', cursor: 'pointer',
                        fontSize: 'var(--text-sm)', fontWeight: 700,
                    }}>
                        <Building2 size={14} />
                        Go to Warrants Page
                    </button>
                </div>
            </div>
        </div>
    );
}

interface PostedSuccessCardProps {
    journalReference?: string;
    vendorInvoiceNumber?: string;
    onCreateAnother: () => void;
    onBackToList: () => void;
}
function PostedSuccessCard({ journalReference, vendorInvoiceNumber, onCreateAnother, onBackToList }: PostedSuccessCardProps) {
    return (
        <div style={{
            marginTop: '0.5rem', padding: '1.25rem', borderRadius: '12px',
            background: 'linear-gradient(135deg, #059669 0%, #10b981 50%, #34d399 100%)',
            color: 'white',
        }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.6rem' }}>
                <CheckCircle size={20} />
                <div style={{ fontWeight: 700, fontSize: 'var(--text-base)' }}>Invoice Verified & Posted to General Ledger</div>
            </div>
            <ul style={{ margin: 0, paddingLeft: '1.2rem', lineHeight: 1.7, fontSize: 'var(--text-xs)', opacity: 0.95 }}>
                {journalReference && <li>Journal: <strong>{journalReference}</strong></li>}
                {vendorInvoiceNumber && <li>Vendor Invoice: <strong>{vendorInvoiceNumber}</strong></li>}
                <li>GR/IR Clearing cleared, Accounts Payable credited</li>
                <li>Budget commitment closed (INVOICED → CLOSED)</li>
            </ul>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                <button type="button" onClick={onCreateAnother} style={{
                    padding: '0.5rem 1.1rem', borderRadius: '6px',
                    background: 'rgba(255,255,255,0.18)', color: 'white',
                    border: '1px solid rgba(255,255,255,0.25)',
                    fontWeight: 600, fontSize: 'var(--text-xs)', cursor: 'pointer',
                    display: 'inline-flex', alignItems: 'center', gap: '0.35rem',
                }}>
                    <Sparkles size={14} /> Verify Another Invoice
                </button>
                <button type="button" onClick={onBackToList} style={{
                    padding: '0.5rem 1.1rem', borderRadius: '6px',
                    background: 'transparent', color: 'white',
                    border: '1px solid rgba(255,255,255,0.35)',
                    fontWeight: 500, fontSize: 'var(--text-xs)', cursor: 'pointer',
                }}>
                    Back to List
                </button>
            </div>
        </div>
    );
}

interface SimulationModalProps {
    sim: SimulationResult;
    formatCurrency: (v: number) => string;
    onClose: () => void;
    onPost: () => void;
    posting: boolean;
}
/**
 * SAP MIRO "Simulate" preview — shows the proposed DR/CR journal entries
 * that will be created when the user clicks Post. Read-only; no records
 * are written until the user confirms via the "Post Invoice" button at
 * the bottom of the modal (which closes the modal and fires the real
 * verify_and_post call).
 *
 * Contains:
 * - Status banner (Matched / Variance) + match type
 * - Three-way amount comparison (PO / GRN / Invoice)
 * - Proposed journal lines table with totals
 * - "Balanced" indicator
 */
function SimulationModal({ sim, formatCurrency, onClose, onPost, posting }: SimulationModalProps) {
    const isVariance = sim.status === 'Variance';
    const variancePct = parseFloat(sim.variance_percentage);
    const banner = isVariance
        ? { bg: '#fef2f2', color: '#b91c1c', border: '#fecaca', label: `Variance ${variancePct.toFixed(2)}% — Above Threshold`, icon: <AlertTriangle size={16} /> }
        : { bg: '#dcfce7', color: '#15803d', border: '#86efac', label: `${sim.match_type} Match — Within Tolerance`, icon: <CheckCircle size={16} /> };

    return (
        <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(15,23,42,0.55)', display: 'flex',
            alignItems: 'center', justifyContent: 'center', zIndex: 9999,
            padding: '1rem',
        }} onClick={onClose}>
            <div style={{
                background: 'var(--color-surface)', borderRadius: '12px',
                padding: '1.5rem', maxWidth: '720px', width: '100%',
                maxHeight: '90vh', overflowY: 'auto',
                boxShadow: '0 25px 60px rgba(0,0,0,0.3)',
            }} onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                    <div>
                        <h3 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Calculator size={20} color="#4f46e5" />
                            Simulate GL Posting
                        </h3>
                        <p style={{ margin: '0.25rem 0 0', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                            Preview only — nothing will be posted until you click "Post Invoice" below.
                        </p>
                    </div>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                        <X size={20} />
                    </button>
                </div>

                {/* Match status banner */}
                <div style={{
                    padding: '0.7rem 0.95rem', marginBottom: '1rem', borderRadius: '8px',
                    background: banner.bg, color: banner.color,
                    border: `1px solid ${banner.border}`,
                    display: 'flex', alignItems: 'center', gap: '0.5rem',
                    fontSize: 'var(--text-sm)', fontWeight: 600,
                }}>
                    {banner.icon}
                    {banner.label}
                    {sim.partial_receipt && (
                        <span style={{
                            marginLeft: 'auto', padding: '0.15rem 0.55rem', borderRadius: '999px',
                            background: 'rgba(245,158,11,0.15)', color: '#a16207',
                            fontSize: '10px', fontWeight: 700,
                        }}>
                            PARTIAL RECEIPT
                        </span>
                    )}
                </div>

                {/* Three-way amount comparison */}
                <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem',
                    marginBottom: '1.25rem',
                }}>
                    {[
                        { label: 'PO Total',       value: parseFloat(sim.po_total) },
                        { label: 'GRN Value',      value: parseFloat(sim.grn_total) },
                        { label: 'Invoice Total',  value: parseFloat(sim.invoice_amount), accent: true },
                    ].map(({ label, value, accent }) => (
                        <div key={label} style={{
                            padding: '0.7rem', borderRadius: '8px',
                            background: accent ? 'rgba(79,70,229,0.06)' : 'rgba(148,163,184,0.06)',
                            border: `1px solid ${accent ? 'rgba(79,70,229,0.25)' : 'var(--color-border)'}`,
                            textAlign: 'center',
                        }}>
                            <div style={{ fontSize: '0.6rem', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.2rem' }}>
                                {label}
                            </div>
                            <div style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: accent ? '#4f46e5' : 'var(--color-text)', fontFamily: 'monospace' }}>
                                {formatCurrency(value)}
                            </div>
                        </div>
                    ))}
                </div>

                {/* Proposed journal lines table */}
                <div style={{
                    border: '1px solid var(--color-border)', borderRadius: '8px',
                    overflow: 'hidden', marginBottom: '1rem',
                }}>
                    <div style={{ padding: '0.55rem 0.85rem', background: 'rgba(0,0,0,0.03)', fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                        Proposed Journal Entries
                    </div>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                        <thead>
                            <tr style={{ background: 'rgba(0,0,0,0.02)' }}>
                                <th style={{ ...th, padding: '0.45rem 0.7rem' }}>Account</th>
                                <th style={{ ...th, padding: '0.45rem 0.7rem', textAlign: 'right' }}>Debit</th>
                                <th style={{ ...th, padding: '0.45rem 0.7rem', textAlign: 'right' }}>Credit</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sim.proposed_lines.length === 0 ? (
                                <tr>
                                    <td colSpan={3} style={{ ...td, textAlign: 'center', color: 'var(--color-text-muted)', padding: '1rem' }}>
                                        No journal lines — check that GR/IR Clearing and AP accounts are configured.
                                    </td>
                                </tr>
                            ) : (
                                sim.proposed_lines.map((line, i) => (
                                    <tr key={i}>
                                        <td style={{ ...td, padding: '0.5rem 0.7rem' }}>
                                            <div style={{ fontFamily: 'monospace', fontWeight: 600 }}>{line.account_code}</div>
                                            <div style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>{line.account_name}</div>
                                            {line.memo && (
                                                <div style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)', fontStyle: 'italic', marginTop: '0.1rem' }}>
                                                    {line.memo}
                                                </div>
                                            )}
                                        </td>
                                        <td style={{ ...td, padding: '0.5rem 0.7rem', textAlign: 'right', fontFamily: 'monospace', color: parseFloat(line.debit) > 0 ? '#16a34a' : 'var(--color-text-muted)' }}>
                                            {parseFloat(line.debit) > 0 ? formatCurrency(parseFloat(line.debit)) : '—'}
                                        </td>
                                        <td style={{ ...td, padding: '0.5rem 0.7rem', textAlign: 'right', fontFamily: 'monospace', color: parseFloat(line.credit) > 0 ? '#dc2626' : 'var(--color-text-muted)' }}>
                                            {parseFloat(line.credit) > 0 ? formatCurrency(parseFloat(line.credit)) : '—'}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                        <tfoot>
                            <tr style={{ borderTop: '2px solid var(--color-border)', background: 'rgba(0,0,0,0.02)' }}>
                                <td style={{ ...td, padding: '0.55rem 0.7rem', fontWeight: 700 }}>Total</td>
                                <td style={{ ...td, padding: '0.55rem 0.7rem', textAlign: 'right', fontWeight: 700, fontFamily: 'monospace', color: '#16a34a' }}>
                                    {formatCurrency(parseFloat(sim.total_debit))}
                                </td>
                                <td style={{ ...td, padding: '0.55rem 0.7rem', textAlign: 'right', fontWeight: 700, fontFamily: 'monospace', color: '#dc2626' }}>
                                    {formatCurrency(parseFloat(sim.total_credit))}
                                </td>
                            </tr>
                        </tfoot>
                    </table>
                </div>

                {/* Balanced indicator */}
                <div style={{
                    padding: '0.55rem 0.75rem', borderRadius: '6px',
                    background: sim.balanced ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
                    border: `1px solid ${sim.balanced ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)'}`,
                    color: sim.balanced ? '#15803d' : '#b91c1c',
                    fontSize: 'var(--text-xs)', fontWeight: 600,
                    display: 'flex', alignItems: 'center', gap: '0.4rem',
                    marginBottom: '1rem',
                }}>
                    {sim.balanced ? <CheckCircle size={14} /> : <XCircle size={14} />}
                    {sim.balanced ? 'Journal is balanced (DR = CR)' : 'Journal is NOT balanced — review before posting'}
                </div>

                {/* Actions */}
                <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                    <button onClick={onClose} style={{
                        padding: '0.5rem 1rem', borderRadius: '6px',
                        border: '1px solid var(--color-border)', background: 'none',
                        color: 'var(--color-text)', cursor: 'pointer',
                        fontSize: 'var(--text-sm)', fontWeight: 500,
                    }}>
                        Close
                    </button>
                    <button onClick={onPost} disabled={posting || !sim.balanced || isVariance} style={{
                        display: 'flex', alignItems: 'center', gap: '0.4rem',
                        padding: '0.5rem 1.25rem', borderRadius: '6px',
                        background: '#22c55e', color: '#fff',
                        border: 'none', cursor: (posting || !sim.balanced || isVariance) ? 'not-allowed' : 'pointer',
                        fontSize: 'var(--text-sm)', fontWeight: 700,
                        opacity: (posting || !sim.balanced || isVariance) ? 0.5 : 1,
                    }} title={isVariance ? 'Close this preview, then click Post — you\'ll be prompted for a variance reason' : ''}>
                        <BookOpen size={15} />
                        {posting ? 'Posting…' : 'Post Invoice'}
                    </button>
                </div>
            </div>
        </div>
    );
}

interface MdaSelectionScreenProps {
    mdas: Array<{ id: number; code: string; name: string }>;
    onSelect: (id: number) => void;
}
/**
 * Full-page MDA selection gate. Modelled on SAP MIRO's "Enter Company
 * Code" prompt that appears the moment you launch the MIRO transaction
 * — you can't see invoices until you've declared scope. Same idea here:
 * the verifier explicitly tells the system which Ministry's books they
 * are working in before the form is rendered.
 *
 * Why upfront, not at post time:
 *  - Forces conscious scope selection — no accidental cross-MDA posts.
 *  - Lets the page filter every dropdown (PO, GRN) by that MDA from
 *    the very first fetch, removing visual noise from other ministries.
 *  - Backend gets to enforce the boundary with a single MDA value
 *    rather than three independent checks.
 *
 * The screen has searchable MDA list — useful when there are many
 * MDAs in larger sub-national governments (e.g. >40 in Lagos State).
 */
function MdaSelectionScreen({ mdas, onSelect }: MdaSelectionScreenProps) {
    const [filter, setFilter] = useState('');
    const filtered = useMemo(() => {
        const q = filter.trim().toLowerCase();
        if (!q) return mdas;
        return mdas.filter(m =>
            m.code.toLowerCase().includes(q) || m.name.toLowerCase().includes(q),
        );
    }, [mdas, filter]);

    return (
        <div style={{
            background: 'linear-gradient(135deg, rgba(79,70,229,0.05) 0%, rgba(99,102,241,0.08) 100%)',
            border: '1px solid rgba(79,70,229,0.2)', borderRadius: '14px',
            padding: '2.5rem 2rem', maxWidth: '720px', margin: '2rem auto',
            boxShadow: '0 10px 30px rgba(79,70,229,0.08)',
        }}>
            <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
                <div style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    width: 64, height: 64, borderRadius: '50%',
                    background: 'rgba(79,70,229,0.1)', marginBottom: '1rem',
                }}>
                    <Building2 size={32} color="#4f46e5" />
                </div>
                <h2 style={{ margin: 0, fontSize: 'var(--text-xl)', fontWeight: 700 }}>
                    Select Posting MDA
                </h2>
                <p style={{ margin: '0.5rem 0 0', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', maxWidth: 480, marginInline: 'auto' }}>
                    Choose the Ministry, Department or Agency this invoice belongs to.
                    All Purchase Orders, GRNs, and budget appropriations on the next
                    screen will be scoped to this MDA.
                </p>
            </div>

            {/* Search */}
            <input
                type="text" placeholder="Search MDA by name or code…"
                value={filter} onChange={e => setFilter(e.target.value)}
                autoFocus
                style={{
                    ...inp,
                    fontSize: 'var(--text-base)',
                    padding: '0.7rem 1rem', marginBottom: '1rem',
                    border: '2px solid rgba(79,70,229,0.25)',
                }}
            />

            {/* Scrollable MDA list */}
            <div style={{
                maxHeight: '360px', overflowY: 'auto',
                border: '1px solid var(--color-border)', borderRadius: '8px',
                background: 'var(--color-surface)',
            }}>
                {filtered.length === 0 ? (
                    <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                        No MDAs match your search.
                    </div>
                ) : (
                    filtered.map((m, i) => (
                        <button
                            key={m.id} type="button"
                            onClick={() => onSelect(m.id)}
                            style={{
                                width: '100%', textAlign: 'left' as const,
                                padding: '0.85rem 1.1rem',
                                background: 'transparent', border: 'none',
                                borderBottom: i < filtered.length - 1 ? '1px solid var(--color-border)' : 'none',
                                cursor: 'pointer',
                                display: 'flex', alignItems: 'center', gap: '0.75rem',
                                transition: 'background 0.15s',
                            }}
                            onMouseEnter={e => e.currentTarget.style.background = 'rgba(79,70,229,0.06)'}
                            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                        >
                            <div style={{
                                width: 36, height: 36, borderRadius: '8px',
                                background: 'rgba(79,70,229,0.1)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                flexShrink: 0,
                            }}>
                                <Building2 size={18} color="#4f46e5" />
                            </div>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>
                                    {m.name}
                                </div>
                                <div style={{ fontFamily: 'monospace', fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                                    {m.code}
                                </div>
                            </div>
                            <div style={{ fontSize: 'var(--text-xs)', color: '#4f46e5', fontWeight: 600 }}>
                                Select →
                            </div>
                        </button>
                    ))
                )}
            </div>

            {mdas.length === 0 && (
                <p style={{ marginTop: '1rem', textAlign: 'center', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                    Loading MDAs…
                </p>
            )}
        </div>
    );
}

interface SessionMdaBannerProps {
    mda: { id: number; code: string; name: string } | null;
    onChange: () => void;
}
/**
 * Sticky banner shown above the main form once the verifier has
 * selected an MDA. Acts as a constant visual reminder of the session
 * scope and provides a single "Change MDA" affordance — clicking it
 * either prompts a confirmation (if the form has data) or returns
 * straight to the MDA selection screen.
 */
function SessionMdaBanner({ mda, onChange }: SessionMdaBannerProps) {
    if (!mda) return null;
    return (
        <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: '1rem', padding: '0.7rem 1rem', marginBottom: '1rem',
            background: 'linear-gradient(90deg, rgba(79,70,229,0.08) 0%, rgba(99,102,241,0.04) 100%)',
            border: '1px solid rgba(79,70,229,0.25)',
            borderRadius: '10px',
            fontSize: 'var(--text-sm)',
        }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <div style={{
                    width: 32, height: 32, borderRadius: '8px',
                    background: 'rgba(79,70,229,0.15)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                    <Building2 size={16} color="#4f46e5" />
                </div>
                <div>
                    <div style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Session MDA
                    </div>
                    <div style={{ fontWeight: 700, color: '#4f46e5' }}>
                        {mda.code} — {mda.name}
                    </div>
                </div>
            </div>
            <button type="button" onClick={onChange} style={{
                display: 'flex', alignItems: 'center', gap: '0.35rem',
                padding: '0.4rem 0.85rem', borderRadius: '6px',
                background: 'transparent', color: '#4f46e5',
                border: '1px solid rgba(79,70,229,0.4)',
                cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600,
            }}>
                <Building2 size={12} />
                Change MDA
            </button>
        </div>
    );
}


// ─── Main component ────────────────────────────────────────────────────────

export default function NewInvoiceMatching() {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const { showPrompt: _showPrompt } = useDialog();
    void _showPrompt;
    const verifyAndPost = useVerifyAndPost();
    const simulate      = useSimulateInvoice();
    const [simulation, setSimulation] = useState<SimulationResult | null>(null);

    // SAP MIRO Company Code-style scoping: the verifier picks an MDA at
    // the START of the session — the main form stays hidden until then.
    // Once selected, every dropdown (PO, GRN) is scoped to that MDA and
    // the backend rejects any payload that crosses MDA boundaries.
    const { data: mdas = [] } = useMDAs({ is_active: true });
    const [sessionMdaId, setSessionMdaId] = useState<number | null>(null);
    const [showChangeMdaConfirm, setShowChangeMdaConfirm] = useState(false);
    const sessionMda = useMemo(
        () => mdas.find((m: any) => m.id === sessionMdaId) ?? null,
        [mdas, sessionMdaId],
    );

    const [form, setForm] = useState({
        purchase_order: '',
        goods_received_note: '',
        invoice_reference: '',
        invoice_date: '',
        invoice_amount: '',
        invoice_tax_amount: '',
        invoice_subtotal: '',
        tax_code: '',                // FK id — VAT / input-tax code
        withholding_tax: '',         // FK id — WHT code (defaults from vendor master)
        wht_exempt: false,           // transaction-level WHT exemption
        wht_exempt_reason: '',
        notes: '',
    });

    // Tax code dropdowns — VAT (purchase or both) + WHT (any active)
    const { data: taxCodesData } = useTaxCodes({ is_active: true, direction: 'purchase' });
    const { data: whtData } = useWithholdingTaxes({ is_active: true });
    const taxCodes: Array<{ id: number; code: string; name: string; rate: number | string }> =
        Array.isArray(taxCodesData) ? taxCodesData : (taxCodesData?.results ?? []);
    const whtCodes: Array<{ id: number; code: string; name: string; rate: number | string }> =
        Array.isArray(whtData) ? whtData : (whtData?.results ?? []);
    const [error, setError] = useState('');
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
    const [posted, setPosted] = useState<{ journalReference?: string; vendorInvoiceNumber?: string } | null>(null);

    // Modal gates — backend tells us which to show via 400 response flags.
    const [partialModal, setPartialModal] = useState(false);
    const [varianceModal, setVarianceModal] = useState<{ pct: string; amount: string } | null>(null);
    const [warrantModal, setWarrantModal] = useState<{
        message: string;
        appropriation_label?: string;
        warrants_released?: string;
        already_consumed?: string;
        available_warrant?: string;
        requested?: string;
    } | null>(null);
    const [varianceReason, setVarianceReason] = useState('');
    const [acknowledgePartial, setAcknowledgePartial] = useState(false);

    const set = (field: string, val: string) => setForm(prev => ({ ...prev, [field]: val }));
    const flash = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 5000);
    };

    // ── Data fetches (scoped to session MDA) ─────────────────────────
    // Both endpoints honour `?mda=<id>`. We only fire the queries once
    // an MDA has been chosen — the main form is hidden until then so
    // the empty-list/loading flicker never reaches the user.
    const { data: posData } = usePurchaseOrders({
        mda: sessionMdaId ?? undefined,
        page_size: 200,
    });
    const pos = Array.isArray(posData) ? posData : (posData?.results ?? []);

    const { data: grnsData } = useGRNs({
        mda: sessionMdaId ?? undefined,
        page_size: 200,
    });
    const grns = Array.isArray(grnsData) ? grnsData : (grnsData?.results ?? []);

    // ── Posted-GRN gating ────────────────────────────────────────────
    // Invoice verification only makes sense for goods that have
    // ACTUALLY been received — i.e. POs with at least one Posted
    // GRN. Draft GRNs represent pending paperwork; their goods
    // haven't been physically received yet and posting an invoice
    // against them would create a liability for goods that may
    // never arrive. So:
    //   1. The PO selector hides POs whose ONLY GRNs are Draft /
    //      Cancelled.
    //   2. The GRN selector below shows only Posted GRNs for the
    //      chosen PO — even if the PO has Draft GRNs, those are
    //      not selectable here.
    // Computed as a Set of stringified PO ids for O(1) lookup
    // when we filter the (potentially large) PO list.
    const postedGrnPoIds = useMemo(() => {
        const ids = new Set<string>();
        for (const g of grns as any[]) {
            if (g?.status === 'Posted' && g?.purchase_order != null) {
                ids.add(String(g.purchase_order));
            }
        }
        return ids;
    }, [grns]);

    // ── Already-posted-invoice gating ────────────────────────────────
    // Once an Invoice Verification has been posted to the GL for a PO,
    // posting another verification against the same PO would double the
    // AP credit, double the GR/IR clearing and double-consume the
    // appropriation. So we hide POs that already have a non-reversed
    // Posted invoice matching from the source list. The only way to
    // raise a fresh verification on such a PO is to first Reverse the
    // existing one (which flips the journal's ``is_reversed`` flag and
    // returns the PO to the eligible pool).
    //
    // The matching list endpoint surfaces ``vendor_invoice_status`` per
    // matching; we treat any matching whose VI is Posted as "blocking"
    // unless the matching itself has been moved out of the active set.
    const { data: matchingsData } = useInvoiceMatchings({ page_size: 500 });
    const matchings = Array.isArray(matchingsData)
        ? matchingsData
        : (matchingsData?.results ?? []);
    const postedInvoicePoIds = useMemo(() => {
        const ids = new Set<string>();
        for (const m of matchings as any[]) {
            const isPosted = (
                m?.vendor_invoice_status === 'Posted'
                || !!m?.journal_entry_id
                || !!m?.journal_reference
            );
            if (isPosted && m?.purchase_order != null) {
                ids.add(String(m.purchase_order));
            }
        }
        return ids;
    }, [matchings]);

    const selectedPoId  = form.purchase_order ? parseInt(form.purchase_order) : null;
    const selectedGrnId = form.goods_received_note ? parseInt(form.goods_received_note) : null;

    const { data: poDetail, isLoading: poLoading } = usePurchaseOrder(selectedPoId);
    const { data: grnDetail, isLoading: grnLoading } = useGRN(selectedGrnId);

    // ── Down Payment ─────────────────────────────────────────────────
    const { data: dpr } = useDownPaymentForPO(selectedPoId);
    const [dpExpanded, setDpExpanded] = useState(false);
    const [dpEnabled, setDpEnabled] = useState(false);
    const [dpAmount, setDpAmount] = useState('');
    const invoiceAmtEarly = form.invoice_amount ? parseFloat(form.invoice_amount) : null;
    const availableAdvance: number | null = dpr?.advance_remaining != null
        ? parseFloat(String(dpr.advance_remaining))
        : null;
    const defaultDpAmount = useMemo(() => {
        if (availableAdvance === null || !invoiceAmtEarly) return '';
        return String(Math.min(availableAdvance, invoiceAmtEarly));
    }, [availableAdvance, invoiceAmtEarly]);
    const effectiveDpAmount = dpEnabled ? (dpAmount || defaultDpAmount) : '0';
    const netPayable = invoiceAmtEarly !== null
        ? Math.max(0, invoiceAmtEarly - parseFloat(effectiveDpAmount || '0'))
        : null;

    // ── Filter GRNs to those linked to the selected PO ──────────────
    // Only Posted GRNs are eligible for invoice verification (Draft /
    // Received / Cancelled GRNs represent goods not yet booked into
    // the GL via post_grn). Without this guard the operator could
    // pick a Draft GRN and post an invoice that has no matching
    // inventory increase — a 3-way-match contract violation.
    const filteredGrns = selectedPoId
        ? grns.filter((g: any) =>
            String(g.purchase_order) === String(selectedPoId)
            && g?.status === 'Posted',
          )
        : grns.filter((g: any) => g?.status === 'Posted');

    // ── Per-line PO/GRN comparison table ────────────────────────────
    const comparisonLines = useMemo(() => {
        if (!poDetail?.lines) return [];
        const grnByPoLine: Record<number, number> = {};
        if (grnDetail?.lines) {
            for (const gl of grnDetail.lines) {
                grnByPoLine[gl.po_line] = (grnByPoLine[gl.po_line] || 0) + parseFloat(gl.quantity_received || 0);
            }
        }
        return poDetail.lines.map((line: any) => {
            const poQty = parseFloat(line.quantity || 0);
            const poPrice = parseFloat(line.unit_price || 0);
            const poAmt = poQty * poPrice;
            const grnQty = grnByPoLine[line.id] ?? null;
            const grnAmt = grnQty !== null ? grnQty * poPrice : null;
            return { ...line, poQty, poPrice, poAmt, grnQty, grnAmt };
        });
    }, [poDetail, grnDetail]);

    // ── PO-driven auto-prefill ──────────────────────────────────────
    // When the user picks a Purchase Order, we pre-populate the invoice
    // amount/subtotal/tax with the PO's totals. The MDA is already locked
    // by the upfront session selector, so no MDA prefill needed here.
    useEffect(() => {
        if (!poDetail) return;
        const poTotal    = parseFloat(poDetail.total_amount ?? 0) || 0;
        const poSubtotal = parseFloat(poDetail.subtotal     ?? 0) || 0;
        const poTax      = parseFloat(poDetail.tax_amount   ?? 0) || 0;
        if (poTotal <= 0) return;
        // Vendor-master defaults (SAP BP parity): prefill WHT from the
        // vendor's default code; if the vendor is permanently exempt, leave
        // WHT blank and flag the transaction exempt too so the user sees why.
        const vendorWht = poDetail.vendor_wht_code
            ? String(poDetail.vendor_wht_code)
            : '';
        const vendorExempt = !!poDetail.vendor_wht_exempt;
        // Auto-pick tax_code: when the PO carries a non-zero tax amount,
        // infer the implied rate (tax/subtotal × 100) and find the active
        // TaxCode whose rate matches within 0.1%. SAP MIRO behaviour —
        // user shouldn't have to re-pick what's already implied by the
        // PO. Falls through to no-op when amounts don't match any code.
        let inferredTaxCode = '';
        const poImpliedSub = poSubtotal || (poTotal - poTax);
        if (poTax > 0 && poImpliedSub > 0 && taxCodes.length > 0) {
            const impliedRate = (poTax / poImpliedSub) * 100;
            const match = taxCodes.find((t) => {
                const r = parseFloat(String(t.rate)) || 0;
                return Math.abs(r - impliedRate) < 0.1;
            });
            if (match) inferredTaxCode = String(match.id);
        }
        setForm(prev => ({
            ...prev,
            invoice_amount:     prev.invoice_amount    || String(poTotal),
            invoice_subtotal:   prev.invoice_subtotal  || String(poImpliedSub),
            invoice_tax_amount: prev.invoice_tax_amount || String(poTax),
            invoice_date:       prev.invoice_date      || new Date().toISOString().split('T')[0],
            tax_code:           prev.tax_code          || inferredTaxCode,
            withholding_tax:    prev.withholding_tax   || (vendorExempt ? '' : vendorWht),
            wht_exempt:         prev.wht_exempt || vendorExempt,
            wht_exempt_reason:  prev.wht_exempt_reason
                || (vendorExempt ? 'Vendor is permanently exempt from WHT (master data)' : ''),
        }));
    }, [poDetail, taxCodes]);

    // When PO changes: reset GRN + clear amount fields so the prefill effect repopulates.
    const handlePoChange = (val: string) => {
        const poGrns = val
            ? grns.filter((g: any) => String(g.purchase_order) === String(val))
            : [];
        setForm(prev => ({
            ...prev,
            purchase_order: val,
            goods_received_note: poGrns.length === 1 ? String(poGrns[0].id) : '',
            invoice_amount: '',
            invoice_subtotal: '',
            invoice_tax_amount: '',
            tax_code: '',
            withholding_tax: '',
            wht_exempt: false,
            wht_exempt_reason: '',
        }));
        // Reset the gates so a new PO starts clean.
        setAcknowledgePartial(false);
        setVarianceReason('');
    };

    // ── Tax-code driven auto-calculation ────────────────────────────
    // When the user picks a VAT code, we compute tax = subtotal × rate
    // and sync the invoice total. WHT is previewed for the right-rail
    // but never modifies the invoice total — WHT is a payment-time
    // deduction, not a line on the vendor's invoice.
    const selectedTaxCode = useMemo(
        () => taxCodes.find(t => String(t.id) === form.tax_code) ?? null,
        [taxCodes, form.tax_code],
    );
    const selectedWht = useMemo(
        () => whtCodes.find(w => String(w.id) === form.withholding_tax) ?? null,
        [whtCodes, form.withholding_tax],
    );
    useEffect(() => {
        if (!selectedTaxCode) return;
        const sub = parseFloat(form.invoice_subtotal || '0');
        if (!sub || sub <= 0) return;
        const rate = parseFloat(String(selectedTaxCode.rate || '0'));
        const tax = +(sub * rate / 100).toFixed(2);
        const total = +(sub + tax).toFixed(2);
        setForm(prev => ({
            ...prev,
            invoice_tax_amount: String(tax),
            invoice_amount: String(total),
        }));
    }, [selectedTaxCode, form.invoice_subtotal]);

    const whtPreview = useMemo(() => {
        if (form.wht_exempt) return 0;
        if (!selectedWht) return 0;
        const sub = parseFloat(form.invoice_subtotal || '0');
        if (!sub) return 0;
        return +(sub * parseFloat(String(selectedWht.rate || '0')) / 100).toFixed(2);
    }, [selectedWht, form.invoice_subtotal, form.wht_exempt]);

    // ── Live amounts for the right-rail summary ─────────────────────
    const poTotal = poDetail ? parseFloat(poDetail.total_amount || 0) : null;
    const grnTotal = grnDetail?.lines
        ? grnDetail.lines.reduce((s: number, l: any) => {
            const poLine = poDetail?.lines?.find((p: any) => p.id === l.po_line);
            const price = poLine ? parseFloat(poLine.unit_price || 0) : 0;
            return s + parseFloat(l.quantity_received || 0) * price;
        }, 0)
        : null;
    const invoiceAmt = form.invoice_amount ? parseFloat(form.invoice_amount) : null;

    // ── GRN-vs-Invoice variance must compare on a like-for-like basis.
    // GRN value is computed as qty_received × unit_price (no VAT —
    // the warehouse never books tax), so a gross invoice with VAT
    // ALWAYS shows a variance equal to the tax rate when compared
    // against the GRN. To make the variance gate meaningful we strip
    // the VAT from the invoice side: when ``invoice_tax_amount > 0``,
    // use ``invoice_subtotal`` instead of the gross ``invoice_amount``.
    // The PO-side comparison still uses gross-vs-gross (PO contracts
    // include VAT) so the existing ``Inv vs PO`` pill is correct.
    const invoiceTaxNum   = form.invoice_tax_amount ? parseFloat(form.invoice_tax_amount) : 0;
    const invoiceSubNum   = form.invoice_subtotal   ? parseFloat(form.invoice_subtotal)   : 0;
    const invoiceForGrnCompare = (invoiceTaxNum > 0 && invoiceSubNum > 0)
        ? invoiceSubNum
        : invoiceAmt;

    // ── Detect partial receipt for the modal gate ───────────────────
    const isPartiallyReceived = useMemo(() => {
        if (!poDetail?.lines) return false;
        return poDetail.lines.some((l: any) => parseFloat(l.quantity_received || 0) < parseFloat(l.quantity || 0));
    }, [poDetail]);

    // ── Single-button POST handler ──────────────────────────────────
    const buildPayload = (overrides?: { acknowledge_partial?: boolean; variance_reason?: string }) => ({
        purchase_order: selectedPoId!,
        goods_received_note: selectedGrnId ?? null,
        invoice_reference: form.invoice_reference.trim(),
        invoice_date: form.invoice_date,
        invoice_amount: parseFloat(form.invoice_amount),
        invoice_subtotal: form.invoice_subtotal ? parseFloat(form.invoice_subtotal) : undefined,
        invoice_tax_amount: form.invoice_tax_amount ? parseFloat(form.invoice_tax_amount) : undefined,
        tax_code: form.tax_code ? parseInt(form.tax_code) : null,
        withholding_tax: form.wht_exempt
            ? null
            : (form.withholding_tax ? parseInt(form.withholding_tax) : null),
        wht_exempt: form.wht_exempt,
        wht_exempt_reason: form.wht_exempt ? form.wht_exempt_reason.trim() : '',
        notes: form.notes.trim() || undefined,
        acknowledge_partial: overrides?.acknowledge_partial ?? acknowledgePartial,
        variance_reason: overrides?.variance_reason ?? varianceReason,
        down_payment_amount: dpEnabled ? parseFloat(effectiveDpAmount || '0') : undefined,
        mda: sessionMdaId,  // SAP MIRO Company-Code-style scoping (locked at session start)
    });

    const submitToBackend = (overrides?: { acknowledge_partial?: boolean; variance_reason?: string }) => {
        verifyAndPost.mutate(buildPayload(overrides), {
            onSuccess: (data: any) => {
                setPosted({
                    journalReference: data?.journal_reference,
                    vendorInvoiceNumber: data?.vendor_invoice_number,
                });
                flash(
                    data?.journal_reference
                        ? `Posted. Journal ${data.journal_reference}`
                        : 'Invoice posted to GL.',
                );
                setPartialModal(false);
                setVarianceModal(null);
                setWarrantModal(null);
            },
            onError: (err: any) => {
                const data = err?.response?.data || {};
                // Backend gate 1: partial receipt → show partial modal
                if (data.partial_receipt) {
                    setPartialModal(true);
                    return;
                }
                // Backend gate 2: variance > threshold → ask for reason
                if (data.requires_variance_reason) {
                    setVarianceModal({
                        pct: data.variance_percentage || '0',
                        amount: data.variance_amount || '0',
                    });
                    return;
                }
                // Backend gate 3: warrant ceiling exceeded — hard stop until
                // an additional warrant is issued. Cannot be overridden by
                // the verifier; treasury/MDA finance must release more cash.
                if (data.warrant_exceeded) {
                    setWarrantModal({
                        message: data.error || 'Warrant ceiling exceeded.',
                        ...(data.warrant_info || {}),
                    });
                    return;
                }
                setError(data.error || data.detail || 'Failed to post invoice.');
                flash(data.error || 'Failed to post invoice.', false);
            },
        });
    };

    const handlePost = (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        // Local guards before hitting the network. The MDA was locked
        // upfront via the session-selector, so we don't need a popup here.
        if (!sessionMdaId)              { setError('Pick an MDA first.'); return; }
        if (!selectedPoId)              { setError('Purchase Order is required.'); return; }
        if (!form.invoice_reference.trim()) { setError('Invoice reference is required.'); return; }
        if (!form.invoice_date)         { setError('Invoice date is required.'); return; }
        if (!form.invoice_amount || parseFloat(form.invoice_amount) <= 0) {
            setError('Invoice amount must be greater than zero.'); return;
        }
        submitToBackend();
    };

    /**
     * Simulate the GL post — read-only preview, never writes.
     * Pops a modal showing the proposed DR/CR lines so the verifier can
     * sanity-check the journal hit before clicking Post Invoice.
     */
    const handleSimulate = () => {
        setError('');
        if (!selectedPoId) { setError('Pick a PO before simulating.'); return; }
        if (!form.invoice_amount || parseFloat(form.invoice_amount) <= 0) {
            setError('Enter the invoice total before simulating.'); return;
        }
        simulate.mutate(
            {
                purchase_order: selectedPoId,
                goods_received_note: selectedGrnId ?? null,
                invoice_reference: form.invoice_reference.trim() || undefined,
                invoice_amount: parseFloat(form.invoice_amount),
                invoice_subtotal: form.invoice_subtotal ? parseFloat(form.invoice_subtotal) : undefined,
                invoice_tax_amount: form.invoice_tax_amount ? parseFloat(form.invoice_tax_amount) : undefined,
                // Tax + WHT codes are required for the backend to look
                // up the correct Input VAT and WHT GL accounts via FK
                // (TaxCode.input_tax_account / WithholdingTax.withholding_account)
                // instead of the legacy "first Liability with 'Tax' in
                // its name" heuristic that mis-resolved to the
                // Withholding Tax account on tenants whose NCoA names
                // every tax-related liability "UNREMITTED TAXES: ...".
                tax_code: form.tax_code ? parseInt(form.tax_code) : undefined,
                withholding_tax: (form.withholding_tax && !form.wht_exempt)
                    ? parseInt(form.withholding_tax)
                    : undefined,
            },
            {
                onSuccess: (data) => setSimulation(data),
                onError: (err: any) => {
                    flash(err?.response?.data?.error || 'Simulation failed.', false);
                },
            },
        );
    };

    const handleResetForAnother = () => {
        setForm({
            purchase_order: '', goods_received_note: '',
            invoice_reference: '', invoice_date: '',
            invoice_amount: '', invoice_tax_amount: '',
            invoice_subtotal: '', notes: '',
        });
        setPosted(null);
        setError('');
        setVarianceReason('');
        setAcknowledgePartial(false);
        setDpEnabled(false);
        setDpAmount('');
    };

    // ── Render ──────────────────────────────────────────────────────
    return (
        <AccountingLayout>
            <div style={{ padding: '1.5rem', maxWidth: '1200px' }}>

                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.25rem' }}>
                    <button onClick={() => navigate('/procurement/matching')} style={{
                        display: 'flex', alignItems: 'center', gap: '0.375rem', background: 'none',
                        border: '1px solid var(--color-border)', borderRadius: '6px',
                        padding: '0.4rem 0.75rem', color: 'var(--color-text-muted)',
                        cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 500,
                    }}>
                        <ArrowLeft size={14} /> Back
                    </button>
                    <div style={{ flex: 1 }}>
                        <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                            Invoice Verification
                        </h1>
                        <p style={{ color: 'var(--color-text-muted)', margin: '0.15rem 0 0', fontSize: 'var(--text-sm)' }}>
                            SAP MIRO-style: pick the PO, enter the invoice, post in one click.
                        </p>
                    </div>
                    {/* Live match badge — updates as user types.
                        Pass ``invoiceForGrnCompare`` (subtotal when tax is
                        present, else gross) as the variance numerator so
                        VAT-on-top doesn't fire a false 7.5% variance
                        against the ex-VAT GRN total. */}
                    <LiveMatchBadge poTotal={poTotal} grnTotal={grnTotal} invoiceAmt={invoiceForGrnCompare} />
                </div>

                {/* Errors / toasts / posted-success */}
                {error && (
                    <div style={{
                        padding: '0.625rem 0.875rem', marginBottom: '1rem',
                        background: 'rgba(239,68,68,0.08)', color: '#ef4444',
                        border: '1px solid rgba(239,68,68,0.2)', borderRadius: '6px',
                        fontSize: 'var(--text-sm)',
                    }}>{error}</div>
                )}
                {toast && (
                    <div style={{
                        padding: '0.7rem 0.95rem', marginBottom: '1rem', borderRadius: '8px',
                        background: toast.ok ? '#ecfdf5' : '#fef2f2',
                        border: `1px solid ${toast.ok ? '#a7f3d0' : '#fecaca'}`,
                        color: toast.ok ? '#065f46' : '#991b1b',
                        fontSize: 'var(--text-sm)', display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 500,
                    }}>
                        {toast.ok ? <CheckCircle size={16} /> : <AlertTriangle size={16} />}
                        {toast.msg}
                    </div>
                )}

                {/* Posted state takes over the page */}
                {posted ? (
                    <PostedSuccessCard
                        journalReference={posted.journalReference}
                        vendorInvoiceNumber={posted.vendorInvoiceNumber}
                        onCreateAnother={() => {
                            handleResetForAnother();
                            // Posted-success → "verify another" returns the user
                            // to the MDA selection screen so they explicitly
                            // re-confirm scope for the next verification.
                            setSessionMdaId(null);
                        }}
                        onBackToList={() => navigate('/procurement/matching')}
                    />
                ) : !sessionMdaId ? (
                    /* MDA selection gate — main form is hidden until the
                       verifier picks an MDA for this session. Mirrors SAP
                       MIRO's Company Code prompt at MIRO transaction launch. */
                    <MdaSelectionScreen
                        mdas={mdas}
                        onSelect={(id) => {
                            setSessionMdaId(id);
                            // Reset form when entering a fresh MDA scope.
                            setForm({
                                purchase_order: '', goods_received_note: '',
                                invoice_reference: '', invoice_date: '',
                                invoice_amount: '', invoice_tax_amount: '',
                                invoice_subtotal: '', notes: '',
                            });
                            setError('');
                        }}
                    />
                ) : (
                    <form onSubmit={handlePost}>
                        {/* Sticky MDA banner — confirms the verifier's session
                            scope at all times, with one-click "Change MDA". */}
                        <SessionMdaBanner
                            mda={sessionMda}
                            onChange={() => {
                                // Only prompt for confirmation if the user has
                                // entered any data — otherwise just switch.
                                const dirty = !!(
                                    form.purchase_order || form.invoice_reference
                                    || form.invoice_amount || form.invoice_date
                                );
                                if (dirty) setShowChangeMdaConfirm(true);
                                else setSessionMdaId(null);
                            }}
                        />
                        <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: '1rem', alignItems: 'start' }}>

                            {/* LEFT — Source documents + invoice header + Post button */}
                            <div>
                                {/* Source Documents */}
                                <div style={card}>
                                    <p style={sectionTitle}><ClipboardList size={15} /> Source Documents</p>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                                        <div>
                                            {/* PO selector — type-to-search via SearchableSelect.
                                                Native <select> required scrolling the entire PO
                                                list; SearchableSelect lets the operator type the
                                                PO number (e.g. "PO-2026-00003") or vendor name
                                                and pick from a filtered list. ``label`` is the
                                                human match-text; ``sublabel`` shows status so
                                                Draft / Pending / Approved / Posted POs can be
                                                distinguished without opening each one. */}
                                            <label style={lbl}>Purchase Order <span style={{ color: '#ef4444' }}>*</span></label>
                                            {/* Only POs that have at least one Posted GRN are
                                                shown — Draft / Cancelled GRNs don't qualify, so a
                                                PO whose only receipts are unposted is correctly
                                                hidden. The Set-based ``postedGrnPoIds`` lookup
                                                keeps this O(P) regardless of how many GRNs
                                                exist in the tenant. */}
                                            <SearchableSelect
                                                options={pos
                                                    .filter((po: any) =>
                                                        postedGrnPoIds.has(String(po.id))
                                                        // Hide POs that already have a Posted
                                                        // Invoice Verification — Reverse the
                                                        // existing one first to re-enable.
                                                        && !postedInvoicePoIds.has(String(po.id))
                                                    )
                                                    .map((po: any) => ({
                                                        value: String(po.id),
                                                        label: `${po.po_number} — ${po.vendor_name || po.vendor}`,
                                                        sublabel: po.status ? `Status: ${po.status}` : undefined,
                                                    }))}
                                                value={form.purchase_order ? String(form.purchase_order) : ''}
                                                onChange={(v: string) => handlePoChange(v)}
                                                placeholder={postedGrnPoIds.size === 0
                                                    ? 'No POs with Posted GRNs available — receive goods first'
                                                    : 'Type PO number or vendor name...'}
                                                required
                                            />
                                        </div>
                                        <div>
                                            <label style={{ ...lbl, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                                <span>Goods Received Note (GRN)</span>
                                                {selectedPoId && filteredGrns.length > 0 && (
                                                    <span style={{
                                                        fontSize: '0.6rem', fontWeight: 700, padding: '0.1rem 0.45rem',
                                                        borderRadius: '9999px',
                                                        background: 'rgba(34,197,94,0.12)', color: '#15803d',
                                                        letterSpacing: '0.02em',
                                                    }}>
                                                        {filteredGrns.length} GRN{filteredGrns.length > 1 ? 's' : ''} found
                                                    </span>
                                                )}
                                            </label>
                                            {!selectedPoId && (
                                                <select style={{ ...inp, color: 'var(--color-text-muted)' }} disabled>
                                                    <option>— Select a PO first —</option>
                                                </select>
                                            )}
                                            {selectedPoId && filteredGrns.length === 0 && (
                                                <div style={{
                                                    ...inp, display: 'flex', alignItems: 'center', gap: '0.5rem',
                                                    color: '#b45309', background: 'rgba(245,158,11,0.07)',
                                                    border: '1.5px solid rgba(245,158,11,0.35)', cursor: 'default',
                                                }}>
                                                    <AlertTriangle size={14} color="#f59e0b" style={{ flexShrink: 0 }} />
                                                    <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                                                        No GRN posted for this PO yet
                                                    </span>
                                                </div>
                                            )}
                                            {selectedPoId && filteredGrns.length > 0 && (
                                                <>
                                                    <select style={{
                                                        ...inp,
                                                        borderColor: form.goods_received_note
                                                            ? 'rgba(34,197,94,0.5)'
                                                            : 'var(--color-border)',
                                                        background: form.goods_received_note
                                                            ? 'rgba(34,197,94,0.04)'
                                                            : 'var(--color-surface)',
                                                    }} value={form.goods_received_note}
                                                        onChange={e => set('goods_received_note', e.target.value)}>
                                                        {filteredGrns.length > 1 && <option value="">— Select GRN —</option>}
                                                        {filteredGrns.map((g: any) => (
                                                            <option key={g.id} value={g.id}>
                                                                {g.grn_number}{g.received_date ? ` — ${g.received_date}` : ''}{g.status ? ` (${g.status})` : ''}
                                                            </option>
                                                        ))}
                                                    </select>
                                                    {filteredGrns.length === 1 && form.goods_received_note && (
                                                        <p style={{ fontSize: '0.6rem', color: '#16a34a', margin: '0.2rem 0 0', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                                                            <CheckCircle size={10} /> Auto-linked — only GRN for this PO
                                                        </p>
                                                    )}
                                                </>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                {/* Invoice Details */}
                                <div style={card}>
                                    <p style={sectionTitle}><FileText size={15} /> Invoice Details</p>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                                        <div>
                                            <label style={lbl}>Invoice Reference <span style={{ color: '#ef4444' }}>*</span></label>
                                            <input type="text" style={inp} placeholder="e.g. INV-2026-001"
                                                value={form.invoice_reference}
                                                onChange={e => set('invoice_reference', e.target.value)} required />
                                        </div>
                                        <div>
                                            <label style={lbl}>Invoice Date <span style={{ color: '#ef4444' }}>*</span></label>
                                            <input type="date" style={inp} value={form.invoice_date}
                                                onChange={e => set('invoice_date', e.target.value)} required />
                                        </div>
                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                                            <div>
                                                <label style={lbl}>Subtotal</label>
                                                <input type="number" style={inp} placeholder="0.00"
                                                    min="0" step="0.01" value={form.invoice_subtotal}
                                                    onChange={e => set('invoice_subtotal', e.target.value)} />
                                            </div>
                                            <div>
                                                <label style={lbl}>Tax Amount {selectedTaxCode && <span style={{ fontWeight: 500, color: 'var(--color-text-muted)', textTransform: 'none', letterSpacing: 0 }}>(auto)</span>}</label>
                                                <input type="number" style={inp} placeholder="0.00"
                                                    min="0" step="0.01" value={form.invoice_tax_amount}
                                                    disabled={!!selectedTaxCode}
                                                    onChange={e => set('invoice_tax_amount', e.target.value)} />
                                            </div>
                                        </div>
                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                                            <div>
                                                <label style={lbl}>VAT / Tax Code</label>
                                                <select style={inp} value={form.tax_code}
                                                    onChange={e => set('tax_code', e.target.value)}>
                                                    <option value="">— none —</option>
                                                    {taxCodes.map(tc => (
                                                        <option key={tc.id} value={tc.id}>
                                                            {tc.code} · {tc.name} ({tc.rate}%)
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>
                                            <div>
                                                <label style={lbl}>
                                                    Withholding Tax
                                                    {poDetail?.vendor_wht_code && !form.wht_exempt && (
                                                        <span style={{ fontWeight: 500, color: 'var(--color-text-muted)', textTransform: 'none', letterSpacing: 0, marginLeft: '0.3rem' }}>
                                                            (vendor default)
                                                        </span>
                                                    )}
                                                </label>
                                                <select style={{ ...inp, opacity: form.wht_exempt ? 0.5 : 1 }}
                                                    value={form.withholding_tax}
                                                    disabled={form.wht_exempt}
                                                    onChange={e => set('withholding_tax', e.target.value)}>
                                                    <option value="">— none —</option>
                                                    {whtCodes.map(w => (
                                                        <option key={w.id} value={w.id}>
                                                            {w.code} · {w.name} ({w.rate}%)
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>
                                        </div>
                                        {/* WHT exemption control — mirrors SAP BP transaction exemption */}
                                        {(form.withholding_tax || form.wht_exempt || poDetail?.vendor_wht_exempt) && (
                                            <div style={{
                                                padding: '0.6rem 0.75rem',
                                                borderRadius: '6px',
                                                background: form.wht_exempt ? 'rgba(100,116,139,0.08)' : 'rgba(234,179,8,0.06)',
                                                border: `1px solid ${form.wht_exempt ? 'rgba(100,116,139,0.3)' : 'rgba(234,179,8,0.3)'}`,
                                                display: 'flex',
                                                flexDirection: 'column',
                                                gap: '0.4rem',
                                            }}>
                                                <label style={{
                                                    display: 'flex', alignItems: 'center', gap: '0.4rem',
                                                    fontSize: '0.72rem', fontWeight: 600,
                                                    color: 'var(--color-text)', cursor: 'pointer',
                                                }}>
                                                    <input type="checkbox"
                                                        checked={form.wht_exempt}
                                                        onChange={e => setForm(prev => ({
                                                            ...prev,
                                                            wht_exempt: e.target.checked,
                                                            wht_exempt_reason: e.target.checked ? prev.wht_exempt_reason : '',
                                                        }))}
                                                    />
                                                    Exempt this transaction from Withholding Tax
                                                    {poDetail?.vendor_wht_exempt && (
                                                        <span style={{ fontWeight: 500, color: '#64748b', textTransform: 'uppercase', fontSize: '0.6rem', letterSpacing: '0.05em' }}>
                                                            (vendor is exempt)
                                                        </span>
                                                    )}
                                                </label>
                                                {form.wht_exempt && (
                                                    <input type="text" style={{ ...inp, fontSize: '0.7rem' }}
                                                        placeholder="Reason for WHT exemption (audit trail)"
                                                        value={form.wht_exempt_reason}
                                                        onChange={e => set('wht_exempt_reason', e.target.value)} />
                                                )}
                                                {!form.wht_exempt && selectedWht && whtPreview > 0 && (
                                                    <div style={{
                                                        display: 'flex', justifyContent: 'space-between',
                                                        fontSize: '0.7rem', color: 'var(--color-text-muted)',
                                                    }}>
                                                        <span>WHT to be withheld at payment ({selectedWht.rate}%):</span>
                                                        <strong style={{ color: '#ca8a04' }}>
                                                            {formatCurrency(whtPreview)}
                                                        </strong>
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                        <div>
                                            <label style={lbl}>Invoice Total <span style={{ color: '#ef4444' }}>*</span></label>
                                            <input type="number" style={{ ...inp, fontWeight: 600, fontSize: 'var(--text-base)' }}
                                                placeholder="0.00" min="0.01" step="0.01"
                                                value={form.invoice_amount}
                                                onChange={e => set('invoice_amount', e.target.value)} required />
                                            {selectedPoId && poDetail && form.invoice_amount === String(parseFloat(poDetail.total_amount || 0)) && (
                                                <p style={{ fontSize: '0.6rem', color: '#16a34a', margin: '0.2rem 0 0', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                                                    <Sparkles size={10} /> Auto-filled from PO — adjust if the supplier billed a different amount
                                                </p>
                                            )}
                                        </div>
                                        <div>
                                            <label style={lbl}>Notes</label>
                                            <textarea style={{ ...inp, resize: 'vertical' }} rows={2}
                                                value={form.notes}
                                                onChange={e => set('notes', e.target.value)} />
                                        </div>
                                    </div>
                                </div>

                                {/* Down Payment (collapsed by default) */}
                                {selectedPoId && dpr && (
                                    <div style={{
                                        ...card,
                                        border: dpEnabled ? '1.5px solid rgba(99,102,241,0.4)' : '1px solid var(--color-border)',
                                        background: dpEnabled ? 'rgba(99,102,241,0.03)' : 'var(--color-surface)',
                                    }}>
                                        <button type="button" onClick={() => setDpExpanded(v => !v)} style={{
                                            width: '100%', background: 'none', border: 'none', cursor: 'pointer',
                                            display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 0,
                                        }}>
                                            <p style={{ ...sectionTitle, margin: 0, color: dpEnabled ? '#4f46e5' : 'var(--color-text)' }}>
                                                <CreditCard size={15} />
                                                Down Payment Matching
                                                {dpEnabled && (
                                                    <span style={{
                                                        marginLeft: '0.4rem', fontSize: '0.6rem', fontWeight: 700,
                                                        padding: '0.1rem 0.45rem', borderRadius: '9999px',
                                                        background: 'rgba(99,102,241,0.12)', color: '#4f46e5',
                                                    }}>Applied</span>
                                                )}
                                            </p>
                                            {dpExpanded
                                                ? <ChevronUp size={15} color="var(--color-text-muted)" />
                                                : <ChevronDown size={15} color="var(--color-text-muted)" />}
                                        </button>
                                        {dpExpanded && (
                                            <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                                                <div style={{
                                                    padding: '0.6rem 0.75rem', borderRadius: '6px',
                                                    background: 'rgba(16,185,129,0.07)', border: '1px solid rgba(16,185,129,0.2)',
                                                    fontSize: 'var(--text-xs)',
                                                }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                                                        <span style={{ color: 'var(--color-text-muted)' }}>Request #</span>
                                                        <span style={{ fontWeight: 600 }}>{dpr.request_number}</span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: 'var(--color-text-muted)' }}>Available Balance</span>
                                                        <span style={{ fontWeight: 700, color: '#059669' }}>
                                                            {availableAdvance !== null ? formatCurrency(availableAdvance) : '—'}
                                                        </span>
                                                    </div>
                                                </div>
                                                <label style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 500 }}>
                                                    <input type="checkbox" checked={dpEnabled}
                                                        onChange={e => {
                                                            setDpEnabled(e.target.checked);
                                                            if (!e.target.checked) setDpAmount('');
                                                        }}
                                                        style={{ width: '16px', height: '16px', cursor: 'pointer', accentColor: '#4f46e5' }} />
                                                    Apply down payment to this invoice
                                                </label>
                                                {dpEnabled && (
                                                    <>
                                                        <div>
                                                            <label style={lbl}>Amount to Apply</label>
                                                            <input type="number" style={inp} placeholder={defaultDpAmount || '0.00'}
                                                                min="0.01" step="0.01"
                                                                max={availableAdvance !== null ? availableAdvance : undefined}
                                                                value={dpAmount}
                                                                onChange={e => setDpAmount(e.target.value)} />
                                                        </div>
                                                        {netPayable !== null && (
                                                            <div style={{
                                                                padding: '0.6rem 0.75rem', borderRadius: '6px',
                                                                background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.2)',
                                                            }}>
                                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                                        <Minus size={12} /> Net Payable to Vendor
                                                                    </span>
                                                                    <span style={{ fontWeight: 800, fontSize: 'var(--text-base)', color: '#4f46e5', fontFamily: 'monospace' }}>
                                                                        {formatCurrency(netPayable)}
                                                                    </span>
                                                                </div>
                                                            </div>
                                                        )}
                                                    </>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Action buttons — Cancel | Simulate | Post Invoice */}
                                <div style={{ display: 'flex', gap: '0.6rem', justifyContent: 'flex-end', paddingTop: '0.25rem', flexWrap: 'wrap' }}>
                                    <button type="button" onClick={() => navigate('/procurement/matching')}
                                        style={{
                                            padding: '0.55rem 1.25rem', borderRadius: '6px',
                                            border: '1px solid var(--color-border)', background: 'none',
                                            color: 'var(--color-text)', cursor: 'pointer',
                                            fontSize: 'var(--text-sm)', fontWeight: 500,
                                        }}>
                                        Cancel
                                    </button>
                                    <button type="button" onClick={handleSimulate} disabled={simulate.isPending}
                                        title="Preview the GL journal entries without posting"
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: '0.4rem',
                                            padding: '0.55rem 1.25rem', borderRadius: '6px',
                                            background: 'rgba(79,70,229,0.08)', color: '#4f46e5',
                                            border: '1px solid rgba(79,70,229,0.3)',
                                            cursor: simulate.isPending ? 'not-allowed' : 'pointer',
                                            fontSize: 'var(--text-sm)', fontWeight: 600,
                                            opacity: simulate.isPending ? 0.7 : 1,
                                        }}>
                                        <Calculator size={15} />
                                        {simulate.isPending ? 'Simulating…' : 'Simulate'}
                                    </button>
                                    <button type="submit" disabled={verifyAndPost.isPending}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: '0.4rem',
                                            padding: '0.55rem 1.6rem', borderRadius: '6px',
                                            background: '#22c55e', color: '#fff',
                                            border: 'none', cursor: verifyAndPost.isPending ? 'not-allowed' : 'pointer',
                                            fontSize: 'var(--text-sm)', fontWeight: 700,
                                            opacity: verifyAndPost.isPending ? 0.7 : 1,
                                        }}>
                                        <BookOpen size={15} />
                                        {verifyAndPost.isPending ? 'Posting…' : 'Post Invoice'}
                                    </button>
                                </div>
                            </div>

                            {/* RIGHT — Amount summary + PO/GRN detail */}
                            <div>
                                <div style={{
                                    position: 'sticky', top: '1rem',
                                    background: 'linear-gradient(135deg, rgba(25,30,106,0.05) 0%, rgba(79,70,229,0.06) 100%)',
                                    border: '1.5px solid rgba(79,70,229,0.2)',
                                    borderRadius: '12px', padding: '1rem 1.1rem',
                                    marginBottom: '1rem', boxShadow: '0 2px 12px rgba(79,70,229,0.08)',
                                }}>
                                    <p style={{ ...sectionTitle, color: 'var(--color-primary)', marginBottom: '0.75rem' }}>
                                        Amount Summary
                                    </p>
                                    {(poTotal === null && grnTotal === null && invoiceAmt === null) ? (
                                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: 0, fontStyle: 'italic' }}>
                                            Select a PO and enter invoice details to see comparison.
                                        </p>
                                    ) : (
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
                                            {poTotal !== null && (
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                                    <span style={{ color: 'var(--color-text-muted)' }}>PO Total</span>
                                                    <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>{formatCurrency(poTotal)}</span>
                                                </div>
                                            )}
                                            {grnTotal !== null && (
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                                    <span style={{ color: 'var(--color-text-muted)' }}>GRN Value (received)</span>
                                                    <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>{formatCurrency(grnTotal)}</span>
                                                </div>
                                            )}
                                            {invoiceAmt !== null && (
                                                <>
                                                    <div style={{
                                                        borderTop: '1px solid rgba(79,70,229,0.15)',
                                                        marginTop: '0.2rem', paddingTop: '0.45rem',
                                                        display: 'flex', justifyContent: 'space-between',
                                                        fontSize: 'var(--text-sm)',
                                                    }}>
                                                        <span style={{ fontWeight: 600 }}>Invoice Total</span>
                                                        <span style={{ fontWeight: 800, fontFamily: 'monospace', fontSize: 'var(--text-base)', color: 'var(--color-primary)' }}>
                                                            {formatCurrency(invoiceAmt)}
                                                        </span>
                                                    </div>
                                                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', paddingTop: '0.15rem' }}>
                                                        {grnTotal !== null && (
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                                <span>Inv vs GRN:</span>
                                                                {/* Subtotal-vs-GRN — both ex-VAT */}
                                                                <VariancePill base={grnTotal} actual={invoiceForGrnCompare} />
                                                            </div>
                                                        )}
                                                        {poTotal !== null && (
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                                <span>Inv vs PO:</span>
                                                                {/* Gross-vs-gross — PO contracts include VAT */}
                                                                <VariancePill base={poTotal} actual={invoiceAmt} />
                                                            </div>
                                                        )}
                                                    </div>
                                                </>
                                            )}
                                        </div>
                                    )}
                                </div>

                                {/* PO Detail card */}
                                {poLoading && (
                                    <div style={{ ...card, color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                        Loading PO details…
                                    </div>
                                )}
                                {poDetail && (
                                    <div style={card}>
                                        <p style={sectionTitle}><Package size={15} /> Purchase Order — {poDetail.po_number}</p>
                                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem 1rem', marginBottom: '1rem' }}>
                                            {[
                                                { label: 'Vendor', value: poDetail.vendor_name },
                                                { label: 'Order Date', value: poDetail.order_date },
                                                { label: 'Expected Delivery', value: poDetail.expected_delivery_date || '—' },
                                                { label: 'Status', value: poDetail.status },
                                                { label: 'Payment Terms', value: poDetail.payment_terms || '—' },
                                                { label: 'PO Total', value: formatCurrency(parseFloat(poDetail.total_amount || 0)) },
                                            ].map(({ label, value }) => (
                                                <div key={label}>
                                                    <div style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '0.15rem' }}>{label}</div>
                                                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{value}</div>
                                                </div>
                                            ))}
                                        </div>
                                        <div style={{ overflowX: 'auto', borderRadius: '6px', border: '1px solid var(--color-border)' }}>
                                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)' }}>
                                                <thead>
                                                    <tr>
                                                        <th style={th}>Description</th>
                                                        <th style={{ ...th, textAlign: 'right' }}>PO Qty</th>
                                                        <th style={{ ...th, textAlign: 'right' }}>Received</th>
                                                        <th style={{ ...th, textAlign: 'right' }}>Pending</th>
                                                        <th style={{ ...th, textAlign: 'right' }}>Unit Price</th>
                                                        <th style={{ ...th, textAlign: 'right' }}>PO Amount</th>
                                                        {selectedGrnId && <th style={{ ...th, textAlign: 'right' }}>GRN Amount</th>}
                                                        {selectedGrnId && <th style={{ ...th, textAlign: 'center' }}>Variance</th>}
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {comparisonLines.map((line: any) => (
                                                        <tr key={line.id}>
                                                            <td style={td}>
                                                                <div style={{ fontWeight: 500 }}>{line.item_description}</div>
                                                            </td>
                                                            <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace' }}>{line.poQty}</td>
                                                            <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace', color: line.is_fully_received ? '#22c55e' : 'var(--color-text)' }}>
                                                                {parseFloat(line.quantity_received || 0)}
                                                            </td>
                                                            <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace', color: parseFloat(line.pending_quantity) > 0 ? '#f59e0b' : '#22c55e' }}>
                                                                {parseFloat(line.pending_quantity || 0)}
                                                            </td>
                                                            <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace' }}>{formatCurrency(line.poPrice)}</td>
                                                            <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace', fontWeight: 600 }}>{formatCurrency(line.poAmt)}</td>
                                                            {selectedGrnId && (
                                                                <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace' }}>
                                                                    {grnLoading ? '…' : line.grnAmt !== null ? formatCurrency(line.grnAmt) : '—'}
                                                                </td>
                                                            )}
                                                            {selectedGrnId && (
                                                                <td style={{ ...td, textAlign: 'center' }}>
                                                                    {line.grnAmt !== null
                                                                        ? <VariancePill base={line.poAmt} actual={line.grnAmt} />
                                                                        : <span style={{ color: 'var(--color-text-muted)', fontSize: '0.65rem' }}>No GRN</span>}
                                                                </td>
                                                            )}
                                                        </tr>
                                                    ))}
                                                </tbody>
                                                <tfoot>
                                                    <tr style={{ borderTop: '2px solid var(--color-border)', background: 'rgba(0,0,0,0.02)' }}>
                                                        <td style={{ ...td, fontWeight: 700 }} colSpan={4}>Total</td>
                                                        <td style={td} />
                                                        <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>
                                                            {formatCurrency(poTotal ?? 0)}
                                                        </td>
                                                        {selectedGrnId && (
                                                            <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>
                                                                {grnTotal !== null ? formatCurrency(grnTotal) : '—'}
                                                            </td>
                                                        )}
                                                        {selectedGrnId && (
                                                            <td style={{ ...td, textAlign: 'center' }}>
                                                                {grnTotal !== null && poTotal !== null && <VariancePill base={poTotal} actual={grnTotal} />}
                                                            </td>
                                                        )}
                                                    </tr>
                                                </tfoot>
                                            </table>
                                        </div>
                                        {/* Receipt status indicators */}
                                        {isPartiallyReceived && (
                                            <div style={{
                                                marginTop: '0.75rem', padding: '0.55rem 0.75rem',
                                                background: 'rgba(245,158,11,0.07)',
                                                border: '1px solid rgba(245,158,11,0.3)',
                                                borderRadius: '6px',
                                                fontSize: 'var(--text-xs)', color: '#92400e',
                                                display: 'flex', alignItems: 'center', gap: '0.4rem',
                                            }}>
                                                <AlertTriangle size={12} color="#d97706" />
                                                <span>This PO is <strong>partially received</strong>. You'll be asked to confirm before posting.</span>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {!selectedPoId && (
                                    <div style={{
                                        ...card, textAlign: 'center', padding: '3rem 2rem',
                                        color: 'var(--color-text-muted)',
                                        border: '2px dashed var(--color-border)',
                                        background: 'transparent',
                                    }}>
                                        <Package size={40} style={{ margin: '0 auto 0.75rem', opacity: 0.3 }} />
                                        <p style={{ margin: 0, fontSize: 'var(--text-sm)' }}>
                                            Select a Purchase Order to begin verification
                                        </p>
                                    </div>
                                )}
                            </div>
                        </div>
                    </form>
                )}

                {/* ── Modals — backend gate prompts ─────────────────── */}
                {partialModal && (
                    <ConfirmModal
                        title="Partial Receipt — Confirm Post"
                        body={
                            <>
                                <p style={{ margin: '0 0 0.6rem' }}>
                                    Goods on this Purchase Order have been only <strong>partially received</strong>.
                                </p>
                                <p style={{ margin: 0, color: 'var(--color-text-muted)' }}>
                                    Posting this invoice now will book the GL entry for what's been received.
                                    The remaining quantity will need a separate GRN + invoice.
                                </p>
                            </>
                        }
                        confirmLabel="Yes, Post Partial Invoice"
                        confirmColor="#f59e0b"
                        onConfirm={() => {
                            setAcknowledgePartial(true);
                            submitToBackend({ acknowledge_partial: true });
                        }}
                        onCancel={() => setPartialModal(false)}
                    />
                )}

                {/* "Change MDA" confirmation modal — clears in-progress
                    selections because they belong to the old MDA. */}
                {showChangeMdaConfirm && (
                    <ConfirmModal
                        title="Change MDA Session?"
                        body={
                            <>
                                <p style={{ margin: '0 0 0.6rem' }}>
                                    Switching MDA will clear the currently selected
                                    Purchase Order, GRN, and invoice details — they
                                    belong to the previous MDA's appropriation.
                                </p>
                                <p style={{ margin: 0, color: 'var(--color-text-muted)' }}>
                                    You'll be returned to the MDA selection screen.
                                </p>
                            </>
                        }
                        confirmLabel="Yes, Change MDA"
                        confirmColor="#f59e0b"
                        onConfirm={() => {
                            setShowChangeMdaConfirm(false);
                            // Wipe everything that was scoped to the old MDA.
                            setForm({
                                purchase_order: '', goods_received_note: '',
                                invoice_reference: '', invoice_date: '',
                                invoice_amount: '', invoice_tax_amount: '',
                                invoice_subtotal: '', notes: '',
                            });
                            setDpEnabled(false);
                            setDpAmount('');
                            setError('');
                            setSessionMdaId(null);  // re-opens the MDA selection screen
                        }}
                        onCancel={() => setShowChangeMdaConfirm(false)}
                    />
                )}

                {/* Warrant Ceiling Exceeded — hard stop, no override available.
                    Verifier must contact treasury to release additional warrants
                    (or reduce the invoice amount to fit). */}
                {warrantModal && (
                    <WarrantExceededModal
                        info={warrantModal}
                        formatCurrency={formatCurrency}
                        onClose={() => setWarrantModal(null)}
                        onGoToWarrants={() => {
                            setWarrantModal(null);
                            navigate('/budget/warrants');
                        }}
                    />
                )}

                {/* Simulation modal — proposed GL journal preview, no writes */}
                {simulation && (
                    <SimulationModal
                        sim={simulation}
                        formatCurrency={formatCurrency}
                        onClose={() => setSimulation(null)}
                        onPost={() => { setSimulation(null); submitToBackend(); }}
                        posting={verifyAndPost.isPending}
                    />
                )}

                {varianceModal && (
                    <ConfirmModal
                        title={`Variance ${parseFloat(varianceModal.pct).toFixed(2)}% — Above 5% Threshold`}
                        body={
                            <>
                                <p style={{ margin: '0 0 0.6rem' }}>
                                    The invoice variance ({formatCurrency(parseFloat(varianceModal.amount))})
                                    exceeds the configured 5% threshold.
                                </p>
                                <p style={{ margin: 0, color: 'var(--color-text-muted)' }}>
                                    Provide a reason to override and post — this will be recorded on the audit trail.
                                </p>
                            </>
                        }
                        confirmLabel="Override & Post"
                        confirmColor="#ef4444"
                        extraInput={{
                            label: 'Variance Reason (required)',
                            value: varianceReason,
                            onChange: setVarianceReason,
                            placeholder: 'e.g. Vendor billed an additional fee per contract clause 3.2',
                        }}
                        onConfirm={() => {
                            if (!varianceReason.trim()) return;
                            submitToBackend({ variance_reason: varianceReason.trim(), acknowledge_partial: acknowledgePartial });
                        }}
                        onCancel={() => setVarianceModal(null)}
                    />
                )}
            </div>
        </AccountingLayout>
    );
}
