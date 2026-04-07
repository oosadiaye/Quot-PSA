import { useState, useMemo } from 'react';
import {
    useCustomerCategories,
    useCreateCustomerCategory,
    useUpdateCustomerCategory,
    useDeleteCustomerCategory,
    useARAccounts,
} from '../hooks/useSales';
import SalesLayout from '../layout/SalesLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, Edit2, Trash2, X, Check, Tag, Info } from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

interface CustomerCategory {
    id: number;
    name: string;
    code: string;
    description: string;
    accounts_receivable_account: number | null;
    accounts_receivable_account_name: string | null;
    accounts_receivable_account_code: string | null;
    customer_count: number;
}

interface ARAccount {
    id: number;
    code: string;
    name: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const labelStyle: React.CSSProperties = {
    display: 'block',
    marginBottom: '0.375rem',
    fontSize: 'var(--text-xs)',
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color: 'var(--color-text-muted)',
};

const thStyle: React.CSSProperties = {
    padding: '0.875rem 1rem',
    fontSize: 'var(--text-xs)',
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color: 'var(--color-text-muted)',
    textAlign: 'left',
    whiteSpace: 'nowrap',
    background: 'var(--color-surface)',
    borderBottom: '2px solid var(--color-border)',
};

const tdStyle: React.CSSProperties = {
    padding: '0.875rem 1rem',
    fontSize: 'var(--text-sm)',
    color: 'var(--color-text)',
    borderBottom: '1px solid var(--color-border)',
    verticalAlign: 'middle',
};

const EMPTY_FORM = {
    name: '',
    code: '',
    description: '',
    accounts_receivable_account: '',
};

// ─── Component ────────────────────────────────────────────────────────────────

const CustomerCategoryList = () => {
    const { data: rawData, isLoading } = useCustomerCategories();
    const { data: arAccountsRaw } = useARAccounts();
    const createCategory = useCreateCustomerCategory();
    const updateCategory = useUpdateCustomerCategory();
    const deleteCategory = useDeleteCustomerCategory();

    const categories: CustomerCategory[] = useMemo(() => rawData ?? [], [rawData]);
    const arAccounts: ARAccount[] = useMemo(() => arAccountsRaw ?? [], [arAccountsRaw]);

    const [search, setSearch] = useState('');
    const [showForm, setShowForm] = useState(false);
    const [editId, setEditId] = useState<number | null>(null);
    const [form, setForm] = useState({ ...EMPTY_FORM });
    const [formError, setFormError] = useState<string | null>(null);
    const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

    const filtered = useMemo(() => {
        if (!search) return categories;
        const q = search.toLowerCase();
        return categories.filter(
            (c) => c.name.toLowerCase().includes(q) || c.code.toLowerCase().includes(q),
        );
    }, [categories, search]);

    // The AR account selected in the form (for live preview)
    const selectedAR = useMemo(
        () => arAccounts.find((a) => String(a.id) === form.accounts_receivable_account) ?? null,
        [arAccounts, form.accounts_receivable_account],
    );

    const openCreate = () => {
        setEditId(null);
        setForm({ ...EMPTY_FORM });
        setFormError(null);
        setShowForm(true);
    };

    const openEdit = (cat: CustomerCategory) => {
        setEditId(cat.id);
        setForm({
            name: cat.name,
            code: cat.code,
            description: cat.description,
            accounts_receivable_account: cat.accounts_receivable_account
                ? String(cat.accounts_receivable_account)
                : '',
        });
        setFormError(null);
        setShowForm(true);
    };

    const handleSave = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError(null);

        if (!form.accounts_receivable_account) {
            setFormError('Accounts Receivable GL account is required.');
            return;
        }

        const payload = {
            name: form.name,
            code: form.code,
            description: form.description,
            accounts_receivable_account: Number(form.accounts_receivable_account),
        };

        try {
            if (editId) {
                await updateCategory.mutateAsync({ id: editId, data: payload });
            } else {
                await createCategory.mutateAsync(payload);
            }
            setShowForm(false);
            setEditId(null);
            setForm({ ...EMPTY_FORM });
        } catch (err: any) {
            const errData = err?.response?.data;
            const msg =
                errData?.name?.[0] ||
                errData?.code?.[0] ||
                errData?.accounts_receivable_account?.[0] ||
                errData?.detail ||
                (typeof errData === 'object' ? JSON.stringify(errData) : null) ||
                err?.message ||
                'Failed to save category';
            setFormError(msg);
        }
    };

