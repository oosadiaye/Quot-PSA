/**
 * UnclearedAdvanceWarning — single uniform popup used everywhere a
 * vendor-affecting posting can happen (AP invoice, IPC approve, PV
 * raise, outgoing payment, vendor ledger view).
 *
 * Mirrors SAP's F-54 "down-payment exists" prompt: when the vendor
 * has uncleared advances, the operator sees a yellow callout listing
 * each open advance with an "AD" tag (the Special-GL indicator) and
 * a "Clear Advance" button that triggers the contra-journal posting
 * in one click.
 *
 * One component, used everywhere — so the message is identical,
 * the actions are identical, and the audit trail captures the same
 * fields regardless of which surface the operator was on.
 */
import { Modal, App as AntApp, Popconfirm } from 'antd';
import { useState } from 'react';
import { AlertTriangle, ExternalLink, X as CloseIcon } from 'lucide-react';
import {
    useOutstandingAdvancesForVendor,
    useClearVendorAdvance,
    type VendorAdvance,
} from '../hooks/useVendorAdvances';
import { useCurrency } from '../../../context/CurrencyContext';

interface Props {
    /** Vendor we're posting against. ``null`` renders nothing. */
    vendorId: number | null | undefined;
    /**
     * What the user is trying to do — used for the toast on success
     * and the optional ``cleared_against_*`` audit pin sent to the
     * backend. e.g. ``{ type: 'IPC', id: 42, reference: 'IPC/2026/01' }``.
     */
    context?: {
        type?: string;
        id?: number | null;
        reference?: string;
    };
    /**
     * Visual variant:
     *   * ``'inline'``   — banner inside a form / panel (default)
     *   * ``'modal'``    — interrupts a flow (controlled by ``open``)
     *   * ``'compact'``  — single-line tag, used in dense headers
     */
    variant?: 'inline' | 'modal' | 'compact';
    /** Modal-only: external open/close control. */
    open?: boolean;
    onClose?: () => void;
    /** Callback after every successful clearance — useful when the
     *  parent wants to re-fetch its own data. */
    onCleared?: (advance: VendorAdvance) => void;
}

export default function UnclearedAdvanceWarning({
    vendorId,
    context,
    variant = 'inline',
    open,
    onClose,
    onCleared,
}: Props) {
    const { data, isLoading } = useOutstandingAdvancesForVendor(vendorId);
    const clearMut = useClearVendorAdvance();
    const { message } = AntApp.useApp();
    const { formatCurrency } = useCurrency();

    // ── Per-row clearance state ────────────────────────────────────
    // The popup lets the operator clear the FULL outstanding amount
    // per advance with one click (the most common case in PFM).
    // Partial clearances are still possible via the contract detail
    // page; this component is the fast path.
    const [pendingId, setPendingId] = useState<number | null>(null);

    if (!vendorId) return null;
    if (isLoading) return null;
    const advances = data?.open_advances ?? [];
    const total = parseFloat(data?.outstanding_total ?? '0') || 0;
    if (advances.length === 0) {
        // No advances → variant decides whether to show "all clear" or
        // collapse silently. Inline / compact collapse; modal renders
        // a friendly success message because it's modal-controlled.
        if (variant === 'modal' && open) {
            return (
                <Modal
                    open={open}
                    onCancel={onClose}
                    footer={null}
                    title="No Uncleared Advances"
                >
                    <p style={{ marginBottom: 0 }}>
                        This vendor has no outstanding advance payments — you can
                        proceed with the posting.
                    </p>
                </Modal>
            );
        }
        return null;
    }

    const handleClear = async (advance: VendorAdvance) => {
        setPendingId(advance.id);
        try {
            const updated = await clearMut.mutateAsync({
                id: advance.id,
                amount: advance.amount_outstanding,
                cleared_against_type: context?.type ?? '',
                cleared_against_id: context?.id ?? null,
                cleared_against_reference: context?.reference ?? '',
            });
            message.success(
                `Cleared ${formatCurrency(parseFloat(advance.amount_outstanding))} `
                + `against advance ${advance.reference}.`,
            );
            if (onCleared) onCleared(updated);
        } catch (e) {
            message.error(
                (e as { response?: { data?: { error?: string } } })?.response?.data?.error
                || 'Failed to clear advance.',
            );
        } finally {
            setPendingId(null);
        }
    };

    const body = (
        <div style={containerStyle}>
            <div style={headerStyle}>
                <AlertTriangle size={16} color="#a16207" />
                <strong>Uncleared Advance Payment</strong>
                <span style={pillStyle}>AD</span>
                <span style={{ marginLeft: 'auto', fontSize: 11, color: '#92400e' }}>
                    Outstanding total:{' '}
                    <strong style={{ fontFamily: 'monospace' }}>
                        {formatCurrency(total)}
                    </strong>
                </span>
            </div>
            <p style={bodyTextStyle}>
                This vendor has {advances.length} uncleared advance
                {advances.length === 1 ? '' : 's'}. Clear before proceeding —
                clearing reduces the net cash payable on the next AP / IPC / PV.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {advances.map((adv) => {
                    const outstanding = parseFloat(adv.amount_outstanding) || 0;
                    return (
                        <div key={adv.id} style={rowStyle}>
                            <span style={adTagStyle}>AD</span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={refLineStyle}>
                                    <strong>{adv.reference}</strong>
                                    <span style={muteTagStyle}>{adv.source_type.replace('_', ' ')}</span>
                                    <span
                                        style={{
                                            ...muteTagStyle,
                                            background: adv.status === 'PARTIAL' ? '#dbeafe' : '#fef3c7',
                                            color: adv.status === 'PARTIAL' ? '#1d4ed8' : '#a16207',
                                        }}
                                    >
                                        {adv.status}
                                    </span>
                                </div>
                                <div style={amountLineStyle}>
                                    Paid {formatCurrency(parseFloat(adv.amount_paid))}
                                    {' · '}
                                    Recovered {formatCurrency(parseFloat(adv.amount_recovered))}
                                    {' · '}
                                    <strong style={{ color: '#b91c1c' }}>
                                        Outstanding {formatCurrency(outstanding)}
                                    </strong>
                                </div>
                            </div>
                            <Popconfirm
                                title="Clear this advance?"
                                description={
                                    <span>
                                        Posts the F-54 contra journal:
                                        <br />
                                        <strong>DR Accounts Payable</strong>{' '}
                                        {formatCurrency(outstanding)}
                                        <br />
                                        <strong>CR Vendor Advance (AD)</strong>{' '}
                                        {formatCurrency(outstanding)}
                                        <br /><br />
                                        Cannot be undone — the contra journal stays on
                                        the books for the audit trail.
                                    </span>
                                }
                                okText="Yes, clear advance"
                                cancelText="Cancel"
                                onConfirm={() => handleClear(adv)}
                            >
                                <button
                                    type="button"
                                    style={clearBtnStyle}
                                    disabled={pendingId === adv.id || clearMut.isPending}
                                >
                                    {pendingId === adv.id ? 'Clearing…' : 'Clear Advance'}
                                </button>
                            </Popconfirm>
                        </div>
                    );
                })}
            </div>
        </div>
    );

    if (variant === 'compact') {
        return (
            <span style={compactPillStyle} title={`${advances.length} uncleared advance(s)`}>
                <AlertTriangle size={11} /> AD · {formatCurrency(total)}
            </span>
        );
    }
    if (variant === 'modal') {
        return (
            <Modal
                open={!!open}
                onCancel={onClose}
                footer={
                    <button onClick={onClose} style={dismissBtnStyle}>
                        <CloseIcon size={12} /> Dismiss
                    </button>
                }
                title="Uncleared advance — please review"
                width={680}
            >
                {body}
            </Modal>
        );
    }
    // inline (default)
    return body;
}


