import { useState, useMemo } from 'react';
import { Package, Calculator, Filter, FolderTree, Plus, LayoutList, LayoutGrid, ChevronUp, ChevronDown, Search, Play, X, Loader2, CheckCircle, AlertTriangle, Clock } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useFixedAssets, useCalculateDepreciation, useBulkDepreciation } from '../hooks/useAccountingEnhancements';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import StatusBadge from '../components/shared/StatusBadge';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import { useDialog } from '../../../hooks/useDialog';
import logger from '../../../utils/logger';
import '../styles/glassmorphism.css';

type SortKey = 'asset_number' | 'name' | 'asset_category' | 'acquisition_date' | 'acquisition_cost' | 'accumulated_depreciation' | 'status';

interface BulkResult {
    asset_id: number;
    asset_number: string;
    asset_name: string;
    depreciation_amount: string;
    accumulated_after: string;
    nbv_after: string;
    status: 'success' | 'skipped' | 'already_posted';
    journal_id: number | null;
    message: string;
}

interface BulkResponse {
    mode: 'simulation' | 'posted';
    period_date: string;
    summary: { total_assets: number; total_amount: string; skipped: number };
    results: BulkResult[];
}

export default function FixedAssets() {
    const { formatCurrency } = useCurrency();
    const navigate = useNavigate();
    const [categoryFilter, setCategoryFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [searchTerm, setSearchTerm] = useState('');
    const [viewMode, setViewMode] = useState<'list' | 'grid'>('list');
    const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: 'asc' | 'desc' }>({ key: 'asset_number', direction: 'asc' });

    // Bulk depreciation state
    const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
    const [showBulkModal, setShowBulkModal] = useState(false);
    const [bulkPeriodDate, setBulkPeriodDate] = useState(new Date().toISOString().split('T')[0]);
    const [bulkResults, setBulkResults] = useState<BulkResponse | null>(null);

    const { showConfirm } = useDialog();
    const { data: assets, isLoading } = useFixedAssets({ category: categoryFilter });
    const calculateDepreciation = useCalculateDepreciation();
    const bulkDepreciation = useBulkDepreciation();

    const activeAssetIds = useMemo(() =>
        (assets || []).filter((a: any) => a.status === 'Active').map((a: any) => a.id),
        [assets]
    );

    const handleCalculateDepreciation = async (assetId: number) => {
        if (await showConfirm('Calculate depreciation for this asset?')) {
            try {
                const today = new Date().toISOString().split('T')[0];
                await calculateDepreciation.mutateAsync({ assetId, period_date: today });
            } catch (error) {
                logger.error('Failed to calculate depreciation:', error);
            }
        }
    };

    const toggleSelect = (id: number) => {
        setSelectedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    };

    const toggleSelectAll = () => {
        if (selectedIds.size === activeAssetIds.length) {
            setSelectedIds(new Set());
        } else {
            setSelectedIds(new Set(activeAssetIds));
        }
    };

    const openBulkModal = () => {
        setBulkResults(null);
        setShowBulkModal(true);
    };

    const handleBulkRun = async (simulate: boolean) => {
        if (!simulate && !await showConfirm('This will post depreciation entries to the General Ledger. Continue?')) return;
        try {
            const payload: { period_date: string; asset_ids?: number[]; simulate: boolean } = {
                period_date: bulkPeriodDate,
                simulate,
            };
            if (selectedIds.size > 0) {
                payload.asset_ids = Array.from(selectedIds);
            }
            const result = await bulkDepreciation.mutateAsync(payload);
            setBulkResults(result as BulkResponse);
        } catch (error) {
            logger.error('Bulk depreciation failed:', error);
        }
    };

    const closeBulkModal = () => {
        setShowBulkModal(false);
        setBulkResults(null);
    };

    const filteredAndSorted = useMemo(() => {
        let list = assets || [];

        if (statusFilter) {
            list = list.filter((a: any) => a.status === statusFilter);
        }

        if (searchTerm) {
            const term = searchTerm.toLowerCase();
            list = list.filter((a: any) =>
                a.asset_number?.toLowerCase().includes(term) ||
                a.name?.toLowerCase().includes(term) ||
                a.asset_category?.toLowerCase().includes(term)
            );
        }

        list = [...list].sort((a: any, b: any) => {
            let aVal = a[sortConfig.key];
            let bVal = b[sortConfig.key];
            if (typeof aVal === 'string') aVal = aVal.toLowerCase();
            if (typeof bVal === 'string') bVal = bVal.toLowerCase();
            if (aVal == null) aVal = '';
            if (bVal == null) bVal = '';
            if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
            if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
            return 0;
        });

        return list;
    }, [assets, statusFilter, searchTerm, sortConfig]);

    const requestSort = (key: SortKey) => {
        setSortConfig(prev =>
            prev.key === key && prev.direction === 'asc'
                ? { key, direction: 'desc' }
                : { key, direction: 'asc' }
        );
    };

    const getSortIcon = (key: SortKey) => {
        if (sortConfig.key !== key) return null;
        return sortConfig.direction === 'asc'
            ? <ChevronUp size={14} style={{ marginLeft: '4px', opacity: 0.7 }} />
            : <ChevronDown size={14} style={{ marginLeft: '4px', opacity: 0.7 }} />;
    };

    const totalCost = assets?.reduce((sum: number, asset: any) => sum + parseFloat(asset.acquisition_cost || 0), 0) || 0;
    const totalDepreciation = assets?.reduce((sum: number, asset: any) => sum + parseFloat(asset.accumulated_depreciation || 0), 0) || 0;
    const netBookValue = totalCost - totalDepreciation;
    const activeAssetsCount = assets?.filter((a: any) => a.status === 'Active').length || 0;

    if (isLoading) {
        return <LoadingScreen message="Loading assets..." />;
    }

    const thStyle: React.CSSProperties = {
        padding: '0.75rem 0.75rem', textAlign: 'left', fontWeight: 600,
        fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.05em',
        color: 'var(--color-text-muted)', cursor: 'pointer', userSelect: 'none',
        borderBottom: '2px solid var(--color-border)', whiteSpace: 'nowrap',
    };

    const tdStyle: React.CSSProperties = {
        padding: '0.7rem 0.75rem', fontSize: 'var(--text-sm)',
        borderBottom: '1px solid var(--color-border)',
    };

    const resultStatusBadge = (s: string) => {
        if (s === 'success') return <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '2px 8px', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 600, background: 'rgba(34,197,94,0.1)', color: '#16a34a' }}><CheckCircle size={12} /> Success</span>;
        if (s === 'already_posted') return <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '2px 8px', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 600, background: 'rgba(148,163,184,0.15)', color: '#64748b' }}><Clock size={12} /> Already Posted</span>;
        return <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '2px 8px', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 600, background: 'rgba(245,158,11,0.1)', color: '#d97706' }}><AlertTriangle size={12} /> Skipped</span>;
    };

    return (
        <AccountingLayout>
            <div>
                <PageHeader
                    title="Fixed Assets Register"
                    subtitle="Track and manage organizational assets"
                    icon={<Package size={22} />}
                    actions={
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <button
                                onClick={() => navigate('/accounting/asset-categories')}
                                className="btn btn-outline"
                                style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
                            >
                                <FolderTree size={16} /> Asset Categories
                            </button>
                            <button
                                onClick={openBulkModal}
                                className="btn btn-outline"
                                style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
                                disabled={activeAssetsCount === 0}
                                title="Run depreciation for multiple assets"
                            >
                                <Play size={16} /> Mass Depreciation Run
                            </button>
                            <button
                                onClick={() => navigate('/accounting/fixed-assets/new')}
                                className="btn btn-primary"
                                style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
                            >
                                <Plus size={18} /> Add Asset
                            </button>
                        </div>
                    }
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1rem' }}>
                    <div style={{
                        display: 'flex', borderRadius: '8px', border: '1px solid var(--color-border)',
                        overflow: 'hidden',
                    }}>
                        <button
                            onClick={() => setViewMode('list')}
                            title="List view"
                            style={{
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                padding: '0.45rem 0.6rem', border: 'none', cursor: 'pointer',
                                background: viewMode === 'list' ? 'var(--color-primary)' : 'var(--color-surface)',
                                color: viewMode === 'list' ? 'white' : 'var(--color-text-muted)',
                                transition: 'all 0.15s',
                            }}
                        >
                            <LayoutList size={16} />
                        </button>
                        <button
                            onClick={() => setViewMode('grid')}
                            title="Grid view"
                            style={{
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                padding: '0.45rem 0.6rem', border: 'none', cursor: 'pointer',
                                borderLeft: '1px solid var(--color-border)',
                                background: viewMode === 'grid' ? 'var(--color-primary)' : 'var(--color-surface)',
                                color: viewMode === 'grid' ? 'white' : 'var(--color-text-muted)',
                                transition: 'all 0.15s',
                            }}
                        >
                            <LayoutGrid size={16} />
                        </button>
                    </div>
                </div>

                {/* Summary Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Total Cost</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>{formatCurrency(totalCost)}</p>
                    </div>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Accumulated Depr.</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-error)' }}>{formatCurrency(totalDepreciation)}</p>
                    </div>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Net Book Value</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-cta)' }}>{formatCurrency(netBookValue)}</p>
                    </div>
                    <div className="card">
                        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Active Assets</p>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>{activeAssetsCount}</p>
                    </div>
                </div>

                {/* Selection info bar */}
                {selectedIds.size > 0 && (
                    <div style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        padding: '0.75rem 1rem', marginBottom: '1rem', borderRadius: '8px',
                        background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.2)',
                    }}>
                        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-primary)' }}>
                            {selectedIds.size} asset{selectedIds.size > 1 ? 's' : ''} selected
                        </span>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                            <button
                                onClick={openBulkModal}
                                className="btn btn-primary"
                                style={{ fontSize: 'var(--text-xs)', padding: '0.35rem 0.75rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}
                            >
                                <Play size={14} /> Run Depreciation
                            </button>
                            <button
                                onClick={() => setSelectedIds(new Set())}
                                className="btn btn-outline"
                                style={{ fontSize: 'var(--text-xs)', padding: '0.35rem 0.75rem' }}
                            >
                                Clear Selection
                            </button>
                        </div>
                    </div>
                )}

                {/* Filters */}
                <div className="card" style={{ padding: '1rem', marginBottom: '1.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, minWidth: '200px', background: 'var(--color-background)', borderRadius: '8px', padding: '0 0.75rem', border: '1px solid var(--color-border)' }}>
                            <Search size={16} style={{ color: 'var(--color-text-muted)', flexShrink: 0 }} />
                            <input
                                type="text"
                                placeholder="Search by number, name, or category..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                style={{ flex: 1, border: 'none', background: 'transparent', padding: '0.55rem 0', outline: 'none', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}
                            />
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <Filter size={16} style={{ color: 'var(--color-text-muted)' }} />
                            <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} style={{ minWidth: '150px', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                <option value="">All Categories</option>
                                <option value="Building">Building</option>
                                <option value="Equipment">Equipment</option>
                                <option value="Vehicle">Vehicle</option>
                                <option value="IT">IT Equipment</option>
                                <option value="Furniture">Furniture</option>
                                <option value="Land">Land</option>
                            </select>
                            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ minWidth: '130px', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                <option value="">All Statuses</option>
                                <option value="Active">Active</option>
                                <option value="Disposed">Disposed</option>
                                <option value="Retired">Retired</option>
                            </select>
                        </div>
                    </div>
                </div>

                {/* LIST VIEW */}
                {viewMode === 'list' && (
                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr>
                                        <th style={{ ...thStyle, width: '40px', cursor: 'default', textAlign: 'center' }}>
                                            <input
                                                type="checkbox"
                                                checked={activeAssetIds.length > 0 && selectedIds.size === activeAssetIds.length}
                                                onChange={toggleSelectAll}
                                                style={{ cursor: 'pointer', width: '16px', height: '16px' }}
                                                title="Select all active assets"
                                            />
                                        </th>
                                        <th style={thStyle} onClick={() => requestSort('asset_number')}>
                                            <div style={{ display: 'flex', alignItems: 'center' }}>Asset # {getSortIcon('asset_number')}</div>
                                        </th>
                                        <th style={thStyle} onClick={() => requestSort('name')}>
                                            <div style={{ display: 'flex', alignItems: 'center' }}>Name {getSortIcon('name')}</div>
                                        </th>
                                        <th style={thStyle} onClick={() => requestSort('asset_category')}>
                                            <div style={{ display: 'flex', alignItems: 'center' }}>Category {getSortIcon('asset_category')}</div>
                                        </th>
                                        <th style={thStyle} onClick={() => requestSort('acquisition_date')}>
                                            <div style={{ display: 'flex', alignItems: 'center' }}>Acq. Date {getSortIcon('acquisition_date')}</div>
                                        </th>
                                        <th style={{ ...thStyle, textAlign: 'right' }} onClick={() => requestSort('acquisition_cost')}>
                                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>Cost {getSortIcon('acquisition_cost')}</div>
                                        </th>
                                        <th style={{ ...thStyle, textAlign: 'right' }} onClick={() => requestSort('accumulated_depreciation')}>
                                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>Accum. Depr. {getSortIcon('accumulated_depreciation')}</div>
                                        </th>
                                        <th style={{ ...thStyle, textAlign: 'right' }}>
                                            NBV
                                        </th>
                                        <th style={thStyle} onClick={() => requestSort('status')}>
                                            <div style={{ display: 'flex', alignItems: 'center' }}>Status {getSortIcon('status')}</div>
                                        </th>
                                        <th style={{ ...thStyle, textAlign: 'center', cursor: 'default' }}>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredAndSorted.map((asset: any) => {
                                        const nbv = parseFloat(asset.acquisition_cost || 0) - parseFloat(asset.accumulated_depreciation || 0);
                                        const isActive = asset.status === 'Active';
                                        return (
                                            <tr key={asset.id} style={{ transition: 'background 0.1s', background: selectedIds.has(asset.id) ? 'rgba(59,130,246,0.06)' : 'transparent' }}
                                                onMouseOver={(e) => { if (!selectedIds.has(asset.id)) e.currentTarget.style.background = 'rgba(59,130,246,0.04)'; }}
                                                onMouseOut={(e) => { if (!selectedIds.has(asset.id)) e.currentTarget.style.background = 'transparent'; }}
                                            >
                                                <td style={{ ...tdStyle, textAlign: 'center', width: '40px' }}>
                                                    {isActive && (
                                                        <input
                                                            type="checkbox"
                                                            checked={selectedIds.has(asset.id)}
                                                            onChange={() => toggleSelect(asset.id)}
                                                            style={{ cursor: 'pointer', width: '16px', height: '16px' }}
                                                        />
                                                    )}
                                                </td>
                                                <td style={{ ...tdStyle, fontWeight: 600, fontFamily: 'monospace', color: 'var(--color-primary)' }}>{asset.asset_number}</td>
                                                <td style={{ ...tdStyle, fontWeight: 500 }}>{asset.name}</td>
                                                <td style={tdStyle}>
                                                    <span style={{ padding: '0.15rem 0.5rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 500, background: 'rgba(59,130,246,0.08)', color: '#2471a3' }}>
                                                        {asset.asset_category}
                                                    </span>
                                                </td>
                                                <td style={tdStyle}>{asset.acquisition_date}</td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace', fontWeight: 500 }}>{formatCurrency(parseFloat(asset.acquisition_cost || 0))}</td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace', color: 'var(--color-error)' }}>{formatCurrency(parseFloat(asset.accumulated_depreciation || 0))}</td>
                                                <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace', fontWeight: 600, color: 'var(--color-cta)' }}>{formatCurrency(nbv)}</td>
                                                <td style={tdStyle}><StatusBadge status={asset.status} /></td>
                                                <td style={{ ...tdStyle, textAlign: 'center' }}>
                                                    {isActive && (
                                                        <button
                                                            onClick={() => handleCalculateDepreciation(asset.id)}
                                                            title="Calculate Depreciation"
                                                            style={{ padding: '0.3rem 0.5rem', borderRadius: '6px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text-muted)', cursor: 'pointer', fontSize: 'var(--text-xs)', display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}
                                                        >
                                                            <Calculator size={13} /> Depr.
                                                        </button>
                                                    )}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>

                        {filteredAndSorted.length === 0 && (
                            <div style={{ textAlign: 'center', padding: '4rem 1.25rem', color: 'var(--color-text-muted)' }}>
                                <Package size={48} style={{ margin: '0 auto 1rem', opacity: 0.3 }} />
                                <p style={{ fontSize: 'var(--text-base)', fontWeight: 500 }}>
                                    {searchTerm || categoryFilter || statusFilter ? 'No assets match the current filters' : 'No fixed assets found'}
                                </p>
                            </div>
                        )}
                    </div>
                )}

                {/* GRID VIEW */}
                {viewMode === 'grid' && (
                    <>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '1.5rem' }}>
                            {filteredAndSorted.map((asset: any) => {
                                const nbv = parseFloat(asset.acquisition_cost || 0) - parseFloat(asset.accumulated_depreciation || 0);
                                const isActive = asset.status === 'Active';
                                return (
                                    <div key={asset.id} className="card" style={{ border: selectedIds.has(asset.id) ? '2px solid var(--color-primary)' : undefined }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                                            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
                                                {isActive && (
                                                    <input
                                                        type="checkbox"
                                                        checked={selectedIds.has(asset.id)}
                                                        onChange={() => toggleSelect(asset.id)}
                                                        style={{ cursor: 'pointer', width: '16px', height: '16px', marginTop: '2px' }}
                                                    />
                                                )}
                                                <div>
                                                    <p style={{ fontSize: 'var(--text-xs)', fontFamily: 'monospace', color: 'var(--color-primary)', fontWeight: 600, marginBottom: '0.25rem' }}>{asset.asset_number}</p>
                                                    <p style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--color-text)', marginBottom: '0.25rem' }}>{asset.name}</p>
                                                    <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{asset.asset_category}</p>
                                                </div>
                                            </div>
                                            <StatusBadge status={asset.status} />
                                        </div>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1rem' }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>Original Cost</span>
                                                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>{formatCurrency(parseFloat(asset.acquisition_cost || 0))}</span>
                                            </div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>Accumulated Depr.</span>
                                                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-error)' }}>{formatCurrency(parseFloat(asset.accumulated_depreciation || 0))}</span>
                                            </div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>Net Book Value</span>
                                                <span style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-cta)' }}>{formatCurrency(nbv)}</span>
                                            </div>
                                        </div>
                                        {isActive && (
                                            <button className="btn btn-outline" style={{ width: '100%' }} onClick={() => handleCalculateDepreciation(asset.id)}>
                                                <Calculator size={16} /> Calculate Depreciation
                                            </button>
                                        )}
                                    </div>
                                );
                            })}
                        </div>

                        {filteredAndSorted.length === 0 && (
                            <div style={{ textAlign: 'center', padding: '5rem 1.25rem', color: 'var(--color-text-muted)' }}>
                                <Package size={64} style={{ margin: '0 auto 1rem', opacity: 0.3 }} />
                                <p style={{ fontSize: 'var(--text-lg)', fontWeight: 500 }}>
                                    {searchTerm || categoryFilter || statusFilter ? 'No assets match the current filters' : 'No fixed assets found'}
                                </p>
                            </div>
                        )}
                    </>
                )}
            </div>

            {/* ── BULK DEPRECIATION MODAL ────────────────────────── */}
            {showBulkModal && (
                <div
                    style={{
                        position: 'fixed', inset: 0, zIndex: 1000,
                        background: 'rgba(0,0,0,0.5)', display: 'flex',
                        alignItems: 'center', justifyContent: 'center',
                        padding: '2rem',
                    }}
                    onClick={closeBulkModal}
                >
                    <div
                        onClick={(e) => e.stopPropagation()}
                        style={{
                            background: 'var(--color-surface, #fff)', borderRadius: '12px',
                            width: '100%', maxWidth: bulkResults ? '900px' : '500px',
                            maxHeight: '85vh', display: 'flex', flexDirection: 'column',
                            boxShadow: '0 25px 50px rgba(0,0,0,0.25)',
                            transition: 'max-width 0.3s',
                        }}
                    >
                        {/* Modal Header */}
                        <div style={{
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                            padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--color-border)',
                        }}>
                            <div>
                                <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                                    Mass Depreciation Run
                                </h2>
                                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: '0.25rem 0 0' }}>
                                    {selectedIds.size > 0
                                        ? `${selectedIds.size} selected asset${selectedIds.size > 1 ? 's' : ''}`
                                        : 'All active assets'}
                                </p>
                            </div>
                            <button
                                onClick={closeBulkModal}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', padding: '4px' }}
                            >
                                <X size={20} />
                            </button>
                        </div>

                        {/* Modal Body */}
                        <div style={{ padding: '1.5rem', overflowY: 'auto', flex: 1 }}>
                            {/* Period date + actions */}
                            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                                <div style={{ flex: 1, minWidth: '180px' }}>
                                    <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>
                                        Period Date<span className="required-mark"> *</span>
                                    </label>
                                    <input
                                        type="date"
                                        value={bulkPeriodDate}
                                        onChange={(e) => setBulkPeriodDate(e.target.value)}
                                        style={{
                                            width: '100%', padding: '0.5rem 0.75rem', borderRadius: '6px',
                                            border: '2px solid var(--color-border)', background: 'var(--color-background)',
                                            color: 'var(--color-text)', fontSize: 'var(--text-sm)',
                                        }}
                                    />
                                </div>
                                <button
                                    onClick={() => handleBulkRun(true)}
                                    className="btn btn-outline"
                                    disabled={bulkDepreciation.isPending || !bulkPeriodDate}
                                    style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', whiteSpace: 'nowrap' }}
                                >
                                    {bulkDepreciation.isPending && bulkResults === null ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
                                    Test Simulation
                                </button>
                                {bulkResults?.mode === 'simulation' ? (
                                    <button
                                        onClick={() => handleBulkRun(false)}
                                        className="btn btn-primary"
                                        disabled={bulkDepreciation.isPending || parseFloat(bulkResults.summary.total_amount) === 0}
                                        style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', whiteSpace: 'nowrap' }}
                                    >
                                        {bulkDepreciation.isPending ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle size={16} />}
                                        Post to GL
                                    </button>
                                ) : (
                                    <button
                                        onClick={() => handleBulkRun(false)}
                                        className="btn btn-primary"
                                        disabled={bulkDepreciation.isPending || !bulkPeriodDate}
                                        style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', whiteSpace: 'nowrap' }}
                                    >
                                        {bulkDepreciation.isPending ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle size={16} />}
                                        Post to GL
                                    </button>
                                )}
                            </div>

                            {/* Results */}
                            {bulkResults && (
                                <>
                                    {/* Summary bar */}
                                    <div style={{
                                        display: 'flex', gap: '1.5rem', padding: '1rem', borderRadius: '8px', marginBottom: '1rem',
                                        background: bulkResults.mode === 'posted' ? 'rgba(34,197,94,0.08)' : 'rgba(59,130,246,0.06)',
                                        border: `1px solid ${bulkResults.mode === 'posted' ? 'rgba(34,197,94,0.2)' : 'rgba(59,130,246,0.15)'}`,
                                    }}>
                                        <div>
                                            <p style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', color: 'var(--color-text-muted)', marginBottom: '2px', fontWeight: 600 }}>Mode</p>
                                            <p style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: bulkResults.mode === 'posted' ? '#16a34a' : 'var(--color-primary)' }}>
                                                {bulkResults.mode === 'posted' ? 'Posted' : 'Simulation'}
                                            </p>
                                        </div>
                                        <div>
                                            <p style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', color: 'var(--color-text-muted)', marginBottom: '2px', fontWeight: 600 }}>Assets</p>
                                            <p style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{bulkResults.summary.total_assets}</p>
                                        </div>
                                        <div>
                                            <p style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', color: 'var(--color-text-muted)', marginBottom: '2px', fontWeight: 600 }}>Total Depreciation</p>
                                            <p style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{formatCurrency(parseFloat(bulkResults.summary.total_amount))}</p>
                                        </div>
                                        {bulkResults.summary.skipped > 0 && (
                                            <div>
                                                <p style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', color: 'var(--color-text-muted)', marginBottom: '2px', fontWeight: 600 }}>Skipped</p>
                                                <p style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: '#d97706' }}>{bulkResults.summary.skipped}</p>
                                            </div>
                                        )}
                                    </div>

                                    {/* Results table */}
                                    <div style={{ overflowX: 'auto', borderRadius: '8px', border: '1px solid var(--color-border)' }}>
                                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                                            <thead>
                                                <tr style={{ background: 'var(--color-background)' }}>
                                                    <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left', fontWeight: 600, fontSize: 'var(--text-xs)', textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Asset #</th>
                                                    <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left', fontWeight: 600, fontSize: 'var(--text-xs)', textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Name</th>
                                                    <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: 600, fontSize: 'var(--text-xs)', textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Depr. Amount</th>
                                                    <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: 600, fontSize: 'var(--text-xs)', textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Accum. After</th>
                                                    <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: 600, fontSize: 'var(--text-xs)', textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>NBV After</th>
                                                    <th style={{ padding: '0.6rem 0.75rem', textAlign: 'center', fontWeight: 600, fontSize: 'var(--text-xs)', textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {bulkResults.results.map((r) => (
                                                    <tr key={r.asset_id} style={{ borderTop: '1px solid var(--color-border)' }}>
                                                        <td style={{ padding: '0.5rem 0.75rem', fontFamily: 'monospace', fontWeight: 600, color: 'var(--color-primary)' }}>{r.asset_number}</td>
                                                        <td style={{ padding: '0.5rem 0.75rem', fontWeight: 500 }}>{r.asset_name}</td>
                                                        <td style={{ padding: '0.5rem 0.75rem', textAlign: 'right', fontFamily: 'monospace', fontWeight: 600 }}>
                                                            {parseFloat(r.depreciation_amount) > 0 ? formatCurrency(parseFloat(r.depreciation_amount)) : '--'}
                                                        </td>
                                                        <td style={{ padding: '0.5rem 0.75rem', textAlign: 'right', fontFamily: 'monospace', color: 'var(--color-error)' }}>
                                                            {formatCurrency(parseFloat(r.accumulated_after))}
                                                        </td>
                                                        <td style={{ padding: '0.5rem 0.75rem', textAlign: 'right', fontFamily: 'monospace', fontWeight: 600, color: 'var(--color-cta)' }}>
                                                            {formatCurrency(parseFloat(r.nbv_after))}
                                                        </td>
                                                        <td style={{ padding: '0.5rem 0.75rem', textAlign: 'center' }}>
                                                            {resultStatusBadge(r.status)}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </>
                            )}

                            {/* Loading state */}
                            {bulkDepreciation.isPending && !bulkResults && (
                                <div style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--color-text-muted)' }}>
                                    <Loader2 size={32} className="animate-spin" style={{ margin: '0 auto 1rem', display: 'block' }} />
                                    <p style={{ fontWeight: 500 }}>Processing depreciation...</p>
                                </div>
                            )}

                            {/* Error state */}
                            {bulkDepreciation.isError && (
                                <div style={{ padding: '1rem', borderRadius: '8px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#dc2626', fontSize: 'var(--text-sm)', marginTop: '1rem' }}>
                                    Failed to run depreciation. Please check asset GL account configurations and try again.
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            <style>{`
                @keyframes spin { to { transform: rotate(360deg); } }
                .animate-spin { animation: spin 1s linear infinite; }
            `}</style>
        </AccountingLayout>
    );
}
