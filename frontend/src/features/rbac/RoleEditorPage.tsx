/**
 * RoleEditorPage
 * ==============
 * Create or edit a tenant Role with full permission tree + live SoD
 * preview.
 *
 * Routes:
 *   - /admin/roles/new          → blank create form
 *   - /admin/roles/:id/edit     → populated edit form
 *
 * Real-time effect: every save invalidates the per-user permission
 * cache via the backend signal (`core/signals.py`); the
 * react-query cache is also invalidated here so the role list +
 * any permission-aware UI refetches immediately.
 *
 * Layout — three columns when wide, stacked when narrow:
 *   ┌────────────────────────┬──────────────────────────┐
 *   │ Header: name / module  │                          │
 *   │ ────────────────────── │   SoD preview sidebar    │
 *   │ Permission tree        │   (live as you check)    │
 *   │                        │                          │
 *   └────────────────────────┴──────────────────────────┘
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    ArrowLeft, Save, ShieldCheck, AlertTriangle, Lock, Trash2,
} from 'lucide-react';
import apiClient from '../../api/client';
import PermissionTreePicker from './PermissionTreePicker';

interface Role {
    id: number;
    code: string;
    name: string;
    description: string;
    module: string;
    role_type: string;
    is_active: boolean;
    is_system: boolean;
    is_default: boolean;
    permission_codes: string[];
    assigned_user_count: number;
}

interface Violation {
    rule_id: number;
    rule_code: string;
    rule_name: string;
    scope: string;
    severity: 'block' | 'warn';
    permission_a_code: string;
    permission_a_label: string;
    permission_b_code: string;
    permission_b_label: string;
    reason: string;
}

const MODULE_OPTIONS = [
    ['accounting',  'General Ledger & Accounting'],
    ['budget',      'Budget & Appropriation'],
    ['treasury',    'Treasury & TSA'],
    ['procurement', 'Procurement & Due Process'],
    ['contracts',   'Contracts & IPC'],
    ['inventory',   'Stores & Inventory'],
    ['hrm',         'Human Resources & Payroll'],
    ['revenue',     'Revenue Collection (IGR)'],
    ['assets',      'Fixed Asset Management'],
    ['workflow',    'Workflow & Approvals'],
    ['reporting',   'Financial Reporting'],
    ['audit',       'Internal Audit & Compliance'],
    ['admin',       'System Administration'],
];

export default function RoleEditorPage() {
    const { id } = useParams<{ id: string }>();
    const isNew = !id || id === 'new';
    const navigate = useNavigate();
    const qc = useQueryClient();

    const [name, setName] = useState('');
    const [code, setCode] = useState('');
    const [description, setDescription] = useState('');
    const [module, setModule] = useState('accounting');
    const [roleType, setRoleType] = useState<'manager' | 'officer'>('officer');
    const [isActive, setIsActive] = useState(true);
    const [permissionCodes, setPermissionCodes] = useState<Set<string>>(new Set());

    const [error, setError] = useState<string | null>(null);
    const [savedAt, setSavedAt] = useState<Date | null>(null);

    // Load existing role for edit.
    const { data: existing, isLoading } = useQuery<Role>({
        queryKey: ['role', id],
        queryFn: async () => {
            const res = await apiClient.get(`/core/roles/${id}/`);
            return res.data;
        },
        enabled: !isNew,
    });

    useEffect(() => {
        if (existing) {
            setName(existing.name);
            setCode(existing.code);
            setDescription(existing.description || '');
            setModule(existing.module);
            setRoleType(existing.role_type as 'manager' | 'officer');
            setIsActive(existing.is_active);
            setPermissionCodes(new Set(existing.permission_codes || []));
        }
    }, [existing]);

    // Live SoD preview — runs every time the permission set changes,
    // but debounced and only when there's something to evaluate.
    const [violations, setViolations] = useState<Violation[]>([]);
    const [previewLoading, setPreviewLoading] = useState(false);

    useEffect(() => {
        if (isNew) {
            // For new roles we can't call check-sod (needs role id);
            // skip the live preview until the role is saved once.
            setViolations([]);
            return;
        }
        if (permissionCodes.size === 0) {
            setViolations([]);
            return;
        }
        const handle = window.setTimeout(async () => {
            setPreviewLoading(true);
            try {
                const res = await apiClient.post(
                    `/core/roles/${id}/check-sod/`,
                    {
                        // We pass the EDITED set, not the saved one,
                        // so the preview reflects pending changes.
                        additional_permissions: Array.from(permissionCodes),
                    },
                );
                setViolations(res.data.violations || []);
            } catch {
                // Non-fatal — the editor should still be usable if
                // the preview endpoint is unreachable.
            } finally {
                setPreviewLoading(false);
            }
        }, 350);
        return () => window.clearTimeout(handle);
    }, [permissionCodes, id, isNew]);

    const saveMutation = useMutation({
        mutationFn: async () => {
            const payload = {
                name, code, description, module,
                role_type: roleType,
                is_active: isActive,
                permission_codes_input: Array.from(permissionCodes),
            };
            if (isNew) {
                const res = await apiClient.post('/core/roles/', payload);
                return res.data as Role;
            }
            const res = await apiClient.patch(`/core/roles/${id}/`, payload);
            return res.data as Role;
        },
        onSuccess: (saved) => {
            qc.invalidateQueries({ queryKey: ['roles'] });
            qc.invalidateQueries({ queryKey: ['role', String(saved.id)] });
            setSavedAt(new Date());
            if (isNew) {
                // Navigate to edit URL so subsequent saves are PATCH +
                // the SoD preview can run.
                navigate(`/admin/roles/${saved.id}/edit`, { replace: true });
            }
        },
        onError: (e: unknown) => {
            const errObj = e as { response?: { data?: unknown }; message?: string };
            setError(
                typeof errObj?.response?.data === 'string'
                    ? errObj.response.data
                    : JSON.stringify(errObj?.response?.data ?? errObj?.message ?? 'Save failed'),
            );
        },
    });

    const deleteMutation = useMutation({
        mutationFn: async () => {
            if (!id || isNew) return;
            await apiClient.delete(`/core/roles/${id}/`);
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['roles'] });
            navigate('/admin/roles');
        },
    });

    const isSystemRole = !!existing?.is_system;
    const blockingCount = useMemo(
        () => violations.filter((v) => v.severity === 'block').length,
        [violations],
    );
    const warningCount = violations.length - blockingCount;

    if (!isNew && isLoading) {
        return <div style={{ padding: 60, textAlign: 'center' }}>Loading…</div>;
    }

    return (
        <div style={{ background: '#f8fafc', minHeight: '100vh' }}>
            {/* Header bar */}
            <div style={{
                background: '#0f172a', color: 'white',
                padding: '14px 24px',
                display: 'flex', alignItems: 'center', gap: 16,
                position: 'sticky', top: 0, zIndex: 5,
            }}>
                <button
                    onClick={() => navigate('/admin/roles')}
                    style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '7px 14px', border: '1px solid #334155',
                        background: '#1e293b', color: 'white',
                        borderRadius: 6, fontSize: 13, fontWeight: 600,
                        cursor: 'pointer',
                    }}
                >
                    <ArrowLeft size={14} /> Back to roles
                </button>
                <div>
                    <div style={{ fontSize: 17, fontWeight: 700 }}>
                        {isNew ? 'New role' : (existing?.name || 'Role')}
                    </div>
                    <div style={{ fontSize: 12, color: '#cbd5e1', marginTop: 2 }}>
                        {isNew ? 'Define a custom role for your tenant'
                               : isSystemRole ? 'System-seeded role — editable but cannot be deleted'
                               : 'Custom role'}
                    </div>
                </div>
                <div style={{ flex: 1 }} />
                {!isNew && !isSystemRole && (
                    <button
                        onClick={() => {
                            if (window.confirm('Delete this role? Active assignments will be removed.')) {
                                deleteMutation.mutate();
                            }
                        }}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '7px 14px', border: 'none',
                            background: '#7f1d1d', color: 'white',
                            borderRadius: 6, fontSize: 13, fontWeight: 600,
                            cursor: 'pointer',
                        }}
                    >
                        <Trash2 size={14} /> Delete
                    </button>
                )}
                <button
                    onClick={() => saveMutation.mutate()}
                    disabled={saveMutation.isPending}
                    style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '8px 18px', border: 'none',
                        background: saveMutation.isPending ? '#64748b' : '#1e40af',
                        color: 'white', borderRadius: 6,
                        fontSize: 13, fontWeight: 700, cursor: 'pointer',
                    }}
                >
                    <Save size={14} />
                    {saveMutation.isPending ? 'Saving…' : 'Save changes'}
                </button>
            </div>

            <div style={{
                maxWidth: 1400, margin: '0 auto', padding: '24px 24px 60px',
                display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 360px',
                gap: 20,
            }}>
                {/* LEFT — form + tree */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                    {error && (
                        <div style={{
                            padding: '10px 14px', borderRadius: 8,
                            background: '#fef2f2', border: '1px solid #fecaca',
                            color: '#b91c1c', fontSize: 13,
                        }}>
                            <AlertTriangle size={14} style={{ marginRight: 6, verticalAlign: -2 }} />
                            {error}
                        </div>
                    )}
                    {savedAt && (
                        <div style={{
                            padding: '10px 14px', borderRadius: 8,
                            background: '#ecfdf5', border: '1px solid #a7f3d0',
                            color: '#047857', fontSize: 13,
                        }}>
                            Saved at {savedAt.toLocaleTimeString()}. Changes apply
                            on the next request from any active user (caches invalidated).
                        </div>
                    )}

                    {/* Identity card */}
                    <section style={card}>
                        <h3 style={cardTitle}>Identity</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                            <Field label="Display name">
                                <input
                                    type="text" value={name}
                                    onChange={(e) => setName(e.target.value)}
                                    style={input} placeholder="e.g. Senior Budget Analyst"
                                />
                            </Field>
                            <Field label="Code (stable id)">
                                <input
                                    type="text" value={code}
                                    onChange={(e) => setCode(e.target.value)}
                                    style={{ ...input, fontFamily: 'JetBrains Mono, monospace' }}
                                    placeholder="e.g. senior_budget_analyst"
                                    disabled={isSystemRole}
                                />
                                {isSystemRole && (
                                    <div style={{ fontSize: 11, color: '#92400e', marginTop: 4 }}>
                                        <Lock size={11} style={{ verticalAlign: -1, marginRight: 4 }} />
                                        Code locked on system roles to preserve seed references.
                                    </div>
                                )}
                            </Field>
                            <Field label="Module">
                                <select
                                    value={module}
                                    onChange={(e) => setModule(e.target.value)}
                                    style={input}
                                >
                                    {MODULE_OPTIONS.map(([v, label]) => (
                                        <option key={v} value={v}>{label}</option>
                                    ))}
                                </select>
                            </Field>
                            <Field label="Role type">
                                <select
                                    value={roleType}
                                    onChange={(e) => setRoleType(e.target.value as 'manager' | 'officer')}
                                    style={input}
                                >
                                    <option value="manager">Manager (approves / posts)</option>
                                    <option value="officer">Officer (drafts / submits)</option>
                                </select>
                            </Field>
                            <Field label="Description" wide>
                                <textarea
                                    value={description}
                                    onChange={(e) => setDescription(e.target.value)}
                                    rows={2}
                                    style={{ ...input, resize: 'vertical', minHeight: 56 }}
                                    placeholder="What does this role authorise? Helpful for auditors."
                                />
                            </Field>
                            <Field label="Active">
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                    <input
                                        type="checkbox"
                                        checked={isActive}
                                        onChange={(e) => setIsActive(e.target.checked)}
                                    />
                                    <span style={{ fontSize: 13 }}>
                                        Inactive roles can't be assigned and existing
                                        assignments stop granting permissions immediately.
                                    </span>
                                </label>
                            </Field>
                        </div>
                    </section>

                    {/* Permission tree */}
                    <section style={card}>
                        <h3 style={cardTitle}>Permissions</h3>
                        <p style={cardHint}>
                            Pick the granular actions this role authorises.
                            Selections take effect immediately on save —
                            the per-user permission cache is invalidated so
                            the very next request reflects the change.
                        </p>
                        <PermissionTreePicker
                            value={permissionCodes}
                            onChange={setPermissionCodes}
                            disabled={saveMutation.isPending}
                        />
                    </section>
                </div>

                {/* RIGHT — SoD preview */}
                <aside style={{
                    display: 'flex', flexDirection: 'column', gap: 14,
                    position: 'sticky', top: 80, alignSelf: 'start',
                    maxHeight: 'calc(100vh - 100px)', overflowY: 'auto',
                }}>
                    <section style={card}>
                        <div style={{
                            display: 'flex', alignItems: 'center', gap: 8,
                            marginBottom: 6,
                        }}>
                            <ShieldCheck size={16} style={{ color: '#1e40af' }} />
                            <h3 style={{ ...cardTitle, margin: 0 }}>SoD preview</h3>
                            {previewLoading && (
                                <span style={{ fontSize: 11, color: '#94a3b8' }}>
                                    checking…
                                </span>
                            )}
                        </div>
                        {isNew ? (
                            <p style={{ ...cardHint, marginTop: 0 }}>
                                Save this role once to enable the live SoD
                                preview. Once saved, edits show violations
                                here in real time.
                            </p>
                        ) : violations.length === 0 ? (
                            <div style={{
                                padding: 14, borderRadius: 8,
                                background: '#ecfdf5', border: '1px solid #a7f3d0',
                                color: '#047857', fontSize: 13,
                            }}>
                                No SoD conflicts. This permission set is clean.
                            </div>
                        ) : (
                            <>
                                <div style={{
                                    display: 'flex', gap: 8, marginBottom: 10,
                                }}>
                                    {blockingCount > 0 && (
                                        <span style={{
                                            padding: '3px 9px', fontSize: 11, fontWeight: 700,
                                            background: '#fee2e2', color: '#991b1b',
                                            borderRadius: 999,
                                        }}>
                                            {blockingCount} BLOCKING
                                        </span>
                                    )}
                                    {warningCount > 0 && (
                                        <span style={{
                                            padding: '3px 9px', fontSize: 11, fontWeight: 700,
                                            background: '#fef3c7', color: '#92400e',
                                            borderRadius: 999,
                                        }}>
                                            {warningCount} WARNING
                                        </span>
                                    )}
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                    {violations.map((v) => (
                                        <div key={v.rule_id} style={{
                                            padding: 12, borderRadius: 8,
                                            background: v.severity === 'block' ? '#fef2f2' : '#fffbeb',
                                            border: `1px solid ${v.severity === 'block' ? '#fecaca' : '#fde68a'}`,
                                        }}>
                                            <div style={{
                                                fontSize: 11, fontWeight: 700,
                                                color: v.severity === 'block' ? '#991b1b' : '#92400e',
                                                textTransform: 'uppercase', letterSpacing: 0.5,
                                                marginBottom: 4,
                                            }}>
                                                {v.severity === 'block' ? 'Blocks save' : 'Warns'} · {v.scope === 'hold' ? 'Hold' : 'Same document'}
                                            </div>
                                            <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a', marginBottom: 6 }}>
                                                {v.rule_name}
                                            </div>
                                            <div style={{ fontSize: 11, color: '#475569', lineHeight: 1.5 }}>
                                                {v.reason}
                                            </div>
                                            <div style={{
                                                marginTop: 8,
                                                display: 'flex', gap: 6, flexWrap: 'wrap',
                                                fontFamily: 'JetBrains Mono, monospace',
                                                fontSize: 10,
                                            }}>
                                                <code style={chip}>{v.permission_a_code}</code>
                                                <span style={{ color: '#94a3b8' }}>×</span>
                                                <code style={chip}>{v.permission_b_code}</code>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </>
                        )}
                    </section>

                    {existing && existing.assigned_user_count > 0 && (
                        <section style={card}>
                            <h3 style={cardTitle}>Impact</h3>
                            <div style={{ fontSize: 13, color: '#475569' }}>
                                <strong style={{ color: '#0f172a' }}>{existing.assigned_user_count}</strong>
                                {' '}user{existing.assigned_user_count === 1 ? '' : 's'} hold this role.
                                Saving will refresh their permission caches immediately —
                                they'll see the change on their next request.
                            </div>
                        </section>
                    )}
                </aside>
            </div>
        </div>
    );
}

function Field({ label, children, wide }: { label: string; children: React.ReactNode; wide?: boolean }) {
    return (
        <div style={{ gridColumn: wide ? 'span 2' : undefined }}>
            <label style={fieldLabel}>{label}</label>
            {children}
        </div>
    );
}

const card: React.CSSProperties = {
    background: '#fff', border: '1px solid #e2e8f0',
    borderRadius: 10, padding: 18,
};
const cardTitle: React.CSSProperties = {
    fontSize: 15, fontWeight: 700, color: '#0f172a',
    margin: '0 0 6px 0',
};
const cardHint: React.CSSProperties = {
    fontSize: 12.5, color: '#64748b', margin: '0 0 14px 0',
    lineHeight: 1.5,
};
const fieldLabel: React.CSSProperties = {
    display: 'block',
    fontSize: 11, fontWeight: 700, color: '#475569',
    textTransform: 'uppercase', letterSpacing: 0.5,
    marginBottom: 6,
};
const input: React.CSSProperties = {
    width: '100%', padding: '8px 11px',
    border: '1px solid #cbd5e1', borderRadius: 6,
    fontSize: 13, fontFamily: 'inherit', color: '#0f172a',
    background: '#fff', outline: 'none',
};
const chip: React.CSSProperties = {
    padding: '2px 6px', background: '#fff',
    border: '1px solid #e2e8f0', borderRadius: 4,
    color: '#0f172a',
};
