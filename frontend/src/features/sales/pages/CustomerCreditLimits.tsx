import { useState } from 'react';
import { useCustomers, useUpdateCustomerCreditLimit } from '../hooks/useSales';
import { useDialog } from '../../../hooks/useDialog';
import SalesLayout from '../layout/SalesLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { AlertTriangle, CheckCircle, XCircle, Edit2 } from 'lucide-react';
import { useCurrency } from '../../../context/CurrencyContext';

const CustomerCreditLimits = () => {
    const { showAlert } = useDialog();
    const [editingId, setEditingId] = useState<number | null>(null);
    const [creditLimit, setCreditLimit] = useState('');
    const { formatCurrency } = useCurrency();

    const { data: customersData, isLoading } = useCustomers();
    const updateCreditLimit = useUpdateCustomerCreditLimit();

    const customers = customersData?.results || customersData || [];

    if (isLoading) {
        return <LoadingScreen message="Loading credit limits..." />;
    }


    const handleEdit = (id: number, currentLimit: number) => {
        setEditingId(id);
        setCreditLimit(currentLimit.toString());
    };

    const handleSave = async (id: number) => {
        try {
            await updateCreditLimit.mutateAsync({ id, credit_limit: parseFloat(creditLimit) });
            setEditingId(null);
        } catch (err: any) {
            showAlert(err.response?.data?.detail || 'Error updating credit limit');
        }
    };

    const getCreditStatus = (customer: any) => {
        const limit = parseFloat(customer.credit_limit || 0);
        const balance = parseFloat(customer.balance || 0);

        if (limit === 0) return { status: 'No Limit', color: 'var(--color-text-muted)', icon: null };
        const utilization = (balance / limit) * 100;

        if (utilization >= 100) return { status: 'Credit Exceeded', color: 'var(--color-error)', icon: <XCircle size={14} /> };
        if (utilization >= 80) return { status: 'Credit Warning', color: '#f59e0b', icon: <AlertTriangle size={14} /> };
        return { status: 'Credit OK', color: 'var(--color-success)', icon: <CheckCircle size={14} /> };
    };

    return (
        <SalesLayout title="Customer Credit Limits" description="Manage customer credit limits and monitor usage">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.5rem', marginBottom: '2.5rem' }}>
                <div className="card">
                    <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>TOTAL CUSTOMERS</div>
                    <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>{customers?.length || 0}</div>
                </div>
                <div className="card">
                    <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>WITH CREDIT LIMIT</div>
                    <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-primary)' }}>
                        {customers?.filter((c: any) => parseFloat(c.credit_limit || 0) > 0).length || 0}
                    </div>
                </div>
                <div className="card">
                    <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>AT RISK</div>
                    <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: '#f59e0b' }}>
                        {customers?.filter((c: any) => {
                            const limit = parseFloat(c.credit_limit || 0);
                            const balance = parseFloat(c.balance || 0);
                            return limit > 0 && (balance / limit) >= 0.8;
                        }).length || 0}
                    </div>
                </div>
                <div className="card">
                    <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>EXCEEDED</div>
                    <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-error)' }}>
                        {customers?.filter((c: any) => {
                            const limit = parseFloat(c.credit_limit || 0);
                            const balance = parseFloat(c.balance || 0);
                            return limit > 0 && balance > limit;
                        }).length || 0}
                    </div>
                </div>
            </div>

            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                            <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Customer Code</th>
                            <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Customer Name</th>
                            <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Credit Limit</th>
                            <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Current Balance</th>
                            <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Available</th>
                            <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                            <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {customers?.length === 0 ? (
                            <tr><td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No customers found</td></tr>
                        ) : (
                            customers?.map((customer: any) => {
                                const creditStatus = getCreditStatus(customer);
                                const limit = parseFloat(customer.credit_limit || 0);
                                const balance = parseFloat(customer.balance || 0);
                                const available = limit - balance;
                                const utilization = limit > 0 ? (balance / limit) * 100 : 0;

                                return (
                                    <tr key={customer.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '1rem', fontWeight: 600 }}>{customer.customer_code}</td>
                                        <td style={{ padding: '1rem' }}>{customer.name}</td>
                                        <td style={{ padding: '1rem' }}>
                                            {editingId === customer.id ? (
                                                <input
                                                    type="number"
                                                    value={creditLimit}
                                                    onChange={e => setCreditLimit(e.target.value)}
                                                    style={{
                                                        padding: '0.5rem', borderRadius: '4px', border: '1px solid var(--color-border)',
                                                        background: 'var(--color-surface)', color: 'var(--color-text)', width: '120px'
                                                    }}
                                                />
                                            ) : (
                                                <span style={{ fontWeight: 600 }}>{formatCurrency(limit)}</span>
                                            )}
                                        </td>
                                        <td style={{ padding: '1rem', fontWeight: 600, color: utilization >= 100 ? 'var(--color-error)' : 'var(--color-text)' }}>
                                            {formatCurrency(balance)}
                                        </td>
                                        <td style={{ padding: '1rem', fontWeight: 600, color: available < 0 ? 'var(--color-error)' : 'var(--color-success)' }}>
                                            {formatCurrency(Math.max(available, 0))}
                                        </td>
                                        <td style={{ padding: '1rem' }}>
                                            <span style={{
                                                padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 700,
                                                background: `${creditStatus.color}20`, color: creditStatus.color,
                                                display: 'inline-flex', alignItems: 'center', gap: '0.25rem'
                                            }}>
                                                {creditStatus.icon} {creditStatus.status}
                                            </span>
                                        </td>
                                        <td style={{ padding: '1rem' }}>
                                            {editingId === customer.id ? (
                                                <div style={{ display: 'flex', gap: '0.5rem' }}>
                                                    <button
                                                        className="btn btn-primary"
                                                        style={{ padding: '0.4rem 0.8rem', fontSize: 'var(--text-xs)' }}
                                                        onClick={() => handleSave(customer.id)}
                                                    >
                                                        Save
                                                    </button>
                                                    <button
                                                        className="btn btn-outline"
                                                        style={{ padding: '0.4rem 0.8rem', fontSize: 'var(--text-xs)' }}
                                                        onClick={() => setEditingId(null)}
                                                    >
                                                        Cancel
                                                    </button>
                                                </div>
                                            ) : (
                                                <button
                                                    className="btn btn-outline"
                                                    style={{ padding: '0.4rem 0.8rem', fontSize: 'var(--text-xs)' }}
                                                    onClick={() => handleEdit(customer.id, limit)}
                                                >
                                                    <Edit2 size={14} />
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                );
                            })
                        )}
                    </tbody>
                </table>
            </div>
        </SalesLayout>
    );
};

export default CustomerCreditLimits;
