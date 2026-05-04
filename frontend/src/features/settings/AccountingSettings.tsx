import { useState, useEffect } from 'react';
import {
    Save, Loader2, Check, AlertCircle, Receipt, Banknote, ShieldAlert, ChevronRight,
} from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/client';
import SettingsLayout from './SettingsLayout';

interface AccountingSettingsData {
    id: number;
    require_vendor_registration_invoice: boolean;
    // GL account credited when a vendor pays their registration invoice.
    // Optional FK; if null, the posting falls back to NCoA 12100200.
    vendor_registration_revenue_account: number | null;
    // When true, outgoing Payments MUST reference a PV. When false,
    // verifiers can raise direct payments from vendor invoices.
    require_pv_before_payment: boolean;
    // When true (the safe default), outgoing Payments are blocked when
    // the released warrant balance can't cover the amount. When false,
    // the payment-stage AND the invoice-stage warrant ceiling checks
    // are bypassed — useful for tenants not yet operating on
    // warrant-based cash control.
    require_warrant_before_payment: boolean;
}

interface IncomeAccountOption {
    id: number;
    code: string;
    name: string;
}

const SETTINGS_URL = '/accounting/settings/';

// ── Styles ───────────────────────────────────────────────────
const cardStyle: React.CSSProperties = {
    background: 'white', borderRadius: '20px', padding: '28px 32px',
    border: '1px solid #e2e8f0',
    boxShadow: '0 1px 3px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.02)',
};

const navCardStyle: React.CSSProperties = {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '16px 20px',
    background: '#ffffff', border: '1px solid rgba(0,0,0,0.08)',
    borderRadius: '12px', cursor: 'pointer',
    marginTop: '20px', transition: 'all 0.15s ease',
};

