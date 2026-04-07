import { useState, useMemo } from 'react';
import { useStockValuation, useItemCategories, useProductTypes } from '../hooks/useInventory';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import { DollarSign, Package, TrendingUp, Download, Search, ChevronUp, ChevronDown, RefreshCw } from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ValuationItem {
    id: number;
    sku: string;
    name: string;
    total_quantity: number;
    total_value: number;
    average_cost: number;
    needs_reorder: boolean;
    unit_of_measure: string;
    valuation_method: string;
    product_type_id?: number | null;
    category_id?: number | null;
    product_type_name?: string | null;
    category_name?: string | null;
}

type SortColumn =
    | 'sku'
    | 'name'
    | 'product_type_name'
    | 'category_name'
    | 'total_quantity'
    | 'average_cost'
    | 'total_value'
    | 'valuation_method'
    | 'status';

type SortDir = 'asc' | 'desc';

// ─── Constants ────────────────────────────────────────────────────────────────

const METHOD_COLORS: Record<string, { bg: string; color: string }> = {
    WA:   { bg: 'rgba(59,130,246,0.15)',  color: '#3b82f6' },
    FIFO: { bg: 'rgba(16,185,129,0.15)',  color: '#10b981' },
    LIFO: { bg: 'rgba(139,92,246,0.15)', color: '#8b5cf6' },
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function normalizeMethod(m: string): string {
    const u = (m || '').toUpperCase();
    if (u.includes('FIFO')) return 'FIFO';
    if (u.includes('LIFO')) return 'LIFO';
    return 'WA';
}

function getStockStatus(item: ValuationItem): 'In Stock' | 'Low Stock' | 'Out of Stock' {
    if (Number(item.total_quantity) <= 0) return 'Out of Stock';
    if (item.needs_reorder) return 'Low Stock';
    return 'In Stock';
}

function exportCSV(rows: ValuationItem[], formatCurrency: (v: number) => string): void {
    const headers = ['SKU', 'Name', 'Product Type', 'Category', 'Qty on Hand', 'UOM', 'Avg Cost', 'Total Value', 'Valuation Method', 'Status'];
    const lines = [
        headers.join(','),
        ...rows.map(r => [
            `"${r.sku}"`,
            `"${r.name}"`,
            `"${r.product_type_name || ''}"`,
            `"${r.category_name || ''}"`,
            Number(r.total_quantity).toFixed(2),
            `"${r.unit_of_measure || ''}"`,
            formatCurrency(Number(r.average_cost)),
            formatCurrency(Number(r.total_value)),
            `"${normalizeMethod(r.valuation_method)}"`,
            `"${getStockStatus(r)}"`,
        ].join(',')),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `stock-valuation-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
}

// ─── Component ────────────────────────────────────────────────────────────────

const StockValuation = () => {
    // ── 1. State ──────────────────────────────────────────────────────────────
    const [search, setSearch] = useState('');
    const [methodFilter, setMethodFilter] = useState<'All' | 'WA' | 'FIFO' | 'LIFO'>('All');
    const [typeFilter, setTypeFilter] = useState('');
    const [catFilter, setCatFilter] = useState('');
    const [sort, setSort] = useState<{ column: SortColumn; dir: SortDir }>({ column: 'total_value', dir: 'desc' });

    // ── 2. Data hooks ─────────────────────────────────────────────────────────
    // Pass active filters so the DB does the heavy lifting; search + method stay client-side
    const { data: valuation, isLoading, isFetching, dataUpdatedAt, refetch } = useStockValuation({
        product_type: typeFilter || undefined,
        category:     catFilter  || undefined,
    });
    // useProductTypes() now returns a plain array directly
    const { data: productTypes = [] } = useProductTypes();
    const { data: categoriesRaw } = useItemCategories();
    const { formatCurrency } = useCurrency();

    // ── 3. useMemo: normalise API responses ───────────────────────────────────
    const rawData: ValuationItem[] = useMemo(() => {
        // Backend returns { items: [...], summary: {...} }
        if (Array.isArray((valuation as any)?.items)) return (valuation as any).items;
        // Fallback: paginated DRF envelope
        if (Array.isArray((valuation as any)?.results)) return (valuation as any).results;
        if (Array.isArray(valuation)) return valuation as any;
        return [];
    }, [valuation]);

    const categories: Array<{ id: number; name: string }> = useMemo(() => {
        if (Array.isArray((categoriesRaw as any)?.results)) return (categoriesRaw as any).results;
        if (Array.isArray(categoriesRaw)) return categoriesRaw as any;
        return [];
    }, [categoriesRaw]);

    const filtered: ValuationItem[] = useMemo(() => {
        return rawData.filter(item => {
            // product_type + category already filtered by the backend; only do text + method here
            const q = search.toLowerCase();
            if (q && !item.sku?.toLowerCase().includes(q) && !item.name?.toLowerCase().includes(q)) return false;
            if (methodFilter !== 'All' && normalizeMethod(item.valuation_method) !== methodFilter) return false;
            return true;
        });
    }, [rawData, search, methodFilter]);

    const sorted: ValuationItem[] = useMemo(() => {
        return [...filtered].sort((a, b) => {
            let av: string | number;
            let bv: string | number;
            if (sort.column === 'status') {
                const order: Record<string, number> = { 'Out of Stock': 0, 'Low Stock': 1, 'In Stock': 2 };
                av = order[getStockStatus(a)];
                bv = order[getStockStatus(b)];
            } else {
                av = (a as Record<string, any>)[sort.column] ?? '';
                bv = (b as Record<string, any>)[sort.column] ?? '';
            }
            if (typeof av === 'number' && typeof bv === 'number') {
                return sort.dir === 'asc' ? av - bv : bv - av;
            }
            return sort.dir === 'asc'
                ? String(av).localeCompare(String(bv))
                : String(bv).localeCompare(String(av));
        });
    }, [filtered, sort]);

    // ── 4. Derived / computed values ──────────────────────────────────────────
    const totalValue    = rawData.reduce((s, i) => s + Number(i.total_value    || 0), 0);
    const totalQty      = rawData.reduce((s, i) => s + Number(i.total_quantity || 0), 0);
    const weightedAvg   = totalQty > 0 ? totalValue / totalQty : 0;

    const chartMethods  = ['WA', 'FIFO', 'LIFO'] as const;
    const methodCounts  = Object.fromEntries(
        chartMethods.map(m => [m, rawData.filter(i => normalizeMethod(i.valuation_method) === m).length])
    );
    const methodValues  = Object.fromEntries(
        chartMethods.map(m => [
            m,
            rawData
                .filter(i => normalizeMethod(i.valuation_method) === m)
                .reduce((s, i) => s + Number(i.total_value || 0), 0),
        ])
    );
    const chartTotal    = Object.values(methodValues).reduce((s, v) => s + v, 0);

    const filteredTotalQty   = filtered.reduce((s, i) => s + Number(i.total_quantity || 0), 0);
    const filteredTotalValue = filtered.reduce((s, i) => s + Number(i.total_value    || 0), 0);

    // ── 5. Conditional return (AFTER all hooks & computed values) ─────────────
    if (isLoading) return <LoadingScreen message="Loading stock valuation..." />;

    // ── 6. Handlers & sub-components ─────────────────────────────────────────
    const toggleSort = (col: SortColumn) => {
        setSort(prev =>
            prev.column === col
                ? { column: col, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
                : { column: col, dir: 'desc' }
        );
    };

    const SortIcon = ({ col }: { col: SortColumn }) => {
        if (sort.column !== col) return <span style={{ opacity: 0.3, fontSize: '0.65rem' }}>↕</span>;
        return sort.dir === 'asc'
            ? <ChevronUp size={13} style={{ color: 'var(--color-primary)' }} />
            : <ChevronDown size={13} style={{ color: 'var(--color-primary)' }} />;
    };

    const thStyle: React.CSSProperties = {
        padding: '0.75rem 1rem',
        fontSize: 'var(--text-xs)',
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        color: 'var(--color-text-muted)',
        cursor: 'pointer',
        userSelect: 'none',
        whiteSpace: 'nowrap',
        background: 'var(--color-surface)',
    };

    // ── 7. JSX ────────────────────────────────────────────────────────────────
    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }} className="animate-fade">
                <PageHeader
                    title="Stock Valuation"
                    subtitle="Financial stock valuation report across all inventory items."
                    icon={<DollarSign size={22} />}
                    actions={
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            {/* Live-refresh status */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                <RefreshCw
                                    size={13}
                                    style={{
                                        color: isFetching ? 'var(--color-primary)' : 'var(--color-text-muted)',
                                        animation: isFetching ? 'spin 1s linear infinite' : 'none',
                                    }}
                                />
                                {isFetching
                                    ? 'Refreshing…'
                                    : dataUpdatedAt
                                        ? `Updated ${new Date(dataUpdatedAt).toLocaleTimeString()}`
                                        : 'Live'}
                            </div>
                            <button className="btn btn-outline" onClick={() => refetch()} disabled={isFetching} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                <RefreshCw size={14} /> Refresh
                            </button>
                            <button className="btn btn-outline" onClick={() => exportCSV(filtered, formatCurrency)}>
                                <Download size={16} /> Export CSV
                            </button>
                        </div>
                    }
                />

                {/* ── Summary Cards ───────────────────────────────────────── */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.25rem', marginBottom: '2rem' }}>

                    {/* Total Inventory Value */}
                    <div className="card" style={{ borderLeft: '4px solid var(--color-success)' }}>
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
                            <div style={{ padding: '0.75rem', borderRadius: '0.625rem', background: 'rgba(16,185,129,0.12)', flexShrink: 0 }}>
                                <DollarSign size={22} style={{ color: 'var(--color-success)' }} />
                            </div>
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.25rem' }}>Total Inventory Value</div>
                                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 800, color: 'var(--color-success)', lineHeight: 1.1 }}>{formatCurrency(totalValue)}</div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>{rawData.length} items tracked</div>
                            </div>
                        </div>
                    </div>

                    {/* Total Items */}
                    <div className="card" style={{ borderLeft: '4px solid var(--color-primary)' }}>
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
                            <div style={{ padding: '0.75rem', borderRadius: '0.625rem', background: 'rgba(59,130,246,0.12)', flexShrink: 0 }}>
                                <Package size={22} style={{ color: 'var(--color-primary)' }} />
                            </div>
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.25rem' }}>Total Items</div>
                                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 800, lineHeight: 1.1 }}>{rawData.length}</div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
                                    {rawData.filter(i => getStockStatus(i) === 'Out of Stock').length} out of stock
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Weighted Average Cost */}
                    <div className="card" style={{ borderLeft: '4px solid #f59e0b' }}>
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
                            <div style={{ padding: '0.75rem', borderRadius: '0.625rem', background: 'rgba(245,158,11,0.12)', flexShrink: 0 }}>
                                <TrendingUp size={22} style={{ color: '#f59e0b' }} />
                            </div>
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.25rem' }}>Avg Cost per Unit</div>
                                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 800, lineHeight: 1.1 }}>{formatCurrency(weightedAvg)}</div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>weighted average</div>
                            </div>
                        </div>
                    </div>

                    {/* Valuation Methods breakdown */}
                    <div className="card" style={{ borderLeft: '4px solid #8b5cf6' }}>
                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.75rem' }}>Valuation Methods</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                            {chartMethods.map(m => (
                                <div key={m} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <span style={{
                                        padding: '0.1rem 0.5rem',
                                        borderRadius: '99px',
                                        fontSize: 'var(--text-xs)',
                                        fontWeight: 700,
                                        background: METHOD_COLORS[m].bg,
                                        color: METHOD_COLORS[m].color,
                                        minWidth: '42px',
                                        textAlign: 'center',
                                    }}>{m}</span>
                                    <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>{methodCounts[m] || 0}</span>
                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>items</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* ── Value Distribution Chart ─────────────────────────────── */}
                {chartTotal > 0 && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '1rem' }}>Value Distribution by Valuation Method</div>
                        {/* Stacked horizontal bar */}
                        <div style={{ height: '24px', borderRadius: '6px', overflow: 'hidden', display: 'flex', marginBottom: '1rem', background: 'var(--color-border)' }}>
                            {chartMethods.map(m => {
                                const pct = (methodValues[m] || 0) / chartTotal * 100;
                                if (pct === 0) return null;
                                return (
                                    <div
                                        key={m}
                                        style={{ width: `${pct}%`, background: METHOD_COLORS[m].color, transition: 'width 0.4s ease' }}
                                        title={`${m}: ${formatCurrency(methodValues[m] || 0)} (${pct.toFixed(1)}%)`}
                                    />
                                );
                            })}
                        </div>
                        {/* Legend */}
                        <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
                            {chartMethods.map(m => {
                                const val = methodValues[m] || 0;
                                const pct = chartTotal > 0 ? (val / chartTotal) * 100 : 0;
                                return (
                                    <div key={m} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <div style={{ width: '12px', height: '12px', borderRadius: '3px', background: METHOD_COLORS[m].color, flexShrink: 0 }} />
                                        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>{m}</span>
                                        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{formatCurrency(val)}</span>
                                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>({pct.toFixed(1)}%)</span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}

                {/* ── Filter Bar ───────────────────────────────────────────── */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', marginBottom: '1.5rem' }}>

                    {/* Row 1 — Search + Product Type + Category */}
                    <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
                        {/* Search */}
                        <div style={{ position: 'relative', flex: 1, minWidth: '220px' }}>
                            <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)', pointerEvents: 'none' }} />
                            <input
                                type="text"
                                className="input"
                                placeholder="Search SKU or item name..."
                                value={search}
                                onChange={e => setSearch(e.target.value)}
                                style={{ paddingLeft: '2.25rem', width: '100%' }}
                            />
                        </div>

                        {/* Product type dropdown */}
                        <select className="input" value={typeFilter} onChange={e => setTypeFilter(e.target.value)} style={{ minWidth: '160px', width: 'auto', flexShrink: 0 }}>
                            <option value="">All Product Types</option>
                            {productTypes.map(pt => (
                                <option key={pt.id} value={String(pt.id)}>{pt.name_display || pt.name}</option>
                            ))}
                        </select>

                        {/* Category dropdown */}
                        <select className="input" value={catFilter} onChange={e => setCatFilter(e.target.value)} style={{ minWidth: '160px', width: 'auto', flexShrink: 0 }}>
                            <option value="">All Categories</option>
                            {categories.map(c => (
                                <option key={c.id} value={String(c.id)}>{c.name}</option>
                            ))}
                        </select>
                    </div>

                    {/* Row 2 — Valuation Method tabs */}
                    <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                        {(['All', 'WA', 'FIFO', 'LIFO'] as const).map(m => (
                            <button
                                key={m}
                                onClick={() => setMethodFilter(m)}
                                style={{
                                    padding: '0.4rem 0.85rem',
                                    borderRadius: '99px',
                                    border: methodFilter === m ? 'none' : '1px solid var(--color-border)',
                                    cursor: 'pointer',
                                    fontSize: 'var(--text-xs)',
                                    fontWeight: 600,
                                    background: methodFilter === m
                                        ? (m === 'All' ? 'var(--color-primary)' : METHOD_COLORS[m]?.color)
                                        : 'transparent',
                                    color: methodFilter === m ? '#fff' : 'var(--color-text-muted)',
                                    transition: 'all 0.15s',
                                }}
                            >{m}</button>
                        ))}
                    </div>

                </div>

                {/* ── Table ────────────────────────────────────────────────── */}
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                            <thead>
                                <tr style={{ borderBottom: '2px solid var(--color-border)' }}>
                                    {(
                                        [
                                            { col: 'sku'               as SortColumn, label: 'SKU',          align: 'left'  },
                                            { col: 'name'              as SortColumn, label: 'Item Name',    align: 'left'  },
                                            { col: 'product_type_name' as SortColumn, label: 'Type',         align: 'left'  },
                                            { col: 'category_name'     as SortColumn, label: 'Category',     align: 'left'  },
                                            { col: 'total_quantity'    as SortColumn, label: 'Qty on Hand',  align: 'right' },
                                            { col: 'average_cost'      as SortColumn, label: 'Avg Cost',     align: 'right' },
                                            { col: 'total_value'       as SortColumn, label: 'Total Value',  align: 'right' },
                                            { col: 'valuation_method'  as SortColumn, label: 'Method',       align: 'left'  },
                                            { col: 'status'            as SortColumn, label: 'Status',       align: 'left'  },
                                        ] as Array<{ col: SortColumn; label: string; align: 'left' | 'right' }>
                                    ).map(({ col, label, align }) => (
                                        <th
                                            key={col}
                                            style={{ ...thStyle, textAlign: align }}
                                            onClick={() => toggleSort(col)}
                                        >
                                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', float: align === 'right' ? 'right' : undefined }}>
                                                {label} <SortIcon col={col} />
                                            </span>
                                        </th>
                                    ))}
                                </tr>
                            </thead>

                            <tbody>
                                {sorted.length === 0 ? (
                                    <tr>
                                        <td colSpan={9} style={{ padding: '3.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                            <Package size={36} style={{ opacity: 0.2, display: 'block', margin: '0 auto 0.75rem' }} />
                                            No items match the current filters.
                                        </td>
                                    </tr>
                                ) : sorted.map(item => {
                                    const method = normalizeMethod(item.valuation_method);
                                    const status = getStockStatus(item);
                                    const statusColors =
                                        status === 'In Stock'    ? { bg: 'rgba(16,185,129,0.15)',  color: '#10b981' }
                                        : status === 'Low Stock' ? { bg: 'rgba(245,158,11,0.15)',  color: '#f59e0b' }
                                                                 : { bg: 'rgba(239,68,68,0.15)',   color: '#ef4444' };
                                    return (
                                        <tr key={item.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                            <td style={{ padding: '0.75rem 1rem' }}>
                                                <span style={{ fontFamily: 'monospace', fontSize: 'var(--text-xs)', background: 'var(--color-surface)', padding: '0.15rem 0.4rem', borderRadius: '4px', color: 'var(--color-primary)', fontWeight: 600 }}>
                                                    {item.sku}
                                                </span>
                                            </td>
                                            <td style={{ padding: '0.75rem 1rem', fontWeight: 500 }}>{item.name}</td>
                                            <td style={{ padding: '0.75rem 1rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>{item.product_type_name || '—'}</td>
                                            <td style={{ padding: '0.75rem 1rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>{item.category_name || '—'}</td>
                                            <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 600 }}>
                                                {Number(item.total_quantity).toFixed(2)}
                                                {item.unit_of_measure && (
                                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginLeft: '4px' }}>{item.unit_of_measure}</span>
                                                )}
                                            </td>
                                            <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                                                {formatCurrency(Number(item.average_cost || 0))}
                                            </td>
                                            <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 700, color: 'var(--color-success)' }}>
                                                {formatCurrency(Number(item.total_value || 0))}
                                            </td>
                                            <td style={{ padding: '0.75rem 1rem' }}>
                                                <span style={{ padding: '0.2rem 0.6rem', borderRadius: '99px', fontSize: 'var(--text-xs)', fontWeight: 700, background: METHOD_COLORS[method]?.bg, color: METHOD_COLORS[method]?.color }}>
                                                    {method}
                                                </span>
                                            </td>
                                            <td style={{ padding: '0.75rem 1rem' }}>
                                                <span style={{ padding: '0.2rem 0.6rem', borderRadius: '99px', fontSize: 'var(--text-xs)', fontWeight: 600, background: statusColors.bg, color: statusColors.color }}>
                                                    {status}
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>

                            {sorted.length > 0 && (
                                <tfoot>
                                    <tr style={{ borderTop: '2px solid var(--color-border)', background: 'var(--color-surface)', fontWeight: 700 }}>
                                        <td colSpan={4} style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                            Subtotal — {filtered.length} item{filtered.length !== 1 ? 's' : ''}
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-sm)' }}>
                                            {filteredTotalQty.toFixed(2)}
                                        </td>
                                        <td />
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right', color: 'var(--color-success)', fontSize: 'var(--text-sm)' }}>
                                            {formatCurrency(filteredTotalValue)}
                                        </td>
                                        <td colSpan={2} />
                                    </tr>
                                </tfoot>
                            )}
                        </table>
                    </div>
                </div>
            </main>
        </div>
    );
};

export default StockValuation;