// ── Styles (kept in-file to match the project's existing pattern) ──

const containerStyle: React.CSSProperties = {
    background: '#fffbeb',
    border: '1px solid #fde68a',
    borderRadius: 8,
    padding: '0.85rem 1rem',
    marginBottom: '0.75rem',
};

const headerStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    color: '#92400e',
    fontSize: 13,
    marginBottom: 6,
};

const pillStyle: React.CSSProperties = {
    background: '#fef3c7',
    color: '#a16207',
    border: '1px solid #fde68a',
    borderRadius: 4,
    fontSize: 9,
    fontWeight: 800,
    padding: '1px 6px',
    letterSpacing: '0.05em',
};

const bodyTextStyle: React.CSSProperties = {
    color: '#92400e',
    fontSize: 12,
    margin: '4px 0 8px',
    lineHeight: 1.4,
};

const rowStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    background: '#fff',
    border: '1px solid #fde68a',
    borderRadius: 6,
    padding: '0.6rem 0.75rem',
};

const adTagStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 32, height: 32,
    borderRadius: 6,
    background: '#fef3c7',
    color: '#a16207',
    border: '1px solid #fde68a',
    fontSize: 11, fontWeight: 800,
    flexShrink: 0,
};

const refLineStyle: React.CSSProperties = {
    display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
    fontSize: 12, color: '#0f172a',
};

const muteTagStyle: React.CSSProperties = {
    fontSize: 9,
    fontWeight: 700,
    background: '#f1f5f9',
    color: '#475569',
    padding: '1px 6px',
    borderRadius: 4,
    letterSpacing: '0.05em',
    textTransform: 'uppercase',
};

const amountLineStyle: React.CSSProperties = {
    fontSize: 11,
    color: '#475569',
    marginTop: 2,
};

const clearBtnStyle: React.CSSProperties = {
    padding: '0.4rem 0.85rem',
    background: '#10b981',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.03em',
    cursor: 'pointer',
    flexShrink: 0,
    boxShadow: '0 4px 10px -4px rgba(16, 185, 129, 0.5)',
};

const compactPillStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    padding: '2px 8px',
    background: '#fef3c7',
    color: '#a16207',
    border: '1px solid #fde68a',
    borderRadius: 999,
    fontSize: 10,
    fontWeight: 700,
};

const dismissBtnStyle: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: '0.5rem 1rem',
    background: '#f1f5f9',
    color: '#475569',
    border: 'none',
    borderRadius: 6,
    fontSize: 12, fontWeight: 600,
    cursor: 'pointer',
};
