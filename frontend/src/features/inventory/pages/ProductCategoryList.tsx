import { useState, useMemo } from 'react';
import {
    useProductCategories,
    useProductTypes,
    useCreateProductCategory,
    useUpdateProductCategory,
    useDeleteProductCategory,
} from '../hooks/useInventory';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Layers, Plus, Edit2, Trash2, X, Search } from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

interface Category {
    id: number;
    name: string;
    product_type: number | null;
    parent: number | null;
    product_type_name?: string;
    parent_name?: string;
}

interface ProductType {
    id: number;
    name: string;
    name_display: string;
}

interface CategoryFormData {
    name: string;
    product_type: string;
    parent: string;
}

const EMPTY_FORM: CategoryFormData = { name: '', product_type: '', parent: '' };

// ─── Type badge palette ───────────────────────────────────────────────────────

const TYPE_PALETTE = [
    { bg: 'rgba(59,130,246,0.15)',  color: '#3b82f6' },
    { bg: 'rgba(16,185,129,0.15)',  color: '#10b981' },
    { bg: 'rgba(139,92,246,0.15)', color: '#8b5cf6' },
    { bg: 'rgba(245,158,11,0.15)',  color: '#f59e0b' },
    { bg: 'rgba(239,68,68,0.15)',   color: '#ef4444' },
    { bg: 'rgba(20,184,166,0.15)',  color: '#14b8a6' },
];

function getTypeColor(id: number | null) {
    if (id === null) return { bg: 'rgba(107,114,128,0.15)', color: '#6b7280' };
    return TYPE_PALETTE[id % TYPE_PALETTE.length];
}

// ─── Inline Form (shared by create panel and inline edit row) ─────────────────

interface InlineFormProps {
    initial: CategoryFormData;
    productTypes: ProductType[];
    parentOptions: Category[];
    onSave: (data: CategoryFormData) => void;
    onCancel: () => void;
    isPending: boolean;
    submitLabel: string;
}

const InlineForm = ({
    initial,
    productTypes,
    parentOptions,
    onSave,
    onCancel,
    isPending,
    submitLabel,
}: InlineFormProps) => {
    const [form, setForm] = useState<CategoryFormData>(initial);

    const selectedTypeId = form.product_type ? Number(form.product_type) : null;
    const filteredParents = parentOptions.filter(
        c => !selectedTypeId || c.product_type === selectedTypeId
    );

    return (
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div style={{ flex: '1 1 160px', minWidth: '140px' }}>
                <label style={fieldLabelStyle}>
                    Name <span style={{ color: 'var(--color-error)' }}>*</span>
                </label>
                <input
                    type="text"
                    className="input"
                    value={form.name}
                    onChange={e => setForm({ ...form, name: e.target.value })}
                    placeholder="Category name"
                    autoFocus
                    style={{ width: '100%' }}
                />
            </div>
            <div style={{ flex: '1 1 150px', minWidth: '130px' }}>
                <label style={fieldLabelStyle}>
                    Product Type <span style={{ color: 'var(--color-error)' }}>*</span>
                </label>
                <select
                    className="input"
                    value={form.product_type}
                    onChange={e => setForm({ ...form, product_type: e.target.value, parent: '' })}
                    style={{ width: '100%' }}
                >
                    <option value="">Select type</option>
                    {productTypes.map(pt => (
                        <option key={pt.id} value={String(pt.id)}>
                            {pt.name_display || pt.name}
                        </option>
                    ))}
                </select>
            </div>
            <div style={{ flex: '1 1 150px', minWidth: '130px' }}>
                <label style={fieldLabelStyle}>Parent Category</label>
                <select
                    className="input"
                    value={form.parent}
                    onChange={e => setForm({ ...form, parent: e.target.value })}
                    style={{ width: '100%' }}
                >
                    <option value="">None (top-level)</option>
                    {filteredParents.map(c => (
                        <option key={c.id} value={String(c.id)}>
                            {c.name}
                        </option>
                    ))}
                </select>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', paddingBottom: '0.05rem' }}>
                <button
                    className="btn btn-primary"
                    style={{ padding: '0.5rem 1rem', fontSize: 'var(--text-xs)', whiteSpace: 'nowrap' }}
                    onClick={() => onSave(form)}
                    disabled={isPending || !form.name.trim() || !form.product_type}
                >
                    {isPending ? 'Saving…' : submitLabel}
                </button>
                <button
                    className="btn btn-outline"
                    style={{ padding: '0.5rem 0.75rem', fontSize: 'var(--text-xs)' }}
                    onClick={onCancel}
                >
                    <X size={14} />
                </button>
            </div>
        </div>
    );
};

