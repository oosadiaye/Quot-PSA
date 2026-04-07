import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
    FileText, Filter, Send, Trash2,
    CheckCircle2, X, AlertTriangle, Percent,
} from 'lucide-react';
import {
    useCustomerInvoices, useSendCustomerInvoice,
    useDeleteCustomerInvoice,
    useAccountingSettings, useUpdateAccountingSettings,
} from '../hooks/useAccountingEnhancements';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import StatusBadge from '../components/shared/StatusBadge';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import { safeSum } from '../utils/currency';
import CustomerInvoiceForm from './CustomerInvoiceForm';
import { useDialog } from '../../../hooks/useDialog';
import '../styles/glassmorphism.css';

// ─── styles ────────────────────────────────────────────────────────────────
const inp: React.CSSProperties = {
    width: '100%', padding: '8px 12px', border: '2.5px solid #d1d5db',
    borderRadius: '8px', fontSize: '14px', outline: 'none',
    background: '#fafbfc', color: '#1e293b', boxSizing: 'border-box',
};

type ActiveTab = 'invoices' | 'settings';

// ─── tiny notification bar ─────────────────────────────────────────────────
function InlineAlert({ msg, type, onClose }: { msg: string; type: 'success' | 'error'; onClose: () => void }) {
    return (
        <div style={{
            display: 'flex', alignItems: 'center', gap: '10px',
            background: type === 'success' ? '#d1fae5' : '#fee2e2',
            border: `1px solid ${type === 'success' ? '#6ee7b7' : '#fca5a5'}`,
            borderRadius: '8px', padding: '12px 16px', marginBottom: '1rem',
            color: type === 'success' ? '#065f46' : '#991b1b',
        }}>
            {type === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
            <span style={{ fontSize: '14px', fontWeight: 500 }}>{msg}</span>
            <button onClick={onClose} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}>
                <X size={14} />
            </button>
        </div>
    );
}

const VALID_TABS: ActiveTab[] = ['invoices', 'settings'];

