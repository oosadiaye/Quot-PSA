import { useState, useMemo, useRef, useCallback } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { BarChart3, Filter, Download, Search, ChevronUp, ChevronDown, ChevronsUpDown, X, Loader2 } from 'lucide-react';
import { useGLBalances } from '../hooks/useAccountingEnhancements';
import { useJournalDetail } from '../hooks/useJournal';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import StatusBadge from '../components/shared/StatusBadge';
import '../styles/glassmorphism.css';

type SortField = 'account_code' | 'account_name' | 'fund_code' | 'reference' | 'journal_number' | 'debit' | 'credit' | 'net';
type SortDir = 'asc' | 'desc';

export default function GLReports() {
    const { formatCurrency } = useCurrency();
    const [fiscalYear, setFiscalYear] = useState(new Date().getFullYear());
    const [fiscalPeriod, setFiscalPeriod] = useState(new Date().getMonth() + 1);

    // Filter states
    const [glFilter, setGlFilter] = useState('');
    const [referenceFilter, setReferenceFilter] = useState('');
    const [journalFilter, setJournalFilter] = useState('');

    // Sort state
    const [sortField, setSortField] = useState<SortField | null>(null);
    const [sortDir, setSortDir] = useState<SortDir>('asc');

    // Journal detail modal state
    const [selectedJournalId, setSelectedJournalId] = useState<number | null>(null);
    const { data: journalDetail, isLoading: journalLoading } = useJournalDetail(selectedJournalId);

    const { data: balances, isLoading } = useGLBalances({
        fiscal_year: fiscalYear,
        fiscal_period: fiscalPeriod
    });

    // Filter + sort the data
    const filteredBalances = useMemo(() => {
        if (!balances) return [];
        let result = [...balances];

        // GL account filter (matches code or name)
        if (glFilter.trim()) {
            const q = glFilter.trim().toLowerCase();
            result = result.filter((b: any) =>
                (b.account_code || '').toLowerCase().includes(q) ||
                (b.account_name || '').toLowerCase().includes(q)
            );
        }

        // Reference filter
        if (referenceFilter.trim()) {
            const q = referenceFilter.trim().toLowerCase();
            result = result.filter((b: any) =>
                (b.reference || '').toLowerCase().includes(q)
            );
        }

        // Journal number filter
        if (journalFilter.trim()) {
            const q = journalFilter.trim().toLowerCase();
            result = result.filter((b: any) =>
                (b.journal_number || '').toLowerCase().includes(q)
            );
        }

        // Sort
        if (sortField) {
            result.sort((a: any, b: any) => {
                let aVal: any, bVal: any;
                switch (sortField) {
                    case 'account_code':
                        aVal = (a.account_code || '').toLowerCase();
                        bVal = (b.account_code || '').toLowerCase();
                        break;
                    case 'account_name':
                        aVal = (a.account_name || '').toLowerCase();
                        bVal = (b.account_name || '').toLowerCase();
                        break;
                    case 'fund_code':
                        aVal = (a.fund_code || '').toLowerCase();
                        bVal = (b.fund_code || '').toLowerCase();
                        break;
                    case 'reference':
                        aVal = (a.reference || '').toLowerCase();
                        bVal = (b.reference || '').toLowerCase();
                        break;
                    case 'journal_number':
                        aVal = (a.journal_number || '').toLowerCase();
                        bVal = (b.journal_number || '').toLowerCase();
                        break;
                    case 'debit':
                        aVal = parseFloat(a.debit_balance) || 0;
                        bVal = parseFloat(b.debit_balance) || 0;
                        break;
                    case 'credit':
                        aVal = parseFloat(a.credit_balance) || 0;
                        bVal = parseFloat(b.credit_balance) || 0;
                        break;
                    case 'net':
                        aVal = (parseFloat(a.debit_balance) || 0) - (parseFloat(a.credit_balance) || 0);
                        bVal = (parseFloat(b.debit_balance) || 0) - (parseFloat(b.credit_balance) || 0);
                        break;
                    default:
                        return 0;
                }
                if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
                if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
                return 0;
            });
        }

        return result;
    }, [balances, glFilter, referenceFilter, journalFilter, sortField, sortDir]);

    const totalDebits = filteredBalances.reduce((sum: number, bal: any) => sum + parseFloat(bal.debit_balance || '0'), 0) || 0;
    const totalCredits = filteredBalances.reduce((sum: number, bal: any) => sum + parseFloat(bal.credit_balance || '0'), 0) || 0;
    const netBalance = totalDebits - totalCredits;

    // Virtual scrolling for large GL balance tables
    const ROW_HEIGHT = 48;
    const VIRTUALIZE_THRESHOLD = 100;
    const shouldVirtualize = filteredBalances.length > VIRTUALIZE_THRESHOLD;
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const virtualizer = useVirtualizer({
        count: filteredBalances.length,
        getScrollElement: () => scrollContainerRef.current,
        estimateSize: useCallback(() => ROW_HEIGHT, []),
        overscan: 15,
        enabled: shouldVirtualize,
    });

    const handleSort = (field: SortField) => {
        if (sortField === field) {
            setSortDir(prev => prev === 'asc' ? 'desc' : 'asc');
        } else {
            setSortField(field);
            setSortDir('asc');
        }
    };

    const SortIcon = ({ field }: { field: SortField }) => {
        if (sortField !== field) return <ChevronsUpDown size={14} style={{ opacity: 0.3 }} />;
        return sortDir === 'asc' ? <ChevronUp size={14} /> : <ChevronDown size={14} />;
    };

    const thStyle = (align: 'left' | 'right' = 'left'): React.CSSProperties => ({
        padding: '1rem 1.5rem',
        fontSize: 'var(--text-xs)',
        fontWeight: 600,
        textTransform: 'uppercase',
        color: 'var(--color-text-muted)',
        cursor: 'pointer',
        userSelect: 'none',
        textAlign: align,
        whiteSpace: 'nowrap',
    });

    // Compute journal detail totals
    const journalTotalDebit = journalDetail?.lines?.reduce((sum: number, l: any) => sum + parseFloat(l.debit || '0'), 0) || 0;
    const journalTotalCredit = journalDetail?.lines?.reduce((sum: number, l: any) => sum + parseFloat(l.credit || '0'), 0) || 0;

    if (isLoading) {
        return <LoadingScreen message="Loading trial balance..." />;
    }

    return (
        <AccountingLayout>
            <div>
                <PageHeader
                    title="General Ledger Reports"
                    subtitle="Trial balance and financial reporting"
                    icon={<BarChart3 size={22} />}
                    actions={
                        <button className="btn btn-primary" onClick={() => {
                            if (!filteredBalances || filteredBalances.length === 0) return;
                            const csv = [
                                ['Account Code', 'Account Name', 'Fund', 'Reference', 'Journal #', 'Debit', 'Credit', 'Net Balance'],
                                ...filteredBalances.map((bal: any) => {
                                    const debit = parseFloat(bal.debit_balance) || 0;
                                    const credit = parseFloat(bal.credit_balance) || 0;
                                    const net = debit - credit;
                                    return [
                                        bal.account_code || '',
                                        `"${(bal.account_name || '').replace(/"/g, '""')}"`,
                                        bal.fund_code || '',
                                        bal.reference || '',
                                        bal.journal_number || '',
                                        debit.toFixed(2),
                                        credit.toFixed(2),
                                        net.toFixed(2),
                                    ];
                                })
                            ].map(row => row.join(',')).join('\n');
                            const blob = new Blob([csv], { type: 'text/csv' });
                            const url = window.URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `gl_report_${fiscalYear}_P${fiscalPeriod}.csv`;
                            a.click();
                            window.URL.revokeObjectURL(url);
                        }}>
                            <Download size={18} /> Export Report
                        </button>
                    }
                />

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Total Debits</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>{formatCurrency(totalDebits)}</p>
                    </div>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Total Credits</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>{formatCurrency(totalCredits)}</p>
                    </div>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Net Balance</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: netBalance >= 0 ? 'var(--color-success)' : 'var(--color-error)' }}>{formatCurrency(Math.abs(netBalance))}</p>
                    </div>
                </div>

                {/* Filters */}
                <div className="card" style={{ padding: '1.25rem', marginBottom: '1.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', flexWrap: 'wrap' }}>
                        <Filter size={18} style={{ color: 'var(--color-text-muted)' }} />
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <label style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-text-muted)' }}>Fiscal Year:</label>
                            <select value={fiscalYear} onChange={(e) => setFiscalYear(Number(e.target.value))} style={{ minWidth: '120px' }}>
                                {[2023, 2024, 2025, 2026].map(year => (
                                    <option key={year} value={year}>{year}</option>
                                ))}
                            </select>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <label style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-text-muted)' }}>Period:</label>
                            <select value={fiscalPeriod} onChange={(e) => setFiscalPeriod(Number(e.target.value))} style={{ minWidth: '140px' }}>
                                {Array.from({ length: 12 }, (_, i) => i + 1).map(month => (
                                    <option key={month} value={month}>
                                        {new Date(2024, month - 1).toLocaleString('default', { month: 'long' })}
                                    </option>
                                ))}
                            </select>
                        </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)' }}>
                        <Search size={18} style={{ color: 'var(--color-text-muted)' }} />
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: '1', minWidth: '180px' }}>
                            <label style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>GL Account:</label>
                            <input
                                type="text"
                                placeholder="Code or name..."
                                value={glFilter}
                                onChange={(e) => setGlFilter(e.target.value)}
                                style={{ flex: 1, minWidth: '120px', padding: '0.375rem 0.75rem', border: '1px solid var(--color-border)', borderRadius: '6px', fontSize: 'var(--text-sm)', background: 'var(--color-surface)', color: 'var(--color-text)' }}
                            />
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: '1', minWidth: '160px' }}>
                            <label style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>Reference:</label>
                            <input
                                type="text"
                                placeholder="Search reference..."
                                value={referenceFilter}
                                onChange={(e) => setReferenceFilter(e.target.value)}
                                style={{ flex: 1, minWidth: '120px', padding: '0.375rem 0.75rem', border: '1px solid var(--color-border)', borderRadius: '6px', fontSize: 'var(--text-sm)', background: 'var(--color-surface)', color: 'var(--color-text)' }}
                            />
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: '1', minWidth: '160px' }}>
                            <label style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>Journal #:</label>
                            <input
                                type="text"
                                placeholder="Search journal..."
                                value={journalFilter}
                                onChange={(e) => setJournalFilter(e.target.value)}
                                style={{ flex: 1, minWidth: '120px', padding: '0.375rem 0.75rem', border: '1px solid var(--color-border)', borderRadius: '6px', fontSize: 'var(--text-sm)', background: 'var(--color-surface)', color: 'var(--color-text)' }}
                            />
                        </div>
                        {(glFilter || referenceFilter || journalFilter) && (
                            <button
                                onClick={() => { setGlFilter(''); setReferenceFilter(''); setJournalFilter(''); }}
                                style={{ padding: '0.375rem 0.75rem', fontSize: 'var(--text-sm)', border: '1px solid var(--color-border)', borderRadius: '6px', background: 'transparent', color: 'var(--color-text-muted)', cursor: 'pointer', whiteSpace: 'nowrap' }}
                            >
                                Clear filters
                            </button>
                        )}
                    </div>
                </div>

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    {/* Virtualized scroll container — only activates for 100+ rows */}
                    <div
                        ref={scrollContainerRef}
                        style={{
                            overflowX: 'auto',
                            ...(shouldVirtualize ? { maxHeight: '70vh', overflowY: 'auto' } : {}),
                        }}
                    >
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead style={shouldVirtualize ? { position: 'sticky', top: 0, zIndex: 2 } : undefined}>
                                <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                    <th style={thStyle()} onClick={() => handleSort('account_code')}>
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem' }}>
                                            Account Code <SortIcon field="account_code" />
                                        </span>
                                    </th>
                                    <th style={thStyle()} onClick={() => handleSort('account_name')}>
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem' }}>
                                            Account Name <SortIcon field="account_name" />
                                        </span>
                                    </th>
                                    <th style={thStyle()} onClick={() => handleSort('fund_code')}>
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem' }}>
                                            Fund <SortIcon field="fund_code" />
                                        </span>
                                    </th>
                                    <th style={thStyle()} onClick={() => handleSort('reference')}>
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem' }}>
                                            Reference <SortIcon field="reference" />
                                        </span>
                                    </th>
                                    <th style={thStyle()} onClick={() => handleSort('journal_number')}>
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem' }}>
                                            Journal # <SortIcon field="journal_number" />
                                        </span>
                                    </th>
                                    <th style={thStyle('right')} onClick={() => handleSort('debit')}>
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem', justifyContent: 'flex-end' }}>
                                            Debit <SortIcon field="debit" />
                                        </span>
                                    </th>
                                    <th style={thStyle('right')} onClick={() => handleSort('credit')}>
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem', justifyContent: 'flex-end' }}>
                                            Credit <SortIcon field="credit" />
                                        </span>
                                    </th>
                                    <th style={thStyle('right')} onClick={() => handleSort('net')}>
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem', justifyContent: 'flex-end' }}>
                                            Net Balance <SortIcon field="net" />
                                        </span>
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {shouldVirtualize ? (
                                    <>
                                        {/* Top spacer row — pushes visible rows to correct scroll position */}
                                        {virtualizer.getVirtualItems().length > 0 && (
                                            <tr aria-hidden="true">
                                                <td colSpan={8} style={{ height: `${virtualizer.getVirtualItems()[0].start}px`, padding: 0, border: 'none' }} />
                                            </tr>
                                        )}
                                        {virtualizer.getVirtualItems().map(virtualRow => {
                                            const balance = filteredBalances[virtualRow.index];
                                            const debit = parseFloat(balance.debit_balance);
                                            const credit = parseFloat(balance.credit_balance);
                                            const net = debit - credit;
                                            return (
                                                <tr key={balance.id} data-index={virtualRow.index} ref={virtualizer.measureElement} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                                    <td style={{ padding: '1rem 1.5rem', fontWeight: 600, color: 'var(--color-primary)', fontFamily: 'monospace' }}>
                                                        {balance.account_code}
                                                    </td>
                                                    <td style={{ padding: '1rem 1.5rem', fontWeight: 500 }}>{balance.account_name}</td>
                                                    <td style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{balance.fund_code}</td>
                                                    <td style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{balance.reference || '-'}</td>
                                                    <td style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-sm)', fontFamily: 'monospace' }}>
                                                        {balance.journal_number ? (
                                                            <button
                                                                onClick={() => setSelectedJournalId(Number(balance.journal_number))}
                                                                style={{
                                                                    background: 'none',
                                                                    border: 'none',
                                                                    color: 'var(--color-primary)',
                                                                    fontFamily: 'monospace',
                                                                    fontSize: 'var(--text-sm)',
                                                                    fontWeight: 600,
                                                                    cursor: 'pointer',
                                                                    textDecoration: 'underline',
                                                                    padding: 0,
                                                                }}
                                                            >
                                                                {balance.journal_number}
                                                            </button>
                                                        ) : '-'}
                                                    </td>
                                                    <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' }}>
                                                        {debit > 0 ? formatCurrency(debit) : '-'}
                                                    </td>
                                                    <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' }}>
                                                        {credit > 0 ? formatCurrency(credit) : '-'}
                                                    </td>
                                                    <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace', color: net >= 0 ? 'var(--color-success)' : 'var(--color-error)' }}>
                                                        {formatCurrency(Math.abs(net))}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                        {/* Bottom spacer row — maintains total scroll height */}
                                        {virtualizer.getVirtualItems().length > 0 && (
                                            <tr aria-hidden="true">
                                                <td colSpan={8} style={{ height: `${virtualizer.getTotalSize() - (virtualizer.getVirtualItems().at(-1)?.end ?? 0)}px`, padding: 0, border: 'none' }} />
                                            </tr>
                                        )}
                                    </>
                                ) : (
                                    filteredBalances.map((balance: any) => {
                                        const debit = parseFloat(balance.debit_balance);
                                        const credit = parseFloat(balance.credit_balance);
                                        const net = debit - credit;
                                        return (
                                            <tr key={balance.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                                <td style={{ padding: '1rem 1.5rem', fontWeight: 600, color: 'var(--color-primary)', fontFamily: 'monospace' }}>
                                                    {balance.account_code}
                                                </td>
                                                <td style={{ padding: '1rem 1.5rem', fontWeight: 500 }}>{balance.account_name}</td>
                                                <td style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{balance.fund_code}</td>
                                                <td style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{balance.reference || '-'}</td>
                                                <td style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-sm)', fontFamily: 'monospace' }}>
                                                    {balance.journal_number ? (
                                                        <button
                                                            onClick={() => setSelectedJournalId(Number(balance.journal_number))}
                                                            style={{
                                                                background: 'none',
                                                                border: 'none',
                                                                color: 'var(--color-primary)',
                                                                fontFamily: 'monospace',
                                                                fontSize: 'var(--text-sm)',
                                                                fontWeight: 600,
                                                                cursor: 'pointer',
                                                                textDecoration: 'underline',
                                                                padding: 0,
                                                            }}
                                                        >
                                                            {balance.journal_number}
                                                        </button>
                                                    ) : '-'}
                                                </td>
                                                <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' }}>
                                                    {debit > 0 ? formatCurrency(debit) : '-'}
                                                </td>
                                                <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' }}>
                                                    {credit > 0 ? formatCurrency(credit) : '-'}
                                                </td>
                                                <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace', color: net >= 0 ? 'var(--color-success)' : 'var(--color-error)' }}>
                                                    {formatCurrency(Math.abs(net))}
                                                </td>
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                            {filteredBalances.length > 0 && (
                                <tfoot style={shouldVirtualize ? { position: 'sticky', bottom: 0, zIndex: 2 } : undefined}>
                                    <tr style={{ background: 'var(--color-surface)', fontWeight: 700 }}>
                                        <td colSpan={5} style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-sm)', textTransform: 'uppercase' }}>
                                            Totals{shouldVirtualize && ` (${filteredBalances.length} rows)`}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontFamily: 'monospace' }}>{formatCurrency(totalDebits)}</td>
                                        <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontFamily: 'monospace' }}>{formatCurrency(totalCredits)}</td>
                                        <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontFamily: 'monospace', color: netBalance >= 0 ? 'var(--color-success)' : 'var(--color-error)' }}>
                                            {formatCurrency(Math.abs(netBalance))}
                                        </td>
                                    </tr>
                                </tfoot>
                            )}
                        </table>
                    </div>
                </div>

                {filteredBalances.length === 0 && (
                    <div style={{ textAlign: 'center', padding: '5rem 1.25rem', color: 'var(--color-text-muted)' }}>
                        <BarChart3 size={64} style={{ margin: '0 auto 1rem', opacity: 0.3 }} />
                        <p style={{ fontSize: 'var(--text-lg)', fontWeight: 500 }}>
                            {(glFilter || referenceFilter || journalFilter)
                                ? 'No results match your filters'
                                : 'No GL balances found'}
                        </p>
                        {(glFilter || referenceFilter || journalFilter) && (
                            <button
                                onClick={() => { setGlFilter(''); setReferenceFilter(''); setJournalFilter(''); }}
                                style={{ marginTop: '0.75rem', padding: '0.5rem 1rem', border: '1px solid var(--color-border)', borderRadius: '6px', background: 'transparent', color: 'var(--color-primary)', cursor: 'pointer' }}
                            >
                                Clear all filters
                            </button>
                        )}
                    </div>
                )}

                {/* Journal Detail Modal */}
                {selectedJournalId !== null && (
                    <div
                        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
                        onClick={() => setSelectedJournalId(null)}
                    >
                        <div
                            className="card"
                            style={{ width: '100%', maxWidth: '800px', maxHeight: '90vh', overflow: 'auto', padding: '2rem' }}
                            onClick={e => e.stopPropagation()}
                        >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                                <h2 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 700 }}>
                                    Journal Entry #{selectedJournalId}
                                </h2>
                                <button
                                    onClick={() => setSelectedJournalId(null)}
                                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            {journalLoading ? (
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '3rem', gap: '0.75rem', color: 'var(--color-text-muted)' }}>
                                    <Loader2 size={20} style={{ animation: 'spin 1s linear infinite' }} />
                                    Loading journal details...
                                </div>
                            ) : journalDetail ? (
                                <>
                                    {/* Journal Header Info */}
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem', marginBottom: '1.5rem', padding: '1rem', background: 'var(--color-background)', borderRadius: '8px' }}>
                                        <div>
                                            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.25rem' }}>Reference #</p>
                                            <p style={{ fontWeight: 600, fontFamily: 'monospace' }}>{journalDetail.reference_number || '-'}</p>
                                        </div>
                                        <div>
                                            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.25rem' }}>Posting Date</p>
                                            <p style={{ fontWeight: 600 }}>{journalDetail.posting_date ? new Date(journalDetail.posting_date).toLocaleDateString() : '-'}</p>
                                        </div>
                                        <div>
                                            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.25rem' }}>Status</p>
                                            <StatusBadge status={journalDetail.status} />
                                        </div>
                                        {journalDetail.fund_name && (
                                            <div>
                                                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.25rem' }}>Fund</p>
                                                <p style={{ fontWeight: 600 }}>{journalDetail.fund_name}</p>
                                            </div>
                                        )}
                                    </div>

                                    {journalDetail.description && (
                                        <div style={{ marginBottom: '1.5rem', padding: '0.75rem 1rem', background: 'var(--color-background)', borderRadius: '8px', borderLeft: '3px solid var(--color-primary)' }}>
                                            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.25rem' }}>Description</p>
                                            <p style={{ fontSize: 'var(--text-sm)' }}>{journalDetail.description}</p>
                                        </div>
                                    )}

                                    {/* Journal Lines Table */}
                                    <div style={{ overflow: 'hidden', borderRadius: '8px', border: '1px solid var(--color-border)' }}>
                                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                            <thead>
                                                <tr style={{ background: 'var(--color-surface)' }}>
                                                    <th style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', textAlign: 'left' }}>Account Code</th>
                                                    <th style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', textAlign: 'left' }}>Account Name</th>
                                                    <th style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', textAlign: 'right' }}>Debit</th>
                                                    <th style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', textAlign: 'right' }}>Credit</th>
                                                    <th style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', textAlign: 'left' }}>Memo</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {journalDetail.lines?.map((line: any) => {
                                                    const lineDebit = parseFloat(line.debit || '0');
                                                    const lineCredit = parseFloat(line.credit || '0');
                                                    return (
                                                        <tr key={line.id} style={{ borderTop: '1px solid var(--color-border)' }}>
                                                            <td style={{ padding: '0.75rem 1rem', fontWeight: 600, color: 'var(--color-primary)', fontFamily: 'monospace', fontSize: 'var(--text-sm)' }}>
                                                                {line.account_code}
                                                            </td>
                                                            <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>
                                                                {line.account_name}
                                                            </td>
                                                            <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontFamily: 'monospace', fontWeight: 500, fontSize: 'var(--text-sm)' }}>
                                                                {lineDebit > 0 ? formatCurrency(lineDebit) : '-'}
                                                            </td>
                                                            <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontFamily: 'monospace', fontWeight: 500, fontSize: 'var(--text-sm)' }}>
                                                                {lineCredit > 0 ? formatCurrency(lineCredit) : '-'}
                                                            </td>
                                                            <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                                                {line.memo || '-'}
                                                            </td>
                                                        </tr>
                                                    );
                                                })}
                                            </tbody>
                                            <tfoot>
                                                <tr style={{ borderTop: '2px solid var(--color-border)', background: 'var(--color-surface)', fontWeight: 700 }}>
                                                    <td colSpan={2} style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)', textTransform: 'uppercase' }}>Totals</td>
                                                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontFamily: 'monospace', fontSize: 'var(--text-sm)' }}>
                                                        {formatCurrency(journalTotalDebit)}
                                                    </td>
                                                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontFamily: 'monospace', fontSize: 'var(--text-sm)' }}>
                                                        {formatCurrency(journalTotalCredit)}
                                                    </td>
                                                    <td></td>
                                                </tr>
                                            </tfoot>
                                        </table>
                                    </div>

                                    {journalDetail.lines?.length === 0 && (
                                        <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-muted)' }}>
                                            No journal lines found for this entry.
                                        </div>
                                    )}
                                </>
                            ) : (
                                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-muted)' }}>
                                    Journal entry not found.
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </AccountingLayout>
    );
}
