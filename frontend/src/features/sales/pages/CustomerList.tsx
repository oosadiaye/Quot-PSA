import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCustomers, useCustomerCategories } from '../hooks/useSales';
import SalesLayout from '../layout/SalesLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import { Plus, Search, Users, BookOpen } from 'lucide-react';

const getCreditStatusColor = (status: string) => {
    const colors: Record<string, string> = {
        Good: 'var(--color-success)',
        Warning: '#f59e0b',
        Exceeded: 'var(--color-error)',
        Blocked: 'var(--color-error)',
    };
    return colors[status] || 'var(--color-text-muted)';
};

const CustomerList = () => {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const [search, setSearch] = useState('');
    const [categoryFilter, setCategoryFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState('');

    const { data: customersData, isLoading } = useCustomers();
    const { data: categoriesData } = useCustomerCategories();

    const allCustomers: any[] = useMemo(() =>
        Array.isArray(customersData) ? customersData : (customersData?.results ?? []),
        [customersData]
    );
    const categories: any[] = useMemo(() => categoriesData ?? [], [categoriesData]);

    const list = useMemo(() => allCustomers.filter((c: any) => {
        const q = search.toLowerCase();
        const matchesSearch = !search ||
            c.name?.toLowerCase().includes(q) ||
            c.customer_code?.toLowerCase().includes(q) ||
            c.contact_email?.toLowerCase().includes(q) ||
            c.contact_person?.toLowerCase().includes(q);
        const matchesCategory = !categoryFilter || String(c.category) === categoryFilter;
        const matchesStatus = !statusFilter ||
            (statusFilter === 'active' && c.is_active) ||
            (statusFilter === 'inactive' && !c.is_active);
        return matchesSearch && matchesCategory && matchesStatus;
    }), [allCustomers, search, categoryFilter, statusFilter]);

    if (isLoading) return <LoadingScreen message="Loading customers..." />;

    return (
        <SalesLayout title="Customers" description="Manage customer accounts and credit information">
            {/* ── Toolbar */}
            <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem', alignItems: 'center' }}>
                <div style={{ position: 'relative', flex: '1 1 0', minWidth: 0 }}>
                    <Search size={15} style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                    <input
                        type="text"
                        placeholder="Search by name, code, email..."
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        style={{
                            width: '100%', padding: '0.625rem 0.75rem 0.625rem 2.25rem',
                            borderRadius: '8px', border: '1px solid var(--color-border)',
                            background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)',
                        }}
                    />
                </div>
                <select value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)}
                    style={{ flex: '0 0 160px', padding: '0.625rem 0.75rem', borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                    <option value="">All Categories</option>
                    {categories.map((cat: any) => (
                        <option key={cat.id} value={cat.id}>{cat.name}</option>
                    ))}
                </select>
                <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
                    style={{ flex: '0 0 140px', padding: '0.625rem 0.75rem', borderRadius: '8px', border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                    <option value="">All Status</option>
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                </select>
                <button className="btn btn-primary" onClick={() => navigate('/sales/customer/new')} style={{ flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Plus size={15} /> Add Customer
                </button>
            </div>

            {/* ── Table */}
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                {['Code', 'Name', 'Category', 'AR Account', 'Contact', 'Phone', 'Credit Limit', 'Balance', 'Credit Status', 'Status', 'Actions'].map(h => (
                                    <th key={h} style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--color-text-muted)', borderBottom: '2px solid var(--color-border)', whiteSpace: 'nowrap' }}>
                                        {h}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {list.length === 0 ? (
                                <tr>
                                    <td colSpan={11} style={{ padding: '4rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <Users size={48} style={{ margin: '0 auto 1rem', opacity: 0.2, display: 'block' }} />
                                        <p style={{ margin: 0, fontWeight: 500 }}>
                                            {search || categoryFilter || statusFilter ? 'No customers match the current filters.' : 'No customers yet. Add one to get started.'}
                                        </p>
                                    </td>
                                </tr>
                            ) : (
                                list.map((c: any) => (
                                    <tr key={c.id} onClick={() => navigate(`/sales/customer/${c.id}`)}
                                        style={{ borderBottom: '1px solid var(--color-border)', cursor: 'pointer', transition: 'background 0.12s' }}
                                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-surface)')}
                                        onMouseLeave={e => (e.currentTarget.style.background = '')}>

                                        <td style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-primary)', whiteSpace: 'nowrap' }}>
                                            {c.customer_code}
                                        </td>
                                        <td style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                                            {c.name}
                                        </td>
                                        <td style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-sm)' }}>
                                            {c.category_name
                                                ? <span style={{ display: 'inline-block', padding: '0.2rem 0.6rem', borderRadius: '20px', fontSize: 'var(--text-xs)', fontWeight: 600, background: 'rgba(59,130,246,0.1)', color: '#3b82f6' }}>
                                                    {c.category_name}
                                                  </span>
                                                : <span style={{ color: 'var(--color-text-muted)' }}>—</span>
                                            }
                                        </td>
                                        <td style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                            {c.category_ar_account_code
                                                ? <span style={{ fontFamily: 'monospace', fontWeight: 600, color: 'var(--color-text)' }}>{c.category_ar_account_code}</span>
                                                : '—'
                                            }
                                        </td>
                                        <td style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-sm)', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {c.contact_person || c.contact_email || '—'}
                                        </td>
                                        <td style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-sm)', whiteSpace: 'nowrap' }}>
                                            {c.contact_phone || '—'}
                                        </td>
                                        <td style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-sm)', fontWeight: 600, whiteSpace: 'nowrap' }}>
                                            {formatCurrency(parseFloat(c.credit_limit || 0))}
                                        </td>
                                        <td style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-sm)', fontWeight: 600, whiteSpace: 'nowrap' }}>
                                            {formatCurrency(parseFloat(c.balance || 0))}
                                        </td>
                                        <td style={{ padding: '0.875rem 1rem' }}>
                                            <span style={{ padding: '0.2rem 0.6rem', borderRadius: '20px', fontSize: 'var(--text-xs)', fontWeight: 700, background: `${getCreditStatusColor(c.credit_status)}22`, color: getCreditStatusColor(c.credit_status), whiteSpace: 'nowrap' }}>
                                                {c.credit_status || '—'}
                                            </span>
                                        </td>
                                        <td style={{ padding: '0.875rem 1rem' }}>
                                            <span style={{ padding: '0.2rem 0.6rem', borderRadius: '20px', fontSize: 'var(--text-xs)', fontWeight: 700, background: c.is_active ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.1)', color: c.is_active ? '#10b981' : 'var(--color-error)', whiteSpace: 'nowrap' }}>
                                                {c.is_active ? 'Active' : 'Inactive'}
                                            </span>
                                        </td>
                                        <td style={{ padding: '0.875rem 1rem', whiteSpace: 'nowrap' }}>
                                            <button
                                                onClick={(e) => { e.stopPropagation(); navigate(`/sales/customer/${c.id}/ledger`); }}
                                                style={{
                                                    padding: '0.375rem 0.75rem', borderRadius: '6px', border: 'none',
                                                    background: 'rgba(36, 113, 163, 0.1)', color: '#2471a3',
                                                    cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600,
                                                    display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                                }}
                                                title="View Ledger"
                                            >
                                                <BookOpen size={14} />
                                                Ledger
                                            </button>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </SalesLayout>
    );
};

export default CustomerList;
