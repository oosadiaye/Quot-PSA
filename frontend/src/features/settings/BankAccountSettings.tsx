import { useState } from 'react';
import { useDialog } from '../../hooks/useDialog';
import {
    Plus, Pencil, Trash2, Building2, Wallet,
    Filter, Search, X, CreditCard,
} from 'lucide-react';
import { useBankAccounts, useCreateBankAccount, useUpdateBankAccount, useDeleteBankAccount } from './hooks/useBankAccounts';
import { useCurrencies } from '../accounting/hooks/useAccountingEnhancements';
import apiClient from '../../api/client';
import SettingsLayout from './SettingsLayout';
import LoadingScreen from '../../components/common/LoadingScreen';
import logger from '../../utils/logger';

interface BankAccountFormData {
    name: string;
    account_number: string;
    account_type: string;
    gl_account: number | '';
    currency: number | '';
    opening_balance: string;
    is_active: boolean;
    is_default: boolean;
    bank_name: string;
    branch_name: string;
    swift_code: string;
    iban: string;
}

const initialFormData: BankAccountFormData = {
    name: '',
    account_number: '',
    account_type: 'Bank',
    gl_account: '',
    currency: '',
    opening_balance: '0.00',
    is_active: true,
    is_default: false,
    bank_name: '',
    branch_name: '',
    swift_code: '',
    iban: '',
};

// ── Design-system style tokens ──────────────────────────────────
const cardStyle: React.CSSProperties = {
    background: 'white',
    borderRadius: '20px',
    padding: '28px 32px',
    border: '1px solid #e2e8f0',
    boxShadow: '0 1px 3px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.02)',
};

const lbl: React.CSSProperties = {
    display: 'block',
    fontSize: '11px',
    fontWeight: 700,
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: '0.6px',
    marginBottom: '6px',
};

const inp: React.CSSProperties = {
    width: '100%',
    padding: '10px 14px',
    border: '1.5px solid #e2e8f0',
    borderRadius: '12px',
    background: '#f8fafc',
    color: '#0f172a',
    fontSize: '14px',
    fontFamily: 'inherit',
    outline: 'none',
};

const selectStyle: React.CSSProperties = {
    ...inp,
    appearance: 'auto' as any,
};

const btnPrimary: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '10px 20px',
    background: 'linear-gradient(135deg, #6366f1, #4f46e5)',
    color: 'white',
    border: 'none',
    borderRadius: '12px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'inherit',
};

const btnOutline: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '10px 20px',
    background: 'white',
    color: '#374151',
    border: '1.5px solid #e2e8f0',
    borderRadius: '12px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'inherit',
};

