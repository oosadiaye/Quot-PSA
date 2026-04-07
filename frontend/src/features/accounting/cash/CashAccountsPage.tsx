import { useState } from 'react';
import {
    Wallet, Plus, Search, DollarSign, RefreshCw, CheckCircle2,
    X, AlertTriangle, Play, Banknote, RotateCcw, Edit2, TrendingDown,
    ChevronRight, ChevronDown,
} from 'lucide-react';
import {
    usePettyCashFunds, useCreatePettyCashFund, useUpdatePettyCashFund,
    usePettyCashVouchers, useCreatePettyCashVoucher,
    useApprovePettyCashVoucher, usePayPettyCashVoucher,
    usePettyCashReplenishments, useCreatePettyCashReplenishment, usePostPettyCashReplenishment,
    useCurrencies,
} from '../hooks/useAccountingEnhancements';
import { useBankAccounts, useCreateBankAccount } from '../../settings/hooks/useBankAccounts';
import { useAccounts } from '../hooks/useBudgetDimensions';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import StatusBadge from '../components/shared/StatusBadge';
import { useCurrency } from '../../../context/CurrencyContext';
import '../styles/glassmorphism.css';

// ─── constants ────────────────────────────────────────────────────────────────
type Tab = 'accounts' | 'petty-cash' | 'replenishments';

const ACCOUNT_TYPES = ['Cash', 'Petty Cash', 'Imprest'];

const TYPE_STYLE: Record<string, { bg: string; color: string; border: string }> = {
    'Cash':       { bg: '#f0fdf4', color: '#15803d', border: '#86efac' },
    'Petty Cash': { bg: '#fffbeb', color: '#b45309', border: '#fcd34d' },
    'Imprest':    { bg: '#f5f3ff', color: '#6d28d9', border: '#c4b5fd' },
};

// ─── shared styles ────────────────────────────────────────────────────────────
const inp: React.CSSProperties = {
    width: '100%', padding: '8px 12px', border: '2px solid #e2e8f0',
    borderRadius: '8px', fontSize: '14px', outline: 'none',
    background: '#fafbfc', color: '#1e293b', boxSizing: 'border-box',
};
const sel: React.CSSProperties = { ...inp, cursor: 'pointer' };

// ─── inline alert ─────────────────────────────────────────────────────────────
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

// ─── confirm modal ────────────────────────────────────────────────────────────
function ConfirmModal({ title, message, confirmLabel, confirmColor, onConfirm, onCancel }: {
    title: string; message: string; confirmLabel: string;
    confirmColor: string; onConfirm: () => void; onCancel: () => void;
}) {
    return (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ background: '#fff', borderRadius: '14px', padding: '28px 32px', width: 420, boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
                <h3 style={{ margin: '0 0 8px', fontSize: '17px', fontWeight: 700, color: '#1e293b' }}>{title}</h3>
                <p style={{ margin: '0 0 24px', fontSize: '14px', color: '#64748b', lineHeight: 1.5 }}>{message}</p>
                <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                    <button onClick={onCancel} style={{ padding: '8px 18px', border: '1.5px solid #d1d5db', borderRadius: '8px', background: '#fff', cursor: 'pointer', fontSize: '14px' }}>Cancel</button>
                    <button onClick={onConfirm} style={{ padding: '8px 18px', border: 'none', borderRadius: '8px', background: confirmColor, color: '#fff', cursor: 'pointer', fontSize: '14px', fontWeight: 600 }}>{confirmLabel}</button>
                </div>
            </div>
        </div>
    );
}

// ─── fund health bar ──────────────────────────────────────────────────────────
function FundHealthBar({ current, float: floatAmt, minimum }: { current: number; float: number; minimum: number }) {
    const pct = floatAmt > 0 ? Math.min(100, (current / floatAmt) * 100) : 0;
    const isLow = current <= minimum && minimum > 0;
    const color = isLow ? '#ef4444' : pct > 50 ? '#10b981' : '#f59e0b';
    return (
        <div style={{ marginTop: '10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Fund Health</span>
                <span style={{ fontSize: '11px', fontWeight: 700, color }}>{pct.toFixed(0)}%</span>
            </div>
            <div style={{ height: '6px', background: '#f1f5f9', borderRadius: '999px', overflow: 'hidden' }}>
                <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: '999px', transition: 'width 0.4s ease' }} />
            </div>
            {isLow && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginTop: '5px' }}>
                    <AlertTriangle size={11} color="#ef4444" />
                    <span style={{ fontSize: '11px', color: '#ef4444', fontWeight: 600 }}>Below minimum — replenishment needed</span>
                </div>
            )}
        </div>
    );
}

// ─── voucher status pill ──────────────────────────────────────────────────────
const VOUCHER_STATUS_STYLE: Record<string, { bg: string; color: string }> = {
    PENDING:  { bg: '#fef9c3', color: '#854d0e' },
    APPROVED: { bg: '#dcfce7', color: '#166534' },
    REJECTED: { bg: '#fee2e2', color: '#991b1b' },
    PAID:     { bg: '#e0f2fe', color: '#075985' },
};
function VoucherStatus({ status }: { status: string }) {
    const s = VOUCHER_STATUS_STYLE[status] || { bg: '#f1f5f9', color: '#64748b' };
    return (
        <span style={{ ...s, padding: '3px 9px', borderRadius: '999px', fontSize: '11px', fontWeight: 700 }}>{status}</span>
    );
}