export default function AccountingSettingsPage() {
    const queryClient = useQueryClient();
    const navigate = useNavigate();
    const [requireVendorInvoice, setRequireVendorInvoice] = useState(true);
    const [vendorRegRevenueAccount, setVendorRegRevenueAccount] = useState<string>('');
    const [requirePvBeforePayment, setRequirePvBeforePayment] = useState(false);
    // Default to true to match the backend safe default — if the
    // settings row hasn't loaded yet, the toggle visually reflects
    // the enforced state until the real value lands.
    const [requireWarrantBeforePayment, setRequireWarrantBeforePayment] = useState(true);

    // Income GL list for the registration-revenue selector. Pulls every
    // active Income account on the COA so tenants pick from real data,
    // never a hardcoded code list. ``page_size=10000`` matches the
    // server-side cap on AccountingPagination so we never silently
    // truncate mid-large COAs.
    const { data: incomeAccounts = [] } = useQuery<IncomeAccountOption[]>({
        queryKey: ['income-accounts-for-settings'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/accounts/', {
                params: { account_type: 'Income', is_active: true, page_size: 10000, ordering: 'code' },
            });
            return Array.isArray(data) ? data : (data?.results ?? []);
        },
        staleTime: 5 * 60 * 1000,
    });
    const [saveMsg, setSaveMsg] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

    const { data: settings, isLoading } = useQuery<AccountingSettingsData>({
        queryKey: ['accounting-settings'],
        queryFn: async () => {
            const res = await apiClient.get(SETTINGS_URL);
            return res.data;
        },
    });

    useEffect(() => {
        if (settings) {
            setRequireVendorInvoice(settings.require_vendor_registration_invoice ?? true);
            setVendorRegRevenueAccount(
                settings.vendor_registration_revenue_account != null
                    ? String(settings.vendor_registration_revenue_account)
                    : ''
            );
            setRequirePvBeforePayment(settings.require_pv_before_payment ?? false);
            setRequireWarrantBeforePayment(settings.require_warrant_before_payment ?? true);
        }
    }, [settings]);

    const saveMutation = useMutation({
        mutationFn: async () => {
            // PATCH rather than PUT: we only want to update the toggles we own,
            // not overwrite unrelated settings (currencies, digit rules, etc.)
            // that this page doesn't surface. PATCH is partial update.
            const res = await apiClient.patch(SETTINGS_URL, {
                require_vendor_registration_invoice: requireVendorInvoice,
                vendor_registration_revenue_account: vendorRegRevenueAccount
                    ? parseInt(vendorRegRevenueAccount)
                    : null,
                require_pv_before_payment: requirePvBeforePayment,
                require_warrant_before_payment: requireWarrantBeforePayment,
            });
            return res.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['accounting-settings'] });
            queryClient.invalidateQueries({ queryKey: ['vendor-invoice-gate'] });
            setSaveMsg({ text: 'Settings saved successfully', type: 'success' });
            setTimeout(() => setSaveMsg(null), 4000);
        },
        onError: () => {
            setSaveMsg({ text: 'Failed to save settings', type: 'error' });
            setTimeout(() => setSaveMsg(null), 4000);
        },
    });

    if (isLoading) {
        return (
            <SettingsLayout>
                <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    minHeight: '400px', gap: '12px', color: '#94a3b8',
                }}>
                    <Loader2 size={28} style={{ animation: 'spin 1s linear infinite' }} />
                    <span style={{ fontSize: '14px', fontWeight: 500 }}>Loading settings...</span>
                </div>
            </SettingsLayout>
        );
    }

    return (
        <SettingsLayout>
            {/* ── Vendor Registration Invoice Gate ────────── */}
            <div style={{ ...cardStyle, marginBottom: '24px' }}>
                <div style={{
                    display: 'flex', alignItems: 'flex-start', gap: '16px',
                    marginBottom: '24px', paddingBottom: '20px',
                    borderBottom: '1px solid #f1f5f9',
                }}>
                    <div style={{
                        width: '48px', height: '48px', borderRadius: '14px',
                        background: 'linear-gradient(135deg, #7c3aed10, #7c3aed06)',
                        border: '1.5px solid #7c3aed20',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                    }}>
                        <Receipt size={22} color="#7c3aed" />
                    </div>
                    <div>
                        <h2 style={{
                            fontSize: '18px', fontWeight: 700, color: '#0f172a',
                            margin: '0 0 4px 0', letterSpacing: '-0.2px',
                        }}>
                            Vendor Registration Invoice
                        </h2>
                        <p style={{ fontSize: '13px', color: '#94a3b8', margin: 0, lineHeight: 1.5 }}>
                            Controls whether new vendors must pay a registration invoice before activation.
                            When disabled, vendors are created as active immediately — useful during initial setup.
                        </p>
                    </div>
                </div>

                <div style={{
                    display: 'flex', alignItems: 'center', gap: '20px',
                    padding: '16px 20px', borderRadius: '14px',
                    background: requireVendorInvoice ? '#f5f3ff' : '#f8fafc',
                    border: `1.5px solid ${requireVendorInvoice ? '#ddd6fe' : '#e2e8f0'}`,
                    transition: 'all 0.3s',
                }}>
                    <button
                        type="button"
                        onClick={() => setRequireVendorInvoice(!requireVendorInvoice)}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '12px',
                            padding: '0', border: 'none', background: 'none',
                            cursor: 'pointer', fontFamily: 'inherit',
                        }}
                    >
                        <div style={{
                            width: '44px', height: '24px', borderRadius: '12px',
                            background: requireVendorInvoice
                                ? 'linear-gradient(135deg, #7c3aed, #6d28d9)'
                                : '#cbd5e1',
                            transition: 'background 0.25s', position: 'relative',
                            boxShadow: requireVendorInvoice ? '0 2px 8px rgba(124, 58, 237, 0.3)' : 'none',
                        }}>
                            <div style={{
                                width: '18px', height: '18px', borderRadius: '50%',
                                background: 'white', position: 'absolute',
                                top: '3px', left: requireVendorInvoice ? '23px' : '3px',
                                transition: 'left 0.25s',
                                boxShadow: '0 1px 3px rgba(0,0,0,0.15)',
                            }} />
                        </div>
                    </button>
                    <div>
                        <div style={{ fontSize: '14px', fontWeight: 700, color: requireVendorInvoice ? '#7c3aed' : '#64748b' }}>
                            {requireVendorInvoice ? 'Enabled' : 'Disabled'}
                        </div>
                        <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '2px' }}>
                            {requireVendorInvoice
                                ? 'New vendors start inactive. Registration invoice + payment required before activation.'
                                : 'New vendors are created active immediately. No invoice gate — finance team can proceed without interruption.'}
                        </div>
                    </div>
                </div>

                {!requireVendorInvoice && (
                    <div style={{
                        display: 'flex', alignItems: 'flex-start', gap: '10px',
                        padding: '14px 16px', borderRadius: '12px',
                        background: '#fffbeb', border: '1.5px solid #fde68a',
                        marginTop: '16px',
                    }}>
                        <AlertCircle size={16} color="#d97706" style={{ marginTop: '1px', flexShrink: 0 }} />
                        <div style={{ fontSize: '12px', color: '#92400e', lineHeight: 1.6 }}>
                            <strong>Note:</strong> Expired supplier renewal invoices are still available on the
                            Expired Suppliers page. This setting only affects new vendor registration.
                        </div>
                    </div>
                )}

                {/* ── Registration-fee revenue GL selector ──────
                    Only meaningful when the gate is ON — shown then so
                    the operator knows exactly which Income account will
                    be credited when a vendor pays their registration
                    invoice. Hidden when gate is OFF (no postings happen
                    so no GL config needed). */}
                {requireVendorInvoice && (
                    <div style={{ marginTop: '20px' }}>
                        <label style={{
                            display: 'block', fontSize: '12px', fontWeight: 700,
                            color: '#475569', textTransform: 'uppercase',
                            letterSpacing: '0.04em', marginBottom: '8px',
                        }}>
                            Registration-Fee Revenue Account
                        </label>
                        <select
                            value={vendorRegRevenueAccount}
                            onChange={(e) => setVendorRegRevenueAccount(e.target.value)}
                            style={{
                                width: '100%', padding: '10px 12px', borderRadius: '10px',
                                border: '1.5px solid #e2e8f0', fontSize: '14px',
                                background: '#fff', color: '#0f172a',
                                cursor: 'pointer',
                            }}
                        >
                            <option value="">— Use NCoA 12100200 default —</option>
                            {incomeAccounts.map((a) => (
                                <option key={a.id} value={a.id}>
                                    {a.code} — {a.name}
                                </option>
                            ))}
                        </select>
                        <p style={{ fontSize: '12px', color: '#94a3b8', margin: '8px 0 0', lineHeight: 1.5 }}>
                            Income account credited when vendors pay their registration invoice.
                            Leave on default to use NCoA code 12100200; pick an explicit account if
                            your CoA uses a different revenue code.
                        </p>
                    </div>
                )}

                {/* ── PV-before-Payment gate ──────────────────────── */}
                {/* This sits in the same card as the Vendor Registration gate,
                    separated by a divider. Both are workflow toggles that
                    govern how permissive the system is about creating
                    downstream records without an upstream authorisation. */}
                <div style={{
                    marginTop: '28px', paddingTop: '24px',
                    borderTop: '1px solid #f1f5f9',
                    display: 'flex', alignItems: 'flex-start', gap: '16px',
                    marginBottom: '20px',
                }}>
                    <div style={{
                        width: '48px', height: '48px', borderRadius: '14px',
                        background: 'linear-gradient(135deg, #f59e0b10, #f59e0b06)',
                        border: '1.5px solid #f59e0b20',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                    }}>
                        <Banknote size={22} color="#f59e0b" />
                    </div>
                    <div>
                        <h2 style={{
                            fontSize: '18px', fontWeight: 700, color: '#0f172a',
                            margin: '0 0 4px 0', letterSpacing: '-0.2px',
                        }}>
                            Require Payment Voucher before Payment
                        </h2>
                        <p style={{ fontSize: '13px', color: '#94a3b8', margin: 0, lineHeight: 1.5 }}>
                            Controls whether every outgoing payment must reference an approved
                            Payment Voucher (PV). When disabled, finance can raise payments
                            directly from vendor invoices without the PV step.
                        </p>
                    </div>
                </div>

                <div style={{
                    display: 'flex', alignItems: 'center', gap: '20px',
                    padding: '16px 20px', borderRadius: '14px',
                    background: requirePvBeforePayment ? '#fef3c7' : '#f8fafc',
                    border: `1.5px solid ${requirePvBeforePayment ? '#fde68a' : '#e2e8f0'}`,
                    transition: 'all 0.3s',
                }}>
                    <button
                        type="button"
                        onClick={() => setRequirePvBeforePayment(!requirePvBeforePayment)}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '12px',
                            padding: '0', border: 'none', background: 'none',
                            cursor: 'pointer', fontFamily: 'inherit',
                        }}
                    >
                        <div style={{
                            width: '44px', height: '24px', borderRadius: '12px',
                            background: requirePvBeforePayment
                                ? 'linear-gradient(135deg, #f59e0b, #d97706)'
                                : '#cbd5e1',
                            transition: 'background 0.25s', position: 'relative',
                            boxShadow: requirePvBeforePayment ? '0 2px 8px rgba(245, 158, 11, 0.3)' : 'none',
                        }}>
                            <div style={{
                                width: '18px', height: '18px', borderRadius: '50%',
                                background: 'white', position: 'absolute',
                                top: '3px', left: requirePvBeforePayment ? '23px' : '3px',
                                transition: 'left 0.25s',
                                boxShadow: '0 1px 3px rgba(0,0,0,0.15)',
                            }} />
                        </div>
                    </button>
                    <div>
                        <div style={{ fontSize: '14px', fontWeight: 700, color: requirePvBeforePayment ? '#d97706' : '#64748b' }}>
                            {requirePvBeforePayment ? 'Enabled — PV Required' : 'Disabled — Direct payments allowed'}
                        </div>
                        <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '2px' }}>
                            {requirePvBeforePayment
                                ? 'Every outgoing payment must reference an approved PV. Enforced at payment-creation time.'
                                : 'Outgoing payments can be posted directly. PV reference is optional.'}
                        </div>
                    </div>
                </div>

                {/* ── Warrant-before-Payment gate ──────────────────────
                    The cash-control gate. Public-sector accounting
                    typically requires a released Warrant (AIE) before
                    cash leaves the consolidated account; this toggle
                    bypasses that check for tenants not yet on
                    warrant-based control. */}
                <div style={{
                    marginTop: '28px', paddingTop: '24px',
                    borderTop: '1px solid #f1f5f9',
                    display: 'flex', alignItems: 'flex-start', gap: '16px',
                    marginBottom: '20px',
                }}>
                    <div style={{
                        width: '48px', height: '48px', borderRadius: '14px',
                        background: 'linear-gradient(135deg, #ef444410, #ef444406)',
                        border: '1.5px solid #ef444420',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                    }}>
                        <ShieldAlert size={22} color="#ef4444" />
                    </div>
                    <div>
                        <h2 style={{
                            fontSize: '18px', fontWeight: 700, color: '#0f172a',
                            margin: '0 0 4px 0', letterSpacing: '-0.2px',
                        }}>
                            Require Warrant (AIE) before Payment
                        </h2>
                        <p style={{ fontSize: '13px', color: '#94a3b8', margin: 0, lineHeight: 1.5 }}>
                            Controls whether outgoing payments and AP-invoice posting
                            are gated by released Warrant (AIE) availability. When
                            disabled, both stages skip the warrant ceiling check —
                            useful for tenants not yet operating on warrant-based
                            cash control. The default (enabled) is GIFMIS-compliant.
                        </p>
                    </div>
                </div>

                <div style={{
                    display: 'flex', alignItems: 'center', gap: '20px',
                    padding: '16px 20px', borderRadius: '14px',
                    background: requireWarrantBeforePayment ? '#fee2e2' : '#f8fafc',
                    border: `1.5px solid ${requireWarrantBeforePayment ? '#fecaca' : '#e2e8f0'}`,
                    transition: 'all 0.3s',
                }}>
                    <button
                        type="button"
                        onClick={() => setRequireWarrantBeforePayment(!requireWarrantBeforePayment)}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '12px',
                            padding: '0', border: 'none', background: 'none',
                            cursor: 'pointer', fontFamily: 'inherit',
                        }}
                    >
                        <div style={{
                            width: '44px', height: '24px', borderRadius: '12px',
                            background: requireWarrantBeforePayment
                                ? 'linear-gradient(135deg, #ef4444, #dc2626)'
                                : '#cbd5e1',
                            transition: 'background 0.25s', position: 'relative',
                            boxShadow: requireWarrantBeforePayment ? '0 2px 8px rgba(239, 68, 68, 0.3)' : 'none',
                        }}>
                            <div style={{
                                width: '18px', height: '18px', borderRadius: '50%',
                                background: 'white', position: 'absolute',
                                top: '3px', left: requireWarrantBeforePayment ? '23px' : '3px',
                                transition: 'left 0.25s',
                                boxShadow: '0 1px 3px rgba(0,0,0,0.15)',
                            }} />
                        </div>
                    </button>
                    <div>
                        <div style={{ fontSize: '14px', fontWeight: 700, color: requireWarrantBeforePayment ? '#dc2626' : '#64748b' }}>
                            {requireWarrantBeforePayment ? 'Enabled — Warrant Required' : 'Disabled — Warrant bypassed'}
                        </div>
                        <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '2px' }}>
                            {requireWarrantBeforePayment
                                ? 'Payments are blocked when released Warrant (AIE) for the MDA + Fund + Account would not cover the amount. AP-invoice posting respects the same ceiling.'
                                : 'Both AP-invoice posting and outgoing payments skip the warrant ceiling check. Cash can leave the TSA without a released Warrant — use only for non-warrant-based jurisdictions.'}
                        </div>
                    </div>
                </div>

                {!requireWarrantBeforePayment && (
                    <div style={{
                        display: 'flex', alignItems: 'flex-start', gap: '10px',
                        padding: '14px 16px', borderRadius: '12px',
                        background: '#fffbeb', border: '1.5px solid #fde68a',
                        marginTop: '16px',
                    }}>
                        <AlertCircle size={16} color="#d97706" style={{ marginTop: '1px', flexShrink: 0 }} />
                        <div style={{ fontSize: '12px', color: '#92400e', lineHeight: 1.6 }}>
                            <strong>Warning:</strong> With warrant enforcement OFF, the system
                            will allow payments to post even when no Warrant has been released
                            for the relevant appropriation. Make sure your finance controls
                            cover this gap externally.
                        </div>
                    </div>
                )}

                {/* Save Button */}
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '16px',
                    paddingTop: '20px', marginTop: '20px', borderTop: '1px solid #f1f5f9',
                }}>
                    <button
                        onClick={() => saveMutation.mutate()}
                        disabled={saveMutation.isPending}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '8px',
                            padding: '12px 28px', borderRadius: '12px', border: 'none',
                            background: 'linear-gradient(135deg, #7c3aed, #6d28d9)',
                            fontSize: '14px', fontWeight: 700, color: 'white',
                            cursor: saveMutation.isPending ? 'wait' : 'pointer',
                            fontFamily: 'inherit', transition: 'all 0.2s',
                            boxShadow: '0 4px 12px rgba(124, 58, 237, 0.3)',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-1px)'; e.currentTarget.style.boxShadow = '0 6px 16px rgba(124, 58, 237, 0.35)'; }}
                        onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = '0 4px 12px rgba(124, 58, 237, 0.3)'; }}
                    >
                        {saveMutation.isPending
                            ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
                            : <Save size={16} />
                        }
                        Save Settings
                    </button>

                    {saveMsg && (
                        <div style={{
                            display: 'flex', alignItems: 'center', gap: '8px',
                            padding: '8px 16px', borderRadius: '10px',
                            background: saveMsg.type === 'success' ? '#ecfdf5' : '#fef2f2',
                            border: `1.5px solid ${saveMsg.type === 'success' ? '#a7f3d0' : '#fecaca'}`,
                            animation: 'fadeIn 0.3s ease',
                        }}>
                            {saveMsg.type === 'success'
                                ? <Check size={15} color="#059669" strokeWidth={3} />
                                : <AlertCircle size={15} color="#dc2626" />
                            }
                            <span style={{
                                fontSize: '13px', fontWeight: 600,
                                color: saveMsg.type === 'success' ? '#059669' : '#dc2626',
                            }}>
                                {saveMsg.text}
                            </span>
                        </div>
                    )}
                </div>
            </div>

            {/* ── Budget Check Rules — cross-module policy ────────────── */}
            <div
                style={navCardStyle}
                role="button"
                tabIndex={0}
                onClick={() => navigate('/settings/accounting/budget-check-rules')}
                onKeyDown={(e) => { if (e.key === 'Enter') navigate('/settings/accounting/budget-check-rules'); }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = '#1a237e'; e.currentTarget.style.boxShadow = '0 4px 16px rgba(26,35,126,0.10)'; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(0,0,0,0.08)'; e.currentTarget.style.boxShadow = 'none'; }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                    <div style={{
                        width: 44, height: 44, borderRadius: 10,
                        background: 'rgba(220,38,38,0.08)', color: '#dc2626',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                        <ShieldAlert size={22} />
                    </div>
                    <div>
                        <div style={{ fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                            Budget Check Rules
                        </div>
                        <div style={{ fontSize: '13px', color: '#64748b', marginTop: 2 }}>
                            Per-GL policy controlling how strictly postings are gated against appropriations
                            (NONE / Warning / Strict). Applies across journals, PO, 3-way match, invoice, PV.
                        </div>
                    </div>
                </div>
                <ChevronRight size={20} color="#94a3b8" />
            </div>

            <style>{`
                @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
                @keyframes fadeIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }
            `}</style>
        </SettingsLayout>
    );
}
