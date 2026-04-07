import { useState } from 'react';
import { Waves, RefreshCw } from 'lucide-react';
import { useCashFlow } from '../hooks/useFinancialReports';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import { useCurrency } from '../../../context/CurrencyContext';
import '../styles/glassmorphism.css';

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

    const operating: any[] = data?.operating_activities ?? [];
    const investing: any[] = data?.investing_activities ?? [];
    const financing: any[] = data?.financing_activities ?? [];

    const totalOp = data?.total_operating ?? operating.reduce((s: number, r: any) => s + parseFloat(r.amount ?? r.value ?? 0), 0);
    const totalInv = data?.total_investing ?? investing.reduce((s: number, r: any) => s + parseFloat(r.amount ?? r.value ?? 0), 0);
    const totalFin = data?.total_financing ?? financing.reduce((s: number, r: any) => s + parseFloat(r.amount ?? r.value ?? 0), 0);
    const netChange = data?.net_change ?? (Number(totalOp) + Number(totalInv) + Number(totalFin));

    const CashSection = ({ title, rows, total, color }: { title: string; rows: any[]; total: number; color: string }) => (
        <div className="glass-card mb-4">
            <div className={`px-4 py-3 border-b border-white/10 font-semibold ${color}`}>{title}</div>
            {rows.length === 0 ? (
                <div className="px-4 py-3 text-gray-500 text-sm">No activity in this period.</div>
            ) : (
                <table className="w-full text-sm">
                    <tbody>
                        {rows.map((r: any, i: number) => (
                            <tr key={r.description ?? r.label ?? r.name ?? i} className="border-b border-white/5 hover:bg-white/5 text-gray-200">
                                <td className="px-4 py-2">{r.description ?? r.label ?? r.name ?? '—'}</td>
                                <td className={`px-4 py-2 text-right ${parseFloat(r.amount ?? r.value ?? 0) >= 0 ? 'text-green-300' : 'text-red-300'}`}>
                                    {formatCurrency(parseFloat(r.amount ?? r.value ?? 0))}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                    <tfoot>
                        <tr className="border-t border-white/20 text-white font-semibold">
                            <td className="px-4 py-3">Net {title}</td>
                            <td className={`px-4 py-3 text-right ${Number(total) >= 0 ? 'text-green-300' : 'text-red-300'}`}>
                                {formatCurrency(Number(total))}
                            </td>
                        </tr>
                    </tfoot>
                </table>
            )}
        </div>
    );

    return (
        <AccountingLayout>
            <PageHeader
                title="Cash Flow Statement"
                subtitle="Operating, Investing, and Financing Activities"
                icon={<Waves className="w-6 h-6" />}
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
                <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">Method</label>
                    <select value={method} onChange={e => setMethod(e.target.value as any)} className="glass-input">
                        <option value="indirect">Indirect</option>
                        <option value="direct">Direct</option>
                    </select>
                </div>
                <button onClick={() => setSubmitted(true)} className="glass-btn flex items-center gap-2">
                    <RefreshCw className="w-4 h-4" /> Generate
                </button>
            </div>

            {!submitted ? (
                <div className="glass-card p-8 text-center text-gray-400">Select a date range and click Generate.</div>
            ) : isLoading ? (
                <div className="glass-card p-8 text-center text-gray-400">Generating Cash Flow Statement…</div>
            ) : error ? (
                <div className="glass-card p-8 text-center text-red-400">Failed to generate report.</div>
            ) : (
                <>
                    <CashSection title="Operating Activities" rows={operating} total={Number(totalOp)} color="text-blue-300" />
                    <CashSection title="Investing Activities" rows={investing} total={Number(totalInv)} color="text-purple-300" />
                    <CashSection title="Financing Activities" rows={financing} total={Number(totalFin)} color="text-yellow-300" />

                    <div className={`glass-card p-5 flex justify-between items-center ${Number(netChange) >= 0 ? 'border border-green-700/40' : 'border border-red-700/40'}`}>
                        <span className="text-white font-bold text-lg">Net Change in Cash</span>
                        <span className={`text-2xl font-bold ${Number(netChange) >= 0 ? 'text-green-300' : 'text-red-300'}`}>
                            {Number(netChange) >= 0 ? '+' : ''}{formatCurrency(Number(netChange))}
                        </span>
                    </div>
                </>
            )}
        </AccountingLayout>
    );
}
