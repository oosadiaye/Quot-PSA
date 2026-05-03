/**
 * IPSAS 24 — Budget Performance Statement (SoFP layout)
 * Route: /accounting/ipsas/budget-performance
 *
 * Shares the visual layout of the Statement of Financial Performance
 * (revenue → expenditure → surplus/deficit) but each line carries
 * THREE figures side by side: Budget, Actual, Variance. Added without
 * touching FinancialPerformanceReport.tsx so the I&E statement keeps
 * its existing behaviour.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Printer, TrendingUp, TrendingDown, Scale } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import apiClient from '../../../api/client';
import ReportError from './ReportError';
import ExportExcelButton from './ExportExcelButton';

const fmtNGN = (v: number | string | null | undefined) => {
    const n = typeof v === 'string' ? parseFloat(v) : (v ?? 0);
    if (!Number.isFinite(n) || n === 0) return 'NGN —';
    return 'NGN ' + n.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};
const fmtPct = (v: number | string | null | undefined) => {
    const n = typeof v === 'string' ? parseFloat(v) : (v ?? 0);
    if (!Number.isFinite(n)) return '—';
    return `${n.toFixed(1)}%`;
};
const card: React.CSSProperties = {
    background: '#fff', borderRadius: '12px',
    border: '1px solid #e8ecf1', padding: '24px', marginBottom: '20px',
};

interface BPRLine {
    code: string;
    name: string;
    original_budget: string | number;
    final_budget: string | number;
    actual: string | number;
    variance: string | number;
    variance_pct: string | number;
    favourable: boolean;
}

interface BPRGroup {
    items: BPRLine[];
    original_budget: string | number;
    final_budget: string | number;
    actual: string | number;
    variance: string | number;
    variance_pct: string | number;
    favourable: boolean;
}

function VarianceCell({ value, favourable }: { value: string | number; favourable: boolean }) {
    const n = typeof value === 'string' ? parseFloat(value) : value;
    const color = n === 0 ? '#64748b' : favourable ? '#16a34a' : '#dc2626';
    return (
        <span style={{ color, fontFamily: 'monospace', fontWeight: 600 }}>
            {fmtNGN(value)}
        </span>
    );
}

function renderLine(label: string, group: BPRGroup | undefined, sectionColor: string) {
    if (!group) return null;
    return (
        <div style={{ marginBottom: '18px' }}>
            <div style={{
                fontSize: '13px', fontWeight: 700, color: sectionColor, marginBottom: '8px',
                borderBottom: `2px solid ${sectionColor}22`, paddingBottom: '4px',
            }}>
                {label}
            </div>
            {(group.items || []).map((item, i) => (
                <div key={i} style={{
                    display: 'grid',
                    gridTemplateColumns: 'minmax(240px, 1.5fr) 1fr 1fr 1fr 70px',
                    gap: '12px',
                    padding: '6px 20px',
                    borderBottom: '1px solid #f1f5f9',
                    alignItems: 'center',
                }}>
                    <span style={{ fontSize: '13px', color: '#1e293b' }}>
                        {item.code} — {item.name}
                    </span>
                    <span style={{ fontSize: '13px', fontFamily: 'monospace', textAlign: 'right', color: '#1e293b' }}>
                        {fmtNGN(item.final_budget)}
                    </span>
                    <span style={{ fontSize: '13px', fontFamily: 'monospace', textAlign: 'right', color: '#1e293b' }}>
                        {fmtNGN(item.actual)}
                    </span>
                    <span style={{ fontSize: '13px', textAlign: 'right' }}>
                        <VarianceCell value={item.variance} favourable={item.favourable} />
                    </span>
                    <span style={{ fontSize: '11px', textAlign: 'right', color: '#64748b' }}>
                        {fmtPct(item.variance_pct)}
                    </span>
                </div>
            ))}
            {/* Subtotal */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(240px, 1.5fr) 1fr 1fr 1fr 70px',
                gap: '12px',
                padding: '8px',
                background: '#f8fafc',
                borderRadius: '4px',
                marginTop: '4px',
                fontWeight: 700,
                fontSize: '13px',
            }}>
                <span style={{ color: sectionColor }}>Subtotal</span>
                <span style={{ fontFamily: 'monospace', textAlign: 'right', color: sectionColor }}>
                    {fmtNGN(group.final_budget)}
                </span>
                <span style={{ fontFamily: 'monospace', textAlign: 'right', color: sectionColor }}>
                    {fmtNGN(group.actual)}
                </span>
                <span style={{ textAlign: 'right' }}>
                    <VarianceCell value={group.variance} favourable={group.favourable} />
                </span>
                <span style={{ fontSize: '11px', textAlign: 'right', color: '#64748b' }}>
                    {fmtPct(group.variance_pct)}
                </span>
            </div>
        </div>
    );
}

