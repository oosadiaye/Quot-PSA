import React, { useState, useEffect, useRef } from 'react';
import { useBudgetPeriods } from '../hooks/useBudgetPeriods';
import { useBudgets, useBudgetExport } from '../hooks/useBudgets';
import { useCostCenters } from '../../hooks/useCostCenters';
import { useMDAs, useAccounts } from '../../hooks/useBudgetDimensions';
import { useFunds, useFunctions, usePrograms, useGeos } from '../../hooks/useDimensions';
import type { BudgetFormData } from '../types/budget.types';
import LoadingScreen from '../../../../components/common/LoadingScreen';
import { Save, Upload, Download, Plus, X, FileSpreadsheet } from 'lucide-react';
import logger from '../../../../utils/logger';
import '../../styles/glassmorphism.css';

const selectStyle: React.CSSProperties = {
    width: '100%',
    padding: '0.5rem 0.625rem',
    borderRadius: '6px',
    border: '2.5px solid var(--color-border)',
    background: 'var(--color-surface)',
    color: 'var(--color-text)',
    fontSize: 'var(--text-xs)',
};

const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '0.5rem 0.625rem',
    borderRadius: '6px',
    border: '2.5px solid var(--color-border)',
    background: 'var(--color-surface)',
    color: 'var(--color-text)',
    fontSize: 'var(--text-xs)',
    textAlign: 'right',
};

