import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useItem, useCreateItem, useUpdateItem, useDeleteItem, useProductCategories } from '../hooks/useInventory';
import apiClient from '../../../api/client';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import { Save, X, Trash2, Package } from 'lucide-react';
import LoadingScreen from '../../../components/common/LoadingScreen';

interface GLAccount {
    id: number;
    code: string;
    name: string;
    account_type: string;
    is_active: boolean;
}

const ItemForm = () => {
    const navigate = useNavigate();
    const { id } = useParams();
    const isEdit = Boolean(id);
    const itemId = isEdit && id ? Number(id) : undefined;
    const { data: item, isLoading } = useItem(itemId!);

    // Show all categories — selecting one auto-sets product_type from the category's assigned type
    const { data: productCategories } = useProductCategories();

    const createItem = useCreateItem();
    const updateItem = useUpdateItem();
    const deleteItem = useDeleteItem();
    const [formError, setFormError] = useState<string | null>(null);
    const [confirmDeleteItem, setConfirmDeleteItem] = useState(false);

    // Fetch all GL accounts for filtered dropdowns
    const { data: accountsData } = useQuery<GLAccount[]>({
        queryKey: ['gl-accounts-all'],
        queryFn: () => apiClient.get('/accounting/accounts/', { params: { page_size: 9999 } }).then(res => { const d = res.data; return Array.isArray(d) ? d : Array.isArray(d?.results) ? d.results : []; }),
        staleTime: 5 * 60 * 1000,
    });

    const allAccounts = useMemo(() => (Array.isArray(accountsData) ? accountsData : []), [accountsData]);
    const assetAccounts = useMemo(() => allAccounts.filter(a => a.account_type === 'Asset' && a.is_active), [allAccounts]);
    const expenseAccounts = useMemo(() => allAccounts.filter(a => a.account_type === 'Expense' && a.is_active), [allAccounts]);

    const { data: bomsData } = useQuery({
        queryKey: ['production-boms'],
        queryFn: () => apiClient.get('/production/bills-of-materials/', { params: { page_size: 9999 } })
            .then(res => { const d = res.data; return Array.isArray(d) ? d : Array.isArray(d?.results) ? d.results : []; }),
        staleTime: 5 * 60 * 1000,
    });
    const boms = useMemo(() => (Array.isArray(bomsData) ? bomsData : []), [bomsData]);

    const [formData, setFormData] = useState({
        sku: '',
        name: '',
        description: '',
        product_type: '',
        product_category: '',
        unit_of_measure: 'PCS',
        valuation_method: 'WA',
        standard_price: '0',
        selling_price: '0',
        shelf_life_days: '',
        reorder_point: '0',
        reorder_quantity: '0',
        min_stock: '0',
        max_stock: '0',
        barcode: '',
        is_active: true,
        inventory_account: '',
        expense_account: '',
        production_bom: '',
    });

    useEffect(() => {
        if (isEdit && item) {
            setFormData({
                sku: item.sku || '',
                name: item.name || '',
                description: item.description || '',
                product_type: item.product_type || '',
                product_category: item.product_category || '',
                unit_of_measure: item.unit_of_measure || 'PCS',
                valuation_method: item.valuation_method || 'WA',
                standard_price: String(item.standard_price || 0),
                selling_price: String(item.selling_price || 0),
                shelf_life_days: item.shelf_life_days != null ? String(item.shelf_life_days) : '',
                reorder_point: String(item.reorder_point || 0),
                reorder_quantity: String(item.reorder_quantity || 0),
                min_stock: String(item.min_stock || 0),
                max_stock: String(item.max_stock || 0),
                barcode: item.barcode || '',
                is_active: item.is_active ?? true,
                inventory_account: item.inventory_account || '',
                expense_account: item.expense_account || '',
                production_bom: item.production_bom ? String(item.production_bom) : '',
            });
        }
    }, [isEdit, item]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const payload: any = {
            sku: formData.sku,
            name: formData.name,
            description: formData.description,
            barcode: formData.barcode,
            unit_of_measure: formData.unit_of_measure,
            valuation_method: formData.valuation_method,
            is_active: formData.is_active,
            // FK fields: empty string → null so Django doesn't reject them
            product_type: formData.product_type ? Number(formData.product_type) : null,
            product_category: formData.product_category ? Number(formData.product_category) : null,
            inventory_account: formData.inventory_account ? Number(formData.inventory_account) : null,
            expense_account: formData.expense_account ? Number(formData.expense_account) : null,
            production_bom: formData.production_bom ? parseInt(formData.production_bom) : null,
            // Numeric fields
            standard_price: parseFloat(formData.standard_price) || 0,
            selling_price: parseFloat(formData.selling_price) || 0,
            reorder_point: parseFloat(formData.reorder_point) || 0,
            reorder_quantity: parseFloat(formData.reorder_quantity) || 0,
            min_stock: parseFloat(formData.min_stock) || 0,
            max_stock: parseFloat(formData.max_stock) || 0,
            shelf_life_days: formData.shelf_life_days !== '' ? parseInt(formData.shelf_life_days) : null,
        };
        try {
            if (isEdit) {
                await updateItem.mutateAsync({ id: Number(id), data: payload });
            } else {
                await createItem.mutateAsync(payload);
            }
            navigate('/inventory');
        } catch (err: any) {
            const msg = err?.response?.data?.detail || err?.response?.data?.error ||
                (typeof err?.response?.data === 'object' ? JSON.stringify(err.response.data) : null) ||
                err?.message || 'An unexpected error occurred';
            setFormError(msg);
        }
    };

    const handleDelete = async () => {
        try {
            await deleteItem.mutateAsync(Number(id));
            navigate('/inventory');
        } catch (err: any) {
            const msg = err?.response?.data?.detail || err?.message || 'Error deleting item';
            setFormError(msg);
            setConfirmDeleteItem(false);
        }
    };

    const labelStyle: React.CSSProperties = {
        display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-xs)',
        fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)',
    };
    const helpStyle: React.CSSProperties = {
        fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px',
    };

    if (isEdit && isLoading) return <LoadingScreen message="Loading..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <form onSubmit={handleSubmit}>
                    <PageHeader
                        title={isEdit ? 'Edit Product' : 'New Product'}
                        subtitle={isEdit ? 'Update product details' : 'Create a new inventory product'}
                        icon={<Package size={22} />}
                        actions={
                            <>
                                {isEdit && !confirmDeleteItem && (
                                    <button type="button" className="btn btn-outline" onClick={() => setConfirmDeleteItem(true)} style={{ color: 'var(--color-error)' }}>
                                        <Trash2 size={18} /> Delete
                                    </button>
                                )}
                                {isEdit && confirmDeleteItem && (
                                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                        <span style={{ fontSize: '0.85rem', color: '#dc2626' }}>Delete this item?</span>
                                        <button type="button" onClick={handleDelete}
                                            style={{ background: '#dc2626', color: 'white', border: 'none', borderRadius: '4px', padding: '4px 12px', cursor: 'pointer', fontWeight: 600 }}>
                                            Yes
                                        </button>
                                        <button type="button" onClick={() => setConfirmDeleteItem(false)}
                                            style={{ background: '#e2e8f0', border: 'none', borderRadius: '4px', padding: '4px 12px', cursor: 'pointer' }}>
                                            No
                                        </button>
                                    </div>
                                )}
                                <button type="button" className="btn btn-outline" onClick={() => navigate('/inventory')}>
                                    <X size={18} /> Cancel
                                </button>
                                <button type="submit" className="btn btn-primary" disabled={createItem.isPending || updateItem.isPending}>
                                    <Save size={18} /> {createItem.isPending || updateItem.isPending ? 'Saving...' : isEdit ? 'Update' : 'Create'}
                                </button>
                            </>
                        }
                    />

                    {formError && (
                        <div style={{ padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626', borderRadius: '8px', marginBottom: '1rem' }}>
                            {formError}
                        </div>
                    )}

                    {/* ── Basic Information ────────────────────── */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>Basic Information</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>SKU<span className="required-mark"> *</span></label>
                                <input type="text" className="input" value={formData.sku} onChange={e => setFormData({ ...formData, sku: e.target.value })} required placeholder="e.g., ITEM-001" />
                            </div>
                            <div>
                                <label style={labelStyle}>Name<span className="required-mark"> *</span></label>
                                <input type="text" className="input" value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} required placeholder="Product name" />
                            </div>
                            <div>
                                <label style={labelStyle}>Barcode</label>
                                <input type="text" className="input" value={formData.barcode} onChange={e => setFormData({ ...formData, barcode: e.target.value })} placeholder="Barcode number" />
                            </div>
                            {/* Product Category — auto-sets product_type from category's assigned type */}
                            <div>
                                <label style={labelStyle}>Product Category<span className="required-mark"> *</span></label>
                                <select
                                    className="input"
                                    value={formData.product_category}
                                    onChange={e => {
                                        const catId = e.target.value;
                                        const cats = productCategories?.results || productCategories || [];
                                        const selectedCat = cats.find((pc: any) => String(pc.id) === catId);
                                        setFormData({
                                            ...formData,
                                            product_category: catId,
                                            product_type: selectedCat?.product_type ? String(selectedCat.product_type) : formData.product_type,
                                        });
                                    }}
                                    required
                                >
                                    <option value="">— Select category —</option>
                                    {(productCategories?.results || productCategories || []).map((pc: any) => (
                                        <option key={pc.id} value={pc.id}>{pc.name}</option>
                                    ))}
                                </select>
                                <p style={helpStyle}>GL accounts are inherited from the category's Product Type.</p>
                            </div>
                            <div>
                                <label style={labelStyle}>Unit of Measure<span className="required-mark"> *</span></label>
                                <select className="input" value={formData.unit_of_measure} onChange={e => setFormData({ ...formData, unit_of_measure: e.target.value })}>
                                    <option value="PCS">Pieces</option>
                                    <option value="KG">Kilogram</option>
                                    <option value="L">Liter</option>
                                    <option value="M">Meter</option>
                                    <option value="BOX">Box</option>
                                    <option value="PKT">Packet</option>
                                    <option value="SET">Set</option>
                                </select>
                            </div>
                        </div>
                        <div style={{ marginTop: '1.5rem' }}>
                            <label style={labelStyle}>Description</label>
                            <textarea className="input" value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} rows={3} placeholder="Product description" style={{ width: '100%' }} />
                        </div>
                    </div>

                    {/* ── Pricing & Valuation ──────────────────── */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '0.35rem' }}>Pricing & Valuation</h3>
                        <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', marginBottom: '1.5rem' }}>
                            Standard Price is set at creation and used as the cost baseline. Current Cost Price is updated automatically on each goods receipt based on the valuation method.
                        </p>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>Valuation Method</label>
                                <select className="input" value={formData.valuation_method} onChange={e => setFormData({ ...formData, valuation_method: e.target.value })}>
                                    <option value="WA">Weighted Average</option>
                                    <option value="FIFO">FIFO</option>
                                    <option value="LIFO">LIFO</option>
                                    <option value="STD">Standard Cost</option>
                                </select>
                                <p style={helpStyle}>
                                    {formData.valuation_method === 'STD'
                                        ? 'Cost price is always fixed at the Standard Price — purchase price variances are not reflected.'
                                        : formData.valuation_method === 'WA'
                                        ? 'Cost price is updated as a running weighted average of all receipts.'
                                        : formData.valuation_method === 'FIFO'
                                        ? 'Cost price reflects the oldest remaining batch cost layer.'
                                        : 'Cost price reflects the most recently received batch cost layer.'}
                                </p>
                            </div>
                            <div>
                                <label style={labelStyle}>Standard Price<span className="required-mark"> *</span></label>
                                <input type="number" className="input" value={formData.standard_price}
                                    onChange={e => setFormData({ ...formData, standard_price: e.target.value })}
                                    step="0.0001" min="0" />
                                <p style={helpStyle}>
                                    {formData.valuation_method === 'STD'
                                        ? 'This price is used as the cost price and never changes automatically.'
                                        : 'Initial cost baseline. Will be superseded by purchase receipts.'}
                                </p>
                            </div>
                            <div>
                                <label style={labelStyle}>Selling Price</label>
                                <input type="number" className="input" value={formData.selling_price} onChange={e => setFormData({ ...formData, selling_price: e.target.value })} step="0.01" min="0" />
                            </div>
                            <div>
                                <label style={labelStyle}>Shelf Life (days)</label>
                                <input type="number" className="input" value={formData.shelf_life_days}
                                    onChange={e => setFormData({ ...formData, shelf_life_days: e.target.value })}
                                    min="1" step="1" placeholder="e.g. 365" />
                                <p style={helpStyle}>Used to auto-suggest expiry date when receiving goods (GRN). Leave blank for non-perishable items.</p>
                            </div>
                        </div>

                        {/* Read-only current cost price — only meaningful on edit */}
                        {isEdit && item && (
                            <div style={{
                                marginTop: '1.5rem', padding: '1rem 1.25rem',
                                background: 'rgba(79,70,229,0.06)', borderRadius: '10px',
                                border: '1px solid rgba(79,70,229,0.15)',
                                display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1.5rem',
                            }}>
                                <div>
                                    <span style={{ ...labelStyle, color: 'var(--color-text-muted)' }}>Current Cost Price</span>
                                    <span style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: '#4f46e5' }}>
                                        {Number(item.cost_price || 0).toFixed(4)}
                                    </span>
                                    <p style={helpStyle}>Last computed from {item.valuation_method === 'STD' ? 'Standard Price' : item.valuation_method === 'WA' ? 'Weighted Average' : item.valuation_method === 'FIFO' ? 'FIFO layers' : 'LIFO layers'}</p>
                                </div>
                                <div>
                                    <span style={{ ...labelStyle, color: 'var(--color-text-muted)' }}>Average Cost (live)</span>
                                    <span style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)' }}>
                                        {Number(item.average_cost || 0).toFixed(4)}
                                    </span>
                                    <p style={helpStyle}>Derived from total_value ÷ total_quantity</p>
                                </div>
                                <div>
                                    <span style={{ ...labelStyle, color: 'var(--color-text-muted)' }}>Stock on Hand</span>
                                    <span style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)' }}>
                                        {Number(item.total_quantity || 0).toFixed(2)} {item.unit_of_measure}
                                    </span>
                                    <p style={helpStyle}>Total value: {Number(item.total_value || 0).toFixed(2)}</p>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* ── Stock Settings ────────────────────────── */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>Stock & Reorder Settings</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>Reorder Point</label>
                                <input type="number" className="input" value={formData.reorder_point} onChange={e => setFormData({ ...formData, reorder_point: e.target.value })} />
                            </div>
                            <div>
                                <label style={labelStyle}>Reorder Qty</label>
                                <input type="number" className="input" value={formData.reorder_quantity} onChange={e => setFormData({ ...formData, reorder_quantity: e.target.value })} />
                            </div>
                            <div>
                                <label style={labelStyle}>Min Stock</label>
                                <input type="number" className="input" value={formData.min_stock} onChange={e => setFormData({ ...formData, min_stock: e.target.value })} />
                            </div>
                            <div>
                                <label style={labelStyle}>Max Stock</label>
                                <input type="number" className="input" value={formData.max_stock} onChange={e => setFormData({ ...formData, max_stock: e.target.value })} />
                            </div>
                        </div>
                        <div style={{ marginTop: '1rem' }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                                <input type="checkbox" checked={formData.is_active} onChange={e => setFormData({ ...formData, is_active: e.target.checked })} />
                                <span>Active (product can be used in transactions)</span>
                            </label>
                        </div>
                    </div>

                    {/* ── GL Accounts (read-only, inherited from Product Type) ── */}
                    <div className="card" style={{ marginBottom: '1.5rem' }}>
                        <h3 style={{ marginBottom: '0.5rem' }}>GL Accounts</h3>
                        <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', marginBottom: '1.5rem' }}>
                            GL accounts are inherited from the Product Type. To change them, update the Product Type configuration.
                        </p>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                            <div>
                                <label style={labelStyle}>Inventory GL (Asset)</label>
                                <div style={{
                                    padding: '0.625rem 0.875rem', borderRadius: '8px',
                                    border: '1px solid var(--color-border)', background: 'var(--color-surface-hover, #f8fafc)',
                                    color: 'var(--color-text)', fontSize: 'var(--text-sm)', minHeight: '40px',
                                    display: 'flex', alignItems: 'center',
                                }}>
                                    {(() => {
                                        if (formData.inventory_account) {
                                            const acc = assetAccounts.find(a => String(a.id) === String(formData.inventory_account));
                                            return acc ? `${acc.code} - ${acc.name}` : `Account #${formData.inventory_account}`;
                                        }
                                        if (isEdit && item?.inventory_account_name) return item.inventory_account_name;
                                        return <span style={{ color: 'var(--color-text-muted)' }}>Inherited from Product Type</span>;
                                    })()}
                                </div>
                            </div>
                            <div>
                                <label style={labelStyle}>Expense GL (COGS)</label>
                                <div style={{
                                    padding: '0.625rem 0.875rem', borderRadius: '8px',
                                    border: '1px solid var(--color-border)', background: 'var(--color-surface-hover, #f8fafc)',
                                    color: 'var(--color-text)', fontSize: 'var(--text-sm)', minHeight: '40px',
                                    display: 'flex', alignItems: 'center',
                                }}>
                                    {(() => {
                                        if (formData.expense_account) {
                                            const acc = expenseAccounts.find(a => String(a.id) === String(formData.expense_account));
                                            return acc ? `${acc.code} - ${acc.name}` : `Account #${formData.expense_account}`;
                                        }
                                        if (isEdit && item?.expense_account_name) return item.expense_account_name;
                                        return <span style={{ color: 'var(--color-text-muted)' }}>Inherited from Product Type</span>;
                                    })()}
                                </div>
                            </div>
                        </div>
                        <div style={{ marginTop: '1.5rem' }}>
                            <div style={{ marginBottom: '1rem' }}>
                                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                                    Production BOM
                                </label>
                                <select
                                    className="input"
                                    value={formData.production_bom}
                                    onChange={e => setFormData({ ...formData, production_bom: e.target.value })}
                                >
                                    <option value="">None (not a manufactured item)</option>
                                    {boms.map((b: any) => (
                                        <option key={b.id} value={b.id}>{b.item_code} — {b.item_name}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    </div>
                </form>
            </main>
        </div>
    );
};

export default ItemForm;
