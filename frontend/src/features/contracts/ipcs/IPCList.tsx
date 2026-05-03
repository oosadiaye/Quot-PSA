import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Scale } from 'lucide-react';
import PageHeader from '../../../components/PageHeader';
import { ListPageShell, FilterBar, SectionCard, StatusBadge, ThemedButton } from '../../../components/layout';
import { ResponsiveTable } from '../../../components/ResponsiveTable';
import type { Column } from '../../../components/ResponsiveTable';
import { useIPCs, type IPCSummary } from '../hooks/useIPCs';
import { useCurrency } from '../../../context/CurrencyContext';

const STATUS_OPTIONS = [
    'SUBMITTED',
    'CERTIFIER_REVIEWED',
    'APPROVED',
    'VOUCHER_RAISED',
    'PAID',
    'REJECTED',
];

const IPCList = () => {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const [searchInput, setSearchInput] = useState('');
    const [search, setSearch] = useState('');
    const [status, setStatus] = useState<string | undefined>();

    const { data, isLoading } = useIPCs({ search, status });
    const rows = data?.results ?? [];

    const columns: Column<IPCSummary>[] = [
        {
            key: 'ipc_number',
            header: 'IPC #',
            mobilePrimary: true,
            render: (r) => (
                <button
                    onClick={() => navigate(`/contracts/ipcs/${r.id}`)}
                    style={{
                        background: 'none',
                        border: 'none',
                        padding: 0,
                        fontWeight: 600,
                        color: '#242a88',
                        cursor: 'pointer',
                        fontSize: 'inherit',
                        fontFamily: 'inherit',
                    }}
                >
                    {r.ipc_number}
                </button>
            ),
        },
        { key: 'contract_reference', header: 'Contract', mobilePrimary: true },
        { key: 'posting_date', header: 'Posted' },
        {
            key: 'gross',
            header: 'Gross',
            align: 'right',
            render: (r) => (
                <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                    {formatCurrency(Number(r.this_certificate_gross || 0))}
                </span>
            ),
        },
        {
            key: 'status',
            header: 'Status',
            render: (r) => <StatusBadge status={r.status}>{r.status}</StatusBadge>,
        },
    ];

    return (
        <ListPageShell>
            <PageHeader
                title="Interim Payment Certificates"
                subtitle="Workflow queue across all contracts"
                icon={<Scale size={22} style={{ color: 'rgba(255,255,255,0.85)' }} />}
                backButton={false}
            />

            <SectionCard flush>
                <div style={{ padding: 16, borderBottom: '1px solid #eef2f7' }}>
                    <FilterBar marginBottom={0}>
                        <div style={{ position: 'relative', flex: 1, maxWidth: 360, minWidth: 0 }}>
                            <Search
                                size={16}
                                style={{
                                    position: 'absolute',
                                    left: 12,
                                    top: '50%',
                                    transform: 'translateY(-50%)',
                                    color: '#94a3b8',
                                    pointerEvents: 'none',
                                }}
                            />
                            <input
                                type="search"
                                placeholder="Search IPC number"
                                value={searchInput}
                                onChange={(e) => setSearchInput(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') setSearch(searchInput);
                                }}
                                style={{
                                    width: '100%',
                                    height: 40,
                                    padding: '0 12px 0 36px',
                                    borderRadius: 10,
                                    border: '1px solid #e2e8f0',
                                    background: '#f8fafc',
                                    fontSize: 14,
                                    fontFamily: 'inherit',
                                    outline: 'none',
                                }}
                            />
                        </div>
                        <select
                            value={status ?? ''}
                            onChange={(e) => setStatus(e.target.value || undefined)}
                            style={{
                                height: 40,
                                padding: '0 12px',
                                borderRadius: 10,
                                border: '1px solid #e2e8f0',
                                background: '#f8fafc',
                                fontSize: 14,
                                fontFamily: 'inherit',
                                outline: 'none',
                                minWidth: 200,
                                color: status ? '#0b1320' : '#94a3b8',
                            }}
                        >
                            <option value="">All statuses</option>
                            {STATUS_OPTIONS.map((s) => (
                                <option key={s} value={s}>
                                    {s}
                                </option>
                            ))}
                        </select>
                        {(searchInput || status) && (
                            <ThemedButton
                                size="sm"
                                variant="ghost"
                                onClick={() => {
                                    setSearchInput('');
                                    setSearch('');
                                    setStatus(undefined);
                                }}
                            >
                                Clear
                            </ThemedButton>
                        )}
                    </FilterBar>
                </div>

                {isLoading ? (
                    <div style={{ padding: 48, textAlign: 'center', color: '#64748b' }}>
                        Loading IPCs…
                    </div>
                ) : (
                    <ResponsiveTable
                        data={rows}
                        columns={columns}
                        keyField="id"
                        emptyState="No IPCs match the current filters."
                    />
                )}

                {data && data.count > 0 && (
                    <div
                        style={{
                            padding: '12px 16px',
                            borderTop: '1px solid #eef2f7',
                            fontSize: 13,
                            color: '#64748b',
                        }}
                    >
                        Showing <strong style={{ color: '#0b1320' }}>{rows.length}</strong> of{' '}
                        <strong style={{ color: '#0b1320' }}>{data.count}</strong> IPCs
                    </div>
                )}
            </SectionCard>
        </ListPageShell>
    );
};

export default IPCList;
