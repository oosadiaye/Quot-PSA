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
import '../accounting/styles/glassmorphism.css';

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

// ── Shared compact style tokens ──────────────────────────────────
const inp: React.CSSProperties = {
    width: '100%', padding: '0.45rem 0.7rem', borderRadius: '7px',
    border: '1.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: '0.875rem',
    outline: 'none', fontFamily: 'inherit',
};
const lbl: React.CSSProperties = {
    display: 'block', marginBottom: '0.25rem',
    fontSize: '0.68rem', fontWeight: 700,
    textTransform: 'uppercase', letterSpacing: '0.05em',
    color: 'var(--color-text-muted)',
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
        <SettingsLayout>
            {/* ── Page header ─────────────────────────────────────── */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                <div>
                    <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)', marginBottom: '0.2rem' }}>
                        Bank & Cash Accounts
                    </h2>
                    <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
                        Manage bank accounts, cash accounts, and petty cash for treasury management.
                    </p>
                </div>
                <button className="btn btn-primary" onClick={() => handleOpenDrawer()}
                    style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Plus size={16} /> Add Account
                </button>
            </div>

            {/* ── Search + filter bar ──────────────────────────────── */}
            <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem' }}>
                <div style={{ position: 'relative', flex: 1, maxWidth: '280px' }}>
                    <Search size={15} style={{
                        position: 'absolute', left: '10px', top: '50%',
                        transform: 'translateY(-50%)', color: 'var(--color-text-muted)',
                        pointerEvents: 'none',
                    }} />
                    <input type="text" placeholder="Search accounts…" value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                        style={{ ...inp, paddingLeft: '32px' }} />
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Filter size={15} style={{ color: 'var(--color-text-muted)' }} />
                    <select style={{ ...inp, width: 'auto', minWidth: '160px' }}
                        value={filterType} onChange={e => setFilterType(e.target.value)}>
                        <option value="">All Types</option>
                        <option value="bank">Bank</option>
                        <option value="cash">Cash / Petty Cash / Imprest</option>
                    </select>
                </div>
            </div>

            {/* ── Accounts table ───────────────────────────────────── */}
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ borderBottom: '1.5px solid var(--color-border)' }}>
                            {['Account', 'Type', 'GL Account', 'Currency', 'Opening Balance', 'Status', 'Actions'].map((h, i) => (
                                <th key={h} style={{
                                    padding: '0.75rem 1.25rem',
                                    fontSize: '0.65rem', fontWeight: 700,
                                    textTransform: 'uppercase', letterSpacing: '0.05em',
                                    color: 'var(--color-text-muted)',
                                    textAlign: i === 4 ? 'right' : i === 6 ? 'center' : 'left',
                                }}>{h}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {filteredAccounts.length === 0 ? (
                            <tr>
                                <td colSpan={7} style={{ padding: '3.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                    <CreditCard size={40} style={{ margin: '0 auto 0.75rem', opacity: 0.25, display: 'block' }} />
                                    <p style={{ fontWeight: 500 }}>No bank accounts found.</p>
                                    <p style={{ fontSize: 'var(--text-xs)', marginTop: '0.25rem' }}>Click "Add Account" to create one.</p>
                                </td>
                            </tr>
                        ) : filteredAccounts.map((account: any) => (
                            <tr key={account.id} style={{ borderBottom: '1px solid var(--color-border)', transition: 'background 0.1s' }}
                                onMouseOver={e => (e.currentTarget.style.background = 'var(--color-surface-hover)')}
                                onMouseOut={e => (e.currentTarget.style.background = '')}>
                                <td style={{ padding: '0.875rem 1.25rem' }}>
                                    <div style={{ fontWeight: 600, color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>{account.name}</div>
                                    <div style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: '1px' }}>{account.account_number}</div>
                                </td>
                                <td style={{ padding: '0.875rem 1.25rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
                                        {getAccountTypeIcon(account.account_type)}
                                        {account.account_type}
                                    </div>
                                </td>
                                <td style={{ padding: '0.875rem 1.25rem' }}>
                                    <div style={{ fontFamily: 'monospace', fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>{account.gl_account_code}</div>
                                    <div style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: '1px' }}>{account.gl_account_name}</div>
                                </td>
                                <td style={{ padding: '0.875rem 1.25rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>{account.currency_code}</td>
                                <td style={{ padding: '0.875rem 1.25rem', textAlign: 'right', fontWeight: 600, fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>
                                    {parseFloat(account.opening_balance).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </td>
                                <td style={{ padding: '0.875rem 1.25rem' }}>
                                    <span style={{
                                        padding: '0.2rem 0.6rem', borderRadius: '20px',
                                        fontSize: '0.68rem', fontWeight: 600,
                                        background: account.is_active ? 'rgba(22,163,74,0.1)' : 'rgba(107,114,128,0.1)',
                                        color: account.is_active ? '#16a34a' : 'var(--color-text-muted)',
                                    }}>
                                        {account.is_active ? 'Active' : 'Inactive'}
                                    </span>
                                    {account.is_default && (
                                        <span style={{
                                            marginLeft: '0.4rem', padding: '0.2rem 0.6rem', borderRadius: '20px',
                                            fontSize: '0.68rem', fontWeight: 600,
                                            background: 'rgba(25,30,106,0.08)', color: 'var(--color-primary)',
                                        }}>Default</span>
                                    )}
                                </td>
                                <td style={{ padding: '0.875rem 1.25rem', textAlign: 'center' }}>
                                    <button onClick={() => handleOpenDrawer(account)}
                                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', padding: '4px', borderRadius: '5px', marginRight: '4px' }}
                                        title="Edit">
                                        <Pencil size={15} />
                                    </button>
                                    <button onClick={() => handleDelete(account.id)}
                                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: '4px', borderRadius: '5px' }}
                                        title="Delete">
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
                    <div style={{
                        flex: 1, background: 'rgba(15,23,42,0.45)',
                        backdropFilter: 'blur(3px)',
                    }} onClick={handleCloseDrawer} />

                    {/* Drawer panel */}
                    <div style={{
                        width: '520px', background: 'var(--color-surface)',
                        boxShadow: '-12px 0 40px rgba(0,0,0,0.15)',
                        display: 'flex', flexDirection: 'column',
                        overflowY: 'auto',
                    }}>

                        {/* Drawer header */}
                        <div style={{
                            padding: '1.1rem 1.5rem',
                            borderBottom: '1px solid var(--color-border)',
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            flexShrink: 0,
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                                <div style={{
                                    width: '32px', height: '32px', borderRadius: '8px',
                                    background: 'rgba(25,30,106,0.08)',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                }}>
                                    <CreditCard size={16} style={{ color: 'var(--color-primary)' }} />
                                </div>
                                <div>
                                    <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                                        {editingId ? 'Edit Bank Account' : 'Add Bank Account'}
                                    </h3>
                                    <p style={{ margin: 0, fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                                        {editingId ? 'Update account details below' : 'Fill in the details to create a new account'}
                                    </p>
                                </div>
                            </div>
                            <button onClick={handleCloseDrawer} style={{
                                background: 'none', border: 'none', cursor: 'pointer',
                                color: 'var(--color-text-muted)', padding: '4px', borderRadius: '6px',
                                display: 'flex', alignItems: 'center',
                            }}>
                                <X size={18} />
                            </button>
                        </div>

                        {/* Drawer body — compact grid form */}
                        <form onSubmit={handleSubmit} style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                            <div style={{ padding: '1.25rem 1.5rem', flex: 1 }}>

                                {formError && (
                                    <div style={{
                                        padding: '0.5rem 0.875rem', background: '#fee2e2', color: '#dc2626',
                                        borderRadius: '7px', marginBottom: '1rem',
                                        fontSize: '0.8rem', fontWeight: 500,
                                    }}>
                                        {formError}
                                    </div>
                                )}

                                {/* ── Section: Core Info ─────────────────── */}
                                <p style={{ ...lbl, marginBottom: '0.75rem', fontSize: '0.6rem', letterSpacing: '0.07em' }}>
                                    Core Information
                                </p>

                                {/* Account Name — full width */}
                                <div style={{ marginBottom: '0.75rem' }}>
                                    <label style={lbl}>Account Name <span style={{ color: '#ef4444' }}>*</span></label>
                                    <input style={inp} type="text" placeholder="e.g. Main Operating Account"
                                        value={formData.name}
                                        onChange={e => setFormData({ ...formData, name: e.target.value })} required />
                                </div>

                                {/* Account Number | Account Type */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
                                    <div>
                                        <label style={lbl}>Account Number <span style={{ color: '#ef4444' }}>*</span></label>
                                        <input style={inp} type="text" placeholder="e.g. 0012345678"
                                            value={formData.account_number}
                                            onChange={e => setFormData({ ...formData, account_number: e.target.value })} required />
                                    </div>
                                    <div>
                                        <label style={lbl}>Account Type <span style={{ color: '#ef4444' }}>*</span></label>
                                        <select style={{ ...inp, appearance: 'auto' as any }}
                                            value={formData.account_type}
                                            onChange={e => setFormData({ ...formData, account_type: e.target.value })} required>
                                            <option value="Bank">Bank</option>
                                            <option value="Cash">Cash</option>
                                            <option value="Petty Cash">Petty Cash</option>
                                            <option value="Imprest">Imprest</option>
                                        </select>
                                    </div>
                                </div>

                                {/* Currency | GL Account */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
                                    <div>
                                        <label style={lbl}>Currency <span style={{ color: '#ef4444' }}>*</span></label>
                                        <select style={{ ...inp, appearance: 'auto' as any }}
                                            value={formData.currency}
                                            onChange={e => setFormData({ ...formData, currency: parseInt(e.target.value) })} required>
                                            <option value="">Select currency…</option>
                                            {currencies?.filter((c: any) => c.is_active).map((c: any) => (
                                                <option key={c.id} value={c.id}>{c.code} – {c.name}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={lbl}>GL Account <span style={{ color: '#ef4444' }}>*</span></label>
                                        <select style={{ ...inp, appearance: 'auto' as any }}
                                            value={formData.gl_account}
                                            onChange={e => setFormData({ ...formData, gl_account: parseInt(e.target.value) })} required>
                                            <option value="">Select GL account…</option>
                                            {glAccounts.map((a: any) => (
                                                <option key={a.id} value={a.id}>{a.code} – {a.name}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>

                                {/* Opening Balance — half width */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1.25rem' }}>
                                    <div>
                                        <label style={lbl}>Opening Balance</label>
                                        <input style={inp} type="number" step="0.01" placeholder="0.00"
                                            value={formData.opening_balance}
                                            onChange={e => setFormData({ ...formData, opening_balance: e.target.value })} />
                                    </div>
                                </div>

                                {/* ── Divider ─────────────────────────── */}
                                <div style={{ borderTop: '1px solid var(--color-border)', margin: '0.25rem 0 1rem' }} />

                                {/* ── Section: Bank Details ──────────── */}
                                <p style={{ ...lbl, marginBottom: '0.75rem', fontSize: '0.6rem', letterSpacing: '0.07em' }}>
                                    Bank Details <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(optional)</span>
                                </p>

                                {/* Bank Name — full width */}
                                <div style={{ marginBottom: '0.75rem' }}>
                                    <label style={lbl}>Bank Name</label>
                                    <input style={inp} type="text" placeholder="e.g. First National Bank"
                                        value={formData.bank_name}
                                        onChange={e => setFormData({ ...formData, bank_name: e.target.value })} />
                                </div>

                                {/* Branch | SWIFT */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
                                    <div>
                                        <label style={lbl}>Branch Name</label>
                                        <input style={inp} type="text" placeholder="Branch"
                                            value={formData.branch_name}
                                            onChange={e => setFormData({ ...formData, branch_name: e.target.value })} />
                                    </div>
                                    <div>
                                        <label style={lbl}>SWIFT Code</label>
                                        <input style={inp} type="text" placeholder="e.g. FNBZAJJXXX"
                                            value={formData.swift_code}
                                            onChange={e => setFormData({ ...formData, swift_code: e.target.value })} />
                                    </div>
                                </div>

                                {/* IBAN — half width */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1.25rem' }}>
                                    <div>
                                        <label style={lbl}>IBAN</label>
                                        <input style={inp} type="text" placeholder="e.g. GB29 NWBK…"
                                            value={formData.iban}
                                            onChange={e => setFormData({ ...formData, iban: e.target.value })} />
                                    </div>
                                </div>

                                {/* ── Checkboxes ──────────────────────── */}
                                <div style={{
                                    display: 'flex', gap: '1.5rem',
                                    padding: '0.75rem 1rem', borderRadius: '8px',
                                    background: 'var(--color-surface-hover)',
                                    border: '1px solid var(--color-border)',
                                }}>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 500 }}>
                                        <input type="checkbox" checked={formData.is_active}
                                            onChange={e => setFormData({ ...formData, is_active: e.target.checked })} />
                                        Active
                                    </label>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 500 }}>
                                        <input type="checkbox" checked={formData.is_default}
                                            onChange={e => setFormData({ ...formData, is_default: e.target.checked })} />
                                        Default Account
                                    </label>
                                </div>

                            </div>

                            {/* Drawer footer — sticky at bottom */}
                            <div style={{
                                padding: '0.875rem 1.5rem',
                                borderTop: '1px solid var(--color-border)',
                                display: 'flex', gap: '0.6rem', justifyContent: 'flex-end',
                                flexShrink: 0,
                                background: 'var(--color-surface)',
                            }}>
                                <button type="button" className="btn btn-outline" onClick={handleCloseDrawer}
                                    style={{ padding: '0.45rem 1.1rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                                    Cancel
                                </button>
                                <button type="submit" className="btn btn-primary" disabled={isSaving}
                                    style={{ padding: '0.45rem 1.25rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                                    {isSaving ? 'Saving…' : editingId ? 'Update Account' : 'Save Account'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </SettingsLayout>
    );
}
