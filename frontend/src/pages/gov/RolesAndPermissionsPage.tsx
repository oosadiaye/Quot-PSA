/**
 * Role & Permission Management — Quot PSE
 * Route: /admin/roles
 *
 * Reviews tenant-local Role definitions (CRUD) and surfaces the
 * Segregation-of-Duties matrix so authorisation design is transparent
 * to auditors. The page is read-biased: non-admin users see the
 * catalogue + SOD matrix, admins see + can edit flag permissions.
 */
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    ShieldCheck, AlertTriangle, Check, X,
    Users as UsersIcon, Award, BadgeCheck,
} from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import apiClient from '../../api/client';
import UserRoleAssignments from './UserRoleAssignments';

interface Role {
    id: number;
    code: string;
    name: string;
    module: string;
    module_display: string;
    role_type: string;
    role_type_display: string;
    can_view: boolean;
    can_add: boolean;
    can_change: boolean;
    can_delete: boolean;
    can_approve: boolean;
    can_post: boolean;
    is_active: boolean;
    is_default: boolean;
    permissions: string[];
}

interface SODRule {
    role_a: string;
    role_b: string;
    severity: 'high' | 'medium' | 'low';
    reason: string;
}

interface SODMatrix {
    rules: SODRule[];
}

const SEVERITY_COLOR = {
    high:   { bg: '#fef2f2', border: '#fca5a5', text: '#991b1b' },
    medium: { bg: '#fffbeb', border: '#fcd34d', text: '#92400e' },
    low:    { bg: '#f0f9ff', border: '#93c5fd', text: '#1e40af' },
} as const;

function PermBadge({ active, label }: { active: boolean; label: string }) {
    return (
        <span
            style={{
                display: 'inline-flex', alignItems: 'center', gap: 3,
                padding: '2px 8px', borderRadius: 999,
                fontSize: 11, fontWeight: 600,
                background: active ? '#ecfdf5' : '#f1f5f9',
                color: active ? '#047857' : '#94a3b8',
                border: `1px solid ${active ? '#a7f3d0' : '#e2e8f0'}`,
            }}
        >
            {active ? <Check size={11} /> : <X size={11} />}
            {label}
        </span>
    );
}

type TabKey = 'catalogue' | 'users' | 'sod';

