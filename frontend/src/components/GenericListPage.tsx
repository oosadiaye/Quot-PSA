/**
 * GenericListPage — Glassmorphism-styled reusable list page for Quot PSE.
 * Uses PageHeader (gradient header) + glass-card table + CSS variable theming.
 */
import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';
import Sidebar from './Sidebar';
import PageHeader from './PageHeader';
import { Search, Pencil, Trash2 } from 'lucide-react';
import '../features/accounting/styles/glassmorphism.css';

interface Column {
    key: string;
    label: string;
    format?: 'currency' | 'date' | 'percent' | 'number' | 'status';
    width?: string;
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

interface GenericListPageProps {
    title: string;
    subtitle?: string;
    endpoint: string;
    columns: Column[];
    searchFields?: string[];
    actions?: ActionButton[];
    onRowClick?: (item: Record<string, unknown>) => void;
    rowActions?: RowActions;
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

const GenericListPage = ({ title, subtitle, endpoint, columns, actions, onRowClick, rowActions }: GenericListPageProps) => {
    const [search, setSearch] = useState('');
    const [page, setPage] = useState(1);
    const pageSize = 25;

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
                                {filtered.map((item: Record<string, unknown>, idx: number) => (
                                    <tr key={idx} style={{
                                        borderBottom: '1px solid var(--color-border, #f1f5f9)',
                                        transition: 'all var(--transition-fast, 150ms)',
                                        cursor: onRowClick ? 'pointer' : 'default',
                                    }}
                                        onClick={() => onRowClick?.(item)}
                                        onMouseEnter={e => (e.currentTarget.style.background = 'rgba(25, 30, 106, 0.03)')}
                                        onMouseLeave={e => (e.currentTarget.style.background = '')}
                                    >
                                        {columns.map(col => (
                                            <td key={col.key} style={{
                                                padding: '0.75rem 1rem',
                                                fontSize: 'var(--text-sm, 14px)',
                                                color: 'var(--color-text, #1e293b)',
                                            }}>
                                                {col.format === 'status' ? (
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
                                ))}
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
