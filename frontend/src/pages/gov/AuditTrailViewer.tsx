/**
 * Audit Trail Viewer — Quot PSE
 * Route: /audit/trail
 *
 * Searchable, filterable log of ALL system changes across all modules.
 * Read-only — no modifications possible. Used by Auditor General and
 * internal audit teams for compliance verification.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search, Shield, ChevronDown, ChevronRight, Clock } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import apiClient from '../../api/client';

const ACTION_COLORS: Record<string, { bg: string; color: string }> = {
    CREATE:  { bg: '#dcfce7', color: '#166534' },
    UPDATE:  { bg: '#dbeafe', color: '#1e40af' },
    DELETE:  { bg: '#fef2f2', color: '#dc2626' },
    POST:    { bg: '#f3e8ff', color: '#6b21a8' },
    APPROVE: { bg: '#dcfce7', color: '#166534' },
    REJECT:  { bg: '#fef2f2', color: '#dc2626' },
    CANCEL:  { bg: '#ffedd5', color: '#c2410c' },
    LOGIN:   { bg: '#f1f5f9', color: '#64748b' },
    LOGOUT:  { bg: '#f1f5f9', color: '#64748b' },
    VOID:    { bg: '#fef2f2', color: '#dc2626' },
    IMPORT:  { bg: '#dbeafe', color: '#1e40af' },
    EXPORT:  { bg: '#f1f5f9', color: '#64748b' },
};

const ALL_ACTIONS = [
    'CREATE', 'UPDATE', 'DELETE', 'POST', 'UNPOST',
    'APPROVE', 'REJECT', 'CANCEL', 'VOID',
    'LOGIN', 'LOGOUT', 'IMPORT', 'EXPORT',
];

const fmtDate = (iso: string) => {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleDateString('en-NG', { day: '2-digit', month: 'short', year: 'numeric' })
        + ' ' + d.toLocaleTimeString('en-NG', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

const fmtNGN = (v: number | null): string =>
    v ? '\u20A6' + v.toLocaleString('en-NG', { minimumFractionDigits: 2 }) : '';

interface AuditEntry {
    id: number;
    timestamp: string;
    action: string;
    username: string;
    model_name: string;
    object_repr: string;
    object_key: string;
    changes: Record<string, unknown>;
    previous_values: Record<string, unknown>;
    new_values: Record<string, unknown>;
    old_status: string;
    new_status: string;
    amount: number | null;
    ip_address: string | null;
    description: string;
    reference: string;
}

export default function AuditTrailViewer() {
    const [search, setSearch] = useState('');
    const [actionFilter, setActionFilter] = useState('');
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');
    const [page, setPage] = useState(1);
    const [expandedId, setExpandedId] = useState<number | null>(null);
    const pageSize = 30;

    const { data: rawData, isLoading } = useQuery({
        queryKey: ['audit-trail', page, search, actionFilter, dateFrom, dateTo],
        queryFn: async () => {
            const params: Record<string, string | number> = { page, page_size: pageSize };
            if (search) params.search = search;
            if (actionFilter) params.action = actionFilter;
            if (dateFrom) params.date_from = dateFrom;
            if (dateTo) params.date_to = dateTo;
            const res = await apiClient.get('/core/audit-trail/', { params });
            const d = res.data;
            if (Array.isArray(d)) return { results: d, count: d.length };
            return { results: d.results || [], count: d.count || 0 };
        },
        staleTime: 10_000,
    });

    const entries: AuditEntry[] = rawData?.results || [];
    const totalCount = rawData?.count || 0;
    const totalPages = Math.ceil(totalCount / pageSize);

    const inputStyle: React.CSSProperties = {
        padding: '8px 10px', borderRadius: '7px', border: '1.5px solid #e2e8f0',
        background: '#fff', color: '#1e293b', fontSize: '13px', outline: 'none',
    };

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '28px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <Shield size={22} color="#4338ca" />
                    <h1 style={{ fontSize: '22px', fontWeight: 800, color: '#1e293b', margin: 0 }}>Audit Trail</h1>
                </div>
                <p style={{ color: '#64748b', fontSize: 13, marginBottom: 20 }}>
                    Complete log of all system changes — {totalCount.toLocaleString()} entries
                </p>

                {/* Filters */}
                <div style={{
                    background: '#fff', borderRadius: 10, border: '1px solid #e8ecf1',
                    padding: '14px 16px', marginBottom: 16,
                    display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap',
                }}>
                    <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
                        <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                        <input
                            style={{ ...inputStyle, width: '100%', paddingLeft: 32 }}
                            placeholder="Search entries..."
                            value={search}
                            onChange={e => { setSearch(e.target.value); setPage(1); }}
                        />
                    </div>
                    <select
                        style={{ ...inputStyle, width: 140, appearance: 'auto' as never }}
                        value={actionFilter}
                        onChange={e => { setActionFilter(e.target.value); setPage(1); }}
                    >
                        <option value="">All Actions</option>
                        {ALL_ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
                    </select>
                    <input type="date" style={{ ...inputStyle, width: 140 }} value={dateFrom} onChange={e => { setDateFrom(e.target.value); setPage(1); }} placeholder="From" />
                    <input type="date" style={{ ...inputStyle, width: 140 }} value={dateTo} onChange={e => { setDateTo(e.target.value); setPage(1); }} placeholder="To" />
                    {(search || actionFilter || dateFrom || dateTo) && (
                        <button onClick={() => { setSearch(''); setActionFilter(''); setDateFrom(''); setDateTo(''); setPage(1); }}
                            style={{ background: 'none', border: '1px solid #e2e8f0', borderRadius: 6, padding: '7px 12px', fontSize: 12, cursor: 'pointer', color: '#64748b' }}>
                            Clear
                        </button>
                    )}
                </div>

                {/* Table */}
                <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e8ecf1', overflow: 'hidden' }}>
                    {isLoading ? (
                        <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>Loading audit trail...</div>
                    ) : entries.length === 0 ? (
                        <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>No audit entries found.</div>
                    ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                            <thead>
                                <tr style={{ borderBottom: '2px solid #e8ecf1', background: '#fafbfc' }}>
                                    <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', width: 30 }}></th>
                                    <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', width: 160 }}>Timestamp</th>
                                    <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', width: 90 }}>Action</th>
                                    <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', width: 110 }}>User</th>
                                    <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', width: 100 }}>Module</th>
                                    <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Description</th>
                                    <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', width: 100 }}>Amount</th>
                                </tr>
                            </thead>
                            <tbody>
                                {entries.map(entry => {
                                    const ac = ACTION_COLORS[entry.action] || { bg: '#f1f5f9', color: '#64748b' };
                                    const isExpanded = expandedId === entry.id;
                                    const hasChanges = Object.keys(entry.changes || {}).length > 0
                                        || Object.keys(entry.previous_values || {}).length > 0
                                        || entry.old_status || entry.new_status;

                                    return (
                                        <>
                                            <tr key={entry.id}
                                                onClick={() => hasChanges && setExpandedId(isExpanded ? null : entry.id)}
                                                style={{
                                                    borderBottom: '1px solid #f1f5f9',
                                                    cursor: hasChanges ? 'pointer' : 'default',
                                                    background: isExpanded ? '#fafaff' : '',
                                                }}
                                                onMouseEnter={e => { if (!isExpanded) e.currentTarget.style.background = '#fafbfc'; }}
                                                onMouseLeave={e => { if (!isExpanded) e.currentTarget.style.background = ''; }}
                                            >
                                                <td style={{ padding: '8px 10px', color: '#94a3b8' }}>
                                                    {hasChanges && (isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />)}
                                                </td>
                                                <td style={{ padding: '8px 12px', fontSize: 12, color: '#64748b', fontFamily: 'monospace' }}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                                        <Clock size={11} /> {fmtDate(entry.timestamp)}
                                                    </div>
                                                </td>
                                                <td style={{ padding: '8px 12px' }}>
                                                    <span style={{
                                                        display: 'inline-block', padding: '2px 8px', borderRadius: 4,
                                                        fontSize: 10, fontWeight: 700, background: ac.bg, color: ac.color,
                                                    }}>{entry.action}</span>
                                                </td>
                                                <td style={{ padding: '8px 12px', fontWeight: 500, color: '#1e293b' }}>{entry.username}</td>
                                                <td style={{ padding: '8px 12px', fontSize: 11, color: '#94a3b8' }}>{entry.model_name}</td>
                                                <td style={{ padding: '8px 12px', color: '#1e293b' }}>
                                                    <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 400 }}>
                                                        {entry.object_repr || entry.description || entry.reference || '—'}
                                                    </div>
                                                </td>
                                                <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#1e293b' }}>
                                                    {fmtNGN(entry.amount)}
                                                </td>
                                            </tr>
                                            {isExpanded && hasChanges && (
                                                <tr key={`${entry.id}-detail`}>
                                                    <td colSpan={7} style={{ padding: '0 12px 12px 44px', background: '#fafaff' }}>
                                                        <div style={{
                                                            background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8,
                                                            padding: 14, fontSize: 12,
                                                        }}>
                                                            {/* Status change */}
                                                            {(entry.old_status || entry.new_status) && (
                                                                <div style={{ marginBottom: 10 }}>
                                                                    <strong style={{ color: '#64748b', fontSize: 10, textTransform: 'uppercase' }}>Status Change:</strong>
                                                                    <div style={{ marginTop: 4 }}>
                                                                        <span style={{ color: '#ef4444' }}>{entry.old_status || '(none)'}</span>
                                                                        {' → '}
                                                                        <span style={{ color: '#22c55e', fontWeight: 600 }}>{entry.new_status || '(none)'}</span>
                                                                    </div>
                                                                </div>
                                                            )}

                                                            {/* Field changes */}
                                                            {Object.keys(entry.changes || {}).length > 0 && (
                                                                <div>
                                                                    <strong style={{ color: '#64748b', fontSize: 10, textTransform: 'uppercase' }}>Field Changes:</strong>
                                                                    <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 6 }}>
                                                                        <thead>
                                                                            <tr style={{ borderBottom: '1px solid #e8ecf1' }}>
                                                                                <th style={{ padding: '4px 8px', textAlign: 'left', fontSize: 10, color: '#94a3b8', fontWeight: 600 }}>Field</th>
                                                                                <th style={{ padding: '4px 8px', textAlign: 'left', fontSize: 10, color: '#94a3b8', fontWeight: 600 }}>Old Value</th>
                                                                                <th style={{ padding: '4px 8px', textAlign: 'left', fontSize: 10, color: '#94a3b8', fontWeight: 600 }}>New Value</th>
                                                                            </tr>
                                                                        </thead>
                                                                        <tbody>
                                                                            {Object.entries(entry.changes).map(([field, val]) => (
                                                                                <tr key={field} style={{ borderBottom: '1px solid #f8fafc' }}>
                                                                                    <td style={{ padding: '4px 8px', fontWeight: 600, color: '#1e293b' }}>{field}</td>
                                                                                    <td style={{ padding: '4px 8px', color: '#ef4444' }}>
                                                                                        {entry.previous_values?.[field] !== undefined ? String(entry.previous_values[field]) : '—'}
                                                                                    </td>
                                                                                    <td style={{ padding: '4px 8px', color: '#22c55e', fontWeight: 500 }}>
                                                                                        {String(val)}
                                                                                    </td>
                                                                                </tr>
                                                                            ))}
                                                                        </tbody>
                                                                    </table>
                                                                </div>
                                                            )}

                                                            {/* Metadata */}
                                                            <div style={{ marginTop: 10, display: 'flex', gap: 20, color: '#94a3b8', fontSize: 11 }}>
                                                                {entry.ip_address && <span>IP: {entry.ip_address}</span>}
                                                                {entry.reference && <span>Ref: {entry.reference}</span>}
                                                                {entry.object_key && <span>Key: {entry.object_key}</span>}
                                                            </div>
                                                        </div>
                                                    </td>
                                                </tr>
                                            )}
                                        </>
                                    );
                                })}
                            </tbody>
                        </table>
                    )}

                    {/* Pagination */}
                    {totalPages > 1 && (
                        <div style={{
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                            padding: '10px 14px', borderTop: '1px solid #e8ecf1',
                        }}>
                            <span style={{ fontSize: 12, color: '#64748b' }}>
                                Showing {((page - 1) * pageSize) + 1}–{Math.min(page * pageSize, totalCount)} of {totalCount.toLocaleString()}
                            </span>
                            <div style={{ display: 'flex', gap: 4 }}>
                                <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                                    style={{ padding: '5px 10px', border: '1px solid #e2e8f0', borderRadius: 5, fontSize: 12, cursor: 'pointer', background: page === 1 ? '#f1f5f9' : '#fff', color: page === 1 ? '#94a3b8' : '#1e293b' }}>
                                    Previous
                                </button>
                                <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                                    style={{ padding: '5px 10px', border: '1px solid #e2e8f0', borderRadius: 5, fontSize: 12, cursor: 'pointer', background: page >= totalPages ? '#f1f5f9' : '#fff', color: page >= totalPages ? '#94a3b8' : '#1e293b' }}>
                                    Next
                                </button>
                            </div>
                        </div>
                    )}
                </div>

                <div style={{ textAlign: 'center', padding: '16px 0', color: '#94a3b8', fontSize: 10 }}>
                    Quot PSE IFMIS — Audit Trail
                </div>
            </main>
        </div>
    );
}
