import React, { useState } from 'react';
import { formatDate } from '@/utils/date';
import { useDialog } from '../hooks/useDialog';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Users, UserPlus, Shield, Eye, Edit2, Trash2, Key,
    Search, RefreshCw, CheckCircle, XCircle, X, Save,
} from 'lucide-react';
import apiClient from '../api/client';
import Sidebar from '../components/Sidebar';
import BackButton from '../components/BackButton';
import LoadingScreen from '../components/common/LoadingScreen';

interface TenantUser {
    id: number;
    username: string;
    email: string;
    first_name: string;
    last_name: string;
    is_active: boolean;
    role: string;
    role_display: string;
    groups: string[];
    employee: { id: number; employee_number: string; department: string | null; position: string | null } | null;
    organizations: UserOrgMembership[];
    created_at: string;
}

/** An MDA a user is assigned to, as the list API returns it. */
interface UserOrgMembership {
    organization: number;
    code: string;
    name: string;
    per_org_role: string;
    is_default: boolean;
}

/** An MDA that can be assigned (active organizations only). */
interface OrgOption {
    id: number;
    code: string;
    name: string;
}

/** What the create/update endpoints accept for one MDA. */
interface OrgAssignment {
    organization: number;
    per_org_role: string;
}

interface AvailableGroup {
    id: number;
    name: string;
}

// Mirrors core.UserOrganization.PER_ORG_ROLE_CHOICES.
const PER_ORG_ROLES = [
    { value: 'admin', label: 'MDA Admin' },
    { value: 'manager', label: 'Manager' },
    { value: 'officer', label: 'Officer' },
    { value: 'viewer', label: 'Read-only' },
];
const DEFAULT_PER_ORG_ROLE = 'officer';

/** Flatten a DRF error body (string, list, or {field: [msgs]}) into one sentence. */
const apiErrorText = (data: any, fallback: string): string => {
    if (!data) return fallback;
    if (typeof data === 'string') return data;
    if (typeof data.error === 'string') return data.error;
    if (typeof data.detail === 'string') return data.detail;
    // Our own messages already name what is wrong; DRF's generic ones
    // ("This field may not be blank.") need the field name to be useful.
    const SELF_EXPLANATORY = new Set(['organizations', 'default_organization', 'non_field_errors']);
    const humanise = (key: string) => key.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
    const parts: string[] = [];
    const walk = (v: any, field?: string) => {
        if (typeof v === 'string') parts.push(field && !SELF_EXPLANATORY.has(field) ? `${humanise(field)}: ${v}` : v);
        else if (Array.isArray(v)) v.forEach(x => walk(x, field));
        else if (v && typeof v === 'object') Object.entries(v).forEach(([k, x]) => walk(x, /^\d+$/.test(k) ? field : k));
    };
    walk(data);
    return parts.length ? parts.join(' ') : fallback;
};

const ROLE_OPTIONS = [
    { value: 'senior_manager', label: 'Senior Manager', color: '#8b5cf6' },
    { value: 'manager', label: 'Mid-Level Manager', color: '#2471a3' },
    { value: 'user', label: 'Standard User', color: 'var(--color-success)' },
    { value: 'viewer', label: 'Read-Only Viewer', color: 'var(--color-text-muted)' },
];

const getRoleColor = (role: string) => {
    const opt = ROLE_OPTIONS.find(r => r.value === role);
    return opt?.color || 'var(--color-text-muted)';
};

const thStyle: React.CSSProperties = {
    padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600,
    textTransform: 'uppercase', color: 'var(--color-text-muted)', textAlign: 'left',
};
const tdStyle: React.CSSProperties = {
    padding: '1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text)',
};
const labelStyle: React.CSSProperties = {
    display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)',
    fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)',
};
const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.625rem', border: '2.5px solid var(--color-border)',
    borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)',
    fontSize: 'var(--text-sm)',
};
const overlayStyle: React.CSSProperties = {
    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
    background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center',
    justifyContent: 'center', zIndex: 1000,
};