export default function BankAccountSettings() {
    const { showConfirm } = useDialog();
    const [showDrawer, setShowDrawer] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [formData, setFormData] = useState<BankAccountFormData>(initialFormData);
    const [filterType, setFilterType] = useState('');
    const [searchQuery, setSearchQuery] = useState('');
    const [glAccounts, setGlAccounts] = useState<any[]>([]);
    const [formError, setFormError] = useState('');

    const { data: bankAccounts, isLoading } = useBankAccounts({});
    const { data: currencies } = useCurrencies();
    const createBankAccount = useCreateBankAccount();
    const updateBankAccount = useUpdateBankAccount();
    const deleteBankAccount = useDeleteBankAccount();

    const fetchGlAccounts = async () => {
        try {
            const response = await apiClient.get('/accounting/accounts/', {
                params: { is_active: true, page_size: 200 },
            });
            setGlAccounts(response.data.results || response.data);
        } catch (error) {
            logger.error('Failed to fetch GL accounts:', error);
        }
    };

    const handleOpenDrawer = async (account?: any) => {
        setFormError('');
        await fetchGlAccounts();
        if (account) {
            setEditingId(account.id);
            setFormData({
                name: account.name,
                account_number: account.account_number,
                account_type: account.account_type,
                gl_account: account.gl_account,
                currency: account.currency,
                opening_balance: account.opening_balance,
                is_active: account.is_active,
                is_default: account.is_default || false,
                bank_name: account.bank_name || '',
                branch_name: account.branch_name || '',
                swift_code: account.swift_code || '',
                iban: account.iban || '',
            });
        } else {
            setEditingId(null);
            setFormData(initialFormData);
        }
        setShowDrawer(true);
    };

    const handleCloseDrawer = () => {
        setShowDrawer(false);
        setEditingId(null);
        setFormData(initialFormData);
        setFormError('');
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');
        try {
            const payload = {
                ...formData,
                opening_balance: parseFloat(formData.opening_balance) || 0,
                current_balance: parseFloat(formData.opening_balance) || 0,
            };
            if (editingId) {
                await updateBankAccount.mutateAsync({ id: editingId, ...payload });
            } else {
                await createBankAccount.mutateAsync(payload);
            }
            handleCloseDrawer();
        } catch (err: any) {
            const data = err.response?.data;
            setFormError(data
                ? (typeof data === 'string' ? data : Object.values(data).flat().join(' '))
                : err.message || 'Failed to save bank account.');
        }
    };

    const handleDelete = async (id: number) => {
        if (await showConfirm('Are you sure you want to delete this bank account?')) {
            try {
                await deleteBankAccount.mutateAsync(id);
            } catch (error) {
                logger.error('Failed to delete bank account:', error);
            }
        }
    };

    const filteredAccounts = bankAccounts?.filter((account: any) => {
        const matchesType = !filterType ||
            (filterType === 'bank' && account.account_type === 'Bank') ||
            (filterType === 'cash' && ['Cash', 'Petty Cash', 'Imprest'].includes(account.account_type));
        const matchesSearch = !searchQuery ||
            account.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            account.account_number.toLowerCase().includes(searchQuery.toLowerCase());
        return matchesType && matchesSearch;
    }) || [];

    const getAccountTypeIcon = (type: string) =>
        type === 'Bank' ? <Building2 size={15} /> : <Wallet size={15} />;

    if (isLoading) return <LoadingScreen message="Loading bank accounts..." />;

    const isSaving = createBankAccount.isPending || updateBankAccount.isPending;

    return (
        <SettingsLayout
            title="Bank & Cash Accounts"
            breadcrumb="Bank Accounts"
            icon={<CreditCard size={22} color="white" />}
            gradient="linear-gradient(135deg, #6366f1, #4f46e5)"
            gradientShadow="rgba(99, 102, 241, 0.25)"
            subtitle="Manage bank accounts, cash accounts, and petty cash for treasury management."
            maxWidth="1060px"
        >
            {/* Search + filter bar + Add button */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
                {/* Search */}
                <div style={{ position: 'relative', flex: 1, maxWidth: '300px' }}>
                    <Search size={15} style={{
                        position: 'absolute', left: '14px', top: '50%',
                        transform: 'translateY(-50%)', color: '#94a3b8',
                        pointerEvents: 'none',
                    }} />
                    <input
                        type="text"
                        placeholder="Search accounts..."
                        value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                        style={{ ...inp, paddingLeft: '38px' }}
                    />
                </div>

                {/* Filter */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Filter size={15} style={{ color: '#94a3b8' }} />
                    <select
                        style={{ ...selectStyle, width: 'auto', minWidth: '180px' }}
                        value={filterType}
                        onChange={e => setFilterType(e.target.value)}
                    >
                        <option value="">All Types</option>
                        <option value="bank">Bank</option>
                        <option value="cash">Cash / Petty Cash / Imprest</option>
                    </select>
                </div>

                <div style={{ flex: 1 }} />

                {/* Add Account */}
                <button onClick={() => handleOpenDrawer()} style={btnPrimary}>
                    <Plus size={16} /> Add Account
                </button>
            </div>

            {/* Accounts table */}
            <div style={{ ...cardStyle, padding: 0, overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ borderBottom: '1.5px solid #e2e8f0' }}>
                            {['Account', 'Type', 'GL Account', 'Currency', 'Opening Balance', 'Status', 'Actions'].map((h, i) => (
                                <th key={h} style={{
                                    padding: '14px 20px',
                                    fontSize: '11px', fontWeight: 700,
                                    textTransform: 'uppercase', letterSpacing: '0.6px',
                                    color: '#64748b',
                                    background: '#f8fafc',
                                    textAlign: i === 4 ? 'right' : i === 6 ? 'center' : 'left',
                                }}>{h}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {filteredAccounts.length === 0 ? (
                            <tr>
                                <td colSpan={7} style={{ padding: '56px 20px', textAlign: 'center', color: '#94a3b8' }}>
                                    <CreditCard size={40} style={{ margin: '0 auto 12px', opacity: 0.25, display: 'block' }} />
                                    <p style={{ fontWeight: 500, margin: '0 0 4px', color: '#64748b' }}>No bank accounts found.</p>
                                    <p style={{ fontSize: '12px', margin: 0, color: '#94a3b8' }}>Click "Add Account" to create one.</p>
                                </td>
                            </tr>
                        ) : filteredAccounts.map((account: any) => (
                            <tr
                                key={account.id}
                                style={{ borderBottom: '1px solid #f1f5f9', transition: 'background 0.15s' }}
                                onMouseOver={e => (e.currentTarget.style.background = '#f8fafc')}
                                onMouseOut={e => (e.currentTarget.style.background = '')}
                            >
                                <td style={{ padding: '14px 20px' }}>
                                    <div style={{ fontWeight: 600, color: '#0f172a', fontSize: '14px' }}>{account.name}</div>
                                    <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '2px' }}>{account.account_number}</div>
                                </td>
                                <td style={{ padding: '14px 20px' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '14px', color: '#475569' }}>
                                        {getAccountTypeIcon(account.account_type)}
                                        {account.account_type}
                                    </div>
                                </td>
                                <td style={{ padding: '14px 20px' }}>
                                    <div style={{ fontFamily: 'monospace', fontSize: '14px', color: '#0f172a' }}>{account.gl_account_code}</div>
                                    <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '2px' }}>{account.gl_account_name}</div>
                                </td>
                                <td style={{ padding: '14px 20px', fontSize: '14px', color: '#475569' }}>{account.currency_code}</td>
                                <td style={{ padding: '14px 20px', textAlign: 'right', fontWeight: 600, fontSize: '14px', color: '#0f172a' }}>
                                    {parseFloat(account.opening_balance).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </td>
                                <td style={{ padding: '14px 20px' }}>
                                    <span style={{
                                        padding: '4px 10px', borderRadius: '20px',
                                        fontSize: '11px', fontWeight: 600,
                                        background: account.is_active ? 'rgba(22,163,74,0.1)' : 'rgba(107,114,128,0.1)',
                                        color: account.is_active ? '#16a34a' : '#94a3b8',
                                    }}>
                                        {account.is_active ? 'Active' : 'Inactive'}
                                    </span>
                                    {account.is_default && (
                                        <span style={{
                                            marginLeft: '6px', padding: '4px 10px', borderRadius: '20px',
                                            fontSize: '11px', fontWeight: 600,
                                            background: 'rgba(99,102,241,0.1)', color: '#6366f1',
                                        }}>Default</span>
                                    )}
                                </td>
                                <td style={{ padding: '14px 20px', textAlign: 'center' }}>
                                    <button
                                        onClick={() => handleOpenDrawer(account)}
                                        style={{
                                            background: 'none', border: 'none', cursor: 'pointer',
                                            color: '#94a3b8', padding: '6px', borderRadius: '8px',
                                            marginRight: '4px', transition: 'color 0.15s, background 0.15s',
                                        }}
                                        onMouseOver={e => { e.currentTarget.style.color = '#6366f1'; e.currentTarget.style.background = 'rgba(99,102,241,0.08)'; }}
                                        onMouseOut={e => { e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.background = 'none'; }}
                                        title="Edit"
                                    >
                                        <Pencil size={15} />
                                    </button>
                                    <button
                                        onClick={() => handleDelete(account.id)}
                                        style={{
                                            background: 'none', border: 'none', cursor: 'pointer',
                                            color: '#94a3b8', padding: '6px', borderRadius: '8px',
                                            transition: 'color 0.15s, background 0.15s',
                                        }}
                                        onMouseOver={e => { e.currentTarget.style.color = '#ef4444'; e.currentTarget.style.background = 'rgba(239,68,68,0.08)'; }}
                                        onMouseOut={e => { e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.background = 'none'; }}
                                        title="Delete"
                                    >
                                        <Trash2 size={15} />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* ══════════════════════════════════════════════════════════
                RIGHT-SIDE DRAWER
                ══════════════════════════════════════════════════════════ */}
            {showDrawer && (
                <div style={{
                    position: 'fixed', inset: 0, zIndex: 1000,
                    display: 'flex',
                }}>
                    {/* Backdrop */}
                    <div
                        style={{
                            flex: 1,
                            background: 'rgba(15, 23, 42, 0.5)',
                            backdropFilter: 'blur(4px)',
                        }}
                        onClick={handleCloseDrawer}
                    />

                    {/* Drawer panel */}
                    <div style={{
                        width: '540px',
                        background: 'white',
                        boxShadow: '-12px 0 48px rgba(0,0,0,0.12)',
                        display: 'flex',
                        flexDirection: 'column',
                        overflowY: 'auto',
                    }}>
                        {/* Drawer header */}
                        <div style={{
                            padding: '24px 28px',
                            borderBottom: '1px solid #e2e8f0',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            flexShrink: 0,
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                                <div style={{
                                    width: '40px', height: '40px', borderRadius: '12px',
                                    background: 'linear-gradient(135deg, #6366f1, #4f46e5)',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    boxShadow: '0 4px 12px rgba(99,102,241,0.3)',
                                }}>
                                    <CreditCard size={18} style={{ color: 'white' }} />
                                </div>
                                <div>
                                    <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: 0 }}>
                                        {editingId ? 'Edit Bank Account' : 'Add Bank Account'}
                                    </h3>
                                    <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#94a3b8' }}>
                                        {editingId ? 'Update account details below' : 'Fill in the details to create a new account'}
                                    </p>
                                </div>
                            </div>
                            <button
                                onClick={handleCloseDrawer}
                                style={{
                                    background: '#f1f5f9', border: 'none', cursor: 'pointer',
                                    color: '#64748b', padding: '8px', borderRadius: '10px',
                                    display: 'flex', alignItems: 'center',
                                    transition: 'background 0.15s',
                                }}
                                onMouseOver={e => (e.currentTarget.style.background = '#e2e8f0')}
                                onMouseOut={e => (e.currentTarget.style.background = '#f1f5f9')}
                            >
                                <X size={18} />
                            </button>
                        </div>

                        {/* Drawer body */}
                        <form onSubmit={handleSubmit} style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                            <div style={{ padding: '24px 28px', flex: 1 }}>

                                {formError && (
                                    <div style={{
                                        padding: '12px 16px',
                                        background: '#fef2f2',
                                        color: '#dc2626',
                                        borderRadius: '12px',
                                        marginBottom: '20px',
                                        fontSize: '13px',
                                        fontWeight: 500,
                                        border: '1px solid #fecaca',
                                    }}>
                                        {formError}
                                    </div>
                                )}

                                {/* Section: Core Info */}
                                <p style={{
                                    fontSize: '10px', fontWeight: 700, color: '#94a3b8',
                                    textTransform: 'uppercase', letterSpacing: '0.8px',
                                    marginBottom: '16px', marginTop: 0,
                                }}>
                                    Core Information
                                </p>

                                {/* Account Name */}
                                <div style={{ marginBottom: '16px' }}>
                                    <label style={lbl}>Account Name <span style={{ color: '#ef4444' }}>*</span></label>
                                    <input
                                        style={inp}
                                        type="text"
                                        placeholder="e.g. Main Operating Account"
                                        value={formData.name}
                                        onChange={e => setFormData({ ...formData, name: e.target.value })}
                                        onFocus={e => (e.currentTarget.style.borderColor = '#6366f1')}
                                        onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
                                        required
                                    />
                                </div>

                                {/* Account Number | Account Type */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '16px' }}>
                                    <div>
                                        <label style={lbl}>Account Number <span style={{ color: '#ef4444' }}>*</span></label>
                                        <input
                                            style={inp}
                                            type="text"
                                            placeholder="e.g. 0012345678"
                                            value={formData.account_number}
                                            onChange={e => setFormData({ ...formData, account_number: e.target.value })}
                                            onFocus={e => (e.currentTarget.style.borderColor = '#6366f1')}
                                            onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
                                            required
                                        />
                                    </div>
                                    <div>
                                        <label style={lbl}>Account Type <span style={{ color: '#ef4444' }}>*</span></label>
                                        <select
                                            style={selectStyle}
                                            value={formData.account_type}
                                            onChange={e => setFormData({ ...formData, account_type: e.target.value })}
                                            onFocus={e => (e.currentTarget.style.borderColor = '#6366f1')}
                                            onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
                                            required
                                        >
                                            <option value="Bank">Bank</option>
                                            <option value="Cash">Cash</option>
                                            <option value="Petty Cash">Petty Cash</option>
                                            <option value="Imprest">Imprest</option>
                                        </select>
                                    </div>
                                </div>

                                {/* Currency | GL Account */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '16px' }}>
                                    <div>
                                        <label style={lbl}>Currency <span style={{ color: '#ef4444' }}>*</span></label>
                                        <select
                                            style={selectStyle}
                                            value={formData.currency}
                                            onChange={e => setFormData({ ...formData, currency: parseInt(e.target.value) })}
                                            onFocus={e => (e.currentTarget.style.borderColor = '#6366f1')}
                                            onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
                                            required
                                        >
                                            <option value="">Select currency...</option>
                                            {currencies?.filter((c: any) => c.is_active).map((c: any) => (
                                                <option key={c.id} value={c.id}>{c.code} - {c.name}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={lbl}>GL Account <span style={{ color: '#ef4444' }}>*</span></label>
                                        <select
                                            style={selectStyle}
                                            value={formData.gl_account}
                                            onChange={e => setFormData({ ...formData, gl_account: parseInt(e.target.value) })}
                                            onFocus={e => (e.currentTarget.style.borderColor = '#6366f1')}
                                            onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
                                            required
                                        >
                                            <option value="">Select GL account...</option>
                                            {glAccounts.map((a: any) => (
                                                <option key={a.id} value={a.id}>{a.code} - {a.name}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>

                                {/* Opening Balance */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '24px' }}>
                                    <div>
                                        <label style={lbl}>Opening Balance</label>
                                        <input
                                            style={inp}
                                            type="number"
                                            step="0.01"
                                            placeholder="0.00"
                                            value={formData.opening_balance}
                                            onChange={e => setFormData({ ...formData, opening_balance: e.target.value })}
                                            onFocus={e => (e.currentTarget.style.borderColor = '#6366f1')}
                                            onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
                                        />
                                    </div>
                                </div>

                                {/* Divider */}
                                <div style={{ borderTop: '1px solid #e2e8f0', margin: '4px 0 20px' }} />

                                {/* Section: Bank Details */}
                                <p style={{
                                    fontSize: '10px', fontWeight: 700, color: '#94a3b8',
                                    textTransform: 'uppercase', letterSpacing: '0.8px',
                                    marginBottom: '16px', marginTop: 0,
                                }}>
                                    Bank Details <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(optional)</span>
                                </p>

                                {/* Bank Name */}
                                <div style={{ marginBottom: '16px' }}>
                                    <label style={lbl}>Bank Name</label>
                                    <input
                                        style={inp}
                                        type="text"
                                        placeholder="e.g. First National Bank"
                                        value={formData.bank_name}
                                        onChange={e => setFormData({ ...formData, bank_name: e.target.value })}
                                        onFocus={e => (e.currentTarget.style.borderColor = '#6366f1')}
                                        onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
                                    />
                                </div>

                                {/* Branch | SWIFT */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '16px' }}>
                                    <div>
                                        <label style={lbl}>Branch Name</label>
                                        <input
                                            style={inp}
                                            type="text"
                                            placeholder="Branch"
                                            value={formData.branch_name}
                                            onChange={e => setFormData({ ...formData, branch_name: e.target.value })}
                                            onFocus={e => (e.currentTarget.style.borderColor = '#6366f1')}
                                            onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
                                        />
                                    </div>
                                    <div>
                                        <label style={lbl}>SWIFT Code</label>
                                        <input
                                            style={inp}
                                            type="text"
                                            placeholder="e.g. FNBZAJJXXX"
                                            value={formData.swift_code}
                                            onChange={e => setFormData({ ...formData, swift_code: e.target.value })}
                                            onFocus={e => (e.currentTarget.style.borderColor = '#6366f1')}
                                            onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
                                        />
                                    </div>
                                </div>

                                {/* IBAN */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '24px' }}>
                                    <div>
                                        <label style={lbl}>IBAN</label>
                                        <input
                                            style={inp}
                                            type="text"
                                            placeholder="e.g. GB29 NWBK..."
                                            value={formData.iban}
                                            onChange={e => setFormData({ ...formData, iban: e.target.value })}
                                            onFocus={e => (e.currentTarget.style.borderColor = '#6366f1')}
                                            onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
                                        />
                                    </div>
                                </div>

                                {/* Checkboxes */}
                                <div style={{
                                    display: 'flex', gap: '12px',
                                    flexDirection: 'column',
                                }}>
                                    <label style={{
                                        display: 'flex', alignItems: 'center', gap: '10px',
                                        cursor: 'pointer', fontSize: '14px', fontWeight: 500, color: '#0f172a',
                                        padding: '12px 16px', borderRadius: '12px',
                                        background: '#f8fafc', border: '1px solid #e2e8f0',
                                    }}>
                                        <input type="checkbox" checked={formData.is_active}
                                            onChange={e => setFormData({ ...formData, is_active: e.target.checked })} />
                                        Active
                                    </label>
                                    <label style={{
                                        display: 'flex', alignItems: 'center', gap: '10px',
                                        cursor: 'pointer', fontSize: '14px', fontWeight: 500, color: '#0f172a',
                                        padding: '12px 16px', borderRadius: '12px',
                                        background: '#f8fafc', border: '1px solid #e2e8f0',
                                    }}>
                                        <input type="checkbox" checked={formData.is_default}
                                            onChange={e => setFormData({ ...formData, is_default: e.target.checked })} />
                                        Default Account
                                    </label>
                                </div>

                            </div>

                            {/* Drawer footer */}
                            <div style={{
                                padding: '16px 28px',
                                borderTop: '1px solid #e2e8f0',
                                display: 'flex', gap: '10px', justifyContent: 'flex-end',
                                flexShrink: 0,
                                background: 'white',
                            }}>
                                <button type="button" onClick={handleCloseDrawer} style={btnOutline}>
                                    Cancel
                                </button>
                                <button type="submit" disabled={isSaving} style={{
                                    ...btnPrimary,
                                    opacity: isSaving ? 0.7 : 1,
                                    cursor: isSaving ? 'not-allowed' : 'pointer',
                                }}>
                                    {isSaving ? 'Saving...' : editingId ? 'Update Account' : 'Save Account'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </SettingsLayout>
    );
}
