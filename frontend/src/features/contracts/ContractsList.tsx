import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { App as AntApp } from 'antd';
import { Plus, Search, FileText, Trash2, ExternalLink } from 'lucide-react';
import PageHeader from '../../components/PageHeader';
import { ListPageShell, FilterBar, SectionCard, ThemedButton, StatusBadge } from '../../components/layout';
import { ResponsiveTable } from '../../components/ResponsiveTable';
import type { Column } from '../../components/ResponsiveTable';
import { useContracts, useDeleteContract, type ContractSummary } from './hooks/useContracts';
import { formatServiceError } from './utils/errors';
import { useCurrency } from '../../context/CurrencyContext';

const ContractsList = () => {
    const navigate = useNavigate();
    const { message } = AntApp.useApp();
    const { formatCurrency } = useCurrency();
    const [search, setSearch] = useState('');
    const [searchInput, setSearchInput] = useState('');

    const { data, isLoading } = useContracts({ search });
    const deleteMut = useDeleteContract();

    const rows = data?.results ?? [];

    const utilizationTone = (pct?: number): 'danger' | 'warning' | 'success' | 'neutral' => {
        if (pct == null) return 'neutral';
        if (pct > 85) return 'danger';
        if (pct > 70) return 'warning';
        return 'success';
    };

    const columns: Column<ContractSummary>[] = [
        {
            key: 'reference',
            header: 'Reference',
            mobilePrimary: true,
            render: (r) => (
                <button
                    onClick={() => navigate(`/contracts/${r.id}`)}
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
                    {r.reference}
                </button>
            ),
        },
        {
            key: 'title',
            header: 'Title',
            mobilePrimary: true,
            render: (r) => (
                <span style={{ color: '#0b1320' }}>{r.title}</span>
            ),
        },
        { key: 'vendor_name', header: 'Vendor' },
        {
            key: 'contract_ceiling',
            header: 'Ceiling',
            align: 'right',
            render: (r) => (
                <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                    {formatCurrency(Number(r.contract_ceiling || 0))}
                </span>
            ),
        },
        {
            key: 'util',
            header: 'Utilization',
            align: 'right',
            render: (r) => (
                <StatusBadge tone={utilizationTone(r.ceiling_utilization_pct)}>
                    {r.ceiling_utilization_pct == null
                        ? '—'
                        : `${Number(r.ceiling_utilization_pct).toFixed(1)}%`}
                </StatusBadge>
            ),
        },
        {
            key: 'status',
            header: 'Status',
            render: (r) => <StatusBadge status={r.status}>{r.status}</StatusBadge>,
        },
        {
            key: 'actions',
            header: '',
            align: 'right',
            render: (r) => (
                <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                    <ThemedButton
                        size="sm"
                        variant="secondary"
                        icon={<ExternalLink size={14} />}
                        onClick={() => navigate(`/contracts/${r.id}`)}
                    >
                        Open
                    </ThemedButton>
                    <ThemedButton
                        size="sm"
                        variant="danger"
                        icon={<Trash2 size={14} />}
                        onClick={async () => {
                            try {
                                await deleteMut.mutateAsync(r.id);
                                message.success('Contract deleted');
                            } catch (e) {
                                message.error(formatServiceError(e, 'Delete failed'));
                            }
                        }}
                    >
                        Delete
                    </ThemedButton>
                </div>
            ),
        },
    ];

    return (
        <ListPageShell>
            <PageHeader
                title="Contracts"
                subtitle="All registered contract awards"
                icon={<FileText size={22} style={{ color: 'rgba(255,255,255,0.85)' }} />}
                backButton={false}
                actions={
                    <ThemedButton
                        variant="primary"
                        icon={<Plus size={16} />}
                        onClick={() => navigate('/contracts/new')}
                    >
                        New Contract
                    </ThemedButton>
                }
            />

            <SectionCard flush>
                <div style={{ padding: 16, borderBottom: '1px solid #eef2f7' }}>
                    <FilterBar marginBottom={0}>
                        <div style={{ position: 'relative', flex: 1, maxWidth: 420, minWidth: 0 }}>
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
                                placeholder="Search reference or title"
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
                        {searchInput && (
                            <ThemedButton
                                size="sm"
                                variant="ghost"
                                onClick={() => {
                                    setSearchInput('');
                                    setSearch('');
                                }}
                            >
                                Clear
                            </ThemedButton>
                        )}
                    </FilterBar>
                </div>

                <div style={{ padding: 0 }}>
                    {isLoading ? (
                        <div style={{ padding: 48, textAlign: 'center', color: '#64748b' }}>
                            Loading contracts…
                        </div>
                    ) : (
                        <ResponsiveTable
                            data={rows}
                            columns={columns}
                            keyField="id"
                            emptyState={
                                <div style={{ padding: 16 }}>
                                    <div style={{ fontWeight: 600, color: '#0b1320', marginBottom: 4 }}>
                                        No contracts yet
                                    </div>
                                    <div style={{ fontSize: 13, color: '#64748b', marginBottom: 16 }}>
                                        Register your first award to start tracking ceiling utilization.
                                    </div>
                                    <ThemedButton
                                        variant="primary"
                                        icon={<Plus size={16} />}
                                        onClick={() => navigate('/contracts/new')}
                                    >
                                        New Contract
                                    </ThemedButton>
                                </div>
                            }
                        />
                    )}
                </div>

                {data && data.count > 0 && (
                    <div
                        style={{
                            padding: '12px 16px',
                            borderTop: '1px solid #eef2f7',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            fontSize: 13,
                            color: '#64748b',
                        }}
                    >
                        <span>
                            Showing <strong style={{ color: '#0b1320' }}>{rows.length}</strong> of{' '}
                            <strong style={{ color: '#0b1320' }}>{data.count}</strong> contracts
                        </span>
                    </div>
                )}
            </SectionCard>
        </ListPageShell>
    );
};

export default ContractsList;
