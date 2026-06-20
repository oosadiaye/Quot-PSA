import { useQuery } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import { Users, Plus, Trash2, Pencil, X, Check, Link as LinkIcon, Shield } from 'lucide-react';
import { useState, useMemo } from 'react';
import {
    useApprovalGroups,
    useCreateApprovalGroup,
    useUpdateApprovalGroup,
    useDeleteApprovalGroup,
} from '../hooks/useWorkflow';

interface UserRow {
    id: number;
    username: string;
    email?: string;
    first_name?: string;
    last_name?: string;
}

interface RoleRow {
    id: number;
    name: string;
    code: string;
    module?: string;
    role_type?: string;
    is_active?: boolean;
}

interface ApprovalGroupRow {
    id: number;
    name: string;
    description?: string;
    members: number[];
    member_names?: string[];
    members_count?: number;
    // Role-based indirect membership (added 2026-06): list of core.Role ids
    // referenced by this group. Effective approvers = direct members ∪
    // users with active RoleAssignment to any role in this list.
    roles?: number[];
    role_names?: string[];
    roles_count?: number;
    effective_members_count?: number;
    templates_count?: number;
    templates_using?: string[];
    min_amount?: string | null;
    max_amount?: string | null;
    is_active?: boolean;
}

interface GroupFormState {
    name: string;
    description: string;
    min_amount: string;
    max_amount: string;
    is_active: boolean;
    member_ids: Set<number>;
    role_ids: Set<number>;
}

const BLANK_FORM: GroupFormState = {
    name: '',
    description: '',
    min_amount: '',
    max_amount: '',
    is_active: true,
    member_ids: new Set<number>(),
    role_ids: new Set<number>(),
};

