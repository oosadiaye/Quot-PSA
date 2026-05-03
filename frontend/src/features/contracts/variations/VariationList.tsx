import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, TrendingUp } from 'lucide-react';
import PageHeader from '../../../components/PageHeader';
import { ListPageShell, FilterBar, SectionCard, StatusBadge, ThemedButton } from '../../../components/layout';
import { ResponsiveTable } from '../../../components/ResponsiveTable';
import type { Column } from '../../../components/ResponsiveTable';
import { useVariations, type VariationSummary } from '../hooks/useVariations';
import { useCurrency } from '../../../context/CurrencyContext';

const TIER_OPTIONS = [
    { value: 'LOCAL', label: 'Local (≤15%)' },
    { value: 'BOARD', label: 'Board (≤25%)' },
    { value: 'BPP_REQUIRED', label: 'BPP Required (>25%)' },
];

const VariationList = () => {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const [searchInput, setSearchInput] = useState('');
    const [search, setSearch] = useState('');
    const [tier, setTier] = useState<string | undefined>();

    const { data, isLoading } = useVariations({ search, approval_tier: tier });
    const rows = data?.results ?? [];

    const columns: Column<VariationSummary>[] = [
        {
            key: 'variation_number',
            header: 'Variation #',
            mobilePrimary: true,
            render: (r) => (
                <button
                    onClick={() => navigate(`/contracts/variations/${r.id}`)}
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
                    {r.variation_number}
                </button>
            ),
        },
        { key: 'contract_reference', header: 'Contract', mobilePrimary: true },
        {
            key: 'delta_amount',
            header: 'Delta',
            align: 'right',
            render: (r) => (
                <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                    {formatCurrency(Number(r.delta_amount || 0))}
                </span>
            ),
        },
        {
            key: 'cumulative_pct',
            header: 'Cumulative %',
            align: 'right',
            render: (r) => `${Number(r.cumulative_pct ?? 0).toFixed(1)}%`,
        },
        {
            key: 'approval_tier',
            header: 'Tier',
            render: (r) => <StatusBadge status={r.approval_tier}>{r.approval_tier}</StatusBadge>,
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
                title="Variations"
                subtitle="Change orders by approval tier"
                icon={<TrendingUp size={22} style={{ color: 'rgba(255,255,255,0.85)' }} />}
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
                                placeholder="Search variation number"
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
                            value={tier ?? ''}
                            onChange={(e) => setTier(e.target.value || undefined)}
                            style={{
                                height: 40,
                                padding: '0 12px',
                                borderRadius: 10,
                                border: '1px solid #e2e8f0',
                                background: '#f8fafc',
                                fontSize: 14,
                                fontFamily: 'inherit',
                                outline: 'none',
                                minWidth: 220,
                                color: tier ? '#0b1320' : '#94a3b8',
                            }}
                        >
                            <option value="">All tiers</option>
                            {TIER_OPTIONS.map((o) => (
                                <option key={o.value} value={o.value}>
                                    {o.label}
                                </option>
                            ))}
                        </select>
                        {(searchInput || tier) && (
                            <ThemedButton
                                size="sm"
                                variant="ghost"
                                onClick={() => {
                                    setSearchInput('');
                                    setSearch('');
                                    setTier(undefined);
                                }}
                            >
                                Clear
                            </ThemedButton>
                        )}
                    </FilterBar>
                </div>

                {isLoading ? (
                    <div style={{ padding: 48, textAlign: 'center', color: '#64748b' }}>
                        Loading variations…
                    </div>
                ) : (
                    <ResponsiveTable
                        data={rows}
                        columns={columns}
                        keyField="id"
                        emptyState="No variations match the current filters."
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
                        <strong style={{ color: '#0b1320' }}>{data.count}</strong> variations
                    </div>
                )}
            </SectionCard>
        </ListPageShell>
    );
};

export default VariationList;
