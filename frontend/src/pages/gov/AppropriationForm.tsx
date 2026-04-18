/**
 * Appropriation / Budget Entry — Quot PSE
 * Route: /budget/appropriations/new
 *
 * Glassmorphism-styled spreadsheet budget entry:
 * - Header: Fiscal Year, MDA, Fund, Type, Law Reference
 * - Lines: Economic Code + Amount per line (add/remove rows)
 * - Auto-detects control level from account type
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, AlertCircle, Plus, X, FileSpreadsheet, Calendar } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import SearchableSelect from '../../components/SearchableSelect';
import {
    useCreateAppropriation, useNCoASegments, useFiscalYears,
} from '../../hooks/useGovForms';
import '../../features/accounting/styles/glassmorphism.css';

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

const lblStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '0.65rem',
    fontWeight: 600,
    color: 'var(--color-text-muted)',
    marginBottom: '0.25rem',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.04em',
};

const APPROPRIATION_TYPES = [
    ['ORIGINAL', 'Original Appropriation'],
    ['SUPPLEMENTARY', 'Supplementary Appropriation'],
    ['VIREMENT', 'Virement (Transfer)'],
];

const requiredMark = <span style={{ color: '#ef4444' }}>*</span>;

interface BudgetLine {
    id: string;
    economic: string;
    functional: string;
    programme: string;
    geographic: string;          // optional — LGA / zone for statistical performance reporting
    amount_approved: string;
    description: string;
}

export default function AppropriationForm() {
    const navigate = useNavigate();
    const createAppropriation = useCreateAppropriation();
    const { data: segments, isLoading: segsLoading } = useNCoASegments();
    const { data: fiscalYears } = useFiscalYears();

    const [formError, setFormError] = useState('');
    const [saveSuccess, setSaveSuccess] = useState('');
    const [isSaving, setIsSaving] = useState(false);

    const [header, setHeader] = useState({
        fiscal_year: '', administrative: '', fund: '',
        appropriation_type: 'ORIGINAL', law_reference: '', enactment_date: '',
    });

    const [lines, setLines] = useState<BudgetLine[]>([
        { id: '1', economic: '', functional: '', programme: '', geographic: '', amount_approved: '', description: '' },
    ]);

    const setH = (field: string, value: string) => setHeader(prev => ({ ...prev, [field]: value }));

    const updateLine = (id: string, field: keyof BudgetLine, value: string) => {
        setLines(prev => prev.map(l => l.id === id ? { ...l, [field]: value } : l));
    };

    const addLine = () => {
        setLines(prev => [...prev, {
            id: String(Date.now()), economic: '', functional: '', programme: '',
            geographic: '', amount_approved: '', description: '',
        }]);
    };

    const removeLine = (id: string) => {
        if (lines.length <= 1) return;
        setLines(prev => prev.filter(l => l.id !== id));
    };

    const totalAmount = lines.reduce((s, l) => s + (parseFloat(l.amount_approved) || 0), 0);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError(''); setSaveSuccess('');

        if (!header.fiscal_year || !header.administrative || !header.fund) {
            setFormError('Fiscal Year, MDA, and Fund are required');
            return;
        }
        const emptyLines = lines.filter(l => !l.economic || !l.amount_approved);
        if (emptyLines.length > 0) {
            setFormError('All lines must have an Economic Code and Amount');
            return;
        }

        setIsSaving(true);
        let created = 0;
        const errors: string[] = [];

        for (const line of lines) {
            try {
                await createAppropriation.mutateAsync({
                    fiscal_year: parseInt(header.fiscal_year),
                    administrative: parseInt(header.administrative),
                    economic: parseInt(line.economic),
                    functional: parseInt(line.functional) || null,
                    programme: parseInt(line.programme) || null,
                    geographic: parseInt(line.geographic) || null,   // optional statistical dim
                    fund: parseInt(header.fund),
                    amount_approved: line.amount_approved,
                    appropriation_type: header.appropriation_type,
                    law_reference: header.law_reference,
                    enactment_date: header.enactment_date || null,
                    description: line.description,
                });
                created++;
            } catch (err: any) {
                const d = err.response?.data;
                const msg = d?.detail || d?.non_field_errors?.[0] || JSON.stringify(d) || 'Error';
                const econName = economicList.find((s: any) => String(s.id) === line.economic)?.name || line.economic;
                errors.push(`${econName}: ${msg}`);
            }
        }

        setIsSaving(false);
        if (created > 0) {
            setSaveSuccess(`${created} appropriation line(s) created`);
            if (errors.length === 0) setTimeout(() => navigate('/budget/appropriations'), 1500);
        }
        if (errors.length > 0) setFormError(errors.join(' | '));
    };

    const economicList = segments?.economic || [];
    const functionalList = segments?.functional || [];
    const programmeList = segments?.programme || [];
    const geographicList = segments?.geographic || [];

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Budget Appropriation Entry"
                    subtitle="Enter expenditure and revenue budget lines per MDA — multiple lines per submission"
                    icon={<Calendar size={22} />}
                    backButton={true}
                />

                {/* Messages */}
                {formError && (
                    <div style={{
                        padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem',
                        background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
                        color: '#ef4444', fontSize: 'var(--text-sm)',
                        display: 'flex', alignItems: 'center', gap: '0.5rem',
                    }}>
                        <AlertCircle size={15} /> {formError}
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

                <form onSubmit={handleSubmit}>
                    {/* Budget Header */}
                    <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                        <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Calendar size={15} color="var(--color-primary)" />
                            Budget Header
                        </h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem', marginBottom: '0.75rem' }}>
                            <div>
                                <label style={lblStyle}>Fiscal Year {requiredMark}</label>
                                <select value={header.fiscal_year} onChange={e => setH('fiscal_year', e.target.value)} style={selectStyle} required>
                                    <option value="">Select year...</option>
                                    {(fiscalYears || []).map((fy: any) => <option key={fy.id} value={fy.id}>{fy.name || `FY ${fy.year}`}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={lblStyle}>Administrative (MDA) {requiredMark}</label>
                                <SearchableSelect
                                    options={(segments?.administrative || []).map((s: any) => ({
                                        value: String(s.id), label: `${s.code} - ${s.name}`, sublabel: s.mda_type || s.level,
                                    }))}
                                    value={header.administrative}
                                    onChange={v => setH('administrative', v)}
                                    placeholder="Type MDA name or code..."
                                    required
                                />
                            </div>
                            <div>
                                <label style={lblStyle}>Fund Source {requiredMark}</label>
                                <select value={header.fund} onChange={e => setH('fund', e.target.value)} style={selectStyle} required>
                                    <option value="">Select fund...</option>
                                    {(segments?.fund || []).map((s: any) => <option key={s.id} value={s.id}>{s.code} - {s.name}</option>)}
                                </select>
                            </div>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
                            <div>
                                <label style={lblStyle}>Appropriation Type</label>
                                <select value={header.appropriation_type} onChange={e => setH('appropriation_type', e.target.value)} style={selectStyle}>
                                    {APPROPRIATION_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={lblStyle}>Law / Act Reference</label>
                                <input style={{ ...inputStyle, textAlign: 'left' }} value={header.law_reference} onChange={e => setH('law_reference', e.target.value)} placeholder="Appropriation Act 2026" />
                            </div>
                            <div>
                                <label style={lblStyle}>Enactment Date</label>
                                <input style={{ ...inputStyle, textAlign: 'left' }} type="date" value={header.enactment_date} onChange={e => setH('enactment_date', e.target.value)} />
                            </div>
                        </div>

                        {/* Control info */}
                        <div style={{
                            marginTop: '0.75rem', padding: '0.5rem 0.75rem', borderRadius: '6px',
                            background: 'rgba(25, 30, 106, 0.04)', border: '1px solid rgba(25, 30, 106, 0.1)',
                            fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)',
                            display: 'flex', gap: '1.5rem',
                        }}>
                            <span><strong style={{ color: '#dc2626' }}>Expenditure (2x):</strong> HARD STOP</span>
                            <span><strong style={{ color: '#166534' }}>Revenue (1x):</strong> Statistical</span>
                            <span><strong style={{ color: '#1e40af' }}>Asset (3x):</strong> HARD STOP</span>
                        </div>
                    </div>

                    {/* Budget Lines */}
                    <div className="glass-card" style={{ overflow: 'hidden' }}>
                        <div style={{
                            padding: '1rem 1.5rem',
                            borderBottom: '1px solid var(--color-border)',
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        }}>
                            <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text)', margin: 0 }}>
                                Budget Lines ({lines.length})
                            </h3>
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                                <button type="button" onClick={addLine} style={{
                                    display: 'flex', alignItems: 'center', gap: '0.25rem',
                                    padding: '0.5rem 0.75rem', borderRadius: '6px',
                                    border: '1px dashed var(--color-border)',
                                    background: 'transparent', color: 'var(--color-primary, #191e6a)',
                                    cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 500,
                                }}>
                                    <Plus size={14} /> Add Line
                                </button>
                            </div>
                        </div>

                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '1100px' }}>
                                <thead>
                                    <tr style={{ borderBottom: '2px solid var(--color-border)' }}>
                                        <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '260px' }}>Economic Code (Account) {requiredMark}</th>
                                        <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '180px' }}>Function (COFOG)</th>
                                        <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '180px' }}>Programme</th>
                                        <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '200px' }}>
                                            Geography (LGA / Zone)
                                            <div style={{ fontSize: '0.6rem', fontWeight: 500, color: 'var(--color-text-muted)', textTransform: 'none', letterSpacing: 0, marginTop: '2px' }}>
                                                Optional — enables geographic distribution report
                                            </div>
                                        </th>
                                        <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', width: '160px' }}>Amount (NGN) {requiredMark}</th>
                                        <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)' }}>Description</th>
                                        <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center', width: '50px' }}></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {lines.length > 0 ? lines.map((line, index) => {
                                        const selectedEcon = economicList.find((s: any) => String(s.id) === line.economic);
                                        const isRevenue = selectedEcon?.code?.startsWith('1');
                                        return (
                                            <tr key={line.id} style={{
                                                borderBottom: '1px solid var(--color-border)',
                                                animation: `fadeIn 0.3s ease-out ${index * 0.03}s both`,
                                            }}>
                                                <td style={{ padding: '0.5rem 1rem' }}>
                                                    <select value={line.economic} onChange={e => updateLine(line.id, 'economic', e.target.value)}
                                                        style={{ ...selectStyle, borderColor: isRevenue ? 'rgba(22,163,74,0.5)' : '' }}>
                                                        <option value="">Select account...</option>
                                                        {economicList.map((s: any) => <option key={s.id} value={s.id}>{s.code} - {s.name}</option>)}
                                                    </select>
                                                    {isRevenue && (
                                                        <div style={{ fontSize: '0.6rem', color: '#166534', fontWeight: 600, marginTop: '0.15rem' }}>
                                                            REVENUE — statistical only
                                                        </div>
                                                    )}
                                                </td>
                                                <td style={{ padding: '0.5rem 0.5rem' }}>
                                                    <select value={line.functional} onChange={e => updateLine(line.id, 'functional', e.target.value)} style={selectStyle}>
                                                        <option value="">Optional</option>
                                                        {functionalList.map((s: any) => <option key={s.id} value={s.id}>{s.code} - {s.name}</option>)}
                                                    </select>
                                                </td>
                                                <td style={{ padding: '0.5rem 0.5rem' }}>
                                                    <select value={line.programme} onChange={e => updateLine(line.id, 'programme', e.target.value)} style={selectStyle}>
                                                        <option value="">Optional</option>
                                                        {programmeList.map((s: any) => <option key={s.id} value={s.id}>{s.code} - {s.name}</option>)}
                                                    </select>
                                                </td>
                                                <td style={{ padding: '0.5rem 0.5rem' }}>
                                                    <select value={line.geographic} onChange={e => updateLine(line.id, 'geographic', e.target.value)} style={selectStyle}>
                                                        <option value="">— Statewide —</option>
                                                        {geographicList.map((s: any) => (
                                                            <option key={s.id} value={s.id}>{s.code} - {s.name}</option>
                                                        ))}
                                                    </select>
                                                </td>
                                                <td style={{ padding: '0.5rem 0.5rem' }}>
                                                    <input type="number" step="0.01" min="0.01"
                                                        value={line.amount_approved}
                                                        onChange={e => updateLine(line.id, 'amount_approved', e.target.value)}
                                                        style={{ ...inputStyle, fontWeight: 600 }}
                                                        placeholder="0.00"
                                                    />
                                                </td>
                                                <td style={{ padding: '0.5rem 0.5rem' }}>
                                                    <input value={line.description} onChange={e => updateLine(line.id, 'description', e.target.value)}
                                                        style={{ ...inputStyle, textAlign: 'left' }} placeholder="Line description" />
                                                </td>
                                                <td style={{ padding: '0.5rem 0.5rem', textAlign: 'center' }}>
                                                    {lines.length > 1 && (
                                                        <button type="button" onClick={() => removeLine(line.id)} style={{
                                                            padding: '0.25rem', borderRadius: '4px', border: 'none',
                                                            background: 'rgba(239,68,68,0.1)', color: '#ef4444',
                                                            cursor: 'pointer', display: 'inline-flex', alignItems: 'center',
                                                        }}>
                                                            <X size={14} />
                                                        </button>
                                                    )}
                                                </td>
                                            </tr>
                                        );
                                    }) : (
                                        <tr>
                                            <td colSpan={7} style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                                <FileSpreadsheet size={40} style={{ margin: '0 auto 0.75rem', opacity: 0.4, display: 'block' }} />
                                                <p style={{ margin: 0 }}>Click "Add Line" to begin entering budget lines.</p>
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                                {lines.length > 0 && (
                                    <tfoot>
                                        <tr style={{ borderTop: '2px solid var(--color-border)' }}>
                                            <td colSpan={4} style={{ padding: '0.75rem 1rem', fontWeight: 700, fontSize: 'var(--text-sm)' }}>
                                                Total ({lines.length} lines)
                                            </td>
                                            <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-base)', color: 'var(--color-primary, #191e6a)' }}>
                                                {'\u20A6'}{totalAmount.toLocaleString('en-NG', { minimumFractionDigits: 2 })}
                                            </td>
                                            <td colSpan={2}></td>
                                        </tr>
                                    </tfoot>
                                )}
                            </table>
                        </div>
                    </div>

                    {/* Actions */}
                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '1.25rem' }}>
                        <button type="button" onClick={() => navigate(-1)} className="glass-button" style={{
                            display: 'flex', alignItems: 'center', gap: '0.375rem',
                            padding: '0.625rem 1.25rem', borderRadius: '8px',
                            border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                            color: 'var(--color-text)', cursor: 'pointer', fontWeight: 500, fontSize: 'var(--text-sm)',
                        }}>
                            Cancel
                        </button>
                        <button type="submit" disabled={isSaving} style={{
                            display: 'flex', alignItems: 'center', gap: '0.375rem',
                            padding: '0.625rem 1.25rem', borderRadius: '8px',
                            border: 'none',
                            background: 'linear-gradient(135deg, var(--primary, #191e6a) 0%, var(--primary-dark, #0f1240) 100%)',
                            color: 'white', cursor: 'pointer', fontWeight: 600, fontSize: 'var(--text-sm)',
                            boxShadow: '0 4px 12px rgba(15, 18, 64, 0.3)',
                            opacity: isSaving ? 0.7 : 1,
                        }}>
                            <Save size={16} /> {isSaving ? 'Saving...' : `Save ${lines.length} Line(s)`}
                        </button>
                    </div>
                </form>
            </main>
        </div>
    );
}
