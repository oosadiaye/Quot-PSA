import React from 'react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import {
    FileText,
    ShoppingCart,
    Package,
    CheckCircle,
    TrendingUp,
    Building,
    ArrowRight,
    ClipboardList,
    Truck
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { usePurchaseRequests, usePurchaseOrders, useGRNs } from './hooks/useProcurement';
import LoadingScreen from '../../components/common/LoadingScreen';

const ProcurementDashboard = () => {
    const navigate = useNavigate();

    const { data: requests, isLoading: loadingPR } = usePurchaseRequests();
    const { data: orders, isLoading: loadingPO } = usePurchaseOrders();
    const { data: grns, isLoading: loadingGRN } = useGRNs();

    if (loadingPR || loadingPO || loadingGRN) {
        return <LoadingScreen message="Loading procurement metrics..." />;
    }

    const prList = requests?.results || requests || [];
    const poList = orders?.results || orders || [];
    const grnList = grns?.results || grns || [];

    const totalPR = prList.length;
    const totalPO = poList.length;
    const totalGRN = grnList.length;
    const pendingPO = poList.filter((po: any) => po.status === 'Draft' || po.status === 'Sent').length;

    const summaryCards = [
        { name: 'Total Requisitions', value: totalPR, icon: ClipboardList, color: '#8b5cf6', desc: 'Total PRs submitted' },
        { name: 'Purchase Orders', value: totalPO, icon: ShoppingCart, color: '#2471a3', desc: 'Total orders placed' },
        { name: 'Goods Received', value: totalGRN, icon: Package, color: '#10b981', desc: 'Recorded receipts' },
        { name: 'Pending Orders', value: pendingPO, icon: Truck, color: '#f59e0b', desc: 'Orders awaiting delivery/GRN' },
    ];

    const sections = [
        {
            title: 'Purchasing Workflow',
            links: [
                { name: 'Purchase Requisitions', path: '/procurement/requisitions', icon: FileText, desc: 'Submit and approve purchase requests' },
                { name: 'Purchase Orders', path: '/procurement/orders', icon: ShoppingCart, desc: 'Manage orders sent to vendors' },
                { name: 'Goods Received Notes', path: '/procurement/grn', icon: Package, desc: 'Record received inventory items' },
            ]
        },
        {
            title: 'Analysis & Compliance',
            links: [
                { name: '3-Way Matching', path: '/procurement/matching', icon: CheckCircle, desc: 'Verify PO vs Receipt vs Invoice' },
                { name: 'Vendor Performance', path: '/procurement/vendor-performance', icon: TrendingUp, desc: 'Analyze vendor reliability and quality' },
                { name: 'Vendor Directory', path: '/procurement/vendors', icon: Building, desc: 'Manage approved vendor list' },
            ]
        }
    ];

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Procurement Dashboard"
                    subtitle="Manage the full procure-to-pay lifecycle."
                    icon={<ShoppingCart size={22} />}
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
                                {card.value}
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
                                            e.currentTarget.style.borderColor = '#8b5cf6';
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
                                                background: 'rgba(139, 92, 246, 0.1)',
                                                color: '#8b5cf6',
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
                                            color: '#8b5cf6',
                                            marginTop: 'auto'
                                        }}>
                                            Launch Module <ArrowRight size={14} />
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

export default ProcurementDashboard;
