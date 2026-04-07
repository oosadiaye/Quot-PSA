import { NavLink, useLocation } from 'react-router-dom';
import { BarChart3, Search, AlertTriangle, UserPlus, ClipboardCheck, Gauge, BadgeCheck } from 'lucide-react';

const tabs = [
    { name: 'Dashboard', path: '/quality/dashboard', icon: BarChart3 },
    { name: 'Inspections', path: '/quality/inspections', icon: Search },
    { name: 'Non-Conformance', path: '/quality/ncr', icon: AlertTriangle },
    { name: 'Complaints', path: '/quality/complaints', icon: UserPlus },
    { name: 'Checklists', path: '/quality/checklists', icon: ClipboardCheck },
    { name: 'Calibrations', path: '/quality/calibrations', icon: Gauge },
    { name: 'Supplier Quality', path: '/quality/supplier-quality', icon: BadgeCheck },
];

const QualityLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const location = useLocation();

    return (
        <div style={{ display: 'flex', minHeight: '100vh' }}>
            <aside style={{
                width: '240px',
                background: 'var(--color-surface)',
                borderRight: '1px solid var(--color-border)',
                padding: '1rem 0',
                flexShrink: 0,
            }}>
                <div style={{ padding: '0 1rem 1rem', borderBottom: '1px solid var(--color-border)', marginBottom: '1rem' }}>
                    <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                        Quality Management
                    </h2>
                    <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: '0.25rem 0 0' }}>
                        Quality control & assurance
                    </p>
                </div>
                <nav>
                    {tabs.map((tab) => {
                        const isActive = location.pathname === tab.path;
                        return (
                            <NavLink
                                key={tab.path}
                                to={tab.path}
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.75rem',
                                    padding: '0.625rem 1rem',
                                    color: isActive ? 'var(--color-primary)' : 'var(--color-text-muted)',
                                    background: isActive ? 'rgba(36, 113, 163, 0.1)' : 'transparent',
                                    borderLeft: isActive ? '3px solid var(--color-primary)' : '3px solid transparent',
                                    textDecoration: 'none',
                                    fontSize: 'var(--text-sm)',
                                    fontWeight: isActive ? 600 : 400,
                                    transition: 'all 0.15s ease',
                                }}
                            >
                                <tab.icon size={18} />
                                {tab.name}
                            </NavLink>
                        );
                    })}
                </nav>
            </aside>
            <main style={{ flex: 1, overflow: 'auto' }}>
                {children}
            </main>
        </div>
    );
};

export default QualityLayout;
