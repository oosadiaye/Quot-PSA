/**
 * PaymentGatewaySettings — which payment gateways are switched on for this
 * organisation. Route: /settings/payment-gateways
 *
 * The disbursement/collection counterpart of the AI settings page. The
 * platform provisions each gateway (credentials, model, spend); this page
 * shows what is switched on and lets an admin turn a provisioned gateway on
 * or off. Credentials are never shown — the tenant sees the gateway, its
 * environment and direction, and a toggle.
 */
import { useState } from 'react';
import type { CSSProperties } from 'react';
import { CreditCard, ShieldCheck, ShieldAlert, Ban, Power } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';
import SettingsLayout from './SettingsLayout';

interface Gateway {
    id: number;
    provider_key: string;
    provider_name: string;
    environment: string;
    supports_disbursement: boolean;
    supports_collection: boolean;
    is_active: boolean;
    is_default: boolean;
    is_usable: boolean;
    per_transaction_cap: string;
    transactions: number;
}

interface GatewayStatus {
    tenant_name: string;
    gateways: Gateway[];
    totals: { provisioned: number; active: number; usable: number };
}

export default function PaymentGatewaySettings() {
    const qc = useQueryClient();
    const [confirmEnable, setConfirmEnable] = useState<string | null>(null);
    const [notice, setNotice] = useState('');
    const [error, setError] = useState('');

    const status = useQuery<GatewayStatus>({
        queryKey: ['tenant-gateway-status'],
        queryFn: async () => (await apiClient.get('/core/gateways/status/')).data,
    });

    const enableGw = useMutation({
        mutationFn: async (gateway: string) =>
            (await apiClient.post('/core/gateways/enable/', { gateway })).data,
        onSuccess: (d: { provider_name: string; is_usable: boolean }) => {
            setError('');
            setConfirmEnable(null);
            setNotice(
                d.is_usable
                    ? `${d.provider_name} switched on.`
                    : `${d.provider_name} switched on, but it is blocked upstream — ask your platform administrator.`,
            );
            qc.invalidateQueries({ queryKey: ['tenant-gateway-status'] });
        },
        onError: () => { setConfirmEnable(null); setError('Could not switch the gateway on.'); },
    });

    const disableAll = useMutation({
        mutationFn: async () => (await apiClient.post('/core/gateways/disable-all/')).data,
        onSuccess: (d: { disabled: number }) => {
            setError('');
            setNotice(d.disabled ? `Switched off ${d.disabled} gateway(s).` : 'Nothing was active.');
            qc.invalidateQueries({ queryKey: ['tenant-gateway-status'] });
        },
        onError: () => setError('Could not switch the gateways off.'),
    });

    const layoutProps = {
        title: 'Payment Gateways',
        breadcrumb: 'Payment Gateways',
        subtitle: 'Which payment gateways are switched on for this organisation, and what they have processed.',
        icon: <CreditCard size={22} color="white" />,
        maxWidth: '920px',
    } as const;

    if (status.isLoading) {
        return <SettingsLayout {...layoutProps}><div style={{ padding: 24, color: 'var(--color-text-muted)' }}>Loading…</div></SettingsLayout>;
    }

    const data = status.data;
    const gateways = data?.gateways ?? [];
    const anyActive = (data?.totals.active ?? 0) > 0;

    return (
        <SettingsLayout {...layoutProps}>
            <div style={infoBanner}>
                <ShieldCheck size={16} style={{ flexShrink: 0, marginTop: 2 }} />
                <span>
                    <strong>The platform provisions, you switch on.</strong> Your platform
                    administrator holds each gateway's credentials and chooses the merchant
                    account; here you decide whether a provisioned gateway is live. Switching
                    one on commits real funds movement, so it asks you to confirm.
                </span>
            </div>

            {notice && <div style={okBox}>{notice}</div>}
            {error && <div style={errBox}>{error}</div>}

            {gateways.length === 0 ? (
                <div style={{ ...card, textAlign: 'center', padding: 48, color: 'var(--color-text-muted)' }}>
                    <CreditCard size={30} style={{ marginBottom: 12, color: 'var(--color-text-subtle)' }} />
                    <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--color-text)', marginBottom: 6 }}>
                        No payment gateways are provisioned
                    </div>
                    <div style={{ fontSize: 13, lineHeight: 1.6, maxWidth: 520, margin: '0 auto' }}>
                        Ask your platform administrator to set up Remita or Xpresspay for this
                        organisation; once provisioned, they will appear here to switch on.
                    </div>
                </div>
            ) : (
                <>
                    {gateways.map((g) => (
                        <div key={g.id} style={card}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
                                <div style={{ minWidth: 240 }}>
                                    <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--color-text)' }}>
                                        {g.provider_name}
                                        {g.is_default && <span style={pill('#eef2ff', '#3730a3')}>Default</span>}
                                    </div>
                                    <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 4, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                        <span style={pill('#f1f5f9', '#475569')}>{g.environment}</span>
                                        {g.supports_disbursement && <span style={pill('#eef2ff', '#3730a3')}>Disbursement</span>}
                                        {g.supports_collection && <span style={pill('#ecfdf5', '#047857')}>Collection</span>}
                                    </div>
                                </div>
                                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                                    {g.is_active && g.is_usable
                                        ? <span style={pill('#dcfce7', '#166534')}><ShieldCheck size={12} />Active</span>
                                        : g.is_active
                                            ? <span style={pill('#ffedd5', '#9a3412')}><ShieldAlert size={12} />Blocked upstream</span>
                                            : <span style={pill('#f1f5f9', '#475569')}>Off</span>}
                                    {!g.is_active && (
                                        confirmEnable === g.provider_key ? (
                                            <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                                                <button type="button" style={confirmBtn} disabled={enableGw.isPending}
                                                    onClick={() => enableGw.mutate(g.provider_key)}>
                                                    <Power size={13} />{enableGw.isPending ? 'Switching on…' : 'Confirm — moves funds'}
                                                </button>
                                                <button type="button" style={cancelBtn} disabled={enableGw.isPending}
                                                    onClick={() => setConfirmEnable(null)}>Cancel</button>
                                            </span>
                                        ) : (
                                            <button type="button" style={enableBtn}
                                                onClick={() => { setError(''); setNotice(''); setConfirmEnable(g.provider_key); }}>
                                                <Power size={13} /> Enable
                                            </button>
                                        )
                                    )}
                                </div>
                            </div>
                            <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px dashed var(--color-border)', fontSize: 13, color: 'var(--color-text-muted)' }}>
                                {g.transactions} transaction{g.transactions === 1 ? '' : 's'} on record
                                {Number(g.per_transaction_cap) > 0 && <> · cap ₦{Number(g.per_transaction_cap).toLocaleString()}</>}
                            </div>
                        </div>
                    ))}

                    <div style={{ ...card, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                        <div style={{ maxWidth: 560 }}>
                            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text)' }}>Switch all gateways off</div>
                            <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', lineHeight: 1.6, marginTop: 4 }}>
                                Stops every gateway immediately. In-flight transactions already sent to a
                                provider settle as normal; nothing new is dispatched.
                            </div>
                        </div>
                        <button type="button" disabled={!anyActive || disableAll.isPending}
                            onClick={() => disableAll.mutate()}
                            style={{
                                padding: '10px 18px', borderRadius: 8, fontSize: 13, fontWeight: 700,
                                display: 'flex', alignItems: 'center', gap: 8,
                                cursor: anyActive && !disableAll.isPending ? 'pointer' : 'not-allowed',
                                background: anyActive ? '#dc2626' : 'var(--color-surface-hover)',
                                color: anyActive ? '#fff' : 'var(--color-text-subtle)',
                                border: anyActive ? '1px solid #b91c1c' : '1px solid var(--color-border)',
                            }}>
                            <Ban size={15} />
                            {disableAll.isPending ? 'Switching off…' : anyActive ? 'Switch all off' : 'Nothing active'}
                        </button>
                    </div>
                </>
            )}
        </SettingsLayout>
    );
}

