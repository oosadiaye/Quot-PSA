import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDialog } from '../../hooks/useDialog';
import {
    Package,
    AlertTriangle,
    Plus,
    Pencil,
    Search,
    ChevronLeft,
    ChevronRight,
    Trash2,
} from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import LoadingScreen from '../../components/common/LoadingScreen';
import { useItems, useItemCategories, useDeleteItem } from './hooks/useInventory';
import { useCurrency } from '../../context/CurrencyContext';

// ─── Types ────────────────────────────────────────────────────────────────────

interface InventoryItem {
    id: number;
    sku: string;
    name: string;
    category: number | null;
    category_name?: string;
    total_quantity: number;
    reorder_point: number;
    average_cost: number;
    total_value: number;
    valuation_method: string;
    unit_of_measure: string;
    needs_reorder: boolean;
    is_active: boolean;
}

interface Category {
    id: number;
    name: string;
}

type StockStatus = 'all' | 'in_stock' | 'low_stock' | 'out_of_stock';

// ─── Helpers ──────────────────────────────────────────────────────────────────

const getStockStatus = (item: InventoryItem): 'in_stock' | 'low_stock' | 'out_of_stock' => {
    const qty = Number(item.total_quantity ?? 0);
    if (qty <= 0) return 'out_of_stock';
    if (item.needs_reorder) return 'low_stock';
    return 'in_stock';
};

const STATUS_LABELS: Record<string, string> = {
    in_stock:     'In Stock',
    low_stock:    'Low Stock',
    out_of_stock: 'Out of Stock',
};

