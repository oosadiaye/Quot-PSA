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
import { useQuery } from '@tanstack/react-query';
import apiClient from '../../../api/client';

/**
 * Fetch active asset categories from the tenant's ``AssetCategory``
 * table. Replaces the previous hardcoded 6-value enum so tenants can
 * maintain their own category taxonomy via
 * ``/accounting/asset-categories/`` instead of being limited to
 * Building / Equipment / Vehicle / IT / Furniture / Land.
 */
interface AccountDisplay {
    id: number;
    code: string;
    name: string;
}

interface AssetCategoryLite {
    id: number;
    code: string;
    name: string;
    depreciation_method?: string;
    default_life_years?: number;
    residual_value_type?: 'percentage' | 'amount';
    residual_value?: string | number;
    // GL account defaults for the category — the asset inherits these
    // on posting. Returned as either the raw FK id OR the
    // ``*_display`` nested object ({id, code, name}) from the
    // AssetCategorySerializer.
    cost_account?: number | null;
    accumulated_depreciation_account?: number | null;
    depreciation_expense_account?: number | null;
    cost_account_display?: AccountDisplay | null;
    accumulated_depreciation_account_display?: AccountDisplay | null;
    depreciation_expense_account_display?: AccountDisplay | null;
}

function useAssetCategories() {
    return useQuery<AssetCategoryLite[]>({
        queryKey: ['asset-categories'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/asset-categories/', {
                params: { is_active: true, page_size: 9999 },
            });
            return Array.isArray(data) ? data : (data?.results || []);
        },
        staleTime: 5 * 60 * 1000,
    });
}

// DEPR_METHODS removed — depreciation method is no longer entered
// per-asset; it's inherited from the selected Asset Category.

