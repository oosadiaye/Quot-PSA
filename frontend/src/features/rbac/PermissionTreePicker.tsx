/**
 * PermissionTreePicker
 * ====================
 * Module-grouped, searchable, checkbox tree for selecting granular
 * permissions on a role. Backed by the
 * `/api/v1/core/roles/permission-catalogue/` endpoint.
 *
 * Design notes:
 *   - The catalogue can be ~150 rows; flat list would be unusable.
 *     Grouping by module → resource → permission makes it scannable.
 *   - "All in module" / "All in resource" toggles are essential —
 *     a budget officer needs ~10 permissions and clicking each one
 *     individually is friction. Bulk toggles are explicit so admins
 *     don't accidentally over-grant.
 *   - Risk level is shown as a coloured pill so admins see at a
 *     glance which permissions carry audit weight (critical perms
 *     get a red badge, high orange, medium amber, low slate).
 *   - Search filters across code + label + module + resource so
 *     "approve" or "ipc.approve" both narrow the tree.
 *
 * The component is fully controlled — parent owns the selected set
 * (a Set<string> of permission codes) and re-renders when it changes.
 * That's the cleanest path for the role-editor's "preview SoD
 * violations" sidebar to react in real time as the admin checks /
 * unchecks boxes.
 */
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight, ChevronDown, Search, Shield } from 'lucide-react';
import apiClient from '../../api/client';

interface PermissionRow {
    id: number;
    code: string;
    action: string;
    label: string;
    description: string;
    risk_level: 'low' | 'medium' | 'high' | 'critical';
    is_system: boolean;
}

interface ResourceGroup {
    resource: string;
    permissions: PermissionRow[];
}

interface ModuleGroup {
    module: string;
    module_display: string;
    resources: ResourceGroup[];
}

interface Props {
    /** Set of permission codes currently selected. Controlled. */
    value: Set<string>;
    /** Called with the new set (a fresh Set, never a mutation). */
    onChange: (next: Set<string>) => void;
    /** When true, all checkboxes are read-only. */
    disabled?: boolean;
    /**
     * Optional callback fired when the catalogue first loads. Useful
     * for the SoD preview sidebar to know the total catalogue size.
     */
    onCatalogueLoaded?: (totalPermissions: number) => void;
}

const RISK_COLORS: Record<string, { bg: string; fg: string; label: string }> = {
    low:      { bg: '#f1f5f9', fg: '#475569', label: 'Low' },
    medium:   { bg: '#fef3c7', fg: '#92400e', label: 'Medium' },
    high:     { bg: '#fed7aa', fg: '#9a3412', label: 'High' },
    critical: { bg: '#fee2e2', fg: '#991b1b', label: 'Critical' },
};

