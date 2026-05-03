/**
 * Organization Management Settings Page — Quot PSE
 * Route: /settings/organizations
 *
 * Shows all MDA organizations with their roles, user counts, and status.
 * Allows toggling MDA isolation mode (UNIFIED ↔ SEPARATED).
 */
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Building2, Shield, Landmark, Eye, LayoutGrid, Users, ToggleLeft, ToggleRight, AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import apiClient from '../../api/client';

const GOV_GREEN = '#008751';

const ROLE_CONFIG: Record<string, { label: string; color: string; bg: string; desc: string }> = {
    MDA:               { label: 'MDA',     color: '#1e40af', bg: '#dbeafe', desc: 'Standard Ministry/Dept/Agency — sees only own data in SEPARATED mode' },
    BUDGET_AUTHORITY:  { label: 'Budget',  color: '#166534', bg: '#dcfce7', desc: 'Min. of Budget & Economic Planning — manages appropriations for ALL MDAs' },
    FINANCE_AUTHORITY: { label: 'Finance', color: '#6b21a8', bg: '#f3e8ff', desc: 'Accountant General Office — manages GL, TSA, payments for ALL MDAs' },
    AUDIT_AUTHORITY:   { label: 'Audit',   color: '#c2410c', bg: '#ffedd5', desc: 'Auditor General Office — read-only access to ALL data' },
};

interface Org {
    id: number;
    name: string;
    code: string;
    short_name: string;
    org_role: string;
    is_active: boolean;
    is_oversight: boolean;
    description: string;
}

