import { useState } from 'react';
import { Lock, CheckCircle, AlertTriangle, XCircle, RefreshCw } from 'lucide-react';
import { usePeriodCloseChecklist } from '../hooks/useFinancialReports';
import type { PeriodCloseChecklistItem } from '../hooks/useFinancialReports';
import { useFiscalPeriods } from '../hooks/useFiscalYear';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';

interface CheckCardProps {
    label: string;
    count: number;
    description: string;
}

function CheckCard({ label, count, description }: CheckCardProps) {
    const isPassed = count === 0;
    return (
        <div style={{
            flex: '1 1 180px',
            minWidth: '180px',
            padding: '16px',
            borderRadius: '12px',
            border: `1.5px solid ${isPassed ? '#a7f3d0' : '#fecaca'}`,
            background: isPassed ? '#ecfdf5' : '#fef2f2',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
        }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                {isPassed ? (
                    <CheckCircle size={20} style={{ color: '#059669' }} />
                ) : (
                    <XCircle size={20} style={{ color: '#dc2626' }} />
                )}
                {!isPassed && (
                    <span style={{
                        background: '#fee2e2', color: '#b91c1c',
                        fontSize: '11px', fontWeight: 700,
                        padding: '2px 8px', borderRadius: '999px',
                    }}>
                        {count}
                    </span>
                )}
            </div>
            <div style={{
                fontSize: '13px', fontWeight: 700,
                color: isPassed ? '#065f46' : '#991b1b',
            }}>
                {label}
            </div>
            <div style={{ fontSize: '11px', color: '#64748b', lineHeight: '1.4' }}>
                {description}
            </div>
        </div>
    );
}

export default function PeriodClose() {
    const [selectedPeriodId, setSelectedPeriodId] = useState<number | null>(null);

    const { data: periodsData } = useFiscalPeriods({ status: 'Open' });
    const periods: any[] = Array.isArray(periodsData) ? periodsData : (periodsData?.results ?? []);

    const { data: checklist, isLoading, refetch } = usePeriodCloseChecklist(selectedPeriodId);

    const items: PeriodCloseChecklistItem | undefined = checklist?.items;

    const checkItems = items ? [
        {
            label: 'Unposted Journals',
            count: items.unposted_journals,
            description: 'Draft or Pending journal entries must be posted or deleted.',
        },
        {
            label: 'Open GRNs',
            count: items.open_grn_without_invoice,
            description: 'GRNs with no matched vendor invoice leave GR/IR clearing open.',
        },
        {
            label: 'Unreconciled Payments',
            count: items.unreconciled_payments,
            description: 'Vendor payments not yet matched in bank reconciliation.',
        },
        {
            label: 'Unreconciled Receipts',
            count: items.unreconciled_receipts,
            description: 'Customer receipts not yet matched in bank reconciliation.',
        },
        {
            label: 'Pending Approvals',
            count: items.pending_approvals,
            description: 'Journal entries awaiting approval must be resolved.',
        },
    ] : [];

    const allClear = checklist?.is_clear_to_close === true;
    const totalIssues = checkItems.reduce((s, c) => s + c.count, 0);

    return (
        <AccountingLayout>
            <PageHeader
                title="Period Close"
                subtitle="Pre-flight checklist before closing an accounting period"
                icon={<Lock className="w-6 h-6" />}
            />

            {/* Filters — horizontal */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: '12px',
                background: '#fff', borderRadius: '12px', padding: '10px 20px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.06)', marginBottom: '20px',
            }}>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#64748b', whiteSpace: 'nowrap' }}>
                    Fiscal Period
                </span>
                <select
                    value={selectedPeriodId ?? ''}
                    onChange={e => setSelectedPeriodId(e.target.value ? Number(e.target.value) : null)}
                    style={{
                        flex: 1, padding: '6px 10px', border: '1px solid #e2e8f0',
                        borderRadius: '8px', fontSize: '13px', fontWeight: 600, color: '#1e293b',
                        maxWidth: '320px',
                    }}
                >
                    <option value="">— All open periods —</option>
                    {periods.map((p: any) => (
                        <option key={p.id} value={p.id}>{p.name ?? `${p.start_date} → ${p.end_date}`}</option>
                    ))}
                </select>
                <button onClick={() => refetch()} style={{
                    display: 'inline-flex', alignItems: 'center', gap: '5px',
                    padding: '6px 12px', border: '1px solid #e2e8f0', borderRadius: '8px',
                    background: '#f8fafc', fontSize: '13px', fontWeight: 600, color: '#475569',
                    cursor: 'pointer', whiteSpace: 'nowrap',
                }}>
                    <RefreshCw size={14} /> Refresh
                </button>
            </div>

            {isLoading ? (
                <div style={{
                    background: '#fff', borderRadius: '12px', padding: '48px',
                    textAlign: 'center', color: '#94a3b8',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                }}>
                    Running pre-flight checks…
                </div>
            ) : !checklist ? (
                <div style={{
                    background: '#fff', borderRadius: '12px', padding: '48px',
                    textAlign: 'center', color: '#94a3b8',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                }}>
                    Select a period to run the checklist.
                </div>
            ) : (
                <>
                    {/* Summary banner */}
                    <div style={{
                        marginBottom: '20px', padding: '14px 20px', borderRadius: '12px',
                        display: 'flex', alignItems: 'center', gap: '14px',
                        border: `1.5px solid ${allClear ? '#a7f3d0' : '#fde68a'}`,
                        background: allClear ? '#ecfdf5' : '#fffbeb',
                    }}>
                        {allClear ? (
                            <CheckCircle size={28} style={{ color: '#059669', flexShrink: 0 }} />
                        ) : (
                            <AlertTriangle size={28} style={{ color: '#d97706', flexShrink: 0 }} />
                        )}
                        <div>
                            <div style={{
                                fontWeight: 700, fontSize: '15px',
                                color: allClear ? '#065f46' : '#92400e',
                            }}>
                                {allClear
                                    ? 'All checks passed — period is clear to close'
                                    : `${totalIssues} issue${totalIssues !== 1 ? 's' : ''} must be resolved before closing`}
                            </div>
                            {checklist.period_name && (
                                <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                                    Period: {checklist.period_name}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Check items — horizontal card grid */}
                    <div style={{
                        display: 'flex', gap: '12px', flexWrap: 'wrap',
                    }}>
                        {checkItems.map((item, i) => (
                            <CheckCard key={i} {...item} />
                        ))}
                    </div>
                </>
            )}
        </AccountingLayout>
    );
}
