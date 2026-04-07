import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Plus, Trash2, FileText, Layers, Info, LayoutGrid, Package, CreditCard, ShieldCheck } from 'lucide-react';
import { useVendors, useCreatePO, usePurchaseRequests, useBankAccounts, usePurchaseOrder } from './hooks/useProcurement';
import { useDimensions } from '../accounting/hooks/useJournal';
import { useCostCenters } from '../accounting/hooks/useCostCenters';
import { useFixedAssets, useTaxCodes } from '../accounting/hooks/useAccountingEnhancements';
import { useItems } from '../inventory/hooks/useInventory';
import { useCurrency } from '../../context/CurrencyContext';
import { safeAdd, safeMultiply } from '../accounting/utils/currency';
import AccountingLayout from '../accounting/AccountingLayout';
import PageHeader from '../../components/PageHeader';
import '../accounting/styles/glassmorphism.css';

interface POLine {
    id: string;
    item_description: string;
    quantity: string;
    unit_price: string;
    account: string;
    asset: string;
    item: string;
}

const POForm = () => {
    const navigate = useNavigate();
    const { prId, id } = useParams<{ prId?: string; id?: string }>();
    const { data: vendors } = useVendors();
    const { data: dims, isLoading: dimsLoading } = useDimensions();
    const { data: costCenters } = useCostCenters({ is_active: true });
    const { formatCurrency, currencySymbol } = useCurrency();
    const createPO = useCreatePO();
    const { data: assets } = useFixedAssets({ status: 'Active' });
    const { data: taxCodesData } = useTaxCodes({ is_active: true });
    const taxCodesList = Array.isArray(taxCodesData) ? taxCodesData : [];
    const { data: itemsData } = useItems();
    const itemsList = itemsData?.results || itemsData || [];

    // When viewing an existing PO (route: /procurement/orders/:id)
    const { data: existingPO } = usePurchaseOrder(id ? Number(id) : null);

    // Fetch PRs to find the one being converted
    const { data: prsData } = usePurchaseRequests();
    const sourcePR = useMemo(() => {
        if (!prId || !prsData) return null;
        const list = prsData?.results || prsData || [];
        return list.find((pr: any) => String(pr.id) === prId) || null;
    }, [prId, prsData]);

    const [header, setHeader] = useState({
        po_number: '',
        vendor: '',
        order_date: new Date().toISOString().split('T')[0],
        expected_delivery_date: '',
        cost_center: '',
        fund: '',
        function: '',
        program: '',
        geo: '',
        tax_code: '' as string | number,
        tax_rate: '0',
        wht_exempt: false,
    });

    const [lines, setLines] = useState<POLine[]>([
        { id: crypto.randomUUID(), item_description: '', quantity: '1', unit_price: '0', account: '', asset: '', item: '' },
    ]);

    const [formError, setFormError] = useState('');

    // Down Payment state — declared early; dpAmount computed AFTER totalOrder below
    const [dpEnabled, setDpEnabled] = useState(false);
    const [dp, setDp] = useState({
        calc_type: 'percentage' as 'percentage' | 'amount',
        calc_value: '',
        payment_method: 'Bank' as 'Bank' | 'Cash',
        bank_account: '',
        notes: '',
    });

    // Pre-fill from PR when converting
    useEffect(() => {
        if (sourcePR) {
            setHeader(prev => ({
                ...prev,
                fund: sourcePR.fund ? String(sourcePR.fund) : '',
                function: sourcePR.function ? String(sourcePR.function) : '',
                program: sourcePR.program ? String(sourcePR.program) : '',
                geo: sourcePR.geo ? String(sourcePR.geo) : '',
                cost_center: sourcePR.cost_center ? String(sourcePR.cost_center) : '',
            }));
            if (sourcePR.lines?.length) {
                setLines(sourcePR.lines.map((l: any) => ({
                    id: crypto.randomUUID(),
                    item_description: l.item_description || '',
                    quantity: String(l.quantity || 1),
                    unit_price: String(l.estimated_unit_price || 0),
                    account: l.account ? String(l.account) : '',
                    asset: l.asset ? String(l.asset) : '',
                    item: l.item ? String(l.item) : '',
                })));
            }
        }
    }, [sourcePR]);

    const totalOrder = useMemo(() => {
        return lines.reduce((sum, l) => {
            return safeAdd(sum, safeMultiply(l.quantity || '0', l.unit_price || '0'));
        }, 0);
    }, [lines]);

    // Bank/Cash accounts for down payment (fetched only when toggle is on)
    const { data: bankAccountsData } = useBankAccounts(
        dpEnabled ? { account_type: dp.payment_method === 'Bank' ? 'Bank' : 'Cash' } : undefined
    );
    const bankAccountsList = bankAccountsData?.results || bankAccountsData || [];

    // Computed down payment amount — must be after totalOrder
    const dpAmount = useMemo(() => {
        if (!dpEnabled || !dp.calc_value) return 0;
        const val = parseFloat(dp.calc_value);
        if (isNaN(val) || val <= 0) return 0;
        if (dp.calc_type === 'percentage') return (totalOrder * val) / 100;
        return val;
    }, [dpEnabled, dp.calc_type, dp.calc_value, totalOrder]);

    // Auto-populate WHT exempt from selected vendor
    useEffect(() => {
        if (!header.vendor) return;
        const vendor = (vendors?.results || vendors || []).find((v: any) => String(v.id) === header.vendor);
        if (vendor) setHeader(h => ({ ...h, wht_exempt: vendor.wht_exempt ?? false }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [header.vendor, vendors]);

    // Auto-populate tax rate from selected tax code
    useEffect(() => {
        if (!header.tax_code) { setHeader(h => ({ ...h, tax_rate: '0' })); return; }
        const tc = taxCodesList.find((t: any) => String(t.id) === String(header.tax_code));
        if (tc) setHeader(h => ({ ...h, tax_rate: String(tc.rate) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [header.tax_code, taxCodesList]);

    const addLine = () => setLines([...lines, { id: crypto.randomUUID(), item_description: '', quantity: '1', unit_price: '0', account: '', asset: '', item: '' }]);
    const removeLine = (index: number) => setLines(lines.filter((_, i) => i !== index));

    const updateLine = (index: number, field: keyof POLine, value: string) => {
        const newLines = [...lines];
        newLines[index][field] = value;
        if (field === 'item' && value) {
            const selectedItem = itemsList.find((i: any) => String(i.id) === value);
            if (selectedItem) {
                newLines[index].item_description = selectedItem.name;
            }
        }
        setLines(newLines);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        const payload: any = {
            po_number: header.po_number,
            vendor: Number(header.vendor),
            order_date: header.order_date,
            status: 'Draft',
            ...(header.expected_delivery_date ? { expected_delivery_date: header.expected_delivery_date } : {}),
            ...(prId ? { purchase_request: Number(prId) } : {}),
            lines: lines.map(l => ({
                item_description: l.item_description,
                quantity: parseFloat(l.quantity),
                unit_price: parseFloat(l.unit_price),
                account: Number(l.account),
                ...(l.asset ? { asset: Number(l.asset) } : {}),
                ...(l.item ? { item: Number(l.item) } : {}),
            })),
            fund: header.fund ? Number(header.fund) : null,
            function: header.function ? Number(header.function) : null,
            program: header.program ? Number(header.program) : null,
            geo: header.geo ? Number(header.geo) : null,
            tax_rate: parseFloat(header.tax_rate || '0'),
            tax_code: header.tax_code ? Number(header.tax_code) : null,
            wht_exempt: header.wht_exempt,
            ...(dpEnabled && dpAmount > 0 ? {
                down_payment_request: {
                    enabled: true,
                    calc_type: dp.calc_type,
                    calc_value: parseFloat(dp.calc_value),
                    requested_amount: parseFloat(dpAmount.toFixed(2)),
                    payment_method: dp.payment_method,
                    bank_account: dp.bank_account ? Number(dp.bank_account) : null,
                    notes: dp.notes,
                },
            } : {}),
        };

        try {
            await createPO.mutateAsync(payload);
            navigate('/procurement/orders');
        } catch (err: any) {
            const data = err.response?.data;
            if (data?.detail) {
                setFormError(data.detail);
            } else if (data && typeof data === 'object') {
                const messages = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`);
                setFormError(messages.join(' | ') || 'Failed to create purchase order.');
            } else {
                setFormError(err.message || 'Failed to create purchase order.');
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
                    title={sourcePR ? 'Convert PR to Purchase Order' : 'Generate Purchase Order'}
                    subtitle={sourcePR
                        ? `Converting requisition ${sourcePR.request_number} to a purchase order.`
                        : 'Create a purchase order with dimension tagging.'}
                    icon={<Package size={22} />}
                    onBack={() => navigate('/procurement/orders')}
                    actions={
                        <>
                            {existingPO && ['Approved', 'Posted'].includes(existingPO.status) && (
                                <button
                                    type="button"
                                    onClick={() => navigate(`/procurement/grn/new?po=${existingPO.id}`)}
                                    style={{
                                        padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px',
                                        background: 'rgba(59, 130, 246, 0.18)', color: 'white',
                                        border: '1px solid rgba(59, 130, 246, 0.4)',
                                        display: 'inline-flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer',
                                    }}
                                >
                                    <Package size={16} />
                                    Receive Goods
                                </button>
                            )}
                            <button type="button" className="btn btn-outline" onClick={() => navigate('/procurement/orders')}
                                style={{ padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px', color: 'white', borderColor: 'rgba(255,255,255,0.3)' }}>
                                Cancel
                            </button>
                            {!existingPO && (
                                <button type="submit" className="btn btn-primary" disabled={createPO.isPending || lines.length === 0}
                                    style={{ padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px', background: 'rgba(255,255,255,0.18)', color: 'white', border: '1px solid rgba(255,255,255,0.25)' }}>
                                    {createPO.isPending ? 'Creating...' : sourcePR ? 'Create PO from PR' : 'Create Purchase Order'}
                                </button>
                            )}
                        </>
                    }
                />

                {/* Source PR Banner */}
                {sourcePR && (
                    <div style={{
                        padding: '0.75rem 1rem', background: 'rgba(79, 70, 229, 0.08)', border: '1px solid rgba(79, 70, 229, 0.2)',
                        borderRadius: '8px', marginBottom: '1.5rem', fontSize: 'var(--text-sm)',
                        display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#4f46e5',
                    }}>
                        <Package size={16} />
                        <span>Source: <strong>{sourcePR.request_number}</strong> — {sourcePR.description}</span>
                        <span style={{ marginLeft: 'auto', fontSize: 'var(--text-xs)', fontWeight: 600, padding: '0.2rem 0.5rem', borderRadius: '4px', background: 'rgba(79, 70, 229, 0.15)' }}>
                            {sourcePR.priority} Priority
                        </span>
                    </div>
                )}

                {formError && (
                    <div style={{ padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626', borderRadius: '8px', marginBottom: '1.5rem', fontSize: 'var(--text-sm)' }}>
                        {formError}
                    </div>
                )}

                {/* Layout */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: '1.5rem', alignItems: 'start' }}>

                    {/* LEFT / MAIN COLUMN */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                        {/* Order Details Card */}
                        <div className="card" style={{ padding: '1.75rem' }}>
                            <div style={sectionHeaderStyle}>
                                <span style={iconBoxStyle}><FileText size={16} color="#4f46e5" /></span>
                                Order Details
                            </div>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                                {/* PO Number + Order Date */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '1rem' }}>
                                    <div>
                                        <label style={labelStyle}>PO Number<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="text" placeholder={`PO-${new Date().getFullYear()}-XXXX`}
                                            value={header.po_number}
                                            onChange={e => setHeader({ ...header, po_number: e.target.value })} required />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Order Date<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="date"
                                            value={header.order_date}
                                            onChange={e => setHeader({ ...header, order_date: e.target.value })} required />
                                    </div>
                                </div>

                                {/* Vendor + Expected Delivery */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '1rem' }}>
                                    <div>
                                        <label style={labelStyle}>Vendor / Supplier<span className="required-mark"> *</span></label>
                                        <select style={selectStyle} value={header.vendor}
                                            onChange={e => setHeader({ ...header, vendor: e.target.value })} required>
                                            <option value="">Select Vendor</option>
                                            {vendors?.map((v: any) => <option key={v.id} value={v.id}>{v.name}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Expected Delivery</label>
                                        <input style={inputStyle} type="date"
                                            value={header.expected_delivery_date}
                                            onChange={e => setHeader({ ...header, expected_delivery_date: e.target.value })} />
                                    </div>
                                </div>

                                {/* Cost Center */}
                                <div>
                                    <label style={labelStyle}>Cost Center</label>
                                    <select style={selectStyle} value={header.cost_center}
                                        onChange={e => setHeader({ ...header, cost_center: e.target.value })}>
                                        <option value="">Select Cost Center</option>
                                        {costCenters?.map((cc: any) => (
                                            <option key={cc.id} value={cc.id}>{cc.code} - {cc.name}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>
                        </div>

                        {/* ── Down Payment Request Card ─────────────────────── */}
                        <div className="card" style={{ padding: '1.75rem' }}>
                            {/* Header row with toggle */}
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: dpEnabled ? '1.5rem' : 0 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                                    <span style={{ width: '28px', height: '28px', borderRadius: '6px', background: 'rgba(245,158,11,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                        <CreditCard size={16} color="#f59e0b" />
                                    </span>
                                    <div>
                                        <p style={{ margin: 0, fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-text)' }}>Down Payment Request</p>
                                        <p style={{ margin: 0, fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>Request an advance payment for this PO</p>
                                    </div>
                                </div>
                                {/* Toggle switch */}
                                <button
                                    type="button"
                                    onClick={() => setDpEnabled(v => !v)}
                                    style={{
                                        position: 'relative', width: '44px', height: '24px', borderRadius: '9999px',
                                        background: dpEnabled ? '#f59e0b' : 'var(--color-border)',
                                        border: 'none', cursor: 'pointer', transition: 'background 0.2s', flexShrink: 0,
                                    }}
                                    aria-checked={dpEnabled}
                                    role="switch"
                                >
                                    <span style={{
                                        position: 'absolute', top: '3px',
                                        left: dpEnabled ? '23px' : '3px',
                                        width: '18px', height: '18px', borderRadius: '50%',
                                        background: '#fff', transition: 'left 0.2s',
                                        boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
                                    }} />
                                </button>
                            </div>

                            {/* Collapsible fields */}
                            {dpEnabled && (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
                                    {/* Calc type + value */}
                                    <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: '1rem', alignItems: 'end' }}>
                                        <div>
                                            <label style={labelStyle}>Payment Type</label>
                                            <select style={selectStyle}
                                                value={dp.calc_type}
                                                onChange={e => setDp({ ...dp, calc_type: e.target.value as 'percentage' | 'amount', calc_value: '' })}>
                                                <option value="percentage">Percentage (%)</option>
                                                <option value="amount">Fixed Amount</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label style={labelStyle}>
                                                {dp.calc_type === 'percentage' ? 'Percentage of PO Total' : 'Down Payment Amount'}
                                            </label>
                                            <div style={{ position: 'relative' }}>
                                                <span style={{
                                                    position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)',
                                                    fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-text-muted)', pointerEvents: 'none',
                                                }}>
                                                    {dp.calc_type === 'percentage' ? '%' : currencySymbol}
                                                </span>
                                                <input
                                                    style={{ ...inputStyle, paddingLeft: '1.75rem' }}
                                                    type="number" min="0" step={dp.calc_type === 'percentage' ? '1' : '0.01'}
                                                    max={dp.calc_type === 'percentage' ? '100' : undefined}
                                                    placeholder={dp.calc_type === 'percentage' ? '30' : '0.00'}
                                                    value={dp.calc_value}
                                                    onChange={e => setDp({ ...dp, calc_value: e.target.value })}
                                                />
                                            </div>
                                        </div>
                                    </div>

                                    {/* Payment Method + Bank Account */}
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                        <div>
                                            <label style={labelStyle}>Payment Method</label>
                                            <select style={selectStyle}
                                                value={dp.payment_method}
                                                onChange={e => setDp({ ...dp, payment_method: e.target.value as 'Bank' | 'Cash', bank_account: '' })}>
                                                <option value="Bank">Bank Transfer</option>
                                                <option value="Cash">Cash</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label style={labelStyle}>{dp.payment_method === 'Bank' ? 'Bank Account' : 'Cash Account'}</label>
                                            <select style={selectStyle}
                                                value={dp.bank_account}
                                                onChange={e => setDp({ ...dp, bank_account: e.target.value })}>
                                                <option value="">Select Account</option>
                                                {Array.isArray(bankAccountsList) && bankAccountsList.map((ba: any) => (
                                                    <option key={ba.id} value={ba.id}>{ba.name}</option>
                                                ))}
                                            </select>
                                        </div>
                                    </div>

                                    {/* Notes */}
                                    <div>
                                        <label style={labelStyle}>Notes / Justification</label>
                                        <textarea
                                            style={{ ...inputStyle, minHeight: '60px', resize: 'vertical', fontFamily: 'inherit' }}
                                            placeholder="Reason for down payment request..."
                                            value={dp.notes}
                                            onChange={e => setDp({ ...dp, notes: e.target.value })}
                                        />
                                    </div>

                                    {/* Preview banner */}
                                    {dpAmount > 0 && (
                                        <div style={{
                                            display: 'flex', alignItems: 'center', gap: '0.75rem',
                                            padding: '0.75rem 1rem', borderRadius: '8px',
                                            background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.25)',
                                        }}>
                                            <Info size={16} color="#f59e0b" style={{ flexShrink: 0 }} />
                                            <div style={{ fontSize: 'var(--text-sm)' }}>
                                                <span style={{ color: 'var(--color-text-muted)' }}>Down payment amount: </span>
                                                <strong style={{ color: '#d97706' }}>{formatCurrency(dpAmount)}</strong>
                                                {dp.calc_type === 'percentage' && (
                                                    <span style={{ color: 'var(--color-text-muted)' }}> ({dp.calc_value}% of {formatCurrency(totalOrder)})</span>
                                                )}
                                                <span style={{ color: 'var(--color-text-muted)', marginLeft: '0.5rem' }}>
                                                    — A payment request will be sent to Finance for review.
                                                </span>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
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
                                            <th style={{ ...thStyle, width: '170px' }}>GL Account</th>
                                            <th style={{ ...thStyle, width: '170px' }}>Asset</th>
                                            <th style={{ ...thStyle, width: '80px' }}>Qty</th>
                                            <th style={{ ...thStyle, width: '120px' }}>Unit Price</th>
                                            <th style={{ ...thStyle, width: '100px', textAlign: 'right' }}>Total</th>
                                            <th style={{ width: '36px' }}></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {lines.map((line, idx) => {
                                            const lineTotal = safeMultiply(line.quantity || '0', line.unit_price || '0');
                                            return (
                                                <tr key={line.id}>
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
                                                        <select style={{ ...selectStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem' }}
                                                            value={line.account} onChange={e => updateLine(idx, 'account', e.target.value)} required>
                                                            <option value="">Select GL Account</option>
                                                            {dims?.accounts?.filter((a: any) => a.account_type === 'Expense' || a.account_type === 'Asset').map((a: any) => <option key={a.id} value={a.id}>{a.code} - {a.name} ({a.account_type})</option>)}
                                                        </select>
                                                    </td>
                                                    <td style={{ padding: '0.35rem' }}>
                                                        <select style={{ ...selectStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem' }}
                                                            value={line.asset} onChange={e => updateLine(idx, 'asset', e.target.value)}>
                                                            <option value="">None</option>
                                                            {assets?.map((a: any) => <option key={a.id} value={a.id}>{a.asset_number} - {a.name}</option>)}
                                                        </select>
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
                                                            <input
                                                                style={{ ...inputStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem 0.5rem 1.5rem' }}
                                                                type="number" step="0.01" min="0"
                                                                value={line.unit_price} onChange={e => updateLine(idx, 'unit_price', e.target.value)} required />
                                                        </div>
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
                                            <td colSpan={6} style={{ padding: '0.75rem 0.35rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)', color: 'var(--color-text)', borderTop: '2px solid var(--color-border, #e2e8f0)' }}>
                                                Order Total:
                                            </td>
                                            <td style={{ padding: '0.75rem 0.35rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)', color: '#4f46e5', borderTop: '2px solid var(--color-border, #e2e8f0)' }}>
                                                {formatCurrency(totalOrder)}
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
                                    {formatCurrency(totalOrder)}
                                </p>

                                <div style={{ borderTop: '1px solid rgba(255,255,255,0.2)', paddingTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                        <span style={{ opacity: 0.85 }}>Line Items</span>
                                        <span style={{ fontWeight: 600 }}>{lines.length}</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                        <span style={{ opacity: 0.85 }}>Vendor</span>
                                        <span style={{ fontWeight: 600 }}>{vendors?.find((v: any) => String(v.id) === header.vendor)?.name || '—'}</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                        <span style={{ opacity: 0.85 }}>Status</span>
                                        <span style={{ fontWeight: 600 }}>Draft</span>
                                    </div>
                                    {dpEnabled && dpAmount > 0 && (
                                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                            <span style={{ opacity: 0.85 }}>Down Payment</span>
                                            <span style={{ fontWeight: 600, color: '#fbbf24' }}>{formatCurrency(dpAmount)}</span>
                                        </div>
                                    )}
                                    {sourcePR && (
                                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                            <span style={{ opacity: 0.85 }}>Source PR</span>
                                            <span style={{ fontWeight: 600 }}>{sourcePR.request_number}</span>
                                        </div>
                                    )}
                                </div>

                                {totalOrder > 0 && (
                                    <div style={{
                                        marginTop: '1.25rem', padding: '0.75rem', borderRadius: '8px',
                                        background: 'rgba(255,255,255,0.15)',
                                        display: 'flex', alignItems: 'center', gap: '0.5rem',
                                        fontSize: 'var(--text-xs)',
                                    }}>
                                        <Info size={16} style={{ flexShrink: 0, opacity: 0.9 }} />
                                        <span>Budget availability will be checked upon posting.</span>
                                    </div>
                                )}
                            </div>

                        {/* Tax & WHT Card */}
                        <div className="card" style={{ padding: '1.5rem', marginTop: '1.5rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
                                <ShieldCheck size={16} color="#4f46e5" />
                                <span style={{ fontWeight: 700, fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>Tax &amp; WHT</span>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-secondary, #64748b)' }}>Input Tax Code (VAT)</label>
                                    <select style={{ width: '100%', padding: '0.625rem 0.875rem', borderRadius: '8px', border: '2.5px solid var(--color-border, #e2e8f0)', background: 'var(--color-background, #fff)', color: 'var(--color-text, #1e293b)', fontSize: 'var(--text-sm)', appearance: 'auto' as any }}
                                        value={String(header.tax_code)}
                                        onChange={e => setHeader({ ...header, tax_code: e.target.value })}>
                                        <option value="">— No tax —</option>
                                        {taxCodesList.filter((tc: any) => tc.direction !== 'sales').map((tc: any) => (
                                            <option key={tc.id} value={tc.id}>{tc.code} — {tc.name} ({tc.rate}%)</option>
                                        ))}
                                    </select>
                                </div>
                                {header.tax_code && (
                                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)', padding: '0.5rem 0.75rem', background: 'rgba(79,70,229,0.06)', borderRadius: '6px' }}>
                                        <span style={{ color: 'var(--color-text-muted)' }}>Tax Amount ({header.tax_rate}%)</span>
                                        <span style={{ fontWeight: 700, color: '#4f46e5' }}>
                                            {formatCurrency(totalOrder * parseFloat(header.tax_rate || '0') / 100)}
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

export default POForm;
