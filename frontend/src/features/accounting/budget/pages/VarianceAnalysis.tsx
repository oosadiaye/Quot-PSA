import React, { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import LoadingScreen from '../../../../components/common/LoadingScreen';
import { useBudgetPeriods } from '../hooks/useBudgetPeriods';
import { useVarianceAnalysis } from '../hooks/useBudgetAnalytics';
import { useCurrency } from '../../../../context/CurrencyContext';
import { useNCoASegments } from '../../../../hooks/useGovForms';
import { Download, TrendingDown, TrendingUp, BarChart3 } from 'lucide-react';
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

export const VarianceAnalysis: React.FC = () => {
    const [selectedYear, setSelectedYear] = useState<number | undefined>();
    const [selectedPeriod, setSelectedPeriod] = useState<number | undefined>();
    const [selectedMda, setSelectedMda] = useState<number | undefined>();
    const [compareToPeriod, setCompareToPeriod] = useState<number | undefined>();

    const { periods, isLoading: periodsLoading } = useBudgetPeriods();
    const { data: segments } = useNCoASegments();
    const { currencySymbol } = useCurrency();
    const { data: varianceData, isLoading: varianceLoading } = useVarianceAnalysis(
        selectedPeriod || null,
        compareToPeriod
    );

    const formatCurrency = (value: string | number) => {
        const num = typeof value === 'string' ? parseFloat(value) : value;
        return new Intl.NumberFormat('en-NG', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(num);
    };

    const calculateVariancePercent = (revised: string, used: string) => {
        const revisedNum = parseFloat(revised);
        const usedNum = parseFloat(used);
        if (revisedNum === 0) return 0;
        return ((usedNum / revisedNum) * 100).toFixed(1);
    };

    const getStatusBadge = (status: string) => {
        const map: Record<string, { bg: string; color: string }> = {
            UNDER: { bg: 'rgba(34, 197, 94, 0.1)', color: '#22c55e' },
            ON_TRACK: { bg: 'rgba(36, 113, 163, 0.1)', color: '#2471a3' },
            OVER: { bg: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' },
        };
        const style = map[status] || { bg: 'rgba(156, 163, 175, 0.1)', color: '#9ca3af' };
        return (
            <span style={{
                display: 'inline-block', padding: '0.25rem 0.75rem',
                borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 500,
                background: style.bg, color: style.color,
            }}>
                {(status ?? '').replace('_', ' ')}
            </span>
        );
    };

    const getUtilBadge = (percent: string | number) => {
        const p = typeof percent === 'string' ? parseFloat(percent) : percent;
        let bg = 'rgba(34, 197, 94, 0.1)', color = '#22c55e';
        if (p >= 95) { bg = 'rgba(239, 68, 68, 0.1)'; color = '#ef4444'; }
        else if (p >= 80) { bg = 'rgba(245, 158, 11, 0.1)'; color = '#f59e0b'; }
        else if (p >= 60) { bg = 'rgba(36, 113, 163, 0.1)'; color = '#2471a3'; }
        return (
            <span style={{
                display: 'inline-block', padding: '0.25rem 0.75rem',
                borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 500,
                background: bg, color,
            }}>
                {typeof p === 'number' ? p.toFixed ? p.toFixed(1) : p : p}%
            </span>
        );
    };

    const chartData = varianceData?.slice(0, 10).map((item: any) => ({
        account: item.account_code,
        Revised: parseFloat(item.revised),
        Used: parseFloat(item.total_used),
        Available: parseFloat(item.available),
    }));

    const isLoading = periodsLoading || varianceLoading;

    if (isLoading) {
        return <LoadingScreen message="Loading variance analysis..." />;
    }

    return (
        <div>
            {/* Header */}
            <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', marginBottom: '0.25rem' }}>
                        Variance Analysis
                    </h2>
                    <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
                        Budget vs Actual comparison and analysis
                    </p>
                </div>
                <button
                    disabled
                    className="glass-button"
                    style={{
                        display: 'flex', alignItems: 'center', gap: '0.375rem',
                        padding: '0.625rem 1rem', borderRadius: '8px',
                        border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                        color: 'var(--color-text)', cursor: 'not-allowed', fontWeight: 500,
                        fontSize: 'var(--text-sm)', opacity: 0.5,
                    }}
                >
                    <Download size={16} /> Export Report
                </button>
            </div>

            {/* Fiscal Year + Period Selectors */}
            <div className="glass-card" style={{ padding: '1rem', marginBottom: '1.5rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '0.75rem' }}>
                    <div>
                        <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', marginBottom: '0.375rem' }}>
                            Fiscal Year <span style={{ color: '#ef4444' }}>*</span>
                        </label>
                        <select value={selectedYear || ''} onChange={e => { setSelectedYear(Number(e.target.value) || undefined); setSelectedPeriod(undefined); }} style={selectStyle}>
                            <option value="">Select fiscal year...</option>
                            {[...new Set((periods || []).map((p: any) => p.fiscal_year))].sort((a: number, b: number) => b - a).map((yr: any) => (
                                <option key={yr} value={yr}>FY {yr}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', marginBottom: '0.375rem' }}>
                            Period <span style={{ color: 'var(--color-text-muted)', fontWeight: 400 }}>(optional)</span>
                        </label>
                        <select value={selectedPeriod || ''} onChange={e => setSelectedPeriod(Number(e.target.value) || undefined)} style={selectStyle} disabled={!selectedYear}>
                            <option value="">{selectedYear ? 'All Periods (Annual)' : 'Select year first'}</option>
                            {(periods || [])
                                .filter((p: any) => p.fiscal_year === selectedYear)
                                .map((p: any) => (
                                    <option key={p.id} value={p.id}>
                                        {p.period_type === 'ANNUAL' ? 'Annual' : p.period_type === 'QUARTERLY' ? `Q${p.period_number}` : `Month ${p.period_number}`}
                                        {p.status === 'ACTIVE' ? ' (Active)' : ''}
                                    </option>
                                ))}
                        </select>
                    </div>
                    <div>
                        <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', marginBottom: '0.375rem' }}>
                            MDA <span style={{ color: 'var(--color-text-muted)', fontWeight: 400 }}>(optional)</span>
                        </label>
                        <select value={selectedMda || ''} onChange={e => setSelectedMda(Number(e.target.value) || undefined)} style={selectStyle}>
                            <option value="">All MDAs</option>
                            {(segments?.administrative || []).map((s: any) => (
                                <option key={s.id} value={s.id}>{s.code} - {s.name}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)', marginBottom: '0.375rem' }}>
                            Compare To <span style={{ color: 'var(--color-text-muted)', fontWeight: 400 }}>(optional)</span>
                        </label>
                        <select value={compareToPeriod || ''} onChange={e => setCompareToPeriod(Number(e.target.value) || undefined)} style={selectStyle}>
                            <option value="">No comparison</option>
                            {(periods || [])
                                .filter((p: any) => p.id !== selectedPeriod)
                                .map((p: any) => (
                                    <option key={p.id} value={p.id}>
                                        FY{p.fiscal_year} - {p.period_type === 'ANNUAL' ? 'Annual' : `Month ${p.period_number}`}
                                    </option>
                                ))}
                        </select>
                    </div>
                </div>
            </div>

            {!selectedYear ? (
                <div className="glass-card" style={{ padding: '2rem', textAlign: 'center' }}>
                    <BarChart3 size={48} style={{ margin: '0 auto 1rem', opacity: 0.5, display: 'block', color: 'var(--color-text-muted)' }} />
                    <h3 style={{ color: 'var(--color-text)', marginBottom: '0.5rem' }}>Select a Fiscal Year</h3>
                    <p style={{ color: 'var(--color-text-muted)', margin: 0, fontSize: 'var(--text-sm)' }}>
                        Select a fiscal year to view budget vs actual variance analysis.
                    </p>
                </div>
            ) : (
                <>
                    {/* Chart */}
                    <div className="glass-card" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>
                            Budget vs Actual (Top 10 Accounts)
                        </h3>
                        <ResponsiveContainer width="100%" height={300}>
                            <BarChart data={chartData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #e5e7eb)" />
                                <XAxis dataKey="account" tick={{ fontSize: 'var(--text-xs)' }} />
                                <YAxis tick={{ fontSize: 'var(--text-xs)' }} />
                                <Tooltip
                                    formatter={(value: any) => `${currencySymbol}${formatCurrency(value || 0)}`}
                                    contentStyle={{
                                        borderRadius: '8px',
                                        border: '1px solid var(--color-border)',
                                        background: 'var(--color-surface, white)',
                                    }}
                                />
                                <Legend />
                                <Bar dataKey="Revised" fill="#2471a3" radius={[4, 4, 0, 0]} />
                                <Bar dataKey="Used" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                                <Bar dataKey="Available" fill="#22c55e" radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>

                    {/* Variance Table */}
                    <div className="glass-card" style={{ overflow: 'hidden' }}>
                        <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--color-border)' }}>
                            <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text)', margin: 0 }}>
                                Detailed Variance Report
                            </h3>
                        </div>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '1100px' }}>
                                <thead>
                                    <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        {['Account', 'Allocated', 'Revised', 'Committed', 'Expended', 'Total Used', 'Available', 'Variance', 'Utilization', 'Status'].map((h) => (
                                            <th
                                                key={h}
                                                style={{
                                                    padding: '0.75rem 1rem',
                                                    textAlign: h === 'Account' ? 'left' : h === 'Utilization' || h === 'Status' ? 'center' : 'right',
                                                    fontSize: 'var(--text-xs)',
                                                    fontWeight: 600,
                                                    color: 'var(--color-text)',
                                                }}
                                            >
                                                {h}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {varianceData && varianceData.length > 0 ? (
                                        varianceData.map((row: any, index: number) => {
                                            const variance = parseFloat(row.variance_amount);
                                            const isNegative = variance < 0;
                                            const utilizationPercent = calculateVariancePercent(row.revised, row.total_used);
                                            return (
                                                <tr
                                                    key={row.budget_code || index}
                                                    style={{
                                                        borderBottom: '1px solid var(--color-border)',
                                                        animation: `fadeInUp 0.3s ease-out ${index * 0.03}s both`,
                                                    }}
                                                >
                                                    <td style={{ padding: '0.75rem 1rem' }}>
                                                        <div style={{ fontWeight: 500, color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                            {row.account_code}
                                                        </div>
                                                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                            {row.account_name}
                                                        </div>
                                                    </td>
                                                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                        {currencySymbol}{formatCurrency(row.allocated)}
                                                    </td>
                                                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                        {currencySymbol}{formatCurrency(row.revised)}
                                                    </td>
                                                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                        {currencySymbol}{formatCurrency(row.encumbered)}
                                                    </td>
                                                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                        {currencySymbol}{formatCurrency(row.expended)}
                                                    </td>
                                                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 600, color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                        {currencySymbol}{formatCurrency(row.total_used)}
                                                    </td>
                                                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                        {currencySymbol}{formatCurrency(row.available)}
                                                    </td>
                                                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', justifyContent: 'flex-end' }}>
                                                            {isNegative ? (
                                                                <TrendingDown size={14} style={{ color: '#22c55e' }} />
                                                            ) : (
                                                                <TrendingUp size={14} style={{ color: '#ef4444' }} />
                                                            )}
                                                            <span style={{ color: isNegative ? '#22c55e' : '#ef4444', fontSize: 'var(--text-sm)' }}>
                                                                {currencySymbol}{formatCurrency(Math.abs(variance))}
                                                            </span>
                                                        </div>
                                                    </td>
                                                    <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                                                        {getUtilBadge(utilizationPercent)}
                                                    </td>
                                                    <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                                                        {getStatusBadge(row.status)}
                                                    </td>
                                                </tr>
                                            );
                                        })
                                    ) : (
                                        <tr>
                                            <td colSpan={10} style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                                No variance data available
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
};

export default VarianceAnalysis;
