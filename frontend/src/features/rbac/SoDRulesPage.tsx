/**
 * SoDRulesPage
 * ============
 * CRUD over the rule-driven Segregation-of-Duties matrix.
 *
 * Route: /admin/sod-rules
 *
 * Each rule names two granular permissions that should not be
 * exercised together (``same_document``) or held by one user at all
 * (``hold``). Tenants edit, deactivate, or extend these freely;
 * changes invalidate the per-user permission cache so the next
 * request reflects the new policy.
 *
 * UI is intentionally simple — a list with inline-edit modal — because
 * the Role editor's live SoD preview is where most admins will discover
 * what rules exist. This page is the management view for compliance
 * officers who need the full matrix.
 */
import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    ShieldCheck, Plus, Pencil, AlertTriangle, Lock, X, Save,
} from 'lucide-react';
import apiClient from '../../api/client';
import { ListPageShell } from '../../components/layout';

interface SoDRule {
    id: number;
    code: string;
    name: string;
    description: string;
    permission_a: number;
    permission_a_code: string;
    permission_a_label: string;
    permission_b: number;
    permission_b_code: string;
    permission_b_label: string;
    scope: 'hold' | 'same_document';
    scope_display: string;
    severity: 'block' | 'warn';
    severity_display: string;
    is_active: boolean;
    is_system: boolean;
}

interface PermissionCatalogueRow {
    code: string;
    label: string;
    module_display: string;
    risk_level: string;
}

