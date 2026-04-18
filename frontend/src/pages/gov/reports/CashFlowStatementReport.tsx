/**
 * IPSAS 2 — Cash Flow Statement (Direct Method) — Quot PSE
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
import apiClient from '../../../api/client';
import ReportError from './ReportError';
import ExportExcelButton from './ExportExcelButton';

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

const fmtNGN = (v: number | string): string => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return 'NGN ' + (Number.isFinite(n) ? n : 0).toLocaleString('en-NG', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
};

const prettify = (k: string): string =>
    k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

interface SectionProps {
    label: string;
    accent: string;
    section: ActivitySection | undefined;
}

function Section({ label, accent, section }: SectionProps) {
    const inflows = Object.entries(section?.inflows ?? {});
    const outflows = Object.entries(section?.outflows ?? {});
    const net = section?.net ?? 0;

    return (
        <div style={{
            background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1',
            padding: '24px', marginBottom: '20px',
        }}>
            <div style={{
                fontSize: '14px', fontWeight: 800, color: accent,
                marginBottom: '16px', textTransform: 'uppercase', letterSpacing: '0.5px',
            }}>
                {label}
            </div>

            {inflows.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                    <div style={{
                        fontSize: '12px', fontWeight: 700, color: '#16a34a',
                        marginBottom: '6px', textTransform: 'uppercase',
                    }}>
                        Inflows
                    </div>
                    {inflows.map(([k, v]) => (
                        <div key={k} style={{
                            display: 'flex', justifyContent: 'space-between',
                            padding: '5px 0 5px 20px', borderBottom: '1px solid #f8fafc',
                        }}>
                            <span style={{ fontSize: '13px', color: '#1e293b' }}>{prettify(k)}</span>
                            <span style={{
                                fontSize: '13px', fontWeight: 600, fontFamily: 'monospace',
                            }}>
                                {fmtNGN(v)}
                            </span>
                        </div>
                    ))}
                </div>
            )}

            {outflows.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                    <div style={{
                        fontSize: '12px', fontWeight: 700, color: '#dc2626',
                        marginBottom: '6px', textTransform: 'uppercase',
                    }}>
                        Outflows
                    </div>
                    {outflows.map(([k, v]) => (
                        <div key={k} style={{
                            display: 'flex', justifyContent: 'space-between',
                            padding: '5px 0 5px 20px', borderBottom: '1px solid #f8fafc',
                        }}>
                            <span style={{ fontSize: '13px', color: '#1e293b' }}>{prettify(k)}</span>
                            <span style={{
                                fontSize: '13px', fontWeight: 600, fontFamily: 'monospace',
                                color: '#64748b',
                            }}>
                                ({fmtNGN(v)})
                            </span>
                        </div>
                    ))}
                </div>
            )}

            <div style={{
                display: 'flex', justifyContent: 'space-between',
                padding: '10px 12px', marginTop: '8px',
                background: `${accent}0d`, borderRadius: '6px',
                borderTop: `2px solid ${accent}`,
            }}>
                <span style={{ fontWeight: 800, fontSize: '13px', color: accent }}>
                    Net Cash from {label}
                </span>
                <span style={{
                    fontWeight: 800, fontSize: '14px', fontFamily: 'monospace',
                    color: parseFloat(String(net)) < 0 ? '#dc2626' : accent,
                }}>
                    {fmtNGN(net)}
                </span>
            </div>
        </div>
    );
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
                            Cash Flow Statement
                        </h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>
                            IPSAS 2 — Direct Method (Operating / Investing / Financing)
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
                        <select
                            value={period}
                            onChange={e => setPeriod(e.target.value)}
                            style={{
                                padding: '8px 12px', borderRadius: '8px',
                                border: '1px solid #e2e8f0', fontSize: '14px',
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
                                border: '1px solid #e2e8f0', background: '#fff',
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
                    <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                        Loading...
                    </div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/cash-flow/" />
                ) : data ? (
                    <div style={{ maxWidth: '900px' }}>
                        <Section label="Operating Activities" accent="#008751" section={data.operating_activities} />
                        <Section label="Investing Activities" accent="#1e4d8c" section={data.investing_activities} />
                        <Section label="Financing Activities" accent="#9333ea" section={data.financing_activities} />

                        {/* Summary reconciliation */}
                        <div style={{
                            background: '#fff', borderRadius: '12px',
                            border: `2px solid ${data.reconciliation?.reconciles ? '#22c55e' : '#ef4444'}`,
                            padding: '24px',
                        }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <tbody>
                                    <ReconRow label="Opening Cash Balance" value={data.opening_cash} />
                                    <ReconRow label="Net Change in Cash"    value={data.net_change_in_cash} bold />
                                    <ReconRow
                                        label="Closing Cash Balance"
                                        value={data.closing_cash}
                                        bold
                                        borderTop
                                    />
                                </tbody>
                            </table>
                            <div style={{
                                marginTop: 16,
                                padding: '12px 16px',
                                borderRadius: 8,
                                background: data.reconciliation?.reconciles ? '#f0fdf4' : '#fef2f2',
                                color: data.reconciliation?.reconciles ? '#16a34a' : '#dc2626',
                                fontSize: 13, fontWeight: 700, textAlign: 'center',
                                letterSpacing: '0.5px', textTransform: 'uppercase',
                            }}>
                                {data.reconciliation?.reconciles
                                    ? '✓ Reconciled (Opening + Net Change = Closing)'
                                    : '✗ Not Reconciled — investigate'}
                            </div>
                        </div>
                    </div>
                ) : null}

                <div style={{
                    textAlign: 'center', padding: '20px 0',
                    color: '#94a3b8', fontSize: '11px',
                }}>
                    Quot PSE IFMIS — IPSAS 2 Compliant
                </div>
            </main>
        </div>
    );
}

interface ReconRowProps {
    label: string;
    value: number | string;
    bold?: boolean;
    borderTop?: boolean;
}

function ReconRow({ label, value, bold, borderTop }: ReconRowProps) {
    return (
        <tr style={{ borderTop: borderTop ? '2px solid #1e293b' : undefined }}>
            <td style={{
                padding: '10px 0', fontSize: '14px',
                fontWeight: bold ? 800 : 500,
                color: '#1e293b',
            }}>
                {label}
            </td>
            <td style={{
                padding: '10px 0', textAlign: 'right', fontFamily: 'monospace',
                fontSize: '14px', fontWeight: bold ? 800 : 600,
                color: parseFloat(String(value)) < 0 ? '#dc2626' : '#1e293b',
            }}>
                {fmtNGN(value)}
            </td>
        </tr>
    );
}
