import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
    Plus, Trash2, FileText, Layers, Info, LayoutGrid,
    ArrowRight, ShieldCheck, Search, Loader2, X,
} from 'lucide-react';
import { useCreateQuotation, useUpdateQuotation, useQuotation, useCustomers, useConvertQuotationToOrder } from '../hooks/useSales';
import { useTaxCodes, useWithholdingTaxes } from '../../accounting/hooks/useAccountingEnhancements';
import { useDimensions } from '../../accounting/hooks/useJournal';
import { useItems } from '../../inventory/hooks/useInventory';
import { useIsDimensionsEnabled } from '../../../hooks/useTenantModules';
import { useCurrency } from '../../../context/CurrencyContext';
import AccountingLayout from '../../accounting/AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import '../../accounting/styles/glassmorphism.css';

interface QuoteLine {
    item: string;
    item_description: string;
    quantity: string;
    unit_price: string;
    discount_percent: string;
}

// ─── Searchable Product Picker ─────────────────────────────────────────────────
// Replaces the plain <select> with a live-filtered combobox.
// - Filters client-side by SKU / name as you type
// - Shows selling_price alongside each result
// - Keyboard navigation: ↑ ↓ Enter Esc
// - isFetching spinner indicates a background refresh is in progress

interface ProductPickerProps {
    value: string;                      // currently selected item id ('' = none)
    onChange: (itemId: string) => void;
    items: any[];
    isFetching: boolean;
    inputStyle: React.CSSProperties;
    formatCurrency: (n: number) => string;
    disabled?: boolean;
}

