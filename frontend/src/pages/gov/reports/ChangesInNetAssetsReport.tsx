/**
 * IPSAS 1 — Statement of Changes in Net Assets / Equity — Quot PSA
 * Route: /accounting/ipsas/changes-in-net-assets
 *
 * Movement from opening net assets → surplus/deficit → revaluation →
 * contributions/distributions → other → closing net assets, with a
 * reconciliation check and prior-year comparative.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Printer } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import apiClient from '../../../api/client';
import ReportError from './ReportError';
import ExportExcelButton from './ExportExcelButton';
import StatementSheet, { sheetFigure, type SheetRow } from '../../../components/statement/StatementSheet';

interface ChangesInnerBlock {
    opening_balance:      number | string;
    surplus_deficit:      number | string;
    revaluation_gains:    number | string;
    owner_contributions:  number | string;
    owner_distributions:  number | string;
    other_movements:      number | string;
    closing_balance:      number | string;
    reconciliation: {
        computed: number | string;
        reported: number | string;
        reconciles: boolean;
        tolerance: string;
    };
}

interface ChangesResponse extends ChangesInnerBlock {
    title: string;
    standard: string;
    fiscal_year: number;
    period: number | null;
    currency: string;
    comparative: ChangesInnerBlock | null;
}

const ROWS: Array<{ key: keyof ChangesInnerBlock; label: string; style?: 'opening' | 'total' | 'movement' }> = [
    { key: 'opening_balance',      label: 'Opening Balance',                         style: 'opening'  },
    { key: 'surplus_deficit',      label: 'Surplus / (Deficit) for the Period',      style: 'movement' },
    { key: 'revaluation_gains',    label: 'Revaluation Gains / (Losses)',            style: 'movement' },
    { key: 'owner_contributions',  label: 'Contributions from Owners (FAAC / Grants)', style: 'movement' },
    { key: 'owner_distributions',  label: 'Distributions to Owners',                 style: 'movement' },
    { key: 'other_movements',      label: 'Other Movements',                         style: 'movement' },
    { key: 'closing_balance',      label: 'Closing Balance',                         style: 'total'    },
];

export default function ChangesInNetAssetsReport() {
    const [fy, setFy] = useState<number>(new Date().getFullYear());

    const { data, isLoading, error } = useQuery<ChangesResponse>({
        queryKey: ['ipsas-changes-in-net-assets', fy],
        queryFn: async () => {
            const res = await apiClient.get('/accounting/ipsas/changes-in-net-assets/', {
                params: { fiscal_year: fy },
            });
            return res.data;
        },
        retry: false,
    });

    const num = (v: number | string | undefined | null): number => {
        const n = parseFloat(String(v ?? 0));
        return Number.isFinite(n) ? n : 0;
    };
    const rows: SheetRow[] = data ? [
        ...ROWS.map((row): SheetRow => {
            const values = [num(data[row.key] as number | string), num(data.comparative?.[row.key] as number | string | undefined)];
            if (row.style === 'total') return { kind: 'total', label: row.label, values };
            if (row.style === 'opening') return { kind: 'subtotal', label: row.label, values };
            return { kind: 'item', label: row.label, values };
        }),
        {
            kind: 'note',
            label: data.reconciliation?.reconciles
                ? `Reconciled: the movements add up to the closing balance (computed ${sheetFigure(data.reconciliation?.computed)}, reported ${sheetFigure(data.reconciliation?.reported)}).`
                : `NOT RECONCILED: computed ${sheetFigure(data.reconciliation?.computed)} against reported ${sheetFigure(data.reconciliation?.reported)} (tolerance ${data.reconciliation?.tolerance}).`,
        },
    ] : [];

    return (
        <div style={{ background: 'var(--color-surface-hover)', minHeight: '100vh' }}>
            <Sidebar />
            <main className="ipsas-report" style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    marginBottom: '24px',
                }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 800, color: 'var(--color-text)', margin: 0 }}>
                            Statement of Changes in Net Assets / Equity
                        </h1>
                        <p style={{ color: 'var(--color-text-muted)', fontSize: '14px', margin: '4px 0 0' }}>
                            IPSAS 1 — Movement in Net Assets / Accumulated Fund
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
                            endpoint="/accounting/ipsas/changes-in-net-assets/"
                            params={{ fiscal_year: fy }}
                            filename={`changes-in-net-assets-${fy}.xlsx`}
                        />
                    </div>
                </div>

                {isLoading ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: 'var(--color-text-subtle)' }}>
                        Loading...
                    </div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/changes-in-net-assets/" />
                ) : data ? (
                    <StatementSheet testId="sheet-changes" caption={`Statement of Changes in Net Assets / Equity for the year ${fy}`}
                        valueColumns={[`FY ${fy}`, `FY ${fy - 1} (comparative)`]} rows={rows} />
                ) : null}

                <div style={{
                    textAlign: 'center', padding: '20px 0',
                    color: 'var(--color-text-subtle)', fontSize: '11px',
                }}>
                    Quot PSA IFMIS — IPSAS 1 Compliant
                </div>
            </main>
        </div>
    );
}
