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
import StatementSheet, { sheetFigure, type SheetRow } from '../../../components/statement/StatementSheet';

interface Line { code?: string; name: string; amount: number; direct_amount?: number; is_header?: boolean }
interface Section { items?: Line[]; total?: number }

const GROUP_NOTE = 'Posted directly to a group account. Included so the statement adds up; move these postings to a leaf account.';

/**
 * A header's ``amount`` is the roll-up of its children, which are listed individually, so showing both would read as double
 * counting and header rows stay hidden. The exception is ``direct_amount``: a balance posted to the header itself, represented
 * by no child line. It is counted in the section total, so it is shown (flagged) to keep the visible lines adding up.
 */
function lines(items: Line[] | undefined): SheetRow[] {
    return (items ?? [])
        .filter((i) => !i.is_header || Number(i.direct_amount || 0) !== 0)
        .map((i): SheetRow => {
            const posted = !!i.is_header && Number(i.direct_amount || 0) !== 0;
            return { kind: 'item', code: i.code, label: i.name, values: [posted ? i.direct_amount : i.amount], flag: posted ? GROUP_NOTE : undefined };
        });
}

/** Accounts in the family but outside the statement's named sub-families: shown only when there is something, so a well-coded chart has no extra heading. */
function unclassified(section: Section | undefined, label: string): SheetRow[] {
    const items = (section?.items ?? []).filter((i) => Number(i.amount) !== 0);
    if (items.length === 0) return [];
    return [
        { kind: 'group', label },
        { kind: 'note', label: 'Not yet assigned to a statement heading; give these codes a sub-family so they report in the right place.' },
        ...lines(items),
        { kind: 'subtotal', label: `Total ${label}`, values: [section?.total ?? 0] },
    ];
}

export default function FinancialPositionReport() {
    const [fy, setFy] = useState(new Date().getFullYear());

    const { data, isLoading, error } = useQuery({
        queryKey: ['ipsas-financial-position', fy],
        queryFn: async () => (await apiClient.get('/accounting/ipsas/financial-position/', { params: { fiscal_year: fy } })).data,
        retry: false,
    });

    const balanced = !!data?.balance_check?.is_balanced;
    const rows: SheetRow[] = data ? [
        { kind: 'section', label: 'Assets' },
        { kind: 'group', label: 'Current Assets' }, ...lines(data.assets?.current?.items),
        { kind: 'subtotal', label: 'Total Current Assets', values: [data.assets?.current?.total ?? 0] },
        { kind: 'group', label: 'Non-Current Assets' }, ...lines(data.assets?.non_current?.items),
        { kind: 'subtotal', label: 'Total Non-Current Assets', values: [data.assets?.non_current?.total ?? 0] },
        ...unclassified(data.assets?.unclassified, 'Unclassified Assets'),
        { kind: 'total', label: 'TOTAL ASSETS', values: [data.assets?.total ?? 0] },
        { kind: 'section', label: 'Liabilities' },
        { kind: 'group', label: 'Current Liabilities' }, ...lines(data.liabilities?.current?.items),
        { kind: 'subtotal', label: 'Total Current Liabilities', values: [data.liabilities?.current?.total ?? 0] },
        { kind: 'group', label: 'Non-Current Liabilities' }, ...lines(data.liabilities?.non_current?.items),
        { kind: 'subtotal', label: 'Total Non-Current Liabilities', values: [data.liabilities?.non_current?.total ?? 0] },
        ...unclassified(data.liabilities?.unclassified, 'Unclassified Liabilities'),
        { kind: 'total', label: 'TOTAL LIABILITIES', values: [data.liabilities?.total ?? 0] },
        { kind: 'section', label: 'Net Assets / Equity' }, ...lines(data.net_assets?.items),
        { kind: 'total', label: 'TOTAL NET ASSETS', values: [data.net_assets?.total ?? 0] },
        { kind: 'grand', label: 'TOTAL LIABILITIES AND NET ASSETS', values: [data.balance_check?.liabilities_plus_net_assets ?? 0] },
        {
            kind: 'note',
            label: balanced
                ? 'The statement balances: total assets equal total liabilities and net assets.'
                : `NOT BALANCED: total assets ${sheetFigure(data.balance_check?.assets)} against liabilities and net assets ${sheetFigure(data.balance_check?.liabilities_plus_net_assets)}.`,
        },
    ] : [];

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
                        <select value={fy} onChange={e => setFy(parseInt(e.target.value))} style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid var(--color-border)', fontSize: '14px' }}>
                            {[2024, 2025, 2026, 2027].map(y => <option key={y} value={y}>FY {y}</option>)}
                        </select>
                        <button onClick={() => window.print()} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', cursor: 'pointer', fontSize: '14px' }}>
                            <Printer size={16} /> Print
                        </button>
                        <ExportExcelButton
                            endpoint="/accounting/ipsas/financial-position/"
                            params={{ fiscal_year: fy }}
                            filename={`sofp-${fy}.xlsx`}
                        />
                    </div>
                </div>

                {isLoading ? (
                    <div style={{ color: 'var(--color-text-subtle)', textAlign: 'center', padding: '40px' }}>Loading...</div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/financial-position/" />
                ) : data ? (
                    <StatementSheet testId="sheet-position" caption={`Statement of Financial Position as at 31 December ${fy}`}
                        valueColumns={[`FY ${fy}`]} rows={rows} />
                ) : null}

                <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--color-text-subtle)', fontSize: '11px' }}>
                    Quot PSA IFMIS — IPSAS 1 Compliant
                </div>
            </main>
        </div>
    );
}