const initialForm: FixedAssetFormData = {
    asset_number: '',
    name: '',
    description: '',
    // Default empty — the user picks from the live AssetCategory list.
    // No hardcoded seed so a tenant with a custom taxonomy isn't
    // pre-pushed toward a category they don't use.
    asset_category: '',
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
    // Live asset categories — replaces the previous hardcoded enum
    const { data: assetCategories = [], isLoading: catsLoading } = useAssetCategories();

    const setField = <K extends keyof FixedAssetFormData>(key: K, value: FixedAssetFormData[K]) => {
        setForm(prev => ({ ...prev, [key]: value }));
        if (formErrors[key as string]) {
            setFormErrors(prev => { const { [key as string]: _, ...rest } = prev; return rest; });
        }
    };

    const validate = (): boolean => {
        const errs: Record<string, string> = {};
        // asset_number is now optional — backend auto-generates
        // FA-YYYY-NNNNN when the field is blank (see
        // FixedAsset._generate_asset_number). Users can still type
        // their own legacy tag number when migrating a pre-existing
        // asset register.
        if (!form.name.trim()) errs.name = 'Name is required.';
        if (!form.asset_category) {
            errs.asset_category = assetCategories.length === 0
                ? 'No asset categories defined — add one in Asset Settings.'
                : 'Category is required.';
        }
        if (!form.acquisition_date) errs.acquisition_date = 'Acquisition date is required.';
        // Acquisition cost, useful life, salvage value and depreciation
        // method are intentionally NOT validated here:
        //   - acquisition_cost: set by the vendor invoice / PO invoice
        //     verification when it posts to GL and debits this asset's
        //     account (avoids double-entry with the source doc).
        //   - depreciation fields: inherited from the selected Asset
        //     Category (single source of truth for category policy).
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
            const created: any = await createAsset.mutateAsync(payload);
            // Server-side BudgetCheckRule warnings (WARNING level +
            // no appropriation yet) come back as budget_warnings. Show
            // them before leaving the page so the user knows the
            // dimension tuple was accepted but isn't under an active
            // appropriation — the expenditure posting step will still
            // enforce the rule at invoice verification.
            const warnings: string[] = Array.isArray(created?.budget_warnings)
                ? created.budget_warnings
                : [];
            if (warnings.length > 0) {
                alert(
                    'Asset saved with budget warnings:\n\n' +
                    warnings.map((w) => '• ' + w).join('\n')
                );
            }
            navigate('/accounting/fixed-assets');
        } catch (err: any) {
            const resp = err?.response?.data;
            if (resp && typeof resp === 'object') {
                // STRICT budget block returns a structured envelope
                // from the serializer ({ non_field_errors, code,
                // mda_code, fund_code, economic_code }). Promote the
                // reason to the top-level error banner with the
                // offending tuple so the user knows exactly which
                // dimension combination failed.
                const bucket = Array.isArray(resp.non_field_errors)
                    ? resp.non_field_errors[0]
                    : resp.non_field_errors;
                if (bucket && resp.code === 'BUDGET_STRICT_BLOCK') {
                    const tuple = [resp.mda_code, resp.economic_code, resp.fund_code]
                        .filter(Boolean).join('/');
                    setSubmitError(
                        `Budget check failed${tuple ? ` for ${tuple}` : ''}: ${bucket}`
                    );
                    return;
                }
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
                                <label style={label}>
                                    Asset Number
                                    <span style={{ marginLeft: 6, fontSize: 11, fontWeight: 500, color: 'var(--color-text-muted)' }}>
                                        (auto-generated — leave blank)
                                    </span>
                                </label>
                                <input
                                    style={inputBase}
                                    value={form.asset_number}
                                    onChange={e => setField('asset_number', e.target.value)}
                                    placeholder="Leave blank: FA-2026-00001 will be allocated on save"
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
                                <label style={label}>
                                    Category *
                                    {catsLoading && (
                                        <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--color-text-muted)' }}>
                                            loading…
                                        </span>
                                    )}
                                </label>
                                <select
                                    style={inputBase}
                                    value={form.asset_category}
                                    onChange={e => setField('asset_category', e.target.value)}
                                >
                                    <option value="">
                                        {assetCategories.length === 0 && !catsLoading
                                            ? 'No categories defined — add one in Asset Settings'
                                            : 'Select category…'}
                                    </option>
                                    {assetCategories.map((c) => (
                                        <option key={c.id} value={c.code || c.name}>
                                            {c.code ? `${c.code} — ${c.name}` : c.name}
                                        </option>
                                    ))}
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
                            {/* Acquisition cost is INTENTIONALLY not shown
                                here — it is set automatically when the
                                vendor invoice / PO invoice verification
                                posts a DR to this asset's GL account.
                                Capturing it on the asset form would lead
                                to double-entry and drift between asset
                                register and GL. See FixedAsset.acquisition_cost. */}
                            <div style={{
                                gridColumn: 'span 1',
                                padding: '10px 12px',
                                borderRadius: 8,
                                background: 'rgba(59,130,246,0.06)',
                                border: '1px solid rgba(59,130,246,0.2)',
                                fontSize: 12,
                                color: '#1e40af',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 8,
                            }}>
                                <span style={{ fontWeight: 700 }}>ℹ</span>
                                <div>
                                    <b>Cost is set on posting.</b> The asset's
                                    acquisition cost will be populated from the
                                    AP Vendor Invoice or PO Invoice Verification
                                    when that document posts and debits this
                                    asset's GL account.
                                </div>
                            </div>
                            {/* Depreciation policy — read-only display of
                                the settings the backend will apply. Pulled
                                live from the selected AssetCategory so users
                                can verify the policy before they save. */}
                            {(() => {
                                const selectedCat = assetCategories.find(
                                    (c) => (c.code || c.name) === form.asset_category
                                );
                                const dmColor = selectedCat ? '#1e40af' : '#94a3b8';
                                const bg = selectedCat ? 'rgba(59,130,246,0.06)' : 'rgba(148,163,184,0.1)';
                                const border = selectedCat ? 'rgba(59,130,246,0.25)' : 'rgba(148,163,184,0.25)';
                                const residualDisplay = selectedCat
                                    ? (selectedCat.residual_value_type === 'percentage'
                                        ? `${Number(selectedCat.residual_value || 0).toFixed(2)}% of cost`
                                        : `NGN ${Number(selectedCat.residual_value || 0).toLocaleString('en-NG', { minimumFractionDigits: 2 })}`)
                                    : '—';
                                return (
                                    <div style={{
                                        gridColumn: 'span 2',
                                        padding: '12px 14px',
                                        borderRadius: 10,
                                        background: bg,
                                        border: `1px solid ${border}`,
                                    }}>
                                        <div style={{
                                            fontSize: 11, fontWeight: 700,
                                            color: dmColor, marginBottom: 8,
                                            textTransform: 'uppercase', letterSpacing: '0.04em',
                                        }}>
                                            Depreciation policy (from category)
                                        </div>
                                        <div style={{
                                            display: 'grid',
                                            gridTemplateColumns: 'repeat(3, 1fr)',
                                            gap: 12,
                                        }}>
                                            <div>
                                                <div style={{ fontSize: 10, color: '#64748b', fontWeight: 600 }}>METHOD</div>
                                                <div style={{ fontSize: 13, color: '#1e293b', fontWeight: 600 }}>
                                                    {selectedCat?.depreciation_method || '—'}
                                                </div>
                                            </div>
                                            <div>
                                                <div style={{ fontSize: 10, color: '#64748b', fontWeight: 600 }}>USEFUL LIFE</div>
                                                <div style={{ fontSize: 13, color: '#1e293b', fontWeight: 600 }}>
                                                    {selectedCat?.default_life_years
                                                        ? `${selectedCat.default_life_years} year${selectedCat.default_life_years === 1 ? '' : 's'}`
                                                        : '—'}
                                                </div>
                                            </div>
                                            <div>
                                                <div style={{ fontSize: 10, color: '#64748b', fontWeight: 600 }}>RESIDUAL</div>
                                                <div style={{ fontSize: 13, color: '#1e293b', fontWeight: 600 }}>
                                                    {residualDisplay}
                                                </div>
                                            </div>
                                        </div>
                                        {!selectedCat && (
                                            <div style={{
                                                marginTop: 8, fontSize: 11, color: '#94a3b8',
                                            }}>
                                                Select a category above to see the depreciation policy
                                                that will be applied on posting.
                                            </div>
                                        )}
                                        {selectedCat && (
                                            <div style={{
                                                marginTop: 8, fontSize: 11, color: '#64748b',
                                            }}>
                                                These values are inherited when the asset saves. To
                                                change them for this category, edit the Asset Category
                                                in <i>Settings → Asset Categories</i>.
                                            </div>
                                        )}
                                    </div>
                                );
                            })()}
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

                    {/* ── GL Account Display ────────────────── */}
                    {/* Read-only view of the three GL accounts inherited
                        from the selected Asset Category. Previously this
                        was a set of override dropdowns — which risked
                        asset-level drift from the category's account
                        policy. Making it display-only enforces the
                        single-source-of-truth on the category and lets
                        auditors trust that every asset under a category
                        hits the same accounts. */}
                    <section style={sectionStyle}>
                        <h3 style={sectionTitle}>
                            GL Account Display
                            <span style={{ fontSize: 12, fontWeight: 500, color: '#64748b' }}>
                                {' '}(inherited from the selected Asset Category)
                            </span>
                        </h3>
                        {(() => {
                            const selectedCat = assetCategories.find(
                                (c) => (c.code || c.name) === form.asset_category,
                            );
                            // Prefer the server's _display payload (nested
                            // {id, code, name}); fall back to looking up by
                            // id in the already-fetched account arrays.
                            const resolve = (
                                display: AccountDisplay | null | undefined,
                                fkId: number | null | undefined,
                                pool: Array<any>,
                            ): AccountDisplay | null => {
                                if (display && display.code) return display;
                                if (fkId) {
                                    const hit = pool.find((p) => p.id === fkId);
                                    if (hit) return { id: hit.id, code: hit.code, name: hit.name };
                                }
                                return null;
                            };
                            const costAcc = selectedCat ? resolve(
                                selectedCat.cost_account_display,
                                selectedCat.cost_account,
                                assetAccounts as any[],
                            ) : null;
                            const accAccDep = selectedCat ? resolve(
                                selectedCat.accumulated_depreciation_account_display,
                                selectedCat.accumulated_depreciation_account,
                                assetAccounts as any[],
                            ) : null;
                            const depExpAcc = selectedCat ? resolve(
                                selectedCat.depreciation_expense_account_display,
                                selectedCat.depreciation_expense_account,
                                expenseAccounts as any[],
                            ) : null;

                            const DisplayCard = ({
                                title, acc,
                            }: { title: string; acc: AccountDisplay | null }) => (
                                <div style={{
                                    padding: '12px 14px',
                                    borderRadius: 8,
                                    background: acc ? '#f8fafc' : 'rgba(148,163,184,0.08)',
                                    border: '1px solid var(--color-border, #e2e8f0)',
                                }}>
                                    <div style={{
                                        fontSize: 10, fontWeight: 700,
                                        color: '#64748b', textTransform: 'uppercase',
                                        letterSpacing: '0.04em', marginBottom: 4,
                                    }}>
                                        {title}
                                    </div>
                                    {acc ? (
                                        <>
                                            <div style={{
                                                fontSize: 13, fontWeight: 700,
                                                color: '#4f46e5', fontFamily: 'monospace',
                                            }}>
                                                {acc.code}
                                            </div>
                                            <div style={{ fontSize: 12, color: '#1e293b', marginTop: 2 }}>
                                                {acc.name}
                                            </div>
                                        </>
                                    ) : (
                                        <div style={{
                                            fontSize: 12, color: '#94a3b8', fontStyle: 'italic',
                                        }}>
                                            {selectedCat
                                                ? 'Not configured on this category'
                                                : 'Pick a category above'}
                                        </div>
                                    )}
                                </div>
                            );

                            return (
                                <>
                                    <div style={gridStyle}>
                                        <DisplayCard title="Asset Account" acc={costAcc} />
                                        <DisplayCard title="Accumulated Depreciation" acc={accAccDep} />
                                        <DisplayCard title="Depreciation Expense" acc={depExpAcc} />
                                    </div>
                                    <div style={{
                                        marginTop: 10, fontSize: 11, color: '#64748b',
                                    }}>
                                        {selectedCat ? (
                                            <>
                                                These accounts are inherited on posting. To change
                                                them, edit the category in{' '}
                                                <i>Settings → Asset Categories</i>.
                                            </>
                                        ) : (
                                            <>Select an Asset Category above to see the GL accounts.</>
                                        )}
                                    </div>
                                </>
                            );
                        })()}
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
