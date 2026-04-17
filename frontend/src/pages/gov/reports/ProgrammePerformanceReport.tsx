/**
 * IPSAS — Programme Performance Report — Quot PSE
 * Route: /accounting/ipsas/programme-performance
 */
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Printer } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import apiClient from '../../../api/client';
import { useFiscalYears } from '../../../hooks/useGovForms';
import ReportError from './ReportError';
import FilterBar from './FilterBar';
import ExportExcelButton from './ExportExcelButton';

const fmtNGN = (v: number | string) => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return 'NGN ' + (n || 0).toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

const FALLBACK_YEARS = [2024, 2025, 2026, 2027];

export default function ProgrammePerformanceReport() {
    const { data: fiscalYears } = useFiscalYears();
    const [fyId, setFyId] = useState('');

    useEffect(() => {
        if (fyId) return;
        const currentYear = new Date().getFullYear();
        if (fiscalYears && fiscalYears.length > 0) {
            const match =
                fiscalYears.find((fy: { year?: number }) => fy.year === currentYear)
                ?? fiscalYears[0];
            const value = match?.year ?? match?.id;
            if (value) setFyId(String(value));
        } else if (fiscalYears && fiscalYears.length === 0) {
            setFyId(String(currentYear));
        }
    }, [fiscalYears, fyId]);

    const yearOptions = fiscalYears && fiscalYears.length > 0
        ? fiscalYears.map((fy: { id: number; year?: number }) => ({
              value: String(fy.year ?? fy.id),
              label: `FY ${fy.year ?? fy.id}`,
          }))
        : FALLBACK_YEARS.map(y => ({ value: String(y), label: `FY ${y}` }));

    const { data, isLoading, error } = useQuery({
        queryKey: ['ipsas-programme-performance', fyId],
        queryFn: async () => {
            return (await apiClient.get('/accounting/ipsas/programme-performance/', { params: { fiscal_year: fyId } })).data;
        },
        enabled: !!fyId,
        retry: false,
    });

    const [filter, setFilter] = useState('');
    const filteredRows = useMemo(() => {
        const rows = (data as any)?.rows ?? [];
        if (!filter.trim()) return rows;
        const needle = filter.trim().toLowerCase();
        return rows.filter((r: any) =>
            (r.program__code ?? '').toLowerCase().includes(needle) ||
            (r.program__name ?? '').toLowerCase().includes(needle),
        );
    }, [data, filter]);

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 800, color: '#1e293b', margin: 0 }}>Programme Performance Report</h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>Budget vs Actual Expenditure by Programme — Utilization Analysis</p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <select value={fyId} onChange={e => setFyId(e.target.value)} style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '14px' }}>
                            {yearOptions.map(opt => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                            ))}
                        </select>
                        <button onClick={() => window.print()} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', borderRadius: '8px', border: '1px solid #e2e8f0', background: '#fff', cursor: 'pointer', fontSize: '14px' }}>
                            <Printer size={16} /> Print
                        </button>
                        <ExportExcelButton
                            endpoint="/accounting/ipsas/programme-performance/"
                            params={{ fiscal_year: fyId || undefined }}
                            filename={`programme-performance-${fyId}.xlsx`}
                        />
                    </div>
                </div>

                <FilterBar
                    value={filter}
                    onChange={setFilter}
                    placeholder="Filter by programme code or name…"
                    total={(data as any)?.rows?.length ?? 0}
                    visible={filteredRows.length}
                />

                {isLoading ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>Loading...</div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/programme-performance/" />
                ) : data ? (
                    <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1', overflow: 'hidden' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e8ecf1' }}>
                                    {['Programme Code', 'Programme Name', 'Budget', 'Actual', 'Variance', '% Utilization'].map(h => (
                                        <th key={h} style={{ padding: '12px 14px', textAlign: h === 'Programme Code' || h === 'Programme Name' ? 'left' : 'right', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {filteredRows.map((row: any, idx: number) => {
                                    const variance = parseFloat(row.variance || '0');
                                    const utilization = parseFloat(row.utilization_pct || '0');
                                    return (
                                        <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                            <td style={{ padding: '10px 14px', fontSize: '13px', fontFamily: 'monospace', fontWeight: 500 }}>{row.program__code}</td>
                                            <td style={{ padding: '10px 14px', fontSize: '13px' }}>{row.program__name}</td>
                                            <td style={{ padding: '10px 14px', fontSize: '13px', textAlign: 'right', fontFamily: 'monospace' }}>{fmtNGN(row.budget_amount)}</td>
                                            <td style={{ padding: '10px 14px', fontSize: '13px', textAlign: 'right', fontFamily: 'monospace' }}>{fmtNGN(row.actual_expenditure)}</td>
                                            <td style={{ padding: '10px 14px', fontSize: '13px', textAlign: 'right', fontFamily: 'monospace', color: variance >= 0 ? '#16a34a' : '#dc2626' }}>{fmtNGN(variance)}</td>
                                            <td style={{ padding: '10px 14px', fontSize: '13px', textAlign: 'right', fontWeight: 700, color: utilization > 100 ? '#dc2626' : utilization > 80 ? '#d97706' : '#16a34a' }}>{utilization.toFixed(1)}%</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                            {data.grand_budget != null && !filter && (
                                <tfoot>
                                    <tr style={{ background: '#f0f4f8', borderTop: '2px solid #1e293b' }}>
                                        <td colSpan={2} style={{ padding: '12px 14px', fontWeight: 800, fontSize: '14px' }}>GRAND TOTAL</td>
                                        <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 800, fontFamily: 'monospace' }}>{fmtNGN(data.grand_budget)}</td>
                                        <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 800, fontFamily: 'monospace' }}>{fmtNGN(data.grand_actual)}</td>
                                        <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 800, fontFamily: 'monospace', color: parseFloat(data.grand_variance || '0') >= 0 ? '#16a34a' : '#dc2626' }}>{fmtNGN(data.grand_variance)}</td>
                                        <td style={{ padding: '12px 14px' }}></td>
                                    </tr>
                                </tfoot>
                            )}
                        </table>
                        {(!data.rows || data.rows.length === 0) && (
                            <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>No programme performance data for this fiscal year.</div>
                        )}
                    </div>
                ) : null}
            </main>
        </div>
    );
}
