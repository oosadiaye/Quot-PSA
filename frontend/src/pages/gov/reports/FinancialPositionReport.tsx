/**
 * IPSAS Statement of Financial Position (Balance Sheet) — Quot PSA
 * Route: /accounting/ipsas/financial-position
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Printer } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import apiClient from '../../../api/client';
import ReportError from './ReportError';
import ExportExcelButton from './ExportExcelButton';
import BrandedPrintHeader from '../../../components/print/BrandedPrintHeader';
import StatementSheet from '../../../components/statement/StatementSheet';
import { buildPositionRows, positionColumns } from './positionRows';

const FIRST_YEAR = 2020;
const LAST_YEAR = 2030;

export default function FinancialPositionReport() {
    const [fy, setFy] = useState(new Date().getFullYear());
    // What to set it against: the year before (the default), none, or any particular year.
    const [against, setAgainst] = useState<string>('prior');
    const compareYear = against === 'none' ? null : against === 'prior' ? fy - 1 : Number(against);
    const comparing = compareYear !== null;

    const { data, isLoading, error } = useQuery({
        queryKey: ['ipsas-financial-position', fy, compareYear],
        queryFn: async () => (await apiClient.get('/accounting/ipsas/financial-position/', {
            params: { fiscal_year: fy, comparative: comparing, ...(comparing ? { compare_year: compareYear } : {}) },
        })).data,
        retry: false,
    });

    const rows = data ? buildPositionRows(data, comparing) : [];
    const columns = positionColumns(fy, compareYear);

    return (
        <div style={{ background: 'var(--color-surface-hover)', minHeight: '100vh' }}>
            {/* Print-only stylesheet: hide the sidebar + screen header,
                show the BrandedPrintHeader + report cards. The
                ``.print-only`` block is invisible on screen but appears
                at the top of every printed page so the report carries
                the tenant's branding (logo, name, address) wherever it
                travels. The screen-only version of the page-header
                stays unchanged so day-to-day use isn't affected. */}
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
                    <BrandedPrintHeader subtitle="Statement of Financial Position · IPSAS 1" />
                    <div style={{ marginTop: 8, fontSize: 11, color: 'var(--color-text-secondary)', textAlign: 'center' }}>
                        Fiscal Year: <strong>FY {fy}</strong>
                    </div>
                </div>

                <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 800, color: 'var(--color-text)', margin: 0 }}>Statement of Financial Position</h1>
                        <p style={{ color: 'var(--color-text-muted)', fontSize: '14px', margin: '4px 0 0' }}>IPSAS 1 — Balance Sheet</p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <select aria-label="Fiscal year" value={fy} onChange={e => setFy(parseInt(e.target.value))} style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid var(--color-border)', fontSize: '14px' }}>
                            {Array.from({ length: LAST_YEAR - FIRST_YEAR + 1 }, (_, n) => FIRST_YEAR + n).map(y => <option key={y} value={y}>FY {y}</option>)}
                        </select>
                        <select aria-label="Compare with" data-testid="compare-with" value={against} onChange={e => setAgainst(e.target.value)} style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid var(--color-border)', fontSize: '14px' }}>
                            <option value="prior">Compare with FY {fy - 1} (previous year)</option>
                            <option value="none">No comparison</option>
                            {Array.from({ length: LAST_YEAR - FIRST_YEAR + 1 }, (_, n) => FIRST_YEAR + n).filter(y => y !== fy && y !== fy - 1).map(y => <option key={y} value={y}>Compare with FY {y}</option>)}
                        </select>
                        <button onClick={() => window.print()} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', cursor: 'pointer', fontSize: '14px' }}>
                            <Printer size={16} /> Print
                        </button>
                        <ExportExcelButton
                            endpoint="/accounting/ipsas/financial-position/"
                            params={{ fiscal_year: fy, comparative: comparing ? 'true' : 'false', compare_year: compareYear }}
                            filename={`sofp-${fy}${comparing ? `-vs-${compareYear}` : ''}.xlsx`}
                        />
                    </div>
                </div>

                {isLoading ? (
                    <div style={{ color: 'var(--color-text-subtle)', textAlign: 'center', padding: '40px' }}>Loading...</div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/financial-position/" />
                ) : data ? (
                    <StatementSheet testId="sheet-position" caption={`Statement of Financial Position as at 31 December ${fy}`}
                        valueColumns={columns} rows={rows} />
                ) : null}

                <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--color-text-subtle)', fontSize: '11px' }}>
                    Quot PSA IFMIS — IPSAS 1 Compliant
                </div>
            </main>
        </div>
    );
}
