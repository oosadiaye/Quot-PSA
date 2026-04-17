/**
 * Revenue Performance Report — Quot PSE
 * Route: /accounting/ipsas/revenue-performance
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Printer } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import apiClient from '../../../api/client';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import ReportError from './ReportError';
import ExportExcelButton from './ExportExcelButton';

const fmtNGN = (v: number) => 'NGN ' + (v || 0).toLocaleString('en-NG', { minimumFractionDigits: 2 });
const fmtShort = (v: number) => {
    if (v >= 1e9) return `NGN ${(v / 1e9).toFixed(1)}B`;
    if (v >= 1e6) return `NGN ${(v / 1e6).toFixed(1)}M`;
    if (v >= 1e3) return `NGN ${(v / 1e3).toFixed(0)}K`;
    return `NGN ${v}`;
};
const MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export default function RevenuePerformanceReport() {
    const [fy, setFy] = useState(new Date().getFullYear());
    const { data, isLoading, error } = useQuery({
        queryKey: ['ipsas-revenue-performance', fy],
        queryFn: async () => (await apiClient.get('/accounting/ipsas/revenue-performance/', { params: { fiscal_year: fy } })).data,
        retry: false,
    });

    const monthData = (data?.by_month || []).map((m: any) => ({
        name: MONTHS[m.collection_date__month] || `M${m.collection_date__month}`,
        amount: m.total || 0,
    }));

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 800, color: '#1e293b', margin: 0 }}>Revenue Performance</h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>IGR Collection Analysis by Revenue Head and Month</p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <select value={fy} onChange={e => setFy(parseInt(e.target.value))} style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '14px' }}>
                            {[2024, 2025, 2026, 2027].map(y => <option key={y} value={y}>FY {y}</option>)}
                        </select>
                        <button onClick={() => window.print()} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', borderRadius: '8px', border: '1px solid #e2e8f0', background: '#fff', cursor: 'pointer', fontSize: '14px' }}>
                            <Printer size={16} /> Print
                        </button>
                        <ExportExcelButton
                            endpoint="/accounting/ipsas/revenue-performance/"
                            params={{ fiscal_year: fy }}
                            filename={`revenue-performance-${fy}.xlsx`}
                        />
                    </div>
                </div>

                {isLoading ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>Loading...</div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/revenue-performance/" />
                ) : data ? (
                    <div style={{ maxWidth: '900px' }}>
                        {/* Total */}
                        <div style={{ background: '#f0fdf4', borderRadius: '12px', border: '2px solid #22c55e', padding: '24px', marginBottom: '20px', textAlign: 'center' }}>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: '#16a34a', textTransform: 'uppercase' }}>Total Revenue Collected (FY {fy})</div>
                            <div style={{ fontSize: '32px', fontWeight: 800, color: '#008751', fontFamily: 'monospace', marginTop: '4px' }}>{fmtNGN(data.total_collected)}</div>
                        </div>

                        {/* By Revenue Head */}
                        <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1', padding: '24px', marginBottom: '20px' }}>
                            <div style={{ fontSize: '15px', fontWeight: 700, color: '#1e293b', marginBottom: '16px' }}>Revenue by Head</div>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ borderBottom: '2px solid #e8ecf1' }}>
                                        <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Code</th>
                                        <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Revenue Head</th>
                                        <th style={{ padding: '8px 12px', textAlign: 'right', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Count</th>
                                        <th style={{ padding: '8px 12px', textAlign: 'right', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Amount</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(data.by_revenue_head || []).map((rh: any, i: number) => (
                                        <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                            <td style={{ padding: '8px 12px', fontSize: '13px', fontFamily: 'monospace' }}>{rh.revenue_head__code}</td>
                                            <td style={{ padding: '8px 12px', fontSize: '13px' }}>{rh.revenue_head__name}</td>
                                            <td style={{ padding: '8px 12px', fontSize: '13px', textAlign: 'right' }}>{rh.count}</td>
                                            <td style={{ padding: '8px 12px', fontSize: '13px', textAlign: 'right', fontFamily: 'monospace', fontWeight: 600 }}>{fmtNGN(rh.total)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            {(!data.by_revenue_head || data.by_revenue_head.length === 0) && (
                                <div style={{ textAlign: 'center', padding: '30px', color: '#94a3b8' }}>No revenue collections posted for FY {fy}.</div>
                            )}
                        </div>

                        {/* Monthly Trend */}
                        {monthData.length > 0 && (
                            <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1', padding: '24px' }}>
                                <div style={{ fontSize: '15px', fontWeight: 700, color: '#1e293b', marginBottom: '16px' }}>Monthly Collection Trend</div>
                                <div style={{ height: 260 }}>
                                    <ResponsiveContainer>
                                        <BarChart data={monthData}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                                            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                                            <YAxis tickFormatter={fmtShort} tick={{ fontSize: 11 }} />
                                            <Tooltip formatter={(v: number) => fmtNGN(v)} />
                                            <Bar dataKey="amount" name="Revenue" fill="#008751" radius={[4, 4, 0, 0]} />
                                        </BarChart>
                                    </ResponsiveContainer>
                                </div>
                            </div>
                        )}
                    </div>
                ) : null}
            </main>
        </div>
    );
}