    const handleDelete = async (id: number) => {
        try {
            await deleteCategory.mutateAsync(id);
        } catch (err: any) {
            const msg = err?.response?.data?.detail || 'Cannot delete — customers may be assigned to this category.';
            setFormError(msg);
        } finally {
            setConfirmDeleteId(null);
        }
    };

    if (isLoading) return <LoadingScreen message="Loading customer categories..." />;

    return (
        <SalesLayout title="Customer Categories" description="Pre-configure AR accounts for customer segments — customers inherit the GL on creation">

            {/* ── KPI strip */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
                {[
                    { label: 'Total Categories', value: categories.length, color: 'var(--color-primary)' },
                    { label: 'Total Customers', value: categories.reduce((s, c) => s + (c.customer_count || 0), 0), color: '#10b981' },
                    { label: 'AR Accounts Mapped', value: categories.filter((c) => c.accounts_receivable_account).length, color: '#8b5cf6' },
                ].map(({ label, value, color }) => (
                    <div key={label} className="card" style={{ padding: '1.25rem 1.5rem' }}>
                        <span style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)', marginBottom: '0.25rem', letterSpacing: '0.05em' }}>{label}</span>
                        <span style={{ fontSize: '1.75rem', fontWeight: 700, color }}>{value}</span>
                    </div>
                ))}
            </div>

            {/* ── Info banner */}
            <div style={{
                display: 'flex', gap: '0.625rem', alignItems: 'flex-start',
                padding: '0.75rem 1rem', marginBottom: '1.25rem',
                background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.18)',
                borderRadius: '8px', fontSize: 'var(--text-sm)',
            }}>
                <Info size={15} style={{ color: 'var(--color-primary)', flexShrink: 0, marginTop: '2px' }} />
                <span style={{ color: 'var(--color-text-muted)' }}>
                    Each category maps to an <strong>Accounts Receivable reconciliation account</strong>.
                    When a customer is created under a category, their AR GL is set automatically — no manual GL entry needed.
                    Only active AR reconciliation accounts appear in the selector below.
                </span>
            </div>

