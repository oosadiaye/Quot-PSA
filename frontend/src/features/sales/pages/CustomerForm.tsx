import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
    useCustomer, useCreateCustomer, useUpdateCustomer, useDeleteCustomer,
    useCustomerCategories,
} from '../hooks/useSales';
import { useDialog } from '../../../hooks/useDialog';
import { useWithholdingTaxes } from '../../accounting/hooks/useAccountingEnhancements';
import SalesLayout from '../layout/SalesLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Save, Trash2, X, Info, Tag, ShieldCheck } from 'lucide-react';

const labelStyle: React.CSSProperties = {
    display: 'block',
    marginBottom: '0.5rem',
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
    color: 'var(--color-text-muted)',
};

const readonlyBoxStyle: React.CSSProperties = {
    padding: '0.625rem 0.875rem',
    borderRadius: '8px',
    border: '1px solid var(--color-border)',
    background: 'rgba(0,0,0,0.03)',
    fontSize: 'var(--text-sm)',
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    minHeight: '38px',
};

const CustomerForm = () => {
    const navigate = useNavigate();
    const { showConfirm } = useDialog();
    const { id } = useParams();
    const isEdit = Boolean(id);
    const customerId = isEdit && id ? Number(id) : undefined;

    const { data: customer, isLoading } = useCustomer(customerId!);
    const { data: categoriesRaw } = useCustomerCategories();
    const { data: whtList } = useWithholdingTaxes({ is_active: true });
    const createCustomer = useCreateCustomer();
    const updateCustomer = useUpdateCustomer();
    const deleteCustomer = useDeleteCustomer();

    const categories: any[] = useMemo(() => categoriesRaw ?? [], [categoriesRaw]);

    const PAYMENT_TERMS = [
        { value: 'immediate', label: 'Due on Receipt (0 days)' },
        { value: 'net_7',  label: 'Net 7 (7 days)' },
        { value: 'net_15', label: 'Net 15 (15 days)' },
        { value: 'net_30', label: 'Net 30 (30 days)' },
        { value: 'net_45', label: 'Net 45 (45 days)' },
        { value: 'net_60', label: 'Net 60 (60 days)' },
        { value: 'net_90', label: 'Net 90 (90 days)' },
    ];

    const [formData, setFormData] = useState({
        name: '',
        customer_code: '',
        contact_email: '',
        contact_phone: '',
        contact_person: '',
        address: '',
        vat_number: '',
        credit_limit: '0',
        industry: '',
        website: '',
        is_active: true,
        category: '',
        payment_terms: 'net_30',
        withholding_tax_code: '' as string | number,
        wht_exempt: false,
    });

    const [formError, setFormError] = useState<string | null>(null);

    useEffect(() => {
        if (isEdit && customer) {
            setFormData({
                name: customer.name || '',
                customer_code: customer.customer_code || '',
                contact_email: customer.contact_email || '',
                contact_phone: customer.contact_phone || '',
                contact_person: customer.contact_person || '',
                address: customer.address || '',
                vat_number: customer.vat_number || '',
                credit_limit: String(customer.credit_limit || 0),
                industry: customer.industry || '',
                website: customer.website || '',
                is_active: customer.is_active ?? true,
                category: customer.category ? String(customer.category) : '',
                payment_terms: customer.payment_terms || 'net_30',
                withholding_tax_code: customer.withholding_tax_code ? String(customer.withholding_tax_code) : '',
                wht_exempt: customer.wht_exempt ?? false,
            });
        }
    }, [isEdit, customer]);

    // Derived: selected category (for AR preview)
    const selectedCategory = useMemo(
        () => categories.find((c) => String(c.id) === formData.category) ?? null,
        [categories, formData.category],
    );

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError(null);

        if (!formData.category) {
            setFormError('Customer category is required.');
            return;
        }

        const payload: Record<string, any> = {
            ...formData,
            credit_limit: parseFloat(formData.credit_limit),
            category: Number(formData.category),
            withholding_tax_code: formData.withholding_tax_code ? Number(formData.withholding_tax_code) : null,
        };

        try {
            if (isEdit) {
                await updateCustomer.mutateAsync({ id: Number(id), data: payload });
            } else {
                await createCustomer.mutateAsync(payload);
            }
            navigate('/sales/customers');
        } catch (err: any) {
            const errData = err.response?.data;
            const msg =
                errData?.detail ||
                errData?.category?.[0] ||
                errData?.customer_code?.[0] ||
                (typeof errData === 'object' ? JSON.stringify(errData) : null) ||
                err?.message ||
                'Error saving customer';
            setFormError(msg);
        }
    };

    const handleDelete = async () => {
        if (await showConfirm('Are you sure you want to delete this customer?')) {
            try {
                await deleteCustomer.mutateAsync(Number(id));
                navigate('/sales/customers');
            } catch {
                setFormError('Error deleting customer');
            }
        }
    };

    if (isEdit && isLoading) return <LoadingScreen message="Loading..." />;

    return (
        <SalesLayout title={isEdit ? 'Edit Customer' : 'New Customer'} description="Manage customer information">
            <form onSubmit={handleSubmit}>

                {/* ── Error banner */}
                {formError && (
                    <div style={{
                        padding: '0.75rem 1rem', marginBottom: '1.25rem',
                        background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
                        borderRadius: '8px', color: 'var(--color-error)',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        fontSize: 'var(--text-sm)',
                    }}>
                        <span>{formError}</span>
                        <button type="button" onClick={() => setFormError(null)}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-error)' }}>
                            <X size={15} />
                        </button>
                    </div>
                )}

                {/* ── Customer Category — required, drives AR GL */}
                <div className="card" style={{ marginBottom: '1.5rem', borderTop: '3px solid var(--color-primary)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                        <Tag size={16} style={{ color: 'var(--color-primary)' }} />
                        <h3 style={{ margin: 0 }}>Customer Category</h3>
                    </div>
                    <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', marginBottom: '1.25rem' }}>
                        The category determines which AR GL account is used for this customer.
                        Categories and their GL accounts are pre-configured in <strong>Customer Categories</strong>.
                    </p>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem' }}>
                        {/* Category selector */}
                        <div>
                            <label style={labelStyle}>
                                Category <span style={{ color: 'var(--color-error)' }}>*</span>
                            </label>
                            <select
                                className="input"
                                value={formData.category}
                                onChange={e => setFormData({ ...formData, category: e.target.value })}
                                required
                                style={!formData.category ? { borderColor: 'var(--color-error)' } : {}}
                            >
                                <option value="">— Select category —</option>
                                {categories.map((c: any) => (
                                    <option key={c.id} value={c.id}>{c.code} — {c.name}</option>
                                ))}
                            </select>
                            {!formData.category && (
                                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-error)', marginTop: '4px', display: 'block' }}>
                                    Category is required
                                </span>
                            )}
                        </div>

                        {/* AR account — read-only from category */}
                        <div>
                            <label style={labelStyle}>AR GL Account (from category)</label>
                            <div style={{
                                ...readonlyBoxStyle,
                                color: selectedCategory ? 'var(--color-text)' : 'var(--color-text-muted)',
                            }}>
                                <Info size={13} style={{ color: 'var(--color-primary)', flexShrink: 0 }} />
                                {selectedCategory?.accounts_receivable_account_name
                                    ? <span>
                                        <strong style={{ fontFamily: 'monospace' }}>{selectedCategory.accounts_receivable_account_code}</strong>
                                        {' — '}{selectedCategory.accounts_receivable_account_name}
                                      </span>
                                    : <span>{selectedCategory ? 'No AR account on this category' : 'Select a category to see the AR account'}</span>
                                }
                            </div>
                        </div>
                    </div>
                </div>

                {/* ── Basic Information */}
                <div className="card" style={{ marginBottom: '1.5rem' }}>
                    <h3 style={{ marginBottom: '1.5rem' }}>Basic Information</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
                        <div>
                            <label style={labelStyle}>Customer Name <span style={{ color: 'var(--color-error)' }}>*</span></label>
                            <input type="text" className="input" value={formData.name}
                                onChange={e => setFormData({ ...formData, name: e.target.value })} required />
                        </div>
                        <div>
                            <label style={labelStyle}>Customer Code <span style={{ color: 'var(--color-error)' }}>*</span></label>
                            <input type="text" className="input" value={formData.customer_code}
                                onChange={e => setFormData({ ...formData, customer_code: e.target.value })}
                                placeholder="CUST-001" required />
                        </div>
                        <div>
                            <label style={labelStyle}>Contact Person</label>
                            <input type="text" className="input" value={formData.contact_person}
                                onChange={e => setFormData({ ...formData, contact_person: e.target.value })} />
                        </div>
                        <div>
                            <label style={labelStyle}>Contact Email</label>
                            <input type="email" className="input" value={formData.contact_email}
                                onChange={e => setFormData({ ...formData, contact_email: e.target.value })} />
                        </div>
                        <div>
                            <label style={labelStyle}>Contact Phone</label>
                            <input type="text" className="input" value={formData.contact_phone}
                                onChange={e => setFormData({ ...formData, contact_phone: e.target.value })} />
                        </div>
                        <div>
                            <label style={labelStyle}>VAT Number</label>
                            <input type="text" className="input" value={formData.vat_number}
                                onChange={e => setFormData({ ...formData, vat_number: e.target.value })} />
                        </div>
                        <div>
                            <label style={labelStyle}>Industry</label>
                            <input type="text" className="input" value={formData.industry}
                                onChange={e => setFormData({ ...formData, industry: e.target.value })} />
                        </div>
                        <div>
                            <label style={labelStyle}>Website</label>
                            <input type="url" className="input" value={formData.website}
                                onChange={e => setFormData({ ...formData, website: e.target.value })} />
                        </div>
                    </div>
                    <div style={{ marginTop: '1rem' }}>
                        <label style={labelStyle}>Address</label>
                        <textarea className="input" rows={3} value={formData.address}
                            onChange={e => setFormData({ ...formData, address: e.target.value })} />
                    </div>
                </div>

                {/* ── Financial Settings */}
                <div className="card" style={{ marginBottom: '1.5rem' }}>
                    <h3 style={{ marginBottom: '1.5rem' }}>Financial Settings</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1.25rem' }}>
                        <div>
                            <label style={labelStyle}>Credit Limit</label>
                            <input type="number" className="input" value={formData.credit_limit}
                                onChange={e => setFormData({ ...formData, credit_limit: e.target.value })} />
                        </div>
                        <div>
                            <label style={labelStyle}>Payment Terms <span style={{ color: 'var(--color-error)' }}>*</span></label>
                            <select className="input" value={formData.payment_terms}
                                onChange={e => setFormData({ ...formData, payment_terms: e.target.value })} required>
                                {PAYMENT_TERMS.map(pt => (
                                    <option key={pt.value} value={pt.value}>{pt.label}</option>
                                ))}
                            </select>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', marginTop: '1.5rem' }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                                <input type="checkbox" checked={formData.is_active}
                                    onChange={e => setFormData({ ...formData, is_active: e.target.checked })} />
                                <span>Active Customer</span>
                            </label>
                        </div>
                    </div>

                    {/* Withholding Tax */}
                    <div style={{ background: 'rgba(79,70,229,0.04)', border: '1px solid rgba(79,70,229,0.15)', borderRadius: '8px', padding: '1rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                            <ShieldCheck size={15} style={{ color: '#4f46e5' }} />
                            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#4f46e5' }}>Withholding Tax</span>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '1rem', alignItems: 'end' }}>
                            <div>
                                <label style={labelStyle}>Default WHT Code</label>
                                <select className="input" value={String(formData.withholding_tax_code)}
                                    onChange={e => setFormData({ ...formData, withholding_tax_code: e.target.value })}>
                                    <option value="">— No withholding tax —</option>
                                    {(Array.isArray(whtList) ? whtList : []).map((w: any) => (
                                        <option key={w.id} value={w.id}>{w.code} — {w.name} ({w.rate}%)</option>
                                    ))}
                                </select>
                            </div>
                            <div style={{ paddingBottom: '2px' }}>
                                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                                    <input type="checkbox" checked={formData.wht_exempt}
                                        onChange={e => setFormData({ ...formData, wht_exempt: e.target.checked })} />
                                    <span style={{ fontSize: 'var(--text-sm)' }}>WHT Exempt</span>
                                </label>
                                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                                    All transactions will skip WHT
                                </p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* ── Actions */}
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <div>
                        {isEdit && (
                            <button type="button" className="btn btn-outline" onClick={handleDelete}
                                style={{ color: 'var(--color-error)' }}>
                                <Trash2 size={16} /> Delete Customer
                            </button>
                        )}
                    </div>
                    <div style={{ display: 'flex', gap: '1rem' }}>
                        <button type="button" className="btn btn-outline" onClick={() => navigate('/sales/customers')}>
                            <X size={16} /> Cancel
                        </button>
                        <button type="submit" className="btn btn-primary"
                            disabled={createCustomer.isPending || updateCustomer.isPending}>
                            <Save size={16} /> {isEdit ? 'Update' : 'Create'} Customer
                        </button>
                    </div>
                </div>
            </form>
        </SalesLayout>
    );
};

export default CustomerForm;
