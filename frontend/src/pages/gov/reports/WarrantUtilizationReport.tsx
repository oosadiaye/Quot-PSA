/**
 * Warrant Utilization Report — Quot PSE
 * Route: /budget/warrant-utilization
 *
 * Public-sector quarterly AIE (Authority to Incur Expenditure) reconciliation:
 * compares "warrants released" against "actual consumption" per
 * appropriation and flags over-drawn / exhausted lines so admins can
 * issue supplementary warrants (or reverse the offending postings)
 * before those GLs block further activity.
 */
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    Printer, Scale, AlertTriangle, CheckCircle2, Wallet, TrendingUp,
} from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import apiClient from '../../../api/client';
import ReportError from './ReportError';
import ExportExcelButton from './ExportExcelButton';

const card: React.CSSProperties = {
    background: '#fff', borderRadius: 12,
    border: '1px solid #e8ecf1', padding: 24, marginBottom: 20,
};

const fmtNGN = (v: number | string | null | undefined): string => {
    const n = typeof v === 'string' ? parseFloat(v) : (v ?? 0);
    if (!Number.isFinite(n)) return 'NGN —';
    return 'NGN ' + n.toLocaleString('en-NG', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
};
const fmtPct = (v: number | string | null | undefined): string => {
    const n = typeof v === 'string' ? parseFloat(v) : (v ?? 0);
    if (!Number.isFinite(n)) return '—';
    return `${n.toFixed(1)}%`;
};

type RowStatus = 'OK' | 'WATCH' | 'EXHAUSTED' | 'OVERDRAWN' | 'NO_WARRANT';

interface WarrantRow {
    appropriation_id: number;
    mda_code: string;
    mda: string;
    account_code: string;
    account_name: string;
    fund_code: string;
    fund: string;
    fiscal_year: number;
    amount_approved: string;
    warrants_released: string;
    consumed: string;
    variance: string;
    utilization_pct: string;
    status: RowStatus;
    warrants: Array<{
        quarter: number;
        amount_released: string;
        release_date: string | null;
        authority_reference: string;
    }>;
}

interface WarrantReport {
    title: string;
    standard: string;
    currency: string;
    fiscal_year: number | null;
    items: WarrantRow[];
    totals: {
        total_approved: string;
        total_warrants_released: string;
        total_consumed: string;
        total_variance: string;
        overall_utilization_pct: string;
        status_counts: Record<RowStatus, number>;
        row_count: number;
    };
}

const STATUS_STYLES: Record<RowStatus, { bg: string; fg: string; border: string; label: string }> = {
    OK:         { bg: 'rgba(34,197,94,0.08)',  fg: '#16a34a', border: '#86efac', label: 'OK' },
    WATCH:      { bg: 'rgba(245,158,11,0.08)', fg: '#d97706', border: '#fcd34d', label: 'WATCH' },
    EXHAUSTED:  { bg: 'rgba(239,68,68,0.10)',  fg: '#b91c1c', border: '#fca5a5', label: 'EXHAUSTED' },
    OVERDRAWN:  { bg: 'rgba(239,68,68,0.14)',  fg: '#991b1b', border: '#ef4444', label: 'OVERDRAWN' },
    NO_WARRANT: { bg: 'rgba(100,116,139,0.1)', fg: '#475569', border: '#cbd5e1', label: 'NO WARRANT' },
};

function StatusBadge({ status }: { status: RowStatus }) {
    const s = STATUS_STYLES[status];
    return (
        <span style={{
            display: 'inline-block',
            padding: '2px 10px',
            borderRadius: 999,
            fontSize: 11,
            fontWeight: 700,
            background: s.bg,
            color: s.fg,
            border: `1px solid ${s.border}`,
            letterSpacing: '0.02em',
        }}>
            {s.label}
        </span>
    );
}

export default function WarrantUtilizationReport() {
    const [fy, setFy] = useState<number | ''>(new Date().getFullYear());
    const [statusFilter, setStatusFilter] = useState<RowStatus | ''>('');

    const { data, isLoading, error } = useQuery<WarrantReport>({
        queryKey: ['warrant-utilization', fy],
        queryFn: async () => (
            await apiClient.get('/budget/warrant-utilization/', {
                params: fy ? { fiscal_year: fy } : {},
            })
        ).data,
        retry: false,
    });

    const filtered = useMemo(() => {
        if (!data) return [];
        return statusFilter
            ? data.items.filter((r) => r.status === statusFilter)
            : data.items;
    }, [data, statusFilter]);

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main className="ipsas-report" style={{ marginLeft: 260, padding: 32 }}>
                <div style={{
                    display: 'flex', justifyContent: 'space-between',
                    alignItems: 'center', marginBottom: 24,
                }}>
                    <div>
                        <h1 style={{ fontSize: 24, fontWeight: 800, color: '#1e293b', margin: 0 }}>
                            Warrant Utilization Report
                        </h1>
                        <p style={{ color: '#64748b', fontSize: 14, margin: '4px 0 0' }}>
                            Warrants released vs. actual consumption per appropriation — surfaces
                            over-drawn and exhausted lines that need a supplementary warrant.
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                        <select
                            value={fy}
                            onChange={(e) => setFy(e.target.value ? parseInt(e.target.value) : '')}
                            style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 14 }}
                        >
                            <option value="">All Fiscal Years</option>
                            {[2024, 2025, 2026, 2027].map((y) => (
                                <option key={y} value={y}>FY {y}</option>
                            ))}
                        </select>
                        <button
                            onClick={() => window.print()}
                            style={{
                                display: 'flex', alignItems: 'center', gap: 6,
                                padding: '8px 16px', borderRadius: 8,
                                border: '1px solid #e2e8f0', background: '#fff',
                                cursor: 'pointer', fontSize: 14,
                            }}
                        >
                            <Printer size={16} /> Print
                        </button>
                        <ExportExcelButton
                            endpoint="/budget/warrant-utilization/"
                            params={fy ? { fiscal_year: fy } : {}}
                            filename={`warrant-utilization-${fy || 'all'}.xlsx`}
                        />
                    </div>
                </div>

                {isLoading ? (
                    <div style={{ color: '#94a3b8', textAlign: 'center', padding: 40 }}>Loading...</div>
                ) : error ? (
                    <ReportError error={error} endpoint="/budget/warrant-utilization/" />
                ) : data ? (
                    <>
                        {/* KPI cards */}
                        <div style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                            gap: 16,
                            marginBottom: 20,
                        }}>
                            <KpiCard
                                icon={<Wallet size={18} />}
                                label="Warrants Released"
                                value={fmtNGN(data.totals.total_warrants_released)}
                                subtitle={`${data.totals.row_count} appropriation row(s)`}
                                accent="#2471a3"
                            />
                            <KpiCard
                                icon={<TrendingUp size={18} />}
                                label="Consumed Against Warrants"
                                value={fmtNGN(data.totals.total_consumed)}
                                subtitle={`Overall utilisation ${fmtPct(data.totals.overall_utilization_pct)}`}
                                accent="#d97706"
                            />
                            <KpiCard
                                icon={parseFloat(data.totals.total_variance) >= 0
                                    ? <CheckCircle2 size={18} />
                                    : <AlertTriangle size={18} />}
                                label="Variance (Released − Consumed)"
                                value={fmtNGN(data.totals.total_variance)}
                                subtitle={parseFloat(data.totals.total_variance) >= 0
                                    ? 'Headroom remaining'
                                    : 'Over-drawn — supplementary warrants needed'}
                                accent={parseFloat(data.totals.total_variance) >= 0 ? '#16a34a' : '#b91c1c'}
                            />
                            <KpiCard
                                icon={<Scale size={18} />}
                                label="Status Mix"
                                value={`${data.totals.status_counts.OVERDRAWN} over • ${data.totals.status_counts.EXHAUSTED} exh • ${data.totals.status_counts.WATCH} watch • ${data.totals.status_counts.OK} ok`}
                                subtitle={data.totals.status_counts.NO_WARRANT > 0
                                    ? `${data.totals.status_counts.NO_WARRANT} row(s) have activity but NO warrant`
                                    : 'Thresholds: 70% watch, 95% exhausted'}
                                accent={data.totals.status_counts.OVERDRAWN > 0 ? '#b91c1c' : '#16a34a'}
                            />
                        </div>

                        {/* Status filter tabs */}
                        <div style={{
                            display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap',
                        }}>
                            {(['', 'OVERDRAWN', 'EXHAUSTED', 'WATCH', 'OK', 'NO_WARRANT'] as const).map((s) => {
                                const count = s === ''
                                    ? data.totals.row_count
                                    : (data.totals.status_counts[s] || 0);
                                const active = statusFilter === s;
                                const label = s === '' ? 'All' : STATUS_STYLES[s].label;
                                return (
                                    <button
                                        key={s || 'all'}
                                        onClick={() => setStatusFilter(s as RowStatus | '')}
                                        style={{
                                            padding: '6px 14px', borderRadius: 999,
                                            border: `1px solid ${active ? '#2471a3' : '#e2e8f0'}`,
                                            background: active ? '#2471a3' : '#fff',
                                            color: active ? '#fff' : '#1e293b',
                                            fontSize: 12, fontWeight: 600, cursor: 'pointer',
                                        }}
                                    >
                                        {label} ({count})
                                    </button>
                                );
                            })}
                        </div>

                        {/* Table */}
                        <div style={card}>
                            <div style={{ overflowX: 'auto' }}>
                                <table style={{
                                    width: '100%', borderCollapse: 'collapse', minWidth: 1100,
                                }}>
                                    <thead>
                                        <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                                            {[
                                                { label: 'MDA', align: 'left' },
                                                { label: 'Economic Code', align: 'left' },
                                                { label: 'Fund', align: 'left' },
                                                { label: 'Approved', align: 'right' },
                                                { label: 'Warrants Released', align: 'right' },
                                                { label: 'Consumed', align: 'right' },
                                                { label: 'Variance', align: 'right' },
                                                { label: 'Utilisation', align: 'right' },
                                                { label: 'Status', align: 'center' },
                                            ].map((h) => (
                                                <th key={h.label} style={{
                                                    padding: '10px 14px',
                                                    fontSize: 11,
                                                    fontWeight: 700,
                                                    textTransform: 'uppercase',
                                                    letterSpacing: '0.04em',
                                                    color: '#475569',
                                                    textAlign: h.align as 'left' | 'right' | 'center',
                                                }}>
                                                    {h.label}
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {filtered.length > 0 ? filtered.map((row) => {
                                            const variance = parseFloat(row.variance);
                                            return (
                                                <tr key={row.appropriation_id} style={{
                                                    borderBottom: '1px solid #f1f5f9',
                                                }}>
                                                    <td style={{ padding: '10px 14px', fontSize: 13 }}>
                                                        <div style={{ fontWeight: 600, color: '#1e293b' }}>{row.mda}</div>
                                                        <div style={{ fontSize: 11, color: '#64748b', fontFamily: 'monospace' }}>{row.mda_code}</div>
                                                    </td>
                                                    <td style={{ padding: '10px 14px', fontSize: 13 }}>
                                                        <div style={{ fontFamily: 'monospace', fontWeight: 700, color: '#4f46e5' }}>{row.account_code}</div>
                                                        <div style={{ fontSize: 11, color: '#64748b' }}>{row.account_name}</div>
                                                    </td>
                                                    <td style={{ padding: '10px 14px', fontSize: 13, color: '#64748b' }}>
                                                        {row.fund}
                                                    </td>
                                                    <td style={{ padding: '10px 14px', textAlign: 'right', fontSize: 13, fontFamily: 'monospace' }}>
                                                        {fmtNGN(row.amount_approved)}
                                                    </td>
                                                    <td style={{ padding: '10px 14px', textAlign: 'right', fontSize: 13, fontFamily: 'monospace', color: '#2471a3', fontWeight: 600 }}>
                                                        {fmtNGN(row.warrants_released)}
                                                    </td>
                                                    <td style={{ padding: '10px 14px', textAlign: 'right', fontSize: 13, fontFamily: 'monospace', color: '#d97706', fontWeight: 600 }}>
                                                        {fmtNGN(row.consumed)}
                                                    </td>
                                                    <td style={{
                                                        padding: '10px 14px',
                                                        textAlign: 'right',
                                                        fontSize: 13,
                                                        fontFamily: 'monospace',
                                                        fontWeight: 700,
                                                        color: variance >= 0 ? '#16a34a' : '#b91c1c',
                                                    }}>
                                                        {fmtNGN(row.variance)}
                                                    </td>
                                                    <td style={{ padding: '10px 14px', textAlign: 'right', fontSize: 13, fontFamily: 'monospace' }}>
                                                        {fmtPct(row.utilization_pct)}
                                                    </td>
                                                    <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                                                        <StatusBadge status={row.status} />
                                                    </td>
                                                </tr>
                                            );
                                        }) : (
                                            <tr>
                                                <td colSpan={9} style={{
                                                    padding: 48, textAlign: 'center',
                                                    color: '#94a3b8', fontSize: 14,
                                                }}>
                                                    No appropriations match the current filter.
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                    {filtered.length > 0 && (
                                        <tfoot>
                                            <tr style={{ borderTop: '2px solid #cbd5e1', background: '#f8fafc' }}>
                                                <td style={{ padding: '12px 14px', fontWeight: 700 }} colSpan={3}>
                                                    Totals ({filtered.length} row{filtered.length === 1 ? '' : 's'})
                                                </td>
                                                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>
                                                    {fmtNGN(data.totals.total_approved)}
                                                </td>
                                                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'monospace', fontWeight: 700, color: '#2471a3' }}>
                                                    {fmtNGN(data.totals.total_warrants_released)}
                                                </td>
                                                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'monospace', fontWeight: 700, color: '#d97706' }}>
                                                    {fmtNGN(data.totals.total_consumed)}
                                                </td>
                                                <td style={{
                                                    padding: '12px 14px', textAlign: 'right',
                                                    fontFamily: 'monospace', fontWeight: 700,
                                                    color: parseFloat(data.totals.total_variance) >= 0 ? '#16a34a' : '#b91c1c',
                                                }}>
                                                    {fmtNGN(data.totals.total_variance)}
                                                </td>
                                                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'monospace', fontWeight: 700 }}>
                                                    {fmtPct(data.totals.overall_utilization_pct)}
                                                </td>
                                                <td></td>
                                            </tr>
                                        </tfoot>
                                    )}
                                </table>
                            </div>
                        </div>
                    </>
                ) : null}
            </main>
        </div>
    );
}

interface KpiCardProps {
    icon: React.ReactNode;
    label: string;
    value: string;
    subtitle?: string;
    accent?: string;
}

function KpiCard({ icon, label, value, subtitle, accent = '#2471a3' }: KpiCardProps) {
    return (
        <div style={{
            padding: 20, background: '#fff',
            borderLeft: `4px solid ${accent}`,
            borderRadius: 10,
            border: '1px solid #e8ecf1',
            display: 'flex', flexDirection: 'column', gap: 6,
        }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: accent }}>
                {icon}
                <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                    {label}
                </span>
            </div>
            <div style={{ fontSize: 18, fontWeight: 800, color: '#1e293b', lineHeight: 1.2 }}>
                {value}
            </div>
            {subtitle && (
                <div style={{ fontSize: 11, color: '#64748b' }}>
                    {subtitle}
                </div>
            )}
        </div>
    );
}