const ApprovalGroups = () => {
    const { data: groupsData, isLoading } = useApprovalGroups();
    const createGroup = useCreateApprovalGroup();
    const updateGroup = useUpdateApprovalGroup();
    const deleteGroup = useDeleteApprovalGroup();

    // Tenant-scoped user list — drives the member picker. The endpoint
    // already filters to active users in the operator's tenant.
    const { data: usersData } = useQuery({
        queryKey: ['users-for-approver-picker'],
        queryFn: async () => {
            const { data } = await apiClient.get('/core/users/', { params: { page_size: 500 } });
            return data;
        },
        staleTime: 5 * 60 * 1000,
    });
    const allUsers: UserRow[] = useMemo(
        () => (usersData?.results || usersData || []) as UserRow[],
        [usersData],
    );

    // Tenant-scoped role list — drives the roles picker. core.Role
    // rows are tenant-isolated (TENANT_APPS schema), so /core/roles/
    // serves only the roles for the current schema.
    const { data: rolesData } = useQuery({
        queryKey: ['roles-for-approver-picker'],
        queryFn: async () => {
            const { data } = await apiClient.get('/core/roles/', { params: { page_size: 500 } });
            return data;
        },
        staleTime: 5 * 60 * 1000,
    });
    const allRoles: RoleRow[] = useMemo(
        () => (rolesData?.results || rolesData || []) as RoleRow[],
        [rolesData],
    );

    // ``null`` = create mode; a row ⇒ edit mode pre-filled with that
    // row's values. The same modal serves both flows — the title and
    // submit handler branch on whether ``editing`` is set.
    const [editing, setEditing] = useState<ApprovalGroupRow | null>(null);
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState<GroupFormState>(BLANK_FORM);
    const [userSearch, setUserSearch] = useState('');
    const [roleSearch, setRoleSearch] = useState('');

    const groups: ApprovalGroupRow[] = useMemo(
        () => (groupsData?.results || groupsData || []) as ApprovalGroupRow[],
        [groupsData],
    );

    const openCreate = () => {
        setEditing(null);
        setForm(BLANK_FORM);
        setUserSearch('');
        setShowForm(true);
    };

    const openEdit = (group: ApprovalGroupRow) => {
        setEditing(group);
        setForm({
            name: group.name,
            description: group.description ?? '',
            min_amount: group.min_amount ?? '',
            max_amount: group.max_amount ?? '',
            is_active: group.is_active ?? true,
            member_ids: new Set<number>(group.members ?? []),
            role_ids: new Set<number>(group.roles ?? []),
        });
        setUserSearch('');
        setRoleSearch('');
        setShowForm(true);
    };

    const closeForm = () => {
        setShowForm(false);
        setEditing(null);
        setForm(BLANK_FORM);
    };

    const toggleMember = (userId: number) => {
        setForm((prev) => {
            const next = new Set(prev.member_ids);
            if (next.has(userId)) next.delete(userId);
            else next.add(userId);
            return { ...prev, member_ids: next };
        });
    };

    const toggleRole = (roleId: number) => {
        setForm((prev) => {
            const next = new Set(prev.role_ids);
            if (next.has(roleId)) next.delete(roleId);
            else next.add(roleId);
            return { ...prev, role_ids: next };
        });
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const payload = {
            name: form.name,
            description: form.description,
            members: Array.from(form.member_ids),
            roles: Array.from(form.role_ids),
            min_amount: form.min_amount ? Number(form.min_amount) : undefined,
            max_amount: form.max_amount ? Number(form.max_amount) : undefined,
            is_active: form.is_active,
        };
        if (editing) {
            updateGroup.mutate(
                { id: editing.id, data: payload },
                { onSuccess: () => closeForm() },
            );
        } else {
            createGroup.mutate(payload, { onSuccess: () => closeForm() });
        }
    };

    const handleDelete = (group: ApprovalGroupRow) => {
        const usageCount = group.templates_count ?? 0;
        const warning = usageCount > 0
            ? `This group is referenced by ${usageCount} approval template${usageCount === 1 ? '' : 's'}. Deleting it will break those workflows. Proceed?`
            : `Delete approval group "${group.name}"?`;
        if (window.confirm(warning)) {
            deleteGroup.mutate(group.id);
        }
    };

    const submitting = createGroup.isPending || updateGroup.isPending;

    const filteredUsers = useMemo(() => {
        const q = userSearch.trim().toLowerCase();
        if (!q) return allUsers;
        return allUsers.filter((u) => {
            const name = `${u.first_name ?? ''} ${u.last_name ?? ''}`.trim().toLowerCase();
            return (
                u.username.toLowerCase().includes(q)
                || (u.email ?? '').toLowerCase().includes(q)
                || name.includes(q)
            );
        });
    }, [allUsers, userSearch]);

    const filteredRoles = useMemo(() => {
        const q = roleSearch.trim().toLowerCase();
        const active = allRoles.filter((r) => r.is_active !== false);
        if (!q) return active;
        return active.filter((r) =>
            r.name.toLowerCase().includes(q)
            || r.code.toLowerCase().includes(q)
            || (r.module ?? '').toLowerCase().includes(q),
        );
    }, [allRoles, roleSearch]);

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Approval Groups"
                    subtitle="Manage approval groups, their members, and which workflows use them."
                    icon={<Users size={22} color="white" />}
                    actions={
                        <button className="btn btn-primary" onClick={openCreate}>
                            <Plus size={18} /> New Group
                        </button>
                    }
                />

                {/* Create / Edit form — same modal, branches on ``editing`` */}
                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem', padding: '1.5rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                            <h3 style={{ margin: 0 }}>
                                {editing ? `Edit "${editing.name}"` : 'Create Approval Group'}
                            </h3>
                            <button
                                onClick={closeForm}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}
                                aria-label="Close form"
                            >
                                <X size={18} />
                            </button>
                        </div>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem', marginBottom: '1.25rem' }}>
                                <div>
                                    <label style={fieldLabelStyle}>Group Name</label>
                                    <input
                                        className="input"
                                        placeholder="e.g. Finance Director"
                                        value={form.name}
                                        onChange={(e) => setForm({ ...form, name: e.target.value })}
                                        required
                                    />
                                </div>
                                <div>
                                    <label style={fieldLabelStyle}>Description</label>
                                    <input
                                        className="input"
                                        placeholder="Optional"
                                        value={form.description}
                                        onChange={(e) => setForm({ ...form, description: e.target.value })}
                                    />
                                </div>
                                <div>
                                    <label style={fieldLabelStyle}>Min Amount (₦)</label>
                                    <input
                                        className="input"
                                        type="number"
                                        placeholder="0"
                                        value={form.min_amount}
                                        onChange={(e) => setForm({ ...form, min_amount: e.target.value })}
                                    />
                                </div>
                                <div>
                                    <label style={fieldLabelStyle}>Max Amount (₦)</label>
                                    <input
                                        className="input"
                                        type="number"
                                        placeholder="Unlimited"
                                        value={form.max_amount}
                                        onChange={(e) => setForm({ ...form, max_amount: e.target.value })}
                                    />
                                </div>
                            </div>

                            <div style={{ marginBottom: '1rem' }}>
                                <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 'var(--text-sm)' }}>
                                    <input
                                        type="checkbox"
                                        checked={form.is_active}
                                        onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                                    />
                                    Active (uncheck to disable without deleting)
                                </label>
                            </div>

                            {/* Members picker — searchable list of tenant users */}
                            <div style={{ marginBottom: '1.25rem' }}>
                                <label style={{ ...fieldLabelStyle, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                    <span>Members ({form.member_ids.size} selected)</span>
                                    <span style={{ fontSize: 'var(--text-xs)', fontWeight: 500, color: 'var(--color-text-muted)' }}>
                                        Tap to add / remove
                                    </span>
                                </label>
                                <input
                                    className="input"
                                    placeholder="Search by name, username, or email..."
                                    value={userSearch}
                                    onChange={(e) => setUserSearch(e.target.value)}
                                    style={{ marginBottom: 8 }}
                                />
                                <div style={memberPickerStyle}>
                                    {filteredUsers.length === 0 && (
                                        <div style={{ padding: '1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', textAlign: 'center' }}>
                                            {userSearch ? 'No users match your search.' : 'No users available.'}
                                        </div>
                                    )}
                                    {filteredUsers.map((u) => {
                                        const isMember = form.member_ids.has(u.id);
                                        const display = (`${u.first_name ?? ''} ${u.last_name ?? ''}`.trim()) || u.username;
                                        return (
                                            <button
                                                type="button"
                                                key={u.id}
                                                onClick={() => toggleMember(u.id)}
                                                style={{
                                                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                                    padding: '0.5rem 0.75rem',
                                                    border: 'none',
                                                    borderBottom: '1px solid var(--color-border)',
                                                    background: isMember ? 'rgba(34, 197, 94, 0.08)' : 'transparent',
                                                    cursor: 'pointer',
                                                    fontSize: 'var(--text-sm)',
                                                    textAlign: 'left',
                                                    width: '100%',
                                                }}
                                            >
                                                <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                                                    <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>{display}</span>
                                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                        @{u.username}{u.email ? ` · ${u.email}` : ''}
                                                    </span>
                                                </div>
                                                {isMember && <Check size={16} color="#16a34a" />}
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>

                            {/* Roles picker — indirect membership via core.Role.
                                Any user with an active RoleAssignment to a
                                role in this list is an effective member of
                                the group. Lets admins delegate at the role
                                level without enumerating users. */}
                            <div style={{ marginBottom: '1.25rem' }}>
                                <label style={{ ...fieldLabelStyle, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                                        <Shield size={12} />
                                        Roles ({form.role_ids.size} selected)
                                    </span>
                                    <span style={{ fontSize: 'var(--text-xs)', fontWeight: 500, color: 'var(--color-text-muted)' }}>
                                        Anyone holding these roles can approve
                                    </span>
                                </label>
                                <input
                                    className="input"
                                    placeholder="Search role by name, code, or module..."
                                    value={roleSearch}
                                    onChange={(e) => setRoleSearch(e.target.value)}
                                    style={{ marginBottom: 8 }}
                                />
                                <div style={memberPickerStyle}>
                                    {filteredRoles.length === 0 && (
                                        <div style={{ padding: '1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', textAlign: 'center' }}>
                                            {roleSearch ? 'No roles match your search.' : 'No roles available — seed roles in System Admin → Roles first.'}
                                        </div>
                                    )}
                                    {filteredRoles.map((r) => {
                                        const isSelected = form.role_ids.has(r.id);
                                        return (
                                            <button
                                                type="button"
                                                key={r.id}
                                                onClick={() => toggleRole(r.id)}
                                                style={{
                                                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                                    padding: '0.5rem 0.75rem',
                                                    border: 'none',
                                                    borderBottom: '1px solid var(--color-border)',
                                                    background: isSelected ? 'rgba(124, 58, 237, 0.08)' : 'transparent',
                                                    cursor: 'pointer',
                                                    fontSize: 'var(--text-sm)',
                                                    textAlign: 'left',
                                                    width: '100%',
                                                }}
                                            >
                                                <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                                                    <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>{r.name}</span>
                                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                        {r.code}
                                                        {r.module && ` · ${r.module}`}
                                                        {r.role_type && ` · ${r.role_type}`}
                                                    </span>
                                                </div>
                                                {isSelected && <Check size={16} color="#7c3aed" />}
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>

                            {/* If editing a group used by templates, surface that
                                fact so the operator knows what they're affecting */}
                            {editing && (editing.templates_using?.length ?? 0) > 0 && (
                                <div style={{
                                    padding: '0.75rem 1rem', marginBottom: '1rem',
                                    background: 'rgba(245, 158, 11, 0.08)',
                                    border: '1px solid rgba(245, 158, 11, 0.3)',
                                    borderRadius: 8, fontSize: 'var(--text-xs)', color: '#92400e',
                                }}>
                                    <strong>Used by these workflows:</strong>{' '}
                                    {editing.templates_using?.join(' · ')}
                                </div>
                            )}

                            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                                <button type="button" className="btn btn-outline" onClick={closeForm}>
                                    Cancel
                                </button>
                                <button type="submit" className="btn btn-primary" disabled={submitting}>
                                    {submitting ? 'Saving...' : editing ? 'Save Changes' : 'Create Group'}
                                </button>
                            </div>
                        </form>
                    </div>
                )}

                {isLoading && (
                    <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-muted)' }}>
                        Loading approval groups...
                    </div>
                )}

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '1.5rem' }}>
                    {groups.map((group) => {
                        const usage = group.templates_count ?? 0;
                        const memberCount = group.members_count ?? group.member_names?.length ?? 0;
                        return (
                            <div key={group.id} className="card" style={{ padding: '1.25rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                                    <div style={{ minWidth: 0, flex: 1 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                            <h3 style={{ marginBottom: '0.25rem' }}>{group.name}</h3>
                                            {!group.is_active && (
                                                <span style={inactivePillStyle}>Inactive</span>
                                            )}
                                        </div>
                                        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                            {group.description || 'No description'}
                                        </p>
                                    </div>
                                    <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                                        <button
                                            className="btn btn-outline"
                                            onClick={() => openEdit(group)}
                                            title="Edit group"
                                            aria-label={`Edit ${group.name}`}
                                            style={{ padding: '0.4rem 0.55rem', color: '#1e4d8c' }}
                                        >
                                            <Pencil size={15} />
                                        </button>
                                        <button
                                            className="btn btn-outline"
                                            onClick={() => handleDelete(group)}
                                            title="Delete group"
                                            aria-label={`Delete ${group.name}`}
                                            style={{ padding: '0.4rem 0.55rem', color: 'var(--color-error)' }}
                                        >
                                            <Trash2 size={15} />
                                        </button>
                                    </div>
                                </div>

                                <div style={{ display: 'flex', gap: '0.75rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                                    <span><strong style={{ color: 'var(--color-text)' }}>Min:</strong> ₦{group.min_amount || '0'}</span>
                                    <span><strong style={{ color: 'var(--color-text)' }}>Max:</strong> ₦{group.max_amount || 'Unlimited'}</span>
                                    <span>
                                        <strong style={{ color: 'var(--color-text)' }}>Direct:</strong> {memberCount}
                                    </span>
                                    {(group.roles_count ?? 0) > 0 && (
                                        <span>
                                            <strong style={{ color: 'var(--color-text)' }}>Roles:</strong> {group.roles_count}
                                        </span>
                                    )}
                                    {(group.effective_members_count ?? 0) > memberCount && (
                                        <span style={{
                                            padding: '1px 8px', borderRadius: 999,
                                            background: 'rgba(124, 58, 237, 0.10)',
                                            color: '#6d28d9',
                                            fontWeight: 700,
                                        }}>
                                            <Shield size={10} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                                            {group.effective_members_count} effective approvers
                                        </span>
                                    )}
                                    <span style={{
                                        padding: '1px 8px', borderRadius: 999,
                                        background: usage > 0 ? 'rgba(34, 197, 94, 0.12)' : 'rgba(148, 163, 184, 0.12)',
                                        color: usage > 0 ? '#15803d' : '#64748b',
                                        fontWeight: 700,
                                    }}>
                                        <LinkIcon size={10} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                                        Used in {usage} workflow{usage === 1 ? '' : 's'}
                                    </span>
                                </div>

                                <div style={{ paddingTop: '0.75rem', borderTop: '1px solid var(--color-border)' }}>
                                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginBottom: '0.5rem', fontWeight: 600, letterSpacing: '0.05em' }}>
                                        MEMBERS
                                    </div>
                                    <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                                        {(group.member_names ?? []).map((name, i) => (
                                            <span key={i} style={{ padding: '0.2rem 0.55rem', background: 'var(--color-surface)', borderRadius: '999px', fontSize: 'var(--text-xs)' }}>
                                                {name}
                                            </span>
                                        ))}
                                        {(!group.member_names || group.member_names.length === 0) && (
                                            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                                {memberCount > 0
                                                    ? `${memberCount} member${memberCount === 1 ? '' : 's'} (names visible to admin only)`
                                                    : 'No members'}
                                            </span>
                                        )}
                                    </div>
                                </div>

                                {(group.role_names?.length ?? 0) > 0 && (
                                    <div style={{ paddingTop: '0.75rem', marginTop: '0.5rem', borderTop: '1px dashed var(--color-border)' }}>
                                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginBottom: '0.4rem', fontWeight: 600, letterSpacing: '0.05em', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                            <Shield size={11} /> ROLES
                                        </div>
                                        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                                            {group.role_names?.map((rn, i) => (
                                                <span key={i} style={{ padding: '0.2rem 0.55rem', background: 'rgba(124,58,237,0.10)', color: '#6d28d9', borderRadius: '999px', fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                                                    {rn}
                                                </span>
                                            ))}
                                            {(group.roles_count ?? 0) > (group.role_names?.length ?? 0) && (
                                                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', alignSelf: 'center' }}>
                                                    +{(group.roles_count ?? 0) - (group.role_names?.length ?? 0)} more
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                )}

                                {(group.templates_using?.length ?? 0) > 0 && (
                                    <div style={{ paddingTop: '0.75rem', marginTop: '0.5rem', borderTop: '1px dashed var(--color-border)' }}>
                                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginBottom: '0.4rem', fontWeight: 600, letterSpacing: '0.05em' }}>
                                            USED BY WORKFLOWS
                                        </div>
                                        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                                            {group.templates_using?.map((t, i) => (
                                                <span key={i} style={{ padding: '0.2rem 0.55rem', background: 'rgba(59,130,246,0.08)', color: '#1e4d8c', borderRadius: '999px', fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                                                    {t}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            </main>
        </div>
    );
};

// ── Shared styles ────────────────────────────────────────────────────

const fieldLabelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
    marginBottom: '0.35rem',
    color: 'var(--color-text-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
};

const memberPickerStyle: React.CSSProperties = {
    maxHeight: 240,
    overflowY: 'auto',
    border: '1px solid var(--color-border)',
    borderRadius: 8,
    background: 'var(--color-surface, #fff)',
};

const inactivePillStyle: React.CSSProperties = {
    padding: '1px 8px',
    borderRadius: 999,
    background: 'rgba(148, 163, 184, 0.15)',
    color: '#64748b',
    fontSize: 10,
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
};

export default ApprovalGroups;
