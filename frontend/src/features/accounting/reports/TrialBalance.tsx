import { useState } from 'react';
import { BarChart3, Download, RefreshCw } from 'lucide-react';
import { useTrialBalance } from '../hooks/useFinancialReports';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import { useCurrency } from '../../../context/CurrencyContext';
import '../styles/glassmorphism.css';

export default function TrialBalance() {
    const { formatCurrency } = useCurrency();
    const currentYear = new Date().getFullYear();
    const currentMonth = new Date().getMonth() + 1;

    const [fiscalYear, setFiscalYear] = useState(currentYear);
    const [period, setPeriod] = useState(currentMonth);

    const { data, isLoading, error, refetch } = useTrialBalance({ fiscal_year: fiscalYear, period });

    const accounts: any[] = data?.results ?? data ?? [];

    const totalDebits = accounts.reduce((sum: number, a: any) => sum + parseFloat(a.debit_balance ?? 0), 0);
    const totalCredits = accounts.reduce((sum: number, a: any) => sum + parseFloat(a.credit_balance ?? 0), 0);
    const isBalanced = Math.abs(totalDebits - totalCredits) < 0.01;

    const handleExport = () => {
        if (!accounts.length) return;
        const rows = [
            ['Account Code', 'Account Name', 'Type', 'Debit', 'Credit', 'Net'],
            ...accounts.map((a: any) => [
                a.account_code ?? a.account?.code ?? '',
                a.account_name ?? a.account?.name ?? '',
                a.account_type ?? '',
                a.debit_balance ?? 0,
                a.credit_balance ?? 0,
                ((a.debit_balance ?? 0) - (a.credit_balance ?? 0)).toFixed(2),
            ]),
            ['', 'TOTALS', '', totalDebits.toFixed(2), totalCredits.toFixed(2), ''],
        ];
        const csv = rows.map(r => r.join(',')).join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `trial-balance-${fiscalYear}-${String(period).padStart(2, '0')}.csv`;
        a.click();
    };

    return (
        <AccountingLayout>
            <PageHeader
                title="Trial Balance"
                subtitle="Aggregated debit and credit balances for all GL accounts"
                icon={<BarChart3 className="w-6 h-6" />}
            />

            {/* Filters */}
            <div className="glass-card p-4 mb-6 flex flex-wrap gap-4 items-end">
                <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">Fiscal Year</label>
                    <input
                        type="number"
                        value={fiscalYear}
                        onChange={e => setFiscalYear(Number(e.target.value))}
                        className="glass-input w-28"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">Period (Month)</label>
                    <select
                        value={period}
                        onChange={e => setPeriod(Number(e.target.value))}
                        className="glass-input"
                    >
                        {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
                            <option key={m} value={m}>
                                {new Date(2000, m - 1).toLocaleString('default', { month: 'long' })} ({m})
                            </option>
                        ))}
                    </select>
                </div>
                <button onClick={() => refetch()} className="glass-btn flex items-center gap-2">
                    <RefreshCw className="w-4 h-4" /> Refresh
                </button>
                <button onClick={handleExport} className="glass-btn flex items-center gap-2 ml-auto">
                    <Download className="w-4 h-4" /> Export CSV
                </button>
            </div>

            {/* Balance status */}
            {!isLoading && accounts.length > 0 && (
                <div className={`mb-4 px-4 py-2 rounded-lg text-sm font-medium ${
                    isBalanced ? 'bg-green-900/30 text-green-300 border border-green-700' : 'bg-red-900/30 text-red-300 border border-red-700'
                }`}>
                    {isBalanced
                        ? '✓ Trial Balance is balanced'
                        : `⚠ Out of balance by ${formatCurrency(Math.abs(totalDebits - totalCredits))}`}
                </div>
            )}

            {/* Table */}
            <div className="glass-card overflow-x-auto">
                {isLoading ? (
                    <div className="p-8 text-center text-gray-400">Loading trial balance…</div>
                ) : error ? (
                    <div className="p-8 text-center text-red-400">Failed to load trial balance.</div>
                ) : accounts.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">No data for selected period.</div>
                ) : (
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-white/10 text-gray-400 text-left">
                                <th className="px-4 py-3">Code</th>
                                <th className="px-4 py-3">Account Name</th>
                                <th className="px-4 py-3">Type</th>
                                <th className="px-4 py-3 text-right">Debit</th>
                                <th className="px-4 py-3 text-right">Credit</th>
                                <th className="px-4 py-3 text-right">Net</th>
                            </tr>
                        </thead>
                        <tbody>
                            {accounts.map((a: any, i: number) => {
                                const dr = parseFloat(a.debit_balance ?? 0);
                                const cr = parseFloat(a.credit_balance ?? 0);
                                const net = dr - cr;
                                return (
                                    <tr key={a.account_code ?? a.account?.code ?? i} className="border-b border-white/5 hover:bg-white/5 text-gray-200">
                                        <td className="px-4 py-2 font-mono text-blue-300">{a.account_code ?? a.account?.code}</td>
                                        <td className="px-4 py-2">{a.account_name ?? a.account?.name}</td>
                                        <td className="px-4 py-2 text-gray-400">{a.account_type}</td>
                                        <td className="px-4 py-2 text-right">{dr > 0 ? formatCurrency(dr) : '—'}</td>
                                        <td className="px-4 py-2 text-right">{cr > 0 ? formatCurrency(cr) : '—'}</td>
                                        <td className={`px-4 py-2 text-right font-medium ${net >= 0 ? 'text-green-300' : 'text-red-300'}`}>
                                            {formatCurrency(Math.abs(net))} {net < 0 ? 'Cr' : 'Dr'}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                        <tfoot>
                            <tr className="border-t border-white/20 text-white font-semibold">
                                <td className="px-4 py-3" colSpan={3}>TOTALS</td>
                                <td className="px-4 py-3 text-right">{formatCurrency(totalDebits)}</td>
                                <td className="px-4 py-3 text-right">{formatCurrency(totalCredits)}</td>
                                <td className="px-4 py-3 text-right">
                                    {isBalanced ? (
                                        <span className="text-green-300">Balanced</span>
                                    ) : (
                                        <span className="text-red-300">{formatCurrency(Math.abs(totalDebits - totalCredits))} diff</span>
                                    )}
                                </td>
                            </tr>
                        </tfoot>
                    </table>
                )}
            </div>
        </AccountingLayout>
    );
}
