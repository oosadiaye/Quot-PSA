/**
 * IPSAS 1 — Statement of Changes in Net Assets / Equity — Quot PSE
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

const fmtNGN = (v: number | string): string => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return 'NGN ' + (Number.isFinite(n) ? n : 0).toLocaleString('en-NG', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
};

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

    const renderCell = (value: number | string, style?: 'opening' | 'total' | 'movement') => {
        const n = parseFloat(String(value));
        const color = n < 0 ? '#dc2626' : '#1e293b';
        return (
            <td style={{
                padding: '10px 14px', textAlign: 'right', fontFamily: 'monospace',
                fontSize: '14px',
                fontWeight: style === 'total' || style === 'opening' ? 800 : 500,
                color,
            }}>
                {fmtNGN(value)}
            </td>
        );
    };

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
                            Statement of Changes in Net Assets / Equity
                        </h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>
                            IPSAS 1 — Movement in Net Assets / Accumulated Fund
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <select
                            value={fy}
                            onChange={e => setFy(parseInt(e.target.value))}
                            style={{
                                padding: '8px 12px', borderRadius: '8px',
                                border: '1px solid #e2e8f0', fontSize: '14px',
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
                                border: '1px solid #e2e8f0', background: '#fff',
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
                    <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                        Loading...
                    </div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/changes-in-net-assets/" />
                ) : data ? (
                    <div style={{ maxWidth: '900px' }}>
                        <div style={{
                            background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1',
                            overflow: 'hidden', marginBottom: '20px',
                        }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e8ecf1' }}>
                                        <th style={{
                                            padding: '12px 14px', textAlign: 'left',
                                            fontSize: '11px', fontWeight: 700, color: '#64748b',
                                            textTransform: 'uppercase', letterSpacing: '0.5px',
                                        }}>
                                            Component
                                        </th>
                                        <th style={{
                                            padding: '12px 14px', textAlign: 'right',
                                            fontSize: '11px', fontWeight: 700, color: '#64748b',
                                            textTransform: 'uppercase', letterSpacing: '0.5px',
                                        }}>
                                            FY {fy}
                                        </th>
                                        <th style={{
                                            padding: '12px 14px', textAlign: 'right',
                                            fontSize: '11px', fontWeight: 700, color: '#64748b',
                                            textTransform: 'uppercase', letterSpacing: '0.5px',
                                        }}>
                                            FY {fy - 1} (Comparative)
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {ROWS.map(row => {
                                        const isTotal = row.style === 'total';
                                        const isOpening = row.style === 'opening';
                                        return (
                                            <tr
                                                key={row.key}
                                                style={{
                                                    borderTop: isTotal ? '2px solid #1e293b' : undefined,
                                                    borderBottom: '1px solid #f1f5f9',
                                                    background: isTotal ? '#f0f4f8' :
                                                                isOpening ? '#fafbfc' : undefined,
                                                }}
                                            >
                                                <td style={{
                                                    padding: '10px 14px', fontSize: '14px',
                                                    fontWeight: isTotal || isOpening ? 800 : 500,
                                                    color: '#1e293b',
                                                }}>
                                                    {row.label}
                                                </td>
                                                {renderCell(data[row.key] as number | string, row.style)}
                                                {renderCell(
                                                    data.comparative?.[row.key] as number | string ?? 0,
                                                    row.style,
                                                )}
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>

                        {/* Reconciliation check */}
                        <div style={{
                            background: data.reconciliation?.reconciles ? '#f0fdf4' : '#fef2f2',
                            border: `2px solid ${data.reconciliation?.reconciles ? '#22c55e' : '#ef4444'}`,
                            borderRadius: '12px', padding: '20px', textAlign: 'center',
                        }}>
                            <div style={{
                                fontSize: '14px', fontWeight: 800,
                                color: data.reconciliation?.reconciles ? '#16a34a' : '#dc2626',
                                textTransform: 'uppercase', letterSpacing: '0.5px',
                            }}>
                                {data.reconciliation?.reconciles ? 'RECONCILED' : 'NOT RECONCILED'}
                            </div>
                            <div style={{ fontSize: '12px', color: '#64748b', marginTop: '6px' }}>
                                Computed: {fmtNGN(data.reconciliation?.computed)} ·
                                Reported: {fmtNGN(data.reconciliation?.reported)} ·
                                Tolerance: {data.reconciliation?.tolerance}
                            </div>
                        </div>
                    </div>
                ) : null}

                <div style={{
                    textAlign: 'center', padding: '20px 0',
                    color: '#94a3b8', fontSize: '11px',
                }}>
                    Quot PSE IFMIS — IPSAS 1 Compliant
                </div>
            </main>
        </div>
    );
}
