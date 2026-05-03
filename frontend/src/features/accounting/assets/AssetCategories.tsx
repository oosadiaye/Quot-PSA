import { useState, useMemo, useRef, useEffect } from 'react';
import { Plus, Edit, Trash2, Search, X, Check, ChevronUp, ChevronDown, ChevronLeft, ChevronRight, FolderTree, Upload, Download, FileDown } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import {
    useAssetCategories,
    useCreateAssetCategory,
    useUpdateAssetCategory,
    useDeleteAssetCategory,
} from '../hooks/useAccountingEnhancements';
import StatusBadge from '../components/shared/StatusBadge';
import GlassCard from '../components/shared/GlassCard';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import { useDialog } from '../../../hooks/useDialog';
import '../styles/glassmorphism.css';

interface AccountOption {
    id: number;
    code: string;
    name: string;
}

interface AccountDisplay {
    id: number;
    code: string;
    name: string;
}

interface AssetCategory {
    id: number;
    name: string;
    code: string;
    asset_class: number | null;
    is_active: boolean;
    cost_account: number | null;
    accumulated_depreciation_account: number | null;
    depreciation_expense_account: number | null;
    cost_account_display: AccountDisplay | null;
    accumulated_depreciation_account_display: AccountDisplay | null;
    depreciation_expense_account_display: AccountDisplay | null;
    depreciation_method: string;
    depreciation_method_display: string;
    default_life_years: number;
    residual_value_type: string;
    residual_value_type_display: string;
    residual_value: string;
}

type SortKey = 'code' | 'name' | 'depreciation_method' | 'default_life_years' | 'is_active';

const DEPRECIATION_METHODS = [
    { value: 'Straight-Line', label: 'Straight-Line' },
    { value: 'Declining Balance', label: 'Declining Balance' },
    { value: 'Double Declining Balance', label: 'Double Declining Balance' },
    { value: 'Sum of Years Digits', label: 'Sum of Years Digits' },
    { value: 'Units of Production', label: 'Units of Production' },
];

const initialFormData = {
    code: '',
    name: '',
    is_active: true,
    cost_account: '' as string | number,
    accumulated_depreciation_account: '' as string | number,
    depreciation_expense_account: '' as string | number,
    depreciation_method: 'Straight-Line',
    default_life_years: 5,
    residual_value_type: 'percentage',
    residual_value: '0',
};

