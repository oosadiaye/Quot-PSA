import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Plus, Search, FolderTree, Edit2, Trash2, X, Save } from 'lucide-react';
import {
    useVendorCategories,
    useCreateVendorCategory,
    useUpdateVendorCategory,
    useDeleteVendorCategory,
} from './hooks/useProcurement';
import apiClient from '../../api/client';
import AccountingLayout from '../accounting/AccountingLayout';
import LoadingScreen from '../../components/common/LoadingScreen';
import PageHeader from '../../components/PageHeader';
import '../accounting/styles/glassmorphism.css';

interface VendorCategory {
    id: number;
    name: string;
    code: string;
    description?: string;
    reconciliation_account: number | null;
    reconciliation_account_name?: string;
    reconciliation_account_code?: string;
    is_active: boolean;
    vendor_count: number;
}

interface CategoryForm {
    name: string;
    code: string;
    description: string;
    reconciliation_account: string;
    is_active: boolean;
}

const emptyForm: CategoryForm = {
    name: '',
    code: '',
    description: '',
    reconciliation_account: '',
    is_active: true,
};

export default function VendorCategoryList() {
    const [searchTerm, setSearchTerm] = useState('');
    const [showModal, setShowModal] = useState(false);
    const [editingCategory, setEditingCategory] = useState<VendorCategory | null>(null);
    const [form, setForm] = useState<CategoryForm>(emptyForm);
    const [formError, setFormError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

    const { data: categoriesRaw, isLoading } = useVendorCategories();
    const createMutation = useCreateVendorCategory();
    const updateMutation = useUpdateVendorCategory();
    const deleteMutation = useDeleteVendorCategory();

    const { data: apAccounts } = useQuery({
        queryKey: ['accounts', 'ap-reconciliation'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/accounts/', {
                params: { reconciliation_type: 'accounts_payable', is_active: true, page_size: 100 },
            });
            return data.results || data || [];
        },
        staleTime: 5 * 60 * 1000,
    });

    const categories: VendorCategory[] = categoriesRaw || [];

    const filtered = categories.filter((cat) => {
        const q = searchTerm.toLowerCase();
        return (
            cat.name.toLowerCase().includes(q) ||
            cat.code.toLowerCase().includes(q)
        );
    });

    const openCreate = () => {
        setEditingCategory(null);
        setForm(emptyForm);
        setFormError('');
        setShowModal(true);
    };

    const openEdit = (cat: VendorCategory) => {
        setEditingCategory(cat);
        setForm({
            name: cat.name,
            code: cat.code,
            description: cat.description || '',
            reconciliation_account: cat.reconciliation_account ? String(cat.reconciliation_account) : '',
            is_active: cat.is_active,
        });
        setFormError('');
        setShowModal(true);
    };

    const closeModal = () => {
        setShowModal(false);
        setEditingCategory(null);
        setForm(emptyForm);
        setFormError('');
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        if (!form.name.trim() || !form.code.trim()) {
            setFormError('Name and Code are required.');
            return;
        }
        if (!form.reconciliation_account) {
            setFormError('Reconciliation Account is required.');
            return;
        }

        const payload = {
            name: form.name.trim(),
            code: form.code.trim(),
            description: form.description.trim() || undefined,
            reconciliation_account: parseInt(form.reconciliation_account),
            is_active: form.is_active,
        };

        try {
            if (editingCategory) {
                await updateMutation.mutateAsync({ id: editingCategory.id, ...payload });
            } else {
                await createMutation.mutateAsync(payload);
            }
            closeModal();
        } catch (err: any) {
            const data = err?.response?.data;
            if (data?.detail) {
                setFormError(data.detail);
            } else if (data && typeof data === 'object') {
                const msgs = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`);
                setFormError(msgs.join(' | '));
            } else {
                setFormError(err?.message || 'Operation failed.');
            }
        }
    };

    const handleDelete = async (id: number) => {
        try {
            await deleteMutation.mutateAsync(id);
        } catch (err: any) {
            const msg = err?.response?.data?.detail || err?.response?.data?.error || err?.message || 'Cannot delete: category may have associated vendors';
            setFormError(msg);
        } finally {
            setDeleteConfirm(null);
        }
    };

    const isPending = createMutation.isPending || updateMutation.isPending;

    if (isLoading) {
        return (
            <AccountingLayout>
                <LoadingScreen message="Loading vendor categories..." />
            </AccountingLayout>
        );
    }

    return (
        <AccountingLayout>
            <PageHeader
                title="Vendor Categories"
                subtitle="Manage vendor categories with AP reconciliation account assignments"
                icon={<FolderTree size={22} />}
                actions={
                    <button
                        onClick={openCreate}
                        className="glass-button"
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.5rem',
                            padding: '0.75rem 1.5rem',
                            background: 'rgba(255,255,255,0.18)',
                            color: 'white',
                            border: '1px solid rgba(255,255,255,0.25)',
                            borderRadius: '8px',
                            cursor: 'pointer',
                            fontWeight: 500,
                        }}
                    >
                        <Plus size={20} />
                        New Category
                    </button>
                }
            />

            {/* Search bar */}
            <div className="glass-card" style={{ marginBottom: '1.5rem', padding: '1rem' }}>
                <div style={{ position: 'relative' }}>
                    <Search
                        style={{
                            position: 'absolute',
                            left: '12px',
                            top: '50%',
                            transform: 'translateY(-50%)',
                            color: 'var(--color-text-muted)',
                        }}
                        size={20}
                    />
                    <input
                        type="text"
                        placeholder="Search by name or code..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        style={{
                            width: '100%',
                            paddingLeft: '2.75rem',
                            paddingRight: '1rem',
                            paddingTop: '0.75rem',
                            paddingBottom: '0.75rem',
                            borderRadius: '8px',
                            border: '1px solid var(--color-border)',
                            background: 'var(--color-surface)',
                            color: 'var(--color-text)',
                            fontSize: 'var(--text-sm)',
                        }}
                    />
                </div>
            </div>

            {/* Delete error banner */}
            {formError && !showModal && (
                <div style={{
                    padding: '0.75rem 1rem', background: 'rgba(239,68,68,0.08)',
                    border: '1px solid rgba(239,68,68,0.2)', color: '#ef4444',
                    borderRadius: '8px', marginBottom: '1rem', fontSize: 'var(--text-sm)',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                    <span>{formError}</span>
                    <button aria-label="Dismiss error" onClick={() => setFormError('')} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontWeight: 700 }}><span aria-hidden="true">&times;</span></button>
                </div>
            )}

            {/* Table */}
            <div className="glass-card" style={{ overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Code</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Name</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Reconciliation Account</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'center', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Vendors</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'center', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Status</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.length > 0 ? (
                                filtered.map((cat, index) => (
                                    <tr
                                        key={cat.id}
                                        style={{
                                            borderBottom: '1px solid var(--color-border)',
                                            animation: `fadeInUp 0.3s ease-out ${index * 0.05}s both`,
                                        }}
                                    >
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)', fontWeight: 600, fontSize: 'var(--text-sm)' }}>
                                            {cat.code}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)' }}>
                                            {cat.name}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                            {cat.reconciliation_account_code && cat.reconciliation_account_name
                                                ? `${cat.reconciliation_account_code} — ${cat.reconciliation_account_name}`
                                                : cat.reconciliation_account_name || '—'}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', textAlign: 'center', color: 'var(--color-text)', fontWeight: 500 }}>
                                            {cat.vendor_count}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', textAlign: 'center' }}>
                                            <span style={{
                                                display: 'inline-block',
                                                padding: '0.25rem 0.75rem',
                                                borderRadius: '9999px',
                                                fontSize: 'var(--text-xs)',
                                                fontWeight: 600,
                                                background: cat.is_active ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                                                color: cat.is_active ? '#22c55e' : '#ef4444',
                                            }}>
                                                {cat.is_active ? 'Active' : 'Inactive'}
                                            </span>
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem' }}>
                                            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                                {deleteConfirm === cat.id ? (
                                                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                                        <span style={{ fontSize: '0.85rem', color: '#dc2626' }}>Delete?</span>
                                                        <button
                                                            onClick={() => handleDelete(cat.id)}
                                                            style={{ background: '#dc2626', color: 'white', border: 'none', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer', fontSize: 'var(--text-xs)' }}
                                                        >
                                                            Yes
                                                        </button>
                                                        <button
                                                            onClick={() => setDeleteConfirm(null)}
                                                            style={{ background: '#e2e8f0', border: 'none', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer', fontSize: 'var(--text-xs)' }}
                                                        >
                                                            No
                                                        </button>
                                                    </div>
                                                ) : (
                                                    <>
                                                        <button
                                                            onClick={() => openEdit(cat)}
                                                            style={{
                                                                padding: '0.375rem 0.75rem',
                                                                borderRadius: '6px',
                                                                border: 'none',
                                                                background: 'rgba(36, 113, 163, 0.1)',
                                                                color: '#2471a3',
                                                                cursor: 'pointer',
                                                                fontSize: 'var(--text-xs)',
                                                                fontWeight: 600,
                                                                display: 'inline-flex',
                                                                alignItems: 'center',
                                                                gap: '0.25rem',
                                                            }}
                                                            title="Edit"
                                                        >
                                                            <Edit2 size={14} />
                                                            Edit
                                                        </button>
                                                        <button
                                                            onClick={() => setDeleteConfirm(cat.id)}
                                                            style={{
                                                                padding: '0.375rem 0.75rem',
                                                                borderRadius: '6px',
                                                                border: 'none',
                                                                background: 'rgba(239, 68, 68, 0.1)',
                                                                color: '#ef4444',
                                                                cursor: 'pointer',
                                                                fontSize: 'var(--text-xs)',
                                                                fontWeight: 600,
                                                                display: 'inline-flex',
                                                                alignItems: 'center',
                                                                gap: '0.25rem',
                                                            }}
                                                            title="Delete"
                                                        >
                                                            <Trash2 size={14} />
                                                            Delete
                                                        </button>
                                                    </>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td colSpan={6} style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <FolderTree size={48} style={{ margin: '0 auto 1rem', opacity: 0.5, display: 'block' }} />
                                        <p>{searchTerm ? 'No categories match your search.' : 'No vendor categories found. Create one to get started.'}</p>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Create / Edit Modal */}
            {showModal && (
                <div style={{
                    position: 'fixed',
                    inset: 0,
                    background: 'rgba(15, 23, 42, 0.55)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    zIndex: 1000,
                    backdropFilter: 'blur(2px)',
                }}>
                    <div style={{
                        background: 'var(--color-card, white)',
                        borderRadius: '16px',
                        padding: '2rem',
                        width: '100%',
                        maxWidth: '520px',
                        boxShadow: '0 24px 64px rgba(0,0,0,0.25)',
                        maxHeight: '90vh',
                        overflowY: 'auto',
                    }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                            <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                                {editingCategory ? 'Edit Vendor Category' : 'New Vendor Category'}
                            </h2>
                            <button
                                onClick={closeModal}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', padding: '4px' }}
                            >
                                <X size={20} />
                            </button>
                        </div>

                        {formError && (
                            <div style={{
                                padding: '0.75rem 1rem',
                                marginBottom: '1rem',
                                borderRadius: '8px',
                                background: 'rgba(239,68,68,0.1)',
                                color: '#ef4444',
                                fontSize: 'var(--text-sm)',
                            }}>
                                {formError}
                            </div>
                        )}

                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.4rem', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>
                                        Code *
                                    </label>
                                    <input
                                        type="text"
                                        value={form.code}
                                        onChange={(e) => setForm({ ...form, code: e.target.value })}
                                        placeholder="e.g. VC-001"
                                        required
                                        style={{
                                            width: '100%',
                                            padding: '0.625rem 0.875rem',
                                            borderRadius: '8px',
                                            border: '1px solid var(--color-border)',
                                            background: 'var(--color-surface)',
                                            color: 'var(--color-text)',
                                            fontSize: 'var(--text-sm)',
                                            boxSizing: 'border-box',
                                        }}
                                    />
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.4rem', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>
                                        Name *
                                    </label>
                                    <input
                                        type="text"
                                        value={form.name}
                                        onChange={(e) => setForm({ ...form, name: e.target.value })}
                                        placeholder="Category name"
                                        required
                                        style={{
                                            width: '100%',
                                            padding: '0.625rem 0.875rem',
                                            borderRadius: '8px',
                                            border: '1px solid var(--color-border)',
                                            background: 'var(--color-surface)',
                                            color: 'var(--color-text)',
                                            fontSize: 'var(--text-sm)',
                                            boxSizing: 'border-box',
                                        }}
                                    />
                                </div>
                                <div style={{ gridColumn: '1 / -1' }}>
                                    <label style={{ display: 'block', marginBottom: '0.4rem', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>
                                        Reconciliation Account (AP) *
                                    </label>
                                    <select
                                        value={form.reconciliation_account}
                                        onChange={(e) => setForm({ ...form, reconciliation_account: e.target.value })}
                                        required
                                        style={{
                                            width: '100%',
                                            padding: '0.625rem 0.875rem',
                                            borderRadius: '8px',
                                            border: '1px solid var(--color-border)',
                                            background: 'var(--color-surface)',
                                            color: 'var(--color-text)',
                                            fontSize: 'var(--text-sm)',
                                        }}
                                    >
                                        <option value="">Select AP account...</option>
                                        {(apAccounts || []).map((acc: any) => (
                                            <option key={acc.id} value={acc.id}>
                                                {acc.code} — {acc.name}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                                <div style={{ gridColumn: '1 / -1' }}>
                                    <label style={{ display: 'block', marginBottom: '0.4rem', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>
                                        Description
                                    </label>
                                    <textarea
                                        value={form.description}
                                        onChange={(e) => setForm({ ...form, description: e.target.value })}
                                        placeholder="Optional description"
                                        rows={3}
                                        style={{
                                            width: '100%',
                                            padding: '0.625rem 0.875rem',
                                            borderRadius: '8px',
                                            border: '1px solid var(--color-border)',
                                            background: 'var(--color-surface)',
                                            color: 'var(--color-text)',
                                            fontSize: 'var(--text-sm)',
                                            resize: 'vertical',
                                            boxSizing: 'border-box',
                                        }}
                                    />
                                </div>
                                <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                    <input
                                        type="checkbox"
                                        id="cat-is-active"
                                        checked={form.is_active}
                                        onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                                        style={{ width: '16px', height: '16px', cursor: 'pointer' }}
                                    />
                                    <label htmlFor="cat-is-active" style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text)', cursor: 'pointer', fontWeight: 500 }}>
                                        Active
                                    </label>
                                </div>
                            </div>

                            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.5rem' }}>
                                <button
                                    type="button"
                                    onClick={closeModal}
                                    style={{
                                        padding: '0.625rem 1.25rem',
                                        borderRadius: '8px',
                                        border: '1px solid var(--color-border)',
                                        background: 'transparent',
                                        color: 'var(--color-text)',
                                        cursor: 'pointer',
                                        fontWeight: 500,
                                        fontSize: 'var(--text-sm)',
                                    }}
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={isPending}
                                    style={{
                                        padding: '0.625rem 1.25rem',
                                        borderRadius: '8px',
                                        border: 'none',
                                        background: 'linear-gradient(135deg, #2471a3, #1a5276)',
                                        color: 'white',
                                        cursor: isPending ? 'not-allowed' : 'pointer',
                                        fontWeight: 600,
                                        fontSize: 'var(--text-sm)',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '0.5rem',
                                        opacity: isPending ? 0.7 : 1,
                                    }}
                                >
                                    <Save size={16} />
                                    {isPending ? 'Saving...' : (editingCategory ? 'Update Category' : 'Create Category')}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </AccountingLayout>
    );
}