            {/* ── Toolbar */}
            <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem', alignItems: 'center' }}>
                <input
                    type="text"
                    placeholder="Search categories..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    style={{
                        flex: 1, maxWidth: '320px',
                        padding: '0.625rem 0.875rem', borderRadius: '8px',
                        border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                        color: 'var(--color-text)', fontSize: 'var(--text-sm)',
                    }}
                />
                <button className="btn btn-primary" onClick={openCreate} style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Plus size={16} /> New Category
                </button>
            </div>

            {/* ── Global error banner */}
            {formError && !showForm && (
                <div style={{ padding: '0.75rem 1rem', marginBottom: '1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: '8px', color: 'var(--color-error)', fontSize: 'var(--text-sm)', display: 'flex', justifyContent: 'space-between' }}>
                    <span>{formError}</span>
                    <button onClick={() => setFormError(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-error)' }}><X size={14} /></button>
                </div>
            )}

            {/* ── Create / Edit Form */}
            {showForm && (
                <div className="card animate-fade" style={{ marginBottom: '1.5rem', padding: '1.5rem', border: '2px solid var(--color-primary)', borderRadius: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                        <h3 style={{ margin: 0 }}>{editId ? 'Edit Category' : 'New Customer Category'}</h3>
                        <button onClick={() => { setShowForm(false); setEditId(null); setFormError(null); }}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                            <X size={18} />
                        </button>
                    </div>

                    {formError && (
                        <div style={{ padding: '0.625rem 0.875rem', marginBottom: '1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: '6px', color: 'var(--color-error)', fontSize: 'var(--text-sm)' }}>
                            {formError}
                        </div>
                    )}

                    <form onSubmit={handleSave}>
                        {/* Identification */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                            <div>
                                <label style={labelStyle}>Category Name <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                <input type="text" className="input" required value={form.name}
                                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                                    placeholder="e.g. Corporate" />
                            </div>
                            <div>
                                <label style={labelStyle}>Category Code <span style={{ color: 'var(--color-error)' }}>*</span></label>
                                <input type="text" className="input" required value={form.code}
                                    onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                                    placeholder="e.g. CORP" maxLength={20} />
                            </div>
                        </div>

                        {/* AR GL Account */}
                        <div style={{
                            padding: '1rem', marginBottom: '1rem',
                            background: 'rgba(59,130,246,0.04)',
                            border: '1px solid rgba(59,130,246,0.18)',
                            borderRadius: '8px',
                        }}>
                            <div style={{ marginBottom: '0.75rem' }}>
                                <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-primary)' }}>
                                    Accounts Receivable GL Account
                                </span>
                            </div>
                            <div>
                                <label style={labelStyle}>
                                    AR Account <span style={{ color: 'var(--color-error)' }}>*</span>
                                </label>
                                <select
                                    className="input"
                                    required
                                    value={form.accounts_receivable_account}
                                    onChange={(e) => setForm({ ...form, accounts_receivable_account: e.target.value })}
                                    style={!form.accounts_receivable_account ? { borderColor: 'var(--color-error)' } : {}}
                                >
                                    <option value="">— Select AR account —</option>
                                    {arAccounts.map((a) => (
                                        <option key={a.id} value={a.id}>
                                            {a.code} — {a.name}
                                        </option>
                                    ))}
                                </select>
                                {arAccounts.length === 0 && (
                                    <span style={{ fontSize: 'var(--text-xs)', color: '#f59e0b', marginTop: '4px', display: 'block' }}>
                                        No AR reconciliation accounts found. Set reconciliation type on accounts in Chart of Accounts first.
                                    </span>
                                )}
                            </div>

                            {/* Live preview of selected account */}
                            {selectedAR && (
                                <div style={{
                                    marginTop: '0.75rem', padding: '0.625rem 0.875rem',
                                    background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)',
                                    borderRadius: '6px', display: 'flex', alignItems: 'center', gap: '0.5rem',
                                    fontSize: 'var(--text-sm)',
                                }}>
                                    <Check size={13} style={{ color: '#10b981', flexShrink: 0 }} />
                                    <span>
                                        Customers in this category will post AR to{' '}
                                        <strong style={{ fontFamily: 'monospace' }}>{selectedAR.code}</strong>
                                        {' — '}{selectedAR.name}
                                    </span>
                                </div>
                            )}
                        </div>

                        <div style={{ marginBottom: '1.25rem' }}>
                            <label style={labelStyle}>Description</label>
                            <textarea className="input" rows={2} value={form.description}
                                onChange={(e) => setForm({ ...form, description: e.target.value })}
                                placeholder="Optional description..." />
                        </div>

                        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                            <button type="button" className="btn btn-outline" onClick={() => { setShowForm(false); setEditId(null); setFormError(null); }}>Cancel</button>
                            <button type="submit" className="btn btn-primary"
                                disabled={createCategory.isPending || updateCategory.isPending}
                                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                                <Check size={15} />
                                {editId ? 'Update Category' : 'Create Category'}
                            </button>
                        </div>
                    </form>
                </div>
            )}

            {/* ── Table */}
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                {filtered.length === 0 ? (
                    <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                        <Tag size={48} style={{ margin: '0 auto 1rem', opacity: 0.2, display: 'block' }} />
                        <p style={{ fontWeight: 500, margin: 0 }}>
                            {search ? 'No categories match your search.' : 'No customer categories yet. Create one to get started.'}
                        </p>
                    </div>
                ) : (
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr>
                                    <th style={thStyle}>Code</th>
                                    <th style={thStyle}>Name</th>
                                    <th style={thStyle}>AR GL Account</th>
                                    <th style={thStyle}>Description</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Customers</th>
                                    <th style={{ ...thStyle, width: '100px' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.map((cat) => (
                                    <tr key={cat.id}
                                        style={{ transition: 'background 0.15s' }}
                                        onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-surface)')}
                                        onMouseLeave={(e) => (e.currentTarget.style.background = '')}
                                    >
                                        <td style={tdStyle}>
                                            <span style={{
                                                display: 'inline-block', padding: '0.2rem 0.6rem',
                                                borderRadius: '20px', fontSize: 'var(--text-xs)', fontWeight: 700,
                                                background: 'rgba(59,130,246,0.1)', color: '#3b82f6',
                                                letterSpacing: '0.04em',
                                            }}>
                                                {cat.code}
                                            </span>
                                        </td>
                                        <td style={{ ...tdStyle, fontWeight: 600 }}>{cat.name}</td>
                                        <td style={tdStyle}>
                                            {cat.accounts_receivable_account_name ? (
                                                <>
                                                    <div style={{ fontWeight: 600 }}>{cat.accounts_receivable_account_name}</div>
                                                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontFamily: 'monospace' }}>
                                                        {cat.accounts_receivable_account_code}
                                                    </div>
                                                </>
                                            ) : (
                                                <span style={{
                                                    display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                                    fontSize: 'var(--text-xs)', color: '#f59e0b', fontWeight: 600,
                                                }}>
                                                    ⚠ Not configured
                                                </span>
                                            )}
                                        </td>
                                        <td style={{ ...tdStyle, color: 'var(--color-text-muted)', maxWidth: '240px' }}>
                                            <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                                                title={cat.description ?? ''}>
                                                {cat.description || '—'}
                                            </span>
                                        </td>
                                        <td style={{ ...tdStyle, textAlign: 'right' }}>
                                            <span style={{
                                                display: 'inline-block', padding: '0.2rem 0.75rem',
                                                borderRadius: '20px', background: '#f1f5f9',
                                                fontSize: 'var(--text-xs)', fontWeight: 600, color: '#475569',
                                            }}>
                                                {cat.customer_count}
                                            </span>
                                        </td>
                                        <td style={tdStyle}>
                                            <div style={{ display: 'flex', gap: '0.375rem', alignItems: 'center' }}>
                                                <button
                                                    onClick={() => openEdit(cat)}
                                                    style={{ background: 'rgba(59,130,246,0.08)', border: 'none', borderRadius: '6px', padding: '0.35rem', cursor: 'pointer', color: '#3b82f6', display: 'flex', alignItems: 'center' }}
                                                    title="Edit">
                                                    <Edit2 size={14} />
                                                </button>
                                                {confirmDeleteId === cat.id ? (
                                                    <>
                                                        <button onClick={() => handleDelete(cat.id)}
                                                            style={{ background: '#ef4444', color: '#fff', border: 'none', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer', fontSize: 'var(--text-xs)', fontFamily: 'inherit', fontWeight: 600 }}>
                                                            Yes
                                                        </button>
                                                        <button onClick={() => setConfirmDeleteId(null)}
                                                            style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer', fontSize: 'var(--text-xs)', fontFamily: 'inherit' }}>
                                                            No
                                                        </button>
                                                    </>
                                                ) : (
                                                    <button
                                                        onClick={() => setConfirmDeleteId(cat.id)}
                                                        disabled={cat.customer_count > 0}
                                                        style={{
                                                            background: cat.customer_count > 0 ? 'transparent' : 'rgba(239,68,68,0.08)',
                                                            border: 'none', borderRadius: '6px', padding: '0.35rem',
                                                            cursor: cat.customer_count > 0 ? 'not-allowed' : 'pointer',
                                                            color: cat.customer_count > 0 ? 'var(--color-text-muted)' : '#ef4444',
                                                            display: 'flex', alignItems: 'center',
                                                            opacity: cat.customer_count > 0 ? 0.4 : 1,
                                                        }}
                                                        title={cat.customer_count > 0 ? `${cat.customer_count} customer(s) — cannot delete` : 'Delete'}>
                                                        <Trash2 size={14} />
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
        </SalesLayout>
    );
};

export default CustomerCategoryList;
