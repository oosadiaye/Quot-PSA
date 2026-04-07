import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, FileText, Layers, Info, LayoutGrid, Building2, Package } from 'lucide-react';
import { useCreatePR } from './hooks/useProcurement';
import { useDimensions } from '../accounting/hooks/useJournal';
import { useCostCenters } from '../accounting/hooks/useCostCenters';
import { useFixedAssets } from '../accounting/hooks/useAccountingEnhancements';
import { useItems } from '../inventory/hooks/useInventory';
import { useIsDimensionsEnabled } from '../../hooks/useTenantModules';
import { useCurrency } from '../../context/CurrencyContext';
import { safeAdd, safeMultiply } from '../accounting/utils/currency';
import AccountingLayout from '../accounting/AccountingLayout';
import PageHeader from '../../components/PageHeader';
import '../accounting/styles/glassmorphism.css';

interface PRLine {
    id: string;
    item_description: string;
    quantity: string;
    estimated_unit_price: string;
    asset: string;
    item: string;
}

const PurchaseRequisitionForm = () => {
    const navigate = useNavigate();
    const { data: dims, isLoading: dimsLoading } = useDimensions();
    const { data: costCenters } = useCostCenters({ is_active: true });
    const { data: assets } = useFixedAssets({ status: 'Active' });
    const { data: itemsData } = useItems();
    const itemsList = itemsData?.results || itemsData || [];
    const { isEnabled: dimensionsEnabled } = useIsDimensionsEnabled();
    const { formatCurrency, currencySymbol } = useCurrency();
    const createPR = useCreatePR();

    const [header, setHeader] = useState({
        description: '',
        requested_date: new Date().toISOString().split('T')[0],
        required_date: '',
        cost_center: '',
        fund: '',
        function: '',
        program: '',
        geo: '',
    });

    const [lines, setLines] = useState<PRLine[]>([
        { id: crypto.randomUUID(), item_description: '', quantity: '1', estimated_unit_price: '0', asset: '', item: '' },
    ]);

    const [formError, setFormError] = useState('');

    const totalEstimated = useMemo(() => {
        return lines.reduce((sum, l) => {
            return safeAdd(sum, safeMultiply(l.quantity || '0', l.estimated_unit_price || '0'));
        }, 0);
    }, [lines]);

    const addLine = () => setLines([...lines, { id: crypto.randomUUID(), item_description: '', quantity: '1', estimated_unit_price: '0', asset: '', item: '' }]);
    const removeLine = (index: number) => setLines(lines.filter((_, i) => i !== index));

    const updateLine = (index: number, field: keyof PRLine, value: string) => {
        const newLines = [...lines];
        newLines[index][field] = value;
        // Auto-fill description when item is selected
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
            description: header.description,
            requested_date: header.requested_date,
            ...(header.required_date ? { required_date: header.required_date } : {}),
            cost_center: header.cost_center ? Number(header.cost_center) : null,
            lines: lines.map(l => ({
                item_description: l.item_description,
                quantity: parseFloat(l.quantity),
                estimated_unit_price: parseFloat(l.estimated_unit_price),
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
            await createPR.mutateAsync(payload);
            navigate('/procurement/requisitions');
        } catch (err: any) {
            const data = err.response?.data;
            if (data?.detail) {
                setFormError(data.detail);
            } else if (data && typeof data === 'object') {
                const messages = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`);
                setFormError(messages.join(' | ') || 'Failed to create requisition.');
            } else {
                setFormError(err.message || 'Failed to create requisition.');
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
                    title="New Purchase Requisition"
                    subtitle={dimensionsEnabled
                        ? 'Create a purchase requisition with dimension tagging.'
                        : 'Create a purchase requisition.'}
                    icon={<FileText size={22} />}
                    onBack={() => navigate('/procurement/requisitions')}
                    actions={
                        <>
                            <button type="button" className="btn btn-outline" onClick={() => navigate('/procurement/requisitions')}
                                style={{ padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px', color: 'white', borderColor: 'rgba(255,255,255,0.3)' }}>
                                Cancel
                            </button>
                            <button type="submit" className="btn btn-primary" disabled={createPR.isPending || lines.length === 0}
                                style={{ padding: '0.6rem 1.5rem', fontWeight: 600, borderRadius: '8px', background: 'rgba(255,255,255,0.18)', color: 'white', border: '1px solid rgba(255,255,255,0.25)' }}>
                                Save Requisition
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

                    {/* LEFT / MAIN COLUMN */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                        {/* Requisition Details Card */}
                        <div className="card" style={{ padding: '1.75rem' }}>
                            <div style={sectionHeaderStyle}>
                                <span style={iconBoxStyle}><FileText size={16} color="#4f46e5" /></span>
                                Requisition Details
                            </div>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                                {/* PR Number */}
                                <div>
                                    <label style={labelStyle}>PR Number</label>
                                    <div style={{
                                        ...inputStyle,
                                        display: 'flex', alignItems: 'center', gap: '0.5rem',
                                        background: 'rgba(255,255,255,0.04)',
                                        color: 'var(--color-text-muted)',
                                        cursor: 'default',
                                    }}>
                                        <span style={{
                                            fontSize: 'var(--text-xs)', fontWeight: 700,
                                            background: 'rgba(79,70,229,0.15)', color: '#818cf8',
                                            padding: '0.1rem 0.45rem', borderRadius: '4px',
                                            letterSpacing: '0.03em',
                                        }}>AUTO</span>
                                        <span style={{ fontSize: 'var(--text-sm)' }}>PR-{new Date().getFullYear()}-XXXXX</span>
                                    </div>
                                </div>

                                {/* Requested Date + Expected Date */}
                                <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '1rem' }}>
                                    <div>
                                        <label style={labelStyle}>Requested Date<span className="required-mark"> *</span></label>
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

                                {/* Description */}
                                <div>
                                    <label style={labelStyle}>Description<span className="required-mark"> *</span></label>
                                    <textarea
                                        style={{ ...inputStyle, minHeight: '90px', resize: 'vertical', fontFamily: 'inherit' }}
                                        placeholder="Describe what is being requested and the justification..."
                                        value={header.description}
                                        onChange={e => setHeader({ ...header, description: e.target.value })}
                                        required
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
                                            <th style={{ ...thStyle, width: '200px' }}>Inventory Item</th>
                                            <th style={thStyle}>Item Description</th>
                                            <th style={{ ...thStyle, width: '170px' }}>Asset</th>
                                            <th style={{ ...thStyle, width: '80px' }}>Qty</th>
                                            <th style={{ ...thStyle, width: '120px' }}>Est. Unit Price</th>
                                            <th style={{ ...thStyle, width: '100px', textAlign: 'right' }}>Est. Total</th>
                                            <th style={{ width: '36px' }}></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {lines.map((line, idx) => {
                                            const lineTotal = safeMultiply(line.quantity || '0', line.estimated_unit_price || '0');
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
                                                                value={line.estimated_unit_price} onChange={e => updateLine(idx, 'estimated_unit_price', e.target.value)} required />
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
                                            <td colSpan={5} style={{ padding: '0.75rem 0.35rem', textAlign: 'right', fontWeight: 700, fontSize: 'var(--text-sm)', color: 'var(--color-text)', borderTop: '2px solid var(--color-border, #e2e8f0)' }}>
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
                </div>
            </form>
        </AccountingLayout>
    );
};

export default PurchaseRequisitionForm;
