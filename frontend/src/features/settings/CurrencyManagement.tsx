import { useState, useEffect, useRef } from 'react';
import { useDialog } from '../../hooks/useDialog';
import { Coins, Plus, Trash2, Edit2, Save, Loader2, ArrowRightLeft, Star, Download, Upload, FileDown, Globe } from 'lucide-react';
import {
    useCurrencies, useCreateCurrency, useUpdateCurrency, useDeleteCurrency,
    useExchangeRates, useCreateExchangeRate, useUpdateExchangeRate, useDeleteExchangeRate,
    useDefaultCurrencies, useSaveDefaultCurrencies,
    downloadExchangeRateTemplate, exportExchangeRates, useBulkImportExchangeRates,
} from '../accounting/hooks/useAccountingEnhancements';
import SettingsLayout from './SettingsLayout';

const cardStyle: React.CSSProperties = {
    background: 'white',
    borderRadius: '20px',
    padding: '28px 32px',
    border: '1px solid #e2e8f0',
    boxShadow: '0 1px 3px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.02)',
};

const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '11px',
    fontWeight: 700,
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: '0.6px',
    marginBottom: '8px',
};

const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '10px 14px',
    border: '1.5px solid #e2e8f0',
    borderRadius: '12px',
    background: '#f8fafc',
    color: '#0f172a',
    fontSize: '14px',
    fontFamily: 'inherit',
    outline: 'none',
    boxSizing: 'border-box',
};

const thStyle: React.CSSProperties = {
    padding: '12px 16px',
    textAlign: 'left',
    fontWeight: 700,
    fontSize: '11px',
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    background: '#f8fafc',
};

const tdStyle: React.CSSProperties = {
    padding: '12px 16px',
    fontSize: '14px',
    color: '#0f172a',
    borderBottom: '1px solid #f1f5f9',
};

const iconBadge = (bg: string): React.CSSProperties => ({
    width: '38px',
    height: '38px',
    borderRadius: '12px',
    background: bg,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
});

const subtleButtonStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '7px 14px',
    border: '1.5px solid #e2e8f0',
    background: 'white',
    borderRadius: '10px',
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: '12px',
    color: '#475569',
    fontFamily: 'inherit',
    transition: 'all 0.15s ease',
};

