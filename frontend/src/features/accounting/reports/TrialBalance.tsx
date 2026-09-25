import { useState } from 'react';
import { BarChart3, Download, RefreshCw, CheckCircle, AlertTriangle } from 'lucide-react';
import { useTrialBalance } from '../hooks/useFinancialReports';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import { useCurrency } from '../../../context/CurrencyContext';

export default function TrialBalance() {
    const { formatCurrency } = useCurrency();
    const currentYear = new Date().getFullYear();
    const currentMonth = new Date().getMonth() + 1;

    const [fiscalYear, setFiscalYear] = useState(currentYear);
    const [period, setPeriod] = useState(currentMonth);

    const { data: rawData, isLoading, error, refetch } = useTrialBalance({ fiscal_year: fiscalYear, period });

    interface TrialBalanceData {
        accounts?: any[];
        results?: any[];
        [key: string]: any;
    }
    const data = rawData as TrialBalanceData | any[] | undefined;

    const accounts: any[] = (data as TrialBalanceData)?.accounts ?? (data as TrialBalanceData)?.results ?? (Array.isArray(data) ? data : []);

    const totalDebits = accounts.reduce((sum: number, a: any) => sum + parseFloat(a.debit_balance ?? a.total_debit ?? 0), 0);
    const totalCredits = accounts.reduce((sum: number, a: any) => sum + parseFloat(a.credit_balance ?? a.total_credit ?? 0), 0);
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

    const inputStyle: React.CSSProperties = {
        padding: '6px 10px',
        border: '1px solid var(--color-border)',
        borderRadius: '8px',
        fontSize: '13px',
        fontWeight: 600,
        color: 'var(--color-text)',
    };

    return (
        <AccountingLayout>
            <PageHeader
                title="Trial Balance"
                subtitle="Aggregated debit and credit balances for all GL accounts"
                icon={<BarChart3 className="w-6 h-6" />}
            />

            {/* Filters — horizontal row */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: '12px',
                background: 'var(--color-surface)', borderRadius: '12px', padding: '10px 20px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.06)', marginBottom: '20px',
                flexWrap: 'wrap',
            }}>
                <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>Fiscal Year</span>
                <input
                    type="number"
                    value={fiscalYear}
                    onChange={e => setFiscalYear(Number(e.target.value))}
                    style={{ ...inputStyle, width: '80px' }}
                />
                <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>Period</span>
                <select
                    value={period}
                    onChange={e => setPeriod(Number(e.target.value))}
                    style={{ ...inputStyle, width: '150px' }}
                >
                    {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
                        <option key={m} value={m}>
                            {new Date(2000, m - 1).toLocaleString('default', { month: 'long' })} ({m})
                        </option>
                    ))}
                </select>
                <button onClick={() => refetch()} style={{
                    display: 'inline-flex', alignItems: 'center', gap: '5px',
                    padding: '6px 12px', border: '1px solid var(--color-border)', borderRadius: '8px',
                    background: 'var(--color-surface-hover)', fontSize: '13px', fontWeight: 600, color: 'var(--color-text-secondary)',
                    cursor: 'pointer', whiteSpace: 'nowrap',
                }}>
                    <RefreshCw size={14} /> Refresh
                </button>
                <div style={{ flex: 1 }} />
                <button onClick={handleExport} style={{
                    display: 'inline-flex', alignItems: 'center', gap: '5px',
                    padding: '6px 12px', border: 'none', borderRadius: '8px',
                    background: '#1e293b', fontSize: '13px', fontWeight: 600, color: '#fff',
                    cursor: 'pointer', whiteSpace: 'nowrap',
                }}>
                    <Download size={14} /> Export CSV
                </button>
            </div>

            {/* Balance status banner */}
            {!isLoading && accounts.length > 0 && (
                <div style={{
                    marginBottom: '16px', padding: '12px 20px', borderRadius: '12px',
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
                            ? 'Trial Balance is balanced'
                            : `Out of balance by ${formatCurrency(Math.abs(totalDebits - totalCredits))}`}
                    </span>
                </div>
            )}

            {/* Summary cards */}
            {!isLoading && accounts.length > 0 && (
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '16px' }}>
                    <div style={{
                        flex: '1 1 180px', padding: '14px 18px', borderRadius: '10px',
                        border: '1.5px solid #bae6fd', background: '#f0f9ff',
                        display: 'flex', flexDirection: 'column', gap: '4px',
                    }}>
                        <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                            Total Debits
                        </span>
                        <span style={{ fontSize: '18px', fontWeight: 700, color: '#0284c7' }}>
                            {formatCurrency(totalDebits)}
                        </span>
                    </div>
                    <div style={{
                        flex: '1 1 180px', padding: '14px 18px', borderRadius: '10px',
                        border: '1.5px solid #ddd6fe', background: '#f5f3ff',
                        display: 'flex', flexDirection: 'column', gap: '4px',
                    }}>
                        <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                            Total Credits
                        </span>
                        <span style={{ fontSize: '18px', fontWeight: 700, color: '#7c3aed' }}>
                            {formatCurrency(totalCredits)}
                        </span>
                    </div>
                    <div style={{
                        flex: '1 1 180px', padding: '14px 18px', borderRadius: '10px',
                        border: `1.5px solid ${isBalanced ? '#a7f3d0' : '#fecaca'}`,
                        background: isBalanced ? '#ecfdf5' : '#fef2f2',
                        display: 'flex', flexDirection: 'column', gap: '4px',
                    }}>
                        <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                            Difference
                        </span>
                        <span style={{ fontSize: '18px', fontWeight: 700, color: isBalanced ? '#059669' : '#dc2626' }}>
                            {isBalanced ? 'Balanced' : formatCurrency(Math.abs(totalDebits - totalCredits))}
                        </span>
                    </div>
                </div>
            )}

            {/* Table */}
            <div style={{
                background: 'var(--color-surface)', borderRadius: '12px', overflow: 'hidden',
                boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                border: '1.5px solid var(--color-border)',
            }}>
                {isLoading ? (
                    <div style={{ padding: '48px', textAlign: 'center', color: 'var(--color-text-subtle)' }}>Loading trial balance…</div>
                ) : error ? (
                    <div style={{ padding: '48px', textAlign: 'center', color: '#ef4444' }}>Failed to load trial balance.</div>
                ) : accounts.length === 0 ? (
                    <div style={{ padding: '48px', textAlign: 'center', color: 'var(--color-text-subtle)' }}>No data for selected period.</div>
                ) : (
                    <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '2px solid var(--color-border)', background: 'var(--color-surface-hover)' }}>
                                <th style={{ padding: '12px 16px', textAlign: 'left', color: 'var(--color-text-muted)', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Code</th>
                                <th style={{ padding: '12px 16px', textAlign: 'left', color: 'var(--color-text-muted)', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Account Name</th>
                                <th style={{ padding: '12px 16px', textAlign: 'left', color: 'var(--color-text-muted)', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Type</th>
                                <th style={{ padding: '12px 16px', textAlign: 'right', color: 'var(--color-text-muted)', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Debit</th>
                                <th style={{ padding: '12px 16px', textAlign: 'right', color: 'var(--color-text-muted)', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Credit</th>
                                <th style={{ padding: '12px 16px', textAlign: 'right', color: 'var(--color-text-muted)', fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Net</th>
                            </tr>
                        </thead>
                        <tbody>
                            {accounts.map((a: any, i: number) => {
                                const dr = parseFloat(a.debit_balance ?? a.total_debit ?? 0);
                                const cr = parseFloat(a.credit_balance ?? a.total_credit ?? 0);
                                const net = dr - cr;
                                return (
                                    <tr key={a.account_code ?? a.account?.code ?? i}
                                        style={{ borderBottom: '1px solid var(--color-border-light)' }}
                                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-surface-hover)')}
                                        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                                    >
                                        <td style={{ padding: '10px 16px', fontFamily: 'monospace', color: '#3b82f6', fontWeight: 600 }}>
                                            {a.account_code ?? a.account?.code}
                                        </td>
                                        <td style={{ padding: '10px 16px', color: 'var(--color-text)' }}>{a.account_name ?? a.account?.name}</td>
                                        <td style={{ padding: '10px 16px' }}>
                                            <span style={{
                                                padding: '2px 8px', borderRadius: '999px', fontSize: '11px', fontWeight: 600,
                                                background: a.account_type === 'Asset' ? '#dbeafe' :
                                                    a.account_type === 'Liability' ? '#fce7f3' :
                                                    a.account_type === 'Equity' ? '#f3e8ff' :
                                                    a.account_type === 'Income' ? '#dcfce7' :
                                                    a.account_type === 'Expense' ? '#fef3c7' : 'var(--color-surface-hover)',
                                                color: a.account_type === 'Asset' ? '#1d4ed8' :
                                                    a.account_type === 'Liability' ? '#be185d' :
                                                    a.account_type === 'Equity' ? '#7c3aed' :
                                                    a.account_type === 'Income' ? '#16a34a' :
                                                    a.account_type === 'Expense' ? '#d97706' : 'var(--color-text-muted)',
                                            }}>
                                                {a.account_type}
                                            </span>
                                        </td>
                                        <td style={{ padding: '10px 16px', textAlign: 'right', fontFamily: 'monospace', color: 'var(--color-text)' }}>
                                            {dr > 0 ? formatCurrency(dr) : '—'}
                                        </td>
                                        <td style={{ padding: '10px 16px', textAlign: 'right', fontFamily: 'monospace', color: 'var(--color-text)' }}>
                                            {cr > 0 ? formatCurrency(cr) : '—'}
                                        </td>
                                        <td style={{
                                            padding: '10px 16px', textAlign: 'right',
                                            fontWeight: 600, fontFamily: 'monospace',
                                            color: net >= 0 ? '#059669' : '#dc2626',
                                        }}>
                                            {net >= 0 ? '+' : '−'}{formatCurrency(Math.abs(net))} {net < 0 ? 'Cr' : 'Dr'}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                        <tfoot>
                            <tr style={{ borderTop: '2px solid var(--color-border)', background: 'var(--color-surface-hover)' }}>
                                <td style={{ padding: '14px 16px', fontWeight: 700, color: 'var(--color-text)' }} colSpan={3}>TOTALS</td>
                                <td style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 700, fontFamily: 'monospace', color: '#0284c7' }}>
                                    {formatCurrency(totalDebits)}
                                </td>
                                <td style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 700, fontFamily: 'monospace', color: '#7c3aed' }}>
                                    {formatCurrency(totalCredits)}
                                </td>
                                <td style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 700, fontFamily: 'monospace' }}>
                                    {isBalanced ? (
                                        <span style={{ color: '#059669' }}>Balanced</span>
                                    ) : (
                                        <span style={{ color: '#dc2626' }}>{formatCurrency(Math.abs(totalDebits - totalCredits))} diff</span>
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
