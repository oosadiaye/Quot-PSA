/**
 * User ↔ Role assignment panel.
 *
 * Rendered inside RolesAndPermissionsPage as its "Users" tab. Lists
 * every user with their currently-assigned roles and surfaces SOD
 * conflicts in-line so an admin sees which assignments violate policy
 * without clicking through. Clicking a user opens the assignment
 * drawer where roles can be toggled with a live SOD preview.
 */
import { useMemo, useState } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import {
    Users as UsersIcon, Plus, Trash2, AlertTriangle,
    ShieldCheck, X, Loader2,
} from 'lucide-react';
import apiClient from '../../api/client';

interface Role {
    id: number;
    code: string;
    name: string;
    module: string;
    role_type: string;
    is_active: boolean;
}

interface Assignment {
    assignment_id: number;
    code: string;
    name: string;
    module: string;
    role_type: string;
    assigned_at: string;
}

interface UserRow {
    user_id: number;
    username: string;
    full_name: string;
    email: string;
    is_superuser: boolean;
    role_codes: string[];
    roles: Assignment[];
    sod_clean: boolean;
    sod_conflicts: Array<{ role_a: string; role_b: string; severity: string; reason: string }>;
    highest_severity: 'none' | 'low' | 'medium' | 'high';
}

interface ByUserResponse {
    count: number;
    rows: UserRow[];
}

interface SODPreview {
    codes_checked: string[];
    conflict_count: number;
    sod_clean: boolean;
    highest_severity: string;
    conflicts: Array<{ role_a: string; role_b: string; severity: string; reason: string }>;
}

const SEV_COLOR: Record<string, { bg: string; border: string; text: string }> = {
    high:   { bg: '#fef2f2', border: '#fca5a5', text: '#991b1b' },
    medium: { bg: '#fffbeb', border: '#fcd34d', text: '#92400e' },
    low:    { bg: '#f0f9ff', border: '#93c5fd', text: '#1e40af' },
    none:   { bg: '#f0fdf4', border: '#86efac', text: '#166534' },
};