export default function CurrencyManagement() {
    const { showConfirm } = useDialog();
    const { data: currencies, isLoading: currLoading } = useCurrencies();
    const { data: exchangeRates, isLoading: ratesLoading } = useExchangeRates();
    const { data: defaults } = useDefaultCurrencies();
    const createCurrency = useCreateCurrency();
    const updateCurrency = useUpdateCurrency();
    const deleteCurrency = useDeleteCurrency();
    const createRate = useCreateExchangeRate();
    const updateRate = useUpdateExchangeRate();
    const deleteRate = useDeleteExchangeRate();
    const saveDefaults = useSaveDefaultCurrencies();
    const bulkImportRates = useBulkImportExchangeRates();
    const rateFileRef = useRef<HTMLInputElement>(null);
    const [importResult, setImportResult] = useState<{ created: number; updated: number; errors: string[] } | null>(null);

    // Currency form
    const [showCurrForm, setShowCurrForm] = useState(false);
    const [editingCurrId, setEditingCurrId] = useState<number | null>(null);
    const [currForm, setCurrForm] = useState({ code: '', name: '', symbol: '', exchange_rate: '1.0', is_active: true });

    // Exchange rate form
    const [showRateForm, setShowRateForm] = useState(false);
    const [editingRateId, setEditingRateId] = useState<number | null>(null);
    const [rateForm, setRateForm] = useState({ from_currency: '', to_currency: '', rate_date: new Date().toISOString().split('T')[0], rate_valid_from: new Date().toISOString().split('T')[0], rate_valid_to: '', exchange_rate: '1.0' });

    // Default currencies
    const [slot1, setSlot1] = useState<number | null>(null);
    const [slot2, setSlot2] = useState<number | null>(null);
    const [slot3, setSlot3] = useState<number | null>(null);
    const [slot4, setSlot4] = useState<number | null>(null);
    const [slot5, setSlot5] = useState<number | null>(null);
    const [defaultsMsg, setDefaultsMsg] = useState('');
    const [seeding, setSeeding] = useState(false);

    // Major currencies: 10 African + 5 Global, NGN as base
    const SEED_CURRENCIES = [
        // African currencies — NGN is base (exchange_rate = 1)
        { code: 'NGN', name: 'Nigerian Naira', symbol: '₦', exchange_rate: 1.0, is_base_currency: true },
        { code: 'ZAR', name: 'South African Rand', symbol: 'R', exchange_rate: 0.012, is_base_currency: false },
        { code: 'KES', name: 'Kenyan Shilling', symbol: 'KSh', exchange_rate: 0.088, is_base_currency: false },
        { code: 'GHS', name: 'Ghanaian Cedi', symbol: '₵', exchange_rate: 0.0084, is_base_currency: false },
        { code: 'EGP', name: 'Egyptian Pound', symbol: 'E£', exchange_rate: 0.032, is_base_currency: false },
        { code: 'TZS', name: 'Tanzanian Shilling', symbol: 'TSh', exchange_rate: 1.72, is_base_currency: false },
        { code: 'UGX', name: 'Ugandan Shilling', symbol: 'USh', exchange_rate: 2.48, is_base_currency: false },
        { code: 'XOF', name: 'West African CFA Franc', symbol: 'CFA', exchange_rate: 0.40, is_base_currency: false },
        { code: 'MAD', name: 'Moroccan Dirham', symbol: 'MAD', exchange_rate: 0.0065, is_base_currency: false },
        { code: 'ETB', name: 'Ethiopian Birr', symbol: 'Br', exchange_rate: 0.082, is_base_currency: false },
        // Global currencies (rate relative to NGN)
        { code: 'USD', name: 'US Dollar', symbol: '$', exchange_rate: 0.00064, is_base_currency: false },
        { code: 'EUR', name: 'Euro', symbol: '€', exchange_rate: 0.00059, is_base_currency: false },
        { code: 'GBP', name: 'British Pound', symbol: '£', exchange_rate: 0.00050, is_base_currency: false },
        { code: 'JPY', name: 'Japanese Yen', symbol: '¥', exchange_rate: 0.096, is_base_currency: false },
        { code: 'CNY', name: 'Chinese Yuan', symbol: '¥', exchange_rate: 0.0046, is_base_currency: false },
    ];

    const handleSeedGlobalCurrencies = async () => {
        setSeeding(true);
        try {
            const existingCodes = new Set((currencies || []).map((c: any) => c.code));
            const createdCurrencies: any[] = [];
            for (const gc of SEED_CURRENCIES) {
                if (!existingCodes.has(gc.code)) {
                    const created = await createCurrency.mutateAsync({ ...gc, is_active: true });
                    createdCurrencies.push(created);
                }
            }

            // Auto-create exchange rates between NGN and all other currencies
            const allCurrs = [...(currencies || []), ...createdCurrencies];
            const ngn = allCurrs.find((c: any) => c.code === 'NGN');
            if (ngn) {
                const others = allCurrs.filter((c: any) => c.code !== 'NGN');
                const today = new Date().toISOString().split('T')[0];
                for (const other of others) {
                    try {
                        await createRate.mutateAsync({
                            from_currency: ngn.id,
                            to_currency: other.id,
                            rate_date: today,
                            exchange_rate: other.exchange_rate,
                        });
                    } catch {
                        // Rate may already exist, skip
                    }
                }
            }
        } finally {
            setSeeding(false);
        }
    };

    useEffect(() => {
        if (defaults) {
            setSlot1(defaults.default_currency_1 || null);
            setSlot2(defaults.default_currency_2 || null);
            setSlot3(defaults.default_currency_3 || null);
            setSlot4(defaults.default_currency_4 || null);
            setSlot5(defaults.default_currency_5 || null);
        }
    }, [defaults]);

    const resetCurrForm = () => {
        setCurrForm({ code: '', name: '', symbol: '', exchange_rate: '1.0', is_active: true });
        setEditingCurrId(null);
        setShowCurrForm(false);
    };

    const handleCurrSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (editingCurrId) {
            await updateCurrency.mutateAsync({ id: editingCurrId, ...currForm, exchange_rate: parseFloat(currForm.exchange_rate) });
        } else {
            await createCurrency.mutateAsync({ ...currForm, exchange_rate: parseFloat(currForm.exchange_rate) });
        }
        resetCurrForm();
    };

    const handleEditCurr = (c: any) => {
        setEditingCurrId(c.id);
        setCurrForm({ code: c.code, name: c.name, symbol: c.symbol, exchange_rate: String(c.exchange_rate), is_active: c.is_active });
        setShowCurrForm(true);
    };

    const resetRateForm = () => {
        setEditingRateId(null);
        setShowRateForm(false);
        setRateForm({ from_currency: '', to_currency: '', rate_date: new Date().toISOString().split('T')[0], rate_valid_from: new Date().toISOString().split('T')[0], rate_valid_to: '', exchange_rate: '1.0' });
    };

    const handleRateSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const payload: any = {
            from_currency: parseInt(rateForm.from_currency),
            to_currency: parseInt(rateForm.to_currency),
            rate_date: rateForm.rate_valid_from,
            rate_valid_from: rateForm.rate_valid_from,
            rate_valid_to: rateForm.rate_valid_to || null,
            exchange_rate: rateForm.exchange_rate,
        };
        if (editingRateId) {
            await updateRate.mutateAsync({ id: editingRateId, ...payload });
        } else {
            await createRate.mutateAsync(payload);
        }
        resetRateForm();
    };

    const handleEditRate = (r: any) => {
        setEditingRateId(r.id);
        setRateForm({
            from_currency: String(r.from_currency),
            to_currency: String(r.to_currency),
            rate_date: r.rate_date,
            rate_valid_from: r.rate_valid_from || r.rate_date,
            rate_valid_to: r.rate_valid_to || '',
            exchange_rate: String(r.exchange_rate),
        });
        setShowRateForm(true);
    };

    const handleSaveDefaults = async () => {
        await saveDefaults.mutateAsync({
            default_currency_1: slot1 || null,
            default_currency_2: slot2 || null,
            default_currency_3: slot3 || null,
            default_currency_4: slot4 || null,
            default_currency_5: slot5 || null,
        });
        setDefaultsMsg('Default currencies saved.');
        setTimeout(() => setDefaultsMsg(''), 3000);
    };

    const handleRateFileImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        try {
            const result = await bulkImportRates.mutateAsync(file);
            setImportResult(result);
        } catch {
            setImportResult(null);
        }
        if (rateFileRef.current) rateFileRef.current.value = '';
    };

    const getCurrencyName = (id: number | null) => {
        if (!id || !currencies) return '—';
        const c = currencies.find((cur: any) => cur.id === id);
        return c ? `${c.code} — ${c.name}` : '—';
    };

    if (currLoading) {
        return (
            <SettingsLayout
                title="Currency Management"
                breadcrumb="Currencies"
                icon={<Coins size={22} color="white" />}
                gradient="linear-gradient(135deg, #0284c7, #0369a1)"
                gradientShadow="rgba(2, 132, 199, 0.25)"
                subtitle="Manage currencies, exchange rates, and default reporting currencies."
                maxWidth="1060px"
            >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '300px' }}>
                    <Loader2 size={32} className="animate-spin" style={{ color: '#0284c7' }} />
                </div>
            </SettingsLayout>
        );
    }

    return (
        <SettingsLayout
            title="Currency Management"
            breadcrumb="Currencies"
            icon={<Coins size={22} color="white" />}
            gradient="linear-gradient(135deg, #0284c7, #0369a1)"
            gradientShadow="rgba(2, 132, 199, 0.25)"
            subtitle="Manage currencies, exchange rates, and default reporting currencies."
            maxWidth="1060px"
        >
            {/* ── Section 1: Currencies ────────────────────────── */}
            <div style={{ ...cardStyle, marginBottom: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={iconBadge('linear-gradient(135deg, #0284c7, #0369a1)')}>
                            <Coins size={18} color="white" />
                        </div>
                        <h2 style={{ fontSize: '17px', fontWeight: 700, color: '#0f172a', margin: 0 }}>Currencies</h2>
                    </div>
                    <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                        {/* Show seed button when not all 15 currencies exist */}
                        {(() => {
                            const existingCodes = new Set((currencies || []).map((c: any) => c.code));
                            const missing = SEED_CURRENCIES.filter(gc => !existingCodes.has(gc.code));
                            if (missing.length === 0) return null;
                            return (
                                <button
                                    onClick={handleSeedGlobalCurrencies}
                                    disabled={seeding}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: '7px', padding: '9px 18px',
                                        background: 'linear-gradient(135deg, #059669, #047857)', color: 'white', border: 'none',
                                        borderRadius: '12px', cursor: seeding ? 'wait' : 'pointer', fontWeight: 600, fontSize: '13px',
                                        fontFamily: 'inherit', boxShadow: '0 2px 8px rgba(5, 150, 105, 0.3)',
                                        transition: 'all 0.15s ease',
                                    }}
                                >
                                    {seeding ? <Loader2 size={15} className="animate-spin" /> : <Globe size={15} />}
                                    {seeding ? 'Seeding...' : `Seed ${missing.length} Currencies`}
                                </button>
                            );
                        })()}
                        <button
                            onClick={() => { resetCurrForm(); setShowCurrForm(true); }}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '7px', padding: '9px 18px',
                                background: 'linear-gradient(135deg, #0284c7, #0369a1)', color: 'white', border: 'none',
                                borderRadius: '12px', cursor: 'pointer', fontWeight: 600, fontSize: '13px',
                                fontFamily: 'inherit', boxShadow: '0 2px 8px rgba(2, 132, 199, 0.3)',
                                transition: 'all 0.15s ease',
                            }}
                        >
                            <Plus size={15} /> Add Currency
                        </button>
                    </div>
                </div>

                {showCurrForm && (
                    <form onSubmit={handleCurrSubmit} style={{
                        marginBottom: '20px', padding: '20px 24px', background: '#f8fafc',
                        borderRadius: '16px', border: '1.5px solid #e2e8f0',
                    }}>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '16px', marginBottom: '16px' }}>
                            <div>
                                <label style={labelStyle}>Code <span style={{ color: '#ef4444' }}>*</span></label>
                                <input style={inputStyle} maxLength={3} required value={currForm.code} onChange={e => setCurrForm({ ...currForm, code: e.target.value.toUpperCase() })} placeholder="USD" />
                            </div>
                            <div>
                                <label style={labelStyle}>Name <span style={{ color: '#ef4444' }}>*</span></label>
                                <input style={inputStyle} required value={currForm.name} onChange={e => setCurrForm({ ...currForm, name: e.target.value })} placeholder="US Dollar" />
                            </div>
                            <div>
                                <label style={labelStyle}>Symbol <span style={{ color: '#ef4444' }}>*</span></label>
                                <input style={inputStyle} maxLength={5} required value={currForm.symbol} onChange={e => setCurrForm({ ...currForm, symbol: e.target.value })} placeholder="$" />
                            </div>
                            <div>
                                <label style={labelStyle}>Exchange Rate</label>
                                <input style={inputStyle} type="number" step="0.000001" required value={currForm.exchange_rate} onChange={e => setCurrForm({ ...currForm, exchange_rate: e.target.value })} />
                            </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', cursor: 'pointer', color: '#334155', fontWeight: 500 }}>
                                <input type="checkbox" checked={currForm.is_active} onChange={e => setCurrForm({ ...currForm, is_active: e.target.checked })} />
                                Active
                            </label>
                            <div style={{ flex: 1 }} />
                            <button type="button" onClick={resetCurrForm} style={{
                                padding: '9px 18px', borderRadius: '10px', border: '1.5px solid #e2e8f0',
                                background: 'white', color: '#475569', cursor: 'pointer', fontSize: '13px',
                                fontWeight: 600, fontFamily: 'inherit',
                            }}>Cancel</button>
                            <button type="submit" disabled={createCurrency.isPending || updateCurrency.isPending} style={{
                                padding: '9px 18px', borderRadius: '10px', border: 'none',
                                background: 'linear-gradient(135deg, #0284c7, #0369a1)', color: 'white',
                                cursor: 'pointer', fontWeight: 600, fontSize: '13px', fontFamily: 'inherit',
                                boxShadow: '0 2px 8px rgba(2, 132, 199, 0.3)',
                            }}>
                                {editingCurrId ? 'Update' : 'Create'}
                            </button>
                        </div>
                    </form>
                )}

                <div style={{ overflowX: 'auto', borderRadius: '14px', border: '1px solid #e2e8f0' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                        <thead>
                            <tr>
                                <th style={{ ...thStyle, borderTopLeftRadius: '14px' }}>Code</th>
                                <th style={thStyle}>Name</th>
                                <th style={{ ...thStyle, textAlign: 'center' }}>Symbol</th>
                                <th style={{ ...thStyle, textAlign: 'right' }}>Rate</th>
                                <th style={{ ...thStyle, textAlign: 'center' }}>Base</th>
                                <th style={{ ...thStyle, textAlign: 'center' }}>Status</th>
                                <th style={{ ...thStyle, textAlign: 'right', borderTopRightRadius: '14px' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {currencies?.map((c: any) => (
                                <tr
                                    key={c.id}
                                    onMouseOver={e => (e.currentTarget.style.background = '#f8fafc')}
                                    onMouseOut={e => (e.currentTarget.style.background = 'transparent')}
                                    style={{ transition: 'background 0.15s ease' }}
                                >
                                    <td style={{ ...tdStyle, fontWeight: 700, color: '#0f172a' }}>{c.code}</td>
                                    <td style={tdStyle}>{c.name}</td>
                                    <td style={{ ...tdStyle, textAlign: 'center', fontSize: '15px' }}>{c.symbol}</td>
                                    <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace', color: '#334155' }}>{parseFloat(c.exchange_rate).toFixed(6)}</td>
                                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                                        {c.is_base_currency && (
                                            <span style={{
                                                padding: '3px 10px', borderRadius: '9999px', fontSize: '11px',
                                                fontWeight: 700, background: 'rgba(2,132,199,0.08)', color: '#0284c7',
                                            }}>BASE</span>
                                        )}
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                                        <span style={{
                                            padding: '3px 10px', borderRadius: '9999px', fontSize: '11px',
                                            fontWeight: 600,
                                            background: c.is_active ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
                                            color: c.is_active ? '#16a34a' : '#ef4444',
                                        }}>
                                            {c.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </td>
                                    <td style={tdStyle}>
                                        <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
                                            <button
                                                onClick={() => handleEditCurr(c)}
                                                style={{
                                                    padding: '6px', borderRadius: '8px', border: '1px solid #e2e8f0',
                                                    background: 'white', color: '#0284c7', cursor: 'pointer',
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                }}
                                                title="Edit"
                                            >
                                                <Edit2 size={13} />
                                            </button>
                                            <button
                                                onClick={async () => { if (await showConfirm(`Delete ${c.code}?`)) deleteCurrency.mutate(c.id); }}
                                                style={{
                                                    padding: '6px', borderRadius: '8px', border: 'none',
                                                    background: 'rgba(239,68,68,0.08)', color: '#ef4444', cursor: 'pointer',
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                }}
                                                title="Delete"
                                            >
                                                <Trash2 size={13} />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                            {(!currencies || currencies.length === 0) && (
                                <tr>
                                    <td colSpan={7} style={{ padding: '48px 20px', textAlign: 'center' }}>
                                        <Globe size={36} style={{ margin: '0 auto 12px', opacity: 0.2, display: 'block', color: '#64748b' }} />
                                        <p style={{ fontWeight: 600, margin: '0 0 6px', color: '#64748b', fontSize: '14px' }}>No currencies configured</p>
                                        <p style={{ fontSize: '13px', color: '#94a3b8', margin: '0 0 16px', maxWidth: '400px', lineHeight: 1.5 }}>
                                            Seed 15 currencies — 10 African (NGN as base) + 5 global (USD, EUR, GBP, JPY, CNY) — with exchange rates.
                                        </p>
                                        <button
                                            onClick={handleSeedGlobalCurrencies}
                                            disabled={seeding}
                                            style={{
                                                display: 'inline-flex', alignItems: 'center', gap: '8px',
                                                padding: '10px 22px', border: 'none', borderRadius: '12px',
                                                background: 'linear-gradient(135deg, #059669, #047857)',
                                                color: 'white', fontSize: '13px', fontWeight: 600,
                                                cursor: seeding ? 'wait' : 'pointer', fontFamily: 'inherit',
                                                boxShadow: '0 2px 8px rgba(5, 150, 105, 0.3)',
                                            }}
                                        >
                                            {seeding ? <Loader2 size={15} className="animate-spin" /> : <Globe size={15} />}
                                            {seeding ? 'Seeding...' : 'Seed Global Currencies'}
                                        </button>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* ── Section 2: Exchange Rate Table ────────────────── */}
            <div style={{ ...cardStyle, marginBottom: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={iconBadge('linear-gradient(135deg, #f59e0b, #d97706)')}>
                            <ArrowRightLeft size={18} color="white" />
                        </div>
                        <h2 style={{ fontSize: '17px', fontWeight: 700, color: '#0f172a', margin: 0 }}>Exchange Rate Table</h2>
                    </div>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                        <button
                            onClick={() => downloadExchangeRateTemplate()}
                            title="Download CSV import template"
                            style={subtleButtonStyle}
                        >
                            <FileDown size={14} /> Template
                        </button>
                        <button
                            onClick={() => rateFileRef.current?.click()}
                            disabled={bulkImportRates.isPending}
                            title="Import exchange rates from CSV/Excel"
                            style={{
                                ...subtleButtonStyle,
                                opacity: bulkImportRates.isPending ? 0.6 : 1,
                            }}
                        >
                            {bulkImportRates.isPending ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} Import
                        </button>
                        <input ref={rateFileRef} type="file" accept=".csv,.xlsx" hidden onChange={handleRateFileImport} />
                        <button
                            onClick={() => exportExchangeRates()}
                            disabled={!exchangeRates || exchangeRates.length === 0}
                            title="Export exchange rates as CSV"
                            style={{
                                ...subtleButtonStyle,
                                opacity: (!exchangeRates || exchangeRates.length === 0) ? 0.4 : 1,
                            }}
                        >
                            <Download size={14} /> Export
                        </button>
                        <button
                            onClick={() => setShowRateForm(true)}
                            disabled={!currencies || currencies.length < 2}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '7px', padding: '9px 18px',
                                background: 'linear-gradient(135deg, #f59e0b, #d97706)', color: 'white', border: 'none',
                                borderRadius: '12px', cursor: 'pointer', fontWeight: 600, fontSize: '13px',
                                fontFamily: 'inherit', boxShadow: '0 2px 8px rgba(245, 158, 11, 0.3)',
                                opacity: (!currencies || currencies.length < 2) ? 0.5 : 1,
                                transition: 'all 0.15s ease',
                            }}
                        >
                            <Plus size={15} /> Add Rate
                        </button>
                    </div>
                </div>

                <p style={{ color: '#64748b', fontSize: '13px', marginBottom: '16px', lineHeight: 1.6, margin: '0 0 16px 0' }}>
                    Historical exchange rates for converting between currencies. Rates are bidirectional — adding a rate from A to B automatically enables conversion from B to A.
                </p>

                {importResult && (
                    <div style={{
                        marginBottom: '16px', padding: '14px 18px', borderRadius: '14px',
                        background: importResult.errors.length > 0 ? 'rgba(245,158,11,0.06)' : 'rgba(34,197,94,0.06)',
                        border: `1.5px solid ${importResult.errors.length > 0 ? 'rgba(245,158,11,0.2)' : 'rgba(34,197,94,0.2)'}`,
                    }}>
                        <div style={{ display: 'flex', gap: '20px', fontSize: '13px', marginBottom: importResult.errors.length > 0 ? '10px' : 0 }}>
                            <span><strong style={{ color: '#16a34a' }}>{importResult.created}</strong> created</span>
                            <span><strong style={{ color: '#0284c7' }}>{importResult.updated}</strong> updated</span>
                            {importResult.errors.length > 0 && <span><strong style={{ color: '#ef4444' }}>{importResult.errors.length}</strong> errors</span>}
                        </div>
                        {importResult.errors.length > 0 && (
                            <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '12px', color: '#ef4444', maxHeight: '120px', overflowY: 'auto' }}>
                                {importResult.errors.map((err, i) => <li key={i}>{err}</li>)}
                            </ul>
                        )}
                    </div>
                )}

                {showRateForm && currencies && (
                    <form onSubmit={handleRateSubmit} style={{
                        marginBottom: '20px', padding: '20px 24px', background: '#f8fafc',
                        borderRadius: '16px', border: `1.5px solid ${editingRateId ? 'rgba(59,130,246,0.3)' : '#e2e8f0'}`,
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                            <div style={{
                                width: '28px', height: '28px', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                background: editingRateId ? 'linear-gradient(135deg, #3b82f6, #2563eb)' : 'linear-gradient(135deg, #f59e0b, #d97706)',
                            }}>
                                {editingRateId ? <Edit2 size={14} color="white" /> : <Plus size={14} color="white" />}
                            </div>
                            <span style={{ fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>{editingRateId ? 'Edit Exchange Rate' : 'Add Exchange Rate'}</span>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '16px', marginBottom: '16px' }}>
                            <div>
                                <label style={labelStyle}>From Currency <span style={{ color: '#ef4444' }}>*</span></label>
                                <select style={inputStyle} required value={rateForm.from_currency} onChange={e => setRateForm({ ...rateForm, from_currency: e.target.value })} disabled={!!editingRateId}>
                                    <option value="">Select...</option>
                                    {currencies.map((c: any) => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={labelStyle}>To Currency <span style={{ color: '#ef4444' }}>*</span></label>
                                <select style={inputStyle} required value={rateForm.to_currency} onChange={e => setRateForm({ ...rateForm, to_currency: e.target.value })} disabled={!!editingRateId}>
                                    <option value="">Select...</option>
                                    {currencies.filter((c: any) => String(c.id) !== rateForm.from_currency).map((c: any) => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={labelStyle}>Exchange Rate <span style={{ color: '#ef4444' }}>*</span></label>
                                <input style={inputStyle} type="number" step="0.000001" required value={rateForm.exchange_rate} onChange={e => setRateForm({ ...rateForm, exchange_rate: e.target.value })} />
                            </div>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                            <div>
                                <label style={labelStyle}>Valid From <span style={{ color: '#ef4444' }}>*</span></label>
                                <input style={inputStyle} type="date" required value={rateForm.rate_valid_from} onChange={e => setRateForm({ ...rateForm, rate_valid_from: e.target.value })} />
                            </div>
                            <div>
                                <label style={labelStyle}>Valid To <span style={{ fontSize: '10px', color: '#94a3b8', fontWeight: 400, textTransform: 'none' }}>(blank = ongoing)</span></label>
                                <input style={inputStyle} type="date" value={rateForm.rate_valid_to} onChange={e => setRateForm({ ...rateForm, rate_valid_to: e.target.value })} />
                            </div>
                        </div>
                        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                            <button type="button" onClick={resetRateForm} style={{
                                padding: '9px 18px', borderRadius: '10px', border: '1.5px solid #e2e8f0',
                                background: 'white', color: '#475569', cursor: 'pointer', fontSize: '13px',
                                fontWeight: 600, fontFamily: 'inherit',
                            }}>Cancel</button>
                            <button type="submit" disabled={createRate.isPending || updateRate.isPending} style={{
                                padding: '9px 18px', borderRadius: '10px', border: 'none',
                                background: editingRateId ? 'linear-gradient(135deg, #3b82f6, #2563eb)' : 'linear-gradient(135deg, #f59e0b, #d97706)',
                                color: 'white', cursor: 'pointer', fontWeight: 600, fontSize: '13px', fontFamily: 'inherit',
                                boxShadow: editingRateId ? '0 2px 8px rgba(59,130,246,0.3)' : '0 2px 8px rgba(245,158,11,0.3)',
                            }}>{editingRateId ? 'Update' : 'Create'}</button>
                        </div>
                    </form>
                )}

                <div style={{ overflowX: 'auto', borderRadius: '14px', border: '1px solid #e2e8f0' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                        <thead>
                            <tr>
                                <th style={{ ...thStyle, borderTopLeftRadius: '14px' }}>From</th>
                                <th style={{ ...thStyle, textAlign: 'center', width: '40px' }}></th>
                                <th style={thStyle}>To</th>
                                <th style={{ ...thStyle, textAlign: 'right' }}>Rate</th>
                                <th style={{ ...thStyle, textAlign: 'center' }}>Valid From</th>
                                <th style={{ ...thStyle, textAlign: 'center' }}>Valid To</th>
                                <th style={{ ...thStyle, textAlign: 'right', borderTopRightRadius: '14px' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {exchangeRates?.map((r: any) => (
                                <tr
                                    key={r.id}
                                    onMouseOver={e => (e.currentTarget.style.background = '#f8fafc')}
                                    onMouseOut={e => (e.currentTarget.style.background = 'transparent')}
                                    style={{ transition: 'background 0.15s ease' }}
                                >
                                    <td style={{ ...tdStyle, fontWeight: 600 }}>{getCurrencyName(r.from_currency)}</td>
                                    <td style={{ ...tdStyle, textAlign: 'center', color: '#94a3b8' }}><ArrowRightLeft size={14} /></td>
                                    <td style={{ ...tdStyle, fontWeight: 600 }}>{getCurrencyName(r.to_currency)}</td>
                                    <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace', color: '#334155' }}>{parseFloat(r.exchange_rate).toFixed(6)}</td>
                                    <td style={{ ...tdStyle, textAlign: 'center', color: '#64748b' }}>{r.rate_valid_from || r.rate_date}</td>
                                    <td style={{ ...tdStyle, textAlign: 'center', color: r.rate_valid_to ? '#64748b' : '#94a3b8', fontStyle: r.rate_valid_to ? 'normal' : 'italic' }}>
                                        {r.rate_valid_to || 'Ongoing'}
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'right' }}>
                                        <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
                                            <button
                                                onClick={() => handleEditRate(r)}
                                                title="Edit rate"
                                                style={{
                                                    padding: '6px', borderRadius: '8px', border: 'none',
                                                    background: 'rgba(59,130,246,0.08)', color: '#3b82f6', cursor: 'pointer',
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                }}
                                            >
                                                <Edit2 size={13} />
                                            </button>
                                            <button
                                                onClick={async () => { if (await showConfirm('Delete this rate?')) deleteRate.mutate(r.id); }}
                                                title="Delete rate"
                                                style={{
                                                    padding: '6px', borderRadius: '8px', border: 'none',
                                                    background: 'rgba(239,68,68,0.08)', color: '#ef4444', cursor: 'pointer',
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                }}
                                            >
                                                <Trash2 size={13} />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                            {(!exchangeRates || exchangeRates.length === 0) && (
                                <tr><td colSpan={7} style={{ padding: '40px', textAlign: 'center', color: '#94a3b8', fontSize: '14px' }}>No exchange rates configured</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* ── Section 3: Default Currency Configuration ─────── */}
            <div style={cardStyle}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
                    <div style={iconBadge('linear-gradient(135deg, #8b5cf6, #7c3aed)')}>
                        <Star size={18} color="white" />
                    </div>
                    <h2 style={{ fontSize: '17px', fontWeight: 700, color: '#0f172a', margin: 0 }}>Default Reporting Currencies</h2>
                </div>

                <p style={{ color: '#64748b', fontSize: '13px', marginBottom: '24px', lineHeight: 1.6, margin: '0 0 24px 0' }}>
                    Select 5 global currencies used for reporting. Reports can display amounts in any of these currencies for comparison.
                    Choose the most relevant currencies for your organisation's international operations.
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(185px, 1fr))', gap: '14px', marginBottom: '24px' }}>
                    {[
                        { label: 'Currency 1 — Local', hint: 'NGN — Nigerian Naira', value: slot1, setter: setSlot1, accent: '#0284c7', bg: 'rgba(2,132,199,0.04)', border: 'rgba(2,132,199,0.15)' },
                        { label: 'Currency 2 — Trade', hint: 'USD — US Dollar', value: slot2, setter: setSlot2, accent: '#16a34a', bg: 'rgba(22,163,74,0.04)', border: 'rgba(22,163,74,0.15)' },
                        { label: 'Currency 3 — Reporting', hint: 'EUR — Euro', value: slot3, setter: setSlot3, accent: '#d97706', bg: 'rgba(217,119,6,0.04)', border: 'rgba(217,119,6,0.15)' },
                        { label: 'Currency 4 — Reporting', hint: 'GBP — British Pound', value: slot4, setter: setSlot4, accent: '#7c3aed', bg: 'rgba(124,58,237,0.04)', border: 'rgba(124,58,237,0.15)' },
                        { label: 'Currency 5 — Reporting', hint: 'ZAR — South African Rand', value: slot5, setter: setSlot5, accent: '#e11d48', bg: 'rgba(225,29,72,0.04)', border: 'rgba(225,29,72,0.15)' },
                    ].map((slot) => (
                        <div key={slot.label} style={{
                            padding: '18px 20px', borderRadius: '16px',
                            border: `1.5px solid ${slot.border}`,
                            background: slot.bg,
                        }}>
                            <label style={{ ...labelStyle, color: slot.accent }}>{slot.label}</label>
                            <select
                                style={{
                                    ...inputStyle,
                                    background: 'white',
                                    borderColor: slot.border,
                                }}
                                value={slot.value || ''}
                                onChange={(e) => slot.setter(e.target.value ? parseInt(e.target.value) : null)}
                            >
                                <option value="">— Not Set —</option>
                                {currencies?.map((c: any) => (
                                    <option key={c.id} value={c.id}>{c.code} — {c.name} ({c.symbol})</option>
                                ))}
                            </select>
                            <div style={{ marginTop: '6px', fontSize: '11px', color: '#94a3b8', fontStyle: 'italic' }}>
                                e.g. {slot.hint}
                            </div>
                        </div>
                    ))}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                    <button
                        onClick={handleSaveDefaults}
                        disabled={saveDefaults.isPending}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 22px',
                            background: 'linear-gradient(135deg, #8b5cf6, #7c3aed)', color: 'white', border: 'none',
                            borderRadius: '12px', cursor: 'pointer', fontWeight: 600, fontSize: '13px',
                            fontFamily: 'inherit', boxShadow: '0 2px 8px rgba(139, 92, 246, 0.3)',
                            transition: 'all 0.15s ease',
                        }}
                    >
                        {saveDefaults.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                        Save Defaults
                    </button>
                    {defaultsMsg && (
                        <span style={{ fontSize: '13px', fontWeight: 600, color: '#16a34a' }}>{defaultsMsg}</span>
                    )}
                </div>
            </div>
        </SettingsLayout>
    );
}
