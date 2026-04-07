import { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, BookOpen, TrendingUp, TrendingDown, DollarSign, Hash } from 'lucide-react';
import { useCustomer, useCustomerLedger } from '../hooks/useSales';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import SalesLayout from '../layout/SalesLayout';
import { useCurrency } from '../../../context/CurrencyContext';
import LoadingScreen from '../../../components/common/LoadingScreen';
import '../../accounting/styles/glassmorphism.css';

// Fetch all GL accounts for the dropdown
const useAllAccounts = () =>
    useQuery({
        queryKey: ['accounts-all-ledger'],
        queryFn: async () => {
            const { data } = await apiClient.get('/accounting/accounts/', {
                params: { is_active: true, page_size: 500 },
            });
            return data.results ?? data;
        },
        staleTime: 10 * 60 * 1000,
    });

// ── Type badges ──────────────────────────────────────────────────────────────
const TYPE_COLORS: Record<string, { bg: string; color: string }> = {
    Invoice:  { bg: 'rgba(36,113,163,0.12)',  color: '#2471a3' },
    Receipt:  { bg: 'rgba(16,185,129,0.12)',  color: '#10b981' },
    Payment:  { bg: 'rgba(16,185,129,0.12)',  color: '#10b981' },
    'Credit Note': { bg: 'rgba(251,191,36,0.12)', color: '#d97706' },
    'Debit Note':  { bg: 'rgba(239,68,68,0.12)',  color: '#ef4444' },
};

const typeBadge = (type: string) => {
    const style = TYPE_COLORS[type] ?? { bg: 'rgba(156,163,175,0.1)', color: '#6b7280' };
    return (
        <span style={{
            display: 'inline-block',
            padding: '0.2rem 0.6rem',
            borderRadius: '9999px',
            fontSize: 'var(--text-xs)',
            fontWeight: 700,
            background: style.bg,
            color: style.color,
            whiteSpace: 'nowrap',
        }}>
            {type}
        </span>
    );
};

// ── Status badges ────────────────────────────────────────────────────────────
const STATUS_COLORS: Record<string, { bg: string; color: string }> = {
    Sent:     { bg: 'rgba(36,113,163,0.12)',  color: '#2471a3' },
    Paid:     { bg: 'rgba(16,185,129,0.12)',  color: '#10b981' },
    Partial:  { bg: 'rgba(251,191,36,0.12)', color: '#d97706' },
    Overdue:  { bg: 'rgba(239,68,68,0.12)',  color: '#ef4444' },
    Draft:    { bg: 'rgba(156,163,175,0.1)', color: '#9ca3af' },
    Posted:   { bg: 'rgba(34,197,94,0.12)',  color: '#22c55e' },
};

const statusBadge = (status: string) => {
    const style = STATUS_COLORS[status] ?? { bg: 'rgba(156,163,175,0.1)', color: '#9ca3af' };
    return (
        <span style={{
            display: 'inline-block',
            padding: '0.2rem 0.6rem',
            borderRadius: '9999px',
            fontSize: 'var(--text-xs)',
            fontWeight: 700,
            background: style.bg,
            color: style.color,
            whiteSpace: 'nowrap',
        }}>
            {status || '—'}
        </span>
    );
};

// ── Summary card ─────────────────────────────────────────────────────────────
interface SummaryCardProps {
    label: string;
    value: string;
    icon: React.ReactNode;
    accentColor: string;
}

const SummaryCard = ({ label, value, icon, accentColor }: SummaryCardProps) => (
    <div className="glass-card" style={{ padding: '1.25rem 1.5rem', display: 'flex', alignItems: 'center', gap: '1rem', flex: '1 1 200px' }}>
        <div style={{
            width: 44, height: 44, borderRadius: '10px',
            background: `${accentColor}20`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
        }}>
            {icon}
        </div>
        <div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.25rem' }}>{label}</div>
            <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)' }}>{value}</div>
        </div>
    </div>
);