export const BudgetEntry: React.FC = () => {
    const [selectedPeriod, setSelectedPeriod] = useState<number | undefined>();
    const [selectedMda, setSelectedMda] = useState<number | undefined>();
    const [selectedFund, setSelectedFund] = useState<number | undefined>();
    const [selectedFunction, setSelectedFunction] = useState<number | undefined>();
    const [selectedProgram, setSelectedProgram] = useState<number | undefined>();
    const [selectedGeo, setSelectedGeo] = useState<number | undefined>();
    const [selectedCostCenter, setSelectedCostCenter] = useState<number | undefined>();
    const [editingData, setEditingData] = useState<any[]>([]);
    const [hasChanges, setHasChanges] = useState(false);
    const [saveError, setSaveError] = useState('');
    const [saveSuccess, setSaveSuccess] = useState('');

    const { periods, isLoading: periodsLoading } = useBudgetPeriods();
    const { data: costCenters } = useCostCenters({ is_active: true });
    const { data: mdas = [] } = useMDAs({ is_active: true });
    const { data: accounts = [] } = useAccounts({ is_active: true });
    const { data: funds = [] } = useFunds();
    const { data: functions = [] } = useFunctions();
    const { data: programs = [] } = usePrograms();
    const { data: geos = [] } = useGeos();
    const {
        budgets,
        isLoading: budgetsLoading,
        createBudget,
        updateBudget,
        isCreating,
        isUpdating,
        importBudgetsAsync,
        isImporting,
    } = useBudgets({
        period: selectedPeriod,
        mda: selectedMda,
        fund: selectedFund,
        function: selectedFunction,
        program: selectedProgram,
        geo: selectedGeo,
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
        setEditingData((prev) =>
            prev.map((item) => item.key === key ? { ...item, [field]: value } : item)
        );
        setHasChanges(true);
    };

    const handleAddRow = () => {
        if (!selectedPeriod || !selectedMda) {
            setSaveError('Please select a period and MDA first');
            setTimeout(() => setSaveError(''), 3000);
            return;
        }
        const newRow = {
            key: Date.now(),
            period: selectedPeriod,
            mda: selectedMda,
            fund: selectedFund,
            function: selectedFunction,
            program: selectedProgram,
            geo: selectedGeo,
            cost_center: selectedCostCenter,
            account: undefined,
            allocated_amount: '0.00',
            revised_amount: '0.00',
            control_level: 'WARNING',
            enable_encumbrance: true,
            notes: '',
            isNew: true,
        };
        setEditingData([...editingData, newRow]);
        setHasChanges(true);
    };

    const handleRemoveRow = (key: number) => {
        setEditingData((prev) => prev.filter((item) => item.key !== key));
        setHasChanges(true);
    };

    const handleSave = async () => {
        setSaveError('');
        setSaveSuccess('');
        try {
            for (const row of editingData) {
                if (!row.account) {
                    setSaveError('All rows must have an account selected');
                    return;
                }
                const budgetData: BudgetFormData = {
                    period: row.period,
                    mda: row.mda,
                    account: row.account,
                    fund: row.fund,
                    function: row.function,
                    program: row.program,
                    geo: row.geo,
                    cost_center: row.cost_center || null,
                    allocated_amount: row.allocated_amount,
                    revised_amount: row.revised_amount || row.allocated_amount,
                    control_level: row.control_level,
                    enable_encumbrance: row.enable_encumbrance,
                    notes: row.notes,
                };
                if (row.isNew) {
                    await createBudget(budgetData);
                } else if (row.id) {
                    await updateBudget({ id: row.id, ...budgetData });
                }
            }
            setSaveSuccess('Budgets saved successfully');
            setHasChanges(false);
            setTimeout(() => setSaveSuccess(''), 3000);
        } catch (error) {
            setSaveError('Failed to save budgets');
            logger.error(error);
        }
    };

    const handleFileImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file || !selectedPeriod) return;
        try {
            const result = await importBudgetsAsync({ file, periodId: selectedPeriod });
            setSaveSuccess(`${result.created || 0} budget(s) imported`);
            if (result.errors?.length) setSaveError(`${result.errors.length} row(s) had errors`);
            setTimeout(() => { setSaveSuccess(''); setSaveError(''); }, 4000);
        } catch {
            setSaveError('Import failed');
        }
        e.target.value = '';
    };

    if (isLoading && !editingData.length) {
        return <LoadingScreen message="Loading budgets..." />;
    }

    return (
        <div>
            {/* Header */}
            <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', marginBottom: '0.25rem' }}>
                        Budget Entry
                    </h2>
                    <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
                        Create and manage budget allocations
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <input
                        type="file"
                        ref={fileInputRef}
                        accept=".csv,.xlsx,.xls"
                        style={{ display: 'none' }}
                        onChange={handleFileImport}
                    />
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={!selectedPeriod || isImporting}
                        className="glass-button"
                        style={{
                            display: 'flex', alignItems: 'center', gap: '0.375rem',
                            padding: '0.625rem 1rem', borderRadius: '8px',
                            border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                            color: 'var(--color-text)', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)',
                            opacity: !selectedPeriod ? 0.5 : 1,
                        }}
                    >
                        <Upload size={16} /> Import
                    </button>
                    <button
                        onClick={() => exportBudgets({
                            period: selectedPeriod, mda: selectedMda, fund: selectedFund,
                            function: selectedFunction, program: selectedProgram, geo: selectedGeo,
                        })}
                        disabled={!selectedPeriod || isExporting}
                        className="glass-button"
                        style={{
                            display: 'flex', alignItems: 'center', gap: '0.375rem',
                            padding: '0.625rem 1rem', borderRadius: '8px',
                            border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                            color: 'var(--color-text)', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)',
                            opacity: !selectedPeriod ? 0.5 : 1,
                        }}
                    >
                        <Download size={16} /> Export
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={!hasChanges || !selectedPeriod || isCreating || isUpdating}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '0.375rem',
                            padding: '0.625rem 1rem', borderRadius: '8px',
                            border: 'none', background: 'var(--color-primary, #1e40af)',
                            color: 'white', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)',
                            opacity: !hasChanges || !selectedPeriod ? 0.5 : 1,
                        }}
                    >
                        <Save size={16} /> Save Changes
                    </button>
                </div>
            </div>

            {/* Status Messages */}
            {saveError && (
                <div style={{
                    padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem',
                    background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
                    color: '#ef4444', fontSize: 'var(--text-sm)',
                }}>
                    {saveError}
                </div>
            )}
            {saveSuccess && (
                <div style={{
                    padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem',
                    background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)',
                    color: '#22c55e', fontSize: 'var(--text-sm)',
                }}>
                    {saveSuccess}
                </div>
            )}

            {/* Period Selector */}
            <div className="glass-card" style={{ padding: '1rem', marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', marginBottom: '0.375rem' }}>
                    Budget Period
                </label>
                <select
                    value={selectedPeriod || ''}
                    onChange={(e) => setSelectedPeriod(Number(e.target.value) || undefined)}
                    style={{ ...selectStyle, maxWidth: '400px' }}
                >
                    <option value="">Select budget period</option>
                    {(periods || []).map((p: any) => (
                        <option key={p.id} value={p.id}>
                            FY{p.fiscal_year} - {p.period_type === 'ANNUAL' ? 'Annual' : p.period_type === 'QUARTERLY' ? `Q${p.period_number}` : `Month ${p.period_number}`}
                            {p.status === 'ACTIVE' ? ' (Active)' : ''}
                        </option>
                    ))}
                </select>
            </div>

            {/* Dimensions Filter */}
            <div className="glass-card" style={{ padding: '1rem', marginBottom: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                    <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Budget Dimensions</span>
                    <button
                        onClick={() => {
                            setSelectedMda(undefined); setSelectedFund(undefined);
                            setSelectedFunction(undefined); setSelectedProgram(undefined);
                            setSelectedGeo(undefined);
                        }}
                        style={{
                            padding: '0.25rem 0.5rem', borderRadius: '4px', border: 'none',
                            background: 'transparent', color: 'var(--color-primary, #1e40af)',
                            cursor: 'pointer', fontSize: 'var(--text-xs)',
                        }}
                    >
                        Clear All
                    </button>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0.75rem' }}>
                    {[
                        { label: 'MDA', value: selectedMda, onChange: setSelectedMda, options: mdas },
                        { label: 'Fund', value: selectedFund, onChange: setSelectedFund, options: funds },
                        { label: 'Function', value: selectedFunction, onChange: setSelectedFunction, options: functions },
                        { label: 'Program', value: selectedProgram, onChange: setSelectedProgram, options: programs },
                        { label: 'Geo Location', value: selectedGeo, onChange: setSelectedGeo, options: geos },
                    ].map(({ label, value, onChange, options }) => (
                        <div key={label}>
                            <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', marginBottom: '0.25rem' }}>
                                {label}
                            </label>
                            <select
                                value={value || ''}
                                onChange={(e) => onChange(Number(e.target.value) || undefined)}
                                style={selectStyle}
                            >
                                <option value="">Select {label}</option>
                                {(options as any[]).map((o: any) => (
                                    <option key={o.id} value={o.id}>{o.code} - {o.name}</option>
                                ))}
                            </select>
                        </div>
                    ))}
                </div>
            </div>

            {/* Cost Center */}
            <div className="glass-card" style={{ padding: '1rem', marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', marginBottom: '0.375rem' }}>
                    Cost Center (Optional)
                </label>
                <select
                    value={selectedCostCenter || ''}
                    onChange={(e) => setSelectedCostCenter(Number(e.target.value) || undefined)}
                    style={{ ...selectStyle, maxWidth: '400px' }}
                >
                    <option value="">Select a cost center</option>
                    {(costCenters || []).map((cc: any) => (
                        <option key={cc.id} value={cc.id}>{cc.code} - {cc.name}</option>
                    ))}
                </select>
            </div>

            {/* Budget Lines */}
            {!selectedPeriod ? (
                <div className="glass-card" style={{ padding: '2rem', textAlign: 'center' }}>
                    <FileSpreadsheet size={48} style={{ margin: '0 auto 1rem', opacity: 0.5, display: 'block', color: 'var(--color-text-muted)' }} />
                    <h3 style={{ color: 'var(--color-text)', marginBottom: '0.5rem' }}>Select a Budget Period</h3>
                    <p style={{ color: 'var(--color-text-muted)', margin: 0, fontSize: 'var(--text-sm)' }}>
                        Please select a budget period to begin entering budget data.
                    </p>
                </div>
            ) : (
                <div className="glass-card" style={{ overflow: 'hidden' }}>
                    <div style={{ padding: '1rem 1.5rem', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text)', margin: 0 }}>
                            Budget Lines
                        </h3>
                        <button
                            onClick={handleAddRow}
                            disabled={!selectedMda}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '0.25rem',
                                padding: '0.5rem 0.75rem', borderRadius: '6px',
                                border: '1px dashed var(--color-border)',
                                background: 'transparent', color: 'var(--color-primary, #1e40af)',
                                cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 500,
                                opacity: !selectedMda ? 0.5 : 1,
                            }}
                        >
                            <Plus size={14} /> Add Line
                        </button>
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '900px' }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                    <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '220px' }}>Account</th>
                                    <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '180px' }}>Cost Center</th>
                                    <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '150px' }}>Allocated Amount</th>
                                    <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '150px' }}>Revised Amount</th>
                                    <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '130px' }}>Control Level</th>
                                    <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '100px' }}>Commitment</th>
                                    <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '50px' }}></th>
                                </tr>
                            </thead>
                            <tbody>
                                {editingData.length > 0 ? (
                                    editingData.map((row: any, index: number) => (
                                        <tr
                                            key={row.key}
                                            style={{
                                                borderBottom: '1px solid var(--color-border)',
                                                animation: `fadeInUp 0.3s ease-out ${index * 0.03}s both`,
                                            }}
                                        >
                                            <td style={{ padding: '0.5rem 1rem' }}>
                                                <select
                                                    value={row.account || ''}
                                                    onChange={(e) => handleCellChange(row.key, 'account', Number(e.target.value) || undefined)}
                                                    style={selectStyle}
                                                >
                                                    <option value="">Select account</option>
                                                    {accounts.map((acc: any) => (
                                                        <option key={acc.id} value={acc.id}>{acc.code} - {acc.name}</option>
                                                    ))}
                                                </select>
                                            </td>
                                            <td style={{ padding: '0.5rem 1rem' }}>
                                                <select
                                                    value={row.cost_center || ''}
                                                    onChange={(e) => handleCellChange(row.key, 'cost_center', Number(e.target.value) || undefined)}
                                                    style={selectStyle}
                                                >
                                                    <option value="">Optional</option>
                                                    {(costCenters || []).map((cc: any) => (
                                                        <option key={cc.id} value={cc.id}>{cc.code} - {cc.name}</option>
                                                    ))}
                                                </select>
                                            </td>
                                            <td style={{ padding: '0.5rem 1rem' }}>
                                                <input
                                                    type="number"
                                                    value={parseFloat(row.allocated_amount) || 0}
                                                    onChange={(e) => handleCellChange(row.key, 'allocated_amount', e.target.value || '0.00')}
                                                    min={0}
                                                    step="0.01"
                                                    style={inputStyle}
                                                />
                                            </td>
                                            <td style={{ padding: '0.5rem 1rem' }}>
                                                <input
                                                    type="number"
                                                    value={parseFloat(row.revised_amount) || 0}
                                                    onChange={(e) => handleCellChange(row.key, 'revised_amount', e.target.value || '0.00')}
                                                    min={0}
                                                    step="0.01"
                                                    style={inputStyle}
                                                />
                                            </td>
                                            <td style={{ padding: '0.5rem 1rem' }}>
                                                <select
                                                    value={row.control_level}
                                                    onChange={(e) => handleCellChange(row.key, 'control_level', e.target.value)}
                                                    style={selectStyle}
                                                >
                                                    <option value="NONE">None</option>
                                                    <option value="WARNING">Warning</option>
                                                    <option value="HARD_STOP">Hard Stop</option>
                                                </select>
                                            </td>
                                            <td style={{ padding: '0.5rem 1rem', textAlign: 'center' }}>
                                                <select
                                                    value={row.enable_encumbrance ? 'Yes' : 'No'}
                                                    onChange={(e) => handleCellChange(row.key, 'enable_encumbrance', e.target.value === 'Yes')}
                                                    style={{ ...selectStyle, textAlign: 'center' }}
                                                >
                                                    <option value="Yes">Yes</option>
                                                    <option value="No">No</option>
                                                </select>
                                            </td>
                                            <td style={{ padding: '0.5rem 0.5rem', textAlign: 'center' }}>
                                                {row.isNew && (
                                                    <button
                                                        onClick={() => handleRemoveRow(row.key)}
                                                        style={{
                                                            padding: '0.25rem', borderRadius: '4px',
                                                            border: 'none', background: 'rgba(239,68,68,0.1)',
                                                            color: '#ef4444', cursor: 'pointer',
                                                            display: 'inline-flex', alignItems: 'center',
                                                        }}
                                                    >
                                                        <X size={14} />
                                                    </button>
                                                )}
                                            </td>
                                        </tr>
                                    ))
                                ) : (
                                    <tr>
                                        <td colSpan={7} style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                            <FileSpreadsheet size={40} style={{ margin: '0 auto 0.75rem', opacity: 0.4, display: 'block' }} />
                                            <p style={{ margin: 0 }}>No budget lines. Click "Add Line" to begin.</p>
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
};

export default BudgetEntry;