export default function PermissionTreePicker({
    value, onChange, disabled, onCatalogueLoaded,
}: Props) {
    const [search, setSearch] = useState('');
    const [expanded, setExpanded] = useState<Set<string>>(new Set());

    const { data: catalogue = [], isLoading } = useQuery<ModuleGroup[]>({
        queryKey: ['permission-catalogue'],
        queryFn: async () => {
            const res = await apiClient.get('/core/roles/permission-catalogue/');
            return res.data;
        },
        staleTime: 5 * 60 * 1000, // catalogue is stable; cache for 5 min
    });

    // Notify parent of catalogue size once.
    useMemo(() => {
        if (catalogue.length && onCatalogueLoaded) {
            const total = catalogue.reduce(
                (acc, m) => acc + m.resources.reduce((a, r) => a + r.permissions.length, 0),
                0,
            );
            onCatalogueLoaded(total);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [catalogue.length]);

    const filtered = useMemo<ModuleGroup[]>(() => {
        if (!search.trim()) return catalogue;
        const q = search.toLowerCase();
        return catalogue
            .map((mod) => ({
                ...mod,
                resources: mod.resources
                    .map((res) => ({
                        ...res,
                        permissions: res.permissions.filter((p) =>
                            p.code.toLowerCase().includes(q) ||
                            p.label.toLowerCase().includes(q) ||
                            p.action.toLowerCase().includes(q) ||
                            mod.module_display.toLowerCase().includes(q) ||
                            res.resource.toLowerCase().includes(q),
                        ),
                    }))
                    .filter((res) => res.permissions.length > 0),
            }))
            .filter((mod) => mod.resources.length > 0);
    }, [search, catalogue]);

    // Auto-expand modules that have search hits so the user sees them.
    const effectivelyExpanded = useMemo(() => {
        if (!search.trim()) return expanded;
        const set = new Set(expanded);
        filtered.forEach((m) => set.add(m.module));
        return set;
    }, [search, filtered, expanded]);

    const toggleModule = (module: string) => {
        const next = new Set(expanded);
        if (next.has(module)) next.delete(module);
        else next.add(module);
        setExpanded(next);
    };

    const togglePerm = (code: string) => {
        if (disabled) return;
        const next = new Set(value);
        if (next.has(code)) next.delete(code);
        else next.add(code);
        onChange(next);
    };

    const toggleResource = (perms: PermissionRow[]) => {
        if (disabled) return;
        const codes = perms.map((p) => p.code);
        const allSelected = codes.every((c) => value.has(c));
        const next = new Set(value);
        if (allSelected) codes.forEach((c) => next.delete(c));
        else codes.forEach((c) => next.add(c));
        onChange(next);
    };

    const toggleModuleAll = (mod: ModuleGroup) => {
        if (disabled) return;
        const codes = mod.resources.flatMap((r) => r.permissions.map((p) => p.code));
        const allSelected = codes.every((c) => value.has(c));
        const next = new Set(value);
        if (allSelected) codes.forEach((c) => next.delete(c));
        else codes.forEach((c) => next.add(c));
        onChange(next);
    };

    if (isLoading) {
        return (
            <div style={{ padding: 24, textAlign: 'center', color: '#64748b' }}>
                Loading permission catalogue…
            </div>
        );
    }

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {/* Search bar */}
            <div style={{
                position: 'relative',
                display: 'flex', alignItems: 'center',
            }}>
                <Search
                    size={16}
                    style={{
                        position: 'absolute', left: 12, color: '#94a3b8',
                        pointerEvents: 'none',
                    }}
                />
                <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search permissions — e.g. 'approve', 'ipc', 'budget.appropriation'"
                    style={{
                        width: '100%', padding: '9px 12px 9px 36px',
                        border: '1px solid #cbd5e1', borderRadius: 8,
                        fontSize: 13, fontFamily: 'inherit',
                    }}
                />
                <div style={{
                    position: 'absolute', right: 12,
                    fontSize: 12, color: '#64748b', fontWeight: 600,
                }}>
                    {value.size} selected
                </div>
            </div>

            {/* Tree */}
            <div style={{
                border: '1px solid #e2e8f0', borderRadius: 8,
                background: '#fff', maxHeight: 560, overflowY: 'auto',
            }}>
                {filtered.length === 0 && (
                    <div style={{ padding: 24, textAlign: 'center', color: '#94a3b8' }}>
                        No permissions match your search.
                    </div>
                )}
                {filtered.map((mod) => {
                    const isOpen = effectivelyExpanded.has(mod.module);
                    const moduleCodes = mod.resources.flatMap((r) =>
                        r.permissions.map((p) => p.code),
                    );
                    const moduleSelected = moduleCodes.filter((c) => value.has(c)).length;
                    return (
                        <div key={mod.module} style={{
                            borderBottom: '1px solid #f1f5f9',
                        }}>
                            {/* Module header */}
                            <div style={{
                                display: 'flex', alignItems: 'center',
                                padding: '10px 12px', gap: 8,
                                background: '#f8fafc', cursor: 'pointer',
                            }} onClick={() => toggleModule(mod.module)}>
                                {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                                <Shield size={14} style={{ color: '#1e40af' }} />
                                <strong style={{ fontSize: 13, color: '#0f172a' }}>
                                    {mod.module_display}
                                </strong>
                                <span style={{
                                    fontSize: 11, color: '#64748b', fontWeight: 500,
                                }}>
                                    ({moduleSelected}/{moduleCodes.length})
                                </span>
                                <div style={{ flex: 1 }} />
                                <button
                                    type="button"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        toggleModuleAll(mod);
                                    }}
                                    disabled={disabled}
                                    style={{
                                        padding: '3px 9px', fontSize: 11,
                                        border: '1px solid #cbd5e1', background: '#fff',
                                        color: '#1e40af', borderRadius: 4,
                                        fontWeight: 600, cursor: 'pointer',
                                    }}
                                >
                                    {moduleSelected === moduleCodes.length ? 'Clear all' : 'Select all'}
                                </button>
                            </div>

                            {/* Resources within module */}
                            {isOpen && mod.resources.map((res) => {
                                const resCodes = res.permissions.map((p) => p.code);
                                const resSelected = resCodes.filter((c) => value.has(c)).length;
                                const allRes = resSelected === resCodes.length;
                                return (
                                    <div key={`${mod.module}.${res.resource}`} style={{
                                        padding: '8px 16px 8px 36px',
                                    }}>
                                        <div style={{
                                            display: 'flex', alignItems: 'center', gap: 8,
                                            paddingBottom: 6,
                                        }}>
                                            <span style={{
                                                fontSize: 12, fontWeight: 700, color: '#475569',
                                                textTransform: 'uppercase', letterSpacing: 0.4,
                                            }}>
                                                {res.resource}
                                            </span>
                                            <span style={{ fontSize: 11, color: '#94a3b8' }}>
                                                {resSelected}/{resCodes.length}
                                            </span>
                                            <div style={{ flex: 1 }} />
                                            <button
                                                type="button"
                                                onClick={() => toggleResource(res.permissions)}
                                                disabled={disabled}
                                                style={{
                                                    padding: '2px 7px', fontSize: 10,
                                                    border: '1px solid #e2e8f0', background: '#fff',
                                                    color: '#64748b', borderRadius: 4,
                                                    cursor: 'pointer',
                                                }}
                                            >
                                                {allRes ? 'Clear' : 'All'}
                                            </button>
                                        </div>
                                        {res.permissions.map((p) => (
                                            <PermissionRow
                                                key={p.code}
                                                perm={p}
                                                checked={value.has(p.code)}
                                                onToggle={() => togglePerm(p.code)}
                                                disabled={disabled}
                                            />
                                        ))}
                                    </div>
                                );
                            })}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

function PermissionRow({
    perm, checked, onToggle, disabled,
}: {
    perm: PermissionRow;
    checked: boolean;
    onToggle: () => void;
    disabled?: boolean;
}) {
    const risk = RISK_COLORS[perm.risk_level];
    return (
        <label
            style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '6px 8px', borderRadius: 6,
                cursor: disabled ? 'not-allowed' : 'pointer',
                background: checked ? '#dbeafe' : 'transparent',
            }}
            onMouseEnter={(e) => {
                if (!checked) e.currentTarget.style.background = '#f8fafc';
            }}
            onMouseLeave={(e) => {
                if (!checked) e.currentTarget.style.background = 'transparent';
            }}
        >
            <input
                type="checkbox"
                checked={checked}
                onChange={onToggle}
                disabled={disabled}
                style={{ cursor: disabled ? 'not-allowed' : 'pointer' }}
            />
            <code style={{
                fontFamily: 'JetBrains Mono, ui-monospace, monospace',
                fontSize: 11, color: '#475569', minWidth: 220,
            }}>
                {perm.code}
            </code>
            <span style={{ fontSize: 12.5, color: '#0f172a', flex: 1 }}>
                {perm.label}
            </span>
            <span
                title={`Risk level: ${risk.label}`}
                style={{
                    padding: '2px 7px', fontSize: 10, fontWeight: 700,
                    background: risk.bg, color: risk.fg,
                    borderRadius: 999, letterSpacing: 0.4,
                    textTransform: 'uppercase',
                }}
            >
                {risk.label}
            </span>
        </label>
    );
}
