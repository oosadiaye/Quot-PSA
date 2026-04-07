import { useEffect, useState } from 'react';
import { useInventorySettings, useUpdateInventorySettings } from '../inventory/hooks/useInventory';
import Sidebar from '../../components/Sidebar';
import BackButton from '../../components/BackButton';
import LoadingScreen from '../../components/common/LoadingScreen';
import {
    Package, Zap, ShoppingCart, CheckCircle, Info,
    AlertTriangle, ToggleLeft, ToggleRight,
} from 'lucide-react';

// ─── Tiny toggle switch ───────────────────────────────────────────────────────

function Toggle({ value, onChange, disabled }: { value: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={value}
            disabled={disabled}
            onClick={() => !disabled && onChange(!value)}
            style={{
                position: 'relative',
                display: 'inline-flex',
                width: '48px',
                height: '26px',
                borderRadius: '13px',
                border: 'none',
                cursor: disabled ? 'not-allowed' : 'pointer',
                background: value ? 'var(--color-primary)' : '#cbd5e1',
                transition: 'background 0.2s',
                flexShrink: 0,
                opacity: disabled ? 0.5 : 1,
                padding: 0,
            }}
        >
            <span style={{
                position: 'absolute',
                top: '3px',
                left: value ? '25px' : '3px',
                width: '20px',
                height: '20px',
                borderRadius: '50%',
                background: '#fff',
                boxShadow: '0 1px 4px rgba(0,0,0,0.25)',
                transition: 'left 0.2s',
            }} />
        </button>
    );
}

// ─── Setting row layout ───────────────────────────────────────────────────────