const ProductPicker: React.FC<ProductPickerProps> = ({
    value, onChange, items, isFetching, inputStyle, formatCurrency, disabled,
}) => {
    const [open,    setOpen]    = useState(false);
    const [query,   setQuery]   = useState('');
    const [cursor,  setCursor]  = useState(-1);
    const containerRef          = useRef<HTMLDivElement>(null);
    const listRef               = useRef<HTMLDivElement>(null);
    const inputRef              = useRef<HTMLInputElement>(null);

    const selectedItem = useMemo(
        () => items.find((i: any) => String(i.id) === value),
        [items, value],
    );

    // Filter list — show first 60 items when no query, otherwise filter by sku/name
    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return items.slice(0, 60);
        return items
            .filter((i: any) =>
                i.sku?.toLowerCase().includes(q) ||
                i.name?.toLowerCase().includes(q) ||
                String(i.id) === q
            )
            .slice(0, 60);
    }, [items, query]);

    // Close on outside click
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setOpen(false);
                setQuery('');
                setCursor(-1);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    // Scroll highlighted item into view
    useEffect(() => {
        if (cursor >= 0 && listRef.current) {
            const el = listRef.current.querySelectorAll<HTMLElement>('[data-item]')[cursor];
            el?.scrollIntoView({ block: 'nearest' });
        }
    }, [cursor]);

    const select = useCallback((id: string) => {
        onChange(id);
        setOpen(false);
        setQuery('');
        setCursor(-1);
    }, [onChange]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (!open) { if (e.key === 'ArrowDown' || e.key === 'Enter') setOpen(true); return; }
        if (e.key === 'Escape')     { setOpen(false); setQuery(''); setCursor(-1); }
        if (e.key === 'ArrowDown')  { e.preventDefault(); setCursor(c => Math.min(c + 1, filtered.length - 1)); }
        if (e.key === 'ArrowUp')    { e.preventDefault(); setCursor(c => Math.max(c - 1, -1)); }
        if (e.key === 'Enter')      { e.preventDefault(); if (cursor >= 0 && filtered[cursor]) select(String(filtered[cursor].id)); }
    };

    const displayText = selectedItem ? `${selectedItem.sku} — ${selectedItem.name}` : '';

    return (
        <div ref={containerRef} style={{ position: 'relative' }}>
            {/* Input row */}
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                <Search
                    size={13}
                    style={{
                        position: 'absolute', left: '9px', top: '50%', transform: 'translateY(-50%)',
                        color: 'var(--color-text-muted)', pointerEvents: 'none', flexShrink: 0,
                    }}
                />
                <input
                    ref={inputRef}
                    type="text"
                    disabled={disabled}
                    placeholder={open ? 'Type SKU or name…' : (displayText || 'Search product…')}
                    value={open ? query : displayText}
                    onChange={e => { setQuery(e.target.value); setCursor(-1); }}
                    onFocus={() => { if (!disabled) { setOpen(true); setQuery(''); setCursor(-1); } }}
                    onKeyDown={handleKeyDown}
                    style={{
                        ...inputStyle,
                        fontSize: 'var(--text-sm)',
                        padding: '0.5rem 2rem 0.5rem 1.75rem',
                        width: '100%',
                    }}
                    autoComplete="off"
                />
                {/* Right-side indicators */}
                <div style={{ position: 'absolute', right: '8px', top: '50%', transform: 'translateY(-50%)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    {isFetching && (
                        <Loader2
                            size={13}
                            style={{ color: '#94a3b8', animation: 'spin 1s linear infinite' }}
                        />
                    )}
                    {value && !disabled && (
                        <button
                            type="button"
                            onClick={e => { e.stopPropagation(); select(''); }}
                            style={{ background: 'none', border: 'none', padding: '1px', cursor: 'pointer', display: 'flex', color: '#94a3b8', lineHeight: 1 }}
                            title="Clear selection"
                        >
                            <X size={13} />
                        </button>
                    )}
                </div>
            </div>

            {/* Dropdown panel */}
            {open && !disabled && (
                <div
                    ref={listRef}
                    style={{
                        position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0, zIndex: 300,
                        background: 'var(--color-surface, #fff)',
                        border: '1.5px solid var(--color-border, #e2e8f0)',
                        borderRadius: '10px',
                        boxShadow: '0 8px 32px rgba(0,0,0,0.12)',
                        maxHeight: '260px', overflowY: 'auto',
                    }}
                >
                    {/* Header: count + live indicator */}
                    <div style={{
                        padding: '7px 12px',
                        borderBottom: '1px solid var(--color-border)',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                        <span style={{ fontSize: '11px', color: 'var(--color-text-muted)', fontWeight: 600 }}>
                            {filtered.length === 0
                                ? 'No products found'
                                : `${filtered.length} product${filtered.length !== 1 ? 's' : ''}${items.length > 60 && !query ? ` of ${items.length}` : ''}`
                            }
                        </span>
                        {isFetching ? (
                            <span style={{ fontSize: '10px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '3px' }}>
                                <Loader2 size={10} style={{ animation: 'spin 1s linear infinite' }} /> Refreshing…
                            </span>
                        ) : (
                            <span style={{ fontSize: '10px', color: '#10b981', fontWeight: 600 }}>● Live</span>
                        )}
                    </div>

                    {/* None / clear row */}
                    <div
                        data-item
                        onClick={() => select('')}
                        style={{
                            padding: '8px 12px',
                            cursor: 'pointer',
                            fontSize: '12px',
                            color: '#94a3b8',
                            borderBottom: '1px solid var(--color-border)',
                            fontStyle: 'italic',
                            background: cursor === -1 ? 'rgba(79,70,229,0.04)' : undefined,
                        }}
                    >
                        — None (free-text description only) —
                    </div>

                    {/* Product rows */}
                    {filtered.length === 0 ? (
                        <div style={{ padding: '16px 12px', textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>
                            {isFetching ? 'Loading products…' : `No products match "${query}"`}
                        </div>
                    ) : (
                        filtered.map((item: any, idx: number) => {
                            const isSelected = String(item.id) === value;
                            const isHighlighted = cursor === idx;
                            return (
                                <div
                                    key={item.id}
                                    data-item
                                    onClick={() => select(String(item.id))}
                                    style={{
                                        padding: '9px 12px',
                                        cursor: 'pointer',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '8px',
                                        borderBottom: '1px solid var(--color-border)',
                                        background: isSelected
                                            ? 'rgba(79,70,229,0.07)'
                                            : isHighlighted
                                            ? 'rgba(79,70,229,0.04)'
                                            : undefined,
                                        transition: 'background 0.1s',
                                    }}
                                    onMouseEnter={() => setCursor(idx)}
                                >
                                    {/* SKU badge */}
                                    <span style={{
                                        flexShrink: 0,
                                        padding: '2px 7px',
                                        borderRadius: '4px',
                                        background: isSelected ? 'rgba(79,70,229,0.15)' : '#f1f5f9',
                                        color: isSelected ? '#4f46e5' : '#64748b',
                                        fontSize: '11px',
                                        fontWeight: 700,
                                        fontFamily: 'monospace',
                                        letterSpacing: '0.02em',
                                    }}>
                                        {item.sku || '—'}
                                    </span>

                                    {/* Name */}
                                    <span style={{
                                        flex: 1,
                                        fontSize: 'var(--text-sm)',
                                        color: 'var(--color-text)',
                                        fontWeight: isSelected ? 600 : 400,
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        whiteSpace: 'nowrap',
                                    }}>
                                        {item.name}
                                    </span>

                                    {/* Price */}
                                    {item.selling_price != null && Number(item.selling_price) > 0 && (
                                        <span style={{
                                            flexShrink: 0,
                                            fontSize: '12px',
                                            color: '#10b981',
                                            fontWeight: 700,
                                        }}>
                                            {formatCurrency(Number(item.selling_price))}
                                        </span>
                                    )}

                                    {/* Selected checkmark */}
                                    {isSelected && (
                                        <span style={{ color: '#4f46e5', fontSize: '14px', fontWeight: 800, flexShrink: 0 }}>✓</span>
                                    )}
                                </div>
                            );
                        })
                    )}
                </div>
            )}
        </div>
    );
};

// ─── Main Form ─────────────────────────────────────────────────────────────────

const QuotationForm = () => {
    const navigate = useNavigate();
    const { id } = useParams<{ id: string }>();
    const editId = id ? Number(id) : undefined;
    const isEdit = Boolean(editId);

    const { data: dims, isLoading: dimsLoading } = useDimensions();
    const { data: customersData } = useCustomers();
    const { isEnabled: dimensionsEnabled } = useIsDimensionsEnabled();
    const { formatCurrency, currencySymbol } = useCurrency();
    const createQuotation = useCreateQuotation();
    const updateQuotation = useUpdateQuotation();
    const convertToOrder  = useConvertQuotationToOrder();
    const { data: taxCodesData } = useTaxCodes({ is_active: true });
    const { data: whtData }      = useWithholdingTaxes({ is_active: true });
    const taxCodesList = Array.isArray(taxCodesData) ? taxCodesData : [];
    const whtList      = Array.isArray(whtData)      ? whtData      : [];

    const { data: existingQuotation, isLoading: quotationLoading } = useQuotation(editId);

    // Fetch ALL items at max page size so the product picker has the full catalog.
    // page_size=500 matches the raised backend max; isFetching drives the live-refresh spinner.
    const { data: itemsData, isFetching: itemsFetching, dataUpdatedAt } = useItems({ page_size: 500 });
    const customers = customersData?.results || customersData || [];
    const itemsList = itemsData?.results    || itemsData    || [];

    const [header, setHeader] = useState({
        quotation_number: '',
        customer: '',
        quotation_date: new Date().toISOString().split('T')[0],
        valid_until: '',
        notes: '',
        terms: '',
        fund: '',
        function: '',
        program: '',
        geo: '',
        tax_code: '' as string | number,
        wht_exempt: false,
    });

    const [lines, setLines] = useState<QuoteLine[]>([
        { item: '', item_description: '', quantity: '1', unit_price: '0', discount_percent: '0' },
    ]);

    const [formError,    setFormError]    = useState('');
    const [convertError, setConvertError] = useState('');

    // Populate form when editing an existing quotation
    useEffect(() => {
        if (!existingQuotation) return;
        setHeader({
            quotation_number: existingQuotation.quotation_number || '',
            customer:         String(existingQuotation.customer ?? ''),
            quotation_date:   existingQuotation.quotation_date || new Date().toISOString().split('T')[0],
            valid_until:      existingQuotation.valid_until || '',
            notes:            existingQuotation.notes  || '',
            terms:            existingQuotation.terms  || '',
            fund:             existingQuotation.fund     ? String(existingQuotation.fund)     : '',
            function:         existingQuotation.function ? String(existingQuotation.function) : '',
            program:          existingQuotation.program  ? String(existingQuotation.program)  : '',
            geo:              existingQuotation.geo       ? String(existingQuotation.geo)      : '',
            tax_code:         existingQuotation.tax_code  ? String(existingQuotation.tax_code) : '',
            wht_exempt:       existingQuotation.wht_exempt ?? false,
        });
        if (existingQuotation.lines?.length) {
            setLines(existingQuotation.lines.map((l: any) => ({
                item:              l.item  ? String(l.item) : '',
                item_description:  l.item_description || '',
                quantity:          String(l.quantity         ?? '1'),
                unit_price:        String(l.unit_price       ?? '0'),
                discount_percent:  String(l.discount_percent ?? '0'),
            })));
        }
    }, [existingQuotation]);

    const totalAmount = useMemo(() => {
        return lines.reduce((sum, l) => {
            const qty  = parseFloat(l.quantity         || '0');
            const price = parseFloat(l.unit_price      || '0');
            const disc  = parseFloat(l.discount_percent || '0');
            return sum + qty * price * (1 - disc / 100);
        }, 0);
    }, [lines]);

    const addLine    = () => setLines([...lines, { item: '', item_description: '', quantity: '1', unit_price: '0', discount_percent: '0' }]);
    const removeLine = (index: number) => setLines(lines.filter((_, i) => i !== index));

    const updateLine = (index: number, field: keyof QuoteLine, value: string) => {
        const newLines = [...lines];
        newLines[index][field] = value;
        // When a product is selected, auto-fill description and unit price
        if (field === 'item' && value) {
            const selectedItem = itemsList.find((i: any) => String(i.id) === value);
            if (selectedItem) {
                newLines[index].item_description = selectedItem.name;
                if (selectedItem.selling_price) {
                    newLines[index].unit_price = String(selectedItem.selling_price);
                }
            }
        }
        // When a product is cleared, reset description and price
        if (field === 'item' && !value) {
            newLines[index].item_description = '';
            newLines[index].unit_price       = '0';
        }
        setLines(newLines);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        const payload: any = {
            quotation_number: header.quotation_number || undefined,
            customer:         header.customer,
            quotation_date:   header.quotation_date,
            valid_until:      header.valid_until,
            notes:            header.notes,
            terms:            header.terms,
            tax_code:         header.tax_code ? Number(header.tax_code) : null,
            wht_exempt:       header.wht_exempt,
            lines: lines.map(l => ({
                item_description: l.item_description,
                quantity:         parseFloat(l.quantity),
                unit_price:       parseFloat(l.unit_price),
                discount_percent: parseFloat(l.discount_percent || '0'),
                ...(l.item ? { item: Number(l.item) } : {}),
            })),
            ...(dimensionsEnabled ? {
                fund:     header.fund     ? Number(header.fund)     : null,
                function: header.function ? Number(header.function) : null,
                program:  header.program  ? Number(header.program)  : null,
                geo:      header.geo      ? Number(header.geo)      : null,
            } : {}),
        };

        if (!isEdit) payload.status = 'Draft';

        try {
            if (isEdit && editId) {
                await updateQuotation.mutateAsync({ id: editId, data: payload });
            } else {
                await createQuotation.mutateAsync(payload);
            }
            navigate('/sales/quotations');
        } catch (err: any) {
            const data = err.response?.data;
            if (data?.detail) {
                setFormError(data.detail);
            } else if (data && typeof data === 'object') {
                const messages = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`);
                setFormError(messages.join(' | ') || 'Failed to save quotation.');
            } else {
                setFormError(err.message || 'Failed to save quotation.');
            }
        }
    };

    const isPending = createQuotation.isPending || updateQuotation.isPending;

    const handleConvert = () => {
        if (!editId) return;
        setConvertError('');
        convertToOrder.mutate(editId, {
            onSuccess: (data: any) => {
                navigate(data?.data?.order_id ? `/sales/orders` : '/sales/orders');
            },
            onError: (err: any) => {
                const d = err.response?.data;
                setConvertError(d?.error || d?.detail || 'Conversion failed.');
            },
        });
    };

    const isConverted = existingQuotation?.status === 'Converted';

    // Human-readable "Updated HH:MM:SS" label
    const updatedLabel = dataUpdatedAt
        ? new Date(dataUpdatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
        : null;

    if (dimsLoading || (isEdit && quotationLoading)) {
        return (
            <AccountingLayout>
                <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                    Loading form data…
                </div>
            </AccountingLayout>
        );
    }

    // ── Shared style tokens ──────────────────────────────────────────────────────
    const labelStyle: React.CSSProperties = {
        display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)',
        fontWeight: 600, color: 'var(--color-text-secondary, #64748b)',
    };

    const inputStyle: React.CSSProperties = {
        width: '100%', padding: '0.625rem 0.875rem', borderRadius: '8px',
        border: '2.5px solid var(--color-border, #e2e8f0)', background: 'var(--color-background, #fff)',
        color: 'var(--color-text, #1e293b)', fontSize: 'var(--text-sm)',
        outline: 'none', transition: 'border-color 0.15s', boxSizing: 'border-box',
    };

    const selectStyle: React.CSSProperties = { ...inputStyle, appearance: 'auto' as any };

    const sectionHeaderStyle: React.CSSProperties = {
        display: 'flex', alignItems: 'center', gap: '0.5rem',
        fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text, #1e293b)',
        marginBottom: '1.5rem',
    };

    const iconBoxStyle: React.CSSProperties = {
        width: '28px', height: '28px', borderRadius: '6px',
        background: 'rgba(79, 70, 229, 0.1)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', flexShrink: 0,
    };

    const thStyle: React.CSSProperties = {
        padding: '0.5rem 0.5rem 0.75rem', textAlign: 'left', fontSize: 'var(--text-xs)',
        fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
        color: 'var(--color-text-muted)',
    };

    return (
        <AccountingLayout>
            <form onSubmit={handleSubmit}>
                <PageHeader
                    title={isEdit ? `Edit Quotation${existingQuotation?.quotation_number ? ` — ${existingQuotation.quotation_number}` : ''}` : 'New Quotation'}
                    subtitle={isEdit ? 'Update quotation details and line items.' : 'Create a new sales quotation for a customer.'}
                    icon={<FileText size={22} color="white" />}
                    onBack={() => navigate('/sales/quotations')}
                    actions={
                        <>
                            <button type="button" className="btn" onClick={() => navigate('/sales/quotations')}
                                style={{ padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px', color: 'white', background: 'transparent', border: '1px solid rgba(255,255,255,0.4)' }}>
                                Cancel
                            </button>
                            {isEdit && !isConverted && (
                                <button
                                    type="button"
                                    onClick={handleConvert}
                                    disabled={convertToOrder.isPending}
                                    style={{
                                        padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px',
                                        background: 'rgba(255,255,255,0.25)', color: 'white',
                                        border: '1px solid rgba(255,255,255,0.5)',
                                        cursor: convertToOrder.isPending ? 'not-allowed' : 'pointer',
                                        display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                                        opacity: convertToOrder.isPending ? 0.7 : 1,
                                    }}
                                >
                                    <ArrowRight size={16} />
                                    {convertToOrder.isPending ? 'Converting…' : 'Convert to SO'}
                                </button>
                            )}
                            <button type="submit" className="btn btn-primary" disabled={isPending || lines.length === 0}
                                style={{ padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px', background: 'rgba(255,255,255,0.2)', color: 'white', border: '1px solid rgba(255,255,255,0.3)' }}>
                                {isPending ? 'Saving…' : isEdit ? 'Update Quotation' : 'Save Quotation'}
                            </button>
                        </>
                    }
                />

                {formError && (
                    <div style={{ padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626', borderRadius: '8px', marginBottom: '1.5rem', fontSize: 'var(--text-sm)' }}>
                        {formError}
                    </div>
                )}
                {convertError && (
                    <div style={{ padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626', borderRadius: '8px', marginBottom: '1.5rem', fontSize: 'var(--text-sm)' }}>
                        Conversion failed: {convertError}
                    </div>
                )}

                {/* Layout */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: '1.5rem', alignItems: 'start' }}>

                    {/* ── MAIN COLUMN ───────────────────────────────────────── */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                        {/* Quotation Details Card */}
                        <div className="card" style={{ padding: '1.75rem' }}>
                            <div style={sectionHeaderStyle}>
                                <span style={iconBoxStyle}><FileText size={16} color="#4f46e5" /></span>
                                Quotation Details
                            </div>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                    <div>
                                        <label style={labelStyle}>Quote Number</label>
                                        <input style={inputStyle} type="text" placeholder="Auto-generated if empty"
                                            value={header.quotation_number}
                                            onChange={e => setHeader({ ...header, quotation_number: e.target.value })} />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Customer<span className="required-mark"> *</span></label>
                                        <select style={selectStyle} value={header.customer}
                                            onChange={e => setHeader({ ...header, customer: e.target.value })} required>
                                            <option value="">Select Customer</option>
                                            {customers?.map((c: any) => (
                                                <option key={c.id} value={c.id}>{c.name}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>

                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                    <div>
                                        <label style={labelStyle}>Quote Date<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="date" value={header.quotation_date}
                                            onChange={e => setHeader({ ...header, quotation_date: e.target.value })} required />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Valid Until<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="date" value={header.valid_until}
                                            onChange={e => setHeader({ ...header, valid_until: e.target.value })} required />
                                    </div>
                                </div>

                                <div>
                                    <label style={labelStyle}>Notes</label>
                                    <textarea
                                        style={{ ...inputStyle, minHeight: '70px', resize: 'vertical', fontFamily: 'inherit' }}
                                        placeholder="Additional notes…"
                                        value={header.notes}
                                        onChange={e => setHeader({ ...header, notes: e.target.value })}
                                    />
                                </div>

                                <div>
                                    <label style={labelStyle}>Terms &amp; Conditions</label>
                                    <textarea
                                        style={{ ...inputStyle, minHeight: '70px', resize: 'vertical', fontFamily: 'inherit' }}
                                        placeholder="Terms and conditions…"
                                        value={header.terms}
                                        onChange={e => setHeader({ ...header, terms: e.target.value })}
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Line Items Card */}
                        <div className="card" style={{ padding: '1.75rem' }}>
                            {/* Section header + live product status */}
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
                                <div style={sectionHeaderStyle as any}>
                                    <span style={iconBoxStyle}><LayoutGrid size={16} color="#4f46e5" /></span>
                                    Line Items
                                </div>
                                {/* Live product catalog indicator */}
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--color-text-muted)' }}>
                                    {itemsFetching ? (
                                        <>
                                            <Loader2 size={11} style={{ animation: 'spin 1s linear infinite', color: '#94a3b8' }} />
                                            <span>Loading products…</span>
                                        </>
                                    ) : (
                                        <>
                                            <span style={{ color: '#10b981', fontWeight: 700 }}>●</span>
                                            <span style={{ fontWeight: 600, color: '#10b981' }}>{itemsList.length} products</span>
                                            {updatedLabel && <span>· Updated {updatedLabel}</span>}
                                        </>
                                    )}
                                </div>
                            </div>

                            <div style={{ overflowX: 'auto' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                    <thead>
                                        <tr>
                                            <th style={{ ...thStyle, width: '220px' }}>Product</th>
                                            <th style={thStyle}>Item Description</th>
                                            <th style={{ ...thStyle, width: '90px' }}>Qty</th>
                                            <th style={{ ...thStyle, width: '130px' }}>Unit Price</th>
                                            <th style={{ ...thStyle, width: '90px' }}>Disc %</th>
                                            <th style={{ ...thStyle, width: '110px', textAlign: 'right' }}>Total</th>
                                            <th style={{ width: '36px' }}></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {lines.map((line, idx) => {
                                            const qty       = parseFloat(line.quantity         || '0');
                                            const price     = parseFloat(line.unit_price        || '0');
                                            const disc      = parseFloat(line.discount_percent  || '0');
                                            const lineTotal = qty * price * (1 - disc / 100);
                                            return (
                                                <tr key={idx}>
                                                    {/* Product picker replaces plain <select> */}
                                                    <td style={{ padding: '0.35rem 0.35rem 0.35rem 0', verticalAlign: 'top' }}>
                                                        <ProductPicker
                                                            value={line.item}
                                                            onChange={itemId => updateLine(idx, 'item', itemId)}
                                                            items={itemsList}
                                                            isFetching={itemsFetching}
                                                            inputStyle={inputStyle}
                                                            formatCurrency={formatCurrency}
                                                        />
                                                    </td>
                                                    <td style={{ padding: '0.35rem', verticalAlign: 'top' }}>
                                                        <input
                                                            style={{ ...inputStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem' }}
                                                            type="text"
                                                            placeholder="Item description"
                                                            value={line.item_description}
                                                            onChange={e => updateLine(idx, 'item_description', e.target.value)}
                                                            required
                                                        />
                                                    </td>
                                                    <td style={{ padding: '0.35rem', verticalAlign: 'top' }}>
                                                        <input
                                                            style={{ ...inputStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem' }}
                                                            type="number" step="1" min="1"
                                                            value={line.quantity}
                                                            onChange={e => updateLine(idx, 'quantity', e.target.value)}
                                                            required
                                                        />
                                                    </td>
                                                    <td style={{ padding: '0.35rem', verticalAlign: 'top' }}>
                                                        <div style={{ position: 'relative' }}>
                                                            <span style={{
                                                                position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)',
                                                                fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, pointerEvents: 'none',
                                                            }}>{currencySymbol}</span>
                                                            <input
                                                                style={{ ...inputStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem 0.5rem 1.5rem' }}
                                                                type="number" step="0.01" min="0"
                                                                value={line.unit_price}
                                                                onChange={e => updateLine(idx, 'unit_price', e.target.value)}
                                                                required
                                                            />
                                                        </div>
                                                    </td>
                                                    <td style={{ padding: '0.35rem', verticalAlign: 'top' }}>
                                                        <input
                                                            style={{ ...inputStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem' }}
                                                            type="number" step="0.01" min="0" max="100"
                                                            value={line.discount_percent}
                                                            onChange={e => updateLine(idx, 'discount_percent', e.target.value)}
                                                        />
                                                    </td>
                                                    <td style={{ padding: '0.35rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', verticalAlign: 'middle' }}>
                                                        {formatCurrency(lineTotal)}
                                                    </td>
                                                    <td style={{ padding: '0.35rem', textAlign: 'center', verticalAlign: 'middle' }}>
                                                        {lines.length > 1 && (
                                                            <button type="button" onClick={() => removeLine(idx)}
                                                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: '4px' }}>
                                                                <Trash2 size={16} />
                                                            </button>
                                                        )}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                    <tfoot>
                                        <tr>
                                            <td colSpan={5} style={{ padding: '0.75rem 0.35rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)', color: 'var(--color-text)', borderTop: '2px solid var(--color-border, #e2e8f0)' }}>
                                                Total:
                                            </td>
                                            <td style={{ padding: '0.75rem 0.35rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)', color: '#4f46e5', borderTop: '2px solid var(--color-border, #e2e8f0)' }}>
                                                {formatCurrency(totalAmount)}
                                            </td>
                                            <td style={{ borderTop: '2px solid var(--color-border, #e2e8f0)' }}></td>
                                        </tr>
                                    </tfoot>
                                </table>
                            </div>

                            <button type="button" onClick={addLine}
                                style={{
                                    background: 'none', border: 'none', cursor: 'pointer',
                                    color: '#4f46e5', fontSize: 'var(--text-sm)', fontWeight: 600,
                                    display: 'flex', alignItems: 'center', gap: '0.35rem',
                                    marginTop: '1rem', padding: 0,
                                }}>
                                <Plus size={16} /> Add Line Item
                            </button>
                        </div>
                    </div>

                    {/* ── RIGHT COLUMN ─────────────────────────────────────── */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                        {/* Dimensions Card */}
                        {dimensionsEnabled && (
                            <div className="card" style={{ padding: '1.75rem' }}>
                                <div style={sectionHeaderStyle}>
                                    <span style={iconBoxStyle}><Layers size={16} color="#4f46e5" /></span>
                                    Dimensions
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                                    <div>
                                        <label style={labelStyle}>Fund<span className="required-mark"> *</span></label>
                                        <select style={selectStyle} value={header.fund}
                                            onChange={e => setHeader({ ...header, fund: e.target.value })} required>
                                            <option value="">Select Fund</option>
                                            {dims?.funds?.map((f: any) => <option key={f.id} value={f.id}>{f.code} - {f.name}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Function<span className="required-mark"> *</span></label>
                                        <select style={selectStyle} value={header.function}
                                            onChange={e => setHeader({ ...header, function: e.target.value })} required>
                                            <option value="">Select Function</option>
                                            {dims?.functions?.map((f: any) => <option key={f.id} value={f.id}>{f.code} - {f.name}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Program<span className="required-mark"> *</span></label>
                                        <select style={selectStyle} value={header.program}
                                            onChange={e => setHeader({ ...header, program: e.target.value })} required>
                                            <option value="">Select Program</option>
                                            {dims?.programs?.map((p: any) => <option key={p.id} value={p.id}>{p.code} - {p.name}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Geography (Geo)<span className="required-mark"> *</span></label>
                                        <select style={selectStyle} value={header.geo}
                                            onChange={e => setHeader({ ...header, geo: e.target.value })} required>
                                            <option value="">Select Geo</option>
                                            {dims?.geos?.map((g: any) => <option key={g.id} value={g.id}>{g.code} - {g.name}</option>)}
                                        </select>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Summary Card */}
                        <div style={{
                            borderRadius: '12px', padding: '1.75rem',
                            background: 'linear-gradient(135deg, #4f46e5 0%, #6366f1 50%, #7c3aed 100%)',
                            color: '#fff',
                        }}>
                            <p style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '0.35rem', opacity: 0.85 }}>
                                Quotation Summary
                            </p>
                            <p style={{ fontSize: 'var(--text-xs)', opacity: 0.8, marginBottom: '0.5rem' }}>
                                Total Amount
                            </p>
                            <p style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: '-0.025em', marginBottom: '1.25rem' }}>
                                {formatCurrency(totalAmount)}
                            </p>
                            <div style={{ borderTop: '1px solid rgba(255,255,255,0.2)', paddingTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                    <span style={{ opacity: 0.85 }}>Line Items</span>
                                    <span style={{ fontWeight: 600 }}>{lines.length}</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                    <span style={{ opacity: 0.85 }}>Customer</span>
                                    <span style={{ fontWeight: 600 }}>
                                        {header.customer
                                            ? (customers.find((c: any) => String(c.id) === header.customer)?.name || '—')
                                            : '—'}
                                    </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                    <span style={{ opacity: 0.85 }}>Status</span>
                                    <span style={{ fontWeight: 600 }}>{isEdit ? (existingQuotation?.status || 'Draft') : 'Draft'}</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                    <span style={{ opacity: 0.85 }}>Catalog</span>
                                    <span style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                                        {itemsFetching
                                            ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} />
                                            : <span style={{ color: '#a5f3d0' }}>●</span>
                                        }
                                        {itemsList.length} items
                                    </span>
                                </div>
                            </div>

                            {totalAmount > 0 && !isEdit && (
                                <div style={{
                                    marginTop: '1.25rem', padding: '0.75rem', borderRadius: '8px',
                                    background: 'rgba(255,255,255,0.15)',
                                    display: 'flex', alignItems: 'center', gap: '0.5rem',
                                    fontSize: 'var(--text-xs)',
                                }}>
                                    <Info size={16} style={{ flexShrink: 0, opacity: 0.9 }} />
                                    <span>Quotation will be saved as Draft. Send to customer after review.</span>
                                </div>
                            )}
                        </div>

                        {/* Tax & WHT Card */}
                        <div className="card" style={{ padding: '1.5rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
                                <ShieldCheck size={16} color="#4f46e5" />
                                <span style={{ fontWeight: 700, fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>Tax &amp; WHT</span>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                <div>
                                    <label style={labelStyle}>VAT Tax Code</label>
                                    <select style={selectStyle} value={String(header.tax_code)}
                                        onChange={e => setHeader({ ...header, tax_code: e.target.value })}>
                                        <option value="">— No tax code —</option>
                                        {taxCodesList.filter((tc: any) => tc.direction !== 'purchase').map((tc: any) => (
                                            <option key={tc.id} value={tc.id}>{tc.code} — {tc.name} ({tc.rate}%)</option>
                                        ))}
                                    </select>
                                </div>
                                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                                    <input type="checkbox" checked={header.wht_exempt}
                                        onChange={e => setHeader({ ...header, wht_exempt: e.target.checked })} />
                                    <span style={{ fontSize: 'var(--text-sm)' }}>WHT Exempt on this transaction</span>
                                </label>
                            </div>
                        </div>
                    </div>
                </div>
            </form>
        </AccountingLayout>
    );
};

export default QuotationForm;
