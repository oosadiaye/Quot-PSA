import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSalesOrders, useApproveSalesOrder, useRejectSalesOrder, usePostSalesOrder } from '../hooks/useSales';
import { useCurrency } from '../../../context/CurrencyContext';
import { useDialog } from '../../../hooks/useDialog';
import AccountingLayout from '../../accounting/AccountingLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import PageHeader from '../../../components/PageHeader';
import { Plus, Search, CheckCircle, XCircle, Send, ShoppingCart, FileCheck, Truck } from 'lucide-react';
import '../../accounting/styles/glassmorphism.css';

const SalesOrders = () => {
    const navigate = useNavigate();
    const { showAlert, showConfirm, showPrompt } = useDialog();
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('');

    const { data: ordersData, isLoading } = useSalesOrders({ status: statusFilter });
    const { formatCurrency } = useCurrency();
    const approveOrder = useApproveSalesOrder();
    const rejectOrder = useRejectSalesOrder();
    const postOrder = usePostSalesOrder();

    const orders = ordersData?.results || ordersData || [];

    const filteredOrders = Array.isArray(orders) ? orders.filter((o: any) =>
        o.order_number?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        o.customer_name?.toLowerCase().includes(searchTerm.toLowerCase())
    ) : [];

    const handleApprove = async (id: number) => {
        if (await showConfirm('Approve this Sales Order?')) {
            approveOrder.mutate(id);
        }
    };

    const handleReject = async (id: number) => {
        const reason = await showPrompt('Reason for rejection:');
        if (reason) {
            rejectOrder.mutate({ id, reason });
        }
    };

    const handlePost = async (id: number) => {
        if (await showConfirm('Post this Sales Order? This will create journal entries.')) {
            postOrder.mutate(id, {
                onError: (err: any) => showAlert(err.response?.data?.error || err.response?.data?.detail || 'Error posting order'),
            });
        }
    };

    const getStatusBadge = (status: string) => {
        const colors: Record<string, string> = {
            'Draft': 'rgba(156, 163, 175, 0.1)',
            'Pending': 'rgba(251, 191, 36, 0.1)',
            'Approved': 'rgba(36, 113, 163, 0.1)',
            'Posted': 'rgba(34, 197, 94, 0.1)',
            'Rejected': 'rgba(239, 68, 68, 0.1)',
        };
        const textColors: Record<string, string> = {
            'Draft': '#9ca3af',
            'Pending': '#fbbf24',
            'Approved': '#2471a3',
            'Posted': '#22c55e',
            'Rejected': '#ef4444',
        };
        return (
            <span style={{
                display: 'inline-block',
                padding: '0.25rem 0.75rem',
                borderRadius: '9999px',
                fontSize: 'var(--text-xs)',
                fontWeight: 500,
                background: colors[status] || colors['Draft'],
                color: textColors[status] || textColors['Draft'],
            }}>
                {status}
            </span>
        );
    };

    if (isLoading) {
        return (
            <AccountingLayout>
                <LoadingScreen message="Loading sales orders..." />
            </AccountingLayout>
        );
    }

    return (
        <AccountingLayout>
            <PageHeader
                title="Sales Orders"
                subtitle="Manage customer sales orders"
                icon={<ShoppingCart size={22} color="white" />}
                actions={
                    <button
                        onClick={() => navigate('/sales/orders/new')}
                        className="glass-button"
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.5rem',
                            padding: '0.75rem 1.5rem',
                            background: 'rgba(255,255,255,0.2)',
                            color: 'white',
                            border: '1px solid rgba(255,255,255,0.3)',
                            borderRadius: '8px',
                            cursor: 'pointer',
                            fontWeight: 500,
                        }}
                    >
                        <Plus size={20} />
                        New Sales Order
                    </button>
                }
            />

            {/* Search & Filter */}
            <div className="glass-card" style={{ marginBottom: '1.5rem', padding: '1rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '1rem' }}>
                    <div style={{ position: 'relative' }}>
                        <Search style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} size={20} />
                        <input
                            type="text"
                            placeholder="Search by order number or customer..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            style={{
                                width: '100%',
                                paddingLeft: '2.75rem',
                                paddingRight: '1rem',
                                paddingTop: '0.75rem',
                                paddingBottom: '0.75rem',
                                borderRadius: '8px',
                                border: '1px solid var(--color-border)',
                                background: 'var(--color-surface)',
                                color: 'var(--color-text)',
                                fontSize: 'var(--text-sm)',
                            }}
                        />
                    </div>
                    <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        style={{
                            padding: '0.75rem 1rem',
                            borderRadius: '8px',
                            border: '1px solid var(--color-border)',
                            background: 'var(--color-surface)',
                            color: 'var(--color-text)',
                            fontSize: 'var(--text-sm)',
                        }}
                    >
                        <option value="">All Status</option>
                        <option value="Draft">Draft</option>
                        <option value="Pending">Pending</option>
                        <option value="Approved">Approved</option>
                        <option value="Posted">Posted</option>
                        <option value="Rejected">Rejected</option>
                    </select>
                </div>
            </div>

            {/* Table */}
            <div className="glass-card" style={{ overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Order #</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Customer</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Date</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Amount</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'center', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Status</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredOrders.length > 0 ? (
                                filteredOrders.map((order: any, index: number) => (
                                    <tr
                                        key={order.id}
                                        style={{
                                            borderBottom: '1px solid var(--color-border)',
                                            animation: `fadeInUp 0.3s ease-out ${index * 0.05}s both`,
                                        }}
                                    >
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)', fontWeight: 500 }}>
                                            {order.order_number}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)' }}>
                                            {order.customer_name}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                            {order.order_date ? new Date(order.order_date).toLocaleDateString() : '—'}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', textAlign: 'right', fontWeight: 500, color: 'var(--color-text)' }}>
                                            {formatCurrency(Number(order.total_amount || 0))}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', textAlign: 'center' }}>
                                            {getStatusBadge(order.status)}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem' }}>
                                            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                                {order.status === 'Pending' && (
                                                    <>
                                                        <button
                                                            onClick={() => handleApprove(order.id)}
                                                            style={{
                                                                padding: '0.5rem',
                                                                borderRadius: '8px',
                                                                border: 'none',
                                                                background: 'rgba(34, 197, 94, 0.1)',
                                                                color: '#22c55e',
                                                                cursor: 'pointer',
                                                            }}
                                                            title="Approve"
                                                        >
                                                            <CheckCircle size={16} />
                                                        </button>
                                                        <button
                                                            onClick={() => handleReject(order.id)}
                                                            style={{
                                                                padding: '0.5rem',
                                                                borderRadius: '8px',
                                                                border: 'none',
                                                                background: 'rgba(239, 68, 68, 0.1)',
                                                                color: '#ef4444',
                                                                cursor: 'pointer',
                                                            }}
                                                            title="Reject"
                                                        >
                                                            <XCircle size={16} />
                                                        </button>
                                                    </>
                                                )}
                                                {order.status === 'Approved' && (
                                                    <button
                                                        onClick={() => handlePost(order.id)}
                                                        style={{
                                                            padding: '0.375rem 0.75rem',
                                                            borderRadius: '6px',
                                                            border: 'none',
                                                            background: 'rgba(34, 197, 94, 0.1)',
                                                            color: '#22c55e',
                                                            cursor: 'pointer',
                                                            fontSize: 'var(--text-xs)',
                                                            fontWeight: 600,
                                                            display: 'inline-flex',
                                                            alignItems: 'center',
                                                            gap: '0.25rem',
                                                        }}
                                                        title="Post Order"
                                                    >
                                                        <Send size={14} />
                                                        Post
                                                    </button>
                                                )}
                                                {order.status === 'Posted' && (
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: '#22c55e', fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                                                            <FileCheck size={14} /> Posted
                                                        </div>
                                                        <button
                                                            onClick={() => navigate(`/sales/delivery-notes/new?so=${order.id}`)}
                                                            style={{
                                                                padding: '0.375rem 0.625rem',
                                                                borderRadius: '6px',
                                                                border: 'none',
                                                                background: 'rgba(59,130,246,0.1)',
                                                                color: '#3b82f6',
                                                                cursor: 'pointer',
                                                                fontSize: 'var(--text-xs)',
                                                                fontWeight: 600,
                                                                display: 'inline-flex',
                                                                alignItems: 'center',
                                                                gap: '0.25rem',
                                                            }}
                                                            title="Create Delivery Note"
                                                        >
                                                            <Truck size={13} /> Deliver
                                                        </button>
                                                    </div>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td colSpan={6} style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <ShoppingCart size={48} style={{ margin: '0 auto 1rem', opacity: 0.5, display: 'block' }} />
                                        <p>No sales orders found</p>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </AccountingLayout>
    );
};

export default SalesOrders;