const card: CSSProperties = {
    background: 'var(--color-surface)', border: '1px solid var(--color-border)',
    borderRadius: 12, padding: 20, marginBottom: 16,
};
const pill = (bg: string, fg: string): CSSProperties => ({
    display: 'inline-flex', alignItems: 'center', gap: 4, marginLeft: 8,
    padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 600,
    background: bg, color: fg, whiteSpace: 'nowrap',
});
const infoBanner: CSSProperties = {
    padding: '12px 16px', borderRadius: 8, marginBottom: 16,
    background: '#f0f9ff', border: '1px solid #bae6fd', color: '#075985',
    display: 'flex', gap: 10, fontSize: 13, lineHeight: 1.6,
};
const okBox: CSSProperties = { padding: '10px 14px', borderRadius: 8, marginBottom: 16, background: '#f0fdf4', border: '1px solid #86efac', color: '#166534', fontSize: 13 };
const errBox: CSSProperties = { padding: '10px 14px', borderRadius: 8, marginBottom: 16, background: '#fef2f2', border: '1px solid #fca5a5', color: '#991b1b', fontSize: 13 };
const enableBtn: CSSProperties = { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 8, fontSize: 12.5, fontWeight: 700, cursor: 'pointer', background: 'var(--color-surface-hover)', color: 'var(--color-primary)', border: '1px solid var(--color-border)' };
const confirmBtn: CSSProperties = { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 8, fontSize: 12.5, fontWeight: 700, cursor: 'pointer', background: '#16a34a', color: '#fff', border: '1px solid #15803d' };
const cancelBtn: CSSProperties = { padding: '6px 10px', borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: 'pointer', background: 'transparent', color: 'var(--color-text-muted)', border: '1px solid var(--color-border)' };
