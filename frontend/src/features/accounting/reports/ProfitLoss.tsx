import { useState } from 'react';
import { TrendingUp, TrendingDown, RefreshCw, DollarSign, ArrowUpDown, Download, FileText } from 'lucide-react';
import { useProfitLoss } from '../hooks/useFinancialReports';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import { useCurrency } from '../../../context/CurrencyContext';
import { exportToCSV, exportToPDF } from '../utils/exportReport';
import type { ExportOptions } from '../utils/exportReport';

interface SectionProps {
    title: string;
    icon: React.ReactNode;
    rows: { code: string; name: string; amount: number }[];
    total: number;
    accentColor: string;
    accentBg: string;
    borderColor: string;
}

function ReportSection({ title, icon, rows, total, accentColor, accentBg, borderColor }: SectionProps) {
    const { formatCurrency } = useCurrency();

    return (
        <div style={{
            background: '#fff', borderRadius: '12px', overflow: 'hidden',
            boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
            border: `1.5px solid ${borderColor}`,
        }}>
            {/* Section Header */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: '10px',
                padding: '14px 20px', background: accentBg,
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
                <span style={{ fontSize: '15px', fontWeight: 700, color: accentColor }}>
                    {formatCurrency(Math.abs(total))}
                </span>
            </div>

            {/* Rows */}
            {rows.length === 0 ? (
                <div style={{ padding: '20px', textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>
                    No accounts found for this period.
                </div>
            ) : (
                <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ borderBottom: '1px solid #e2e8f0', background: '#fafafa' }}>
                            <th style={{ padding: '8px 20px', textAlign: 'left', color: '#94a3b8', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Code</th>
                            <th style={{ padding: '8px 20px', textAlign: 'left', color: '#94a3b8', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Account</th>
                            <th style={{ padding: '8px 20px', textAlign: 'right', color: '#94a3b8', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Amount</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((r, i) => (
                            <tr key={r.code ?? i}
                                style={{ borderBottom: '1px solid #f1f5f9' }}
                                onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                            >
                                <td style={{ padding: '10px 20px', fontFamily: 'monospace', color: '#3b82f6', fontWeight: 600, width: '120px' }}>
                                    {r.code}
                                </td>
                                <td style={{ padding: '10px 20px', color: '#334155' }}>
                                    {r.name}
                                </td>
                                <td style={{
                                    padding: '10px 20px', textAlign: 'right',
                                    fontWeight: 600, fontFamily: 'monospace', color: accentColor,
                                }}>
                                    {formatCurrency(Math.abs(r.amount))}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                    <tfoot>
                        <tr style={{ borderTop: '2px solid #e2e8f0', background: '#f8fafc' }}>
                            <td style={{ padding: '12px 20px', fontWeight: 700, color: '#1e293b' }} colSpan={2}>
                                Total {title}
                            </td>
                            <td style={{
                                padding: '12px 20px', textAlign: 'right',
                                fontWeight: 700, fontSize: '14px', fontFamily: 'monospace', color: accentColor,
                            }}>
                                {formatCurrency(Math.abs(total))}
                            </td>
                        </tr>
                    </tfoot>
                </table>
            )}
        </div>
    );
}

export default function ProfitLoss() {
    const { formatCurrency } = useCurrency();
    const today = new Date().toISOString().split('T')[0];
    const firstOfYear = `${new Date().getFullYear()}-01-01`;

    const [startDate, setStartDate] = useState(firstOfYear);
    const [endDate, setEndDate] = useState(today);
    const [submitted, setSubmitted] = useState(false);

    const params = submitted ? { start_date: startDate, end_date: endDate } : null;
    const { data, isLoading, error } = useProfitLoss(params);

    // Backend returns { revenue: { total, details }, expenses: { total, details }, net_income }
    const revenueRaw = data?.revenue;
    const expensesRaw = data?.expenses;

    const revenueRows: { code: string; name: string; amount: number }[] =
        (Array.isArray(revenueRaw) ? revenueRaw : revenueRaw?.details ?? [])
            .map((r: any) => ({
                code: r.account_code ?? r.code ?? '',
                name: r.account_name ?? r.name ?? '',
                amount: Number(r.balance ?? r.net ?? r.amount ?? r.total ?? 0),
            }));

    const expenseRows: { code: string; name: string; amount: number }[] =
        (Array.isArray(expensesRaw) ? expensesRaw : expensesRaw?.details ?? [])
            .map((r: any) => ({
                code: r.account_code ?? r.code ?? '',
                name: r.account_name ?? r.name ?? '',
                amount: Number(r.balance ?? r.net ?? r.amount ?? r.total ?? 0),
            }));

    const totalRevenue = Number(
        revenueRaw?.total ?? data?.total_revenue ?? data?.total_income ??
        revenueRows.reduce((s, r) => s + r.amount, 0)
    );
    const totalExpenses = Number(
        expensesRaw?.total ?? data?.total_expenses ??
        expenseRows.reduce((s, r) => s + r.amount, 0)
    );
    const netIncome = Number(data?.net_income ?? (totalRevenue - totalExpenses));

    const buildExportOptions = (): ExportOptions => {
        const cols = [
            { header: 'Code', key: 'code' },
            { header: 'Account', key: 'name' },
            { header: 'Amount', key: 'amount', align: 'right' as const },
        ];
        return {
            title: 'Income Statement',
            subtitle: 'Revenue minus Expenses for the period',
            dateRange: `${startDate} to ${endDate}`,
            sections: [
                {
                    title: 'Revenue',
                    columns: cols,
                    rows: revenueRows.map(r => ({ ...r, amount: formatCurrency(Math.abs(r.amount)) })),
                    totals: { code: '', name: 'Total Revenue', amount: formatCurrency(totalRevenue) },
                },
                {
                    title: 'Expenses',
                    columns: cols,
                    rows: expenseRows.map(r => ({ ...r, amount: formatCurrency(Math.abs(r.amount)) })),
                    totals: { code: '', name: 'Total Expenses', amount: formatCurrency(totalExpenses) },
                },
            ],
            summary: [
                { label: 'Revenue', value: formatCurrency(totalRevenue) },
                { label: 'Expenses', value: formatCurrency(totalExpenses) },
                { label: 'Net Income', value: `${netIncome >= 0 ? '+' : '−'}${formatCurrency(Math.abs(netIncome))}` },
            ],
        };
    };

    const handleExportCSV = () => {
        if (!submitted) return;
        exportToCSV(buildExportOptions(), `income-statement-${startDate}-to-${endDate}.csv`);
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
                title="Income Statement"
                subtitle="Revenue minus Expenses for the period"
                icon={<TrendingUp className="w-6 h-6" />}
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
                    Generating Income Statement…
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
                    {/* Revenue */}
                    <ReportSection
                        title="Revenue"
                        icon={<TrendingUp size={16} />}
                        rows={revenueRows}
                        total={totalRevenue}
                        accentColor="#059669"
                        accentBg="#ecfdf5"
                        borderColor="#a7f3d0"
                    />

                    {/* Expenses */}
                    <ReportSection
                        title="Expenses"
                        icon={<TrendingDown size={16} />}
                        rows={expenseRows}
                        total={totalExpenses}
                        accentColor="#dc2626"
                        accentBg="#fef2f2"
                        borderColor="#fecaca"
                    />

                    {/* Net Income / Loss — summary card */}
                    <div style={{
                        background: netIncome >= 0 ? '#ecfdf5' : '#fef2f2',
                        border: `2px solid ${netIncome >= 0 ? '#a7f3d0' : '#fecaca'}`,
                        borderRadius: '12px',
                        padding: '20px 24px',
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <div style={{
                                width: '40px', height: '40px', borderRadius: '10px',
                                background: netIncome >= 0 ? '#059669' : '#dc2626',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                color: '#fff',
                            }}>
                                <DollarSign size={20} />
                            </div>
                            <div>
                                <div style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>
                                    {netIncome >= 0 ? 'Net Income (Profit)' : 'Net Loss'}
                                </div>
                                <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                                    Revenue − Expenses
                                </div>
                            </div>
                        </div>
                        <div style={{
                            fontSize: '24px', fontWeight: 800,
                            color: netIncome >= 0 ? '#059669' : '#dc2626',
                        }}>
                            {netIncome >= 0 ? '+' : '−'}{formatCurrency(Math.abs(netIncome))}
                        </div>
                    </div>

                    {/* Breakdown summary cards */}
                    <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                        <div style={{
                            flex: '1 1 180px', padding: '14px 18px', borderRadius: '10px',
                            border: '1.5px solid #a7f3d0', background: '#ecfdf5',
                            display: 'flex', flexDirection: 'column', gap: '4px',
                        }}>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Revenue</span>
                            <span style={{ fontSize: '18px', fontWeight: 700, color: '#059669' }}>{formatCurrency(totalRevenue)}</span>
                        </div>
                        <div style={{
                            flex: '1 1 180px', padding: '14px 18px', borderRadius: '10px',
                            border: '1.5px solid #fecaca', background: '#fef2f2',
                            display: 'flex', flexDirection: 'column', gap: '4px',
                        }}>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Expenses</span>
                            <span style={{ fontSize: '18px', fontWeight: 700, color: '#dc2626' }}>{formatCurrency(totalExpenses)}</span>
                        </div>
                        <div style={{
                            flex: '1 1 180px', padding: '14px 18px', borderRadius: '10px',
                            border: `1.5px solid ${netIncome >= 0 ? '#a7f3d0' : '#fecaca'}`,
                            background: netIncome >= 0 ? '#ecfdf5' : '#fef2f2',
                            display: 'flex', flexDirection: 'column', gap: '4px',
                        }}>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Net Income</span>
                            <span style={{ fontSize: '18px', fontWeight: 700, color: netIncome >= 0 ? '#059669' : '#dc2626' }}>
                                {netIncome >= 0 ? '+' : '−'}{formatCurrency(Math.abs(netIncome))}
                            </span>
                        </div>
                    </div>
                </div>
            )}
        </AccountingLayout>
    );
}
