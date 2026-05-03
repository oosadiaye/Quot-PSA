import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    useJournals, usePostJournal, useUpdateJournalDescription, useUnpostJournal, useJournalDetail,
    useBulkDeleteJournals, useDeleteJournal,
    useDownloadJournalTemplate, useBulkImportJournals, useBulkPostJournals,
} from './hooks/useJournal';
import AccountingLayout from './AccountingLayout';
import PageHeader from '../../components/PageHeader';
import {
    Plus, Check, FileText, Eye, Edit, RotateCcw, X, Save, Search, Filter,
    ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Trash2,
    FileDown, Upload,
} from 'lucide-react';
import LoadingScreen from '../../components/common/LoadingScreen';
import { useDebounce } from '../../hooks/useDebounce';
import { useDialog } from '../../hooks/useDialog';

// Inner component to fetch details safely across re-renders
const JournalDetailModal = ({ id, onClose }: { id: number; onClose: () => void }) => {
    const { data: journal, isLoading } = useJournalDetail(id);

    return (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div className="card glass" style={{ width: '90%', maxWidth: '800px', maxHeight: '90vh', overflowY: 'auto' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
                    <h2 style={{ fontSize: 'var(--text-lg)', margin: 0 }}>Journal Details: {journal?.reference_number || `JE-${id}`}</h2>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text)' }}><X size={20} /></button>
                </div>
                {isLoading ? (
                    <p>Loading details...</p>
                ) : (
                    <div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem', fontSize: 'var(--text-sm)' }}>
                            <div><strong>Date:</strong> {journal?.posting_date}</div>
                            <div><strong>Status:</strong> {journal?.status}</div>
                            <div><strong>Fund:</strong> {journal?.fund_name || '-'}</div>
                            <div><strong>Geo:</strong> {journal?.geo_name || '-'}</div>
                            <div style={{ gridColumn: 'span 2' }}><strong>Description:</strong> {journal?.description}</div>
                        </div>

                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                            <thead>
                                <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                    <th style={{ padding: '0.75rem' }}>Account</th>
                                    <th style={{ padding: '0.75rem' }}>Document No.</th>
                                    <th style={{ padding: '0.75rem', textAlign: 'right' }}>Debit</th>
                                    <th style={{ padding: '0.75rem', textAlign: 'right' }}>Credit</th>
                                    <th style={{ padding: '0.75rem' }}>Memo</th>
                                </tr>
                            </thead>
                            <tbody>
                                {journal?.lines?.map((line: any) => (
                                    <tr key={line.id ?? line.account_code} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.75rem' }}>{line.account_code} - {line.account_name}</td>
                                        <td style={{ padding: '0.75rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>{line.document_number || '-'}</td>
                                        <td style={{ padding: '0.75rem', textAlign: 'right' }}>{(parseFloat(line.debit) || 0) > 0 ? (parseFloat(line.debit)).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '-'}</td>
                                        <td style={{ padding: '0.75rem', textAlign: 'right' }}>{(parseFloat(line.credit) || 0) > 0 ? (parseFloat(line.credit)).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '-'}</td>
                                        <td style={{ padding: '0.75rem' }}>{line.memo || '-'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
};

const JournalList = () => {
    const { showConfirm } = useDialog();
    const navigate = useNavigate();
    const [reverseId, setReverseId] = useState<number | null>(null);
    const [reverseReason, setReverseReason] = useState<string>('');

    // Filtering & Sorting State
    // Default ordering: Draft journals before Posted (status asc — 'Draft' < 'Posted'),
    // then most recent posting date first. DRF OrderingFilter supports comma-separated
    // multi-field ordering, so this drives both groupings server-side.
    const [sortField, setSortField] = useState<string>('status,-posting_date');
    const [filters, setFilters] = useState({
        reference_number: '',
        document_number: '',
        account: '',
        status: '',
        min_amount: '',
        max_amount: ''
    });
    const [showFilters, setShowFilters] = useState(false);

    // Mutation hooks
    const postJournal = usePostJournal();
    const updateDesc = useUpdateJournalDescription();
    const unpostJournal = useUnpostJournal();
    const deleteJournal = useDeleteJournal();
    const bulkDelete = useBulkDeleteJournals();
    const bulkPost = useBulkPostJournals();
    const downloadTemplate = useDownloadJournalTemplate();
    const bulkImport = useBulkImportJournals();
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [importBanner, setImportBanner] = useState<{
        kind: 'success' | 'error'; message: string;
    } | null>(null);

    /**
     * Trigger the hidden file input when the user clicks "Import".
     * The input's onChange handles the actual upload + result banner.
     */
    const handleImportClick = () => {
        setImportBanner(null);
        fileInputRef.current?.click();
    };

    const handleFileChosen: React.ChangeEventHandler<HTMLInputElement> = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        try {
            const result = await bulkImport.mutateAsync(file);
            const errMsg = result.errors?.length
                ? ` · ${result.errors.length} error${result.errors.length === 1 ? '' : 's'}`
                : '';
            setImportBanner({
                kind: result.errors?.length ? 'error' : 'success',
                message: `${result.created} created, ${result.skipped} skipped${errMsg}`
                    + (result.errors?.length ? `: ${result.errors.slice(0, 3).join('; ')}` : ''),
            });
        } catch (err: unknown) {
            const e2 = err as { response?: { data?: { error?: string; detail?: string } }; message?: string };
            setImportBanner({
                kind: 'error',
                message: e2?.response?.data?.error
                    || e2?.response?.data?.detail
                    || e2?.message
                    || 'Import failed.',
            });
        } finally {
            // Reset so the same file can be re-selected after a fix
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    /**
     * Bulk-post: posts every Draft in the current selection.
     * Server-side filters; non-Draft selections are silently skipped
     * and counted in the response.
     */
    const handleBulkPost = async () => {
        if (selectedDraftCount === 0) return;
        const ok = await showConfirm(
            `Post ${selectedDraftCount} draft journal${selectedDraftCount === 1 ? '' : 's'} ` +
            `to the General Ledger?\n\nPosted entries cannot be edited — only reversed.`
        );
        if (!ok) return;
        try {
            const result = await bulkPost.mutateAsync(Array.from(selectedIds));
            setSelectedIds(new Set());
            const errLines = (result.failed || []).slice(0, 8)
                .map(f => `  • ${f.reference}: ${f.error}`)
                .join('\n');
            const more = (result.failed?.length ?? 0) > 8
                ? `\n  • +${result.failed.length - 8} more` : '';
            if (result.failed?.length) {
                window.alert(
                    `${result.posted} posted · ${result.skipped} skipped (not Draft) · ` +
                    `${result.failed.length} failed:\n${errLines}${more}`
                );
            } else {
                window.alert(
                    `${result.posted} journal${result.posted === 1 ? '' : 's'} posted` +
                    (result.skipped ? ` (${result.skipped} skipped — not Draft)` : '') + '.'
                );
            }
        } catch (err: unknown) {
            const e2 = err as { response?: { data?: { error?: string } }; message?: string };
            window.alert(`Bulk post failed: ${e2?.response?.data?.error || e2?.message || 'Unknown error'}`);
        }
    };

    const [viewId, setViewId] = useState<number | null>(null);
    const [editId, setEditId] = useState<number | null>(null);

    // Structured error state for the post-journal action. The backend
    // returns { error, detail, code, budget_violations? } for any failure
    // — we surface all of that in a modal-style banner instead of letting
    // the "Post" button look broken. `null` = no error visible.
    const [postError, setPostError] = useState<{
        headline: string;
        detail: string;
        code: string;
        violations?: Array<{ account?: string; account_name?: string; message?: string }>;
    } | null>(null);

    const handlePostJournal = (id: number) => {
        setPostError(null);
        postJournal.mutate(id, {
            onError: (err: any) => {
                const data = err?.response?.data || {};
                setPostError({
                    headline: data.error || data.detail || 'Posting failed.',
                    detail: data.detail || '',
                    code: data.code || 'INTERNAL',
                    violations: data.budget_violations || [],
                });
            },
        });
    };
    const [editDescription, setEditDescription] = useState<string>('');

    // Pagination state
    const [currentPage, setCurrentPage] = useState(1);
    const [pageSize] = useState(20);

    // Selection state for bulk actions
    const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

    // Debounced filters
    const debouncedFilters = useDebounce(filters, 500);

    const { data: journalsData, isLoading } = useJournals({
        ordering: sortField,
        page: currentPage,
        page_size: pageSize,
        ...debouncedFilters
    });
    const journals = journalsData?.results;
    const totalCount = journalsData?.count ?? 0;
    const totalPages = Math.ceil(totalCount / pageSize);

    // Reset to page 1 when filters or sort change
    useEffect(() => {
        setCurrentPage(1);
    }, [debouncedFilters, sortField]);

    const handleSort = (field: string) => {
        if (sortField === field) {
            setSortField(`-${field}`);
        } else if (sortField === `-${field}`) {
            setSortField(field);
        } else {
            setSortField(`-${field}`); // Default to descending
        }
    };

    const getSortIcon = (field: string) => {
        if (sortField === field) return <ChevronUp size={14} style={{ marginLeft: '4px' }} />;
        if (sortField === `-${field}`) return <ChevronDown size={14} style={{ marginLeft: '4px' }} />;
        return null;
    };

    const updateFilter = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        const { name, value } = e.target;
        setFilters(prev => ({ ...prev, [name]: value }));
    };

    const openEdit = (journal: any) => {
        setEditId(journal.id);
        setEditDescription(journal.description || '');
    };

    const handleSaveEdit = async () => {
        if (!editId) return;
        await updateDesc.mutateAsync({ id: editId, description: editDescription });
        setEditId(null);
    };

    const handleReverse = async () => {
        if (!reverseId) return;
        await unpostJournal.mutateAsync({ id: reverseId, reason: reverseReason || 'Manual reverse' });
        setReverseId(null);
        setReverseReason('');
    };

    const toggleSelect = (id: number) => {
        setSelectedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const toggleSelectAll = () => {
        if (!journals) return;
        if (selectedIds.size === journals.length) {
            setSelectedIds(new Set());
        } else {
            setSelectedIds(new Set(journals.map((j: any) => j.id)));
        }
    };

    const selectedCount = selectedIds.size;
    const selectedPostedCount = journals?.filter((j: any) => selectedIds.has(j.id) && j.status === 'Posted').length || 0;
    const selectedDraftCount = journals?.filter((j: any) => selectedIds.has(j.id) && j.status === 'Draft').length || 0;
    const canBulkDelete = selectedCount > 0 && selectedPostedCount === 0;
    const canBulkPost = selectedDraftCount > 0;

    const handleBulkDelete = async () => {
        try {
            await bulkDelete.mutateAsync(Array.from(selectedIds));
            setSelectedIds(new Set());
            setShowDeleteConfirm(false);
        } catch {
            // Error handled by mutation
        }
    };

    const handleSingleDelete = async (id: number) => {
        if (await showConfirm('Are you sure you want to delete this journal entry?')) {
            await deleteJournal.mutateAsync(id);
        }
    };

    if (isLoading) {
        return <LoadingScreen message="Loading transactions..." />;
    }

    return (
        <AccountingLayout>
            <PageHeader
                title="Chart of Journals"
                subtitle="Manage and audit your multi-dimensional financial transactions."
                icon={<FileText size={22} />}
                actions={
                    <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
                        <button
                            className="btn btn-outline"
                            onClick={() => downloadTemplate.mutate()}
                            disabled={downloadTemplate.isPending}
                            title="Download CSV template for journal import"
                        >
                            <FileDown size={16} /> Template
                        </button>
                        <button
                            className="btn btn-outline"
                            onClick={handleImportClick}
                            disabled={bulkImport.isPending}
                            title="Bulk-import journals from CSV / XLSX"
                        >
                            <Upload size={16} /> {bulkImport.isPending ? 'Importing…' : 'Import'}
                        </button>
                        <button className="btn btn-outline" onClick={() => setShowFilters(!showFilters)}>
                            <Filter size={18} /> {showFilters ? 'Hide Filters' : 'Show Filters'}
                        </button>
                        <button className="btn btn-primary" onClick={() => navigate('/accounting/new')}>
                            <Plus size={18} /> New Journal Entry
                        </button>
                    </div>
                }
            />

            {/* Hidden file input — triggered programmatically by the Import button. */}
            <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                style={{ display: 'none' }}
                onChange={handleFileChosen}
            />

            {/* Import result banner — shown until dismissed or replaced by next import. */}
            {importBanner && (
                <div
                    className="card"
                    style={{
                        marginBottom: '1rem', padding: '0.75rem 1.25rem',
                        background: importBanner.kind === 'success' ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
                        border: `1px solid ${importBanner.kind === 'success' ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                        color: importBanner.kind === 'success' ? '#15803d' : '#991b1b',
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem',
                        fontSize: 'var(--text-sm)',
                    }}
                >
                    <span><strong>{importBanner.kind === 'success' ? 'Import complete' : 'Import had errors'}:</strong> {importBanner.message}</span>
                    <button
                        onClick={() => setImportBanner(null)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}
                        aria-label="Dismiss"
                    >
                        <X size={16} />
                    </button>
                </div>
            )}

            {showFilters && (
                <div className="card glass animate-fade" style={{ marginBottom: '1.5rem', padding: '1.5rem' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>Reference number</label>
                            <div style={{ position: 'relative' }}>
                                <Search size={14} style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                                <input 
                                    type="text" 
                                    name="reference_number"
                                    className="input" 
                                    style={{ paddingLeft: '2.5rem', fontSize: 'var(--text-sm)' }} 
                                    placeholder="Search ref..." 
                                    value={filters.reference_number}
                                    onChange={updateFilter}
                                />
                            </div>
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>Document No</label>
                            <input 
                                type="text" 
                                name="document_number"
                                className="input" 
                                style={{ fontSize: 'var(--text-sm)' }} 
                                placeholder="Search doc..." 
                                value={filters.document_number}
                                onChange={updateFilter}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>Account Code/Name</label>
                            <input 
                                type="text" 
                                name="account"
                                className="input" 
                                style={{ fontSize: 'var(--text-sm)' }} 
                                placeholder="Search account..." 
                                value={filters.account}
                                onChange={updateFilter}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>Status</label>
                            <select 
                                name="status"
                                className="input" 
                                style={{ fontSize: 'var(--text-sm)' }}
                                value={filters.status}
                                onChange={updateFilter}
                            >
                                <option value="">All Statuses</option>
                                <option value="Draft">Draft</option>
                                <option value="Posted">Posted</option>
                            </select>
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>Min Amount</label>
                            <input 
                                type="number" 
                                name="min_amount"
                                className="input" 
                                style={{ fontSize: 'var(--text-sm)' }} 
                                placeholder="Min debit..." 
                                value={filters.min_amount}
                                onChange={updateFilter}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>Max Amount</label>
                            <input 
                                type="number" 
                                name="max_amount"
                                className="input" 
                                style={{ fontSize: 'var(--text-sm)' }} 
                                placeholder="Max debit..." 
                                value={filters.max_amount}
                                onChange={updateFilter}
                            />
                        </div>
                        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem' }}>
                            <button className="btn btn-primary" style={{ height: '42px', flex: 1, fontSize: 'var(--text-sm)' }} onClick={() => setShowFilters(false)}>
                                Done
                            </button>
                            <button className="btn btn-outline" style={{ height: '42px', flex: 1, fontSize: 'var(--text-sm)' }} onClick={() => setFilters({
                                reference_number: '',
                                document_number: '',
                                account: '',
                                status: '',
                                min_amount: '',
                                max_amount: ''
                            })}>
                                Reset
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Bulk action bar */}
            {selectedCount > 0 && (
                <div className="card glass animate-fade" style={{
                    marginBottom: '1rem', padding: '0.75rem 1.5rem',
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    background: 'rgba(36, 113, 163, 0.08)', border: '1px solid rgba(36, 113, 163, 0.2)',
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <span style={{ fontWeight: 600, fontSize: 'var(--text-sm)', color: 'var(--color-primary)' }}>
                            {selectedCount} journal{selectedCount > 1 ? 's' : ''} selected
                        </span>
                        {selectedPostedCount > 0 && (
                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--error)', fontWeight: 500 }}>
                                ({selectedPostedCount} posted — cannot delete)
                            </span>
                        )}
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button className="btn btn-outline" style={{ fontSize: 'var(--text-xs)', padding: '0.4rem 0.8rem' }} onClick={() => setSelectedIds(new Set())}>
                            Clear Selection
                        </button>
                        <button
                            className="btn"
                            style={{
                                fontSize: 'var(--text-xs)', padding: '0.4rem 0.8rem',
                                background: canBulkPost ? '#15803d' : '#e2e8f0',
                                color: canBulkPost ? '#fff' : '#94a3b8',
                                border: 'none',
                                cursor: canBulkPost ? 'pointer' : 'not-allowed',
                            }}
                            disabled={!canBulkPost || bulkPost.isPending}
                            onClick={handleBulkPost}
                            title={canBulkPost
                                ? `Post ${selectedDraftCount} draft journal${selectedDraftCount === 1 ? '' : 's'} to GL`
                                : 'No Draft journals in selection'}
                        >
                            <Check size={14} style={{ marginRight: '0.25rem' }} />
                            {bulkPost.isPending ? 'Posting…' : `Post ${selectedDraftCount > 0 ? `(${selectedDraftCount})` : 'Drafts'}`}
                        </button>
                        {showDeleteConfirm ? (
                            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--error)', fontWeight: 600 }}>Confirm delete?</span>
                                <button className="btn" style={{ fontSize: 'var(--text-xs)', padding: '0.4rem 0.8rem', background: 'var(--error)', color: '#fff', border: 'none' }}
                                    onClick={handleBulkDelete} disabled={bulkDelete.isPending}>
                                    {bulkDelete.isPending ? 'Deleting...' : 'Yes, Delete'}
                                </button>
                                <button className="btn btn-outline" style={{ fontSize: 'var(--text-xs)', padding: '0.4rem 0.8rem' }} onClick={() => setShowDeleteConfirm(false)}>
                                    Cancel
                                </button>
                            </div>
                        ) : (
                            <button className="btn" style={{ fontSize: 'var(--text-xs)', padding: '0.4rem 0.8rem', background: 'var(--error)', color: '#fff', border: 'none', opacity: canBulkDelete ? 1 : 0.5 }}
                                disabled={!canBulkDelete}
                                onClick={() => setShowDeleteConfirm(true)}
                                title={!canBulkDelete ? 'Cannot delete Posted journals' : `Delete ${selectedCount} journal(s)`}>
                                <Trash2 size={14} style={{ marginRight: '0.25rem' }} /> Delete Selected
                            </button>
                        )}
                    </div>
                </div>
            )}

            <div className="card glass animate-fade" style={{ padding: 0, overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                            <th style={{ padding: '1rem 0.75rem 1rem 1.5rem', width: '40px' }}>
                                <input
                                    type="checkbox"
                                    checked={journals?.length > 0 && selectedIds.size === journals.length}
                                    onChange={toggleSelectAll}
                                    style={{ cursor: 'pointer', width: '16px', height: '16px', accentColor: 'var(--color-primary)' }}
                                    title="Select all"
                                />
                            </th>
                            <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', cursor: 'pointer' }} onClick={() => handleSort('document_number')}>
                                <div style={{ display: 'flex', alignItems: 'center' }}>Document No {getSortIcon('document_number')}</div>
                            </th>
                            <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', cursor: 'pointer' }} onClick={() => handleSort('reference_number')}>
                                <div style={{ display: 'flex', alignItems: 'center' }}>Ref Number {getSortIcon('reference_number')}</div>
                            </th>
                            <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', cursor: 'pointer' }} onClick={() => handleSort('posting_date')}>
                                <div style={{ display: 'flex', alignItems: 'center' }}>Date {getSortIcon('posting_date')}</div>
                            </th>
                            <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Description</th>
                            <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', textAlign: 'right', cursor: 'pointer' }} onClick={() => handleSort('total_debit')}>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>Total Debit {getSortIcon('total_debit')}</div>
                            </th>
                            <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', textAlign: 'right', cursor: 'pointer' }} onClick={() => handleSort('total_credit')}>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>Total Credit {getSortIcon('total_credit')}</div>
                            </th>
                            <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', cursor: 'pointer' }} onClick={() => handleSort('status')}>
                                <div style={{ display: 'flex', alignItems: 'center' }}>Status {getSortIcon('status')}</div>
                            </th>
                            <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', textAlign: 'right' }}>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {journals?.map((journal: any) => (
                            <tr key={journal.id} style={{
                                borderBottom: '1px solid var(--color-border)', transition: 'var(--transition)',
                                background: selectedIds.has(journal.id) ? 'rgba(36, 113, 163, 0.05)' : undefined,
                            }}>
                                <td style={{ padding: '1rem 0.75rem 1rem 1.5rem', width: '40px' }}>
                                    <input
                                        type="checkbox"
                                        checked={selectedIds.has(journal.id)}
                                        onChange={() => toggleSelect(journal.id)}
                                        style={{ cursor: 'pointer', width: '16px', height: '16px', accentColor: 'var(--color-primary)' }}
                                    />
                                </td>
                                <td style={{ padding: '1rem 1.5rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                        <FileText size={18} style={{ color: 'var(--color-text-muted)' }} />
                                        <span style={{ fontWeight: 600, color: 'var(--color-text)', fontFamily: 'monospace' }}>{journal.document_number || '-'}</span>
                                    </div>
                                </td>
                                <td style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                    {journal.reference_number || `JE-${journal.id}`}
                                </td>
                                <td style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{journal.posting_date}</td>
                                <td style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-sm)' }}>
                                    <div style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={journal.description}>
                                        {journal.description || '-'}
                                    </div>
                                </td>
                                <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)' }}>
                                    {(parseFloat(journal.total_debit) || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                </td>
                                <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)' }}>
                                    {(parseFloat(journal.total_credit) || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                </td>
                                <td style={{ padding: '1rem 1.5rem' }}>
                                    <span style={{
                                        padding: '0.25rem 0.625rem', borderRadius: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600,
                                        background: journal.status === 'Posted' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(249, 115, 22, 0.15)',
                                        color: journal.status === 'Posted' ? 'var(--success)' : 'var(--color-cta)'
                                    }}>
                                        {journal.status}
                                    </span>
                                </td>
                                <td style={{ padding: '1rem 1.5rem', textAlign: 'right' }}>
                                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                        <button className="btn btn-outline" style={{ padding: '0.4rem', fontSize: 'var(--text-xs)' }} title="View Details" onClick={() => setViewId(journal.id)}>
                                            <Eye size={14} />
                                        </button>
                                        {journal.status === 'Posted' ? (
                                            // Posted/Approved entries are immutable — only Reverse remains.
                                            <button className="btn btn-outline" style={{ padding: '0.4rem', fontSize: 'var(--text-xs)', color: 'var(--error)', borderColor: 'var(--error)' }} title="Reverse Journal" onClick={() => setReverseId(journal.id)}>
                                                <RotateCcw size={14} />
                                            </button>
                                        ) : (
                                            <>
                                                <button className="btn btn-outline" style={{ padding: '0.4rem', fontSize: 'var(--text-xs)' }} title="Edit Journal (lines, accounts, amounts)" onClick={() => navigate(`/accounting/journals/${journal.id}/edit`)}>
                                                    <Edit size={14} />
                                                </button>
                                                <button className="btn btn-primary" style={{ padding: '0.4rem 0.8rem', fontSize: 'var(--text-xs)' }} onClick={() => handlePostJournal(journal.id)}>
                                                    <Check size={14} /> Post
                                                </button>
                                                <button className="btn btn-outline" style={{ padding: '0.4rem', fontSize: 'var(--text-xs)', color: 'var(--error)', borderColor: 'var(--error)' }} title="Delete Journal" onClick={() => handleSingleDelete(journal.id)}>
                                                    <Trash2 size={14} />
                                                </button>
                                            </>
                                        )}
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
                <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '1rem 0', marginTop: '1rem'
                }}>
                    <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                        Showing {((currentPage - 1) * pageSize) + 1}-{Math.min(currentPage * pageSize, totalCount)} of {totalCount} entries
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <button
                            className="btn btn-outline"
                            style={{ padding: '0.4rem 0.6rem', fontSize: 'var(--text-xs)' }}
                            disabled={currentPage <= 1}
                            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                        >
                            <ChevronLeft size={16} />
                        </button>
                        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', minWidth: '80px', textAlign: 'center' }}>
                            Page {currentPage} of {totalPages}
                        </span>
                        <button
                            className="btn btn-outline"
                            style={{ padding: '0.4rem 0.6rem', fontSize: 'var(--text-xs)' }}
                            disabled={currentPage >= totalPages}
                            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                        >
                            <ChevronRight size={16} />
                        </button>
                    </div>
                </div>
            )}

            {/* View Modal */}
            {viewId && <JournalDetailModal id={viewId} onClose={() => setViewId(null)} />}

            {/* Edit Description Modal */}
            {editId && (
                <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div className="card glass" style={{ width: '400px' }}>
                        <h3 style={{ marginTop: 0 }}>Edit Journal Description</h3>
                        <div style={{ marginBottom: '1rem' }}>
                            <label style={{ display: 'block', fontSize: 'var(--text-sm)', marginBottom: '0.5rem' }}>Description</label>
                            <textarea 
                                className="input" 
                                style={{ width: '100%', minHeight: '80px', padding: '0.5rem', borderRadius: '4px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)' }}
                                value={editDescription}
                                onChange={e => setEditDescription(e.target.value)}
                            />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                            <button className="btn btn-outline" onClick={() => setEditId(null)}>Cancel</button>
                            <button className="btn btn-primary" onClick={handleSaveEdit} disabled={updateDesc.isPending}>
                                <Save size={16} style={{ marginRight: '0.25rem' }}/> Save
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Reverse Modal */}
            {reverseId && (
                <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div className="card glass" style={{ width: '400px' }}>
                        <h3 style={{ marginTop: 0, color: 'var(--error)' }}>Reverse Journal Entry</h3>
                        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', marginBottom: '1rem' }}>
                            Are you sure you want to reverse this posted entry? This action will create a reversing entry to offset the balances.
                        </p>
                        <div style={{ marginBottom: '1.5rem' }}>
                            <label style={{ display: 'block', fontSize: 'var(--text-sm)', marginBottom: '0.5rem' }}>Reason for Reversal</label>
                            <input 
                                type="text"
                                className="input" 
                                style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)' }}
                                placeholder="e.g. Incorrect period"
                                value={reverseReason}
                                onChange={e => setReverseReason(e.target.value)}
                            />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                            <button className="btn btn-outline" onClick={() => setReverseId(null)}>Cancel</button>
                            <button className="btn" style={{ background: 'var(--error)', color: '#fff', border: 'none' }} onClick={handleReverse} disabled={unpostJournal.isPending}>
                                Confirm Reversal
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Post-journal error modal — shown whenever post_journal
                returns a structured error so users see exactly what to fix. */}
            {postError && (
                <div
                    role="dialog"
                    aria-modal="true"
                    style={{
                        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        zIndex: 1000, padding: '1rem',
                    }}
                    onClick={() => setPostError(null)}
                >
                    <div
                        className="glass-card"
                        style={{
                            maxWidth: 560, width: '100%', padding: '1.5rem',
                            background: 'var(--color-surface)',
                            border: '1px solid var(--color-border)',
                            borderRadius: 12, boxShadow: '0 20px 50px rgba(0,0,0,0.15)',
                        }}
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', marginBottom: '0.75rem' }}>
                            <div style={{
                                width: 36, height: 36, borderRadius: '50%',
                                background: 'rgba(239,68,68,0.12)', color: '#b91c1c',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                flexShrink: 0, fontWeight: 700,
                            }}>
                                !
                            </div>
                            <div style={{ flex: 1 }}>
                                <h3 style={{ margin: 0, fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)' }}>
                                    Cannot post journal
                                </h3>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: 2 }}>
                                    Reason code: <b>{postError.code}</b>
                                </div>
                            </div>
                        </div>
                        <div style={{
                            padding: '0.75rem 1rem', borderRadius: 8,
                            background: 'rgba(239,68,68,0.06)',
                            border: '1px solid rgba(239,68,68,0.2)',
                            color: 'var(--color-text)', fontSize: 'var(--text-sm)',
                            lineHeight: 1.5, marginBottom: '0.75rem',
                        }}>
                            {postError.headline}
                        </div>
                        {postError.violations && postError.violations.length > 0 && (
                            <div style={{ marginBottom: '0.75rem' }}>
                                <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', marginBottom: '0.375rem' }}>
                                    Offending lines:
                                </div>
                                <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: 'var(--text-xs)', color: 'var(--color-text)' }}>
                                    {postError.violations.map((v, i) => (
                                        <li key={i} style={{ marginBottom: '0.25rem' }}>
                                            <b>{v.account}</b>{v.account_name ? ` — ${v.account_name}` : ''}: {v.message}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                        {postError.code === 'BUDGET_NO_APPROPRIATION' && (
                            <div style={{
                                padding: '0.625rem 0.875rem', borderRadius: 6,
                                background: 'rgba(59,130,246,0.08)',
                                border: '1px solid rgba(59,130,246,0.2)',
                                color: '#1e40af', fontSize: 'var(--text-xs)',
                                lineHeight: 1.5, marginBottom: '0.75rem',
                            }}>
                                <b>Next step:</b> Go to <a href="/budget/appropriations/new" style={{ color: '#1e40af', fontWeight: 600 }}>Budget &rarr; New Appropriation</a>{' '}
                                and upload the appropriation line for this MDA + Economic Code + Fund. Once the
                                appropriation exists the journal can be posted.
                            </div>
                        )}
                        {postError.code === 'BUDGET_STRICT_BLOCK' && (
                            <div style={{
                                padding: '0.625rem 0.875rem', borderRadius: 6,
                                background: 'rgba(59,130,246,0.08)',
                                border: '1px solid rgba(59,130,246,0.2)',
                                color: '#1e40af', fontSize: 'var(--text-xs)',
                                lineHeight: 1.5, marginBottom: '0.75rem',
                            }}>
                                <b>Next step:</b> The GL series is under STRICT budget control. Either{' '}
                                <a href="/budget/appropriations/new" style={{ color: '#1e40af', fontWeight: 600 }}>add an appropriation</a> for this
                                account, raise a <a href="/budget/virements/new" style={{ color: '#1e40af', fontWeight: 600 }}>virement</a> from
                                another line, or adjust the <a href="/settings/accounting/budget-check-rules" style={{ color: '#1e40af', fontWeight: 600 }}>Budget Check Rules</a> if this code
                                shouldn't be hard-stopped.
                            </div>
                        )}
                        {postError.code === 'BUDGET_BALANCE_EXCEEDED' && (
                            <div style={{
                                padding: '0.625rem 0.875rem', borderRadius: 6,
                                background: 'rgba(59,130,246,0.08)',
                                border: '1px solid rgba(59,130,246,0.2)',
                                color: '#1e40af', fontSize: 'var(--text-xs)',
                                lineHeight: 1.5, marginBottom: '0.75rem',
                            }}>
                                <b>Next step:</b> The appropriation balance is not enough to cover this post. Raise a{' '}
                                <a href="/budget/virements/new" style={{ color: '#1e40af', fontWeight: 600 }}>virement</a> from
                                another line with available balance, or a{' '}
                                <a href="/budget/appropriations/new" style={{ color: '#1e40af', fontWeight: 600 }}>supplementary appropriation</a>.
                            </div>
                        )}
                        {postError.code === 'PERIOD_CLOSED' && (
                            <div style={{
                                padding: '0.625rem 0.875rem', borderRadius: 6,
                                background: 'rgba(59,130,246,0.08)',
                                border: '1px solid rgba(59,130,246,0.2)',
                                color: '#1e40af', fontSize: 'var(--text-xs)',
                                lineHeight: 1.5, marginBottom: '0.75rem',
                            }}>
                                <b>Next step:</b> The fiscal period for this journal's date is closed. Change the
                                posting date to an open period, or have an administrator reopen the period.
                            </div>
                        )}
                        {postError.detail && postError.detail !== postError.headline && (
                            <details style={{ marginBottom: '0.75rem' }}>
                                <summary style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', cursor: 'pointer' }}>
                                    Technical detail
                                </summary>
                                <div style={{
                                    marginTop: '0.5rem', padding: '0.5rem 0.75rem',
                                    background: 'var(--color-surface-muted, rgba(0,0,0,0.04))',
                                    borderRadius: 6, fontSize: '0.7rem',
                                    color: 'var(--color-text-muted)', lineHeight: 1.5,
                                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                                }}>
                                    {postError.detail}
                                </div>
                            </details>
                        )}
                        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                            <button
                                className="btn btn-primary"
                                onClick={() => setPostError(null)}
                                style={{ padding: '0.5rem 1.25rem' }}
                            >
                                OK, got it
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <style>{`
        .badge {
          background: var(--color-surface);
          color: var(--color-text-muted);
          padding: 0.125rem 0.5rem;
          border-radius: 4px;
          border: 1px solid var(--color-border);
          font-size: 0.75rem;
          font-weight: 500;
        }
      `}</style>
        </AccountingLayout>
    );
};

export default JournalList;
