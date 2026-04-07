import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useJournals, usePostJournal, useUpdateJournalDescription, useUnpostJournal, useJournalDetail, useBulkDeleteJournals, useDeleteJournal } from './hooks/useJournal';
import AccountingLayout from './AccountingLayout';
import PageHeader from '../../components/PageHeader';
import { Plus, Check, FileText, Eye, Edit, RotateCcw, X, Save, Search, Filter, ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Trash2 } from 'lucide-react';
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
    const [sortField, setSortField] = useState<string>('-posting_date');
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

    const [viewId, setViewId] = useState<number | null>(null);
    const [editId, setEditId] = useState<number | null>(null);
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
    const canBulkDelete = selectedCount > 0 && selectedPostedCount === 0;

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
                    <div style={{ display: 'flex', gap: '1rem' }}>
                        <button className="btn btn-outline" onClick={() => setShowFilters(!showFilters)}>
                            <Filter size={18} /> {showFilters ? 'Hide Filters' : 'Show Filters'}
                        </button>
                        <button className="btn btn-primary" onClick={() => navigate('/accounting/new')}>
                            <Plus size={18} /> New Journal Entry
                        </button>
                    </div>
                }
            />

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
                            <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', cursor: 'pointer' }} onClick={() => handleSort('reference_number')}>
                                <div style={{ display: 'flex', alignItems: 'center' }}>Ref Number {getSortIcon('reference_number')}</div>
                            </th>
                            <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', cursor: 'pointer' }} onClick={() => handleSort('document_number')}>
                                <div style={{ display: 'flex', alignItems: 'center' }}>Document No {getSortIcon('document_number')}</div>
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
                                        <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>{journal.reference_number || `JE-${journal.id}`}</span>
                                    </div>
                                </td>
                                <td style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', fontFamily: 'monospace' }}>
                                    {journal.document_number}
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
                                        <button className="btn btn-outline" style={{ padding: '0.4rem', fontSize: 'var(--text-xs)' }} title="Edit Description" onClick={() => openEdit(journal)}>
                                            <Edit size={14} />
                                        </button>
                                        {journal.status === 'Posted' && (
                                            <button className="btn btn-outline" style={{ padding: '0.4rem', fontSize: 'var(--text-xs)', color: 'var(--error)', borderColor: 'var(--error)' }} title="Reverse Journal" onClick={() => setReverseId(journal.id)}>
                                                <RotateCcw size={14} />
                                            </button>
                                        )}
                                        {journal.status !== 'Posted' && (
                                            <>
                                                <button className="btn btn-primary" style={{ padding: '0.4rem 0.8rem', fontSize: 'var(--text-xs)' }} onClick={() => postJournal.mutate(journal.id)}>
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
