import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Receipt, Filter, CheckCircle, X, ChevronDown, Download, FileSpreadsheet, Upload, Eye, BookOpen, FileText, Building2, Calendar, AlertTriangle, Edit } from 'lucide-react';
import apiClient from '../../../api/client';
import { useVendorInvoices, useApproveVendorInvoice, useCreateVendorInvoice } from '../hooks/useAccountingEnhancements';
import { useJournal, useSimulatedInvoiceJournal } from '../hooks/useJournal';
import { useAccounts } from '../hooks/useBudgetDimensions';
import { useVendors } from '../../procurement/hooks/useProcurement';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import StatusBadge from '../components/shared/StatusBadge';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import { safeSum } from '../utils/currency';
import VendorInvoiceForm from './VendorInvoiceForm';
import { useDialog } from '../../../hooks/useDialog';
import logger from '../../../utils/logger';
import '../styles/glassmorphism.css';

export default function APManagement() {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const [statusFilter, setStatusFilter] = useState('');
    const [showForm, setShowForm] = useState(false);
    // When set, the form opens in EDIT mode for this Draft invoice's id.
    // null = create mode. Closing/saving the form clears both.
    const [editingInvoiceId, setEditingInvoiceId] = useState<number | null>(null);

    const [actionsOpen, setActionsOpen] = useState(false);
    const actionsRef = useRef<HTMLDivElement>(null);

    // Budget-error banner — shown when an approve/post action returns a
    // structured budget/warrant violation. Multi-line so it can render
    // the full backend message (Requested / Available / Deficit block).
    const [budgetError, setBudgetError] = useState<string>('');
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
    // The invoice the user is currently viewing in the detail modal.
    // Null = no modal open.
    const [viewingInvoice, setViewingInvoice] = useState<any | null>(null);
    const flash = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 5000);
    };

    const { showConfirm } = useDialog();
    const { data: invoices, isLoading } = useVendorInvoices({ status: statusFilter });
    const approveInvoice = useApproveVendorInvoice();

    // Close dropdown on outside click
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (actionsRef.current && !actionsRef.current.contains(e.target as Node)) {
                setActionsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const importFileRef = useRef<HTMLInputElement>(null);
    const [importMsg, setImportMsg] = useState('');

    const handleDownloadTemplate = async () => {
        setActionsOpen(false);
        try {
            const res = await apiClient.get('/accounting/vendor-invoices/import-template/', { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
            const a = document.createElement('a'); a.href = url; a.download = 'vendor_invoice_template.csv';
            document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url);
        } catch { /* ignore */ }
    };

    const handleImportInvoices = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]; if (!file) return;
        setActionsOpen(false);
        const fd = new FormData(); fd.append('file', file);
        try {
            const res = await apiClient.post('/accounting/vendor-invoices/bulk-import/', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
            const d = res.data;
            setImportMsg(`${d.created} invoice(s) imported${d.skipped ? `, ${d.skipped} skipped` : ''}${d.errors?.length ? `, ${d.errors.length} error(s)` : ''}`);
            setTimeout(() => setImportMsg(''), 5000);
        } catch (err: any) {
            setImportMsg(err?.response?.data?.error || 'Import failed');
            setTimeout(() => setImportMsg(''), 5000);
        }
        e.target.value = '';
    };

    const handleExportInvoices = () => {
        setActionsOpen(false);
        if (!invoices || invoices.length === 0) return;
        const headers = ['Invoice #', 'Vendor', 'Reference', 'Invoice Date', 'Due Date', 'Total Amount', 'Paid Amount', 'Balance Due', 'Status'];
        const rows = invoices.map((inv: any) => [
            inv.invoice_number,
            inv.vendor_name || '',
            inv.reference || '',
            inv.invoice_date,
            inv.due_date,
            inv.total_amount,
            inv.paid_amount,
            inv.balance_due,
            inv.status,
        ].map((v: any) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','));
        const csv = [headers.join(','), ...rows].join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `accounts_payable_${new Date().toISOString().split('T')[0]}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
    };

    const handleApprove = async (invoiceId: number) => {
        if (!await showConfirm('Approve & post this vendor invoice to the GL?')) return;
        setBudgetError('');
        try {
            const resp = await approveInvoice.mutateAsync(invoiceId);
            const r: any = resp;
            flash(
                r?.journal_reference
                    ? `Posted. Journal ${r.journal_reference}`
                    : r?.status || 'Invoice approved and posted.',
            );
        } catch (error: any) {
            // Extract structured budget/warrant error and display prominently.
            // `approve_invoice` now delegates to `post_invoice` so the same
            // response shape (appropriation_exceeded / warrant_exceeded /
            // budget) is returned here as at the dedicated post endpoint.
            const data = error?.response?.data;
            logger.error('Failed to approve invoice:', error);
            if (data?.appropriation_exceeded || data?.warrant_exceeded || data?.budget) {
                const msg =
                    data.error
                    || (Array.isArray(data.budget) ? data.budget.join(' ') : data.budget)
                    || 'Budget validation failed.';
                setBudgetError(msg);
                // Scroll the banner into view so the user sees it immediately.
                setTimeout(() => window.scrollTo({ top: 0, behavior: 'smooth' }), 50);
            } else {
                const msg = data?.error || data?.detail || error?.message || 'Failed to approve invoice.';
                flash(msg, false);
            }
        }
    };

    const totalPayable = invoices ? safeSum(invoices, 'balance_due') : 0;
    // Overdue = posted (or legacy Approved) invoice that's past its due
    // date and not yet paid. Partially Paid is excluded because a payment
    // has started; Paid is excluded because it's settled.
    const overdueCount = invoices?.filter(
        (inv: any) => ['Posted', 'Approved'].includes(inv.status)
            && new Date(inv.due_date) < new Date()
    ).length || 0;
    const pendingApproval = invoices?.filter((inv: any) => inv.status === 'Draft').length || 0;

    if (isLoading) {
        return <LoadingScreen message="Loading invoices..." />;
    }

    if (showForm) {
        return (
            <AccountingLayout>
                <VendorInvoiceForm
                    editingInvoiceId={editingInvoiceId}
                    onCancel={() => { setShowForm(false); setEditingInvoiceId(null); }}
                    onSuccess={() => { setShowForm(false); setEditingInvoiceId(null); }}
                />
            </AccountingLayout>
        );
    }

    return (
        <>
            <AccountingLayout>
                <div>
                    {/* Budget-error banner — shown when the 3-pillar
                        appropriation/warrant check rejects an approve/post.
                        Preserves newlines from the backend message so the
                        Requested/Available/Deficit block stays formatted. */}
                    {budgetError && (
                        <div style={{
                            padding: '0.85rem 1.1rem', marginBottom: '1rem',
                            background: '#fef2f2', color: '#991b1b',
                            border: '1.5px solid #fecaca', borderLeft: '5px solid #dc2626',
                            borderRadius: '8px', fontSize: 'var(--text-sm)',
                            whiteSpace: 'pre-wrap' as const,
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.3rem' }}>
                                <strong style={{ fontSize: 'var(--text-base)' }}>
                                    ⚠ Budget Validation Failed
                                </strong>
                                <button onClick={() => setBudgetError('')}
                                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#991b1b', fontSize: 18, lineHeight: 1 }}>
                                    ×
                                </button>
                            </div>
                            {budgetError}
                        </div>
                    )}

                    {/* Success/generic toast */}
                    {toast && (
                        <div style={{
                            padding: '0.7rem 0.95rem', marginBottom: '1rem', borderRadius: '8px',
                            background: toast.ok ? '#ecfdf5' : '#fef2f2',
                            border: `1px solid ${toast.ok ? '#a7f3d0' : '#fecaca'}`,
                            color: toast.ok ? '#065f46' : '#991b1b',
                            fontSize: 'var(--text-sm)', fontWeight: 500,
                        }}>
                            {toast.msg}
                        </div>
                    )}

                    <PageHeader
                        title="Accounts Payable"
                        subtitle="Manage vendor invoices and payments"
                        icon={<Receipt size={22} />}
                        actions={
                            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                                {/* Actions Dropdown */}
                                <div ref={actionsRef} style={{ position: 'relative' }}>
                                    <button
                                        className="btn btn-outline"
                                        onClick={() => setActionsOpen(!actionsOpen)}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: '0.4rem',
                                            padding: '0.6rem 1rem', fontWeight: 600, borderRadius: '8px',
                                        }}
                                    >
                                        Actions <ChevronDown size={16} style={{
                                            transition: 'transform 0.2s',
                                            transform: actionsOpen ? 'rotate(180deg)' : 'rotate(0deg)',
                                        }} />
                                    </button>
                                    {actionsOpen && (
                                        <div style={{
                                            position: 'absolute', right: 0, top: 'calc(100% + 6px)',
                                            minWidth: '220px', background: 'var(--color-background, #fff)',
                                            borderRadius: '10px', border: '1px solid var(--color-border, #e2e8f0)',
                                            boxShadow: '0 8px 24px rgba(0,0,0,0.1)', zIndex: 50,
                                            overflow: 'hidden',
                                        }}>
                                            <button
                                                onClick={handleDownloadTemplate}
                                                style={{
                                                    width: '100%', display: 'flex', alignItems: 'center', gap: '0.625rem',
                                                    padding: '0.75rem 1rem', background: 'none', border: 'none',
                                                    cursor: 'pointer', fontSize: 'var(--text-sm)', color: 'var(--color-text)',
                                                    transition: 'background 0.15s',
                                                }}
                                                onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-surface, #f8fafc)')}
                                                onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                                            >
                                                <FileSpreadsheet size={16} color="#4f46e5" />
                                                <div style={{ textAlign: 'left' }}>
                                                    <span style={{ fontWeight: 600, display: 'block' }}>Download Template</span>
                                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>CSV with MDA, vendor, NCoA dimensions</span>
                                                </div>
                                            </button>
                                            <div style={{ height: '1px', background: 'var(--color-border, #e2e8f0)' }} />
                                            <button
                                                onClick={() => { setActionsOpen(false); importFileRef.current?.click(); }}
                                                style={{
                                                    width: '100%', display: 'flex', alignItems: 'center', gap: '0.625rem',
                                                    padding: '0.75rem 1rem', background: 'none', border: 'none',
                                                    cursor: 'pointer', fontSize: 'var(--text-sm)', color: 'var(--color-text)',
                                                    transition: 'background 0.15s',
                                                }}
                                                onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-surface, #f8fafc)')}
                                                onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                                            >
                                                <Upload size={16} color="#4f46e5" />
                                                <div style={{ textAlign: 'left' }}>
                                                    <span style={{ fontWeight: 600, display: 'block' }}>Import Invoices</span>
                                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>Upload CSV or Excel file</span>
                                                </div>
                                            </button>
                                            <div style={{ height: '1px', background: 'var(--color-border, #e2e8f0)' }} />
                                            <button
                                                onClick={handleExportInvoices}
                                                style={{
                                                    width: '100%', display: 'flex', alignItems: 'center', gap: '0.625rem',
                                                    padding: '0.75rem 1rem', background: 'none', border: 'none',
                                                    cursor: 'pointer', fontSize: 'var(--text-sm)', color: 'var(--color-text)',
                                                    transition: 'background 0.15s',
                                                    opacity: invoices?.length ? 1 : 0.5,
                                                    pointerEvents: invoices?.length ? 'auto' : 'none',
                                                }}
                                                onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-surface, #f8fafc)')}
                                                onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                                            >
                                                <Download size={16} color="#4f46e5" />
                                                <div style={{ textAlign: 'left' }}>
                                                    <span style={{ fontWeight: 600, display: 'block' }}>Export Invoices</span>
                                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>Download as CSV</span>
                                                </div>
                                            </button>
                                        </div>
                                    )}
                                </div>

                                <button className="btn btn-primary" onClick={() => setShowForm(true)}>
                                    <Receipt size={18} /> New Invoice
                                </button>
                            </div>
                        }
                    />

                    {/* Hidden file input for import */}
                    <input ref={importFileRef} type="file" accept=".csv,.xlsx" style={{ display: 'none' }} onChange={handleImportInvoices} />

                    {importMsg && (
                        <div style={{ padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem', background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)', color: '#166534', fontSize: 'var(--text-sm)' }}>
                            {importMsg}
                        </div>
                    )}

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
                        <div className="card">
                            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Total Payable</p>
                            <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>{formatCurrency(totalPayable)}</p>
                        </div>
                        <div className="card">
                            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Pending Approval</p>
                            <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>{pendingApproval}</p>
                        </div>
                        <div className="card">
                            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Overdue</p>
                            <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-error)' }}>{overdueCount}</p>
                        </div>
                    </div>

                    <div className="card" style={{ padding: '1rem', marginBottom: '1.5rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <Filter size={18} style={{ color: 'var(--color-text-muted)' }} />
                            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ minWidth: '200px' }}>
                                <option value="">All Statuses</option>
                                <option value="Draft">Draft</option>
                                <option value="Posted">Posted (awaiting payment)</option>
                                <option value="Partially Paid">Partially Paid</option>
                                <option value="Paid">Paid</option>
                                <option value="Void">Void</option>
                            </select>
                        </div>
                    </div>

                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                    <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Invoice #</th>
                                    <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Vendor</th>
                                    <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Due Date</th>
                                    <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', textAlign: 'right' }}>Balance Due</th>
                                    <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                                    <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', textAlign: 'center' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {invoices?.map((invoice: any) => (
                                    <tr key={invoice.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem 1.5rem' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                <span style={{ fontWeight: 600, color: 'var(--color-primary)' }}>{invoice.invoice_number}</span>
                                                {invoice.document_type === 'Credit Memo' && (
                                                    <span style={{
                                                        padding: '0.1rem 0.5rem', borderRadius: '20px',
                                                        fontSize: '10px', fontWeight: 700, textTransform: 'uppercase',
                                                        background: 'rgba(13,148,136,0.12)', color: '#0d9488',
                                                        border: '1px solid rgba(13,148,136,0.3)',
                                                        letterSpacing: '0.04em',
                                                    }}>CM</span>
                                                )}
                                            </div>
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem' }}>{invoice.vendor_name}</td>
                                        <td style={{ padding: '1rem 1.5rem' }}>{new Date(invoice.due_date).toLocaleDateString()}</td>
                                        <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontWeight: 600, color: 'var(--color-cta)' }}>{invoice.currency_code} {parseFloat(invoice.balance_due || '0').toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                                        <td style={{ padding: '1rem 1.5rem' }}><StatusBadge status={invoice.status} /></td>
                                        <td style={{ padding: '1rem 1.5rem', textAlign: 'center' }}>
                                            <div style={{ display: 'inline-flex', gap: '0.4rem', flexWrap: 'wrap', justifyContent: 'center' }}>
                                                {/* Decide what action to surface based on (status, has-journal).
                                                    needsPost is true when the invoice hasn't actually hit
                                                    the GL yet — either it's a fresh Draft, or it's a
                                                    legacy "Approved" row left over from before
                                                    approve_invoice auto-posted.
                                                    canPay is true when the GL journal already exists. */}
                                                {(() => {
                                                    const needsPost =
                                                        invoice.status === 'Draft' ||
                                                        (invoice.status === 'Approved' && !invoice.journal_entry);
                                                    const canPay =
                                                        invoice.status === 'Posted' ||
                                                        (invoice.status === 'Approved' && !!invoice.journal_entry);
                                                    return (
                                                        <>
                                                            {needsPost && (
                                                                <button
                                                                    className="btn btn-primary"
                                                                    style={{ padding: '0.375rem 0.75rem', fontSize: 'var(--text-xs)' }}
                                                                    onClick={() => handleApprove(invoice.id)}
                                                                    title="Approve this invoice, post the GL journal, and mark it Posted for Treasury to pay"
                                                                >
                                                                    <CheckCircle size={14} /> Approve &amp; Post
                                                                </button>
                                                            )}
                                                            {canPay && (
                                                                <button
                                                                    className="btn btn-primary"
                                                                    style={{ padding: '0.375rem 0.75rem', fontSize: 'var(--text-xs)' }}
                                                                    onClick={() => navigate(`/accounting/payments/new?invoice=${invoice.id}`)}
                                                                    title="Raise a Payment Voucher against this posted invoice (Treasury)"
                                                                >
                                                                    Pay
                                                                </button>
                                                            )}
                                                        </>
                                                    );
                                                })()}
                                                {/* Edit — Draft only. Project rule: non-Draft documents
                                                    are immutable; user must reverse them via Credit Memo. */}
                                                {invoice.status === 'Draft' && (
                                                    <button
                                                        onClick={() => { setEditingInvoiceId(invoice.id); setShowForm(true); }}
                                                        style={{
                                                            padding: '0.375rem 0.75rem', borderRadius: '6px',
                                                            background: 'transparent', color: 'var(--color-text-muted)',
                                                            border: '1px solid var(--color-border)',
                                                            cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600,
                                                            display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                                        }}
                                                        title="Edit this draft invoice (lines, vendor, amounts, dimensions)"
                                                    >
                                                        <Edit size={14} /> Edit
                                                    </button>
                                                )}
                                                {/* View — always available, opens detail modal with
                                                    invoice lines + linked journal DR/CR breakdown */}
                                                <button
                                                    onClick={() => setViewingInvoice(invoice)}
                                                    style={{
                                                        padding: '0.375rem 0.75rem', borderRadius: '6px',
                                                        background: 'transparent', color: 'var(--color-text-muted)',
                                                        border: '1px solid var(--color-border)',
                                                        cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600,
                                                        display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                                    }}
                                                    title="View invoice details and GL journal"
                                                >
                                                    <Eye size={14} /> View
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    {invoices?.length === 0 && (
                        <div style={{ textAlign: 'center', padding: '5rem 1.25rem', color: 'var(--color-text-muted)' }}>
                            <Receipt size={64} style={{ margin: '0 auto 1rem', opacity: 0.3 }} />
                            <p style={{ fontSize: 'var(--text-lg)', fontWeight: 500 }}>No vendor invoices found</p>
                        </div>
                    )}

                    {/* View modal — opens when user clicks Eye icon on a row */}
                    {viewingInvoice && (
                        <InvoiceViewModal
                            invoice={viewingInvoice}
                            onClose={() => setViewingInvoice(null)}
                            formatCurrency={formatCurrency}
                        />
                    )}
                </div>
            </AccountingLayout>
            <style>{`
                .label {
                    display: block; 
                    margin-bottom: 0.5rem; 
                    font-size: 0.75rem; 
                    font-weight: 600; 
                    text-transform: uppercase; 
                    color: var(--color-text-muted);
                }
            `}</style>
        </>
    );
};

// ───────────────────────────────────────────────────────────────────────────
// InvoiceViewModal — detail panel for a single Vendor Invoice.
// Shows header info, invoice lines, and (if posted) the linked GL journal's
// DR/CR breakdown. Opened from the Eye icon on each row.
// ───────────────────────────────────────────────────────────────────────────

interface InvoiceViewModalProps {
    invoice: any;
    onClose: () => void;
    formatCurrency: (v: number) => string;
}
function InvoiceViewModal({ invoice, onClose, formatCurrency }: InvoiceViewModalProps) {
    // Two journal sources depending on invoice state:
    //   1. Posted invoice → fetch the REAL journal via `useJournal`
    //   2. Draft / Approved-without-journal → call simulate_posting to
    //      compute the PROPOSED DR/CR without writing anything
    // The simulated journal is labelled "Proposed" in the UI so the
    // finance team can sanity-check the GL hit before approving, and
    // matches the actual journal byte-for-byte on Post.
    const hasRealJournal = !!invoice?.journal_entry;
    const { data: realJournal, isLoading: realJournalLoading } = useJournal(
        hasRealJournal ? invoice.journal_entry : null,
    );
    const { data: proposedJournal, isLoading: proposedLoading } = useSimulatedInvoiceJournal(
        invoice?.id,
        !hasRealJournal,  // only fire when we don't already have a real journal
    );
    const journal = hasRealJournal ? realJournal : proposedJournal;
    const journalLoading = hasRealJournal ? realJournalLoading : proposedLoading;
    const isProposed = !hasRealJournal;

    const statusStyles: Record<string, React.CSSProperties> = {
        Draft:            { bg: '#f1f5f9', color: '#475569', border: '#cbd5e1' },
        Approved:         { bg: '#dbeafe', color: '#1d4ed8', border: '#93c5fd' },
        Posted:           { bg: '#dcfce7', color: '#15803d', border: '#86efac' },
        'Partially Paid': { bg: '#fef3c7', color: '#a16207', border: '#fde68a' },
        Paid:             { bg: '#d1fae5', color: '#047857', border: '#6ee7b7' },
        Void:             { bg: '#fee2e2', color: '#b91c1c', border: '#fecaca' },
    };
    const st = statusStyles[invoice.status] || statusStyles.Draft;

    const lines = Array.isArray(invoice.lines) ? invoice.lines : [];
    const journalLines = Array.isArray(journal?.lines) ? journal.lines : [];

    return (
        <div
            style={{
                position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                background: 'rgba(15,23,42,0.55)', display: 'flex',
                alignItems: 'center', justifyContent: 'center', zIndex: 9999,
                padding: '1rem',
            }}
            onClick={onClose}
        >
            <div
                style={{
                    background: 'var(--color-surface)', borderRadius: '12px',
                    padding: '1.5rem', maxWidth: '800px', width: '100%',
                    maxHeight: '90vh', overflowY: 'auto',
                    boxShadow: '0 25px 60px rgba(0,0,0,0.3)',
                }}
                onClick={e => e.stopPropagation()}
            >
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.25rem' }}>
                    <div>
                        <div style={{
                            display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                            padding: '0.25rem 0.7rem', borderRadius: '999px',
                            background: st.bg, color: st.color, border: `1px solid ${st.border}`,
                            fontSize: 'var(--text-xs)', fontWeight: 700, marginBottom: '0.5rem',
                        }}>
                            <FileText size={12} /> {invoice.status}
                        </div>
                        <h3 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Receipt size={20} color="#4f46e5" />
                            {invoice.invoice_number}
                            {invoice.document_type === 'Credit Memo' && (
                                <span style={{
                                    padding: '0.1rem 0.5rem', borderRadius: '999px',
                                    fontSize: '10px', fontWeight: 700, textTransform: 'uppercase',
                                    background: 'rgba(13,148,136,0.12)', color: '#0d9488',
                                    border: '1px solid rgba(13,148,136,0.3)',
                                }}>Credit Memo</span>
                            )}
                        </h3>
                        <p style={{ margin: '0.25rem 0 0', fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                            Reference: {invoice.reference || '—'}
                        </p>
                    </div>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                        <X size={20} />
                    </button>
                </div>

                {/* Key details grid */}
                <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem',
                    padding: '0.95rem 1rem', marginBottom: '1rem',
                    background: 'rgba(79,70,229,0.04)',
                    border: '1px solid rgba(79,70,229,0.12)',
                    borderRadius: '8px',
                }}>
                    <DetailRow icon={<Building2 size={12} />} label="Vendor" value={invoice.vendor_name || `#${invoice.vendor}`} />
                    <DetailRow icon={<Calendar size={12} />} label="Invoice Date" value={invoice.invoice_date ? new Date(invoice.invoice_date).toLocaleDateString() : '—'} />
                    <DetailRow icon={<Calendar size={12} />} label="Due Date" value={invoice.due_date ? new Date(invoice.due_date).toLocaleDateString() : '—'} />
                    <DetailRow label="MDA" value={invoice.mda_name || (invoice.mda ? `#${invoice.mda}` : '—')} />
                    <DetailRow
                        label="Account"
                        value={
                            invoice.account_code && invoice.account_name
                                ? `${invoice.account_code} — ${invoice.account_name}`
                                : invoice.account_name
                                    || invoice.account_code
                                    || (invoice.account ? `#${invoice.account}` : '—')
                        }
                    />
                    <DetailRow label="Fund" value={invoice.fund_name || (invoice.fund ? `#${invoice.fund}` : '—')} />
                </div>

                {/* Amounts */}
                <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.5rem',
                    marginBottom: '1rem',
                }}>
                    {[
                        { label: 'Subtotal',     value: invoice.subtotal },
                        { label: 'Tax',          value: invoice.tax_amount },
                        { label: 'Total',        value: invoice.total_amount, accent: true },
                        { label: 'Balance Due',  value: invoice.balance_due },
                    ].map(({ label, value, accent }) => (
                        <div key={label} style={{
                            padding: '0.6rem 0.75rem', borderRadius: '6px',
                            background: accent ? 'rgba(79,70,229,0.08)' : 'rgba(148,163,184,0.06)',
                            border: `1px solid ${accent ? 'rgba(79,70,229,0.25)' : 'var(--color-border)'}`,
                        }}>
                            <div style={{ fontSize: '0.6rem', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '0.2rem' }}>
                                {label}
                            </div>
                            <div style={{ fontFamily: 'monospace', fontSize: accent ? 'var(--text-base)' : 'var(--text-sm)', fontWeight: accent ? 800 : 600, color: accent ? '#4f46e5' : 'var(--color-text)' }}>
                                {formatCurrency(parseFloat(value || '0'))}
                            </div>
                        </div>
                    ))}
                </div>

                {/* Invoice lines */}
                {lines.length > 0 && (
                    <div style={{
                        border: '1px solid var(--color-border)', borderRadius: '8px',
                        marginBottom: '1rem', overflow: 'hidden',
                    }}>
                        <div style={{ padding: '0.55rem 0.85rem', background: 'rgba(0,0,0,0.03)', fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            Invoice Lines ({lines.length})
                        </div>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                            <thead>
                                <tr style={{ background: 'rgba(0,0,0,0.02)' }}>
                                    <th style={thStyle}>Account</th>
                                    <th style={thStyle}>Description</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Amount</th>
                                </tr>
                            </thead>
                            <tbody>
                                {lines.map((line: any, i: number) => (
                                    <tr key={line.id ?? i}>
                                        <td style={tdStyle}>
                                            <div style={{ fontFamily: 'monospace', fontWeight: 600 }}>{line.account_code || `#${line.account}`}</div>
                                            {line.account_name && (
                                                <div style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)' }}>{line.account_name}</div>
                                            )}
                                        </td>
                                        <td style={tdStyle}>{line.description || '—'}</td>
                                        <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace', fontWeight: 600 }}>
                                            {formatCurrency(parseFloat(line.amount || '0'))}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* Accounting entries — either the ACTUAL posted journal
                    or the PROPOSED entries (computed by the backend's
                    simulate_posting action). Same rendering, different
                    labels/colours so the user knows which they're looking at. */}
                {(() => {
                    // Colours: green for posted (done), indigo for proposed (preview)
                    const borderColor = isProposed ? 'rgba(99,102,241,0.35)' : 'rgba(34,197,94,0.25)';
                    const bannerBg    = isProposed ? 'rgba(99,102,241,0.08)' : 'rgba(34,197,94,0.08)';
                    const cardBg      = isProposed ? 'rgba(99,102,241,0.02)' : 'rgba(34,197,94,0.02)';
                    const bannerColor = isProposed ? '#4338ca'               : '#15803d';
                    const bannerLabel = isProposed ? 'Proposed Accounting Entry'
                                                   : 'GL Journal Posted';

                    return (
                        <div style={{
                            border: `2px solid ${borderColor}`, borderRadius: '8px',
                            overflow: 'hidden', background: cardBg,
                        }}>
                            <div style={{ padding: '0.65rem 0.9rem', background: bannerBg, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: 'var(--text-xs)', fontWeight: 700, color: bannerColor, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                    <BookOpen size={13} />
                                    {bannerLabel}
                                    {journal?.reference_number && (
                                        <span style={{ fontFamily: 'monospace', background: 'white', padding: '2px 8px', borderRadius: '4px', marginLeft: '0.3rem' }}>
                                            {journal.reference_number}
                                        </span>
                                    )}
                                </div>
                                {journal?.posting_date && !isProposed && (
                                    <div style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                                        Posted {new Date(journal.posting_date).toLocaleDateString()}
                                    </div>
                                )}
                                {isProposed && (
                                    <div style={{ fontSize: '0.7rem', color: bannerColor, fontWeight: 600, fontStyle: 'italic' }}>
                                        Preview — will post on approval
                                    </div>
                                )}
                            </div>

                            {journalLoading && (
                                <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                    {isProposed ? 'Computing proposed entries…' : 'Loading journal…'}
                                </div>
                            )}

                            {/* Warnings from simulate_posting (proposed only) — e.g.
                                "No Input Tax account configured" — surfaces
                                config gaps before the user hits the real Post. */}
                            {isProposed && Array.isArray(journal?.warnings) && journal.warnings.length > 0 && (
                                <div style={{
                                    padding: '0.5rem 0.9rem',
                                    background: 'rgba(245,158,11,0.08)',
                                    borderBottom: '1px solid rgba(245,158,11,0.25)',
                                    color: '#92400e', fontSize: '0.7rem',
                                }}>
                                    <strong style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', marginBottom: '0.2rem' }}>
                                        <AlertTriangle size={11} /> Configuration warnings
                                    </strong>
                                    {journal.warnings.map((w: string, i: number) => (
                                        <div key={i} style={{ marginLeft: '1.1rem' }}>• {w}</div>
                                    ))}
                                </div>
                            )}

                            {!journalLoading && journalLines.length > 0 && (
                                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                                    <thead>
                                        <tr style={{ background: 'rgba(0,0,0,0.02)' }}>
                                            <th style={thStyle}>Account</th>
                                            <th style={{ ...thStyle, textAlign: 'right' }}>Debit</th>
                                            <th style={{ ...thStyle, textAlign: 'right' }}>Credit</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {journalLines.map((jl: any, i: number) => (
                                            <tr key={jl.id ?? i}>
                                                <td style={tdStyle}>
                                                    <div style={{ fontFamily: 'monospace', fontWeight: 600 }}>{jl.account_code || `#${jl.account}`}</div>
                                                    {jl.account_name && (
                                                        <div style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)' }}>{jl.account_name}</div>
                                                    )}
                                                    {jl.memo && (
                                                        <div style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)', fontStyle: 'italic', marginTop: '0.15rem' }}>
                                                            {jl.memo}
                                                        </div>
                                                    )}
                                                </td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace', color: parseFloat(jl.debit || '0') > 0 ? '#16a34a' : 'var(--color-text-muted)' }}>
                                                    {parseFloat(jl.debit || '0') > 0 ? formatCurrency(parseFloat(jl.debit)) : '—'}
                                                </td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace', color: parseFloat(jl.credit || '0') > 0 ? '#dc2626' : 'var(--color-text-muted)' }}>
                                                    {parseFloat(jl.credit || '0') > 0 ? formatCurrency(parseFloat(jl.credit)) : '—'}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                    <tfoot>
                                        <tr style={{ borderTop: '2px solid var(--color-border)', background: 'rgba(0,0,0,0.02)', fontWeight: 700 }}>
                                            <td style={tdStyle}>Total</td>
                                            <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace', color: '#16a34a' }}>
                                                {formatCurrency(journalLines.reduce((s: number, l: any) => s + parseFloat(l.debit || '0'), 0))}
                                            </td>
                                            <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace', color: '#dc2626' }}>
                                                {formatCurrency(journalLines.reduce((s: number, l: any) => s + parseFloat(l.credit || '0'), 0))}
                                            </td>
                                        </tr>
                                    </tfoot>
                                </table>
                            )}

                            {!journalLoading && journalLines.length === 0 && (
                                <div style={{ padding: '0.75rem 0.9rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontStyle: 'italic' }}>
                                    No entries to display. Check that the invoice has an account
                                    + total amount set so the proposed journal can be computed.
                                </div>
                            )}
                        </div>
                    );
                })()}

                {/* Close action */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}>
                    <button onClick={onClose} style={{
                        padding: '0.5rem 1.25rem', borderRadius: '6px',
                        border: '1px solid var(--color-border)', background: 'none',
                        color: 'var(--color-text)', cursor: 'pointer',
                        fontSize: 'var(--text-sm)', fontWeight: 500,
                    }}>
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
}

const thStyle: React.CSSProperties = {
    padding: '0.5rem 0.7rem', fontSize: '0.65rem', fontWeight: 700,
    color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em',
    textAlign: 'left' as const, whiteSpace: 'nowrap' as const,
};
const tdStyle: React.CSSProperties = {
    padding: '0.5rem 0.7rem', fontSize: 'var(--text-sm)',
    borderTop: '1px solid var(--color-border)',
};

function DetailRow({ icon, label, value }: { icon?: React.ReactNode; label: string; value: React.ReactNode }) {
    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.6rem', color: 'var(--color-text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '0.2rem' }}>
                {icon}
                {label}
            </div>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                {value}
            </div>
        </div>
    );
}

