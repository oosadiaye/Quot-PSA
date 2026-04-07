import { useState } from 'react';
import { Plus, FileText, ArrowLeftRight, Banknote, GitMerge, Play, Trash2, CheckCircle, Clock, AlertCircle } from 'lucide-react';
import {
    useCompanies, useICInvoices, useCreateICInvoice, usePostICInvoice, useDeleteICInvoice,
    useICTransfers, useCreateICTransfer, useDeleteICTransfer,
    useICCashTransfers, useCreateICCashTransfer, useDeleteICCashTransfer,
    useICAllocations, useCreateICAllocation,
} from '../hooks/useMultiCompany';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import { useDialog } from '../../../hooks/useDialog';

type Tab = 'invoices' | 'transfers' | 'cash' | 'allocations';

const statusStyle = (status: string) => {
    const map: Record<string, { bg: string; color: string }> = {
        draft:   { bg: 'rgba(100,116,139,0.1)', color: '#64748b' },
        pending: { bg: 'rgba(245,158,11,0.1)',  color: '#f59e0b' },
        posted:  { bg: 'rgba(34,197,94,0.1)',   color: '#22c55e' },
        approved:{ bg: 'rgba(34,197,94,0.1)',   color: '#22c55e' },
        completed:{ bg: 'rgba(34,197,94,0.1)',  color: '#22c55e' },
        rejected:{ bg: 'rgba(239,68,68,0.1)',   color: '#ef4444' },
    };
    const s = map[status?.toLowerCase()] || map.draft;
    return { padding: '0.2rem 0.65rem', borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 600, background: s.bg, color: s.color };
};

const labelStyle: React.CSSProperties = {
    display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600,
    color: 'var(--color-text-muted)', marginBottom: '0.35rem', textTransform: 'uppercase',
};
const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.625rem 0.875rem', borderRadius: '8px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-sm)', outline: 'none',
};
const gridTwo: React.CSSProperties = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' };

