import { useState } from 'react';
import { Waves, RefreshCw, TrendingUp, Building2, Landmark, ArrowUpDown, Download, FileText } from 'lucide-react';
import { useCashFlow } from '../hooks/useFinancialReports';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import { useCurrency } from '../../../context/CurrencyContext';
import { exportToCSV, exportToPDF } from '../utils/exportReport';
import type { ExportOptions } from '../utils/exportReport';

interface CashSectionProps {
    title: string;
    icon: React.ReactNode;
    rows: { description: string; amount: number }[];
    total: number;
    accentColor: string;
    accentBg: string;
    borderColor: string;
}

function CashSection({ title, icon, rows, total, accentColor, accentBg, borderColor }: CashSectionProps) {
    const { formatCurrency } = useCurrency();

    return (
        <div style={{
            background: '#fff',
            borderRadius: '12px',
            overflow: 'hidden',
            boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
            border: `1.5px solid ${borderColor}`,
        }}>
            {/* Section Header */}
            <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '14px 20px',
                background: accentBg,
                borderBottom: `1.5px solid ${borderColor}`,
            }}>
                <div style={{
                    width: '32px', height: '32px', borderRadius: '8px',
                    background: accentColor, display: 'flex',
                    alignItems: 'center', justifyContent: 'center',
                    color: '#fff', flexShrink: 0,
                }}>
                    {icon}
                </div>
                <span style={{ fontSize: '15px', fontWeight: 700, color: '#1e293b' }}>
                    {title}
                </span>
                <div style={{ flex: 1 }} />
                <span style={{
                    fontSize: '15px', fontWeight: 700,
                    color: total >= 0 ? '#059669' : '#dc2626',
                }}>
                    {total >= 0 ? '+' : '−'}{formatCurrency(Math.abs(total))}
                </span>
            </div>

            {/* Rows */}
            {rows.length === 0 ? (
                <div style={{ padding: '20px', textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>
                    No activity in this period.
                </div>
            ) : (
                <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse' }}>
                    <tbody>
                        {rows.map((r, i) => (
                            <tr key={r.description ?? i}
                                style={{ borderBottom: '1px solid #f1f5f9' }}
                                onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                            >
                                <td style={{ padding: '10px 20px', color: '#334155' }}>
                                    {r.description}
                                </td>
                                <td style={{
                                    padding: '10px 20px',
                                    textAlign: 'right',
                                    fontWeight: 600,
                                    fontFamily: 'monospace',
                                    color: r.amount >= 0 ? '#059669' : '#dc2626',
                                }}>
                                    {r.amount >= 0 ? '+' : '−'}{formatCurrency(Math.abs(r.amount))}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                    <tfoot>
                        <tr style={{ borderTop: '2px solid #e2e8f0' }}>
                            <td style={{ padding: '12px 20px', fontWeight: 700, color: '#1e293b' }}>
                                Net {title}
                            </td>
                            <td style={{
                                padding: '12px 20px',
                                textAlign: 'right',
                                fontWeight: 700,
                                fontSize: '14px',
                                color: total >= 0 ? '#059669' : '#dc2626',
                            }}>
                                {total >= 0 ? '+' : '−'}{formatCurrency(Math.abs(total))}
                            </td>
                        </tr>
                    </tfoot>
                </table>
            )}
        </div>
    );
}

/**
 * Normalize backend response into a consistent shape.
 *
 * Indirect method returns:
 *   { net_income, adjustments: [...], working_capital_changes, operating_cash_flow,
 *     investing_activities: { net }, financing_activities: { net } }
 *
 * Direct method returns:
 *   { operating_activities: { net }, investing_activities: { net },
 *     financing_activities: { net }, details: [...], net_change }
 */
function normalizeCashFlow(data: any) {
    if (!data) {
        return {
            operatingRows: [] as { description: string; amount: number }[],
            investingRows: [] as { description: string; amount: number }[],
            financingRows: [] as { description: string; amount: number }[],
            totalOp: 0,
            totalInv: 0,
            totalFin: 0,
            netChange: 0,
        };
    }

    const isIndirect = data.report_type?.includes('Indirect') || data.net_income !== undefined;

    // --- Operating ---
    const operatingRows: { description: string; amount: number }[] = [];
    let totalOp = 0;

    if (isIndirect) {
        // Indirect: net_income + adjustments + working_capital_changes
        const netIncome = Number(data.net_income ?? 0);
        operatingRows.push({ description: 'Net Income', amount: netIncome });

        const adjustments: any[] = Array.isArray(data.adjustments) ? data.adjustments : [];
        for (const adj of adjustments) {
            operatingRows.push({
                description: adj.description ?? adj.label ?? 'Adjustment',
                amount: Number(adj.amount ?? adj.value ?? 0),
            });
        }

        const wcChange = Number(data.working_capital_changes ?? 0);
        if (wcChange !== 0) {
            operatingRows.push({
                description: wcChange < 0 ? 'Increase in Working Capital' : 'Decrease in Working Capital',
                amount: wcChange,
            });
        }

        totalOp = Number(data.operating_cash_flow ?? 0);
    } else {
        // Direct: operating_activities might be { net } or an array
        if (Array.isArray(data.operating_activities)) {
            for (const r of data.operating_activities) {
                const amt = Number(r.amount ?? r.value ?? 0);
                operatingRows.push({ description: r.description ?? r.label ?? r.name ?? '—', amount: amt });
            }
            totalOp = operatingRows.reduce((s, r) => s + r.amount, 0);
        } else {
            totalOp = Number(data.operating_activities?.net ?? 0);
        }

        // Add detail lines filtered by category
        if (Array.isArray(data.details)) {
            for (const d of data.details) {
                if (d.category === 'operating') {
                    operatingRows.push({
                        description: d.reference ?? d.date ?? 'Operating item',
                        amount: Number(d.amount ?? 0),
                    });
                }
            }
        }
    }

    // --- Investing ---
    const investingRows: { description: string; amount: number }[] = [];
    let totalInv = 0;

    if (Array.isArray(data.investing_activities)) {
        for (const r of data.investing_activities) {
            const amt = Number(r.amount ?? r.value ?? 0);
            investingRows.push({ description: r.description ?? r.label ?? r.name ?? '—', amount: amt });
        }
        totalInv = investingRows.reduce((s, r) => s + r.amount, 0);
    } else {
        totalInv = Number(data.investing_activities?.net ?? 0);
    }

    if (Array.isArray(data.details)) {
        for (const d of data.details) {
            if (d.category === 'investing') {
                investingRows.push({
                    description: d.reference ?? d.date ?? 'Investing item',
                    amount: Number(d.amount ?? 0),
                });
            }
        }
    }

    // --- Financing ---
    const financingRows: { description: string; amount: number }[] = [];
    let totalFin = 0;

    if (Array.isArray(data.financing_activities)) {
        for (const r of data.financing_activities) {
            const amt = Number(r.amount ?? r.value ?? 0);
            financingRows.push({ description: r.description ?? r.label ?? r.name ?? '—', amount: amt });
        }
        totalFin = financingRows.reduce((s, r) => s + r.amount, 0);
    } else {
        totalFin = Number(data.financing_activities?.net ?? 0);
    }

    if (Array.isArray(data.details)) {
        for (const d of data.details) {
            if (d.category === 'financing') {
                financingRows.push({
                    description: d.reference ?? d.date ?? 'Financing item',
                    amount: Number(d.amount ?? 0),
                });
            }
        }
    }

    const netChange = Number(data.net_change ?? (totalOp + totalInv + totalFin));

    return { operatingRows, investingRows, financingRows, totalOp, totalInv, totalFin, netChange };
}

export default function CashFlow() {
    const { formatCurrency } = useCurrency();
    const today = new Date().toISOString().split('T')[0];
    const firstOfYear = `${new Date().getFullYear()}-01-01`;

    const [startDate, setStartDate] = useState(firstOfYear);
    const [endDate, setEndDate] = useState(today);
    const [method, setMethod] = useState<'direct' | 'indirect'>('indirect');
    const [submitted, setSubmitted] = useState(false);

    const params = submitted ? { start_date: startDate, end_date: endDate, method } : null;
    const { data, isLoading, error } = useCashFlow(params);

    const { operatingRows, investingRows, financingRows, totalOp, totalInv, totalFin, netChange } =
        normalizeCashFlow(data);

    const buildExportOptions = (): ExportOptions => {
        const cols = [
            { header: 'Description', key: 'description' },
            { header: 'Amount', key: 'amount', align: 'right' as const },
        ];
        const fmtRows = (rows: { description: string; amount: number }[]) =>
            rows.map(r => ({
                description: r.description,
                amount: `${r.amount >= 0 ? '+' : '−'}${formatCurrency(Math.abs(r.amount))}`,
            }));

        return {
            title: 'Cash Flow Statement',
            subtitle: `${method === 'indirect' ? 'Indirect' : 'Direct'} Method`,
            dateRange: `${startDate} to ${endDate}`,
            sections: [
                {
                    title: 'Operating Activities',
                    columns: cols,
                    rows: fmtRows(operatingRows),
                    totals: { description: 'Net Operating', amount: `${totalOp >= 0 ? '+' : '−'}${formatCurrency(Math.abs(totalOp))}` },
                },
                {
                    title: 'Investing Activities',
                    columns: cols,
                    rows: fmtRows(investingRows),
                    totals: { description: 'Net Investing', amount: `${totalInv >= 0 ? '+' : '−'}${formatCurrency(Math.abs(totalInv))}` },
                },
                {
                    title: 'Financing Activities',
                    columns: cols,
                    rows: fmtRows(financingRows),
                    totals: { description: 'Net Financing', amount: `${totalFin >= 0 ? '+' : '−'}${formatCurrency(Math.abs(totalFin))}` },
                },
            ],
            summary: [
                { label: 'Operating', value: `${totalOp >= 0 ? '+' : '−'}${formatCurrency(Math.abs(totalOp))}` },
                { label: 'Investing', value: `${totalInv >= 0 ? '+' : '−'}${formatCurrency(Math.abs(totalInv))}` },
                { label: 'Financing', value: `${totalFin >= 0 ? '+' : '−'}${formatCurrency(Math.abs(totalFin))}` },
                { label: 'Net Change', value: `${netChange >= 0 ? '+' : '−'}${formatCurrency(Math.abs(netChange))}` },
            ],
        };
    };

    const handleExportCSV = () => {
        if (!submitted) return;
        exportToCSV(buildExportOptions(), `cash-flow-${method}-${startDate}-to-${endDate}.csv`);
    };

    const handleExportPDF = () => {
        if (!submitted) return;
        exportToPDF(buildExportOptions());
    };

    const inputStyle: React.CSSProperties = {
        padding: '6px 10px',
        border: '1px solid #e2e8f0',
        borderRadius: '8px',
        fontSize: '13px',
        fontWeight: 600,
        color: '#1e293b',
    };

    const exportBtnStyle: React.CSSProperties = {
        display: 'inline-flex', alignItems: 'center', gap: '5px',
        padding: '6px 12px', border: '1px solid #e2e8f0', borderRadius: '8px',
        background: '#f8fafc', fontSize: '13px', fontWeight: 600, color: '#475569',
        cursor: 'pointer', whiteSpace: 'nowrap',
        opacity: submitted ? 1 : 0.4, pointerEvents: submitted ? 'auto' : 'none',
    };

    return (
        <AccountingLayout>
            <PageHeader
                title="Cash Flow Statement"
                subtitle="Operating, Investing, and Financing Activities"
                icon={<Waves className="w-6 h-6" />}
            />

            {/* Filters — horizontal row */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: '12px',
                background: '#fff', borderRadius: '12px', padding: '10px 20px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.06)', marginBottom: '20px',
                flexWrap: 'wrap',
            }}>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#64748b', whiteSpace: 'nowrap' }}>
                    Start Date
                </span>
                <input
                    type="date"
                    value={startDate}
                    onChange={e => setStartDate(e.target.value)}
                    style={{ ...inputStyle, width: '150px' }}
                />
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#64748b', whiteSpace: 'nowrap' }}>
                    End Date
                </span>
                <input
                    type="date"
                    value={endDate}
                    onChange={e => setEndDate(e.target.value)}
                    style={{ ...inputStyle, width: '150px' }}
                />
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#64748b', whiteSpace: 'nowrap' }}>
                    Method
                </span>
                <select
                    value={method}
                    onChange={e => setMethod(e.target.value as any)}
                    style={{ ...inputStyle, width: '120px' }}
                >
                    <option value="indirect">Indirect</option>
                    <option value="direct">Direct</option>
                </select>
                <button
                    onClick={() => setSubmitted(true)}
                    style={{
                        display: 'inline-flex', alignItems: 'center', gap: '5px',
                        padding: '6px 14px', border: 'none', borderRadius: '8px',
                        background: '#1e293b', fontSize: '13px', fontWeight: 600,
                        color: '#fff', cursor: 'pointer', whiteSpace: 'nowrap',
                    }}
                >
                    <RefreshCw size={14} /> Generate
                </button>
                <div style={{ flex: 1 }} />
                <button onClick={handleExportCSV} style={exportBtnStyle}>
                    <Download size={14} /> Excel
                </button>
                <button onClick={handleExportPDF} style={exportBtnStyle}>
                    <FileText size={14} /> PDF
                </button>
            </div>

            {!submitted ? (
                <div style={{
                    background: '#fff', borderRadius: '12px', padding: '48px',
                    textAlign: 'center', color: '#94a3b8',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                }}>
                    Select a date range and click Generate.
                </div>
            ) : isLoading ? (
                <div style={{
                    background: '#fff', borderRadius: '12px', padding: '48px',
                    textAlign: 'center', color: '#94a3b8',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                }}>
                    Generating Cash Flow Statement…
                </div>
            ) : error ? (
                <div style={{
                    background: '#fff', borderRadius: '12px', padding: '48px',
                    textAlign: 'center', color: '#ef4444',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                }}>
                    Failed to generate report.
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {/* Operating Activities */}
                    <CashSection
                        title="Operating Activities"
                        icon={<TrendingUp size={16} />}
                        rows={operatingRows}
                        total={totalOp}
                        accentColor="#0284c7"
                        accentBg="#f0f9ff"
                        borderColor="#bae6fd"
                    />

                    {/* Investing Activities */}
                    <CashSection
                        title="Investing Activities"
                        icon={<Building2 size={16} />}
                        rows={investingRows}
                        total={totalInv}
                        accentColor="#7c3aed"
                        accentBg="#f5f3ff"
                        borderColor="#ddd6fe"
                    />

                    {/* Financing Activities */}
                    <CashSection
                        title="Financing Activities"
                        icon={<Landmark size={16} />}
                        rows={financingRows}
                        total={totalFin}
                        accentColor="#d97706"
                        accentBg="#fffbeb"
                        borderColor="#fde68a"
                    />

                    {/* Net Change in Cash — summary card */}
                    <div style={{
                        background: netChange >= 0 ? '#ecfdf5' : '#fef2f2',
                        border: `2px solid ${netChange >= 0 ? '#a7f3d0' : '#fecaca'}`,
                        borderRadius: '12px',
                        padding: '20px 24px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <div style={{
                                width: '40px', height: '40px', borderRadius: '10px',
                                background: netChange >= 0 ? '#059669' : '#dc2626',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                color: '#fff',
                            }}>
                                <ArrowUpDown size={20} />
                            </div>
                            <div>
                                <div style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>
                                    Net Change in Cash
                                </div>
                                <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                                    Operating + Investing + Financing
                                </div>
                            </div>
                        </div>
                        <div style={{
                            fontSize: '24px',
                            fontWeight: 800,
                            color: netChange >= 0 ? '#059669' : '#dc2626',
                        }}>
                            {netChange >= 0 ? '+' : '−'}{formatCurrency(Math.abs(netChange))}
                        </div>
                    </div>

                    {/* Breakdown summary cards */}
                    <div style={{
                        display: 'flex', gap: '12px', flexWrap: 'wrap',
                    }}>
                        {[
                            { label: 'Operating', value: totalOp, color: '#0284c7', bg: '#f0f9ff', border: '#bae6fd' },
                            { label: 'Investing', value: totalInv, color: '#7c3aed', bg: '#f5f3ff', border: '#ddd6fe' },
                            { label: 'Financing', value: totalFin, color: '#d97706', bg: '#fffbeb', border: '#fde68a' },
                        ].map(item => (
                            <div key={item.label} style={{
                                flex: '1 1 180px',
                                padding: '14px 18px',
                                borderRadius: '10px',
                                border: `1.5px solid ${item.border}`,
                                background: item.bg,
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '4px',
                            }}>
                                <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                                    {item.label}
                                </span>
                                <span style={{ fontSize: '18px', fontWeight: 700, color: item.value >= 0 ? '#059669' : '#dc2626' }}>
                                    {item.value >= 0 ? '+' : '−'}{formatCurrency(Math.abs(item.value))}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </AccountingLayout>
    );
}
