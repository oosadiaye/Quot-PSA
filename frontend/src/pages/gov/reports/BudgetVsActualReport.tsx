/**
 * IPSAS 24 — Statement of Comparison of Budget and Actual Amounts — Quot PSE
 * Route: /accounting/ipsas/budget-vs-actual
 *
 * IPSAS 24 ¶14 mandates THREE budget columns:
 *   - Original Budget (initial appropriation as enacted)
 *   - Final Budget   (after supplementary / virement / amendment)
 *   - Actual
 *
 * Plus Warrants Released, Variance (Final − Actual), and % Execution.
 */
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Printer } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import apiClient from '../../../api/client';
import { useFiscalYears } from '../../../hooks/useGovForms';
import ReportError from './ReportError';
import ExportExcelButton from './ExportExcelButton';

interface BudgetVsActualRow {
    mda: string;
    mda_code: string;
    account: string;
    account_code: string;
    fund: string;
    original_budget: string | number;
    final_budget: string | number;
    warrants_released: string | number;
    actual_expenditure: string | number;
    variance: string | number;
    variance_explanation: string;
    execution_percentage: number;
}

interface BudgetVsActualResponse {
    title: string;
    standard: string;
    fiscal_year_id: number;
    currency: string;
    items: BudgetVsActualRow[];
    totals: {
        total_original_budget: string | number;
        total_final_budget:    string | number;
        total_warrants:        string | number;
        total_expended:        string | number;
        total_variance:        string | number;
        overall_execution_pct: number;
    };
}

const fmtNGN = (v: number | string): string => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return 'NGN ' + (Number.isFinite(n) ? n : 0).toLocaleString('en-NG', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
};

const execColor = (p: number): string => {
    if (p > 100) return '#dc2626';
    if (p > 80)  return '#d97706';
    return '#16a34a';
};

