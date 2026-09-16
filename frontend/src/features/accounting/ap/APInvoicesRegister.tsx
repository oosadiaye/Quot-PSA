import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Receipt, Search, Eye, ExternalLink, BookOpen, X,
    Building2, Calendar, FileText, ClipboardCheck, Layers, CheckCircle,
} from 'lucide-react';
import { useVendorInvoices, useApproveVendorInvoice, useCreateDraftVoucherFromInvoice } from '../hooks/useAccountingEnhancements';
import { useInvoiceMatchings } from '../../procurement/hooks/useProcurement';
import { useJournal } from '../hooks/useJournal';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import StatusBadge from '../components/shared/StatusBadge';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import { useDialog } from '../../../hooks/useDialog';
import logger from '../../../utils/logger';

// ───────────────────────────────────────────────────────────────────────────
// AP Invoices Register — a single central list of every payable document,
// merging two sources that otherwise live in different apps:
//   • VendorInvoice          → /accounting/vendor-invoices/   (Accounts Payable)
//   • InvoiceMatching        → /procurement/invoice-matching/ (Invoice Verification)
//
// An InvoiceMatching that has been turned into an AP invoice points back to it
// (matching.vendor_invoice). That link classifies each row's SOURCE:
//   • direct        — an AP invoice raised directly, no 3-way match
//   • verified      — an AP invoice that came out of a 3-way match
//   • verification  — a verification not yet converted to an AP invoice
// ───────────────────────────────────────────────────────────────────────────

type Source = 'direct' | 'verified' | 'verification';

interface RegisterRow {
    key: string;
    source: Source;
    docNumber: string;
    vendorName: string;
    reference: string;
    date: string | null;
    amount: number;
    status: string;
    poNumber: string | null;
    verificationNumber: string | null;
    matchingId: number | null;   // → /procurement/matching/:id
    journalId: number | null;    // GL journal behind the document
    invoiceRaw: any | null;      // present for VendorInvoice rows (drives the detail modal)
}

/** DRF-paginated ({results}) or bare list — return an array either way. */
function toArray(payload: any): any[] {
    if (Array.isArray(payload)) return payload;
    if (Array.isArray(payload?.results)) return payload.results;
    return [];
}

const fmtDate = (d?: string | null) =>
    d ? new Date(d).toLocaleDateString('en-GB') : '—';

const SOURCE_META: Record<Source, { label: string; bg: string; color: string; border: string }> = {
    direct:       { label: 'Direct AP',    bg: '#eef2ff', color: '#4338ca', border: '#c7d2fe' },
    verified:     { label: 'Verified',     bg: '#ecfdf5', color: '#047857', border: '#a7f3d0' },
    verification: { label: 'Verification', bg: '#fffbeb', color: '#b45309', border: '#fde68a' },
};

