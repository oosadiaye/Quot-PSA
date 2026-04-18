/**
 * FixedAssetForm — create a new government fixed asset.
 *
 * Flow:
 *   1. User picks asset_category (Building / Vehicle / IT etc.)
 *   2. User picks MDA + Fund (required for budget control)
 *   3. Cost + useful life + depreciation method
 *   4. Optional: NCoA dims, optional GL account overrides
 *
 * Backend notes (see accounting.models.assets.FixedAsset):
 *   · asset_category is a CharField enum, not an FK to the AssetCategory table
 *   · mda + fund are enforced required when the `dimensions` feature flag is on
 *   · Blank asset_account / dep_expense / accum_depr fallback to the matching
 *     AssetCategory.cost_account / depreciation_expense_account /
 *     accumulated_depreciation_account on the server (clean defaults)
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, X } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import { useCreateFixedAsset } from '../hooks/useAccountingEnhancements';
import type { FixedAssetFormData } from '../hooks/useAccountingEnhancements';
import { useMDAs, useAccounts } from '../hooks/useBudgetDimensions';
import { useFunds, useFunctions, usePrograms, useGeos } from '../hooks/useDimensions';

const ASSET_CATEGORIES = [
    { value: 'Building',  label: 'Building' },
    { value: 'Equipment', label: 'Equipment' },
    { value: 'Vehicle',   label: 'Vehicle' },
    { value: 'IT',        label: 'IT Equipment' },
    { value: 'Furniture', label: 'Furniture' },
    { value: 'Land',      label: 'Land' },
];

const DEPR_METHODS = [
    { value: 'Straight-Line',      label: 'Straight-Line' },
    { value: 'Declining Balance',  label: 'Declining Balance' },
];

const initialForm: FixedAssetFormData = {
    asset_number: '',
    name: '',
    description: '',
    asset_category: 'Equipment',
    acquisition_date: new Date().toISOString().slice(0, 10),
    acquisition_cost: '',
    salvage_value: '0',
    useful_life_years: 5,
    depreciation_method: 'Straight-Line',
    mda: null,
    fund: null,
    function: null,
    program: null,
    geo: null,
    asset_account: null,
    depreciation_expense_account: null,
    accumulated_depreciation_account: null,
    status: 'Active',
};

const label: React.CSSProperties = {
    fontSize: 12, fontWeight: 600, color: '#475569',
    textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 6,
    display: 'block',
};

const inputBase: React.CSSProperties = {
    width: '100%', padding: '10px 12px', fontSize: 14,
    borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff',
    outline: 'none', transition: 'border-color 150ms ease, box-shadow 150ms ease',
};

const fieldErr: React.CSSProperties = { color: '#dc2626', fontSize: 12, marginTop: 4 };

export default function FixedAssetForm() {
    const navigate = useNavigate();
    const createAsset = useCreateFixedAsset();

    const [form, setForm] = useState<FixedAssetFormData>(initialForm);
    const [formErrors, setFormErrors] = useState<Record<string, string>>({});
    const [submitError, setSubmitError] = useState<string>('');

    // Dimension dropdowns
    const { data: mdas = [] } = useMDAs({ is_active: true });
    const { data: funds = [] } = useFunds();
    const { data: functionsList = [] } = useFunctions();
    const { data: programs = [] } = usePrograms();
    const { data: geos = [] } = useGeos();
    // Asset GL accounts (optional overrides)
    const { data: assetAccounts = [] } = useAccounts({ account_type: 'Asset', is_active: true });
    const { data: expenseAccounts = [] } = useAccounts({ account_type: 'Expense', is_active: true });

    const setField = <K extends keyof FixedAssetFormData>(key: K, value: FixedAssetFormData[K]) => {
        setForm(prev => ({ ...prev, [key]: value }));
        if (formErrors[key as string]) {
            setFormErrors(prev => { const { [key as string]: _, ...rest } = prev; return rest; });
        }
    };

    const validate = (): boolean => {
        const errs: Record<string, string> = {};
        if (!form.asset_number.trim()) errs.asset_number = 'Asset number is required.';
        if (!form.name.trim()) errs.name = 'Name is required.';
        if (!form.asset_category) errs.asset_category = 'Category is required.';
        if (!form.acquisition_date) errs.acquisition_date = 'Acquisition date is required.';
        const cost = Number(form.acquisition_cost);
        if (!form.acquisition_cost || isNaN(cost) || cost <= 0) {
            errs.acquisition_cost = 'Acquisition cost must be greater than zero.';
        }
        if (!form.useful_life_years || form.useful_life_years <= 0) {
            errs.useful_life_years = 'Useful life (years) is required.';
        }
        setFormErrors(errs);
        return Object.keys(errs).length === 0;
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setSubmitError('');
        if (!validate()) return;

        // Strip nullish keys so Django doesn't choke on empty-string numeric FKs
        const payload = Object.fromEntries(
            Object.entries(form).filter(([, v]) => v !== '' && v !== null && v !== undefined)
        ) as unknown as FixedAssetFormData;

        try {
            await createAsset.mutateAsync(payload);
            navigate('/accounting/fixed-assets');
        } catch (err: any) {
            const resp = err?.response?.data;
            if (resp && typeof resp === 'object') {
                // Map field-level DRF errors back onto formErrors
                const mapped: Record<string, string> = {};
                for (const [k, v] of Object.entries(resp)) {
                    mapped[k] = Array.isArray(v) ? String(v[0]) : String(v);
                }
                setFormErrors(mapped);
                setSubmitError(mapped.detail || 'Validation failed — see highlighted fields.');
            } else {
                setSubmitError(err?.message || 'Failed to create asset.');
            }
        }
    };

    return (
        <div style={{ background: '#f5f7fb', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '32px' }}>
                <PageHeader
                    title="New Fixed Asset"
                    subtitle="Register a new government asset in the IPSAS-compliant register"
                    onBack={() => navigate('/accounting/fixed-assets')}
                    actions={
                        <button
                            type="button"
                            onClick={() => navigate('/accounting/fixed-assets')}
                            className="btn btn-outline"
                            style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(255,255,255,0.12)', color: '#fff', border: '1px solid rgba(255,255,255,0.25)' }}
                        >
                            <ArrowLeft size={16} /> Back to Register
                        </button>
                    }
                />

                <form onSubmit={handleSubmit} style={{ maxWidth: 920 }}>
                    {submitError && (
                        <div style={{
                            padding: '12px 16px', borderRadius: 8, marginBottom: 20,
                            background: '#fee2e2', border: '1px solid #fca5a5', color: '#991b1b',
                            fontSize: 14,
                        }}>
                            {submitError}
                        </div>
                    )}

                    {/* ── Identification ──────────────────────── */}
                    <section style={sectionStyle}>
                        <h3 style={sectionTitle}>Identification</h3>
                        <div style={gridStyle}>
                            <div>
                                <label style={label}>Asset Number *</label>
                                <input
                                    style={inputBase}
                                    value={form.asset_number}
                                    onChange={e => setField('asset_number', e.target.value)}
                                    placeholder="FA-2026-0001"
                                />
                                {formErrors.asset_number && <div style={fieldErr}>{formErrors.asset_number}</div>}
                            </div>
                            <div>
                                <label style={label}>Asset Name *</label>
                                <input
                                    style={inputBase}
                                    value={form.name}
                                    onChange={e => setField('name', e.target.value)}
                                    placeholder="Toyota Hilux 2026"
                                />
                                {formErrors.name && <div style={fieldErr}>{formErrors.name}</div>}
                            </div>
                            <div>
                                <label style={label}>Category *</label>
                                <select
                                    style={inputBase}
                                    value={form.asset_category}
                                    onChange={e => setField('asset_category', e.target.value)}
                                >
                                    {ASSET_CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                                </select>
                                {formErrors.asset_category && <div style={fieldErr}>{formErrors.asset_category}</div>}
                            </div>
                            <div>
                                <label style={label}>Status</label>
                                <select
                                    style={inputBase}
                                    value={form.status || 'Active'}
                                    onChange={e => setField('status', e.target.value)}
                                >
                                    <option value="Active">Active</option>
                                    <option value="Disposed">Disposed</option>
                                    <option value="Retired">Retired</option>
                                </select>
                            </div>
                        </div>
                        <div style={{ marginTop: 16 }}>
                            <label style={label}>Description</label>
                            <textarea
                                style={{ ...inputBase, minHeight: 72, fontFamily: 'inherit' }}
                                value={form.description || ''}
                                onChange={e => setField('description', e.target.value)}
                                placeholder="Asset notes / serial number / chassis, etc."
                            />
                        </div>
                    </section>

                    {/* ── Acquisition & Depreciation ────────── */}
                    <section style={sectionStyle}>
                        <h3 style={sectionTitle}>Acquisition &amp; Depreciation</h3>
                        <div style={gridStyle}>
                            <div>
                                <label style={label}>Acquisition Date *</label>
                                <input
                                    type="date"
                                    style={inputBase}
                                    value={form.acquisition_date}
                                    onChange={e => setField('acquisition_date', e.target.value)}
                                />
                                {formErrors.acquisition_date && <div style={fieldErr}>{formErrors.acquisition_date}</div>}
                            </div>
                            <div>
                                <label style={label}>Acquisition Cost (₦) *</label>
                                <input
                                    type="number" step="0.01" min="0"
                                    style={inputBase}
                                    value={form.acquisition_cost}
                                    onChange={e => setField('acquisition_cost', e.target.value)}
                                    placeholder="0.00"
                                />
                                {formErrors.acquisition_cost && <div style={fieldErr}>{formErrors.acquisition_cost}</div>}
                            </div>
                            <div>
                                <label style={label}>Salvage Value (₦)</label>
                                <input
                                    type="number" step="0.01" min="0"
                                    style={inputBase}
                                    value={form.salvage_value || ''}
                                    onChange={e => setField('salvage_value', e.target.value)}
                                    placeholder="0.00"
                                />
                            </div>
                            <div>
                                <label style={label}>Useful Life (years) *</label>
                                <input
                                    type="number" min="1" step="1"
                                    style={inputBase}
                                    value={form.useful_life_years}
                                    onChange={e => setField('useful_life_years', Number(e.target.value))}
                                />
                                {formErrors.useful_life_years && <div style={fieldErr}>{formErrors.useful_life_years}</div>}
                            </div>
                            <div>
                                <label style={label}>Depreciation Method *</label>
                                <select
                                    style={inputBase}
                                    value={form.depreciation_method}
                                    onChange={e => setField('depreciation_method', e.target.value)}
                                >
                                    {DEPR_METHODS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                                </select>
                            </div>
                        </div>
                    </section>

                    {/* ── Dimensions ────────────────────────── */}
                    <section style={sectionStyle}>
                        <h3 style={sectionTitle}>Budget Dimensions</h3>
                        <p style={{ fontSize: 13, color: '#64748b', marginTop: 0, marginBottom: 16 }}>
                            Required for government accounting — every asset must be coded to an MDA and Fund
                            source so IPSAS reports can attribute it correctly.
                        </p>
                        <div style={gridStyle}>
                            <div>
                                <label style={label}>MDA *</label>
                                <select
                                    style={inputBase}
                                    value={form.mda ?? ''}
                                    onChange={e => setField('mda', e.target.value ? Number(e.target.value) : null)}
                                >
                                    <option value="">Select MDA…</option>
                                    {(mdas as any[]).map((m: any) => (
                                        <option key={m.id} value={m.id}>{m.code ? `${m.code} — ${m.name}` : m.name}</option>
                                    ))}
                                </select>
                                {formErrors.mda && <div style={fieldErr}>{formErrors.mda}</div>}
                            </div>
                            <div>
                                <label style={label}>Fund *</label>
                                <select
                                    style={inputBase}
                                    value={form.fund ?? ''}
                                    onChange={e => setField('fund', e.target.value ? Number(e.target.value) : null)}
                                >
                                    <option value="">Select Fund…</option>
                                    {(funds as any[]).map((f: any) => (
                                        <option key={f.id} value={f.id}>{f.code ? `${f.code} — ${f.name}` : f.name}</option>
                                    ))}
                                </select>
                                {formErrors.fund && <div style={fieldErr}>{formErrors.fund}</div>}
                            </div>
                            <div>
                                <label style={label}>Function (COFOG)</label>
                                <select
                                    style={inputBase}
                                    value={form.function ?? ''}
                                    onChange={e => setField('function', e.target.value ? Number(e.target.value) : null)}
                                >
                                    <option value="">—</option>
                                    {(functionsList as any[]).map((fn: any) => (
                                        <option key={fn.id} value={fn.id}>{fn.code ? `${fn.code} — ${fn.name}` : fn.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label style={label}>Programme</label>
                                <select
                                    style={inputBase}
                                    value={form.program ?? ''}
                                    onChange={e => setField('program', e.target.value ? Number(e.target.value) : null)}
                                >
                                    <option value="">—</option>
                                    {(programs as any[]).map((p: any) => (
                                        <option key={p.id} value={p.id}>{p.code ? `${p.code} — ${p.name}` : p.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label style={label}>Geographic</label>
                                <select
                                    style={inputBase}
                                    value={form.geo ?? ''}
                                    onChange={e => setField('geo', e.target.value ? Number(e.target.value) : null)}
                                >
                                    <option value="">—</option>
                                    {(geos as any[]).map((g: any) => (
                                        <option key={g.id} value={g.id}>{g.code ? `${g.code} — ${g.name}` : g.name}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    </section>

                    {/* ── GL Account Overrides ──────────────── */}
                    <section style={sectionStyle}>
                        <h3 style={sectionTitle}>GL Account Overrides <span style={{ fontSize: 12, fontWeight: 500, color: '#64748b' }}>(optional — defaults pulled from Asset Category)</span></h3>
                        <div style={gridStyle}>
                            <div>
                                <label style={label}>Asset Account</label>
                                <select
                                    style={inputBase}
                                    value={form.asset_account ?? ''}
                                    onChange={e => setField('asset_account', e.target.value ? Number(e.target.value) : null)}
                                >
                                    <option value="">Use Category default</option>
                                    {(assetAccounts as any[]).map((a: any) => (
                                        <option key={a.id} value={a.id}>{a.code} — {a.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label style={label}>Accumulated Depreciation Account</label>
                                <select
                                    style={inputBase}
                                    value={form.accumulated_depreciation_account ?? ''}
                                    onChange={e => setField('accumulated_depreciation_account', e.target.value ? Number(e.target.value) : null)}
                                >
                                    <option value="">Use Category default</option>
                                    {(assetAccounts as any[]).map((a: any) => (
                                        <option key={a.id} value={a.id}>{a.code} — {a.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label style={label}>Depreciation Expense Account</label>
                                <select
                                    style={inputBase}
                                    value={form.depreciation_expense_account ?? ''}
                                    onChange={e => setField('depreciation_expense_account', e.target.value ? Number(e.target.value) : null)}
                                >
                                    <option value="">Use Category default</option>
                                    {(expenseAccounts as any[]).map((a: any) => (
                                        <option key={a.id} value={a.id}>{a.code} — {a.name}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    </section>

                    {/* ── Action bar ────────────────────────── */}
                    <div style={{
                        display: 'flex', justifyContent: 'flex-end', gap: 10,
                        padding: '16px 0', borderTop: '1px solid #e2e8f0', marginTop: 8,
                    }}>
                        <button
                            type="button"
                            onClick={() => navigate('/accounting/fixed-assets')}
                            className="btn btn-outline"
                            style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                        >
                            <X size={16} /> Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={createAsset.isPending}
                            className="btn btn-primary"
                            style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                        >
                            <Save size={16} />
                            {createAsset.isPending ? 'Saving…' : 'Save Asset'}
                        </button>
                    </div>
                </form>
            </main>
        </div>
    );
}

const sectionStyle: React.CSSProperties = {
    background: '#fff', borderRadius: 12, padding: '20px 24px',
    border: '1px solid #e2e8f0', marginBottom: 20,
};

const sectionTitle: React.CSSProperties = {
    margin: '0 0 16px', fontSize: 16, fontWeight: 700, color: '#0f172a',
};

const gridStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
    gap: 16,
};
