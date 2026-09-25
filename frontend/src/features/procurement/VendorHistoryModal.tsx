import { useState, useMemo } from 'react';
import { formatDate } from '@/utils/date';
import { X, CheckCircle2, ArrowDownRight, ArrowUpRight, Download, Sparkles, CheckCheck } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useVendorTransactionHistory } from './hooks/useProcurement';
import apiClient from '../../api/client';
import { useCurrency } from '../../context/CurrencyContext';
import { useFocusTrap } from '../../hooks/useFocusTrap';
import { exportToCSV } from '../accounting/utils/exportReport';
import type { ExportOptions } from '../accounting/utils/exportReport';

// Clearance state derived from REAL posting data (not the manual
// match tool): how much of an invoice has actually been settled by
// posted payments/allocations.
//   paid    — invoice fully settled (balance_due == 0)
//   partial — invoice part-paid (0 < paid < total)
//   open    — invoice unpaid (paid == 0)
//   cleared — a posted payment/disbursement (money left the bank)
//   applied — a posted purchase return (credit applied to the account)
type ClearKey = 'paid' | 'partial' | 'open' | 'cleared' | 'applied';

interface TransactionRow {
    id: string;
    date: string;
    reference: string;
    type: string;
    description: string;
    debit: number;
    credit: number;
    status: string;
    sourceType: string;
    // Real-data clearance signal + the figures that drive the
    // supplier-level cleared/outstanding banner. ``paidAmount`` and
    // ``balanceDue`` are only meaningful on invoice rows (0 elsewhere).
    clearKey: ClearKey;
    paidAmount: number;
    balanceDue: number;
    // Numeric VendorInvoice id on invoice rows (undefined elsewhere) — the
    // key the open-item clearing API selects on.
    invoiceId?: number;
}

const CLEAR_BADGE: Record<ClearKey, { label: string; bg: string; color: string }> = {
    paid:    { label: 'Paid ✓',  bg: 'rgba(34,197,94,0.12)',  color: '#16a34a' },
    partial: { label: 'Partial', bg: 'rgba(245,158,11,0.14)', color: '#d97706' },
    open:    { label: 'Open',    bg: 'rgba(148,163,184,0.16)', color: '#64748b' },
    cleared: { label: 'Cleared', bg: 'rgba(34,197,94,0.12)',  color: '#16a34a' },
    applied: { label: 'Applied', bg: 'rgba(168,85,247,0.12)', color: '#9333ea' },
};

interface Props {
    vendor: { id: number; name: string; code: string };
    onClose: () => void;
}

