import { useState, useMemo } from 'react';
import { Plus, Edit, Trash2, Search, X, Check, ChevronUp, ChevronDown, Receipt, ShieldCheck } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import {
    useTaxCodes,
    useCreateTaxCode,
    useUpdateTaxCode,
    useDeleteTaxCode,
    useWithholdingTaxes,
    useCreateWithholdingTax,
    useUpdateWithholdingTax,
    useDeleteWithholdingTax,
} from '../hooks/useAccountingEnhancements';
import StatusBadge from '../components/shared/StatusBadge';
import GlassCard from '../components/shared/GlassCard';
import SettingsLayout from '../../settings/SettingsLayout';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useDialog } from '../../../hooks/useDialog';
import '../styles/glassmorphism.css';

interface AccountOption {
    id: number;
    code: string;
    name: string;
}

interface TaxCode {
    id: number;
    code: string;
    name: string;
    tax_type: string;
    tax_type_display: string;
    direction: string;
    direction_display: string;
    rate: string;
    tax_account: number | null;
    tax_account_display: AccountOption | null;
    input_tax_account: number | null;
    input_tax_account_display: AccountOption | null;
    output_tax_account: number | null;
    output_tax_account_display: AccountOption | null;
    is_active: boolean;
    description: string;
}

interface WithholdingTax {
    id: number;
    code: string;
    name: string;
    income_type: string;
    rate: string;
    withholding_account: number | null;
    withholding_account_display: AccountOption | null;
    is_active: boolean;
}

type TaxCodeSortKey = 'code' | 'name' | 'tax_type' | 'direction' | 'rate' | 'is_active';
type WHTSortKey = 'code' | 'name' | 'income_type' | 'rate' | 'is_active';

const TAX_TYPES = [
    { value: 'vat', label: 'VAT' },
    { value: 'sales_tax', label: 'Sales Tax' },
    { value: 'service_tax', label: 'Service Tax' },
    { value: 'excise_duty', label: 'Excise Duty' },
    { value: 'customs_duty', label: 'Customs Duty' },
];

const DIRECTIONS = [
    { value: 'purchase', label: 'Purchase (Input)' },
    { value: 'sales', label: 'Sales (Output)' },
    { value: 'both', label: 'Both' },
];

const initialTaxCodeForm = {
    code: '',
    name: '',
    tax_type: 'vat',
    direction: 'sales',
    rate: '',
    tax_account: '' as string | number,
    input_tax_account: '' as string | number,
    output_tax_account: '' as string | number,
    is_active: true,
    description: '',
};

const initialWHTForm = {
    code: '',
    name: '',
    income_type: '',
    rate: '',
    withholding_account: '' as string | number,
    is_active: true,
};

const labelStyle: React.CSSProperties = {
    display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600,
    color: 'var(--text-secondary)', marginBottom: '8px',
    textTransform: 'uppercase', letterSpacing: '0.05em',
};

