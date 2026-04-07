import { useState } from 'react';
import { Lock, CheckCircle, AlertTriangle, XCircle, RefreshCw } from 'lucide-react';
import { usePeriodCloseChecklist, PeriodCloseChecklistItem } from '../hooks/useFinancialReports';
import { useFiscalPeriods } from '../hooks/useFiscalYear';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import '../styles/glassmorphism.css';

interface CheckItemProps {
    label: string;
    count: number;
    description: string;
}

function CheckItem({ label, count, description }: CheckItemProps) {
    const isPassed = count === 0;
    return (
        <div className={`flex items-start gap-4 p-4 rounded-lg border ${
            isPassed
                ? 'border-green-700/40 bg-green-900/10'
                : 'border-red-700/40 bg-red-900/10'
        }`}>
            <div className="mt-0.5">
                {isPassed ? (
                    <CheckCircle className="w-5 h-5 text-green-400" />
                ) : (
                    <XCircle className="w-5 h-5 text-red-400" />
                )}
            </div>
            <div className="flex-1">
                <div className="flex justify-between items-center">
                    <span className={`font-medium ${isPassed ? 'text-green-300' : 'text-red-300'}`}>{label}</span>
                    {!isPassed && (
                        <span className="bg-red-800/50 text-red-200 text-xs font-bold px-2 py-0.5 rounded-full">
                            {count} pending
                        </span>
                    )}
                </div>
                <p className="text-gray-400 text-sm mt-0.5">{description}</p>
            </div>
        </div>
    );
}

export default function PeriodClose() {
    const [selectedPeriodId, setSelectedPeriodId] = useState<number | null>(null);

    // Use existing fiscal periods hook — filter to open periods only
    const { data: periodsData } = useFiscalPeriods({ status: 'Open' });
    const periods: any[] = Array.isArray(periodsData) ? periodsData : (periodsData?.results ?? []);

    const { data: checklist, isLoading, refetch } = usePeriodCloseChecklist(selectedPeriodId);

    const items: PeriodCloseChecklistItem | undefined = checklist?.items;

    const checkItems = items ? [
        {
            label: 'Unposted Journal Entries',
            count: items.unposted_journals,
            description: 'All journal entries in Draft or Pending status must be posted or deleted before closing.',
        },
        {
            label: 'Open GRNs Without Invoice',
            count: items.open_grn_without_invoice,
            description: 'Goods received notes with no matched vendor invoice leave GR/IR clearing unresolved.',
        },
        {
            label: 'Unreconciled Payments',
            count: items.unreconciled_payments,
            description: 'Posted vendor payments that have not been matched in a bank reconciliation.',
        },
        {
            label: 'Unreconciled Receipts',
            count: items.unreconciled_receipts,
            description: 'Posted customer receipts that have not been matched in a bank reconciliation.',
        },
        {
            label: 'Pending Approval Workflows',
            count: items.pending_approvals,
            description: 'Journal entries awaiting approval must be resolved (approved or rejected) before closing.',
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

            <div className="glass-card p-4 mb-6 flex flex-wrap gap-4 items-end">
                <div className="flex-1">
                    <label className="block text-sm font-medium text-gray-300 mb-1">Fiscal Period</label>
                    <select
                        value={selectedPeriodId ?? ''}
                        onChange={e => setSelectedPeriodId(e.target.value ? Number(e.target.value) : null)}
                        className="glass-input w-full"
                    >
                        <option value="">— All open periods —</option>
                        {periods.map((p: any) => (
                            <option key={p.id} value={p.id}>{p.name ?? `${p.start_date} → ${p.end_date}`}</option>
                        ))}
                    </select>
                </div>
                <button onClick={() => refetch()} className="glass-btn flex items-center gap-2">
                    <RefreshCw className="w-4 h-4" /> Refresh
                </button>
            </div>

            {isLoading ? (
                <div className="glass-card p-8 text-center text-gray-400">Running pre-flight checks…</div>
            ) : !checklist ? (
                <div className="glass-card p-8 text-center text-gray-400">Select a period to run the checklist.</div>
            ) : (
                <>
                    {/* Summary banner */}
                    <div className={`mb-6 p-4 rounded-xl border flex items-center gap-4 ${
                        allClear
                            ? 'bg-green-900/20 border-green-700/50'
                            : 'bg-yellow-900/20 border-yellow-700/50'
                    }`}>
                        {allClear ? (
                            <CheckCircle className="w-8 h-8 text-green-400 flex-shrink-0" />
                        ) : (
                            <AlertTriangle className="w-8 h-8 text-yellow-400 flex-shrink-0" />
                        )}
                        <div>
                            <div className={`font-bold text-lg ${allClear ? 'text-green-300' : 'text-yellow-300'}`}>
                                {allClear ? 'All checks passed — period is clear to close' : `${totalIssues} issue${totalIssues !== 1 ? 's' : ''} must be resolved before closing`}
                            </div>
                            {checklist.period_name && (
                                <div className="text-gray-400 text-sm">Period: {checklist.period_name}</div>
                            )}
                        </div>
                    </div>

                    {/* Check items */}
                    <div className="space-y-3">
                        {checkItems.map((item, i) => (
                            <CheckItem key={i} {...item} />
                        ))}
                    </div>
                </>
            )}
        </AccountingLayout>
    );
}
