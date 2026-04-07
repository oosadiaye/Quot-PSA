import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { FileText, Truck, Info, LayoutGrid } from 'lucide-react';
import PageHeader from '../../../components/PageHeader';
import { useCreateDeliveryNote, useSalesOrders, useSalesOrder } from '../hooks/useSales';
import { useCurrency } from '../../../context/CurrencyContext';
import AccountingLayout from '../../accounting/AccountingLayout';
import '../../accounting/styles/glassmorphism.css';

interface DNLine {
    so_line: number;
    item_description: string;
    ordered_qty: number;
    unit_price: number;
    quantity_delivered: string;
}

const DeliveryNoteForm = () => {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const { formatCurrency } = useCurrency();
    const createDN = useCreateDeliveryNote();

    const { data: ordersData } = useSalesOrders({ status: 'Posted' });
    const ordersList = ordersData?.results || ordersData || [];

    const soParam = Number(searchParams.get('so'));
    const preselectedSoId = Number.isFinite(soParam) && soParam > 0 ? soParam : undefined;
    const [selectedOrderId, setSelectedOrderId] = useState<number | undefined>(preselectedSoId);
    const { data: selectedOrder } = useSalesOrder(selectedOrderId);

    const [header, setHeader] = useState({
        delivery_date: new Date().toISOString().split('T')[0],
        delivered_by: '',
        driver_name: '',
        vehicle_number: '',
        notes: '',
    });

    const [lines, setLines] = useState<DNLine[]>([]);
    const [formError, setFormError] = useState('');

    // Populate lines when SO is selected
    useEffect(() => {
        if (selectedOrder?.lines) {
            setLines(selectedOrder.lines.map((l: any) => ({
                so_line: l.id,
                item_description: l.item_description,
                ordered_qty: parseFloat(l.quantity),
                unit_price: parseFloat(l.unit_price),
                quantity_delivered: String(l.quantity),
            })));
        } else {
            setLines([]);
        }
    }, [selectedOrder]);

    const totalDeliveryValue = useMemo(() => {
        return lines.reduce((sum, l) => {
            return sum + parseFloat(l.quantity_delivered || '0') * l.unit_price;
        }, 0);
    }, [lines]);

    const updateLineQty = (index: number, value: string) => {
        const newLines = [...lines];
        newLines[index].quantity_delivered = value;
        setLines(newLines);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');

        if (!selectedOrderId) {
            setFormError('Please select a Sales Order.');
            return;
        }

        const payload: any = {
            sales_order: selectedOrderId,
            delivery_date: header.delivery_date,
            delivered_by: header.delivered_by,
            driver_name: header.driver_name,
            vehicle_number: header.vehicle_number,
            notes: header.notes,
            lines: lines
                .filter(l => parseFloat(l.quantity_delivered || '0') > 0)
                .map(l => ({
                    so_line: l.so_line,
                    quantity_delivered: parseFloat(l.quantity_delivered),
                })),
        };

        try {
            await createDN.mutateAsync(payload);
            navigate('/sales/delivery-notes');
        } catch (err: any) {
            const data = err.response?.data;
            if (data?.detail) {
                setFormError(data.detail);
            } else if (data?.error) {
                setFormError(data.error);
            } else if (data && typeof data === 'object') {
                const messages = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`);
                setFormError(messages.join(' | ') || 'Failed to create delivery note.');
            } else {
                setFormError(err.message || 'Failed to create delivery note.');
            }
        }
    };

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
                    title="New Delivery Note"
                    subtitle="Record goods delivery against a posted sales order."
                    icon={<Truck size={22} color="white" />}
                    onBack={() => navigate('/sales/delivery-notes')}
                    actions={
                        <>
                            <button type="button" className="btn btn-outline" onClick={() => navigate('/sales/delivery-notes')}
                                style={{ padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px', color: 'white', borderColor: 'rgba(255,255,255,0.3)' }}>
                                Cancel
                            </button>
                            <button type="submit" className="btn btn-primary" disabled={createDN.isPending || lines.length === 0}
                                style={{ padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px', background: 'rgba(255,255,255,0.2)', color: 'white', border: '1px solid rgba(255,255,255,0.3)' }}>
                                {createDN.isPending ? 'Saving...' : 'Save Delivery Note'}
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

                        {/* Delivery Details Card */}
                        <div className="card" style={{ padding: '1.75rem' }}>
                            <div style={sectionHeaderStyle}>
                                <span style={iconBoxStyle}><FileText size={16} color="#4f46e5" /></span>
                                Delivery Details
                            </div>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                    <div>
                                        <label style={labelStyle}>Sales Order<span className="required-mark"> *</span></label>
                                        <select style={selectStyle} value={selectedOrderId || ''}
                                            onChange={e => setSelectedOrderId(e.target.value ? Number(e.target.value) : undefined)} required>
                                            <option value="">Select Posted Sales Order</option>
                                            {ordersList.map((o: any) => (
                                                <option key={o.id} value={o.id}>{o.order_number} — {o.customer_name}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Delivery Date<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="date" value={header.delivery_date}
                                            onChange={e => setHeader({ ...header, delivery_date: e.target.value })} required />
                                    </div>
                                </div>

                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                    <div>
                                        <label style={labelStyle}>Delivered By<span className="required-mark"> *</span></label>
                                        <input style={inputStyle} type="text" placeholder="Person delivering"
                                            value={header.delivered_by}
                                            onChange={e => setHeader({ ...header, delivered_by: e.target.value })} required />
                                    </div>
                                    <div>
                                        <label style={labelStyle}>Driver Name</label>
                                        <input style={inputStyle} type="text" placeholder="Driver name"
                                            value={header.driver_name}
                                            onChange={e => setHeader({ ...header, driver_name: e.target.value })} />
                                    </div>
                                </div>

                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                    <div>
                                        <label style={labelStyle}>Vehicle Number</label>
                                        <input style={inputStyle} type="text" placeholder="Vehicle number"
                                            value={header.vehicle_number}
                                            onChange={e => setHeader({ ...header, vehicle_number: e.target.value })} />
                                    </div>
                                </div>

                                <div>
                                    <label style={labelStyle}>Notes</label>
                                    <textarea
                                        style={{ ...inputStyle, minHeight: '70px', resize: 'vertical', fontFamily: 'inherit' }}
                                        placeholder="Delivery notes..."
                                        value={header.notes}
                                        onChange={e => setHeader({ ...header, notes: e.target.value })}
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Line Items Card */}
                        {lines.length > 0 && (
                            <div className="card" style={{ padding: '1.75rem' }}>
                                <div style={sectionHeaderStyle}>
                                    <span style={iconBoxStyle}><LayoutGrid size={16} color="#4f46e5" /></span>
                                    Delivery Lines
                                </div>

                                <div style={{ overflowX: 'auto' }}>
                                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                        <thead>
                                            <tr>
                                                <th style={thStyle}>Item Description</th>
                                                <th style={{ ...thStyle, width: '100px', textAlign: 'right' }}>Ordered Qty</th>
                                                <th style={{ ...thStyle, width: '130px', textAlign: 'right' }}>Unit Price</th>
                                                <th style={{ ...thStyle, width: '120px' }}>Qty to Deliver</th>
                                                <th style={{ ...thStyle, width: '110px', textAlign: 'right' }}>Line Total</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {lines.map((line, idx) => {
                                                const qtyDel = parseFloat(line.quantity_delivered || '0');
                                                const lineTotal = qtyDel * line.unit_price;
                                                return (
                                                    <tr key={idx} style={{ borderBottom: '1px solid var(--color-border, #e2e8f0)' }}>
                                                        <td style={{ padding: '0.6rem 0.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>
                                                            {line.item_description}
                                                        </td>
                                                        <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                                            {line.ordered_qty}
                                                        </td>
                                                        <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                                            {formatCurrency(line.unit_price)}
                                                        </td>
                                                        <td style={{ padding: '0.35rem 0.5rem' }}>
                                                            <input style={{ ...inputStyle, fontSize: 'var(--text-sm)', padding: '0.5rem 0.625rem' }}
                                                                type="number" step="0.01" min="0" max={line.ordered_qty}
                                                                value={line.quantity_delivered} onChange={e => updateLineQty(idx, e.target.value)} required />
                                                        </td>
                                                        <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>
                                                            {formatCurrency(lineTotal)}
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                        <tfoot>
                                            <tr>
                                                <td colSpan={4} style={{ padding: '0.75rem 0.5rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)', color: 'var(--color-text)', borderTop: '2px solid var(--color-border, #e2e8f0)' }}>
                                                    Total Delivery Value:
                                                </td>
                                                <td style={{ padding: '0.75rem 0.5rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)', color: '#4f46e5', borderTop: '2px solid var(--color-border, #e2e8f0)' }}>
                                                    {formatCurrency(totalDeliveryValue)}
                                                </td>
                                            </tr>
                                        </tfoot>
                                    </table>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* RIGHT COLUMN — Summary */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                        {/* Delivery Info Card */}
                        <div className="card" style={{ padding: '1.75rem' }}>
                            <div style={sectionHeaderStyle}>
                                <span style={iconBoxStyle}><Truck size={16} color="#4f46e5" /></span>
                                Delivery Info
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                    <span>Sales Order</span>
                                    <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>
                                        {selectedOrder?.order_number || '—'}
                                    </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                    <span>Customer</span>
                                    <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>
                                        {selectedOrder?.customer_name || '—'}
                                    </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                    <span>Items</span>
                                    <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>
                                        {lines.length}
                                    </span>
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
                                Delivery Summary
                            </p>
                            <p style={{ fontSize: 'var(--text-xs)', opacity: 0.8, marginBottom: '0.5rem' }}>
                                Total Delivery Value
                            </p>
                            <p style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: '-0.025em', marginBottom: '1.25rem' }}>
                                {formatCurrency(totalDeliveryValue)}
                            </p>
                            <div style={{ borderTop: '1px solid rgba(255,255,255,0.2)', paddingTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                    <span style={{ opacity: 0.85 }}>Line Items</span>
                                    <span style={{ fontWeight: 600 }}>{lines.filter(l => parseFloat(l.quantity_delivered || '0') > 0).length}</span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                                    <span style={{ opacity: 0.85 }}>Status</span>
                                    <span style={{ fontWeight: 600 }}>Draft</span>
                                </div>
                            </div>

                            {selectedOrderId && (
                                <div style={{
                                    marginTop: '1.25rem', padding: '0.75rem', borderRadius: '8px',
                                    background: 'rgba(255,255,255,0.15)',
                                    display: 'flex', alignItems: 'center', gap: '0.5rem',
                                    fontSize: 'var(--text-xs)',
                                }}>
                                    <Info size={16} style={{ flexShrink: 0, opacity: 0.9 }} />
                                    <span>Delivery note will be saved as Draft. Post to update inventory.</span>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </form>
        </AccountingLayout>
    );
};

export default DeliveryNoteForm;
