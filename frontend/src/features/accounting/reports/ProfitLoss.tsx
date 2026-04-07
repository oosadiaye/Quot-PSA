import { useState } from 'react';
import { TrendingUp, RefreshCw } from 'lucide-react';
import { useProfitLoss } from '../hooks/useFinancialReports';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import { useCurrency } from '../../../context/CurrencyContext';
import '../styles/glassmorphism.css';

export default function ProfitLoss() {
    const { formatCurrency } = useCurrency();
    const today = new Date().toISOString().split('T')[0];
    const firstOfYear = `${new Date().getFullYear()}-01-01`;

    const [startDate, setStartDate] = useState(firstOfYear);
    const [endDate, setEndDate] = useState(today);
    const [submitted, setSubmitted] = useState(false);

    const params = submitted ? { start_date: startDate, end_date: endDate } : null;
    const { data, isLoading, error } = useProfitLoss(params);

    const revenue: any[] = data?.revenue ?? data?.income ?? [];
    const expenses: any[] = data?.expenses ?? [];
    const totalRevenue = data?.total_revenue ?? data?.total_income ??
        revenue.reduce((s: number, r: any) => s + parseFloat(r.balance ?? r.net ?? 0), 0);
    const totalExpenses = data?.total_expenses ??
        expenses.reduce((s: number, r: any) => s + parseFloat(r.balance ?? r.net ?? 0), 0);
    const netIncome = typeof data?.net_income !== 'undefined' ? data.net_income : (totalRevenue - totalExpenses);

    return (
        <AccountingLayout>
            <PageHeader
                title="Profit & Loss"
                subtitle="Income Statement — Revenue minus Expenses"
                icon={<TrendingUp className="w-6 h-6" />}
            />

            <div className="glass-card p-4 mb-6 flex flex-wrap gap-4 items-end">
                <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">Start Date</label>
                    <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="glass-input" />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">End Date</label>
                    <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className="glass-input" />
                </div>
                <button onClick={() => setSubmitted(true)} className="glass-btn flex items-center gap-2">
                    <RefreshCw className="w-4 h-4" /> Generate
                </button>
            </div>

            {!submitted ? (
                <div className="glass-card p-8 text-center text-gray-400">Select a date range and click Generate.</div>
            ) : isLoading ? (
                <div className="glass-card p-8 text-center text-gray-400">Generating P&L…</div>
            ) : error ? (
                <div className="glass-card p-8 text-center text-red-400">Failed to generate report.</div>
            ) : (
                <div className="space-y-4">
                    {/* Revenue Section */}
                    <div className="glass-card">
                        <div className="px-4 py-3 border-b border-white/10 text-green-300 font-semibold">Revenue</div>
                        <table className="w-full text-sm">
                            <tbody>
                                {revenue.map((r: any) => (
                                    <tr key={r.account_code ?? r.code ?? r.name} className="border-b border-white/5 hover:bg-white/5 text-gray-200">
                                        <td className="px-4 py-2 font-mono text-gray-400 w-32">{r.account_code ?? r.code}</td>
                                        <td className="px-4 py-2">{r.account_name ?? r.name}</td>
                                        <td className="px-4 py-2 text-right text-green-300">{formatCurrency(parseFloat(r.balance ?? r.net ?? 0))}</td>
                                    </tr>
                                ))}
                            </tbody>
                            <tfoot>
                                <tr className="border-t border-white/20 text-white font-semibold">
                                    <td colSpan={2} className="px-4 py-3">Total Revenue</td>
                                    <td className="px-4 py-3 text-right text-green-300">{formatCurrency(Number(totalRevenue))}</td>
                                </tr>
                            </tfoot>
                        </table>
                    </div>

                    {/* Expenses Section */}
                    <div className="glass-card">
                        <div className="px-4 py-3 border-b border-white/10 text-red-300 font-semibold">Expenses</div>
                        <table className="w-full text-sm">
                            <tbody>
                                {expenses.map((r: any) => (
                                    <tr key={r.account_code ?? r.code ?? r.name} className="border-b border-white/5 hover:bg-white/5 text-gray-200">
                                        <td className="px-4 py-2 font-mono text-gray-400 w-32">{r.account_code ?? r.code}</td>
                                        <td className="px-4 py-2">{r.account_name ?? r.name}</td>
                                        <td className="px-4 py-2 text-right text-red-300">{formatCurrency(parseFloat(r.balance ?? r.net ?? 0))}</td>
                                    </tr>
                                ))}
                            </tbody>
                            <tfoot>
                                <tr className="border-t border-white/20 text-white font-semibold">
                                    <td colSpan={2} className="px-4 py-3">Total Expenses</td>
                                    <td className="px-4 py-3 text-right text-red-300">{formatCurrency(Number(totalExpenses))}</td>
                                </tr>
                            </tfoot>
                        </table>
                    </div>

                    {/* Net Income */}
                    <div className={`glass-card p-5 flex justify-between items-center ${Number(netIncome) >= 0 ? 'border border-green-700/40' : 'border border-red-700/40'}`}>
                        <span className="text-white font-bold text-lg">
                            {Number(netIncome) >= 0 ? 'Net Income (Profit)' : 'Net Loss'}
                        </span>
                        <span className={`text-2xl font-bold ${Number(netIncome) >= 0 ? 'text-green-300' : 'text-red-300'}`}>
                            {formatCurrency(Math.abs(Number(netIncome)))}
                        </span>
                    </div>
                </div>
            )}
        </AccountingLayout>
    );
}