export default function TaxManagement() {
    const { showConfirm } = useDialog();
    const [activeTab, setActiveTab] = useState<'taxcodes' | 'wht'>('taxcodes');

    // ── Tax Code state ────────────────────────────────────────
    const [showTaxCodeForm, setShowTaxCodeForm] = useState(false);
    const [editingTaxCode, setEditingTaxCode] = useState<TaxCode | null>(null);
    const [taxCodeSearch, setTaxCodeSearch] = useState('');
    const [taxCodeSort, setTaxCodeSort] = useState<{ key: TaxCodeSortKey; direction: 'asc' | 'desc' } | null>(null);
    const [taxCodeForm, setTaxCodeForm] = useState(initialTaxCodeForm);

    // ── WHT state ─────────────────────────────────────────────
    const [showWHTForm, setShowWHTForm] = useState(false);
    const [editingWHT, setEditingWHT] = useState<WithholdingTax | null>(null);
    const [whtSearch, setWHTSearch] = useState('');
    const [whtSort, setWHTSort] = useState<{ key: WHTSortKey; direction: 'asc' | 'desc' } | null>(null);
    const [whtForm, setWHTForm] = useState(initialWHTForm);

    // ── Data hooks ────────────────────────────────────────────
    const { data: taxCodes, isLoading: tcLoading, isError: tcError, error: tcErr } = useTaxCodes();
    const createTaxCode = useCreateTaxCode();
    const updateTaxCode = useUpdateTaxCode();
    const deleteTaxCode = useDeleteTaxCode();

    const { data: whtList, isLoading: whtLoading, isError: whtError, error: whtErr } = useWithholdingTaxes();
    const createWHT = useCreateWithholdingTax();
    const updateWHT = useUpdateWithholdingTax();
    const deleteWHT = useDeleteWithholdingTax();

    // ── GL Account dropdowns ──────────────────────────────────
    const { data: allAccounts } = useQuery<AccountOption[]>({
        queryKey: ['accounts', 'all-active'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/accounts/', {
                params: { is_active: true, page_size: 200 },
            });
            return data.results;
        },
        staleTime: 5 * 60 * 1000,
    });

    const { data: liabilityAccounts } = useQuery<AccountOption[]>({
        queryKey: ['accounts', 'liability'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/accounts/', {
                params: { account_type: 'Liability', is_active: true, page_size: 200 },
            });
            return data.results;
        },
        staleTime: 5 * 60 * 1000,
    });

    // ── Tax Code handlers ─────────────────────────────────────
    const resetTaxCodeForm = () => { setTaxCodeForm(initialTaxCodeForm); setEditingTaxCode(null); };

    const handleTaxCodeSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const payload = {
            ...taxCodeForm,
            tax_account: taxCodeForm.tax_account || null,
            input_tax_account: taxCodeForm.input_tax_account || null,
            output_tax_account: taxCodeForm.output_tax_account || null,
        };
        if (editingTaxCode) {
            updateTaxCode.mutate({ id: editingTaxCode.id, ...payload }, {
                onSuccess: () => { setShowTaxCodeForm(false); resetTaxCodeForm(); },
            });
        } else {
            createTaxCode.mutate(payload, {
                onSuccess: () => { setShowTaxCodeForm(false); resetTaxCodeForm(); },
            });
        }
    };

    const handleEditTaxCode = (tc: TaxCode) => {
        setEditingTaxCode(tc);
        setTaxCodeForm({
            code: tc.code,
            name: tc.name,
            tax_type: tc.tax_type,
            direction: tc.direction,
            rate: tc.rate,
            tax_account: tc.tax_account || '',
            input_tax_account: tc.input_tax_account || '',
            output_tax_account: tc.output_tax_account || '',
            is_active: tc.is_active,
            description: tc.description,
        });
        setShowTaxCodeForm(true);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const handleDeleteTaxCode = async (id: number, name: string) => {
        if (await showConfirm(`Delete tax code "${name}"? This action cannot be undone.`)) {
            deleteTaxCode.mutate(id);
        }
    };

    // ── WHT handlers ──────────────────────────────────────────
    const resetWHTForm = () => { setWHTForm(initialWHTForm); setEditingWHT(null); };

    const handleWHTSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const payload = {
            ...whtForm,
            withholding_account: whtForm.withholding_account || null,
        };
        if (editingWHT) {
            updateWHT.mutate({ id: editingWHT.id, ...payload }, {
                onSuccess: () => { setShowWHTForm(false); resetWHTForm(); },
            });
        } else {
            createWHT.mutate(payload, {
                onSuccess: () => { setShowWHTForm(false); resetWHTForm(); },
            });
        }
    };

    const handleEditWHT = (w: WithholdingTax) => {
        setEditingWHT(w);
        setWHTForm({
            code: w.code,
            name: w.name,
            income_type: w.income_type,
            rate: w.rate,
            withholding_account: w.withholding_account || '',
            is_active: w.is_active,
        });
        setShowWHTForm(true);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const handleDeleteWHT = async (id: number, name: string) => {
        if (await showConfirm(`Delete withholding tax "${name}"? This action cannot be undone.`)) {
            deleteWHT.mutate(id);
        }
    };

    // ── Sorting helpers ───────────────────────────────────────
    const requestTaxCodeSort = (key: TaxCodeSortKey) => {
        let direction: 'asc' | 'desc' = 'asc';
        if (taxCodeSort && taxCodeSort.key === key && taxCodeSort.direction === 'asc') direction = 'desc';
        setTaxCodeSort({ key, direction });
    };

    const requestWHTSort = (key: WHTSortKey) => {
        let direction: 'asc' | 'desc' = 'asc';
        if (whtSort && whtSort.key === key && whtSort.direction === 'asc') direction = 'desc';
        setWHTSort({ key, direction });
    };

    const sortedTaxCodes = useMemo(() => {
        let filtered = (Array.isArray(taxCodes) ? taxCodes : []).filter((tc: TaxCode) =>
            tc.code.toLowerCase().includes(taxCodeSearch.toLowerCase()) ||
            tc.name.toLowerCase().includes(taxCodeSearch.toLowerCase())
        );
        if (taxCodeSort) {
            filtered.sort((a: any, b: any) => {
                const aVal = a[taxCodeSort.key];
                const bVal = b[taxCodeSort.key];
                if (aVal < bVal) return taxCodeSort.direction === 'asc' ? -1 : 1;
                if (aVal > bVal) return taxCodeSort.direction === 'asc' ? 1 : -1;
                return 0;
            });
        }
        return filtered;
    }, [taxCodes, taxCodeSearch, taxCodeSort]);

    const sortedWHT = useMemo(() => {
        let filtered = (Array.isArray(whtList) ? whtList : []).filter((w: WithholdingTax) =>
            w.code.toLowerCase().includes(whtSearch.toLowerCase()) ||
            w.name.toLowerCase().includes(whtSearch.toLowerCase())
        );
        if (whtSort) {
            filtered.sort((a: any, b: any) => {
                const aVal = a[whtSort.key];
                const bVal = b[whtSort.key];
                if (aVal < bVal) return whtSort.direction === 'asc' ? -1 : 1;
                if (aVal > bVal) return whtSort.direction === 'asc' ? 1 : -1;
                return 0;
            });
        }
        return filtered;
    }, [whtList, whtSearch, whtSort]);

    const getTCSortIndicator = (key: TaxCodeSortKey) => {
        if (!taxCodeSort || taxCodeSort.key !== key) return null;
        return taxCodeSort.direction === 'asc'
            ? <ChevronUp size={14} style={{ marginLeft: '4px' }} />
            : <ChevronDown size={14} style={{ marginLeft: '4px' }} />;
    };

    const getWHTSortIndicator = (key: WHTSortKey) => {
        if (!whtSort || whtSort.key !== key) return null;
        return whtSort.direction === 'asc'
            ? <ChevronUp size={14} style={{ marginLeft: '4px' }} />
            : <ChevronDown size={14} style={{ marginLeft: '4px' }} />;
    };

    // ── Loading / Error ───────────────────────────────────────
    if (tcLoading || whtLoading) return <LoadingScreen message="Loading tax management..." />;

    if (tcError || whtError) {
        return (
            <SettingsLayout>
                <div style={{ padding: '2rem', textAlign: 'center', color: 'red' }}>
                    <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 600, marginBottom: '1rem' }}>Error loading Tax Management</h2>
                    <p style={{ marginBottom: '1.5rem' }}>{(tcErr as any)?.message || (whtErr as any)?.message || 'Unknown error'}</p>
                    <button className="btn btn-primary" onClick={() => window.location.reload()}>Retry</button>
                </div>
            </SettingsLayout>
        );
    }

    // ── Tab style helper ──────────────────────────────────────
    const tabStyle = (active: boolean): React.CSSProperties => ({
        padding: '0.75rem 1.5rem',
        border: 'none',
        borderBottom: active ? '3px solid var(--primary)' : '3px solid transparent',
        background: 'transparent',
        color: active ? 'var(--primary)' : 'var(--text-muted)',
        fontWeight: active ? 700 : 500,
        fontSize: 'var(--text-sm)',
        cursor: 'pointer',
        transition: 'all 0.2s',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
    });

    return (
        <SettingsLayout>
            <PageHeader
                title="Tax Management"
                subtitle="Configure tax codes (VAT) and withholding tax with GL account integration"
                icon={<ShieldCheck size={22} />}
                backButton={false}
                actions={
                    <button
                        className="btn-primary ripple"
                        onClick={() => {
                            if (activeTab === 'taxcodes') {
                                if (showTaxCodeForm && !editingTaxCode) { setShowTaxCodeForm(false); }
                                else { resetTaxCodeForm(); setShowTaxCodeForm(true); }
                            } else {
                                if (showWHTForm && !editingWHT) { setShowWHTForm(false); }
                                else { resetWHTForm(); setShowWHTForm(true); }
                            }
                        }}
                    >
                        {((activeTab === 'taxcodes' && showTaxCodeForm && !editingTaxCode) || (activeTab === 'wht' && showWHTForm && !editingWHT))
                            ? <><X size={18} style={{ marginRight: '8px' }} /> Close Form</>
                            : <><Plus size={18} style={{ marginRight: '8px' }} /> {activeTab === 'taxcodes' ? 'Add Tax Code' : 'Add WHT Code'}</>
                        }
                    </button>
                }
            />

            {/* Tabs */}
            <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: '1.5rem' }}>
                <button style={tabStyle(activeTab === 'taxcodes')} onClick={() => { setActiveTab('taxcodes'); setShowWHTForm(false); resetWHTForm(); }}>
                    <Receipt size={18} /> Tax Codes (VAT)
                </button>
                <button style={tabStyle(activeTab === 'wht')} onClick={() => { setActiveTab('wht'); setShowTaxCodeForm(false); resetTaxCodeForm(); }}>
                    <ShieldCheck size={18} /> Withholding Tax
                </button>
            </div>

            {/* ═══════════════════════════════════════════════════════════
                TAX CODES TAB
               ═══════════════════════════════════════════════════════════ */}
            {activeTab === 'taxcodes' && (
                <>
                    {/* Tax Code Form */}
                    {showTaxCodeForm && (
                        <div className="animate-slide-down" style={{ marginBottom: '2rem' }}>
                            <GlassCard gradient style={{ padding: '2rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                                    <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>
                                        {editingTaxCode ? 'Edit Tax Code' : 'Create New Tax Code'}
                                    </h2>
                                    <button onClick={() => { setShowTaxCodeForm(false); resetTaxCodeForm(); }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
                                        <X size={20} />
                                    </button>
                                </div>
                                <form onSubmit={handleTaxCodeSubmit}>
                                    {/* Row 1: Code, Name, Active */}
                                    <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr auto', gap: '1.5rem', marginBottom: '1.5rem' }}>
                                        <div>
                                            <label style={labelStyle}>Tax Code<span className="required-mark"> *</span></label>
                                            <input type="text" required maxLength={20} value={taxCodeForm.code}
                                                onChange={(e) => setTaxCodeForm({ ...taxCodeForm, code: e.target.value })}
                                                placeholder="e.g. VAT-S15" className="glass-input"
                                                style={{ width: '100%', fontFamily: 'monospace', fontSize: 'var(--text-base)' }}
                                            />
                                        </div>
                                        <div>
                                            <label style={labelStyle}>Name<span className="required-mark"> *</span></label>
                                            <input type="text" required value={taxCodeForm.name}
                                                onChange={(e) => setTaxCodeForm({ ...taxCodeForm, name: e.target.value })}
                                                placeholder="e.g. Output VAT 15%" className="glass-input"
                                                style={{ width: '100%', fontSize: 'var(--text-base)' }}
                                            />
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: '12px' }}>
                                            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', userSelect: 'none' }}>
                                                <div style={{
                                                    width: '24px', height: '24px', borderRadius: '6px',
                                                    border: '2px solid var(--primary)',
                                                    background: taxCodeForm.is_active ? 'var(--primary)' : 'transparent',
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                    transition: 'all 0.2s',
                                                }}>
                                                    {taxCodeForm.is_active && <Check size={16} color="white" strokeWidth={3} />}
                                                    <input type="checkbox" checked={taxCodeForm.is_active}
                                                        onChange={(e) => setTaxCodeForm({ ...taxCodeForm, is_active: e.target.checked })}
                                                        style={{ position: 'absolute', opacity: 0, cursor: 'pointer' }}
                                                    />
                                                </div>
                                                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>Active</span>
                                            </label>
                                        </div>
                                    </div>

                                    {/* Row 2: Type, Direction, Rate */}
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 140px', gap: '1.5rem', marginBottom: '1.5rem' }}>
                                        <div>
                                            <label style={labelStyle}>Tax Type<span className="required-mark"> *</span></label>
                                            <select value={taxCodeForm.tax_type}
                                                onChange={(e) => setTaxCodeForm({ ...taxCodeForm, tax_type: e.target.value })}
                                                required className="glass-input" style={{ width: '100%', fontSize: 'var(--text-sm)' }}
                                            >
                                                {TAX_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label style={labelStyle}>Direction<span className="required-mark"> *</span></label>
                                            <select value={taxCodeForm.direction}
                                                onChange={(e) => setTaxCodeForm({ ...taxCodeForm, direction: e.target.value })}
                                                required className="glass-input" style={{ width: '100%', fontSize: 'var(--text-sm)' }}
                                            >
                                                {DIRECTIONS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label style={labelStyle}>Rate (%)<span className="required-mark"> *</span></label>
                                            <div style={{ position: 'relative' }}>
                                                <input type="number" required step="0.01" min="0" max="100"
                                                    value={taxCodeForm.rate}
                                                    onChange={(e) => setTaxCodeForm({ ...taxCodeForm, rate: e.target.value })}
                                                    placeholder="7.50" className="glass-input"
                                                    style={{ width: '100%', fontSize: 'var(--text-base)', paddingRight: '2rem' }}
                                                />
                                                <span style={{
                                                    position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)',
                                                    fontSize: 'var(--text-sm)', color: 'var(--text-muted)', fontWeight: 600,
                                                }}>%</span>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Row 3: GL Account Integration */}
                                    <div style={{ background: 'rgba(79,70,229,0.04)', border: '1px solid rgba(79,70,229,0.15)', borderRadius: '10px', padding: '1.25rem', marginBottom: '1.5rem' }}>
                                        <p style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#4f46e5', marginBottom: '1rem' }}>
                                            GL Account Integration
                                        </p>
                                        <div style={{ display: 'grid', gridTemplateColumns: taxCodeForm.direction === 'both' ? '1fr 1fr' : '1fr', gap: '1rem' }}>
                                            {(taxCodeForm.direction === 'purchase' || taxCodeForm.direction === 'both') && (
                                                <div>
                                                    <label style={labelStyle}>Input Tax GL Account (Purchase)<span className="required-mark"> *</span></label>
                                                    <select value={taxCodeForm.input_tax_account}
                                                        onChange={(e) => setTaxCodeForm({ ...taxCodeForm, input_tax_account: e.target.value ? Number(e.target.value) : '' })}
                                                        className="glass-input" style={{ width: '100%', fontSize: 'var(--text-sm)' }}
                                                    >
                                                        <option value="">-- Select Input VAT Account --</option>
                                                        {(allAccounts || []).map(acc => (
                                                            <option key={acc.id} value={acc.id}>{acc.code} — {acc.name}</option>
                                                        ))}
                                                    </select>
                                                </div>
                                            )}
                                            {(taxCodeForm.direction === 'sales' || taxCodeForm.direction === 'both') && (
                                                <div>
                                                    <label style={labelStyle}>Output Tax GL Account (Sales)<span className="required-mark"> *</span></label>
                                                    <select value={taxCodeForm.output_tax_account}
                                                        onChange={(e) => setTaxCodeForm({ ...taxCodeForm, output_tax_account: e.target.value ? Number(e.target.value) : '' })}
                                                        className="glass-input" style={{ width: '100%', fontSize: 'var(--text-sm)' }}
                                                    >
                                                        <option value="">-- Select Output VAT Account --</option>
                                                        {(allAccounts || []).map(acc => (
                                                            <option key={acc.id} value={acc.id}>{acc.code} — {acc.name}</option>
                                                        ))}
                                                    </select>
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    {/* Row 3: Description */}
                                    <div style={{ marginBottom: '2rem' }}>
                                        <label style={labelStyle}>Description</label>
                                        <textarea value={taxCodeForm.description}
                                            onChange={(e) => setTaxCodeForm({ ...taxCodeForm, description: e.target.value })}
                                            placeholder="Optional description..." className="glass-input"
                                            rows={2} style={{ width: '100%', fontSize: 'var(--text-sm)', resize: 'vertical' }}
                                        />
                                    </div>

                                    {/* Actions */}
                                    <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
                                        <button className="btn-glass" onClick={() => { setShowTaxCodeForm(false); resetTaxCodeForm(); }} type="button" style={{ minWidth: '120px' }}>
                                            Discard
                                        </button>
                                        <button className="btn-primary ripple" type="submit"
                                            disabled={createTaxCode.isPending || updateTaxCode.isPending}
                                            style={{ minWidth: '160px' }}
                                        >
                                            {createTaxCode.isPending || updateTaxCode.isPending
                                                ? 'Processing...'
                                                : (editingTaxCode ? 'Save Changes' : 'Create Tax Code')}
                                        </button>
                                    </div>
                                </form>
                            </GlassCard>
                        </div>
                    )}

                    {/* Search */}
                    <GlassCard style={{ padding: '1.25rem', marginBottom: '1.5rem' }} className="animate-fade-in">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', background: 'rgba(255,255,255,0.05)', borderRadius: '10px', padding: '0 1rem' }}>
                            <Search size={20} style={{ color: 'var(--text-muted)' }} />
                            <input type="text" placeholder="Filter by code or name..."
                                value={taxCodeSearch} onChange={(e) => setTaxCodeSearch(e.target.value)}
                                style={{ flex: 1, border: 'none', background: 'transparent', padding: '0.75rem 0', color: 'var(--text-primary)', fontWeight: 500, outline: 'none' }}
                            />
                        </div>
                    </GlassCard>

                    {/* Tax Codes Table */}
                    <GlassCard style={{ padding: 0 }} className="animate-fade-in">
                        <table className="glass-table" style={{ width: '100%' }}>
                            <thead>
                                <tr>
                                    <th style={{ width: '10%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestTaxCodeSort('code')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Code {getTCSortIndicator('code')}</div>
                                    </th>
                                    <th style={{ width: '18%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestTaxCodeSort('name')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Name {getTCSortIndicator('name')}</div>
                                    </th>
                                    <th style={{ width: '12%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestTaxCodeSort('tax_type')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Type {getTCSortIndicator('tax_type')}</div>
                                    </th>
                                    <th style={{ width: '12%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestTaxCodeSort('direction')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Direction {getTCSortIndicator('direction')}</div>
                                    </th>
                                    <th style={{ width: '8%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestTaxCodeSort('rate')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Rate {getTCSortIndicator('rate')}</div>
                                    </th>
                                    <th style={{ width: '22%' }}>GL Account(s)</th>
                                    <th style={{ width: '8%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestTaxCodeSort('is_active')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Status {getTCSortIndicator('is_active')}</div>
                                    </th>
                                    <th style={{ width: '8%', textAlign: 'center' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sortedTaxCodes.map((tc: TaxCode, idx: number) => (
                                    <tr key={tc.id} className="stagger-item" style={{ animationDelay: `${idx * 0.03}s` }}>
                                        <td style={{ fontWeight: 700, color: 'var(--primary)', fontFamily: 'monospace', letterSpacing: '0.05em' }}>
                                            {tc.code}
                                        </td>
                                        <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{tc.name}</td>
                                        <td><span className="badge-glass" style={{ fontSize: 'var(--text-xs)' }}>{tc.tax_type_display}</span></td>
                                        <td><span className="badge-glass" style={{ fontSize: 'var(--text-xs)' }}>{tc.direction_display}</span></td>
                                        <td style={{ fontWeight: 700, fontFamily: 'monospace' }}>{parseFloat(tc.rate)}%</td>
                                        <td style={{ fontSize: 'var(--text-sm)' }}>
                                            {tc.direction === 'purchase' || tc.direction === 'both' ? (
                                                tc.input_tax_account_display
                                                    ? <div title={tc.input_tax_account_display.name} style={{ marginBottom: tc.direction === 'both' ? '4px' : 0 }}>
                                                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', display: 'block' }}>IN</span>
                                                        {tc.input_tax_account_display.code} — {tc.input_tax_account_display.name}
                                                      </div>
                                                    : <span style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>No input acct</span>
                                            ) : null}
                                            {tc.direction === 'sales' || tc.direction === 'both' ? (
                                                tc.output_tax_account_display
                                                    ? <div title={tc.output_tax_account_display.name}>
                                                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', display: 'block' }}>OUT</span>
                                                        {tc.output_tax_account_display.code} — {tc.output_tax_account_display.name}
                                                      </div>
                                                    : <span style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>No output acct</span>
                                            ) : null}
                                        </td>
                                        <td><StatusBadge status={tc.is_active ? 'Active' : 'Inactive'} /></td>
                                        <td>
                                            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
                                                <button onClick={() => handleEditTaxCode(tc)} className="btn-glass" style={{ padding: '6px 10px' }} title="Edit">
                                                    <Edit size={14} color="var(--primary)" />
                                                </button>
                                                <button onClick={() => handleDeleteTaxCode(tc.id, tc.name)} className="btn-glass" style={{ padding: '6px 10px' }} title="Delete">
                                                    <Trash2 size={14} color="#ef4444" />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>

                        {sortedTaxCodes.length === 0 && (
                            <div style={{ textAlign: 'center', padding: '6rem 2rem', color: 'var(--text-muted)' }}>
                                <div style={{
                                    width: '80px', height: '80px',
                                    background: 'rgba(36, 113, 163, 0.05)', borderRadius: '50%',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    margin: '0 auto 1.5rem',
                                }}>
                                    <Receipt size={40} style={{ opacity: 0.5 }} />
                                </div>
                                <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                                    No tax codes yet
                                </h3>
                                <p style={{ fontSize: 'var(--text-sm)' }}>
                                    {taxCodeSearch ? 'No tax codes match your search.' : 'Create your first tax code to manage VAT and sales tax rates.'}
                                </p>
                            </div>
                        )}
                    </GlassCard>
                </>
            )}

            {/* ═══════════════════════════════════════════════════════════
                WITHHOLDING TAX TAB
               ═══════════════════════════════════════════════════════════ */}
            {activeTab === 'wht' && (
                <>
                    {/* WHT Form */}
                    {showWHTForm && (
                        <div className="animate-slide-down" style={{ marginBottom: '2rem' }}>
                            <GlassCard gradient style={{ padding: '2rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                                    <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>
                                        {editingWHT ? 'Edit Withholding Tax' : 'Create New Withholding Tax'}
                                    </h2>
                                    <button onClick={() => { setShowWHTForm(false); resetWHTForm(); }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
                                        <X size={20} />
                                    </button>
                                </div>
                                <form onSubmit={handleWHTSubmit}>
                                    {/* Row 1: Code, Name, Active */}
                                    <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr auto', gap: '1.5rem', marginBottom: '1.5rem' }}>
                                        <div>
                                            <label style={labelStyle}>WHT Code<span className="required-mark"> *</span></label>
                                            <input type="text" required maxLength={20} value={whtForm.code}
                                                onChange={(e) => setWHTForm({ ...whtForm, code: e.target.value })}
                                                placeholder="e.g. WHT-01" className="glass-input"
                                                style={{ width: '100%', fontFamily: 'monospace', fontSize: 'var(--text-base)' }}
                                            />
                                        </div>
                                        <div>
                                            <label style={labelStyle}>Name<span className="required-mark"> *</span></label>
                                            <input type="text" required value={whtForm.name}
                                                onChange={(e) => setWHTForm({ ...whtForm, name: e.target.value })}
                                                placeholder="e.g. Professional Services WHT" className="glass-input"
                                                style={{ width: '100%', fontSize: 'var(--text-base)' }}
                                            />
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: '12px' }}>
                                            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', userSelect: 'none' }}>
                                                <div style={{
                                                    width: '24px', height: '24px', borderRadius: '6px',
                                                    border: '2px solid var(--primary)',
                                                    background: whtForm.is_active ? 'var(--primary)' : 'transparent',
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                    transition: 'all 0.2s',
                                                }}>
                                                    {whtForm.is_active && <Check size={16} color="white" strokeWidth={3} />}
                                                    <input type="checkbox" checked={whtForm.is_active}
                                                        onChange={(e) => setWHTForm({ ...whtForm, is_active: e.target.checked })}
                                                        style={{ position: 'absolute', opacity: 0, cursor: 'pointer' }}
                                                    />
                                                </div>
                                                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>Active</span>
                                            </label>
                                        </div>
                                    </div>

                                    {/* Row 2: Income Type, Rate, GL Account */}
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 140px 1fr', gap: '1.5rem', marginBottom: '2rem' }}>
                                        <div>
                                            <label style={labelStyle}>Income Type<span className="required-mark"> *</span></label>
                                            <input type="text" required value={whtForm.income_type}
                                                onChange={(e) => setWHTForm({ ...whtForm, income_type: e.target.value })}
                                                placeholder="e.g. Professional Services" className="glass-input"
                                                style={{ width: '100%', fontSize: 'var(--text-sm)' }}
                                            />
                                        </div>
                                        <div>
                                            <label style={labelStyle}>Rate (%)<span className="required-mark"> *</span></label>
                                            <div style={{ position: 'relative' }}>
                                                <input type="number" required step="0.01" min="0" max="100"
                                                    value={whtForm.rate}
                                                    onChange={(e) => setWHTForm({ ...whtForm, rate: e.target.value })}
                                                    placeholder="5.00" className="glass-input"
                                                    style={{ width: '100%', fontSize: 'var(--text-base)', paddingRight: '2rem' }}
                                                />
                                                <span style={{
                                                    position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)',
                                                    fontSize: 'var(--text-sm)', color: 'var(--text-muted)', fontWeight: 600,
                                                }}>%</span>
                                            </div>
                                        </div>
                                        <div>
                                            <label style={labelStyle}>Withholding GL Account</label>
                                            <select value={whtForm.withholding_account}
                                                onChange={(e) => setWHTForm({ ...whtForm, withholding_account: e.target.value ? Number(e.target.value) : '' })}
                                                className="glass-input" style={{ width: '100%', fontSize: 'var(--text-sm)' }}
                                            >
                                                <option value="">-- Select Liability GL --</option>
                                                {(liabilityAccounts || []).map(acc => (
                                                    <option key={acc.id} value={acc.id}>{acc.code} — {acc.name}</option>
                                                ))}
                                            </select>
                                        </div>
                                    </div>

                                    {/* Actions */}
                                    <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
                                        <button className="btn-glass" onClick={() => { setShowWHTForm(false); resetWHTForm(); }} type="button" style={{ minWidth: '120px' }}>
                                            Discard
                                        </button>
                                        <button className="btn-primary ripple" type="submit"
                                            disabled={createWHT.isPending || updateWHT.isPending}
                                            style={{ minWidth: '160px' }}
                                        >
                                            {createWHT.isPending || updateWHT.isPending
                                                ? 'Processing...'
                                                : (editingWHT ? 'Save Changes' : 'Create WHT Code')}
                                        </button>
                                    </div>
                                </form>
                            </GlassCard>
                        </div>
                    )}

                    {/* Search */}
                    <GlassCard style={{ padding: '1.25rem', marginBottom: '1.5rem' }} className="animate-fade-in">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', background: 'rgba(255,255,255,0.05)', borderRadius: '10px', padding: '0 1rem' }}>
                            <Search size={20} style={{ color: 'var(--text-muted)' }} />
                            <input type="text" placeholder="Filter by code or name..."
                                value={whtSearch} onChange={(e) => setWHTSearch(e.target.value)}
                                style={{ flex: 1, border: 'none', background: 'transparent', padding: '0.75rem 0', color: 'var(--text-primary)', fontWeight: 500, outline: 'none' }}
                            />
                        </div>
                    </GlassCard>

                    {/* WHT Table */}
                    <GlassCard style={{ padding: 0 }} className="animate-fade-in">
                        <table className="glass-table" style={{ width: '100%' }}>
                            <thead>
                                <tr>
                                    <th style={{ width: '12%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestWHTSort('code')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Code {getWHTSortIndicator('code')}</div>
                                    </th>
                                    <th style={{ width: '20%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestWHTSort('name')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Name {getWHTSortIndicator('name')}</div>
                                    </th>
                                    <th style={{ width: '18%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestWHTSort('income_type')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Income Type {getWHTSortIndicator('income_type')}</div>
                                    </th>
                                    <th style={{ width: '10%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestWHTSort('rate')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Rate {getWHTSortIndicator('rate')}</div>
                                    </th>
                                    <th style={{ width: '20%' }}>GL Account</th>
                                    <th style={{ width: '10%', cursor: 'pointer', userSelect: 'none' }} onClick={() => requestWHTSort('is_active')}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>Status {getWHTSortIndicator('is_active')}</div>
                                    </th>
                                    <th style={{ width: '10%', textAlign: 'center' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sortedWHT.map((w: WithholdingTax, idx: number) => (
                                    <tr key={w.id} className="stagger-item" style={{ animationDelay: `${idx * 0.03}s` }}>
                                        <td style={{ fontWeight: 700, color: 'var(--primary)', fontFamily: 'monospace', letterSpacing: '0.05em' }}>
                                            {w.code}
                                        </td>
                                        <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{w.name}</td>
                                        <td><span className="badge-glass" style={{ fontSize: 'var(--text-xs)' }}>{w.income_type}</span></td>
                                        <td style={{ fontWeight: 700, fontFamily: 'monospace' }}>{parseFloat(w.rate)}%</td>
                                        <td style={{ fontSize: 'var(--text-sm)' }}>
                                            {w.withholding_account_display
                                                ? <span title={w.withholding_account_display.name}>{w.withholding_account_display.code} — {w.withholding_account_display.name}</span>
                                                : <span style={{ color: 'var(--text-muted)' }}>--</span>}
                                        </td>
                                        <td><StatusBadge status={w.is_active ? 'Active' : 'Inactive'} /></td>
                                        <td>
                                            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
                                                <button onClick={() => handleEditWHT(w)} className="btn-glass" style={{ padding: '6px 10px' }} title="Edit">
                                                    <Edit size={14} color="var(--primary)" />
                                                </button>
                                                <button onClick={() => handleDeleteWHT(w.id, w.name)} className="btn-glass" style={{ padding: '6px 10px' }} title="Delete">
                                                    <Trash2 size={14} color="#ef4444" />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>

                        {sortedWHT.length === 0 && (
                            <div style={{ textAlign: 'center', padding: '6rem 2rem', color: 'var(--text-muted)' }}>
                                <div style={{
                                    width: '80px', height: '80px',
                                    background: 'rgba(36, 113, 163, 0.05)', borderRadius: '50%',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    margin: '0 auto 1.5rem',
                                }}>
                                    <ShieldCheck size={40} style={{ opacity: 0.5 }} />
                                </div>
                                <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                                    No withholding tax codes yet
                                </h3>
                                <p style={{ fontSize: 'var(--text-sm)' }}>
                                    {whtSearch ? 'No WHT codes match your search.' : 'Create your first withholding tax code to configure tax deductions.'}
                                </p>
                            </div>
                        )}
                    </GlassCard>
                </>
            )}
        </SettingsLayout>
    );
}