export default function OrganizationManagement() {
    const qc = useQueryClient();
    const [expandedOrg, setExpandedOrg] = useState<number | null>(null);

    // Fetch all organizations
    const { data: orgs = [], isLoading } = useQuery<Org[]>({
        queryKey: ['organizations-all'],
        queryFn: async () => {
            const res = await apiClient.get('/core/organizations/', { params: { page_size: 999 } });
            return Array.isArray(res.data) ? res.data : res.data.results || [];
        },
    });

    // Fetch isolation mode
    const { data: modeData } = useQuery({
        queryKey: ['isolation-mode'],
        queryFn: async () => {
            const res = await apiClient.get('/tenants/isolation-mode/');
            return res.data;
        },
    });

    const isSeparated = modeData?.mda_isolation_mode === 'SEPARATED';

    // Toggle isolation mode
    const toggleMode = useMutation({
        mutationFn: async () => {
            const newMode = isSeparated ? 'UNIFIED' : 'SEPARATED';
            const res = await apiClient.post('/tenants/isolation-mode/', { mda_isolation_mode: newMode });
            return res.data;
        },
        onSuccess: (data) => {
            qc.invalidateQueries({ queryKey: ['isolation-mode'] });
            // Update localStorage so sidebar/auth context picks up the change
            localStorage.setItem('mdaIsolationMode', data.mda_isolation_mode);
            // Reload to propagate the mode change across all components
            window.location.reload();
        },
        onError: (err: any) => {
            alert(err?.response?.data?.error || 'Failed to switch mode. Check console for details.');
        },
    });

    // Sync Organizations from NCoA Administrative Segments. Idempotent —
    // only segments that don't already have a linked Organization are
    // created. Useful for first-time setup and any time new MDAs are
    // added to NCoA but not yet promoted to access-control entities.
    const syncFromNcoa = useMutation({
        mutationFn: async () => {
            const res = await apiClient.post('/core/organizations/sync-from-ncoa/');
            return res.data as { created: number; skipped: number; total_segments: number };
        },
        onSuccess: (data) => {
            qc.invalidateQueries({ queryKey: ['organizations-all'] });
            const msg = data.created > 0
                ? `Created ${data.created} organization(s) from NCoA. ${data.skipped} already existed.`
                : `No new organizations to create. ${data.skipped} of ${data.total_segments} segments already had organizations.`;
            alert(msg);
        },
        onError: (err: any) => {
            alert(err?.response?.data?.error || 'Sync failed. Check console for details.');
        },
    });

    // Fetch users for expanded org
    const { data: orgUsers = [] } = useQuery({
        queryKey: ['org-users', expandedOrg],
        queryFn: async () => {
            const res = await apiClient.get(`/core/organizations/${expandedOrg}/users/`);
            return Array.isArray(res.data) ? res.data : res.data.results || [];
        },
        enabled: !!expandedOrg,
    });

    // Group orgs
    const oversightOrgs = orgs.filter(o => o.is_oversight);
    const mdaOrgs = orgs.filter(o => !o.is_oversight);

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '32px' }}>
                <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#1e293b', marginBottom: 4 }}>
                    Organization Management (MDAs)
                </h1>
                <p style={{ color: '#64748b', fontSize: 14, marginBottom: 28 }}>
                    Manage ministries, departments, and agencies. Control who sees what data.
                </p>

                {/* Isolation Mode Toggle */}
                <div style={{
                    background: '#fff', borderRadius: 12, border: '1px solid #e8ecf1',
                    padding: '20px 24px', marginBottom: 24,
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}>
                    <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                            {isSeparated
                                ? <Shield size={18} color="#166534" />
                                : <LayoutGrid size={18} color="#64748b" />}
                            <span style={{ fontWeight: 700, fontSize: 15, color: '#1e293b' }}>
                                MDA Isolation Mode: {isSeparated ? 'SEPARATED' : 'UNIFIED'}
                            </span>
                        </div>
                        <p style={{ color: '#64748b', fontSize: 13, margin: 0 }}>
                            {isSeparated
                                ? 'Each MDA only sees their own data. Oversight offices (AG, Budget) see all MDAs.'
                                : 'All users see all MDAs data. Organizations exist for reporting and identification only.'}
                        </p>
                    </div>
                    <button
                        onClick={() => toggleMode.mutate()}
                        disabled={toggleMode.isPending}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 8,
                            padding: '10px 20px', borderRadius: 8, border: 'none',
                            background: isSeparated ? '#fef2f2' : GOV_GREEN,
                            color: isSeparated ? '#dc2626' : '#fff',
                            fontWeight: 600, fontSize: 13, cursor: 'pointer',
                        }}
                    >
                        {isSeparated ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
                        {toggleMode.isPending ? 'Switching...' : isSeparated ? 'Switch to UNIFIED' : 'Switch to SEPARATED'}
                    </button>
                </div>

                {isSeparated && (
                    <div style={{
                        background: '#fffbeb', border: '1px solid #fbbf24', borderRadius: 8,
                        padding: '12px 16px', marginBottom: 24, display: 'flex', gap: 8, alignItems: 'flex-start',
                    }}>
                        <AlertTriangle size={16} color="#b45309" style={{ flexShrink: 0, marginTop: 2 }} />
                        <div style={{ fontSize: 13, color: '#92400e' }}>
                            <strong>SEPARATED mode is active.</strong> Each MDA user can only see their own ministry's budgets,
                            payment vouchers, procurement, and revenue. Make sure all users are assigned to their correct organization below.
                        </div>
                    </div>
                )}

                {/* Oversight Offices */}
                <h2 style={{ fontSize: 16, fontWeight: 700, color: '#1e293b', marginBottom: 12 }}>
                    Oversight Offices ({oversightOrgs.length})
                </h2>
                <p style={{ fontSize: 13, color: '#64748b', marginBottom: 12 }}>
                    These offices have cross-MDA access — they can see data from all ministries.
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 28 }}>
                    {oversightOrgs.map(org => {
                        const rc = ROLE_CONFIG[org.org_role] || ROLE_CONFIG.MDA;
                        return (
                            <div key={org.id} style={{
                                background: '#fff', borderRadius: 12, border: `2px solid ${rc.bg}`,
                                padding: 16, cursor: 'pointer',
                                outline: expandedOrg === org.id ? `2px solid ${rc.color}` : 'none',
                            }} onClick={() => setExpandedOrg(expandedOrg === org.id ? null : org.id)}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                                    <span style={{
                                        padding: '2px 8px', borderRadius: 4, fontSize: 10,
                                        fontWeight: 700, background: rc.bg, color: rc.color,
                                    }}>{rc.label}</span>
                                    {org.is_active
                                        ? <CheckCircle2 size={14} color="#22c55e" />
                                        : <span style={{ fontSize: 10, color: '#ef4444' }}>Inactive</span>}
                                </div>
                                <div style={{ fontWeight: 600, fontSize: 14, color: '#1e293b', marginBottom: 4 }}>{org.name}</div>
                                <div style={{ fontSize: 11, color: '#94a3b8' }}>{rc.desc}</div>
                            </div>
                        );
                    })}
                </div>

                {/* MDA List header — section title on the left, Sync from
                    NCoA button on the right so admins can populate the
                    organization list from existing Administrative Segments
                    without re-entering them by hand. */}
                <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    marginBottom: 12, gap: 16, flexWrap: 'wrap',
                }}>
                    <h2 style={{ fontSize: 16, fontWeight: 700, color: '#1e293b', margin: 0 }}>
                        Ministries, Departments & Agencies ({mdaOrgs.length})
                    </h2>
                    <button
                        onClick={() => syncFromNcoa.mutate()}
                        disabled={syncFromNcoa.isPending}
                        title="Create one Organization for every NCoA Administrative Segment that doesn't already have one. Idempotent — safe to re-run."
                        style={{
                            display: 'inline-flex', alignItems: 'center', gap: 8,
                            padding: '0.5rem 1rem',
                            background: '#16a34a',
                            color: '#ffffff',
                            border: '1px solid #16a34a',
                            borderRadius: 8,
                            fontSize: 13,
                            fontWeight: 600,
                            cursor: syncFromNcoa.isPending ? 'wait' : 'pointer',
                            opacity: syncFromNcoa.isPending ? 0.7 : 1,
                            boxShadow: '0 2px 6px rgba(22,163,74,0.35)',
                            transition: 'background 0.15s, box-shadow 0.15s',
                        }}
                        onMouseEnter={(e) => { if (!syncFromNcoa.isPending) (e.currentTarget as HTMLButtonElement).style.background = '#15803d'; }}
                        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#16a34a'; }}
                    >
                        <RefreshCw size={14} className={syncFromNcoa.isPending ? 'animate-spin' : ''} />
                        {syncFromNcoa.isPending ? 'Syncing…' : 'Sync from NCoA'}
                    </button>
                </div>
                <p style={{ fontSize: 13, color: '#64748b', marginBottom: 12 }}>
                    {isSeparated
                        ? 'Each MDA below operates as an independent branch — users only see their own data.'
                        : 'In UNIFIED mode, all users can see all MDA data. Click an MDA to see assigned users.'}
                </p>

                <div style={{
                    background: '#fff', borderRadius: 12, border: '1px solid #e8ecf1', overflow: 'hidden',
                }}>
                    {isLoading ? (
                        <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>Loading...</div>
                    ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '2px solid #e8ecf1' }}>
                                    <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>Code</th>
                                    <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>Organization Name</th>
                                    <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>Role</th>
                                    <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {mdaOrgs.map(org => {
                                    const rc = ROLE_CONFIG[org.org_role] || ROLE_CONFIG.MDA;
                                    const isExpanded = expandedOrg === org.id;
                                    // Use the long-form Fragment so we can put
                                    // the React key on the outer wrapper that
                                    // .map() returns. Shorthand <>...</> can't
                                    // accept a key prop — that's what React
                                    // was warning about in the console.
                                    return (
                                        <React.Fragment key={org.id}>
                                            <tr
                                                onClick={() => setExpandedOrg(isExpanded ? null : org.id)}
                                                style={{
                                                    borderBottom: '1px solid #f1f5f9', cursor: 'pointer',
                                                    background: isExpanded ? '#f8fafc' : '',
                                                }}
                                                onMouseEnter={e => { if (!isExpanded) e.currentTarget.style.background = '#fafbfc'; }}
                                                onMouseLeave={e => { if (!isExpanded) e.currentTarget.style.background = ''; }}
                                            >
                                                <td style={{ padding: '10px 16px', fontSize: 13, fontFamily: 'monospace', color: '#64748b' }}>{org.code}</td>
                                                <td style={{ padding: '10px 16px', fontSize: 14, fontWeight: 500, color: '#1e293b' }}>{org.name}</td>
                                                <td style={{ padding: '10px 16px' }}>
                                                    <span style={{
                                                        padding: '2px 8px', borderRadius: 4, fontSize: 10,
                                                        fontWeight: 700, background: rc.bg, color: rc.color,
                                                    }}>{rc.label}</span>
                                                </td>
                                                <td style={{ padding: '10px 16px' }}>
                                                    {org.is_active
                                                        ? <span style={{ color: '#22c55e', fontSize: 12, fontWeight: 600 }}>Active</span>
                                                        : <span style={{ color: '#ef4444', fontSize: 12, fontWeight: 600 }}>Inactive</span>}
                                                </td>
                                            </tr>
                                            {isExpanded && (
                                                <tr>
                                                    <td colSpan={4} style={{ padding: '0 16px 16px', background: '#f8fafc' }}>
                                                        <div style={{
                                                            background: '#fff', borderRadius: 8, border: '1px solid #e2e8f0',
                                                            padding: 16, marginTop: 8,
                                                        }}>
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                                                                <Users size={14} color="#64748b" />
                                                                <span style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>
                                                                    Assigned Users ({orgUsers.length})
                                                                </span>
                                                            </div>
                                                            {orgUsers.length === 0 ? (
                                                                <p style={{ color: '#94a3b8', fontSize: 13, margin: 0 }}>
                                                                    No users assigned. Use User Management to assign staff to this MDA.
                                                                </p>
                                                            ) : (
                                                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                                                                    {orgUsers.map((ua: any) => (
                                                                        <div key={ua.id} style={{
                                                                            background: '#f1f5f9', borderRadius: 6, padding: '6px 12px',
                                                                            fontSize: 12, color: '#1e293b',
                                                                        }}>
                                                                            <strong>{ua.username}</strong>
                                                                            <span style={{ color: '#94a3b8', marginLeft: 6 }}>[{ua.per_org_role}]</span>
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            )}
                                                        </div>
                                                    </td>
                                                </tr>
                                            )}
                                        </React.Fragment>
                                    );
                                })}
                            </tbody>
                        </table>
                    )}
                </div>

                <div style={{ textAlign: 'center', padding: '20px 0', color: '#94a3b8', fontSize: 11 }}>
                    Quot PSE IFMIS — Organization Management
                </div>
            </main>
        </div>
    );
}
