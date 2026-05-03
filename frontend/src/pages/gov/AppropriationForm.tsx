/**
 * Appropriation / Budget Entry — Quot PSE
 * Route: /budget/appropriations/new
 *
 * Glassmorphism-styled spreadsheet budget entry:
 * - Header: Fiscal Year, MDA, Fund, Type, Law Reference
 * - Lines: Economic Code + Amount per line (add/remove rows)
 * - Auto-detects control level from account type
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, AlertCircle, Plus, X, FileSpreadsheet, Calendar, Info } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import SearchableSelect from '../../components/SearchableSelect';
import {
    useCreateAppropriation, useNCoASegments, useFiscalYears,
    useAppropriationsList,
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
    // Business rule: one active Appropriation per (MDA, Economic, Fund, FiscalYear).
    // We pre-load ACTIVE appropriations so the Economic-code dropdown can mark
    // codes already taken for the selected header, steering users to
    // Supplementary / Virement instead of attempting a duplicate.
    const { data: existingAppropriations = [] } = useAppropriationsList();

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

        // Guard: ORIGINAL appropriations cannot duplicate an existing
        // (MDA, Economic, Fund, FY) tuple. Route the user to Supplementary
        // or Virement before hitting the API.
        if (header.appropriation_type === 'ORIGINAL') {
            const clashes = lines
                .filter(l => l.economic && takenEconomicIds.has(Number(l.economic)))
                .map(l => {
                    const s = economicList.find((seg: any) => String(seg.id) === l.economic);
                    return s ? `${s.code} - ${s.name}` : l.economic;
                });
            if (clashes.length > 0) {
                setFormError(
                    `Cannot create ORIGINAL appropriations for already-appropriated code(s): ` +
                    `${clashes.join(', ')}. Switch Appropriation Type to ` +
                    `Supplementary Appropriation or Virement to adjust the existing line(s).`,
                );
                return;
            }
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

    // Pre-shape option lists for SearchableSelect once — these are global to
    // the tenant, not per-line, so we don't want to rebuild them on every
    // line render. Sorted by code (numeric-aware) for predictable UX.
    const sortByCode = (a: any, b: any) =>
        (a.code ?? '').localeCompare(b.code ?? '', undefined, { numeric: true });

    const fiscalYearOptions = useMemo(() =>
        (fiscalYears || []).map((fy: any) => ({
            value: String(fy.id),
            label: fy.name || `FY ${fy.year}`,
            sublabel: fy.status,
        })),
    [fiscalYears]);

    const fundOptions = useMemo(() =>
        [...(segments?.fund || [])].sort(sortByCode).map((s: any) => ({
            value: String(s.id),
            label: `${s.code} - ${s.name}`,
            sublabel: s.code,
        })),
    [segments?.fund]);

    const appropriationTypeOptions = useMemo(() =>
        APPROPRIATION_TYPES.map(([v, l]: [string, string]) => ({
            value: v, label: l,
        })),
    []);

    const functionalOptions = useMemo(() =>
        [...functionalList].sort(sortByCode).map((s: any) => ({
            value: String(s.id), label: `${s.code} - ${s.name}`, sublabel: s.code,
        })),
    [functionalList]);

    const programmeOptions = useMemo(() =>
        [...programmeList].sort(sortByCode).map((s: any) => ({
            value: String(s.id), label: `${s.code} - ${s.name}`, sublabel: s.code,
        })),
    [programmeList]);

    const geographicOptions = useMemo(() =>
        [...geographicList].sort(sortByCode).map((s: any) => ({
            value: String(s.id), label: `${s.code} - ${s.name}`, sublabel: s.code,
        })),
    [geographicList]);

    /**
     * Economic-segment ids already covered by an ACTIVE Appropriation for
     * the selected (MDA, Fund, FY) header. Users cannot create another
     * ORIGINAL line for these — they must use Supplementary / Virement.
     */
    const takenEconomicIds = useMemo(() => {
        if (!header.fiscal_year || !header.administrative || !header.fund) {
            return new Set<number>();
        }
        const fy = parseInt(header.fiscal_year);
        const mda = parseInt(header.administrative);
        const fund = parseInt(header.fund);
        return new Set(
            existingAppropriations
                .filter((a: any) =>
                    a.status === 'ACTIVE' &&
                    Number(a.fiscal_year) === fy &&
                    Number(a.administrative) === mda &&
                    Number(a.fund) === fund,
                )
                .map((a: any) => Number(a.economic)),
        );
    }, [header.fiscal_year, header.administrative, header.fund, existingAppropriations]);

    // For banners / hints, map each taken economic id → its existing appropriation row
    const takenEconomicById = useMemo(() => {
        const m = new Map<number, any>();
        if (!header.fiscal_year || !header.administrative || !header.fund) return m;
        const fy = parseInt(header.fiscal_year);
        const mda = parseInt(header.administrative);
        const fund = parseInt(header.fund);
        for (const a of existingAppropriations) {
            if (
                a.status === 'ACTIVE' &&
                Number(a.fiscal_year) === fy &&
                Number(a.administrative) === mda &&
                Number(a.fund) === fund
            ) m.set(Number(a.economic), a);
        }
        return m;
    }, [header.fiscal_year, header.administrative, header.fund, existingAppropriations]);

    const isOriginalType = header.appropriation_type === 'ORIGINAL';

    const linesWithClash = lines.filter(
        l => l.economic && takenEconomicIds.has(Number(l.economic)) && isOriginalType,
    );

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

                {/* Rule banner: when the selected header has existing appropriations */}
                {header.fiscal_year && header.administrative && header.fund && takenEconomicIds.size > 0 && (
                    <div style={{
                        padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem',
                        background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.25)',
                        color: '#1e40af', fontSize: 'var(--text-sm)',
                        display: 'flex', alignItems: 'flex-start', gap: '0.5rem',
                    }}>
                        <Info size={16} style={{ marginTop: '2px', flexShrink: 0 }} />
                        <div>
                            <b>{takenEconomicIds.size}</b> economic code(s) already have an active
                            appropriation under this MDA + Fund + Fiscal Year. One active
                            appropriation is allowed per (MDA, Economic Code, Fund, FY).
                            <br />
                            To adjust an existing line, switch <b>Appropriation Type</b> to{' '}
                            <b>Supplementary Appropriation</b> (to add to the approved amount), or
                            go to{' '}
                            <a
                                href="/budget/virements/new"
                                onClick={(e) => { e.preventDefault(); navigate('/budget/virements/new'); }}
                                style={{ color: '#1e40af', fontWeight: 600, textDecoration: 'underline' }}
                            >
                                Virement (Transfer)
                            </a>{' '}
                            to move funds between existing lines.
                        </div>
                    </div>
                )}

                {linesWithClash.length > 0 && (
                    <div style={{
                        padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem',
                        background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)',
                        color: '#b91c1c', fontSize: 'var(--text-sm)',
                        display: 'flex', alignItems: 'flex-start', gap: '0.5rem',
                    }}>
                        <AlertCircle size={16} style={{ marginTop: '2px', flexShrink: 0 }} />
                        <div>
                            {linesWithClash.length} line(s) point at economic code(s) that are
                            already appropriated. Change <b>Appropriation Type</b> to
                            Supplementary / Virement, or pick a different economic code, before
                            saving.
                        </div>
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
                                <SearchableSelect
                                    options={fiscalYearOptions}
                                    value={String(header.fiscal_year || '')}
                                    onChange={v => setH('fiscal_year', v)}
                                    placeholder="Type or select fiscal year..."
                                    required
                                />
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
                                <SearchableSelect
                                    options={fundOptions}
                                    value={String(header.fund || '')}
                                    onChange={v => setH('fund', v)}
                                    placeholder="Type fund code or name..."
                                    required
                                />
                            </div>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
                            <div>
                                <label style={lblStyle}>Appropriation Type</label>
                                <SearchableSelect
                                    options={appropriationTypeOptions}
                                    value={header.appropriation_type}
                                    onChange={v => setH('appropriation_type', v)}
                                    placeholder="Select appropriation type..."
                                />
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
                                        const isTaken = !!line.economic
                                            && takenEconomicIds.has(Number(line.economic))
                                            && isOriginalType;
                                        const takenAppr = isTaken ? takenEconomicById.get(Number(line.economic)) : null;
                                        return (
                                            <tr key={line.id} style={{
                                                borderBottom: '1px solid var(--color-border)',
                                                animation: `fadeIn 0.3s ease-out ${index * 0.03}s both`,
                                                background: isTaken ? 'rgba(239,68,68,0.04)' : undefined,
                                            }}>
                                                <td style={{ padding: '0.5rem 1rem' }}>
                                                    {/* Per-line economic options — recomputed cheaply each
                                                        render because the "already-appropriated" annotation
                                                        depends on isOriginalType + takenEconomicIds, which
                                                        change as the user adds lines or switches type. The
                                                        annotation goes into the label so the user sees the
                                                        warning while typing in the searchable picker; the
                                                        downstream "switch to Supplementary" hint below
                                                        still fires on isTaken. */}
                                                    <SearchableSelect
                                                        options={[...economicList]
                                                            .sort(sortByCode)
                                                            .map((s: any) => {
                                                                const taken = isOriginalType && takenEconomicIds.has(Number(s.id));
                                                                return {
                                                                    value: String(s.id),
                                                                    label: `${s.code} - ${s.name}${taken ? '  (already appropriated)' : ''}`,
                                                                    sublabel: s.code,
                                                                };
                                                            })}
                                                        value={String(line.economic || '')}
                                                        onChange={v => updateLine(line.id, 'economic', v)}
                                                        placeholder="Type code or name..."
                                                        style={{
                                                            borderColor: isTaken
                                                                ? 'rgba(239,68,68,0.6)'
                                                                : isRevenue ? 'rgba(22,163,74,0.5)' : '',
                                                        }}
                                                    />
                                                    {isRevenue && !isTaken && (
                                                        <div style={{ fontSize: '0.6rem', color: '#166534', fontWeight: 600, marginTop: '0.15rem' }}>
                                                            REVENUE — statistical only
                                                        </div>
                                                    )}
                                                    {isTaken && takenAppr && (
                                                        <div style={{ fontSize: '0.6rem', color: '#ef4444', fontWeight: 600, marginTop: '0.25rem', lineHeight: 1.3 }}>
                                                            Already appropriated NGN {Number(takenAppr.amount_approved || 0).toLocaleString('en-NG', { minimumFractionDigits: 2 })}.
                                                            Switch Type to <b>Supplementary</b> or <b>Virement</b> to adjust.
                                                        </div>
                                                    )}
                                                </td>
                                                <td style={{ padding: '0.5rem 0.5rem' }}>
                                                    <SearchableSelect
                                                        options={functionalOptions}
                                                        value={String(line.functional || '')}
                                                        onChange={v => updateLine(line.id, 'functional', v)}
                                                        placeholder="Optional — type code or name..."
                                                    />
                                                </td>
                                                <td style={{ padding: '0.5rem 0.5rem' }}>
                                                    <SearchableSelect
                                                        options={programmeOptions}
                                                        value={String(line.programme || '')}
                                                        onChange={v => updateLine(line.id, 'programme', v)}
                                                        placeholder="Optional — type code or name..."
                                                    />
                                                </td>
                                                <td style={{ padding: '0.5rem 0.5rem' }}>
                                                    <SearchableSelect
                                                        options={geographicOptions}
                                                        value={String(line.geographic || '')}
                                                        onChange={v => updateLine(line.id, 'geographic', v)}
                                                        placeholder="— Statewide —"
                                                    />
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