export default function UserRoleAssignments() {
    const qc = useQueryClient();
    const [activeUser, setActiveUser] = useState<UserRow | null>(null);

    const { data: byUser, isLoading } = useQuery<ByUserResponse>({
        queryKey: ['role-assignments-by-user'],
        queryFn: async () =>
            (await apiClient.get('/core/role-assignments/by-user/')).data,
        staleTime: 10_000,
    });

    const { data: roles } = useQuery<Role[]>({
        queryKey: ['core-roles', 'active-only'],
        queryFn: async () => {
            const res = await apiClient.get('/core/roles/', {
                params: { is_active: true, page_size: 200 },
            });
            return Array.isArray(res.data) ? res.data : (res.data?.results ?? []);
        },
    });

    return (
        <div>
            <div style={{
                display: 'flex', justifyContent: 'space-between',
                alignItems: 'center', marginBottom: 16,
            }}>
                <h2 style={{
                    margin: 0, fontSize: 16, fontWeight: 800, color: '#1e293b',
                    display: 'flex', alignItems: 'center', gap: 8,
                }}>
                    <UsersIcon size={18} /> User Assignments
                    <span style={{ fontSize: 12, color: '#64748b', fontWeight: 500 }}>
                        ({byUser?.count ?? 0} user{byUser?.count === 1 ? '' : 's'})
                    </span>
                </h2>
            </div>

            {isLoading ? (
                <div style={{ padding: 40, color: '#94a3b8', textAlign: 'center' }}>
                    Loading…
                </div>
            ) : !byUser || byUser.rows.length === 0 ? (
                <div style={{ padding: 40, color: '#94a3b8', textAlign: 'center' }}>
                    No users with assigned roles yet.
                </div>
            ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e8ecf1' }}>
                            {['User', 'Roles', 'SOD Status', ''].map(h => (
                                <th key={h} style={{
                                    padding: '10px 14px', textAlign: 'left', fontSize: 11,
                                    fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
                                    letterSpacing: '0.5px',
                                }}>{h}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {byUser.rows.map(row => {
                            const colours = SEV_COLOR[row.highest_severity] ?? SEV_COLOR.none;
                            return (
                                <tr key={row.user_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                    <td style={{ padding: '10px 14px', fontSize: 13 }}>
                                        <div style={{ fontWeight: 600, color: '#1e293b' }}>
                                            {row.username}
                                            {row.is_superuser && (
                                                <span style={{
                                                    marginLeft: 6, fontSize: 10,
                                                    padding: '1px 6px', borderRadius: 999,
                                                    background: '#fee2e2', color: '#991b1b',
                                                    fontWeight: 700,
                                                }}>SUPER</span>
                                            )}
                                        </div>
                                        <div style={{ fontSize: 11, color: '#64748b' }}>
                                            {row.full_name || '—'} · {row.email || '—'}
                                        </div>
                                    </td>
                                    <td style={{ padding: '10px 14px' }}>
                                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                            {row.roles.map(r => (
                                                <span key={r.assignment_id} style={{
                                                    padding: '2px 8px', borderRadius: 999,
                                                    background: r.role_type === 'manager'
                                                        ? '#f5f3ff' : '#eff6ff',
                                                    color: r.role_type === 'manager'
                                                        ? '#7c3aed' : '#1e40af',
                                                    fontSize: 11, fontWeight: 600,
                                                    border: `1px solid ${r.role_type === 'manager'
                                                        ? '#ddd6fe' : '#bfdbfe'}`,
                                                }}>
                                                    {r.name}
                                                </span>
                                            ))}
                                        </div>
                                    </td>
                                    <td style={{ padding: '10px 14px' }}>
                                        <span style={{
                                            display: 'inline-flex', alignItems: 'center', gap: 4,
                                            padding: '3px 10px', borderRadius: 999,
                                            fontSize: 11, fontWeight: 700,
                                            background: colours.bg,
                                            color: colours.text,
                                            border: `1px solid ${colours.border}`,
                                            textTransform: 'uppercase', letterSpacing: '0.5px',
                                        }}>
                                            {row.sod_clean
                                                ? <ShieldCheck size={11} />
                                                : <AlertTriangle size={11} />}
                                            {row.highest_severity === 'none' ? 'clean' : row.highest_severity}
                                        </span>
                                        {row.sod_conflicts.length > 0 && (
                                            <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
                                                {row.sod_conflicts.length} conflict
                                                {row.sod_conflicts.length === 1 ? '' : 's'}
                                            </div>
                                        )}
                                    </td>
                                    <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                                        <button
                                            onClick={() => setActiveUser(row)}
                                            style={{
                                                padding: '6px 12px', borderRadius: 8,
                                                border: '1px solid #e2e8f0', background: '#fff',
                                                color: '#1e293b', fontSize: 12, fontWeight: 600,
                                                cursor: 'pointer',
                                            }}
                                        >
                                            Manage
                                        </button>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            )}

            {activeUser && (
                <AssignmentDrawer
                    user={activeUser}
                    roles={roles ?? []}
                    onClose={() => setActiveUser(null)}
                    onChanged={() => {
                        qc.invalidateQueries({ queryKey: ['role-assignments-by-user'] });
                    }}
                />
            )}
        </div>
    );
}

interface AssignmentDrawerProps {
    user: UserRow;
    roles: Role[];
    onClose: () => void;
    onChanged: () => void;
}

function AssignmentDrawer({ user, roles, onClose, onChanged }: AssignmentDrawerProps) {
    const [proposed, setProposed] = useState<Set<string>>(
        new Set(user.role_codes),
    );
    const [override, setOverride] = useState(false);
    const [notes, setNotes] = useState('');
    const [serverError, setServerError] = useState<string | null>(null);

    // Live SOD preview whenever proposed changes.
    const { data: preview, isFetching: previewing } = useQuery<SODPreview>({
        queryKey: ['sod-preview', user.user_id, Array.from(proposed).sort().join(',')],
        queryFn: async () => {
            const codes = Array.from(proposed);
            const res = await apiClient.post(
                '/core/role-assignments/preview-sod/',
                { user_id: user.user_id, role_codes: codes },
            );
            return res.data;
        },
        enabled: proposed.size > 0,
    });

    const assignMutation = useMutation({
        mutationFn: async (role: Role) => {
            return apiClient.post('/core/role-assignments/', {
                user: user.user_id,
                role: role.id,
                override,
                notes,
            });
        },
    });

    const revokeMutation = useMutation({
        mutationFn: async (assignmentId: number) =>
            apiClient.delete(`/core/role-assignments/${assignmentId}/`),
    });

    const byModule = useMemo(() => {
        const groups: Record<string, Role[]> = {};
        roles.forEach(r => {
            if (!groups[r.module]) groups[r.module] = [];
            groups[r.module].push(r);
        });
        return groups;
    }, [roles]);

    const roleByCode = useMemo(() => {
        const m = new Map<string, Role>();
        roles.forEach(r => m.set(r.code, r));
        return m;
    }, [roles]);

    const toggleRole = async (role: Role) => {
        setServerError(null);
        const isCurrentlyAssigned = user.role_codes.includes(role.code);

        if (isCurrentlyAssigned) {
            // Revoke existing assignment.
            const assignment = user.roles.find(r => r.code === role.code);
            if (!assignment) return;
            try {
                await revokeMutation.mutateAsync(assignment.assignment_id);
                setProposed(prev => {
                    const next = new Set(prev);
                    next.delete(role.code);
                    return next;
                });
                onChanged();
            } catch (err: unknown) {
                const msg = err instanceof Error ? err.message : 'Revoke failed';
                setServerError(msg);
            }
        } else {
            // Add — check SOD first then POST.
            try {
                await assignMutation.mutateAsync(role);
                setProposed(prev => {
                    const next = new Set(prev);
                    next.add(role.code);
                    return next;
                });
                setOverride(false);
                setNotes('');
                onChanged();
            } catch (err: unknown) {
                const e = err as { response?: { status?: number; data?: { error?: string; conflicts?: unknown[] } } };
                if (e.response?.status === 409) {
                    setServerError(
                        e.response.data?.error
                        ?? 'SOD conflict — set Override + add justification to proceed.'
                    );
                } else {
                    setServerError(
                        e.response?.data?.error
                        ?? (err instanceof Error ? err.message : 'Assignment failed')
                    );
                }
            }
        }
    };

    const previewColours = preview
        ? SEV_COLOR[preview.highest_severity] ?? SEV_COLOR.none
        : SEV_COLOR.none;

    return (
        <div style={{
            position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.5)',
            display: 'flex', justifyContent: 'flex-end', zIndex: 9998,
        }}>
            <div style={{
                width: 560, maxWidth: '100%', background: '#fff', overflow: 'auto',
                boxShadow: '-4px 0 20px rgba(0,0,0,0.15)', padding: '24px 28px',
            }}>
                <div style={{
                    display: 'flex', justifyContent: 'space-between',
                    alignItems: 'flex-start', marginBottom: 20,
                }}>
                    <div>
                        <h3 style={{
                            margin: 0, fontSize: 18, fontWeight: 800, color: '#1e293b',
                        }}>
                            Manage roles — {user.username}
                        </h3>
                        <div style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
                            {user.full_name || '(no full name)'}
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        style={{
                            padding: 6, border: 'none', background: 'transparent',
                            cursor: 'pointer', color: '#64748b',
                        }}
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* SOD preview banner */}
                <div style={{
                    background: previewColours.bg,
                    border: `1px solid ${previewColours.border}`,
                    borderRadius: 10, padding: '12px 14px', marginBottom: 16,
                    display: 'flex', alignItems: 'flex-start', gap: 10,
                }}>
                    <div style={{ flexShrink: 0, marginTop: 2 }}>
                        {previewing
                            ? <Loader2 size={18} style={{
                                animation: 'spin 1s linear infinite',
                                color: previewColours.text,
                              }} />
                            : preview?.sod_clean !== false
                                ? <ShieldCheck size={18} style={{ color: previewColours.text }} />
                                : <AlertTriangle size={18} style={{ color: previewColours.text }} />}
                    </div>
                    <div style={{ flex: 1 }}>
                        <div style={{
                            fontSize: 13, fontWeight: 700, color: previewColours.text,
                            textTransform: 'uppercase', letterSpacing: '0.5px',
                        }}>
                            {preview
                                ? (preview.sod_clean
                                    ? 'SOD-clean'
                                    : `SOD ${preview.highest_severity}`)
                                : 'Preview —'}
                        </div>
                        {preview && preview.conflicts.length > 0 ? (
                            <ul style={{
                                margin: '6px 0 0 0', paddingLeft: 16,
                                fontSize: 12, color: '#475569', lineHeight: 1.5,
                            }}>
                                {preview.conflicts.map((c, i) => {
                                    const a = roleByCode.get(c.role_a);
                                    const b = roleByCode.get(c.role_b);
                                    return (
                                        <li key={i}>
                                            <strong>{a?.name ?? c.role_a}</strong>
                                            {' + '}
                                            <strong>{b?.name ?? c.role_b}</strong>
                                            {' — '}
                                            {c.reason}
                                        </li>
                                    );
                                })}
                            </ul>
                        ) : (
                            <div style={{ fontSize: 12, color: '#475569', marginTop: 2 }}>
                                No conflicts for the current role combination.
                            </div>
                        )}
                    </div>
                </div>

                {/* Override toggle */}
                {preview && !preview.sod_clean && (
                    <div style={{
                        background: '#fef2f2', border: '1px solid #fca5a5',
                        borderRadius: 10, padding: '12px 14px', marginBottom: 16,
                    }}>
                        <label style={{
                            display: 'flex', alignItems: 'center', gap: 8,
                            fontSize: 13, fontWeight: 600, color: '#991b1b',
                            cursor: 'pointer',
                        }}>
                            <input
                                type="checkbox"
                                checked={override}
                                onChange={e => setOverride(e.target.checked)}
                            />
                            Override SOD — dual-control justification required
                        </label>
                        {override && (
                            <textarea
                                value={notes}
                                onChange={e => setNotes(e.target.value)}
                                placeholder="Explain why this combination is necessary (recorded on assignment)…"
                                rows={3}
                                style={{
                                    width: '100%', marginTop: 10, padding: 8,
                                    border: '1px solid #fca5a5', borderRadius: 6,
                                    fontSize: 13, fontFamily: 'inherit',
                                }}
                            />
                        )}
                    </div>
                )}

                {serverError && (
                    <div style={{
                        background: '#fef2f2', border: '1px solid #fca5a5',
                        color: '#991b1b', padding: '10px 14px', borderRadius: 8,
                        fontSize: 13, marginBottom: 16,
                    }}>
                        {serverError}
                    </div>
                )}

                {/* Role grid */}
                {Object.entries(byModule).map(([mod, modRoles]) => (
                    <div key={mod} style={{ marginBottom: 20 }}>
                        <h4 style={{
                            margin: '0 0 8px', fontSize: 12, fontWeight: 700,
                            color: '#64748b', textTransform: 'uppercase',
                            letterSpacing: '0.5px',
                        }}>
                            {mod}
                        </h4>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            {modRoles.map(role => {
                                const isAssigned = proposed.has(role.code);
                                return (
                                    <button
                                        key={role.id}
                                        onClick={() => toggleRole(role)}
                                        disabled={assignMutation.isPending || revokeMutation.isPending}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: 10,
                                            padding: '10px 12px', borderRadius: 8,
                                            border: `1px solid ${isAssigned ? '#10b981' : '#e2e8f0'}`,
                                            background: isAssigned ? '#ecfdf5' : '#fff',
                                            cursor: 'pointer',
                                            textAlign: 'left',
                                        }}
                                    >
                                        {isAssigned
                                            ? <Trash2 size={14} style={{ color: '#047857' }} />
                                            : <Plus size={14} style={{ color: '#64748b' }} />}
                                        <div style={{ flex: 1 }}>
                                            <div style={{ fontSize: 13, fontWeight: 600, color: '#1e293b' }}>
                                                {role.name}
                                            </div>
                                            <div style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'monospace' }}>
                                                {role.code} · {role.role_type}
                                            </div>
                                        </div>
                                        {isAssigned && (
                                            <span style={{
                                                fontSize: 10, color: '#047857', fontWeight: 700,
                                                textTransform: 'uppercase',
                                            }}>
                                                Assigned
                                            </span>
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
