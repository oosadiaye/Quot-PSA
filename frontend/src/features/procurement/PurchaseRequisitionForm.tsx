import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Plus, Trash2, FileText, Layers, Info, LayoutGrid, Building2, Package } from 'lucide-react';
import { useCreatePR, useUpdatePR, usePurchaseRequest } from './hooks/useProcurement';
import { useDimensions } from '../accounting/hooks/useJournal';
import { useFixedAssets } from '../accounting/hooks/useAccountingEnhancements';
import { useItems } from '../inventory/hooks/useInventory';
import { useMDAs, useAccounts } from '../accounting/hooks/useBudgetDimensions';
import { useIsDimensionsEnabled } from '../../hooks/useTenantModules';
import { useCurrency } from '../../context/CurrencyContext';
import SearchableSelect from '../../components/SearchableSelect';
import { safeAdd, safeMultiply } from '../accounting/utils/currency';
import AccountingLayout from '../accounting/AccountingLayout';
import PageHeader from '../../components/PageHeader';
import '../accounting/styles/glassmorphism.css';

type LineType = 'expense' | 'asset' | 'item';

interface PRLine {
    id: string;
    line_type: LineType;
    item_description: string;
    quantity: string;
    estimated_unit_price: string;
    account: string;
    asset: string;
    item: string;
}

const LINE_TYPE_CONFIG: Record<LineType, { label: string; bg: string; color: string; border: string }> = {
    expense: { label: 'Expense', bg: '#eff6ff', color: '#2563eb', border: '#bfdbfe' },
    asset:   { label: 'Asset',   bg: '#faf5ff', color: '#7c3aed', border: '#ddd6fe' },
    item:    { label: 'Item',    bg: '#ecfdf5', color: '#059669', border: '#a7f3d0' },
};

const newLine = (type: LineType = 'expense'): PRLine => ({
    id: crypto.randomUUID(),
    line_type: type,
    item_description: '',
    quantity: '1',
    estimated_unit_price: '0',
    account: '',
    asset: '',
    item: '',
});

