/**
 * Budget Entry — Quot PSE (Public Sector)
 *
 * Appropriation budget entry with mandatory NCoA dimensions:
 * - Fiscal Year + Period (Monthly or Annual)
 * - Administrative Segment (MDA) — MANDATORY (budget control)
 * - Economic Code (Account) — MANDATORY (budget control)
 * - Fund Source — MANDATORY (budget control)
 * - Function, Programme, Geographic — OPTIONAL (statistical)
 *
 * All expenditure budgets are HARD_STOP with encumbrance enabled.
 * Cost Center removed — MDA replaces it in PSA.
 */
import React, { useState, useEffect, useRef } from 'react';
import { useBudgetPeriods } from '../hooks/useBudgetPeriods';
import { useBudgets, useBudgetExport } from '../hooks/useBudgets';
import { useMDAs, useAccounts } from '../../hooks/useBudgetDimensions';
import { useFunds, useFunctions, usePrograms, useGeos } from '../../hooks/useDimensions';
import type { BudgetFormData } from '../types/budget.types';
import LoadingScreen from '../../../../components/common/LoadingScreen';
import { Save, Upload, Download, Plus, X, FileSpreadsheet } from 'lucide-react';
import logger from '../../../../utils/logger';
import '../../styles/glassmorphism.css';

const selectStyle: React.CSSProperties = {
    width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-xs)',
};
const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-xs)', textAlign: 'right',
};
const lblStyle: React.CSSProperties = {
    display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600,
    color: 'var(--color-text)', marginBottom: '0.25rem',
};
const requiredMark = <span style={{ color: '#ef4444', marginLeft: 2 }}>*</span>;