export default function SoDRulesPage() {
    const qc = useQueryClient();
    const [editing, setEditing] = useState<Partial<SoDRule> | null>(null);
    const [showInactive, setShowInactive] = useState(false);

    const { data: rules = [], isLoading } = useQuery<SoDRule[]>({
        queryKey: ['sod-rules', showInactive],
        queryFn: async () => {
            const params = showInactive ? '' : '?is_active=true';
            const res = await apiClient.get(`/core/sod-rules/${params}`);
            return res.data.results || res.data;
        },
    });

    const { data: permissions = [] } = useQuery<PermissionCatalogueRow[]>({
        queryKey: ['permissions-flat'],
        queryFn: async () => {
            const res = await apiClient.get('/core/permissions/');
            return (res.data.results || res.data).map((p: {
                code: string; label: string; module_display: string; risk_level: string;
            }) => ({
                code: p.code,
                label: p.label,
                module_display: p.module_display,
                risk_level: p.risk_level,
            }));
        },
    });

    const saveMutation = useMutation({
        mutationFn: async (rule: Partial<SoDRule>) => {
            const payload = {
                code: rule.code,
                name: rule.name,
                description: rule.description || '',
                permission_a_input: rule.permission_a_code,
                permission_b_input: rule.permission_b_code,
                scope: rule.scope || 'same_document',
                severity: rule.severity || 'block',
                is_active: rule.is_active !== false,
            };
            if (rule.id) {
                const res = await apiClient.patch(`/core/sod-rules/${rule.id}/`, payload);
                return res.data;
            }
            const res = await apiClient.post('/core/sod-rules/', payload);
            return res.data;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['sod-rules'] });
            setEditing(null);
        },
    });

    const toggleActiveMutation = useMutation({
        mutationFn: async (rule: SoDRule) => {
            const res = await apiClient.patch(`/core/sod-rules/${rule.id}/`, {
                is_active: !rule.is_active,
            });
            return res.data;
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['sod-rules'] });
        },
    });

    const deleteMutation = useMutation({
        mutationFn: async (id: number) => {
            await apiClient.delete(`/core/sod-rules/${id}/`);
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['sod-rules'] });
        },
    });

    const grouped = useMemo(() => {
        const map = new Map<string, SoDRule[]>();
        rules.forEach((r) => {
            const mod = r.permission_a_code.split('.')[0] || 'other';
            const list = map.get(mod) || [];
            list.push(r);
            map.set(mod, list);
        });
        return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
    }, [rules]);

    return (
        <ListPageShell
            title="Segregation-of-Duties Rules"
            subtitle="Declarative incompatibilities between permissions. Changes apply on the next request."
        >
            <div style={{ padding: '0 24px 40px', display: 'flex', flexDirection: 'column', gap: 16 }}>
                {/* Toolbar */}
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '12px 14px', background: '#fff',
                    border: '1px solid #e2e8f0', borderRadius: 8,
                }}>
                    <ShieldCheck size={18} style={{ color: '#1e40af' }} />
                    <strong style={{ fontSize: 13, color: '#0f172a' }}>
                        {rules.filter((r) => r.is_active).length} active
                    </strong>
                    <span style={{ color: '#cbd5e1' }}>·</span>
                    <span style={{ fontSize: 13, color: '#475569' }}>
                        {rules.filter((r) => !r.is_active).length} inactive
                    </span>
                    <label style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        marginLeft: 16, fontSize: 12, color: '#475569',
                    }}>
                        <input
                            type="checkbox"
                            checked={showInactive}
                            onChange={(e) => setShowInactive(e.target.checked)}
                        />
                        Show inactive rules
                    </label>
                    <div style={{ flex: 1 }} />
                    <button
                        type="button"
                        onClick={() => setEditing({
                            scope: 'same_document', severity: 'block', is_active: true,
                        })}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '8px 14px', border: 'none',
                            background: '#1e40af', color: 'white',
                            borderRadius: 6, fontSize: 13, fontWeight: 700,
                            cursor: 'pointer',
                        }}
                    >
                        <Plus size={14} /> New rule
                    </button>
                </div>

                {isLoading ? (
                    <div style={{ padding: 60, textAlign: 'center', color: '#64748b' }}>
                        Loading SoD rules…
                    </div>
                ) : (
                    grouped.map(([module, group]) => (
                        <section key={module} style={{
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
                                {module} · {group.length} rule{group.length === 1 ? '' : 's'}
                            </div>
                            <div>
                                {group.map((rule) => (
                                    <div key={rule.id} style={{
                                        padding: '12px 16px',
                                        borderBottom: '1px solid #f1f5f9',
                                        display: 'grid',
                                        gridTemplateColumns: '1fr auto auto auto',
                                        gap: 12,
                                        alignItems: 'center',
                                        opacity: rule.is_active ? 1 : 0.55,
                                    }}>
                                        <div>
                                            <div style={{
                                                display: 'flex', alignItems: 'center', gap: 8,
                                                marginBottom: 4,
                                            }}>
                                                <strong style={{ fontSize: 13, color: '#0f172a' }}>
                                                    {rule.name}
                                                </strong>
                                                {rule.is_system && (
                                                    <span title="System rule — cannot be deleted, can only be deactivated" style={{
                                                        padding: '1px 6px', fontSize: 9, fontWeight: 700,
                                                        background: '#dbeafe', color: '#1e40af',
                                                        borderRadius: 4, letterSpacing: 0.4,
                                                    }}>
                                                        SYSTEM
                                                    </span>
                                                )}
                                            </div>
                                            <div style={{
                                                fontFamily: 'JetBrains Mono, monospace',
                                                fontSize: 11, color: '#475569',
                                                display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'center',
                                            }}>
                                                <code style={chipStyle}>{rule.permission_a_code}</code>
                                                <span style={{ color: '#94a3b8', fontSize: 11 }}>×</span>
                                                <code style={chipStyle}>{rule.permission_b_code}</code>
                                            </div>
                                            {rule.description && (
                                                <div style={{
                                                    fontSize: 11, color: '#64748b',
                                                    marginTop: 6, lineHeight: 1.5,
                                                }}>
                                                    {rule.description}
                                                </div>
                                            )}
                                        </div>
                                        <span style={pill(rule.scope === 'hold' ? '#fde68a' : '#dbeafe',
                                                          rule.scope === 'hold' ? '#92400e' : '#1e40af')}>
                                            {rule.scope_display}
                                        </span>
                                        <span style={pill(rule.severity === 'block' ? '#fee2e2' : '#fef3c7',
                                                          rule.severity === 'block' ? '#991b1b' : '#92400e')}>
                                            {rule.severity === 'block' ? 'BLOCKS' : 'WARNS'}
                                        </span>
                                        <div style={{ display: 'flex', gap: 6 }}>
                                            <button
                                                type="button"
                                                onClick={() => setEditing(rule)}
                                                style={iconBtn}
                                                title="Edit rule"
                                            >
                                                <Pencil size={12} />
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => toggleActiveMutation.mutate(rule)}
                                                style={{ ...iconBtn, color: rule.is_active ? '#92400e' : '#047857' }}
                                                title={rule.is_active ? 'Deactivate' : 'Activate'}
                                            >
                                                {rule.is_active ? 'OFF' : 'ON'}
                                            </button>
                                            {!rule.is_system && (
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        if (window.confirm(`Delete rule "${rule.name}"?`)) {
                                                            deleteMutation.mutate(rule.id);
                                                        }
                                                    }}
                                                    style={{ ...iconBtn, color: '#dc2626' }}
                                                    title="Delete rule"
                                                >
                                                    <X size={12} />
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </section>
                    ))
                )}
            </div>

            {editing && (
                <RuleEditModal
                    rule={editing}
                    permissions={permissions}
                    onClose={() => setEditing(null)}
                    onSave={(rule) => saveMutation.mutate(rule)}
                    saving={saveMutation.isPending}
                />
            )}
        </ListPageShell>
    );
}

function RuleEditModal({
    rule, permissions, onClose, onSave, saving,
}: {
    rule: Partial<SoDRule>;
    permissions: PermissionCatalogueRow[];
    onClose: () => void;
    onSave: (r: Partial<SoDRule>) => void;
    saving: boolean;
}) {
    const [draft, setDraft] = useState<Partial<SoDRule>>(rule);
    const isNew = !rule.id;
    const isSystem = !!rule.is_system;

    const valid = !!(
        draft.code && draft.name &&
        draft.permission_a_code && draft.permission_b_code &&
        draft.permission_a_code !== draft.permission_b_code
    );

    return (
        <div style={{
            position: 'fixed', inset: 0, zIndex: 1000,
            background: 'rgba(15, 23, 42, 0.6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 24,
        }} onClick={onClose}>
            <div onClick={(e) => e.stopPropagation()} style={{
                background: '#fff', borderRadius: 12,
                width: '100%', maxWidth: 640,
                maxHeight: 'calc(100vh - 48px)', overflowY: 'auto',
            }}>
                <div style={{
                    padding: '14px 18px',
                    borderBottom: '1px solid #e2e8f0',
                    display: 'flex', alignItems: 'center', gap: 8,
                }}>
                    <ShieldCheck size={16} style={{ color: '#1e40af' }} />
                    <strong style={{ fontSize: 15, color: '#0f172a', flex: 1 }}>
                        {isNew ? 'New SoD rule' : 'Edit SoD rule'}
                    </strong>
                    <button onClick={onClose} style={iconBtn}>
                        <X size={14} />
                    </button>
                </div>

                <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
                    {isSystem && (
                        <div style={{
                            padding: '8px 12px', borderRadius: 6,
                            background: '#dbeafe', color: '#1e40af',
                            fontSize: 12, display: 'flex', alignItems: 'center', gap: 6,
                        }}>
                            <Lock size={12} />
                            System rule. The code cannot be changed; deactivation
                            is preferred over deletion.
                        </div>
                    )}

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                        <div>
                            <label style={lbl}>Code (stable id)</label>
                            <input
                                style={inp} value={draft.code || ''}
                                onChange={(e) => setDraft({ ...draft, code: e.target.value })}
                                placeholder="e.g. sod.invoice.match_approve"
                                disabled={isSystem}
                            />
                        </div>
                        <div>
                            <label style={lbl}>Display name</label>
                            <input
                                style={inp} value={draft.name || ''}
                                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                            />
                        </div>
                    </div>

                    <div>
                        <label style={lbl}>Description (shown to operators on violation)</label>
                        <textarea
                            style={{ ...inp, resize: 'vertical', minHeight: 60 }}
                            rows={2}
                            value={draft.description || ''}
                            onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                        />
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                        <PermissionSelect
                            label="Permission A"
                            value={draft.permission_a_code || ''}
                            onChange={(v) => setDraft({ ...draft, permission_a_code: v })}
                            options={permissions}
                        />
                        <PermissionSelect
                            label="Permission B"
                            value={draft.permission_b_code || ''}
                            onChange={(v) => setDraft({ ...draft, permission_b_code: v })}
                            options={permissions}
                        />
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                        <div>
                            <label style={lbl}>Scope</label>
                            <select
                                style={inp} value={draft.scope || 'same_document'}
                                onChange={(e) => setDraft({ ...draft, scope: e.target.value as 'hold' | 'same_document' })}
                            >
                                <option value="same_document">Same document — cannot exercise both on one record</option>
                                <option value="hold">Hold — cannot hold both at all</option>
                            </select>
                        </div>
                        <div>
                            <label style={lbl}>Severity</label>
                            <select
                                style={inp} value={draft.severity || 'block'}
                                onChange={(e) => setDraft({ ...draft, severity: e.target.value as 'block' | 'warn' })}
                            >
                                <option value="block">Block — hard reject the action</option>
                                <option value="warn">Warn — log and allow with banner</option>
                            </select>
                        </div>
                    </div>

                    <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <input
                            type="checkbox"
                            checked={draft.is_active !== false}
                            onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })}
                        />
                        <span style={{ fontSize: 13 }}>Active</span>
                    </label>

                    {!valid && (
                        <div style={{
                            padding: 10, borderRadius: 6,
                            background: '#fef2f2', color: '#991b1b',
                            fontSize: 12,
                        }}>
                            <AlertTriangle size={12} style={{ marginRight: 6, verticalAlign: -1 }} />
                            All fields required. Permissions A and B must be different.
                        </div>
                    )}
                </div>

                <div style={{
                    padding: '12px 18px', borderTop: '1px solid #e2e8f0',
                    display: 'flex', justifyContent: 'flex-end', gap: 8,
                }}>
                    <button onClick={onClose} style={{
                        padding: '8px 14px', border: '1px solid #cbd5e1',
                        background: '#fff', color: '#475569',
                        borderRadius: 6, fontSize: 13, fontWeight: 600,
                        cursor: 'pointer',
                    }}>Cancel</button>
                    <button
                        onClick={() => onSave(draft)}
                        disabled={!valid || saving}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '8px 16px', border: 'none',
                            background: !valid || saving ? '#94a3b8' : '#1e40af',
                            color: 'white', borderRadius: 6,
                            fontSize: 13, fontWeight: 700, cursor: 'pointer',
                        }}
                    >
                        <Save size={13} />
                        {saving ? 'Saving…' : 'Save rule'}
                    </button>
                </div>
            </div>
        </div>
    );
}