const STATUS_COLORS: Record<string, { text: string; bg: string }> = {
    in_stock:     { text: '#10b981', bg: 'rgba(16,185,129,0.12)' },
    low_stock:    { text: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
    out_of_stock: { text: '#ef4444', bg: 'rgba(239,68,68,0.12)' },
};

const METHOD_COLORS: Record<string, { text: string; bg: string }> = {
    WA:   { text: '#3b82f6', bg: 'rgba(59,130,246,0.12)' },
    FIFO: { text: '#10b981', bg: 'rgba(16,185,129,0.12)' },
    LIFO: { text: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
};

const PAGE_SIZE_OPTIONS = [20, 50, 100];

// ─── Component ────────────────────────────────────────────────────────────────

const ItemInventory = () => {
    const navigate = useNavigate();
    const { showConfirm } = useDialog();
    const { formatCurrency } = useCurrency();
    const deleteItem = useDeleteItem();

    // Filters
    const [rawSearch,     setRawSearch]     = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');
    const [statusFilter,  setStatusFilter]  = useState<StockStatus>('all');
    const [categoryFilter, setCategoryFilter] = useState<string>('');
    const [pageSize,      setPageSize]      = useState<number>(20);
    const [currentPage,   setCurrentPage]   = useState(1);

    // Selection
    const [selectedIds,   setSelectedIds]   = useState<Set<number>>(new Set());
    const [isDeleting,    setIsDeleting]    = useState(false);
    const selectAllRef = useRef<HTMLInputElement>(null);

    // Debounce search
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    useEffect(() => {
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => {
            setDebouncedSearch(rawSearch);
            setCurrentPage(1);
        }, 400);
        return () => {
            if (debounceRef.current) clearTimeout(debounceRef.current);
        };
    }, [rawSearch]);

    // Reset page when filters change
    useEffect(() => { setCurrentPage(1); }, [statusFilter, categoryFilter, pageSize]);

    // Clear selection when page/filters change
    useEffect(() => { setSelectedIds(new Set()); }, [currentPage, statusFilter, categoryFilter, debouncedSearch, pageSize]);

    // Data
    const queryFilters: Record<string, string | number> = {
        page:      currentPage,
        page_size: pageSize,
    };
    if (debouncedSearch) queryFilters.search   = debouncedSearch;
    if (categoryFilter)  queryFilters.category = categoryFilter;
    // Note: status filter applied client-side since API doesn't natively support it
    const { data: itemsData, isLoading: itemsLoading } = useItems(queryFilters);
    const { data: categoriesRaw }                      = useItemCategories();

    // Derive list early so selection helpers & effects can run before the loading guard
    const rawList: InventoryItem[]  = Array.isArray(itemsData) ? itemsData : (itemsData?.results ?? []);
    const serverCount: number       = itemsData?.count ?? (Array.isArray(itemsData) ? itemsData.length : 0);
    const categories: Category[]    = Array.isArray(categoriesRaw) ? categoriesRaw : (categoriesRaw?.results ?? []);
    const itemsList: InventoryItem[] = statusFilter === 'all'
        ? rawList
        : rawList.filter(item => getStockStatus(item) === statusFilter);
    const totalPages = Math.ceil(serverCount / pageSize);

    // Selection helpers — computed before early return so hooks below stay stable
    const visibleIds    = itemsList.map(i => i.id);
    const selectedCount = visibleIds.filter(id => selectedIds.has(id)).length;
    const allSelected   = visibleIds.length > 0 && selectedCount === visibleIds.length;
    const someSelected  = selectedCount > 0 && !allSelected;

    // Keep the header checkbox indeterminate when only some rows are ticked
    // MUST stay above the early return to satisfy Rules of Hooks
    useEffect(() => {
        if (selectAllRef.current) {
            selectAllRef.current.indeterminate = someSelected;
        }
    }, [someSelected]);

    if (itemsLoading) {
        return <LoadingScreen message="Loading inventory..." />;
    }

    const toggleSelectAll = () => {
        if (allSelected || someSelected) {
            // Deselect all visible
            setSelectedIds(prev => {
                const next = new Set(prev);
                visibleIds.forEach(id => next.delete(id));
                return next;
            });
        } else {
            // Select all visible
            setSelectedIds(prev => {
                const next = new Set(prev);
                visibleIds.forEach(id => next.add(id));
                return next;
            });
        }
    };

    const toggleRow = (id: number) => {
        setSelectedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    };

    const handleMassDelete = async () => {
        if (selectedIds.size === 0) return;
        const confirmed = await showConfirm(
            `Delete ${selectedIds.size} product${selectedIds.size > 1 ? 's' : ''}? This cannot be undone.`
        );
        if (!confirmed) return;
        setIsDeleting(true);
        try {
            await Promise.all([...selectedIds].map(id => deleteItem.mutateAsync(id)));
            setSelectedIds(new Set());
        } finally {
            setIsDeleting(false);
        }
    };

    // Summary stats (from full server count, approximated from current page data)
    const inStockCount  = rawList.filter(i => getStockStatus(i) === 'in_stock').length;
    const lowStockCount = rawList.filter(i => getStockStatus(i) === 'low_stock').length;
    const pageValue     = rawList.reduce((s, i) => s + Number(i.total_value || 0), 0);

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>

                {/* Header */}
                <PageHeader
                    title="Inventory Ledger"
                    subtitle="Monitor stock levels, costs, and valuation across all warehouses."
                    icon={<Package size={22} />}
                    actions={
                        <button
                            className="btn btn-primary"
                            onClick={() => navigate('/inventory/new')}
                            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: 'var(--text-xs)', padding: '0.5rem 1rem' }}
                        >
                            <Plus size={14} />
                            Create Product
                        </button>
                    }
                />

                {/* ── Summary mini-cards ───────────────────────────────────── */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.1rem', marginBottom: '1.75rem' }}>
                    {[
                        { label: 'Total SKUs',    value: serverCount.toLocaleString(),    color: 'var(--color-primary)' },
                        { label: 'In Stock',      value: inStockCount.toLocaleString(),   color: '#10b981' },
                        { label: 'Low Stock',     value: lowStockCount.toLocaleString(),  color: '#f59e0b' },
                        { label: 'Page Value',    value: formatCurrency(pageValue),       color: '#10b981' },
                    ].map(card => (
                        <div key={card.label} className="card" style={{ padding: '1rem 1.25rem' }}>
                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '0.3rem' }}>
                                {card.label}
                            </div>
                            <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: card.color }}>
                                {card.value}
                            </div>
                        </div>
                    ))}
                </div>

                {/* ── Filters bar ──────────────────────────────────────────── */}
                <div style={{
                    display: 'flex', gap: '0.75rem', alignItems: 'center',
                    marginBottom: '1.5rem', flexWrap: 'wrap',
                }}>
                    {/* Search */}
                    <div style={{ position: 'relative', flex: '1 1 240px', maxWidth: '360px' }}>
                        <Search
                            size={15}
                            style={{
                                position: 'absolute', left: '0.75rem', top: '50%',
                                transform: 'translateY(-50%)', color: 'var(--color-text-muted)',
                                pointerEvents: 'none',
                            }}
                        />
                        <input
                            className="input"
                            type="text"
                            placeholder="Search by name or SKU..."
                            value={rawSearch}
                            onChange={e => setRawSearch(e.target.value)}
                            style={{ paddingLeft: '2.25rem', width: '100%', boxSizing: 'border-box' }}
                        />
                    </div>

                    {/* Status filter */}
                    <select
                        className="input"
                        value={statusFilter}
                        onChange={e => setStatusFilter(e.target.value as StockStatus)}
                        style={{ flex: '0 1 160px' }}
                    >
                        <option value="all">All Status</option>
                        <option value="in_stock">In Stock</option>
                        <option value="low_stock">Low Stock</option>
                        <option value="out_of_stock">Out of Stock</option>
                    </select>

                    {/* Category filter */}
                    <select
                        className="input"
                        value={categoryFilter}
                        onChange={e => setCategoryFilter(e.target.value)}
                        style={{ flex: '0 1 180px' }}
                    >
                        <option value="">All Categories</option>
                        {categories.map(cat => (
                            <option key={cat.id} value={String(cat.id)}>{cat.name}</option>
                        ))}
                    </select>

                    {/* Page size */}
                    <select
                        className="input"
                        value={pageSize}
                        onChange={e => setPageSize(Number(e.target.value))}
                        style={{ flex: '0 0 90px' }}
                    >
                        {PAGE_SIZE_OPTIONS.map(n => (
                            <option key={n} value={n}>{n} / page</option>
                        ))}
                    </select>

                    {/* Mass delete button — only visible when items are selected */}
                    {selectedIds.size > 0 && (
                        <button
                            className="btn btn-danger"
                            onClick={handleMassDelete}
                            disabled={isDeleting}
                            style={{
                                display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                                fontSize: 'var(--text-xs)', padding: '0.5rem 1rem',
                                background: '#ef4444', color: '#fff', border: 'none',
                                borderRadius: '6px', cursor: isDeleting ? 'not-allowed' : 'pointer',
                                opacity: isDeleting ? 0.7 : 1,
                            }}
                        >
                            <Trash2 size={14} />
                            {isDeleting ? 'Deleting…' : `Delete ${selectedIds.size} Selected`}
                        </button>
                    )}
                </div>

                {/* ── Table ───────────────────────────────────────────────── */}
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                {/* Select-all checkbox */}
                                <th style={{ padding: '0.875rem 0.75rem 0.875rem 1rem', width: '36px' }}>
                                    <input
                                        ref={selectAllRef}
                                        type="checkbox"
                                        checked={allSelected}
                                        onChange={toggleSelectAll}
                                        title="Select all on this page"
                                        style={{ cursor: 'pointer', width: '15px', height: '15px', accentColor: 'var(--color-primary)' }}
                                    />
                                </th>
                                {[
                                    { label: 'SKU / Item',         align: 'left'  },
                                    { label: 'Category',           align: 'left'  },
                                    { label: 'Qty on Hand',        align: 'right' },
                                    { label: 'Reorder Point',      align: 'right' },
                                    { label: 'Avg Cost',           align: 'right' },
                                    { label: 'Total Value',        align: 'right' },
                                    { label: 'Method',             align: 'center'},
                                    { label: 'Status',             align: 'center'},
                                    { label: '',                   align: 'right' },
                                ].map(col => (
                                    <th
                                        key={col.label}
                                        style={{
                                            padding: '0.875rem 1rem',
                                            fontSize: 'var(--text-xs)', fontWeight: 600,
                                            textTransform: 'uppercase', color: 'var(--color-text-muted)',
                                            textAlign: col.align as 'left' | 'right' | 'center',
                                            whiteSpace: 'nowrap',
                                        }}
                                    >
                                        {col.label}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {itemsList.length === 0 && (
                                <tr>
                                    <td colSpan={10}>
                                        <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                            <Package size={48} style={{ marginBottom: '1rem', opacity: 0.35 }} />
                                            <div style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: '0.4rem', color: 'var(--color-text)' }}>
                                                No products found
                                            </div>
                                            <div style={{ fontSize: 'var(--text-sm)' }}>
                                                Try adjusting your search or filter criteria.
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            )}
                            {itemsList.map((item, idx) => {
                                const status    = getStockStatus(item);
                                const statusCfg = STATUS_COLORS[status];
                                const qty       = Number(item.total_quantity ?? 0);
                                const reorder   = Number(item.reorder_point   ?? 0);
                                const barPct    = reorder > 0 ? Math.min((qty / reorder) * 100, 100) : (qty > 0 ? 100 : 0);
                                const barColor  = status === 'out_of_stock' ? '#ef4444' : status === 'low_stock' ? '#f59e0b' : '#10b981';
                                const method    = (item.valuation_method ?? '').toUpperCase();
                                const methodCfg = METHOD_COLORS[method] ?? { text: '#6b7280', bg: 'rgba(107,114,128,0.12)' };

                                const isSelected = selectedIds.has(item.id);

                                return (
                                    <tr
                                        key={item.id}
                                        style={{
                                            borderBottom: '1px solid var(--color-border)',
                                            background: isSelected
                                                ? 'rgba(46,56,152,0.06)'
                                                : idx % 2 === 1 ? 'var(--color-surface)' : 'transparent',
                                            transition: 'background 0.1s',
                                        }}
                                    >
                                        {/* Row checkbox */}
                                        <td style={{ padding: '0.875rem 0.75rem 0.875rem 1rem', width: '36px' }}>
                                            <input
                                                type="checkbox"
                                                checked={isSelected}
                                                onChange={() => toggleRow(item.id)}
                                                style={{ cursor: 'pointer', width: '15px', height: '15px', accentColor: 'var(--color-primary)' }}
                                            />
                                        </td>

                                        {/* SKU / Item */}
                                        <td style={{ padding: '0.875rem 1rem' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                                                <div style={{
                                                    width: '30px', height: '30px', borderRadius: '7px',
                                                    background: 'rgba(46,56,152,0.08)',
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                    flexShrink: 0,
                                                }}>
                                                    <Package size={14} color="var(--color-primary)" />
                                                </div>
                                                <div>
                                                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', whiteSpace: 'nowrap' }}>
                                                        {item.name}
                                                    </div>
                                                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontFamily: 'monospace' }}>
                                                        {item.sku}
                                                    </div>
                                                </div>
                                            </div>
                                        </td>

                                        {/* Category */}
                                        <td style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                                            {item.category_name || '—'}
                                        </td>

                                        {/* Qty on Hand */}
                                        <td style={{ padding: '0.875rem 1rem', textAlign: 'right', whiteSpace: 'nowrap' }}>
                                            <span style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: qty <= 0 ? '#ef4444' : 'var(--color-text)' }}>
                                                {qty.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                                            </span>
                                            {item.unit_of_measure && (
                                                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginLeft: '0.25rem' }}>
                                                    {item.unit_of_measure}
                                                </span>
                                            )}
                                        </td>

                                        {/* Reorder Point + mini bar */}
                                        <td style={{ padding: '0.875rem 1rem', textAlign: 'right', minWidth: '120px' }}>
                                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.25rem' }}>
                                                <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                                    {reorder > 0 ? reorder.toLocaleString() : '—'}
                                                </span>
                                                {reorder > 0 && (
                                                    <div style={{ width: '80px', height: '4px', background: 'var(--color-border)', borderRadius: '2px', overflow: 'hidden' }}>
                                                        <div style={{
                                                            height: '100%', width: `${barPct}%`,
                                                            background: barColor, borderRadius: '2px',
                                                            transition: 'width 0.3s ease',
                                                        }} />
                                                    </div>
                                                )}
                                            </div>
                                        </td>

                                        {/* Avg Cost */}
                                        <td style={{ padding: '0.875rem 1rem', textAlign: 'right', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                                            {formatCurrency(Number(item.average_cost || 0))}
                                        </td>

                                        {/* Total Value */}
                                        <td style={{ padding: '0.875rem 1rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 700, color: '#10b981', whiteSpace: 'nowrap' }}>
                                            {formatCurrency(Number(item.total_value || 0))}
                                        </td>

                                        {/* Valuation Method badge */}
                                        <td style={{ padding: '0.875rem 1rem', textAlign: 'center' }}>
                                            {method ? (
                                                <span style={{
                                                    display: 'inline-block',
                                                    padding: '0.2rem 0.55rem', borderRadius: '999px',
                                                    background: methodCfg.bg, color: methodCfg.text,
                                                    fontSize: 'var(--text-xs)', fontWeight: 700, whiteSpace: 'nowrap',
                                                }}>
                                                    {method}
                                                </span>
                                            ) : (
                                                <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>—</span>
                                            )}
                                        </td>

                                        {/* Status badge */}
                                        <td style={{ padding: '0.875rem 1rem', textAlign: 'center', whiteSpace: 'nowrap' }}>
                                            <span style={{
                                                display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                                padding: '0.2rem 0.6rem', borderRadius: '999px',
                                                background: statusCfg.bg, color: statusCfg.text,
                                                fontSize: 'var(--text-xs)', fontWeight: 700,
                                            }}>
                                                {status === 'low_stock' && <AlertTriangle size={11} />}
                                                {STATUS_LABELS[status]}
                                            </span>
                                        </td>

                                        {/* Actions */}
                                        <td style={{ padding: '0.875rem 1rem', textAlign: 'right' }}>
                                            <button
                                                className="btn btn-outline"
                                                onClick={() => navigate(`/inventory/${item.id}`)}
                                                style={{
                                                    display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                                    padding: '0.35rem 0.75rem', fontSize: 'var(--text-xs)',
                                                }}
                                            >
                                                <Pencil size={13} />
                                                Edit
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>

                {/* ── Pagination ───────────────────────────────────────────── */}
                {totalPages > 1 && (
                    <div style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        marginTop: '1.25rem', flexWrap: 'wrap', gap: '0.75rem',
                    }}>
                        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                            Showing page {currentPage} of {totalPages} ({serverCount.toLocaleString()} total)
                        </span>
                        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                            <button
                                className="btn btn-outline"
                                disabled={currentPage <= 1}
                                onClick={() => setCurrentPage(p => p - 1)}
                                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', padding: '0.4rem 0.875rem', fontSize: 'var(--text-sm)' }}
                            >
                                <ChevronLeft size={15} />
                                Previous
                            </button>

                            {/* Page numbers (show up to 7 centered around current) */}
                            {Array.from({ length: totalPages }, (_, i) => i + 1)
                                .filter(p => p === 1 || p === totalPages || Math.abs(p - currentPage) <= 2)
                                .reduce<(number | '...')[]>((acc, p, i, arr) => {
                                    if (i > 0 && (p as number) - (arr[i - 1] as number) > 1) acc.push('...');
                                    acc.push(p);
                                    return acc;
                                }, [])
                                .map((entry, i) =>
                                    entry === '...' ? (
                                        <span key={`ellipsis-${i}`} style={{ padding: '0 0.25rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                            …
                                        </span>
                                    ) : (
                                        <button
                                            key={entry}
                                            onClick={() => setCurrentPage(entry as number)}
                                            style={{
                                                padding: '0.4rem 0.75rem',
                                                borderRadius: '6px', border: '1px solid',
                                                borderColor: currentPage === entry ? 'var(--color-primary)' : 'var(--color-border)',
                                                background: currentPage === entry ? 'var(--color-primary)' : 'transparent',
                                                color: currentPage === entry ? 'white' : 'var(--color-text)',
                                                fontSize: 'var(--text-sm)', fontWeight: currentPage === entry ? 700 : 400,
                                                cursor: 'pointer', minWidth: '36px',
                                            }}
                                        >
                                            {entry}
                                        </button>
                                    )
                                )
                            }

                            <button
                                className="btn btn-outline"
                                disabled={currentPage >= totalPages}
                                onClick={() => setCurrentPage(p => p + 1)}
                                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', padding: '0.4rem 0.875rem', fontSize: 'var(--text-sm)' }}
                            >
                                Next
                                <ChevronRight size={15} />
                            </button>
                        </div>
                    </div>
                )}

            </main>
        </div>
    );
};

export default ItemInventory;
