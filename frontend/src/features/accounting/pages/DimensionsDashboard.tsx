import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import {
    Wallet,
    BarChart3,
    FileText,
    MapPin,
    ArrowRight,
    Layers,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const DimensionsDashboard = () => {
    const navigate = useNavigate();

    const dimensions = [
        {
            name: 'Funds',
            path: '/accounting/dimensions/funds',
            icon: Wallet,
            color: '#2471a3',
            description: 'Public sector fund accounting — track revenue sources, grants, and designated funds.',
        },
        {
            name: 'Functions',
            path: '/accounting/dimensions/functions',
            icon: BarChart3,
            color: '#8b5cf6',
            description: 'Functional classification of expenditure — group spending by purpose or department.',
        },
        {
            name: 'Programs',
            path: '/accounting/dimensions/programs',
            icon: FileText,
            color: '#10b981',
            description: 'Program-based budgeting — link financial data to strategic programs and objectives.',
        },
        {
            name: 'Geo Locations',
            path: '/accounting/dimensions/geos',
            icon: MapPin,
            color: '#f59e0b',
            description: 'Geographic classification — track spending and allocation by region or location.',
        },
    ];

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Dimensions"
                    subtitle="Multi-dimensional accounting -- manage Funds, Functions, Programs, and Geographic classifications."
                    icon={<Layers size={22} />}
                />

                <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                    gap: '1.5rem',
                }}>
                    {dimensions.map((dim) => (
                        <div
                            key={dim.name}
                            className="card glass animate-fade"
                            style={{
                                cursor: 'pointer',
                                padding: '1.75rem',
                                transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                                border: '1px solid var(--color-border)',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '1rem',
                            }}
                            onClick={() => navigate(dim.path)}
                            onMouseOver={(e) => {
                                e.currentTarget.style.transform = 'translateY(-6px)';
                                e.currentTarget.style.borderColor = dim.color;
                            }}
                            onMouseOut={(e) => {
                                e.currentTarget.style.transform = 'translateY(0)';
                                e.currentTarget.style.borderColor = 'var(--color-border)';
                            }}
                        >
                            <div style={{
                                width: '48px',
                                height: '48px',
                                borderRadius: '12px',
                                background: `${dim.color}15`,
                                color: dim.color,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                            }}>
                                <dim.icon size={24} />
                            </div>
                            <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: '#000000' }}>{dim.name}</h3>
                            <p style={{ color: '#374151', fontSize: 'var(--text-sm)', lineHeight: '1.7', fontWeight: 450 }}>
                                {dim.description}
                            </p>
                            <div style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.5rem',
                                color: dim.color,
                                fontWeight: 700,
                                fontSize: 'var(--text-sm)',
                                marginTop: 'auto',
                            }}>
                                Manage {dim.name} <ArrowRight size={16} />
                            </div>
                        </div>
                    ))}
                </div>
            </main>
        </div>
    );
};

export default DimensionsDashboard;
