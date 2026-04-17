/**
 * IPSAS Statement of Financial Performance (Income & Expenditure) — Quot PSE
 * Route: /accounting/ipsas/financial-performance
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Printer, TrendingUp, TrendingDown } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import apiClient from '../../../api/client';
import ReportError from './ReportError';
import ExportExcelButton from './ExportExcelButton';

const fmtNGN = (v: number) => 'NGN ' + (v || 0).toLocaleString('en-NG', { minimumFractionDigits: 2 });
const card: React.CSSProperties = { background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1', padding: '24px', marginBottom: '20px' };

export default function FinancialPerformanceReport() {
    const [fy, setFy] = useState(new Date().getFullYear());

    const { data, isLoading, error } = useQuery({
        queryKey: ['ipsas-financial-performance', fy],
        queryFn: async () => (await apiClient.get('/accounting/ipsas/financial-performance/', { params: { fiscal_year: fy } })).data,
        retry: false,
    });

    const renderSection = (title: string, items: any[], total: number, color: string) => (
        <div style={{ marginBottom: '16px' }}>
            <div style={{ fontSize: '13px', fontWeight: 700, color, marginBottom: '8px' }}>{title}</div>
            {(items || []).map((i: any, idx: number) => (
                <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0 5px 20px', borderBottom: '1px solid #f8fafc' }}>
                    <span style={{ fontSize: '13px', color: '#1e293b' }}>{i.code} — {i.name}</span>
                    <span style={{ fontSize: '13px', fontWeight: 600, fontFamily: 'monospace' }}>{fmtNGN(i.amount)}</span>
                </div>
            ))}
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px', fontWeight: 700, fontSize: '13px', background: '#f8fafc', borderRadius: '4px', marginTop: '4px' }}>
                <span>Subtotal</span><span style={{ fontFamily: 'monospace', color }}>{fmtNGN(total)}</span>
            </div>
        </div>
    );

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 800, color: '#1e293b', margin: 0 }}>Statement of Financial Performance</h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>IPSAS 1 — Income and Expenditure Statement</p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <select value={fy} onChange={e => setFy(parseInt(e.target.value))} style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '14px' }}>
                            {[2024, 2025, 2026, 2027].map(y => <option key={y} value={y}>FY {y}</option>)}
                        </select>
                        <button onClick={() => window.print()} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', borderRadius: '8px', border: '1px solid #e2e8f0', background: '#fff', cursor: 'pointer', fontSize: '14px' }}>
                            <Printer size={16} /> Print
                        </button>
                        <ExportExcelButton
                            endpoint="/accounting/ipsas/financial-performance/"
                            params={{ fiscal_year: fy }}
                            filename={`sofperformance-${fy}.xlsx`}
                        />
                    </div>
                </div>

                {isLoading ? (
                    <div style={{ color: '#94a3b8', textAlign: 'center', padding: '40px' }}>Loading...</div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/financial-performance/" />
                ) : data ? (
                    <div style={{ maxWidth: '800px' }}>
                        {/* Revenue */}
                        <div style={card}>
                            <div style={{ fontSize: '14px', fontWeight: 800, color: '#008751', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <TrendingUp size={18} /> REVENUE
                            </div>
                            {renderSection('Tax Revenue', data.revenue?.tax_revenue?.items, data.revenue?.tax_revenue?.total, '#16a34a')}
                            {renderSection('Non-Tax Revenue', data.revenue?.non_tax_revenue?.items, data.revenue?.non_tax_revenue?.total, '#059669')}
                            {renderSection('Grants & Transfers', data.revenue?.grants_transfers?.items, data.revenue?.grants_transfers?.total, '#0d9488')}
                            {renderSection('Other Revenue', data.revenue?.other_revenue?.items, data.revenue?.other_revenue?.total, '#64748b')}
                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px', borderTop: '3px solid #008751', marginTop: '8px' }}>
                                <span style={{ fontWeight: 800, fontSize: '15px', color: '#008751' }}>TOTAL REVENUE</span>
                                <span style={{ fontWeight: 800, fontSize: '15px', fontFamily: 'monospace', color: '#008751' }}>{fmtNGN(data.revenue?.total)}</span>
                            </div>
                        </div>

                        {/* Expenditure */}
                        <div style={card}>
                            <div style={{ fontSize: '14px', fontWeight: 800, color: '#c0392b', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <TrendingDown size={18} /> EXPENDITURE
                            </div>
                            {renderSection('Personnel Costs', data.expenditure?.personnel_costs?.items, data.expenditure?.personnel_costs?.total, '#dc2626')}
                            {renderSection('Overhead / O&M', data.expenditure?.overhead_costs?.items, data.expenditure?.overhead_costs?.total, '#ea580c')}
                            {renderSection('Capital Expenditure', data.expenditure?.capital_expenditure?.items, data.expenditure?.capital_expenditure?.total, '#9333ea')}
                            {renderSection('Debt Service', data.expenditure?.debt_service?.items, data.expenditure?.debt_service?.total, '#64748b')}
                            {renderSection('Transfers & Subventions', data.expenditure?.transfers_subventions?.items, data.expenditure?.transfers_subventions?.total, '#0369a1')}
                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px', borderTop: '3px solid #c0392b', marginTop: '8px' }}>
                                <span style={{ fontWeight: 800, fontSize: '15px', color: '#c0392b' }}>TOTAL EXPENDITURE</span>
                                <span style={{ fontWeight: 800, fontSize: '15px', fontFamily: 'monospace', color: '#c0392b' }}>{fmtNGN(data.expenditure?.total)}</span>
                            </div>
                        </div>

                        {/* Surplus / Deficit */}
                        <div style={{
                            ...card,
                            background: (data.surplus_deficit || 0) >= 0 ? '#f0fdf4' : '#fef2f2',
                            border: `2px solid ${(data.surplus_deficit || 0) >= 0 ? '#22c55e' : '#ef4444'}`,
                            textAlign: 'center',
                        }}>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: '4px' }}>
                                Surplus / (Deficit) for the Period
                            </div>
                            <div style={{
                                fontSize: '28px', fontWeight: 800, fontFamily: 'monospace',
                                color: (data.surplus_deficit || 0) >= 0 ? '#008751' : '#c0392b',
                            }}>
                                {fmtNGN(data.surplus_deficit)}
                            </div>
                        </div>
                    </div>
                ) : null}
            </main>
        </div>
    );
}