const VendorHistoryModal = ({ vendor, onClose }: Props) => {
    const dialogRef = useFocusTrap(true, onClose);
    const { data, isLoading } = useVendorTransactionHistory(vendor.id);
    const { formatCurrency } = useCurrency();
    const queryClient = useQueryClient();
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [activeTab, setActiveTab] = useState<'open' | 'cleared' | 'all'>('all');
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

    const flash = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 4500);
    };

    // Credit available to clear this vendor's open invoices (outstanding
    // advances + unapplied payments) — from the clearing read model.
    const { data: openItems } = useQuery({
        queryKey: ['vendor-open-items', vendor.id],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/payments/vendor-open-items/', {
                params: { vendor: vendor.id },
            });
            return data as {
                open_total: string; available_credit: string;
                advance_credit: string; payment_credit: string;
            };
        },
    });
    const availableCredit = Number(openItems?.available_credit ?? 0);

    // SAP F-44 style clearing. No ids → auto-clear every open invoice (FIFO);
    // ids → clear only the selected ones (manual).
    const clearMutation = useMutation({
        mutationFn: async (invoiceIds?: number[]) => {
            const { data } = await apiClient.post('/accounting/payments/clear-open-items/', {
                vendor: vendor.id,
                ...(invoiceIds && invoiceIds.length ? { invoice_ids: invoiceIds } : {}),
            });
            return data as { total_cleared: string; invoices_touched: number };
        },
        onSuccess: (res) => {
            queryClient.invalidateQueries({ queryKey: ['vendor-history', vendor.id] });
            queryClient.invalidateQueries({ queryKey: ['vendor-open-items', vendor.id] });
            setSelected(new Set());
            flash(`Cleared ${formatCurrency(res.total_cleared)} across ${res.invoices_touched} invoice(s).`, true);
        },
        onError: (err: unknown) => {
            const e = err as { response?: { data?: { error?: string } } };
            flash(e?.response?.data?.error || 'Clearing failed.', false);
        },
    });

    // A vendor's transaction history is a *subledger view* — it should
    // only show transactions that have actually hit the GL. Drafts and
    // Approved-but-unposted records exist in the AP operator worklist,
    // not in the ledger. Mixing them here was misleading: the totals
    // and balance counted Draft amounts that the GL hadn't recognised,
    // which contradicted what the Trial Balance shows for the same
    // vendor.
    //
    // GL-recognised statuses (the only ones that belong on the ledger):
    //   • Invoice → 'Posted' | 'Partially Paid' | 'Paid'
    //                (Draft / Approved haven't posted; Void was reversed)
    //   • Payment → 'Posted'
    //                (Draft / Cancelled haven't posted; Void was reversed)
    //   • Return  → 'Posted' | 'Approved' | 'Processed'
    //                (covers the common return lifecycles across models)
    const isOnLedger = (sourceType: string, status: string): boolean => {
        const s = (status || '').toLowerCase();
        if (sourceType === 'invoice') {
            return s === 'posted' || s === 'partially paid' || s === 'paid';
        }
        if (sourceType === 'payment') {
            return s === 'posted';
        }
        if (sourceType === 'return') {
            return s === 'posted' || s === 'approved' || s === 'processed';
        }
        return false;
    };

    const transactions: TransactionRow[] = useMemo(() => {
        if (!data) return [];
        const rows: TransactionRow[] = [];

        // Vendor Invoices → Credit. Clearance derives from the
        // serializer's ``balance_due`` (authoritative outstanding);
        // fall back to ``total - paid_amount`` when it's absent.
        (data.invoices || []).forEach((inv: any) => {
            const total = Number(inv.total_amount) || 0;
            const balanceDue = inv.balance_due != null
                ? Number(inv.balance_due)
                : Math.max(0, total - (Number(inv.paid_amount) || 0));
            const paidAmount = Math.max(0, total - balanceDue);
            const clearKey: ClearKey =
                balanceDue <= 0.005 ? 'paid'
                : paidAmount > 0.005 ? 'partial'
                : 'open';
            rows.push({
                id: `inv-${inv.id}`,
                date: inv.invoice_date,
                reference: inv.invoice_number || inv.reference || '',
                type: 'Invoice',
                description: inv.description || `Invoice ${inv.invoice_number}`,
                debit: 0,
                credit: total,
                status: inv.status,
                sourceType: 'invoice',
                clearKey,
                paidAmount,
                balanceDue,
                invoiceId: inv.id,
            });
        });

        // Payments → Debit. A posted payment means cash left the bank,
        // so it reads as "Cleared" on the subledger.
        (data.payments || []).forEach((pmt: any) => {
            rows.push({
                id: `pmt-${pmt.id}`,
                date: pmt.payment_date,
                reference: pmt.payment_number || pmt.reference_number || '',
                type: 'Payment',
                description: `${pmt.payment_method || ''} Payment ${pmt.payment_number}`,
                debit: Number(pmt.total_amount) || 0,
                credit: 0,
                status: pmt.status,
                sourceType: 'payment',
                clearKey: 'cleared',
                paidAmount: 0,
                balanceDue: 0,
            });
        });

        // Purchase Returns → Debit (reduces AP); a posted return is an
        // applied credit on the account.
        (data.returns || []).forEach((ret: any) => {
            rows.push({
                id: `ret-${ret.id}`,
                date: ret.return_date,
                reference: ret.return_number || `RET-${ret.id}`,
                type: 'Return',
                description: ret.reason || `Purchase Return`,
                debit: Number(ret.total_amount) || 0,
                credit: 0,
                status: ret.status,
                sourceType: 'return',
                clearKey: 'applied',
                paidAmount: 0,
                balanceDue: 0,
            });
        });

        // Filter out non-GL statuses — see ``isOnLedger``. Totals,
        // balance, and the matched/unmatched splits below all derive
        // from this list, so excluding drafts here propagates correctly.
        return rows
            .filter((r) => isOnLedger(r.sourceType, r.status))
            .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    }, [data]);

    // Diagnostic counts — show the operator how many documents were
    // filtered out so they don't think the modal is missing data.
    const draftCounts = useMemo(() => {
        if (!data) return { invoices: 0, payments: 0, returns: 0, total: 0 };
        const invoices = (data.invoices || []).filter(
            (inv: any) => !isOnLedger('invoice', inv.status),
        ).length;
        const payments = (data.payments || []).filter(
            (pmt: any) => !isOnLedger('payment', pmt.status),
        ).length;
        const returns = (data.returns || []).filter(
            (ret: any) => !isOnLedger('return', ret.status),
        ).length;
        return { invoices, payments, returns, total: invoices + payments + returns };
    }, [data]);

    // Tab buckets. Open = unpaid / part-paid invoices (the items to clear);
    // Cleared = settled invoices plus applied payments/returns.
    const isOpen = (t: TransactionRow) => t.clearKey === 'open' || t.clearKey === 'partial';
    const openRows = transactions.filter(isOpen);
    const clearedRows = transactions.filter(t => !isOpen(t));
    const visibleRows = activeTab === 'open' ? openRows
        : activeTab === 'cleared' ? clearedRows
        : transactions;
    // Open invoices the operator can pick to clear (only these are selectable).
    const selectableOpenIds = openRows
        .filter(t => t.sourceType === 'invoice' && t.invoiceId != null)
        .map(t => t.id);

    const totalDebit = transactions.reduce((s, t) => s + t.debit, 0);
    const totalCredit = transactions.reduce((s, t) => s + t.credit, 0);
    const balance = totalCredit - totalDebit;

    // Supplier-level clearance — driven by real invoice settlement, not
    // the manual match tool. ``totalCleared`` is how much of this
    // supplier's invoiced amount has actually been paid; ``totalOpen``
    // is what's still outstanding. Drives the banner below.
    const invoiceRows = transactions.filter(t => t.sourceType === 'invoice');
    const totalCleared = invoiceRows.reduce((s, t) => s + t.paidAmount, 0);
    const totalOpen = invoiceRows.reduce((s, t) => s + t.balanceDue, 0);
    const fullyPaidCount = invoiceRows.filter(t => t.clearKey === 'paid').length;

    const toggleSelect = (id: string) => {
        const next = new Set(selected);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        setSelected(next);
    };

    // Map selected row ids → numeric VendorInvoice ids for the clearing API.
    const selectedInvoiceIds = [...selected]
        .map(id => transactions.find(t => t.id === id)?.invoiceId)
        .filter((v): v is number => v != null);

    const clearSelected = () => {
        if (selectedInvoiceIds.length === 0 || clearMutation.isPending) return;
        clearMutation.mutate(selectedInvoiceIds);
    };
    const autoClearAll = () => {
        if (clearMutation.isPending) return;
        clearMutation.mutate(undefined);   // no ids → clear all open (FIFO)
    };

    const buildExportOptions = (): ExportOptions => {
        const columns = [
            { header: 'Date', key: 'date' },
            { header: 'Reference', key: 'reference' },
            { header: 'Type', key: 'type' },
            { header: 'Description', key: 'description' },
            { header: 'Debit', key: 'debit', align: 'right' as const },
            { header: 'Credit', key: 'credit', align: 'right' as const },
            { header: 'Status', key: 'status' },
            { header: 'Clearance', key: 'clearance' },
        ];
        return {
            title: 'Vendor Transaction History',
            subtitle: `${vendor.name} (${vendor.code})`,
            dateRange: `Exported ${new Date().toLocaleDateString('en-GB')}`,
            sections: [
                {
                    title: 'Transactions',
                    columns,
                    rows: transactions.map(t => ({
                        date: formatDate(t.date),
                        reference: t.reference,
                        type: t.type,
                        description: t.description,
                        debit: t.debit > 0 ? formatCurrency(t.debit) : '',
                        credit: t.credit > 0 ? formatCurrency(t.credit) : '',
                        status: t.status,
                        // Real clearance status (strip the ✓ glyph for a clean cell).
                        clearance: CLEAR_BADGE[t.clearKey].label.replace(/\s*✓/, ''),
                    })),
                    totals: {
                        date: '', reference: '', type: '', description: 'Totals',
                        debit: formatCurrency(totalDebit),
                        credit: formatCurrency(totalCredit),
                        status: '', clearance: '',
                    },
                },
            ],
            summary: [
                { label: 'Total Debit', value: formatCurrency(totalDebit) },
                { label: 'Total Credit', value: formatCurrency(totalCredit) },
                {
                    label: 'Balance (Cr - Dr)',
                    value: `${formatCurrency(Math.abs(balance))} ${balance > 0 ? 'CR' : balance < 0 ? 'DR' : ''}`.trim(),
                },
                { label: 'Cleared (paid)', value: formatCurrency(totalCleared) },
                { label: 'Outstanding', value: formatCurrency(totalOpen) },
            ],
        };
    };

    const handleExportExcel = () => {
        if (transactions.length === 0) return;
        const safeCode = (vendor.code || 'vendor').replace(/[^a-zA-Z0-9_-]/g, '_');
        exportToCSV(buildExportOptions(), `vendor-transactions-${safeCode}.csv`);
    };

    const typeColors: Record<string, { bg: string; color: string }> = {
        Invoice: { bg: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' },
        Payment: { bg: 'rgba(34, 197, 94, 0.1)', color: '#22c55e' },
        Return: { bg: 'rgba(168, 85, 247, 0.1)', color: '#a855f7' },
    };

    const thStyle: React.CSSProperties = {
        padding: '0.625rem 0.75rem', fontSize: 'var(--text-xs)', fontWeight: 700,
        textTransform: 'uppercase', letterSpacing: '0.05em',
        color: 'var(--color-text-muted)', whiteSpace: 'nowrap',
        borderBottom: '2px solid var(--color-border)',
    };

    const tdStyle: React.CSSProperties = {
        padding: '0.625rem 0.75rem', fontSize: 'var(--text-sm)',
        color: 'var(--color-text)', borderBottom: '1px solid var(--color-border)',
    };

    const renderRow = (t: TransactionRow) => {
        const tc = typeColors[t.type] || { bg: 'rgba(156,163,175,0.1)', color: '#6b7280' };
        // Only open invoices are selectable, and only on the Open Items tab.
        const selectable = activeTab === 'open' && selectableOpenIds.includes(t.id);
        const isSettled = t.clearKey === 'paid' || t.clearKey === 'cleared' || t.clearKey === 'applied';
        return (
            <tr key={t.id} style={{
                background: selected.has(t.id) ? 'rgba(79, 70, 229, 0.06)' : undefined,
            }}>
                <td style={{ ...tdStyle, width: '36px', textAlign: 'center' }}>
                    {selectable ? (
                        <input type="checkbox" checked={selected.has(t.id)}
                            onChange={() => toggleSelect(t.id)}
                            aria-label={`Select ${t.reference} to clear`}
                            style={{ cursor: 'pointer', accentColor: '#4f46e5' }} />
                    ) : isSettled ? (
                        <CheckCircle2 size={14} color="#22c55e" />
                    ) : null}
                </td>
                <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>
                    {formatDate(t.date)}
                </td>
                <td style={{ ...tdStyle, fontWeight: 600 }}>{t.reference}</td>
                <td style={tdStyle}>
                    <span style={{
                        padding: '0.15rem 0.5rem', borderRadius: '9999px', fontSize: 'var(--text-xs)',
                        fontWeight: 600, background: tc.bg, color: tc.color,
                    }}>
                        {t.type}
                    </span>
                </td>
                <td style={{ ...tdStyle, maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {t.description}
                </td>
                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: t.debit > 0 ? 600 : 400, color: t.debit > 0 ? '#22c55e' : 'var(--color-text-muted)' }}>
                    {t.debit > 0 ? formatCurrency(t.debit) : '—'}
                </td>
                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: t.credit > 0 ? 600 : 400, color: t.credit > 0 ? '#ef4444' : 'var(--color-text-muted)' }}>
                    {t.credit > 0 ? formatCurrency(t.credit) : '—'}
                </td>
                <td style={tdStyle}>
                    <span style={{
                        padding: '0.15rem 0.5rem', borderRadius: '9999px', fontSize: 'var(--text-xs)',
                        fontWeight: 600,
                        background: t.status === 'Posted' || t.status === 'Paid' ? 'rgba(34,197,94,0.1)' :
                            t.status === 'Void' ? 'rgba(239,68,68,0.1)' : 'rgba(156,163,175,0.1)',
                        color: t.status === 'Posted' || t.status === 'Paid' ? '#22c55e' :
                            t.status === 'Void' ? '#ef4444' : '#9ca3af',
                    }}>
                        {t.status}
                    </span>
                </td>
                <td style={tdStyle}>
                    {/* Real-data clearance badge — tells the operator at a
                        glance whether this document has been paid/matched,
                        independent of the manual match tool. */}
                    {(() => {
                        const c = CLEAR_BADGE[t.clearKey];
                        return (
                            <span
                                title={t.sourceType === 'invoice'
                                    ? `Paid ${formatCurrency(t.paidAmount)} of ${formatCurrency(t.credit)} · ${formatCurrency(t.balanceDue)} outstanding`
                                    : undefined}
                                style={{
                                    padding: '0.15rem 0.5rem', borderRadius: '9999px',
                                    fontSize: 'var(--text-xs)', fontWeight: 700,
                                    background: c.bg, color: c.color, whiteSpace: 'nowrap',
                                }}
                            >
                                {c.label}
                            </span>
                        );
                    })()}
                </td>
            </tr>
        );
    };

    return (
        <div style={{
            position: 'fixed', inset: 0, zIndex: 9999,
            background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '2rem',
        }} onClick={onClose} role="presentation">
            <div
                ref={dialogRef}
                role="dialog"
                aria-modal="true"
                aria-label={`Transaction history for ${vendor.name}`}
                style={{
                    background: 'var(--color-surface, #fff)', borderRadius: '16px',
                    width: '100%', maxWidth: '1100px', maxHeight: '90vh',
                    display: 'flex', flexDirection: 'column',
                    boxShadow: '0 25px 50px rgba(0,0,0,0.25)',
                }}
                onClick={e => e.stopPropagation()}
            >

                {/* Header */}
                <div style={{
                    padding: '1.5rem 1.75rem', borderBottom: '1px solid var(--color-border)',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                    <div>
                        <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                            Transaction History
                        </h2>
                        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', margin: '0.25rem 0 0' }}>
                            {vendor.name} <span style={{ fontWeight: 600, opacity: 0.7 }}>({vendor.code})</span>
                        </p>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <button
                            onClick={handleExportExcel}
                            disabled={isLoading || transactions.length === 0}
                            title="Export all transactions to Excel (.csv)"
                            style={{
                                display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                                padding: '0.5rem 0.9rem', borderRadius: '8px',
                                border: '1px solid #10b981',
                                background: '#ecfdf5', color: '#047857',
                                fontSize: 'var(--text-sm)', fontWeight: 600,
                                cursor: isLoading || transactions.length === 0 ? 'not-allowed' : 'pointer',
                                opacity: isLoading || transactions.length === 0 ? 0.5 : 1,
                                whiteSpace: 'nowrap',
                            }}
                        >
                            <Download size={16} /> Export to Excel
                        </button>
                        <button onClick={onClose} aria-label="Close" style={{
                            background: 'none', border: 'none', cursor: 'pointer',
                            color: 'var(--color-text-muted)', padding: '0.5rem',
                        }}>
                            <X size={20} />
                        </button>
                    </div>
                </div>

                {/* Summary Cards */}
                <div style={{ padding: '1rem 1.75rem', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
                    <div style={{
                        padding: '1rem', borderRadius: '10px',
                        background: 'rgba(34, 197, 94, 0.08)', border: '1px solid rgba(34, 197, 94, 0.2)',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                            <ArrowDownRight size={16} color="#22c55e" />
                            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: '#22c55e' }}>Total Debit</span>
                        </div>
                        <p style={{ fontSize: 'var(--text-lg)', fontWeight: 700, margin: 0, color: 'var(--color-text)' }}>
                            {formatCurrency(totalDebit)}
                        </p>
                    </div>
                    <div style={{
                        padding: '1rem', borderRadius: '10px',
                        background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.2)',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                            <ArrowUpRight size={16} color="#ef4444" />
                            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: '#ef4444' }}>Total Credit</span>
                        </div>
                        <p style={{ fontSize: 'var(--text-lg)', fontWeight: 700, margin: 0, color: 'var(--color-text)' }}>
                            {formatCurrency(totalCredit)}
                        </p>
                    </div>
                    <div style={{
                        padding: '1rem', borderRadius: '10px',
                        background: balance > 0 ? 'rgba(239, 68, 68, 0.08)' : 'rgba(34, 197, 94, 0.08)',
                        border: `1px solid ${balance > 0 ? 'rgba(239, 68, 68, 0.2)' : 'rgba(34, 197, 94, 0.2)'}`,
                    }}>
                        <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)', display: 'block', marginBottom: '0.35rem' }}>
                            Balance (Cr - Dr)
                        </span>
                        <p style={{
                            fontSize: 'var(--text-lg)', fontWeight: 700, margin: 0,
                            color: balance > 0 ? '#ef4444' : '#22c55e',
                        }}>
                            {formatCurrency(Math.abs(balance))} {balance > 0 ? 'CR' : balance < 0 ? 'DR' : ''}
                        </p>
                    </div>
                </div>

                {/* Clearance banner — at-a-glance "is this supplier paid &
                    matched?" Driven by real invoice settlement (paid vs
                    balance_due), not the manual match tool. Green when fully
                    cleared, amber while anything is still outstanding. */}
                {!isLoading && invoiceRows.length > 0 && (
                    <div style={{
                        margin: '0 1.75rem 0.75rem', padding: '0.7rem 1rem', borderRadius: 10,
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        gap: '1rem', flexWrap: 'wrap',
                        background: totalOpen <= 0.005 ? 'rgba(34,197,94,0.10)' : 'rgba(245,158,11,0.10)',
                        border: `1px solid ${totalOpen <= 0.005 ? 'rgba(34,197,94,0.30)' : 'rgba(245,158,11,0.30)'}`,
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <CheckCircle2 size={18} color={totalOpen <= 0.005 ? '#16a34a' : '#d97706'} />
                            <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-text)' }}>
                                {totalOpen <= 0.005
                                    ? 'All invoices cleared & matched'
                                    : `${fullyPaidCount} of ${invoiceRows.length} invoice${invoiceRows.length === 1 ? '' : 's'} fully paid`}
                            </span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', fontSize: 'var(--text-sm)' }}>
                            <span style={{ color: '#16a34a', fontWeight: 600 }}>
                                ✓ {formatCurrency(totalCleared)} cleared
                            </span>
                            <span style={{ color: totalOpen <= 0.005 ? 'var(--color-text-muted)' : '#d97706', fontWeight: 700 }}>
                                {formatCurrency(totalOpen)} outstanding
                            </span>
                        </div>
                    </div>
                )}

                {/* Draft-exclusion note. The vendor history is a GL
                    subledger view; drafts / unposted documents stay in
                    the AP operator worklist. We tell the operator how
                    many were filtered out so they don't think the modal
                    is missing data. */}
                {draftCounts.total > 0 && (
                    <div style={{
                        margin: '0 1.75rem 0.75rem', padding: '0.6rem 0.9rem',
                        borderRadius: 8,
                        background: 'rgba(148, 163, 184, 0.10)',
                        border: '1px solid rgba(148, 163, 184, 0.25)',
                        fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)',
                        display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
                    }}>
                        <span style={{ fontWeight: 700, color: 'var(--color-text)' }}>
                            Ledger view — Posted only.
                        </span>
                        <span>
                            Excluded from this view:
                            {draftCounts.invoices > 0 && ` ${draftCounts.invoices} draft / unposted invoice${draftCounts.invoices === 1 ? '' : 's'}`}
                            {draftCounts.invoices > 0 && (draftCounts.payments > 0 || draftCounts.returns > 0) && ','}
                            {draftCounts.payments > 0 && ` ${draftCounts.payments} draft / cancelled payment${draftCounts.payments === 1 ? '' : 's'}`}
                            {draftCounts.payments > 0 && draftCounts.returns > 0 && ','}
                            {draftCounts.returns > 0 && ` ${draftCounts.returns} unposted return${draftCounts.returns === 1 ? '' : 's'}`}
                            . Manage them in their respective modules.
                        </span>
                    </div>
                )}

                {/* Clearing result toast */}
                {toast && (
                    <div style={{
                        margin: '0 1.75rem 0.5rem', padding: '0.6rem 1rem', borderRadius: 8,
                        fontSize: 'var(--text-sm)', fontWeight: 600,
                        background: toast.ok ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
                        color: toast.ok ? '#16a34a' : '#b91c1c',
                        border: `1px solid ${toast.ok ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                    }}>{toast.msg}</div>
                )}

                {/* Tabs — Open Items / Cleared Items / All */}
                <div style={{
                    margin: '0 1.75rem', display: 'flex', gap: '0.25rem',
                    borderBottom: '1px solid var(--color-border)',
                }}>
                    {([
                        ['open', `Open Items (${openRows.length})`],
                        ['cleared', `Cleared Items (${clearedRows.length})`],
                        ['all', `All (${transactions.length})`],
                    ] as const).map(([key, label]) => (
                        <button
                            key={key}
                            onClick={() => { setActiveTab(key); setSelected(new Set()); }}
                            style={{
                                padding: '0.6rem 0.9rem', border: 'none', background: 'none',
                                cursor: 'pointer', fontSize: 'var(--text-sm)',
                                fontWeight: activeTab === key ? 700 : 500,
                                color: activeTab === key ? '#4f46e5' : 'var(--color-text-muted)',
                                borderBottom: `2px solid ${activeTab === key ? '#4f46e5' : 'transparent'}`,
                                marginBottom: '-1px',
                            }}>
                            {label}
                        </button>
                    ))}
                </div>

                {/* Clearing toolbar — Open Items tab only */}
                {activeTab === 'open' && (
                    <div style={{
                        margin: '0.75rem 1.75rem 0', padding: '0.75rem 1rem', borderRadius: '8px',
                        background: 'rgba(79, 70, 229, 0.06)', border: '1px solid rgba(79, 70, 229, 0.18)',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        gap: '1rem', flexWrap: 'wrap',
                    }}>
                        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>
                            {selected.size > 0
                                ? <><strong>{selected.size}</strong> invoice{selected.size === 1 ? '' : 's'} selected</>
                                : 'Select open invoices to clear, or auto-clear all.'}
                            <span style={{ marginLeft: '0.75rem', color: 'var(--color-text-muted)' }}>
                                {formatCurrency(availableCredit)} credit available
                            </span>
                        </span>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                            <button
                                onClick={clearSelected}
                                disabled={selected.size === 0 || availableCredit <= 0 || clearMutation.isPending}
                                style={{
                                    padding: '0.5rem 1rem', borderRadius: '8px', border: '1px solid #4f46e5',
                                    background: 'var(--color-surface)', color: '#4f46e5',
                                    cursor: (selected.size === 0 || availableCredit <= 0 || clearMutation.isPending) ? 'not-allowed' : 'pointer',
                                    fontWeight: 600, fontSize: 'var(--text-sm)',
                                    display: 'flex', alignItems: 'center', gap: '0.35rem',
                                    opacity: (selected.size === 0 || availableCredit <= 0) ? 0.5 : 1,
                                }}>
                                <CheckCheck size={14} /> Clear Selected
                            </button>
                            <button
                                onClick={autoClearAll}
                                disabled={openRows.length === 0 || availableCredit <= 0 || clearMutation.isPending}
                                title="Apply all available credit to open invoices, oldest-first (FIFO)"
                                style={{
                                    padding: '0.5rem 1rem', borderRadius: '8px', border: 'none',
                                    background: '#4f46e5', color: '#fff',
                                    cursor: (openRows.length === 0 || availableCredit <= 0 || clearMutation.isPending) ? 'not-allowed' : 'pointer',
                                    fontWeight: 600, fontSize: 'var(--text-sm)',
                                    display: 'flex', alignItems: 'center', gap: '0.35rem',
                                    opacity: (openRows.length === 0 || availableCredit <= 0) ? 0.5 : 1,
                                }}>
                                <Sparkles size={14} /> {clearMutation.isPending ? 'Clearing…' : 'Auto-Clear All'}
                            </button>
                        </div>
                    </div>
                )}

                {/* Table */}
                <div style={{ flex: 1, overflow: 'auto', padding: '0 1.75rem 1.5rem', marginTop: '0.75rem' }}>
                    {isLoading ? (
                        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                            Loading transactions...
                        </div>
                    ) : transactions.length === 0 ? (
                        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                            No transactions found for this vendor.
                        </div>
                    ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr>
                                    <th style={{ ...thStyle, width: '36px' }}></th>
                                    <th style={{ ...thStyle, textAlign: 'left' }}>Date</th>
                                    <th style={{ ...thStyle, textAlign: 'left' }}>Reference</th>
                                    <th style={{ ...thStyle, textAlign: 'left' }}>Type</th>
                                    <th style={{ ...thStyle, textAlign: 'left' }}>Description</th>
                                    <th style={{ ...thStyle, textAlign: 'right', color: '#22c55e' }}>Debit</th>
                                    <th style={{ ...thStyle, textAlign: 'right', color: '#ef4444' }}>Credit</th>
                                    <th style={{ ...thStyle, textAlign: 'left' }}>Status</th>
                                    <th style={{ ...thStyle, textAlign: 'left' }}>Clearance</th>
                                </tr>
                            </thead>
                            <tbody>
                                {visibleRows.length === 0 ? (
                                    <tr>
                                        <td colSpan={9} style={{ ...tdStyle, textAlign: 'center', color: 'var(--color-text-muted)', padding: '2rem' }}>
                                            {activeTab === 'open' ? 'No open items — everything is cleared.' : 'No cleared items yet.'}
                                        </td>
                                    </tr>
                                ) : (
                                    visibleRows.map(t => renderRow(t))
                                )}
                            </tbody>
                            <tfoot>
                                <tr style={{ borderTop: '2px solid var(--color-border)' }}>
                                    <td colSpan={5} style={{ ...tdStyle, fontWeight: 700, textAlign: 'right', borderBottom: 'none' }}>
                                        Totals:
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#22c55e', borderBottom: 'none' }}>
                                        {formatCurrency(totalDebit)}
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#ef4444', borderBottom: 'none' }}>
                                        {formatCurrency(totalCredit)}
                                    </td>
                                    <td style={{ ...tdStyle, borderBottom: 'none' }}></td>
                                    <td style={{ ...tdStyle, borderBottom: 'none' }}></td>
                                </tr>
                            </tfoot>
                        </table>
                    )}
                </div>
            </div>
        </div>
    );
};

export default VendorHistoryModal;