export const BudgetEntry: React.FC = () => {
    const [selectedYear, setSelectedYear] = useState<number | undefined>();
    const [selectedPeriod, setSelectedPeriod] = useState<number | undefined>();
    const [selectedMda, setSelectedMda] = useState<number | undefined>();
    const [selectedFund, setSelectedFund] = useState<number | undefined>();
    const [selectedFunction, setSelectedFunction] = useState<number | undefined>();
    const [selectedProgram, setSelectedProgram] = useState<number | undefined>();
    const [selectedGeo, setSelectedGeo] = useState<number | undefined>();
    const [editingData, setEditingData] = useState<any[]>([]);
    const [hasChanges, setHasChanges] = useState(false);
    const [saveError, setSaveError] = useState('');
    const [saveSuccess, setSaveSuccess] = useState('');

    const { periods, isLoading: periodsLoading } = useBudgetPeriods();
    const { data: mdas = [] } = useMDAs({ is_active: true });
    const { data: accounts = [] } = useAccounts({ is_active: true });
    const { data: funds = [] } = useFunds();
    const { data: functions = [] } = useFunctions();
    const { data: programs = [] } = usePrograms();
    const { data: geos = [] } = useGeos();
    const {
        budgets, isLoading: budgetsLoading,
        createBudget, updateBudget, isCreating, isUpdating,
        importBudgetsAsync, isImporting,
    } = useBudgets({
        period: selectedPeriod, mda: selectedMda, fund: selectedFund,
        function: selectedFunction, program: selectedProgram, geo: selectedGeo,
    });
    const { exportBudgets, isExporting } = useBudgetExport();
    const fileInputRef = useRef<HTMLInputElement>(null);

    const isLoading = periodsLoading || budgetsLoading || isCreating || isUpdating;

    useEffect(() => {
        if (budgets) {
            setEditingData(budgets.map((budget: any) => ({ ...budget, key: budget.id })));
            setHasChanges(false);
        }
    }, [budgets]);

    const handleCellChange = (key: number, field: string, value: any) => {
        setEditingData(prev => prev.map(item => item.key === key ? { ...item, [field]: value } : item));
        setHasChanges(true);
    };

    const handleAddRow = () => {
        if (!selectedYear || !selectedMda || !selectedFund) {
            setSaveError('Fiscal Year, MDA, and Fund are required before adding budget lines');
            // 12s — errors need time to read (field + reason + action)
            setTimeout(() => setSaveError(''), 12000);
            return;
        }
        setEditingData([...editingData, {
            key: Date.now(),
            period: selectedPeriod,
            mda: selectedMda,
            fund: selectedFund,
            function: selectedFunction,
            program: selectedProgram,
            geo: selectedGeo,
            account: undefined,
            allocated_amount: '0.00',
            revised_amount: '0.00',
            control_level: 'HARD_STOP',
            enable_encumbrance: true,
            notes: '',
            isNew: true,
        }]);
        setHasChanges(true);
    };

    const handleRemoveRow = (key: number) => {
        setEditingData(prev => prev.filter(item => item.key !== key));
        setHasChanges(true);
    };

    const handleSave = async () => {
        setSaveError(''); setSaveSuccess('');
        try {
            for (const row of editingData) {
                if (!row.account) { setSaveError('All rows must have an account selected'); return; }

                // Auto-detect control level from account code:
                // 1xxxxxxx (Revenue/Income) = NONE (statistical, no enforcement)
                // 2xxxxxxx (Expenditure) = HARD_STOP
                // 3xxxxxxx (Assets) = HARD_STOP
                // 4xxxxxxx (Liabilities) = WARNING
                const selectedAccount = accounts.find((a: any) => a.id === row.account);
                const code = selectedAccount?.code || '';
                let controlLevel = 'HARD_STOP';
                if (code.startsWith('1')) controlLevel = 'NONE'; // Revenue = statistical
                else if (code.startsWith('4')) controlLevel = 'WARNING'; // Liabilities = warning

                const budgetData: BudgetFormData = {
                    period: row.period,
                    mda: row.mda,
                    account: row.account,
                    fund: row.fund,
                    function: row.function,
                    program: row.program,
                    geo: row.geo,
                    cost_center: null,
                    allocated_amount: row.allocated_amount,
                    revised_amount: row.revised_amount || row.allocated_amount,
                    control_level: controlLevel,
                    enable_encumbrance: !code.startsWith('1'), // No encumbrance for revenue
                    notes: row.notes,
                };
                if (row.isNew) await createBudget(budgetData);
                else if (row.id) await updateBudget({ id: row.id, ...budgetData });
            }
            setSaveSuccess('Budget saved successfully');
            setHasChanges(false);
            setTimeout(() => setSaveSuccess(''), 5000);
        } catch (error) {
            setSaveError('Failed to save budget');
            logger.error(error);
        }
    };

    const handleFileImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file || !selectedPeriod) return;
        try {
            const result = await importBudgetsAsync({ file, periodId: selectedPeriod });
            setSaveSuccess(`${result.created || 0} budget line(s) imported`);
            if (result.errors?.length) setSaveError(`${result.errors.length} row(s) had errors`);
            setTimeout(() => { setSaveSuccess(''); setSaveError(''); }, 4000);
        } catch { setSaveError('Import failed'); }
        e.target.value = '';
    };

    // Compute totals
    const totalAllocated = editingData.reduce((s, r) => s + (parseFloat(r.allocated_amount) || 0), 0);
    const totalRevised = editingData.reduce((s, r) => s + (parseFloat(r.revised_amount) || 0), 0);

    if (isLoading && !editingData.length) return <LoadingScreen message="Loading budgets..." />;

    return (
        <div>
            {/* Header */}
            <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', marginBottom: '0.25rem' }}>
                        Budget Entry
                    </h2>
                    <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
                        Enter expenditure and revenue budgets by MDA, Economic Code, and Fund
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <input type="file" ref={fileInputRef} accept=".csv,.xlsx,.xls" style={{ display: 'none' }} onChange={handleFileImport} />
                    <button onClick={() => fileInputRef.current?.click()} disabled={!selectedYear || isImporting}
                        className="glass-button" style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', padding: '0.625rem 1rem', borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)', opacity: !selectedYear ? 0.5 : 1 }}>
                        <Upload size={16} /> Import
                    </button>
                    <button onClick={() => exportBudgets({ period: selectedPeriod, mda: selectedMda, fund: selectedFund, function: selectedFunction, program: selectedProgram, geo: selectedGeo })}
                        disabled={!selectedYear || isExporting} className="glass-button"
                        style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', padding: '0.625rem 1rem', borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)', opacity: !selectedYear ? 0.5 : 1 }}>
                        <Download size={16} /> Export
                    </button>
                    <button onClick={handleSave} disabled={!hasChanges || !selectedYear || isCreating || isUpdating}
                        style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', padding: '0.625rem 1rem', borderRadius: '8px', border: 'none', background: 'var(--color-primary, #008751)', color: 'white', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)', opacity: !hasChanges || !selectedYear ? 0.5 : 1 }}>
                        <Save size={16} /> Save Changes
                    </button>
                </div>
            </div>

            {/* Messages */}
            {saveError && <div style={{ padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#ef4444', fontSize: 'var(--text-sm)' }}>{saveError}</div>}
            {saveSuccess && <div style={{ padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem', background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)', color: '#22c55e', fontSize: 'var(--text-sm)' }}>{saveSuccess}</div>}

            {/* Fiscal Year + Period Selection */}
            <div className="glass-card" style={{ padding: '1rem', marginBottom: '1rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                    <div>
                        <label style={lblStyle}>Fiscal Year {requiredMark}</label>
                        <select value={selectedYear || ''} onChange={e => { setSelectedYear(Number(e.target.value) || undefined); setSelectedPeriod(undefined); }} style={selectStyle}>
                            <option value="">Select fiscal year...</option>
                            {[...new Set((periods || []).map((p: any) => p.fiscal_year))].sort((a: number, b: number) => b - a).map((yr: any) => (
                                <option key={yr} value={yr}>FY {yr}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label style={lblStyle}>Period <span style={{ color: 'var(--color-text-muted)', fontWeight: 400 }}>(optional — leave as "All Periods" for annual budget)</span></label>
                        <select value={selectedPeriod || ''} onChange={e => setSelectedPeriod(Number(e.target.value) || undefined)} style={selectStyle} disabled={!selectedYear}>
                            <option value="">{selectedYear ? 'All Periods (Annual)' : 'Select fiscal year first'}</option>
                            {(periods || [])
                                .filter((p: any) => p.fiscal_year === selectedYear)
                                .map((p: any) => (
                                    <option key={p.id} value={p.id}>
                                        {p.period_type === 'ANNUAL' ? 'Annual (Full Year)' : p.period_type === 'QUARTERLY' ? `Q${p.period_number}` : `Month ${p.period_number}`}
                                        {p.status === 'ACTIVE' ? ' (Active)' : p.status === 'CLOSED' ? ' (Closed)' : ''}
                                    </option>
                                ))}
                        </select>
                    </div>
                </div>
            </div>

            {/* NCoA Budget Dimensions */}
            <div className="glass-card" style={{ padding: '1rem', marginBottom: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                    <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>NCoA Budget Dimensions</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem', marginBottom: '0.75rem' }}>
                    {/* MANDATORY — Budget Control */}
                    <div>
                        <label style={lblStyle}>Administrative (MDA) {requiredMark}</label>
                        <select value={selectedMda || ''} onChange={e => setSelectedMda(Number(e.target.value) || undefined)} style={{ ...selectStyle, borderColor: !selectedMda && selectedPeriod ? '#ef4444' : '' }}>
                            <option value="">Select MDA...</option>
                            {mdas.map((o: any) => <option key={o.id} value={o.id}>{o.code} - {o.name}</option>)}
                        </select>
                    </div>
                    <div>
                        <label style={lblStyle}>Fund Source {requiredMark}</label>
                        <select value={selectedFund || ''} onChange={e => setSelectedFund(Number(e.target.value) || undefined)} style={{ ...selectStyle, borderColor: !selectedFund && selectedPeriod ? '#ef4444' : '' }}>
                            <option value="">Select fund...</option>
                            {funds.map((o: any) => <option key={o.id} value={o.id}>{o.code} - {o.name}</option>)}
                        </select>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'end' }}>
                        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6, padding: '6px 10px', fontSize: 'var(--text-xs)', color: '#475569', width: '100%', lineHeight: 1.5 }}>
                            <div><span style={{ color: '#dc2626' }}>Expenditure (2x):</span> HARD STOP</div>
                            <div><span style={{ color: '#166534' }}>Revenue (1x):</span> Statistical only</div>
                            <div><span style={{ color: '#1e40af' }}>Asset (3x):</span> HARD STOP</div>
                        </div>
                    </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
                    {/* OPTIONAL — Statistical/Reporting */}
                    <div>
                        <label style={lblStyle}>Function (COFOG) <span style={{ color: 'var(--color-text-muted)', fontWeight: 400 }}>optional</span></label>
                        <select value={selectedFunction || ''} onChange={e => setSelectedFunction(Number(e.target.value) || undefined)} style={selectStyle}>
                            <option value="">All functions</option>
                            {functions.map((o: any) => <option key={o.id} value={o.id}>{o.code} - {o.name}</option>)}
                        </select>
                    </div>
                    <div>
                        <label style={lblStyle}>Programme <span style={{ color: 'var(--color-text-muted)', fontWeight: 400 }}>optional</span></label>
                        <select value={selectedProgram || ''} onChange={e => setSelectedProgram(Number(e.target.value) || undefined)} style={selectStyle}>
                            <option value="">All programmes</option>
                            {programs.map((o: any) => <option key={o.id} value={o.id}>{o.code} - {o.name}</option>)}
                        </select>
                    </div>
                    <div>
                        <label style={lblStyle}>Geographic <span style={{ color: 'var(--color-text-muted)', fontWeight: 400 }}>optional</span></label>
                        <select value={selectedGeo || ''} onChange={e => setSelectedGeo(Number(e.target.value) || undefined)} style={selectStyle}>
                            <option value="">All locations</option>
                            {geos.map((o: any) => <option key={o.id} value={o.id}>{o.code} - {o.name}</option>)}
                        </select>
                    </div>
                </div>
            </div>

            {/* Budget Lines Table */}
            {!selectedYear ? (
                <div className="glass-card" style={{ padding: '2rem', textAlign: 'center' }}>
                    <FileSpreadsheet size={48} style={{ margin: '0 auto 1rem', opacity: 0.5, display: 'block', color: 'var(--color-text-muted)' }} />
                    <h3 style={{ color: 'var(--color-text)', marginBottom: '0.5rem' }}>Select a Fiscal Year</h3>
                    <p style={{ color: 'var(--color-text-muted)', margin: 0, fontSize: 'var(--text-sm)' }}>
                        Select a fiscal year, MDA, and fund source to begin entering budget data.
                        Period is optional — leave as "All Periods" for annual budgets.
                    </p>
                </div>
            ) : (
                <div className="glass-card" style={{ overflow: 'hidden' }}>
                    <div style={{ padding: '1rem 1.5rem', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text)', margin: 0 }}>
                            Budget Lines ({editingData.length})
                        </h3>
                        <button onClick={handleAddRow} disabled={!selectedMda || !selectedFund}
                            style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px dashed var(--color-border)', background: 'transparent', color: 'var(--color-primary, #008751)', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 500, opacity: !selectedMda || !selectedFund ? 0.5 : 1 }}>
                            <Plus size={14} /> Add Line
                        </button>
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '700px' }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                    <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '280px' }}>Economic Code (Account) {requiredMark}</th>
                                    <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '160px' }}>Allocated Amount</th>
                                    <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '160px' }}>Revised Amount</th>
                                    <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)' }}>Notes</th>
                                    <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center', width: '50px' }}></th>
                                </tr>
                            </thead>
                            <tbody>
                                {editingData.length > 0 ? editingData.map((row: any) => (
                                    <tr key={row.key} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.5rem 1rem' }}>
                                            <select value={row.account || ''} onChange={e => handleCellChange(row.key, 'account', Number(e.target.value) || undefined)} style={selectStyle}>
                                                <option value="">Select account...</option>
                                                {accounts.map((acc: any) => <option key={acc.id} value={acc.id}>{acc.code} - {acc.name}</option>)}
                                            </select>
                                        </td>
                                        <td style={{ padding: '0.5rem 1rem' }}>
                                            <input type="number" value={parseFloat(row.allocated_amount) || 0} onChange={e => handleCellChange(row.key, 'allocated_amount', e.target.value || '0.00')} min={0} step="0.01" style={inputStyle} />
                                        </td>
                                        <td style={{ padding: '0.5rem 1rem' }}>
                                            <input type="number" value={parseFloat(row.revised_amount) || 0} onChange={e => handleCellChange(row.key, 'revised_amount', e.target.value || '0.00')} min={0} step="0.01" style={inputStyle} />
                                        </td>
                                        <td style={{ padding: '0.5rem 1rem' }}>
                                            <input type="text" value={row.notes || ''} onChange={e => handleCellChange(row.key, 'notes', e.target.value)} style={{ ...selectStyle, textAlign: 'left' }} placeholder="Budget line notes" />
                                        </td>
                                        <td style={{ padding: '0.5rem 0.5rem', textAlign: 'center' }}>
                                            {row.isNew && (
                                                <button onClick={() => handleRemoveRow(row.key)} style={{ padding: '0.25rem', borderRadius: '4px', border: 'none', background: 'rgba(239,68,68,0.1)', color: '#ef4444', cursor: 'pointer', display: 'inline-flex', alignItems: 'center' }}>
                                                    <X size={14} />
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                )) : (
                                    <tr>
                                        <td colSpan={5} style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                            <FileSpreadsheet size={40} style={{ margin: '0 auto 0.75rem', opacity: 0.4, display: 'block' }} />
                                            <p style={{ margin: 0 }}>No budget lines. Select MDA + Fund, then click "Add Line".</p>
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                            {editingData.length > 0 && (
                                <tfoot>
                                    <tr style={{ borderTop: '2px solid var(--color-border)', background: 'var(--color-surface-alt, #f8fafc)' }}>
                                        <td style={{ padding: '0.75rem 1rem', fontWeight: 700, fontSize: 'var(--text-sm)' }}>
                                            Total ({editingData.length} lines)
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)', color: '#166534' }}>
                                            {'\u20A6'}{totalAllocated.toLocaleString('en-NG', { minimumFractionDigits: 2 })}
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)', color: '#1e40af' }}>
                                            {'\u20A6'}{totalRevised.toLocaleString('en-NG', { minimumFractionDigits: 2 })}
                                        </td>
                                        <td colSpan={2}></td>
                                    </tr>
                                </tfoot>
                            )}
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
};

export default BudgetEntry;