// ─── main component ───────────────────────────────────────────────────────────
export default function CashAccountsPage() {
    const { formatCurrency } = useCurrency();
    const [activeTab, setActiveTab] = useState<Tab>('accounts');
    const [notification, setNotification] = useState<{ msg: string; type: 'success' | 'error' } | null>(null);

    // Search / filter
    const [search, setSearch] = useState('');
    const [typeFilter, setTypeFilter] = useState('all');

    // Selected fund for drilling into vouchers
    const [selectedFund, setSelectedFund] = useState<any | null>(null);

    // Modals
    const [showAccountForm, setShowAccountForm] = useState(false);
    const [showFundForm, setShowFundForm] = useState(false);
    const [showVoucherForm, setShowVoucherForm] = useState(false);
    const [showReplenForm, setShowReplenForm] = useState(false);
    const [editFund, setEditFund] = useState<any | null>(null);
    const [approveConfirm, setApproveConfirm] = useState<{ id: number; num: string } | null>(null);
    const [payConfirm, setPayConfirm] = useState<{ id: number; num: string; amount: string } | null>(null);
    const [postReplenConfirm, setPostReplenConfirm] = useState<{ id: number; num: string } | null>(null);

    // ─── queries ─────────────────────────────────────────────────────────────
    const { data: bankAccounts, isLoading: loadingAccounts } = useBankAccounts({ is_active: true });
    const { data: pettyCashFunds, isLoading: loadingFunds } = usePettyCashFunds({ is_active: true });
    const { data: glAccounts } = useAccounts({ is_active: true });
    const { data: currencies } = useCurrencies();
    const voucherFilters = selectedFund ? { petty_cash_fund: selectedFund.id } : {};
    const { data: vouchers, isLoading: loadingVouchers } = usePettyCashVouchers(voucherFilters);
    const { data: replenishments, isLoading: loadingReplenishments } = usePettyCashReplenishments({});

    // ─── mutations ────────────────────────────────────────────────────────────
    const createBankAccount = useCreateBankAccount();
    const createFund = useCreatePettyCashFund();
    const updateFund = useUpdatePettyCashFund();
    const createVoucher = useCreatePettyCashVoucher();
    const approveVoucher = useApprovePettyCashVoucher();
    const payVoucher = usePayPettyCashVoucher();
    const createReplenishment = useCreatePettyCashReplenishment();
    const postReplenishment = usePostPettyCashReplenishment();

    // ─── helpers ──────────────────────────────────────────────────────────────
    const showSuccess = (msg: string) => { setNotification({ msg, type: 'success' }); setTimeout(() => setNotification(null), 3500); };
    const showError   = (msg: string) => { setNotification({ msg, type: 'error'   }); setTimeout(() => setNotification(null), 4500); };

    // ─── derived data ─────────────────────────────────────────────────────────
    const cashBankAccounts: any[] = (bankAccounts as any[] || []).filter((a: any) =>
        ACCOUNT_TYPES.includes(a.account_type)
    );
    const filtered = cashBankAccounts.filter((a: any) => {
        const matchesType = typeFilter === 'all' || a.account_type === typeFilter;
        const matchesSearch = !search || a.name?.toLowerCase().includes(search.toLowerCase()) || a.account_number?.toLowerCase().includes(search.toLowerCase());
        return matchesType && matchesSearch;
    });

    const totalByType = ACCOUNT_TYPES.reduce((acc, t) => {
        acc[t] = cashBankAccounts.filter(a => a.account_type === t).reduce((s: number, a: any) => s + parseFloat(a.current_balance || '0'), 0);
        return acc;
    }, {} as Record<string, number>);
    const totalAll = Object.values(totalByType).reduce((s, v) => s + v, 0);

    const funds: any[] = pettyCashFunds as any[] || [];
    const voucherList: any[] = vouchers as any[] || [];
    const replenList: any[] = replenishments as any[] || [];

    const fundStats = {
        totalFloat: funds.reduce((s, f) => s + parseFloat(f.float_amount || '0'), 0),
        totalBalance: funds.reduce((s, f) => s + parseFloat(f.current_balance || '0'), 0),
        lowFunds: funds.filter(f => parseFloat(f.current_balance) <= parseFloat(f.minimum_balance) && parseFloat(f.minimum_balance) > 0).length,
    };

    // ─── handlers ─────────────────────────────────────────────────────────────
    const handleCreateAccount = async (form: any) => {
        try {
            const payload: any = {
                name: form.name,
                account_number: form.account_number,
                account_type: form.account_type,
                opening_balance: parseFloat(form.opening_balance || '0'),
            };
            if (form.currency) payload.currency = Number(form.currency);
            if (form.gl_account) payload.gl_account = Number(form.gl_account);
            await createBankAccount.mutateAsync(payload);
            setShowAccountForm(false);
            showSuccess('Cash account created.');
        } catch (err: any) {
            const data = err?.response?.data;
            const msg = data ? (typeof data === 'string' ? data : Object.values(data).flat().join(' ')) : 'Failed to create account.';
            showError(msg);
        }
    };

    const handleSaveFund = async (form: any) => {
        // Strip empty strings so DRF FK/decimal validators don't reject them
        const payload: any = { ...form };
        if (!payload.bank_account) delete payload.bank_account;
        if (payload.minimum_balance === '') delete payload.minimum_balance;
        try {
            if (editFund) {
                await updateFund.mutateAsync({ id: editFund.id, ...payload });
                showSuccess('Fund updated.');
            } else {
                await createFund.mutateAsync(payload);
                showSuccess('Petty cash fund created.');
            }
            setShowFundForm(false);
            setEditFund(null);
        } catch (err: any) {
            const d = err?.response?.data;
            const msg = d?.detail || (d && typeof d === 'object' ? Object.values(d).flat().join(' ') : null) || 'Failed to save fund.';
            showError(String(msg));
        }
    };

    const handleCreateVoucher = async (form: any) => {
        try {
            await createVoucher.mutateAsync(form);
            setShowVoucherForm(false);
            showSuccess('Voucher created.');
        } catch (err: any) { showError(err?.response?.data?.detail || 'Failed to create voucher.'); }
    };

    const handleApprove = async () => {
        if (!approveConfirm) return;
        try {
            await approveVoucher.mutateAsync(approveConfirm.id);
            setApproveConfirm(null);
            showSuccess(`Voucher ${approveConfirm.num} approved.`);
        } catch (err: any) { setApproveConfirm(null); showError(err?.response?.data?.error || 'Approval failed.'); }
    };

    const handlePay = async () => {
        if (!payConfirm) return;
        try {
            await payVoucher.mutateAsync(payConfirm.id);
            setPayConfirm(null);
            showSuccess(`Voucher ${payConfirm.num} paid and posted to GL.`);
        } catch (err: any) { setPayConfirm(null); showError(err?.response?.data?.error || 'Payment failed.'); }
    };

    const handleCreateReplenishment = async (form: any) => {
        try {
            await createReplenishment.mutateAsync(form);
            setShowReplenForm(false);
            showSuccess('Replenishment created.');
        } catch (err: any) { showError(err?.response?.data?.detail || 'Failed to create replenishment.'); }
    };

    const handlePostReplenishment = async () => {
        if (!postReplenConfirm) return;
        try {
            await postReplenishment.mutateAsync(postReplenConfirm.id);
            setPostReplenConfirm(null);
            showSuccess(`Replenishment ${postReplenConfirm.num} posted to GL.`);
        } catch (err: any) { setPostReplenConfirm(null); showError(err?.response?.data?.error || 'Failed to post.'); }
    };

    // ─── Summary card ──────────────────────────────────────────────────────────
    const SumCard = ({ label, value, sub, accent, icon }: any) => (
        <div style={{
            background: '#fff', borderRadius: '14px', padding: '20px 22px',
            border: '1px solid #f1f5f9', boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
            borderLeft: `4px solid ${accent}`,
        }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                {icon}
                <span style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</span>
            </div>
            <div style={{ fontSize: '22px', fontWeight: 800, color: '#1e293b', letterSpacing: '-0.5px' }}>{value}</div>
            {sub && <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>{sub}</div>}
        </div>
    );

    // ─── Account form modal ───────────────────────────────────────────────────
    const [accountForm, setAccountForm] = useState({ name: '', account_number: '', account_type: 'Cash', currency: '', gl_account: '', opening_balance: '0' });
    const setAF = (k: string, v: string) => setAccountForm(p => ({ ...p, [k]: v }));
    const accountFormModal = showAccountForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ background: '#fff', borderRadius: '16px', padding: '32px', width: 480, boxShadow: '0 24px 80px rgba(0,0,0,0.2)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                    <div style={{ width: 38, height: 38, borderRadius: '10px', background: '#f0fdf4', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <DollarSign size={18} color="#16a34a" />
                    </div>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>New Cash Account</h3>
                    <button onClick={() => setShowAccountForm(false)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer' }}><X size={18} color="#94a3b8" /></button>
                </div>
                <form onSubmit={e => { e.preventDefault(); handleCreateAccount(accountForm); }}>
                    <div style={{ display: 'grid', gap: '14px' }}>
                        <div>
                            <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Account Name *</label>
                            <input style={inp} required value={accountForm.name} onChange={e => setAF('name', e.target.value)} placeholder="e.g. Main Cash Office" />
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                            <div>
                                <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Account Number *</label>
                                <input style={inp} required value={accountForm.account_number} onChange={e => setAF('account_number', e.target.value)} placeholder="CASH-001" />
                            </div>
                            <div>
                                <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Type *</label>
                                <select style={sel} value={accountForm.account_type} onChange={e => setAF('account_type', e.target.value)}>
                                    {ACCOUNT_TYPES.map(t => <option key={t}>{t}</option>)}
                                </select>
                            </div>
                        </div>
                        <div>
                            <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>GL Account</label>
                            <select style={sel} value={accountForm.gl_account} onChange={e => setAF('gl_account', e.target.value)}>
                                <option value="">-- Select GL Account --</option>
                                {(glAccounts as any[] || []).map((a: any) => <option key={a.id} value={a.id}>{a.code} - {a.name}</option>)}
                            </select>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                            <div>
                                <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Currency</label>
                                <select style={sel} value={accountForm.currency} onChange={e => setAF('currency', e.target.value)}>
                                    <option value="">-- Select Currency --</option>
                                    {(currencies as any[] || []).map((c: any) => <option key={c.id} value={c.id}>{c.code} - {c.name}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Opening Balance</label>
                                <input style={inp} type="number" step="0.01" value={accountForm.opening_balance} onChange={e => setAF('opening_balance', e.target.value)} />
                            </div>
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '24px' }}>
                        <button type="button" onClick={() => setShowAccountForm(false)} style={{ padding: '9px 20px', border: '1.5px solid #d1d5db', borderRadius: '8px', background: '#fff', cursor: 'pointer', fontSize: '14px' }}>Cancel</button>
                        <button type="submit" disabled={createBankAccount.isPending} style={{ padding: '9px 20px', border: 'none', borderRadius: '8px', background: '#15803d', color: '#fff', cursor: 'pointer', fontSize: '14px', fontWeight: 600 }}>
                            {createBankAccount.isPending ? 'Saving…' : 'Create Account'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );

    // ─── Fund form modal ──────────────────────────────────────────────────────
    const [fundForm, setFundForm] = useState({ name: '', code: '', bank_account: '', float_amount: '', minimum_balance: '' });
    const setFF = (k: string, v: string) => setFundForm(p => ({ ...p, [k]: v }));
    const pettyCashBankAccounts = cashBankAccounts.filter(a => a.account_type === 'Petty Cash');
    const fundFormModal = showFundForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ background: '#fff', borderRadius: '16px', padding: '32px', width: 480, boxShadow: '0 24px 80px rgba(0,0,0,0.2)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                    <div style={{ width: 38, height: 38, borderRadius: '10px', background: '#fffbeb', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Wallet size={18} color="#d97706" />
                    </div>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>{editFund ? 'Edit Fund' : 'New Petty Cash Fund'}</h3>
                    <button onClick={() => { setShowFundForm(false); setEditFund(null); }} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer' }}><X size={18} color="#94a3b8" /></button>
                </div>
                <form onSubmit={e => { e.preventDefault(); handleSaveFund(fundForm); }}>
                    <div style={{ display: 'grid', gap: '14px' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                            <div>
                                <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Fund Name *</label>
                                <input style={inp} required value={fundForm.name} onChange={e => setFF('name', e.target.value)} placeholder="Ops Petty Cash" />
                            </div>
                            <div>
                                <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Code *</label>
                                <input style={inp} required value={fundForm.code} onChange={e => setFF('code', e.target.value)} placeholder="PCF-001" />
                            </div>
                        </div>
                        <div>
                            <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Linked Bank Account (Petty Cash type)</label>
                            <select style={sel} value={fundForm.bank_account} onChange={e => setFF('bank_account', e.target.value)}>
                                <option value="">— none —</option>
                                {pettyCashBankAccounts.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
                            </select>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                            <div>
                                <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Float Amount *</label>
                                <input style={inp} type="number" step="0.01" required value={fundForm.float_amount} onChange={e => setFF('float_amount', e.target.value)} placeholder="50000" />
                            </div>
                            <div>
                                <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Minimum Balance</label>
                                <input style={inp} type="number" step="0.01" value={fundForm.minimum_balance} onChange={e => setFF('minimum_balance', e.target.value)} placeholder="10000" />
                            </div>
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '24px' }}>
                        <button type="button" onClick={() => { setShowFundForm(false); setEditFund(null); }} style={{ padding: '9px 20px', border: '1.5px solid #d1d5db', borderRadius: '8px', background: '#fff', cursor: 'pointer', fontSize: '14px' }}>Cancel</button>
                        <button type="submit" disabled={createFund.isPending || updateFund.isPending} style={{ padding: '9px 20px', border: 'none', borderRadius: '8px', background: '#d97706', color: '#fff', cursor: 'pointer', fontSize: '14px', fontWeight: 600 }}>
                            {createFund.isPending || updateFund.isPending ? 'Saving…' : editFund ? 'Update Fund' : 'Create Fund'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );

    // ─── Voucher form modal ───────────────────────────────────────────────────
    const [voucherForm, setVoucherForm] = useState({
        petty_cash_fund: selectedFund?.id?.toString() || '',
        voucher_date: new Date().toISOString().slice(0, 10),
        payee: '', description: '', amount: '', account: '',
    });
    const setVF = (k: string, v: string) => setVoucherForm(p => ({ ...p, [k]: v }));
    const expenseAccounts = (glAccounts as any[] || []).filter((a: any) => a.account_type === 'Expense');
    const voucherFormModal = showVoucherForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ background: '#fff', borderRadius: '16px', padding: '32px', width: 500, boxShadow: '0 24px 80px rgba(0,0,0,0.2)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                    <div style={{ width: 38, height: 38, borderRadius: '10px', background: '#fef9c3', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Banknote size={18} color="#b45309" />
                    </div>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>New Petty Cash Voucher</h3>
                    <button onClick={() => setShowVoucherForm(false)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer' }}><X size={18} color="#94a3b8" /></button>
                </div>
                <form onSubmit={e => { e.preventDefault(); handleCreateVoucher({ ...voucherForm, petty_cash_fund: Number(voucherForm.petty_cash_fund), account: Number(voucherForm.account) }); }}>
                    <div style={{ display: 'grid', gap: '14px' }}>
                        <div>
                            <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Petty Cash Fund *</label>
                            <select style={sel} required value={voucherForm.petty_cash_fund} onChange={e => setVF('petty_cash_fund', e.target.value)}>
                                <option value="">Select fund…</option>
                                {funds.map((f: any) => <option key={f.id} value={f.id}>{f.name} (Balance: {formatCurrency(f.current_balance)})</option>)}
                            </select>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                            <div>
                                <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Voucher Date *</label>
                                <input style={inp} type="date" required value={voucherForm.voucher_date} onChange={e => setVF('voucher_date', e.target.value)} />
                            </div>
                            <div>
                                <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Amount *</label>
                                <input style={inp} type="number" step="0.01" required value={voucherForm.amount} onChange={e => setVF('amount', e.target.value)} placeholder="0.00" />
                            </div>
                        </div>
                        <div>
                            <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Payee *</label>
                            <input style={inp} required value={voucherForm.payee} onChange={e => setVF('payee', e.target.value)} placeholder="Who is being paid?" />
                        </div>
                        <div>
                            <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Description *</label>
                            <input style={inp} required value={voucherForm.description} onChange={e => setVF('description', e.target.value)} placeholder="Office stationery, transport, etc." />
                        </div>
                        <div>
                            <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Expense Account *</label>
                            <select style={sel} required value={voucherForm.account} onChange={e => setVF('account', e.target.value)}>
                                <option value="">Select account…</option>
                                {expenseAccounts.map((a: any) => <option key={a.id} value={a.id}>{a.code} — {a.name}</option>)}
                                {!(expenseAccounts.length) && (glAccounts as any[] || []).map((a: any) => <option key={a.id} value={a.id}>{a.code} — {a.name}</option>)}
                            </select>
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '24px' }}>
                        <button type="button" onClick={() => setShowVoucherForm(false)} style={{ padding: '9px 20px', border: '1.5px solid #d1d5db', borderRadius: '8px', background: '#fff', cursor: 'pointer', fontSize: '14px' }}>Cancel</button>
                        <button type="submit" disabled={createVoucher.isPending} style={{ padding: '9px 20px', border: 'none', borderRadius: '8px', background: '#b45309', color: '#fff', cursor: 'pointer', fontSize: '14px', fontWeight: 600 }}>
                            {createVoucher.isPending ? 'Saving…' : 'Create Voucher'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );

    // ─── Replenishment form modal ─────────────────────────────────────────────
    const cashOnlyAccounts = cashBankAccounts.filter(a => a.account_type === 'Cash');
    const [replenForm, setReplenForm] = useState({ petty_cash_fund: '', replenishment_date: new Date().toISOString().slice(0, 10), reimbursement_amount: '', bank_account: '' });
    const setRF = (k: string, v: string) => setReplenForm(p => ({ ...p, [k]: v }));
    const replenFormModal = showReplenForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ background: '#fff', borderRadius: '16px', padding: '32px', width: 460, boxShadow: '0 24px 80px rgba(0,0,0,0.2)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                    <div style={{ width: 38, height: 38, borderRadius: '10px', background: '#f0f9ff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <RotateCcw size={18} color="#0284c7" />
                    </div>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>New Replenishment</h3>
                    <button onClick={() => setShowReplenForm(false)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer' }}><X size={18} color="#94a3b8" /></button>
                </div>
                <form onSubmit={e => {
                    e.preventDefault();
                    handleCreateReplenishment({
                        ...replenForm,
                        petty_cash_fund: Number(replenForm.petty_cash_fund),
                        bank_account: Number(replenForm.bank_account),
                        vouchers_total: replenForm.reimbursement_amount,
                    });
                }}>
                    <div style={{ display: 'grid', gap: '14px' }}>
                        <div>
                            <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Fund to Replenish *</label>
                            <select style={sel} required value={replenForm.petty_cash_fund} onChange={e => setRF('petty_cash_fund', e.target.value)}>
                                <option value="">Select fund…</option>
                                {funds.map((f: any) => <option key={f.id} value={f.id}>{f.name} · Balance: {formatCurrency(f.current_balance)}</option>)}
                            </select>
                        </div>
                        <div>
                            <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Source Bank Account *</label>
                            <select style={sel} required value={replenForm.bank_account} onChange={e => setRF('bank_account', e.target.value)}>
                                <option value="">Select bank account…</option>
                                {cashOnlyAccounts.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
                                {!cashOnlyAccounts.length && cashBankAccounts.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
                            </select>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                            <div>
                                <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Date *</label>
                                <input style={inp} type="date" required value={replenForm.replenishment_date} onChange={e => setRF('replenishment_date', e.target.value)} />
                            </div>
                            <div>
                                <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Amount *</label>
                                <input style={inp} type="number" step="0.01" required value={replenForm.reimbursement_amount} onChange={e => setRF('reimbursement_amount', e.target.value)} placeholder="0.00" />
                            </div>
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '24px' }}>
                        <button type="button" onClick={() => setShowReplenForm(false)} style={{ padding: '9px 20px', border: '1.5px solid #d1d5db', borderRadius: '8px', background: '#fff', cursor: 'pointer', fontSize: '14px' }}>Cancel</button>
                        <button type="submit" disabled={createReplenishment.isPending} style={{ padding: '9px 20px', border: 'none', borderRadius: '8px', background: '#0284c7', color: '#fff', cursor: 'pointer', fontSize: '14px', fontWeight: 600 }}>
                            {createReplenishment.isPending ? 'Saving…' : 'Create Replenishment'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );

    // ─── Tab: Cash Accounts ───────────────────────────────────────────────────
    const accountsTabJSX = (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
                <div style={{ display: 'flex', gap: '10px', flex: 1, maxWidth: '480px' }}>
                    <div style={{ position: 'relative', flex: 1 }}>
                        <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                        <input style={{ ...inp, paddingLeft: '32px' }} placeholder="Search accounts…" value={search} onChange={e => setSearch(e.target.value)} />
                    </div>
                    <select style={{ ...sel, width: '160px' }} value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
                        <option value="all">All Types</option>
                        {ACCOUNT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                </div>
                <button onClick={() => setShowAccountForm(true)} style={{
                    display: 'flex', alignItems: 'center', gap: '6px',
                    padding: '9px 18px', border: 'none', borderRadius: '9px',
                    background: '#15803d', color: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: 600,
                }}>
                    <Plus size={14} /> New Account
                </button>
            </div>

            {loadingAccounts ? (
                <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>Loading…</div>
            ) : !filtered.length ? (
                <div style={{ textAlign: 'center', padding: '60px', background: '#f8fafc', borderRadius: '12px', border: '2px dashed #e2e8f0' }}>
                    <DollarSign size={40} color="#cbd5e1" style={{ marginBottom: '12px' }} />
                    <p style={{ color: '#94a3b8', fontSize: '14px', margin: 0 }}>No cash accounts found. Create one above.</p>
                </div>
            ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
                    {filtered.map((acct: any) => {
                        const ts = TYPE_STYLE[acct.account_type] || { bg: '#f8fafc', color: '#64748b', border: '#e2e8f0' };
                        return (
                            <div key={acct.id} style={{
                                background: '#fff', borderRadius: '14px', padding: '20px',
                                border: `1px solid ${ts.border}`, boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
                                transition: 'box-shadow 0.15s, transform 0.15s',
                            }}
                                onMouseOver={e => { (e.currentTarget as any).style.boxShadow = '0 4px 16px rgba(0,0,0,0.1)'; (e.currentTarget as any).style.transform = 'translateY(-1px)'; }}
                                onMouseOut={e => { (e.currentTarget as any).style.boxShadow = '0 1px 4px rgba(0,0,0,0.04)'; (e.currentTarget as any).style.transform = 'translateY(0)'; }}
                            >
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '14px' }}>
                                    <div>
                                        <div style={{ fontWeight: 700, fontSize: '15px', color: '#1e293b', marginBottom: '4px' }}>{acct.name}</div>
                                        <div style={{ fontSize: '12px', color: '#94a3b8', fontFamily: 'monospace' }}>{acct.account_number}</div>
                                    </div>
                                    <span style={{ ...ts, padding: '3px 10px', borderRadius: '999px', fontSize: '11px', fontWeight: 700, border: `1px solid ${ts.border}` }}>
                                        {acct.account_type}
                                    </span>
                                </div>
                                <div style={{ background: '#f8fafc', borderRadius: '10px', padding: '12px 14px' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <span style={{ fontSize: '12px', color: '#64748b' }}>Current Balance</span>
                                        <span style={{ fontSize: '18px', fontWeight: 800, color: '#1e293b', letterSpacing: '-0.5px' }}>
                                            {formatCurrency(parseFloat(acct.current_balance || '0'))}
                                        </span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px' }}>
                                        <span style={{ fontSize: '11px', color: '#94a3b8' }}>Currency</span>
                                        <span style={{ fontSize: '12px', fontWeight: 600, color: '#374151' }}>{acct.currency_code || acct.currency || '—'}</span>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );

    // ─── Tab: Petty Cash ──────────────────────────────────────────────────────
    const pettyCashTabJSX = (
        <div>
            <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: '20px', minHeight: '400px' }}>
                {/* Fund list */}
                <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <span style={{ fontSize: '13px', fontWeight: 700, color: '#374151' }}>Funds</span>
                        <button onClick={() => { setEditFund(null); setFundForm({ name: '', code: '', bank_account: '', float_amount: '', minimum_balance: '' }); setShowFundForm(true); }}
                            style={{ padding: '5px 12px', border: 'none', borderRadius: '7px', background: '#d97706', color: '#fff', cursor: 'pointer', fontSize: '12px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <Plus size={12} /> New
                        </button>
                    </div>
                    {loadingFunds ? (
                        <div style={{ padding: '20px', textAlign: 'center', color: '#94a3b8' }}>Loading…</div>
                    ) : !funds.length ? (
                        <div style={{ padding: '24px', textAlign: 'center', background: '#fafbfc', borderRadius: '10px', border: '2px dashed #e2e8f0' }}>
                            <Wallet size={28} color="#cbd5e1" style={{ marginBottom: '8px' }} />
                            <p style={{ margin: 0, fontSize: '13px', color: '#94a3b8' }}>No funds yet.</p>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {funds.map((fund: any) => {
                                const current = parseFloat(fund.current_balance || '0');
                                const floatAmt = parseFloat(fund.float_amount || '0');
                                const minimum = parseFloat(fund.minimum_balance || '0');
                                const isSelected = selectedFund?.id === fund.id;
                                const isLow = current <= minimum && minimum > 0;
                                return (
                                    <div key={fund.id}
                                        onClick={() => setSelectedFund(isSelected ? null : fund)}
                                        style={{
                                            background: isSelected ? '#fffbeb' : '#fff',
                                            border: `1.5px solid ${isSelected ? '#fcd34d' : isLow ? '#fca5a5' : '#e2e8f0'}`,
                                            borderRadius: '10px', padding: '14px', cursor: 'pointer',
                                            transition: 'all 0.15s',
                                        }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                            <div>
                                                <div style={{ fontWeight: 700, fontSize: '13px', color: '#1e293b' }}>{fund.name}</div>
                                                <div style={{ fontSize: '11px', color: '#94a3b8', fontFamily: 'monospace', marginTop: '2px' }}>{fund.code}</div>
                                                {fund.gl_account_code && (
                                                    <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                                        <span style={{ fontFamily: 'monospace', background: '#f1f5f9', padding: '1px 5px', borderRadius: '4px', color: '#475569', fontSize: '10px' }}>{fund.gl_account_code}</span>
                                                        <span style={{ color: '#94a3b8', fontSize: '10px' }}>{fund.gl_account_name}</span>
                                                    </div>
                                                )}
                                            </div>
                                            <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                                                <button onClick={e => { e.stopPropagation(); setEditFund(fund); setFundForm({ name: fund.name, code: fund.code, bank_account: fund.bank_account?.toString() || '', float_amount: fund.float_amount, minimum_balance: fund.minimum_balance }); setShowFundForm(true); }}
                                                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px' }}>
                                                    <Edit2 size={13} color="#94a3b8" />
                                                </button>
                                                {isSelected ? <ChevronDown size={14} color="#d97706" /> : <ChevronRight size={14} color="#94a3b8" />}
                                            </div>
                                        </div>
                                        <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'space-between' }}>
                                            <span style={{ fontSize: '12px', color: '#64748b' }}>Balance</span>
                                            <span style={{ fontSize: '13px', fontWeight: 700, color: isLow ? '#dc2626' : '#1e293b' }}>{formatCurrency(current)}</span>
                                        </div>
                                        <FundHealthBar current={current} float={floatAmt} minimum={minimum} />
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>

                {/* Vouchers panel */}
                <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '14px', overflow: 'hidden' }}>
                    <div style={{ padding: '16px 20px', background: '#fafbfc', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                            <span style={{ fontWeight: 700, fontSize: '14px', color: '#1e293b' }}>
                                {selectedFund ? `Vouchers — ${selectedFund.name}` : 'Vouchers — Select a fund'}
                            </span>
                            {selectedFund && (
                                <span style={{ fontSize: '12px', color: '#64748b', marginLeft: '10px' }}>
                                    Balance: <strong>{formatCurrency(selectedFund.current_balance)}</strong> / Float: {formatCurrency(selectedFund.float_amount)}
                                </span>
                            )}
                        </div>
                        <button onClick={() => { setVoucherForm(p => ({ ...p, petty_cash_fund: selectedFund?.id?.toString() || '' })); setShowVoucherForm(true); }}
                            style={{ padding: '7px 14px', border: 'none', borderRadius: '8px', background: '#b45309', color: '#fff', cursor: 'pointer', fontSize: '12px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '5px' }}>
                            <Plus size={13} /> New Voucher
                        </button>
                    </div>

                    {!selectedFund ? (
                        <div style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>
                            <TrendingDown size={36} color="#e2e8f0" style={{ marginBottom: '12px' }} />
                            <p style={{ margin: 0, fontSize: '13px' }}>Select a fund on the left to view its vouchers.</p>
                        </div>
                    ) : loadingVouchers ? (
                        <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8' }}>Loading vouchers…</div>
                    ) : !voucherList.length ? (
                        <div style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>
                            <p style={{ margin: 0, fontSize: '13px' }}>No vouchers for this fund yet.</p>
                        </div>
                    ) : (
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                                <thead>
                                    <tr style={{ background: '#f8fafc' }}>
                                        {['Voucher #', 'Date', 'Payee', 'Description', 'Amount', 'Status', 'Actions'].map(h => (
                                            <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, color: '#64748b', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid #e2e8f0', whiteSpace: 'nowrap' }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {voucherList.map((v: any) => (
                                        <tr key={v.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                            <td style={{ padding: '10px 14px', fontWeight: 600, color: '#1e293b', fontFamily: 'monospace', fontSize: '12px' }}>{v.voucher_number}</td>
                                            <td style={{ padding: '10px 14px', color: '#374151' }}>{v.voucher_date}</td>
                                            <td style={{ padding: '10px 14px', color: '#374151', maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.payee}</td>
                                            <td style={{ padding: '10px 14px', color: '#64748b', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.description}</td>
                                            <td style={{ padding: '10px 14px', fontWeight: 700, color: '#b45309' }}>{formatCurrency(parseFloat(v.amount))}</td>
                                            <td style={{ padding: '10px 14px' }}><VoucherStatus status={v.approval_status} /></td>
                                            <td style={{ padding: '10px 14px' }}>
                                                <div style={{ display: 'flex', gap: '6px' }}>
                                                    {v.approval_status === 'PENDING' && (
                                                        <button onClick={() => setApproveConfirm({ id: v.id, num: v.voucher_number })}
                                                            style={{ padding: '4px 10px', border: 'none', borderRadius: '6px', background: '#dcfce7', color: '#166534', cursor: 'pointer', fontSize: '11px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '3px' }}>
                                                            <CheckCircle2 size={11} /> Approve
                                                        </button>
                                                    )}
                                                    {v.approval_status === 'APPROVED' && (
                                                        <button onClick={() => setPayConfirm({ id: v.id, num: v.voucher_number, amount: v.amount })}
                                                            style={{ padding: '4px 10px', border: 'none', borderRadius: '6px', background: '#dbeafe', color: '#1d4ed8', cursor: 'pointer', fontSize: '11px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '3px' }}>
                                                            <Play size={11} /> Pay
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
                </div>
            </div>
        </div>
    );

    // ─── Tab: Replenishments ──────────────────────────────────────────────────
    const replenTabJSX = (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <div>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>Petty Cash Replenishments</h3>
                    <p style={{ margin: '2px 0 0', fontSize: '13px', color: '#64748b' }}>Restore petty cash fund balances from main bank accounts — posts Dr Petty Cash / Cr Bank</p>
                </div>
                <button onClick={() => setShowReplenForm(true)}
                    style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 18px', border: 'none', borderRadius: '9px', background: '#0284c7', color: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: 600 }}>
                    <RotateCcw size={14} /> New Replenishment
                </button>
            </div>

            {/* Low balance alerts */}
            {funds.filter(f => parseFloat(f.current_balance) <= parseFloat(f.minimum_balance) && parseFloat(f.minimum_balance) > 0).map((f: any) => (
                <div key={f.id} style={{ display: 'flex', alignItems: 'center', gap: '10px', background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: '8px', padding: '10px 14px', marginBottom: '8px' }}>
                    <AlertTriangle size={14} color="#dc2626" />
                    <span style={{ fontSize: '13px', color: '#991b1b', fontWeight: 500 }}>
                        <strong>{f.name}</strong> is below minimum balance ({formatCurrency(f.current_balance)} / min {formatCurrency(f.minimum_balance)})
                    </span>
                    <button onClick={() => { setReplenForm(p => ({ ...p, petty_cash_fund: f.id.toString() })); setShowReplenForm(true); }}
                        style={{ marginLeft: 'auto', padding: '4px 10px', border: 'none', borderRadius: '6px', background: '#dc2626', color: '#fff', cursor: 'pointer', fontSize: '12px', fontWeight: 600 }}>
                        Replenish Now
                    </button>
                </div>
            ))}

            {loadingReplenishments ? (
                <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>Loading…</div>
            ) : !replenList.length ? (
                <div style={{ textAlign: 'center', padding: '60px 20px', background: '#f8fafc', borderRadius: '12px', border: '2px dashed #e2e8f0' }}>
                    <RotateCcw size={40} color="#cbd5e1" style={{ marginBottom: '12px' }} />
                    <p style={{ color: '#94a3b8', fontSize: '14px', margin: 0 }}>No replenishments yet.</p>
                </div>
            ) : (
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                        <thead>
                            <tr style={{ background: '#f8fafc' }}>
                                {['Ref #', 'Fund', 'Date', 'Vouchers Total', 'Reimbursement', 'Status', 'Actions'].map(h => (
                                    <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, color: '#64748b', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid #e2e8f0', whiteSpace: 'nowrap' }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {replenList.map((r: any) => (
                                <tr key={r.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                    <td style={{ padding: '11px 14px', fontWeight: 600, color: '#1e293b', fontFamily: 'monospace', fontSize: '12px' }}>{r.replenishment_number}</td>
                                    <td style={{ padding: '11px 14px', color: '#374151' }}>{funds.find(f => f.id === r.petty_cash_fund)?.name || `Fund #${r.petty_cash_fund}`}</td>
                                    <td style={{ padding: '11px 14px', color: '#374151' }}>{r.replenishment_date}</td>
                                    <td style={{ padding: '11px 14px', fontWeight: 600, color: '#374151' }}>{formatCurrency(parseFloat(r.vouchers_total || '0'))}</td>
                                    <td style={{ padding: '11px 14px', fontWeight: 700, color: '#0284c7' }}>{formatCurrency(parseFloat(r.reimbursement_amount || '0'))}</td>
                                    <td style={{ padding: '11px 14px' }}><StatusBadge status={r.status} /></td>
                                    <td style={{ padding: '11px 14px' }}>
                                        {(r.status === 'DRAFT' || r.status === 'APPROVED') && (
                                            <button onClick={() => setPostReplenConfirm({ id: r.id, num: r.replenishment_number })}
                                                style={{ padding: '5px 10px', border: 'none', borderRadius: '6px', background: '#dcfce7', color: '#166534', cursor: 'pointer', fontSize: '12px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                                                <Play size={12} /> Post
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );

    // ─── render ───────────────────────────────────────────────────────────────
    return (
        <AccountingLayout>
            <PageHeader
                title="Cash Accounts"
                subtitle="Manage cash accounts, petty cash, and imprest accounts for cash transactions."
                icon={<Wallet size={22} />}
            />

            {/* Summary cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '14px', marginBottom: '24px' }}>
                <SumCard label="Total Cash" value={formatCurrency(totalAll)} sub={`${cashBankAccounts.length} accounts`} accent="#15803d" icon={<DollarSign size={14} color="#15803d" />} />
                <SumCard label="Cash Accounts" value={formatCurrency(totalByType['Cash'] || 0)} sub={`${cashBankAccounts.filter(a => a.account_type === 'Cash').length} accounts`} accent="#22c55e" icon={<Banknote size={14} color="#22c55e" />} />
                <SumCard label="Petty Cash" value={formatCurrency(totalByType['Petty Cash'] || 0)} sub={`${funds.length} funds`} accent="#d97706" icon={<Wallet size={14} color="#d97706" />} />
                <SumCard label="Imprest" value={formatCurrency(totalByType['Imprest'] || 0)} sub={`${cashBankAccounts.filter(a => a.account_type === 'Imprest').length} accounts`} accent="#7c3aed" icon={<RefreshCw size={14} color="#7c3aed" />} />
                {fundStats.lowFunds > 0 && (
                    <SumCard label="Low Funds" value={fundStats.lowFunds} sub="Need replenishment" accent="#ef4444" icon={<AlertTriangle size={14} color="#ef4444" />} />
                )}
            </div>

            {notification && <InlineAlert msg={notification.msg} type={notification.type} onClose={() => setNotification(null)} />}

            {/* Tabs */}
            <div style={{ background: '#fff', borderRadius: '16px', border: '1px solid #e2e8f0', boxShadow: '0 1px 6px rgba(0,0,0,0.04)', overflow: 'hidden' }}>
                <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
                    {([
                        { key: 'accounts',     label: 'Cash Accounts',  icon: <DollarSign size={14} /> },
                        { key: 'petty-cash',   label: 'Petty Cash',     icon: <Wallet size={14} /> },
                        { key: 'replenishments', label: 'Replenishments', icon: <RotateCcw size={14} /> },
                    ] as { key: Tab; label: string; icon: React.ReactNode }[]).map(tab => (
                        <button key={tab.key} onClick={() => setActiveTab(tab.key)} style={{
                            display: 'flex', alignItems: 'center', gap: '6px',
                            padding: '13px 20px', border: 'none', cursor: 'pointer', fontSize: '13px',
                            fontWeight: activeTab === tab.key ? 700 : 500,
                            color: activeTab === tab.key ? '#15803d' : '#64748b',
                            background: 'none',
                            borderBottom: activeTab === tab.key ? '2.5px solid #15803d' : '2.5px solid transparent',
                            transition: 'all 0.15s',
                        }}>
                            {tab.icon} {tab.label}
                            {tab.key === 'petty-cash' && fundStats.lowFunds > 0 && (
                                <span style={{ background: '#ef4444', color: '#fff', borderRadius: '10px', padding: '1px 6px', fontSize: '10px', fontWeight: 700 }}>{fundStats.lowFunds}</span>
                            )}
                        </button>
                    ))}
                </div>
                <div style={{ padding: '24px' }}>
                    {activeTab === 'accounts'       && accountsTabJSX}
                    {activeTab === 'petty-cash'     && pettyCashTabJSX}
                    {activeTab === 'replenishments' && replenTabJSX}
                </div>
            </div>

            {/* Modals */}
            {accountFormModal}
            {fundFormModal}
            {voucherFormModal}
            {replenFormModal}

            {approveConfirm && (
                <ConfirmModal
                    title="Approve Voucher"
                    message={`Approve voucher ${approveConfirm.num}? Once approved it can be paid out.`}
                    confirmLabel="Approve"
                    confirmColor="#16a34a"
                    onConfirm={handleApprove}
                    onCancel={() => setApproveConfirm(null)}
                />
            )}
            {payConfirm && (
                <ConfirmModal
                    title="Pay Voucher"
                    message={`Pay voucher ${payConfirm.num} for ${formatCurrency(parseFloat(payConfirm.amount))}? This posts Dr Expense / Cr Petty Cash to the GL.`}
                    confirmLabel="Pay & Post"
                    confirmColor="#1d4ed8"
                    onConfirm={handlePay}
                    onCancel={() => setPayConfirm(null)}
                />
            )}
            {postReplenConfirm && (
                <ConfirmModal
                    title="Post Replenishment"
                    message={`Post replenishment ${postReplenConfirm.num}? This posts Dr Petty Cash / Cr Bank to the GL.`}
                    confirmLabel="Post to GL"
                    confirmColor="#0284c7"
                    onConfirm={handlePostReplenishment}
                    onCancel={() => setPostReplenConfirm(null)}
                />
            )}
        </AccountingLayout>
    );
}
