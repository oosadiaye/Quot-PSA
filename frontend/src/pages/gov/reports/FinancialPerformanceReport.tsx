/**
 * IPSAS Statement of Financial Performance (Income & Expenditure) — Quot PSA
 * Route: /accounting/ipsas/financial-performance
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Printer } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import BrandedPrintHeader from '../../../components/print/BrandedPrintHeader';
import apiClient from '../../../api/client';
import ReportError from './ReportError';
import ExportExcelButton from './ExportExcelButton';
import StatementSheet, { type SheetRow } from '../../../components/statement/StatementSheet';

interface Item { code?: string; name: string; amount: number; is_header?: boolean }
interface Group { items?: Item[]; total?: number }

const GROUP_NOTE = 'Posted directly to a group account. Included so the statement adds up; move these postings to a leaf account.';

/** One heading, its lines, and its sub-total, for each family of the statement that has any lines. */
function familyRows(groups: [string, Group | undefined, boolean?][]): SheetRow[] {
    return groups.flatMap(([label, g, onlyIfAny]) => {
        const items = g?.items ?? [];
        if (onlyIfAny && items.length === 0) return [];
        return [
            { kind: 'group', label } as SheetRow,
            ...items.map((i): SheetRow => ({ kind: 'item', code: i.code, label: i.name, values: [i.amount], flag: i.is_header ? GROUP_NOTE : undefined })),
            { kind: 'subtotal', label: `Total ${label}`, values: [g?.total ?? 0] } as SheetRow,
        ];
    });
}

export default function FinancialPerformanceReport() {
    const [fy, setFy] = useState(new Date().getFullYear());

    const { data, isLoading, error } = useQuery({
        queryKey: ['ipsas-financial-performance', fy],
        queryFn: async () => (await apiClient.get('/accounting/ipsas/financial-performance/', { params: { fiscal_year: fy } })).data,
        retry: false,
    });

    const rows: SheetRow[] = data ? [
        { kind: 'section', label: 'Revenue' },
        ...familyRows([
            ['Tax Revenue', data.revenue?.tax_revenue],
            ['Non-Tax Revenue', data.revenue?.non_tax_revenue],
            ['Grants & Transfers', data.revenue?.grants_transfers],
            ['Other Revenue', data.revenue?.other_revenue],
            // Family 1 outside 11-14: shown only when there is something, so a well-coded chart has no extra heading.
            ['Unclassified Revenue (assign a sub-family)', data.revenue?.unclassified, true],
        ]),
        { kind: 'total', label: 'TOTAL REVENUE', values: [data.revenue?.total ?? 0] },
        { kind: 'section', label: 'Expenditure' },
        ...familyRows([
            ['Personnel Costs', data.expenditure?.personnel_costs],
            ['Overhead / O&M', data.expenditure?.overhead_costs],
            ['Capital Expenditure', data.expenditure?.capital_expenditure],
            ['Debt Service', data.expenditure?.debt_service],
            ['Transfers & Subventions', data.expenditure?.transfers_subventions],
            // Missing expenditure reads as underspend, so anything outside the families is shown.
            ['Unclassified Expenditure (assign a sub-family)', data.expenditure?.unclassified, true],
        ]),
        { kind: 'total', label: 'TOTAL EXPENDITURE', values: [data.expenditure?.total ?? 0] },
        { kind: 'grand', label: 'SURPLUS / (DEFICIT) FOR THE PERIOD', values: [data.surplus_deficit ?? 0] },
    ] : [];

    return (
        <div style={{ background: 'var(--color-surface-hover)', minHeight: '100vh' }}>
            {/* See FinancialPositionReport for the rationale on the
                print-only branded header pattern. Same approach
                everywhere so a printed report carries the tenant's
                logo + contact details no matter where it travels. */}
            <style>{`
                @media print {
                    aside, nav, .no-print { display: none !important; }
                    .print-only { display: block !important; }
                    main.ipsas-report { margin-left: 0 !important; padding: 16mm !important; }
                    body { background: white !important; }
                }
                .print-only { display: none; }
            `}</style>
            <Sidebar />
            <main className="ipsas-report" style={{ marginLeft: '260px', padding: '32px' }}>
                <div className="print-only" style={{ marginBottom: 16 }}>
                    <BrandedPrintHeader subtitle="Statement of Financial Performance · IPSAS 1" />
                    <div style={{ marginTop: 8, fontSize: 11, color: 'var(--color-text-secondary)', textAlign: 'center' }}>
                        Fiscal Year: <strong>FY {fy}</strong>
                    </div>
                </div>
                <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 800, color: 'var(--color-text)', margin: 0 }}>Statement of Financial Performance</h1>
                        <p style={{ color: 'var(--color-text-muted)', fontSize: '14px', margin: '4px 0 0' }}>IPSAS 1 — Income and Expenditure Statement</p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <select value={fy} onChange={e => setFy(parseInt(e.target.value))} style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid var(--color-border)', fontSize: '14px' }}>
                            {[2024, 2025, 2026, 2027].map(y => <option key={y} value={y}>FY {y}</option>)}
                        </select>
                        <button onClick={() => window.print()} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', cursor: 'pointer', fontSize: '14px' }}>
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
                    <div style={{ color: 'var(--color-text-subtle)', textAlign: 'center', padding: '40px' }}>Loading...</div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/financial-performance/" />
                ) : data ? (
                    <StatementSheet testId="sheet-performance" caption={`Statement of Financial Performance for the year ended 31 December ${fy}`}
                        valueColumns={[`FY ${fy}`]} rows={rows} />
                ) : null}
            </main>
        </div>
    );
}
