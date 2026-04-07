import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, Wallet, ArrowUpRight, ArrowDownLeft, Filter, Search, CheckCircle2, Clock, XCircle, Plus, Play } from 'lucide-react';
import { useBankAccounts, useBankAccountSummary, useBankAccountTransactions, useBankReconciliations, useCreateBankReconciliation, useReconcileBank } from '../../settings/hooks/useBankAccounts';
import { useCurrencies } from '../hooks/useAccountingEnhancements';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import logger from '../../../utils/logger';
import '../styles/glassmorphism.css';

const inputStyle: React.CSSProperties = {
    width: '100%', padding: '8px 12px',
    border: '2.5px solid #d1d5db', borderRadius: '8px',
    fontSize: '14px', outline: 'none', background: '#fafbfc', color: '#1e293b',
    boxSizing: 'border-box',
};

const RECON_STATUS: Record<string, { color: string; bg: string; icon: JSX.Element }> = {
    draft:       { color: '#374151', bg: '#f3f4f6', icon: <Clock size={12} /> },
    reconciled:  { color: '#065f46', bg: '#d1fae5', icon: <CheckCircle2 size={12} /> },
    approved:    { color: '#1e40af', bg: '#dbeafe', icon: <CheckCircle2 size={12} /> },
    rejected:    { color: '#991b1b', bg: '#fee2e2', icon: <XCircle size={12} /> },
};

function ReconBadge({ status }: { status: string }) {
    const cfg = RECON_STATUS[status?.toLowerCase()] ?? RECON_STATUS.draft;
    return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '2px 8px', borderRadius: '12px', fontSize: '12px', fontWeight: 600, color: cfg.color, background: cfg.bg }}>
            {cfg.icon}{status}
        </span>
    );
}

