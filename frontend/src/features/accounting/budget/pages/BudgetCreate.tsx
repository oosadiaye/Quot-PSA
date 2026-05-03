import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBudgetPeriods, useBudgetFiscalYears, periodLabel } from '../hooks/useBudgetPeriods';
import { useBudgets } from '../hooks/useBudgets';
import { useCostCenters } from '../../hooks/useCostCenters';
import { useMDAs, useAccounts } from '../../hooks/useBudgetDimensions';
import { useFunds, useFunctions, usePrograms, useGeos } from '../../hooks/useDimensions';
import apiClient from '../../../../api/client';
import { Save, Upload, Download, CheckCircle, AlertTriangle, Inbox, FileSpreadsheet, FilePlus } from 'lucide-react';
import { useDialog } from '../../../../hooks/useDialog';
import '../../styles/glassmorphism.css';

const labelStyle: React.CSSProperties = {
    display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600,
    color: 'var(--color-text)', marginBottom: '0.375rem',
};
const selectStyle: React.CSSProperties = {
    width: '100%', padding: '0.625rem', borderRadius: '8px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-sm)',
};
const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.625rem', borderRadius: '8px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-sm)',
};

// ─── Single Budget Creation Form ─────────────────────────────
const CreateForm: React.FC = () => {
    const navigate = useNavigate();
    const { years: fiscalYears } = useBudgetFiscalYears();
    const [selectedFY, setSelectedFY] = useState<string>('');
    const { periods, isLoading: periodsLoading } = useBudgetPeriods(
        selectedFY ? { fiscal_year: selectedFY, period_type: 'MONTHLY' } : { period_type: 'MONTHLY' }
    );
    const { createBudgetAsync, isCreating } = useBudgets();
    const { data: costCenters } = useCostCenters({ is_active: true });
    const { data: mdas = [] } = useMDAs({ is_active: true });
    const { data: accounts = [] } = useAccounts({ is_active: true });
    const { data: funds = [] } = useFunds();
    const { data: functions = [] } = useFunctions();
    const { data: programs = [] } = usePrograms();
    const { data: geos = [] } = useGeos();

    const [formData, setFormData] = useState<any>({
        period: '', mda: '', account: '',
        fund: '', function: '', program: '', geo: '', cost_center: '',
        allocated_amount: 0, revised_amount: '',
        control_level: 'HARD_STOP', enable_encumbrance: true,
    });
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    const updateField = (field: string, value: any) => {
        setFormData((prev: any) => ({ ...prev, [field]: value }));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setSuccess('');

        if (!formData.period || !formData.mda || !formData.account) {
            setError('Period, MDA, and Account are required');
            return;
        }
        try {
            const payload = {
                ...formData,
                period: Number(formData.period),
                mda: Number(formData.mda),
                account: Number(formData.account),
                fund: formData.fund ? Number(formData.fund) : undefined,
                function: formData.function ? Number(formData.function) : undefined,
                program: formData.program ? Number(formData.program) : undefined,
                geo: formData.geo ? Number(formData.geo) : undefined,
                cost_center: formData.cost_center ? Number(formData.cost_center) : undefined,
                allocated_amount: String(formData.allocated_amount),
                revised_amount: formData.revised_amount ? String(formData.revised_amount) : String(formData.allocated_amount),
            };
            await createBudgetAsync(payload);
            setSuccess('Budget created successfully');
            setFormData({
                period: '', mda: '', account: '',
                fund: '', function: '', program: '', geo: '', cost_center: '',
                allocated_amount: 0, revised_amount: '',
                control_level: 'HARD_STOP', enable_encumbrance: true,
            });
            setTimeout(() => setSuccess(''), 5000);
        } catch (err: any) {
            const detail = err?.response?.data;
            if (detail && typeof detail === 'object') {
                const msgs = Object.entries(detail)
                    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
                    .join('; ');
                setError(msgs);
            } else {
                setError('Failed to create budget');
            }
        }
    };

    return (
        <form onSubmit={handleSubmit}>
            {error && (
                <div style={{
                    padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem',
                    background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
                    color: '#ef4444', fontSize: 'var(--text-sm)',
                }}>
                    {error}
                </div>
            )}
            {success && (
                <div style={{
                    padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem',
                    background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)',
                    color: '#22c55e', fontSize: 'var(--text-sm)', display: 'flex', alignItems: 'center', gap: '0.5rem',
                }}>
                    <CheckCircle size={16} /> {success}
                </div>
            )}

            {/* Period & MDA */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                    <label style={labelStyle}>Budget Period *</label>
                    {/* Fiscal year filter then month picker */}
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <select
                            value={selectedFY}
                            onChange={(e) => { setSelectedFY(e.target.value); updateField('period', ''); }}
                            style={{ ...selectStyle, flex: '0 0 110px', fontSize: 'var(--text-xs)' }}
                        >
                            <option value="">All Years</option>
                            {(fiscalYears ?? []).map((yr: number) => (
                                <option key={yr} value={yr}>FY {yr}</option>
                            ))}
                        </select>
                        <select
                            value={formData.period}
                            onChange={(e) => updateField('period', e.target.value)}
                            style={selectStyle}
                            required
                            disabled={periodsLoading}
                        >
                            <option value="">
                                {periodsLoading ? 'Loading…' : periods?.length === 0 ? 'No periods — create a fiscal year first' : 'Select month…'}
                            </option>
                            {(periods ?? []).map((p: any) => (
                                <option key={p.id} value={p.id}>
                                    FY{p.fiscal_year} – {periodLabel(p)}
                                    {p.status === 'OPEN' ? ' ✓' : p.status === 'ACTIVE' ? ' (Active)' : ''}
                                </option>
                            ))}
                        </select>
                    </div>
                </div>
                <div>
                    <label style={labelStyle}>MDA *</label>
                    <select value={formData.mda} onChange={(e) => updateField('mda', e.target.value)} style={selectStyle} required>
                        <option value="">Select MDA</option>
                        {mdas.map((m: any) => (
                            <option key={m.id} value={m.id}>{m.code} - {m.name}</option>
                        ))}
                    </select>
                </div>
            </div>

            {/* GL Account */}
            <div style={{ marginBottom: '1rem' }}>
                <label style={labelStyle}>GL Account *</label>
                <select value={formData.account} onChange={(e) => updateField('account', e.target.value)} style={selectStyle} required>
                    <option value="">Select account</option>
                    {accounts.map((a: any) => (
                        <option key={a.id} value={a.id}>{a.code} - {a.name}</option>
                    ))}
                </select>
            </div>

            {/* Dimensions */}
            <div style={{ marginBottom: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                    <div style={{ flex: 1, height: '1px', background: 'var(--color-border)' }} />
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>Dimensions (optional)</span>
                    <div style={{ flex: 1, height: '1px', background: 'var(--color-border)' }} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0.75rem' }}>
                    {[
                        { label: 'Fund', field: 'fund', options: funds },
                        { label: 'Function', field: 'function', options: functions },
                        { label: 'Program', field: 'program', options: programs },
                        { label: 'Geo Location', field: 'geo', options: geos },
                        { label: 'Cost Center', field: 'cost_center', options: costCenters || [] },
                    ].map(({ label, field, options }) => (
                        <div key={field}>
                            <label style={labelStyle}>{label}</label>
                            <select
                                value={formData[field]}
                                onChange={(e) => updateField(field, e.target.value)}
                                style={selectStyle}
                            >
                                <option value="">{label}</option>
                                {(options as any[]).map((o: any) => (
                                    <option key={o.id} value={o.id}>{o.code} - {o.name}</option>
                                ))}
                            </select>
                        </div>
                    ))}
                </div>
            </div>

            {/* Amounts & Controls */}
            <div style={{ marginBottom: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                    <div style={{ flex: 1, height: '1px', background: 'var(--color-border)' }} />
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>Budget Amounts</span>
                    <div style={{ flex: 1, height: '1px', background: 'var(--color-border)' }} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '0.75rem' }}>
                    <div>
                        <label style={labelStyle}>Allocated Amount *</label>
                        <input
                            type="number"
                            value={formData.allocated_amount}
                            onChange={(e) => updateField('allocated_amount', e.target.value)}
                            min={0}
                            step="0.01"
                            required
                            style={{ ...inputStyle, textAlign: 'right' }}
                        />
                    </div>
                    <div>
                        <label style={labelStyle}>Revised Amount</label>
                        <input
                            type="number"
                            value={formData.revised_amount}
                            onChange={(e) => updateField('revised_amount', e.target.value)}
                            min={0}
                            step="0.01"
                            placeholder="Same as allocated"
                            style={{ ...inputStyle, textAlign: 'right' }}
                        />
                    </div>
                    <div>
                        <label style={labelStyle}>Control Level *</label>
                        <select value={formData.control_level} onChange={(e) => updateField('control_level', e.target.value)} style={selectStyle}>
                            <option value="HARD_STOP">Hard Stop</option>
                            <option value="WARNING">Warning</option>
                            <option value="NONE">None</option>
                        </select>
                    </div>
                    <div>
                        <label style={labelStyle}>Commitment Tracking</label>
                        <select
                            value={formData.enable_encumbrance ? 'On' : 'Off'}
                            onChange={(e) => updateField('enable_encumbrance', e.target.value === 'On')}
                            style={selectStyle}
                        >
                            <option value="On">On</option>
                            <option value="Off">Off</option>
                        </select>
                    </div>
                </div>
            </div>

            <button
                type="submit"
                disabled={isCreating}
                style={{
                    display: 'flex', alignItems: 'center', gap: '0.5rem',
                    padding: '0.75rem 1.5rem', borderRadius: '8px', border: 'none',
                    background: 'var(--color-primary, #1e40af)', color: 'white',
                    cursor: 'pointer', fontWeight: 600, fontSize: 'var(--text-sm)',
                    opacity: isCreating ? 0.6 : 1,
                }}
            >
                <Save size={18} /> Create Budget
            </button>
        </form>
    );
};

// ─── Bulk Upload Tab ─────────────────────────────────────────
const BulkUpload: React.FC = () => {
    const { showAlert } = useDialog();
    const [selectedPeriod, setSelectedPeriod] = useState<string>('');
    const [selectedFY, setSelectedFY] = useState<string>('');
    const [uploadedFile, setUploadedFile] = useState<File | null>(null);
    const [importResult, setImportResult] = useState<{ created: number; errors: string[] } | null>(null);
    const [importing, setImporting] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const { years: fiscalYears } = useBudgetFiscalYears();
    const { periods, isLoading: periodsLoading } = useBudgetPeriods(
        selectedFY ? { fiscal_year: selectedFY, period_type: 'MONTHLY' } : { period_type: 'MONTHLY' }
    );
    const { importBudgetsAsync } = useBudgets();

    const handleDownloadTemplate = async () => {
        try {
            const { data } = await apiClient.get('/accounting/budgets/import-template/', { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([data]));
            const link = document.createElement('a');
            link.href = url;
            link.download = 'budget_import_template.csv';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
        } catch {
            showAlert('Failed to download template');
        }
    };

    const handleImport = async () => {
        if (!uploadedFile || !selectedPeriod) return;
        setImporting(true);
        setImportResult(null);
        try {
            const result = await importBudgetsAsync({ file: uploadedFile, periodId: Number(selectedPeriod) });
            setImportResult({ created: result.created || 0, errors: result.errors || [] });
        } catch (err: any) {
            setImportResult({ created: 0, errors: [err?.response?.data?.error || 'Import failed'] });
        } finally {
            setImporting(false);
        }
    };

    return (
        <div>
            {/* Step 1: Period */}
            <div style={{ marginBottom: '1.5rem' }}>
                <label style={{ ...labelStyle, fontSize: 'var(--text-sm)' }}>1. Select Budget Period</label>
                <div style={{ display: 'flex', gap: '0.5rem', maxWidth: '480px' }}>
                    <select
                        value={selectedFY}
                        onChange={(e) => { setSelectedFY(e.target.value); setSelectedPeriod(''); }}
                        style={{ ...selectStyle, flex: '0 0 120px', fontSize: 'var(--text-xs)' }}
                    >
                        <option value="">All Years</option>
                        {(fiscalYears ?? []).map((yr: number) => (
                            <option key={yr} value={yr}>FY {yr}</option>
                        ))}
                    </select>
                    <select
                        value={selectedPeriod}
                        onChange={(e) => setSelectedPeriod(e.target.value)}
                        style={selectStyle}
                        disabled={periodsLoading}
                    >
                        <option value="">
                            {periodsLoading ? 'Loading…' : periods?.length === 0 ? 'No periods available' : 'Select month…'}
                        </option>
                        {(periods ?? []).map((p: any) => (
                            <option key={p.id} value={p.id}>
                                FY{p.fiscal_year} – {periodLabel(p)}
                                {p.status === 'OPEN' ? ' ✓' : p.status === 'ACTIVE' ? ' (Active)' : ''}
                            </option>
                        ))}
                    </select>
                </div>
            </div>

            {/* Step 2: Template */}
            <div style={{ marginBottom: '1.5rem' }}>
                <label style={{ ...labelStyle, fontSize: 'var(--text-sm)' }}>2. Download Template</label>
                <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', margin: '0 0 0.5rem 0' }}>
                    Download the CSV template, fill in your budget data, then upload below.
                    Required columns: mda_id, account_id, allocated_amount.
                </p>
                <button
                    onClick={handleDownloadTemplate}
                    className="glass-button"
                    style={{
                        display: 'flex', alignItems: 'center', gap: '0.375rem',
                        padding: '0.625rem 1rem', borderRadius: '8px',
                        border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                        color: 'var(--color-text)', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)',
                    }}
                >
                    <Download size={16} /> Download CSV Template
                </button>
            </div>

            {/* Step 3: Upload */}
            <div style={{ marginBottom: '1.5rem' }}>
                <label style={{ ...labelStyle, fontSize: 'var(--text-sm)' }}>3. Upload File</label>
                <div
                    onClick={() => fileInputRef.current?.click()}
                    style={{
                        maxWidth: '500px',
                        padding: '2rem',
                        borderRadius: '8px',
                        border: '2px dashed var(--color-border)',
                        background: 'var(--color-surface)',
                        textAlign: 'center',
                        cursor: 'pointer',
                        transition: 'border-color 0.2s',
                    }}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                        e.preventDefault();
                        const file = e.dataTransfer.files[0];
                        if (file) { setUploadedFile(file); setImportResult(null); }
                    }}
                >
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept=".csv,.xlsx,.xls"
                        style={{ display: 'none' }}
                        onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) { setUploadedFile(file); setImportResult(null); }
                            e.target.value = '';
                        }}
                    />
                    <Inbox size={36} style={{ color: 'var(--color-text-muted)', marginBottom: '0.5rem' }} />
                    <p style={{ color: 'var(--color-text)', margin: '0 0 0.25rem 0', fontWeight: 500 }}>
                        {uploadedFile ? uploadedFile.name : 'Click or drag CSV/Excel file here'}
                    </p>
                    <p style={{ color: 'var(--color-text-muted)', margin: 0, fontSize: 'var(--text-xs)' }}>
                        Supports .csv, .xlsx, .xls formats
                    </p>
                </div>
            </div>

            {/* Import Button */}
            <button
                onClick={handleImport}
                disabled={!uploadedFile || !selectedPeriod || importing}
                style={{
                    display: 'flex', alignItems: 'center', gap: '0.5rem',
                    padding: '0.75rem 1.5rem', borderRadius: '8px', border: 'none',
                    background: 'var(--color-primary, #1e40af)', color: 'white',
                    cursor: 'pointer', fontWeight: 600, fontSize: 'var(--text-sm)',
                    opacity: !uploadedFile || !selectedPeriod ? 0.5 : 1,
                }}
            >
                <Upload size={18} /> Import Budgets
            </button>

            {/* Import Results */}
            {importResult && (
                <div style={{ marginTop: '1.5rem' }}>
                    {importResult.created > 0 && (
                        <div style={{
                            padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '0.75rem',
                            background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)',
                            color: '#22c55e', fontSize: 'var(--text-sm)', display: 'flex', alignItems: 'center', gap: '0.5rem',
                        }}>
                            <CheckCircle size={16} /> {importResult.created} budget(s) created successfully
                        </div>
                    )}
                    {importResult.errors.length > 0 && (
                        <div style={{
                            padding: '0.75rem 1rem', borderRadius: '8px',
                            background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)',
                            fontSize: 'var(--text-sm)',
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#f59e0b', marginBottom: '0.5rem' }}>
                                <AlertTriangle size={16} /> {importResult.errors.length} row(s) had errors
                            </div>
                            <ul style={{
                                margin: 0, paddingLeft: '1.25rem',
                                maxHeight: '200px', overflowY: 'auto',
                                fontSize: 'var(--text-xs)', color: '#ef4444',
                            }}>
                                {importResult.errors.slice(0, 20).map((err, i) => (
                                    <li key={i} style={{ marginBottom: '0.25rem' }}>{err}</li>
                                ))}
                                {importResult.errors.length > 20 && (
                                    <li>...and {importResult.errors.length - 20} more</li>
                                )}
                            </ul>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

// ─── Main Page ───────────────────────────────────────────────
export const BudgetCreate: React.FC = () => {
    const [activeTab, setActiveTab] = useState<'create' | 'upload'>('create');

    return (
        <div>
            {/* Header */}
            <div style={{ marginBottom: '1.5rem' }}>
                <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', marginBottom: '0.25rem' }}>
                    Create Budget
                </h2>
                <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
                    Add a single budget allocation or bulk upload from a file
                </p>
            </div>

            {/* Tab Switcher */}
            <div style={{ display: 'flex', gap: '0', marginBottom: '1.5rem', borderBottom: '2px solid var(--color-border)' }}>
                {[
                    { key: 'create' as const, label: 'Create Budget', icon: <FilePlus size={16} /> },
                    { key: 'upload' as const, label: 'Bulk Upload', icon: <FileSpreadsheet size={16} /> },
                ].map((tab) => (
                    <button
                        key={tab.key}
                        onClick={() => setActiveTab(tab.key)}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '0.375rem',
                            padding: '0.75rem 1.25rem',
                            border: 'none',
                            borderBottom: activeTab === tab.key ? '2px solid var(--color-primary, #1e40af)' : '2px solid transparent',
                            background: 'transparent',
                            color: activeTab === tab.key ? 'var(--color-primary, #1e40af)' : 'var(--color-text-muted)',
                            cursor: 'pointer',
                            fontWeight: activeTab === tab.key ? 600 : 400,
                            fontSize: 'var(--text-sm)',
                            marginBottom: '-2px',
                            transition: 'all 0.2s',
                        }}
                    >
                        {tab.icon} {tab.label}
                    </button>
                ))}
            </div>

            {/* Tab Content */}
            <div className="glass-card" style={{ padding: '1.5rem' }}>
                {activeTab === 'create' ? <CreateForm /> : <BulkUpload />}
            </div>
        </div>
    );
};

export default BudgetCreate;