export default function BudgetVsActualReport() {
    const { data: fiscalYears } = useFiscalYears();
    const [fyId, setFyId] = useState<string>('');

    // Auto-select the fiscal year closest to the current year on first load.
    useEffect(() => {
        if (fyId || !fiscalYears || fiscalYears.length === 0) return;
        const currentYear = new Date().getFullYear();
        const match =
            fiscalYears.find((fy: { id: number; year?: number }) => fy.year === currentYear)
            ?? fiscalYears[0];
        if (match?.id) setFyId(String(match.id));
    }, [fiscalYears, fyId]);

    const { data, isLoading, error } = useQuery<BudgetVsActualResponse | null>({
        queryKey: ['ipsas-budget-vs-actual', fyId],
        queryFn: async () => {
            if (!fyId) return null;
            const res = await apiClient.get('/accounting/ipsas/budget-vs-actual/', {
                params: { fiscal_year_id: fyId },
            });
            return res.data;
        },
        enabled: !!fyId,
        retry: false,
    });

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main className="ipsas-report" style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    marginBottom: '24px',
                }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 800, color: '#1e293b', margin: 0 }}>
                            Budget vs Actual Comparison
                        </h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>
                            IPSAS 24 — Statement of Comparison of Budget and Actual Amounts
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <select
                            value={fyId}
                            onChange={e => setFyId(e.target.value)}
                            style={{
                                padding: '8px 12px', borderRadius: '8px',
                                border: '1px solid #e2e8f0', fontSize: '14px',
                            }}
                        >
                            {(!fiscalYears || fiscalYears.length === 0) && (
                                <option value="">No fiscal years available</option>
                            )}
                            {(fiscalYears ?? []).map((fy: { id: number; year?: number }) => (
                                <option key={fy.id} value={fy.id}>FY {fy.year ?? fy.id}</option>
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
                            endpoint="/accounting/ipsas/budget-vs-actual/"
                            params={{ fiscal_year_id: fyId || undefined }}
                            filename={`budget-vs-actual-${fyId}.xlsx`}
                        />
                    </div>
                </div>

                {!fyId ? (
                    <div style={{ textAlign: 'center', padding: '60px', color: '#94a3b8' }}>
                        {fiscalYears && fiscalYears.length === 0
                            ? 'No Fiscal Year records found in this tenant. Create one under Fiscal Year settings, then reload this page.'
                            : 'Loading fiscal years...'}
                    </div>
                ) : isLoading ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                        Loading...
                    </div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/budget-vs-actual/" />
                ) : data ? (
                    <div style={{
                        background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1',
                        overflow: 'hidden',
                    }}>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1100 }}>
                                <thead>
                                    <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e8ecf1' }}>
                                        {['MDA', 'Economic Code', 'Fund', 'Original Budget', 'Final Budget', 'Warrants', 'Actual', 'Variance', '% Exec'].map((h, i) => (
                                            <th key={h} style={{
                                                padding: '12px 14px',
                                                textAlign: i >= 3 ? 'right' : 'left',
                                                fontSize: '11px', fontWeight: 700, color: '#64748b',
                                                textTransform: 'uppercase', letterSpacing: '0.5px',
                                            }}>
                                                {h}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {(data.items || []).map((item, idx) => {
                                        const variance = parseFloat(String(item.variance || '0'));
                                        const pct = Number(item.execution_percentage ?? 0);
                                        return (
                                            <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                                <td style={{ padding: '10px 14px', fontSize: '13px', fontWeight: 500 }}>
                                                    {item.mda}
                                                </td>
                                                <td style={{ padding: '10px 14px', fontSize: '13px' }}>
                                                    {item.account_code ? (
                                                        <>
                                                            <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#4f46e5' }}>
                                                                {item.account_code}
                                                            </span>
                                                            {item.account && (
                                                                <span style={{ marginLeft: 6, color: '#1e293b' }}>
                                                                    — {item.account}
                                                                </span>
                                                            )}
                                                        </>
                                                    ) : (
                                                        item.account
                                                    )}
                                                </td>
                                                <td style={{ padding: '10px 14px', fontSize: '12px', color: '#64748b' }}>
                                                    {item.fund}
                                                </td>
                                                <td style={{
                                                    padding: '10px 14px', fontSize: '13px',
                                                    textAlign: 'right', fontFamily: 'monospace',
                                                }}>
                                                    {fmtNGN(item.original_budget)}
                                                </td>
                                                <td style={{
                                                    padding: '10px 14px', fontSize: '13px',
                                                    textAlign: 'right', fontFamily: 'monospace', fontWeight: 600,
                                                }}>
                                                    {fmtNGN(item.final_budget)}
                                                </td>
                                                <td style={{
                                                    padding: '10px 14px', fontSize: '13px',
                                                    textAlign: 'right', fontFamily: 'monospace', color: '#64748b',
                                                }}>
                                                    {fmtNGN(item.warrants_released)}
                                                </td>
                                                <td style={{
                                                    padding: '10px 14px', fontSize: '13px',
                                                    textAlign: 'right', fontFamily: 'monospace',
                                                }}>
                                                    {fmtNGN(item.actual_expenditure)}
                                                </td>
                                                <td style={{
                                                    padding: '10px 14px', fontSize: '13px',
                                                    textAlign: 'right', fontFamily: 'monospace',
                                                    color: variance >= 0 ? '#16a34a' : '#dc2626',
                                                    fontWeight: 600,
                                                }}>
                                                    {fmtNGN(variance)}
                                                </td>
                                                <td style={{
                                                    padding: '10px 14px', fontSize: '13px',
                                                    textAlign: 'right', fontWeight: 700,
                                                    color: execColor(pct),
                                                }}>
                                                    {pct.toFixed(1)}%
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                                {data.totals && (
                                    <tfoot>
                                        <tr style={{ background: '#f0f4f8', borderTop: '2px solid #1e293b' }}>
                                            <td colSpan={3} style={{
                                                padding: '12px 14px', fontWeight: 800, fontSize: '14px',
                                            }}>
                                                TOTAL
                                            </td>
                                            <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 800, fontFamily: 'monospace' }}>
                                                {fmtNGN(data.totals.total_original_budget)}
                                            </td>
                                            <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 800, fontFamily: 'monospace' }}>
                                                {fmtNGN(data.totals.total_final_budget)}
                                            </td>
                                            <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 800, fontFamily: 'monospace' }}>
                                                {fmtNGN(data.totals.total_warrants)}
                                            </td>
                                            <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 800, fontFamily: 'monospace' }}>
                                                {fmtNGN(data.totals.total_expended)}
                                            </td>
                                            <td style={{
                                                padding: '12px 14px', textAlign: 'right',
                                                fontWeight: 800, fontFamily: 'monospace',
                                                color: parseFloat(String(data.totals.total_variance ?? '0')) >= 0 ? '#16a34a' : '#dc2626',
                                            }}>
                                                {fmtNGN(data.totals.total_variance)}
                                            </td>
                                            <td style={{
                                                padding: '12px 14px', textAlign: 'right',
                                                fontWeight: 800, fontSize: '14px',
                                                color: execColor(Number(data.totals.overall_execution_pct ?? 0)),
                                            }}>
                                                {Number(data.totals.overall_execution_pct ?? 0).toFixed(1)}%
                                            </td>
                                        </tr>
                                    </tfoot>
                                )}
                            </table>
                        </div>
                        {(!data.items || data.items.length === 0) && (
                            <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                                No active appropriations for this fiscal year.
                            </div>
                        )}
                    </div>
                ) : null}
            </main>
        </div>
    );
}
