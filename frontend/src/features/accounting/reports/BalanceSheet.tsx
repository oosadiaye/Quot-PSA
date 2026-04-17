import { useState } from 'react';
import { Scale, RefreshCw, Wallet, CreditCard, Landmark, CheckCircle, AlertTriangle, ArrowLeftRight, Download, FileText } from 'lucide-react';
import { useBalanceSheet } from '../hooks/useFinancialReports';
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
                            <th style={{ padding: '8px 20px', textAlign: 'right', color: '#94a3b8', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Balance</th>
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

export default function BalanceSheet() {
    const { formatCurrency } = useCurrency();
    const today = new Date().toISOString().split('T')[0];
    const firstOfYear = `${new Date().getFullYear()}-01-01`;

    const [startDate, setStartDate] = useState(firstOfYear);
    const [endDate, setEndDate] = useState(today);
    const [submitted, setSubmitted] = useState(false);

    const params = submitted ? { start_date: startDate, end_date: endDate } : null;
    const { data, isLoading, error } = useBalanceSheet(params);

    // Backend returns { assets: { total, details }, liabilities: { total, details }, equity: { total, details, net_income } }
    const assetsRaw = data?.assets;
    const liabilitiesRaw = data?.liabilities;
    const equityRaw = data?.equity;

    const toRows = (raw: any) =>
        (Array.isArray(raw) ? raw : raw?.details ?? [])
            .map((r: any) => ({
                code: r.account_code ?? r.code ?? '',
                name: r.account_name ?? r.name ?? '',
                amount: Number(r.balance ?? r.net ?? r.amount ?? 0),
            }));

    const assetRows = toRows(assetsRaw);
    const liabilityRows = toRows(liabilitiesRaw);
    const equityRows = toRows(equityRaw);

    const totalAssets = Number(assetsRaw?.total ?? assetRows.reduce((s: number, r: any) => s + r.amount, 0));
    const totalLiabilities = Number(liabilitiesRaw?.total ?? liabilityRows.reduce((s: number, r: any) => s + r.amount, 0));
    const totalEquity = Number(equityRaw?.total ?? equityRows.reduce((s: number, r: any) => s + r.amount, 0));
    const isBalanced = Math.abs(totalAssets - (totalLiabilities + totalEquity)) < 0.01;
    const balanceDiff = Math.abs(totalAssets - (totalLiabilities + totalEquity));

    const buildExportOptions = (): ExportOptions => {
        const cols = [
            { header: 'Code', key: 'code' },
            { header: 'Account', key: 'name' },
            { header: 'Balance', key: 'amount', align: 'right' as const },
        ];
        return {
            title: 'Statement of Financial Position',
            subtitle: 'Assets = Liabilities + Equity',
            dateRange: `As of ${endDate}`,
            sections: [
                {
                    title: 'Assets',
                    columns: cols,
                    rows: assetRows.map(r => ({ ...r, amount: formatCurrency(Math.abs(r.amount)) })),
                    totals: { code: '', name: 'Total Assets', amount: formatCurrency(totalAssets) },
                },
                {
                    title: 'Liabilities',
                    columns: cols,
                    rows: liabilityRows.map(r => ({ ...r, amount: formatCurrency(Math.abs(r.amount)) })),
                    totals: { code: '', name: 'Total Liabilities', amount: formatCurrency(totalLiabilities) },
                },
                {
                    title: 'Equity',
                    columns: cols,
                    rows: equityRows.map(r => ({ ...r, amount: formatCurrency(Math.abs(r.amount)) })),
                    totals: { code: '', name: 'Total Equity', amount: formatCurrency(totalEquity) },
                },
            ],
            summary: [
                { label: 'Total Assets', value: formatCurrency(totalAssets) },
                { label: 'Total Liabilities', value: formatCurrency(totalLiabilities) },
                { label: 'Total Equity', value: formatCurrency(totalEquity) },
                { label: 'L + E', value: formatCurrency(totalLiabilities + totalEquity) },
            ],
        };
    };

    const handleExportCSV = () => {
        if (!submitted) return;
        exportToCSV(buildExportOptions(), `financial-position-${endDate}.csv`);
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
                title="Statement of Financial Position"
                subtitle="Assets = Liabilities + Equity"
                icon={<Scale className="w-6 h-6" />}
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
                    As of Date
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
                    Generating Statement of Financial Position…
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
                    {/* Balance check banner */}
                    <div style={{
                        padding: '12px 20px', borderRadius: '12px',
                        display: 'flex', alignItems: 'center', gap: '10px',
                        background: isBalanced ? '#ecfdf5' : '#fef2f2',
                        border: `1.5px solid ${isBalanced ? '#a7f3d0' : '#fecaca'}`,
                    }}>
                        {isBalanced ? (
                            <CheckCircle size={20} style={{ color: '#059669', flexShrink: 0 }} />
                        ) : (
                            <AlertTriangle size={20} style={{ color: '#dc2626', flexShrink: 0 }} />
                        )}
                        <span style={{
                            fontSize: '13px', fontWeight: 600,
                            color: isBalanced ? '#059669' : '#dc2626',
                        }}>
                            {isBalanced
                                ? 'Balance Sheet is balanced — Assets = Liabilities + Equity'
                                : `Out of balance by ${formatCurrency(balanceDiff)}`}
                        </span>
                    </div>

                    {/* Assets */}
                    <ReportSection
                        title="Assets"
                        icon={<Wallet size={16} />}
                        rows={assetRows}
                        total={totalAssets}
                        accentColor="#0284c7"
                        accentBg="#f0f9ff"
                        borderColor="#bae6fd"
                    />

                    {/* Liabilities */}
                    <ReportSection
                        title="Liabilities"
                        icon={<CreditCard size={16} />}
                        rows={liabilityRows}
                        total={totalLiabilities}
                        accentColor="#dc2626"
                        accentBg="#fef2f2"
                        borderColor="#fecaca"
                    />

                    {/* Equity */}
                    <ReportSection
                        title="Equity"
                        icon={<Landmark size={16} />}
                        rows={equityRows}
                        total={totalEquity}
                        accentColor="#7c3aed"
                        accentBg="#f5f3ff"
                        borderColor="#ddd6fe"
                    />

                    {/* Accounting equation card */}
                    <div style={{
                        background: isBalanced ? '#ecfdf5' : '#fef2f2',
                        border: `2px solid ${isBalanced ? '#a7f3d0' : '#fecaca'}`,
                        borderRadius: '12px',
                        padding: '20px 24px',
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <div style={{
                                width: '40px', height: '40px', borderRadius: '10px',
                                background: isBalanced ? '#059669' : '#dc2626',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                color: '#fff',
                            }}>
                                <ArrowLeftRight size={20} />
                            </div>
                            <div>
                                <div style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>
                                    Accounting Equation
                                </div>
                                <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                                    Assets = Liabilities + Equity
                                </div>
                            </div>
                        </div>
                        <div style={{
                            fontSize: '16px', fontWeight: 700,
                            color: isBalanced ? '#059669' : '#dc2626',
                        }}>
                            {isBalanced ? 'Balanced' : `${formatCurrency(balanceDiff)} difference`}
                        </div>
                    </div>

                    {/* Breakdown summary cards */}
                    <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                        <div style={{
                            flex: '1 1 180px', padding: '14px 18px', borderRadius: '10px',
                            border: '1.5px solid #bae6fd', background: '#f0f9ff',
                            display: 'flex', flexDirection: 'column', gap: '4px',
                        }}>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Total Assets</span>
                            <span style={{ fontSize: '18px', fontWeight: 700, color: '#0284c7' }}>{formatCurrency(totalAssets)}</span>
                        </div>
                        <div style={{
                            flex: '1 1 180px', padding: '14px 18px', borderRadius: '10px',
                            border: '1.5px solid #fecaca', background: '#fef2f2',
                            display: 'flex', flexDirection: 'column', gap: '4px',
                        }}>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Total Liabilities</span>
                            <span style={{ fontSize: '18px', fontWeight: 700, color: '#dc2626' }}>{formatCurrency(totalLiabilities)}</span>
                        </div>
                        <div style={{
                            flex: '1 1 180px', padding: '14px 18px', borderRadius: '10px',
                            border: '1.5px solid #ddd6fe', background: '#f5f3ff',
                            display: 'flex', flexDirection: 'column', gap: '4px',
                        }}>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Total Equity</span>
                            <span style={{ fontSize: '18px', fontWeight: 700, color: '#7c3aed' }}>{formatCurrency(totalEquity)}</span>
                        </div>
                        <div style={{
                            flex: '1 1 180px', padding: '14px 18px', borderRadius: '10px',
                            border: `1.5px solid ${isBalanced ? '#a7f3d0' : '#fde68a'}`,
                            background: isBalanced ? '#ecfdf5' : '#fffbeb',
                            display: 'flex', flexDirection: 'column', gap: '4px',
                        }}>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>L + E</span>
                            <span style={{ fontSize: '18px', fontWeight: 700, color: isBalanced ? '#059669' : '#d97706' }}>
                                {formatCurrency(totalLiabilities + totalEquity)}
                            </span>
                        </div>
                    </div>
                </div>
            )}
        </AccountingLayout>
    );
}
