/**
 * TSA Cash Position Report — Quot PSE
 * Route: /accounting/ipsas/tsa-cash-position
 */
import { useQuery } from '@tanstack/react-query';
import { Printer, Landmark } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import apiClient from '../../../api/client';
import ReportError from './ReportError';
import ExportExcelButton from './ExportExcelButton';

const fmtNGN = (v: number) => 'NGN ' + (v || 0).toLocaleString('en-NG', { minimumFractionDigits: 2 });

export default function TSACashPositionReport() {
    const { data, isLoading, error } = useQuery({
        queryKey: ['ipsas-tsa-cash-full'],
        queryFn: async () => (await apiClient.get('/accounting/ipsas/tsa-cash-position/')).data,
        retry: false,
    });

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 800, color: '#1e293b', margin: 0 }}>TSA Cash Position</h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>Real-time Treasury Single Account balance overview</p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <button onClick={() => window.print()} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', borderRadius: '8px', border: '1px solid #e2e8f0', background: '#fff', cursor: 'pointer', fontSize: '14px' }}>
                            <Printer size={16} /> Print
                        </button>
                        <ExportExcelButton
                            endpoint="/accounting/ipsas/tsa-cash-position/"
                            filename="tsa-cash-position.xlsx"
                        />
                    </div>
                </div>

                {isLoading ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>Loading...</div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/tsa-cash-position/" />
                ) : data ? (
                    <div style={{ maxWidth: '900px' }}>
                        {/* Total Balance */}
                        <div style={{ background: '#008751', borderRadius: '12px', padding: '32px', marginBottom: '24px', textAlign: 'center', color: '#fff' }}>
                            <Landmark size={32} style={{ marginBottom: '8px', opacity: 0.8 }} />
                            <div style={{ fontSize: '13px', fontWeight: 600, textTransform: 'uppercase', opacity: 0.8 }}>Total TSA Balance</div>
                            <div style={{ fontSize: '36px', fontWeight: 800, fontFamily: 'monospace', marginTop: '4px' }}>{fmtNGN(data.total_balance)}</div>
                            <div style={{ fontSize: '13px', opacity: 0.7, marginTop: '4px' }}>{data.account_count} active accounts</div>
                        </div>

                        {/* By Account Type */}
                        <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1', padding: '24px', marginBottom: '20px' }}>
                            <div style={{ fontSize: '15px', fontWeight: 700, color: '#1e293b', marginBottom: '16px' }}>Balance by Account Type</div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
                                {(data.by_account_type || []).map((acct: any, i: number) => (
                                    <div key={i} style={{ padding: '16px', borderRadius: '10px', background: '#f8fafc', border: '1px solid #e8ecf1' }}>
                                        <div style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: '6px' }}>
                                            {(acct.account_type || '').replace(/_/g, ' ')}
                                        </div>
                                        <div style={{ fontSize: '20px', fontWeight: 800, color: '#1e293b', fontFamily: 'monospace' }}>{fmtNGN(acct.balance)}</div>
                                        <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px' }}>{acct.count} account{acct.count !== 1 ? 's' : ''}</div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Top MDA Balances */}
                        {data.top_mda_balances?.length > 0 && (
                            <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e8ecf1', padding: '24px' }}>
                                <div style={{ fontSize: '15px', fontWeight: 700, color: '#1e293b', marginBottom: '16px' }}>Top MDA Balances</div>
                                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                    <thead>
                                        <tr style={{ borderBottom: '2px solid #e8ecf1' }}>
                                            <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>MDA</th>
                                            <th style={{ padding: '8px 12px', textAlign: 'right', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Balance</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {data.top_mda_balances.map((mda: any, i: number) => (
                                            <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                                <td style={{ padding: '8px 12px', fontSize: '13px' }}>{mda.mda__name}</td>
                                                <td style={{ padding: '8px 12px', fontSize: '13px', textAlign: 'right', fontFamily: 'monospace', fontWeight: 600 }}>{fmtNGN(mda.balance)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                ) : null}
            </main>
        </div>
    );
}
