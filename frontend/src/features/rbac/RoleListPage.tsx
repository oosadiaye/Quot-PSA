/**
 * RoleListPage
 * ============
 * Tenant-wide role catalogue — the seven seeded defaults
 * (accountant_general, accounting_officer, procurement_admin,
 * budget_director, budget_officer, treasury_manager, treasury_officer)
 * alongside any custom roles the tenant has created.
 *
 * Route: /admin/roles
 *
 * The previous role page is preserved as a tab on this surface so the
 * legacy SoD matrix view stays accessible during migration.
 */
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
    ShieldCheck, Plus, Pencil, Users, Lock, ShieldAlert,
} from 'lucide-react';
import apiClient from '../../api/client';
import { ListPageShell } from '../../components/layout';

interface Role {
    id: number;
    code: string;
    name: string;
    description: string;
    module: string;
    module_display: string;
    role_type: string;
    role_type_display: string;
    is_active: boolean;
    is_system: boolean;
    permission_codes: string[];
    assigned_user_count: number;
}

export default function RoleListPage() {
    const navigate = useNavigate();
    const [filter, setFilter] = useState<'all' | 'system' | 'custom'>('all');
    const [moduleFilter, setModuleFilter] = useState<string>('');

    const { data: roles = [], isLoading } = useQuery<Role[]>({
        queryKey: ['roles'],
        queryFn: async () => {
            const res = await apiClient.get('/core/roles/');
            return res.data.results || res.data;
        },
    });

    const filtered = useMemo(() => {
        return roles.filter((r) => {
            if (filter === 'system' && !r.is_system) return false;
            if (filter === 'custom' && r.is_system) return false;
            if (moduleFilter && r.module !== moduleFilter) return false;
            return true;
        });
    }, [roles, filter, moduleFilter]);

    const grouped = useMemo(() => {
        const map = new Map<string, Role[]>();
        filtered.forEach((r) => {
            const list = map.get(r.module_display) || [];
            list.push(r);
            map.set(r.module_display, list);
        });
        return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
    }, [filtered]);

    const stats = useMemo(() => ({
        total: roles.length,
        system: roles.filter((r) => r.is_system).length,
        custom: roles.filter((r) => !r.is_system).length,
        active: roles.filter((r) => r.is_active).length,
        users: roles.reduce((acc, r) => acc + r.assigned_user_count, 0),
    }), [roles]);

    const modules = useMemo(() => {
        const set = new Set(roles.map((r) => r.module));
        return Array.from(set).sort();
    }, [roles]);

    return (
        <ListPageShell
            title="Roles & Permissions"
            subtitle="Tenant-editable role catalogue with rule-driven SoD. Changes apply on the next request from any active user."
        >
            <div style={{ padding: '0 24px 40px', display: 'flex', flexDirection: 'column', gap: 16 }}>
                {/* Stats strip */}
                <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)',
                    gap: 12,
                }}>
                    <Stat icon={<ShieldCheck size={16} />} label="Total roles" value={stats.total} />
                    <Stat icon={<Lock size={16} />} label="System (seeded)" value={stats.system} />
                    <Stat icon={<Pencil size={16} />} label="Custom" value={stats.custom} />
                    <Stat icon={<ShieldCheck size={16} />} label="Active" value={stats.active} />
                    <Stat icon={<Users size={16} />} label="Total assignments" value={stats.users} />
                </div>

                {/* Toolbar */}
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '12px 14px', background: '#fff',
                    border: '1px solid #e2e8f0', borderRadius: 8,
                    flexWrap: 'wrap',
                }}>
                    <div style={{ display: 'flex', gap: 4 }}>
                        {(['all', 'system', 'custom'] as const).map((f) => (
                            <button
                                key={f}
                                onClick={() => setFilter(f)}
                                style={{
                                    padding: '6px 12px', fontSize: 12, fontWeight: 600,
                                    border: 'none',
                                    background: filter === f ? '#1e40af' : '#f1f5f9',
                                    color: filter === f ? 'white' : '#475569',
                                    borderRadius: 6, cursor: 'pointer',
                                }}
                            >
                                {f.toUpperCase()}
                            </button>
                        ))}
                    </div>
                    <select
                        value={moduleFilter}
                        onChange={(e) => setModuleFilter(e.target.value)}
                        style={{
                            padding: '6px 11px', fontSize: 12,
                            border: '1px solid #cbd5e1', borderRadius: 6,
                            background: '#fff', color: '#0f172a',
                        }}
                    >
                        <option value="">All modules</option>
                        {modules.map((m) => (
                            <option key={m} value={m}>{m}</option>
                        ))}
                    </select>
                    <div style={{ flex: 1 }} />
                    <button
                        type="button"
                        onClick={() => navigate('/admin/sod-rules')}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '7px 13px', border: '1px solid #cbd5e1',
                            background: '#fff', color: '#1e40af',
                            borderRadius: 6, fontSize: 12, fontWeight: 600,
                            cursor: 'pointer',
                        }}
                    >
                        <ShieldAlert size={13} /> SoD rules
                    </button>
                    <button
                        type="button"
                        onClick={() => navigate('/admin/roles/new')}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '8px 14px', border: 'none',
                            background: '#1e40af', color: 'white',
                            borderRadius: 6, fontSize: 13, fontWeight: 700,
                            cursor: 'pointer',
                        }}
                    >
                        <Plus size={14} /> New role
                    </button>
                </div>

                {/* Role groups */}
                {isLoading && (
                    <div style={{ padding: 60, textAlign: 'center', color: '#64748b' }}>
                        Loading roles…
                    </div>
                )}
                {grouped.map(([moduleDisplay, group]) => (
                    <section key={moduleDisplay} style={{
                        background: '#fff', border: '1px solid #e2e8f0',
                        borderRadius: 8, overflow: 'hidden',
                    }}>
                        <div style={{
                            padding: '10px 16px',
                            background: '#f8fafc',
                            borderBottom: '1px solid #e2e8f0',
                            fontSize: 12, fontWeight: 700, color: '#0f172a',
                            textTransform: 'uppercase', letterSpacing: 0.5,
                        }}>
                            {moduleDisplay} · {group.length} role{group.length === 1 ? '' : 's'}
                        </div>
                        <div>
                            {group.map((role) => (
                                <div
                                    key={role.id}
                                    onClick={() => navigate(`/admin/roles/${role.id}/edit`)}
                                    style={{
                                        padding: '14px 16px',
                                        borderBottom: '1px solid #f1f5f9',
                                        display: 'grid',
                                        gridTemplateColumns: '1fr auto auto auto',
                                        gap: 14, alignItems: 'center',
                                        cursor: 'pointer',
                                        opacity: role.is_active ? 1 : 0.55,
                                    }}
                                    onMouseEnter={(e) => e.currentTarget.style.background = '#f8fafc'}
                                    onMouseLeave={(e) => e.currentTarget.style.background = ''}
                                >
                                    <div>
                                        <div style={{
                                            display: 'flex', alignItems: 'center', gap: 8,
                                            marginBottom: 3,
                                        }}>
                                            <strong style={{ fontSize: 14, color: '#0f172a' }}>
                                                {role.name}
                                            </strong>
                                            <code style={{
                                                fontFamily: 'JetBrains Mono, monospace',
                                                fontSize: 11, color: '#64748b',
                                            }}>{role.code}</code>
                                            {role.is_system && (
                                                <span title="System-seeded role" style={{
                                                    padding: '1px 6px', fontSize: 9, fontWeight: 700,
                                                    background: '#dbeafe', color: '#1e40af',
                                                    borderRadius: 4, letterSpacing: 0.4,
                                                }}>
                                                    SYSTEM
                                                </span>
                                            )}
                                            {!role.is_active && (
                                                <span style={{
                                                    padding: '1px 6px', fontSize: 9, fontWeight: 700,
                                                    background: '#fee2e2', color: '#991b1b',
                                                    borderRadius: 4, letterSpacing: 0.4,
                                                }}>
                                                    INACTIVE
                                                </span>
                                            )}
                                        </div>
                                        {role.description && (
                                            <div style={{
                                                fontSize: 12, color: '#64748b', lineHeight: 1.5,
                                                maxWidth: 720,
                                            }}>
                                                {role.description}
                                            </div>
                                        )}
                                    </div>
                                    <span style={{
                                        padding: '3px 9px', fontSize: 10, fontWeight: 700,
                                        background: role.role_type === 'manager' ? '#fef3c7' : '#dbeafe',
                                        color: role.role_type === 'manager' ? '#92400e' : '#1e40af',
                                        borderRadius: 999, letterSpacing: 0.4,
                                        textTransform: 'uppercase', whiteSpace: 'nowrap',
                                    }}>
                                        {role.role_type_display}
                                    </span>
                                    <div style={{ fontSize: 11, color: '#475569', textAlign: 'right' }}>
                                        <div style={{ fontWeight: 700, color: '#0f172a' }}>
                                            {role.permission_codes.length}
                                        </div>
                                        <div style={{ fontSize: 10 }}>permissions</div>
                                    </div>
                                    <div style={{ fontSize: 11, color: '#475569', textAlign: 'right' }}>
                                        <div style={{ fontWeight: 700, color: '#0f172a' }}>
                                            {role.assigned_user_count}
                                        </div>
                                        <div style={{ fontSize: 10 }}>users</div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </section>
                ))}
            </div>
        </ListPageShell>
    );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
    return (
        <div style={{
            background: '#fff', border: '1px solid #e2e8f0',
            borderRadius: 8, padding: '12px 14px',
            display: 'flex', alignItems: 'center', gap: 10,
        }}>
            <div style={{
                width: 32, height: 32, borderRadius: 8,
                background: '#dbeafe', color: '#1e40af',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
                {icon}
            </div>
            <div>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#0f172a' }}>{value}</div>
                <div style={{ fontSize: 11, color: '#64748b' }}>{label}</div>
            </div>
        </div>
    );
}