function renderHeaderRow() {
    return (
        <div style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(240px, 1.5fr) 1fr 1fr 1fr 70px',
            gap: '12px',
            padding: '8px 20px',
            marginBottom: '4px',
            fontSize: '11px',
            fontWeight: 700,
            color: '#64748b',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            borderBottom: '1px solid #cbd5e1',
        }}>
            <span>Description</span>
            <span style={{ textAlign: 'right' }}>Budget</span>
            <span style={{ textAlign: 'right' }}>Actual</span>
            <span style={{ textAlign: 'right' }}>Variance</span>
            <span style={{ textAlign: 'right' }}>%</span>
        </div>
    );
}

export default function BudgetPerformanceReport() {
    const [fy, setFy] = useState(new Date().getFullYear());

    const { data, isLoading, error } = useQuery({
        queryKey: ['ipsas-budget-performance', fy],
        queryFn: async () => (
            await apiClient.get('/accounting/ipsas/budget-performance/', {
                params: { fiscal_year: fy },
            })
        ).data,
        retry: false,
    });

    const surplus = data?.surplus_deficit;
    const actualSurplus = typeof surplus?.actual === 'string' ? parseFloat(surplus.actual) : (surplus?.actual ?? 0);
    const budgetSurplus = typeof surplus?.final_budget === 'string' ? parseFloat(surplus.final_budget) : (surplus?.final_budget ?? 0);

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main className="ipsas-report" style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 800, color: '#1e293b', margin: 0 }}>
                            Budget Performance Statement
                        </h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>
                            IPSAS 24 — Budget vs Actual in Income &amp; Expenditure layout
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <select
                            value={fy}
                            onChange={(e) => setFy(parseInt(e.target.value))}
                            style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '14px' }}
                        >
                            {[2024, 2025, 2026, 2027].map((y) => (
                                <option key={y} value={y}>FY {y}</option>
                            ))}
                        </select>
                        <button
                            onClick={() => window.print()}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '6px',
                                padding: '8px 16px', borderRadius: '8px',
                                border: '1px solid #e2e8f0', background: '#fff',
                                cursor: 'pointer', fontSize: '14px',
                            }}
                        >
                            <Printer size={16} /> Print
                        </button>
                        <ExportExcelButton
                            endpoint="/accounting/ipsas/budget-performance/"
                            params={{ fiscal_year: fy }}
                            filename={`budget-performance-${fy}.xlsx`}
                        />
                    </div>
                </div>

                {isLoading ? (
                    <div style={{ color: '#94a3b8', textAlign: 'center', padding: '40px' }}>Loading...</div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/budget-performance/" />
                ) : data ? (
                    <div style={{ maxWidth: '1100px' }}>
                        {/* Revenue */}
                        <div style={card}>
                            <div style={{
                                fontSize: '14px', fontWeight: 800, color: '#008751',
                                marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px',
                            }}>
                                <TrendingUp size={18} /> REVENUE
                            </div>
                            {renderHeaderRow()}
                            {renderLine('Tax Revenue', data.revenue?.tax_revenue, '#16a34a')}
                            {renderLine('Non-Tax Revenue', data.revenue?.non_tax_revenue, '#059669')}
                            {renderLine('Grants &amp; Transfers', data.revenue?.grants_transfers, '#0d9488')}
                            {renderLine('Other Revenue', data.revenue?.other_revenue, '#64748b')}
                            <div style={{
                                display: 'grid',
                                gridTemplateColumns: 'minmax(240px, 1.5fr) 1fr 1fr 1fr 70px',
                                gap: '12px',
                                padding: '12px',
                                borderTop: '3px solid #008751',
                                marginTop: '8px',
                                fontWeight: 800, fontSize: '15px', color: '#008751',
                            }}>
                                <span>TOTAL REVENUE</span>
                                <span style={{ fontFamily: 'monospace', textAlign: 'right' }}>
                                    {fmtNGN(data.revenue?.total?.final_budget)}
                                </span>
                                <span style={{ fontFamily: 'monospace', textAlign: 'right' }}>
                                    {fmtNGN(data.revenue?.total?.actual)}
                                </span>
                                <span style={{ textAlign: 'right' }}>
                                    <VarianceCell value={data.revenue?.total?.variance} favourable={data.revenue?.total?.favourable} />
                                </span>
                                <span style={{ fontSize: '11px', textAlign: 'right' }}>
                                    {fmtPct(data.revenue?.total?.variance_pct)}
                                </span>
                            </div>
                        </div>

                        {/* Expenditure */}
                        <div style={card}>
                            <div style={{
                                fontSize: '14px', fontWeight: 800, color: '#c0392b',
                                marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px',
                            }}>
                                <TrendingDown size={18} /> EXPENDITURE
                            </div>
                            {renderHeaderRow()}
                            {renderLine('Personnel Costs', data.expenditure?.personnel_costs, '#dc2626')}
                            {renderLine('Overhead / O&amp;M', data.expenditure?.overhead_costs, '#ea580c')}
                            {renderLine('Capital Expenditure', data.expenditure?.capital_expenditure, '#9333ea')}
                            {renderLine('Debt Service', data.expenditure?.debt_service, '#64748b')}
                            {renderLine('Transfers &amp; Subventions', data.expenditure?.transfers_subventions, '#0369a1')}
                            <div style={{
                                display: 'grid',
                                gridTemplateColumns: 'minmax(240px, 1.5fr) 1fr 1fr 1fr 70px',
                                gap: '12px',
                                padding: '12px',
                                borderTop: '3px solid #c0392b',
                                marginTop: '8px',
                                fontWeight: 800, fontSize: '15px', color: '#c0392b',
                            }}>
                                <span>TOTAL EXPENDITURE</span>
                                <span style={{ fontFamily: 'monospace', textAlign: 'right' }}>
                                    {fmtNGN(data.expenditure?.total?.final_budget)}
                                </span>
                                <span style={{ fontFamily: 'monospace', textAlign: 'right' }}>
                                    {fmtNGN(data.expenditure?.total?.actual)}
                                </span>
                                <span style={{ textAlign: 'right' }}>
                                    <VarianceCell value={data.expenditure?.total?.variance} favourable={data.expenditure?.total?.favourable} />
                                </span>
                                <span style={{ fontSize: '11px', textAlign: 'right' }}>
                                    {fmtPct(data.expenditure?.total?.variance_pct)}
                                </span>
                            </div>
                        </div>

                        {/* Surplus / Deficit summary card */}
                        <div style={{
                            ...card,
                            background: actualSurplus >= 0 ? '#f0fdf4' : '#fef2f2',
                            border: `2px solid ${actualSurplus >= 0 ? '#22c55e' : '#ef4444'}`,
                        }}>
                            <div style={{
                                display: 'flex', alignItems: 'center', gap: '8px',
                                fontSize: '12px', fontWeight: 700, color: '#64748b',
                                textTransform: 'uppercase', marginBottom: '12px',
                            }}>
                                <Scale size={14} /> Surplus / (Deficit) for the Period
                            </div>
                            <div style={{
                                display: 'grid', gridTemplateColumns: '1fr 1fr 1fr',
                                gap: '16px',
                            }}>
                                <div>
                                    <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 600, marginBottom: '4px' }}>
                                        BUDGETED
                                    </div>
                                    <div style={{ fontSize: '20px', fontWeight: 800, fontFamily: 'monospace', color: budgetSurplus >= 0 ? '#008751' : '#c0392b' }}>
                                        {fmtNGN(surplus?.final_budget)}
                                    </div>
                                </div>
                                <div>
                                    <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 600, marginBottom: '4px' }}>
                                        ACTUAL
                                    </div>
                                    <div style={{ fontSize: '20px', fontWeight: 800, fontFamily: 'monospace', color: actualSurplus >= 0 ? '#008751' : '#c0392b' }}>
                                        {fmtNGN(surplus?.actual)}
                                    </div>
                                </div>
                                <div>
                                    <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 600, marginBottom: '4px' }}>
                                        VARIANCE ({fmtPct(surplus?.variance_pct)})
                                    </div>
                                    <div style={{ fontSize: '20px', fontWeight: 800, fontFamily: 'monospace' }}>
                                        <VarianceCell value={surplus?.variance} favourable={(typeof surplus?.variance === 'string' ? parseFloat(surplus.variance) : surplus?.variance ?? 0) <= 0} />
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                ) : null}
            </main>
        </div>
    );
}