// ─── Shared label style (module-level so InlineForm can use it) ───────────────

const fieldLabelStyle: React.CSSProperties = {
    display: 'block',
    marginBottom: '0.35rem',
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
    color: 'var(--color-text-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.03em',
};

// ─── Component ────────────────────────────────────────────────────────────────

const ProductCategoryList = () => {
    const { data: categoriesRaw, isLoading } = useProductCategories();
    // useProductTypes() returns a plain array — no need to unpack pagination envelope
    const { data: productTypes = [] }        = useProductTypes();
    const createCategory = useCreateProductCategory();
    const updateCategory = useUpdateProductCategory();
    const deleteCategory = useDeleteProductCategory();

    const [showNewForm, setShowNewForm]       = useState(false);
    const [newForm, setNewForm]               = useState<CategoryFormData>(EMPTY_FORM);
    const [newFormError, setNewFormError]     = useState<string | null>(null);
    const [editingId, setEditingId]           = useState<number | null>(null);
    const [confirmDelete, setConfirmDelete]   = useState<number | null>(null);
    const [deleteBanner, setDeleteBanner]     = useState<string | null>(null);
    const [searchQuery, setSearchQuery]       = useState('');
    const [filterTypeId, setFilterTypeId]     = useState<string>('');

    // ── Normalise API responses ───────────────────────────────────────────────

    const allCats: Category[] = Array.isArray((categoriesRaw as any)?.results)
        ? (categoriesRaw as any).results
        : Array.isArray(categoriesRaw) ? (categoriesRaw as any) : [];

    // ── Summary stats ─────────────────────────────────────────────────────────

    const totalCategories  = allCats.length;
    const rootCategories   = allCats.filter(c => c.parent === null).length;
    const subCategories    = allCats.filter(c => c.parent !== null).length;

    const summaryCards = [
        {
            label: 'Total Categories',
            value: totalCategories,
            color: 'var(--color-primary)',
            bg: 'rgba(46,56,152,0.1)',
        },
        {
            label: 'Root Categories',
            value: rootCategories,
            color: '#10b981',
            bg: 'rgba(16,185,129,0.1)',
        },
        {
            label: 'Subcategories',
            value: subCategories,
            color: '#8b5cf6',
            bg: 'rgba(139,92,246,0.1)',
        },
    ];

    // ── Filter ────────────────────────────────────────────────────────────────

    const filteredCats: Category[] = useMemo(() => {
        let cats = allCats;
        if (filterTypeId) cats = cats.filter(c => String(c.product_type) === filterTypeId);
        if (searchQuery.trim()) {
            const q = searchQuery.trim().toLowerCase();
            cats = cats.filter(c => c.name.toLowerCase().includes(q));
        }
        return cats;
    }, [allCats, filterTypeId, searchQuery]);

    // ── Flat sorted tree: roots first, children grouped under parent ──────────

    type FlatRow = { cat: Category; indented: boolean };

    const flatRows: FlatRow[] = useMemo(() => {
        const roots   = filteredCats.filter(c => c.parent === null);
        const children = filteredCats.filter(c => c.parent !== null);

        const rows: FlatRow[] = [];
        roots.forEach(root => {
            rows.push({ cat: root, indented: false });
            children
                .filter(c => c.parent === root.id)
                .forEach(child => rows.push({ cat: child, indented: true }));
        });

        // Orphan children whose parent was filtered out
        const visibleParentIds = new Set(roots.map(r => r.id));
        children
            .filter(c => !visibleParentIds.has(c.parent as number))
            .forEach(child => rows.push({ cat: child, indented: false }));

        return rows;
    }, [filteredCats]);

    // ── Helpers ───────────────────────────────────────────────────────────────

    const childCountFor = (id: number) => allCats.filter(c => c.parent === id).length;

    const resolveError = (err: any): string => {
        const raw = err?.response?.data;
        return (
            raw?.detail ||
            raw?.error ||
            (typeof raw === 'object' && raw !== null ? JSON.stringify(raw) : null) ||
            err?.message ||
            'An unexpected error occurred.'
        );
    };

    // ── CRUD handlers ─────────────────────────────────────────────────────────

    const handleCreate = async (data: CategoryFormData) => {
        setNewFormError(null);
        try {
            await createCategory.mutateAsync({
                name: data.name.trim(),
                product_type: Number(data.product_type),
                ...(data.parent ? { parent: Number(data.parent) } : {}),
            });
            setNewForm(EMPTY_FORM);
            setShowNewForm(false);
        } catch (err) {
            setNewFormError(resolveError(err));
        }
    };

    const handleUpdate = async (id: number, data: CategoryFormData) => {
        try {
            await updateCategory.mutateAsync({
                id,
                data: {
                    name: data.name.trim(),
                    ...(data.product_type ? { product_type: Number(data.product_type) } : {}),
                    parent: data.parent ? Number(data.parent) : null,
                },
            });
            setEditingId(null);
        } catch (err) {
            setDeleteBanner(resolveError(err));
        }
    };

    const handleDelete = async (id: number) => {
        setDeleteBanner(null);
        try {
            await deleteCategory.mutateAsync(id);
            setConfirmDelete(null);
        } catch (err: any) {
            setDeleteBanner(resolveError(err));
            setConfirmDelete(null);
        }
    };

    // ── Derived options ───────────────────────────────────────────────────────

    const newFormParentOptions = allCats.filter(c => c.parent === null);

    // ── Loading guard (after all hooks) ──────────────────────────────────────

    if (isLoading) return <LoadingScreen message="Loading categories..." />;

    // ── Shared table header style ─────────────────────────────────────────────

    const thStyle: React.CSSProperties = {
        padding: '0.75rem 1rem',
        fontSize: 'var(--text-xs)',
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        color: 'var(--color-text-muted)',
        background: 'var(--color-surface)',
        whiteSpace: 'nowrap',
        textAlign: 'left',
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }} className="animate-fade">

                <PageHeader
                    title="Product Categories"
                    subtitle="Organise items into a hierarchical category structure."
                    icon={<Layers size={22} />}
                    actions={
                        <button
                            className="btn btn-primary"
                            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
                            onClick={() => {
                                setShowNewForm(v => !v);
                                setNewFormError(null);
                                setNewForm(EMPTY_FORM);
                            }}
                        >
                            <Plus size={16} />
                            New Category
                        </button>
                    }
                />

                {/* ── Delete / update error banner ─────────────────────────── */}
                {deleteBanner && (
                    <div style={{
                        padding: '0.75rem 1rem',
                        background: 'rgba(239,68,68,0.08)',
                        color: 'var(--color-error)',
                        border: '1px solid rgba(239,68,68,0.3)',
                        borderRadius: '8px',
                        marginBottom: '1.25rem',
                        fontSize: 'var(--text-sm)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: '1rem',
                    }}>
                        <span>{deleteBanner}</span>
                        <button
                            onClick={() => setDeleteBanner(null)}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-error)', padding: 0, display: 'flex' }}
                        >
                            <X size={16} />
                        </button>
                    </div>
                )}

                {/* ── Summary cards ────────────────────────────────────────── */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1.1rem', marginBottom: '1.75rem' }}>
                    {summaryCards.map(card => (
                        <div key={card.label} className="card" style={{ padding: '1.25rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <div style={{
                                width: '42px', height: '42px', borderRadius: '10px',
                                background: card.bg, display: 'flex', alignItems: 'center',
                                justifyContent: 'center', flexShrink: 0,
                            }}>
                                <Layers size={18} color={card.color} />
                            </div>
                            <div>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '0.2rem' }}>
                                    {card.label}
                                </div>
                                <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: 'var(--color-text)', lineHeight: 1 }}>
                                    {card.value}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>

                {/* ── New Category collapsible form ────────────────────────── */}
                {showNewForm && (
                    <div className="card animate-fade" style={{ marginBottom: '1.75rem', borderTop: '3px solid var(--color-primary)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.1rem' }}>
                            <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0 }}>New Category</h3>
                            <button
                                onClick={() => { setShowNewForm(false); setNewForm(EMPTY_FORM); setNewFormError(null); }}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', display: 'flex', padding: '0.25rem' }}
                            >
                                <X size={18} />
                            </button>
                        </div>

                        {newFormError && (
                            <div style={{
                                padding: '0.6rem 0.875rem',
                                background: 'rgba(239,68,68,0.08)',
                                color: 'var(--color-error)',
                                border: '1px solid rgba(239,68,68,0.25)',
                                borderRadius: '6px',
                                fontSize: 'var(--text-sm)',
                                marginBottom: '1rem',
                            }}>
                                {newFormError}
                            </div>
                        )}

                        <InlineForm
                            initial={newForm}
                            productTypes={productTypes}
                            parentOptions={newFormParentOptions}
                            onSave={handleCreate}
                            onCancel={() => { setShowNewForm(false); setNewForm(EMPTY_FORM); setNewFormError(null); }}
                            isPending={createCategory.isPending}
                            submitLabel="Create Category"
                        />
                    </div>
                )}

                {/* ── Filter bar ───────────────────────────────────────────── */}
                <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem', flexWrap: 'wrap', alignItems: 'center' }}>
                    <div style={{ position: 'relative', flex: '1 1 220px', minWidth: '180px' }}>
                        <Search
                            size={15}
                            style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)', pointerEvents: 'none' }}
                        />
                        <input
                            type="text"
                            className="input"
                            placeholder="Search categories…"
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                            style={{ paddingLeft: '2.25rem', width: '100%' }}
                        />
                    </div>
                    <div style={{ flex: '0 1 200px', minWidth: '160px' }}>
                        <select
                            className="input"
                            value={filterTypeId}
                            onChange={e => setFilterTypeId(e.target.value)}
                            style={{ width: '100%' }}
                        >
                            <option value="">All Product Types</option>
                            {productTypes.map(pt => (
                                <option key={pt.id} value={String(pt.id)}>
                                    {pt.name_display || pt.name}
                                </option>
                            ))}
                        </select>
                    </div>
                    {(searchQuery || filterTypeId) && (
                        <button
                            className="btn btn-outline"
                            style={{ fontSize: 'var(--text-xs)', padding: '0.5rem 0.875rem', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '0.35rem' }}
                            onClick={() => { setSearchQuery(''); setFilterTypeId(''); }}
                        >
                            <X size={13} /> Clear filters
                        </button>
                    )}
                </div>

                {/* ── Table ────────────────────────────────────────────────── */}
                {flatRows.length === 0 ? (
                    <div className="card" style={{ textAlign: 'center', padding: '4rem 2rem' }}>
                        <Layers size={44} style={{ opacity: 0.13, display: 'block', margin: '0 auto 1rem' }} />
                        <div style={{ fontWeight: 600, fontSize: 'var(--text-base)', marginBottom: '0.4rem' }}>
                            No categories configured yet
                        </div>
                        <div style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                            {searchQuery || filterTypeId
                                ? 'No categories match your current filters.'
                                : 'Use the "New Category" button above to get started.'}
                        </div>
                    </div>
                ) : (
                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                                <thead>
                                    <tr style={{ borderBottom: '2px solid var(--color-border)' }}>
                                        <th style={{ ...thStyle }}>Name</th>
                                        <th style={{ ...thStyle }}>Product Type</th>
                                        <th style={{ ...thStyle }}>Parent</th>
                                        <th style={{ ...thStyle, textAlign: 'center' }}>Children</th>
                                        <th style={{ ...thStyle, width: '180px' }}>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {flatRows.map(({ cat, indented }) => {
                                        const isRoot     = !indented && cat.parent === null;
                                        const typeColor  = getTypeColor(cat.product_type);
                                        const typeName   = cat.product_type_name ||
                                            productTypes.find(pt => pt.id === cat.product_type)?.name_display ||
                                            productTypes.find(pt => pt.id === cat.product_type)?.name ||
                                            '—';
                                        const parentName = cat.parent_name ||
                                            (cat.parent ? allCats.find(c => c.id === cat.parent)?.name : null) ||
                                            '—';
                                        const childCount = childCountFor(cat.id);

                                        // ── Inline edit row ───────────────────────────────────────
                                        if (editingId === cat.id) {
                                            const editParentOptions = allCats.filter(
                                                c => c.parent === null && c.id !== cat.id
                                            );
                                            return (
                                                <tr
                                                    key={cat.id}
                                                    style={{
                                                        borderBottom: '1px solid var(--color-border)',
                                                        background: 'rgba(59,130,246,0.04)',
                                                    }}
                                                >
                                                    <td
                                                        colSpan={5}
                                                        style={{ padding: '0.75rem 1rem', paddingLeft: indented ? '2.5rem' : '1rem' }}
                                                    >
                                                        <InlineForm
                                                            initial={{
                                                                name: cat.name,
                                                                product_type: cat.product_type !== null ? String(cat.product_type) : '',
                                                                parent: cat.parent !== null ? String(cat.parent) : '',
                                                            }}
                                                            productTypes={productTypes}
                                                            parentOptions={editParentOptions}
                                                            onSave={data => handleUpdate(cat.id, data)}
                                                            onCancel={() => setEditingId(null)}
                                                            isPending={updateCategory.isPending}
                                                            submitLabel="Save"
                                                        />
                                                    </td>
                                                </tr>
                                            );
                                        }

                                        // ── Normal display row ────────────────────────────────────
                                        return (
                                            <tr
                                                key={cat.id}
                                                style={{
                                                    borderBottom: '1px solid var(--color-border)',
                                                    background: isRoot ? 'rgba(0,0,0,0.018)' : 'transparent',
                                                }}
                                            >
                                                {/* Name */}
                                                <td style={{ padding: '0.75rem 1rem', paddingLeft: indented ? '2.5rem' : '1rem' }}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                        {isRoot
                                                            ? <Layers size={14} style={{ color: 'var(--color-text-muted)', flexShrink: 0 }} />
                                                            : <span style={{ color: 'var(--color-text-muted)', fontSize: '1rem', lineHeight: 1, userSelect: 'none' }}>└</span>
                                                        }
                                                        <span style={{ fontWeight: isRoot ? 700 : 400, fontSize: 'var(--text-sm)' }}>
                                                            {cat.name}
                                                        </span>
                                                        {isRoot && childCount > 0 && (
                                                            <span style={{
                                                                fontSize: 'var(--text-xs)',
                                                                background: 'var(--color-surface)',
                                                                border: '1px solid var(--color-border)',
                                                                borderRadius: '99px',
                                                                padding: '0.1rem 0.5rem',
                                                                color: 'var(--color-text-muted)',
                                                                fontWeight: 600,
                                                            }}>
                                                                {childCount}
                                                            </span>
                                                        )}
                                                    </div>
                                                </td>

                                                {/* Product Type */}
                                                <td style={{ padding: '0.75rem 1rem' }}>
                                                    <span style={{
                                                        padding: '0.2rem 0.65rem',
                                                        borderRadius: '99px',
                                                        fontSize: 'var(--text-xs)',
                                                        fontWeight: 600,
                                                        background: typeColor.bg,
                                                        color: typeColor.color,
                                                    }}>
                                                        {typeName}
                                                    </span>
                                                </td>

                                                {/* Parent */}
                                                <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                                    {parentName}
                                                </td>

                                                {/* Children count */}
                                                <td style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                                    {childCount > 0 ? childCount : '—'}
                                                </td>

                                                {/* Actions */}
                                                <td style={{ padding: '0.75rem 1rem' }}>
                                                    {confirmDelete === cat.id ? (
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-error)', fontWeight: 600 }}>
                                                                Confirm?
                                                            </span>
                                                            <button
                                                                onClick={() => handleDelete(cat.id)}
                                                                style={{
                                                                    background: 'var(--color-error)', color: '#fff', border: 'none',
                                                                    borderRadius: '5px', padding: '0.25rem 0.6rem',
                                                                    fontSize: 'var(--text-xs)', fontWeight: 600, cursor: 'pointer',
                                                                }}
                                                            >
                                                                Yes
                                                            </button>
                                                            <button
                                                                onClick={() => setConfirmDelete(null)}
                                                                style={{
                                                                    background: 'var(--color-surface)', color: 'var(--color-text-muted)',
                                                                    border: '1px solid var(--color-border)', borderRadius: '5px',
                                                                    padding: '0.25rem 0.6rem', fontSize: 'var(--text-xs)', cursor: 'pointer',
                                                                }}
                                                            >
                                                                No
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        <div style={{ display: 'flex', gap: '0.4rem' }}>
                                                            <button
                                                                className="btn btn-outline"
                                                                onClick={() => { setEditingId(cat.id); setConfirmDelete(null); }}
                                                                style={{
                                                                    padding: '0.3rem 0.65rem',
                                                                    fontSize: 'var(--text-xs)',
                                                                    display: 'flex', alignItems: 'center', gap: '0.3rem',
                                                                }}
                                                            >
                                                                <Edit2 size={12} /> Edit
                                                            </button>
                                                            <button
                                                                className="btn btn-outline"
                                                                onClick={() => setConfirmDelete(cat.id)}
                                                                style={{
                                                                    padding: '0.3rem 0.6rem',
                                                                    fontSize: 'var(--text-xs)',
                                                                    color: 'var(--color-error)',
                                                                    display: 'flex', alignItems: 'center', gap: '0.3rem',
                                                                }}
                                                            >
                                                                <Trash2 size={12} />
                                                            </button>
                                                        </div>
                                                    )}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
};

export default ProductCategoryList;