export default function BankCashDashboard() {
    const navigate = useNavigate();
    const [activeTab, setActiveTab] = useState<'overview' | 'reconciliation'>('overview');
    const [filterType, setFilterType] = useState('');
    const [searchQuery, setSearchQuery] = useState('');

    // Reconciliation state
    const [showNewReconModal, setShowNewReconModal] = useState(false);
    const [showReconcileModal, setShowReconcileModal] = useState<any>(null);
    const [reconForm, setReconForm] = useState({ bank_account: '', statement_date: '', statement_balance: '' });
    const [adjustForm, setAdjustForm] = useState({ deposits_in_transit: '0', outstanding_checks: '0', bank_charges: '0' });

    const { data: bankAccounts, isLoading } = useBankAccounts({ is_active: true });
    const { data: summary } = useBankAccountSummary();
    const { data: currencies } = useCurrencies();
    const { data: reconciliations } = useBankReconciliations({});
    const createRecon = useCreateBankReconciliation();
    const reconcileBank = useReconcileBank();

    const defaultCurrencies = currencies?.filter((c: any) => c.is_active).slice(0, 4) || [];

    const filteredAccounts = bankAccounts?.filter((account: any) => {
        const matchesType = !filterType || 
            (filterType === 'bank' && account.account_type === 'Bank') ||
            (filterType === 'cash' && ['Cash', 'Petty Cash', 'Imprest'].includes(account.account_type));
        const matchesSearch = !searchQuery ||
            account.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            account.account_number.toLowerCase().includes(searchQuery.toLowerCase());
        return matchesType && matchesSearch;
    }) || [];

    const bankAccountsList = filteredAccounts.filter((a: any) => a.account_type === 'Bank');
    const cashAccountsList = filteredAccounts.filter((a: any) => ['Cash', 'Petty Cash', 'Imprest'].includes(a.account_type));

    const formatCurrency = (amount: number, currencyCode: string = 'USD') => {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: currencyCode,
            minimumFractionDigits: 2,
        }).format(amount);
    };

    const handleAccountClick = (accountId: number) => {
        navigate(`/accounting/bank-cash/${accountId}`);
    };

    const handleCreateRecon = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createRecon.mutateAsync(reconForm);
            setShowNewReconModal(false);
            setReconForm({ bank_account: '', statement_date: '', statement_balance: '' });
            setActiveTab('reconciliation');
        } catch (err) {
            logger.error('Failed to create reconciliation:', err);
        }
    };

    const handleReconcile = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!showReconcileModal) return;
        try {
            await reconcileBank.mutateAsync({
                id: showReconcileModal.id,
                deposits_in_transit: Number(adjustForm.deposits_in_transit),
                outstanding_checks: Number(adjustForm.outstanding_checks),
                bank_charges: Number(adjustForm.bank_charges),
            });
            setShowReconcileModal(null);
            setAdjustForm({ deposits_in_transit: '0', outstanding_checks: '0', bank_charges: '0' });
        } catch (err) {
            logger.error('Failed to reconcile:', err);
        }
    };

    if (isLoading) {
        return <LoadingScreen message="Loading bank accounts..." />;
    }

    return (
        <AccountingLayout>
            <div>
                <PageHeader
                    title="Bank & Cash"
                    subtitle="Manage bank accounts and view treasury balances across currencies."
                    icon={<Building2 size={22} />}
                    actions={activeTab === 'reconciliation' ? (
                        <button onClick={() => setShowNewReconModal(true)} style={{
                            display: 'flex', alignItems: 'center', gap: '6px',
                            padding: '9px 16px', borderRadius: '8px', border: 'none',
                            background: '#191e6a', color: '#fff', fontWeight: 600,
                            fontSize: '14px', cursor: 'pointer',
                        }}>
                            <Plus size={14} /> New Reconciliation
                        </button>
                    ) : undefined}
                />

                {/* Tab Nav */}
                <div style={{ display: 'flex', gap: '4px', background: '#fff', padding: '6px', borderRadius: '10px', marginBottom: '1.5rem', boxShadow: '0 1px 3px rgba(0,0,0,0.06)', width: 'fit-content' }}>
                    {[
                        { key: 'overview', label: 'Overview' },
                        { key: 'reconciliation', label: 'Bank Reconciliation' },
                    ].map(tab => (
                        <button key={tab.key} onClick={() => setActiveTab(tab.key as any)} style={{
                            padding: '8px 16px', borderRadius: '8px', border: 'none',
                            background: activeTab === tab.key ? '#191e6a' : 'transparent',
                            color: activeTab === tab.key ? '#fff' : '#64748b',
                            fontWeight: activeTab === tab.key ? 600 : 400,
                            fontSize: '14px', cursor: 'pointer', transition: 'all 0.15s ease',
                        }}>
                            {tab.label}
                        </button>
                    ))}
                </div>

                {activeTab === 'overview' && <div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
                    <div className="card">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                            <div style={{ padding: '0.5rem', borderRadius: '8px', background: 'rgba(36, 113, 163, 0.1)' }}>
                                <Building2 size={20} style={{ color: 'var(--color-primary)' }} />
                            </div>
                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Bank Balance</span>
                        </div>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>
                            {summary ? formatCurrency(summary.total_bank_balance) : '$0.00'}
                        </p>
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                            {summary?.bank_accounts_count || 0} accounts
                        </p>
                    </div>

                    <div className="card">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                            <div style={{ padding: '0.5rem', borderRadius: '8px', background: 'rgba(34, 197, 94, 0.1)' }}>
                                <Wallet size={20} style={{ color: 'var(--color-success)' }} />
                            </div>
                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Cash Balance</span>
                        </div>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>
                            {summary ? formatCurrency(summary.total_cash_balance) : '$0.00'}
                        </p>
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                            {summary?.cash_accounts_count || 0} accounts
                        </p>
                    </div>

                    <div className="card">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                            <div style={{ padding: '0.5rem', borderRadius: '8px', background: 'rgba(168, 85, 247, 0.1)' }}>
                                <ArrowDownLeft size={20} style={{ color: '#a855f7' }} />
                            </div>
                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Customer Advances</span>
                        </div>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>
                            {summary ? formatCurrency(summary.total_customer_advance) : '$0.00'}
                        </p>
                    </div>

                    <div className="card">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                            <div style={{ padding: '0.5rem', borderRadius: '8px', background: 'rgba(249, 115, 22, 0.1)' }}>
                                <ArrowUpRight size={20} style={{ color: 'var(--color-warning)' }} />
                            </div>
                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Supplier Advances</span>
                        </div>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>
                            {summary ? formatCurrency(summary.total_supplier_advance) : '$0.00'}
                        </p>
                    </div>
                </div>

                {defaultCurrencies.length > 1 && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text)' }}>
                            Multi-Currency Overview
                        </h3>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '400px' }}>
                                <thead>
                                    <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <th style={{ padding: '0.75rem', textAlign: 'left', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Account</th>
                                        {defaultCurrencies.map((curr: any) => (
                                            <th key={curr.id} style={{ padding: '0.75rem', textAlign: 'right', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>{curr.code}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredAccounts.slice(0, 5).map((account: any) => (
                                        <tr key={account.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                            <td style={{ padding: '0.75rem', fontWeight: 500 }}>{account.name}</td>
                                            {defaultCurrencies.map((curr: any) => (
                                                <td key={curr.id} style={{ padding: '0.75rem', textAlign: 'right', fontFamily: 'monospace' }}>
                                                    {account.currency_code === curr.code 
                                                        ? formatCurrency(parseFloat(account.current_balance), curr.code)
                                                        : '-'
                                                    }
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem' }}>
                    <div style={{ position: 'relative', flex: 1, maxWidth: '300px' }}>
                        <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                        <input
                            type="text"
                            placeholder="Search accounts..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="input"
                            style={{ paddingLeft: '40px' }}
                        />
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Filter size={18} style={{ color: 'var(--color-text-muted)' }} />
                        <select
                            className="input"
                            value={filterType}
                            onChange={(e) => setFilterType(e.target.value)}
                            style={{ minWidth: '150px' }}
                        >
                            <option value="">All Types</option>
                            <option value="bank">Bank</option>
                            <option value="cash">Cash / Petty Cash / Imprest</option>
                        </select>
                    </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem' }}>
                    <div>
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Building2 size={18} style={{ color: 'var(--color-primary)' }} />
                            Bank Accounts
                        </h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                            {bankAccountsList.length === 0 ? (
                                <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                    No bank accounts configured. Go to Settings to add bank accounts.
                                </div>
                            ) : (
                                bankAccountsList.map((account: any) => (
                                    <div
                                        key={account.id}
                                        className="card"
                                        style={{ cursor: 'pointer', transition: 'all 0.15s' }}
                                        onClick={() => handleAccountClick(account.id)}
                                        onMouseOver={(e) => e.currentTarget.style.borderColor = 'var(--color-primary)'}
                                        onMouseOut={(e) => e.currentTarget.style.borderColor = 'var(--color-border)'}
                                    >
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                            <div>
                                                <div style={{ fontWeight: 600, color: 'var(--color-text)', marginBottom: '0.25rem' }}>
                                                    {account.name}
                                                </div>
                                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                    {account.account_number} • {account.bank_name || 'N/A'}
                                                </div>
                                            </div>
                                            <div style={{ textAlign: 'right' }}>
                                                <div style={{ fontWeight: 700, fontSize: 'var(--text-lg)', color: 'var(--color-text)' }}>
                                                    {formatCurrency(parseFloat(account.current_balance), account.currency_code)}
                                                </div>
                                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                    {account.currency_code}
                                                </div>
                                            </div>
                                        </div>
                                        {account.advance_customer_balance > 0 || account.advance_supplier_balance > 0 ? (
                                            <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid var(--color-border)', display: 'flex', gap: '1.5rem', fontSize: 'var(--text-xs)' }}>
                                                {account.advance_customer_balance > 0 && (
                                                    <span style={{ color: '#a855f7' }}>Advance in: {formatCurrency(parseFloat(account.advance_customer_balance), account.currency_code)}</span>
                                                )}
                                                {account.advance_supplier_balance > 0 && (
                                                    <span style={{ color: 'var(--color-warning)' }}>Advance out: {formatCurrency(parseFloat(account.advance_supplier_balance), account.currency_code)}</span>
                                                )}
                                            </div>
                                        ) : null}
                                    </div>
                                ))
                            )}
                        </div>
                    </div>

                    <div>
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Wallet size={18} style={{ color: 'var(--color-success)' }} />
                            Cash Accounts
                        </h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                            {cashAccountsList.length === 0 ? (
                                <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                    No cash accounts configured. Go to Settings to add cash accounts.
                                </div>
                            ) : (
                                cashAccountsList.map((account: any) => (
                                    <div
                                        key={account.id}
                                        className="card"
                                        style={{ cursor: 'pointer', transition: 'all 0.15s' }}
                                        onClick={() => handleAccountClick(account.id)}
                                        onMouseOver={(e) => e.currentTarget.style.borderColor = 'var(--color-success)'}
                                        onMouseOut={(e) => e.currentTarget.style.borderColor = 'var(--color-border)'}
                                    >
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                            <div>
                                                <div style={{ fontWeight: 600, color: 'var(--color-text)', marginBottom: '0.25rem' }}>
                                                    {account.name}
                                                </div>
                                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                    {account.account_type}
                                                </div>
                                            </div>
                                            <div style={{ textAlign: 'right' }}>
                                                <div style={{ fontWeight: 700, fontSize: 'var(--text-lg)', color: 'var(--color-text)' }}>
                                                    {formatCurrency(parseFloat(account.current_balance), account.currency_code)}
                                                </div>
                                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                    {account.currency_code}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>
                </div>}

                {/* ── Reconciliation Tab ── */}
                {activeTab === 'reconciliation' && (
                    <div>
                        <div style={{ background: '#fff', borderRadius: '12px', boxShadow: '0 1px 3px rgba(0,0,0,0.06)', overflow: 'hidden' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ background: '#f4f7fb', borderBottom: '1px solid #e2e8f0' }}>
                                        {['Bank Account', 'Statement Date', 'Statement Balance', 'Book Balance', 'Difference', 'Status', 'Actions'].map(h => (
                                            <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {(!reconciliations || reconciliations.length === 0) ? (
                                        <tr><td colSpan={7} style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>
                                            No reconciliations yet. Click "New Reconciliation" to start one.
                                        </td></tr>
                                    ) : reconciliations.map((recon: any) => {
                                        const diff = Number(recon.difference ?? 0);
                                        return (
                                            <tr key={recon.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                                <td style={{ padding: '12px 16px', fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>
                                                    {recon.bank_account_name ?? recon.bank_account}
                                                </td>
                                                <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>
                                                    {recon.statement_date}
                                                </td>
                                                <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569', textAlign: 'right', fontFamily: 'monospace' }}>
                                                    {Number(recon.statement_balance).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                                </td>
                                                <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569', textAlign: 'right', fontFamily: 'monospace' }}>
                                                    {Number(recon.book_balance).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                                </td>
                                                <td style={{ padding: '12px 16px', fontSize: '13px', fontWeight: 600, textAlign: 'right', fontFamily: 'monospace', color: diff === 0 ? '#059669' : '#dc2626' }}>
                                                    {diff.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                                </td>
                                                <td style={{ padding: '12px 16px' }}>
                                                    <ReconBadge status={recon.status} />
                                                </td>
                                                <td style={{ padding: '12px 16px' }}>
                                                    {recon.status?.toLowerCase() === 'draft' && (
                                                        <button
                                                            onClick={() => { setShowReconcileModal(recon); setAdjustForm({ deposits_in_transit: String(recon.deposits_in_transit ?? 0), outstanding_checks: String(recon.outstanding_checks ?? 0), bank_charges: String(recon.bank_charges ?? 0) }); }}
                                                            style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '5px 10px', borderRadius: '6px', border: 'none', background: '#191e6a', color: '#fff', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}
                                                        >
                                                            <Play size={12} /> Reconcile
                                                        </button>
                                                    )}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </div>

            {/* ── New Reconciliation Modal ── */}
            {showNewReconModal && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
                    <div style={{ background: '#fff', borderRadius: '16px', padding: '28px', width: '440px' }}>
                        <h2 style={{ margin: '0 0 20px', fontSize: '18px', fontWeight: 700, color: '#1e293b' }}>New Bank Reconciliation</h2>
                        <form onSubmit={handleCreateRecon}>
                            <div style={{ marginBottom: '16px' }}>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Bank Account *</label>
                                <select style={inputStyle} required value={reconForm.bank_account} onChange={e => setReconForm(f => ({ ...f, bank_account: e.target.value }))}>
                                    <option value="">Select bank account...</option>
                                    {bankAccounts?.filter((a: any) => a.account_type === 'Bank').map((a: any) => (
                                        <option key={a.id} value={a.id}>{a.name} — {a.account_number}</option>
                                    ))}
                                </select>
                            </div>
                            <div style={{ marginBottom: '16px' }}>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Statement Date *</label>
                                <input style={inputStyle} type="date" required value={reconForm.statement_date} onChange={e => setReconForm(f => ({ ...f, statement_date: e.target.value }))} />
                            </div>
                            <div style={{ marginBottom: '24px' }}>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Statement Balance *</label>
                                <input style={inputStyle} type="number" step="0.01" required placeholder="0.00" value={reconForm.statement_balance} onChange={e => setReconForm(f => ({ ...f, statement_balance: e.target.value }))} />
                            </div>
                            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                                <button type="button" onClick={() => setShowNewReconModal(false)} style={{ padding: '9px 18px', borderRadius: '8px', border: '1.5px solid #e2e8f0', background: '#fff', color: '#374151', fontWeight: 600, cursor: 'pointer' }}>Cancel</button>
                                <button type="submit" disabled={createRecon.isPending} style={{ padding: '9px 18px', borderRadius: '8px', border: 'none', background: '#191e6a', color: '#fff', fontWeight: 600, cursor: 'pointer' }}>
                                    {createRecon.isPending ? 'Creating...' : 'Create'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ── Reconcile Adjustments Modal ── */}
            {showReconcileModal && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
                    <div style={{ background: '#fff', borderRadius: '16px', padding: '28px', width: '480px' }}>
                        <h2 style={{ margin: '0 0 4px', fontSize: '18px', fontWeight: 700, color: '#1e293b' }}>Reconcile Account</h2>
                        <p style={{ margin: '0 0 20px', fontSize: '13px', color: '#64748b' }}>
                            Statement Date: {showReconcileModal.statement_date} · Statement Balance: {Number(showReconcileModal.statement_balance).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </p>
                        <form onSubmit={handleReconcile}>
                            <div style={{ marginBottom: '16px' }}>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>
                                    Deposits in Transit
                                    <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 400, marginLeft: '8px' }}>Deposits recorded in books but not on statement</span>
                                </label>
                                <input style={inputStyle} type="number" step="0.01" value={adjustForm.deposits_in_transit} onChange={e => setAdjustForm(f => ({ ...f, deposits_in_transit: e.target.value }))} />
                            </div>
                            <div style={{ marginBottom: '16px' }}>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>
                                    Outstanding Checks
                                    <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 400, marginLeft: '8px' }}>Checks issued but not yet cleared</span>
                                </label>
                                <input style={inputStyle} type="number" step="0.01" value={adjustForm.outstanding_checks} onChange={e => setAdjustForm(f => ({ ...f, outstanding_checks: e.target.value }))} />
                            </div>
                            <div style={{ marginBottom: '20px' }}>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>
                                    Bank Charges
                                    <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 400, marginLeft: '8px' }}>Service fees on statement not in books</span>
                                </label>
                                <input style={inputStyle} type="number" step="0.01" value={adjustForm.bank_charges} onChange={e => setAdjustForm(f => ({ ...f, bank_charges: e.target.value }))} />
                            </div>
                            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                                <button type="button" onClick={() => setShowReconcileModal(null)} style={{ padding: '9px 18px', borderRadius: '8px', border: '1.5px solid #e2e8f0', background: '#fff', color: '#374151', fontWeight: 600, cursor: 'pointer' }}>Cancel</button>
                                <button type="submit" disabled={reconcileBank.isPending} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 18px', borderRadius: '8px', border: 'none', background: '#059669', color: '#fff', fontWeight: 600, cursor: 'pointer' }}>
                                    <CheckCircle2 size={14} />
                                    {reconcileBank.isPending ? 'Reconciling...' : 'Reconcile'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </AccountingLayout>
    );
}
