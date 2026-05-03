/**
 * GenericListPage — Glassmorphism-styled reusable list page for Quot PSE.
 * Uses PageHeader (gradient header) + glass-card table + CSS variable theming.
 */
import { useState, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';
import Sidebar from './Sidebar';
import PageHeader from './PageHeader';
import { Search, Pencil, Trash2, X } from 'lucide-react';
import '../features/accounting/styles/glassmorphism.css';

interface Column {
    key: string;
    label: string;
    format?: 'currency' | 'date' | 'percent' | 'number' | 'status';
    width?: string;
    /**
     * Optional custom cell renderer. When provided, takes precedence
     * over the default `formatCell(item[key])` behaviour. Use this to
     * combine multiple fields into a single cell — e.g. show
     * `{code} — {name}` for an NCoA economic column so users can
     * identify the row by either identifier.
     */
    render?: (item: Record<string, unknown>) => React.ReactNode;
}

interface ActionButton {
    label: string;
    onClick: () => void;
    variant?: 'primary' | 'secondary' | 'danger';
    icon?: React.ReactNode;
}

interface CustomRowAction {
    label: string;
    icon?: React.ReactNode;
    onClick: (item: Record<string, unknown>) => void;
    color?: string;          // button text/icon colour
    borderColor?: string;    // optional border override
}

interface RowActions {
    onEdit?: (item: Record<string, unknown>) => void;
    onDelete?: (item: Record<string, unknown>) => void;
    custom?: CustomRowAction[];  // extra actions rendered before Edit/Delete
}

/**
 * BulkAction — operates on the array of selected row items.
 *
 * Activating bulk mode by passing any element here automatically renders
 * a leading checkbox column plus a contextual action bar that surfaces
 * once at least one row is selected.
 */
interface BulkAction {
    label: string;
    icon?: React.ReactNode;
    /**
     * Called with the full record objects (not just ids) so handlers can
     * access any field they need (e.g. `account_number` for an audit log).
     * Return false to keep the selection after the action; default clears it.
     */
    onClick: (items: Record<string, unknown>[]) => void | Promise<void> | boolean | Promise<boolean>;
    variant?: 'primary' | 'danger' | 'secondary';
}

interface GenericListPageProps {
    title: string;
    subtitle?: string;
    endpoint: string;
    columns: Column[];
    searchFields?: string[];
    actions?: ActionButton[];
    onRowClick?: (item: Record<string, unknown>) => void;
    rowActions?: RowActions;
    /**
     * When provided, the table renders a leading checkbox column and a
     * contextual action bar that appears once at least one row is selected.
     * The bar lists each bulk action; clicking calls the action's onClick
     * with the array of selected row records.
     */
    bulkActions?: BulkAction[];
}

const fmtNGN = (val: number | string): string => {
    const num = typeof val === 'string' ? parseFloat(val) : val;
    if (isNaN(num)) return '\u20A60';
    return '\u20A6' + num.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const statusColor = (status: string): string => {
    const s = status?.toUpperCase() || '';
    if (s === 'ACTIVE' || s === 'POSTED' || s === 'PAID' || s === 'RELEASED' || s === 'APPROVED') return '#22c55e';
    if (s === 'DRAFT' || s === 'PENDING') return '#f59e0b';
    if (s === 'CANCELLED' || s === 'REVERSED' || s === 'FAILED' || s === 'REJECTED') return '#ef4444';
    return '#64748b';
};

const formatCell = (value: unknown, format?: string): string => {
    if (value === null || value === undefined) return '\u2014';
    if (format === 'currency') return fmtNGN(value as number);
    if (format === 'percent') return `${Number(value).toFixed(1)}%`;
    if (format === 'date' && typeof value === 'string') return value.split('T')[0];
    if (format === 'number') return Number(value).toLocaleString('en-NG');
    return String(value);
};

const GenericListPage = ({ title, subtitle, endpoint, columns, actions, onRowClick, rowActions, bulkActions }: GenericListPageProps) => {
    const [search, setSearch] = useState('');
    const [page, setPage] = useState(1);
    const pageSize = 25;
    // Bulk-select state. Keys are stringified row ids (we tolerate numeric or
    // uuid ids transparently). Cleared on page change so a user paging through
    // the list isn't quietly accumulating off-screen selections.
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
    const bulkEnabled = !!bulkActions && bulkActions.length > 0;

    const { data: rawData, isLoading, error } = useQuery({
        queryKey: ['generic-list', endpoint, page],
        queryFn: async () => {
            const res = await apiClient.get(endpoint, {
                params: { page, page_size: pageSize },
            });
            const d = res.data;
            if (Array.isArray(d)) return { results: d, count: d.length };
            return { results: d.results || [], count: d.count || 0 };
        },
        staleTime: 30_000,
    });

    const items = rawData?.results || [];
    const totalCount = rawData?.count || 0;
    const totalPages = Math.ceil(totalCount / pageSize);

    // Reset selection on page change OR endpoint change (different rows visible).
    useEffect(() => {
        setSelectedIds(new Set());
    }, [page, endpoint]);

    const toggleRow = (id: string) => {
        setSelectedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const runBulkAction = async (action: BulkAction, currentItems: Record<string, unknown>[]) => {
        const selectedItems = currentItems.filter(it => selectedIds.has(String(it.id)));
        if (selectedItems.length === 0) return;
        const result = await action.onClick(selectedItems);
        // Default behaviour: clear selection. Handlers can return `false` to
        // preserve the selection (e.g. when the action is non-destructive and
        // the user is likely to chain another bulk action).
        if (result !== false) setSelectedIds(new Set());
    };

    const filtered = useMemo(() => {
        if (!search.trim()) return items;
        const q = search.toLowerCase();
        return items.filter((item: Record<string, unknown>) =>
            columns.some(col => {
                const val = item[col.key];
                return val && String(val).toLowerCase().includes(q);
            })
        );
    }, [items, search, columns]);

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader title={title} subtitle={subtitle} />

                {/* Action buttons + Search bar */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', gap: '1rem' }}>
                    <div style={{ position: 'relative', maxWidth: '400px', flex: 1 }}>
                        <Search size={16} style={{
                            position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)',
                            color: 'var(--color-text-muted, #94a3b8)',
                        }} />
                        <input
                            type="text"
                            placeholder={`Search ${title.toLowerCase()}...`}
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                            style={{
                                width: '100%', padding: '0.625rem 0.75rem 0.625rem 2.25rem',
                                border: '2.5px solid var(--color-border, #e2e8f0)', borderRadius: '8px',
                                fontSize: 'var(--text-sm, 14px)',
                                background: 'var(--color-surface, #fff)',
                                color: 'var(--color-text, #1e293b)',
                                outline: 'none',
                            }}
                        />
                    </div>
                    {actions && actions.length > 0 && (
                        <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0 }}>
                            {actions.map((action, i) => (
                                <button
                                    key={i}
                                    onClick={action.onClick}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: '0.375rem',
                                        padding: '0.625rem 1.125rem',
                                        border: action.variant === 'primary' ? 'none' : '1px solid var(--color-border, #e2e8f0)',
                                        borderRadius: '8px',
                                        fontSize: 'var(--text-sm, 14px)', fontWeight: 600,
                                        cursor: 'pointer',
                                        background: action.variant === 'primary'
                                            ? 'linear-gradient(135deg, var(--primary, #191e6a) 0%, var(--primary-dark, #0f1240) 100%)'
                                            : action.variant === 'danger' ? '#ef4444'
                                            : 'var(--color-surface, #fff)',
                                        color: action.variant === 'primary' || action.variant === 'danger'
                                            ? '#fff' : 'var(--color-text, #1e293b)',
                                        boxShadow: action.variant === 'primary' ? '0 4px 12px rgba(15, 18, 64, 0.3)' : 'none',
                                        transition: 'all 0.15s',
                                    }}
                                >
                                    {action.icon}
                                    {action.label}
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                {/* Contextual bulk-action bar — visible only when at least
                    one row on the current page is selected. */}
                {bulkEnabled && selectedIds.size > 0 && (
                    <div style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        gap: '0.75rem', padding: '0.75rem 1rem', marginBottom: '0.75rem',
                        background: 'rgba(25, 30, 106, 0.06)',
                        border: '1.5px solid rgba(25, 30, 106, 0.2)',
                        borderRadius: '8px',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: 'var(--text-sm, 14px)' }}>
                            <span style={{ fontWeight: 600, color: 'var(--primary, #191e6a)' }}>
                                {selectedIds.size} selected
                            </span>
                            <button
                                onClick={() => setSelectedIds(new Set())}
                                title="Clear selection"
                                style={{
                                    display: 'inline-flex', alignItems: 'center', gap: 4,
                                    padding: '3px 8px', border: '1px solid var(--color-border, #e2e8f0)',
                                    borderRadius: 6, background: 'var(--color-surface, #fff)',
                                    cursor: 'pointer', fontSize: 'var(--text-xs, 12px)',
                                    color: 'var(--color-text-muted, #64748b)',
                                }}
                            >
                                <X size={12} /> Clear
                            </button>
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                            {bulkActions!.map((act, i) => (
                                <button
                                    key={i}
                                    onClick={() => runBulkAction(act, filtered)}
                                    style={{
                                        display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
                                        padding: '0.5rem 1rem',
                                        border: act.variant === 'danger' ? '1px solid #ef4444'
                                              : act.variant === 'primary' ? 'none'
                                              : '1px solid var(--color-border, #e2e8f0)',
                                        borderRadius: 6,
                                        background: act.variant === 'danger' ? '#ef4444'
                                                  : act.variant === 'primary'
                                                      ? 'linear-gradient(135deg, var(--primary, #191e6a) 0%, var(--primary-dark, #0f1240) 100%)'
                                                      : 'var(--color-surface, #fff)',
                                        color: (act.variant === 'danger' || act.variant === 'primary') ? '#fff' : 'var(--color-text, #1e293b)',
                                        fontSize: 'var(--text-xs, 13px)', fontWeight: 600,
                                        cursor: 'pointer',
                                    }}
                                >
                                    {act.icon}
                                    {act.label}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* Table */}
                <div className="glass-card" style={{ overflow: 'hidden' }}>
                    {isLoading ? (
                        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted, #94a3b8)' }}>
                            Loading...
                        </div>
                    ) : error ? (
                        <div style={{ padding: '3rem', textAlign: 'center', color: '#ef4444' }}>
                            Error loading data. Check API connection.
                        </div>
                    ) : filtered.length === 0 ? (
                        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted, #94a3b8)' }}>
                            No records found.
                        </div>
                    ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '2px solid var(--color-border, #e8ecf1)' }}>
                                    {bulkEnabled && (
                                        <th style={{ padding: '0.875rem 0.5rem 0.875rem 1rem', width: 36 }}>
                                            <input
                                                type="checkbox"
                                                aria-label="Select all on page"
                                                checked={filtered.length > 0 && filtered.every((it: Record<string, unknown>) => selectedIds.has(String(it.id)))}
                                                onChange={e => {
                                                    if (e.target.checked) {
                                                        setSelectedIds(new Set(filtered.map((it: Record<string, unknown>) => String(it.id))));
                                                    } else {
                                                        setSelectedIds(new Set());
                                                    }
                                                }}
                                                style={{ cursor: 'pointer', width: 16, height: 16, accentColor: 'var(--primary, #191e6a)' }}
                                            />
                                        </th>
                                    )}
                                    {columns.map(col => (
                                        <th key={col.key} style={{
                                            padding: '0.875rem 1rem', textAlign: 'left',
                                            fontSize: 'var(--text-xs, 12px)', fontWeight: 600,
                                            color: 'var(--color-text-muted, #64748b)',
                                            textTransform: 'uppercase', letterSpacing: '0.5px',
                                            width: col.width,
                                        }}>
                                            {col.label}
                                        </th>
                                    ))}
                                    {rowActions && (
                                        <th style={{
                                            padding: '0.875rem 1rem', textAlign: 'right',
                                            fontSize: 'var(--text-xs, 12px)', fontWeight: 600,
                                            color: 'var(--color-text-muted, #64748b)',
                                            textTransform: 'uppercase', letterSpacing: '0.5px',
                                            width: '100px',
                                        }}>
                                            Actions
                                        </th>
                                    )}
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.map((item: Record<string, unknown>, idx: number) => {
                                    const rowId = String(item.id);
                                    const checked = bulkEnabled && selectedIds.has(rowId);
                                    return (
                                    <tr key={idx} style={{
                                        borderBottom: '1px solid var(--color-border, #f1f5f9)',
                                        transition: 'all var(--transition-fast, 150ms)',
                                        cursor: onRowClick ? 'pointer' : 'default',
                                        background: checked ? 'rgba(25, 30, 106, 0.04)' : undefined,
                                    }}
                                        onClick={() => onRowClick?.(item)}
                                        onMouseEnter={e => { if (!checked) e.currentTarget.style.background = 'rgba(25, 30, 106, 0.03)'; }}
                                        onMouseLeave={e => { if (!checked) e.currentTarget.style.background = ''; }}
                                    >
                                        {bulkEnabled && (
                                            <td style={{ padding: '0.75rem 0.5rem 0.75rem 1rem', width: 36 }}
                                                onClick={e => e.stopPropagation()}>
                                                <input
                                                    type="checkbox"
                                                    aria-label={`Select row ${rowId}`}
                                                    checked={checked}
                                                    onChange={() => toggleRow(rowId)}
                                                    style={{ cursor: 'pointer', width: 16, height: 16, accentColor: 'var(--primary, #191e6a)' }}
                                                />
                                            </td>
                                        )}
                                        {columns.map(col => (
                                            <td key={col.key} style={{
                                                padding: '0.75rem 1rem',
                                                fontSize: 'var(--text-sm, 14px)',
                                                color: 'var(--color-text, #1e293b)',
                                            }}>
                                                {col.render ? (
                                                    col.render(item)
                                                ) : col.format === 'status' ? (
                                                    <span className="badge-glass" style={{
                                                        padding: '4px 10px',
                                                        borderRadius: '20px',
                                                        fontSize: '11px',
                                                        fontWeight: 600,
                                                        background: `${statusColor(String(item[col.key]))}14`,
                                                        color: statusColor(String(item[col.key])),
                                                        border: `1px solid ${statusColor(String(item[col.key]))}30`,
                                                    }}>
                                                        {String(item[col.key])}
                                                    </span>
                                                ) : (
                                                    formatCell(item[col.key], col.format)
                                                )}
                                            </td>
                                        ))}
                                        {rowActions && (
                                            <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                                                <div style={{ display: 'flex', gap: '4px', justifyContent: 'flex-end' }}>
                                                    {rowActions.custom?.map((act, i) => (
                                                        <button
                                                            key={`custom-${i}`}
                                                            onClick={e => { e.stopPropagation(); act.onClick(item); }}
                                                            title={act.label}
                                                            style={{
                                                                padding: '6px',
                                                                border: `1px solid ${act.borderColor || 'var(--color-border, #e2e8f0)'}`,
                                                                borderRadius: '6px',
                                                                background: 'var(--color-surface, #fff)',
                                                                cursor: 'pointer',
                                                                color: act.color || 'var(--primary-light, #4a52c0)',
                                                            }}
                                                        >
                                                            {act.icon}
                                                        </button>
                                                    ))}
                                                    {rowActions.onEdit && (
                                                        <button
                                                            onClick={e => { e.stopPropagation(); rowActions.onEdit!(item); }}
                                                            title="Edit"
                                                            style={{
                                                                padding: '6px', border: '1px solid var(--color-border, #e2e8f0)',
                                                                borderRadius: '6px', background: 'var(--color-surface, #fff)',
                                                                cursor: 'pointer', color: 'var(--primary-light, #4a52c0)',
                                                            }}
                                                        >
                                                            <Pencil size={14} />
                                                        </button>
                                                    )}
                                                    {rowActions.onDelete && (
                                                        <button
                                                            onClick={e => { e.stopPropagation(); rowActions.onDelete!(item); }}
                                                            title="Delete"
                                                            style={{
                                                                padding: '6px', border: '1px solid #fecaca',
                                                                borderRadius: '6px', background: 'var(--color-surface, #fff)',
                                                                cursor: 'pointer', color: '#ef4444',
                                                            }}
                                                        >
                                                            <Trash2 size={14} />
                                                        </button>
                                                    )}
                                                </div>
                                            </td>
                                        )}
                                    </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    )}

                    {/* Pagination */}
                    {totalPages > 1 && (
                        <div style={{
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                            padding: '0.75rem 1rem', borderTop: '1px solid var(--color-border, #e8ecf1)',
                        }}>
                            <div style={{ fontSize: 'var(--text-xs, 13px)', color: 'var(--color-text-muted, #64748b)' }}>
                                Showing {((page - 1) * pageSize) + 1}\u2013{Math.min(page * pageSize, totalCount)} of {totalCount}
                            </div>
                            <div style={{ display: 'flex', gap: '6px' }}>
                                <button
                                    onClick={() => setPage(p => Math.max(1, p - 1))}
                                    disabled={page === 1}
                                    className="glass-button"
                                    style={{
                                        padding: '6px 12px', border: '1px solid var(--color-border, #e2e8f0)',
                                        borderRadius: '6px', fontSize: 'var(--text-xs, 13px)', cursor: 'pointer',
                                        background: page === 1 ? 'var(--color-surface, #f1f5f9)' : 'var(--color-surface, #fff)',
                                        color: page === 1 ? 'var(--color-text-muted, #94a3b8)' : 'var(--color-text, #1e293b)',
                                    }}
                                >
                                    Previous
                                </button>
                                <button
                                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                                    disabled={page >= totalPages}
                                    className="glass-button"
                                    style={{
                                        padding: '6px 12px', border: '1px solid var(--color-border, #e2e8f0)',
                                        borderRadius: '6px', fontSize: 'var(--text-xs, 13px)', cursor: 'pointer',
                                        background: page >= totalPages ? 'var(--color-surface, #f1f5f9)' : 'var(--color-surface, #fff)',
                                        color: page >= totalPages ? 'var(--color-text-muted, #94a3b8)' : 'var(--color-text, #1e293b)',
                                    }}
                                >
                                    Next
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
};

export default GenericListPage;
