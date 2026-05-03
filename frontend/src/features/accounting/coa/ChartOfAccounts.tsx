import { useState, useEffect, useRef, useMemo } from 'react';
import { List, Plus, Download, Edit, Trash2, Filter, Search, X, Check, ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Upload, FileDown, Copy, BookOpen } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import { useDebounce } from '../../../hooks/useDebounce';
import StatusBadge from '../components/shared/StatusBadge';
import GlassCard from '../components/shared/GlassCard';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useDialog } from '../../../hooks/useDialog';
import '../styles/glassmorphism.css';

const API_URL = '/accounting/accounts/';

interface Account {
    id: number;
    code: string;
    name: string;
    account_type: string;
    is_active: boolean;
    is_reconciliation: boolean;
    reconciliation_type: string;
    reconciliation_type_display: string;
    current_balance: string;
    // Asset auto-capitalisation linkage. When set, posting-time interception
    // creates a FixedAsset, clears this GL to zero (contra credit), and debits
    // the category's cost_account (asset recon GL).
    auto_create_asset?: boolean;
    asset_category?: number | null;
    asset_category_code?: string;
    asset_category_name?: string;
}

interface AssetCategoryOption {
    id: number;
    code: string;
    name: string;
    cost_account_display?: { id: number; code: string; name: string } | null;
}

type SortKey = 'code' | 'name' | 'account_type' | 'is_active' | 'is_reconciliation';

