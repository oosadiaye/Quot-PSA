import { useState } from 'react';
import { Scale, Download, RefreshCw } from 'lucide-react';
import { useBalanceSheet } from '../hooks/useFinancialReports';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import { useCurrency } from '../../../context/CurrencyContext';
import '../styles/glassmorphism.css';

function SectionTable({ title, rows, total, formatCurrency }: {
    title: string;
    rows: any[];
    total: number;
    formatCurrency: (v: number) => string;
}) {
    return (
        <div className="glass-card mb-4">
            <div className="px-4 py-3 border-b border-white/10 text-blue-300 font-semibold">{title}</div>
            <table className="w-full text-sm">
                <tbody>
                    {rows.map((row: any) => (
                        <tr key={row.account_code ?? row.code ?? row.name} className="border-b border-white/5 hover:bg-white/5 text-gray-200">
                            <td className="px-4 py-2 font-mono text-gray-400 w-32">{row.account_code ?? row.code}</td>
                            <td className="px-4 py-2">{row.account_name ?? row.name}</td>
                            <td className="px-4 py-2 text-right">{formatCurrency(parseFloat(row.balance ?? row.net ?? 0))}</td>
                        </tr>
                    ))}
                </tbody>
                <tfoot>
                    <tr className="border-t border-white/20 text-white font-semibold">
                        <td colSpan={2} className="px-4 py-3">Total {title}</td>
                        <td className="px-4 py-3 text-right">{formatCurrency(total)}</td>
                    </tr>
                </tfoot>
            </table>
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

    const assets = data?.assets ?? [];
    const liabilities = data?.liabilities ?? [];
    const equity = data?.equity ?? [];

    const totalAssets = assets.reduce((s: number, r: any) => s + parseFloat(r.balance ?? r.net ?? 0), 0);
    const totalLiabilities = liabilities.reduce((s: number, r: any) => s + parseFloat(r.balance ?? r.net ?? 0), 0);
    const totalEquity = equity.reduce((s: number, r: any) => s + parseFloat(r.balance ?? r.net ?? 0), 0);
    const isBalanced = Math.abs(totalAssets - (totalLiabilities + totalEquity)) < 0.01;

    return (
        <AccountingLayout>
            <PageHeader
                title="Balance Sheet"
                subtitle="Assets = Liabilities + Equity"
                icon={<Scale className="w-6 h-6" />}
            />

            <div className="glass-card p-4 mb-6 flex flex-wrap gap-4 items-end">
                <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">Start Date</label>
                    <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="glass-input" />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">End Date (As Of)</label>
                    <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className="glass-input" />
                </div>
                <button onClick={() => setSubmitted(true)} className="glass-btn flex items-center gap-2">
                    <RefreshCw className="w-4 h-4" /> Generate
                </button>
            </div>

            {!submitted ? (
                <div className="glass-card p-8 text-center text-gray-400">Select a date range and click Generate.</div>
            ) : isLoading ? (
                <div className="glass-card p-8 text-center text-gray-400">Generating Balance Sheet…</div>
            ) : error ? (
                <div className="glass-card p-8 text-center text-red-400">Failed to generate report.</div>
            ) : (
                <>
                    {!isBalanced && (
                        <div className="mb-4 px-4 py-2 rounded-lg text-sm font-medium bg-red-900/30 text-red-300 border border-red-700">
                            ⚠ Balance Sheet out of balance by {formatCurrency(Math.abs(totalAssets - totalLiabilities - totalEquity))}
                        </div>
                    )}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div>
                            <SectionTable title="Assets" rows={assets} total={totalAssets} formatCurrency={formatCurrency} />
                        </div>
                        <div>
                            <SectionTable title="Liabilities" rows={liabilities} total={totalLiabilities} formatCurrency={formatCurrency} />
                            <SectionTable title="Equity" rows={equity} total={totalEquity} formatCurrency={formatCurrency} />
                            <div className="glass-card p-4 mt-4 flex justify-between items-center">
                                <span className="text-gray-300">Total Liabilities + Equity</span>
                                <span className={`text-xl font-bold ${isBalanced ? 'text-green-300' : 'text-red-300'}`}>
                                    {formatCurrency(totalLiabilities + totalEquity)}
                                </span>
                            </div>
                        </div>
                    </div>
                    <div className="glass-card p-4 mt-4 flex justify-between items-center">
                        <span className="text-white font-semibold text-lg">Total Assets</span>
                        <span className="text-xl font-bold text-blue-300">{formatCurrency(totalAssets)}</span>
                    </div>
                </>
            )}
        </AccountingLayout>
    );
}
