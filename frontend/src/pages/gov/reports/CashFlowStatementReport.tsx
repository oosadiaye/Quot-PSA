/**
 * IPSAS 2 — Cash Flow Statement (Direct Method) — Quot PSA
 * Route: /accounting/ipsas/cash-flow
 *
 * Three activity sections (Operating / Investing / Financing), each with
 * inflows and outflows, plus net change in cash and opening/closing
 * reconciliation.
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

type AmountMap = Record<string, number | string>;

interface ActivitySection {
    inflows:  AmountMap;
    outflows: AmountMap;
    net:      number | string;
}

interface CashFlowResponse {
    title: string;
    standard: string;
    fiscal_year: number;
    currency: string;
    operating_activities: ActivitySection;
    investing_activities: ActivitySection;
    financing_activities: ActivitySection;
    opening_cash:       number | string;
    closing_cash:       number | string;
    net_change_in_cash: number | string;
    reconciliation: {
        opening_plus_change: number | string;
        closing_balance:     number | string;
        reconciles:          boolean;
        tolerance:           string;
    };
}

const prettify = (k: string): string =>
    k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

const num = (v: number | string | undefined): number => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return Number.isFinite(n as number) ? (n as number) : 0;
};

/** One activity: what came in, what went out (shown as a deduction), and the net. */
function activityRows(label: string, section: ActivitySection | undefined): SheetRow[] {
    const inflows = Object.entries(section?.inflows ?? {});
    const outflows = Object.entries(section?.outflows ?? {});
    return [
        { kind: 'section', label },
        ...(inflows.length ? [{ kind: 'group', label: 'Cash inflows' } as SheetRow, ...inflows.map(([k, v]): SheetRow => ({ kind: 'item', label: prettify(k), values: [num(v)] }))] : []),
        ...(outflows.length ? [{ kind: 'group', label: 'Cash outflows' } as SheetRow, ...outflows.map(([k, v]): SheetRow => ({ kind: 'item', label: prettify(k), values: [-num(v)] }))] : []),
        { kind: 'total', label: `Net cash from ${label.toLowerCase()}`, values: [num(section?.net)] },
    ];
}

export default function CashFlowStatementReport() {
    const [fy, setFy] = useState<number>(new Date().getFullYear());
    const [period, setPeriod] = useState<string>('');

    const { data, isLoading, error } = useQuery<CashFlowResponse>({
        queryKey: ['ipsas-cash-flow', fy, period],
        queryFn: async () => {
            const params: Record<string, string | number> = { fiscal_year: fy };
            if (period) params.period = period;
            const res = await apiClient.get('/accounting/ipsas/cash-flow/', { params });
            return res.data;
        },
        retry: false,
    });

    const rows: SheetRow[] = data ? [
        ...activityRows('Operating Activities', data.operating_activities),
        ...activityRows('Investing Activities', data.investing_activities),
        ...activityRows('Financing Activities', data.financing_activities),
        { kind: 'section', label: 'Cash and cash equivalents' },
        { kind: 'item', label: 'Opening cash balance', values: [num(data.opening_cash)] },
        { kind: 'item', label: 'Net change in cash', values: [num(data.net_change_in_cash)] },
        { kind: 'grand', label: 'CLOSING CASH BALANCE', values: [num(data.closing_cash)] },
        {
            kind: 'note',
            label: data.reconciliation?.reconciles
                ? 'Reconciled: opening balance plus the net change equals the closing balance.'
                : 'NOT RECONCILED: opening balance plus the net change does not equal the closing balance. Investigate.',
        },
    ] : [];

    return (
        <div style={{ background: 'var(--color-surface-hover)', minHeight: '100vh' }}>
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
                    <BrandedPrintHeader subtitle="Cash Flow Statement · IPSAS 2" />
                </div>
                <div className="no-print" style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    marginBottom: '24px',
                }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 800, color: 'var(--color-text)', margin: 0 }}>
                            Cash Flow Statement
                        </h1>
                        <p style={{ color: 'var(--color-text-muted)', fontSize: '14px', margin: '4px 0 0' }}>
                            IPSAS 2 — Direct Method (Operating / Investing / Financing)
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <select
                            value={fy}
                            onChange={e => setFy(parseInt(e.target.value))}
                            style={{
                                padding: '8px 12px', borderRadius: '8px',
                                border: '1px solid var(--color-border)', fontSize: '14px',
                            }}
                        >
                            {[2024, 2025, 2026, 2027].map(y => (
                                <option key={y} value={y}>FY {y}</option>
                            ))}
                        </select>
                        <select
                            value={period}
                            onChange={e => setPeriod(e.target.value)}
                            style={{
                                padding: '8px 12px', borderRadius: '8px',
                                border: '1px solid var(--color-border)', fontSize: '14px',
                            }}
                        >
                            <option value="">Full year</option>
                            {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
                                <option key={m} value={m}>Through period {m}</option>
                            ))}
                        </select>
                        <button
                            onClick={() => window.print()}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '6px',
                                padding: '8px 16px', borderRadius: '8px',
                                border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                                cursor: 'pointer', fontSize: '14px',
                            }}
                        >
                            <Printer size={16} /> Print
                        </button>
                        <ExportExcelButton
                            endpoint="/accounting/ipsas/cash-flow/"
                            params={{ fiscal_year: fy, period: period || undefined }}
                            filename={`cashflow-${fy}${period ? '-' + period : ''}.xlsx`}
                        />
                    </div>
                </div>

                {isLoading ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: 'var(--color-text-subtle)' }}>
                        Loading...
                    </div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/cash-flow/" />
                ) : data ? (
                    <StatementSheet testId="sheet-cashflow" caption={`Cash Flow Statement (direct method) for the year ${fy}${period ? `, through period ${period}` : ''}`}
                        valueColumns={[`FY ${fy}`]} rows={rows} />
                ) : null}

                <div style={{
                    textAlign: 'center', padding: '20px 0',
                    color: 'var(--color-text-subtle)', fontSize: '11px',
                }}>
                    Quot PSA IFMIS — IPSAS 2 Compliant
                </div>
            </main>
        </div>
    );
}
