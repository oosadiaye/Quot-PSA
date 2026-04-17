/**
 * IPSAS — Functional Classification Report (COFOG) — Quot PSE
 * Route: /accounting/ipsas/functional-classification
 */
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Printer, Search } from 'lucide-react';
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

/** Fallback year list used when useFiscalYears returns an empty array. */
const FALLBACK_YEARS = [2024, 2025, 2026, 2027];

export default function FunctionalClassificationReport() {
    const { data: fiscalYears } = useFiscalYears();
    const [fyId, setFyId] = useState('');

    // Auto-select the current year (or the first available FY) on load.
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
        queryKey: ['ipsas-functional-classification', fyId],
        queryFn: async () => {
            return (await apiClient.get('/accounting/ipsas/functional-classification/', { params: { fiscal_year: fyId } })).data;
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
            (r.function__code ?? '').toLowerCase().includes(needle) ||
            (r.function__name ?? '').toLowerCase().includes(needle),
        );
    }, [data, filter]);

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 800, color: '#1e293b', margin: 0 }}>Functional Classification Performance Report (COFOG)</h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>Budget vs Actual by COFOG Function — Utilization Analysis</p>
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
                            endpoint="/accounting/ipsas/functional-classification/"
                            params={{ fiscal_year: fyId || undefined }}
                            filename={`functional-classification-${fyId}.xlsx`}
                        />
                    </div>
                </div>

                <FilterBar
                    value={filter}
                    onChange={setFilter}
                    placeholder="Filter by function code or name…"
                    total={(data as any)?.rows?.length ?? 0}
                    visible={filteredRows.length}
                />

                {isLoading ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>Loading...</div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/functional-classification/" />
                ) : data ? (
                    <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1', overflow: 'hidden' }}>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 960 }}>
                                <thead>
                                    <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e8ecf1' }}>
                                        {['Function Code', 'Function Name', 'Budget', 'Actual', 'Variance', '% Utilization', '% of Total'].map((h, i) => (
                                            <th key={h} style={{ padding: '12px 14px', textAlign: i < 2 ? 'left' : 'right', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredRows.map((row: any, idx: number) => {
                                        const variance = parseFloat(row.variance ?? '0');
                                        const utilization = parseFloat(row.utilization_pct ?? '0');
                                        const utilColor = utilization > 100 ? '#dc2626' : utilization > 80 ? '#d97706' : '#16a34a';
                                        return (
                                            <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                                <td style={{ padding: '10px 14px', fontSize: '13px', fontFamily: 'monospace', fontWeight: 500 }}>{row.function__code}</td>
                                                <td style={{ padding: '10px 14px', fontSize: '13px' }}>{row.function__name}</td>
                                                <td style={{ padding: '10px 14px', fontSize: '13px', textAlign: 'right', fontFamily: 'monospace' }}>{fmtNGN(row.budget_amount)}</td>
                                                <td style={{ padding: '10px 14px', fontSize: '13px', textAlign: 'right', fontFamily: 'monospace' }}>{fmtNGN(row.net_expenditure)}</td>
                                                <td style={{ padding: '10px 14px', fontSize: '13px', textAlign: 'right', fontFamily: 'monospace', color: variance >= 0 ? '#16a34a' : '#dc2626' }}>{fmtNGN(variance)}</td>
                                                <td style={{ padding: '10px 14px', fontSize: '13px', textAlign: 'right', fontWeight: 700, color: utilColor }}>{utilization.toFixed(1)}%</td>
                                                <td style={{ padding: '10px 14px', fontSize: '13px', textAlign: 'right', fontWeight: 700, color: '#64748b' }}>{parseFloat(row.pct_of_total ?? '0').toFixed(1)}%</td>
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
                                            <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 800, fontFamily: 'monospace', color: parseFloat(data.grand_variance ?? '0') >= 0 ? '#16a34a' : '#dc2626' }}>{fmtNGN(data.grand_variance)}</td>
                                            <td style={{ padding: '12px 14px' }}></td>
                                            <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 800, fontSize: '14px' }}>100.0%</td>
                                        </tr>
                                    </tfoot>
                                )}
                            </table>
                        </div>
                        {(!data.rows || data.rows.length === 0) && (
                            <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>No functional classification data for this fiscal year.</div>
                        )}
                    </div>
                ) : null}
            </main>
        </div>
    );
}