export default function RolesAndPermissionsPage() {
    const [moduleFilter, setModuleFilter] = useState<string>('');
    const [tab, setTab] = useState<TabKey>('catalogue');

    const { data: roles, isLoading: rolesLoading } = useQuery<Role[]>({
        queryKey: ['core-roles', moduleFilter],
        queryFn: async () => {
            const res = await apiClient.get('/core/roles/', {
                params: moduleFilter ? { module: moduleFilter } : {},
            });
            return Array.isArray(res.data) ? res.data : (res.data?.results ?? []);
        },
    });

    const { data: sodMatrix } = useQuery<SODMatrix>({
        queryKey: ['sod-matrix'],
        queryFn: async () => (await apiClient.get('/core/roles/sod-matrix/')).data,
    });

    const modules = useMemo(() => {
        const set = new Set<string>();
        (roles ?? []).forEach(r => set.add(r.module));
        return Array.from(set).sort();
    }, [roles]);

    const roleByCode = useMemo(() => {
        const out = new Map<string, Role>();
        (roles ?? []).forEach(r => out.set(r.code, r));
        return out;
    }, [roles]);

    const filteredRoles = (roles ?? []).filter(r =>
        !moduleFilter || r.module === moduleFilter,
    );

    // Group roles by module for the catalogue section.
    const rolesByModule = useMemo(() => {
        const groups: Record<string, Role[]> = {};
        filteredRoles.forEach(r => {
            if (!groups[r.module]) groups[r.module] = [];
            groups[r.module].push(r);
        });
        return groups;
    }, [filteredRoles]);

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{
                    display: 'flex', justifyContent: 'space-between',
                    alignItems: 'center', marginBottom: '24px',
                }}>
                    <div>
                        <h1 style={{
                            fontSize: 24, fontWeight: 800, color: '#1e293b', margin: 0,
                            display: 'flex', alignItems: 'center', gap: 10,
                        }}>
                            <ShieldCheck size={22} /> Roles & Permissions
                        </h1>
                        <p style={{ color: '#64748b', fontSize: 14, margin: '4px 0 0' }}>
                            Tenant-local authorisation catalogue with Segregation-of-Duties matrix
                        </p>
                    </div>
                    {tab === 'catalogue' && (
                        <select
                            value={moduleFilter}
                            onChange={e => setModuleFilter(e.target.value)}
                            style={{
                                padding: '8px 12px', borderRadius: 8,
                                border: '1px solid #e2e8f0', fontSize: 14,
                            }}
                        >
                            <option value="">All modules</option>
                            {modules.map(m => (
                                <option key={m} value={m}>
                                    {m.charAt(0).toUpperCase() + m.slice(1)}
                                </option>
                            ))}
                        </select>
                    )}
                </div>

                {/* Tab strip */}
                <div style={{
                    display: 'flex', gap: 4, marginBottom: 20,
                    borderBottom: '1px solid #e8ecf1',
                }}>
                    {([
                        { key: 'catalogue' as TabKey, label: 'Role Catalogue' },
                        { key: 'users'     as TabKey, label: 'User Assignments' },
                        { key: 'sod'       as TabKey, label: 'SOD Matrix' },
                    ]).map(t => (
                        <button
                            key={t.key}
                            onClick={() => setTab(t.key)}
                            style={{
                                padding: '10px 18px', border: 'none',
                                background: 'transparent', cursor: 'pointer',
                                fontSize: 14,
                                fontWeight: tab === t.key ? 700 : 500,
                                color: tab === t.key ? '#1e40af' : '#64748b',
                                borderBottom: `2px solid ${
                                    tab === t.key ? '#1e40af' : 'transparent'
                                }`,
                                marginBottom: -1,
                            }}
                        >
                            {t.label}
                        </button>
                    ))}
                </div>

                {tab === 'users' && (
                    <div style={{
                        background: '#fff', borderRadius: 12,
                        border: '1px solid #e8ecf1', padding: 24, marginBottom: 24,
                    }}>
                        <UserRoleAssignments />
                    </div>
                )}

                {tab === 'catalogue' && (
                    <>
                {/* Role catalogue */}
                <div style={{
                    background: '#fff', borderRadius: 12,
                    border: '1px solid #e8ecf1', padding: 24, marginBottom: 24,
                }}>
                    <h2 style={{
                        margin: 0, fontSize: 16, fontWeight: 800, color: '#1e293b',
                        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16,
                    }}>
                        <UsersIcon size={18} /> Role Catalogue
                        <span style={{
                            fontSize: 12, color: '#64748b', fontWeight: 500,
                        }}>
                            ({filteredRoles.length} role{filteredRoles.length === 1 ? '' : 's'})
                        </span>
                    </h2>

                    {rolesLoading ? (
                        <div style={{ color: '#94a3b8', padding: 20 }}>Loading…</div>
                    ) : filteredRoles.length === 0 ? (
                        <div style={{ color: '#94a3b8', padding: 20 }}>
                            No roles. Run <code>python manage.py tenant_command seed_baseline_roles</code>.
                        </div>
                    ) : (
                        Object.entries(rolesByModule).map(([mod, list]) => (
                            <ModuleSection key={mod} module={mod} roles={list} />
                        ))
                    )}
                </div>
                    </>
                )}

                {/* SOD matrix */}
                {tab === 'sod' && (
                <div style={{
                    background: '#fff', borderRadius: 12,
                    border: '1px solid #e8ecf1', padding: 24,
                }}>
                    <h2 style={{
                        margin: 0, fontSize: 16, fontWeight: 800, color: '#1e293b',
                        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
                    }}>
                        <AlertTriangle size={18} /> Segregation-of-Duties Matrix
                    </h2>
                    <p style={{
                        margin: 0, fontSize: 13, color: '#64748b', marginBottom: 16,
                    }}>
                        Role combinations that must not be held by the same user. Derived from the ICAN
                        public-sector manual, IPSAS conceptual framework, and the Nigerian Public Procurement Act.
                    </p>

                    {!sodMatrix ? (
                        <div style={{ color: '#94a3b8', padding: 20 }}>Loading…</div>
                    ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e8ecf1' }}>
                                    <th style={{
                                        padding: '10px 14px', textAlign: 'left', fontSize: 11,
                                        fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
                                        letterSpacing: '0.5px',
                                    }}>Role A</th>
                                    <th style={{
                                        padding: '10px 14px', textAlign: 'left', fontSize: 11,
                                        fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
                                        letterSpacing: '0.5px',
                                    }}>Role B</th>
                                    <th style={{
                                        padding: '10px 14px', textAlign: 'left', fontSize: 11,
                                        fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
                                        letterSpacing: '0.5px',
                                    }}>Severity</th>
                                    <th style={{
                                        padding: '10px 14px', textAlign: 'left', fontSize: 11,
                                        fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
                                        letterSpacing: '0.5px',
                                    }}>Reason</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sodMatrix.rules.map((rule, idx) => {
                                    const colours = SEVERITY_COLOR[rule.severity];
                                    const a = roleByCode.get(rule.role_a);
                                    const b = roleByCode.get(rule.role_b);
                                    return (
                                        <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                            <td style={{
                                                padding: '10px 14px', fontSize: 13, fontWeight: 600,
                                            }}>
                                                {a?.name ?? rule.role_a}
                                                <div style={{
                                                    fontSize: 11, color: '#94a3b8', fontFamily: 'monospace',
                                                }}>{rule.role_a}</div>
                                            </td>
                                            <td style={{ padding: '10px 14px', fontSize: 13, fontWeight: 600 }}>
                                                {b?.name ?? rule.role_b}
                                                <div style={{
                                                    fontSize: 11, color: '#94a3b8', fontFamily: 'monospace',
                                                }}>{rule.role_b}</div>
                                            </td>
                                            <td style={{ padding: '10px 14px' }}>
                                                <span style={{
                                                    display: 'inline-block', padding: '3px 10px',
                                                    borderRadius: 999, fontSize: 11, fontWeight: 700,
                                                    background: colours.bg,
                                                    color: colours.text,
                                                    border: `1px solid ${colours.border}`,
                                                    textTransform: 'uppercase', letterSpacing: '0.5px',
                                                }}>
                                                    {rule.severity}
                                                </span>
                                            </td>
                                            <td style={{
                                                padding: '10px 14px', fontSize: 13,
                                                color: '#475569', lineHeight: 1.5,
                                            }}>
                                                {rule.reason}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    )}
                </div>
                )}

                <div style={{
                    textAlign: 'center', padding: '20px 0',
                    color: '#94a3b8', fontSize: 11,
                }}>
                    Quot PSE IFMIS — Role & Permission Management
                </div>
            </main>
        </div>
    );
}

interface ModuleSectionProps {
    module: string;
    roles: Role[];
}

function ModuleSection({ module, roles }: ModuleSectionProps) {
    return (
        <div style={{ marginBottom: 20 }}>
            <h3 style={{
                margin: '0 0 10px', fontSize: 13, fontWeight: 700,
                color: '#64748b', textTransform: 'uppercase',
                letterSpacing: '0.5px',
            }}>
                {module}
            </h3>
            <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
                gap: 12,
            }}>
                {roles.map(role => (
                    <div key={role.id} style={{
                        border: '1px solid #e8ecf1', borderRadius: 10,
                        padding: 14, background: role.is_active ? '#fff' : '#f8fafc',
                    }}>
                        <div style={{
                            display: 'flex', justifyContent: 'space-between',
                            alignItems: 'flex-start', marginBottom: 8,
                        }}>
                            <div>
                                <div style={{
                                    fontSize: 15, fontWeight: 800, color: '#1e293b',
                                    display: 'flex', alignItems: 'center', gap: 6,
                                }}>
                                    {role.role_type === 'manager'
                                        ? <Award size={14} style={{ color: '#7c3aed' }} />
                                        : <BadgeCheck size={14} style={{ color: '#3b82f6' }} />}
                                    {role.name}
                                </div>
                                <div style={{
                                    fontSize: 11, color: '#94a3b8', fontFamily: 'monospace',
                                    marginTop: 2,
                                }}>
                                    {role.code}
                                </div>
                            </div>
                            {role.is_default && (
                                <span style={{
                                    fontSize: 10, padding: '2px 8px', borderRadius: 999,
                                    background: '#eff6ff', color: '#1e40af',
                                    border: '1px solid #bfdbfe', fontWeight: 700,
                                    textTransform: 'uppercase',
                                }}>
                                    Default
                                </span>
                            )}
                        </div>

                        <div style={{
                            display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 8,
                        }}>
                            <PermBadge active={role.can_view}    label="View" />
                            <PermBadge active={role.can_add}     label="Add" />
                            <PermBadge active={role.can_change}  label="Edit" />
                            <PermBadge active={role.can_delete}  label="Delete" />
                            <PermBadge active={role.can_approve} label="Approve" />
                            <PermBadge active={role.can_post}    label="Post" />
                        </div>

                        {!role.is_active && (
                            <div style={{
                                marginTop: 8, fontSize: 11, color: '#dc2626',
                                fontWeight: 600,
                            }}>
                                Deactivated
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