export default function APInvoicesRegister() {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();

    const [search, setSearch] = useState('');
    const [sourceFilter, setSourceFilter] = useState<'all' | Source>('all');
    const [statusFilter, setStatusFilter] = useState('');
    const [viewing, setViewing] = useState<RegisterRow | null>(null);

    // Workflow actions moved here from the AP Invoice page: the register is
    // now where an invoice is approved/posted and turned into a payment.
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
    const [budgetError, setBudgetError] = useState('');
    const approveInvoice = useApproveVendorInvoice();
    const createDraftPV = useCreateDraftVoucherFromInvoice();
    const { showConfirm } = useDialog();
    const flash = (msg: string, ok = true) => { setToast({ msg, ok }); setTimeout(() => setToast(null), 5000); };

    // Pull the full set from both endpoints. page_size is a hint for the
    // paginated AP endpoint so the register stays "complete" for a tenant;
    // the verification endpoint returns a bare list today.
    const { data: invoiceData, isLoading: invLoading } = useVendorInvoices({ page_size: 500 });
    const { data: matchingData, isLoading: matchLoading } = useInvoiceMatchings({ page_size: 500 });

    const rows = useMemo<RegisterRow[]>(() => {
        const invoices = toArray(invoiceData);
        const matchings = toArray(matchingData);

        // Which AP invoices originated from a 3-way match, and the matching
        // that produced each — so a verified row can cross-link to it.
        const matchingByInvoiceId = new Map<number, any>();
        for (const m of matchings) {
            if (m.vendor_invoice) matchingByInvoiceId.set(m.vendor_invoice, m);
        }

        const invoiceRows: RegisterRow[] = invoices.map((inv) => {
            const match = matchingByInvoiceId.get(inv.id);
            return {
                key: `vi-${inv.id}`,
                source: match ? 'verified' : 'direct',
                docNumber: inv.invoice_number,
                vendorName: inv.vendor_name || (inv.vendor ? `#${inv.vendor}` : '—'),
                reference: inv.reference || '',
                date: inv.invoice_date ?? null,
                amount: parseFloat(inv.total_amount || '0'),
                status: inv.status,
                poNumber: match?.po_number ?? null,
                verificationNumber: match?.verification_number ?? null,
                matchingId: match?.id ?? null,
                journalId: inv.journal_entry ?? null,
                invoiceRaw: inv,
            };
        });

        // Verifications with no AP invoice yet — still owed, not yet booked.
        const pendingRows: RegisterRow[] = matchings
            .filter((m) => !m.vendor_invoice)
            .map((m) => ({
                key: `im-${m.id}`,
                source: 'verification' as const,
                docNumber: m.verification_number,
                vendorName: m.vendor_name || (m.vendor_id ? `#${m.vendor_id}` : '—'),
                reference: m.invoice_reference || '',
                date: m.invoice_date ?? null,
                amount: parseFloat(m.invoice_amount || '0'),
                status: m.status,
                poNumber: m.po_number ?? null,
                verificationNumber: m.verification_number ?? null,
                matchingId: m.id,
                journalId: m.journal_entry_id ?? null,
                invoiceRaw: null,
            }));

        return [...invoiceRows, ...pendingRows].sort((a, b) =>
            (b.date || '').localeCompare(a.date || ''),
        );
    }, [invoiceData, matchingData]);

    const statuses = useMemo(
        () => Array.from(new Set(rows.map((r) => r.status))).filter(Boolean).sort(),
        [rows],
    );

    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase();
        return rows.filter((r) => {
            if (sourceFilter !== 'all' && r.source !== sourceFilter) return false;
            if (statusFilter && r.status !== statusFilter) return false;
            if (!q) return true;
            return [r.docNumber, r.vendorName, r.reference, r.poNumber, r.verificationNumber]
                .some((v) => (v || '').toLowerCase().includes(q));
        });
    }, [rows, search, sourceFilter, statusFilter]);

    const totalValue = filtered.reduce((s, r) => s + r.amount, 0);
    const verifiedCount = rows.filter((r) => r.source === 'verified').length;
    const pendingCount = rows.filter((r) => r.source === 'verification').length;

    if (invLoading || matchLoading) {
        return <LoadingScreen message="Loading AP invoices register…" />;
    }

    // Approve & post an invoice to the GL. Mirrors the AP Invoice page:
    // a structured budget/warrant rejection is surfaced in the banner, any
    // other failure as a toast.
    const handleApprove = async (invoiceId: number) => {
        if (!await showConfirm('Approve & post this vendor invoice to the GL?')) return;
        setBudgetError('');
        try {
            const resp: any = await approveInvoice.mutateAsync(invoiceId);
            flash(resp?.journal_reference ? `Posted. Journal ${resp.journal_reference}` : (resp?.status || 'Invoice approved and posted.'));
        } catch (error: any) {
            const data = error?.response?.data;
            logger.error('Failed to approve invoice:', error);
            if (data?.appropriation_exceeded || data?.warrant_exceeded || data?.budget) {
                const msg = data.error || (Array.isArray(data.budget) ? data.budget.join(' ') : data.budget) || 'Budget validation failed.';
                setBudgetError(msg);
                setTimeout(() => window.scrollTo({ top: 0, behavior: 'smooth' }), 50);
            } else {
                flash(data?.error || data?.detail || error?.message || 'Failed to approve invoice.', false);
            }
        }
    };

    // Auto-create a draft Payment Voucher from the invoice and open it.
    const handleCreatePV = async (invoiceId: number) => {
        try {
            const result: any = await createDraftPV.mutateAsync({ invoiceId });
            const pv = result.payment_voucher;
            flash(`Draft PV ${pv.voucher_number} created — opening for review.`, true);
            navigate(`/accounting/payment-vouchers/${pv.id}`);
        } catch (err: any) {
            flash(err?.response?.data?.error ?? err?.message ?? 'Failed to create draft PV.', false);
        }
    };

    return (
        <AccountingLayout>
            <div>
                {budgetError && (
                    <div style={{ padding: '0.85rem 1.1rem', marginBottom: '1rem', background: '#fef2f2', color: '#991b1b', border: '1.5px solid #fecaca', borderLeft: '5px solid #dc2626', borderRadius: 8, fontSize: 'var(--text-sm)', whiteSpace: 'pre-wrap' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.3rem' }}>
                            <strong style={{ fontSize: 'var(--text-base)' }}>⚠ Budget Validation Failed</strong>
                            <button onClick={() => setBudgetError('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#991b1b', fontSize: 18, lineHeight: 1 }}>×</button>
                        </div>
                        {budgetError}
                    </div>
                )}
                {toast && (
                    <div style={{ padding: '0.7rem 0.95rem', marginBottom: '1rem', borderRadius: 8, background: toast.ok ? '#ecfdf5' : '#fef2f2', border: `1px solid ${toast.ok ? '#a7f3d0' : '#fecaca'}`, color: toast.ok ? '#065f46' : '#991b1b', fontSize: 'var(--text-sm)', fontWeight: 500 }}>
                        {toast.msg}
                    </div>
                )}

                <PageHeader
                    title="AP Invoices Register"
                    subtitle="Every payable document in one place — direct AP invoices and 3-way verified invoices"
                    icon={<Layers size={22} />}
                />

                {/* Summary cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '1.25rem', margin: '1.25rem 0 1.75rem' }}>
                    <SummaryCard label="Documents" value={String(filtered.length)} />
                    <SummaryCard label="Total Value" value={formatCurrency(totalValue)} accent />
                    <SummaryCard label="Verified (3-way)" value={String(verifiedCount)} />
                    <SummaryCard label="Pending Verification" value={String(pendingCount)} warn={pendingCount > 0} />
                </div>

                {/* Filters */}
                <div className="card" style={{ padding: '0.85rem 1rem', marginBottom: '1.25rem', display: 'flex', gap: '0.85rem', alignItems: 'center', flexWrap: 'wrap' }}>
                    <div style={{ position: 'relative', flex: '1 1 240px', minWidth: 0 }}>
                        <Search size={16} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                        <input
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Search invoice #, verification #, vendor, PO, reference…"
                            style={{ width: '100%', padding: '0.55rem 0.75rem 0.55rem 2rem', borderRadius: 8, border: '1px solid var(--color-border)' }}
                        />
                    </div>
                    {/* Explicit width beats the global `select { width: 100% }` in
                        index.css, which would otherwise force each select onto its
                        own row. flex:0 0 auto keeps them from growing. */}
                    <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value as 'all' | Source)} style={{ flex: '0 0 auto', width: 190 }}>
                        <option value="all">All Sources</option>
                        <option value="direct">Direct AP</option>
                        <option value="verified">Verified (3-way)</option>
                        <option value="verification">Verification (pending)</option>
                    </select>
                    <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ flex: '0 0 auto', width: 170 }}>
                        <option value="">All Statuses</option>
                        {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                </div>

                {/* Register table — horizontally scrollable so the action
                    column is never clipped on narrower viewports. */}
                <div className="card" style={{ padding: 0, overflowX: 'auto', overflowY: 'hidden' }}>
                    <table data-plain-table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                {['Source', 'Document #', 'Vendor', 'Reference', 'Date', 'Status', 'PO #', 'Amount', ''].map((h, i) => (
                                    <th key={h || i} style={{ padding: '0.85rem 1.1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', textAlign: h === 'Amount' ? 'right' : 'left', whiteSpace: 'nowrap' }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((row) => {
                                const meta = SOURCE_META[row.source];
                                return (
                                    <tr key={row.key} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.8rem 1.1rem' }}>
                                            <span style={{ display: 'inline-block', padding: '0.15rem 0.6rem', borderRadius: 999, fontSize: 11, fontWeight: 700, background: meta.bg, color: meta.color, border: `1px solid ${meta.border}`, whiteSpace: 'nowrap' }}>
                                                {meta.label}
                                            </span>
                                        </td>
                                        <td style={{ padding: '0.8rem 1.1rem', maxWidth: 210 }}>
                                            <span title={row.docNumber} style={{ display: 'block', fontWeight: 600, color: 'var(--color-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.docNumber}</span>
                                            {row.source === 'verified' && row.verificationNumber && (
                                                <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2 }}>
                                                    via {row.verificationNumber}
                                                </div>
                                            )}
                                        </td>
                                        <td style={{ padding: '0.8rem 1.1rem' }}>{row.vendorName}</td>
                                        <td title={row.reference} style={{ padding: '0.8rem 1.1rem', color: 'var(--color-text-muted)', maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.reference || '—'}</td>
                                        <td style={{ padding: '0.8rem 1.1rem', whiteSpace: 'nowrap' }}>{fmtDate(row.date)}</td>
                                        <td style={{ padding: '0.8rem 1.1rem' }}><StatusBadge status={row.status} /></td>
                                        <td style={{ padding: '0.8rem 1.1rem', fontFamily: 'monospace', fontSize: 'var(--text-xs)' }}>{row.poNumber || '—'}</td>
                                        <td style={{ padding: '0.8rem 1.1rem', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>{formatCurrency(row.amount)}</td>
                                        <td style={{ padding: '0.8rem 1.1rem', textAlign: 'right', whiteSpace: 'nowrap' }}>
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', alignItems: 'stretch', width: 132, marginLeft: 'auto' }}>
                                                {row.invoiceRaw ? (() => {
                                                    // Same (status, has-journal) decision as the AP Invoice page:
                                                    // needsPost → not yet in the GL; canPay → journal exists.
                                                    const inv = row.invoiceRaw;
                                                    const needsPost = inv.status === 'Draft' || (inv.status === 'Approved' && !inv.journal_entry);
                                                    const canPay = inv.status === 'Posted' || (inv.status === 'Approved' && !!inv.journal_entry);
                                                    return (
                                                        <>
                                                            {needsPost && (
                                                                <button className="btn btn-primary" style={btnSm} onClick={() => handleApprove(inv.id)} title="Approve this invoice, post the GL journal, and mark it Posted for Treasury to pay">
                                                                    <CheckCircle size={14} /> Approve &amp; Post
                                                                </button>
                                                            )}
                                                            {canPay && (inv.payment_voucher_id ? (
                                                                <button style={{ ...btnSm, background: '#ecfdf5', border: '1px solid #a7f3d0', color: '#047857' }} onClick={() => navigate(`/accounting/payment-vouchers/${inv.payment_voucher_id}`)} title={`A Payment Voucher (${inv.payment_voucher_number ?? ''}, status ${inv.payment_voucher_status ?? ''}) has already been raised. Click to open it.`}>
                                                                    <Receipt size={14} /> View PV
                                                                </button>
                                                            ) : (
                                                                <>
                                                                    <button className="btn btn-primary" style={btnSm} onClick={() => handleCreatePV(inv.id)} disabled={createDraftPV.isPending} title="Auto-create a draft Payment Voucher from this invoice (vendor, amount, narration pre-filled)">
                                                                        <Receipt size={14} /> {createDraftPV.isPending ? 'Creating PV…' : 'Create PV'}
                                                                    </button>
                                                                    <button style={{ ...btnSm, background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-muted)' }} onClick={() => navigate(`/accounting/payments/new?invoice=${inv.id}`)} title="Use the payments form for advanced settlement (multi-invoice, allocations)">
                                                                        Pay
                                                                    </button>
                                                                </>
                                                            ))}
                                                            <button style={viewBtnStyle} onClick={() => setViewing(row)} title="View invoice detail & GL journal">
                                                                <Eye size={14} /> View
                                                            </button>
                                                        </>
                                                    );
                                                })() : (
                                                    <button style={viewBtnStyle} onClick={() => row.matchingId && navigate(`/procurement/matching/${row.matchingId}`)} title="Open verification">
                                                        <ExternalLink size={14} /> Open
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>

                    {filtered.length === 0 && (
                        <div style={{ textAlign: 'center', padding: '4rem 1.25rem', color: 'var(--color-text-muted)' }}>
                            <Receipt size={56} style={{ margin: '0 auto 1rem', opacity: 0.3 }} />
                            <p style={{ fontSize: 'var(--text-lg)', fontWeight: 500 }}>No documents match the current filters</p>
                        </div>
                    )}
                </div>

                {viewing?.invoiceRaw && (
                    <RegisterDetailModal row={viewing} onClose={() => setViewing(null)} formatCurrency={formatCurrency} navigate={navigate} />
                )}
            </div>
        </AccountingLayout>
    );
}

function SummaryCard({ label, value, accent, warn }: { label: string; value: string; accent?: boolean; warn?: boolean }) {
    return (
        <div className="card">
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.4rem', letterSpacing: '0.04em' }}>{label}</p>
            <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: warn ? 'var(--color-error, #dc2626)' : accent ? '#4f46e5' : 'var(--color-text)' }}>{value}</p>
        </div>
    );
}

// ───────────────────────────────────────────────────────────────────────────
// RegisterDetailModal — compact detail for a VendorInvoice row, with the
// GL journal DR/CR behind it (so a reviewer can confirm how the invoice hit
// the ledger, mirroring the TSA-ledger "trace to GL" pattern).
// ───────────────────────────────────────────────────────────────────────────
interface DetailModalProps {
    row: RegisterRow;
    onClose: () => void;
    formatCurrency: (v: number) => string;
    navigate: (to: string) => void;
}
function RegisterDetailModal({ row, onClose, formatCurrency, navigate }: DetailModalProps) {
    const inv = row.invoiceRaw;
    const { data: journal, isLoading: journalLoading } = useJournal(row.journalId);
    const journalLines = Array.isArray(journal?.lines) ? journal.lines : [];

    return (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999, padding: '1rem' }} onClick={onClose}>
            <div style={{ background: 'var(--color-surface)', borderRadius: 12, padding: '1.5rem', maxWidth: 760, width: '100%', maxHeight: '90vh', overflowY: 'auto', boxShadow: '0 25px 60px rgba(0,0,0,0.3)' }} onClick={(e) => e.stopPropagation()}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.25rem' }}>
                    <div>
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.2rem 0.65rem', borderRadius: 999, background: SOURCE_META[row.source].bg, color: SOURCE_META[row.source].color, border: `1px solid ${SOURCE_META[row.source].border}`, fontSize: 'var(--text-xs)', fontWeight: 700, marginBottom: '0.5rem' }}>
                            <FileText size={12} /> {SOURCE_META[row.source].label}
                        </div>
                        <h3 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Receipt size={20} color="#4f46e5" /> {row.docNumber}
                        </h3>
                        <p style={{ margin: '0.25rem 0 0', fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>Reference: {row.reference || '—'}</p>
                    </div>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}><X size={20} /></button>
                </div>

                {/* Key details */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem', padding: '0.95rem 1rem', marginBottom: '1rem', background: 'rgba(79,70,229,0.04)', border: '1px solid rgba(79,70,229,0.12)', borderRadius: 8 }}>
                    <Detail icon={<Building2 size={12} />} label="Vendor" value={row.vendorName} />
                    <Detail icon={<Calendar size={12} />} label="Invoice Date" value={fmtDate(inv.invoice_date)} />
                    <Detail icon={<Calendar size={12} />} label="Due Date" value={fmtDate(inv.due_date)} />
                    <Detail label="MDA" value={inv.mda_name || (inv.mda ? `#${inv.mda}` : '—')} />
                    <Detail label="Account" value={inv.account_code && inv.account_name ? `${inv.account_code} — ${inv.account_name}` : (inv.account_name || inv.account_code || '—')} />
                    <Detail label="Fund" value={inv.fund_name || '—'} />
                </div>

                {/* Amounts */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem', marginBottom: '1rem' }}>
                    {[
                        { label: 'Total', value: inv.total_amount, accent: true },
                        { label: 'Paid', value: inv.paid_amount },
                        { label: 'Balance Due', value: inv.balance_due },
                    ].map(({ label, value, accent }) => (
                        <div key={label} style={{ padding: '0.6rem 0.75rem', borderRadius: 6, background: accent ? 'rgba(79,70,229,0.08)' : 'rgba(148,163,184,0.06)', border: `1px solid ${accent ? 'rgba(79,70,229,0.25)' : 'var(--color-border)'}` }}>
                            <div style={{ fontSize: '0.6rem', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '0.2rem' }}>{label}</div>
                            <div style={{ fontFamily: 'monospace', fontWeight: accent ? 800 : 600, color: accent ? '#4f46e5' : 'var(--color-text)' }}>{formatCurrency(parseFloat(value || '0'))}</div>
                        </div>
                    ))}
                </div>

                {/* Cross-link to the verification that produced this invoice */}
                {row.source === 'verified' && row.matchingId && (
                    <button onClick={() => { onClose(); navigate(`/procurement/matching/${row.matchingId}`); }} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', marginBottom: '1rem', padding: '0.5rem 0.85rem', borderRadius: 8, border: '1px solid #a7f3d0', background: '#ecfdf5', color: '#047857', cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                        <ClipboardCheck size={15} /> View 3-way verification {row.verificationNumber} <ExternalLink size={13} />
                    </button>
                )}

                {/* GL journal behind the invoice */}
                <div style={{ border: '2px solid rgba(34,197,94,0.25)', borderRadius: 8, overflow: 'hidden', background: 'rgba(34,197,94,0.02)' }}>
                    <div style={{ padding: '0.65rem 0.9rem', background: 'rgba(34,197,94,0.08)', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: 'var(--text-xs)', fontWeight: 700, color: '#15803d', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                        <BookOpen size={13} /> GL Journal
                        {journal?.reference_number && (
                            <span style={{ fontFamily: 'monospace', background: 'white', padding: '2px 8px', borderRadius: 4, marginLeft: '0.3rem' }}>{journal.reference_number}</span>
                        )}
                    </div>
                    {!row.journalId && (
                        <div style={{ padding: '0.75rem 0.9rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontStyle: 'italic' }}>
                            Not yet posted to the GL — this document has no journal entry.
                        </div>
                    )}
                    {row.journalId && journalLoading && (
                        <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>Loading journal…</div>
                    )}
                    {row.journalId && !journalLoading && journalLines.length > 0 && (
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                            <thead>
                                <tr style={{ background: 'rgba(0,0,0,0.02)' }}>
                                    <th style={jTh}>Account</th>
                                    <th style={{ ...jTh, textAlign: 'right' }}>Debit</th>
                                    <th style={{ ...jTh, textAlign: 'right' }}>Credit</th>
                                </tr>
                            </thead>
                            <tbody>
                                {journalLines.map((jl: any, i: number) => (
                                    <tr key={jl.id ?? i}>
                                        <td style={jTd}>
                                            <div style={{ fontFamily: 'monospace', fontWeight: 600 }}>{jl.account_code || `#${jl.account}`}</div>
                                            {jl.account_name && <div style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)' }}>{jl.account_name}</div>}
                                        </td>
                                        <td style={{ ...jTd, textAlign: 'right', fontFamily: 'monospace', color: parseFloat(jl.debit || '0') > 0 ? '#16a34a' : 'var(--color-text-muted)' }}>{parseFloat(jl.debit || '0') > 0 ? formatCurrency(parseFloat(jl.debit)) : '—'}</td>
                                        <td style={{ ...jTd, textAlign: 'right', fontFamily: 'monospace', color: parseFloat(jl.credit || '0') > 0 ? '#dc2626' : 'var(--color-text-muted)' }}>{parseFloat(jl.credit || '0') > 0 ? formatCurrency(parseFloat(jl.credit)) : '—'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}>
                    <button onClick={onClose} style={{ padding: '0.5rem 1.25rem', borderRadius: 6, border: '1px solid var(--color-border)', background: 'none', color: 'var(--color-text)', cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Close</button>
                </div>
            </div>
        </div>
    );
}

const jTh: React.CSSProperties = { padding: '0.5rem 0.7rem', fontSize: '0.65rem', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', textAlign: 'left', whiteSpace: 'nowrap' };
const jTd: React.CSSProperties = { padding: '0.5rem 0.7rem', fontSize: 'var(--text-sm)', borderTop: '1px solid var(--color-border)' };

// Compact row-action button sizing (the `btn btn-primary` class supplies the
// primary colour; this only fixes the dimensions). viewBtnStyle is the neutral
// outline variant used for View / Open.
const btnSm: React.CSSProperties = { padding: '0.35rem 0.7rem', fontSize: 'var(--text-xs)', fontWeight: 600, borderRadius: 6, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '0.3rem', cursor: 'pointer', whiteSpace: 'nowrap' };
const viewBtnStyle: React.CSSProperties = { ...btnSm, background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-muted)' };

function Detail({ icon, label, value }: { icon?: React.ReactNode; label: string; value: React.ReactNode }) {
    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.6rem', color: 'var(--color-text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '0.2rem' }}>
                {icon}{label}
            </div>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>{value}</div>
        </div>
    );
}
