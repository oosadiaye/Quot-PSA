/**
 * Fund Performance Report — Quot PSE
 * Route: /accounting/ipsas/fund-performance
 *
 * Budget vs actual expenditure classified by Fund segment (Federation
 * Account, Capital Development Fund, IGR Fund, Donor/Grant Funds, etc.)
 * with utilisation analysis, filter-by-code-or-name, and print.
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

interface FundRow {
    fund__code: string;
    fund__name: string;
    budget_amount: number | string;
    actual_expenditure: number | string;
    expenditure: number | string;
    variance: number | string;
    utilization_pct: number;
    pct_of_total: number;
}

interface FundResponse {
    title: string;
    fiscal_year: number;
    currency: string;
    rows: FundRow[];
    grand_total: number | string;
    grand_actual: number | string;
    grand_budget: number | string;
    grand_variance: number | string;
}

const fmtNGN = (v: number | string) => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return 'NGN ' + (Number.isFinite(n) ? n : 0).toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

const FALLBACK_YEARS = [2024, 2025, 2026, 2027];

export default function FundPerformanceReport() {
    const { data: fiscalYears } = useFiscalYears();
    const [fyId, setFyId] = useState<string>('');
    const [filter, setFilter] = useState<string>('');

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

    const { data, isLoading, error } = useQuery<FundResponse>({
        queryKey: ['ipsas-fund-performance', fyId],
        queryFn: async () => (await apiClient.get('/accounting/ipsas/fund-performance/', {
            params: { fiscal_year: fyId },
        })).data,
        enabled: !!fyId,
        retry: false,
    });

    const filteredRows = useMemo(() => {
        const rows = data?.rows ?? [];
        if (!filter.trim()) return rows;
        const needle = filter.trim().toLowerCase();
        return rows.filter(r =>
            (r.fund__code ?? '').toLowerCase().includes(needle) ||
            (r.fund__name ?? '').toLowerCase().includes(needle),
        );
    }, [data, filter]);

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 800, color: '#1e293b', margin: 0 }}>Fund Performance Report</h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>Budget vs Actual by Fund Source — Utilization Analysis</p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <select value={fyId} onChange={e => setFyId(e.target.value)} style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '14px' }}>
                            {yearOptions.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                        </select>
                        <button onClick={() => window.print()} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', borderRadius: '8px', border: '1px solid #e2e8f0', background: '#fff', cursor: 'pointer', fontSize: '14px' }}>
                            <Printer size={16} /> Print
                        </button>
                        <ExportExcelButton
                            endpoint="/accounting/ipsas/fund-performance/"
                            params={{ fiscal_year: fyId || undefined }}
                            filename={`fund-performance-${fyId}.xlsx`}
                        />
                    </div>
                </div>

                <FilterBar
                    value={filter}
                    onChange={setFilter}
                    placeholder="Filter by fund code or name…"
                    total={data?.rows?.length ?? 0}
                    visible={filteredRows.length}
                />

                {isLoading ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>Loading...</div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/fund-performance/" />
                ) : data ? (
                    <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1', overflow: 'hidden' }}>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 960 }}>
                                <thead>
                                    <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e8ecf1' }}>
                                        {['Fund Code', 'Fund Name', 'Budget', 'Actual', 'Variance', '% Utilization', '% of Total'].map((h, i) => (
                                            <th key={h} style={{ padding: '12px 14px', textAlign: i < 2 ? 'left' : 'right', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredRows.map((row, idx) => {
                                        const variance = parseFloat(String(row.variance ?? '0'));
                                        const utilization = Number(row.utilization_pct ?? 0);
                                        const utilColor = utilization > 100 ? '#dc2626' : utilization > 80 ? '#d97706' : '#16a34a';
                                        return (
                                            <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                                <td style={{ padding: '10px 14px', fontSize: '13px', fontFamily: 'monospace', fontWeight: 500 }}>{row.fund__code}</td>
                                                <td style={{ padding: '10px 14px', fontSize: '13px' }}>{row.fund__name}</td>
                                                <td style={{ padding: '10px 14px', fontSize: '13px', textAlign: 'right', fontFamily: 'monospace' }}>{fmtNGN(row.budget_amount)}</td>
                                                <td style={{ padding: '10px 14px', fontSize: '13px', textAlign: 'right', fontFamily: 'monospace' }}>{fmtNGN(row.expenditure)}</td>
                                                <td style={{ padding: '10px 14px', fontSize: '13px', textAlign: 'right', fontFamily: 'monospace', color: variance >= 0 ? '#16a34a' : '#dc2626' }}>{fmtNGN(variance)}</td>
                                                <td style={{ padding: '10px 14px', fontSize: '13px', textAlign: 'right', fontWeight: 700, color: utilColor }}>{utilization.toFixed(1)}%</td>
                                                <td style={{ padding: '10px 14px', fontSize: '13px', textAlign: 'right', fontWeight: 700, color: '#64748b' }}>{Number(row.pct_of_total ?? 0).toFixed(1)}%</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                                {data.grand_total != null && !filter && (
                                    <tfoot>
                                        <tr style={{ background: '#f0f4f8', borderTop: '2px solid #1e293b' }}>
                                            <td colSpan={2} style={{ padding: '12px 14px', fontWeight: 800, fontSize: '14px' }}>GRAND TOTAL</td>
                                            <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 800, fontFamily: 'monospace' }}>{fmtNGN(data.grand_budget)}</td>
                                            <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 800, fontFamily: 'monospace' }}>{fmtNGN(data.grand_total)}</td>
                                            <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 800, fontFamily: 'monospace', color: parseFloat(String(data.grand_variance ?? '0')) >= 0 ? '#16a34a' : '#dc2626' }}>{fmtNGN(data.grand_variance)}</td>
                                            <td style={{ padding: '12px 14px' }}></td>
                                            <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 800, fontSize: '14px' }}>100.0%</td>
                                        </tr>
                                    </tfoot>
                                )}
                            </table>
                        </div>
                        {filteredRows.length === 0 && (
                            <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                                {filter ? `No funds match "${filter}".` : 'No fund performance data for this fiscal year.'}
                            </div>
                        )}
                    </div>
                ) : null}
            </main>
        </div>
    );
}
