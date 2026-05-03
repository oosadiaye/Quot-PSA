/**
 * Override Audit — Quot PSE
 * Route: /admin/audit/overrides
 *
 * Combines two override streams for audit review:
 *   1. SOD-override role assignments (notes starts with [SOD override]).
 *   2. DualControlOverride entries (when a single user bypassed dual
 *      approval with documented justification).
 *
 * Both surface who + when + why so auditors see the decision trail
 * without spelunking through the audit log.
 */
import { useQuery } from '@tanstack/react-query';
import {
    ShieldAlert, AlertTriangle, CheckCircle2, Clock, User,
} from 'lucide-react';
import apiClient from '../../api/client';
import { ListPageShell } from '../../components/layout';

interface SODOverride {
    assignment_id: number;
    user_id: number;
    username: string;
    full_name: string;
    role_code: string;
    role_name: string;
    role_module: string;
    assigned_at: string;
    assigned_by: string | null;
    is_active: boolean;
    notes: string;
}

interface SODOverridesResponse {
    count: number;
    rows: SODOverride[];
}

interface DualControlOverride {
    id: number;
    document_type: string;
    document_id: number;
    requested_by: number | null;
    requested_by_username: string | null;
    requested_at: string;
    justification: string;
    approved_by: number | null;
    approved_by_username: string | null;
    approved_at: string | null;
    status: string;
    ip_address: string | null;
}

