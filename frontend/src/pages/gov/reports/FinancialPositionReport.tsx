/**
 * IPSAS Statement of Financial Position (Balance Sheet) — Quot PSE
 * Route: /accounting/ipsas/financial-position
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Printer } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import apiClient from '../../../api/client';
import ReportError from './ReportError';
import ExportExcelButton from './ExportExcelButton';
import BrandedPrintHeader from '../../../components/print/BrandedPrintHeader';

const fmtNGN = (v: number) => 'NGN ' + (v || 0).toLocaleString('en-NG', { minimumFractionDigits: 2 });
const card: React.CSSProperties = { background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', padding: '24px', marginBottom: '20px' };
const hdr: React.CSSProperties = { fontSize: '13px', fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', padding: '8px 0', borderBottom: '2px solid var(--color-border)' };

export default function FinancialPositionReport() {
    const [fy, setFy] = useState(new Date().getFullYear());

    const { data, isLoading, error } = useQuery({
        queryKey: ['ipsas-financial-position', fy],
        queryFn: async () => (await apiClient.get('/accounting/ipsas/financial-position/', { params: { fiscal_year: fy } })).data,
        retry: false,
    });

    // A header's ``amount`` is the roll-up of its children, which are
    // listed individually — showing both would read as double counting,
    // so header rows stay hidden. The exception is ``direct_amount``:
    // a balance posted to the header itself, represented by no child
    // line. It is counted in the section total, so hiding it would
    // leave the visible rows not adding up to the total shown beneath
    // them. It is rendered, flagged, and almost always absent.
    const renderItems = (items: any[]) => items
        ?.filter((i: any) => !i.is_header || Number(i.direct_amount || 0) !== 0)
        .map((i: any, idx: number) => {
            const postedToHeader = i.is_header && Number(i.direct_amount || 0) !== 0;
            return (
                <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0 6px 20px', borderBottom: '1px solid #f8fafc' }}>
                    <span style={{ fontSize: '13px', color: postedToHeader ? '#92400e' : 'var(--color-text)' }}>
                        {i.code} — {i.name}
                        {postedToHeader && (
                            <span
                                title="Posted directly to a group account. Included so the statement adds up; move these postings to a leaf account."
                                style={{ marginLeft: 8, fontSize: '11px', fontWeight: 700, color: '#92400e', background: '#fef3c7', borderRadius: 3, padding: '1px 6px' }}
                            >
                                posted to group account
                            </span>
                        )}
                    </span>
                    <span style={{ fontSize: '13px', fontWeight: 600, fontFamily: 'monospace', color: postedToHeader ? '#92400e' : undefined }}>
                        {fmtNGN(postedToHeader ? i.direct_amount : i.amount)}
                    </span>
                </div>
            );
        });

    // Accounts in the family but outside the statement's named
    // sub-families (30xxxxxx, 48xxxxxx …). The backend reports them so
    // they are not lost; this renders them only when there is something
    // to render, so a well-coded chart shows no extra heading.
    const renderUnclassified = (section: any, label: string) => {
        const items = (section?.items || []).filter((i: any) => Number(i.amount) !== 0);
        if (items.length === 0) return null;
        return (
            <div style={{ padding: '12px 0' }}>
                <div style={{ fontSize: '13px', fontWeight: 700, color: '#92400e', marginBottom: '8px' }}>
                    {label}
                    <span style={{ marginLeft: 8, fontWeight: 500, color: '#b45309', fontSize: '12px' }}>
                        — not yet assigned to a statement heading; give these codes a
                        sub-family so they report in the right place
                    </span>
                </div>
                {renderItems(items)}
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px', fontWeight: 600, fontSize: '13px', background: '#fffbeb', borderRadius: '4px' }}>
                    <span>Total {label}</span><span style={{ fontFamily: 'monospace' }}>{fmtNGN(section?.total)}</span>
                </div>
            </div>
        );
    };

    const renderTotal = (label: string, amount: number, color: string) => (
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderTop: '2px solid #1e293b', marginTop: '8px' }}>
            <span style={{ fontWeight: 800, fontSize: '14px', color }}>{label}</span>
            <span style={{ fontWeight: 800, fontSize: '14px', fontFamily: 'monospace', color }}>{fmtNGN(amount)}</span>
        </div>
    );

    return (
        <div style={{ background: 'var(--color-surface-hover)', minHeight: '100vh' }}>
            {/* Print-only stylesheet: hide the sidebar + screen header,
                show the BrandedPrintHeader + report cards. The
                ``.print-only`` block is invisible on screen but appears
                at the top of every printed page so the report carries
                the tenant's branding (logo, name, address) wherever it
                travels. The screen-only version of the page-header
                stays unchanged so day-to-day use isn't affected. */}
            <style>{`
                @media print {
                    aside, nav, .no-print { display: none !important; }
                    .print-only { display: block !important; }
                    main.ipsas-report { margin-left: 0 !important; padding: 16mm !important; }
                    body { background: white !important; }
                }
                .print-only { display: none; }
            `}</style>
            <Sidebar />
            <main className="ipsas-report" style={{ marginLeft: '260px', padding: '32px' }}>
                <div className="print-only" style={{ marginBottom: 16 }}>
                    <BrandedPrintHeader subtitle="Statement of Financial Position · IPSAS 1" />
                    <div style={{ marginTop: 8, fontSize: 11, color: 'var(--color-text-secondary)', textAlign: 'center' }}>
                        Fiscal Year: <strong>FY {fy}</strong>
                    </div>
                </div>

                <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 800, color: 'var(--color-text)', margin: 0 }}>Statement of Financial Position</h1>
                        <p style={{ color: 'var(--color-text-muted)', fontSize: '14px', margin: '4px 0 0' }}>IPSAS 1 — Balance Sheet</p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <select value={fy} onChange={e => setFy(parseInt(e.target.value))} style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid var(--color-border)', fontSize: '14px' }}>
                            {[2024, 2025, 2026, 2027].map(y => <option key={y} value={y}>FY {y}</option>)}
                        </select>
                        <button onClick={() => window.print()} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', cursor: 'pointer', fontSize: '14px' }}>
                            <Printer size={16} /> Print
                        </button>
                        <ExportExcelButton
                            endpoint="/accounting/ipsas/financial-position/"
                            params={{ fiscal_year: fy }}
                            filename={`sofp-${fy}.xlsx`}
                        />
                    </div>
                </div>

                {isLoading ? (
                    <div style={{ color: 'var(--color-text-subtle)', textAlign: 'center', padding: '40px' }}>Loading...</div>
                ) : error ? (
                    <ReportError error={error} endpoint="/accounting/ipsas/financial-position/" />
                ) : data ? (
                    <div style={{ maxWidth: '800px' }}>
                        {/* Assets */}
                        <div style={card}>
                            <div style={hdr}>ASSETS</div>
                            <div style={{ padding: '12px 0' }}>
                                <div style={{ fontSize: '13px', fontWeight: 700, color: '#008751', marginBottom: '8px' }}>Current Assets</div>
                                {renderItems(data.assets?.current?.items)}
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600, fontSize: '13px', background: '#f0fdf4', borderRadius: '4px', padding: '8px' }}>
                                    <span>Total Current Assets</span><span style={{ fontFamily: 'monospace' }}>{fmtNGN(data.assets?.current?.total)}</span>
                                </div>
                            </div>
                            <div style={{ padding: '12px 0' }}>
                                <div style={{ fontSize: '13px', fontWeight: 700, color: '#1e4d8c', marginBottom: '8px' }}>Non-Current Assets</div>
                                {renderItems(data.assets?.non_current?.items)}
                                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px', fontWeight: 600, fontSize: '13px', background: '#eff6ff', borderRadius: '4px' }}>
                                    <span>Total Non-Current Assets</span><span style={{ fontFamily: 'monospace' }}>{fmtNGN(data.assets?.non_current?.total)}</span>
                                </div>
                            </div>
                            {renderUnclassified(data.assets?.unclassified, 'Unclassified Assets')}
                            {renderTotal('TOTAL ASSETS', data.assets?.total, '#008751')}
                        </div>

                        {/* Liabilities */}
                        <div style={card}>
                            <div style={hdr}>LIABILITIES</div>
                            <div style={{ padding: '12px 0' }}>
                                <div style={{ fontSize: '13px', fontWeight: 700, color: '#c0392b', marginBottom: '8px' }}>Current Liabilities</div>
                                {renderItems(data.liabilities?.current?.items)}
                                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px', fontWeight: 600, fontSize: '13px', background: '#fef2f2', borderRadius: '4px' }}>
                                    <span>Total Current Liabilities</span><span style={{ fontFamily: 'monospace' }}>{fmtNGN(data.liabilities?.current?.total)}</span>
                                </div>
                            </div>
                            <div style={{ padding: '12px 0' }}>
                                <div style={{ fontSize: '13px', fontWeight: 700, color: '#92400e', marginBottom: '8px' }}>Non-Current Liabilities</div>
                                {renderItems(data.liabilities?.non_current?.items)}
                            </div>
                            {renderUnclassified(data.liabilities?.unclassified, 'Unclassified Liabilities')}
                            {renderTotal('TOTAL LIABILITIES', data.liabilities?.total, '#c0392b')}
                        </div>

                        {/* Net Assets */}
                        <div style={card}>
                            <div style={hdr}>NET ASSETS / EQUITY</div>
                            {renderItems(data.net_assets?.items)}
                            {renderTotal('TOTAL NET ASSETS', data.net_assets?.total, '#1e4d8c')}
                        </div>

                        {/* Balance Check */}
                        <div style={{
                            ...card, background: data.balance_check?.is_balanced ? '#f0fdf4' : '#fef2f2',
                            border: `2px solid ${data.balance_check?.is_balanced ? '#22c55e' : '#ef4444'}`,
                            textAlign: 'center',
                        }}>
                            <div style={{ fontSize: '14px', fontWeight: 700, color: data.balance_check?.is_balanced ? '#16a34a' : '#dc2626' }}>
                                {data.balance_check?.is_balanced ? 'BALANCED' : 'NOT BALANCED'}
                            </div>
                            <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                                Assets: {fmtNGN(data.balance_check?.assets)} = Liabilities + Net Assets: {fmtNGN(data.balance_check?.liabilities_plus_net_assets)}
                            </div>
                        </div>
                    </div>
                ) : null}

                <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--color-text-subtle)', fontSize: '11px' }}>
                    Quot PSE IFMIS — IPSAS 1 Compliant
                </div>
            </main>
        </div>
    );
}
