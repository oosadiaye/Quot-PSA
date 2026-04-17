import { useEffect, useState } from 'react';
import { useInventorySettings, useUpdateInventorySettings } from '../inventory/hooks/useInventory';
import SettingsLayout from './SettingsLayout';
import LoadingScreen from '../../components/common/LoadingScreen';
import {
    Package, Zap, ShoppingCart, CheckCircle, Info,
    AlertTriangle,
} from 'lucide-react';

// ─── Card style constant ─────────────────────────────────────────────────────

const CARD_STYLE: React.CSSProperties = {
    background: 'white',
    borderRadius: '20px',
    padding: '28px 32px',
    border: '1px solid #e2e8f0',
    boxShadow: '0 1px 3px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.02)',
};

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
                background: value ? '#059669' : '#cbd5e1',
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
            padding: indent ? '16px 20px 16px 40px' : '20px',
            borderBottom: '1px solid #e2e8f0',
            background: indent ? '#f8fafc' : undefined,
            opacity: disabled ? 0.55 : 1,
            transition: 'opacity 0.2s',
            gap: '24px',
        }}>
            <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: '14px', color: '#0f172a', marginBottom: description ? '3px' : 0 }}>
                    {label}
                </div>
                {description && (
                    <div style={{ fontSize: '13px', color: '#94a3b8', lineHeight: 1.5 }}>
                        {description}
                    </div>
                )}
            </div>
            <Toggle value={value} onChange={onChange} disabled={disabled} />
        </div>
    );
}

// ─── Section icon badge ──────────────────────────────────────────────────────

function SectionBadge({ icon, color }: { icon: React.ReactNode; color: string }) {
    return (
        <div style={{
            width: '32px', height: '32px', borderRadius: '10px',
            background: `linear-gradient(135deg, ${color}, ${color}dd)`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: `0 2px 8px ${color}33`,
            flexShrink: 0,
        }}>
            {icon}
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
        <SettingsLayout
            title="Inventory Settings"
            breadcrumb="Inventory"
            icon={<Package size={22} color="white" />}
            gradient="linear-gradient(135deg, #059669, #047857)"
            gradientShadow="rgba(5, 150, 105, 0.25)"
            subtitle="Configure inventory automation and replenishment behaviour."
        >
            {/* Save status */}
            {saveMsg && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '8px',
                    padding: '10px 16px', background: 'rgba(16,185,129,0.08)',
                    color: '#059669', borderRadius: '12px', marginBottom: '24px',
                    fontSize: '14px', fontWeight: 600,
                    border: '1px solid rgba(16,185,129,0.15)',
                }}>
                    <CheckCircle size={16} /> {saveMsg}
                </div>
            )}
            {saveErr && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '8px',
                    padding: '10px 16px', background: 'rgba(239,68,68,0.08)',
                    color: '#ef4444', borderRadius: '12px', marginBottom: '24px',
                    fontSize: '14px', fontWeight: 600,
                    border: '1px solid rgba(239,68,68,0.15)',
                }}>
                    <AlertTriangle size={16} /> {saveErr}
                </div>
            )}

            {/* ── Section: Automation ──────────────────────────────── */}
            <div style={{ marginBottom: '32px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
                    <SectionBadge icon={<Zap size={16} color="white" />} color="#059669" />
                    <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#0f172a' }}>Automation</h2>
                </div>

                <div style={{ ...CARD_STYLE, padding: 0, overflow: 'hidden' }}>
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
            <div style={{ marginBottom: '32px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
                    <SectionBadge icon={<ShoppingCart size={16} color="white" />} color="#3b82f6" />
                    <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#0f172a' }}>How Auto PO Works</h2>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
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
                            color: '#059669',
                            title: 'Buyer reviews and submits',
                            body: 'The Draft PO appears in Procurement → Purchase Orders. A buyer reviews qty, price, and vendor, then submits for approval. Only one open auto-PO exists per item at a time.',
                        },
                    ].map(({ step, color, title, body }) => (
                        <div key={step} style={{
                            ...CARD_STYLE,
                            padding: '20px 24px',
                            display: 'flex', gap: '16px', alignItems: 'flex-start',
                        }}>
                            <div style={{
                                width: '32px', height: '32px', borderRadius: '50%',
                                background: `${color}18`, color, fontWeight: 800,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontSize: '14px', flexShrink: 0,
                                border: `2px solid ${color}30`,
                            }}>{step}</div>
                            <div>
                                <div style={{ fontWeight: 600, fontSize: '14px', color: '#0f172a', marginBottom: '4px' }}>{title}</div>
                                <div style={{ fontSize: '13px', color: '#94a3b8', lineHeight: 1.6 }}>{body}</div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* ── Section: Requirements ────────────────────────────── */}
            <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
                    <SectionBadge icon={<Info size={16} color="white" />} color="#f59e0b" />
                    <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#0f172a' }}>Item Requirements</h2>
                </div>

                <div style={{
                    ...CARD_STYLE,
                    background: 'rgba(245,158,11,0.04)',
                    border: '1px solid rgba(245,158,11,0.2)',
                }}>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '14px' }}>
                        <AlertTriangle size={16} style={{ color: '#f59e0b', flexShrink: 0, marginTop: '1px' }} />
                        <span style={{ fontWeight: 600, fontSize: '14px', color: '#f59e0b' }}>
                            Each item must be configured correctly for auto-PO to trigger
                        </span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {[
                            ['Reorder Point', 'Set on the product — the stock level that triggers replenishment'],
                            ['Reorder Quantity', 'How many units to order when the alert fires'],
                            ['Preferred Vendor', 'The supplier the PO will be addressed to (set on the product)'],
                            ['Expense Account', 'The GL account for the PO line (set on the product)'],
                        ].map(([field, desc]) => (
                            <div key={field} style={{ display: 'flex', gap: '12px', fontSize: '14px' }}>
                                <span style={{ fontWeight: 600, minWidth: '140px', flexShrink: 0, color: '#0f172a' }}>{field}</span>
                                <span style={{ color: '#94a3b8' }}>{desc}</span>
                            </div>
                        ))}
                    </div>
                    <div style={{ marginTop: '16px', fontSize: '13px', color: '#94a3b8' }}>
                        Items missing any of these fields will be skipped — a log entry is recorded for each skipped item.
                    </div>
                </div>
            </div>
        </SettingsLayout>
    );
}
