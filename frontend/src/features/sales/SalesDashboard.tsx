import { useSalesOrders, usePostSalesOrder, useCustomers } from './hooks/useSales';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import { TrendingUp, Users, FileCheck, Package } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useCurrency } from '../../context/CurrencyContext';

import LoadingScreen from '../../components/common/LoadingScreen';

const SalesDashboard = () => {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const { data: ordersData, isLoading: isOrdersLoading } = useSalesOrders();
    const { data: customersData, isLoading: isCustomersLoading } = useCustomers();
    const postOrder = usePostSalesOrder();

    const orders = ordersData?.results || ordersData || [];
    const customers = customersData?.results || customersData || [];

    if (isOrdersLoading || isCustomersLoading) {
        return <LoadingScreen message="Loading sales dashboard..." />;
    }


    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Sales & Revenue"
                    subtitle="Manage customers and track order-to-invoice lifecycles."
                    icon={<TrendingUp size={22} color="white" />}
                />

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1.5rem', marginBottom: '2.5rem' }}>
                    <div className="card">
                        <Users size={24} style={{ color: 'var(--color-primary)', marginBottom: '1rem' }} />
                        <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)' }}>TOTAL CUSTOMERS</div>
                        <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>{customers.length || 0}</div>
                    </div>
                    <div className="card">
                        <TrendingUp size={24} style={{ color: 'var(--color-success)', marginBottom: '1rem' }} />
                        <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)' }}>REVENUE (POSTED)</div>
                        <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>
                            {formatCurrency(orders.filter((o: any) => o.status === 'Posted').reduce((sum: number, o: any) => sum + parseFloat(o.total_order || '0'), 0))}
                        </div>
                    </div>
                </div>

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Order #</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Customer</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Amount</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Status</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Accounting</th>
                            </tr>
                        </thead>
                        <tbody>
                            {orders.map((order: any) => (
                                <tr key={order.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                    <td style={{ padding: '1rem', fontWeight: 600, color: 'var(--color-text)' }}>{order.order_number}</td>
                                    <td style={{ padding: '1rem' }}>{order.customer_name}</td>
                                    <td style={{ padding: '1rem', fontWeight: 600, color: 'var(--color-primary)' }}>{formatCurrency(parseFloat(order.total_order || '0'))}</td>
                                    <td style={{ padding: '1rem' }}>
                                        <span style={{
                                            padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 700,
                                            background: order.status === 'Posted' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(36, 113, 163, 0.15)',
                                            color: order.status === 'Posted' ? 'var(--color-success)' : 'var(--color-primary)'
                                        }}>
                                            {order.status}
                                        </span>
                                    </td>
                                    <td style={{ padding: '1rem' }}>
                                        {order.status !== 'Posted' ? (
                                            <button
                                                className="btn btn-primary"
                                                style={{ padding: '0.4rem 0.8rem', fontSize: 'var(--text-xs)' }}
                                                onClick={() => postOrder.mutate(order.id)}
                                            >
                                                Send to Invoice
                                            </button>
                                        ) : (
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: 'var(--color-success)', fontSize: 'var(--text-xs)' }}>
                                                <FileCheck size={14} /> Invoiced
                                            </div>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                <div style={{ marginTop: '3rem' }}>
                    <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, marginBottom: '1.25rem', color: 'var(--color-text)' }}>
                        Quick Links
                    </h2>
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                        gap: '1.5rem'
                    }}>
                        {[
                            { name: 'CRM & Leads', path: '/sales/crm', icon: Users, desc: 'Manage prospects and customers' },
                            { name: 'Quotations', path: '/sales/quotations', icon: FileCheck, desc: 'Generate and track sales quotes' },
                            { name: 'Sales Orders', path: '/sales/orders', icon: TrendingUp, desc: 'Process customer orders' },
                            { name: 'Invoice Automation', path: '/sales/invoicing', icon: FileCheck, desc: 'Convert orders to invoices' },
                        ].map((link) => (
                            <div
                                key={link.name}
                                className="card glass animate-fade"
                                style={{
                                    cursor: 'pointer',
                                    padding: '1.25rem',
                                    transition: 'var(--transition)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '1rem'
                                }}
                                onClick={() => navigate(link.path)}
                                onMouseOver={(e) => {
                                    e.currentTarget.style.transform = 'translateY(-4px)';
                                    e.currentTarget.style.borderColor = '#f59e0b';
                                }}
                                onMouseOut={(e) => {
                                    e.currentTarget.style.transform = 'translateY(0)';
                                    e.currentTarget.style.borderColor = 'var(--color-border)';
                                }}
                            >
                                <div style={{
                                    width: '36px',
                                    height: '36px',
                                    borderRadius: '8px',
                                    background: 'rgba(245, 158, 11, 0.1)',
                                    color: '#f59e0b',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    flexShrink: 0
                                }}>
                                    <link.icon size={18} />
                                </div>
                                <div>
                                    <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>{link.name}</div>
                                    <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: 0 }}>{link.desc}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </main>
        </div>
    );
};

export default SalesDashboard;