export default function OverrideAuditPage() {
    const { data: sod, isLoading: sodLoading } = useQuery<SODOverridesResponse>({
        queryKey: ['sod-overrides'],
        queryFn: async () =>
            (await apiClient.get('/core/role-assignments/overrides/')).data,
    });

    const { data: dualControl, isLoading: dcLoading } = useQuery<DualControlOverride[]>({
        queryKey: ['dual-control-overrides'],
        queryFn: async () => {
            const res = await apiClient.get(
                '/accounting/dual-control-overrides/',
                { params: { page_size: 500 } },
            );
            return Array.isArray(res.data) ? res.data : (res.data?.results ?? []);
        },
    });

    return (
        <ListPageShell>
                <div style={{ marginBottom: 20 }}>
                    <h1 style={{
                        fontSize: 24, fontWeight: 800, color: '#1e293b', margin: 0,
                        display: 'flex', alignItems: 'center', gap: 10,
                    }}>
                        <ShieldAlert size={22} /> Override Audit
                    </h1>
                    <p style={{ color: '#64748b', fontSize: 14, margin: '4px 0 0' }}>
                        Audit trail of SOD overrides and dual-control bypasses —
                        every authority concentration with its justification.
                    </p>
                </div>

                {/* Summary strip */}
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: 12, marginBottom: 20,
                }}>
                    <SummaryCard
                        label="SOD overrides"
                        value={sod?.count ?? 0}
                        accent="#dc2626"
                        icon={AlertTriangle}
                    />
                    <SummaryCard
                        label="Dual-control overrides"
                        value={dualControl?.length ?? 0}
                        accent="#d97706"
                        icon={Clock}
                    />
                </div>

                {/* SOD overrides */}
                <div style={{
                    background: '#fff', borderRadius: 12,
                    border: '1px solid #e8ecf1', padding: 24, marginBottom: 20,
                }}>
                    <h2 style={{
                        margin: 0, fontSize: 15, fontWeight: 800, color: '#1e293b',
                        marginBottom: 14,
                    }}>
                        SOD-override role assignments
                    </h2>

                    {sodLoading ? (
                        <div style={{ padding: 20, color: '#94a3b8' }}>Loading…</div>
                    ) : !sod || sod.rows.length === 0 ? (
                        <div style={{
                            padding: 30, textAlign: 'center', color: '#64748b',
                        }}>
                            <CheckCircle2 size={24} style={{ color: '#16a34a', marginBottom: 8 }} />
                            <div style={{ fontSize: 14, fontWeight: 600 }}>
                                No SOD overrides on record
                            </div>
                            <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>
                                All role assignments comply with the SOD matrix.
                            </div>
                        </div>
                    ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e8ecf1' }}>
                                    {['User', 'Role', 'Granted By', 'When', 'Active', 'Justification'].map(h => (
                                        <th key={h} style={{
                                            padding: '10px 14px', textAlign: 'left', fontSize: 11,
                                            fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
                                            letterSpacing: '0.5px',
                                        }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {sod.rows.map(row => (
                                    <tr key={row.assignment_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                        <td style={{ padding: '10px 14px', fontSize: 13 }}>
                                            <div style={{
                                                display: 'flex', alignItems: 'center', gap: 6,
                                                fontWeight: 600, color: '#1e293b',
                                            }}>
                                                <User size={12} style={{ color: '#94a3b8' }} />
                                                {row.username}
                                            </div>
                                            {row.full_name && (
                                                <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
                                                    {row.full_name}
                                                </div>
                                            )}
                                        </td>
                                        <td style={{ padding: '10px 14px' }}>
                                            <div style={{ fontSize: 13, fontWeight: 600 }}>
                                                {row.role_name}
                                            </div>
                                            <div style={{ fontSize: 11, color: '#94a3b8' }}>
                                                {row.role_module} · {row.role_code}
                                            </div>
                                        </td>
                                        <td style={{ padding: '10px 14px', fontSize: 13 }}>
                                            {row.assigned_by ?? '—'}
                                        </td>
                                        <td style={{
                                            padding: '10px 14px', fontSize: 12,
                                            color: '#64748b', fontFamily: 'monospace',
                                        }}>
                                            {new Date(row.assigned_at).toLocaleString('en-NG')}
                                        </td>
                                        <td style={{ padding: '10px 14px' }}>
                                            <span style={{
                                                fontSize: 10, padding: '2px 8px', borderRadius: 999,
                                                background: row.is_active ? '#f0fdf4' : '#f1f5f9',
                                                color: row.is_active ? '#166534' : '#64748b',
                                                fontWeight: 700,
                                                border: `1px solid ${row.is_active ? '#86efac' : '#cbd5e1'}`,
                                                textTransform: 'uppercase',
                                            }}>
                                                {row.is_active ? 'Active' : 'Revoked'}
                                            </span>
                                        </td>
                                        <td style={{
                                            padding: '10px 14px', fontSize: 12, color: '#475569',
                                            maxWidth: 380,
                                            whiteSpace: 'pre-wrap',
                                            wordBreak: 'break-word',
                                        }}>
                                            {row.notes}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>

                {/* Dual-control override feed (P4-T5) */}
                <div style={{
                    background: '#fff', borderRadius: 12,
                    border: '1px solid #e8ecf1', padding: 24, marginBottom: 20,
                }}>
                    <h2 style={{
                        margin: 0, fontSize: 15, fontWeight: 800, color: '#1e293b',
                        marginBottom: 14,
                    }}>
                        Dual-control overrides
                    </h2>

                    {dcLoading ? (
                        <div style={{ padding: 20, color: '#94a3b8' }}>Loading…</div>
                    ) : !dualControl || dualControl.length === 0 ? (
                        <div style={{
                            padding: 30, textAlign: 'center', color: '#64748b',
                        }}>
                            <CheckCircle2 size={24} style={{ color: '#16a34a', marginBottom: 8 }} />
                            <div style={{ fontSize: 14, fontWeight: 600 }}>
                                No dual-control overrides on record
                            </div>
                        </div>
                    ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e8ecf1' }}>
                                    {['Document', 'Requested By', 'When', 'Reviewer', 'Status', 'Justification'].map(h => (
                                        <th key={h} style={{
                                            padding: '10px 14px', textAlign: 'left', fontSize: 11,
                                            fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
                                            letterSpacing: '0.5px',
                                        }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {dualControl.map(row => (
                                    <tr key={row.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                        <td style={{ padding: '10px 14px', fontSize: 13 }}>
                                            <div style={{ fontWeight: 600, color: '#1e293b' }}>
                                                {row.document_type}
                                            </div>
                                            <div style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'monospace' }}>
                                                #{row.document_id}
                                            </div>
                                        </td>
                                        <td style={{ padding: '10px 14px', fontSize: 13 }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                                <User size={12} style={{ color: '#94a3b8' }} />
                                                {row.requested_by_username ?? '—'}
                                            </div>
                                            {row.ip_address && (
                                                <div style={{ fontSize: 10, color: '#94a3b8', fontFamily: 'monospace', marginTop: 2 }}>
                                                    {row.ip_address}
                                                </div>
                                            )}
                                        </td>
                                        <td style={{
                                            padding: '10px 14px', fontSize: 12,
                                            color: '#64748b', fontFamily: 'monospace',
                                        }}>
                                            {new Date(row.requested_at).toLocaleString('en-NG')}
                                        </td>
                                        <td style={{ padding: '10px 14px', fontSize: 13 }}>
                                            {row.approved_by_username ?? '—'}
                                            {row.approved_at && (
                                                <div style={{
                                                    fontSize: 10, color: '#94a3b8',
                                                    fontFamily: 'monospace', marginTop: 2,
                                                }}>
                                                    {new Date(row.approved_at).toLocaleString('en-NG')}
                                                </div>
                                            )}
                                        </td>
                                        <td style={{ padding: '10px 14px' }}>
                                            <DCPill status={row.status} />
                                        </td>
                                        <td style={{
                                            padding: '10px 14px', fontSize: 12,
                                            color: '#475569', maxWidth: 380,
                                            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                                        }}>
                                            {row.justification}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>

                <div style={{
                    textAlign: 'center', padding: '20px 0',
                    color: '#94a3b8', fontSize: 11,
                }}>
                    Quot PSE IFMIS — Authorisation Override Audit
                </div>
            </main>
        </div>
    );
}

function DCPill({ status }: { status: string }) {
    const up = (status ?? '').toUpperCase();
    const meta: Record<string, { bg: string; border: string; color: string }> = {
        PENDING:  { bg: '#fffbeb', border: '#fcd34d', color: '#92400e' },
        APPROVED: { bg: '#f0fdf4', border: '#86efac', color: '#166534' },
        REJECTED: { bg: '#fef2f2', border: '#fca5a5', color: '#991b1b' },
    };
    const m = meta[up] ?? meta.PENDING;
    return (
        <span style={{
            padding: '3px 10px', borderRadius: 999, fontSize: 11, fontWeight: 700,
            background: m.bg, color: m.color, border: `1px solid ${m.border}`,
            textTransform: 'uppercase', letterSpacing: '0.5px',
        }}>
            {up || 'PENDING'}
        </span>
    );
}

interface SummaryCardProps {
    label: string;
    value: number | string;
    accent: string;
    icon: typeof AlertTriangle;
}

function SummaryCard({ label, value, accent, icon }: SummaryCardProps) {
    const Icon = icon;
    return (
        <div style={{
            background: '#fff', borderRadius: 12,
            border: `1px solid ${accent}33`, padding: 16,
            display: 'flex', alignItems: 'center', gap: 12,
        }}>
            <div style={{
                padding: 10, borderRadius: 8,
                background: `${accent}14`, color: accent,
            }}>
                <Icon size={18} />
            </div>
            <div>
                <div style={{
                    fontSize: 11, fontWeight: 700, color: accent,
                    textTransform: 'uppercase', letterSpacing: '0.5px',
                }}>
                    {label}
                </div>
                <div style={{
                    fontSize: 22, fontWeight: 800, color: '#1e293b',
                    marginTop: 2, fontFamily: 'monospace',
                }}>
                    {value}
                </div>
        </ListPageShell>
    );
}
