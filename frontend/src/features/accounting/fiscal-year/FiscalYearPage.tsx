import React, { useState, useEffect } from 'react';
import { Lock as LockIcon, Unlock, Users, ChevronDown, ChevronRight, Check, Plus, Calendar, Zap, Eye, AlertTriangle } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useFiscalYears, useFiscalPeriods, useCreateFiscalYear, useCloseFiscalYear, useSetActiveFiscalYear, useClosePeriods, useReopenPeriod, useGrantPeriodAccess } from '../hooks/useFiscalYear';
import apiClient from '../../../api/client';
import SettingsLayout from '../../settings/SettingsLayout';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import logger from '../../../utils/logger';
import '../styles/glassmorphism.css';

const inp: React.CSSProperties = {
    width: '100%',
    padding: '0.4rem 0.5rem',
    borderRadius: '6px',
    border: '1px solid var(--color-border)',
    background: 'var(--color-surface)',
    color: 'var(--color-text)',
    fontSize: 'var(--text-xs)',
};

const lbl: React.CSSProperties = {
    display: 'block',
    fontSize: '0.65rem',
    fontWeight: 600,
    color: 'var(--color-text-muted)',
    marginBottom: '0.25rem',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.04em',
};

// ─── Month helpers ────────────────────────────────────────────────────────────
const MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];

const pad = (n: number) => String(n).padStart(2, '0');

/** Compute 12 monthly periods for a given year, pure client-side. */
const generateMonthlyPeriods = (year: number) =>
    MONTH_NAMES.map((name, i) => {
        const month = i + 1;
        const lastDay = new Date(year, month, 0).getDate(); // JS trick: day 0 = last day of prev month
        return {
            period_number: month,
            name,
            start_date: `${year}-${pad(month)}-01`,
            end_date: `${year}-${pad(month)}-${pad(lastDay)}`,
        };
    });

type PreviewPeriod = ReturnType<typeof generateMonthlyPeriods>[number];

