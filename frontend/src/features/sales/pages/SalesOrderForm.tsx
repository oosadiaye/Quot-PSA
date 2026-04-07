import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, FileText, Layers, Info, LayoutGrid, Package, ShoppingCart, Calendar, ShieldCheck } from 'lucide-react';
import { useCreateSalesOrder, useCustomers } from '../hooks/useSales';
import { useTaxCodes } from '../../accounting/hooks/useAccountingEnhancements';
import { useDimensions } from '../../accounting/hooks/useJournal';
import { useItems } from '../../inventory/hooks/useInventory';
import { useIsDimensionsEnabled } from '../../../hooks/useTenantModules';
import { useCurrency } from '../../../context/CurrencyContext';
import AccountingLayout from '../../accounting/AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import '../../accounting/styles/glassmorphism.css';

interface SOLine {
    item: string;
    item_description: string;
    quantity: string;
    unit_price: string;
    discount_percent: string;
}

const SalesOrderForm = () => {
    const navigate = useNavigate();
    const { data: dims, isLoading: dimsLoading } = useDimensions();
    const { data: customersData } = useCustomers();
    const { data: itemsData } = useItems();
    const { isEnabled: dimensionsEnabled } = useIsDimensionsEnabled();
    const { formatCurrency, currencySymbol } = useCurrency();
    const createOrder = useCreateSalesOrder();
    const { data: taxCodesData } = useTaxCodes({ is_active: true });
    const taxCodesList = Array.isArray(taxCodesData) ? taxCodesData : [];

    const PAYMENT_TERMS = [
        { value: 'immediate', label: 'Due on Receipt', days: 0 },
        { value: 'net_7',  label: 'Net 7',  days: 7 },
        { value: 'net_15', label: 'Net 15', days: 15 },
        { value: 'net_30', label: 'Net 30', days: 30 },
        { value: 'net_45', label: 'Net 45', days: 45 },
        { value: 'net_60', label: 'Net 60', days: 60 },
        { value: 'net_90', label: 'Net 90', days: 90 },
    ];

    const computeDueDate = (orderDate: string, terms: string): string => {
        if (!orderDate || !terms) return '';
        const pt = PAYMENT_TERMS.find(p => p.value === terms);
        if (!pt) return '';
        const d = new Date(orderDate);
        d.setDate(d.getDate() + pt.days);
        return d.toISOString().split('T')[0];
    };

    const customers = customersData?.results || customersData || [];
    const itemsList = itemsData?.results || itemsData || [];
    const today = new Date().toISOString().split('T')[0];
    const [header, setHeader] = useState({
        customer: '',
        order_date: today,
        expected_delivery_date: '',
        delivery_address: '',
        delivery_contact: '',
        payment_terms: 'net_30',
        payment_due_date: computeDueDate(today, 'net_30'),
        notes: '',
        terms_and_conditions: '',
        fund: '',
        function: '',
        program: '',
        geo: '',
        tax_code: '' as string | number,
        tax_rate: '0',
        wht_exempt: false,
    });

    const [lines, setLines] = useState<SOLine[]>([
        { item: '', item_description: '', quantity: '1', unit_price: '0', discount_percent: '0' },
    ]);

    const [formError, setFormError] = useState('');

    // Auto-populate payment terms and WHT exempt from selected customer; recompute due date
    useEffect(() => {
        if (!header.customer) return;
        const cust = customers.find((c: any) => String(c.id) === header.customer);
        if (!cust) return;
        const updates: Partial<typeof header> = {};
        if (cust.payment_terms) {
            updates.payment_terms = cust.payment_terms;
            updates.payment_due_date = computeDueDate(header.order_date, cust.payment_terms);
        }
        if (cust.withholding_tax_code) updates.wht_exempt = cust.wht_exempt ?? false;
        if (Object.keys(updates).length) setHeader(h => ({ ...h, ...updates }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [header.customer, customers]);

    // Recompute due date when order_date or payment_terms changes
    useEffect(() => {
        setHeader(h => ({ ...h, payment_due_date: computeDueDate(h.order_date, h.payment_terms) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [header.order_date, header.payment_terms]);

    // Auto-populate tax rate when tax code changes
    useEffect(() => {
        if (!header.tax_code) { setHeader(h => ({ ...h, tax_rate: '0' })); return; }
        const tc = taxCodesList.find((t: any) => String(t.id) === String(header.tax_code));
        if (tc) setHeader(h => ({ ...h, tax_rate: String(tc.rate) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [header.tax_code, taxCodesList]);

    const totalAmount = useMemo(() => {
        return lines.reduce((sum, l) => {
            const qty = parseFloat(l.quantity || '0');
            const price = parseFloat(l.unit_price || '0');
            const disc = parseFloat(l.discount_percent || '0');
            return sum + qty * price * (1 - disc / 100);
        }, 0);
    }, [lines]);

    const addLine = () => setLines([...lines, { item: '', item_description: '', quantity: '1', unit_price: '0', discount_percent: '0' }]);
    const removeLine = (index: number) => setLines(lines.filter((_, i) => i !== index));

    const updateLine = (index: number, field: keyof SOLine, value: string) => {
        const newLines = [...lines];
        newLines[index][field] = value;
        if (field === 'item' && value) {
            const selectedItem = itemsList.find((i: any) => String(i.id) === value);
            if (selectedItem) {
                newLines[index].item_description = selectedItem.name;
                if (selectedItem.selling_price) {
                    newLines[index].unit_price = String(selectedItem.selling_price);
                }
            }
        }
        setLines(newLines);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        const payload: any = {
            customer: header.customer,
            order_date: header.order_date,
            expected_delivery_date: header.expected_delivery_date || null,
            delivery_address: header.delivery_address,
            delivery_contact: header.delivery_contact,
            payment_terms: header.payment_terms,
            notes: header.notes,
            terms_and_conditions: header.terms_and_conditions,
            tax_rate: parseFloat(header.tax_rate || '0'),
            tax_code: header.tax_code ? Number(header.tax_code) : null,
            wht_exempt: header.wht_exempt,
            status: 'Draft',
            lines: lines.map(l => ({
                item_description: l.item_description,
                quantity: parseFloat(l.quantity),
                unit_price: parseFloat(l.unit_price),
                discount_percent: parseFloat(l.discount_percent || '0'),
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
            await createOrder.mutateAsync(payload);
            navigate('/sales/orders');
        } catch (err: any) {
            const data = err.response?.data;
            if (data?.detail) {
                setFormError(data.detail);
            } else if (data?.error) {
                setFormError(data.error);
            } else if (data && typeof data === 'object') {
                const messages = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`);
                setFormError(messages.join(' | ') || 'Failed to create sales order.');
            } else {
                setFormError(err.message || 'Failed to create sales order.');
            }
        }
    };

    if (dimsLoading) return <AccountingLayout><div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>Loading form data...</div></AccountingLayout>;

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

    const selectStyle: React.CSSProperties = {
        ...inputStyle, appearance: 'auto' as any,
    };

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
                    title="New Sales Order"
                    subtitle="Create a new sales order for a customer."
                    icon={<ShoppingCart size={22} color="white" />}
                    onBack={() => navigate('/sales/orders')}
                    actions={
                        <>
                            <button type="button" className="btn" onClick={() => navigate('/sales/orders')}
                                style={{ padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px', color: 'white', background: 'transparent', border: '1px solid rgba(255,255,255,0.4)' }}>
                                Cancel
                            </button>
                            <button type="submit" className="btn btn-primary" disabled={createOrder.isPending || lines.length === 0}
                                style={{ padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px', background: 'rgba(255,255,255,0.2)', color: 'white', border: '1px solid rgba(255,255,255,0.3)' }}>
                                {createOrder.isPending ? 'Saving...' : 'Save Sales Order'}
                            </button>
                        </>
                    }
                />

                {formError && (
                    <div style={{ padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626', borderRadius: '8px', marginBottom: '1.5rem', fontSize: 'var(--text-sm)' }}>
                        {formError}
                    </div>
                )}

                {/* Layout */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: '1.5rem', alignItems: 'start' }}>

                    {/* MAIN COLUMN */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                        {/* Order Details Card */}
                        <div className="card" style={{ padding: '1.75rem' }}>
                            <div style={sectionHeaderStyle}>
                                <span style={iconBoxStyle}><FileText size={16} color="#4f46e5" /></span>
                                Order Details
                            </div>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
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
                                        <label style={labelStyle}>Order Date<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="date" value={header.order_date}
                                            onChange={e => setHeader({ ...header, order_date: e.target.value })} required />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Expected Delivery Date</label>
                                        <input style={inputStyle} type="date" value={header.expected_delivery_date}
                                            onChange={e => setHeader({ ...header, expected_delivery_date: e.target.value })} />
                                    </div>
                                </div>

                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                    <div>
                                        <label style={labelStyle}>Delivery Address</label>
                                        <input style={inputStyle} type="text" placeholder="Delivery address"
                                            value={header.delivery_address}
                                            onChange={e => setHeader({ ...header, delivery_address: e.target.value })} />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Delivery Contact</label>
                                        <input style={inputStyle} type="text" placeholder="Contact person"
                                            value={header.delivery_contact}
                                            onChange={e => setHeader({ ...header, delivery_contact: e.target.value })} />
                                    </div>
                                </div>

                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                    <div>
                                        <label style={labelStyle}>Payment Terms</label>
                                        <select style={selectStyle} value={header.payment_terms}
                                            onChange={e => setHeader({ ...header, payment_terms: e.target.value })}>
                                            <option value="">— Select —</option>
                                            {PAYMENT_TERMS.map(pt => (
                                                <option key={pt.value} value={pt.value}>{pt.label}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>
                                            <Calendar size={12} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'middle' }} />
                                            Payment Due Date
                                        </label>
                                        <div style={{
                                            ...inputStyle,
                                            background: 'rgba(79,70,229,0.04)',
                                            border: '2px solid rgba(79,70,229,0.2)',
                                            color: header.payment_due_date ? '#4f46e5' : 'var(--color-text-muted)',
                                            fontWeight: header.payment_due_date ? 600 : 400,
                                            display: 'flex', alignItems: 'center', gap: '0.5rem',
                                        }}>
                                            <Calendar size={14} style={{ color: '#4f46e5', flexShrink: 0 }} />
                                            {header.payment_due_date
                                                ? new Date(header.payment_due_date + 'T00:00:00').toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
                                                : 'Select terms above'}
                                        </div>
                                    </div>
                                </div>

                                <div>
                                    <label style={labelStyle}>Notes</label>
                                    <textarea
                                        style={{ ...inputStyle, minHeight: '70px', resize: 'vertical', fontFamily: 'inherit' }}
                                        placeholder="Additional notes..."
                                        value={header.notes}
                                        onChange={e => setHeader({ ...header, notes: e.target.value })}
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Line Items Card */}
                        <div className="card" style={{ padding: '1.75rem' }}>
                            <div style={sectionHeaderStyle}>
                                <span style={iconBoxStyle}><LayoutGrid size={16} color="#4f46e5" /></span>
                                Line Items
                            </div>

                            <div style={{ overflowX: 'auto' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                    <thead>
                                        <tr>
                                            <th style={{ ...thStyle, width: '180px' }}>Inventory Item</th>
                                            <th style={thStyle}>Item Description</th>
                                            <th style={{ ...thStyle, width: '80px' }}>Qty</th>
                                            <th style={{ ...thStyle, width: '130px' }}>Unit Price</th>
                                            <th style={{ ...thStyle, width: '80px' }}>Disc %</th>
                                            <th style={{ ...thStyle, width: '110px', textAlign: 'right' }}>Total</th>
                                            <th style={{ width: '36px' }}></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {lines.map((line, idx) => {
                                            const qty = parseFloat(line.quantity || '0');
                                            const price = parseFloat(line.unit_price || '0');
                                            const disc = parseFloat(line.discount_percent || '0');
                                            const lineTotal = qty * price * (1 - disc / 100);
                                            return (
                                                <tr key={idx}>
                                                    <td style={{ padding: '0.35rem 0.35rem 0.35rem 0' }}>
                                                        <select style={{ ...selectStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem' }}
                                                            value={line.item} onChange={e => updateLine(idx, 'item', e.target.value)}>
                                                            <option value="">None</option>
                                                            {itemsList.map((i: any) => <option key={i.id} value={i.id}>{i.sku} - {i.name}</option>)}
                                                        </select>
                                                    </td>
                                                    <td style={{ padding: '0.35rem' }}>
                                                        <input style={{ ...inputStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem' }}
                                                            type="text" placeholder="Item description"
                                                            value={line.item_description} onChange={e => updateLine(idx, 'item_description', e.target.value)} required />
                                                    </td>
                                                    <td style={{ padding: '0.35rem' }}>
                                                        <input style={{ ...inputStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem' }}
                                                            type="number" step="1" min="1"
                                                            value={line.quantity} onChange={e => updateLine(idx, 'quantity', e.target.value)} required />
                                                    </td>
                                                    <td style={{ padding: '0.35rem' }}>
                                                        <div style={{ position: 'relative' }}>
                                                            <span style={{
                                                                position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)',
                                                                fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600, pointerEvents: 'none',
                                                            }}>{currencySymbol}</span>
                                                            <input style={{ ...inputStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem 0.5rem 1.5rem' }}
                                                                type="number" step="0.01" min="0"
                                                                value={line.unit_price} onChange={e => updateLine(idx, 'unit_price', e.target.value)} required />
                                                        </div>
                                                    </td>
                                                    <td style={{ padding: '0.35rem' }}>
                                                        <input style={{ ...inputStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem' }}
                                                            type="number" step="0.01" min="0" max="100"
                                                            value={line.discount_percent} onChange={e => updateLine(idx, 'discount_percent', e.target.value)} />
                                                    </td>
                                                    <td style={{ padding: '0.35rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>
                                                        {formatCurrency(lineTotal)}
                                                    </td>
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

                    {/* RIGHT COLUMN */}
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
                                Order Summary
                            </p>
                            <p style={{ fontSize: 'var(--text-xs)', opacity: 0.8, marginBottom: '0.5rem' }}>
                                Total Order Value
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
                                    <span style={{ fontWeight: 600 }}>{header.customer ? (customers.find((c: any) => String(c.id) === header.customer)?.name || '\u2014') : '\u2014'}</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                    <span style={{ opacity: 0.85 }}>Status</span>
                                    <span style={{ fontWeight: 600 }}>Draft</span>
                                </div>
                            </div>

                            {totalAmount > 0 && (
                                <div style={{
                                    marginTop: '1.25rem', padding: '0.75rem', borderRadius: '8px',
                                    background: 'rgba(255,255,255,0.15)',
                                    display: 'flex', alignItems: 'center', gap: '0.5rem',
                                    fontSize: 'var(--text-xs)',
                                }}>
                                    <Info size={16} style={{ flexShrink: 0, opacity: 0.9 }} />
                                    <span>Order will be saved as Draft. Submit for approval after review.</span>
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
                                        <option value="">— No tax —</option>
                                        {taxCodesList.filter((tc: any) => tc.direction !== 'purchase').map((tc: any) => (
                                            <option key={tc.id} value={tc.id}>{tc.code} — {tc.name} ({tc.rate}%)</option>
                                        ))}
                                    </select>
                                </div>
                                {header.tax_code && (
                                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)', padding: '0.5rem 0.75rem', background: 'rgba(79,70,229,0.06)', borderRadius: '6px' }}>
                                        <span style={{ color: 'var(--color-text-muted)' }}>Tax Amount ({header.tax_rate}%)</span>
                                        <span style={{ fontWeight: 700, color: '#4f46e5' }}>
                                            {formatCurrency(totalAmount * parseFloat(header.tax_rate || '0') / 100)}
                                        </span>
                                    </div>
                                )}
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

export default SalesOrderForm;