// ── Main component ────────────────────────────────────────────────────────────
const CustomerLedger = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const customerId = id ? parseInt(id, 10) : undefined;

    // Filters
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate]     = useState('');
    const [docNumber, setDocNumber] = useState('');
    const [account, setAccount]     = useState('');
    const [minAmount, setMinAmount] = useState('');
    const [maxAmount, setMaxAmount] = useState('');

    // Applied filter params (only send non-empty values)
    const ledgerParams = useMemo(() => {
        const p: Record<string, any> = { customer: customerId };
        if (startDate)  p.start_date       = startDate;
        if (endDate)    p.end_date         = endDate;
        if (docNumber)  p.document_number  = docNumber;
        if (account)    p.account          = account;
        if (minAmount)  p.min_amount       = minAmount;
        if (maxAmount)  p.max_amount       = maxAmount;
        return p;
    }, [customerId, startDate, endDate, docNumber, account, minAmount, maxAmount]);

    const { data: customer, isLoading: loadingCustomer } = useCustomer(customerId);
    const { data: ledgerData, isLoading: loadingLedger, isFetching } = useCustomerLedger(ledgerParams);
    const { data: accounts = [] } = useAllAccounts();

    const entries: any[] = ledgerData?.entries ?? [];
    const summary        = ledgerData?.summary ?? {};

    const inputStyle: React.CSSProperties = {
        padding: '0.5rem 0.75rem',
        borderRadius: '8px',
        border: '1px solid var(--color-border)',
        background: 'var(--color-surface)',
        color: 'var(--color-text)',
        fontSize: 'var(--text-sm)',
        width: '100%',
    };

    if (loadingCustomer) return <LoadingScreen message="Loading customer..." />;

    const customerName = customer?.name ?? `Customer #${id}`;

    return (
        <SalesLayout
            title={`${customerName} — Ledger`}
            description="Complete transaction history and running balance"
            icon={<BookOpen size={22} color="white" />}
            actions={
                <button
                    onClick={() => navigate(`/sales/customer/${id}`)}
                    style={{
                        display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                        padding: '0.5rem 1rem', borderRadius: '8px', border: '1px solid var(--color-border)',
                        background: 'var(--color-surface)', color: 'var(--color-text)',
                        cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 600,
                    }}
                >
                    <ArrowLeft size={15} />
                    Back to Customer
                </button>
            }
        >
            {/* ── Filter bar ─────────────────────────────────────────────── */}
            <div className="glass-card" style={{ padding: '1.25rem 1.5rem', marginBottom: '1.5rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '0.875rem', alignItems: 'end' }}>
                    {/* Date range */}
                    <div>
                        <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            Start Date
                        </label>
                        <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} style={inputStyle} />
                    </div>
                    <div>
                        <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            End Date
                        </label>
                        <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} style={inputStyle} />
                    </div>

                    {/* Document number */}
                    <div>
                        <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            Document #
                        </label>
                        <input type="text" placeholder="e.g. INV-001" value={docNumber} onChange={e => setDocNumber(e.target.value)} style={inputStyle} />
                    </div>

                    {/* GL Account */}
                    <div>
                        <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            GL Account
                        </label>
                        <select value={account} onChange={e => setAccount(e.target.value)} style={inputStyle}>
                            <option value="">All Accounts</option>
                            {accounts.map((acc: any) => (
                                <option key={acc.id} value={acc.id}>
                                    {acc.code} — {acc.name}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* Amount range */}
                    <div>
                        <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            Min Amount
                        </label>
                        <input type="number" placeholder="0.00" value={minAmount} onChange={e => setMinAmount(e.target.value)} style={inputStyle} />
                    </div>
                    <div>
                        <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            Max Amount
                        </label>
                        <input type="number" placeholder="0.00" value={maxAmount} onChange={e => setMaxAmount(e.target.value)} style={inputStyle} />
                    </div>

                    {/* Clear button */}
                    <div style={{ display: 'flex', alignItems: 'flex-end' }}>
                        <button
                            onClick={() => { setStartDate(''); setEndDate(''); setDocNumber(''); setAccount(''); setMinAmount(''); setMaxAmount(''); }}
                            style={{
                                width: '100%', padding: '0.5rem 0.75rem', borderRadius: '8px',
                                border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                                color: 'var(--color-text-muted)', cursor: 'pointer', fontSize: 'var(--text-sm)',
                                fontWeight: 600,
                            }}
                        >
                            Clear Filters
                        </button>
                    </div>
                </div>
            </div>

            {/* ── Summary cards ──────────────────────────────────────────── */}
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginBottom: '1.5rem' }}>
                <SummaryCard
                    label="Total Debits"
                    value={formatCurrency(parseFloat(summary.total_debit ?? '0'))}
                    icon={<TrendingUp size={20} color="#ef4444" />}
                    accentColor="#ef4444"
                />
                <SummaryCard
                    label="Total Credits"
                    value={formatCurrency(parseFloat(summary.total_credit ?? '0'))}
                    icon={<TrendingDown size={20} color="#10b981" />}
                    accentColor="#10b981"
                />
                <SummaryCard
                    label="Balance"
                    value={formatCurrency(parseFloat(summary.balance ?? '0'))}
                    icon={<DollarSign size={20} color="#2471a3" />}
                    accentColor="#2471a3"
                />
                <SummaryCard
                    label="Transactions"
                    value={String(summary.transaction_count ?? 0)}
                    icon={<Hash size={20} color="#d97706" />}
                    accentColor="#d97706"
                />
            </div>

            {/* ── Table ─────────────────────────────────────────────────── */}
            <div className="glass-card" style={{ padding: 0, overflow: 'hidden' }}>
                {(loadingLedger || isFetching) && (
                    <div style={{ padding: '0.5rem 1rem', background: 'rgba(36,113,163,0.08)', borderBottom: '1px solid var(--color-border)', fontSize: 'var(--text-xs)', color: '#2471a3', fontWeight: 600 }}>
                        Refreshing data...
                    </div>
                )}
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                {['Date', 'Type', 'Document #', 'Description', 'Debit', 'Credit', 'Running Balance', 'Status', 'Journal #'].map(h => (
                                    <th key={h} style={{
                                        padding: '0.875rem 1rem',
                                        fontSize: 'var(--text-xs)',
                                        fontWeight: 700,
                                        textTransform: 'uppercase',
                                        letterSpacing: '0.04em',
                                        color: 'var(--color-text-muted)',
                                        borderBottom: '2px solid var(--color-border)',
                                        whiteSpace: 'nowrap',
                                    }}>
                                        {h}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {entries.length === 0 ? (
                                <tr>
                                    <td colSpan={9} style={{ padding: '4rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <BookOpen size={48} style={{ margin: '0 auto 1rem', opacity: 0.2, display: 'block' }} />
                                        <p style={{ margin: 0, fontWeight: 500 }}>
                                            {loadingLedger ? 'Loading ledger entries...' : 'No transactions found for the selected filters.'}
                                        </p>
                                    </td>
                                </tr>
                            ) : (
                                entries.map((entry: any, idx: number) => (
                                    <tr
                                        key={entry.id ?? idx}
                                        style={{ borderBottom: '1px solid var(--color-border)', transition: 'background 0.12s' }}
                                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-surface)')}
                                        onMouseLeave={e => (e.currentTarget.style.background = '')}
                                    >
                                        {/* Date */}
                                        <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)', whiteSpace: 'nowrap', color: 'var(--color-text-muted)' }}>
                                            {entry.date}
                                        </td>

                                        {/* Type */}
                                        <td style={{ padding: '0.75rem 1rem', whiteSpace: 'nowrap' }}>
                                            {typeBadge(entry.type)}
                                        </td>

                                        {/* Document # */}
                                        <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-primary)', whiteSpace: 'nowrap' }}>
                                            {entry.document_number || '—'}
                                        </td>

                                        {/* Description */}
                                        <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {entry.description || '—'}
                                        </td>

                                        {/* Debit */}
                                        <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)', fontWeight: 600, whiteSpace: 'nowrap', color: parseFloat(entry.debit || '0') > 0 ? '#ef4444' : 'var(--color-text-muted)' }}>
                                            {parseFloat(entry.debit || '0') > 0 ? formatCurrency(parseFloat(entry.debit)) : '—'}
                                        </td>

                                        {/* Credit */}
                                        <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)', fontWeight: 600, whiteSpace: 'nowrap', color: parseFloat(entry.credit || '0') > 0 ? '#10b981' : 'var(--color-text-muted)' }}>
                                            {parseFloat(entry.credit || '0') > 0 ? formatCurrency(parseFloat(entry.credit)) : '—'}
                                        </td>

                                        {/* Running Balance */}
                                        <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)', fontWeight: 700, whiteSpace: 'nowrap', color: parseFloat(entry.running_balance || '0') >= 0 ? 'var(--color-text)' : '#ef4444' }}>
                                            {formatCurrency(parseFloat(entry.running_balance || '0'))}
                                        </td>

                                        {/* Status */}
                                        <td style={{ padding: '0.75rem 1rem', whiteSpace: 'nowrap' }}>
                                            {statusBadge(entry.status)}
                                        </td>

                                        {/* Journal # */}
                                        <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-xs)', fontFamily: 'monospace', fontWeight: 600, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                                            {entry.journal_number || '—'}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </SalesLayout>
    );
};

export default CustomerLedger;