const UserManagement = () => {
    const { showConfirm } = useDialog();
    const queryClient = useQueryClient();
    const [search, setSearch] = useState('');
    const [roleFilter, setRoleFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [editUser, setEditUser] = useState<TenantUser | null>(null);
    const [showPermsModal, setShowPermsModal] = useState<number | null>(null);
    const [showResetPassword, setShowResetPassword] = useState<TenantUser | null>(null);

    const { data: users = [], isLoading } = useQuery<TenantUser[]>({
        queryKey: ['tenant-users'],
        queryFn: async () => {
            const res = await apiClient.get('/core/tenant-users/');
            return res.data;
        },
    });

    const { data: availableGroups = [] } = useQuery<AvailableGroup[]>({
        queryKey: ['available-groups'],
        queryFn: async () => {
            const res = await apiClient.get('/core/tenant-users/available_groups/');
            return res.data;
        },
    });

    // Active MDAs a user can be assigned to. The endpoint may paginate or not.
    const { data: orgOptions = [], status: orgQueryStatus } = useQuery<OrgOption[]>({
        queryKey: ['org-options'],
        queryFn: async () => {
            const res = await apiClient.get('/core/organizations/');
            const rows: any[] = Array.isArray(res.data) ? res.data : (res.data?.results ?? []);
            return rows
                .filter(o => o.is_active)
                .map(o => ({ id: o.id, code: o.code, name: o.name }));
        },
    });
    const orgStatus: OrgOptionsStatus =
        orgQueryStatus === 'success' ? 'ready' : orgQueryStatus === 'error' ? 'error' : 'loading';

    const deactivateMutation = useMutation({
        mutationFn: (id: number) => apiClient.delete(`/core/tenant-users/${id}/`),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tenant-users'] }),
    });

    if (isLoading) return <LoadingScreen message="Loading user management..." />;

    const filtered = users.filter((u) => {
        const matchesSearch = !search ||
            u.username.toLowerCase().includes(search.toLowerCase()) ||
            u.email.toLowerCase().includes(search.toLowerCase()) ||
            `${u.first_name} ${u.last_name}`.toLowerCase().includes(search.toLowerCase()) ||
            u.employee?.employee_number?.toLowerCase().includes(search.toLowerCase());
        const matchesRole = !roleFilter || u.role === roleFilter;
        const matchesStatus = !statusFilter ||
            (statusFilter === 'active' && u.is_active) ||
            (statusFilter === 'inactive' && !u.is_active);
        return matchesSearch && matchesRole && matchesStatus;
    });

    const totalUsers = users.length;
    const activeUsers = users.filter(u => u.is_active).length;
    const inactiveUsers = users.filter(u => !u.is_active).length;
    const linkedEmployees = users.filter(u => u.employee).length;

    const summaryCards = [
        { name: 'Total Users', value: totalUsers, icon: Users, color: 'var(--color-primary)', desc: 'All tenant users' },
        { name: 'Active Users', value: activeUsers, icon: CheckCircle, color: 'var(--color-success)', desc: 'Currently active accounts' },
        { name: 'Inactive Users', value: inactiveUsers, icon: XCircle, color: 'var(--color-error)', desc: 'Deactivated accounts' },
        { name: 'Linked Employees', value: linkedEmployees, icon: Shield, color: '#2471a3', desc: 'Users with HRM records' },
    ];

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <header style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    marginBottom: '2.5rem', borderBottom: '1px solid var(--color-border)',
                    paddingBottom: '1.5rem',
                }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <BackButton />
                        <h1 style={{ fontSize: 'var(--text-2xl)', marginBottom: 0, color: 'var(--color-text)' }}>User Management</h1>
                        <p style={{ color: 'var(--color-text-muted)', margin: 0 }}>Manage users, roles, and permissions for this organization.</p>
                    </div>
                    <button
                        className="btn btn-primary"
                        onClick={() => setShowCreateModal(true)}
                        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
                    >
                        <UserPlus size={16} /> Add User
                    </button>
                </header>

                {/* Summary Cards */}
                <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: '1.5rem', marginBottom: '2rem',
                }}>
                    {summaryCards.map((card) => (
                        <div key={card.name} className="card glass animate-fade" style={{ padding: '1.5rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                                <div style={{
                                    width: '40px', height: '40px', borderRadius: '10px',
                                    background: `${card.color}15`, color: card.color,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                }}>
                                    <card.icon size={20} />
                                </div>
                            </div>
                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600, letterSpacing: '0.05em', marginBottom: '0.25rem' }}>
                                {card.name}
                            </div>
                            <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: '0.5rem' }}>
                                {card.value}
                            </div>
                            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: 0 }}>{card.desc}</p>
                        </div>
                    ))}
                </div>

                {/* Role Breakdown */}
                <div style={{
                    display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap',
                }}>
                    {ROLE_OPTIONS.map(r => {
                        const count = users.filter(u => u.role === r.value && u.is_active).length;
                        return (
                            <div key={r.value} style={{
                                display: 'flex', alignItems: 'center', gap: '0.5rem',
                                padding: '0.5rem 1rem', borderRadius: '8px',
                                background: `${r.color}10`, border: `1px solid ${r.color}30`,
                            }}>
                                <span style={{
                                    width: '8px', height: '8px', borderRadius: '50%', background: r.color,
                                }} />
                                <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)' }}>{r.label}</span>
                                <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: r.color }}>{count}</span>
                            </div>
                        );
                    })}
                </div>

                {/* Filters */}
                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                    <div style={{ position: 'relative', flex: '1 1 250px', maxWidth: '350px' }}>
                        <Search size={16} style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                        <input
                            type="text"
                            placeholder="Search by name, username, email..."
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                            style={{ ...inputStyle, paddingLeft: '2.25rem' }}
                        />
                    </div>
                    <select value={roleFilter} onChange={e => setRoleFilter(e.target.value)} style={inputStyle}>
                        <option value="">All Roles</option>
                        {ROLE_OPTIONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                    </select>
                    <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={inputStyle}>
                        <option value="">All Status</option>
                        <option value="active">Active</option>
                        <option value="inactive">Inactive</option>
                    </select>
                    <button
                        className="btn btn-outline"
                        onClick={() => queryClient.invalidateQueries({ queryKey: ['tenant-users'] })}
                        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.625rem 1rem' }}
                    >
                        <RefreshCw size={16} /> Refresh
                    </button>
                </div>

                {/* User Table */}
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                <th style={thStyle}>User</th>
                                <th style={thStyle}>Role</th>
                                <th style={thStyle}>Groups</th>
                                <th style={thStyle}>MDAs</th>
                                <th style={thStyle}>Employee</th>
                                <th style={thStyle}>Status</th>
                                <th style={thStyle}>Created</th>
                                <th style={{ ...thStyle, textAlign: 'right' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.length === 0 ? (
                                <tr>
                                    <td colSpan={8} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <Users size={48} style={{ margin: '0 auto 1rem', opacity: 0.5, display: 'block' }} />
                                        <p style={{ margin: 0 }}>No users found</p>
                                    </td>
                                </tr>
                            ) : filtered.map(u => (
                                <tr key={u.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                    <td style={tdStyle}>
                                        <div style={{ fontWeight: 600, marginBottom: '0.15rem' }}>
                                            {u.first_name || u.last_name ? `${u.first_name} ${u.last_name}`.trim() : u.username}
                                        </div>
                                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                            {u.username} &middot; {u.email}
                                        </div>
                                    </td>
                                    <td style={tdStyle}>
                                        <span style={{
                                            padding: '0.2rem 0.6rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 700,
                                            background: `${getRoleColor(u.role)}20`, color: getRoleColor(u.role),
                                        }}>
                                            {u.role_display || u.role}
                                        </span>
                                    </td>
                                    <td style={tdStyle}>
                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                                            {u.groups.length > 0 ? u.groups.map(g => (
                                                <span key={g} style={{
                                                    padding: '0.15rem 0.4rem', borderRadius: '4px', fontSize: 'var(--text-xs)',
                                                    background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                                                    color: 'var(--color-text-muted)',
                                                }}>{g}</span>
                                            )) : (
                                                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>No groups</span>
                                            )}
                                        </div>
                                    </td>
                                    <td style={tdStyle} data-testid={`mdas-${u.username}`}>
                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                                            {(u.organizations ?? []).length > 0 ? u.organizations.map(o => (
                                                <span key={o.organization} title={`${o.name} — ${o.per_org_role}${o.is_default ? ' (default)' : ''}`} style={{
                                                    padding: '0.15rem 0.4rem', borderRadius: '4px', fontSize: 'var(--text-xs)',
                                                    background: o.is_default ? 'var(--color-primary)15' : 'var(--color-surface)',
                                                    border: `1px solid ${o.is_default ? 'var(--color-primary)' : 'var(--color-border)'}`,
                                                    color: o.is_default ? 'var(--color-primary)' : 'var(--color-text-muted)',
                                                    fontWeight: o.is_default ? 700 : 400,
                                                }}>{o.code}{o.is_default ? ' ★' : ''}</span>
                                            )) : (
                                                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>No MDA</span>
                                            )}
                                        </div>
                                    </td>
                                    <td style={tdStyle}>
                                        {u.employee ? (
                                            <div>
                                                <div style={{ fontWeight: 600, fontSize: 'var(--text-xs)' }}>{u.employee.employee_number}</div>
                                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                    {[u.employee.department, u.employee.position].filter(Boolean).join(' / ') || 'No dept/pos'}
                                                </div>
                                            </div>
                                        ) : (
                                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>Not linked</span>
                                        )}
                                    </td>
                                    <td style={tdStyle}>
                                        <span style={{
                                            display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                            padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 700,
                                            background: u.is_active ? 'var(--color-success)20' : 'var(--color-error)20',
                                            color: u.is_active ? 'var(--color-success)' : 'var(--color-error)',
                                        }}>
                                            {u.is_active ? <CheckCircle size={12} /> : <XCircle size={12} />}
                                            {u.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </td>
                                    <td style={{ ...tdStyle, fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                        {u.created_at ? formatDate(u.created_at) : '-'}
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'right' }}>
                                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.25rem' }}>
                                            <button onClick={() => setShowPermsModal(u.id)} title="View Permissions"
                                                style={{
                                                    padding: '0.375rem', background: 'transparent', border: '1px solid var(--color-border)',
                                                    borderRadius: '6px', cursor: 'pointer', color: 'var(--color-text-muted)',
                                                }}>
                                                <Eye size={14} />
                                            </button>
                                            <button onClick={() => setEditUser(u)} title="Edit User"
                                                style={{
                                                    padding: '0.375rem', background: 'transparent', border: '1px solid var(--color-border)',
                                                    borderRadius: '6px', cursor: 'pointer', color: 'var(--color-text-muted)',
                                                }}>
                                                <Edit2 size={14} />
                                            </button>
                                            <button onClick={() => setShowResetPassword(u)} title="Reset Password"
                                                style={{
                                                    padding: '0.375rem', background: 'transparent', border: '1px solid var(--color-border)',
                                                    borderRadius: '6px', cursor: 'pointer', color: 'var(--color-text-muted)',
                                                }}>
                                                <Key size={14} />
                                            </button>
                                            {u.is_active && (
                                                <button
                                                    onClick={async () => {
                                                        if (await showConfirm(`Deactivate user "${u.username}"? They will lose access to this tenant.`))
                                                            deactivateMutation.mutate(u.id);
                                                    }}
                                                    title="Deactivate"
                                                    style={{
                                                        padding: '0.375rem', background: 'transparent', border: '1px solid var(--color-border)',
                                                        borderRadius: '6px', cursor: 'pointer', color: 'var(--color-error)',
                                                    }}>
                                                    <Trash2 size={14} />
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Create User Modal */}
                {showCreateModal && (
                    <CreateUserModal
                        groups={availableGroups}
                        orgOptions={orgOptions}
                        orgStatus={orgStatus}
                        onClose={() => setShowCreateModal(false)}
                        onSuccess={() => {
                            setShowCreateModal(false);
                            queryClient.invalidateQueries({ queryKey: ['tenant-users'] });
                        }}
                    />
                )}

                {/* Edit User Modal */}
                {editUser && (
                    <EditUserModal
                        user={editUser}
                        groups={availableGroups}
                        orgOptions={orgOptions}
                        orgStatus={orgStatus}
                        onClose={() => setEditUser(null)}
                        onSuccess={() => {
                            setEditUser(null);
                            queryClient.invalidateQueries({ queryKey: ['tenant-users'] });
                        }}
                    />
                )}

                {/* Permissions Modal */}
                {showPermsModal !== null && (
                    <PermissionsModal userId={showPermsModal} onClose={() => setShowPermsModal(null)} />
                )}

                {/* Reset Password Modal */}
                {showResetPassword && (
                    <ResetPasswordModal user={showResetPassword} onClose={() => setShowResetPassword(null)} />
                )}
            </main>
        </div>
    );
};

// ── MDA assignment field ───────────────────────────────────────────
//
// Which MDA(s) a user belongs to decides what the app scopes their data to
// (the active-MDA switcher and the per-MDA filters read these memberships).
// One MDA is the default — the one selected automatically at sign-in.

type OrgOptionsStatus = 'loading' | 'ready' | 'error';

const MdaAssignmentField: React.FC<{
    options: OrgOption[];
    status: OrgOptionsStatus;
    assignments: OrgAssignment[];
    defaultOrg: number | null;
    onChange: (assignments: OrgAssignment[], defaultOrg: number | null) => void;
}> = ({ options, status, assignments, defaultOrg, onChange }) => {
    const assigned = new Map(assignments.map(a => [a.organization, a]));
    // A tenant can have hundreds of MDAs (OAG has ~200), so the list is searchable.
    const [query, setQuery] = useState('');
    const needle = query.trim().toLowerCase();
    const visible = needle
        ? options.filter(o => o.code.toLowerCase().includes(needle) || o.name.toLowerCase().includes(needle))
        : options;
    const optionById = new Map(options.map(o => [o.id, o]));

    const toggle = (id: number, checked: boolean) => {
        if (checked) {
            // The first MDA ticked becomes the default automatically.
            onChange([...assignments, { organization: id, per_org_role: DEFAULT_PER_ORG_ROLE }], defaultOrg ?? id);
            return;
        }
        const next = assignments.filter(a => a.organization !== id);
        onChange(next, defaultOrg === id ? (next[0]?.organization ?? null) : defaultOrg);
    };

    const setRole = (id: number, role: string) =>
        onChange(assignments.map(a => (a.organization === id ? { ...a, per_org_role: role } : a)), defaultOrg);

    const hint = { fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' } as const;

    return (
        <div style={{ marginTop: '1rem' }} data-testid="mda-field">
            <label style={labelStyle}>MDA Assignment (optional)</label>
            {status === 'loading' && <div style={hint}>Loading MDAs…</div>}
            {status === 'error' && (
                <div role="alert" style={{ ...hint, color: 'var(--color-error)' }}>
                    Could not load the MDA list. Existing MDA assignments will be left unchanged.
                </div>
            )}
            {status === 'ready' && options.length === 0 && (
                <div style={hint}>No MDAs are set up yet. Add them under Settings → Organizations (MDAs).</div>
            )}
            {status === 'ready' && assignments.length > 0 && (
                <div data-testid="mda-selected" style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginBottom: '0.5rem' }}>
                    {assignments.map(a => {
                        const o = optionById.get(a.organization);
                        return (
                            <span key={a.organization} style={{
                                display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                padding: '0.15rem 0.4rem', borderRadius: '999px', fontSize: 'var(--text-xs)',
                                border: `1px solid ${defaultOrg === a.organization ? 'var(--color-primary)' : 'var(--color-border)'}`,
                                color: defaultOrg === a.organization ? 'var(--color-primary)' : 'var(--color-text)',
                                fontWeight: defaultOrg === a.organization ? 700 : 400,
                            }}>
                                {o ? o.code : `#${a.organization}`}{defaultOrg === a.organization ? ' ★' : ''}
                                <button type="button" aria-label={`Remove ${o ? o.code : a.organization}`}
                                    onClick={() => toggle(a.organization, false)}
                                    style={{ border: 'none', background: 'transparent', cursor: 'pointer', padding: 0, lineHeight: 1, color: 'var(--color-text-muted)' }}>
                                    <X size={12} />
                                </button>
                            </span>
                        );
                    })}
                </div>
            )}
            {status === 'ready' && options.length > 8 && (
                <input type="search" aria-label="Search MDAs" placeholder="Search MDAs by code or name…"
                    value={query} onChange={e => setQuery(e.target.value)}
                    style={{ ...inputStyle, marginBottom: '0.5rem' }} />
            )}
            {status === 'ready' && options.length > 0 && (
                <div style={{
                    maxHeight: '170px', overflowY: 'auto', padding: '0.25rem 0.5rem',
                    borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                }}>
                    {visible.length === 0 && (
                        <div style={{ ...hint, padding: '0.4rem 0' }}>No MDA matches “{query}”.</div>
                    )}
                    {visible.map(o => {
                        const a = assigned.get(o.id);
                        return (
                            <div key={o.id} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.3rem 0' }}>
                                <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flex: 1, minWidth: 0, fontSize: 'var(--text-xs)', color: 'var(--color-text)', cursor: 'pointer' }}>
                                    <input type="checkbox" checked={!!a} onChange={e => toggle(o.id, e.target.checked)} />
                                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.code} — {o.name}</span>
                                </label>
                                {a && (
                                    <>
                                        <select aria-label={`Role in ${o.code}`} value={a.per_org_role}
                                            onChange={e => setRole(o.id, e.target.value)}
                                            style={{ ...inputStyle, width: 'auto', padding: '0.2rem 0.4rem' }}>
                                            {PER_ORG_ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                                        </select>
                                        <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: 'var(--text-xs)', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                                            <input type="radio" name="default-mda" aria-label={`Default MDA ${o.code}`}
                                                checked={defaultOrg === o.id} onChange={() => onChange(assignments, o.id)} />
                                            Default
                                        </label>
                                    </>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

// ── Create User Modal ──────────────────────────────────────────────

const CreateUserModal: React.FC<{
    groups: AvailableGroup[];
    orgOptions: OrgOption[];
    orgStatus: OrgOptionsStatus;
    onClose: () => void;
    onSuccess: () => void;
}> = ({ groups, orgOptions, orgStatus, onClose, onSuccess }) => {
    const [form, setForm] = useState({
        username: '', email: '', first_name: '', last_name: '',
        password: '', role: 'user', link_employee: false,
    });
    const [selectedGroups, setSelectedGroups] = useState<number[]>([]);
    const [assignments, setAssignments] = useState<OrgAssignment[]>([]);
    const [defaultOrg, setDefaultOrg] = useState<number | null>(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        try {
            await apiClient.post('/core/tenant-users/', {
                ...form,
                group_ids: selectedGroups,
                organizations: assignments,
                default_organization: assignments.length ? defaultOrg : null,
            });
            onSuccess();
        } catch (err: any) {
            setError(apiErrorText(err.response?.data, 'Failed to create user'));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={overlayStyle} onClick={onClose}>
            <div className="card" style={{ width: '600px', padding: '2rem' }} onClick={e => e.stopPropagation()}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                    <h2 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <UserPlus size={20} /> Create New User
                    </h2>
                    <button onClick={onClose} style={{
                        padding: '0.375rem', background: 'transparent', border: '1px solid var(--color-border)',
                        borderRadius: '6px', cursor: 'pointer', color: 'var(--color-text-muted)',
                    }}>
                        <X size={18} />
                    </button>
                </div>

                {error && (
                    <div style={{
                        marginBottom: '1rem', padding: '0.75rem', borderRadius: '8px',
                        background: 'var(--color-error)10', border: '1px solid var(--color-error)30',
                        color: 'var(--color-error)', fontSize: 'var(--text-sm)',
                    }}>{error}</div>
                )}

                <form onSubmit={handleSubmit}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                        <div>
                            <label style={labelStyle}>Username<span className="required-mark"> *</span></label>
                            <input required value={form.username}
                                onChange={e => setForm({ ...form, username: e.target.value })}
                                className="input" placeholder="e.g. john.doe" />
                        </div>
                        <div>
                            <label style={labelStyle}>Email<span className="required-mark"> *</span></label>
                            <input type="email" required value={form.email}
                                onChange={e => setForm({ ...form, email: e.target.value })}
                                className="input" placeholder="john@example.com" />
                        </div>
                        <div>
                            <label style={labelStyle}>First Name</label>
                            <input value={form.first_name}
                                onChange={e => setForm({ ...form, first_name: e.target.value })}
                                className="input" />
                        </div>
                        <div>
                            <label style={labelStyle}>Last Name</label>
                            <input value={form.last_name}
                                onChange={e => setForm({ ...form, last_name: e.target.value })}
                                className="input" />
                        </div>
                        <div style={{ gridColumn: '1 / -1' }}>
                            <label style={labelStyle}>Password<span className="required-mark"> *</span></label>
                            <input type="password" required value={form.password}
                                onChange={e => setForm({ ...form, password: e.target.value })}
                                className="input" />
                        </div>
                        <div>
                            <label style={labelStyle}>Role</label>
                            <select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} className="input">
                                {ROLE_OPTIONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                            </select>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: '0.25rem' }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>
                                <input type="checkbox" checked={form.link_employee}
                                    onChange={e => setForm({ ...form, link_employee: e.target.checked })} />
                                Create HRM Employee record
                            </label>
                        </div>
                    </div>

                    {groups.length > 0 && (
                        <div style={{ marginTop: '1rem' }}>
                            <label style={labelStyle}>Permission Groups (optional — auto-assigned from role if empty)</label>
                            <div style={{
                                display: 'flex', flexWrap: 'wrap', gap: '0.75rem', maxHeight: '100px',
                                overflowY: 'auto', padding: '0.5rem', borderRadius: '8px',
                                border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                            }}>
                                {groups.map(g => (
                                    <label key={g.id} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: 'var(--text-xs)', color: 'var(--color-text)', cursor: 'pointer' }}>
                                        <input type="checkbox" checked={selectedGroups.includes(g.id)}
                                            onChange={e => setSelectedGroups(e.target.checked
                                                ? [...selectedGroups, g.id]
                                                : selectedGroups.filter(id => id !== g.id)
                                            )} />
                                        {g.name}
                                    </label>
                                ))}
                            </div>
                        </div>
                    )}

                    <MdaAssignmentField options={orgOptions} status={orgStatus}
                        assignments={assignments} defaultOrg={defaultOrg}
                        onChange={(next, nextDefault) => { setAssignments(next); setDefaultOrg(nextDefault); }} />

                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.5rem' }}>
                        <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={loading}
                            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Save size={16} /> {loading ? 'Creating...' : 'Create User'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

// ── Edit User Modal ────────────────────────────────────────────────

const EditUserModal: React.FC<{
    user: TenantUser;
    groups: AvailableGroup[];
    orgOptions: OrgOption[];
    orgStatus: OrgOptionsStatus;
    onClose: () => void;
    onSuccess: () => void;
}> = ({ user, groups, orgOptions, orgStatus, onClose, onSuccess }) => {
    const [form, setForm] = useState({
        email: user.email,
        first_name: user.first_name,
        last_name: user.last_name,
        role: user.role,
        is_active: user.is_active,
    });
    const [selectedGroups, setSelectedGroups] = useState<number[]>(
        groups.filter(g => user.groups.includes(g.name)).map(g => g.id)
    );
    const [assignments, setAssignments] = useState<OrgAssignment[]>(
        (user.organizations ?? []).map(o => ({ organization: o.organization, per_org_role: o.per_org_role }))
    );
    const [defaultOrg, setDefaultOrg] = useState<number | null>(
        (user.organizations ?? []).find(o => o.is_default)?.organization ?? null
    );
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        try {
            const { role, ...profile } = form;
            const payload: Record<string, unknown> = { ...profile, group_ids: selectedGroups };
            // Send the role only when it was changed: the server will not grant
            // `admin` through an edit, so echoing an admin's own role back is
            // rejected ("admin is not a valid choice").
            if (role !== user.role) payload.role = role;
            // Only send MDAs when the list loaded: omitting the field leaves the
            // user's assignments untouched, whereas sending [] would clear them.
            // An assignment to an MDA that has since been deactivated is dropped
            // (the API only accepts active MDAs, and it grants nothing anyway).
            if (orgStatus === 'ready') {
                const active = new Set(orgOptions.map(o => o.id));
                const kept = assignments.filter(a => active.has(a.organization));
                payload.organizations = kept;
                payload.default_organization =
                    kept.length ? (kept.some(a => a.organization === defaultOrg) ? defaultOrg : kept[0].organization) : null;
            }
            await apiClient.put(`/core/tenant-users/${user.id}/`, payload);
            onSuccess();
        } catch (err: any) {
            setError(apiErrorText(err.response?.data, 'Failed to update user'));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={overlayStyle} onClick={onClose}>
            <div className="card" style={{ width: '600px', padding: '2rem' }} onClick={e => e.stopPropagation()}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                    <h2 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Edit2 size={20} /> Edit User: {user.username}
                    </h2>
                    <button onClick={onClose} style={{
                        padding: '0.375rem', background: 'transparent', border: '1px solid var(--color-border)',
                        borderRadius: '6px', cursor: 'pointer', color: 'var(--color-text-muted)',
                    }}>
                        <X size={18} />
                    </button>
                </div>

                {error && (
                    <div style={{
                        marginBottom: '1rem', padding: '0.75rem', borderRadius: '8px',
                        background: 'var(--color-error)10', border: '1px solid var(--color-error)30',
                        color: 'var(--color-error)', fontSize: 'var(--text-sm)',
                    }}>{error}</div>
                )}

                {/* Current Info */}
                <div style={{
                    marginBottom: '1.25rem', padding: '0.75rem 1rem', borderRadius: '8px',
                    background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                    display: 'flex', gap: '2rem', fontSize: 'var(--text-xs)',
                }}>
                    <div><span style={{ color: 'var(--color-text-muted)' }}>Username:</span> <span style={{ fontWeight: 600 }}>{user.username}</span></div>
                    {user.employee && (
                        <div><span style={{ color: 'var(--color-text-muted)' }}>Employee:</span> <span style={{ fontWeight: 600 }}>{user.employee.employee_number}</span></div>
                    )}
                    {user.created_at && (
                        <div><span style={{ color: 'var(--color-text-muted)' }}>Created:</span> <span style={{ fontWeight: 600 }}>{formatDate(user.created_at)}</span></div>
                    )}
                </div>

                <form onSubmit={handleSubmit}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                        <div>
                            <label style={labelStyle}>First Name</label>
                            <input value={form.first_name}
                                onChange={e => setForm({ ...form, first_name: e.target.value })}
                                className="input" />
                        </div>
                        <div>
                            <label style={labelStyle}>Last Name</label>
                            <input value={form.last_name}
                                onChange={e => setForm({ ...form, last_name: e.target.value })}
                                className="input" />
                        </div>
                        <div>
                            <label style={labelStyle}>Email</label>
                            <input type="email" value={form.email}
                                onChange={e => setForm({ ...form, email: e.target.value })}
                                className="input" />
                        </div>
                        <div>
                            <label style={labelStyle}>Role</label>
                            <select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} className="input">
                                {/* A role that is not assignable here (e.g. Tenant Admin) must still
                                    show as the current value, not silently read as Senior Manager. */}
                                {!ROLE_OPTIONS.some(r => r.value === user.role) && (
                                    <option value={user.role}>{user.role_display || user.role} (current)</option>
                                )}
                                {ROLE_OPTIONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                            </select>
                        </div>
                    </div>

                    <div style={{ marginTop: '1rem' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>
                            <input type="checkbox" checked={form.is_active}
                                onChange={e => setForm({ ...form, is_active: e.target.checked })} />
                            Active Account
                        </label>
                    </div>

                    {groups.length > 0 && (
                        <div style={{ marginTop: '1rem' }}>
                            <label style={labelStyle}>Permission Groups</label>
                            <div style={{
                                display: 'flex', flexWrap: 'wrap', gap: '0.75rem', maxHeight: '100px',
                                overflowY: 'auto', padding: '0.5rem', borderRadius: '8px',
                                border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                            }}>
                                {groups.map(g => (
                                    <label key={g.id} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: 'var(--text-xs)', color: 'var(--color-text)', cursor: 'pointer' }}>
                                        <input type="checkbox" checked={selectedGroups.includes(g.id)}
                                            onChange={e => setSelectedGroups(e.target.checked
                                                ? [...selectedGroups, g.id]
                                                : selectedGroups.filter(id => id !== g.id)
                                            )} />
                                        {g.name}
                                    </label>
                                ))}
                            </div>
                        </div>
                    )}

                    <MdaAssignmentField options={orgOptions} status={orgStatus}
                        assignments={assignments} defaultOrg={defaultOrg}
                        onChange={(next, nextDefault) => { setAssignments(next); setDefaultOrg(nextDefault); }} />

                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.5rem' }}>
                        <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={loading}
                            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Save size={16} /> {loading ? 'Saving...' : 'Save Changes'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

// ── Permissions Modal ──────────────────────────────────────────────

const PermissionsModal: React.FC<{ userId: number; onClose: () => void }> = ({ userId, onClose }) => {
    const { data, isLoading } = useQuery({
        queryKey: ['user-permissions', userId],
        queryFn: async () => {
            const res = await apiClient.get(`/core/tenant-users/${userId}/effective_permissions/`);
            return res.data;
        },
    });

    return (
        <div style={overlayStyle} onClick={onClose}>
            <div className="card" style={{ width: '550px', padding: '2rem', maxHeight: '80vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                    <h2 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Shield size={20} /> Effective Permissions
                    </h2>
                    <button onClick={onClose} style={{
                        padding: '0.375rem', background: 'transparent', border: '1px solid var(--color-border)',
                        borderRadius: '6px', cursor: 'pointer', color: 'var(--color-text-muted)',
                    }}>
                        <X size={18} />
                    </button>
                </div>

                {isLoading ? (
                    <p style={{ color: 'var(--color-text-muted)', textAlign: 'center', padding: '2rem' }}>Loading permissions...</p>
                ) : data ? (
                    <div>
                        {/* User Info */}
                        <div style={{
                            display: 'flex', gap: '1.5rem', marginBottom: '1rem', padding: '0.75rem 1rem',
                            borderRadius: '8px', background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                            fontSize: 'var(--text-sm)',
                        }}>
                            <div>
                                <span style={{ color: 'var(--color-text-muted)' }}>User: </span>
                                <span style={{ fontWeight: 600 }}>{data.user}</span>
                            </div>
                            <div>
                                <span style={{ color: 'var(--color-text-muted)' }}>Role: </span>
                                <span style={{
                                    padding: '0.15rem 0.5rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 700,
                                    background: `${getRoleColor(data.role)}20`, color: getRoleColor(data.role),
                                }}>{data.role}</span>
                            </div>
                        </div>

                        {/* Groups */}
                        <div style={{ marginBottom: '1rem' }}>
                            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Groups: </span>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginTop: '0.35rem' }}>
                                {data.groups?.length > 0 ? data.groups.map((g: string) => (
                                    <span key={g} style={{
                                        padding: '0.15rem 0.5rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 600,
                                        background: '#2471a320', color: '#2471a3',
                                    }}>{g}</span>
                                )) : (
                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>No groups assigned</span>
                                )}
                            </div>
                        </div>

                        {/* Permission Count */}
                        <div style={{ marginBottom: '0.75rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                            {data.total_permissions} permission{data.total_permissions !== 1 ? 's' : ''} resolved
                        </div>

                        {/* Permissions List */}
                        <div style={{
                            maxHeight: '300px', overflowY: 'auto', borderRadius: '8px',
                            border: '1px solid var(--color-border)', padding: '0.75rem',
                            background: 'var(--color-surface)',
                        }}>
                            {data.permissions?.map((p: string) => (
                                <div key={p} style={{
                                    fontSize: 'var(--text-xs)', fontFamily: 'monospace', padding: '0.2rem 0',
                                    color: 'var(--color-text)', borderBottom: '1px solid var(--color-border)',
                                }}>{p}</div>
                            ))}
                        </div>
                    </div>
                ) : (
                    <p style={{ color: 'var(--color-error)' }}>Failed to load permissions</p>
                )}

                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
                    <button className="btn btn-outline" onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    );
};

// ── Reset Password Modal ───────────────────────────────────────────

const ResetPasswordModal: React.FC<{ user: TenantUser; onClose: () => void }> = ({ user, onClose }) => {
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [success, setSuccess] = useState(false);
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        try {
            await apiClient.post(`/core/tenant-users/${user.id}/reset_password/`, { new_password: password });
            setSuccess(true);
        } catch (err: any) {
            setError(err.response?.data?.error || 'Failed to reset password');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={overlayStyle} onClick={onClose}>
            <div className="card" style={{ width: '420px', padding: '2rem' }} onClick={e => e.stopPropagation()}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                    <h2 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Key size={20} /> Reset Password
                    </h2>
                    <button onClick={onClose} style={{
                        padding: '0.375rem', background: 'transparent', border: '1px solid var(--color-border)',
                        borderRadius: '6px', cursor: 'pointer', color: 'var(--color-text-muted)',
                    }}>
                        <X size={18} />
                    </button>
                </div>

                <div style={{
                    marginBottom: '1rem', padding: '0.75rem 1rem', borderRadius: '8px',
                    background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                    fontSize: 'var(--text-sm)',
                }}>
                    Resetting password for <strong>{user.first_name || user.username} {user.last_name}</strong>
                    <span style={{ color: 'var(--color-text-muted)' }}> ({user.username})</span>
                </div>

                {success ? (
                    <div>
                        <div style={{
                            padding: '1rem', borderRadius: '8px', marginBottom: '1rem',
                            background: 'var(--color-success)10', border: '1px solid var(--color-success)30',
                            color: 'var(--color-success)', fontSize: 'var(--text-sm)', fontWeight: 600,
                            display: 'flex', alignItems: 'center', gap: '0.5rem',
                        }}>
                            <CheckCircle size={18} /> Password reset successfully!
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                            <button className="btn btn-outline" onClick={onClose}>Close</button>
                        </div>
                    </div>
                ) : (
                    <form onSubmit={handleSubmit}>
                        {error && (
                            <div style={{
                                marginBottom: '1rem', padding: '0.75rem', borderRadius: '8px',
                                background: 'var(--color-error)10', border: '1px solid var(--color-error)30',
                                color: 'var(--color-error)', fontSize: 'var(--text-sm)',
                            }}>{error}</div>
                        )}
                        <div>
                            <label style={labelStyle}>New Password<span className="required-mark"> *</span></label>
                            <input type="password" required value={password}
                                onChange={e => setPassword(e.target.value)}
                                className="input" placeholder="Enter new password" />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.5rem' }}>
                            <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
                            <button type="submit" className="btn btn-primary" disabled={loading}
                                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <Key size={16} /> {loading ? 'Resetting...' : 'Reset Password'}
                            </button>
                        </div>
                    </form>
                )}
            </div>
        </div>
    );
};

export default UserManagement;
