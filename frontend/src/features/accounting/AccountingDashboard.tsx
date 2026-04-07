import React from 'react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import {
    List,
    FileText,
    BarChart3,
    Receipt,
    DollarSign,
    Building,
    Coins,
    Wallet,
    ArrowRight,
    TrendingUp,
    TrendingDown,
    CreditCard
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useVendorInvoices, useCustomerInvoices, usePayments, useReceipts } from './hooks/useAccountingEnhancements';
import LoadingScreen from '../../components/common/LoadingScreen';
import { useCurrency } from '../../context/CurrencyContext';
import { safeSum } from './utils/currency';

const AccountingDashboard = () => {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();

    const { data: vendorInvoices, isLoading: loadingAP } = useVendorInvoices();
    const { data: customerInvoices, isLoading: loadingAR } = useCustomerInvoices();
    const { data: payments, isLoading: loadingPayments } = usePayments();
    const { data: receipts, isLoading: loadingReceipts } = useReceipts();

    if (loadingAP || loadingAR || loadingPayments || loadingReceipts) {
        return <LoadingScreen message="Loading financial metrics..." />;
    }

    const totalPayable = vendorInvoices ? safeSum(vendorInvoices, 'balance_due') : 0;
    const totalReceivable = customerInvoices ? safeSum(customerInvoices, 'balance_due') : 0;
    const totalPaymentsReceived = receipts ? safeSum(receipts, 'total_amount') : 0;
    const totalPaymentsMade = payments ? safeSum(payments, 'total_amount') : 0;

    const summaryCards = [
        { name: 'Total Payable', value: totalPayable, icon: TrendingUp, color: 'var(--color-error)', desc: 'Unpaid vendor invoices' },
        { name: 'Total Receivable', value: totalReceivable, icon: TrendingDown, color: 'var(--color-success)', desc: 'Outstanding customer invoices' },
        { name: 'Payments Received', value: totalPaymentsReceived, icon: CreditCard, color: 'var(--color-primary)', desc: 'Total inflows recorded' },
        { name: 'Payments Made', value: totalPaymentsMade, icon: DollarSign, color: 'var(--color-cta)', desc: 'Total outflows recorded' },
    ];

    const sections = [
        {
            title: 'Core Accounting',
            links: [
                { name: 'Chart of Accounts', path: '/accounting/coa', icon: List, desc: 'Manage GL accounts and structure' },
                { name: 'Journal Entries', path: '/accounting', icon: FileText, desc: 'Record financial transactions' },
                { name: 'GL Reports', path: '/accounting/reports', icon: BarChart3, desc: 'Financial statements and trial balance' },
            ]
        },
        {
            title: 'Sub-Ledgers',
            links: [
                { name: 'Accounts Payable', path: '/accounting/ap', icon: Receipt, desc: 'Manage vendor invoices and payments' },
                { name: 'Accounts Receivable', path: '/accounting/ar', icon: DollarSign, desc: 'Manage customer invoices and receipts' },
                { name: 'Fixed Assets', path: '/accounting/fixed-assets', icon: Building, desc: 'Track and depreciate assets' },
            ]
        },
        {
            title: 'Setup',
            links: [
                { name: 'Currencies', path: '/accounting/currencies', icon: Coins, desc: 'Manage exchange rates and FX' },
            ]
        }
    ];

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Accounting Dashboard"
                    subtitle="Central control for financial operations and reporting."
                    icon={<Wallet size={22} />}
                    backButton={false}
                />

                <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                    gap: '1.5rem',
                    marginBottom: '3rem'
                }}>
                    {summaryCards.map((card) => (
                        <div key={card.name} className="card glass animate-fade" style={{ padding: '1.5rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                                <div style={{
                                    width: '40px',
                                    height: '40px',
                                    borderRadius: '10px',
                                    background: `${card.color}15`,
                                    color: card.color,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center'
                                }}>
                                    <card.icon size={20} />
                                </div>
                            </div>
                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600, letterSpacing: '0.05em', marginBottom: '0.25rem' }}>
                                {card.name}
                            </div>
                            <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: '0.5rem' }}>
                                {formatCurrency(card.value)}
                            </div>
                            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: 0 }}>
                                {card.desc}
                            </p>
                        </div>
                    ))}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
                    {sections.map((section) => (
                        <div key={section.title}>
                            <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, marginBottom: '1.25rem', color: 'var(--color-text)' }}>
                                {section.title}
                            </h2>
                            <div style={{
                                display: 'grid',
                                gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                                gap: '1.5rem'
                            }}>
                                {section.links.map((link) => (
                                    <div
                                        key={link.name}
                                        className="card glass animate-fade"
                                        style={{
                                            cursor: 'pointer',
                                            padding: '1.5rem',
                                            transition: 'var(--transition)',
                                            display: 'flex',
                                            flexDirection: 'column',
                                            gap: '1rem'
                                        }}
                                        onClick={() => navigate(link.path)}
                                        onMouseOver={(e) => {
                                            e.currentTarget.style.transform = 'translateY(-4px)';
                                            e.currentTarget.style.borderColor = 'var(--color-primary)';
                                        }}
                                        onMouseOut={(e) => {
                                            e.currentTarget.style.transform = 'translateY(0)';
                                            e.currentTarget.style.borderColor = 'var(--color-border)';
                                        }}
                                    >
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                            <div style={{
                                                width: '40px',
                                                height: '40px',
                                                borderRadius: '10px',
                                                background: 'rgba(36, 113, 163, 0.1)',
                                                color: 'var(--color-primary)',
                                                display: 'flex',
                                                alignItems: 'center',
                                                justifyContent: 'center'
                                            }}>
                                                <link.icon size={20} />
                                            </div>
                                            <div style={{ fontWeight: 600 }}>{link.name}</div>
                                        </div>
                                        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', lineHeight: '1.5' }}>
                                            {link.desc}
                                        </p>
                                        <div style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '0.25rem',
                                            fontSize: 'var(--text-xs)',
                                            fontWeight: 600,
                                            color: 'var(--color-primary)',
                                            marginTop: 'auto'
                                        }}>
                                            Launch <ArrowRight size={14} />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            </main>
        </div>
    );
};

export default AccountingDashboard;
