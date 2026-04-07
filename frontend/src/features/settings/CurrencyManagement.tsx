import { useState, useEffect, useRef } from 'react';
import { useDialog } from '../../hooks/useDialog';
import { Coins, Plus, Trash2, Edit2, Save, Loader2, ArrowRightLeft, Star, Download, Upload, FileDown } from 'lucide-react';
import PageHeader from '../../components/PageHeader';
import {
    useCurrencies, useCreateCurrency, useUpdateCurrency, useDeleteCurrency,
    useExchangeRates, useCreateExchangeRate, useDeleteExchangeRate,
    useDefaultCurrencies, useSaveDefaultCurrencies,
    downloadExchangeRateTemplate, exportExchangeRates, useBulkImportExchangeRates,
} from '../accounting/hooks/useAccountingEnhancements';
import SettingsLayout from './SettingsLayout';
import GlassCard from '../accounting/components/shared/GlassCard';
import '../accounting/styles/glassmorphism.css';

export default function CurrencyManagement() {
    const { showConfirm } = useDialog();
    const { data: currencies, isLoading: currLoading } = useCurrencies();
    const { data: exchangeRates, isLoading: ratesLoading } = useExchangeRates();
    const { data: defaults } = useDefaultCurrencies();
    const createCurrency = useCreateCurrency();
    const updateCurrency = useUpdateCurrency();
    const deleteCurrency = useDeleteCurrency();
    const createRate = useCreateExchangeRate();
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
    const [rateForm, setRateForm] = useState({ from_currency: '', to_currency: '', rate_date: new Date().toISOString().split('T')[0], exchange_rate: '1.0' });

    // Default currencies
    const [slot1, setSlot1] = useState<number | null>(null);
    const [slot2, setSlot2] = useState<number | null>(null);
    const [slot3, setSlot3] = useState<number | null>(null);
    const [slot4, setSlot4] = useState<number | null>(null);
    const [defaultsMsg, setDefaultsMsg] = useState('');

    useEffect(() => {
        if (defaults) {
            setSlot1(defaults.default_currency_1 || null);
            setSlot2(defaults.default_currency_2 || null);
            setSlot3(defaults.default_currency_3 || null);
            setSlot4(defaults.default_currency_4 || null);
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

    const handleRateSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        await createRate.mutateAsync({
            from_currency: parseInt(rateForm.from_currency),
            to_currency: parseInt(rateForm.to_currency),
            rate_date: rateForm.rate_date,
            exchange_rate: parseFloat(rateForm.exchange_rate),
        });
        setShowRateForm(false);
        setRateForm({ from_currency: '', to_currency: '', rate_date: new Date().toISOString().split('T')[0], exchange_rate: '1.0' });
    };

    const handleSaveDefaults = async () => {
        await saveDefaults.mutateAsync({
            default_currency_1: slot1 || null,
            default_currency_2: slot2 || null,
            default_currency_3: slot3 || null,
            default_currency_4: slot4 || null,
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

    const inputStyle: React.CSSProperties = {
        width: '100%', padding: '0.6rem 0.75rem', borderRadius: '8px',
        border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
        color: 'var(--color-text)', fontSize: 'var(--text-sm)',
    };

    const labelStyle: React.CSSProperties = {
        display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '0.4rem',
        color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em',
    };

    if (currLoading) {
        return (
            <SettingsLayout>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '300px' }}>
                    <Loader2 size={32} className="animate-spin" style={{ color: 'var(--color-primary)' }} />
                </div>
            </SettingsLayout>
        );
    }

    return (
        <SettingsLayout>
            <PageHeader
                title="Currency Management"
                subtitle="Manage currencies, exchange rates, and default reporting currencies."
                icon={<Coins size={22} color="white" />}
                backButton={false}
            />

            {/* ── Section 1: Currencies ────────────────────────── */}
            <GlassCard style={{ marginBottom: '1.5rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <Coins size={20} style={{ color: '#2471a3' }} />
                        <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 600 }}>Currencies</h2>
                    </div>
                    <button
                        onClick={() => { resetCurrForm(); setShowCurrForm(true); }}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem',
                            background: 'var(--color-primary)', color: 'white', border: 'none',
                            borderRadius: '8px', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)',
                        }}
                    >
                        <Plus size={16} /> Add Currency
                    </button>
                </div>

                {showCurrForm && (
                    <form onSubmit={handleCurrSubmit} style={{ marginBottom: '1.25rem', padding: '1rem', background: 'var(--color-background)', borderRadius: '8px', border: '1px solid var(--color-border)' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.75rem', marginBottom: '0.75rem' }}>
                            <div>
                                <label style={labelStyle}>Code<span className="required-mark"> *</span></label>
                                <input style={inputStyle} maxLength={3} required value={currForm.code} onChange={e => setCurrForm({ ...currForm, code: e.target.value.toUpperCase() })} placeholder="USD" />
                            </div>
                            <div>
                                <label style={labelStyle}>Name<span className="required-mark"> *</span></label>
                                <input style={inputStyle} required value={currForm.name} onChange={e => setCurrForm({ ...currForm, name: e.target.value })} placeholder="US Dollar" />
                            </div>
                            <div>
                                <label style={labelStyle}>Symbol<span className="required-mark"> *</span></label>
                                <input style={inputStyle} maxLength={5} required value={currForm.symbol} onChange={e => setCurrForm({ ...currForm, symbol: e.target.value })} placeholder="$" />
                            </div>
                            <div>
                                <label style={labelStyle}>Exchange Rate</label>
                                <input style={inputStyle} type="number" step="0.000001" required value={currForm.exchange_rate} onChange={e => setCurrForm({ ...currForm, exchange_rate: e.target.value })} />
                            </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: 'var(--text-sm)', cursor: 'pointer' }}>
                                <input type="checkbox" checked={currForm.is_active} onChange={e => setCurrForm({ ...currForm, is_active: e.target.checked })} />
                                Active
                            </label>
                            <div style={{ flex: 1 }} />
                            <button type="button" onClick={resetCurrForm} style={{ padding: '0.5rem 1rem', borderRadius: '6px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)', cursor: 'pointer', fontSize: 'var(--text-sm)' }}>Cancel</button>
                            <button type="submit" disabled={createCurrency.isPending || updateCurrency.isPending} style={{ padding: '0.5rem 1rem', borderRadius: '6px', border: 'none', background: 'var(--color-primary)', color: 'white', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)' }}>
                                {editingCurrId ? 'Update' : 'Create'}
                            </button>
                        </div>
                    </form>
                )}

                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: 600 }}>Code</th>
                                <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: 600 }}>Name</th>
                                <th style={{ padding: '0.75rem', textAlign: 'center', fontWeight: 600 }}>Symbol</th>
                                <th style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 600 }}>Rate</th>
                                <th style={{ padding: '0.75rem', textAlign: 'center', fontWeight: 600 }}>Base</th>
                                <th style={{ padding: '0.75rem', textAlign: 'center', fontWeight: 600 }}>Status</th>
                                <th style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 600 }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {currencies?.map((c: any) => (
                                <tr key={c.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                    <td style={{ padding: '0.75rem', fontWeight: 600 }}>{c.code}</td>
                                    <td style={{ padding: '0.75rem' }}>{c.name}</td>
                                    <td style={{ padding: '0.75rem', textAlign: 'center', fontSize: 'var(--text-base)' }}>{c.symbol}</td>
                                    <td style={{ padding: '0.75rem', textAlign: 'right', fontFamily: 'monospace' }}>{parseFloat(c.exchange_rate).toFixed(6)}</td>
                                    <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                                        {c.is_base_currency && <span style={{ padding: '0.15rem 0.5rem', borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 600, background: 'rgba(59,130,246,0.1)', color: '#2471a3' }}>BASE</span>}
                                    </td>
                                    <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                                        <span style={{ padding: '0.15rem 0.5rem', borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 500, background: c.is_active ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)', color: c.is_active ? '#22c55e' : '#ef4444' }}>
                                            {c.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </td>
                                    <td style={{ padding: '0.75rem' }}>
                                        <div style={{ display: 'flex', gap: '0.4rem', justifyContent: 'flex-end' }}>
                                            <button onClick={() => handleEditCurr(c)} style={{ padding: '0.35rem', borderRadius: '6px', border: 'none', background: 'var(--color-surface)', color: 'var(--color-primary)', cursor: 'pointer' }} title="Edit"><Edit2 size={14} /></button>
                                            <button onClick={async () => { if (await showConfirm(`Delete ${c.code}?`)) deleteCurrency.mutate(c.id); }} style={{ padding: '0.35rem', borderRadius: '6px', border: 'none', background: 'rgba(239,68,68,0.1)', color: '#ef4444', cursor: 'pointer' }} title="Delete"><Trash2 size={14} /></button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                            {(!currencies || currencies.length === 0) && (
                                <tr><td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No currencies configured</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </GlassCard>

            {/* ── Section 2: Exchange Rate Table ────────────────── */}
            <GlassCard style={{ marginBottom: '1.5rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <ArrowRightLeft size={20} style={{ color: '#f59e0b' }} />
                        <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 600 }}>Exchange Rate Table</h2>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                        <button
                            onClick={() => downloadExchangeRateTemplate()}
                            title="Download CSV import template"
                            style={{
                                display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.5rem 0.75rem',
                                border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                                borderRadius: '8px', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-xs)',
                                color: 'var(--color-text)',
                            }}
                        >
                            <FileDown size={15} /> Template
                        </button>
                        <button
                            onClick={() => rateFileRef.current?.click()}
                            disabled={bulkImportRates.isPending}
                            title="Import exchange rates from CSV/Excel"
                            style={{
                                display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.5rem 0.75rem',
                                border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                                borderRadius: '8px', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-xs)',
                                color: 'var(--color-text)',
                            }}
                        >
                            {bulkImportRates.isPending ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />} Import
                        </button>
                        <input ref={rateFileRef} type="file" accept=".csv,.xlsx" hidden onChange={handleRateFileImport} />
                        <button
                            onClick={() => exportExchangeRates()}
                            disabled={!exchangeRates || exchangeRates.length === 0}
                            title="Export exchange rates as CSV"
                            style={{
                                display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.5rem 0.75rem',
                                border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                                borderRadius: '8px', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-xs)',
                                color: 'var(--color-text)',
                                opacity: (!exchangeRates || exchangeRates.length === 0) ? 0.5 : 1,
                            }}
                        >
                            <Download size={15} /> Export
                        </button>
                        <button
                            onClick={() => setShowRateForm(true)}
                            disabled={!currencies || currencies.length < 2}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem',
                                background: 'var(--color-primary)', color: 'white', border: 'none',
                                borderRadius: '8px', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)',
                                opacity: (!currencies || currencies.length < 2) ? 0.5 : 1,
                            }}
                        >
                            <Plus size={16} /> Add Rate
                        </button>
                    </div>
                </div>

                <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', marginBottom: '1rem', lineHeight: 1.5 }}>
                    Historical exchange rates for converting between currencies. Rates are bidirectional — adding a rate from A to B automatically enables conversion from B to A.
                </p>

                {importResult && (
                    <div style={{
                        marginBottom: '1rem', padding: '0.75rem 1rem', borderRadius: '8px',
                        background: importResult.errors.length > 0 ? 'rgba(245,158,11,0.08)' : 'rgba(34,197,94,0.08)',
                        border: `1px solid ${importResult.errors.length > 0 ? 'rgba(245,158,11,0.3)' : 'rgba(34,197,94,0.3)'}`,
                    }}>
                        <div style={{ display: 'flex', gap: '1.5rem', fontSize: 'var(--text-sm)', marginBottom: importResult.errors.length > 0 ? '0.5rem' : 0 }}>
                            <span><strong style={{ color: '#22c55e' }}>{importResult.created}</strong> created</span>
                            <span><strong style={{ color: '#2471a3' }}>{importResult.updated}</strong> updated</span>
                            {importResult.errors.length > 0 && <span><strong style={{ color: '#ef4444' }}>{importResult.errors.length}</strong> errors</span>}
                        </div>
                        {importResult.errors.length > 0 && (
                            <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: 'var(--text-xs)', color: '#ef4444', maxHeight: '120px', overflowY: 'auto' }}>
                                {importResult.errors.map((err, i) => <li key={i}>{err}</li>)}
                            </ul>
                        )}
                    </div>
                )}

                {showRateForm && currencies && (
                    <form onSubmit={handleRateSubmit} style={{ marginBottom: '1.25rem', padding: '1rem', background: 'var(--color-background)', borderRadius: '8px', border: '1px solid var(--color-border)' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.75rem', marginBottom: '0.75rem' }}>
                            <div>
                                <label style={labelStyle}>From Currency<span className="required-mark"> *</span></label>
                                <select style={inputStyle} required value={rateForm.from_currency} onChange={e => setRateForm({ ...rateForm, from_currency: e.target.value })}>
                                    <option value="">Select...</option>
                                    {currencies.map((c: any) => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={labelStyle}>To Currency<span className="required-mark"> *</span></label>
                                <select style={inputStyle} required value={rateForm.to_currency} onChange={e => setRateForm({ ...rateForm, to_currency: e.target.value })}>
                                    <option value="">Select...</option>
                                    {currencies.filter((c: any) => String(c.id) !== rateForm.from_currency).map((c: any) => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={labelStyle}>Rate Date<span className="required-mark"> *</span></label>
                                <input style={inputStyle} type="date" required value={rateForm.rate_date} onChange={e => setRateForm({ ...rateForm, rate_date: e.target.value })} />
                            </div>
                            <div>
                                <label style={labelStyle}>Exchange Rate<span className="required-mark"> *</span></label>
                                <input style={inputStyle} type="number" step="0.000001" required value={rateForm.exchange_rate} onChange={e => setRateForm({ ...rateForm, exchange_rate: e.target.value })} />
                            </div>
                        </div>
                        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                            <button type="button" onClick={() => setShowRateForm(false)} style={{ padding: '0.5rem 1rem', borderRadius: '6px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)', cursor: 'pointer', fontSize: 'var(--text-sm)' }}>Cancel</button>
                            <button type="submit" disabled={createRate.isPending} style={{ padding: '0.5rem 1rem', borderRadius: '6px', border: 'none', background: 'var(--color-primary)', color: 'white', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)' }}>Create</button>
                        </div>
                    </form>
                )}

                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: 600 }}>From</th>
                                <th style={{ padding: '0.75rem', textAlign: 'center', fontWeight: 600 }}></th>
                                <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: 600 }}>To</th>
                                <th style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 600 }}>Rate</th>
                                <th style={{ padding: '0.75rem', textAlign: 'center', fontWeight: 600 }}>Date</th>
                                <th style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 600 }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {exchangeRates?.map((r: any) => (
                                <tr key={r.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                    <td style={{ padding: '0.75rem', fontWeight: 500 }}>{getCurrencyName(r.from_currency)}</td>
                                    <td style={{ padding: '0.75rem', textAlign: 'center', color: 'var(--color-text-muted)' }}><ArrowRightLeft size={14} /></td>
                                    <td style={{ padding: '0.75rem', fontWeight: 500 }}>{getCurrencyName(r.to_currency)}</td>
                                    <td style={{ padding: '0.75rem', textAlign: 'right', fontFamily: 'monospace' }}>{parseFloat(r.exchange_rate).toFixed(6)}</td>
                                    <td style={{ padding: '0.75rem', textAlign: 'center' }}>{r.rate_date}</td>
                                    <td style={{ padding: '0.75rem', textAlign: 'right' }}>
                                        <button onClick={async () => { if (await showConfirm('Delete this rate?')) deleteRate.mutate(r.id); }} style={{ padding: '0.35rem', borderRadius: '6px', border: 'none', background: 'rgba(239,68,68,0.1)', color: '#ef4444', cursor: 'pointer' }}><Trash2 size={14} /></button>
                                    </td>
                                </tr>
                            ))}
                            {(!exchangeRates || exchangeRates.length === 0) && (
                                <tr><td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No exchange rates configured</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </GlassCard>

            {/* ── Section 3: Default Currency Configuration ─────── */}
            <GlassCard>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.25rem' }}>
                    <Star size={20} style={{ color: '#8b5cf6' }} />
                    <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 600 }}>Default Reporting Currencies</h2>
                </div>

                <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', marginBottom: '1.5rem', lineHeight: 1.5 }}>
                    Configure up to 4 default currencies. Reports can display amounts in any of these currencies for comparison.
                    Currency 1 is your local/base currency. Currency 2 is for document transactions. Currencies 3-4 are optional reporting currencies.
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
                    {[
                        { label: 'Currency 1 — Local', value: slot1, setter: setSlot1, color: '#2471a3' },
                        { label: 'Currency 2 — Document', value: slot2, setter: setSlot2, color: '#10b981' },
                        { label: 'Currency 3 — Reporting', value: slot3, setter: setSlot3, color: '#f59e0b' },
                        { label: 'Currency 4 — Reporting', value: slot4, setter: setSlot4, color: '#8b5cf6' },
                    ].map((slot) => (
                        <div key={slot.label} style={{ padding: '1rem', borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-background)' }}>
                            <label style={{ ...labelStyle, color: slot.color }}>{slot.label}</label>
                            <select
                                style={inputStyle}
                                value={slot.value || ''}
                                onChange={(e) => slot.setter(e.target.value ? parseInt(e.target.value) : null)}
                            >
                                <option value="">— Not Set —</option>
                                {currencies?.map((c: any) => (
                                    <option key={c.id} value={c.id}>{c.code} — {c.name} ({c.symbol})</option>
                                ))}
                            </select>
                        </div>
                    ))}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <button
                        onClick={handleSaveDefaults}
                        disabled={saveDefaults.isPending}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1.25rem',
                            background: 'var(--color-primary)', color: 'white', border: 'none',
                            borderRadius: '8px', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)',
                        }}
                    >
                        {saveDefaults.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                        Save Defaults
                    </button>
                    {defaultsMsg && (
                        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-success)' }}>{defaultsMsg}</span>
                    )}
                </div>
            </GlassCard>
        </SettingsLayout>
    );
}