const PurchaseRequisitionForm = () => {
    const navigate = useNavigate();
    const { id: editId } = useParams<{ id?: string }>();
    const isEditMode = !!editId;

    const { data: dims, isLoading: dimsLoading } = useDimensions();
    const { data: assets } = useFixedAssets({ status: 'Active' });
    const { data: itemsData } = useItems();
    const itemsList = itemsData?.results || itemsData || [];
    const { data: mdas } = useMDAs({ is_active: true });
    const { data: expenseAccounts } = useAccounts({ account_type: 'Expense' });
    const { isEnabled: dimensionsEnabled } = useIsDimensionsEnabled();
    const { formatCurrency, currencySymbol } = useCurrency();
    const createPR = useCreatePR();
    const updatePR = useUpdatePR();
    const { data: existingPR, isLoading: existingLoading } = usePurchaseRequest(editId ? Number(editId) : null);

    const [header, setHeader] = useState({
        description: '',
        mda: '',
        requested_date: new Date().toISOString().split('T')[0],
        required_date: '',
        fund: '',
        function: '',
        program: '',
        geo: '',
    });

    const [lines, setLines] = useState<PRLine[]>([newLine('expense')]);
    const [formError, setFormError] = useState('');
    const [createdPR, setCreatedPR] = useState<{ request_number: string; id: number } | null>(null);

    // Populate form when editing an existing PR
    useEffect(() => {
        if (!existingPR) return;
        setHeader({
            description: existingPR.description || '',
            mda: existingPR.mda ? String(existingPR.mda) : '',
            requested_date: existingPR.requested_date || new Date().toISOString().split('T')[0],
            required_date: existingPR.required_date || '',
            fund: existingPR.fund ? String(existingPR.fund) : '',
            function: existingPR.function ? String(existingPR.function) : '',
            program: existingPR.program ? String(existingPR.program) : '',
            geo: existingPR.geo ? String(existingPR.geo) : '',
        });
        if (existingPR.lines?.length) {
            setLines(existingPR.lines.map((l: any) => ({
                id: String(l.id || crypto.randomUUID()),
                line_type: l.asset ? 'asset' : l.item ? 'item' : 'expense',
                item_description: l.item_description || '',
                quantity: String(l.quantity ?? '1'),
                estimated_unit_price: String(l.estimated_unit_price ?? '0'),
                account: l.account ? String(l.account) : '',
                asset: l.asset ? String(l.asset) : '',
                item: l.item ? String(l.item) : '',
            })));
        }
    }, [existingPR]);

    const totalEstimated = useMemo(() => {
        return lines.reduce((sum, l) => {
            return safeAdd(sum, safeMultiply(l.quantity || '0', l.estimated_unit_price || '0'));
        }, 0);
    }, [lines]);

    const addLine = (type: LineType = 'expense') => setLines([...lines, newLine(type)]);
    const removeLine = (index: number) => setLines(lines.filter((_, i) => i !== index));

    const updateLine = (index: number, field: keyof PRLine, value: string) => {
        const newLines = [...lines];
        (newLines[index] as any)[field] = value;
        if (field === 'item' && value) {
            const selectedItem = itemsList.find((i: any) => String(i.id) === value);
            if (selectedItem) {
                newLines[index].item_description = selectedItem.name;
                if (selectedItem.unit_price) newLines[index].estimated_unit_price = String(selectedItem.unit_price);
            }
        }
        if (field === 'asset' && value) {
            const selectedAsset = (assets || []).find((a: any) => String(a.id) === value);
            if (selectedAsset) {
                newLines[index].item_description = selectedAsset.name;
            }
        }
        if (field === 'account' && value) {
            const selectedAcct = (expenseAccounts || []).find((a: any) => String(a.id) === value);
            if (selectedAcct && !newLines[index].item_description) {
                newLines[index].item_description = selectedAcct.name;
            }
        }
        setLines(newLines);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        if (!header.mda) {
            setFormError('MDA (Ministry/Department/Agency) is required.');
            return;
        }

        const payload: any = {
            description: header.description,
            mda: Number(header.mda),
            requested_date: header.requested_date,
            ...(header.required_date ? { required_date: header.required_date } : {}),
            lines: lines.map(l => ({
                item_description: l.item_description,
                quantity: parseFloat(l.quantity),
                estimated_unit_price: parseFloat(l.estimated_unit_price),
                ...(l.account ? { account: Number(l.account) } : {}),
                ...(l.asset ? { asset: Number(l.asset) } : {}),
                ...(l.item ? { item: Number(l.item) } : {}),
            })),
            ...(dimensionsEnabled ? {
                fund: header.fund ? Number(header.fund) : null,
                function: header.function ? Number(header.function) : null,
                program: header.program ? Number(header.program) : null,
                geo: header.geo ? Number(header.geo) : null,
            } : {}),
        };

        try {
            if (isEditMode && editId) {
                const result = await updatePR.mutateAsync({ id: Number(editId), data: payload });
                setCreatedPR({ request_number: result.request_number, id: result.id });
            } else {
                const result = await createPR.mutateAsync(payload);
                setCreatedPR({ request_number: result.request_number, id: result.id });
            }
        } catch (err: any) {
            const data = err.response?.data;
            if (data?.detail) {
                setFormError(data.detail);
            } else if (data && typeof data === 'object') {
                const messages = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`);
                setFormError(messages.join(' | ') || `Failed to ${isEditMode ? 'update' : 'create'} requisition.`);
            } else {
                setFormError(err.message || `Failed to ${isEditMode ? 'update' : 'create'} requisition.`);
            }
        }
    };

    if (dimsLoading || (isEditMode && existingLoading)) return <AccountingLayout><div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>Loading{isEditMode ? ' requisition' : ' form data'}...</div></AccountingLayout>;

    const labelStyle: React.CSSProperties = {
        display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)',
        fontWeight: 600, color: 'var(--color-text-secondary, #64748b)',
    };
    const inputStyle: React.CSSProperties = {
        width: '100%', padding: '0.625rem 0.875rem', borderRadius: '8px',
        border: '2.5px solid var(--color-border, #e2e8f0)', background: 'var(--color-background, #fff)',
        color: 'var(--color-text, #1e293b)', fontSize: 'var(--text-sm)',
        outline: 'none', transition: 'border-color 0.15s',
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
                    title={isEditMode ? 'Edit Purchase Requisition' : 'New Purchase Requisition'}
                    subtitle={isEditMode ? 'Update the requisition details below.' : 'Create a purchase requisition with MDA and dimension tagging.'}
                    icon={<FileText size={22} />}
                    onBack={() => navigate('/procurement/requisitions')}
                    actions={
                        <>
                            <button type="button" className="btn btn-outline" onClick={() => navigate('/procurement/requisitions')}
                                style={{ padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px', color: 'white', border: '1.5px solid rgba(255,255,255,0.5)', background: 'rgba(255,255,255,0.12)' }}>
                                Cancel
                            </button>
                            <button type="submit" className="btn btn-primary" disabled={(isEditMode ? updatePR.isPending : createPR.isPending) || lines.length === 0}
                                style={{ padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px', background: 'rgba(255,255,255,0.22)', color: 'white', border: '1.5px solid rgba(255,255,255,0.5)' }}>
                                {isEditMode ? 'Save Changes' : 'Save Requisition'}
                            </button>
                        </>
                    }
                />

                {formError && (
                    <div style={{ padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626', borderRadius: '8px', marginBottom: '1.5rem', fontSize: 'var(--text-sm)' }}>
                        {formError}
                    </div>
                )}

                {/* ── Success Confirmation ────────────────────── */}
                {createdPR && (
                    <div style={{ maxWidth: 520, margin: '2rem auto', textAlign: 'center' }}>
                        <div className="card" style={{ padding: '2.5rem 2rem' }}>
                            <div style={{
                                width: 64, height: 64, borderRadius: '50%', margin: '0 auto 1.25rem',
                                background: 'linear-gradient(135deg, #ecfdf5, #d1fae5)',
                                border: '3px solid #a7f3d0',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}>
                                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                                    <polyline points="20 6 9 17 4 12" />
                                </svg>
                            </div>
                            <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 800, color: 'var(--color-text)', marginBottom: '0.5rem' }}>
                                {isEditMode ? 'Requisition Updated' : 'Requisition Created'}
                            </h2>
                            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', marginBottom: '1.5rem' }}>
                                {isEditMode ? 'Your changes have been saved.' : 'Your purchase requisition has been saved as Draft.'}
                            </p>
                            <div style={{
                                display: 'inline-flex', alignItems: 'center', gap: '0.5rem',
                                padding: '0.75rem 1.5rem', borderRadius: '12px',
                                background: 'linear-gradient(135deg, #4f46e5, #6366f1)',
                                color: '#fff', marginBottom: '1.5rem',
                            }}>
                                <FileText size={18} />
                                <span style={{ fontSize: 'var(--text-lg)', fontWeight: 800, letterSpacing: '0.02em' }}>
                                    {createdPR.request_number}
                                </span>
                            </div>
                            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginBottom: '2rem' }}>
                                Use this number to track and reference this requisition.
                            </p>
                            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
                                <button type="button" onClick={() => navigate('/procurement/requisitions')}
                                    className="btn btn-outline" style={{ padding: '0.6rem 1.5rem', fontWeight: 600 }}>
                                    View All Requisitions
                                </button>
                                <button type="button" onClick={() => {
                                    setCreatedPR(null);
                                    setHeader({ description: '', mda: '', requested_date: new Date().toISOString().split('T')[0], required_date: '', fund: '', function: '', program: '', geo: '' });
                                    setLines([newLine('expense')]);
                                }}
                                    className="btn btn-primary" style={{ padding: '0.6rem 1.5rem', fontWeight: 600 }}>
                                    <Plus size={16} /> Create New PR
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {!createdPR && <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '1.5rem', alignItems: 'start' }}>

                    {/* LEFT COLUMN */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                        {/* Requisition Details — compact */}
                        <div className="card" style={{ padding: '1.5rem' }}>
                            <div style={sectionHeaderStyle}>
                                <span style={iconBoxStyle}><FileText size={16} color="#4f46e5" /></span>
                                Requisition Details
                            </div>

                            {/* MDA + Dates in one row */}
                            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
                                <div>
                                    <label style={{ ...labelStyle, fontSize: 'var(--text-xs)' }}>
                                        <Building2 size={12} style={{ verticalAlign: 'middle', marginRight: 3 }} />
                                        MDA <span style={{ color: '#dc2626' }}>*</span>
                                    </label>
                                    <select style={{ ...selectStyle, fontWeight: 600, borderColor: header.mda ? 'var(--color-border)' : '#fbbf24' }}
                                        value={header.mda} onChange={e => setHeader({ ...header, mda: e.target.value })} required>
                                        <option value="">Select MDA...</option>
                                        {(mdas || []).map((m: any) => (
                                            <option key={m.id} value={m.id}>{m.code} — {m.name}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label style={labelStyle}>Requested Date <span style={{ color: '#dc2626' }}>*</span></label>
                                    <input style={inputStyle} type="date"
                                        value={header.requested_date}
                                        onChange={e => setHeader({ ...header, requested_date: e.target.value })} required />
                                </div>
                                <div>
                                    <label style={labelStyle}>Required By</label>
                                    <input style={inputStyle} type="date"
                                        value={header.required_date}
                                        onChange={e => setHeader({ ...header, required_date: e.target.value })} />
                                </div>
                            </div>

                            {/* NCoA Dimensions — horizontal row */}
                            {dimensionsEnabled && (
                                <div style={{ marginBottom: '0.75rem' }}>
                                    <label style={{ ...labelStyle, display: 'flex', alignItems: 'center', gap: '0.35rem', marginBottom: '0.5rem' }}>
                                        <Layers size={12} /> NCoA Dimensions
                                    </label>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '0.5rem' }}>
                                        <div>
                                            <label style={{ ...labelStyle, fontSize: '0.6rem', marginBottom: '0.25rem' }}>Fund <span style={{ color: '#dc2626' }}>*</span></label>
                                            <select style={{ ...selectStyle, padding: '0.45rem 0.5rem', fontSize: 'var(--text-xs)' }} value={header.fund}
                                                onChange={e => setHeader({ ...header, fund: e.target.value })} required>
                                                <option value="">Select...</option>
                                                {dims?.funds?.map((f: any) => <option key={f.id} value={f.id}>{f.code} - {f.name}</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label style={{ ...labelStyle, fontSize: '0.6rem', marginBottom: '0.25rem' }}>Function <span style={{ color: '#dc2626' }}>*</span></label>
                                            <select style={{ ...selectStyle, padding: '0.45rem 0.5rem', fontSize: 'var(--text-xs)' }} value={header.function}
                                                onChange={e => setHeader({ ...header, function: e.target.value })} required>
                                                <option value="">Select...</option>
                                                {dims?.functions?.map((f: any) => <option key={f.id} value={f.id}>{f.code} - {f.name}</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label style={{ ...labelStyle, fontSize: '0.6rem', marginBottom: '0.25rem' }}>Program <span style={{ color: '#dc2626' }}>*</span></label>
                                            <select style={{ ...selectStyle, padding: '0.45rem 0.5rem', fontSize: 'var(--text-xs)' }} value={header.program}
                                                onChange={e => setHeader({ ...header, program: e.target.value })} required>
                                                <option value="">Select...</option>
                                                {dims?.programs?.map((p: any) => <option key={p.id} value={p.id}>{p.code} - {p.name}</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label style={{ ...labelStyle, fontSize: '0.6rem', marginBottom: '0.25rem' }}>Geo <span style={{ color: '#dc2626' }}>*</span></label>
                                            <select style={{ ...selectStyle, padding: '0.45rem 0.5rem', fontSize: 'var(--text-xs)' }} value={header.geo}
                                                onChange={e => setHeader({ ...header, geo: e.target.value })} required>
                                                <option value="">Select...</option>
                                                {dims?.geos?.map((g: any) => <option key={g.id} value={g.id}>{g.code} - {g.name}</option>)}
                                            </select>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Description */}
                            <div>
                                <label style={labelStyle}>Description <span style={{ color: '#dc2626' }}>*</span></label>
                                <textarea
                                    style={{ ...inputStyle, minHeight: '60px', resize: 'vertical', fontFamily: 'inherit' }}
                                    placeholder="Describe what is being requested and the justification..."
                                    value={header.description}
                                    onChange={e => setHeader({ ...header, description: e.target.value })}
                                    required
                                />
                            </div>
                        </div>

                        {/* Line Items Card */}
                        <div className="card" style={{ padding: '1.75rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                                <div style={sectionHeaderStyle}>
                                    <span style={iconBoxStyle}><LayoutGrid size={16} color="#4f46e5" /></span>
                                    Line Items
                                </div>
                                {/* Add line buttons by type */}
                                <div style={{ display: 'flex', gap: '0.35rem', marginBottom: '1.5rem' }}>
                                    {(Object.entries(LINE_TYPE_CONFIG) as [LineType, typeof LINE_TYPE_CONFIG['expense']][]).map(([type, cfg]) => (
                                        <button key={type} type="button" onClick={() => addLine(type)}
                                            style={{
                                                display: 'flex', alignItems: 'center', gap: '0.25rem',
                                                padding: '0.3rem 0.6rem', borderRadius: '6px',
                                                border: `1.5px solid ${cfg.border}`, background: cfg.bg,
                                                color: cfg.color, fontSize: 'var(--text-xs)', fontWeight: 600,
                                                cursor: 'pointer',
                                            }}>
                                            <Plus size={12} /> {cfg.label}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div style={{ overflowX: 'auto' }}>
                                {/* ``table-layout: fixed`` forces the
                                    browser to honour the per-th widths
                                    declared below instead of letting the
                                    longest cell content (the SearchableSelect's
                                    full GL account label) push the column
                                    width. Without this rule the description
                                    column stretches and squeezes Qty / Unit
                                    Price / Total down to a few characters
                                    each, even truncating their headers.
                                    A ``minWidth`` on the table gives the
                                    horizontal scroll wrapper something to
                                    grab on small viewports. */}
                                <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed', minWidth: '820px' }}>
                                    <thead>
                                        <tr>
                                            <th style={{ ...thStyle, width: '70px' }}>Type</th>
                                            {/* Description column carries TWO widgets side-by-side
                                                (selector + description input), so it gets a wider
                                                allocation than the previous stacked layout. The
                                                table's ``minWidth: 820px`` ensures both fit
                                                comfortably on a normal viewport. */}
                                            <th style={{ ...thStyle, width: '52%' }}>Description / Item</th>
                                            <th style={{ ...thStyle, width: '80px' }}>Qty</th>
                                            <th style={{ ...thStyle, width: '120px' }}>Est. Unit Price</th>
                                            <th style={{ ...thStyle, width: '110px', textAlign: 'right' }}>Est. Total</th>
                                            <th style={{ width: '36px' }}></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {lines.map((line, idx) => {
                                            const lineTotal = safeMultiply(line.quantity || '0', line.estimated_unit_price || '0');
                                            const ltc = LINE_TYPE_CONFIG[line.line_type];
                                            return (
                                                <tr key={line.id} style={{ borderBottom: '1px solid var(--color-border, #f1f5f9)' }}>
                                                    {/* Type badge */}
                                                    <td style={{ padding: '0.35rem' }}>
                                                        <span style={{
                                                            display: 'inline-block', padding: '0.2rem 0.4rem', borderRadius: '4px',
                                                            fontSize: '0.6rem', fontWeight: 700, textTransform: 'uppercase',
                                                            background: ltc.bg, color: ltc.color, border: `1px solid ${ltc.border}`,
                                                        }}>{ltc.label}</span>
                                                    </td>
                                                    {/* Description / selector based on type.
                                                        ``overflow: hidden`` on the cell, paired
                                                        with the table's ``table-layout: fixed``
                                                        above, makes the SearchableSelect's
                                                        closed-state label clip with ellipsis
                                                        (its inner span already has the right
                                                        text-overflow rules) instead of
                                                        ballooning the column. */}
                                                    <td style={{ padding: '0.35rem', overflow: 'hidden' }}>
                                                        {/* Selector + description laid out HORIZONTALLY.
                                                            ``flex: 1, minWidth: 0`` on each child lets
                                                            them share the cell width evenly while still
                                                            allowing long labels to truncate (instead of
                                                            forcing the cell wider). The wrapper is the
                                                            same shape for every line type so spacing
                                                            stays consistent across Item / Asset / Expense. */}
                                                        {line.line_type === 'item' ? (
                                                            <div style={{ display: 'flex', flexDirection: 'row', gap: '0.4rem', alignItems: 'center' }}>
                                                                <div style={{ flex: 1, minWidth: 0 }}>
                                                                    <SearchableSelect
                                                                        options={itemsList.map((i: any) => ({
                                                                            value: String(i.id),
                                                                            label: `${i.sku} — ${i.name}`,
                                                                            sublabel: i.category_name || '',
                                                                        }))}
                                                                        value={line.item}
                                                                        onChange={v => updateLine(idx, 'item', v)}
                                                                        placeholder="Type to search items..."
                                                                        style={{ fontSize: 'var(--text-sm)', padding: '0.4rem 0.5rem' }}
                                                                    />
                                                                </div>
                                                                <input style={{ ...inputStyle, flex: 1, minWidth: 0, fontSize: 'var(--text-xs)', padding: '0.4rem 0.5rem' }}
                                                                    type="text" placeholder="Description (auto-filled)"
                                                                    value={line.item_description} onChange={e => updateLine(idx, 'item_description', e.target.value)} required />
                                                            </div>
                                                        ) : line.line_type === 'asset' ? (
                                                            <div style={{ display: 'flex', flexDirection: 'row', gap: '0.4rem', alignItems: 'center' }}>
                                                                <div style={{ flex: 1, minWidth: 0 }}>
                                                                    <SearchableSelect
                                                                        options={(assets || []).map((a: any) => ({
                                                                            value: String(a.id),
                                                                            label: `${a.asset_number} — ${a.name}`,
                                                                            sublabel: a.category_name || a.location || '',
                                                                        }))}
                                                                        value={line.asset}
                                                                        onChange={v => updateLine(idx, 'asset', v)}
                                                                        placeholder="Type to search assets..."
                                                                        style={{ fontSize: 'var(--text-sm)', padding: '0.4rem 0.5rem' }}
                                                                    />
                                                                </div>
                                                                <input style={{ ...inputStyle, flex: 1, minWidth: 0, fontSize: 'var(--text-xs)', padding: '0.4rem 0.5rem' }}
                                                                    type="text" placeholder="Description (auto-filled)"
                                                                    value={line.item_description} onChange={e => updateLine(idx, 'item_description', e.target.value)} required />
                                                            </div>
                                                        ) : (
                                                            <div style={{ display: 'flex', flexDirection: 'row', gap: '0.4rem', alignItems: 'center' }}>
                                                                <div style={{ flex: 1, minWidth: 0 }}>
                                                                    <SearchableSelect
                                                                        options={(expenseAccounts || []).map((a: any) => ({
                                                                            value: String(a.id),
                                                                            label: `${a.code} — ${a.name}`,
                                                                            sublabel: a.account_type || '',
                                                                        }))}
                                                                        value={line.account}
                                                                        onChange={v => updateLine(idx, 'account', v)}
                                                                        placeholder="Type to search expense accounts..."
                                                                        style={{ fontSize: 'var(--text-sm)', padding: '0.4rem 0.5rem' }}
                                                                    />
                                                                </div>
                                                                <input style={{ ...inputStyle, flex: 1, minWidth: 0, fontSize: 'var(--text-xs)', padding: '0.4rem 0.5rem' }}
                                                                    type="text" placeholder="Description (auto-filled from account)"
                                                                    value={line.item_description} onChange={e => updateLine(idx, 'item_description', e.target.value)} required />
                                                            </div>
                                                        )}
                                                    </td>
                                                    {/* Qty */}
                                                    <td style={{ padding: '0.35rem' }}>
                                                        <input style={{ ...inputStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem' }}
                                                            type="number" step="1" min="1"
                                                            value={line.quantity} onChange={e => updateLine(idx, 'quantity', e.target.value)} required />
                                                    </td>
                                                    {/* Price */}
                                                    <td style={{ padding: '0.35rem' }}>
                                                        <div style={{ position: 'relative' }}>
                                                            <span style={{
                                                                position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)',
                                                                fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, pointerEvents: 'none',
                                                            }}>{currencySymbol}</span>
                                                            <input
                                                                style={{ ...inputStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem 0.5rem 1.5rem' }}
                                                                type="number" step="0.01" min="0"
                                                                value={line.estimated_unit_price} onChange={e => updateLine(idx, 'estimated_unit_price', e.target.value)} required />
                                                        </div>
                                                    </td>
                                                    {/* Total */}
                                                    <td style={{ padding: '0.35rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>
                                                        {formatCurrency(lineTotal)}
                                                    </td>
                                                    {/* Delete */}
                                                    <td style={{ padding: '0.35rem', textAlign: 'center' }}>
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
                                            <td colSpan={4} style={{ padding: '0.75rem 0.35rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)', color: 'var(--color-text)', borderTop: '2px solid var(--color-border, #e2e8f0)' }}>
                                                Total Estimated:
                                            </td>
                                            <td style={{ padding: '0.75rem 0.35rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)', color: '#4f46e5', borderTop: '2px solid var(--color-border, #e2e8f0)' }}>
                                                {formatCurrency(totalEstimated)}
                                            </td>
                                            <td style={{ borderTop: '2px solid var(--color-border, #e2e8f0)' }}></td>
                                        </tr>
                                    </tfoot>
                                </table>
                            </div>
                        </div>
                    </div>

                    {/* RIGHT COLUMN — Summary at top */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                        {/* Summary Card */}
                        <div style={{
                            borderRadius: '12px', padding: '1.75rem',
                            background: 'linear-gradient(135deg, #4f46e5 0%, #6366f1 50%, #7c3aed 100%)',
                            color: '#fff',
                        }}>
                            <p style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '0.35rem', opacity: 0.85 }}>
                                Requisition Summary
                            </p>
                            <p style={{ fontSize: 'var(--text-xs)', opacity: 0.8, marginBottom: '0.5rem' }}>
                                Total Estimated Value
                            </p>
                            <p style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: '-0.025em', marginBottom: '1.25rem' }}>
                                {formatCurrency(totalEstimated)}
                            </p>

                            <div style={{ borderTop: '1px solid rgba(255,255,255,0.2)', paddingTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                    <span style={{ opacity: 0.85 }}>Line Items</span>
                                    <span style={{ fontWeight: 600 }}>{lines.length}</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                    <span style={{ opacity: 0.85 }}>Expense Lines</span>
                                    <span style={{ fontWeight: 600 }}>{lines.filter(l => l.line_type === 'expense').length}</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                    <span style={{ opacity: 0.85 }}>Asset Lines</span>
                                    <span style={{ fontWeight: 600 }}>{lines.filter(l => l.line_type === 'asset').length}</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                    <span style={{ opacity: 0.85 }}>Item Lines</span>
                                    <span style={{ fontWeight: 600 }}>{lines.filter(l => l.line_type === 'item').length}</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                    <span style={{ opacity: 0.85 }}>Status</span>
                                    <span style={{ fontWeight: 600 }}>Draft</span>
                                </div>
                            </div>

                            {totalEstimated > 0 && (
                                <div style={{
                                    marginTop: '1.25rem', padding: '0.75rem', borderRadius: '8px',
                                    background: 'rgba(255,255,255,0.15)',
                                    display: 'flex', alignItems: 'center', gap: '0.5rem',
                                    fontSize: 'var(--text-xs)',
                                }}>
                                    <Info size={16} style={{ flexShrink: 0, opacity: 0.9 }} />
                                    <span>Requisition will be saved as Draft. Submit for approval after review.</span>
                                </div>
                            )}
                        </div>
                    </div>
                </div>}
            </form>
        </AccountingLayout>
    );
};

export default PurchaseRequisitionForm;