export default function InterCompanyPage() {
    const { showAlert, showConfirm } = useDialog();
    const { formatCurrency } = useCurrency();
    const [tab, setTab] = useState<Tab>('invoices');

    // Invoice state
    const [showInvoiceModal, setShowInvoiceModal] = useState(false);
    const [invoiceForm, setInvoiceForm] = useState({
        from_company: '', to_company: '', invoice_date: '', due_date: '',
        description: '', amount: '', currency_code: 'NGN',
    });

    // Transfer state
    const [showTransferModal, setShowTransferModal] = useState(false);
    const [transferForm, setTransferForm] = useState({
        from_company: '', to_company: '', transfer_date: '', description: '', amount: '',
    });

    // Cash transfer state
    const [showCashModal, setShowCashModal] = useState(false);
    const [cashForm, setCashForm] = useState({
        from_company: '', to_company: '', transfer_date: '', amount: '',
        currency_code: 'NGN', reference: '', description: '',
    });

    // Allocation state
    const [showAllocModal, setShowAllocModal] = useState(false);
    const [allocForm, setAllocForm] = useState({
        source_company: '', allocation_date: '', allocation_method: 'equal',
        total_amount: '', description: '',
    });

    const { data: companies } = useCompanies({ is_active: true });
    const { data: icInvoices, isLoading: invLoading } = useICInvoices({});
    const { data: icTransfers, isLoading: trLoading } = useICTransfers({});
    const { data: icCash, isLoading: cashLoading } = useICCashTransfers({});
    const { data: icAlloc, isLoading: allocLoading } = useICAllocations({});

    const createInvoice = useCreateICInvoice();
    const postInvoice = usePostICInvoice();
    const deleteInvoice = useDeleteICInvoice();
    const createTransfer = useCreateICTransfer();
    const deleteTransfer = useDeleteICTransfer();
    const createCash = useCreateICCashTransfer();
    const deleteCash = useDeleteICCashTransfer();
    const createAlloc = useCreateICAllocation();

    const companyName = (id: any) => companies?.find((c: any) => String(c.id) === String(id))?.name || id;

    const handleCreateInvoice = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createInvoice.mutateAsync({ ...invoiceForm, amount: parseFloat(invoiceForm.amount) });
            setShowInvoiceModal(false);
            setInvoiceForm({ from_company: '', to_company: '', invoice_date: '', due_date: '', description: '', amount: '', currency_code: 'NGN' });
        } catch (err: any) {
            showAlert(err?.response?.data?.detail || 'Error creating IC invoice');
        }
    };

    const handlePostInvoice = async (id: number) => {
        if (!await showConfirm('Post this intercompany invoice? This will create journal entries.')) return;
        try {
            await postInvoice.mutateAsync(id);
        } catch (err: any) {
            showAlert(err?.response?.data?.detail || 'Error posting invoice');
        }
    };

    const handleCreateTransfer = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createTransfer.mutateAsync({ ...transferForm, amount: parseFloat(transferForm.amount) });
            setShowTransferModal(false);
            setTransferForm({ from_company: '', to_company: '', transfer_date: '', description: '', amount: '' });
        } catch (err: any) {
            showAlert(err?.response?.data?.detail || 'Error creating transfer');
        }
    };

    const handleCreateCash = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createCash.mutateAsync({ ...cashForm, amount: parseFloat(cashForm.amount) });
            setShowCashModal(false);
            setCashForm({ from_company: '', to_company: '', transfer_date: '', amount: '', currency_code: 'NGN', reference: '', description: '' });
        } catch (err: any) {
            showAlert(err?.response?.data?.detail || 'Error creating cash transfer');
        }
    };

    const handleCreateAlloc = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createAlloc.mutateAsync({ ...allocForm, total_amount: parseFloat(allocForm.total_amount) });
            setShowAllocModal(false);
            setAllocForm({ source_company: '', allocation_date: '', allocation_method: 'equal', total_amount: '', description: '' });
        } catch (err: any) {
            showAlert(err?.response?.data?.detail || 'Error creating allocation');
        }
    };

    const tabs: { id: Tab; label: string; icon: any; count?: number }[] = [
        { id: 'invoices',    label: 'IC Invoices',       icon: FileText,       count: icInvoices?.length },
        { id: 'transfers',   label: 'Asset Transfers',   icon: ArrowLeftRight, count: icTransfers?.length },
        { id: 'cash',        label: 'Cash Transfers',    icon: Banknote,       count: icCash?.length },
        { id: 'allocations', label: 'Cost Allocations',  icon: GitMerge,       count: icAlloc?.length },
    ];

    const isLoading = invLoading || trLoading || cashLoading || allocLoading;

    return (
        <AccountingLayout>
            <div style={{ maxWidth: '1200px' }}>
                <PageHeader
                    title="Intercompany Transactions"
                    subtitle="Manage invoices, transfers, and cost allocations between entities."
                    icon={<ArrowLeftRight size={22} />}
                    actions={
                        <button className="btn btn-primary" onClick={() => {
                            if (tab === 'invoices') setShowInvoiceModal(true);
                            else if (tab === 'transfers') setShowTransferModal(true);
                            else if (tab === 'cash') setShowCashModal(true);
                            else setShowAllocModal(true);
                        }}>
                            <Plus size={16} /> New {tab === 'invoices' ? 'Invoice' : tab === 'transfers' ? 'Transfer' : tab === 'cash' ? 'Cash Transfer' : 'Allocation'}
                        </button>
                    }
                />

                {/* Summary stats */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1.75rem' }}>
                    {[
                        { label: 'IC Invoices', value: icInvoices?.length ?? 0, icon: FileText, color: '#191e6a' },
                        { label: 'Asset Transfers', value: icTransfers?.length ?? 0, icon: ArrowLeftRight, color: '#0d9488' },
                        { label: 'Cash Transfers', value: icCash?.length ?? 0, icon: Banknote, color: '#7c3aed' },
                        { label: 'Allocations', value: icAlloc?.length ?? 0, icon: GitMerge, color: '#f59e0b' },
                    ].map(s => (
                        <div key={s.label} className="card" style={{ padding: '1.25rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <div style={{ width: '40px', height: '40px', borderRadius: '10px', background: `${s.color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                <s.icon size={18} style={{ color: s.color }} />
                            </div>
                            <div>
                                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>{s.label}</p>
                                <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>{s.value}</p>
                            </div>
                        </div>
                    ))}
                </div>

                {/* Tabs */}
                <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '1.5rem', borderBottom: '2px solid var(--color-border)', paddingBottom: '0' }}>
                    {tabs.map(t => (
                        <button key={t.id} onClick={() => setTab(t.id)} style={{
                            display: 'flex', alignItems: 'center', gap: '0.5rem',
                            padding: '0.625rem 1.25rem', border: 'none', cursor: 'pointer',
                            background: 'none', fontFamily: 'inherit', fontSize: 'var(--text-sm)', fontWeight: tab === t.id ? 700 : 500,
                            color: tab === t.id ? 'var(--color-primary)' : 'var(--color-text-muted)',
                            borderBottom: `2.5px solid ${tab === t.id ? 'var(--color-primary)' : 'transparent'}`,
                            marginBottom: '-2px', transition: 'all 0.15s',
                        }}>
                            <t.icon size={15} />
                            {t.label}
                            {t.count !== undefined && (
                                <span style={{ padding: '0.1rem 0.5rem', borderRadius: '9999px', fontSize: '11px', fontWeight: 700, background: tab === t.id ? 'rgba(25,30,106,0.1)' : 'rgba(100,116,139,0.1)', color: tab === t.id ? 'var(--color-primary)' : 'var(--color-text-muted)' }}>
                                    {t.count}
                                </span>
                            )}
                        </button>
                    ))}
                </div>

                {isLoading && <LoadingScreen message="Loading transactions..." />}

                {/* IC Invoices tab */}
                {!isLoading && tab === 'invoices' && (
                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr>
                                    <th style={{ padding: '0.875rem 1.25rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)', background: 'var(--color-surface-hover)', letterSpacing: '0.05em' }}>Invoice #</th>
                                    <th style={{ padding: '0.875rem 1.25rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)', background: 'var(--color-surface-hover)', letterSpacing: '0.05em' }}>From</th>
                                    <th style={{ padding: '0.875rem 1.25rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)', background: 'var(--color-surface-hover)', letterSpacing: '0.05em' }}>To</th>
                                    <th style={{ padding: '0.875rem 1.25rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)', background: 'var(--color-surface-hover)', letterSpacing: '0.05em' }}>Date</th>
                                    <th style={{ padding: '0.875rem 1.25rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)', background: 'var(--color-surface-hover)', letterSpacing: '0.05em' }}>Amount</th>
                                    <th style={{ padding: '0.875rem 1.25rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)', background: 'var(--color-surface-hover)', letterSpacing: '0.05em' }}>Status</th>
                                    <th style={{ padding: '0.875rem 1.25rem', background: 'var(--color-surface-hover)' }}></th>
                                </tr>
                            </thead>
                            <tbody>
                                {!icInvoices?.length ? (
                                    <tr><td colSpan={7} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No intercompany invoices yet. Click "New Invoice" to create one.</td></tr>
                                ) : icInvoices.map((inv: any) => (
                                    <tr key={inv.id} style={{ borderTop: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.875rem 1.25rem', fontWeight: 600, fontSize: 'var(--text-sm)', color: 'var(--color-primary)' }}>{inv.invoice_number || `IC-${inv.id}`}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)' }}>{companyName(inv.from_company)}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)' }}>{companyName(inv.to_company)}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{inv.invoice_date}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', textAlign: 'right', fontWeight: 600, fontSize: 'var(--text-sm)' }}>{formatCurrency(inv.amount)}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', textAlign: 'center' }}><span style={statusStyle(inv.status)}>{inv.status}</span></td>
                                        <td style={{ padding: '0.875rem 1.25rem' }}>
                                            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                                {inv.status === 'draft' && (
                                                    <button onClick={() => handlePostInvoice(inv.id)} title="Post Invoice"
                                                        style={{ background: 'rgba(25,30,106,0.08)', border: 'none', borderRadius: '6px', padding: '0.35rem 0.6rem', cursor: 'pointer', color: 'var(--color-primary)', display: 'flex', alignItems: 'center', gap: '4px', fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                                                        <Play size={12} /> Post
                                                    </button>
                                                )}
                                                {inv.status !== 'posted' && (
                                                    <button onClick={() => deleteInvoice.mutate(inv.id)} title="Delete"
                                                        style={{ background: 'rgba(239,68,68,0.08)', border: 'none', borderRadius: '6px', padding: '0.35rem 0.5rem', cursor: 'pointer', color: '#ef4444', display: 'flex', alignItems: 'center' }}>
                                                        <Trash2 size={13} />
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* Asset Transfers tab */}
                {!isLoading && tab === 'transfers' && (
                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr>
                                    {['From', 'To', 'Date', 'Amount', 'Description', ''].map(h => (
                                        <th key={h} style={{ padding: '0.875rem 1.25rem', textAlign: h === 'Amount' ? 'right' : 'left', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)', background: 'var(--color-surface-hover)', letterSpacing: '0.05em' }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {!icTransfers?.length ? (
                                    <tr><td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No asset transfers yet.</td></tr>
                                ) : icTransfers.map((tr: any) => (
                                    <tr key={tr.id} style={{ borderTop: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>{companyName(tr.from_company)}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)' }}>{companyName(tr.to_company)}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{tr.transfer_date}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', textAlign: 'right', fontWeight: 600, fontSize: 'var(--text-sm)' }}>{formatCurrency(tr.amount)}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{tr.description || '—'}</td>
                                        <td style={{ padding: '0.875rem 1.25rem' }}>
                                            <button onClick={() => deleteTransfer.mutate(tr.id)} style={{ background: 'rgba(239,68,68,0.08)', border: 'none', borderRadius: '6px', padding: '0.35rem 0.5rem', cursor: 'pointer', color: '#ef4444', display: 'flex', alignItems: 'center' }}><Trash2 size={13} /></button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* Cash Transfers tab */}
                {!isLoading && tab === 'cash' && (
                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr>
                                    {['From', 'To', 'Date', 'Amount', 'Currency', 'Reference', ''].map(h => (
                                        <th key={h} style={{ padding: '0.875rem 1.25rem', textAlign: h === 'Amount' ? 'right' : 'left', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)', background: 'var(--color-surface-hover)', letterSpacing: '0.05em' }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {!icCash?.length ? (
                                    <tr><td colSpan={7} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No cash transfers yet.</td></tr>
                                ) : icCash.map((ct: any) => (
                                    <tr key={ct.id} style={{ borderTop: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>{companyName(ct.from_company)}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)' }}>{companyName(ct.to_company)}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{ct.transfer_date}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', textAlign: 'right', fontWeight: 600, fontSize: 'var(--text-sm)' }}>{formatCurrency(ct.amount)}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)' }}>{ct.currency_code}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{ct.reference || '—'}</td>
                                        <td style={{ padding: '0.875rem 1.25rem' }}>
                                            <button onClick={() => deleteCash.mutate(ct.id)} style={{ background: 'rgba(239,68,68,0.08)', border: 'none', borderRadius: '6px', padding: '0.35rem 0.5rem', cursor: 'pointer', color: '#ef4444', display: 'flex', alignItems: 'center' }}><Trash2 size={13} /></button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* Cost Allocations tab */}
                {!isLoading && tab === 'allocations' && (
                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr>
                                    {['Source Company', 'Date', 'Method', 'Total Amount', 'Description', ''].map(h => (
                                        <th key={h} style={{ padding: '0.875rem 1.25rem', textAlign: h === 'Total Amount' ? 'right' : 'left', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)', background: 'var(--color-surface-hover)', letterSpacing: '0.05em' }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {!icAlloc?.length ? (
                                    <tr><td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No cost allocations yet.</td></tr>
                                ) : icAlloc.map((al: any) => (
                                    <tr key={al.id} style={{ borderTop: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>{companyName(al.source_company)}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{al.allocation_date}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)', textTransform: 'capitalize' }}>{al.allocation_method}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', textAlign: 'right', fontWeight: 600, fontSize: 'var(--text-sm)' }}>{formatCurrency(al.total_amount)}</td>
                                        <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{al.description || '—'}</td>
                                        <td style={{ padding: '0.875rem 1.25rem' }}></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* ── IC Invoice Modal ─────────────────────────────── */}
                {showInvoiceModal && (
                    <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.5)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <div className="card" style={{ width: '520px', maxHeight: '90vh', overflowY: 'auto' }}>
                            <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, marginBottom: '1.5rem' }}>New Intercompany Invoice</h3>
                            <form onSubmit={handleCreateInvoice} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                <div style={gridTwo}>
                                    <div>
                                        <label style={labelStyle}>From Company<span className="required-mark"> *</span></label>
                                        <select style={inputStyle} required value={invoiceForm.from_company} onChange={e => setInvoiceForm(f => ({ ...f, from_company: e.target.value }))}>
                                            <option value="">Select company</option>
                                            {companies?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>To Company<span className="required-mark"> *</span></label>
                                        <select style={inputStyle} required value={invoiceForm.to_company} onChange={e => setInvoiceForm(f => ({ ...f, to_company: e.target.value }))}>
                                            <option value="">Select company</option>
                                            {companies?.filter((c: any) => String(c.id) !== invoiceForm.from_company).map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                                        </select>
                                    </div>
                                </div>
                                <div style={gridTwo}>
                                    <div>
                                        <label style={labelStyle}>Invoice Date<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="date" required value={invoiceForm.invoice_date} onChange={e => setInvoiceForm(f => ({ ...f, invoice_date: e.target.value }))} />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Due Date</label>
                                        <input style={inputStyle} type="date" value={invoiceForm.due_date} onChange={e => setInvoiceForm(f => ({ ...f, due_date: e.target.value }))} />
                                    </div>
                                </div>
                                <div style={gridTwo}>
                                    <div>
                                        <label style={labelStyle}>Amount<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="number" step="0.01" min="0.01" required value={invoiceForm.amount} onChange={e => setInvoiceForm(f => ({ ...f, amount: e.target.value }))} placeholder="0.00" />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Currency</label>
                                        <input style={inputStyle} value={invoiceForm.currency_code} onChange={e => setInvoiceForm(f => ({ ...f, currency_code: e.target.value }))} placeholder="NGN" />
                                    </div>
                                </div>
                                <div>
                                    <label style={labelStyle}>Description</label>
                                    <input style={inputStyle} value={invoiceForm.description} onChange={e => setInvoiceForm(f => ({ ...f, description: e.target.value }))} placeholder="Invoice description..." />
                                </div>
                                <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                                    <button type="button" className="btn btn-outline" onClick={() => setShowInvoiceModal(false)}>Cancel</button>
                                    <button type="submit" className="btn btn-primary" disabled={createInvoice.isPending}>{createInvoice.isPending ? 'Creating...' : 'Create Invoice'}</button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}

                {/* ── Asset Transfer Modal ─────────────────────────── */}
                {showTransferModal && (
                    <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.5)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <div className="card" style={{ width: '480px' }}>
                            <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, marginBottom: '1.5rem' }}>New Asset Transfer</h3>
                            <form onSubmit={handleCreateTransfer} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                <div style={gridTwo}>
                                    <div>
                                        <label style={labelStyle}>From Company<span className="required-mark"> *</span></label>
                                        <select style={inputStyle} required value={transferForm.from_company} onChange={e => setTransferForm(f => ({ ...f, from_company: e.target.value }))}>
                                            <option value="">Select</option>
                                            {companies?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>To Company<span className="required-mark"> *</span></label>
                                        <select style={inputStyle} required value={transferForm.to_company} onChange={e => setTransferForm(f => ({ ...f, to_company: e.target.value }))}>
                                            <option value="">Select</option>
                                            {companies?.filter((c: any) => String(c.id) !== transferForm.from_company).map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                                        </select>
                                    </div>
                                </div>
                                <div style={gridTwo}>
                                    <div>
                                        <label style={labelStyle}>Transfer Date<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="date" required value={transferForm.transfer_date} onChange={e => setTransferForm(f => ({ ...f, transfer_date: e.target.value }))} />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Amount<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="number" step="0.01" min="0" required value={transferForm.amount} onChange={e => setTransferForm(f => ({ ...f, amount: e.target.value }))} placeholder="0.00" />
                                    </div>
                                </div>
                                <div>
                                    <label style={labelStyle}>Description</label>
                                    <input style={inputStyle} value={transferForm.description} onChange={e => setTransferForm(f => ({ ...f, description: e.target.value }))} placeholder="Transfer description..." />
                                </div>
                                <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                                    <button type="button" className="btn btn-outline" onClick={() => setShowTransferModal(false)}>Cancel</button>
                                    <button type="submit" className="btn btn-primary" disabled={createTransfer.isPending}>{createTransfer.isPending ? 'Creating...' : 'Create Transfer'}</button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}

                {/* ── Cash Transfer Modal ──────────────────────────── */}
                {showCashModal && (
                    <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.5)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <div className="card" style={{ width: '520px' }}>
                            <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, marginBottom: '1.5rem' }}>New Cash Transfer</h3>
                            <form onSubmit={handleCreateCash} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                <div style={gridTwo}>
                                    <div>
                                        <label style={labelStyle}>From Company<span className="required-mark"> *</span></label>
                                        <select style={inputStyle} required value={cashForm.from_company} onChange={e => setCashForm(f => ({ ...f, from_company: e.target.value }))}>
                                            <option value="">Select</option>
                                            {companies?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>To Company<span className="required-mark"> *</span></label>
                                        <select style={inputStyle} required value={cashForm.to_company} onChange={e => setCashForm(f => ({ ...f, to_company: e.target.value }))}>
                                            <option value="">Select</option>
                                            {companies?.filter((c: any) => String(c.id) !== cashForm.from_company).map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                                        </select>
                                    </div>
                                </div>
                                <div style={gridTwo}>
                                    <div>
                                        <label style={labelStyle}>Date<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="date" required value={cashForm.transfer_date} onChange={e => setCashForm(f => ({ ...f, transfer_date: e.target.value }))} />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Amount<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="number" step="0.01" min="0" required value={cashForm.amount} onChange={e => setCashForm(f => ({ ...f, amount: e.target.value }))} placeholder="0.00" />
                                    </div>
                                </div>
                                <div style={gridTwo}>
                                    <div>
                                        <label style={labelStyle}>Currency</label>
                                        <input style={inputStyle} value={cashForm.currency_code} onChange={e => setCashForm(f => ({ ...f, currency_code: e.target.value }))} placeholder="NGN" />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Reference</label>
                                        <input style={inputStyle} value={cashForm.reference} onChange={e => setCashForm(f => ({ ...f, reference: e.target.value }))} placeholder="Ref. number" />
                                    </div>
                                </div>
                                <div>
                                    <label style={labelStyle}>Description</label>
                                    <input style={inputStyle} value={cashForm.description} onChange={e => setCashForm(f => ({ ...f, description: e.target.value }))} placeholder="Transfer description..." />
                                </div>
                                <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                                    <button type="button" className="btn btn-outline" onClick={() => setShowCashModal(false)}>Cancel</button>
                                    <button type="submit" className="btn btn-primary" disabled={createCash.isPending}>{createCash.isPending ? 'Creating...' : 'Create Transfer'}</button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}

                {/* ── Cost Allocation Modal ────────────────────────── */}
                {showAllocModal && (
                    <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.5)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <div className="card" style={{ width: '480px' }}>
                            <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, marginBottom: '1.5rem' }}>New Cost Allocation</h3>
                            <form onSubmit={handleCreateAlloc} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                <div>
                                    <label style={labelStyle}>Source Company<span className="required-mark"> *</span></label>
                                    <select style={inputStyle} required value={allocForm.source_company} onChange={e => setAllocForm(f => ({ ...f, source_company: e.target.value }))}>
                                        <option value="">Select company</option>
                                        {companies?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                                    </select>
                                </div>
                                <div style={gridTwo}>
                                    <div>
                                        <label style={labelStyle}>Allocation Date<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="date" required value={allocForm.allocation_date} onChange={e => setAllocForm(f => ({ ...f, allocation_date: e.target.value }))} />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Total Amount<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="number" step="0.01" min="0" required value={allocForm.total_amount} onChange={e => setAllocForm(f => ({ ...f, total_amount: e.target.value }))} placeholder="0.00" />
                                    </div>
                                </div>
                                <div>
                                    <label style={labelStyle}>Allocation Method</label>
                                    <select style={inputStyle} value={allocForm.allocation_method} onChange={e => setAllocForm(f => ({ ...f, allocation_method: e.target.value }))}>
                                        <option value="equal">Equal Split</option>
                                        <option value="revenue">Revenue-Based</option>
                                        <option value="headcount">Headcount-Based</option>
                                        <option value="manual">Manual</option>
                                    </select>
                                </div>
                                <div>
                                    <label style={labelStyle}>Description</label>
                                    <input style={inputStyle} value={allocForm.description} onChange={e => setAllocForm(f => ({ ...f, description: e.target.value }))} placeholder="Allocation description..." />
                                </div>
                                <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                                    <button type="button" className="btn btn-outline" onClick={() => setShowAllocModal(false)}>Cancel</button>
                                    <button type="submit" className="btn btn-primary" disabled={createAlloc.isPending}>{createAlloc.isPending ? 'Creating...' : 'Create Allocation'}</button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}
            </div>
        </AccountingLayout>
    );
}
