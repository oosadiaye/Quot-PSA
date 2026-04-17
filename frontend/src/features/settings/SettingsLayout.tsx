import { Settings, ChevronRight } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import BackButton from '../../components/BackButton';

interface SettingsLayoutProps {
    children: React.ReactNode;
    title?: string;
    breadcrumb?: string;
    icon?: React.ReactNode;
    gradient?: string;
    gradientShadow?: string;
    subtitle?: string;
    maxWidth?: string;
}

export default function SettingsLayout({
    children,
    title = 'Accounting Settings',
    breadcrumb = 'Accounting',
    icon,
    gradient = 'linear-gradient(135deg, #242a88, #2e35a0)',
    gradientShadow = 'rgba(36, 42, 136, 0.25)',
    subtitle,
    maxWidth = '920px',
}: SettingsLayoutProps) {
    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <div style={{
                flex: 1, marginLeft: '260px', minHeight: '100vh',
                background: '#f8fafc',
                fontFamily: "'Inter', -apple-system, sans-serif",
            }}>
                {/* Page Header */}
                <div style={{
                    padding: '24px 40px 20px',
                    borderBottom: '1px solid #e2e8f0',
                    background: 'white',
                }}>
                    <BackButton />
                    <div style={{
                        display: 'flex', alignItems: 'center', gap: '14px',
                        marginTop: '10px',
                    }}>
                        <div style={{
                            width: '44px', height: '44px', borderRadius: '14px',
                            background: gradient,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            boxShadow: `0 4px 12px ${gradientShadow}`,
                        }}>
                            {icon || <Settings size={22} color="white" />}
                        </div>
                        <div>
                            <h1 style={{
                                fontSize: '22px', fontWeight: 800, color: '#0f172a',
                                margin: 0, letterSpacing: '-0.3px',
                            }}>
                                {title}
                            </h1>
                            {subtitle && (
                                <p style={{
                                    fontSize: '13px', color: '#94a3b8', margin: '2px 0 0',
                                    maxWidth: '500px',
                                }}>
                                    {subtitle}
                                </p>
                            )}
                            <div style={{
                                display: 'flex', alignItems: 'center', gap: '4px',
                                fontSize: '13px', color: '#94a3b8', marginTop: '2px',
                            }}>
                                <span>Settings</span>
                                <ChevronRight size={12} />
                                <span style={{ color: '#64748b', fontWeight: 500 }}>{breadcrumb}</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div style={{ padding: '32px 40px 48px', maxWidth }}>
                    <main>{children}</main>
                </div>
            </div>
        </div>
    );
}