function PermissionSelect({
    label, value, onChange, options,
}: {
    label: string;
    value: string;
    onChange: (v: string) => void;
    options: PermissionCatalogueRow[];
}) {
    return (
        <div>
            <label style={lbl}>{label}</label>
            <select
                style={{ ...inp, fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}
                value={value}
                onChange={(e) => onChange(e.target.value)}
            >
                <option value="">— select permission —</option>
                {options.map((p) => (
                    <option key={p.code} value={p.code}>
                        {p.code}  ·  {p.label}
                    </option>
                ))}
            </select>
        </div>
    );
}

const chipStyle: React.CSSProperties = {
    padding: '2px 6px', background: '#f8fafc',
    border: '1px solid #e2e8f0', borderRadius: 4,
    color: '#0f172a', fontSize: 11,
};
const pill = (bg: string, fg: string): React.CSSProperties => ({
    padding: '3px 10px', fontSize: 10, fontWeight: 700,
    background: bg, color: fg, borderRadius: 999,
    letterSpacing: 0.4, textTransform: 'uppercase',
    whiteSpace: 'nowrap',
});
const iconBtn: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    minWidth: 28, height: 28, padding: '0 8px',
    border: '1px solid #cbd5e1', background: '#fff',
    color: '#475569', borderRadius: 4,
    fontSize: 11, fontWeight: 700, cursor: 'pointer',
};
const lbl: React.CSSProperties = {
    display: 'block',
    fontSize: 11, fontWeight: 700, color: '#475569',
    textTransform: 'uppercase', letterSpacing: 0.5,
    marginBottom: 6,
};
const inp: React.CSSProperties = {
    width: '100%', padding: '8px 11px',
    border: '1px solid #cbd5e1', borderRadius: 6,
    fontSize: 13, fontFamily: 'inherit', color: '#0f172a',
    background: '#fff', outline: 'none',
};