export default function FiscalYearPage() {
    const [showCloseModal, setShowCloseModal] = useState(false);
    const [showReopenModal, setShowReopenModal] = useState(false);
    const [showAccessModal, setShowAccessModal] = useState(false);
    const [selectedYear, setSelectedYear] = useState<any>(null);
    const [selectedPeriod, setSelectedPeriod] = useState<any>(null);
    const [expandedYears, setExpandedYears] = useState<number[]>([]);
    const [users, setUsers] = useState<any[]>([]);

    // ─── Fiscal Year Availability (SAP-style max 2 open) ────────────────────
    const { data: availability, refetch: refetchAvailability } = useQuery({
        queryKey: ['fiscal-year-availability'],
        queryFn: async () => {
            const res = await apiClient.get('/accounting/fiscal-years/next_available/');
            return res.data as {
                next_year: number;
                open_years: number[];
                open_count: number;
                max_open_years: number;
                must_close_year: number | null;
                can_create: boolean;
            };
        },
        staleTime: 10_000,
    });

    // ─── Two-step Create flow ─────────────────────────────────────────────────
    const nextYear = availability?.next_year || new Date().getFullYear();
    const canCreate = availability?.can_create ?? true;
    const mustCloseYear = availability?.must_close_year;
    const openYears = availability?.open_years || [];
    const maxOpenYears = availability?.max_open_years || 2;

    const [createData, setCreateData] = useState({
        year: nextYear,
        name: `FY ${nextYear}`,
        period_type: 'Monthly',
    });
    const [previewPeriods, setPreviewPeriods] = useState<PreviewPeriod[] | null>(null);
    const [createError, setCreateError] = useState('');

    // Auto-update year when availability data loads
    useEffect(() => {
        if (availability) {
            setCreateData(prev => ({
                ...prev,
                year: availability.next_year,
                name: `FY ${availability.next_year}`,
            }));
        }
    }, [availability]);

    const handleCreateChange = (field: string, value: string | number) => {
        const updated = { ...createData, [field]: value };
        if (field === 'year') {
            const yr = Number(value);
            if (yr >= 1000 && yr <= 9999) {
                updated.name = `FY ${yr}`;
            }
        }
        setCreateData(updated as typeof createData);
        setPreviewPeriods(null);
        setCreateError('');
    };

    /** Step 1: Generate period preview (pure client-side) */
    const handleGenerate = () => {
        const yr = Number(createData.year);
        if (yr < 1000 || yr > 9999) {
            setCreateError('Please enter a valid 4-digit year.');
            return;
        }
        setCreateError('');
        if (createData.period_type === 'Monthly') {
            setPreviewPeriods(generateMonthlyPeriods(yr));
        } else {
            // For daily/yearly just show a simple summary — still let them create
            setPreviewPeriods([]);
        }
    };

    /** Step 2: Actually create the fiscal year via API */
    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        setCreateError('');
        const yr = Number(createData.year);
        const payload = {
            year: yr,
            name: createData.name || `FY ${yr}`,
            start_date: `${yr}-01-01`,
            end_date: `${yr}-12-31`,
            period_type: createData.period_type,
        };
        try {
            await createFiscalYear.mutateAsync(payload);
            setPreviewPeriods(null);
            // Refetch availability to get the NEXT year
            refetchAvailability();
        } catch (error: any) {
            const msg = error?.response?.data?.error || error?.response?.data?.detail || JSON.stringify(error?.response?.data) || 'Failed to create fiscal year.';
            setCreateError(String(msg));
        }
    };

    const [closeData, setCloseData] = useState({ close_type: 'monthly', target_date: '', reason: '' });
    const [reopenData, setReopenData] = useState({ reason: '' });
    const [accessData, setAccessData] = useState({
        user_id: '', access_type: 'Temporary', start_date: '', end_date: '', reason: '',
    });

    const { data: fiscalYears, isLoading } = useFiscalYears({});
    const { data: fiscalPeriods } = useFiscalPeriods({});
    const createFiscalYear = useCreateFiscalYear();
    const closeFiscalYear = useCloseFiscalYear();
    const setActiveFiscalYear = useSetActiveFiscalYear();
    const closePeriods = useClosePeriods();
    const reopenPeriod = useReopenPeriod();
    const grantAccess = useGrantPeriodAccess();

    const toggleYearExpand = (year: number) =>
        setExpandedYears(prev =>
            prev.includes(year) ? prev.filter(y => y !== year) : [...prev, year]
        );

    const handleCloseYear = async () => {
        if (!selectedYear) return;
        try {
            await closeFiscalYear.mutateAsync({ id: selectedYear.id, reason: closeData.reason });
            setShowCloseModal(false);
            setSelectedYear(null);
        } catch (error) { logger.error('Failed to close fiscal year:', error); }
    };

    const handleClosePeriods = async () => {
        try {
            await closePeriods.mutateAsync(closeData);
            setShowCloseModal(false);
        } catch (error) { logger.error('Failed to close periods:', error); }
    };

    const handleReopenPeriod = async () => {
        if (!selectedPeriod) return;
        try {
            await reopenPeriod.mutateAsync({ id: selectedPeriod.id, reason: reopenData.reason });
            setShowReopenModal(false);
            setSelectedPeriod(null);
        } catch (error) { logger.error('Failed to reopen period:', error); }
    };

    const fetchUsers = async () => {
        try {
            const response = await apiClient.get('/core/users/', { params: { page_size: 100 } });
            setUsers(response.data.results || response.data);
        } catch (error) { logger.error('Failed to fetch users:', error); }
    };

    const handleOpenAccessModal = (period: any) => {
        setSelectedPeriod(period);
        fetchUsers();
        setShowAccessModal(true);
    };

    const [accessMsg, setAccessMsg] = useState('');
    const handleGrantAccess = async () => {
        if (!selectedPeriod) return;
        try {
            await grantAccess.mutateAsync({ periodId: selectedPeriod.id, accessData });
            setShowAccessModal(false);
            setSelectedPeriod(null);
            setAccessData({ user_id: '', access_type: 'Temporary', start_date: '', end_date: '', reason: '' });
            setAccessMsg('Period access granted successfully.');
            setTimeout(() => setAccessMsg(''), 3000);
        } catch (error: any) {
            const msg = error?.response?.data?.error || error?.response?.data?.detail || 'Failed to grant access.';
            setAccessMsg(msg);
            setTimeout(() => setAccessMsg(''), 4000);
        }
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'Open': return 'var(--color-success)';
            case 'Closed': return 'var(--color-error)';
            case 'Locked': return 'var(--color-warning)';
            default: return 'var(--color-text-muted)';
        }
    };

    const getPeriodsForYear = (year: number) =>
        fiscalPeriods?.filter((p: any) => p.fiscal_year === year) || [];

    if (isLoading) return <LoadingScreen message="Loading fiscal years..." />;

    // ─── Preview table colours ────────────────────────────────────────────────
    const QUARTER_COLORS: Record<number, string> = {
        1: '#eff6ff', 2: '#eff6ff', 3: '#eff6ff',   // Q1 – blue
        4: '#f0fdf4', 5: '#f0fdf4', 6: '#f0fdf4',   // Q2 – green
        7: '#fff7ed', 8: '#fff7ed', 9: '#fff7ed',   // Q3 – amber
        10: '#fdf4ff', 11: '#fdf4ff', 12: '#fdf4ff', // Q4 – purple
    };
    const QUARTER_LABELS: Record<number, string> = { 1: 'Q1', 4: 'Q2', 7: 'Q3', 10: 'Q4' };

    return (
        <SettingsLayout>
            <div>
                <PageHeader
                    title="Fiscal Year Management"
                    subtitle="Create and manage fiscal years, close periods, and control access."
                    icon={<Calendar size={22} />}
                    backButton={false}
                />

                {/* ─── Stats ──────────────────────────────────────────────────── */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
                    <div className="card" style={{ borderLeft: '4px solid var(--color-success)' }}>
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Active Year</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{fiscalYears?.find((y: any) => y.is_active)?.year || 'None'}</p>
                    </div>
                    <div className="card" style={{ borderLeft: '4px solid var(--color-primary)' }}>
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Open Years</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>
                            {openYears.length} / {maxOpenYears}
                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginLeft: '0.5rem' }}>
                                {openYears.length > 0 ? `(${openYears.join(', ')})` : ''}
                            </span>
                        </p>
                    </div>
                    <div className="card" style={{ borderLeft: '4px solid var(--color-success)' }}>
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Open Periods</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{fiscalPeriods?.filter((p: any) => p.status === 'Open').length || 0}</p>
                    </div>
                    <div className="card" style={{ borderLeft: '4px solid var(--color-error)' }}>
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Next Year</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{nextYear}</p>
                    </div>
                </div>

                {/* ─── Max Open Years Warning ───────────────────────────────── */}
                {!canCreate && mustCloseYear && (
                    <div style={{
                        background: '#fffbeb', border: '1px solid #fbbf24', borderRadius: '0.5rem',
                        padding: '0.75rem 1rem', marginBottom: '1.25rem',
                        display: 'flex', alignItems: 'center', gap: '0.5rem',
                    }}>
                        <AlertTriangle size={16} color="#b45309" />
                        <span style={{ fontSize: '0.8rem', color: '#92400e' }}>
                            <strong>Maximum {maxOpenYears} fiscal years can be open simultaneously.</strong>{' '}
                            Close fiscal year <strong>{mustCloseYear}</strong> before opening {nextYear}.
                        </span>
                    </div>
                )}

                {/* ─── New Fiscal Year (two-step) ──────────────────────────────── */}
                <div className="glass-card" style={{ padding: '1.25rem', marginBottom: '1.5rem', opacity: canCreate ? 1 : 0.5, pointerEvents: canCreate ? 'auto' : 'none' }}>
                    <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Calendar size={15} color="var(--color-primary)" />
                        New Fiscal Year — {nextYear}
                    </h3>

                    <form onSubmit={handleCreate}>
                        {/* ── Step 1: Year, Name, Period Type, Generate ── */}
                        <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr 200px auto', gap: '0.75rem', alignItems: 'end', marginBottom: '0.75rem' }}>
                            <div>
                                <label style={lbl}>Year <span style={{ color: '#ef4444' }}>*</span></label>
                                <input
                                    type="number"
                                    style={{ ...inp, background: '#f1f5f9', fontWeight: 700 }}
                                    value={createData.year}
                                    readOnly
                                    title={`Next available year (auto-calculated). ${!canCreate ? `Close ${mustCloseYear} first.` : ''}`}
                                />
                            </div>
                            <div>
                                <label style={lbl}>Name <span style={{ color: '#ef4444' }}>*</span></label>
                                <input
                                    type="text"
                                    style={inp}
                                    value={createData.name}
                                    placeholder="e.g. FY 2026"
                                    onChange={(e) => handleCreateChange('name', e.target.value)}
                                    required
                                />
                            </div>
                            <div>
                                <label style={lbl}>Period Type <span style={{ color: '#ef4444' }}>*</span></label>
                                <select style={inp} value={createData.period_type} onChange={(e) => handleCreateChange('period_type', e.target.value)}>
                                    <option value="Monthly">Monthly (12 periods)</option>
                                    <option value="Daily">Daily (365 periods)</option>
                                    <option value="Yearly">Yearly (1 period)</option>
                                </select>
                            </div>
                            <div>
                                <button
                                    type="button"
                                    onClick={handleGenerate}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: '0.375rem',
                                        padding: '0.45rem 1rem',
                                        background: previewPeriods !== null ? '#f0fdf4' : 'var(--color-primary)',
                                        color: previewPeriods !== null ? '#15803d' : '#fff',
                                        border: previewPeriods !== null ? '1.5px solid #86efac' : 'none',
                                        borderRadius: '6px',
                                        fontSize: 'var(--text-xs)',
                                        fontWeight: 600,
                                        cursor: 'pointer',
                                        whiteSpace: 'nowrap',
                                    }}
                                >
                                    {previewPeriods !== null ? <><Eye size={13} /> Preview Ready</> : <><Zap size={13} /> Generate</>}
                                </button>
                            </div>
                        </div>

                        {/* ── Step 2: Period Preview Table (Monthly) ── */}
                        {previewPeriods !== null && createData.period_type === 'Monthly' && (
                            <div style={{ marginBottom: '1rem', border: '1.5px solid #c7d2fe', borderRadius: '10px', overflow: 'hidden' }}>
                                {/* Header bar */}
                                <div style={{ background: 'linear-gradient(90deg, #4f46e5 0%, #7c3aed 100%)', padding: '8px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                    <span style={{ color: '#fff', fontSize: '11px', fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                                        Preview — {previewPeriods.length} Monthly Periods for {createData.year}
                                    </span>
                                    <span style={{ color: 'rgba(255,255,255,0.75)', fontSize: '10px' }}>
                                        Start and end dates are auto-calculated ✓
                                    </span>
                                </div>

                                {/* Period grid — 4 columns (3 months each = Q1-Q4) */}
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 0 }}>
                                    {previewPeriods.map((p, idx) => (
                                        <div key={p.period_number} style={{
                                            padding: '10px 14px',
                                            background: QUARTER_COLORS[p.period_number],
                                            borderRight: (idx % 4 !== 3) ? '1px solid #e2e8f0' : 'none',
                                            borderBottom: idx < 8 ? '1px solid #e2e8f0' : 'none',
                                            position: 'relative',
                                        }}>
                                            {/* Quarter label on first of each quarter */}
                                            {QUARTER_LABELS[p.period_number] && (
                                                <span style={{
                                                    position: 'absolute', top: '6px', right: '8px',
                                                    fontSize: '9px', fontWeight: 800, color: '#94a3b8',
                                                    textTransform: 'uppercase', letterSpacing: '0.05em',
                                                }}>
                                                    {QUARTER_LABELS[p.period_number]}
                                                </span>
                                            )}
                                            <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginBottom: '3px' }}>
                                                <span style={{ fontSize: '10px', fontWeight: 800, color: '#64748b', minWidth: '18px' }}>P{p.period_number}</span>
                                                <span style={{ fontSize: '12px', fontWeight: 700, color: '#1e293b' }}>{p.name}</span>
                                            </div>
                                            <div style={{ fontSize: '10px', color: '#64748b', fontFamily: 'monospace' }}>
                                                {p.start_date} → {p.end_date}
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                {/* Footer note */}
                                <div style={{ padding: '7px 14px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', fontSize: '10px', color: '#64748b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    <Check size={11} color="#16a34a" />
                                    Creating this fiscal year will also auto-generate 12 budget periods (Jan–Dec {createData.year}) for use in Budget Management.
                                </div>
                            </div>
                        )}

                        {/* Non-monthly preview summary */}
                        {previewPeriods !== null && createData.period_type !== 'Monthly' && (
                            <div style={{ marginBottom: '1rem', padding: '10px 14px', background: '#fffbeb', border: '1.5px solid #fde68a', borderRadius: '8px', fontSize: '12px', color: '#92400e', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <Calendar size={14} />
                                <span>
                                    {createData.period_type === 'Daily'
                                        ? `365 daily periods will be created for FY ${createData.year} (Jan 1 – Dec 31).`
                                        : `1 annual period will be created for FY ${createData.year} (Jan 1 – Dec 31).`}
                                </span>
                            </div>
                        )}

                        {/* ── Create button (only shown after Generate) ── */}
                        {previewPeriods !== null && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                <button
                                    type="submit"
                                    disabled={createFiscalYear.isPending}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: '0.375rem',
                                        padding: '0.5rem 1.25rem',
                                        background: '#16a34a',
                                        color: '#fff',
                                        border: 'none',
                                        borderRadius: '6px',
                                        fontSize: 'var(--text-xs)',
                                        fontWeight: 700,
                                        cursor: createFiscalYear.isPending ? 'not-allowed' : 'pointer',
                                        opacity: createFiscalYear.isPending ? 0.7 : 1,
                                    }}
                                >
                                    <Plus size={14} />
                                    {createFiscalYear.isPending ? 'Creating…' : `Create Fiscal Year ${createData.year}`}
                                </button>
                                <button
                                    type="button"
                                    onClick={() => { setPreviewPeriods(null); setCreateError(''); }}
                                    style={{ background: 'none', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '0.45rem 0.75rem', cursor: 'pointer', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}
                                >
                                    Reset
                                </button>
                            </div>
                        )}

                        {createError && (
                            <div style={{ marginTop: '0.75rem', padding: '0.5rem 0.75rem', background: 'rgba(239,68,68,0.08)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.2)', borderRadius: '6px', fontSize: 'var(--text-xs)' }}>
                                {createError}
                            </div>
                        )}

                        {previewPeriods === null && (
                            <p style={{ margin: '0.4rem 0 0', fontSize: '0.65rem', color: 'var(--color-text-muted)' }}>
                                Enter a year and click <strong>Generate</strong> to preview all monthly periods before creating.
                            </p>
                        )}
                    </form>
                </div>

                {/* ─── Quick Actions ───────────────────────────────────────────── */}
                <div className="card" style={{ marginBottom: '2rem', padding: '1rem' }}>
                    <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: '1rem' }}>Quick Actions</h3>
                    <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                        <button className="btn btn-secondary" onClick={() => { setCloseData({ close_type: 'daily', target_date: '', reason: '' }); setShowCloseModal(true); }}>
                            <LockIcon size={16} /> Close Daily
                        </button>
                        <button className="btn btn-secondary" onClick={() => { setCloseData({ close_type: 'monthly', target_date: '', reason: '' }); setShowCloseModal(true); }}>
                            <LockIcon size={16} /> Close Monthly
                        </button>
                        <button className="btn btn-secondary" onClick={() => { setCloseData({ close_type: 'yearly', target_date: '', reason: '' }); setShowCloseModal(true); }}>
                            <LockIcon size={16} /> Close Yearly
                        </button>
                    </div>
                </div>

                {/* ─── Fiscal Years Table ──────────────────────────────────────── */}
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', width: '30px' }}></th>
                                <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Fiscal Year</th>
                                <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Period Type</th>
                                <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Periods</th>
                                <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                                <th style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {fiscalYears?.length === 0 ? (
                                <tr>
                                    <td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        No fiscal years found. Fill the form above to create one.
                                    </td>
                                </tr>
                            ) : (
                                fiscalYears?.map((year: any) => (
                                    <React.Fragment key={year.id}>
                                        <tr style={{ borderBottom: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
                                            <td style={{ padding: '1rem' }}>
                                                <button onClick={() => toggleYearExpand(year.year)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                                                    {expandedYears.includes(year.year) ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                                                </button>
                                            </td>
                                            <td style={{ padding: '1rem', fontWeight: 600 }}>FY {year.year} — {year.name}</td>
                                            <td style={{ padding: '1rem' }}>{year.period_type}</td>
                                            <td style={{ padding: '1rem' }}>{year.open_periods_count} open / {year.closed_periods_count} closed</td>
                                            <td style={{ padding: '1rem' }}>
                                                <span style={{
                                                    padding: '0.25rem 0.75rem', borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 500,
                                                    background: year.status === 'Open' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                                                    color: year.status === 'Open' ? 'var(--color-success)' : 'var(--color-error)',
                                                }}>
                                                    {year.status}
                                                </span>
                                                {year.is_active && <span style={{ marginLeft: '0.5rem', fontSize: 'var(--text-xs)', color: 'var(--color-primary)' }}>● Active</span>}
                                            </td>
                                            <td style={{ padding: '1rem' }}>
                                                {!year.is_active && year.status === 'Open' && (
                                                    <button className="btn btn-secondary" style={{ marginRight: '0.5rem', padding: '0.25rem 0.5rem', fontSize: 'var(--text-xs)' }} onClick={() => setActiveFiscalYear.mutate(year.id)}>
                                                        Set Active
                                                    </button>
                                                )}
                                                {year.status === 'Open' && (
                                                    <button className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem', fontSize: 'var(--text-xs)', color: 'var(--color-error)' }} onClick={() => { setSelectedYear(year); setShowCloseModal(true); }}>
                                                        Close Year
                                                    </button>
                                                )}
                                            </td>
                                        </tr>

                                        {/* ── Expanded period rows ── */}
                                        {expandedYears.includes(year.year) && (
                                            <tr>
                                                <td colSpan={6} style={{ padding: '0.75rem 2rem 1rem', background: 'rgba(0,0,0,0.02)' }}>
                                                    <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem', letterSpacing: '0.05em' }}>
                                                        Periods — FY {year.year}
                                                    </div>
                                                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                                        <thead>
                                                            <tr>
                                                                {['#', 'Month', 'Start Date', 'End Date', 'Status', 'Actions'].map(h => (
                                                                    <th key={h} style={{ padding: '0.4rem 0.5rem', fontSize: '10px', textTransform: 'uppercase', color: 'var(--color-text-muted)', fontWeight: 700, textAlign: 'left', letterSpacing: '0.04em' }}>{h}</th>
                                                                ))}
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            {getPeriodsForYear(year.year).map((period: any) => {
                                                                const monthName = period.period_type === 'Monthly'
                                                                    ? MONTH_NAMES[period.period_number - 1] ?? `Period ${period.period_number}`
                                                                    : `${period.period_type} ${period.period_number}`;
                                                                return (
                                                                    <tr key={period.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                                                        <td style={{ padding: '0.4rem 0.5rem', fontSize: '12px', color: '#64748b', fontFamily: 'monospace' }}>{period.period_number}</td>
                                                                        <td style={{ padding: '0.4rem 0.5rem', fontSize: '12px', fontWeight: 600 }}>{monthName}</td>
                                                                        <td style={{ padding: '0.4rem 0.5rem', fontSize: '12px' }}>{period.start_date}</td>
                                                                        <td style={{ padding: '0.4rem 0.5rem', fontSize: '12px' }}>{period.end_date}</td>
                                                                        <td style={{ padding: '0.4rem 0.5rem' }}>
                                                                            <span style={{ color: getStatusColor(period.status), fontWeight: 600, fontSize: '12px' }}>{period.status}</span>
                                                                        </td>
                                                                        <td style={{ padding: '0.4rem 0.5rem' }}>
                                                                            {period.status === 'Closed' && (
                                                                                <button className="btn btn-secondary" style={{ padding: '0.2rem 0.4rem', fontSize: '10px' }} onClick={() => { setSelectedPeriod(period); setShowReopenModal(true); }}>
                                                                                    <Unlock size={11} /> Reopen
                                                                                </button>
                                                                            )}
                                                                            {period.status === 'Open' && (
                                                                                <button className="btn btn-secondary" style={{ padding: '0.2rem 0.4rem', fontSize: '10px' }} onClick={() => handleOpenAccessModal(period)}>
                                                                                    <Users size={11} /> Access
                                                                                </button>
                                                                            )}
                                                                        </td>
                                                                    </tr>
                                                                );
                                                            })}
                                                        </tbody>
                                                    </table>
                                                </td>
                                            </tr>
                                        )}
                                    </React.Fragment>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {/* ─── Close Modal ─────────────────────────────────────────────── */}
                {showCloseModal && (
                    <div className="modal-overlay" onClick={() => setShowCloseModal(false)}>
                        <div className="modal" style={{ minWidth: '560px' }} onClick={(e) => e.stopPropagation()}>
                            <div className="modal-header">
                                <h3>Close Periods</h3>
                                <button className="btn-close" aria-label="Close" onClick={() => setShowCloseModal(false)}><span aria-hidden="true">&times;</span></button>
                            </div>
                            <div className="modal-body">
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
                                    <div>
                                        <label style={lbl}>Close Type <span style={{ color: '#ef4444' }}>*</span></label>
                                        <select style={inp} value={closeData.close_type} onChange={(e) => setCloseData({ ...closeData, close_type: e.target.value })}>
                                            <option value="daily">Daily</option>
                                            <option value="monthly">Monthly</option>
                                            <option value="yearly">Yearly</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label style={lbl}>Target {closeData.close_type === 'yearly' ? 'Year' : 'Date'} <span style={{ color: '#ef4444' }}>*</span></label>
                                        <input
                                            type={closeData.close_type === 'yearly' ? 'number' : 'date'}
                                            style={inp}
                                            value={closeData.target_date}
                                            onChange={(e) => setCloseData({ ...closeData, target_date: e.target.value })}
                                            placeholder={closeData.close_type === 'yearly' ? new Date().getFullYear().toString() : ''}
                                            required
                                        />
                                    </div>
                                </div>
                                <div>
                                    <label style={lbl}>Reason</label>
                                    <textarea style={{ ...inp, resize: 'vertical' }} value={closeData.reason} onChange={(e) => setCloseData({ ...closeData, reason: e.target.value })} rows={2} />
                                </div>
                            </div>
                            <div className="modal-footer">
                                <button type="button" className="btn btn-secondary" onClick={() => setShowCloseModal(false)}>Cancel</button>
                                <button type="button" className="btn btn-primary" onClick={selectedYear ? handleCloseYear : handleClosePeriods} disabled={closePeriods.isPending}>
                                    {closePeriods.isPending ? 'Closing...' : 'Close Periods'}
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* ─── Reopen Modal ────────────────────────────────────────────── */}
                {showReopenModal && (
                    <div className="modal-overlay" onClick={() => setShowReopenModal(false)}>
                        <div className="modal" onClick={(e) => e.stopPropagation()}>
                            <div className="modal-header">
                                <h3>Reopen Period</h3>
                                <button className="btn-close" aria-label="Close" onClick={() => setShowReopenModal(false)}><span aria-hidden="true">&times;</span></button>
                            </div>
                            <div className="modal-body">
                                <p style={{ marginBottom: '1rem' }}>
                                    Reopen period <strong>{selectedPeriod?.period_number}</strong> ({MONTH_NAMES[(selectedPeriod?.period_number ?? 1) - 1]}) of FY <strong>{selectedPeriod?.fiscal_year}</strong>
                                </p>
                                <div>
                                    <label className="form-label">Reason</label>
                                    <textarea className="input" value={reopenData.reason} onChange={(e) => setReopenData({ ...reopenData, reason: e.target.value })} rows={3} />
                                </div>
                            </div>
                            <div className="modal-footer">
                                <button type="button" className="btn btn-secondary" onClick={() => setShowReopenModal(false)}>Cancel</button>
                                <button type="button" className="btn btn-primary" onClick={handleReopenPeriod} disabled={reopenPeriod.isPending}>
                                    {reopenPeriod.isPending ? 'Reopening...' : 'Reopen Period'}
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* ─── Access Modal ────────────────────────────────────────────── */}
                {showAccessModal && (
                    <div className="modal-overlay" onClick={() => setShowAccessModal(false)}>
                        <div className="modal" style={{ minWidth: '640px' }} onClick={(e) => e.stopPropagation()}>
                            <div className="modal-header">
                                <h3>Grant Period Access</h3>
                                <button className="btn-close" aria-label="Close" onClick={() => setShowAccessModal(false)}><span aria-hidden="true">&times;</span></button>
                            </div>
                            <div className="modal-body">
                                <p style={{ marginBottom: '1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                    Granting access to period <strong style={{ color: 'var(--color-text)' }}>{selectedPeriod?.period_number}</strong> ({MONTH_NAMES[(selectedPeriod?.period_number ?? 1) - 1]}) of FY <strong style={{ color: 'var(--color-text)' }}>{selectedPeriod?.fiscal_year}</strong>
                                </p>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
                                    <div>
                                        <label style={lbl}>User <span style={{ color: '#ef4444' }}>*</span></label>
                                        <select style={inp} value={accessData.user_id} onChange={(e) => setAccessData({ ...accessData, user_id: e.target.value })}>
                                            <option value="">Select User</option>
                                            {users.map((user: any) => (
                                                <option key={user.id} value={user.id}>{user.username}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={lbl}>Access Type <span style={{ color: '#ef4444' }}>*</span></label>
                                        <select style={inp} value={accessData.access_type} onChange={(e) => setAccessData({ ...accessData, access_type: e.target.value })}>
                                            <option value="Temporary">Temporary</option>
                                            <option value="Permanent">Permanent</option>
                                        </select>
                                    </div>
                                </div>
                                {accessData.access_type === 'Temporary' && (
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
                                        <div>
                                            <label style={lbl}>Access From <span style={{ color: '#ef4444' }}>*</span></label>
                                            <input type="date" style={inp} value={accessData.start_date} onChange={(e) => setAccessData({ ...accessData, start_date: e.target.value })} />
                                        </div>
                                        <div>
                                            <label style={lbl}>Access Until <span style={{ color: '#ef4444' }}>*</span></label>
                                            <input type="datetime-local" style={inp} value={accessData.end_date} onChange={(e) => setAccessData({ ...accessData, end_date: e.target.value })} />
                                        </div>
                                    </div>
                                )}
                                <div>
                                    <label style={lbl}>Reason</label>
                                    <textarea style={{ ...inp, resize: 'vertical' }} value={accessData.reason} onChange={(e) => setAccessData({ ...accessData, reason: e.target.value })} rows={2} />
                                </div>
                            </div>
                            <div className="modal-footer" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                <button type="button" className="btn btn-secondary" onClick={() => setShowAccessModal(false)}>Cancel</button>
                                <button type="button" className="btn btn-primary" onClick={handleGrantAccess} disabled={grantAccess.isPending}>
                                    {grantAccess.isPending ? 'Granting...' : 'Grant Access'}
                                </button>
                                {accessMsg && (
                                    <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: accessMsg.includes('success') ? 'var(--color-success)' : '#ef4444' }}>
                                        {accessMsg}
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </SettingsLayout>
    );
}