export default function ChartOfAccounts() {
    const { showAlert, showConfirm } = useDialog();
    const queryClient = useQueryClient();
    const formRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [showForm, setShowForm] = useState(false);
    const [importResult, setImportResult] = useState<{
        success: boolean;
        created: number;
        skipped: number;
        errors: string[];
    } | null>(null);
    const [isImporting, setIsImporting] = useState(false);
    const [editingAccount, setEditingAccount] = useState<Account | null>(null);
    const [typeFilter, setTypeFilter] = useState('');
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
    const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: 'asc' | 'desc' } | null>(null);
    const [currentPage, setCurrentPage] = useState(1);
    const [pageSize, setPageSize] = useState(20);

    // GL Ledger drill-down
    const [ledgerAccount, setLedgerAccount] = useState<Account | null>(null);
    const today = new Date().toISOString().split('T')[0];
    // Default the From-date to the start of the fiscal year (1 January
    // of the current civil year) — that's the "show me everything in
    // this account YTD" question the user almost always wants. The
    // previous "first of month" default produced empty ledgers when
    // the user clicked through from the CoA list and the entries
    // pre-dated the current month, even though the closing balance
    // showed a non-zero figure (true cumulative balance).
    const startOfFY = new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0];
    const [ledgerStartDate, setLedgerStartDate] = useState(startOfFY);
    const [ledgerEndDate, setLedgerEndDate] = useState(today);
    const [ledgerData, setLedgerData] = useState<any>(null);

    const [formData, setFormData] = useState({
        code: '',
        name: '',
        account_type: 'Asset',
        is_active: true,
        is_reconciliation: false,
        reconciliation_type: '',
        // Phase 1 — asset auto-capitalisation. Off by default so behaviour
        // for existing accounts is unchanged. Tenants opt in per account
        // (typically on the 23xxxxxx capex series, but not restricted).
        auto_create_asset: false,
        asset_category: null as number | null,
    });

    // Asset categories for the dropdown that appears when
    // "Auto-create asset on debit" is toggled ON. Note the queryKey prefix
    // matches the AssetCategories page's invalidation surface
    // (``['asset-categories', …]``) so any CRUD on a category invalidates
    // this cache via ``invalidateQueries({ queryKey: ['asset-categories'] })``
    // without each mutation having to know about every consumer.
    // staleTime is short (30s) so even outside-app changes (an admin running
    // a seed script, an importer running on another tab) surface within a
    // window the user notices.
    const {
        data: assetCategories = [],
        refetch: refetchAssetCategories,
    } = useQuery<AssetCategoryOption[]>({
        queryKey: ['asset-categories', { dropdown: 'options' }],
        queryFn: async () => {
            const res = await apiClient.get('/accounting/asset-categories/', {
                params: { is_active: true, page_size: 999 },
            });
            const d = res.data;
            return Array.isArray(d) ? d : (d.results || []);
        },
        staleTime: 30 * 1000,
        refetchOnWindowFocus: true,
    });

    // Auto-scroll to top when editing starts
    useEffect(() => {
        if (editingAccount) {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    }, [editingAccount]);

    // Reset to page 1 when filters change
    useEffect(() => {
        setCurrentPage(1);
    }, [typeFilter, searchTerm]);

    // Fetch accounting settings (digit enforcement only — series is
    // hard-coded per Nigeria CoA standards and no longer read from DB)
    const { data: acctSettings } = useQuery<{
        account_code_digits: number;
        is_digit_enforcement_active: boolean;
    }>({
        queryKey: ['accounting-settings'],
        queryFn: async () => {
            const res = await apiClient.get('/accounting/settings/');
            return res.data;
        },
        staleTime: 5 * 60 * 1000,
    });

    const digitEnforcement = acctSettings?.is_digit_enforcement_active ?? false;
    const requiredDigits = acctSettings?.account_code_digits ?? 8;

    // ── Nigeria Chart of Accounts series mapping ──────────────────
    // Hard-coded to match the backend's serializer validation in
    // ``AccountSerializer.NIGERIA_COA_SERIES``. Tenants cannot
    // customise these — the rule is mandated by Nigerian CoA compliance.
    //
    //   1xxxxxxx → Revenue (stored internally as "Income")
    //   2xxxxxxx → Expense
    //   3xxxxxxx → Asset
    //   4xxxxxxx → Liability
    //
    // Equity has no enforced prefix — user can pick any unused range.
    const NIGERIA_COA_SERIES: Record<string, string> = {
        '1': 'Income',
        '2': 'Expense',
        '3': 'Asset',
        '4': 'Liability',
    };

    /**
     * Nigeria-CoA series check: the FIRST digit of the account code
     * determines the expected account_type. Returns null if the first
     * digit is outside the 1-4 mandated range (which is legal for
     * Equity accounts and for any legacy codes the tenant may have).
     */
    const expectedTypeForCode = (code: string): string | null => {
        if (!code) return null;
        return NIGERIA_COA_SERIES[code[0]] ?? null;
    };

    /** Label-swap helper: internal "Income" → user-facing "Revenue". */
    const displayType = (t: string): string => (t === 'Income' ? 'Revenue' : t);

    // Debounce search term to avoid excessive API calls
    const debouncedSearchTerm = useDebounce(searchTerm, 300);

    // Fetch accounts
    const { data: accountsData, isLoading, isError, error } = useQuery({
        queryKey: ['accounts', typeFilter, currentPage, pageSize, debouncedSearchTerm],
        queryFn: async () => {
            const params: Record<string, any> = { page: currentPage, page_size: pageSize };
            if (typeFilter) params.account_type = typeFilter;
            if (debouncedSearchTerm) params.search = debouncedSearchTerm;
            const response = await apiClient.get(API_URL, { params });
            return { results: response.data.results, count: response.data.count };
        },
        staleTime: 5 * 60 * 1000, // 5 minutes
    });

    const accounts = accountsData?.results;
    const totalCount = accountsData?.count ?? 0;
    const totalPages = Math.ceil(totalCount / pageSize);

    // Extract a human-readable error message from a DRF 400 response.
    // DRF returns `{fieldName: ["msg", ...]}` for serializer.ValidationError,
    // or `{detail: "..."}` / `{error: "..."}` for view-level errors.
    // We flatten everything into a single string for the alert banner.
    const extractBackendError = (err: any, fallback: string): string => {
        const d = err?.response?.data;
        if (!d) return err?.message || fallback;
        if (typeof d === 'string') return d;
        if (d.detail) return String(d.detail);
        if (d.error) return String(d.error);
        // Field-level errors: flatten arrays + join
        const parts: string[] = [];
        for (const [field, value] of Object.entries(d)) {
            const msg = Array.isArray(value) ? value.join(' ') : String(value);
            parts.push(field === 'non_field_errors' ? msg : `${field}: ${msg}`);
        }
        return parts.length > 0 ? parts.join(' | ') : fallback;
    };

    // Create account
    const createAccount = useMutation({
        mutationFn: (data: any) => apiClient.post(API_URL, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['accounts'] });
            setShowForm(false);
            resetForm();
            showAlert('Account created successfully.', 'success');
        },
        onError: (err: any) => {
            // Backend returned 400 — surface the actual validation message
            // (number-series mismatch, digit enforcement, duplicate code, etc.)
            showAlert(extractBackendError(err, 'Failed to create account.'), 'error');
        },
    });

    // Update account
    const updateAccount = useMutation({
        mutationFn: ({ id, data }: { id: number; data: any }) =>
            apiClient.put(`${API_URL}${id}/`, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['accounts'] });
            setShowForm(false);
            setEditingAccount(null);
            resetForm();
            showAlert('Account updated successfully.', 'success');
        },
        onError: (err: any) => {
            showAlert(extractBackendError(err, 'Failed to update account.'), 'error');
        },
    });

    // Delete account
    const deleteAccount = useMutation({
        mutationFn: (id: number) => apiClient.delete(`${API_URL}${id}/`),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['accounts'] });
            showAlert('Account deleted successfully.', 'success');
        },
        onError: (err: any) => {
            const msg = err.response?.data?.detail || err.response?.data?.error || 'Failed to delete account. It may have journal entries.';
            showAlert(msg, 'error');
        },
    });

    // Bulk delete mutation (single batch request)
    const bulkDeleteAccounts = useMutation({
        mutationFn: async (ids: number[]) => {
            return apiClient.post(`${API_URL}bulk-delete/`, { ids });
        },
        onSuccess: (res) => {
            queryClient.invalidateQueries({ queryKey: ['accounts'] });
            setSelectedIds(new Set());
            const count = res.data?.deleted ?? selectedIds.size;
            showAlert(`${count} account(s) deleted successfully.`, 'success');
        },
        onError: (err: any) => {
            const msg = err.response?.data?.error || 'Failed to delete selected accounts. Some may have journal entries.';
            showAlert(msg, 'error');
        },
    });

    // Bulk reconcile — flips ``is_reconciliation`` + ``reconciliation_type``
    // on every selected Asset/Liability account in a single request. Other
    // account types are silently skipped server-side; we surface the count.
    const [reconModalOpen, setReconModalOpen] = useState(false);
    const [reconType, setReconType] = useState('');
    const bulkReconcileAccounts = useMutation({
        mutationFn: async ({ ids, reconciliation_type }: { ids: number[]; reconciliation_type: string }) => {
            return apiClient.post(`${API_URL}bulk-reconcile/`, { ids, reconciliation_type });
        },
        onSuccess: (res) => {
            queryClient.invalidateQueries({ queryKey: ['accounts'] });
            setSelectedIds(new Set());
            setReconModalOpen(false);
            setReconType('');
            const updated = res.data?.updated ?? 0;
            const skipped = res.data?.skipped_count ?? 0;
            const msg = skipped > 0
                ? `${updated} account(s) updated. ${skipped} skipped (only Asset / Liability accounts can be reconciliation).`
                : `${updated} account(s) updated.`;
            showAlert(msg, skipped > 0 ? 'warning' : 'success');
        },
        onError: (err: any) => {
            const msg = err.response?.data?.error || 'Failed to update reconciliation flag.';
            showAlert(msg, 'error');
        },
    });

    // Bulk set asset auto-capitalisation — flips ``auto_create_asset`` +
    // ``asset_category`` on every selected account. The picked category's
    // cost_account must exist (validated server-side) so posting-time
    // interception has a recon GL to debit.
    const [autoAssetModalOpen, setAutoAssetModalOpen] = useState(false);
    const [autoAssetCategoryId, setAutoAssetCategoryId] = useState<number | null>(null);
    const bulkSetAutoAsset = useMutation({
        mutationFn: async ({ ids, asset_category_id }: { ids: number[]; asset_category_id: number | null }) => {
            return apiClient.post(`${API_URL}bulk-set-auto-asset/`, { ids, asset_category_id });
        },
        onSuccess: (res) => {
            queryClient.invalidateQueries({ queryKey: ['accounts'] });
            setSelectedIds(new Set());
            setAutoAssetModalOpen(false);
            setAutoAssetCategoryId(null);
            const updated = res.data?.updated ?? 0;
            showAlert(res.data?.status || `${updated} account(s) updated.`, 'success');
        },
        onError: (err: any) => {
            const msg = err.response?.data?.error || 'Failed to update asset auto-capitalisation flag.';
            showAlert(msg, 'error');
        },
    });

    // GL Ledger fetch
    const fetchLedger = useMutation({
        mutationFn: async ({ accountCode, startDate, endDate }: { accountCode: string; startDate: string; endDate: string }) => {
            const { data } = await apiClient.post('/accounting/reports/general-ledger/', {
                account_code: accountCode,
                start_date: startDate,
                end_date: endDate,
            });
            return data;
        },
        onSuccess: (data) => {
            setLedgerData(data);
        },
        onError: () => {
            setLedgerData(null);
        },
    });

    const handleOpenLedger = (account: Account) => {
        setLedgerAccount(account);
        setLedgerData(null);
        fetchLedger.mutate({ accountCode: account.code, startDate: ledgerStartDate, endDate: ledgerEndDate });
    };

    const handleLedgerDateChange = (start: string, end: string) => {
        setLedgerStartDate(start);
        setLedgerEndDate(end);
        if (ledgerAccount) {
            fetchLedger.mutate({ accountCode: ledgerAccount.code, startDate: start, endDate: end });
        }
    };

    const sortedAccounts = useMemo(() => {
        let filtered = (Array.isArray(accounts) ? accounts : []).filter((acc: Account) => {
            return acc.code.toLowerCase().includes(searchTerm.toLowerCase()) ||
                acc.name.toLowerCase().includes(searchTerm.toLowerCase());
        }) || [];

        if (sortConfig !== null) {
            filtered.sort((a, b) => {
                const aValue = a[sortConfig.key];
                const bValue = b[sortConfig.key];

                if (aValue < bValue) {
                    return sortConfig.direction === 'asc' ? -1 : 1;
                }
                if (aValue > bValue) {
                    return sortConfig.direction === 'asc' ? 1 : -1;
                }
                return 0;
            });
        }
        return filtered;
    }, [accounts, searchTerm, sortConfig]);

    if (isError) {
        return (
            <AccountingLayout>
                <div style={{ padding: '2rem', textAlign: 'center', color: 'red' }}>
                    <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 600, marginBottom: '1rem' }}>Error loading Chart of Accounts</h2>
                    <p style={{ marginBottom: '1.5rem' }}>{(error as any)?.message || 'Unknown error occurred'}</p>
                    <button className="btn btn-primary" onClick={() => window.location.reload()}>Retry</button>
                </div>
            </AccountingLayout>
        );
    }

    if (isLoading) {
        return <LoadingScreen message="Loading chart of accounts..." />;
    }

    const resetForm = () => {
        setFormData({ code: '', name: '', account_type: 'Asset', is_active: true, is_reconciliation: false, reconciliation_type: '', auto_create_asset: false, asset_category: null });
        setEditingAccount(null);
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        // Digit enforcement validation
        if (digitEnforcement && formData.code.length !== requiredDigits) {
            showAlert(`Account code must be exactly ${requiredDigits} digits when digit enforcement is active.`, 'warning');
            return;
        }
        if (editingAccount) {
            updateAccount.mutate({ id: editingAccount.id, data: formData });
        } else {
            createAccount.mutate(formData);
        }
    };

    const handleCopy = (account: Account) => {
        // Find the next available code for this account type
        const sameTypeAccounts = (Array.isArray(accounts) ? accounts : [])
            .filter((acc: Account) => acc.account_type === account.account_type)
            .map((acc: Account) => acc.code)
            .sort();

        let nextCode = account.code;
        if (digitEnforcement) {
            // Parse the numeric code and increment by 1
            const numericCode = parseInt(account.code, 10);
            if (!isNaN(numericCode)) {
                let candidate = numericCode + 1;
                const existingCodes = new Set(sameTypeAccounts);
                while (existingCodes.has(String(candidate).padStart(requiredDigits, '0'))) {
                    candidate++;
                }
                nextCode = String(candidate).padStart(requiredDigits, '0');
            }
        } else {
            // Try incrementing the trailing number portion
            const match = account.code.match(/^(.*?)(\d+)$/);
            if (match) {
                const prefix = match[1];
                const num = parseInt(match[2], 10);
                const numLen = match[2].length;
                const existingCodes = new Set(sameTypeAccounts);
                let candidate = num + 1;
                while (existingCodes.has(prefix + String(candidate).padStart(numLen, '0'))) {
                    candidate++;
                }
                nextCode = prefix + String(candidate).padStart(numLen, '0');
            }
        }

        setFormData({
            code: nextCode,
            name: account.name,
            account_type: account.account_type,
            is_active: account.is_active,
            is_reconciliation: account.is_reconciliation,
            reconciliation_type: account.reconciliation_type,
            auto_create_asset: account.auto_create_asset ?? false,
            asset_category: account.asset_category ?? null,
        });
        setEditingAccount(null);
        setShowForm(true);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const handleEdit = (account: Account) => {
        setEditingAccount(account);
        setFormData({
            code: account.code,
            name: account.name,
            account_type: account.account_type,
            is_active: account.is_active,
            is_reconciliation: account.is_reconciliation,
            reconciliation_type: account.reconciliation_type,
            auto_create_asset: account.auto_create_asset ?? false,
            asset_category: account.asset_category ?? null,
        });
        // Refresh the asset-category dropdown when entering edit mode so the
        // user always sees the current set of categories regardless of cache age.
        refetchAssetCategories();
        setShowForm(true);
    };

    const handleDelete = async (id: number, name: string) => {
        if (await showConfirm(`Delete account "${name}"? This action cannot be undone.`)) {
            deleteAccount.mutate(id);
            if (selectedIds.has(id)) {
                const next = new Set(selectedIds);
                next.delete(id);
                setSelectedIds(next);
            }
        }
    };

    const handleBulkDelete = async () => {
        if (selectedIds.size === 0) return;
        if (await showConfirm(`Delete ${selectedIds.size} selected accounts? This action cannot be undone.`)) {
            bulkDeleteAccounts.mutate(Array.from(selectedIds));
        }
    };

    const handleExport = () => {
        // CSV-with-UTF-8-BOM is the canonical "open cleanly in Excel"
        // format. The leading BOM (﻿) tells Excel the file is
        // UTF-8 — without it, Excel guesses Windows-1252 and renders
        // ₦ / accented characters as mojibake. ``application/vnd.ms-excel``
        // mime type with a ``.csv`` extension makes Windows associate
        // the download with Excel by default while still being a
        // plain text file other tools can open.
        const escapeCsvCell = (cell: unknown): string => {
            const str = String(cell ?? '');
            return str.includes(',') || str.includes('"') || str.includes('\n')
                ? `"${str.replace(/"/g, '""')}"` : str;
        };

        const fmtAmount = (v: unknown): string => {
            const n = parseFloat(String(v ?? '0'));
            return Number.isFinite(n) ? n.toFixed(2) : '0.00';
        };

        // Header row now includes the balance — that's the column
        // the operator actually needs in Excel for variance and trial
        // balance work. Adding it doesn't break existing import flows
        // because the import template ignores unknown columns.
        const csv = [
            ['Code', 'Name', 'Type', 'Active', 'Is Reconciliation', 'Reconciliation Type', 'Current Balance'],
            ...(Array.isArray(accounts) ? accounts : []).map((acc: Account) => [
                acc.code,
                acc.name,
                acc.account_type,
                acc.is_active ? 'Yes' : 'No',
                acc.is_reconciliation ? 'true' : 'false',
                acc.reconciliation_type || '',
                fmtAmount(acc.current_balance),
            ])
        ].map(row => row.map(escapeCsvCell).join(',')).join('\n');

        // ﻿ = UTF-8 BOM. Required for Excel to detect UTF-8.
        const blob = new Blob(['﻿' + csv], { type: 'application/vnd.ms-excel;charset=utf-8' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        // Stamped filename so multiple exports in the same day don't
        // overwrite each other in the operator's Downloads folder.
        const stamp = new Date().toISOString().slice(0, 10);
        a.download = `gl_balances_${stamp}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
    };

    /**
     * Download the COA import template from the BACKEND, not from a
     * hardcoded array in this file. This keeps the template as a single
     * source of truth — the backend serves the NCoA-aligned content
     * (1xxxxxxx Income, 2xxxxxxx Expense, 3xxxxxxx Asset, 4xxxxxxx
     * Liability/Equity) plus a leading `#` help block. Same pattern
     * the NCoA dimension pages already use via downloadNCoATemplate().
     */
    const handleDownloadTemplate = async () => {
        try {
            const res = await apiClient.get(`${API_URL}import-template/`, {
                responseType: 'blob',
            });
            const blob = new Blob([res.data], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'account_import_template.csv';
            a.click();
            window.URL.revokeObjectURL(url);
        } catch (err) {
            // Surface a friendly message if the backend is unreachable; the
            // user can retry without the page going blank.
            // eslint-disable-next-line no-console
            console.error('Failed to download account template:', err);
            alert('Could not download the template. Please check your connection and try again.');
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

            // Override the global ``Content-Type: application/json`` baked
            // into apiClient — without this, axios JSON-serialises the
            // FormData object (turning it into ``{}``) and the backend's
            // ``request.FILES.get('file')`` returns None, surfacing as
            // "A CSV or Excel file is required." Setting the multipart
            // header explicitly delegates serialization to the browser,
            // which inserts the random boundary the multipart parser needs.
            // This mirrors the pattern in hooks/useNCoAImportExport.ts.
            const response = await apiClient.post(`${API_URL}bulk-import/`, formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });

            setImportResult(response.data);
            queryClient.invalidateQueries({ queryKey: ['accounts'] });
        } catch (err: any) {
            setImportResult({
                success: false,
                created: 0,
                skipped: 0,
                errors: [err.response?.data?.error || 'Import failed. Please check the file format.'],
            });
        } finally {
            setIsImporting(false);
            if (fileInputRef.current) {
                fileInputRef.current.value = '';
            }
        }
    };

    const requestSort = (key: SortKey) => {
        let direction: 'asc' | 'desc' = 'asc';
        if (sortConfig && sortConfig.key === key && sortConfig.direction === 'asc') {
            direction = 'desc';
        }
        setSortConfig({ key, direction });
    };


    const toggleSelectAll = () => {
        if (selectedIds.size === sortedAccounts.length && sortedAccounts.length > 0) {
            setSelectedIds(new Set());
        } else {
            setSelectedIds(new Set(sortedAccounts.map(acc => acc.id)));
        }
    };

    const toggleSelectOne = (id: number) => {
        const next = new Set(selectedIds);
        if (next.has(id)) {
            next.delete(id);
        } else {
            next.add(id);
        }
        setSelectedIds(next);
    };

    const getSortIndicator = (key: SortKey) => {
        if (!sortConfig || sortConfig.key !== key) return null;
        return sortConfig.direction === 'asc' ? <ChevronUp size={14} style={{ marginLeft: '4px' }} /> : <ChevronDown size={14} style={{ marginLeft: '4px' }} />;
    };


    return (
        <AccountingLayout>
            <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx"
                onChange={handleImport}
                style={{ display: 'none' }}
            />
            <PageHeader
                title="Chart of Accounts"
                subtitle="Design and manage your global financial structure"
                icon={<List size={22} />}
                actions={
                    <div style={{ display: 'flex', gap: '0.85rem', alignItems: 'center', flexWrap: 'wrap' }}>
                        {selectedIds.size > 0 && (
                            <>
                                {/* Solid green fill — high contrast on the dark
                                    page header; semantic colour signals a
                                    constructive bulk action. */}
                                <button
                                    className="animate-scale-in"
                                    style={{
                                        display: 'inline-flex', alignItems: 'center',
                                        padding: '0.55rem 1.1rem',
                                        background: '#16a34a',  // green-600
                                        color: '#ffffff',
                                        border: '1px solid #16a34a',
                                        borderRadius: '8px',
                                        fontSize: 'var(--text-sm)',
                                        fontWeight: 600,
                                        cursor: 'pointer',
                                        boxShadow: '0 2px 6px rgba(22,163,74,0.35)',
                                        transition: 'transform 0.15s, box-shadow 0.15s',
                                    }}
                                    onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#15803d'; }}
                                    onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#16a34a'; }}
                                    onClick={() => { setReconType(''); setReconModalOpen(true); }}
                                    title="Mark selected Asset/Liability accounts as reconciliation accounts"
                                >
                                    <Check size={18} style={{ marginRight: '8px' }} /> Mark Reconciliation ({selectedIds.size})
                                </button>
                                {/* Solid amber/orange fill — distinct from green
                                    (reconciliation) and red (delete). Signals
                                    a configuration change that affects future
                                    journal posting behaviour. */}
                                <button
                                    className="animate-scale-in"
                                    style={{
                                        display: 'inline-flex', alignItems: 'center',
                                        padding: '0.55rem 1.1rem',
                                        background: '#d97706',  // amber-600
                                        color: '#ffffff',
                                        border: '1px solid #d97706',
                                        borderRadius: '8px',
                                        fontSize: 'var(--text-sm)',
                                        fontWeight: 600,
                                        cursor: 'pointer',
                                        boxShadow: '0 2px 6px rgba(217,119,6,0.35)',
                                        transition: 'transform 0.15s, box-shadow 0.15s',
                                    }}
                                    onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#b45309'; }}
                                    onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#d97706'; }}
                                    onClick={() => {
                                        // Belt-and-braces refetch — even if the cache wasn't
                                        // invalidated for any reason, opening this modal pulls
                                        // the freshest list of asset categories so the dropdown
                                        // always reflects current state.
                                        refetchAssetCategories();
                                        setAutoAssetCategoryId(null);
                                        setAutoAssetModalOpen(true);
                                    }}
                                    title="Mark selected GL accounts so that any debit auto-creates a FixedAsset and reroutes the GL debit to the chosen category's cost account"
                                >
                                    <List size={18} style={{ marginRight: '8px' }} /> Auto-Asset on Debit ({selectedIds.size})
                                </button>
                                {/* Solid red fill — high contrast for destructive
                                    bulk action. */}
                                <button
                                    className="animate-scale-in"
                                    style={{
                                        display: 'inline-flex', alignItems: 'center',
                                        padding: '0.55rem 1.1rem',
                                        background: '#dc2626',  // red-600
                                        color: '#ffffff',
                                        border: '1px solid #dc2626',
                                        borderRadius: '8px',
                                        fontSize: 'var(--text-sm)',
                                        fontWeight: 600,
                                        cursor: 'pointer',
                                        boxShadow: '0 2px 6px rgba(220,38,38,0.35)',
                                        transition: 'transform 0.15s, box-shadow 0.15s',
                                    }}
                                    onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#b91c1c'; }}
                                    onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#dc2626'; }}
                                    onClick={handleBulkDelete}
                                >
                                    <Trash2 size={18} style={{ marginRight: '8px' }} /> Delete Selected ({selectedIds.size})
                                </button>
                            </>
                        )}
                        {/* Template / Import / Export — same geometry as the
                            colored bulk-action buttons (padding, border-radius,
                            font-weight, shadow) so the toolbar reads as one
                            coherent row. Color stays neutral white/glass with
                            dark text, hover lifts the surface. */}
                        <button
                            onClick={handleDownloadTemplate}
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
                                if (showForm && !editingAccount) {
                                    setShowForm(false);
                                } else {
                                    // Refetch asset categories so the per-row
                                    // Asset Category dropdown is up-to-date the
                                    // moment the form opens — same defense as
                                    // the bulk-action modal above.
                                    refetchAssetCategories();
                                    resetForm();
                                    setShowForm(true);
                                }
                            }}
                        >
                            {showForm && !editingAccount ? <X size={18} style={{ marginRight: '8px' }} /> : <Plus size={18} style={{ marginRight: '8px' }} />}
                            {showForm && !editingAccount ? 'Close Form' : 'Add Account'}
                        </button>
                    </div>
                }
            />

            {/* Top-aligned Account Form */}
            {showForm && (
                <div ref={formRef} className="animate-slide-down" style={{ marginBottom: '2.5rem' }}>
                    <GlassCard gradient style={{ padding: '2rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                            <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>
                                {editingAccount ? 'Edit Account Details' : 'Register New Ledger Account'}
                            </h2>
                            <button
                                onClick={() => { setShowForm(false); resetForm(); }}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
                            >
                                <X size={20} />
                            </button>
                        </div>

                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
                                <div>
                                    <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        Account Code<span className="required-mark"> *</span> {digitEnforcement && <span style={{ color: '#2471a3', fontWeight: 400, textTransform: 'none' }}>({requiredDigits} digits required)</span>}
                                    </label>
                                    <input
                                        type="text"
                                        maxLength={digitEnforcement ? requiredDigits : 20}
                                        value={formData.code}
                                        onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                                        placeholder={digitEnforcement ? `e.g. ${'1'.padEnd(requiredDigits, '0')}` : 'e.g. 10001001'}
                                        required
                                        className="glass-input"
                                        style={{
                                            width: '100%', fontFamily: 'monospace', fontSize: 'var(--text-base)',
                                            borderColor: digitEnforcement && formData.code.length > 0 && formData.code.length !== requiredDigits ? '#ef4444' : undefined,
                                        }}
                                    />
                                    {digitEnforcement && formData.code.length > 0 && formData.code.length !== requiredDigits && (
                                        <div style={{ fontSize: 'var(--text-xs)', color: '#ef4444', marginTop: '4px' }}>
                                            Code must be exactly {requiredDigits} digits ({formData.code.length}/{requiredDigits})
                                        </div>
                                    )}
                                    {/* Nigeria CoA series hint — shows expected account type
                                        based on the first digit (1=Revenue, 2=Expense, 3=Asset,
                                        4=Liability). Mirrors the backend's hardcoded validation
                                        in AccountSerializer.NIGERIA_COA_SERIES so the user sees
                                        the issue BEFORE clicking Save. */}
                                    {(() => {
                                        if (!formData.code) return null;
                                        const expected = expectedTypeForCode(formData.code);
                                        if (!expected) return null;
                                        const matches = expected === formData.account_type;
                                        const expectedLabel = displayType(expected);
                                        return (
                                            <div style={{
                                                fontSize: 'var(--text-xs)', marginTop: '4px',
                                                color: matches ? '#15803d' : '#b45309',
                                                display: 'flex', alignItems: 'center', gap: '0.3rem',
                                            }}>
                                                {matches
                                                    ? <>✓ Nigeria CoA: prefix <strong>{formData.code[0]}</strong> matches <strong>{expectedLabel}</strong></>
                                                    : (
                                                        <>
                                                            ⚠ Nigeria CoA: prefix <strong>{formData.code[0]}</strong> is reserved for&nbsp;
                                                            <strong>{expectedLabel}</strong>.&nbsp;
                                                            <button
                                                                type="button"
                                                                onClick={() => setFormData({
                                                                    ...formData,
                                                                    account_type: expected,
                                                                    ...(expected !== 'Asset' && expected !== 'Liability'
                                                                        ? { is_reconciliation: false, reconciliation_type: '' }
                                                                        : {}),
                                                                })}
                                                                style={{
                                                                    background: 'none', border: 'none',
                                                                    color: '#2471a3', textDecoration: 'underline',
                                                                    cursor: 'pointer', padding: 0, font: 'inherit',
                                                                }}
                                                            >
                                                                Switch type to {expectedLabel}
                                                            </button>
                                                        </>
                                                    )
                                                }
                                            </div>
                                        );
                                    })()}
                                </div>

                                <div>
                                    <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        Account Name<span className="required-mark"> *</span>
                                    </label>
                                    <input
                                        type="text"
                                        value={formData.name}
                                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                        placeholder="e.g. Petty Cash"
                                        required
                                        className="glass-input"
                                        style={{ width: '100%', fontSize: 'var(--text-base)' }}
                                    />
                                </div>

                                <div>
                                    <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        Category Type<span className="required-mark"> *</span>
                                    </label>
                                    <select
                                        value={formData.account_type}
                                        onChange={(e) => {
                                            const newType = e.target.value;
                                            const isReconAllowed = newType === 'Asset' || newType === 'Liability';
                                            setFormData({
                                                ...formData,
                                                account_type: newType,
                                                ...(!isReconAllowed ? { is_reconciliation: false, reconciliation_type: '' } : {}),
                                            });
                                        }}
                                        required
                                        className="glass-input"
                                        style={{ width: '100%', fontSize: 'var(--text-base)' }}
                                    >
                                        <option value="Asset">Asset</option>
                                        <option value="Liability">Liability</option>
                                        <option value="Equity">Equity</option>
                                        <option value="Income">Income</option>
                                        <option value="Expense">Expense</option>
                                    </select>
                                </div>

                                <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: '12px' }}>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', userSelect: 'none' }}>
                                        <div style={{
                                            width: '24px',
                                            height: '24px',
                                            borderRadius: '6px',
                                            border: '2px solid var(--primary)',
                                            background: formData.is_active ? 'var(--primary)' : 'transparent',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            transition: 'all 0.2s'
                                        }}>
                                            {formData.is_active && <Check size={16} color="white" strokeWidth={3} />}
                                            <input
                                                type="checkbox"
                                                checked={formData.is_active}
                                                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                                                style={{ position: 'absolute', opacity: 0, cursor: 'pointer' }}
                                            />
                                        </div>
                                        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>Account Active</span>
                                    </label>
                                </div>
                            </div>

                            {/* Reconciliation fields — only for Asset/Liability */}
                            {(formData.account_type === 'Asset' || formData.account_type === 'Liability') && (
                                <div style={{ display: 'flex', alignItems: 'center', gap: '2rem', marginBottom: '2rem', flexWrap: 'wrap' }}>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', userSelect: 'none' }}>
                                        <div style={{
                                            width: '24px',
                                            height: '24px',
                                            borderRadius: '6px',
                                            border: '2px solid var(--primary)',
                                            background: formData.is_reconciliation ? 'var(--primary)' : 'transparent',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            transition: 'all 0.2s'
                                        }}>
                                            {formData.is_reconciliation && <Check size={16} color="white" strokeWidth={3} />}
                                            <input
                                                type="checkbox"
                                                checked={formData.is_reconciliation}
                                                onChange={(e) => setFormData({
                                                    ...formData,
                                                    is_reconciliation: e.target.checked,
                                                    ...(!e.target.checked ? { reconciliation_type: '' } : {}),
                                                })}
                                                style={{ position: 'absolute', opacity: 0, cursor: 'pointer' }}
                                            />
                                        </div>
                                        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>Reconciliation Account</span>
                                    </label>

                                    {formData.is_reconciliation && (
                                        <div style={{ minWidth: '220px' }}>
                                            <select
                                                value={formData.reconciliation_type}
                                                onChange={(e) => setFormData({ ...formData, reconciliation_type: e.target.value })}
                                                required
                                                className="glass-input"
                                                style={{ width: '100%', fontSize: 'var(--text-sm)', padding: '0.5rem 1rem' }}
                                            >
                                                <option value="">-- Select Sub-Type --</option>
                                                <option value="accounts_payable">Account Payable</option>
                                                <option value="accounts_receivable">Account Receivable</option>
                                                <option value="inventory">Inventory</option>
                                                <option value="asset_accounting">Asset Accounting</option>
                                                <option value="bank_accounting">Bank Accounting</option>
                                            </select>
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* IPSAS Asset Auto-Capitalisation (Phase 1).
                                Available on every account — tenants opt in per
                                account; no GL-series restriction in code. The
                                category dropdown only renders when the toggle
                                is ON, and submission is blocked if it stays
                                empty (matches the model's clean() rule). */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: '2rem', marginBottom: '2rem', flexWrap: 'wrap' }}>
                                <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', userSelect: 'none' }}>
                                    <div style={{
                                        width: '24px', height: '24px', borderRadius: '6px',
                                        border: '2px solid var(--primary)',
                                        background: formData.auto_create_asset ? 'var(--primary)' : 'transparent',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        transition: 'all 0.2s', position: 'relative',
                                    }}>
                                        {formData.auto_create_asset && <Check size={16} color="white" strokeWidth={3} />}
                                        <input
                                            type="checkbox"
                                            checked={formData.auto_create_asset}
                                            onChange={(e) => setFormData({
                                                ...formData,
                                                auto_create_asset: e.target.checked,
                                                // Clearing the category when toggling off avoids stale FK on the next save.
                                                ...(!e.target.checked ? { asset_category: null } : {}),
                                            })}
                                            style={{ position: 'absolute', opacity: 0, cursor: 'pointer' }}
                                        />
                                    </div>
                                    <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>
                                        Auto-create asset on debit
                                    </span>
                                </label>

                                {formData.auto_create_asset && (
                                    <div style={{ minWidth: '320px' }}>
                                        <select
                                            value={formData.asset_category ?? ''}
                                            onChange={(e) => setFormData({
                                                ...formData,
                                                asset_category: e.target.value ? Number(e.target.value) : null,
                                            })}
                                            required
                                            className="glass-input"
                                            style={{ width: '100%', fontSize: 'var(--text-sm)', padding: '0.5rem 1rem' }}
                                        >
                                            <option value="">-- Select Asset Category --</option>
                                            {assetCategories.map((c) => (
                                                <option key={c.id} value={c.id}>
                                                    {c.code} — {c.name}
                                                    {c.cost_account_display
                                                        ? ` (Recon GL: ${c.cost_account_display.code} ${c.cost_account_display.name})`
                                                        : ' (⚠ no cost account set)'}
                                                </option>
                                            ))}
                                        </select>
                                        <p style={{ margin: '0.4rem 0 0', fontSize: '0.7rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                            On debit posting: creates a FixedAsset record, credits this GL to zero (clearing), and debits the category's cost account (asset recon GL). Works in Journal Entry, AP Invoice, and GRN receipt.
                                        </p>
                                    </div>
                                )}
                            </div>

                            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
                                <button className="btn-glass" onClick={() => { setShowForm(false); resetForm(); }} type="button" style={{ minWidth: '120px' }}>
                                    Discard
                                </button>
                                <button
                                    className="btn-primary ripple"
                                    type="submit"
                                    disabled={createAccount.isPending || updateAccount.isPending}
                                    style={{ minWidth: '160px' }}
                                >
                                    {createAccount.isPending || updateAccount.isPending ? 'Processing...' : (editingAccount ? 'Save Changes' : 'Register Account')}
                                </button>
                            </div>
                        </form>
                    </GlassCard>
                </div>
            )}

            {/* Import Result Banner */}
            {importResult && (
                <div className="animate-slide-down" style={{ marginBottom: '1.5rem' }}>
                    <GlassCard style={{
                        padding: '1.5rem',
                        borderLeft: `4px solid ${importResult.errors.length > 0 ? '#f59e0b' : '#22c55e'}`,
                    }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div>
                                <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
                                    Import Results
                                </h3>
                                <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>
                                    Created: <strong>{importResult.created}</strong> &nbsp;|&nbsp;
                                    Skipped (duplicates): <strong>{importResult.skipped}</strong>
                                    {importResult.errors.length > 0 && (
                                        <> &nbsp;|&nbsp; Errors: <strong style={{ color: '#ef4444' }}>{importResult.errors.length}</strong></>
                                    )}
                                </p>
                                {importResult.errors.length > 0 && (
                                    <ul style={{
                                        marginTop: '0.75rem',
                                        paddingLeft: '1.25rem',
                                        color: '#ef4444',
                                        fontSize: 'var(--text-sm)',
                                        maxHeight: '150px',
                                        overflowY: 'auto',
                                    }}>
                                        {importResult.errors.map((err, i) => (
                                            <li key={`err-${i}-${err.slice(0, 20)}`} style={{ marginBottom: '0.25rem' }}>{err}</li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                            <button
                                onClick={() => setImportResult(null)}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
                            >
                                <X size={18} />
                            </button>
                        </div>
                    </GlassCard>
                </div>
            )}

            {/* List Controls */}
            <GlassCard style={{ padding: '1.25rem', marginBottom: '1.5rem' }} className="animate-fade-in">
                <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1, minWidth: '300px', background: 'rgba(255,255,255,0.05)', borderRadius: '10px', padding: '0 1rem' }}>
                        <Search size={20} style={{ color: 'var(--text-muted)' }} />
                        <input
                            type="text"
                            placeholder="Filter by code or description..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            style={{
                                flex: 1,
                                border: 'none',
                                background: 'transparent',
                                padding: '0.75rem 0',
                                color: 'var(--text-primary)',
                                fontWeight: 500,
                                outline: 'none'
                            }}
                        />
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Filter size={18} style={{ color: 'var(--text-muted)' }} />
                            <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-secondary)' }}>Type:</span>
                        </div>
                        <select
                            value={typeFilter}
                            onChange={(e) => setTypeFilter(e.target.value)}
                            className="glass-input"
                            style={{ minWidth: '160px', padding: '0.5rem 1rem' }}
                        >
                            <option value="">Full Registry</option>
                            <option value="Asset">Asset Ledger</option>
                            <option value="Liability">Liability Ledger</option>
                            <option value="Equity">Equity Ledger</option>
                            <option value="Income">Income Ledger</option>
                            <option value="Expense">Expense Ledger</option>
                        </select>
                    </div>
                </div>
            </GlassCard>

            {/* Accounts Registry Table */}
            <GlassCard style={{ padding: 0 }} className="animate-fade-in">
                <table className="glass-table" style={{ width: '100%' }}>
                    <thead>
                        <tr>
                            <th style={{ width: '40px', padding: '1rem' }}>
                                <input
                                    type="checkbox"
                                    checked={selectedIds.size === sortedAccounts.length && sortedAccounts.length > 0}
                                    onChange={toggleSelectAll}
                                    style={{ cursor: 'pointer' }}
                                />
                            </th>
                            <th
                                style={{ width: '15%', cursor: 'pointer', userSelect: 'none' }}
                                onClick={() => requestSort('code')}
                            >
                                <div style={{ display: 'flex', alignItems: 'center' }}>
                                    Code {getSortIndicator('code')}
                                </div>
                            </th>
                            <th
                                style={{ width: '35%', cursor: 'pointer', userSelect: 'none' }}
                                onClick={() => requestSort('name')}
                            >
                                <div style={{ display: 'flex', alignItems: 'center' }}>
                                    Account Name {getSortIndicator('name')}
                                </div>
                            </th>
                            <th
                                style={{ width: '15%', cursor: 'pointer', userSelect: 'none' }}
                                onClick={() => requestSort('account_type')}
                            >
                                <div style={{ display: 'flex', alignItems: 'center' }}>
                                    Category {getSortIndicator('account_type')}
                                </div>
                            </th>
                            <th
                                style={{ width: '12%', cursor: 'pointer', userSelect: 'none' }}
                                onClick={() => requestSort('is_active')}
                            >
                                <div style={{ display: 'flex', alignItems: 'center' }}>
                                    Status {getSortIndicator('is_active')}
                                </div>
                            </th>
                            <th
                                style={{ width: '15%', cursor: 'pointer', userSelect: 'none' }}
                                onClick={() => requestSort('is_reconciliation')}
                            >
                                <div style={{ display: 'flex', alignItems: 'center' }}>
                                    Reconciliation {getSortIndicator('is_reconciliation')}
                                </div>
                            </th>
                            <th style={{ width: '15%', textAlign: 'right' }}>Balance</th>
                            <th style={{ width: '12%', textAlign: 'center' }}>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {sortedAccounts.map((account: Account, index: number) => (
                            <tr key={account.id} className="stagger-item" style={{ animationDelay: `${index * 0.03}s` }}>
                                <td style={{ padding: '1rem' }}>
                                    <input
                                        type="checkbox"
                                        checked={selectedIds.has(account.id)}
                                        onChange={() => toggleSelectOne(account.id)}
                                        style={{ cursor: 'pointer' }}
                                    />
                                </td>
                                <td style={{ fontWeight: 700, color: 'var(--primary)', fontFamily: 'monospace', letterSpacing: '0.05em' }}>
                                    {account.code}
                                </td>
                                <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{account.name}</td>
                                <td>
                                    <span className="badge-glass badge-approved" style={{ fontSize: 'var(--text-xs)' }}>
                                        {account.account_type}
                                    </span>
                                </td>
                                <td>
                                    <StatusBadge status={account.is_active ? 'Active' : 'Inactive'} />
                                </td>
                                <td>
                                    {account.is_reconciliation ? (
                                        <span className="badge-glass" style={{
                                            fontSize: 'var(--text-xs)',
                                            background: 'rgba(139, 92, 246, 0.15)',
                                            color: '#a78bfa',
                                            border: '1px solid rgba(139, 92, 246, 0.3)',
                                        }}>
                                            {account.reconciliation_type_display}
                                        </span>
                                    ) : (
                                        <span style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>--</span>
                                    )}
                                </td>
                                <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--text-primary)', fontSize: 'var(--text-sm)' }}>
                                    {parseFloat(account.current_balance).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </td>
                                <td>
                                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
                                        <button
                                            onClick={() => handleOpenLedger(account)}
                                            className="btn-glass"
                                            style={{ padding: '6px 10px' }}
                                            title="View GL Ledger"
                                        >
                                            <BookOpen size={14} color="#10b981" />
                                        </button>
                                        <button
                                            onClick={() => handleCopy(account)}
                                            className="btn-glass"
                                            style={{ padding: '6px 10px' }}
                                            title="Copy Account"
                                        >
                                            <Copy size={14} color="var(--text-secondary)" />
                                        </button>
                                        <button
                                            onClick={() => handleEdit(account)}
                                            className="btn-glass"
                                            style={{ padding: '6px 10px' }}
                                            title="Modify Account"
                                        >
                                            <Edit size={14} color="var(--primary)" />
                                        </button>
                                        <button
                                            onClick={() => handleDelete(account.id, account.name)}
                                            className="btn-glass"
                                            style={{ padding: '6px 10px' }}
                                            title="Delete Account"
                                        >
                                            <Trash2 size={14} color="#ef4444" />
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>

                {sortedAccounts.length === 0 && (
                    <div style={{ textAlign: 'center', padding: '6rem 2rem', color: 'var(--text-muted)' }}>
                        <div style={{
                            width: '80px',
                            height: '80px',
                            background: 'rgba(36, 113, 163, 0.05)',
                            borderRadius: '50%',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            margin: '0 auto 1.5rem'
                        }}>
                            <List size={40} style={{ opacity: 0.5 }} />
                        </div>
                        <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                            Registry looks clear
                        </h3>
                        <p style={{ fontSize: 'var(--text-sm)' }}>
                            {searchTerm || typeFilter
                                ? "No accounts match your current search criteria."
                                : "Your Chart of Accounts is currently empty. Start by adding your first ledger account."}
                        </p>
                        {(searchTerm || typeFilter) && (
                            <button
                                className="btn-primary"
                                style={{ marginTop: '1.5rem' }}
                                onClick={() => { setSearchTerm(''); setTypeFilter(''); }}
                            >
                                Clear All Search Filters
                            </button>
                        )}
                    </div>
                )}
            </GlassCard>

            {/* Pagination Controls */}
            {totalCount > 0 && (
                <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginTop: '1.5rem',
                    flexWrap: 'wrap',
                    gap: '1rem',
                }} className="animate-fade-in">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-secondary)' }}>
                            Rows per page:
                        </span>
                        <select
                            value={pageSize}
                            onChange={(e) => {
                                setPageSize(Number(e.target.value));
                                setCurrentPage(1);
                            }}
                            className="glass-input"
                            style={{ padding: '0.4rem 0.75rem', minWidth: '70px' }}
                        >
                            <option value={10}>10</option>
                            <option value={20}>20</option>
                            <option value={50}>50</option>
                            <option value={100}>100</option>
                        </select>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginRight: '0.5rem' }}>
                            {((currentPage - 1) * pageSize) + 1}–{Math.min(currentPage * pageSize, totalCount)} of {totalCount}
                        </span>
                        <button
                            className="btn-glass"
                            style={{ padding: '6px 10px' }}
                            disabled={currentPage <= 1}
                            onClick={() => setCurrentPage(1)}
                            title="First page"
                        >
                            <ChevronLeft size={14} /><ChevronLeft size={14} style={{ marginLeft: '-8px' }} />
                        </button>
                        <button
                            className="btn-glass"
                            style={{ padding: '6px 10px' }}
                            disabled={currentPage <= 1}
                            onClick={() => setCurrentPage(p => p - 1)}
                            title="Previous page"
                        >
                            <ChevronLeft size={14} />
                        </button>
                        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)', minWidth: '80px', textAlign: 'center' }}>
                            Page {currentPage} of {totalPages}
                        </span>
                        <button
                            className="btn-glass"
                            style={{ padding: '6px 10px' }}
                            disabled={currentPage >= totalPages}
                            onClick={() => setCurrentPage(p => p + 1)}
                            title="Next page"
                        >
                            <ChevronRight size={14} />
                        </button>
                        <button
                            className="btn-glass"
                            style={{ padding: '6px 10px' }}
                            disabled={currentPage >= totalPages}
                            onClick={() => setCurrentPage(totalPages)}
                            title="Last page"
                        >
                            <ChevronRight size={14} /><ChevronRight size={14} style={{ marginLeft: '-8px' }} />
                        </button>
                    </div>
                </div>
            )}
            {/* Bulk Reconciliation modal — picks the sub-type and confirms.
                The backend silently skips Income / Expense / Equity rows (only
                Asset and Liability are valid reconciliation candidates) and
                returns a count, which we surface in the success toast. */}
            {reconModalOpen && (
                <div style={{
                    position: 'fixed', inset: 0, zIndex: 1000,
                    background: 'rgba(0,0,0,0.55)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                    <div style={{
                        background: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        borderRadius: '1rem',
                        width: '100%',
                        maxWidth: '480px',
                        margin: '0 1rem',
                        boxShadow: '0 25px 60px rgba(0,0,0,0.4)',
                        padding: '1.75rem',
                    }}>
                        <h3 style={{ margin: '0 0 0.5rem', fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>
                            Mark Selected as Reconciliation
                        </h3>
                        <p style={{ margin: '0 0 1.25rem', fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                            {selectedIds.size} account(s) selected. Choose the reconciliation sub-type to apply.
                            Income / Expense / Equity accounts in the selection will be skipped — only Asset
                            and Liability accounts can be reconciliation accounts.
                        </p>
                        <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                            Reconciliation Sub-Type
                        </label>
                        <select
                            value={reconType}
                            onChange={(e) => setReconType(e.target.value)}
                            className="glass-input"
                            style={{ width: '100%', fontSize: 'var(--text-sm)', padding: '0.6rem 1rem', marginBottom: '0.5rem' }}
                        >
                            <option value="">-- (Clear reconciliation flag) --</option>
                            <option value="accounts_payable">Account Payable</option>
                            <option value="accounts_receivable">Account Receivable</option>
                            <option value="inventory">Inventory</option>
                            <option value="asset_accounting">Asset Accounting</option>
                            <option value="bank_accounting">Bank Accounting</option>
                        </select>
                        <p style={{ margin: '0.4rem 0 1.25rem', fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
                            Picking the empty option turns off the reconciliation flag on every selected account.
                        </p>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.6rem' }}>
                            <button
                                className="btn-glass"
                                type="button"
                                onClick={() => { setReconModalOpen(false); setReconType(''); }}
                                disabled={bulkReconcileAccounts.isPending}
                            >
                                Cancel
                            </button>
                            <button
                                className="btn-primary ripple"
                                type="button"
                                onClick={() => bulkReconcileAccounts.mutate({
                                    ids: Array.from(selectedIds),
                                    reconciliation_type: reconType,
                                })}
                                disabled={bulkReconcileAccounts.isPending}
                            >
                                {bulkReconcileAccounts.isPending ? 'Updating…' : (reconType ? 'Apply' : 'Clear Flag')}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Bulk Auto-Capitalisation modal — picks the Asset Category whose
                cost_account will receive the capitalisation debit at posting time.
                Selecting "(Clear flag)" turns the toggle OFF and detaches the
                category on every selected account in one request. */}
            {autoAssetModalOpen && (
                <div style={{
                    position: 'fixed', inset: 0, zIndex: 1000,
                    background: 'rgba(0,0,0,0.55)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                    <div style={{
                        background: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        borderRadius: '1rem',
                        width: '100%',
                        maxWidth: '520px',
                        margin: '0 1rem',
                        boxShadow: '0 25px 60px rgba(0,0,0,0.4)',
                        padding: '1.75rem',
                    }}>
                        <h3 style={{ margin: '0 0 0.5rem', fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>
                            Auto-Asset Capitalisation on Debit
                        </h3>
                        <p style={{ margin: '0 0 1.25rem', fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                            {selectedIds.size} account(s) selected. Pick the Asset Category to link.
                            From the next posting onwards, every debit to these GL accounts will
                            auto-create a FixedAsset in this category and reroute the GL debit to
                            the category's cost account.
                        </p>
                        <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                            Asset Category
                        </label>
                        <select
                            value={autoAssetCategoryId ?? ''}
                            onChange={(e) => setAutoAssetCategoryId(e.target.value ? Number(e.target.value) : null)}
                            className="glass-input"
                            style={{ width: '100%', fontSize: 'var(--text-sm)', padding: '0.6rem 1rem', marginBottom: '0.5rem' }}
                        >
                            <option value="">-- (Clear flag — turn auto-asset OFF) --</option>
                            {assetCategories.map((c) => (
                                <option key={c.id} value={c.id}>
                                    {c.code} — {c.name}
                                </option>
                            ))}
                        </select>
                        <p style={{ margin: '0.4rem 0 1.25rem', fontSize: '0.7rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                            Picking the empty option clears the auto-create toggle on every selected
                            account. The chosen category must have a Cost Account set in Asset
                            Categories — the importer / posting hook will fail loudly otherwise.
                        </p>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.6rem' }}>
                            <button
                                className="btn-glass"
                                type="button"
                                onClick={() => { setAutoAssetModalOpen(false); setAutoAssetCategoryId(null); }}
                                disabled={bulkSetAutoAsset.isPending}
                            >
                                Cancel
                            </button>
                            <button
                                className="btn-primary ripple"
                                type="button"
                                onClick={() => bulkSetAutoAsset.mutate({
                                    ids: Array.from(selectedIds),
                                    asset_category_id: autoAssetCategoryId,
                                })}
                                disabled={bulkSetAutoAsset.isPending}
                            >
                                {bulkSetAutoAsset.isPending ? 'Updating…' : (autoAssetCategoryId ? 'Apply' : 'Clear Flag')}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* GL Ledger Modal */}
            {ledgerAccount && (
                <div style={{
                    position: 'fixed', inset: 0, zIndex: 1000,
                    background: 'rgba(0,0,0,0.55)',
                    display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
                    paddingTop: '4rem', overflowY: 'auto',
                }}>
                    <div style={{
                        background: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        borderRadius: '1rem',
                        width: '100%',
                        maxWidth: '1100px',
                        margin: '0 1rem 4rem',
                        boxShadow: '0 25px 60px rgba(0,0,0,0.4)',
                        overflow: 'hidden',
                    }}>
                        {/* Header */}
                        <div style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            padding: '1.25rem 1.5rem',
                            borderBottom: '1px solid rgba(139,92,246,0.15)',
                            background: 'rgba(139,92,246,0.06)',
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                <BookOpen size={20} color="#10b981" />
                                <div>
                                    <h3 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)' }}>
                                        GL Ledger — {ledgerAccount.code} · {ledgerAccount.name}
                                    </h3>
                                    <p style={{ margin: 0, fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                        {ledgerAccount.account_type} account · Running balance view
                                    </p>
                                </div>
                            </div>
                            <button
                                onClick={() => { setLedgerAccount(null); setLedgerData(null); }}
                                style={{ padding: '6px 10px', background: 'none', border: '1px solid var(--color-border)', borderRadius: '6px', cursor: 'pointer', color: 'var(--color-text)', display: 'flex', alignItems: 'center' }}
                            >
                                <X size={16} />
                            </button>
                        </div>

                        {/* Date-range filter row + Export button.
                            Two-group flex with ``justify-content: space-between``:
                            the date filter group sits on the left, the Export
                            button on the right. Each group has its own internal
                            wrap behaviour, so on narrow modals the date inputs
                            wrap onto a second line BEFORE the Export button
                            ever gets pushed off-screen — this is the failure
                            mode an earlier ``flex: nowrap`` + ``flex-shrink: 0``
                            attempt suffered, where the To input and Export
                            button became invisible on tight widths.
                            ``flexWrap: 'wrap'`` on the outer row is the safety
                            net for very narrow viewports. */}
                        <div style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            gap: '0.75rem',
                            padding: '1rem 1.5rem',
                            borderBottom: '1px solid var(--color-border)',
                            flexWrap: 'wrap',
                            background: 'var(--color-surface)',
                        }}>
                            {/* Left group — From / To pickers. They share the
                                same row but each owns enough width to display
                                a full date string. */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
                                <label style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', fontWeight: 600 }}>From</label>
                                <input
                                    type="date"
                                    value={ledgerStartDate}
                                    onChange={(e) => handleLedgerDateChange(e.target.value, ledgerEndDate)}
                                    style={{ minWidth: '160px', padding: '0.4rem 0.6rem', fontSize: 'var(--text-sm)', borderRadius: '6px', border: '1px solid var(--color-border)', background: 'var(--color-background)', color: 'var(--color-text)' }}
                                />
                                <label style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', fontWeight: 600 }}>To</label>
                                <input
                                    type="date"
                                    value={ledgerEndDate}
                                    onChange={(e) => handleLedgerDateChange(ledgerStartDate, e.target.value)}
                                    style={{ minWidth: '160px', padding: '0.4rem 0.6rem', fontSize: 'var(--text-sm)', borderRadius: '6px', border: '1px solid var(--color-border)', background: 'var(--color-background)', color: 'var(--color-text)' }}
                                />
                                {fetchLedger.isPending && (
                                    <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>Loading...</span>
                                )}
                            </div>

                            {/* Right group — Export button. Always visible
                                because it lives in its own flex group, so
                                the left group's wrapping never pushes it
                                off the right edge. CSV with UTF-8 BOM so
                                Excel renders ₦ / Unicode names correctly. */}
                            <button
                                type="button"
                                onClick={() => {
                                    if (!ledgerData || !ledgerAccount) return;
                                    const escape = (cell: unknown): string => {
                                        const str = String(cell ?? '');
                                        return str.includes(',') || str.includes('"') || str.includes('\n')
                                            ? `"${str.replace(/"/g, '""')}"` : str;
                                    };
                                    const fmt = (v: unknown) => {
                                        const n = parseFloat(String(v ?? '0'));
                                        return Number.isFinite(n) ? n.toFixed(2) : '0.00';
                                    };
                                    const rows: any[][] = [
                                        [`GL Ledger: ${ledgerAccount.code} ${ledgerAccount.name}`],
                                        [`Period: ${ledgerStartDate} to ${ledgerEndDate}`],
                                        [],
                                        ['Date', 'Reference', 'Description', 'Debit', 'Credit', 'Balance'],
                                    ];
                                    const entries = (ledgerData.entries || []) as any[];
                                    for (const e of entries) {
                                        rows.push([
                                            e.date || '',
                                            e.reference || '',
                                            e.description || '',
                                            fmt(e.debit),
                                            fmt(e.credit),
                                            fmt(e.balance),
                                        ]);
                                    }
                                    rows.push([]);
                                    // Closing balance is the running ``balance`` on
                                    // the last entry — backend (GeneralLedgerReportService)
                                    // returns ``total_debit`` / ``total_credit`` but
                                    // not a separate ``closing_balance`` field, so
                                    // we derive it from the entry list rather than
                                    // expecting a non-existent key (which would
                                    // silently print '0.00' for any non-zero ledger).
                                    const closingBalance = entries.length > 0 ? entries[entries.length - 1].balance : '0';
                                    rows.push(['', '', 'Totals', fmt(ledgerData.total_debit), fmt(ledgerData.total_credit), fmt(closingBalance)]);
                                    const csv = rows.map(r => r.map(escape).join(',')).join('\n');
                                    const blob = new Blob(['﻿' + csv], { type: 'application/vnd.ms-excel;charset=utf-8' });
                                    const url = window.URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = url;
                                    const stamp = new Date().toISOString().slice(0, 10);
                                    a.download = `ledger_${ledgerAccount.code}_${stamp}.csv`;
                                    a.click();
                                    window.URL.revokeObjectURL(url);
                                }}
                                disabled={!ledgerData || (ledgerData?.entries?.length ?? 0) === 0}
                                title={!ledgerData ? 'Run the report first' : 'Export ledger entries to Excel'}
                                style={{
                                    // Right-positioning is handled by the parent's
                                    // ``justify-content: space-between``; no
                                    // ``marginLeft: auto`` needed (and it would
                                    // misbehave when the row wraps).
                                    flexShrink: 0,
                                    display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                                    padding: '0.45rem 0.95rem',
                                    background: !ledgerData ? 'var(--color-surface)' : '#0f172a',
                                    color: !ledgerData ? 'var(--color-text-muted)' : '#ffffff',
                                    border: !ledgerData ? '1px solid var(--color-border)' : '1px solid #0f172a',
                                    borderRadius: '6px',
                                    fontSize: 'var(--text-sm)',
                                    fontWeight: 600,
                                    cursor: !ledgerData ? 'not-allowed' : 'pointer',
                                    transition: 'background 0.15s, color 0.15s',
                                }}
                            >
                                <Download size={16} /> Export to Excel
                            </button>
                        </div>

                        {/* Table */}
                        <div style={{ overflowX: 'auto' }}>
                            {fetchLedger.isError && (
                                <div style={{ padding: '2rem', textAlign: 'center', color: '#ef4444', fontSize: 'var(--text-sm)' }}>
                                    Failed to load ledger entries. Please try again.
                                </div>
                            )}
                            {ledgerData && (
                                <>
                                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                                        <thead>
                                            <tr style={{ borderBottom: '2px solid var(--color-border)', background: 'var(--color-surface)' }}>
                                                {['Date', 'Reference', 'Description', 'Debit', 'Credit', 'Balance'].map(h => (
                                                    <th key={h} style={{
                                                        padding: '0.75rem 1rem',
                                                        textAlign: h === 'Date' || h === 'Reference' || h === 'Description' ? 'left' : 'right',
                                                        fontSize: 'var(--text-xs)',
                                                        fontWeight: 700,
                                                        color: 'var(--color-text-muted)',
                                                        textTransform: 'uppercase',
                                                        letterSpacing: '0.05em',
                                                        whiteSpace: 'nowrap',
                                                    }}>{h}</th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {/* Opening balance row — shows the cumulative
                                                balance carried into this window from
                                                prior posted entries. Surfaces the figure
                                                that previously lived only on the CoA list,
                                                so the closing balance reconciles even on
                                                a narrow date filter. */}
                                            <tr style={{
                                                borderBottom: '1px solid var(--color-border)',
                                                background: 'var(--color-surface)',
                                                fontStyle: 'italic',
                                            }}>
                                                <td style={{ padding: '0.65rem 1rem', color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                                                    {ledgerStartDate}
                                                </td>
                                                <td style={{ padding: '0.65rem 1rem', color: 'var(--color-text-muted)', whiteSpace: 'nowrap', fontWeight: 600 }}>—</td>
                                                <td style={{ padding: '0.65rem 1rem', color: 'var(--color-text-muted)', fontWeight: 600 }}>
                                                    Opening Balance (brought forward)
                                                </td>
                                                <td style={{ padding: '0.65rem 1rem', color: 'var(--color-text-muted)' }}>—</td>
                                                <td style={{ padding: '0.65rem 1rem', color: 'var(--color-text-muted)' }}>—</td>
                                                <td style={{
                                                    padding: '0.65rem 1rem', textAlign: 'right',
                                                    fontWeight: 700,
                                                    color: parseFloat(ledgerData.opening_balance ?? '0') < 0 ? '#ef4444' : 'var(--color-text)',
                                                    whiteSpace: 'nowrap',
                                                }}>
                                                    {parseFloat(ledgerData.opening_balance ?? '0').toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                                </td>
                                            </tr>
                                            {ledgerData.entries.length === 0 ? (
                                                <tr>
                                                    <td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                                        No transactions in this date window. Opening balance shown above —
                                                        widen the From date to see the source entries.
                                                    </td>
                                                </tr>
                                            ) : (
                                                ledgerData.entries.map((entry: any, idx: number) => (
                                                    <tr key={entry.id ?? `${entry.date}-${idx}`} style={{
                                                        borderBottom: '1px solid var(--color-border)',
                                                        background: idx % 2 === 0 ? 'transparent' : 'var(--color-surface)',
                                                    }}>
                                                        <td style={{ padding: '0.65rem 1rem', color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                                                            {entry.date}
                                                        </td>
                                                        <td style={{ padding: '0.65rem 1rem', color: 'var(--color-primary)', whiteSpace: 'nowrap', fontWeight: 600 }}>
                                                            {entry.reference || '—'}
                                                        </td>
                                                        <td style={{ padding: '0.65rem 1rem', color: 'var(--color-text)', maxWidth: '320px' }}>
                                                            {entry.description || '—'}
                                                        </td>
                                                        <td style={{ padding: '0.65rem 1rem', textAlign: 'right', color: parseFloat(entry.debit) > 0 ? '#10b981' : 'var(--color-text-muted)', fontWeight: parseFloat(entry.debit) > 0 ? 600 : 400, whiteSpace: 'nowrap' }}>
                                                            {parseFloat(entry.debit) > 0 ? parseFloat(entry.debit).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
                                                        </td>
                                                        <td style={{ padding: '0.65rem 1rem', textAlign: 'right', color: parseFloat(entry.credit) > 0 ? '#f59e0b' : 'var(--color-text-muted)', fontWeight: parseFloat(entry.credit) > 0 ? 600 : 400, whiteSpace: 'nowrap' }}>
                                                            {parseFloat(entry.credit) > 0 ? parseFloat(entry.credit).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
                                                        </td>
                                                        <td style={{ padding: '0.65rem 1rem', textAlign: 'right', fontWeight: 700, color: parseFloat(entry.balance) < 0 ? '#ef4444' : 'var(--color-text)', whiteSpace: 'nowrap' }}>
                                                            {parseFloat(entry.balance).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                                        </td>
                                                    </tr>
                                                ))
                                            )}
                                        </tbody>
                                    </table>

                                    {/* Totals footer — always shown when ledgerData
                                        loaded, even with zero in-window entries,
                                        because the Opening / Closing balances are
                                        meaningful regardless. */}
                                    <div style={{
                                        display: 'flex', justifyContent: 'flex-end', gap: '2.5rem',
                                        padding: '1rem 1.5rem',
                                        borderTop: '2px solid var(--color-border)',
                                        background: 'var(--color-surface)',
                                    }}>
                                        <div style={{ textAlign: 'right' }}>
                                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.25rem' }}>Opening</div>
                                            <div style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)' }}>
                                                {parseFloat(ledgerData.opening_balance ?? '0').toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                            </div>
                                        </div>
                                        <div style={{ textAlign: 'right' }}>
                                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.25rem' }}>Total Debit</div>
                                            <div style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: '#10b981' }}>
                                                {parseFloat(ledgerData.total_debit).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                            </div>
                                        </div>
                                        <div style={{ textAlign: 'right' }}>
                                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.25rem' }}>Total Credit</div>
                                            <div style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: '#f59e0b' }}>
                                                {parseFloat(ledgerData.total_credit).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                            </div>
                                        </div>
                                        <div style={{ textAlign: 'right' }}>
                                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.25rem' }}>Closing</div>
                                            <div style={{ fontSize: 'var(--text-base)', fontWeight: 800, color: parseFloat(ledgerData.closing_balance ?? '0') < 0 ? '#ef4444' : 'var(--color-primary)' }}>
                                                {parseFloat(ledgerData.closing_balance ?? '0').toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                            </div>
                                        </div>
                                        <div style={{ textAlign: 'right' }}>
                                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.25rem' }}>Entries</div>
                                            <div style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)' }}>
                                                {ledgerData.entries.length}
                                            </div>
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </AccountingLayout>
    );
}
