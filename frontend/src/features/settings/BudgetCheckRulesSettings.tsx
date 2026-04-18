/**
 * BudgetCheckRulesSettings — tenant-configurable budget-check policy.
 * Route: /settings/accounting/budget-check-rules
 *
 * Each row defines a contiguous GL-code range and the check level that
 * applies to postings within it:
 *   · NONE    — posts freely, no budget gate
 *   · WARNING — posts, but flags when appropriation ≥ threshold %
 *   · STRICT  — blocks posting when no appropriation / over budget
 *               across all modules (journals, PO, 3-way match,
 *               vendor invoice, payment voucher)
 *
 * The narrowest active rule wins (broad defaults + narrow overrides).
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, Save, AlertCircle, CheckCircle2, Info, ArrowLeft } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import apiClient from '../../api/client';
import { formatApiError } from '../../utils/apiError';

interface Rule {
    id?: number;
    gl_from: string;
    gl_to: string;
    check_level: 'NONE' | 'WARNING' | 'STRICT';
    warning_threshold_pct: string;
    description: string;
    priority: number;
    is_active: boolean;
    _new?: boolean;          // unsaved row flag
    _dirty?: boolean;        // modified since load
    _deleted?: boolean;      // marked for delete
}

const CHECK_LEVELS: Array<{ value: Rule['check_level']; label: string; hint: string; tint: string }> = [
    { value: 'NONE', label: 'No check', hint: 'Posts freely; no appropriation gate', tint: '#64748b' },
    { value: 'WARNING', label: 'Warning', hint: 'Posts, flags when utilisation ≥ threshold', tint: '#ca8a04' },
    { value: 'STRICT', label: 'Strict', hint: 'Blocks posting without an active appropriation', tint: '#dc2626' },
];

const lblStyle: React.CSSProperties = {
    fontSize: 11, fontWeight: 700, color: '#64748b',
    textTransform: 'uppercase', letterSpacing: '0.4px',
    display: 'block', marginBottom: 4,
};
const inputBase: React.CSSProperties = {
    width: '100%', padding: '8px 10px', fontSize: 13,
    borderRadius: 6, border: '1.5px solid #e2e8f0', background: '#fff',
    outline: 'none', fontFamily: 'inherit',
};

export default function BudgetCheckRulesSettings() {
    const navigate = useNavigate();
    const [rules, setRules] = useState<Rule[]>([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    const load = async () => {
        setLoading(true);
        try {
            const { data } = await apiClient.get('/accounting/budget-check-rules/', {
                params: { page_size: 200 },
            });
            const rows: Rule[] = (data?.results ?? data ?? []).map((r: any) => ({
                id: r.id,
                gl_from: r.gl_from,
                gl_to: r.gl_to,
                check_level: r.check_level,
                warning_threshold_pct: String(r.warning_threshold_pct ?? '80'),
                description: r.description ?? '',
                priority: r.priority ?? 0,
                is_active: r.is_active ?? true,
            }));
            setRules(rows);
        } catch (err) {
            setError(formatApiError(err, 'Failed to load budget check rules.'));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { load(); }, []);

    const addLine = () => {
        setRules(prev => [
            ...prev,
            {
                gl_from: '',
                gl_to: '',
                check_level: 'WARNING',
                warning_threshold_pct: '80',
                description: '',
                priority: 0,
                is_active: true,
                _new: true,
                _dirty: true,
            },
        ]);
    };

    const updateLine = <K extends keyof Rule>(idx: number, field: K, value: Rule[K]) => {
        setRules(prev => prev.map((r, i) => i === idx ? { ...r, [field]: value, _dirty: true } : r));
    };

    const removeLine = (idx: number) => {
        setRules(prev => {
            const next = [...prev];
            const row = next[idx];
            if (row._new) {
                // Not saved yet — just drop it
                next.splice(idx, 1);
            } else {
                // Mark for delete, keep in state so user can undo before Save
                next[idx] = { ...row, _deleted: true, _dirty: true };
            }
            return next;
        });
    };

    const restoreLine = (idx: number) => {
        setRules(prev => prev.map((r, i) => i === idx ? { ...r, _deleted: false } : r));
    };

    const saveAll = async () => {
        setSaving(true);
        setError('');
        setSuccess('');

        try {
            // Validate client-side first
            for (const r of rules) {
                if (r._deleted) continue;
                if (!r.gl_from || !r.gl_to) {
                    throw new Error(`Row "${r.description || '(no description)'}" — GL From and GL To are required.`);
                }
                if (r.gl_from > r.gl_to) {
                    throw new Error(`Row "${r.description || r.gl_from}" — GL To must be ≥ GL From.`);
                }
            }

            // Batch: DELETE, then PATCH, then POST — order matters to avoid
            // range-conflict errors (deleting old before inserting the
            // replacement covers the range cleanly).
            const deletes = rules.filter(r => r._deleted && r.id);
            const updates = rules.filter(r => r.id && r._dirty && !r._new && !r._deleted);
            const creates = rules.filter(r => r._new && !r._deleted);

            for (const r of deletes) {
                await apiClient.delete(`/accounting/budget-check-rules/${r.id}/`);
            }
            for (const r of updates) {
                await apiClient.patch(`/accounting/budget-check-rules/${r.id}/`, toPayload(r));
            }
            for (const r of creates) {
                await apiClient.post('/accounting/budget-check-rules/', toPayload(r));
            }

            setSuccess(
                `Saved — ${creates.length} added · ${updates.length} updated · ${deletes.length} removed.`
            );
            await load();
            setTimeout(() => setSuccess(''), 5000);
        } catch (err: any) {
            setError(err?.message?.startsWith('Row') ? err.message : formatApiError(err, 'Failed to save rules.'));
        } finally {
            setSaving(false);
        }
    };

    const visibleRules = rules.filter(r => !r._deleted);
    const deletedCount = rules.filter(r => r._deleted).length;
    const dirtyCount = rules.filter(r => r._dirty).length;

    if (loading) {
        return (
            <div style={{ display: 'flex' }}>
                <Sidebar />
                <main style={{ flex: 1, marginLeft: 260, padding: 40, color: '#94a3b8' }}>Loading…</main>
            </div>
        );
    }

    return (
        <div style={{ display: 'flex', background: '#f5f7fb', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: 260, padding: '32px' }}>
                <PageHeader
                    title="Budget Check Rules"
                    subtitle="GL-range policy for budget appropriation enforcement — applies across all posting modules"
                    onBack={() => navigate('/settings/accounting')}
                    actions={
                        <button
                            type="button"
                            onClick={() => navigate('/settings/accounting')}
                            style={{
                                padding: '8px 16px', borderRadius: 8, cursor: 'pointer',
                                background: 'rgba(255,255,255,0.12)', color: '#fff',
                                border: '1px solid rgba(255,255,255,0.25)', fontSize: 13, fontWeight: 600,
                                display: 'flex', alignItems: 'center', gap: 6,
                            }}
                        >
                            <ArrowLeft size={14} /> Back to Accounting Settings
                        </button>
                    }
                />

                {/* ── Info banner ─────────────────────────────────────── */}
                <div style={{
                    padding: '12px 16px', borderRadius: 8, marginBottom: 16,
                    background: '#f0f9ff', border: '1px solid #bae6fd', color: '#075985',
                    display: 'flex', alignItems: 'flex-start', gap: 10, fontSize: 13, lineHeight: 1.6,
                }}>
                    <Info size={16} style={{ flexShrink: 0, marginTop: 1 }} />
                    <div>
                        <strong>How rules resolve:</strong> when more than one rule matches a GL code, the
                        <em> narrowest range</em> wins. Ties break by <em>priority</em> (higher wins).
                        Accounts outside every active rule fall back to the global default — typically NONE
                        (no check). <strong>STRICT</strong> applies across all modules: journal post, PO
                        approval, 3-way match invoice verification, vendor invoice post, payment voucher.
                    </div>
                </div>

                {/* ── Error / Success banners ─────────────────────────── */}
                {error && (
                    <div style={{
                        padding: '12px 16px', borderRadius: 8, marginBottom: 14,
                        background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c',
                        display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13,
                    }}>
                        <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} /> {error}
                    </div>
                )}
                {success && (
                    <div style={{
                        padding: '12px 16px', borderRadius: 8, marginBottom: 14,
                        background: '#f0fdf4', border: '1px solid #86efac', color: '#166534',
                        display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 500,
                    }}>
                        <CheckCircle2 size={16} /> {success}
                    </div>
                )}

                {/* ── Rules table ─────────────────────────────────────── */}
                <div style={{
                    background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0',
                    padding: 20, marginBottom: 20,
                }}>
                    <div style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        marginBottom: 14, paddingBottom: 12, borderBottom: '1px solid #e2e8f0',
                    }}>
                        <div>
                            <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#0f172a' }}>
                                Rules ({visibleRules.length})
                            </h3>
                            {(dirtyCount > 0 || deletedCount > 0) && (
                                <div style={{ fontSize: 12, color: '#b45309', marginTop: 4 }}>
                                    Unsaved changes: {dirtyCount} modified · {deletedCount} pending delete
                                </div>
                            )}
                        </div>
                        <button
                            type="button"
                            onClick={addLine}
                            style={{
                                padding: '8px 14px', borderRadius: 8, cursor: 'pointer',
                                background: '#1a237e', color: '#fff', border: 'none',
                                display: 'flex', alignItems: 'center', gap: 6,
                                fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                            }}
                        >
                            <Plus size={14} /> Add Line
                        </button>
                    </div>

                    {visibleRules.length === 0 ? (
                        <div style={{
                            padding: 40, textAlign: 'center', color: '#94a3b8', fontSize: 14,
                            background: '#f8fafc', borderRadius: 8, border: '1px dashed #cbd5e1',
                        }}>
                            No rules yet — click <strong>Add Line</strong> to define one.
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                            {rules.map((r, i) => {
                                if (r._deleted) {
                                    return (
                                        <div key={i} style={{
                                            padding: '10px 14px', borderRadius: 8,
                                            background: '#fef2f2', border: '1px dashed #fca5a5',
                                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                            fontSize: 13, color: '#991b1b',
                                        }}>
                                            <span>
                                                <strong>Will delete:</strong>{' '}
                                                {r.gl_from}–{r.gl_to} · {r.check_level}{' '}
                                                {r.description ? `· ${r.description}` : ''}
                                            </span>
                                            <button
                                                type="button"
                                                onClick={() => restoreLine(i)}
                                                style={{
                                                    background: 'none', border: 'none', cursor: 'pointer',
                                                    color: '#1a237e', fontSize: 12, fontWeight: 600,
                                                }}
                                            >
                                                Undo
                                            </button>
                                        </div>
                                    );
                                }
                                const tint = CHECK_LEVELS.find(c => c.value === r.check_level)?.tint || '#64748b';
                                return (
                                    <div key={i} style={{
                                        padding: 14, borderRadius: 10,
                                        background: r._new ? '#f0fdf4' : '#fff',
                                        border: `1.5px solid ${r._new ? '#86efac' : '#e2e8f0'}`,
                                        borderLeft: `4px solid ${tint}`,
                                        display: 'grid',
                                        gridTemplateColumns: '120px 120px 150px 100px 1fr 70px 60px 40px',
                                        gap: 12, alignItems: 'end',
                                    }}>
                                        <div>
                                            <label style={lblStyle}>GL From *</label>
                                            <input
                                                style={{ ...inputBase, fontFamily: 'monospace' }}
                                                value={r.gl_from}
                                                onChange={e => updateLine(i, 'gl_from', e.target.value)}
                                                placeholder="e.g. 21000000"
                                            />
                                        </div>
                                        <div>
                                            <label style={lblStyle}>GL To *</label>
                                            <input
                                                style={{ ...inputBase, fontFamily: 'monospace' }}
                                                value={r.gl_to}
                                                onChange={e => updateLine(i, 'gl_to', e.target.value)}
                                                placeholder="e.g. 21999999"
                                            />
                                        </div>
                                        <div>
                                            <label style={lblStyle}>Check Level *</label>
                                            <select
                                                style={inputBase}
                                                value={r.check_level}
                                                onChange={e => updateLine(i, 'check_level', e.target.value as Rule['check_level'])}
                                            >
                                                {CHECK_LEVELS.map(c => (
                                                    <option key={c.value} value={c.value}>{c.label}</option>
                                                ))}
                                            </select>
                                        </div>
                                        <div>
                                            <label style={lblStyle}>Warn ≥ (%)</label>
                                            <input
                                                type="number" step="1" min="0" max="100"
                                                disabled={r.check_level !== 'WARNING'}
                                                style={{
                                                    ...inputBase,
                                                    background: r.check_level === 'WARNING' ? '#fff' : '#f1f5f9',
                                                    color: r.check_level === 'WARNING' ? '#0f172a' : '#94a3b8',
                                                }}
                                                value={r.warning_threshold_pct}
                                                onChange={e => updateLine(i, 'warning_threshold_pct', e.target.value)}
                                            />
                                        </div>
                                        <div>
                                            <label style={lblStyle}>Description</label>
                                            <input
                                                style={inputBase}
                                                value={r.description}
                                                onChange={e => updateLine(i, 'description', e.target.value)}
                                                placeholder="e.g. Personnel Costs"
                                            />
                                        </div>
                                        <div>
                                            <label style={lblStyle}>Priority</label>
                                            <input
                                                type="number"
                                                style={{ ...inputBase, textAlign: 'right' }}
                                                value={r.priority}
                                                onChange={e => updateLine(i, 'priority', Number(e.target.value))}
                                            />
                                        </div>
                                        <div>
                                            <label style={lblStyle}>Active</label>
                                            <div style={{ height: 34, display: 'flex', alignItems: 'center' }}>
                                                <input
                                                    type="checkbox"
                                                    checked={r.is_active}
                                                    onChange={e => updateLine(i, 'is_active', e.target.checked)}
                                                    style={{ width: 18, height: 18, accentColor: '#1a237e', cursor: 'pointer' }}
                                                />
                                            </div>
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                            <button
                                                type="button"
                                                onClick={() => removeLine(i)}
                                                title="Remove this rule"
                                                style={{
                                                    padding: 6, border: 'none', cursor: 'pointer',
                                                    background: 'rgba(239,68,68,0.1)', color: '#dc2626',
                                                    borderRadius: 6, display: 'flex', alignItems: 'center',
                                                }}
                                            >
                                                <Trash2 size={14} />
                                            </button>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>

                {/* ── Action bar ──────────────────────────────────────── */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                    <button
                        type="button"
                        onClick={() => load()}
                        disabled={saving}
                        style={{
                            padding: '10px 20px', borderRadius: 8, cursor: 'pointer',
                            background: '#fff', color: '#64748b', border: '1px solid #e2e8f0',
                            fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                        }}
                    >
                        Discard Changes
                    </button>
                    <button
                        type="button"
                        onClick={saveAll}
                        disabled={saving || (dirtyCount === 0 && deletedCount === 0)}
                        style={{
                            padding: '10px 24px', borderRadius: 8,
                            cursor: saving || (dirtyCount === 0 && deletedCount === 0) ? 'not-allowed' : 'pointer',
                            background: saving || (dirtyCount === 0 && deletedCount === 0) ? '#94a3b8' : '#1a237e',
                            color: '#fff', border: 'none',
                            fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                            display: 'flex', alignItems: 'center', gap: 6,
                        }}
                    >
                        <Save size={14} />
                        {saving ? 'Saving…' : 'Save All Rules'}
                    </button>
                </div>
            </main>
        </div>
    );
}

function toPayload(r: Rule) {
    return {
        gl_from: r.gl_from,
        gl_to: r.gl_to,
        check_level: r.check_level,
        warning_threshold_pct: Number(r.warning_threshold_pct) || 80,
        description: r.description,
        priority: r.priority,
        is_active: r.is_active,
    };
}