function SettingRow({
    label, description, value, onChange, disabled, indent = false,
}: {
    label: string;
    description?: string;
    value: boolean;
    onChange: (v: boolean) => void;
    disabled?: boolean;
    indent?: boolean;
}) {
    return (
        <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
            padding: indent ? '1rem 1.25rem 1rem 2.5rem' : '1.25rem',
            borderBottom: '1px solid var(--color-border)',
            background: indent ? 'var(--color-surface)' : undefined,
            opacity: disabled ? 0.55 : 1,
            transition: 'opacity 0.2s',
            gap: '1.5rem',
        }}>
            <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)', marginBottom: description ? '0.2rem' : 0 }}>
                    {label}
                </div>
                {description && (
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', lineHeight: 1.5 }}>
                        {description}
                    </div>
                )}
            </div>
            <Toggle value={value} onChange={onChange} disabled={disabled} />
        </div>
    );
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function InventorySettingsPage() {
    const { data: settingsRaw, isLoading } = useInventorySettings();
    const updateSettings = useUpdateInventorySettings();

    const [autoPo, setAutoPo]           = useState(false);
    const [draftOnly, setDraftOnly]     = useState(true);
    const [saveMsg, setSaveMsg]         = useState<string | null>(null);
    const [saveErr, setSaveErr]         = useState<string | null>(null);

    // Sync local state from server
    useEffect(() => {
        if (!settingsRaw) return;
        setAutoPo(settingsRaw.auto_po_enabled ?? false);
        setDraftOnly(settingsRaw.auto_po_draft_only ?? true);
    }, [settingsRaw]);

    const handleToggle = async (field: 'auto_po_enabled' | 'auto_po_draft_only', value: boolean) => {
        if (field === 'auto_po_enabled') setAutoPo(value);
        if (field === 'auto_po_draft_only') setDraftOnly(value);
        setSaveMsg(null);
        setSaveErr(null);
        try {
            await updateSettings.mutateAsync({ [field]: value });
            setSaveMsg('Settings saved.');
            setTimeout(() => setSaveMsg(null), 2500);
        } catch {
            setSaveErr('Failed to save. Please try again.');
            // revert
            if (field === 'auto_po_enabled') setAutoPo(!value);
            if (field === 'auto_po_draft_only') setDraftOnly(!value);
        }
    };

    if (isLoading) return <LoadingScreen message="Loading inventory settings..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <div style={{ flex: 1, marginLeft: '260px', minHeight: '100vh', background: 'var(--color-background)' }}>

                {/* ── Page header */}
                <div style={{
                    padding: '1.5rem 3rem 1.25rem',
                    borderBottom: '1px solid var(--color-border)',
                    background: 'var(--color-surface)',
                }}>
                    <BackButton />
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.25rem', marginTop: '0.5rem' }}>
                        <Package size={22} style={{ color: 'var(--color-primary)' }} />
                        <h1 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                            Inventory Settings
                        </h1>
                    </div>
                    <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
                        Configure inventory automation and replenishment behaviour for this organisation.
                    </p>
                </div>

                <div style={{ padding: '2.5rem 3rem', maxWidth: '860px' }}>

                    {/* Save status */}
                    {saveMsg && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1rem', background: 'rgba(16,185,129,0.1)', color: '#10b981', borderRadius: '8px', marginBottom: '1.5rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                            <CheckCircle size={15} /> {saveMsg}
                        </div>
                    )}
                    {saveErr && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1rem', background: 'rgba(239,68,68,0.1)', color: '#ef4444', borderRadius: '8px', marginBottom: '1.5rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                            <AlertTriangle size={15} /> {saveErr}
                        </div>
                    )}

                    {/* ── Section: Automation ──────────────────────────────── */}
                    <div style={{ marginBottom: '2rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                            <Zap size={16} style={{ color: 'var(--color-primary)' }} />
                            <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0 }}>Automation</h2>
                        </div>

                        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>

                            {/* Main toggle */}
                            <SettingRow
                                label="Automatic Purchase Order Creation"
                                description="When enabled, a Draft Purchase Order is automatically created the moment any item's stock falls at or below its reorder point. The PO is addressed to the item's preferred vendor."
                                value={autoPo}
                                onChange={v => handleToggle('auto_po_enabled', v)}
                                disabled={updateSettings.isPending}
                            />

                            {/* Sub-option — indented, only active when main toggle is on */}
                            <SettingRow
                                label='Always create as "Draft" (recommended)'
                                description="Auto-generated POs land in Draft status, requiring a buyer to review and submit. Disabling this would immediately submit POs — not recommended unless you have a trusted replenishment workflow."
                                value={draftOnly}
                                onChange={v => handleToggle('auto_po_draft_only', v)}
                                disabled={!autoPo || updateSettings.isPending}
                                indent
                            />

                        </div>
                    </div>

                    {/* ── Section: How it works ────────────────────────────── */}
                    <div style={{ marginBottom: '2rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                            <ShoppingCart size={16} style={{ color: 'var(--color-primary)' }} />
                            <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0 }}>How Auto PO Works</h2>
                        </div>

                        <div className="card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                            {[
                                {
                                    step: '1',
                                    color: '#3b82f6',
                                    title: 'Stock movement is posted',
                                    body: 'A Stock Out, Adjustment, or Transfer is recorded. The system checks whether total stock across all warehouses has dropped to or below the item\'s reorder point.',
                                },
                                {
                                    step: '2',
                                    color: '#f59e0b',
                                    title: 'Reorder threshold crossed',
                                    body: 'If the item now sits at or below its reorder point and has a preferred vendor and expense account configured, a Draft Purchase Order is auto-generated for the item\'s reorder quantity.',
                                },
                                {
                                    step: '3',
                                    color: '#10b981',
                                    title: 'Buyer reviews and submits',
                                    body: 'The Draft PO appears in Procurement → Purchase Orders. A buyer reviews qty, price, and vendor, then submits for approval. Only one open auto-PO exists per item at a time.',
                                },
                            ].map(({ step, color, title, body }) => (
                                <div key={step} style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
                                    <div style={{
                                        width: '28px', height: '28px', borderRadius: '50%',
                                        background: color + '20', color, fontWeight: 800,
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        fontSize: 'var(--text-sm)', flexShrink: 0,
                                    }}>{step}</div>
                                    <div>
                                        <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)', marginBottom: '0.2rem' }}>{title}</div>
                                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', lineHeight: 1.6 }}>{body}</div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* ── Section: Requirements ────────────────────────────── */}
                    <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                            <Info size={16} style={{ color: 'var(--color-primary)' }} />
                            <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0 }}>Item Requirements</h2>
                        </div>

                        <div className="card" style={{ padding: '1.25rem', background: 'rgba(245,158,11,0.04)', border: '1px solid rgba(245,158,11,0.2)' }}>
                            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem' }}>
                                <AlertTriangle size={16} style={{ color: '#f59e0b', flexShrink: 0, marginTop: '1px' }} />
                                <span style={{ fontWeight: 600, fontSize: 'var(--text-sm)', color: '#f59e0b' }}>
                                    Each item must be configured correctly for auto-PO to trigger
                                </span>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                {[
                                    ['Reorder Point', 'Set on the product — the stock level that triggers replenishment'],
                                    ['Reorder Quantity', 'How many units to order when the alert fires'],
                                    ['Preferred Vendor', 'The supplier the PO will be addressed to (set on the product)'],
                                    ['Expense Account', 'The GL account for the PO line (set on the product)'],
                                ].map(([field, desc]) => (
                                    <div key={field} style={{ display: 'flex', gap: '0.75rem', fontSize: 'var(--text-sm)' }}>
                                        <span style={{ fontWeight: 600, minWidth: '140px', flexShrink: 0 }}>{field}</span>
                                        <span style={{ color: 'var(--color-text-muted)' }}>{desc}</span>
                                    </div>
                                ))}
                            </div>
                            <div style={{ marginTop: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                Items missing any of these fields will be skipped — a log entry is recorded for each skipped item.
                            </div>
                        </div>
                    </div>

                </div>
            </div>
        </div>
    );
}
