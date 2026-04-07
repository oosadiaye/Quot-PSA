import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Receipt, Filter, CheckCircle, X, ChevronDown, Download, FileSpreadsheet } from 'lucide-react';
import { useVendorInvoices, useApproveVendorInvoice, useCreateVendorInvoice } from '../hooks/useAccountingEnhancements';
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

    const [actionsOpen, setActionsOpen] = useState(false);
    const actionsRef = useRef<HTMLDivElement>(null);

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

    const handleDownloadTemplate = () => {
        setActionsOpen(false);
        const headers = ['vendor_id', 'reference', 'description', 'invoice_date', 'due_date', 'account_code', 'line_description', 'amount', 'tax_code', 'withholding_tax_code'];
        const sampleRow = ['1', 'INV-001', 'Office supplies', '2026-01-15', '2026-02-15', '50100000', 'Printer paper', '25000.00', '', ''];
        const csv = [headers.join(','), sampleRow.join(',')].join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'vendor_invoice_bulk_template.csv';
        a.click();
        window.URL.revokeObjectURL(url);
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
        if (await showConfirm('Approve this vendor invoice?')) {
            try {
                await approveInvoice.mutateAsync(invoiceId);
            } catch (error) {
                logger.error('Failed to approve invoice:', error);
            }
        }
    };

    const totalPayable = invoices ? safeSum(invoices, 'balance_due') : 0;
    const overdueCount = invoices?.filter((inv: any) => inv.status === 'Approved' && new Date(inv.due_date) < new Date()).length || 0;
    const pendingApproval = invoices?.filter((inv: any) => inv.status === 'Draft').length || 0;

    if (isLoading) {
        return <LoadingScreen message="Loading invoices..." />;
    }

    if (showForm) {
        return (
            <AccountingLayout>
                <VendorInvoiceForm
                    onCancel={() => setShowForm(false)}
                    onSuccess={() => setShowForm(false)}
                />
            </AccountingLayout>
        );
    }

    return (
        <>
            <AccountingLayout>
                <div>
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
                                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>Bulk import journal CSV</span>
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
                                <option value="Approved">Approved</option>
                                <option value="Partially Paid">Partially Paid</option>
                                <option value="Paid">Paid</option>
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
                                            {invoice.status === 'Draft' && (
                                                <button className="btn btn-outline" style={{ padding: '0.375rem 0.75rem', fontSize: 'var(--text-xs)' }} onClick={() => handleApprove(invoice.id)}>
                                                    <CheckCircle size={14} /> Approve
                                                </button>
                                            )}
                                            {invoice.status === 'Approved' && (
                                                <button className="btn btn-primary" style={{ padding: '0.375rem 0.75rem', fontSize: 'var(--text-xs)' }} onClick={() => navigate(`/accounting/payments/new?invoice=${invoice.id}`)}>Pay</button>
                                            )}
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