export default function AssetCategories() {
    const { showConfirm, showAlert } = useDialog();
    const { formatCurrency, currencySymbol } = useCurrency();
    const queryClient = useQueryClient();

    // Import / Export plumbing — mirrors COA + NCoA dimension pages.
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [isImporting, setIsImporting] = useState(false);
    const [importResult, setImportResult] = useState<{
        success: boolean;
        created: number;
        updated: number;
        skipped: number;
        errors: string[];
    } | null>(null);

    const handleDownloadTemplate = async () => {
        try {
            const res = await apiClient.get('/accounting/asset-categories/import-template/', {
                responseType: 'blob',
            });
            const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
            const a = document.createElement('a');
            a.href = url;
            a.download = 'asset_category_import_template.csv';
            a.click();
            window.URL.revokeObjectURL(url);
        } catch {
            showAlert('Could not download the template. Please check your connection and try again.', 'error');
        }
    };

    const handleExport = async () => {
        try {
            const res = await apiClient.get('/accounting/asset-categories/export/', {
                responseType: 'blob',
            });
            const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
            const a = document.createElement('a');
            a.href = url;
            a.download = 'asset_categories_export.csv';
            a.click();
            window.URL.revokeObjectURL(url);
        } catch {
            showAlert('Failed to export asset categories.', 'error');
        }
    };

    const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;
        setIsImporting(true);
        setImportResult(null);
        try {
            const formData = new FormData();
            formData.append('file', file);
            // Same Content-Type override pattern as COA / NCoA imports —
            // without it, the global ``application/json`` baked into
            // apiClient JSON-serialises the FormData and the file is lost.
            const response = await apiClient.post(
                '/accounting/asset-categories/bulk-import/',
                formData,
                { headers: { 'Content-Type': 'multipart/form-data' } },
            );
            setImportResult(response.data);
            // Invalidate the prefix — every query whose key starts with
            // 'asset-categories' (the AssetCategories list, the COA dropdown,
            // any future consumer) re-fetches in one shot.
            queryClient.invalidateQueries({ queryKey: ['asset-categories'] });
        } catch (err: any) {
            setImportResult({
                success: false,
                created: 0,
                updated: 0,
                skipped: 0,
                errors: [err.response?.data?.error || 'Import failed. Please check the file format.'],
            });
        } finally {
            setIsImporting(false);
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    const [showForm, setShowForm] = useState(false);
    const [editingCategory, setEditingCategory] = useState<AssetCategory | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: 'asc' | 'desc' } | null>(null);
    const [formData, setFormData] = useState(initialFormData);
    const [formError, setFormError] = useState('');

    // Data hooks
    const { data: categories, isLoading, isError, error } = useAssetCategories();
    const createCategory = useCreateAssetCategory();
    const updateCategory = useUpdateAssetCategory();
    const deleteCategory = useDeleteAssetCategory();

    // Fetch GL accounts for dropdowns. page_size=10000 is the server-side
    // cap (AccountingPagination.max_page_size); 100 was too small for real
    // tenant Charts of Accounts (175 Asset / 619 Expense accounts in this
    // tenant got silently truncated).
    const { data: assetAccounts } = useQuery<AccountOption[]>({
        queryKey: ['accounts', 'asset-all'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/accounts/', {
                params: { account_type: 'Asset', page_size: 10000, ordering: 'code' },
            });
            return Array.isArray(data) ? data : (data?.results ?? []);
        },
        staleTime: 5 * 60 * 1000,
    });

    const { data: expenseAccounts } = useQuery<AccountOption[]>({
        queryKey: ['accounts', 'expense-all'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/accounts/', {
                params: { account_type: 'Expense', page_size: 10000, ordering: 'code' },
            });
            return Array.isArray(data) ? data : (data?.results ?? []);
        },
        staleTime: 5 * 60 * 1000,
    });

    const resetForm = () => {
        setFormData(initialFormData);
        setEditingCategory(null);
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');
        const payload = {
            ...formData,
            cost_account: formData.cost_account || null,
            accumulated_depreciation_account: formData.accumulated_depreciation_account || null,
            depreciation_expense_account: formData.depreciation_expense_account || null,
            residual_value: formData.residual_value || '0',
        };

        const errorHandler = {
            onSuccess: () => { setShowForm(false); resetForm(); setFormError(''); },
            onError: (err: any) => {
                const data = err?.response?.data;
                if (data) {
                    const messages = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join('; ');
                    setFormError(messages);
                } else {
                    setFormError(err?.message || 'Failed to save asset category');
                }
            },
        };

        if (editingCategory) {
            updateCategory.mutate({ id: editingCategory.id, ...payload }, errorHandler);
        } else {
            createCategory.mutate(payload, errorHandler);
        }
    };

    const handleEdit = (cat: AssetCategory) => {
        setEditingCategory(cat);
        setFormData({
            code: cat.code,
            name: cat.name,
            is_active: cat.is_active,
            cost_account: cat.cost_account || '',
            accumulated_depreciation_account: cat.accumulated_depreciation_account || '',
            depreciation_expense_account: cat.depreciation_expense_account || '',
            depreciation_method: cat.depreciation_method,
            default_life_years: cat.default_life_years,
            residual_value_type: cat.residual_value_type,
            residual_value: cat.residual_value,
        });
        setShowForm(true);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const handleDelete = async (id: number, name: string) => {
        if (await showConfirm(`Delete asset category "${name}"? This action cannot be undone.`)) {
            deleteCategory.mutate(id);
        }
    };

    const requestSort = (key: SortKey) => {
        let direction: 'asc' | 'desc' = 'asc';
        if (sortConfig && sortConfig.key === key && sortConfig.direction === 'asc') {
            direction = 'desc';
        }
        setSortConfig({ key, direction });
    };

    const sortedCategories = useMemo(() => {
        let filtered = (Array.isArray(categories) ? categories : []).filter((cat: AssetCategory) =>
            cat.code.toLowerCase().includes(searchTerm.toLowerCase()) ||
            cat.name.toLowerCase().includes(searchTerm.toLowerCase())
        );

        if (sortConfig !== null) {
            filtered.sort((a: any, b: any) => {
                const aValue = a[sortConfig.key];
                const bValue = b[sortConfig.key];
                if (aValue < bValue) return sortConfig.direction === 'asc' ? -1 : 1;
                if (aValue > bValue) return sortConfig.direction === 'asc' ? 1 : -1;
                return 0;
            });
        }
        return filtered;
    }, [categories, searchTerm, sortConfig]);

    // Client-side pagination state. Default page-size of 20 matches the COA
    // list so the two pages feel identical. Changing search or sort resets
    // to page 1 so the user isn't stranded on an empty page after filtering.
    const [currentPage, setCurrentPage] = useState(1);
    const [pageSize, setPageSize] = useState(20);
    const totalCount = sortedCategories.length;
    const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
    // Clamp the page index in case the filtered list shrinks below the
    // current page boundary (e.g. user types a search that filters everything
    // off the back pages). We don't useEffect — clamping at render is enough
    // and avoids an extra render cycle.
    const safePage = Math.min(currentPage, totalPages);
    const pageStart = (safePage - 1) * pageSize;
    const pageEnd = pageStart + pageSize;
    const paginatedCategories = sortedCategories.slice(pageStart, pageEnd);
    // Reset to page 1 whenever the underlying filter / sort / page-size
    // changes. Without this, after typing a query that narrows results
    // below the current page boundary the user lands on an empty page.
    useEffect(() => { setCurrentPage(1); }, [searchTerm, sortConfig, pageSize]);

    const getSortIndicator = (key: SortKey) => {
        if (!sortConfig || sortConfig.key !== key) return null;
        return sortConfig.direction === 'asc'
            ? <ChevronUp size={14} style={{ marginLeft: '4px' }} />
            : <ChevronDown size={14} style={{ marginLeft: '4px' }} />;
    };

    if (isError) {
        return (
            <AccountingLayout>
                <div style={{ padding: '2rem', textAlign: 'center', color: 'red' }}>
                    <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 600, marginBottom: '1rem' }}>Error loading Asset Categories</h2>
                    <p style={{ marginBottom: '1.5rem' }}>{(error as any)?.message || 'Unknown error occurred'}</p>
                    <button className="btn btn-primary" onClick={() => window.location.reload()}>Retry</button>
                </div>
            </AccountingLayout>
        );
    }

    if (isLoading) {
        return <LoadingScreen message="Loading asset categories..." />;
    }

    const labelStyle: React.CSSProperties = {
        display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600,
        color: 'var(--text-secondary)', marginBottom: '8px',
        textTransform: 'uppercase', letterSpacing: '0.05em',
    };

    return (
        <AccountingLayout>
            {/* Hidden file input — triggered by the Import button. */}
            <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx"
                style={{ display: 'none' }}
                onChange={handleImport}
            />
            <PageHeader
                title="Asset Categories"
                subtitle="Define asset groups with GL assignments, depreciation methods, and residual values"
                icon={<FolderTree size={22} />}
                actions={
                    <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
                        {/* Template / Import / Export — matched geometry with
                            the COA toolbar (padding, border-radius, font-weight,
                            shadow). Neutral white/glass fill keeps them quiet
                            so the primary Add Category CTA reads loudest. */}
                        <button
                            onClick={handleDownloadTemplate}
                            title="Download a CSV template with help block + example rows"
                            style={{
                                display: 'inline-flex', alignItems: 'center',
                                padding: '0.55rem 1.1rem',
                                background: '#ffffff',
                                color: '#0f172a',
                                border: '1px solid rgba(255,255,255,0.6)',
                                borderRadius: '8px',
                                fontSize: 'var(--text-sm)',
                                fontWeight: 600,
                                cursor: 'pointer',
                                boxShadow: '0 2px 6px rgba(0,0,0,0.12)',
                                transition: 'transform 0.15s, box-shadow 0.15s, background 0.15s',
                            }}
                            onMouseEnter={(e) => {
                                (e.currentTarget as HTMLButtonElement).style.background = '#f8fafc';
                                (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 4px 10px rgba(0,0,0,0.18)';
                            }}
                            onMouseLeave={(e) => {
                                (e.currentTarget as HTMLButtonElement).style.background = '#ffffff';
                                (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 2px 6px rgba(0,0,0,0.12)';
                            }}
                        >
                            <FileDown size={18} style={{ marginRight: '8px' }} /> Template
                        </button>
                        <button
                            onClick={() => fileInputRef.current?.click()}
                            disabled={isImporting}
                            title="Upload a CSV / XLSX to bulk-create or update asset categories"
                            style={{
                                display: 'inline-flex', alignItems: 'center',
                                padding: '0.55rem 1.1rem',
                                background: '#ffffff',
                                color: '#0f172a',
                                border: '1px solid rgba(255,255,255,0.6)',
                                borderRadius: '8px',
                                fontSize: 'var(--text-sm)',
                                fontWeight: 600,
                                cursor: isImporting ? 'not-allowed' : 'pointer',
                                opacity: isImporting ? 0.65 : 1,
                                boxShadow: '0 2px 6px rgba(0,0,0,0.12)',
                                transition: 'transform 0.15s, box-shadow 0.15s, background 0.15s',
                            }}
                            onMouseEnter={(e) => {
                                if (isImporting) return;
                                (e.currentTarget as HTMLButtonElement).style.background = '#f8fafc';
                                (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 4px 10px rgba(0,0,0,0.18)';
                            }}
                            onMouseLeave={(e) => {
                                (e.currentTarget as HTMLButtonElement).style.background = '#ffffff';
                                (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 2px 6px rgba(0,0,0,0.12)';
                            }}
                        >
                            <Upload size={18} style={{ marginRight: '8px' }} />
                            {isImporting ? 'Importing...' : 'Import'}
                        </button>
                        <button
                            onClick={handleExport}
                            title="Export every asset category as a CSV (re-importable)"
                            style={{
                                display: 'inline-flex', alignItems: 'center',
                                padding: '0.55rem 1.1rem',
                                background: '#ffffff',
                                color: '#0f172a',
                                border: '1px solid rgba(255,255,255,0.6)',
                                borderRadius: '8px',
                                fontSize: 'var(--text-sm)',
                                fontWeight: 600,
                                cursor: 'pointer',
                                boxShadow: '0 2px 6px rgba(0,0,0,0.12)',
                                transition: 'transform 0.15s, box-shadow 0.15s, background 0.15s',
                            }}
                            onMouseEnter={(e) => {
                                (e.currentTarget as HTMLButtonElement).style.background = '#f8fafc';
                                (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 4px 10px rgba(0,0,0,0.18)';
                            }}
                            onMouseLeave={(e) => {
                                (e.currentTarget as HTMLButtonElement).style.background = '#ffffff';
                                (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 2px 6px rgba(0,0,0,0.12)';
                            }}
                        >
                            <Download size={18} style={{ marginRight: '8px' }} /> Export
                        </button>
                        <button
                            className="btn-primary ripple"
                            onClick={() => {
                                if (showForm && !editingCategory) {
                                    setShowForm(false);
                                } else {
                                    resetForm();
                                    setShowForm(true);
                                }
                            }}
                        >
                            {showForm && !editingCategory ? <X size={18} style={{ marginRight: '8px' }} /> : <Plus size={18} style={{ marginRight: '8px' }} />}
                            {showForm && !editingCategory ? 'Close Form' : 'Add Category'}
                        </button>
                    </div>
                }
            />

            {/* Import result banner — counts + collapsible error list. */}
            {importResult && (
                <div className="animate-slide-down" style={{ marginBottom: '1.5rem' }}>
                    <GlassCard style={{
                        padding: '1.25rem',
                        borderLeft: `4px solid ${importResult.errors.length > 0 ? '#f59e0b' : '#22c55e'}`,
                    }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div>
                                <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.4rem' }}>
                                    Import Results
                                </h3>
                                <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', margin: 0 }}>
                                    Created: <strong>{importResult.created}</strong> &nbsp;|&nbsp;
                                    Updated: <strong>{importResult.updated}</strong>
                                    {importResult.errors.length > 0 && (
                                        <> &nbsp;|&nbsp; Errors: <strong style={{ color: '#ef4444' }}>{importResult.errors.length}</strong></>
                                    )}
                                </p>
                                {importResult.errors.length > 0 && (
                                    <ul style={{
                                        marginTop: '0.6rem', paddingLeft: '1.25rem',
                                        color: '#ef4444', fontSize: 'var(--text-sm)',
                                        maxHeight: '140px', overflowY: 'auto',
                                    }}>
                                        {importResult.errors.map((err, i) => (
                                            <li key={`err-${i}-${err.slice(0, 20)}`} style={{ marginBottom: '0.2rem' }}>{err}</li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                            <button
                                onClick={() => setImportResult(null)}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}
                                aria-label="Dismiss"
                            >
                                <X size={18} />
                            </button>
                        </div>
                    </GlassCard>
                </div>
            )}

            {/* Add/Edit Form */}
            {showForm && (
                <div className="animate-slide-down" style={{ marginBottom: '2.5rem' }}>
                    <GlassCard gradient style={{ padding: '2rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                            <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>
                                {editingCategory ? 'Edit Asset Category' : 'Create New Asset Category'}
                            </h2>
                            <button
                                onClick={() => { setShowForm(false); resetForm(); }}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
                            >
                                <X size={20} />
                            </button>
                        </div>

                        <form onSubmit={handleSubmit}>
                            {formError && (
                                <div style={{
                                    padding: '10px 16px', borderRadius: '8px', marginBottom: '1rem',
                                    background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
                                    color: '#ef4444', fontSize: '13px', fontWeight: 500,
                                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                }}>
                                    <span>{formError}</span>
                                    <button type="button" aria-label="Dismiss error" onClick={() => setFormError('')} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontWeight: 700, fontSize: '14px' }}><span aria-hidden="true">&times;</span></button>
                                </div>
                            )}
                            {/* Row 1: Code, Name, Active */}
                            <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr auto', gap: '1.5rem', marginBottom: '1.5rem' }}>
                                <div>
                                    <label style={labelStyle}>Category Code<span className="required-mark"> *</span></label>
                                    <input
                                        type="text" required maxLength={20}
                                        value={formData.code}
                                        onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                                        placeholder="e.g. VEH"
                                        className="glass-input"
                                        style={{ width: '100%', fontFamily: 'monospace', fontSize: 'var(--text-base)', borderWidth: '2px' }}
                                    />
                                </div>
                                <div>
                                    <label style={labelStyle}>Category Name<span className="required-mark"> *</span></label>
                                    <input
                                        type="text" required
                                        value={formData.name}
                                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
placeholder="e.g. Motor Vehicles"
                                        className="glass-input"
                                        style={{ width: '100%', fontSize: 'var(--text-base)', borderWidth: '2px' }}
                                    />
                                </div>
                                <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: '12px' }}>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', userSelect: 'none' }}>
                                        <div style={{
                                            width: '24px', height: '24px', borderRadius: '6px',
                                            border: '2px solid var(--primary)',
                                            background: formData.is_active ? 'var(--primary)' : 'transparent',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            transition: 'all 0.2s',
                                        }}>
                                            {formData.is_active && <Check size={16} color="white" strokeWidth={3} />}
                                            <input
                                                type="checkbox"
                                                checked={formData.is_active}
                                                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                                                style={{ position: 'absolute', opacity: 0, cursor: 'pointer' }}
                                            />
                                        </div>
                                        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>Active</span>
                                    </label>
                                </div>
                            </div>

                            {/* Row 2: GL Account Assignments */}
                            <div style={{ marginBottom: '1.5rem' }}>
                                <h3 style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '1rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                                    GL Account Assignments
                                </h3>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1.5rem' }}>
                                    <div>
                                        <label style={labelStyle}>Cost Account (Asset Recon)</label>
                                        <select
                                            value={formData.cost_account}
                                            onChange={(e) => setFormData({ ...formData, cost_account: e.target.value ? Number(e.target.value) : '' })}
className="glass-input"
                                            style={{ width: '100%', fontSize: 'var(--text-sm)', borderWidth: '2px' }}
                                        >
                                            <option value="">-- Select Cost GL --</option>
                                            {(assetAccounts || []).map((acc) => (
                                                <option key={acc.id} value={acc.id}>{acc.code} — {acc.name}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Accum. Depreciation Account</label>
                                        <select
                                            value={formData.accumulated_depreciation_account}
                                            onChange={(e) => setFormData({ ...formData, accumulated_depreciation_account: e.target.value ? Number(e.target.value) : '' })}
className="glass-input"
                                            style={{ width: '100%', fontSize: 'var(--text-sm)', borderWidth: '2px' }}
                                        >
                                            <option value="">-- Select Accum. Depr. GL --</option>
                                            {(assetAccounts || []).map((acc) => (
                                                <option key={acc.id} value={acc.id}>{acc.code} — {acc.name}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Depreciation Expense Account</label>
                                        <select
                                            value={formData.depreciation_expense_account}
                                            onChange={(e) => setFormData({ ...formData, depreciation_expense_account: e.target.value ? Number(e.target.value) : '' })}
className="glass-input"
                                            style={{ width: '100%', fontSize: 'var(--text-sm)', borderWidth: '2px' }}
                                        >
                                            <option value="">-- Select Expense GL --</option>
                                            {(expenseAccounts || []).map((acc) => (
                                                <option key={acc.id} value={acc.id}>{acc.code} — {acc.name}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>
                            </div>

                            {/* Row 3: Depreciation & Residual Value */}
                            <div style={{ marginBottom: '2rem' }}>
                                <h3 style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '1rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                                    Depreciation Configuration
                                </h3>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px 160px 180px', gap: '1.5rem' }}>
                                    <div>
                                        <label style={labelStyle}>Depreciation Method<span className="required-mark"> *</span></label>
                                        <select
                                            value={formData.depreciation_method}
                                            onChange={(e) => setFormData({ ...formData, depreciation_method: e.target.value })}
                                            required
className="glass-input"
                                            style={{ width: '100%', fontSize: 'var(--text-sm)', borderWidth: '2px' }}
                                        >
                                            {DEPRECIATION_METHODS.map((m) => (
                                                <option key={m.value} value={m.value}>{m.label}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Useful Life<span className="required-mark"> *</span></label>
                                        <div style={{ position: 'relative' }}>
                                            <input
                                                type="number" required min={1} max={100}
                                                value={formData.default_life_years}
                                                onChange={(e) => setFormData({ ...formData, default_life_years: parseInt(e.target.value) || 1 })}
className="glass-input"
                                                style={{ width: '100%', fontSize: 'var(--text-base)', paddingRight: '3rem', borderWidth: '2px' }}
                                            />
                                            <span style={{
                                                position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)',
                                                fontSize: 'var(--text-xs)', color: 'var(--text-muted)', fontWeight: 600,
                                            }}>years</span>
                                        </div>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Residual Value Type</label>
                                        <select
                                            value={formData.residual_value_type}
                                            onChange={(e) => setFormData({ ...formData, residual_value_type: e.target.value })}
className="glass-input"
                                            style={{ width: '100%', fontSize: 'var(--text-sm)', borderWidth: '2px' }}
                                        >
                                            <option value="percentage">Percentage (%)</option>
                                            <option value="amount">Fixed Amount</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>
                                            Residual Value {formData.residual_value_type === 'percentage' ? '(%)' : '(Amount)'}
                                        </label>
                                        <div style={{ position: 'relative' }}>
                                            {formData.residual_value_type === 'amount' && (
                                                <span style={{
                                                    position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)',
                                                    fontSize: 'var(--text-sm)', color: 'var(--text-muted)', fontWeight: 600,
                                                }}>{currencySymbol}</span>
                                            )}
                                            <input
                                                type="number" step="0.01" min="0"
                                                max={formData.residual_value_type === 'percentage' ? 100 : undefined}
                                                value={formData.residual_value}
                                                onChange={(e) => setFormData({ ...formData, residual_value: e.target.value })}
className="glass-input"
                                                style={{
                                                    width: '100%', fontSize: 'var(--text-base)', borderWidth: '2px',
                                                    paddingLeft: formData.residual_value_type === 'amount' ? '1.75rem' : undefined,
                                                    paddingRight: formData.residual_value_type === 'percentage' ? '2rem' : undefined,
                                                }}
                                            />
                                            {formData.residual_value_type === 'percentage' && (
                                                <span style={{
                                                    position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)',
                                                    fontSize: 'var(--text-sm)', color: 'var(--text-muted)', fontWeight: 600,
                                                }}>%</span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Action Buttons */}
                            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
                                <button className="btn-glass" onClick={() => { setShowForm(false); resetForm(); }} type="button" style={{ minWidth: '120px' }}>
                                    Discard
                                </button>
                                <button
                                    className="btn-primary ripple" type="submit"
                                    disabled={createCategory.isPending || updateCategory.isPending}
                                    style={{ minWidth: '160px' }}
                                >
                                    {createCategory.isPending || updateCategory.isPending
                                        ? 'Processing...'
                                        : (editingCategory ? 'Save Changes' : 'Create Category')}
                                </button>
                            </div>
                        </form>
                    </GlassCard>
                </div>
            )}

            {/* Search Bar */}
            <GlassCard style={{ padding: '1.25rem', marginBottom: '1.5rem' }} className="animate-fade-in">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', background: 'rgba(255,255,255,0.05)', borderRadius: '10px', padding: '0 1rem' }}>
                    <Search size={20} style={{ color: 'var(--text-muted)' }} />
                    <input
                        type="text"
                        placeholder="Filter by code or name..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        style={{
                            flex: 1, border: 'none', background: 'transparent',
                            padding: '0.75rem 0', color: 'var(--text-primary)',
                            fontWeight: 500, outline: 'none',
                        }}
                    />
                </div>
            </GlassCard>

            {/* Categories Table */}
            <GlassCard style={{ padding: 0 }} className="animate-fade-in">
                <table className="glass-table" style={{ width: '100%' }}>
                    <thead>
                        <tr>
                            <th style={{ width: '8%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestSort('code')}>
                                <div style={{ display: 'flex', alignItems: 'center' }}>Code {getSortIndicator('code')}</div>
                            </th>
                            <th style={{ width: '14%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestSort('name')}>
                                <div style={{ display: 'flex', alignItems: 'center' }}>Name {getSortIndicator('name')}</div>
                            </th>
                            <th style={{ width: '13%' }}>Cost GL</th>
                            <th style={{ width: '13%' }}>Accum. Depr. GL</th>
                            <th style={{ width: '13%' }}>Expense GL</th>
                            <th style={{ width: '12%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestSort('depreciation_method')}>
                                <div style={{ display: 'flex', alignItems: 'center' }}>Method {getSortIndicator('depreciation_method')}</div>
                            </th>
                            <th style={{ width: '7%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestSort('default_life_years')}>
                                <div style={{ display: 'flex', alignItems: 'center' }}>Life {getSortIndicator('default_life_years')}</div>
                            </th>
                            <th style={{ width: '8%' }}>Residual</th>
                            <th style={{ width: '6%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestSort('is_active')}>
                                <div style={{ display: 'flex', alignItems: 'center' }}>Status {getSortIndicator('is_active')}</div>
                            </th>
                            <th style={{ width: '6%', textAlign: 'center' }}>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {paginatedCategories.map((cat: AssetCategory, index: number) => (
                            <tr key={cat.id} className="stagger-item" style={{ animationDelay: `${index * 0.03}s` }}>
                                <td style={{ fontWeight: 700, color: 'var(--primary)', fontFamily: 'monospace', letterSpacing: '0.05em' }}>
                                    {cat.code}
                                </td>
                                <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{cat.name}</td>
                                <td style={{ fontSize: 'var(--text-sm)' }}>
                                    {cat.cost_account_display
                                        ? <span title={cat.cost_account_display.name}>{cat.cost_account_display.code}</span>
                                        : <span style={{ color: 'var(--text-muted)' }}>--</span>}
                                </td>
                                <td style={{ fontSize: 'var(--text-sm)' }}>
                                    {cat.accumulated_depreciation_account_display
                                        ? <span title={cat.accumulated_depreciation_account_display.name}>{cat.accumulated_depreciation_account_display.code}</span>
                                        : <span style={{ color: 'var(--text-muted)' }}>--</span>}
                                </td>
                                <td style={{ fontSize: 'var(--text-sm)' }}>
                                    {cat.depreciation_expense_account_display
                                        ? <span title={cat.depreciation_expense_account_display.name}>{cat.depreciation_expense_account_display.code}</span>
                                        : <span style={{ color: 'var(--text-muted)' }}>--</span>}
                                </td>
                                <td>
                                    <span className="badge-glass" style={{ fontSize: 'var(--text-xs)' }}>
                                        {cat.depreciation_method_display}
                                    </span>
                                </td>
                                <td style={{ fontWeight: 600, textAlign: 'center' }}>{cat.default_life_years}y</td>
                                <td style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                                    {parseFloat(cat.residual_value) > 0
                                        ? (cat.residual_value_type === 'percentage'
                                            ? `${parseFloat(cat.residual_value)}%`
                                            : formatCurrency(parseFloat(cat.residual_value)))
                                        : <span style={{ color: 'var(--text-muted)' }}>0</span>}
                                </td>
                                <td>
                                    <StatusBadge status={cat.is_active ? 'Active' : 'Inactive'} />
                                </td>
                                <td>
                                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
                                        <button onClick={() => handleEdit(cat)} className="btn-glass" style={{ padding: '6px 10px' }} title="Edit">
                                            <Edit size={14} color="var(--primary)" />
                                        </button>
                                        <button onClick={() => handleDelete(cat.id, cat.name)} className="btn-glass" style={{ padding: '6px 10px' }} title="Delete">
                                            <Trash2 size={14} color="#ef4444" />
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>

                {sortedCategories.length === 0 && (
                    <div style={{ textAlign: 'center', padding: '6rem 2rem', color: 'var(--text-muted)' }}>
                        <div style={{
                            width: '80px', height: '80px',
                            background: 'rgba(36, 113, 163, 0.05)', borderRadius: '50%',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            margin: '0 auto 1.5rem',
                        }}>
                            <FolderTree size={40} style={{ opacity: 0.5 }} />
                        </div>
                        <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                            No asset categories yet
                        </h3>
                        <p style={{ fontSize: 'var(--text-sm)' }}>
                            {searchTerm
                                ? 'No categories match your search.'
                                : 'Create your first asset category to define GL assignments and depreciation rules.'}
                        </p>
                    </div>
                )}

                {/* Pagination footer — visible whenever the result set spans
                    more than one page. Mirrors the COA list layout: range
                    summary on the left, page-size selector + prev/next on
                    the right. */}
                {totalCount > 0 && (
                    <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '1rem 1.25rem',
                        borderTop: '1px solid var(--color-border)',
                        flexWrap: 'wrap',
                        gap: '1rem',
                    }}>
                        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                            Showing <strong>{Math.min(pageStart + 1, totalCount)}</strong>
                            {' '}–{' '}
                            <strong>{Math.min(pageEnd, totalCount)}</strong>
                            {' '}of <strong>{totalCount}</strong> categor{totalCount === 1 ? 'y' : 'ies'}
                            {searchTerm && <span style={{ marginLeft: '0.4rem', color: 'var(--text-muted)' }}>(filtered)</span>}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <label style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                                Rows:
                                <select
                                    value={pageSize}
                                    onChange={(e) => setPageSize(Number(e.target.value))}
                                    style={{
                                        marginLeft: '0.5rem',
                                        padding: '0.3rem 0.5rem',
                                        borderRadius: '6px',
                                        border: '1px solid var(--color-border)',
                                        background: 'var(--color-surface)',
                                        color: 'var(--text-primary)',
                                        fontSize: 'var(--text-sm)',
                                        cursor: 'pointer',
                                    }}
                                >
                                    <option value={10}>10</option>
                                    <option value={20}>20</option>
                                    <option value={50}>50</option>
                                    <option value={100}>100</option>
                                </select>
                            </label>
                            <button
                                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                                disabled={safePage <= 1}
                                style={{
                                    display: 'inline-flex', alignItems: 'center',
                                    padding: '0.4rem 0.7rem',
                                    background: 'var(--color-surface)',
                                    color: safePage <= 1 ? 'var(--text-muted)' : 'var(--text-primary)',
                                    border: '1px solid var(--color-border)',
                                    borderRadius: '6px',
                                    fontSize: 'var(--text-sm)',
                                    fontWeight: 600,
                                    cursor: safePage <= 1 ? 'not-allowed' : 'pointer',
                                    opacity: safePage <= 1 ? 0.5 : 1,
                                }}
                            >
                                <ChevronLeft size={16} style={{ marginRight: '4px' }} /> Previous
                            </button>
                            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', minWidth: '90px', textAlign: 'center' }}>
                                Page <strong>{safePage}</strong> of <strong>{totalPages}</strong>
                            </span>
                            <button
                                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                                disabled={safePage >= totalPages}
                                style={{
                                    display: 'inline-flex', alignItems: 'center',
                                    padding: '0.4rem 0.7rem',
                                    background: 'var(--color-surface)',
                                    color: safePage >= totalPages ? 'var(--text-muted)' : 'var(--text-primary)',
                                    border: '1px solid var(--color-border)',
                                    borderRadius: '6px',
                                    fontSize: 'var(--text-sm)',
                                    fontWeight: 600,
                                    cursor: safePage >= totalPages ? 'not-allowed' : 'pointer',
                                    opacity: safePage >= totalPages ? 0.5 : 1,
                                }}
                            >
                                Next <ChevronRight size={16} style={{ marginLeft: '4px' }} />
                            </button>
                        </div>
                    </div>
                )}
            </GlassCard>
        </AccountingLayout>
    );
}