export default function ARManagement() {
    const { showConfirm } = useDialog();
    const { formatCurrency } = useCurrency();
    const [searchParams, setSearchParams] = useSearchParams();
    const tabParam = searchParams.get('tab') as ActiveTab | null;
    const [activeTab, setActiveTab] = useState<ActiveTab>(
        tabParam && VALID_TABS.includes(tabParam) ? tabParam : 'invoices'
    );

    const handleTabChange = (tab: ActiveTab) => {
        setActiveTab(tab);
        setSearchParams({ tab }, { replace: true });
    };
    const [statusFilter, setStatusFilter] = useState('');
    const [showInvoiceForm, setShowInvoiceForm] = useState(false);
    const [notification, setNotification] = useState<{ msg: string; type: 'success' | 'error' } | null>(null);
    const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

    // ─── queries ──────────────────────────────────────────────────────────
    const { data: invoices, isLoading } = useCustomerInvoices({ status: statusFilter });
    const { data: accountingSettings } = useAccountingSettings();

    // ─── mutations ────────────────────────────────────────────────────────
    const sendInvoice = useSendCustomerInvoice();
    const deleteInvoice = useDeleteCustomerInvoice();
    const updateSettings = useUpdateAccountingSettings();

    // ─── notification helpers ──────────────────────────────────────────────
    const showSuccess = (msg: string) => { setNotification({ msg, type: 'success' }); setTimeout(() => setNotification(null), 3500); };
    const showError = (msg: string) => { setNotification({ msg, type: 'error' }); setTimeout(() => setNotification(null), 4500); };

    // ─── summary metrics ──────────────────────────────────────────────────
    const totalReceivable = invoices ? safeSum(invoices, 'balance_due') : 0;
    const overdueCount = invoices?.filter((inv: any) => inv.status === 'Overdue').length || 0;
    const thisMonthRevenue = invoices?.filter((inv: any) => {
        const d = new Date(inv.invoice_date); const n = new Date();
        return d.getMonth() === n.getMonth() && d.getFullYear() === n.getFullYear();
    }).reduce((s: number, inv: any) => s + parseFloat(inv.total_amount || '0'), 0) || 0;

    // ─── handlers ─────────────────────────────────────────────────────────
    const handleSend = async (invoiceId: number) => {
        try {
            await sendInvoice.mutateAsync(invoiceId);
            showSuccess('Invoice sent to customer.');
        } catch { showError('Failed to send invoice.'); }
    };

    // ─── bulk selection helpers ─────────────────────────────────────────
    const draftInvoices = invoices?.filter((inv: any) => inv.status === 'Draft') || [];
    const allDraftSelected = draftInvoices.length > 0 && draftInvoices.every((inv: any) => selectedIds.has(inv.id));

    const toggleSelect = (id: number) => {
        setSelectedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    };

    const toggleSelectAll = () => {
        if (allDraftSelected) {
            setSelectedIds(new Set());
        } else {
            setSelectedIds(new Set(draftInvoices.map((inv: any) => inv.id)));
        }
    };

    const handleBulkDelete = async () => {
        if (selectedIds.size === 0) return;
        if (!await showConfirm(`Delete ${selectedIds.size} draft invoice(s)? This cannot be undone.`)) return;
        let deleted = 0;
        for (const id of selectedIds) {
            try {
                await deleteInvoice.mutateAsync(id);
                deleted++;
            } catch { /* skip non-deletable */ }
        }
        setSelectedIds(new Set());
        if (deleted > 0) showSuccess(`${deleted} invoice(s) deleted.`);
        else showError('No invoices could be deleted. Only draft invoices can be removed.');
    };

    const handleToggleDownpayment = async (enabled: boolean) => {
        try {
            await updateSettings.mutateAsync({ enable_sales_downpayment: enabled });
            showSuccess(enabled ? 'Sales downpayment enabled.' : 'Sales downpayment disabled.');
        } catch { showError('Failed to update setting.'); }
    };

    // ─── loading / form screens ────────────────────────────────────────────
    if (isLoading) return <LoadingScreen message="Loading invoices..." />;

    if (showInvoiceForm) {
        return (
            <AccountingLayout>
                <CustomerInvoiceForm onCancel={() => setShowInvoiceForm(false)} onSuccess={() => setShowInvoiceForm(false)} />
            </AccountingLayout>
        );
    }

    const tabs: { key: ActiveTab; label: string; icon: JSX.Element }[] = [
        { key: 'invoices', label: 'Invoices', icon: <FileText size={15} /> },
        { key: 'settings', label: 'Settings', icon: <Percent size={15} /> },
    ];

    return (
        <AccountingLayout>
            <div>
                {notification && <InlineAlert msg={notification.msg} type={notification.type} onClose={() => setNotification(null)} />}

                <PageHeader
                    title="Accounts Receivable"
                    subtitle="Manage customer invoices and AR settings"
                    icon={<FileText size={22} />}
                    actions={
                        <button className="btn btn-primary" onClick={() => setShowInvoiceForm(true)} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <FileText size={16} /> New Invoice
                        </button>
                    }
                />

                {/* Summary Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Total Receivable</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>{formatCurrency(totalReceivable)}</p>
                    </div>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>This Month</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-success)' }}>{formatCurrency(thisMonthRevenue)}</p>
                    </div>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Overdue</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-error)' }}>{overdueCount}</p>
                    </div>
                </div>

                {/* Tab Nav */}
                <div style={{ display: 'flex', gap: '4px', background: '#fff', padding: '6px', borderRadius: '10px', marginBottom: '1.5rem', boxShadow: '0 1px 3px rgba(0,0,0,0.06)', width: 'fit-content' }}>
                    {tabs.map(t => (
                        <button key={t.key} onClick={() => handleTabChange(t.key)} style={{
                            display: 'flex', alignItems: 'center', gap: '6px',
                            padding: '8px 16px', borderRadius: '8px', border: 'none',
                            background: activeTab === t.key ? '#191e6a' : 'transparent',
                            color: activeTab === t.key ? '#fff' : '#64748b',
                            fontWeight: activeTab === t.key ? 600 : 400,
                            fontSize: '14px', cursor: 'pointer', transition: 'all 0.15s',
                        }}>
                            {t.icon} {t.label}
                        </button>
                    ))}
                </div>

                {/* ── INVOICES TAB ── */}
                {activeTab === 'invoices' && (
                    <div>
                        <div className="card" style={{ padding: '1rem', marginBottom: '1.5rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                <Filter size={18} style={{ color: 'var(--color-text-muted)' }} />
                                <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="input" style={{ minWidth: '200px' }}>
                                    <option value="">All Statuses</option>
                                    <option value="Draft">Draft</option>
                                    <option value="Sent">Sent</option>
                                    <option value="Partially Paid">Partially Paid</option>
                                    <option value="Paid">Paid</option>
                                    <option value="Overdue">Overdue</option>
                                </select>
                                {selectedIds.size > 0 && (
                                    <button
                                        onClick={handleBulkDelete}
                                        disabled={deleteInvoice.isPending}
                                        style={{
                                            marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px',
                                            padding: '8px 16px', borderRadius: '8px', border: 'none',
                                            background: '#ef4444', color: '#fff', fontWeight: 600,
                                            fontSize: '13px', cursor: 'pointer',
                                        }}
                                    >
                                        <Trash2 size={14} />
                                        {deleteInvoice.isPending ? 'Deleting...' : `Delete ${selectedIds.size} Selected`}
                                    </button>
                                )}
                            </div>
                        </div>

                        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                        <th style={{ padding: '1rem 0.75rem 1rem 1.5rem', width: '40px' }}>
                                            <input
                                                type="checkbox"
                                                checked={allDraftSelected}
                                                onChange={toggleSelectAll}
                                                title="Select all draft invoices"
                                                style={{ width: '16px', height: '16px', cursor: 'pointer', accentColor: '#191e6a' }}
                                            />
                                        </th>
                                        {['Invoice #', 'Customer', 'Due Date', 'Balance Due', 'Status', 'Actions'].map(h => (
                                            <th key={h} style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', textAlign: h === 'Balance Due' ? 'right' : h === 'Actions' ? 'center' : 'left' }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {!invoices?.length ? (
                                        <tr><td colSpan={7} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                            <FileText size={48} style={{ margin: '0 auto 1rem', opacity: 0.3, display: 'block' }} />
                                            No customer invoices found
                                        </td></tr>
                                    ) : invoices.map((invoice: any) => (
                                        <tr key={invoice.id} style={{
                                            borderBottom: '1px solid var(--color-border)',
                                            background: selectedIds.has(invoice.id) ? 'rgba(25, 30, 106, 0.04)' : undefined,
                                        }}>
                                            <td style={{ padding: '1rem 0.75rem 1rem 1.5rem' }}>
                                                {invoice.status === 'Draft' ? (
                                                    <input
                                                        type="checkbox"
                                                        checked={selectedIds.has(invoice.id)}
                                                        onChange={() => toggleSelect(invoice.id)}
                                                        style={{ width: '16px', height: '16px', cursor: 'pointer', accentColor: '#191e6a' }}
                                                    />
                                                ) : (
                                                    <span style={{ display: 'inline-block', width: '16px' }} />
                                                )}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem', fontWeight: 600, color: 'var(--color-primary)' }}>
                                                {invoice.invoice_number}
                                                {invoice.document_type === 'Credit Memo' && (
                                                    <span style={{ marginLeft: '0.5rem', padding: '0.1rem 0.5rem', borderRadius: '20px', fontSize: '0.65rem', fontWeight: 700, background: 'rgba(13,148,136,0.12)', color: '#0d9488', verticalAlign: 'middle' }}>CM</span>
                                                )}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem' }}>{invoice.customer_name}</td>
                                            <td style={{ padding: '1rem 1.5rem' }}>{new Date(invoice.due_date).toLocaleDateString()}</td>
                                            <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontWeight: 600, color: invoice.status === 'Overdue' ? 'var(--color-error)' : 'var(--color-cta)' }}>
                                                {invoice.currency_code} {parseFloat(invoice.balance_due || '0').toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem' }}><StatusBadge status={invoice.status} /></td>
                                            <td style={{ padding: '1rem 1.5rem', textAlign: 'center' }}>
                                                {invoice.status === 'Draft' && (
                                                    <button className="btn btn-outline" style={{ padding: '0.375rem 0.75rem', fontSize: 'var(--text-xs)' }} onClick={() => handleSend(invoice.id)}>
                                                        <Send size={14} /> Send
                                                    </button>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {/* ── SETTINGS TAB ── */}
                {activeTab === 'settings' && (
                    <div style={{ maxWidth: '600px' }}>
                        <div className="card" style={{ padding: '24px' }}>
                            <h3 style={{ margin: '0 0 4px', fontSize: '16px', fontWeight: 700, color: 'var(--color-text)' }}>Sales Downpayment</h3>
                            <p style={{ margin: '0 0 20px', fontSize: '13px', color: 'var(--color-text-muted)' }}>
                                When enabled, users can create downpayment requests on sales orders — either as a fixed amount or a percentage of the order total.
                            </p>

                            {/* Toggle */}
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px', background: 'var(--color-surface)', borderRadius: '10px', marginBottom: '20px' }}>
                                <div>
                                    <p style={{ margin: 0, fontWeight: 600, fontSize: '14px', color: 'var(--color-text)' }}>Enable Sales Downpayments</p>
                                    <p style={{ margin: '2px 0 0', fontSize: '12px', color: 'var(--color-text-muted)' }}>Allow downpayment requests on sales orders</p>
                                </div>
                                <button
                                    onClick={() => handleToggleDownpayment(!accountingSettings?.enable_sales_downpayment)}
                                    disabled={updateSettings.isPending}
                                    style={{
                                        width: '48px', height: '26px', borderRadius: '13px', border: 'none', cursor: 'pointer',
                                        background: accountingSettings?.enable_sales_downpayment ? '#191e6a' : '#e2e8f0',
                                        position: 'relative', transition: 'background 0.2s', flexShrink: 0,
                                    }}
                                >
                                    <span style={{
                                        position: 'absolute', top: '3px',
                                        left: accountingSettings?.enable_sales_downpayment ? '25px' : '3px',
                                        width: '20px', height: '20px', borderRadius: '50%',
                                        background: '#fff', transition: 'left 0.2s',
                                        boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                                    }} />
                                </button>
                            </div>

                            {accountingSettings?.enable_sales_downpayment && (
                                <DownpaymentDefaults settings={accountingSettings} onSave={updateSettings.mutateAsync} onSuccess={showSuccess} onError={showError} />
                            )}
                        </div>
                    </div>
                )}
            </div>

        </AccountingLayout>
    );
}

// ─── Downpayment Defaults sub-component ───────────────────────────────────
function DownpaymentDefaults({ settings, onSave, onSuccess, onError }: { settings: any; onSave: (p: any) => Promise<any>; onSuccess: (m: string) => void; onError: (m: string) => void }) {
    const [type, setType] = useState<'percentage' | 'amount'>(settings.downpayment_default_type || 'percentage');
    const [value, setValue] = useState<string>(String(settings.downpayment_default_value || '30'));
    const [saving, setSaving] = useState(false);

    const handleSave = async () => {
        setSaving(true);
        try {
            await onSave({ downpayment_default_type: type, downpayment_default_value: value });
            onSuccess('Downpayment defaults saved.');
        } catch { onError('Failed to save defaults.'); }
        setSaving(false);
    };

    return (
        <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: '20px' }}>
            <p style={{ margin: '0 0 14px', fontSize: '14px', fontWeight: 600, color: 'var(--color-text)' }}>Default Downpayment Request</p>
            <p style={{ margin: '0 0 16px', fontSize: '12px', color: 'var(--color-text-muted)' }}>
                When a user clicks "Request Downpayment" on a sales order, these defaults will pre-fill the form.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '16px' }}>
                <div>
                    <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text)', display: 'block', marginBottom: '6px' }}>Calculation Type</label>
                    <div style={{ display: 'flex', gap: '8px' }}>
                        {(['percentage', 'amount'] as const).map(t => (
                            <button key={t} onClick={() => setType(t)} type="button" style={{
                                flex: 1, padding: '8px', borderRadius: '8px', border: '2px solid', cursor: 'pointer',
                                borderColor: type === t ? '#191e6a' : '#e2e8f0',
                                background: type === t ? '#eff6ff' : '#fff',
                                color: type === t ? '#191e6a' : '#64748b',
                                fontWeight: type === t ? 700 : 400, fontSize: '13px',
                            }}>
                                {t === 'percentage' ? '% Percent' : '# Fixed Amount'}
                            </button>
                        ))}
                    </div>
                </div>
                <div>
                    <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text)', display: 'block', marginBottom: '6px' }}>
                        Default Value {type === 'percentage' ? '(%)' : '(Amount)'}
                    </label>
                    <input style={{ width: '100%', padding: '8px 12px', border: '2.5px solid #d1d5db', borderRadius: '8px', fontSize: '14px', outline: 'none', background: '#fafbfc', color: '#1e293b', boxSizing: 'border-box' as const }}
                        type="number" step={type === 'percentage' ? '1' : '0.01'} min="0" max={type === 'percentage' ? '100' : undefined}
                        value={value} onChange={e => setValue(e.target.value)} />
                </div>
            </div>
            <button onClick={handleSave} disabled={saving} style={{ padding: '9px 20px', borderRadius: '8px', border: 'none', background: '#191e6a', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: '14px' }}>
                {saving ? 'Saving...' : 'Save Defaults'}
            </button>
        </div>
    );
}
