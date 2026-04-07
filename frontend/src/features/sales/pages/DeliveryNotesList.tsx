import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDeliveryNotes, useCustomers, useSalesOrders, usePostDeliveryNote } from '../hooks/useSales';
import { useDialog } from '../../../hooks/useDialog';
import AccountingLayout from '../../accounting/AccountingLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import PageHeader from '../../../components/PageHeader';
import { Plus, Search, Truck, Send, Package } from 'lucide-react';
import '../../accounting/styles/glassmorphism.css';

const DeliveryNotesList = () => {
    const navigate = useNavigate();
    const { showAlert, showConfirm } = useDialog();
    const { data: deliveryNotes, isLoading } = useDeliveryNotes();
    const { data: customers } = useCustomers();
    const { data: salesOrders } = useSalesOrders({ status: 'Posted' });
    const postDN = usePostDeliveryNote();

    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('');

    const notesList = deliveryNotes?.results || deliveryNotes || [];
    const customersList = customers?.results || customers || [];
    const ordersList = salesOrders?.results || salesOrders || [];

    const getCustomerName = (id: number) => customersList.find((c: any) => c.id === id)?.name || '-';
    const getOrderNumber = (id: number) => ordersList.find((o: any) => o.id === id)?.order_number || '-';

    const filteredNotes = Array.isArray(notesList) ? notesList.filter((dn: any) => {
        const matchesSearch = !searchTerm ||
            dn.delivery_number?.toLowerCase().includes(searchTerm.toLowerCase()) ||
            dn.recipient_name?.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesStatus = !statusFilter || dn.status === statusFilter;
        return matchesSearch && matchesStatus;
    }) : [];

    const handlePost = async (id: number) => {
        if (await showConfirm('Post this delivery note? This will update inventory.')) {
            postDN.mutate({ id, warehouse_id: 0 }, {
                onError: (err: any) => showAlert(err.response?.data?.error || err.response?.data?.detail || 'Error posting delivery note'),
            });
        }
    };

    const getStatusBadge = (status: string) => {
        const colors: Record<string, string> = {
            'Draft': 'rgba(156, 163, 175, 0.1)',
            'Issued': 'rgba(36, 113, 163, 0.1)',
            'Delivered': 'rgba(16, 185, 129, 0.1)',
            'Posted': 'rgba(34, 197, 94, 0.1)',
            'Received': 'rgba(34, 197, 94, 0.1)',
            'Returned': 'rgba(245, 158, 11, 0.1)',
            'Cancelled': 'rgba(239, 68, 68, 0.1)',
        };
        const textColors: Record<string, string> = {
            'Draft': '#9ca3af',
            'Issued': '#2471a3',
            'Delivered': '#10b981',
            'Posted': '#22c55e',
            'Received': '#22c55e',
            'Returned': '#f59e0b',
            'Cancelled': '#ef4444',
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
                <LoadingScreen message="Loading delivery notes..." />
            </AccountingLayout>
        );
    }

    return (
        <AccountingLayout>
            <PageHeader
                title="Delivery Notes"
                subtitle="Track goods delivery to customers"
                icon={<Truck size={22} color="white" />}
                actions={
                    <button
                        onClick={() => navigate('/sales/delivery-notes/new')}
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
                        New Delivery Note
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
                            placeholder="Search by delivery number or recipient..."
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
                        <option value="Delivered">Delivered</option>
                        <option value="Posted">Posted</option>
                        <option value="Cancelled">Cancelled</option>
                    </select>
                </div>
            </div>

            {/* Table */}
            <div className="glass-card" style={{ overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Delivery #</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Sales Order</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Customer</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Date</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'center', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Status</th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredNotes.length > 0 ? (
                                filteredNotes.map((dn: any, index: number) => (
                                    <tr
                                        key={dn.id}
                                        style={{
                                            borderBottom: '1px solid var(--color-border)',
                                            animation: `fadeInUp 0.3s ease-out ${index * 0.05}s both`,
                                        }}
                                    >
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)', fontWeight: 500 }}>
                                            {dn.delivery_number}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)' }}>
                                            {dn.so_number || getOrderNumber(dn.sales_order)}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)' }}>
                                            {dn.customer_name || getCustomerName(dn.customer)}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                            {dn.delivery_date ? new Date(dn.delivery_date).toLocaleDateString() : '—'}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', textAlign: 'center' }}>
                                            {getStatusBadge(dn.status)}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem' }}>
                                            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                                {dn.status === 'Draft' && (
                                                    <button
                                                        onClick={() => handlePost(dn.id)}
                                                        style={{
                                                            padding: '0.375rem 0.75rem',
                                                            borderRadius: '6px',
                                                            border: 'none',
                                                            background: 'rgba(36, 113, 163, 0.1)',
                                                            color: '#2471a3',
                                                            cursor: 'pointer',
                                                            fontSize: 'var(--text-xs)',
                                                            fontWeight: 600,
                                                            display: 'inline-flex',
                                                            alignItems: 'center',
                                                            gap: '0.25rem',
                                                        }}
                                                        title="Post Delivery"
                                                    >
                                                        <Send size={14} />
                                                        Post
                                                    </button>
                                                )}
                                                {(dn.status === 'Delivered' || dn.status === 'Posted') && (
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: '#22c55e', fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                                                        <Truck size={14} /> {dn.status}
                                                    </div>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td colSpan={6} style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <Package size={48} style={{ margin: '0 auto 1rem', opacity: 0.5, display: 'block' }} />
                                        <p>No delivery notes found</p>
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

export default DeliveryNotesList;
